"""Parse fallback chain for the Nerd Referee profile harvester.

Round 2 of the harvester overhaul. Escalation order when the primary
mwparserfromhell path fails or leaks markup into extracted values:

    1. mwparserfromhell  (existing extract_vsbattles_fields in auto_profile_harvester)
    2. wikitextparser    (second-pass on the same wikitext)
    3. rendered HTML     (action=parse + BeautifulSoup, "Powers and Stats" section)
    4. LLM extraction    (instructor + Ollama; env-gated, last resort)

Every parse result records which parser handled the page:

    parser_used:       mwparserfromhell | wikitextparser | rendered_html | llm
    extraction_method: parser | wikitextparser | rendered_html | llm
                       (persisted on character_profiles.extraction_method)

LLM fallback is OFF unless the environment variable
``HARVEST_LLM_FALLBACK=1`` is set. Use extract_with_llm() directly for
offline evaluation.

All imports of auto_profile_harvester are deferred to call time so this
module never creates an import cycle and never hard-fails if optional
parse libraries are missing.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Awaitable, Callable

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PARSER_MWPARSE = "mwparserfromhell"
PARSER_WIKITEXTPARSER = "wikitextparser"
PARSER_RENDERED_HTML = "rendered_html"
PARSER_LLM = "llm"

METHOD_FOR_PARSER = {
    PARSER_MWPARSE: "parser",
    PARSER_WIKITEXTPARSER: "wikitextparser",
    PARSER_RENDERED_HTML: "rendered_html",
    PARSER_LLM: "llm",
}

HTML_SECTION_TARGETS = (
    "powers and stats",
    "powers & stats",
    "powers and abilities",
    "statistics",
)

DEFAULT_OLLAMA_BASE_URL = os.getenv("HARVEST_OLLAMA_URL", "http://192.168.1.207:11434")
DEFAULT_OLLAMA_MODEL = os.getenv("HARVEST_OLLAMA_MODEL", "qwen2.5:3b")
LLM_MAX_WIKITEXT_CHARS = int(os.getenv("HARVEST_LLM_MAX_CHARS", "6000"))
# AltProx Ollama box is CPU-only: full extractions take minutes.
LLM_TIMEOUT_SECONDS = float(os.getenv("HARVEST_LLM_TIMEOUT", "600"))

EXTRACTION_METHOD_MIGRATION_SQL = (
    "ALTER TABLE character_profiles "
    "ADD COLUMN IF NOT EXISTS extraction_method text NOT NULL DEFAULT 'parser';"
)


def llm_fallback_enabled() -> bool:
    """True only when HARVEST_LLM_FALLBACK=1 (default off)."""
    return os.getenv("HARVEST_LLM_FALLBACK", "0") == "1"


# ---------------------------------------------------------------------------
# Step 1b -- markup leak detection
# ---------------------------------------------------------------------------

# Residual MediaWiki markup that should never survive field extraction.
# Each entry: (leak_name, compiled_pattern)
_LEAK_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("unresolved_template", re.compile(r"\{\{|\}\}")),
    ("unresolved_link", re.compile(r"\[\[|\]\]")),
    ("tabber_tag", re.compile(r"(?i)<\s*/?\s*tabber\b|\{\{\s*#tag\s*:\s*tabber")),
    ("tabber_separator", re.compile(r"\|-\|")),
    ("table_markup", re.compile(r"(?m)^\s*\{\||^\s*!\s*[-+]")),
    ("html_comment", re.compile(r"<!--")),
    ("magic_word", re.compile(r"__[A-Z]+__")),
)


def detect_markup_leak(fields: dict[str, Any]) -> dict[str, list[str]]:
    """Scan extracted field values for leaked MediaWiki markup.

    Returns {field_name: [leak_names...]} for offending fields, {} if clean.
    """
    leaks: dict[str, list[str]] = {}
    for key, value in fields.items():
        if not isinstance(value, str) or not value:
            continue
        hits = [name for name, pattern in _LEAK_PATTERNS if pattern.search(value)]
        if hits:
            leaks[str(key)] = hits
    return leaks


def has_markup_leak(fields: dict[str, Any]) -> bool:
    """True when any extracted value still contains raw MediaWiki markup."""
    return bool(detect_markup_leak(fields))


# ---------------------------------------------------------------------------
# Step 2 -- wikitextparser second pass
# ---------------------------------------------------------------------------

def _aph():
    """Deferred import of auto_profile_harvester (avoids import cycles)."""
    from battlebot.harvest import auto_profile_harvester

    return auto_profile_harvester


_TABBER_TAG_RE = re.compile(r"(?is)<tabber[^>]*>(.*?)</tabber\s*>")
_TABBER_HEADER_RE = re.compile(r"^\s*[A-Za-z][A-Za-z0-9 /&\-.]*\s*=\s*(.*)$")


def _expand_tabber_tags(wikitext: str) -> str:
    """Expand <tabber>...</tabber> blocks into plain concatenated tab contents.

    wikitextparser keeps extension tags in plain_text(); expanding them up
    front stops <tabber> fragments and |-| separators leaking into values.
    """

    def _sub(match: re.Match[str]) -> str:
        inner = re.sub(r"\|-\|", "\n", match.group(1))
        out: list[str] = []
        for line in inner.split("\n"):
            header = _TABBER_HEADER_RE.match(line)
            if header:
                rest = header.group(1).strip()
                if rest:
                    out.append(rest)
                # pure "TabName=" header line: drop it
            else:
                out.append(line)
        return "\n".join(out)

    return _TABBER_TAG_RE.sub(_sub, wikitext or "")


def _scrub_value(value: str) -> str:
    """Remove tabber/table residue that can survive template stripping."""
    value = re.sub(r"\|-\|", " ", value)
    value = _TABBER_TAG_RE.sub(" ", value)
    value = re.sub(r"(?i)<\s*/?\s*tabber[^>]*>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def parse_with_wikitextparser(wikitext: str) -> dict[str, str]:
    """Re-parse wikitext with wikitextparser after mwparserfromhell leaked.

    Uses wikitextparser's own template-argument model (a genuinely different
    parse path from mwparserfromhell) plus the harvester's standard label
    extractors run over template-stripped plain text.
    """
    import wikitextparser as wtp

    aph = _aph()
    fields: dict[str, str] = {}

    parsed = wtp.parse(_expand_tabber_tags(wikitext))

    # Pass A: template arguments via wikitextparser's argument model.
    for tmpl in parsed.templates:
        for arg in tmpl.arguments:
            canon = aph.field_alias(aph.normalize_field_name(str(arg.name)))
            if not canon or canon in fields:
                continue
            raw_value = str(arg.value).strip()
            if not raw_value:
                continue
            # Strip nested templates/links inside the value with wikitextparser
            # itself (plain_text keeps link display text, drops template bodies).
            value = aph.normalize_text(wtp.parse(raw_value).plain_text())
            value = _scrub_value(value)
            if value and not has_markup_leak({canon: value}):
                fields[canon] = value

    # Pass B: the harvester's label-line extractors over template-free text.
    plain = aph.normalize_text(parsed.plain_text())
    for extractor in (
        aph.extract_inline_labeled_fields,
        aph.extract_delimiterless_labeled_fields,
    ):
        for key, value in extractor(plain).items():
            value = _scrub_value(value)
            if key not in fields and value and not has_markup_leak({key: value}):
                fields[key] = value
    for key, value in aph.extract_section_fields(plain).items():
        if key not in fields or (
            key == "powers_and_abilities" and len(value) > len(fields.get(key, ""))
        ):
            fields[key] = value
    return fields


# ---------------------------------------------------------------------------
# Step 3 -- rendered HTML fallback (nuclear option)
# ---------------------------------------------------------------------------

def extract_from_rendered_html(html: str) -> dict[str, str]:
    """Extract stat fields from rendered page HTML via BeautifulSoup.

    Finds the "Powers and Stats" (or equivalent) heading and converts the
    section body into the harvester's canonical labeled-field structure.
    Returns {} when no usable section is found.
    """
    from bs4 import BeautifulSoup

    aph = _aph()
    fields: dict[str, str] = {}
    if not html:
        return fields

    soup = BeautifulSoup(html, "lxml")

    heading = None
    for tag in soup.find_all(["h1", "h2", "h3", "h4"]):
        text = tag.get_text(" ", strip=True).lower()
        if any(target in text for target in HTML_SECTION_TARGETS):
            heading = tag
            break
    if heading is None:
        return fields

    # Collect the section body up to the next heading of equal/higher rank.
    level = int(heading.name[1]) if heading.name[1].isdigit() else 2
    chunks: list[str] = []
    for sibling in heading.find_next_siblings():
        name = getattr(sibling, "name", None)
        if name and name.startswith("h") and name[1:].isdigit() and int(name[1:]) <= level:
            break
        chunks.append(sibling.get_text("\n", strip=True))
    raw_section = "\n".join(c for c in chunks if c)
    # Normalize per line: collapsing whitespace first would destroy the
    # line structure the label-line extractors depend on.
    lines = [aph.normalize_text(line) for line in raw_section.splitlines()]
    lines = [line for line in lines if line]
    section_text = "\n".join(lines)
    if not section_text:
        return fields
    # Rendered VSB HTML puts label, colon, and value on separate lines
    # ("Tier" / ":" / "At least" / "5-A"), so skip lone separator lines and
    # glue continuation lines until the next label-like line.
    _LABELISH_RE = re.compile(r"^[A-Za-z][A-Za-z0-9 /&'()\-.,]*:\s*$")

    def _looks_like_label(text: str) -> bool:
        if aph.parse_field_line(text):
            return True
        # normalize_field_name keeps trailing colons, so strip separators
        # before aliasing ("Name:" -> "name").
        stripped = text.rstrip(":\uff1a-\u2013 ").strip()
        if not stripped:
            return True  # lone separator line
        if aph.field_alias(aph.normalize_field_name(stripped)) is not None:
            return True
        # Structural: short line ending in a colon ("Name:", "Age:") even
        # when the label has no canonical alias.
        return bool(_LABELISH_RE.match(text)) and len(text) <= 40

    index = 0
    while index < len(lines):
        line = lines[index]
        parsed = aph.parse_field_line(line)
        if parsed:
            key, value = parsed
            fields.setdefault(key, value)
            index += 1
            continue
        header = aph.normalize_field_name(line)
        canonical = aph.field_alias(header)
        if canonical:
            value_at = index + 1
            while value_at < len(lines) and lines[value_at] in (":", "\uff1a", "-", "\u2013"):
                value_at += 1
            if value_at < len(lines):
                parts = [lines[value_at]]
                nxt = value_at + 1
                while nxt < len(lines) and not _looks_like_label(lines[nxt]):
                    parts.append(lines[nxt])
                    nxt += 1
                fields.setdefault(canonical, " ".join(parts))
                index = nxt
                continue
        index += 1
    for extractor in (
        aph.extract_inline_labeled_fields,
        aph.extract_delimiterless_labeled_fields,
    ):
        for key, value in extractor(section_text).items():
            if key not in fields and value:
                fields[key] = value
    return fields


# ---------------------------------------------------------------------------
# Step 4 -- LLM extraction (last resort, env-gated)
# ---------------------------------------------------------------------------

try:
    from pydantic import BaseModel, Field
except ImportError:  # pragma: no cover - evaluated at import time
    BaseModel = None  # type: ignore[assignment]
    Field = None  # type: ignore[assignment]


if BaseModel is not None:

    class CharacterStats(BaseModel):
        """Structured character stats extracted by the LLM fallback."""

        tier: str = Field(default="", description="Tier rating, e.g. '9-A', 'High 6-C'")
        attack_potency: str = Field(default="", description="Attack Potency stat line")
        speed: str = Field(default="", description="Speed stat line")
        durability: str = Field(default="", description="Durability stat line")
        powers: list[str] = Field(
            default_factory=list,
            description="Powers and abilities, one short entry per item",
        )
        key_forms: list[str] = Field(
            default_factory=list,
            description="Named keys/forms/versions of the character",
        )
        notes: str = Field(default="", description="Brief extraction notes or caveats")

        def to_canonical_fields(self) -> dict[str, str]:
            """Map the LLM model onto the harvester's canonical field names."""
            from battlebot.harvest import auto_profile_harvester as aph

            fields: dict[str, str] = {}
            for attr, canon in (
                ("tier", "tier"),
                ("attack_potency", "attack_potency"),
                ("speed", "speed"),
                ("durability", "durability"),
            ):
                value = aph.normalize_text(str(getattr(self, attr) or ""))
                if value:
                    fields[canon] = value
            if self.powers:
                fields["powers_and_abilities"] = "\n".join(
                    f"- {aph.normalize_text(p)}" for p in self.powers if str(p).strip()
                )
            if self.key_forms:
                fields["keys"] = "; ".join(
                    aph.normalize_text(k) for k in self.key_forms if str(k).strip()
                )
            if self.notes:
                fields["extraction_notes"] = aph.normalize_text(self.notes)
            return fields

else:  # pragma: no cover

    class CharacterStats:  # type: ignore[no-redef]
        def __init__(self, **kwargs: Any) -> None:
            raise RuntimeError("pydantic is required for the LLM fallback")


_LLM_SYSTEM_PROMPT = """You extract versus-battle character statistics from wiki page text.
Return ONLY the fields you can actually find in the provided text.
Use empty strings / empty lists for anything not present. Do not invent stats.
Keep each value short: the stat line as written on the page.
Powers: one concise ability per list item, no duplicates."""


def extract_with_llm(
    text: str,
    *,
    title: str = "",
    ollama_base_url: str = DEFAULT_OLLAMA_BASE_URL,
    model: str = DEFAULT_OLLAMA_MODEL,
    max_chars: int = LLM_MAX_WIKITEXT_CHARS,
    timeout: float | None = None,
) -> "CharacterStats | None":
    """Extract CharacterStats from page text via instructor + Ollama.

    Last-resort path: only called when every wikitext/HTML parser failed.
    Returns None on any error (never raises into the harvester).
    """
    if BaseModel is None:
        log.warning("llm fallback unavailable: pydantic not installed")
        return None
    if not (text or "").strip():
        return None
    if timeout is None:
        timeout = LLM_TIMEOUT_SECONDS
    try:
        from openai import OpenAI
        import instructor
    except ImportError as exc:
        log.warning("llm fallback unavailable: %s", exc)
        return None

    try:
        client = instructor.from_openai(
            OpenAI(
                base_url=ollama_base_url.rstrip("/") + "/v1",
                api_key="ollama",
                timeout=timeout,
            ),
            mode=instructor.Mode.JSON,
        )
        stats = client.chat.completions.create(
            model=model,
            response_model=CharacterStats,
            messages=[
                {"role": "system", "content": _LLM_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Character page: {title}\n\n"
                        f"Page text:\n{(text or '')[:max_chars]}"
                    ),
                },
            ],
            max_retries=2,
        )
        return stats
    except Exception as exc:
        log.warning("llm extraction failed for %r: %s", title, exc)
        return None


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

async def run_parse_fallback_chain(
    *,
    wikitext: str,
    title: str = "",
    first_pass_fields: dict[str, str] | None = None,
    fetch_rendered_html: Callable[[], Awaitable[str]] | None = None,
    min_core_fields: int = 3,
) -> dict[str, Any]:
    """Run the full parse fallback chain for one page's wikitext.

    Chain: mwparserfromhell -> wikitextparser -> rendered HTML -> LLM.

    Each step only runs when the previous one failed, where "failed" means
    markup leaked into extracted values or fewer than ``min_core_fields``
    core fields were recovered. Any exception keeps the best fields found
    so far; this function does not raise for parse-level failures.

    Returns a dict with:
        fields            merged canonical fields
        parser_used       mwparserfromhell | wikitextparser | rendered_html | llm
        extraction_method parser | wikitextparser | rendered_html | llm
        leak              {field: [leak names]} from the first pass
        used_rendered_html bool (caller may need the parse record)
        rendered_text     str (plain text of rendered HTML, when fetched;
                           also fed to the LLM fallback)
    """
    aph = _aph()

    fields = dict(first_pass_fields) if first_pass_fields is not None else aph.extract_vsbattles_fields(wikitext or "")
    parser_used = PARSER_MWPARSE
    leak = detect_markup_leak(fields)
    rendered_text = ""
    used_rendered_html = False

    def _core_ok(current: dict[str, str]) -> bool:
        return aph.count_core_fields(current) >= min_core_fields

    # Step 2: wikitextparser second pass on leak or weak parse.
    if leak or not _core_ok(fields):
        try:
            wtp_fields = parse_with_wikitextparser(wikitext or "")
            clean_first = {k: v for k, v in fields.items() if k not in leak}
            merged = aph.merge_extracted_fields(clean_first, wtp_fields)
            # Leaked values are poison: judge step 2 against the clean
            # baseline, not against the poisoned first pass.
            baseline = aph.count_core_fields(clean_first)
            if wtp_fields and aph.count_core_fields(merged) >= baseline:
                fields = merged
                parser_used = PARSER_WIKITEXTPARSER
        except Exception as exc:
            log.warning("wikitextparser fallback failed for %r: %s", title, exc)

    # Step 3: rendered HTML via action=parse. A result that still leaks
    # markup after the wikitextparser pass counts as failed too.
    # fetch_rendered_html MUST return raw HTML (not stripped text) so
    # BeautifulSoup can locate the "Powers and Stats" section.
    if (not _core_ok(fields) or has_markup_leak(fields)) and fetch_rendered_html is not None:
        try:
            rendered_html = await fetch_rendered_html()
            html_fields = extract_from_rendered_html(rendered_html)
            if html_fields:
                fields = aph.merge_extracted_fields(fields, html_fields)
                parser_used = PARSER_RENDERED_HTML
                used_rendered_html = True
                from bs4 import BeautifulSoup

                rendered_text = BeautifulSoup(rendered_html, "lxml").get_text("\n")
        except Exception as exc:
            log.warning("rendered-html fallback failed for %r: %s", title, exc)

    # Step 4: LLM extraction, only when explicitly enabled.
    if not _core_ok(fields) and llm_fallback_enabled():
        try:
            stats = extract_with_llm(
                rendered_text or (wikitext or ""), title=title
            )
            if stats is not None:
                llm_fields = stats.to_canonical_fields()
                if llm_fields:
                    fields = aph.merge_extracted_fields(fields, llm_fields)
                    parser_used = PARSER_LLM
        except Exception as exc:
            log.warning("llm fallback failed for %r: %s", title, exc)

    return {
        "fields": fields,
        "parser_used": parser_used,
        "extraction_method": METHOD_FOR_PARSER[parser_used],
        "leak": leak,
        "used_rendered_html": used_rendered_html,
        "rendered_text": rendered_text,
    }


# ---------------------------------------------------------------------------
# Idempotent migration for character_profiles.extraction_method
# ---------------------------------------------------------------------------

async def ensure_extraction_method_column(connection: Any) -> None:
    """Add character_profiles.extraction_method idempotently (safe to rerun)."""
    await connection.execute(EXTRACTION_METHOD_MIGRATION_SQL)

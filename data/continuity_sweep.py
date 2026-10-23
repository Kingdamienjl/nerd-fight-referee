#!/usr/bin/env python3
"""Continuity recorded-source repair sweep (Job 2, 2026-10-22).

For every version-scoped profile, check its recorded sources: a RESOLVED
source (revision_id present) whose recorded page title names a DIFFERENT
continuity than the profile scope is proven-wrong evidence plumbing.
  - If the correct-continuity page exists on the source's own wiki (API
    titles+redirects lookup with the scope's disambiguator candidates) and
    resolving it does not cross continuity, rewrite the entry to that page
    (revision/fetch cleared for refetch; provenance stamped).
  - Otherwise mark the entry continuity_suspect so repair/recovery skip it.
Single-label stubs whose title mismatch is provable also become suspect.
Profiles whose power/ability scaling cites a proven-bad resolved source are
reported in stamped_profiles for the live audit.

Dry-run by default; --apply writes. Report -> data/continuity_sweep_report.json
"""
import datetime
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

from battlebot.profiles import yaml_io
from battlebot.review import auto_repair as ar
from battlebot.review import service


def _text(value) -> str:
    return str(value or "").strip()


def _canonical_text(value) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-")


def resolve_page(source_url: str, title: str):
    """Existence + redirect resolution on the source's own wiki.

    Returns {"exists": bool, "title": final title, "url": full url} or
    None when the wiki cannot be queried. Fandom/Wikipedia both serve
    api.php at the host root.
    """
    if not source_url or not title:
        return None
    parts = urllib.parse.urlparse(source_url)
    if not parts.scheme or not parts.netloc:
        return None
    api = f"{parts.scheme}://{parts.netloc}/api.php"
    query = urllib.parse.urlencode({
        "action": "query", "format": "json", "formatversion": "2",
        "titles": title, "redirects": "1", "prop": "info", "inprop": "url",
    })
    request = urllib.request.Request(
        f"{api}?{query}", headers={"User-Agent": "referee-continuity-sweep/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = json.loads(response.read().decode("utf-8"))
    except Exception:
        return None
    pages = (body.get("query") or {}).get("pages") or []
    if not pages:
        return {"exists": False, "title": title, "url": ""}
    page = pages[0]
    if page.get("missing"):
        return {"exists": False, "title": page.get("title") or title, "url": ""}
    return {"exists": True, "title": page.get("title") or title,
            "url": page.get("fullurl") or ""}

PROFILES_ROOT = Path("/app/profiles")
REPORT_PATH = Path("/app/data/continuity_sweep_report.json")
PROVIDER_BY_KEY = {
    "vsbattles": "vsbattles",
    "fandom": "fandom",
    "marvel": "marvel",
    "dc": "dc",
    "wikipedia": "wikipedia",
    "character-stats-and-profiles-wiki": "cspw",
    "characterstatprofiles": "cspw",
}
SCOPE_DISAMBIGUATORS = {
    "post-crisis": ["Post-Crisis", "New Earth"],
    "new-earth": ["New Earth", "Post-Crisis"],
    "post-flashpoint": ["Post-Flashpoint", "Prime Earth", "New 52"],
    "prime-earth": ["Prime Earth", "Post-Flashpoint", "New 52"],
    "new-52": ["New 52", "Prime Earth", "Post-Flashpoint"],
    "earth-0": ["Prime Earth", "Post-Flashpoint", "New 52"],
    "rebirth": ["Rebirth", "Post-Flashpoint"],
    "dc-comics": [],
    "marvel-comics": [],
    "earth-616": ["Earth-616"],
    "earth-1610": ["Earth-1610", "Ultimate Universe"],
    "ultimate-universe": ["Ultimate Universe", "Earth-1610"],
    "mcu": ["Marvel Cinematic Universe"],
    "dcau": ["DC Animated Universe"],
    "dceu": ["DC Extended Universe"],
}


def provider_for(source):
    key = _canonical_text(source.get("id") or "") \
        or _canonical_text(source.get("url") or "")
    tokens = set(key.split("-"))
    for fragment, provider in PROVIDER_BY_KEY.items():
        if fragment in tokens or fragment in key:
            return provider
    return None


def base_name(profile):
    name = _text(profile.get("name"))
    for suffix in (" (", " ["):
        if suffix in name:
            return name.split(suffix)[0].strip()
    return name


def resolve_correct_page(profile, source, scope_key, provider):
    candidates = SCOPE_DISAMBIGUATORS.get(scope_key)
    if candidates is None:
        return None
    base = base_name(profile)
    for disambiguator in candidates:
        title = f"{base} ({disambiguator})"
        try:
            info = resolve_page(source.get("url") or "", title)
        except Exception:
            return None
        if not isinstance(info, dict) or not info.get("exists"):
            continue
        resolved_title = _text(info.get("title"))
        verdict = ar.continuity_check(profile, page_title=resolved_title, page_url=info.get("url") or "")
        if not verdict["mismatch"] and ar._title_continuity(resolved_title)[0]:
            return {"title": resolved_title, "url": info.get("url") or ""}
    return None


def main() -> int:
    apply = "--apply" in sys.argv
    report = {"generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "apply": apply, "scanned": 0, "scoped": 0, "fixed": [], "suspect": [],
              "unresolvable": [], "stamped_profiles": []}
    files = sorted(p for p in PROFILES_ROOT.rglob("*.yaml")
                   if "review_archive" not in p.parts and p.name != "index.json")
    for path in files:
        try:
            profile = yaml_io.load_yaml(path)
        except Exception:
            continue
        if not isinstance(profile, dict):
            continue
        report["scanned"] += 1
        scope_label, _scope_kind, _scope_origin = ar.profile_continuity_scope(profile)
        if not scope_label:
            continue
        report["scoped"] += 1
        scope_key = scope_label
        sources = profile.get("sources")
        if not isinstance(sources, list):
            continue
        changed = False
        bad_resolved_ids = set()
        for entry in sources:
            if not isinstance(entry, dict) or entry.get("continuity_suspect"):
                continue
            title = _text(entry.get("title"))
            verdict = ar.continuity_check(profile, page_title=title or None,
                                          page_url=entry.get("url") or None)
            if not verdict["mismatch"]:
                continue
            resolved = entry.get("revision_id") is not None
            label = verdict["page_continuity"]
            record = {"profile": str(path.relative_to(PROFILES_ROOT)),
                      "source_id": entry.get("id"), "title": title, "url": entry.get("url"),
                      "scope": verdict["profile_scope"],
                      "page_continuity": label or None,
                      "resolved": resolved}
            verdict_done = False
            if resolved:
                bad_resolved_ids.add(_text(entry.get("id")))
                provider = provider_for(entry)
                correct = resolve_correct_page(profile, entry, scope_key, provider) if provider else None
                if correct:
                    record["action"] = "rewrite"
                    record["new_title"] = correct["title"]
                    record["new_url"] = correct["url"]
                    if apply:
                        stamp = {"rule": "continuity_source_repair",
                                 "at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                                 "old_title": title, "old_url": entry.get("url"),
                                 "old_revision_id": entry.get("revision_id"),
                                 "new_title": correct["title"], "new_url": correct["url"]}
                        entry["title"] = correct["title"]
                        entry["url"] = correct["url"]
                        entry["revision_id"] = None
                        entry["fetch_status"] = None
                        entry.pop("continuity_suspect", None)
                        entry.pop("continuity_suspect_reason", None)
                        entry["continuity_repair"] = stamp
                        changed = True
                    report["fixed"].append(record)
                    verdict_done = True
            if not verdict_done:
                record["action"] = "mark_suspect"
                if apply:
                    entry["continuity_suspect"] = True
                    entry["continuity_suspect_reason"] = (
                        f"Recorded page continuity "
                        f"{label} != profile scope "
                        f"{verdict['profile_scope']}")
                    changed = True
                report["suspect"].append(record)
                if not resolved:
                    report["unresolvable"].append(record)
        if bad_resolved_ids:
            cited = set()
            for section in ("power_scale", "abilities"):
                entries = profile.get(section)
                if isinstance(entries, dict):
                    entries = entries.values()
                if isinstance(entries, list):
                    for item in entries:
                        if isinstance(item, dict):
                            for sid in item.get("source_ids") or []:
                                cited.add(_text(sid))
            tainted = sorted(cited & bad_resolved_ids)
            if tainted:
                report["stamped_profiles"].append({
                    "profile": str(path.relative_to(PROFILES_ROOT)),
                    "profile_id": profile.get("profile_id") or profile.get("id"),
                    "status": profile.get("status"),
                    "battle_eligible": bool(profile.get("battle_eligible")),
                    "tainted_source_ids": tainted})
        if changed and apply:
            yaml_io.write_yaml(path, profile)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"scanned": report["scanned"], "scoped": report["scoped"],
                      "fixed": len(report["fixed"]), "suspect": len(report["suspect"]),
                      "stamped": len(report["stamped_profiles"])}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

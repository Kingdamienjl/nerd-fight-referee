from __future__ import annotations

import argparse
import json
import os
import random
import re
import urllib.request
from datetime import datetime
from pathlib import Path

STATE_PATH = Path("logs/proactive/announcer_state.json")


def load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {"posted": []}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def post_webhook(content: str, dry_run: bool) -> None:
    content = content.strip()
    if len(content) > 1900:
        content = content[:1880].rstrip() + "\n..."

    if dry_run:
        print("\n--- DRY RUN DISCORD POST ---")
        print(ai_nerd_sanitize_final_post_text(content))
        return

    webhook_url = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
    if not webhook_url:
        raise SystemExit("DISCORD_WEBHOOK_URL is not set.")

    payload = json.dumps({"content": content}).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "AI-Nerd-Referee-Proactive-Announcer/1.0",
        },
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=30) as response:
        if response.status not in {200, 204}:
            raise RuntimeError(f"Discord webhook returned {response.status}")


def split_social_posts() -> list[str]:
    path = Path("harvest/social_posts_tonight.md")
    if not path.exists():
        return []

    text = path.read_text(encoding="utf-8", errors="ignore")
    chunks = [chunk.strip() for chunk in re.split(r"\n---\n", text) if chunk.strip()]
    return [chunk for chunk in chunks if not chunk.startswith("#")]


def stable_matchup_id_from_post(post: str) -> str:
    for line in post.splitlines():
        clean = line.strip()
        if " VS " in clean:
            clean = re.sub(r"\([^)]*\)", "", clean)
            clean = re.sub(r"\s+", " ", clean).strip().casefold()
            return clean
    return re.sub(r"\s+", " ", post[:80]).strip().casefold()


def add_franchise_to_social_post(post: str) -> str:
    lines = post.splitlines()
    if not lines:
        return post

    # First non-empty line should be "A VS B".
    for i, line in enumerate(lines):
        clean = line.strip()
        if " VS " in clean:
            a, b = clean.split(" VS ", 1)
            lines[i] = f"{display_fighter_name(a.strip())} VS {display_fighter_name(b.strip())}"
            break

    # Also update Winner line where possible.
    for i, line in enumerate(lines):
        if line.startswith("Winner: "):
            winner = line.removeprefix("Winner: ").strip()
            lines[i] = f"Winner: {display_fighter_name(winner)}"

    # Also update Battle odds names where possible.
    for i, line in enumerate(lines):
        if line.startswith("Battle odds: "):
            odds = line.removeprefix("Battle odds: ").strip()
            if " / " in odds:
                left, right = odds.split(" / ", 1)
                left = rewrite_odds_side_with_franchise(left)
                right = rewrite_odds_side_with_franchise(right)
                lines[i] = f"Battle odds: {left} / {right}"

    return "\n".join(lines)


def rewrite_odds_side_with_franchise(text: str) -> str:
    # Converts "Cloud Strife 70%" into "Cloud Strife (Final Fantasy) 70%".
    m = re.match(r"^(.*?)(\s+\d+%)$", text.strip())
    if not m:
        return text

    name, pct = m.groups()
    return f"{display_fighter_name(name.strip())}{pct}"


def make_social_result(state: dict) -> str | None:
    posts = split_social_posts()
    posted = set(state.get("posted") or [])

    for post in posts:
        patched_post = add_franchise_to_social_post(post)
        post_id = "social:" + stable_matchup_id_from_post(patched_post)
        if post_id in posted:
            continue

        state.setdefault("posted", []).append(post_id)
        return "⚔️ **AI Nerd Referee Result**\n\n" + patched_post

    return None



# AI_NERD_PROACTIVE_FRANCHISE_FIX
EXTRA_FRANCHISE_HINTS = {
    "zodd": "Berserk",
    "nosferatu zodd": "Berserk",
    "casca": "Berserk",
    "griffith": "Berserk",
    "guts": "Berserk",
    "father": "Fullmetal Alchemist",
    "roy mustang": "Fullmetal Alchemist",
    "edward elric": "Fullmetal Alchemist",
    "alphonse elric": "Fullmetal Alchemist",
    "muzan kibutsuji": "Demon Slayer",
    "nezuko kamado": "Demon Slayer",
    "tanjiro kamado": "Demon Slayer",
    "yoriichi tsugikuni": "Demon Slayer",
    "toshiro hitsugaya": "Bleach",
    "shunsui kyoraku": "Bleach",
    "ulquiorra cifer": "Bleach",
    "ichigo kurosaki": "Bleach",
    "ikki": "Saint Seiya",
    "nier": "NieR",
    "lina": "Slayers",
    "dante zogratis": "Black Clover",
}

FRANCHISE_HINTS = {
    "kaworu nagisa": "Neon Genesis Evangelion",
    "rei ayanami": "Neon Genesis Evangelion",
    "shinji ikari": "Neon Genesis Evangelion",
    "unit 01": "Neon Genesis Evangelion",
    "unit-01": "Neon Genesis Evangelion",
    "eva unit 01": "Neon Genesis Evangelion",
    "eva unit-01": "Neon Genesis Evangelion",
    "asuka": "Neon Genesis Evangelion",
    "asuka langley soryu": "Neon Genesis Evangelion",
    "lady": "Devil May Cry",
    "quanxi": "Chainsaw Man",
    "sesshomaru": "Inuyasha",
    "nicholas d. wolfwood": "Trigun",
    "millions knives": "Trigun",
    "omni man": "Invincible",
    "omni-man": "Invincible",
    "jinx": "League of Legends",
    "darius": "League of Legends",
    "lucifero": "Black Clover",
    "noble six": "Halo",
    "edea kramer": "Final Fantasy",
    "yoko littner": "Gurren Lagann",
    "ryu": "Street Fighter",
    "ken masters": "Street Fighter",
    "m. bison": "Street Fighter",
    "chun-li": "Street Fighter",
    "akuma": "Street Fighter",
    "jin kazama": "Tekken",
    "devil jin": "Tekken",
    "paul phoenix": "Tekken",
    "kazuya": "Tekken",
    "heihachi": "Tekken",
    "cloud strife": "Final Fantasy",
    "sephiroth": "Final Fantasy",
    "tifa": "Final Fantasy",
    "squall leonhart": "Final Fantasy",
    "rinoa heartilly": "Final Fantasy",
    "vaan": "Final Fantasy",
    "jecht": "Final Fantasy",
    "kimahri ronso": "Final Fantasy",
    "kratos": "God of War",
    "luigi": "Mario",
    "mario": "Mario",
    "princess peach": "Mario",
    "bowser": "Mario",
    "donkey kong": "Donkey Kong",
    "naruto": "Naruto",
    "tobirama senju": "Naruto",
    "itachi": "Naruto",
    "sasuke": "Naruto",
    "goku": "Dragon Ball",
    "gohan": "Dragon Ball",
    "vegeta": "Dragon Ball",
    "frieza": "Dragon Ball",
    "piccolo": "Dragon Ball",
    "ichigo kurosaki": "Bleach",
    "uryu ishida": "Bleach",
    "yhwach": "Bleach",
    "byakuya kuchiki": "Bleach",
    "kaname tosen": "Bleach",
    "denji": "Chainsaw Man",
    "power": "Chainsaw Man",
    "aki hayakawa": "Chainsaw Man",
    "makima": "Chainsaw Man",
    "boros": "One Punch Man",
    "genos": "One Punch Man",
    "saitama": "One Punch Man",
    "meruem": "Hunter x Hunter",
    "killua zoldyck": "Hunter x Hunter",
    "gon freecss": "Hunter x Hunter",
    "inuyasha": "Inuyasha",
    "naraku": "Inuyasha",
    "kagome higurashi": "Inuyasha",
    "vi": "League of Legends",
    "garen": "League of Legends",
    "lux": "League of Legends",
    "viego": "League of Legends",
    "invoker": "Dota",
    "terrorblade": "Dota",
    "radahn": "Elden Ring",
    "melina": "Elden Ring",
    "elden beast": "Elden Ring",
    "genichiro ashina": "Sekiro",
    "isshin ashina": "Sekiro",
    "sentry": "Marvel",
    "wolverine": "Marvel",
    "scarlet witch": "Marvel",
    "she-hulk": "Marvel",
    "spider-man": "Marvel",
    "black panther": "Marvel",
    "spawn": "Image Comics",
    "godzilla": "Godzilla",
    "adam smasher": "Cyberpunk",
    "v": "Cyberpunk",
    "kilik": "Soulcalibur",
    "siegfried schtauffen": "Soulcalibur",
    "nightmare": "Soulcalibur",
    "mitsurugi": "Soulcalibur",
    "pit": "Kid Icarus",
    "c.c.": "Code Geass",
    "lelouch vi britannia": "Code Geass",
    "suzaku kururugi": "Code Geass",
    "thragg": "Invincible",
    "invincible": "Invincible",
    "battle beast": "Invincible",
    "asta": "Black Clover",
    "yuno": "Black Clover",
    "julius novachrono": "Black Clover",
    "gabranth": "Final Fantasy XII",
    "basch fon ronsenburg": "Final Fantasy XII",
    "ashe": "Final Fantasy XII",
    "fran": "Final Fantasy XII",
    "tidus": "Final Fantasy X",
    "seymour guado": "Final Fantasy X",
    "barret wallace": "Final Fantasy VII",
    "cid highwind": "Final Fantasy VII",
    "red xiii": "Final Fantasy VII",
}


INLINE_FRANCHISE_SUFFIXES = [
    "Street Fighter",
    "Tekken",
    "Final Fantasy",
    "God Of War",
    "God of War",
    "Dragon Ball",
    "Bleach",
    "Naruto",
    "One Punch Man",
    "Hunter X Hunter",
    "Hunter x Hunter",
    "Chainsaw Man",
    "League Of Legends",
    "League of Legends",
    "Dota",
    "Elden Ring",
    "Sekiro",
    "Marvel",
    "Image Comics",
    "Godzilla",
    "Cyberpunk",
    "Soulcalibur",
    "Kid Icarus",
    "Code Geass",
    "Invincible",
    "Black Clover",
    "Mario",
    "Donkey Kong",
    "Inuyasha",
]



FRANCHISE_HINTS.update({
    "gabranth": "Final Fantasy",
    "sephiroth": "Final Fantasy",
    "cloud strife": "Final Fantasy",
    "tifa lockhart": "Final Fantasy",
    "barret wallace": "Final Fantasy",
    "tidus": "Final Fantasy",
    "power": "Chainsaw Man",
    "makima": "Chainsaw Man",
    "denji": "Chainsaw Man",
    "reze": "Chainsaw Man",
    "aki hayakawa": "Chainsaw Man",
    "jinx": "League of Legends",
    "yone": "League of Legends",
    "ryu": "Street Fighter",
    "cammy white": "Street Fighter",
    "heihachi mishima": "Tekken",
    "hwoarang": "Tekken",
    "ganondorf": "The Legend of Zelda",
    "vaati": "The Legend of Zelda",
    "radagon of the golden order": "Elden Ring",
    "melina": "Elden Ring",
})

def split_inline_franchise(name: str) -> tuple[str, str | None]:
    raw = name.strip()

    # Already formatted, e.g. Ryu (Street Fighter).
    if raw.endswith(")") and "(" in raw:
        base = raw.rsplit("(", 1)[0].strip()
        franchise = raw.rsplit("(", 1)[1].rstrip(")").strip()
        return base, franchise or None

    lowered = raw.casefold()

    for suffix in sorted(INLINE_FRANCHISE_SUFFIXES, key=len, reverse=True):
        s = suffix.casefold()
        if lowered.endswith(" " + s):
            base = raw[: -(len(suffix) + 1)].strip()
            return base, suffix.title().replace("Of", "of").replace("X", "x")

    return raw, None


def infer_franchise(name: str) -> str | None:
    base, inline = split_inline_franchise(name)
    if inline:
        return inline

    key = base.casefold().strip()

    if key in FRANCHISE_HINTS:
        return FRANCHISE_HINTS[key]

    # Safe partial matching only for longer multi-word hints.
    # Prevents tiny hints like "v" from tagging unrelated names.
    for hint, franchise in sorted(FRANCHISE_HINTS.items(), key=lambda x: len(x[0]), reverse=True):
        h = hint.casefold().strip()
        if len(h) < 4:
            continue
        if " " not in h and len(h) < 6:
            continue
        if re.search(rf"(^|\\b){re.escape(h)}($|\\b)", key):
            return franchise

    return None


FRANCHISE_HINTS.update(EXTRA_FRANCHISE_HINTS)

# AI_NERD_DYNAMIC_FRANCHISE_HINTS
def _ai_nerd_load_dynamic_franchise_hints():
    try:
        import json, re
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        hint_path = root / "config" / "proactive_franchise_hints.json"
        if not hint_path.exists():
            return {}
        raw = json.loads(hint_path.read_text(errors="ignore"))
        return {re.sub(r"[^a-z0-9]+", " ", str(k).lower()).strip(): str(v).strip() for k, v in raw.items() if v}
    except Exception:
        return {}

try:
    FRANCHISE_HINTS.update(_ai_nerd_load_dynamic_franchise_hints())
except Exception:
    FRANCHISE_HINTS = _ai_nerd_load_dynamic_franchise_hints()

def display_fighter_name(name: str) -> str:
    base, inline = split_inline_franchise(name)

    exact_franchise_overrides = {
        "gabranth": "Final Fantasy XII",
    }

    franchise = inline or exact_franchise_overrides.get(base.casefold().strip()) or infer_franchise(base)

    if franchise:
        return f"{base} ({franchise})"

    return base


def profile_names_from_candidates() -> list[str]:
    names: list[str] = []

    for p in sorted(Path("harvest/promo_candidates").glob("*.md")):
        text = p.read_text(encoding="utf-8", errors="ignore")
        first = text.splitlines()[0].strip() if text.splitlines() else ""
        if " VS " in first:
            a, b = first.split(" VS ", 1)
            names.extend([display_fighter_name(a.strip()), display_fighter_name(b.strip())])

    clean = []
    seen = set()
    for name in names:
        if not name or len(name) > 100:
            continue
        key = name.casefold()
        if key not in seen:
            seen.add(key)
            clean.append(name)

    return clean


def make_matchup_suggestion(state: dict) -> str | None:
    names = profile_names_from_candidates()

    if len(names) < 2:
        # Fallback if harvest candidates are missing.
        names = [
            "Ryu",
            "Jin Kazama",
            "Cloud Strife",
            "Kratos",
            "Boros",
            "Genos",
            "M. Bison",
            "Ken Masters",
            "Radahn",
            "Melina",
        ]

    posted = set(state.get("posted") or [])

    for _ in range(100):
        a, b = random.sample(names, 2)
        post_id = f"suggest:{a.casefold()}:{b.casefold()}"
        reverse_id = f"suggest:{b.casefold()}:{a.casefold()}"

        if post_id in posted or reverse_id in posted:
            continue

        state.setdefault("posted", []).append(post_id)
        return (
            "🥊 **Suggested Matchup**\n\n"
            "Who wins?\n\n"
            f"**{a} VS {b}**\n\n"
            "React or drop your argument before the AI Nerd Referee calls it."
        )

    return None


def extract_promoted_names_from_log(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    names: list[str] = []

    # Try JSON-ish/common promotion output patterns first.
    patterns = [
        r'"name"\s*:\s*"([^"]+)"',
        r'"fighter"\s*:\s*"([^"]+)"',
        r'"character"\s*:\s*"([^"]+)"',
        r'"profile_name"\s*:\s*"([^"]+)"',
        r'"promoted"\s*:\s*"([^"]+)"',
        r'Promoted:\s*([^\n]+)',
        r'promoted\s+([^\n]+)',
    ]

    for pat in patterns:
        for m in re.finditer(pat, text, flags=re.I):
            name = m.group(1).strip()
            if name and len(name) <= 100:
                names.append(name)

    # Fallback: infer from moved/generated file paths in log text.
    for m in re.finditer(r'profiles/generated/([^\s",]+)', text):
        stem = Path(m.group(1)).stem
        name = stem.replace("_", " ").replace("-", " ").strip().title()
        if name:
            names.append(name)

    clean = []
    seen = set()

    bad_words = {
        "true",
        "false",
        "none",
        "null",
        "ok",
        "success",
        "failed",
        "generated",
        "needs_review",
    }

    for name in names:
        name = name.strip().strip(",")
        key = name.casefold()

        if not name or key in bad_words:
            continue
        if "/" in name or "\\n" in name:
            continue
        if key not in seen:
            seen.add(key)
            clean.append(display_fighter_name(name))

    return clean


def latest_actual_promotions(limit: int = 12) -> tuple[list[str], str | None]:
    logs = sorted(
        Path("logs/promote").glob("refinement_promote_*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    if not logs:
        return [], None

    picked: list[str] = []
    seen = set()
    source_log = None

    # Look through a few recent logs, newest first, but only return actual promotion-log names.
    for log in logs[:5]:
        names = extract_promoted_names_from_log(log)
        if names and source_log is None:
            source_log = log.name

        for name in names:
            key = name.casefold()
            if key not in seen:
                seen.add(key)
                picked.append(name)

            if len(picked) >= limit:
                return picked, source_log or log.name

    return picked, source_log


def make_recent_ready_report(state: dict) -> str | None:
    fighters, source_log = latest_actual_promotions(limit=12)

    if not fighters:
        return None

    batch_key = "real_promotions:" + "|".join(x.casefold() for x in fighters)

    posted = set(state.get("posted") or [])
    if batch_key in posted:
        return None

    state.setdefault("posted", []).append(batch_key)

    body = "\n".join(f"- {name}" for name in fighters)

    return (
        "🧬 **Recently Promoted Battle-Ready Fighters**\n\n"
        f"{body}\n\n"
        f"Source: latest promotion log `{source_log}`. Pick two and call the next fight."
    )


def _parse_auto_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _cooldown_ready(state: dict, key: str, hours: int) -> bool:
    last = _parse_auto_time(state.get(key))
    if last is None:
        return True
    age_seconds = (datetime.now() - last).total_seconds()
    return age_seconds >= hours * 3600


def _mark_auto_post(state: dict, kind: str) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    state["last_auto_post_at"] = now
    state[f"last_{kind}_post_at"] = now
    state["last_auto_kind"] = kind



def humanize_referee_copy(content: str) -> str:
    """Give proactive posts a rotating nerd-referee voice."""
    if not content:
        return content

    lines = content.splitlines()
    winner = loser = odds = confidence = title = None

    for line in lines:
        stripped = line.strip().strip("*").strip()
        if " VS " in stripped and not stripped.startswith("Who wins?") and not stripped.startswith("React"):
            title = stripped
        elif stripped.startswith("Winner:"):
            winner = stripped.split("Winner:", 1)[1].strip()
        elif stripped.startswith("Battle odds:"):
            odds = stripped.split("Battle odds:", 1)[1].strip()
        elif stripped.startswith("Confidence:"):
            confidence = stripped.split("Confidence:", 1)[1].strip()

    if title and winner:
        parts = title.split(" VS ", 1)
        if len(parts) == 2:
            a, b = parts[0].strip(), parts[1].strip()
            wb = re.sub(r"\s*\([^)]*\)", "", winner).strip()
            ab = re.sub(r"\s*\([^)]*\)", "", a).strip()
            bb = re.sub(r"\s*\([^)]*\)", "", b).strip()
            loser = b if winner in a or wb == ab else a if winner in b or wb == bb else b

    seed = sum(ord(c) for c in (title or winner or content))
    openers = [
        "The ref is practically throwing index cards across the table for this one:",
        "Comic-shop debate mode activated:",
        "The ref checks the tape and makes the call:",
        "The ref has watched the tape, checked the tools, and circled the winner:",
        "This one has debate-room energy, and the ref is ready:",
        "The ref opens the case file:",
        "The ref just slammed the matchup folder shut:",
        "Power-scaling board is up, and the call is:",
    ]
    mids = [
        "has the cleaner fight script, safer answers, and the more believable finish.",
        "controls the better win lane once the fight stops being theoretical.",
        "has the stronger route from opening pressure to final checkmate.",
        "does not need the fight to go perfect; the other side kind of does.",
        "brings the tools that matter more often in the actual exchange.",
        "wins the ugly middle of the fight, and that is where this matchup breaks.",
    ]
    underdog = [
        "is dangerous, but their path needs tighter timing and less room for error.",
        "has a real argument, but it leans too hard on a perfect opening.",
        "can make it messy, but messy still favors the winner here.",
        "has upset potential, but not enough reliable control of the exchange.",
        "needed a cleaner exploit than the matchup evidence supports.",
    ]

    if winner and loser:
        call = (
            f"{openers[seed % len(openers)]} {winner} takes it. "
            f"{winner} {mids[(seed // 3) % len(mids)]} "
            f"{loser} {underdog[(seed // 7) % len(underdog)]}"
        )
    elif winner:
        call = (
            f"{openers[seed % len(openers)]} {winner}. "
            f"The winning route is cleaner, the counterplay is easier to manage, "
            f"and the finish shows up more reliably."
        )
    else:
        call = "The ref is holding this one for judge review. The evidence is too thin for a clean call."

    if odds:
        call += f" Odds board: {odds}."
    if confidence:
        call += f" Ref confidence: {confidence}."

    content = re.sub(
        r"^.*?has the more reliable stat-and-tool profile over .*? from the profile data\.\s*$",
        call,
        content,
        flags=re.MULTILINE,
    )
    content = re.sub(
        r"^.*?has the more reliable stat-and-tool profile over .*?\.\s*$",
        call,
        content,
        flags=re.MULTILINE,
    )
    content = content.replace(
        "This matchup needs judge review because the profiles do not provide enough clean battle data.",
        "The ref is holding this one for judge review. The current files do not give enough clean fight evidence for a confident call yet.",
    )
    content = content.replace(
        "No expanded evidence available until judge review.",
        "The ref wants more tape before making this call. Current evidence is too thin for a clean verdict.",
    )
    return content



def _ranked_outbox_files(outbox: Path) -> list[Path]:
    ranked = Path("harvest/promotion_ranked_today.json")
    if not ranked.exists():
        return sorted(outbox.glob("*.md"))
    try:
        data = __import__("json").loads(ranked.read_text())
    except Exception:
        return sorted(outbox.glob("*.md"))
    files = []
    for item in data:
        path = Path(item.get("path", ""))
        if path.exists() and path.parent == outbox:
            files.append(path)
    return files or sorted(outbox.glob("*.md"))


def make_outbox_social_result(state: dict) -> str | None:
    outbox = Path("harvest/promotion_outbox")
    if not outbox.exists():
        return None

    posted = set(state.get("posted_outbox_files") or [])
    files = _ranked_outbox_files(outbox)

    for path in files:
        key = path.name
        if key in posted:
            continue

        text = path.read_text(errors="ignore").strip()
        if not text:
            continue

        # Keep Discord post compact.
        lines = []
        for line in text.splitlines():
            if line.strip().startswith("<!--"):
                continue
            lines.append(line.rstrip())

        body = "\n".join(lines).strip()
        if len(body) > 1400:
            body = body[:1390].rstrip() + "\n..."

        posted.add(key)
        state["posted_outbox_files"] = sorted(posted)

        return (
            "⚔️ **AI Nerd Referee Result**\n\n"
            + body
            + "\n\nThe ref has ruled. Drop the next matchup."
        )

    return None


def choose_auto(state: dict) -> str | None:
    # Proactive auto cadence:
    # - Max one proactive post per hour.
    # - Promotions/ready reports get first priority when present.
    # - Already-decided fight summaries are the default.
    # - Suggestions are intentionally staggered so they appear periodically without taking over the channel.
    if not _cooldown_ready(state, "last_auto_post_at", 1):
        return None

    plan = (
        ("ready", make_recent_ready_report, 1),
        ("social", make_outbox_social_result, 1),
        ("suggest", make_matchup_suggestion, 3),
    )

    for kind, maker, hours in plan:
        if not _cooldown_ready(state, f"last_{kind}_post_at", hours):
            continue

        content = maker(state)
        if content:
            _mark_auto_post(state, kind)
            return content

    return None



# AI_NERD_FINAL_PROACTIVE_SANITIZER
def ai_nerd_sanitize_final_post_text(text: str) -> str:
    text = str(text or "")
    replacements = {
        "The AI Nerd Referee has spoken. Drop the next matchup.": "The ref has ruled. Drop the next matchup.",
        "AI Nerd Referee has spoken. Drop the next matchup.": "The ref has ruled. Drop the next matchup.",
        "The bracket goblin in the striped shirt has a call:": "The ref checks the tape and makes the call:",
        "Power-scaling chalkboard is out, and the call is:": "Power-scaling board is up, and the call is:",
        "The nerd tribunal is in session:": "The ref opens the case file:",
        "wins the ugly middle of the fight, and that is where this matchup breaks.": "wins the key exchange, and that is where this matchup breaks.",
        "has the cleaner fight script, safer answers, and the more believable finish.": "has the cleaner route, safer answers, and the more believable finish.",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["auto", "social", "suggest", "ready"], default="auto")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    state = load_state()

    if args.mode == "social":
        content = make_social_result(state)
    elif args.mode == "suggest":
        content = make_matchup_suggestion(state)
    elif args.mode == "ready":
        content = make_recent_ready_report(state)
    else:
        content = choose_auto(state)

    if not content:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{now_str}] Cadence check: No post available or cooldown active.")
        return 0

    content += f"\n\n`posted {datetime.now().strftime('%Y-%m-%d %H:%M')}`"

    content = humanize_referee_copy(content)

    post_webhook(content, dry_run=args.dry_run)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now_str}] Successfully posted announcement via webhook.")

    if not args.dry_run:
        save_state(state)
    else:
        print("\nDry run only. State was not saved.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

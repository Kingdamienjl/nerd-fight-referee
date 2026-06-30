"""Batch audit deterministic fight output without Discord."""

from __future__ import annotations

import argparse
import json
import random
import re
from pathlib import Path
from typing import Any

import yaml

from battlebot.fight.decision_formatter import format_fight_card, structured_decision_output
from battlebot.fight.smoke_judge import smoke_judge_packet


DEFAULT_REPORT_PATH = Path("data/reports/fight_output_audit.json")
HIGH_PROFILE_NAMES = (
    "Usagi Tsukino",
    "Sephiroth",
    "Cloud Strife",
    "Kratos",
    "Sentry",
    "Wolverine",
    "Spawn",
    "Godzilla",
)
DIRTY_TOKENS = (
    "however",
    "intrinsic",
    "original",
    "innate",
    "none notable",
    "none notable optional",
    "optional",
    "cla",
    "right, thumb",
    "magic, including",
    "are allowed to use their own personalized gear",
    "strongest consistent canonical form",
    "base form",
    "base▼",
    "volume 0▼",
    "No • Yes",
    "No, Yes",
    "Content",
    "Border",
    "tabber",
    "{{",
    "}}",
    ".png",
    ".jpg",
    ".gif",
    "File:",
    "Image:",
)
GENERIC_PHRASES = (
    "packet-backed route",
    "packet-backed",
    "strongest confirmed lane",
    "force their strongest confirmed lane early",
    "best listed tactic",
    "force their best listed tactic early",
    "weathering early answers",
    "making each return hit cost",
    "controlled the pace",
    "repeatable control",
    "cleaner route",
    "from the supplied packet",
    "the supplied packet",
    "the opponent",
    "his opponent",
    "her opponent",
)
SOURCE_TAB_TERMS = (
    "Before Crisis",
    "Crisis Core",
    "Disc 1",
    "Disc 2",
    "Disc 3",
    "Advent Children",
    "Original",
    "Intrinsic",
)
LOW_VALUE_TOOLS = (
    "however",
    "intrinsic",
    "original",
    "innate",
    "content",
    "before crisis",
    "crisis core",
    "disc 1",
    "disc 2",
    "no",
    "yes",
)
STYLE_MISCLASSIFICATION_NAMES = ("wolverine", "guts", "power girl", "android 17", "roy mustang")
SCALAR_KEYS = ("name", "value", "tier", "rating", "level", "text", "description", "label")
CONTEXT_DIRTY_TOKEN_RE = {
    "cla": re.compile(r"(?:^|[^\w])cla(?:[^\w]|$)", re.IGNORECASE),
    "original": re.compile(r"\boriginal\b(?!\s+sin\b)", re.IGNORECASE),
    "innate": re.compile(r"\binnate\b(?!\s+technique\b)", re.IGNORECASE),
}


def clean_id(value: Any, fallback: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", str(value or "").casefold()).strip("-")
    return text or fallback


def scalar_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    if isinstance(value, dict):
        for key in SCALAR_KEYS:
            candidate = scalar_text(value.get(key))
            if candidate:
                return candidate
        for item in value.values():
            candidate = scalar_text(item)
            if candidate:
                return candidate
        return ""
    if isinstance(value, list):
        for item in value:
            candidate = scalar_text(item)
            if candidate:
                return candidate
        return ""
    return str(value)


def nested_value(profile: dict[str, Any], *paths: tuple[str, ...]) -> Any:
    for path in paths:
        current: Any = profile
        for key in path:
            if not isinstance(current, dict) or key not in current:
                current = None
                break
            current = current.get(key)
        if current not in (None, "", [], {}):
            return current
    return None


def normalize_power_scale(profile: dict[str, Any]) -> dict[str, str]:
    return {
        "attack_potency": scalar_text(
            nested_value(
                profile,
                ("power_scale", "attack_potency"),
                ("stats", "attack_potency"),
                ("scales", "attack_potency"),
                ("battle_stats", "attack_potency"),
                ("attack_potency",),
            )
        ),
        "speed": scalar_text(
            nested_value(
                profile,
                ("power_scale", "speed"),
                ("stats", "speed"),
                ("scales", "speed"),
                ("battle_stats", "speed"),
                ("speed",),
            )
        ),
        "durability": scalar_text(
            nested_value(
                profile,
                ("power_scale", "durability"),
                ("stats", "durability"),
                ("scales", "durability"),
                ("battle_stats", "durability"),
                ("durability",),
            )
        ),
    }


def normalize_profile_for_fight(profile: dict[str, Any]) -> dict[str, Any]:
    name = scalar_text(profile.get("canonical_name") or profile.get("name"))
    character_id = scalar_text(profile.get("character_id") or profile.get("id")) or clean_id(name, "unknown")
    return {
        "canonical_name": name or character_id,
        "character_id": character_id,
        "franchise": scalar_text(profile.get("franchise")),
        "category": scalar_text(profile.get("category")),
        "power_scale": normalize_power_scale(profile),
        "abilities": profile.get("abilities") or profile.get("powers") or profile.get("special_abilities") or [],
        "equipment": profile.get("equipment") or profile.get("weapons") or [],
        "weapons": profile.get("weapons") or [],
        "forms": profile.get("forms") or profile.get("transformations") or [],
        "weaknesses": profile.get("weaknesses") or [],
        "tactical_profile": profile.get("tactical_profile") if isinstance(profile.get("tactical_profile"), dict) else {},
        "warnings": profile.get("warnings") or [],
        "profile_path": scalar_text(profile.get("profile_path")),
    }


def profile_from_yaml(path: Path) -> dict[str, Any] | None:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return None
    if not isinstance(data, dict) or not data.get("battle_eligible"):
        return None
    profile_id = str(data.get("character_id") or data.get("id") or clean_id(data.get("name"), path.stem))
    return normalize_profile_for_fight({
        "canonical_name": str(data.get("name") or path.stem),
        "character_id": profile_id,
        "franchise": str(data.get("franchise") or ""),
        "category": str(data.get("category") or ""),
        "power_scale": data.get("power_scale") if isinstance(data.get("power_scale"), dict) else {},
        "stats": data.get("stats") if isinstance(data.get("stats"), dict) else {},
        "scales": data.get("scales") if isinstance(data.get("scales"), dict) else {},
        "battle_stats": data.get("battle_stats") if isinstance(data.get("battle_stats"), dict) else {},
        "attack_potency": data.get("attack_potency"),
        "speed": data.get("speed"),
        "durability": data.get("durability"),
        "abilities": data.get("abilities") or data.get("powers") or data.get("special_abilities") or [],
        "equipment": data.get("equipment") or data.get("weapons") or [],
        "weapons": data.get("weapons") or [],
        "forms": data.get("forms") or data.get("transformations") or [],
        "weaknesses": data.get("weaknesses") or [],
        "tactical_profile": data.get("tactical_profile") if isinstance(data.get("tactical_profile"), dict) else {},
        "warnings": data.get("warnings") or [],
        "profile_path": path.as_posix(),
    })


def load_profiles(generated_dir: Path, needs_review_dir: Path) -> list[dict[str, Any]]:
    profiles = []
    for root in (generated_dir, needs_review_dir):
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.yaml")):
            profile = profile_from_yaml(path)
            if profile:
                profiles.append(profile)
    return profiles


def high_profile_pairs(profiles: list[dict[str, Any]]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    by_name = {str(profile.get("canonical_name") or "").casefold(): profile for profile in profiles}
    selected = [by_name[name.casefold()] for name in HIGH_PROFILE_NAMES if name.casefold() in by_name]
    return [(selected[index], selected[index + 1]) for index in range(0, len(selected) - 1, 2)]


def sample_matchups(profiles: list[dict[str, Any]], *, sample_size: int, seed: int) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    rng = random.Random(seed)
    pairs = high_profile_pairs(profiles)
    same_franchise: dict[str, list[dict[str, Any]]] = {}
    for profile in profiles:
        same_franchise.setdefault(str(profile.get("franchise") or ""), []).append(profile)
    for bucket in same_franchise.values():
        if len(bucket) >= 2:
            left, right = rng.sample(bucket, 2)
            if left["character_id"] != right["character_id"]:
                pairs.append((left, right))
    categories: dict[str, list[dict[str, Any]]] = {}
    for profile in profiles:
        categories.setdefault(str(profile.get("category") or ""), []).append(profile)
    category_names = [name for name, bucket in categories.items() if bucket]
    while len(pairs) < sample_size and len(profiles) >= 2:
        if len(category_names) >= 2:
            left_category, right_category = rng.sample(category_names, 2)
            left = rng.choice(categories[left_category])
            right = rng.choice(categories[right_category])
        else:
            left, right = rng.sample(profiles, 2)
        if left["character_id"] != right["character_id"]:
            pairs.append((left, right))
    unique = []
    seen = set()
    for left, right in pairs:
        key = tuple(sorted((left["character_id"], right["character_id"])))
        if key not in seen:
            seen.add(key)
            unique.append((left, right))
        if len(unique) >= sample_size:
            break
    return unique


def detect_output_problems(entry: dict[str, Any]) -> list[str]:
    text = json.dumps(entry, sort_keys=True)
    problems = []
    for token in DIRTY_TOKENS:
        if token in CONTEXT_DIRTY_TOKEN_RE:
            if CONTEXT_DIRTY_TOKEN_RE[token].search(text):
                problems.append(f"dirty token leakage: {token}")
        elif token.casefold() in text.casefold():
            problems.append(f"dirty token leakage: {token}")
    for phrase in GENERIC_PHRASES:
        if phrase.casefold() in text.casefold():
            problems.append(f"generic narration: {phrase}")
    for bullet in entry.get("quick_evidence") or []:
        if "Special Abilities" in bullet and any(term.casefold() in bullet.casefold() for term in SOURCE_TAB_TERMS):
            problems.append("wrong evidence label: source tabs labeled Special Abilities")
    fight_card = str(entry.get("public_fight_card_text") or "")
    for line in fight_card.splitlines():
        value = line.split(":", 1)[-1].strip()
        if value.casefold() in LOW_VALUE_TOOLS:
            problems.append(f"low-value tool: {value}")
    if "magic user" in text.casefold() and any(name in text.casefold() for name in STYLE_MISCLASSIFICATION_NAMES):
        problems.append("style misclassification: likely physical/tech fighter labeled magic user")
    return sorted(set(problems))


def problem_type(problem: str) -> str:
    return problem.split(":", 1)[0]


def audit_matchup(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    left = normalize_profile_for_fight(left)
    right = normalize_profile_for_fight(right)
    packet = {"errors": [], "contender_a": left, "contender_b": right, "warnings": []}
    smoke = smoke_judge_packet(packet)
    structured = structured_decision_output(smoke)
    entry = {
        "fighter_a": left.get("canonical_name"),
        "fighter_b": right.get("canonical_name"),
        "winner": structured["winner"],
        "confidence": structured["confidence"],
        "battle_odds_text": structured["battle_odds_text"],
        "public_fight_card_text": "\n".join(format_fight_card(smoke)),
        "quick_evidence": structured["quick_evidence"],
        "full_evidence": structured["full_evidence"],
        "summary": structured["short_summary"],
        "loser_best_path": structured["loser_best_path"],
    }
    problems = detect_output_problems(entry)
    entry["problems"] = problems
    entry["problem_score"] = len(problems)
    return entry


def build_report(profiles: list[dict[str, Any]], *, sample_size: int, seed: int) -> dict[str, Any]:
    entries = [audit_matchup(left, right) for left, right in sample_matchups(profiles, sample_size=sample_size, seed=seed)]
    counts_by_problem_type: dict[str, int] = {}
    for entry in entries:
        for problem in entry["problems"]:
            key = problem_type(str(problem))
            counts_by_problem_type[key] = counts_by_problem_type.get(key, 0) + 1
    return {
        "summary": {
            "profiles_loaded": len(profiles),
            "matchups_audited": len(entries),
            "problem_entries": sum(1 for entry in entries if entry["problems"]),
            "total_problem_score": sum(int(entry["problem_score"]) for entry in entries),
            "problem_counts_by_type": counts_by_problem_type,
        },
        "entries": entries,
    }


def write_report(report: dict[str, Any], path: Path = DEFAULT_REPORT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit deterministic fight output quality")
    parser.add_argument("--database-url")
    parser.add_argument("--generated-dir", type=Path, default=Path("profiles/generated"))
    parser.add_argument("--needs-review-dir", type=Path, default=Path("profiles/needs_review"))
    parser.add_argument("--sample-size", type=int, default=100)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--write-report", action="store_true")
    parser.add_argument("--include-llm", action="store_true", default=False)
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    profiles = load_profiles(args.generated_dir, args.needs_review_dir)
    report = build_report(profiles, sample_size=max(0, args.sample_size), seed=args.seed)
    if args.write_report:
        write_report(report)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

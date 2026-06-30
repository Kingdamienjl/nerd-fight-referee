"""Format fight decisions for Discord."""

from __future__ import annotations

import re
from typing import Any


PUBLIC_LIMIT = 1800
DISCORD_FIELD_LIMIT = 1024
RAW_TEMPLATE_RE = re.compile(r"\{\{[^{}\n]*(?:\n[^{}]*)?\}\}")
GENERIC_ROUTE = "converts stat leads into initiative, damage pressure, and survivable exchanges"
DIRTY_FIGHT_CARD_PATTERNS = (
    "{{",
    "}}",
    "{{!",
    "#tag",
    "tag:",
    "tabber",
    "border",
    "content",
    "file:",
    "image:",
    "{|",
    "|}",
    "no • yes",
    "yes • no",
    "no, yes",
    "yes, no",
)
IMAGE_FILE_RE = re.compile(r"\.(?:png|jpe?g|gif|webp|svg)\b", re.IGNORECASE)
FIELD_LABEL_RE = re.compile(
    r"\b(?:tier|origin|classification|powers?|abilities|equipment|weaknesses|notable attacks/techniques|attack potency|speed|durability)\s*:",
    re.IGNORECASE,
)
KNOWN_SHORT_TOOL_PHRASES = (
    "Buster Sword",
    "Limit Breaks",
    "Materia",
    "Masamune",
    "Silver Crystal",
    "Moon Stick",
    "Spiral Heart Moon Rod",
    "Magic",
    "Purification",
    "Energy Projection",
    "Forcefield Creation",
)
LOW_VALUE_TOOL_TERMS = ("innate", "before crisis", "crisis core", "disc 1", "content")
BOOLEAN_RESIDUE_RE = re.compile(r"^(?:no|yes)(?:\s*(?:,|•|/)\s*(?:no|yes))*$", re.IGNORECASE)


def truncate_at_sentence_boundary(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    cutoff = max(0, limit - 3)
    truncated = text[:cutoff].rstrip()
    sentence_end = max(truncated.rfind("."), truncated.rfind("!"), truncated.rfind("?"))
    if sentence_end >= cutoff // 3:
        return f"{truncated[: sentence_end + 1]}..."
    word_end = truncated.rfind(" ")
    if word_end > 0:
        truncated = truncated[:word_end].rstrip()
    return f"{truncated}..."


def clamp_text(text: str, limit: int = PUBLIC_LIMIT) -> str:
    return truncate_at_sentence_boundary(text, limit)


def compact_field(value: Any, max_chars: int = DISCORD_FIELD_LIMIT) -> str:
    return clamp_text(str(value or "").strip(), max_chars)


def split_text_for_discord(value: Any, max_chars: int = 1800) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []
    chunks: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= max_chars:
            chunks.append(remaining)
            break
        window = remaining[:max_chars].rstrip()
        split_at = max(window.rfind("\n\n"), window.rfind("\n"))
        if split_at < max_chars // 3:
            split_at = max(window.rfind(". "), window.rfind("! "), window.rfind("? "))
            if split_at >= max_chars // 3:
                split_at += 1
        if split_at < max_chars // 3:
            split_at = window.rfind(" ")
        if split_at <= 0:
            split_at = len(window)
        chunk = window[:split_at].rstrip()
        if not chunk:
            break
        chunks.append(chunk)
        remaining = remaining[len(chunk) :].lstrip()
    return chunks


def clean_text(value: Any, *, limit: int = 220) -> str:
    text = str(value or "")
    text = RAW_TEMPLATE_RE.sub("", text)
    text = re.sub(r"\bPart\s+[IVXLC]+\s*=\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\b[A-Z][A-Za-z .'-]{1,40}=\s*", "", text)
    text = re.sub(r"^\s*\d+\s*(?:&\s*\d+)?\)\s*", "", text)
    text = re.sub(r"^\s*\d+[.)]\s*", "", text)
    text = re.sub(r"\bNotable Attacks/Techniques\s*:?", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(?:Weaknesses|Weakness|Abilities|Equipment|Powers?)\s*:", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(his|her|their),\s+\1\b", r"\1", text, flags=re.IGNORECASE)
    text = re.sub(r"\.{3,}", "...", text)
    if text.count("(") != text.count(")"):
        text = text.replace("(", " ").replace(")", " ")
    text = re.sub(r"\s+", " ", text).strip(" -:\n\t")
    text = text.replace(GENERIC_ROUTE, "turns the listed packet edge into practical fight pressure")
    return clamp_text(text, limit)


def clean_detail_text(value: Any, *, limit: int = 8000) -> str:
    text = str(value or "")
    text = RAW_TEMPLATE_RE.sub("", text)
    text = re.sub(r"\{\{|\}\}|\|", " ", text)
    text = re.sub(r"\bPart\s+[IVXLC]+\s*=\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\bNotable Attacks/Techniques\s*:?", "Notable techniques:", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(his|her|their),\s+\1\b", r"\1", text, flags=re.IGNORECASE)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip(" -:\n\t")
    return text[:limit].rstrip()


def compress_route_text(decision: dict[str, Any], route: str) -> str:
    normalized = route.casefold()
    if any(axis in normalized for axis in ("attack_potency:", "speed:", "durability:", "outerverse level", "athlete level")):
        winner = clean_text(decision.get("winner"), limit=80) or "The winner"
        loser_path = clean_text(decision.get("loser_best_path"), limit=120)
        if "prep" in loser_path.casefold() or "tactic" in loser_path.casefold():
            return f"{winner} has the stronger packet-backed output range; the opposing route leans on tactics, counters, or prep."
        return f"{winner} has the stronger packet-backed output and survivability lane without relying on raw tier dumps."
    return route


def factor_category(value: str) -> str:
    normalized = value.casefold()
    if "range" in normalized:
        return "Range Control"
    if "speed" in normalized or "initiative" in normalized or "mobility" in normalized:
        return "Mobility / Initiative"
    if "attack" in normalized or "power" in normalized or "finishing" in normalized:
        return "Finishing Power"
    if "durability" in normalized or "attrition" in normalized:
        return "Durability / Attrition"
    if "resistance" in normalized or "counter" in normalized:
        return "Resistance / Counterplay"
    if "skill" in normalized or "tactic" in normalized or "intelligence" in normalized:
        return "Skill / Tactics"
    if "prep" in normalized:
        return "Prep Dependence"
    if "weakness" in normalized:
        return "Weakness Exploitation"
    if "battlefield" in normalized:
        return "Battlefield Control"
    if "ability" in normalized or "special" in normalized:
        return "Special Abilities"
    return clean_text(value, limit=48) or "Key Factor"


def compressed_evidence(factor: dict[str, Any], *, limit: int = 160) -> str:
    category = factor_category(str(factor.get("factor") or ""))
    evidence = clean_evidence_text(factor.get("evidence"), limit=max(80, limit - 35))
    effect = clean_evidence_text(factor.get("tactical_effect"), limit=max(80, limit - 35))
    if evidence:
        return bullet_text(clamp_text(f"{category}: {evidence}", limit))
    if category and effect:
        return bullet_text(clamp_text(f"{category}: {effect}", limit))
    return ""


def bullet_text(value: str) -> str:
    return str(value or "").rstrip(" ,;:")


def clean_evidence_text(value: Any, *, limit: int = 220) -> str:
    raw = str(value or "")
    if is_dirty_evidence_item(raw):
        return ""
    cleaned = clean_text(raw, limit=limit)
    if is_dirty_evidence_item(cleaned):
        return ""
    return cleaned


def is_dirty_evidence_item(value: str) -> bool:
    text = str(value or "")
    normalized = text.casefold()
    if IMAGE_FILE_RE.search(text):
        return True
    if BOOLEAN_RESIDUE_RE.fullmatch(text.strip()):
        return True
    return any(pattern in normalized for pattern in DIRTY_FIGHT_CARD_PATTERNS)


def is_dirty_fight_card_item(value: str) -> bool:
    text = str(value or "")
    normalized = text.casefold()
    if IMAGE_FILE_RE.search(text):
        return True
    if BOOLEAN_RESIDUE_RE.fullmatch(text.strip()):
        return True
    if any(pattern in normalized for pattern in DIRTY_FIGHT_CARD_PATTERNS):
        return True
    if FIELD_LABEL_RE.search(text):
        return True
    if normalized.count("|") >= 2 or normalized.count("{") or normalized.count("}"):
        return True
    punctuation = sum(normalized.count(mark) for mark in ("=", "[", "]", "{", "}", "|"))
    return punctuation >= 3


def sanitize_fight_card_item(value: str) -> str:
    raw = str(value or "")
    if not raw.strip():
        return ""
    if IMAGE_FILE_RE.search(raw):
        return ""
    if is_dirty_fight_card_item(raw):
        source_label_match = re.match(r"^[A-Z][A-Za-z .'-]{1,40}=\s*(.+)$", raw)
        if not source_label_match:
            return ""
        raw = source_label_match.group(1)
    text = RAW_TEMPLATE_RE.sub("", raw)
    text = re.sub(r"\{\{.*?$", "", text)
    text = re.sub(r"\{\{|\}\}|\|", " ", text)
    text = re.sub(r"\b(?:tag:|tabber|Border|Content)\b", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(?:No|Yes)\b(?:\s*•\s*\b(?:No|Yes|Content)\b)+", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bPart\s+[IVXLC]+\s*=\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^\s*\d+\s*(?:&\s*\d+)?\)\s*", "", text)
    text = re.sub(r"^\s*\d+[.)]\s*", "", text)
    text = re.sub(r"^[A-Z][A-Za-z .'-]{1,40}=\s*", "", text)
    text = re.sub(r"[*_`#>-]+", " ", text)
    text = re.sub(r"\.{3,}", "...", text)
    text = re.sub(r"\s+", " ", text).strip(" -,:;*_\n\t")
    if not text:
        return ""
    if "(" in text:
        text = text.split("(", 1)[0].strip()
    text = re.split(r"\s+-\s+|\s+–\s+|\s+—\s+|:\s+", text, maxsplit=1)[0].strip()
    if "..." in text:
        text = text.split("...", 1)[0].strip()
    for phrase in KNOWN_SHORT_TOOL_PHRASES:
        if re.search(rf"\b{re.escape(phrase)}\b", text, flags=re.IGNORECASE):
            text = phrase
            break
    if "," in text:
        parts = [part.strip(" -,:;") for part in text.split(",") if part.strip(" -,:;")]
        text = ", ".join(parts[:4])
    text = text.replace("[", " ").replace("]", " ")
    if text.count("(") != text.count(")"):
        text = text.replace("(", " ").replace(")", " ")
    text = re.sub(r"\s+", " ", text).strip(" -,:;.")
    if is_dirty_fight_card_item(text):
        return ""
    return bullet_text(clamp_text(text, 60))


def compact_list(values: Any, *, limit: int = 5) -> list[str]:
    if not values:
        return []
    items = values if isinstance(values, list) else [values]
    compact = []
    seen = set()
    for item in items:
        if isinstance(item, dict):
            value = item.get("name") or item.get("id") or item.get("description")
        else:
            value = item
        cleaned = sanitize_fight_card_item(str(value or ""))
        normalized = cleaned.casefold()
        if cleaned and normalized not in seen:
            seen.add(normalized)
            compact.append(cleaned)
    return sorted(compact, key=tool_display_priority, reverse=True)[:limit]


def tool_display_priority(value: str) -> int:
    normalized = str(value or "").casefold()
    if any(phrase.casefold() in normalized for phrase in KNOWN_SHORT_TOOL_PHRASES):
        return 40
    if any(term in normalized for term in ("magic", "purification", "energy projection", "barrier", "transformation")):
        return 30
    if any(term in normalized for term in LOW_VALUE_TOOL_TERMS):
        return -10
    return 10


def compact_value(value: Any, *, limit: int = 60) -> str:
    if isinstance(value, dict):
        value = value.get("name") or value.get("value") or value.get("description")
    cleaned = sanitize_fight_card_item(str(value or ""))
    return clamp_text(cleaned, limit) if cleaned else ""


def join_tools(values: Any, *, limit: int = 4) -> str:
    tools = compact_list(values, limit=limit)
    if not tools:
        return "No named tools supplied."
    return clean_text(", ".join(tools), limit=150)


def formatted_loser_best_path(decision: dict[str, Any]) -> str:
    loser = clean_text(decision.get("loser"), limit=80)
    winner = clean_text(decision.get("winner"), limit=80)
    path = truncate_at_sentence_boundary(clean_text(decision.get("loser_best_path"), limit=360), 300)
    if not path:
        if loser and winner:
            return (
                f"{loser} needed to force the fight against {winner} into their strongest confirmed lane, "
                "but the packet did not provide a clean exploitable weakness."
            )
        return "The loser needed to force the fight into their strongest confirmed lane, but the packet did not provide a clean exploitable weakness."
    if loser and loser.casefold() not in path.casefold():
        path = f"{loser}'s best path was {path[0].casefold()}{path[1:]}" if path else path
    if winner and winner.casefold() not in path.casefold():
        path = path.rstrip(".") + f" before {winner} could control the pace."
    return truncate_at_sentence_boundary(path, 300)


def formatted_loser_best_path_full(decision: dict[str, Any]) -> str:
    short = formatted_loser_best_path(decision)
    loser = clean_text(decision.get("loser"), limit=80) or "The loser"
    winner = clean_text(decision.get("winner"), limit=80) or "the winner"
    raw = clean_detail_text(decision.get("loser_best_path_full") or decision.get("loser_best_path"), limit=2500)
    if raw and len(raw) > len(short) + 40:
        base = raw
    else:
        base = short
    if loser.casefold() not in base.casefold() or winner.casefold() not in base.casefold():
        base = (
            f"{base.rstrip('.')} The practical upset route for {loser} was to pressure {winner}'s risk early, "
            f"force the fight into {loser}'s strongest confirmed lane, and prevent {winner} from settling into "
            "the more reliable route."
        )
    if "less reliable" not in base.casefold():
        base = (
            f"{base.rstrip('.')} It remained less reliable because the deterministic packet gave "
            f"{winner} the cleaner route to repeatable control or finishing pressure."
        )
    return clean_detail_text(base, limit=3000)


def probability_pair(decision: dict[str, Any]) -> tuple[int, int]:
    winner_probability = decision.get("winner_probability")
    loser_probability = decision.get("loser_probability")
    overall = decision.get("overall_probability") if isinstance(decision.get("overall_probability"), dict) else {}
    if winner_probability is None:
        winner_probability = overall.get("winner")
    if loser_probability is None:
        loser_probability = overall.get("loser")
    if winner_probability is not None and loser_probability is not None:
        winner_pct = int(round(float(winner_probability) * 100)) if float(winner_probability) <= 1 else int(round(float(winner_probability)))
        loser_pct = int(round(float(loser_probability) * 100)) if float(loser_probability) <= 1 else int(round(float(loser_probability)))
        return winner_pct, loser_pct
    confidence = str(decision.get("confidence") or "").casefold()
    if confidence in {"strong", "high"}:
        return 75, 25
    if "medium" in confidence:
        return 65, 35
    return 55, 45


def matchup_title(decision: dict[str, Any]) -> str:
    cards = decision.get("matchup_card") if isinstance(decision.get("matchup_card"), list) else []
    names = [clean_text(card.get("name"), limit=80) for card in cards[:2] if isinstance(card, dict) and card.get("name")]
    if len(names) >= 2:
        return f"{names[0]} vs {names[1]}"
    winner = clean_text(decision.get("winner"), limit=80)
    loser = clean_text(decision.get("loser"), limit=80)
    if winner and loser:
        return f"{winner} vs {loser}"
    return "Nerd Fight Referee"


def short_summary(decision: dict[str, Any]) -> str:
    raw_analysis = clean_text(
        decision.get("summary") or decision.get("win_condition") or decision.get("route_to_victory"),
        limit=950,
    )
    analysis = compress_route_text(decision, truncate_at_sentence_boundary(raw_analysis, 900))
    return analysis or "Deterministic referee could not produce a supported fight explanation."


def fight_card_blocks(decision: dict[str, Any]) -> list[dict[str, str]]:
    cards = decision.get("matchup_card") if isinstance(decision.get("matchup_card"), list) else []
    blocks: list[dict[str, str]] = []
    for card in cards[:2]:
        if not isinstance(card, dict):
            continue
        name = clean_text(card.get("name"), limit=80)
        if not name:
            continue
        lines = []
        height_weight = clean_text(card.get("height_weight"), limit=80)
        if height_weight:
            lines.append(f"Height/Weight: {height_weight}")
        weapon_power = join_tools(card.get("weapon_power") or card.get("weapon_of_choice") or card.get("power_of_choice"), limit=2)
        if weapon_power != "No named tools supplied.":
            lines.append(f"Weapon/Power: {weapon_power}")
        style = clean_text(card.get("style") or (card.get("combat_identity") or {}).get("combat_style"), limit=90)
        if style:
            lines.append(f"Style: {style}")
        lines.extend(
            [
                f"Key tools: {join_tools(card.get('key_tools'), limit=3)}",
                f"Win path: {clean_text(card.get('best_route') or 'Needs a clearer packet-backed win route.', limit=170)}",
            ]
        )
        risk = clean_text(card.get("risk"), limit=130)
        if risk:
            lines.append(f"Risk: {risk}")
        blocks.append({"name": name, "value": clamp_text("\n".join(lines), DISCORD_FIELD_LIMIT)})
    return blocks


def fighter_cards(decision: dict[str, Any]) -> list[dict[str, Any]]:
    cards = decision.get("matchup_card") if isinstance(decision.get("matchup_card"), list) else []
    fighters: list[dict[str, Any]] = []
    for card in cards[:2]:
        if not isinstance(card, dict):
            continue
        name = clean_text(card.get("name"), limit=80)
        if not name:
            continue
        fighters.append(
            {
                "fighter_name": name,
                "height_weight": clean_text(card.get("height_weight"), limit=80),
                "weapon_power": compact_list(card.get("weapon_power") or card.get("weapon_of_choice") or card.get("power_of_choice"), limit=2),
                "style": clean_text(card.get("style") or (card.get("combat_identity") or {}).get("combat_style"), limit=90),
                "key_tools": compact_list(card.get("key_tools"), limit=3),
                "win_path": clean_text(card.get("best_route") or "Needs a clearer packet-backed win route.", limit=160),
                "risk": clean_text(card.get("risk") or "No clean exploitable weakness supplied.", limit=120),
            }
        )
    return fighters


def evidence_bullets(decision: dict[str, Any], *, limit: int = 160) -> list[str]:
    factors = [factor for factor in decision.get("deciding_factors") or [] if isinstance(factor, dict)]
    loser_best_path = formatted_loser_best_path(decision)
    bullets = [compressed_evidence(factor, limit=limit) for factor in factors[:2]]
    if loser_best_path:
        bullets.append(bullet_text(clamp_text(f"Loser path: {loser_best_path}", limit)))
    return [bullet for bullet in bullets[:3] if bullet]


def full_evidence_text(decision: dict[str, Any]) -> str:
    lines: list[str] = []
    for card in decision.get("matchup_card") or []:
        if not isinstance(card, dict):
            continue
        identity = card.get("combat_identity") if isinstance(card.get("combat_identity"), dict) else {}
        summary = clean_detail_text(identity.get("identity_summary"), limit=400)
        non_physical = ", ".join(compact_list(identity.get("non_physical_options"), limit=4))
        if summary:
            lines.append(f"Combat identity: {summary}")
        if non_physical:
            lines.append(f"Non-physical options: {card.get('name')}: {non_physical}")
    for factor in decision.get("deciding_factors") or []:
        if not isinstance(factor, dict):
            continue
        category = factor_category(str(factor.get("factor") or "Key Factor"))
        evidence = clean_detail_text(factor.get("evidence"), limit=900)
        effect = clean_detail_text(factor.get("tactical_effect"), limit=900)
        if evidence or effect:
            lines.append(f"{category}: {evidence or effect}")
            if evidence and effect and effect.casefold() not in evidence.casefold():
                lines.append(f"  Matchup read: {effect}")
    breakdown = decision.get("advantage_breakdown") if isinstance(decision.get("advantage_breakdown"), dict) else {}
    for category, item in breakdown.items():
        if not isinstance(item, dict):
            continue
        reason = clean_detail_text(item.get("reason"), limit=600)
        winner = clean_text(item.get("winner"), limit=80)
        margin = clean_text(item.get("margin"), limit=40)
        if reason:
            label = factor_category(str(category))
            suffix = f" ({winner}, {margin} margin)" if winner or margin else ""
            lines.append(f"{label}{suffix}: {reason}")
    for swing in decision.get("swing_factors") or []:
        if not isinstance(swing, dict):
            continue
        title = clean_text(swing.get("title"), limit=80) or "Swing factor"
        reason = clean_detail_text(swing.get("reason") or swing.get("impact"), limit=700)
        if reason:
            lines.append(f"{title}: {reason}")
    loser_path = formatted_loser_best_path_full(decision)
    if loser_path:
        lines.append(f"Why the alternate route fell short: {loser_path}")
    deduped: list[str] = []
    seen = set()
    for line in lines:
        normalized = line.casefold()
        if line and normalized not in seen:
            seen.add(normalized)
            deduped.append(line)
    return "\n".join(f"• {line}" for line in deduped) or "No expanded evidence available."


def structured_decision_output(decision: dict[str, Any]) -> dict[str, Any]:
    winner = clean_text(decision.get("winner"), limit=80)
    loser = clean_text(decision.get("loser"), limit=80)
    confidence = clean_text(decision.get("confidence"), limit=40)
    winner_pct, loser_pct = probability_pair(decision)
    summary = short_summary(decision)
    loser_best_path_short = formatted_loser_best_path(decision)
    loser_best_path_full = formatted_loser_best_path_full(decision)
    evidence = evidence_bullets(decision, limit=140)
    battle_odds_text = f"{winner or 'Winner'} {winner_pct}% / {loser or 'Loser'} {loser_pct}%"
    title = matchup_title(decision)
    display_title = f"⚔️ {title.upper()}"
    confidence_key = str(confidence or "").casefold()
    if confidence_key in {"strong", "high"}:
        confidence_color_name = "emerald"
    elif "medium" in confidence_key:
        confidence_color_name = "gold"
    elif "low" in confidence_key or "close" in confidence_key:
        confidence_color_name = "orange"
    else:
        confidence_color_name = "neutral"
    public_summary = clamp_text(summary, 300)
    full_analysis = clean_detail_text(decision.get("summary") or decision.get("analysis") or summary, limit=8000)
    full_evidence = full_evidence_text(decision)
    return {
        "matchup_title": title,
        "display_title": display_title,
        "winner": winner,
        "loser": loser,
        "confidence": confidence,
        "confidence_color_name": confidence_color_name,
        "winner_probability": winner_pct,
        "loser_probability": loser_pct,
        "battle_odds_text": battle_odds_text,
        "fight_card": fight_card_blocks(decision),
        "fighter_cards": fighter_cards(decision),
        "public_summary": public_summary,
        "quick_verdict": public_summary,
        "quick_evidence": evidence,
        "status": clean_text(decision.get("status") or "", limit=180),
        "short_summary": clamp_text(summary, 650),
        "evidence_bullets": evidence,
        "full_evidence": full_evidence,
        "loser_best_path": loser_best_path_short,
        "loser_best_path_short": loser_best_path_short,
        "loser_best_path_full": loser_best_path_full,
        "full_analysis": full_analysis,
    }


def format_fight_card(decision: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for block in structured_decision_output(decision)["fight_card"]:
        lines.append(block["name"])
        lines.extend(f"- {line}" for line in block["value"].splitlines())
    return lines


def fallback_diagnostics(decision: dict[str, Any]) -> list[str]:
    diagnostics = decision.get("diagnostics")
    lines = []
    if isinstance(diagnostics, dict):
        reason = diagnostics.get("fallback_reason")
        detail = diagnostics.get("fallback_detail")
        if reason:
            lines.append(f"fallback reason: {clean_text(reason, limit=80)}")
        if detail:
            lines.append(f"fallback detail: {clean_text(detail, limit=160)}")
    lines.extend(f"judge note: {clean_text(note, limit=160)}" for note in decision.get("judge_notes") or [])
    return [line for line in lines if line.strip()]


def format_decision(
    decision: dict[str, Any],
    *,
    limit: int = PUBLIC_LIMIT,
    include_diagnostics: bool = False,
) -> str:
    structured = structured_decision_output(decision)
    analysis = structured["short_summary"]
    loser_best_path = structured["loser_best_path"]
    lines = [
        "Nerd Fight Referee Decision",
        f"winner: {structured['winner']}",
        f"confidence: {structured['confidence']}",
    ]
    fight_card = format_fight_card(decision)
    if fight_card:
        lines.extend(["", "fight card:", *fight_card])
    lines.extend([
        "",
        "judge's analysis:",
        analysis,
    ])
    if structured["evidence_bullets"]:
        lines.extend(["", "evidence:"])
        for evidence in structured["evidence_bullets"]:
            lines.append(f"- {evidence}")
    lines.extend(["", "loser's best path:", loser_best_path])
    warnings = decision.get("warnings") or []
    if warnings:
        lines.append("caveats:")
        lines.extend(f"- {clean_text(warning, limit=160)}" for warning in warnings[:3])
    if include_diagnostics:
        diagnostics = fallback_diagnostics(decision)
        if diagnostics:
            lines.append("diagnostics:")
            lines.extend(f"- {line}" for line in diagnostics[:5])
    return clamp_text("\n".join(lines), limit)

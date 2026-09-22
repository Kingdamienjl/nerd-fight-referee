"""Shared evidence-backed presentation for Discord and the web portal."""
from typing import Any
from battlebot.fight.decision_formatter import structured_decision_output
from battlebot.fight.personality import details as personality_details
from battlebot.fight.citations import linked_citations, source_panel, evidence_brief, source_catalog, clean_profile_text

def fight_detail_payload(decision: dict[str, Any]) -> dict[str, str]:
    structured = structured_decision_output(decision)
    packet = decision.get("presentation_packet") or {}
    content = personality_details(decision, packet)
    winner = decision.get("winner") or "Unresolved"
    difficulty = decision.get("difficulty") or "Unresolved"
    verdict = decision.get("quick_verdict") or "A matchup-specific verdict is not available yet. Review the evidence before relying on the provisional result."
    return {
        **{key: linked_citations(value, packet) for key, value in content.items()},
        "quick_verdict": f"**Predicted winner: {winner}**\n**Difficulty: {difficulty}**\n\n" + linked_citations(verdict, packet),
        "quick_evidence": evidence_brief(packet),
        "full_battle": linked_citations("\n\n".join(content[f"phase_{i}"] for i in range(3)), packet),
        "sources": source_panel(packet),
        "full_analysis": structured["full_analysis"],
        "full_evidence": structured["full_evidence"] or "No expanded evidence available.",
        "loser_best_path": structured["loser_best_path_full"] or "No alternate loser path available.",
    }


def present_decision(decision):
    result = structured_decision_output(decision)
    packet = decision.get("presentation_packet") or {}
    failed = bool((decision.get("diagnostics") or {}).get("fallback"))
    winner = decision.get("winner")
    if failed or winner in (None, "", "needs_judge_review", "Unresolved"):
        winner = "Unresolved"
    result.update(winner=winner, difficulty=decision.get("difficulty") if winner != "Unresolved" else "Unresolved",
                  quick_verdict=decision.get("quick_verdict") or "A complete source-backed interaction assessment is not available.",
                  narrative_phases=decision.get("narrative_phases") if not failed else [],
                  sections=fight_detail_payload(decision), sources=source_catalog(packet),
                  assessment_status="provisional" if failed or winner == "Unresolved" else "assessed")
    result["public_summary"] = result["quick_verdict"]
    result["profile_readiness"] = {side: (packet.get(side) or {}).get("readiness") for side in ("contender_a", "contender_b")}
    for side in ("contender_a", "contender_b"):
        contender = packet.get(side) or {}
        previous = result.get(side + "_card") or {}
        tools = [clean_profile_text(x.get("name"), 120) for x in [*(contender.get("equipment") or []), *(contender.get("abilities") or [])]]
        result[side + "_card"] = {"key_tools": [x for x in tools if x][:6],
            "version": (contender.get("variant") or {}).get("variant_name") or "Canonical base",
            "win_path": previous.get("win_path") if winner != "Unresolved" else "Not established by a complete assessment.",
            "risk": previous.get("risk") if winner != "Unresolved" else "Not established by a complete assessment."}
    return result

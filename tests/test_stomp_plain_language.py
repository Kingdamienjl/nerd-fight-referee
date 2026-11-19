"""Stomp plain-language rendering tests (2026-11-18 stomp fix).

The tier pre-filter's user-facing output used to read like a scaling-forum
post (tier codes, "threshold", "5 tier gap" x4, no analogy) and leaked
internal placeholders ("source-cleanup pending", "listed signature tools").
These tests pin the SB-shaped rendering and prove non-stomp output is
byte-identical to the pre-fix formatter.

Fixtures use the REAL Kratos/Ryu packet names (pulled from the live packet
2026-11-18): Kratos's equipment/ability names are wiki-markup prose, every
one rejected by the public-safe filter; Ryu's first ability is a multi-tool
blob ending in the fragment "without them being able to recover".
"""
import copy
import re
import unittest

from battlebot.fight.decision_formatter import (
    format_decision,
    is_public_junk,
    public_safe_list,
    public_safe_text,
    sanitize_fight_card_item,
    structured_decision_output,
)
from battlebot.fight.tier_utils import TierToken, build_stomp_decision

TIER_CODE_RE = re.compile(r"\bTier\s*\d|\d+\s*tier gap|\b[01]?\d-[ABC]\b")
BANNED_WORDS = ("counterplay", "leverage", "threshold", "deployment", "tempo")


def _contender(name, tier_text, abilities, equipment=None, style="Fights head-on"):
    return {
        "canonical_name": name,
        "power_scale": {"tier": tier_text},
        "abilities": [{"name": a} for a in abilities],
        "equipment": [{"name": e} for e in (equipment or [])],
        "tactical_profile": {"combat_style": style},
    }


def _packet(a, b):
    return {"contender_a": a, "contender_b": b}


# Real names from the live Kratos vs Ryu packet (2026-11-18). _fighter_tools
# reads equipment first, so these three equipment names are the ones that
# must all be rejected for the tools line to drop.
KRATOS_EQUIPMENT = [
    "and had it taken away at the end of the quest) *Sun Shield (Optional): **Attack Reflection (Can turn attacks back at one",
    "including projectiles) !-!Artefacts=Border",
    "Precognition and Clairvoyance (The Gem of Uroboros has the same Life Cycle powers as the Amulet itself at a weaker scale",
]
KRATOS_ABILITIES = [
    "Magic is inherent to all beings. Is capable of siphoning magic and life energy from opponentsGod of War Sons of Sparta (",
    "dodge or evasion such that time stands still from his perspective",
    "these actions being described as altering timeGod of War Sons of Sparta (2026) - Goals. Could discern Ladon's diet of go",
]
RYU_ABILITIES = [
    "SF I-Alpha 3= *Superhuman Physical Characteristics *Martial Arts (Master of Shotokan Karate and Ansatsuken.) *Acrobatics",
    "without them being able to recover",
    'he can cause them to enter the "Stun" status',
]

KRATOS = _contender(
    "Kratos",
    "At least High 8-C, likely Low 7-B | 4-A, Possibly High 3-A with the Rage of the Gods, 1-C with Divine Weapons | 1-C",
    KRATOS_ABILITIES,
    equipment=KRATOS_EQUIPMENT,
)
RYU = _contender("Ryu", "6-C", RYU_ABILITIES)


def kratos_vs_ryu_stomp():
    """The measured fight: Kratos (Tier 1-C) vs Ryu (Tier 6-C), gap 5."""
    return build_stomp_decision(
        _packet(KRATOS, RYU),
        TierToken(None, 1, "C"),
        TierToken(None, 6, "C"),
    )


# Golden non-stomp decision + its pre-fix format_decision output, captured
# 2026-11-18 via render_golden.py (single format_decision call, fresh dict).
GOLDEN_DECISION = {
    "title": "Nerd Fight Referee Decision",
    "winner": "Iron Man",
    "loser": "Batman",
    "confidence": "High",
    "difficulty": "Mid Diff",
    "summary": "Iron Man controls the range. Batman cannot close without taking fire. The armor holds while the gadgets run out.",
    "win_condition": "Iron Man controls the range.",
    "loser_best_path": "Batman needed an opening Iron Man never gave him.",
    "deciding_factors": [
        {"factor": "Finishing Power", "evidence": "Iron Man has the stronger finishing lane."},
        {"factor": "Mobility / Initiative", "evidence": "Iron Man acts first and holds the range."},
    ],
    "matchup_card": [
        {
            "name": "Iron Man",
            "height_weight": "6'6\", 425 lbs",
            "weapon_power": "Repulsor array",
            "style": "Ranged aerial combat",
            "key_tools": ["Repulsor Blasts", "Uni-Beam", "Flight"],
            "best_route": "Open at range and wear Batman down.",
            "risk": "Armor can be breached by sustained fire.",
        },
        {
            "name": "Batman",
            "height_weight": "6'2\", 210 lbs",
            "weapon_power": "Utility belt",
            "style": "Stealth and close combat",
            "key_tools": ["Batarangs", "Smoke Pellets", "Grapnel Gun"],
            "best_route": "Close the distance and force a brawl.",
            "risk": "No answer for sustained aerial fire.",
        },
    ],
    "narrative_phases": [],
    "diagnostics": {"fallback": False, "pipeline": "2-llm-dynamic+schema-verdict"},
}

GOLDEN_FORMAT_DECISION = (
    "Nerd Fight Referee Decision\n"
    "winner: Iron Man\n"
    "confidence: High\n"
    "\n"
    "fight card:\n"
    "Iron Man\n"
    "- Height/Weight: 6'6\", 425 lbs\n"
    "- Weapon/Power: Repulsor array\n"
    "- Style: Ranged aerial combat\n"
    "- Key tools: Repulsor Blasts, Uni-Beam, Flight\n"
    "- Win path: Open at range and wear Batman down.\n"
    "- Risk: Armor can be breached by sustained fire.\n"
    "Batman\n"
    "- Height/Weight: 6'2\", 210 lbs\n"
    "- Weapon/Power: Utility belt\n"
    "- Style: Stealth and close combat\n"
    "- Key tools: Batarangs, Smoke Pellets, Grapnel Gun\n"
    "- Win path: Close the distance and force a brawl.\n"
    "- Risk: No answer for sustained aerial fire.\n"
    "\n"
    "judge's analysis:\n"
    "Iron Man controls the range. Batman cannot close without taking fire. The armor holds while the gadgets run out.\n"
    "\n"
    "evidence:\n"
    "- Finishing Power: Iron Man has the stronger finishing lane.\n"
    "- Mobility / Initiative: Iron Man acts first and holds the range.\n"
    "- Loser path: Batman needed an opening Iron Man never gave him.\n"
    "\n"
    "loser's best path:\n"
    "Batman needed an opening Iron Man never gave him."
)


class StompPlainLanguageTests(unittest.TestCase):
    def test_stomp_render_has_no_tier_codes_or_banned_words(self):
        text = format_decision(copy.deepcopy(kratos_vs_ryu_stomp()))
        self.assertIsNone(TIER_CODE_RE.search(text), f"tier code leaked: {text!r}")
        for word in BANNED_WORDS:
            self.assertNotIn(word, text.casefold(), f"banned word {word!r} in: {text!r}")
        self.assertNotIn("level", text.casefold())
        self.assertNotIn("VS Battles Wiki", text)

    def test_stomp_analysis_is_three_sentences_with_analogy_last(self):
        structured = structured_decision_output(copy.deepcopy(kratos_vs_ryu_stomp()))
        analysis = structured["short_summary"]
        sentences = [s.strip() for s in analysis.split(".") if s.strip()]
        self.assertEqual(len(sentences), 3, f"expected 3 sentences, got: {analysis!r}")
        self.assertTrue(
            sentences[-1].startswith("It is a firecracker against a supernova")
            or sentences[-1].endswith("a firecracker against a supernova"),
            f"analogy is not the last sentence: {analysis!r}",
        )
        self.assertIn("Ryu cannot hurt Kratos", sentences[0])
        self.assertIn("one clean hit", sentences[1])

    def test_stomp_analogy_ladder_by_gap(self):
        cases = [
            (2, "a spark against a campfire"),
            (3, "a sparkler against a bonfire"),
            (4, "a firecracker against a volcano"),
            (5, "a firecracker against a supernova"),
            (9, "a firecracker against a supernova"),
        ]
        for main_gap, analogy in cases:
            with self.subTest(gap=main_gap):
                decision = build_stomp_decision(
                    _packet(
                        _contender("Big", "1-C", ["Big Punch"]),
                        _contender("Small", f"{1 + main_gap}-C", ["Small Punch"]),
                    ),
                    TierToken(None, 1, "C"),
                    TierToken(None, 1 + main_gap, "C"),
                )
                self.assertTrue(
                    decision["summary"].rstrip(".").endswith(f"It is {analogy}"),
                    f"gap {main_gap}: {decision['summary']!r}",
                )

    def test_stomp_difficulty_in_plain_words(self):
        text = format_decision(copy.deepcopy(kratos_vs_ryu_stomp()))
        self.assertIn("difficulty: No contest", text)
        self.assertNotIn("Neg/No Diff", text)

    def test_tools_line_dropped_when_all_tools_rejected(self):
        text = format_decision(copy.deepcopy(kratos_vs_ryu_stomp()))
        self.assertNotIn("listed signature tools", text)
        self.assertNotIn("profile-backed abilities", text)
        # Kratos's card has no Key tools line at all (all names rejected);
        # Ryu's card keeps his (the blob survives as one readable item).
        kratos_card = text.split("Kratos")[1].split("Ryu")[0]
        self.assertNotIn("Key tools:", kratos_card)
        self.assertIn(
            "Key tools: Superhuman Physical Characteristics Martial Arts Acrobatics",
            text,
        )

    def test_tools_line_kept_when_tools_survive(self):
        decision = build_stomp_decision(
            _packet(
                _contender("Big", "1-C", ["Big Punch", "Big Kick"]),
                _contender("Small", "6-C", ["Small Punch"]),
            ),
            TierToken(None, 1, "C"),
            TierToken(None, 6, "C"),
        )
        text = format_decision(copy.deepcopy(decision))
        self.assertIn("Key tools: Big Punch, Big Kick", text)

    def test_risk_lines_print_real_text(self):
        text = format_decision(copy.deepcopy(kratos_vs_ryu_stomp()))
        self.assertNotIn("source-cleanup pending", text)
        self.assertIn("Almost nothing can go wrong.", text)
        self.assertIn("Every trade costs Ryu more than it costs Kratos.", text)

    def test_fragment_ability_names_excluded(self):
        self.assertEqual(
            public_safe_list(
                [
                    "Superhuman Physical Characteristics",
                    "Martial Arts",
                    "Acrobatics, without them being able to recover",
                ],
                limit=3,
            ),
            ["Superhuman Physical Characteristics", "Martial Arts", "Acrobatics"],
        )
        self.assertEqual(public_safe_list(["without them being able to recover"]), [])
        self.assertEqual(
            sanitize_fight_card_item("Acrobatics, without them being able to recover"),
            "Acrobatics",
        )
        self.assertEqual(sanitize_fight_card_item("without them being able to recover"), "")
        # Regression (gate catch, 2026-11-19): lowercase alone is NOT a
        # fragment signal — real tool names are often lowercase.
        self.assertEqual(
            public_safe_list(
                ["Materia", "SOLDIER skill", "superhuman speed"], limit=3
            ),
            ["Materia", "SOLDIER skill", "superhuman speed"],
        )
        self.assertEqual(
            public_safe_list(["Necroplasm", "chains", "teleportation"], limit=3),
            ["Necroplasm", "chains", "teleportation"],
        )
        self.assertEqual(public_safe_list(["atomic breath"], limit=3), ["atomic breath"])
        # A short starter-led name is a name, not a clause.
        self.assertEqual(public_safe_list(["Without Mercy"], limit=3), ["Without Mercy"])
        # A pronoun-led clause is still dropped.
        self.assertEqual(
            public_safe_list(['he can cause them to enter the "Stun" status']), []
        )

    def test_real_ryu_blob_survives_as_one_readable_item(self):
        self.assertEqual(
            public_safe_list(RYU_ABILITIES, limit=3),
            ["Superhuman Physical Characteristics Martial Arts Acrobatics"],
        )

    def test_sentence_risk_survives_junk_filter_when_sentence_ok(self):
        risk = "Every trade costs Ryu more than it costs Kratos."
        self.assertTrue(is_public_junk(risk), "default rule still treats long text as junk")
        self.assertFalse(is_public_junk(risk, sentence_ok=True))
        self.assertEqual(
            public_safe_text(risk, "source-cleanup pending", sentence_ok=True), risk
        )

    def test_stomp_quick_verdict_and_loser_path_are_plain(self):
        stomp = kratos_vs_ryu_stomp()
        self.assertIsNone(TIER_CODE_RE.search(stomp["quick_verdict"]))
        self.assertIn("wins with no contest", stomp["quick_verdict"])
        self.assertIsNone(TIER_CODE_RE.search(stomp["loser_best_path"]))
        structured = structured_decision_output(copy.deepcopy(stomp))
        self.assertIsNone(TIER_CODE_RE.search(structured["quick_verdict"]))
        for bullet in structured["evidence_bullets"]:
            self.assertIsNone(TIER_CODE_RE.search(bullet), f"tier code in bullet: {bullet!r}")

    def test_nonstomp_render_byte_identical(self):
        text = format_decision(copy.deepcopy(GOLDEN_DECISION))
        self.assertEqual(text, GOLDEN_FORMAT_DECISION)

    def test_nonstomp_tools_and_risk_lines_unchanged(self):
        self.assertEqual(
            public_safe_list(["Repulsor Blasts", "Uni-Beam", "Flight"], limit=3),
            ["Repulsor Blasts", "Uni-Beam", "Flight"],
        )
        self.assertEqual(
            public_safe_text("Armor can be breached by sustained fire.", "x"),
            "Armor can be breached by sustained fire.",
        )


if __name__ == "__main__":
    unittest.main()

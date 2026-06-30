import unittest

from battlebot.fight.decision_formatter import format_decision
from battlebot.fight.smoke_judge import smoke_judge_packet


def contender(name, character_id, attack, speed, durability, *, abilities=None, tactical_profile=None):
    return {
        "canonical_name": name,
        "character_id": character_id,
        "power_scale": {
            "attack_potency": attack,
            "speed": speed,
            "durability": durability,
        },
        "abilities": abilities or [],
        "equipment": [],
        "weaknesses": [],
        "tactical_profile": tactical_profile or {},
    }


def packet(a, b):
    return {"errors": [], "contender_a": a, "contender_b": b, "warnings": []}


class DecisionFormatterTests(unittest.TestCase):
    def test_public_fight_output_under_1800_characters(self):
        decision = smoke_judge_packet(
            packet(
                contender("Iron Man", "iron-man", "Outerverse level " * 80, "FTL", "Planet level"),
                contender("Batman", "batman", "Building level " * 80, "Peak Human", "Building level"),
            )
        )

        text = format_decision(decision)

        self.assertLessEqual(len(text), 1800)

    def test_public_fight_output_omits_raw_evidence_strings_and_wiki_templates(self):
        decision = {
            "title": "Nerd Fight Referee Decision",
            "winner": "Iron Man",
            "confidence": "medium",
            "win_condition": "Iron Man leads attack_potency: Athlete level " + ("Outerverse level " * 40),
            "loser_best_path": "Batman needs prep.",
            "deciding_factors": [
                {
                    "factor": "attack_potency",
                    "evidence": "Iron Man leads attack_potency: {{Border, Scroll=No}}\nOuterverse level " * 12,
                    "tactical_effect": "converts stat leads into initiative, damage pressure, and survivable exchanges",
                }
            ],
            "warnings": [],
            "judge_notes": ["LLM disabled"],
        }

        text = format_decision(decision)

        self.assertNotIn("{{Border", text)
        self.assertNotIn("Outerverse level Outerverse level Outerverse level", text)
        self.assertNotIn("converts stat leads into initiative, damage pressure, and survivable exchanges", text)
        self.assertNotIn("LLM disabled", text)

    def test_batman_iron_man_and_kratos_dante_routes_vary(self):
        batman_iron_man = smoke_judge_packet(
            packet(
                contender("Batman", "batman", "Building level", "Peak Human", "Building level"),
                contender(
                    "Iron Man",
                    "iron-man",
                    "City level",
                    "Supersonic",
                    "City level",
                    tactical_profile={"battlefield_control": "flight and ranged sensors"},
                ),
            )
        )
        kratos_dante = smoke_judge_packet(
            packet(
                contender("Kratos", "kratos", "Planet level", "Supersonic", "Planet level"),
                contender(
                    "Dante",
                    "dante",
                    "City level",
                    "FTL",
                    "City level",
                    tactical_profile={"combat_style": "agile sword-and-gun pressure"},
                ),
            )
        )

        self.assertNotEqual(batman_iron_man["win_condition"], kratos_dante["win_condition"])

    def test_structured_fields_influence_tactical_explanation(self):
        decision = smoke_judge_packet(
            packet(
                contender(
                    "A",
                    "a",
                    "Planet level",
                    "FTL",
                    "Planet level",
                    tactical_profile={"battlefield_control": "controls terrain and lanes"},
                ),
                contender("B", "b", "Building level", "Human", "Building level"),
            )
        )

        text = format_decision(decision)

        self.assertIn("judge's analysis:", text)
        self.assertIn("evidence:", text)
        self.assertIn("- Battlefield Control", text)
        self.assertIn("loser's best path:", text)
        self.assertIn("controlling distance and engagement terms", decision["win_condition"])

    def test_judge_analysis_truncates_at_sentence_boundary_when_possible(self):
        complete_sentence = "Superman uses Flight to control range. "
        decision = {
            "title": "Nerd Fight Referee Decision",
            "winner": "Superman",
            "confidence": "strong",
            "summary": (complete_sentence * 22) + ("This unfinished clause keeps expanding " * 30),
            "loser_best_path": "Batman needs repeated clean openings.",
            "deciding_factors": [],
            "warnings": [],
        }

        text = format_decision(decision)
        analysis = text.split("judge's analysis:\n", 1)[1].split("\n\nloser's best path:", 1)[0]

        self.assertTrue(analysis.endswith("..."))
        self.assertTrue(analysis.removesuffix("...").endswith("."))
        self.assertNotIn("unfinished clause", analysis)

    def test_judge_analysis_truncation_does_not_cut_mid_word(self):
        decision = {
            "title": "Nerd Fight Referee Decision",
            "winner": "Cloud",
            "confidence": "medium",
            "summary": " ".join(f"suppliedterm{i}" for i in range(140)),
            "loser_best_path": "Opponent needs a clean counter.",
            "deciding_factors": [],
            "warnings": [],
        }

        text = format_decision(decision)
        analysis = text.split("judge's analysis:\n", 1)[1].split("\n\nloser's best path:", 1)[0]
        final_word = analysis.removesuffix("...").split()[-1]

        self.assertTrue(analysis.endswith("..."))
        self.assertRegex(final_word, r"^suppliedterm\d+$")

    def test_evidence_bullets_do_not_end_with_commas(self):
        decision = {
            "title": "Nerd Fight Referee Decision",
            "winner": "Spawn",
            "confidence": "medium",
            "summary": "Spawn pressures with necroplasm, then changes angles before the counter lands.",
            "loser_best_path": "Godzilla needs to force a beam trade.",
            "deciding_factors": [
                {
                    "factor": "Battlefield Control",
                    "evidence": "Spawn has necroplasm.",
                    "tactical_effect": "Spawn uses short necroplasm bursts,",
                },
                {
                    "factor": "Resistance / Counterplay",
                    "evidence": "Godzilla has atomic breath,",
                    "tactical_effect": "",
                },
            ],
            "warnings": [],
        }

        text = format_decision(decision)
        bullets = [line for line in text.splitlines() if line.startswith("- ")]

        self.assertTrue(bullets)
        self.assertTrue(all(not bullet.endswith(",") for bullet in bullets))

    def test_evidence_bullets_include_concrete_named_ability_when_available(self):
        decision = {
            "title": "Nerd Fight Referee Decision",
            "winner": "Itachi",
            "confidence": "medium",
            "summary": "Itachi controlled the pace through named packet tools.",
            "loser_best_path": "Kratos needed to force close range.",
            "deciding_factors": [
                {
                    "factor": "Special Abilities",
                    "evidence": "Itachi brings named tools: Sharingan, Genjutsu, Susanoo",
                    "tactical_effect": "Itachi can build a fight plan around those named tools.",
                }
            ],
            "warnings": [],
        }

        text = format_decision(decision)

        self.assertIn("- Special Abilities: Itachi brings named tools: Sharingan, Genjutsu, Susanoo", text)

    def test_loser_best_path_removes_scraped_field_labels(self):
        decision = {
            "title": "Nerd Fight Referee Decision",
            "winner": "Itachi",
            "confidence": "medium",
            "summary": "Itachi controlled the pace through named packet tools.",
            "loser_best_path": (
                "Kratos needs to exploit weaknesses such as Part I= The Sharingan's ability. "
                "Notable Attacks/Techniques: Sword pressure."
            ),
            "deciding_factors": [],
            "warnings": [],
        }

        text = format_decision(decision)

        self.assertNotIn("Part I=", text)
        self.assertNotIn("Notable Attacks/Techniques:", text)
        self.assertIn("The Sharingan's ability.", text)

    def test_loser_best_path_falls_back_cleanly_when_empty(self):
        decision = {
            "title": "Nerd Fight Referee Decision",
            "winner": "Itachi",
            "confidence": "medium",
            "summary": "Itachi controlled the pace through named packet tools.",
            "loser_best_path": "",
            "deciding_factors": [],
            "warnings": [],
        }

        text = format_decision(decision)

        self.assertIn(
            "The loser needed to force the fight into their strongest confirmed lane, but the packet did not provide a clean exploitable weakness.",
            text,
        )


if __name__ == "__main__":
    unittest.main()

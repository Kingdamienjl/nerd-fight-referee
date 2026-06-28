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


if __name__ == "__main__":
    unittest.main()

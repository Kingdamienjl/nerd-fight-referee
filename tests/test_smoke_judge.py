import unittest

from battlebot.fight.smoke_judge import smoke_judge_packet, text_rank


def contender(name, character_id, attack, speed, durability, warnings=None):
    return {
        "canonical_name": name,
        "character_id": character_id,
        "power_scale": {
            "attack_potency": attack,
            "speed": speed,
            "durability": durability,
        },
        "warnings": warnings or [],
    }


RICH_ADVANTAGE_CATEGORIES = {"speed", "strength", "durability", "mobility", "range", "skill", "abilities", "battlefield"}
FIGHT_FLOW_PHASES = {"opening", "pressure", "counterplay", "adaptation", "finish", "loser_path"}
BANNED_GENERIC_PHRASES = (
    "clean openings",
    "exchange pattern",
    "main route stabilizes",
    "escalation options",
)


class SmokeJudgeTests(unittest.TestCase):
    def test_tier_phrase_ranking(self):
        self.assertGreater(text_rank("Solar System level"), text_rank("Building level"))
        self.assertGreater(text_rank("Massively FTL+", speed=True), text_rank("Peak Human", speed=True))

    def test_smoke_judge_picks_sephiroth_over_current_weak_goku_packet(self):
        packet = {
            "errors": [],
            "contender_a": contender("Son Goku", "son-goku", "Building level", "Supersonic", "Building level"),
            "contender_b": contender("Sephiroth", "sephiroth", "Solar System level", "Massively FTL+", "Solar System level"),
            "warnings": [
                {
                    "contender": "contender_a",
                    "flag": "suspicious_low_power_for_known_high_tier",
                }
            ],
        }

        result = smoke_judge_packet(packet)

        self.assertEqual(result["winner"], "Sephiroth")
        self.assertEqual(result["confidence"], "low_to_medium")
        self.assertTrue(any("Sephiroth leads" in factor["evidence"] for factor in result["deciding_factors"]))
        self.assertTrue(all("tactical_effect" in factor for factor in result["deciding_factors"]))

    def test_batman_vs_superman_style_clean_sweep_returns_strong(self):
        packet = {
            "errors": [],
            "contender_a": contender("Batman", "batman", "Building level", "Peak Human", "Building level"),
            "contender_b": contender("Superman", "superman", "Solar System level", "Massively FTL+", "Solar System level"),
            "warnings": [],
        }

        result = smoke_judge_packet(packet)

        self.assertEqual(result["winner"], "Superman")
        self.assertEqual(result["confidence"], "strong")

    def test_smoke_judge_exposes_probability_and_advantage_breakdown(self):
        packet = {
            "errors": [],
            "contender_a": contender("Batman", "batman", "Building level", "Peak Human", "Building level"),
            "contender_b": contender("Superman", "superman", "Solar System level", "Massively FTL+", "Solar System level"),
            "warnings": [],
        }

        result = smoke_judge_packet(packet)

        self.assertEqual(result["winner_probability"], 0.85)
        self.assertEqual(result["loser_probability"], 0.15)
        self.assertEqual(result["overall_probability"], {"winner": 0.85, "loser": 0.15})
        self.assertEqual(set(result["advantage_breakdown"]), RICH_ADVANTAGE_CATEGORIES)
        for factor in result["advantage_breakdown"].values():
            self.assertEqual(set(factor), {"winner", "margin", "reason"})
            self.assertIn(factor["margin"], {"low", "medium", "high"})
            self.assertTrue(factor["reason"])
            self.assertNotIn("packet compares", factor["reason"])
        self.assertTrue(result["swing_factors"])
        for factor in result["swing_factors"]:
            self.assertEqual(set(factor), {"title", "reason", "impact"})
            self.assertTrue(factor["title"])
            self.assertTrue(factor["reason"])
            self.assertTrue(factor["impact"])
        self.assertEqual(set(result["fight_flow"]), FIGHT_FLOW_PHASES)
        for phase in result["fight_flow"].values():
            self.assertTrue(phase)
            for item in phase:
                self.assertEqual(set(item), {"winner", "reason"})
                self.assertTrue(item["winner"])
                self.assertTrue(item["reason"])
        self.assertTrue(result["engine_reasoning"])
        self.assertTrue(all(isinstance(step, str) and step for step in result["engine_reasoning"]))
        self.assertEqual(
            result["engine_reasoning"][0],
            result["fight_flow"]["opening"][0]["reason"],
        )
        serialized = str(result)
        for phrase in BANNED_GENERIC_PHRASES:
            self.assertNotIn(phrase, serialized)

    def test_ordinary_loser_warning_does_not_reduce_clean_sweep_confidence(self):
        packet = {
            "errors": [],
            "contender_a": contender("Son Goku", "son-goku", "Building level", "Supersonic", "Building level"),
            "contender_b": contender("Sephiroth", "sephiroth", "Solar System level", "Massively FTL+", "Solar System level"),
            "warnings": [{"contender": "contender_a", "flag": "minor_source_note"}],
        }

        result = smoke_judge_packet(packet)

        self.assertEqual(result["winner"], "Sephiroth")
        self.assertEqual(result["confidence"], "strong")

    def test_winner_warning_caps_confidence(self):
        packet = {
            "errors": [],
            "contender_a": contender("A", "a", "Planet level", "FTL", "Planet level"),
            "contender_b": contender("B", "b", "Building level", "Human", "Building level"),
            "warnings": [{"contender": "contender_a", "flag": "needs_manual_review"}],
        }

        result = smoke_judge_packet(packet)

        self.assertEqual(result["winner"], "A")
        self.assertEqual(result["confidence"], "low_to_medium")

    def test_two_axis_lead_returns_medium(self):
        packet = {
            "errors": [],
            "contender_a": contender("A", "a", "Planet level", "FTL", "Building level"),
            "contender_b": contender("B", "b", "Building level", "Human", "Building level"),
            "warnings": [],
        }

        result = smoke_judge_packet(packet)

        self.assertEqual(result["winner"], "A")
        self.assertEqual(result["confidence"], "medium")


if __name__ == "__main__":
    unittest.main()

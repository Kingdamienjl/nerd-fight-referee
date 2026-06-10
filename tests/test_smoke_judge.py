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

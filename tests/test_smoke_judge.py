import unittest

from battlebot.fight.smoke_judge import smoke_judge_packet, text_rank


def contender(name, character_id, attack, speed, durability, warnings=None, abilities=None, weaknesses=None, equipment=None, tactical_profile=None):
    return {
        "canonical_name": name,
        "character_id": character_id,
        "power_scale": {
            "attack_potency": attack,
            "speed": speed,
            "durability": durability,
        },
        "abilities": abilities or [],
        "equipment": equipment or [],
        "weaknesses": weaknesses or [],
        "tactical_profile": tactical_profile or {},
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

    def test_deciding_factor_evidence_names_abilities_when_available(self):
        packet = {
            "errors": [],
            "contender_a": contender(
                "Itachi",
                "itachi",
                "Town level",
                "Supersonic",
                "Building level",
                abilities=[
                    {"name": "Sharingan"},
                    {"name": "Genjutsu"},
                    {"name": "Susanoo"},
                ],
            ),
            "contender_b": contender("Kratos", "kratos", "Building level", "Human", "Wall level"),
            "warnings": [],
        }

        result = smoke_judge_packet(packet)
        evidence = " ".join(factor["evidence"] for factor in result["deciding_factors"])

        self.assertIn("Sharingan", evidence)
        self.assertIn("Genjutsu", evidence)
        self.assertIn("Susanoo", evidence)

    def test_smoke_judge_exposes_compact_matchup_card_for_both_fighters(self):
        packet = {
            "errors": [],
            "contender_a": contender(
                "Spawn",
                "spawn",
                "Town level",
                "Subsonic",
                "Building level",
                abilities=[{"name": "Necroplasm"}, {"name": "teleportation"}],
                equipment=[{"name": "chains"}],
                weaknesses=[{"name": "limited necroplasm supply"}],
                tactical_profile={"forms": [{"name": "Hell King Spawn"}]},
            ),
            "contender_b": contender(
                "Godzilla",
                "godzilla",
                "Building level",
                "Human",
                "Wall level",
                abilities=[{"name": "atomic breath"}, {"name": "raw power"}],
                weaknesses=[{"name": "slower adaptation"}],
            ),
            "warnings": [],
        }

        result = smoke_judge_packet(packet)

        self.assertEqual([card["name"] for card in result["matchup_card"]], ["Spawn", "Godzilla"])
        self.assertIn("Necroplasm", result["matchup_card"][0]["key_tools"])
        self.assertIn("atomic breath", result["matchup_card"][1]["key_tools"])
        self.assertTrue(result["matchup_card"][0]["best_route"])
        self.assertTrue(result["matchup_card"][1]["best_route"])
        self.assertEqual(result["matchup_card"][0]["risk"], "limited necroplasm supply")

    def test_smoke_judge_matchup_card_extracts_physical_and_weapon_power_fields(self):
        cloud = contender(
            "Cloud Strife",
            "cloud",
            "Town level",
            "Subsonic",
            "Building level",
            abilities=[{"name": "Limit Breaks"}, {"name": "{{ tag:tabber"}],
            equipment=[{"name": "Buster Sword"}],
        )
        cloud["physical_profile"] = {"height": "5'7\"", "weight": "160 lb"}
        kratos = contender(
            "Kratos",
            "kratos",
            "Building level",
            "Human",
            "Wall level",
            equipment=[{"name": "{{Border|No|Yes|Content}}"}, {"name": "Blades of Chaos"}],
        )
        packet = {"errors": [], "contender_a": cloud, "contender_b": kratos, "warnings": []}

        result = smoke_judge_packet(packet)

        self.assertEqual(result["matchup_card"][0]["height_weight"], "5'7\" / 160 lb")
        self.assertIn("Buster Sword", result["matchup_card"][0]["weapon_power"])
        self.assertIn("Limit Breaks", result["matchup_card"][0]["key_tools"])
        self.assertNotIn("{{ tag:tabber", result["matchup_card"][0]["key_tools"])
        self.assertIn("Blades of Chaos", result["matchup_card"][1]["weapon_power"])
        self.assertNotIn("{{Border|No|Yes|Content}}", result["matchup_card"][1]["weapon_power"])

    def test_smoke_judge_rejects_image_filename_and_keeps_clean_masamune(self):
        sephiroth = contender(
            "Sephiroth",
            "sephiroth",
            "Moon level",
            "Supersonic",
            "Building level",
            abilities=[{"name": "No, Yes, Yes"}],
            equipment=[
                {"name": "SephirothCGModel CrisisCore.png"},
                {"name": "Sephiroth with the Masamune in Crisis Core Original"},
            ],
        )
        packet = {
            "errors": [],
            "contender_a": sephiroth,
            "contender_b": contender("Cloud", "cloud", "Town level", "Subsonic", "Building level"),
            "warnings": [],
        }

        result = smoke_judge_packet(packet)
        card = result["matchup_card"][0]

        self.assertIn("Masamune", card["weapon_power"])
        self.assertNotIn("SephirothCGModel CrisisCore.png", card["weapon_power"])
        self.assertNotIn("No, Yes, Yes", card["key_tools"])

    def test_smoke_judge_extracts_magical_combat_identity_and_non_physical_options(self):
        sailor_moon = contender(
            "Usagi Tsukino",
            "sailor-moon",
            "Moon level",
            "Subsonic",
            "Building level",
            abilities=[
                {"name": "Transformation"},
                {"name": "Magic"},
                {"name": "Purification"},
                {"name": "Healing"},
                {"name": "Energy Projection"},
                {"name": "Barriers"},
                {"name": "Superhuman Physical Characteristics"},
                {"name": "{{Border|No|Yes|Content}}"},
            ],
            equipment=[{"name": "Silver Crystal"}, {"name": "Moon Stick"}],
            tactical_profile={"combat_style": "magical ranged escalation"},
        )
        packet = {
            "errors": [],
            "contender_a": sailor_moon,
            "contender_b": contender("Street Fighter", "street-fighter", "Wall level", "Human", "Wall level"),
            "warnings": [],
        }

        result = smoke_judge_packet(packet)
        identity = result["matchup_card"][0]["combat_identity"]

        self.assertIn(identity["combat_mode"], {"magic user", "cosmic/reality hax user"})
        self.assertIn("Magic", identity["non_physical_options"])
        self.assertIn("Purification", identity["non_physical_options"])
        self.assertIn("Barriers", identity["non_physical_options"])
        self.assertIn("Silver Crystal", result["matchup_card"][0]["weapon_power"])
        self.assertNotIn("Superhuman Physical Characteristics", result["matchup_card"][0]["weapon_power"])
        if "Superhuman Physical Characteristics" in result["matchup_card"][0]["key_tools"]:
            self.assertLess(
                result["matchup_card"][0]["key_tools"].index("Magic"),
                result["matchup_card"][0]["key_tools"].index("Superhuman Physical Characteristics"),
            )
        self.assertNotEqual(result["matchup_card"][0]["key_tools"], ["Superhuman Physical Characteristics"])
        self.assertNotIn("{{Border", " ".join(result["matchup_card"][0]["key_tools"]))

    def test_loser_best_path_cleans_scraped_weakness_fragments(self):
        packet = {
            "errors": [],
            "contender_a": contender(
                "Itachi",
                "itachi",
                "Town level",
                "Supersonic",
                "Building level",
                weaknesses=[
                    {"name": "Part I= The Sharingan's ability to copy Ninjutsu"},
                    {"name": "Notable Attacks/Techniques: stamina drain"},
                ],
            ),
            "contender_b": contender("Kratos", "kratos", "Building level", "Human", "Wall level"),
            "warnings": [],
        }

        result = smoke_judge_packet(packet)

        self.assertNotIn("Part I=", result["loser_best_path"])
        self.assertNotIn("Notable Attacks/Techniques:", result["loser_best_path"])
        self.assertIn("The Sharingan's ability to copy Ninjutsu", result["loser_best_path"])

    def test_loser_best_path_falls_back_when_weaknesses_are_empty(self):
        packet = {
            "errors": [],
            "contender_a": contender("Itachi", "itachi", "Town level", "Supersonic", "Building level"),
            "contender_b": contender("Kratos", "kratos", "Building level", "Human", "Wall level"),
            "warnings": [],
        }

        result = smoke_judge_packet(packet)

        self.assertEqual(
            result["loser_best_path"],
            "Kratos needed to force the fight against Itachi into their most reliable opening, but the profile data did not provide a clean exploitable weakness.",
        )

    def test_incidental_terms_do_not_make_physical_fighters_magic_users(self):
        cases = [
            contender(
                "Wolverine",
                "wolverine",
                "Building level",
                "Peak Human",
                "Building level",
                abilities=[
                    {"name": "Regeneration"},
                    {"name": "Resistance to Telepathy"},
                    {"name": "Adamantium claws"},
                ],
            ),
            contender(
                "Guts",
                "guts",
                "Building level",
                "Peak Human",
                "Building level",
                equipment=[{"name": "Dragon Slayer"}],
            ),
            contender(
                "Power Girl",
                "power-girl",
                "Town level",
                "Supersonic",
                "Town level",
                abilities=[{"name": "Flight"}, {"name": "Spaceflight"}, {"name": "Superhuman Strength"}],
            ),
            contender(
                "Android 17",
                "android-17",
                "Town level",
                "Supersonic",
                "Town level",
                abilities=[{"name": "Barrier"}, {"name": "Cyborg physiology"}, {"name": "Energy Projection"}],
            ),
        ]

        for fighter in cases:
            packet = {
                "errors": [],
                "contender_a": fighter,
                "contender_b": contender("Baseline", "baseline", "Wall level", "Human", "Wall level"),
                "warnings": [],
            }
            result = smoke_judge_packet(packet)
            self.assertNotEqual(result["matchup_card"][0]["combat_identity"]["combat_mode"], "magic user")

    def test_sailor_moon_core_magic_still_classifies_as_magic_or_cosmic(self):
        packet = {
            "errors": [],
            "contender_a": contender(
                "Usagi Tsukino",
                "usagi",
                "Moon level",
                "Subsonic",
                "Building level",
                abilities=[{"name": "Magic"}, {"name": "Purification"}, {"name": "Energy Projection"}],
                equipment=[{"name": "Silver Crystal"}],
            ),
            "contender_b": contender("Baseline", "baseline", "Wall level", "Human", "Wall level"),
            "warnings": [],
        }

        result = smoke_judge_packet(packet)

        self.assertIn(result["matchup_card"][0]["combat_identity"]["combat_mode"], {"magic user", "cosmic/reality hax user"})


if __name__ == "__main__":
    unittest.main()

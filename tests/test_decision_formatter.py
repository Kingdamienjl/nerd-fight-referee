import unittest

from battlebot.fight.decision_formatter import (
    compact_field,
    format_decision,
    is_dirty_fight_card_item,
    sanitize_fight_card_item,
    split_text_for_discord,
    structured_decision_output,
)
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
        analysis = text.split("judge's analysis:\n", 1)[1].split("\n\nevidence:", 1)[0]

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
        analysis = text.split("judge's analysis:\n", 1)[1].split("\n\nevidence:", 1)[0]
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

    def test_formatted_decision_includes_compact_fight_card_for_both_fighters(self):
        decision = {
            "title": "Nerd Fight Referee Decision",
            "winner": "Spawn",
            "loser": "Godzilla",
            "confidence": "medium",
            "summary": "Spawn opened by forcing short engagements. Godzilla answered with pressure. The finish came when Spawn reset spacing.",
            "loser_best_path": "Godzilla needed to keep Spawn spending necroplasm before Spawn controlled spacing.",
            "matchup_card": [
                {
                    "name": "Spawn",
                    "key_tools": ["Necroplasm", "chains", "teleportation", "Hell King Spawn"],
                    "best_route": "Burst in and out, spend necroplasm carefully, and avoid a long attrition fight.",
                    "risk": "limited necroplasm supply",
                },
                {
                    "name": "Godzilla",
                    "key_tools": ["atomic breath", "size", "durability", "raw power"],
                    "best_route": "Force a long fight and punish Spawn's resource drain.",
                    "risk": "slower adaptation",
                },
            ],
            "deciding_factors": [
                {
                    "factor": "Forms",
                    "evidence": "Spawn had Pre-Metamorphosis, Post-Metamorphosis, and Hell King Spawn to change tempo.",
                    "tactical_effect": "",
                }
            ],
            "warnings": [],
        }

        text = format_decision(decision)

        self.assertIn("fight card:", text)
        self.assertIn("Spawn\n- Key tools: Necroplasm, chains, teleportation", text)
        self.assertIn("Godzilla\n- Key tools: atomic breath, size, durability", text)
        self.assertIn("- Win path: Burst in and out", text)
        self.assertIn("- Risk: limited necroplasm supply", text)

    def test_evidence_bullets_are_compact_and_include_loser_path(self):
        decision = {
            "title": "Nerd Fight Referee Decision",
            "winner": "Spawn",
            "loser": "Godzilla",
            "confidence": "medium",
            "summary": "Spawn opened by forcing short engagements. Godzilla answered with pressure. The finish came when Spawn reset spacing.",
            "loser_best_path": "Godzilla needed to drag the fight out and exploit Spawn's limited necroplasm before Spawn controlled spacing.",
            "deciding_factors": [
                {
                    "factor": "Forms",
                    "evidence": "Spawn had Pre-Metamorphosis, Post-Metamorphosis, and Hell King Spawn to change tempo.",
                    "tactical_effect": "",
                },
                {
                    "factor": "Mobility",
                    "evidence": "Spawn's Subsonic travel speed let him choose when to engage Godzilla.",
                    "tactical_effect": "",
                },
                {
                    "factor": "Extra",
                    "evidence": "This should not appear because evidence is capped.",
                    "tactical_effect": "",
                },
            ],
            "warnings": [],
        }

        text = format_decision(decision)
        evidence_section = text.split("\nevidence:\n", 1)[1].split("\n\nloser's best path:", 1)[0]
        bullets = [line for line in evidence_section.splitlines() if line.startswith("- ")]

        self.assertEqual(len(bullets), 3)
        self.assertTrue(any("Loser path: Godzilla" in bullet and "Spawn" in bullet for bullet in bullets))
        self.assertTrue(all(len(bullet.removeprefix("- ")) <= 140 for bullet in bullets))
        self.assertTrue(all(not bullet.endswith(",") for bullet in bullets))

    def test_evidence_omits_boolean_template_residue(self):
        structured = structured_decision_output(
            {
                "winner": "Sephiroth",
                "loser": "Cloud",
                "confidence": "medium",
                "summary": "Sephiroth controlled the weapon lane.",
                "loser_best_path": "Cloud needed to interrupt Sephiroth before range settled.",
                "deciding_factors": [
                    {"factor": "Named tools", "evidence": "named tools: No, Yes, Yes"},
                    {"factor": "Weapon", "evidence": "Weapon/power: Sephiroth's clean weapon lane is Masamune."},
                ],
            }
        )

        evidence = "\n".join(structured["quick_evidence"])

        self.assertNotIn("No, Yes, Yes", evidence)
        self.assertIn("Masamune", evidence)

    def test_structured_decision_output_is_embed_friendly(self):
        decision = {
            "title": "Nerd Fight Referee Decision",
            "winner": "Sentry",
            "loser": "Godzilla",
            "confidence": "medium",
            "summary": "Sentry opened with pressure. Godzilla forced a durability check. Sentry finished by changing range.",
            "loser_best_path": "Godzilla needed to drag the fight out before Sentry controlled the pace.",
            "matchup_card": [
                {
                    "name": "Sentry",
                    "key_tools": [
                        "Robert Reynolds= Life Creation (Created one of Sentry's first villains)...",
                        "3 & 4) Transformation",
                        "Fusionism",
                        "Energy Projection",
                        "Molecular Manipulation",
                    ],
                    "best_route": "Use versatile powers without allowing a long attrition fight.",
                    "risk": "unstable mental state",
                },
                {
                    "name": "Godzilla",
                    "key_tools": ["atomic breath", "durability", "raw power"],
                    "best_route": "Force a long fight.",
                    "risk": "slower adaptation",
                },
            ],
            "deciding_factors": [
                {
                    "factor": "Special Abilities",
                    "evidence": "Sentry brings named tools: Life Creation, Transformation, Fusionism, Energy Projection",
                    "tactical_effect": "",
                }
            ],
            "warnings": [],
        }

        structured = structured_decision_output(decision)

        self.assertEqual(structured["winner"], "Sentry")
        self.assertEqual(structured["loser"], "Godzilla")
        self.assertEqual(len(structured["fight_card"]), 2)
        self.assertIn("Life Creation", structured["fight_card"][0]["value"])
        self.assertNotIn("Robert Reynolds=", structured["fight_card"][0]["value"])
        self.assertNotIn("3 & 4)", structured["fight_card"][0]["value"])
        self.assertLessEqual(structured["fight_card"][0]["value"].splitlines()[0].count(","), 3)
        self.assertTrue(structured["evidence_bullets"])
        self.assertTrue(all(len(bullet) <= 160 for bullet in structured["evidence_bullets"]))
        self.assertTrue(all(not bullet.endswith(",") for bullet in structured["evidence_bullets"]))
        self.assertIn("Godzilla", structured["loser_best_path"])
        self.assertIn("Sentry", structured["loser_best_path"])
        self.assertNotIn("Robert Reynolds=", structured["full_evidence"])

    def test_structured_decision_output_includes_matchup_title_and_odds(self):
        decision = {
            "winner": "Sentry",
            "loser": "Wolverine",
            "confidence": "medium",
            "winner_probability": 0.65,
            "loser_probability": 0.35,
            "summary": "Sentry controlled range.",
            "loser_best_path": "Wolverine needed melee attrition before Sentry controlled range.",
            "matchup_card": [
                {"name": "Sentry", "key_tools": ["flight"], "best_route": "Deny melee.", "risk": "instability"},
                {"name": "Wolverine", "key_tools": ["Adamantium claws"], "best_route": "Force melee.", "risk": "range denial"},
            ],
            "deciding_factors": [],
        }

        structured = structured_decision_output(decision)

        self.assertEqual(structured["matchup_title"], "Sentry vs Wolverine")
        self.assertEqual(structured["display_title"], "⚔️ SENTRY VS WOLVERINE")
        self.assertEqual(structured["winner"], "Sentry")
        self.assertEqual(structured["battle_odds_text"], "Sentry 65% / Wolverine 35%")
        self.assertEqual(structured["confidence_color_name"], "gold")
        self.assertEqual(structured["fighter_cards"][0]["fighter_name"], "Sentry")
        self.assertIn("quick_verdict", structured)
        self.assertIn("full_evidence", structured)
        self.assertIn("public_summary", structured)
        self.assertIn("loser_best_path_full", structured)

    def test_medium_confidence_probability_fallback_gives_65_35(self):
        structured = structured_decision_output(
            {
                "winner": "Sentry",
                "loser": "Wolverine",
                "confidence": "medium",
                "summary": "Sentry controlled range.",
                "loser_best_path": "Wolverine needed melee attrition.",
                "deciding_factors": [],
            }
        )

        self.assertEqual(structured["winner_probability"], 65)
        self.assertEqual(structured["loser_probability"], 35)
        self.assertEqual(structured["battle_odds_text"], "Sentry 65% / Wolverine 35%")

    def test_compact_field_does_not_cut_mid_word(self):
        value = compact_field("alpha beta gamma delta", 17)

        self.assertEqual(value, "alpha beta...")

    def test_split_text_for_discord_avoids_mid_word_and_empty_chunks(self):
        chunks = split_text_for_discord("Alpha beta gamma.\n\nDelta epsilon zeta. Eta theta iota.", 24)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(chunk for chunk in chunks))
        self.assertTrue(all(len(chunk) <= 24 for chunk in chunks))
        self.assertEqual(chunks[1], "Delta epsilon zeta.")

    def test_long_analysis_splits_into_multiple_chunks(self):
        text = "\n\n".join(f"Paragraph {index} has enough words to split safely." for index in range(12))
        chunks = split_text_for_discord(text, 80)

        self.assertGreater(len(chunks), 2)
        self.assertTrue(all(" " in chunk for chunk in chunks))

    def test_sanitize_fight_card_item_removes_scraped_source_heading(self):
        item = sanitize_fight_card_item("Robert Reynolds= Life Creation (Created one of Sentry's first villains)...")

        self.assertEqual(item, "Life Creation")

    def test_dirty_fight_card_items_are_rejected(self):
        dirty_values = [
            "{{Border|No|Yes|Content}}",
            "{{ tag:tabber | Before Crisis and Crisis Core | Disc 1",
            "{{#Tag:Tabber | Before Crisis and Crisis Core | Disc 1",
            "No • Yes • Content",
            "No, Yes, Yes",
            "SephirothCGModel CrisisCore.png",
            "File:Sephiroth.jpg",
            "however",
            "are allowed to use their own personalized gear",
            "None notable Optional",
            "right, thumb",
            "Strongest consistent canonical form",
            "High 7 A with A.T. Field Name",
        ]

        for value in dirty_values:
            self.assertTrue(is_dirty_fight_card_item(value))
            self.assertEqual(sanitize_fight_card_item(value), "")

    def test_clean_weapon_phrase_survives_non_image_caption(self):
        self.assertEqual(
            sanitize_fight_card_item("Sephiroth with the Masamune in Crisis Core Original"),
            "Masamune",
        )

    def test_source_tab_residue_is_rejected_but_meaningful_names_survive(self):
        self.assertEqual(sanitize_fight_card_item("cla"), "")
        self.assertEqual(sanitize_fight_card_item("weakness, cla"), "")
        self.assertEqual(sanitize_fight_card_item("Original"), "")
        self.assertEqual(sanitize_fight_card_item("Innate"), "")
        self.assertEqual(sanitize_fight_card_item("Original Sin"), "Original Sin")
        self.assertEqual(sanitize_fight_card_item("Innate Technique: Shrine"), "Shrine")

    def test_cloud_like_dirty_item_is_omitted_from_fight_card(self):
        structured = structured_decision_output(
            {
                "winner": "Cloud",
                "loser": "Kratos",
                "confidence": "medium",
                "summary": "Cloud controlled the decisive burst.",
                "loser_best_path": "Kratos needed to force melee before Cloud controlled range.",
                "matchup_card": [
                    {
                        "name": "Cloud",
                        "key_tools": [
                            "Innate",
                            "{{ tag:tabber",
                            "Before Crisis and Crisis Core",
                            "Disc 1",
                            "Buster Sword",
                        ],
                        "best_route": "Use burst damage.",
                        "risk": "needs pressure",
                    }
                ],
            }
        )

        card = structured["fight_card"][0]["value"]

        self.assertNotIn("{{", card)
        self.assertNotIn("tag:tabber", card)
        self.assertIn("Buster Sword", card)

    def test_fight_card_includes_height_weight_and_weapon_power_when_provided(self):
        structured = structured_decision_output(
            {
                "winner": "Cloud",
                "loser": "Kratos",
                "confidence": "medium",
                "summary": "Cloud controlled the decisive burst.",
                "loser_best_path": "Kratos needed to force melee before Cloud controlled range.",
                "matchup_card": [
                    {
                        "name": "Cloud",
                        "height_weight": "5'7\" / 160 lb",
                        "weapon_power": ["Buster Sword", "Limit Breaks", "Materia"],
                        "key_tools": ["SOLDIER skill", "Materia", "superhuman speed"],
                        "best_route": "Punish openings with burst damage.",
                        "risk": "Needs pressure to access Limit Breaks.",
                    }
                ],
            }
        )

        card = structured["fight_card"][0]["value"]

        self.assertIn("Height/Weight: 5'7\" / 160 lb", card)
        self.assertIn("Weapon/Power: Buster Sword, Limit Breaks", card)
        self.assertIn("Key tools: Materia, SOLDIER skill, superhuman speed", card)

    def test_fight_card_surfaces_magical_style_and_non_physical_evidence(self):
        structured = structured_decision_output(
            {
                "winner": "Usagi Tsukino",
                "loser": "Street Fighter",
                "confidence": "medium",
                "summary": "Usagi used magical range rather than trading melee.",
                "loser_best_path": "Street Fighter needed to rush Usagi before magical escalation.",
                "matchup_card": [
                    {
                        "name": "Usagi Tsukino",
                        "weapon_power": ["Silver Crystal", "Moon Stick"],
                        "style": "magical ranged escalation",
                        "key_tools": ["Transformation", "Magic", "Purification", "Superhuman Physical Characteristics"],
                        "best_route": "Create space, escalate forms, and attack with magic instead of trading melee.",
                        "risk": "vulnerable if rushed before transformation",
                        "combat_identity": {
                            "identity_summary": "Usagi Tsukino is a magic user with non-physical options: Magic, Purification, Barriers",
                            "combat_style": "magical ranged escalation",
                            "non_physical_options": ["Magic", "Purification", "Barriers"],
                        },
                    }
                ],
                "deciding_factors": [
                    {
                        "factor": "Non-physical options",
                        "evidence": "Usagi's best lane was magical escalation and ranged pressure, not melee trading.",
                    }
                ],
            }
        )

        card = structured["fight_card"][0]["value"]
        evidence = "\n".join(structured["quick_evidence"])

        self.assertIn("Weapon/Power: Silver Crystal, Moon Stick", card)
        self.assertIn("Style: magical ranged escalation", card)
        self.assertIn("Key tools: Magic, Purification, Transformation", card)
        self.assertNotIn("Superhuman Physical Characteristics", card.split("Key tools: ", 1)[1].splitlines()[0])
        self.assertNotIn("{{", card)
        self.assertIn("magical escalation", evidence)
        self.assertTrue(all(not bullet.endswith("...") for bullet in structured["quick_evidence"]))

    def test_fight_card_omits_unknown_height_weight_cleanly(self):
        structured = structured_decision_output(
            {
                "winner": "Cloud",
                "loser": "Kratos",
                "confidence": "medium",
                "summary": "Cloud controlled the decisive burst.",
                "loser_best_path": "Kratos needed to force melee before Cloud controlled range.",
                "matchup_card": [{"name": "Cloud", "key_tools": ["Buster Sword"], "best_route": "Burst.", "risk": "pressure"}],
            }
        )

        self.assertNotIn("Height/Weight:", structured["fight_card"][0]["value"])

    def test_sanitize_fight_card_item_removes_numbering_and_markdown(self):
        item = sanitize_fight_card_item("3 & 4)Transformation *Fusionism...")

        self.assertIn(item, {"Transformation Fusionism", "Transformation, Fusionism"})
        self.assertNotIn("3 & 4)", item)
        self.assertNotIn("*", item)

    def test_fight_card_items_are_short_and_not_comma_ended(self):
        decision = {
            "winner": "Sentry",
            "loser": "Godzilla",
            "confidence": "medium",
            "summary": "Sentry controlled the range.",
            "loser_best_path": "Godzilla needed pressure.",
            "matchup_card": [
                {
                    "name": "Sentry",
                    "key_tools": [
                        "Robert Reynolds= Life Creation (Created one of Sentry's first villains)...",
                        "3 & 4)Transformation *Fusionism...",
                        "Energy Projection,",
                    ],
                    "best_route": "Use versatile powers.",
                    "risk": "unstable mental state",
                }
            ],
            "deciding_factors": [],
        }

        structured = structured_decision_output(decision)
        key_tools = structured["fight_card"][0]["value"].splitlines()[0].removeprefix("Key tools: ")

        for item in [part.strip() for part in key_tools.split(",")]:
            self.assertLessEqual(len(item), 60)
            self.assertFalse(item.endswith(","))

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

    def test_loser_best_path_names_both_fighters_and_cleans_duplicate_pronouns(self):
        decision = {
            "title": "Nerd Fight Referee Decision",
            "winner": "Itachi",
            "loser": "Kratos",
            "confidence": "medium",
            "summary": "Itachi controlled the pace through named packet tools.",
            "loser_best_path": "force close range around his, his stamina drain",
            "deciding_factors": [],
            "warnings": [],
        }

        text = format_decision(decision)
        loser_path = text.split("\n\nloser's best path:\n", 1)[1]

        self.assertIn("Kratos", loser_path)
        self.assertIn("Itachi", loser_path)
        self.assertNotIn("his, his", loser_path)

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
            "No supported loser path available.",
            text,
        )

    def test_quick_evidence_skips_source_tab_forms(self):
        structured = structured_decision_output(
            {
                "winner": "Sephiroth",
                "loser": "Cloud",
                "confidence": "medium",
                "summary": "Sephiroth had the more consistent finish.",
                "loser_best_path": "Cloud needed to pressure Sephiroth early.",
                "deciding_factors": [
                    {
                        "factor": "Forms/Eras",
                        "evidence": "Sephiroth has listed form access: Before Crisis and Crisis Core, Disc 1",
                    },
                    {"factor": "Finishing Power", "evidence": "Sephiroth has the stronger finishing tier."},
                ],
            }
        )

        evidence = "\n".join(structured["quick_evidence"])

        self.assertNotIn("Before Crisis", evidence)
        self.assertIn("stronger finishing tier", evidence)

    def test_quick_evidence_prefers_combat_reason_over_real_forms(self):
        structured = structured_decision_output(
            {
                "winner": "Spawn",
                "loser": "Godzilla",
                "confidence": "medium",
                "summary": "Spawn had the more reliable toolset.",
                "loser_best_path": "Godzilla needed sustained pressure.",
                "deciding_factors": [
                    {"factor": "Forms/Eras", "evidence": "Spawn has listed form access: Hell King Spawn."},
                    {"factor": "Finishing Power", "evidence": "Spawn has the stronger finishing tier."},
                    {"factor": "Special Abilities", "evidence": "Spawn brings named tools: Necroplasm, Teleportation"},
                ],
            }
        )

        evidence = structured["quick_evidence"]

        self.assertIn("Finishing Power", evidence[0])
        self.assertTrue(all("Forms/Eras" not in bullet for bullet in evidence[:2]))

    def test_full_evidence_uses_grouped_sections_and_no_generic_packet_phrases(self):
        structured = structured_decision_output(
            {
                "winner": "Usagi Tsukino",
                "loser": "Sephiroth",
                "confidence": "medium",
                "summary": "Usagi Tsukino controlled the pace from the supplied packet.",
                "loser_best_path": "Sephiroth needed to force their best listed tactic early.",
                "matchup_card": [
                    {
                        "name": "Usagi Tsukino",
                        "combat_identity": {"identity_summary": "Usagi Tsukino is a magic user."},
                    },
                    {
                        "name": "Sephiroth",
                        "combat_identity": {"identity_summary": "Sephiroth is a weapon specialist."},
                    },
                ],
                "deciding_factors": [
                    {"factor": "Abilities", "evidence": "Usagi Tsukino had a packet-backed route."}
                ],
            }
        )

        text = "\n".join(
            [
                structured["public_summary"],
                "\n".join(structured["quick_evidence"]),
                structured["full_evidence"],
                structured["loser_best_path"],
            ]
        )

        self.assertIn("Winner evidence", structured["full_evidence"])
        self.assertIn("Loser evidence", structured["full_evidence"])
        self.assertIn("Matchup read", structured["full_evidence"])
        self.assertNotIn("supplied packet", text)
        self.assertNotIn("packet-backed", text)
        self.assertNotIn("controlled the pace", text)
        self.assertNotIn("best listed tactic", text)

    def test_needs_judge_review_output_is_user_safe(self):
        structured = structured_decision_output(
            {
                "winner": "needs_judge_review",
                "confidence": "low",
                "verdict_type": "needs_judge_review",
                "summary": "",
                "loser_best_path": "",
                "matchup_card": [{"name": "Dirty Profile", "key_tools": ["Masamune"]}],
            }
        )

        self.assertEqual(structured["winner"], "Judge review needed")
        self.assertEqual(structured["battle_odds_text"], "Judge review needed")
        self.assertIn("needs judge review", structured["public_summary"])
        self.assertEqual(structured["loser_best_path"], "No supported loser path available.")
        self.assertNotIn("needs_judge_review", format_decision({"winner": "needs_judge_review", "verdict_type": "needs_judge_review"}))


if __name__ == "__main__":
    unittest.main()

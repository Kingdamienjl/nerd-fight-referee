import json

import yaml

from battlebot.fight.decision_formatter import sanitize_fight_card_item, structured_decision_output
from battlebot.review import fight_output_audit


def test_audit_detects_dirty_tokens_and_generic_phrases():
    entry = {
        "public_fight_card_text": "Weapon/Power: however\nKey tools: SephirothCGModel CrisisCore.png",
        "quick_evidence": ["Special Abilities: Sephiroth has listed form access: Before Crisis, Crisis Core"],
        "full_evidence": "No, Yes and {{Border Content",
        "summary": "The opponent used a packet-backed route and controlled the pace.",
        "loser_best_path": "force their strongest confirmed lane early",
    }

    problems = fight_output_audit.detect_output_problems(entry)

    assert "dirty token leakage: however" in problems
    assert "dirty token leakage: .png" in problems
    assert "dirty token leakage: No, Yes" in problems
    assert "generic narration: packet-backed route" in problems
    assert "wrong evidence label: source tabs labeled Special Abilities" in problems


def test_audit_detects_new_bad_fragments_and_style_misclassification():
    entry = {
        "public_fight_card_text": (
            "Style: Wolverine is a magic user\n"
            "Key tools: are allowed to use their own personalized gear, None notable Optional, right, thumb"
        ),
        "quick_evidence": ["Forms/Eras: Strongest consistent canonical form, Disc 3"],
        "full_evidence": "Magic, including cla and base▼",
        "summary": "The route came from the supplied packet and used the best listed tactic.",
        "loser_best_path": "repeatable control",
    }

    problems = fight_output_audit.detect_output_problems(entry)

    assert "dirty token leakage: are allowed to use their own personalized gear" in problems
    assert "dirty token leakage: none notable" in problems
    assert "dirty token leakage: right, thumb" in problems
    assert "generic narration: best listed tactic" in problems
    assert "style misclassification: likely physical/tech fighter labeled magic user" in problems


def test_low_value_standalone_tools_are_rejected():
    for value in ("however", "Intrinsic", "Original", "Innate", "Content", "No", "Yes", "cla", "weakness, cla"):
        assert sanitize_fight_card_item(value) == ""
    assert sanitize_fight_card_item("Original Sin") == "Original Sin"
    assert sanitize_fight_card_item("Innate Technique: Shrine") == "Shrine"


def test_full_evidence_groups_by_winner_loser_and_matchup():
    structured = structured_decision_output(
        {
            "winner": "Usagi Tsukino",
            "loser": "Sephiroth",
            "confidence": "medium",
            "summary": "Usagi used magical pressure.",
            "loser_best_path": "Sephiroth needed to force weapon range before Usagi escalated.",
            "matchup_card": [
                {
                    "name": "Usagi Tsukino",
                    "combat_identity": {
                        "identity_summary": "Usagi Tsukino is a magic user.",
                        "non_physical_options": ["Magic", "Purification"],
                    },
                },
                {
                    "name": "Sephiroth",
                    "combat_identity": {
                        "identity_summary": "Sephiroth is a weapon specialist.",
                        "non_physical_options": [],
                    },
                },
            ],
            "deciding_factors": [{"factor": "Weapon", "evidence": "Usagi Tsukino used Magic."}],
        }
    )

    evidence = structured["full_evidence"]

    assert "Winner evidence" in evidence
    assert "Loser evidence" in evidence
    assert "Matchup read" in evidence
    assert "Why loser path was less reliable" in evidence


def test_normalize_power_scale_accepts_dict_attack_potency():
    profile = {"power_scale": {"attack_potency": {"tier": "Moon level"}}}

    normalized = fight_output_audit.normalize_power_scale(profile)

    assert normalized["attack_potency"] == "Moon level"


def test_normalize_power_scale_accepts_nested_dict_speed():
    profile = {"stats": {"speed": {"rating": {"name": "Subsonic"}}}}

    normalized = fight_output_audit.normalize_power_scale(profile)

    assert normalized["speed"] == "Subsonic"


def test_normalize_power_scale_accepts_list_durability():
    profile = {"battle_stats": {"durability": [{"level": "Building level"}]}}

    normalized = fight_output_audit.normalize_power_scale(profile)

    assert normalized["durability"] == "Building level"


def test_audit_matchup_handles_real_shaped_dict_power_scale_fields():
    left = {
        "canonical_name": "Usagi Tsukino",
        "character_id": "usagi",
        "franchise": "Sailor Moon",
        "category": "anime",
        "power_scale": {
            "attack_potency": {"tier": "Moon level"},
            "speed": {"rating": {"name": "Subsonic"}},
            "durability": [{"level": "Building level"}],
        },
        "abilities": [{"name": "Magic"}, {"name": "Purification"}],
        "equipment": [{"name": "Silver Crystal"}],
        "battle_eligible": True,
    }
    right = {
        "canonical_name": "Sephiroth",
        "character_id": "sephiroth",
        "franchise": "Final Fantasy",
        "category": "game",
        "power_scale": {
            "attack_potency": {"value": "Town level"},
            "speed": [{"label": "Subsonic"}],
            "durability": {"text": "Building level"},
        },
        "equipment": [{"name": "Masamune"}],
        "battle_eligible": True,
    }

    entry = fight_output_audit.audit_matchup(left, right)

    assert entry["fighter_a"] == "Usagi Tsukino"
    assert entry["fighter_b"] == "Sephiroth"
    assert entry["winner"]


def test_report_writes_expected_json_shape(tmp_path):
    profiles = [
        {
            "canonical_name": "Usagi Tsukino",
            "character_id": "usagi",
            "franchise": "Sailor Moon",
            "category": "anime",
            "power_scale": {"attack_potency": "Moon level", "speed": "Subsonic", "durability": "Building level"},
            "abilities": [{"name": "Magic"}, {"name": "Purification"}],
            "equipment": [{"name": "Silver Crystal"}],
            "battle_eligible": True,
        },
        {
            "canonical_name": "Sephiroth",
            "character_id": "sephiroth",
            "franchise": "Final Fantasy",
            "category": "game",
            "power_scale": {"attack_potency": "Town level", "speed": "Subsonic", "durability": "Building level"},
            "equipment": [{"name": "Masamune"}],
            "battle_eligible": True,
        },
    ]
    report = fight_output_audit.build_report(profiles, sample_size=1, seed=1)
    target = tmp_path / "data/reports/fight_output_audit.json"

    fight_output_audit.write_report(report, path=target)
    payload = json.loads(target.read_text(encoding="utf-8"))

    assert {"summary", "entries"} <= set(payload)
    assert payload["summary"]["matchups_audited"] == 1
    assert "problem_counts_by_type" in payload["summary"]
    assert "average_quality_score" in payload["summary"]
    assert "quality_note_counts" in payload["summary"]
    assert {"quality_notes", "quality_score"} <= set(payload["entries"][0])
    assert {"fighter_a", "fighter_b", "problems", "problem_score"} <= set(payload["entries"][0])


def test_quality_notes_detect_low_quality_but_clean_output():
    entry = {
        "public_fight_card_text": (
            "Cloud\n"
            "- Weapon/Power: Final Fantasy VII\n"
            "- Key tools: I have to work harder than anyone else to win this fight\n"
            "- Win path: Cloud wins by taking first meaningful action, forcing reactions, then cashing in the higher output edge.\n"
            "- Risk: No clean exploitable weakness supplied."
        ),
        "quick_evidence": [
            "Forms/Eras: Cloud has listed form access: Disc 1",
            "Finishing Power: Cloud has the stronger finishing tier.",
        ],
        "full_evidence": "• " + ("Attack potency raw dump " * 20),
        "summary": "Cloud wins.",
        "loser_best_path": "No supported loser path available.",
    }

    notes = fight_output_audit.quality_notes_for_entry(entry)

    assert "source_label_as_tool" in notes
    assert "weak_key_tools" in notes
    assert "sentence_fragment_tool" in notes
    assert "forms_eras_overused" in notes
    assert "raw_stat_dump" in notes
    assert "generic_win_path" in notes
    assert "vague_risk" in notes
    assert fight_output_audit.quality_score_from_notes(notes) < 60


def test_named_scenario_quality_scores_are_present():
    profiles = [
        {
            "canonical_name": "Usagi Tsukino",
            "character_id": "usagi",
            "franchise": "Sailor Moon",
            "category": "anime",
            "power_scale": {"attack_potency": "Moon level", "speed": "Subsonic", "durability": "Building level"},
            "abilities": [{"name": "Magic"}, {"name": "Purification"}, {"name": "Energy Projection"}],
            "equipment": [{"name": "Silver Crystal"}],
            "battle_eligible": True,
        },
        {
            "canonical_name": "Sephiroth",
            "character_id": "sephiroth",
            "franchise": "Final Fantasy VII",
            "category": "game",
            "power_scale": {"attack_potency": "Town level", "speed": "Subsonic", "durability": "Building level"},
            "equipment": [{"name": "Masamune"}],
            "battle_eligible": True,
        },
        {
            "canonical_name": "Spawn",
            "character_id": "spawn",
            "franchise": "Image Comics",
            "category": "comic",
            "power_scale": {"attack_potency": "City level", "speed": "Supersonic", "durability": "City level"},
            "abilities": [{"name": "Necroplasm"}, {"name": "Teleportation"}],
            "equipment": [{"name": "Chains"}],
            "battle_eligible": True,
        },
        {
            "canonical_name": "Godzilla",
            "character_id": "godzilla",
            "franchise": "Godzilla",
            "category": "movie",
            "power_scale": {"attack_potency": "Town level", "speed": "Subsonic", "durability": "City level"},
            "abilities": [{"name": "Atomic breath"}, {"name": "Regeneration"}],
            "battle_eligible": True,
        },
    ]

    report = fight_output_audit.build_report(profiles, sample_size=2, seed=1)

    assert all(0 <= entry["quality_score"] <= 100 for entry in report["entries"])
    assert all(isinstance(entry["quality_notes"], list) for entry in report["entries"])


def test_audit_records_llm_foreign_entity_guard():
    left = {
        "canonical_name": "Power Girl",
        "character_id": "power-girl",
        "franchise": "DC Comics",
        "category": "comic",
        "power_scale": {"attack_potency": "Town level", "speed": "Supersonic", "durability": "Town level"},
        "abilities": [{"name": "Flight"}, {"name": "Superhuman Strength"}],
    }
    right = {
        "canonical_name": "Riddler",
        "character_id": "riddler",
        "franchise": "DC Comics",
        "category": "comic",
        "power_scale": {"attack_potency": "Wall level", "speed": "Human", "durability": "Wall level"},
        "abilities": [{"name": "Planning"}],
    }

    entry = fight_output_audit.audit_matchup(
        left,
        right,
        include_llm=True,
        llm_analysis="Green Lantern attacked Naruto with Shadow Clone Jutsu.",
    )

    assert entry["llm_guarded"] is True
    assert entry["llm_analysis"] == ""
    assert "llm foreign entity: Green Lantern" in entry["problems"]
    assert "llm foreign entity: Naruto" in entry["problems"]
    assert "llm foreign technique: Shadow Clone Jutsu" in entry["problems"]


def test_report_problem_counts_stay_empty_for_cleaned_residue_cases():
    profiles = [
        {
            "canonical_name": "Original Sin User",
            "character_id": "original-sin-user",
            "franchise": "Test",
            "category": "comic",
            "power_scale": {"attack_potency": "Town level", "speed": "Subsonic", "durability": "Building level"},
            "abilities": [{"name": "Original Sin"}, {"name": "Innate Technique: Shrine"}, {"name": "cla"}],
            "battle_eligible": True,
        },
        {
            "canonical_name": "Roy Mustang",
            "character_id": "roy-mustang",
            "franchise": "Fullmetal Alchemist",
            "category": "anime",
            "power_scale": {"attack_potency": "Building level", "speed": "Peak Human", "durability": "Wall level"},
            "abilities": [{"name": "Flame Alchemy"}, {"name": "Fire blasts"}],
            "equipment": [{"name": "Ignition gloves"}],
            "battle_eligible": True,
        },
    ]

    report = fight_output_audit.build_report(profiles, sample_size=1, seed=1)

    assert report["summary"]["problem_counts_by_type"].get("dirty token leakage", 0) == 0
    assert report["summary"]["problem_counts_by_type"].get("style misclassification", 0) == 0


def test_load_profiles_reads_battle_eligible_yaml_only(tmp_path):
    generated = tmp_path / "profiles/generated"
    generated.mkdir(parents=True)
    eligible = generated / "usagi.yaml"
    ineligible = generated / "draft.yaml"
    eligible.write_text(
        yaml.safe_dump(
            {
                "id": "usagi",
                "name": "Usagi Tsukino",
                "franchise": "Sailor Moon",
                "category": "anime",
                "battle_eligible": True,
                "abilities": [{"name": "Magic"}],
            }
        ),
        encoding="utf-8",
    )
    ineligible.write_text(yaml.safe_dump({"id": "draft", "name": "Draft"}), encoding="utf-8")

    profiles = fight_output_audit.load_profiles(generated, tmp_path / "profiles/needs_review")

    assert [profile["canonical_name"] for profile in profiles] == ["Usagi Tsukino"]

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from battlebot.harvest.auto_profile_harvester import (
    RosterRow,
    build_profile,
    explicit_none_value,
    extract_vsbattles_fields,
    profile_output_path,
    row_fingerprint,
    select_queue_rows,
    split_listish,
)


class HarvesterExtractionTests(unittest.TestCase):
    def test_pipe_field_extraction(self):
        fields = extract_vsbattles_fields(
            """
            | Tier = 4-B
            | AP = Solar System level
            | Speed = Massively FTL+
            | Durability = Solar System level
            | P&A = Flight, Ki Manipulation
            """
        )
        self.assertEqual(fields["tier"], "4-B")
        self.assertEqual(fields["attack_potency"], "Solar System level")
        self.assertEqual(fields["powers_and_abilities"], "Flight, Ki Manipulation")

    def test_bold_label_extraction(self):
        fields = extract_vsbattles_fields(
            "'''Attack Potency''': Planet level\n'''Speed''': Relativistic"
        )
        self.assertEqual(fields["attack_potency"], "Planet level")
        self.assertEqual(fields["speed"], "Relativistic")

    def test_plain_label_extraction(self):
        fields = extract_vsbattles_fields("Durability: City level\nWeakness: Fire")
        self.assertEqual(fields["durability"], "City level")
        self.assertEqual(fields["weaknesses"], "Fire")

    def test_section_heading_extraction(self):
        fields = extract_vsbattles_fields(
            """
            == Powers and Abilities ==
            Magic, teleportation, summoning
            == Standard Equipment ==
            Sword and shield
            """
        )
        self.assertIn("summoning", fields["powers_and_abilities"])
        self.assertEqual(fields["standard_equipment"], "Sword and shield")

    def test_ineligible_profile_has_generation_reasons(self):
        profile = build_profile(
            row=RosterRow(category="anime", franchise="Test", name="No Fields"),
            anilist_identity=None,
            igdb_identity=None,
            wiki_source={
                "fields": {},
                "revision_id": "123",
                "revision_timestamp": "2026-01-01T00:00:00Z",
                "source_id": "src",
                "title": "No Fields",
                "full_url": "https://example.com",
                "page_id": "1",
                "retrieved_at": "2026-01-01T00:00:00Z",
                "cache_key": "cache",
            },
            errors=[],
        )
        self.assertFalse(profile["battle_eligible"])
        self.assertEqual(profile["profile_type"], "needs_review")
        self.assertEqual(profile["status"], "needs_review")
        self.assertTrue(profile["generation"]["ineligible_reasons"])

    def test_queue_state_marks_generated_rows_complete(self):
        with TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "generated"
            review_dir = Path(tmpdir) / "needs_review"
            row = RosterRow(category="anime", franchise="Test", name="Done")
            output_path = profile_output_path(output_dir, row)
            output_path.parent.mkdir(parents=True)
            output_path.write_text("schema_version: '1'\n", encoding="utf-8")
            roster_state = {"cursor_index": 0, "completed": {}, "needs_review": {}, "failed": {}}

            selected, summary = select_queue_rows(
                [row],
                output_dir=output_dir,
                needs_review_dir=review_dir,
                roster_state=roster_state,
                skip_needs_review_existing=False,
                max_per_cycle=25,
            )

            self.assertEqual(selected, [])
            self.assertEqual(summary.completed, 1)
            self.assertIn("anime-test-done", roster_state["completed"])

    def test_queue_state_skips_completed_rows_without_reprocessing_them(self):
        with TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "generated"
            review_dir = Path(tmpdir) / "needs_review"
            done = RosterRow(category="anime", franchise="Test", name="Done")
            pending = RosterRow(category="anime", franchise="Test", name="Pending")
            roster_state = {
                "cursor_index": 0,
                "completed": {"anime-test-done": row_fingerprint(done)},
                "needs_review": {},
                "failed": {},
            }

            selected, _summary = select_queue_rows(
                [done, pending],
                output_dir=output_dir,
                needs_review_dir=review_dir,
                roster_state=roster_state,
                skip_needs_review_existing=False,
                max_per_cycle=25,
            )

            self.assertEqual([row.name for _index, row in selected], ["Pending"])

    def test_queue_mode_respects_max_per_cycle(self):
        with TemporaryDirectory() as tmpdir:
            rows = [
                RosterRow(category="anime", franchise="Test", name=f"Pending {index}")
                for index in range(3)
            ]
            selected, _summary = select_queue_rows(
                rows,
                output_dir=Path(tmpdir) / "generated",
                needs_review_dir=Path(tmpdir) / "needs_review",
                roster_state={"cursor_index": 0, "completed": {}, "needs_review": {}, "failed": {}},
                skip_needs_review_existing=False,
                max_per_cycle=2,
            )

            self.assertEqual(len(selected), 2)

    def test_queue_mode_treats_existing_needs_review_as_done_when_enabled(self):
        with TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "generated"
            review_dir = Path(tmpdir) / "needs_review"
            row = RosterRow(category="anime", franchise="Test", name="Review")
            review_path = profile_output_path(review_dir, row)
            review_path.parent.mkdir(parents=True)
            review_path.write_text("schema_version: '1'\n", encoding="utf-8")
            roster_state = {"cursor_index": 0, "completed": {}, "needs_review": {}, "failed": {}}

            selected, summary = select_queue_rows(
                [row],
                output_dir=output_dir,
                needs_review_dir=review_dir,
                roster_state=roster_state,
                skip_needs_review_existing=True,
                max_per_cycle=25,
            )

            self.assertEqual(selected, [])
            self.assertEqual(summary.needs_review, 1)


class ExplicitNoneExtractionTests(unittest.TestCase):
    """Frag-7: explicit-none weakness sections and section boundaries
    at the extraction layer (the gate 50j root cause)."""

    IMMORTAL_PAGE = (
        "'''Powers and Abilities:''' Superhuman Physical Characteristics\n"
        "'''Weaknesses:''' None notable\n"
        "'''Notable Attacks/Techniques:'''\n"
        "* '''Out Orbital Punch'''\n"
        "* '''Air Strike'''\n"
        "==Notable Matchups==\n"
        "'''Victories:'''\n"
        "Category:Characters\n"
    )

    def test_none_notable_page_yields_no_weaknesses_field(self):
        fields = extract_vsbattles_fields(self.IMMORTAL_PAGE)
        self.assertNotIn("weaknesses", fields)

    def test_explicit_none_family(self):
        for text in (
            "None",
            "none",
            "None notable",
            "None notable.",
            "None known",
            "None whatsoever",
            "N/A",
            "n/a",
            "Not applicable",
            "No weaknesses",
            "No known weaknesses",
            "None notable as of Season 2",
            "None Notable (Has never displayed a weakness)",
            "''' None notable",
            "None notable'''",
        ):
            self.assertTrue(explicit_none_value(text), text)

    def test_explicit_none_negatives(self):
        for text in (
            "No weaknesses known to his enemies, but sunlight kills him",
            "None of his attacks work on Tuesdays",
            "No weakness to magic",
            "Fire",
            "",
            None,
        ):
            self.assertFalse(explicit_none_value(text), text)

    def test_none_known_field_dropped(self):
        fields = extract_vsbattles_fields(
            "'''Attack Potency''': Planet level\n'''Weaknesses:''' None known"
        )
        self.assertEqual(fields["attack_potency"], "Planet level")
        self.assertNotIn("weaknesses", fields)

    def test_real_weakness_survives(self):
        fields = extract_vsbattles_fields(
            "'''Weaknesses:''' Fire, sunlight"
        )
        self.assertEqual(fields["weaknesses"], "Fire, sunlight")

    def test_value_truncated_at_next_heading(self):
        fields = extract_vsbattles_fields(
            "'''Weaknesses:''' He can't regenerate if his body parts "
            "are kept separate\n==Gallery==\nImage one\nImage two"
        )
        self.assertEqual(
            fields["weaknesses"],
            "He can't regenerate if his body parts are kept separate",
        )

    def test_value_truncated_at_notable_attacks_label(self):
        fields = extract_vsbattles_fields(
            "'''Weaknesses:''' Sunlight kills him Notable "
            "Attacks/Techniques: * Doom Fist * Doom Kick"
        )
        self.assertEqual(fields["weaknesses"], "Sunlight kills him")


class ThousandsCommaSplitTests(unittest.TestCase):
    """Frag-9: split_listish must not split a thousands-grouped
    number at its comma ("radiation up to 4,000 hertz" split into
    "radiation up to 4" / "000 hertz" in gate 50l)."""

    def test_thousands_comma_kept_whole(self):
        self.assertEqual(
            split_listish("radiation up to 4,000 hertz, fire, ice"),
            ["radiation up to 4,000 hertz", "fire", "ice"],
        )

    def test_millions_kept_whole(self):
        self.assertEqual(
            split_listish("deals 1,000,000 damage, fire"),
            ["deals 1,000,000 damage", "fire"],
        )

    def test_number_list_still_splits(self):
        # The comma BETWEEN two thousands numbers is a real
        # separator (followed by a space, not three digits).
        self.assertEqual(
            split_listish("1,000, 2,000"),
            ["1,000", "2,000"],
        )

    def test_ordinary_list_commas_still_split(self):
        self.assertEqual(
            split_listish("Strength 4, Speed 5"),
            ["Strength 4", "Speed 5"],
        )
        self.assertEqual(
            split_listish("fire, ice, lightning"),
            ["fire", "ice", "lightning"],
        )

    def test_short_digit_runs_still_split(self):
        # "4,00" is not a thousands grouping (two digits after).
        self.assertEqual(
            split_listish("level 4,00, fire"),
            ["level 4", "00", "fire"],
        )


class TierRatingTemplateTests(unittest.TestCase):
    """Frag-10: VSB tier ratings are TEMPLATES, not bold text --
    {{Low 5-B}} / {{High 5-A}} render as bold linked ratings on the
    page, and every template stripper deleted them, so "Low 5-B,
    likely higher. High 5-A with swords" arrived as "likely higher.
    with swords" (gate 50m, all five Transformers tiers). A rating
    template's NAME is its value: preserve it as plain text, remove
    every other template."""

    def test_arcee_verbatim_tier_keeps_both_ratings(self):
        fields = extract_vsbattles_fields(
            "'''[[Tiering System|Tier]]:''' {{Low 5-B}}, likely "
            "'''higher'''. {{High 5-A}} with swords"
        )
        self.assertEqual(
            fields["tier"], "Low 5-B, likely higher. High 5-A with swords"
        )

    def test_plain_rating_template_preserved(self):
        fields = extract_vsbattles_fields("'''Tier:''' {{9-C}}")
        self.assertEqual(fields["tier"], "9-C")

    def test_qualified_rating_template_preserved(self):
        fields = extract_vsbattles_fields(
            "'''Tier:''' {{At least 8-C}}, likely higher"
        )
        self.assertEqual(fields["tier"], "At least 8-C, likely higher")

    def test_plus_rating_template_preserved(self):
        fields = extract_vsbattles_fields(
            "'''Tier:''' {{9-A+}} with the sword"
        )
        self.assertEqual(fields["tier"], "9-A+ with the sword")

    def test_non_rating_templates_still_removed(self):
        fields = extract_vsbattles_fields(
            "'''Tier:''' {{Low 5-B}} {{SomeOther|foo}}"
        )
        self.assertEqual(fields["tier"], "Low 5-B")


if __name__ == "__main__":
    unittest.main()

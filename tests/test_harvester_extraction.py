import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from battlebot.harvest.auto_profile_harvester import (
    RosterRow,
    build_profile,
    extract_vsbattles_fields,
    profile_output_path,
    row_fingerprint,
    select_queue_rows,
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


if __name__ == "__main__":
    unittest.main()

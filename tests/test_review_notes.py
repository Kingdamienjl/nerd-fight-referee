import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from battlebot.review import service


class ReviewNotesTests(unittest.TestCase):
    def test_append_creates_notes_file_when_missing(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            notes_path = root / "profiles" / "review_notes.yaml"
            # Ensure parent dir does not exist
            if notes_path.parent.exists():
                for p in notes_path.parent.rglob("*"):
                    p.unlink(missing_ok=True)
                notes_path.parent.rmdir()

            service.add_review_note(
                profile_path=Path("profiles/needs_review/comic/dummy.yaml"),
                field_path="test",
                issue_type="unit_test",
                note="test note",
                suggested_value="val",
                source_id="s1",
                notes_path=notes_path,
            )

            self.assertTrue(notes_path.exists())
            data = service.load_yaml(notes_path)
            self.assertIn("notes", data)
            self.assertIsInstance(data["notes"], list)
            self.assertEqual(len(data["notes"]), 1)
            self.assertEqual(data["notes"][0]["issue_type"], "unit_test")


if __name__ == "__main__":
    unittest.main()

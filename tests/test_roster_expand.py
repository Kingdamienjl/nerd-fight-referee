import csv
import tempfile
import unittest
from pathlib import Path

from battlebot.rosters.expand import OUTPUT_FILES, ROSTER_HEADER, expand_rosters


class RosterExpandTests(unittest.TestCase):
    def test_expand_rosters_writes_requested_files_and_deduplicates(self):
        with tempfile.TemporaryDirectory() as temp:
            roster_dir = Path(temp)
            existing = roster_dir / "starter_roster.csv"
            existing.write_text(
                "category,franchise,name,aliases,wiki_title,wiki_url\n"
                "comic,Marvel,Iron Man,Tony Stark,Iron Man,\n",
                encoding="utf-8",
            )

            counts = expand_rosters(roster_dir, target_total=30)

            self.assertGreaterEqual(counts["total_roster_rows"], 30)
            for filename in OUTPUT_FILES.values():
                path = roster_dir / filename
                self.assertTrue(path.exists())
                with path.open(newline="", encoding="utf-8") as handle:
                    self.assertEqual(next(csv.reader(handle)), ROSTER_HEADER)

            all_rows = []
            for path in roster_dir.glob("*.csv"):
                with path.open(newline="", encoding="utf-8") as handle:
                    all_rows.extend(
                        (row["category"].casefold(), row["franchise"].casefold(), row["name"].casefold())
                        for row in csv.DictReader(handle)
                    )
            self.assertEqual(len(all_rows), len(set(all_rows)))


if __name__ == "__main__":
    unittest.main()

import csv
import tempfile
import unittest
from pathlib import Path

from battlebot.rosters.expand import OUTPUT_FILES, ROSTER_HEADER, expand_rosters


def expanded_rows(roster_dir: Path) -> list[dict[str, str]]:
    rows = []
    for filename in OUTPUT_FILES.values():
        with (roster_dir / filename).open(newline="", encoding="utf-8") as handle:
            rows.extend(dict(row) for row in csv.DictReader(handle))
    return rows


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

    def test_curated_variants_are_written_to_007(self):
        with tempfile.TemporaryDirectory() as temp:
            roster_dir = Path(temp)

            expand_rosters(roster_dir, target_total=1500)
            variant_path = roster_dir / "backfill_roster_007_variants.csv"
            with variant_path.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            names = {row["name"] for row in rows}

        self.assertIn("Iron Man (Hulkbuster)", names)
        self.assertIn("Batman (Hellbat Armor)", names)
        self.assertIn("Son Goku (Ultra Instinct)", names)
        self.assertIn("Dante (Sin Devil Trigger)", names)
        self.assertNotIn("Iron Man (DC Comics)", names)
        self.assertNotIn("Cloud Strife (Marvel Comics)", names)

    def test_expansion_uses_franchise_aware_variants(self):
        with tempfile.TemporaryDirectory() as temp:
            roster_dir = Path(temp)

            counts = expand_rosters(roster_dir, target_total=1400)
            rows = expanded_rows(roster_dir)

            self.assertGreaterEqual(counts["total_roster_rows"], 1400)
            for row in rows:
                name = row["name"]
                category = row["category"]
                franchise = row["franchise"]
                if franchise == "Marvel":
                    self.assertNotIn("(DC Comics)", name)
                    self.assertNotIn("(Anime)", name)
                    self.assertNotIn("(Post-Crisis)", name)
                if franchise == "DC":
                    self.assertNotIn("(Marvel Comics)", name)
                    self.assertNotIn("(Anime)", name)
                if category == "anime":
                    self.assertNotIn("(Marvel Comics)", name)
                    self.assertNotIn("(DC Comics)", name)
                    self.assertNotIn("(Post-Crisis)", name)
                    self.assertNotIn("(Post-Flashpoint)", name)
                    self.assertNotIn("(Rebirth)", name)
                if category == "game" and franchise == "Final Fantasy":
                    self.assertNotIn("(Marvel Comics)", name)
                    self.assertNotIn("(DC Comics)", name)
                    self.assertNotIn("(Post-Crisis)", name)


if __name__ == "__main__":
    unittest.main()

def test_non_comic_roster_expansion_uses_only_base_title_variant():
    from battlebot.rosters.expand import title_variants

    assert title_variants("anime", "Dragon Ball") == ("",)
    assert title_variants("game", "Final Fantasy") == ("",)
    assert title_variants("mixed", "Crossover Icons") == ("",)


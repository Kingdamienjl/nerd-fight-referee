import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import yaml

from battlebot.profiles.search import format_search_results, search_characters


def write_profile(path: Path, name: str, franchise: str = "Test", category: str = "anime"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(
            {
                "name": name,
                "franchise": franchise,
                "category": category,
                "battle_eligible": True,
                "sources": [],
                "abilities": [],
                "weaknesses": [],
                "power_scale": {},
            }
        ),
        encoding="utf-8",
    )


class ProfileSearchTests(unittest.IsolatedAsyncioTestCase):
    async def test_search_output_includes_status(self):
        rows = await search_characters("Batman", limit=5)
        text = format_search_results(rows)

        self.assertIn("Batman", text)
        self.assertRegex(text, "generated|needs_review|roster_stub|imported")

    async def test_alias_search_marks_alias_used(self):
        rows = await search_characters("ironman", limit=5)

        self.assertTrue(rows)
        self.assertEqual(rows[0].get("alias_canonical"), "Iron Man")

    async def test_needs_review_search_can_find_missing_profiles(self):
        from pathlib import Path
        import yaml

        needs_review_paths = sorted(Path("profiles/needs_review").rglob("*.yaml"))
        self.assertTrue(needs_review_paths, "expected at least one needs_review profile")

        searched = []
        for profile_path in needs_review_paths[:200]:
            try:
                data = yaml.safe_load(profile_path.read_text(encoding="utf-8")) or {}
            except Exception:
                continue

            candidates = [
                data.get("name"),
                data.get("character_name"),
                profile_path.stem.replace("-", " "),
            ]

            for query in [str(item).strip() for item in candidates if str(item or "").strip()]:
                searched.append(query)
                rows = await search_characters(query, status_filter="needs_review", limit=10)
                if any(row.get("status") == "needs_review" for row in rows):
                    return

        self.fail(f"could not find a searchable needs_review profile; tried: {searched[:20]}")
    async def test_characters_query_paginates_by_slice(self):
        rows = await search_characters("", status_filter="generated", limit=15)
        page_two = rows[10:15]

        self.assertLessEqual(len(page_two), 5)
        self.assertTrue(rows)

    async def test_search_iron_man_returns_base_and_curated_variant(self):
        with TemporaryDirectory() as temp_dir:
            generated = Path(temp_dir) / "generated"
            write_profile(generated / "comic" / "marvel" / "iron-man.yaml", "Iron Man", "Marvel", "comic")
            write_profile(generated / "comic" / "marvel" / "iron-man-hulkbuster.yaml", "Iron Man (Hulkbuster)", "Marvel", "comic")

            rows = await search_characters(
                "iron man",
                limit=20,
                generated_dir=generated,
                needs_review_dir=Path(temp_dir) / "missing-review",
                rosters_dir=Path(temp_dir) / "missing-rosters",
            )
        names = {row["canonical_name"] for row in rows}

        self.assertIn("Iron Man", names)
        self.assertIn("Iron Man (Hulkbuster)", names)

    async def test_exact_variant_search_resolves_variant_row(self):
        with TemporaryDirectory() as temp_dir:
            generated = Path(temp_dir) / "generated"
            write_profile(generated / "comic" / "marvel" / "iron-man-hulkbuster.yaml", "Iron Man (Hulkbuster)", "Marvel", "comic")

            rows = await search_characters(
                "Iron Man (Hulkbuster)",
                limit=10,
                generated_dir=generated,
                needs_review_dir=Path(temp_dir) / "missing-review",
                rosters_dir=Path(temp_dir) / "missing-rosters",
            )

        self.assertTrue(rows)
        self.assertEqual(rows[0]["canonical_name"], "Iron Man (Hulkbuster)")
        self.assertEqual(rows[0]["variant"]["variant_name"], "Hulkbuster")

    async def test_search_goku_ranks_son_goku_above_unrelated_alias_matches(self):
        with TemporaryDirectory() as temp_dir:
            generated = Path(temp_dir) / "generated"
            write_profile(generated / "anime" / "dragon-ball" / "son-goku.yaml", "Son Goku", "Dragon Ball")
            for name in ("Alexander Anderson", "Lars Alexandersson", "M. Bison", "Poison Ivy", "Sergeant Johnson"):
                write_profile(generated / "misc" / f"{name.lower().replace(' ', '-')}-son-goku-alias.yaml", name, "Unrelated")

            rows = await search_characters(
                "goku",
                limit=5,
                generated_dir=generated,
                needs_review_dir=Path(temp_dir) / "missing-review",
                rosters_dir=Path(temp_dir) / "missing-rosters",
            )

        self.assertGreaterEqual(len(rows), 1)
        self.assertEqual(rows[0]["canonical_name"], "Son Goku")
        names = {row["canonical_name"] for row in rows}
        self.assertNotIn("Alexander Anderson", names)
        self.assertNotIn("Lars Alexandersson", names)
        self.assertNotIn("M. Bison", names)
        self.assertNotIn("Poison Ivy", names)
        self.assertNotIn("Sergeant Johnson", names)

    async def test_search_cloud_ranks_canonical_before_crossover_duplicates(self):
        with TemporaryDirectory() as temp_dir:
            generated = Path(temp_dir) / "generated"
            write_profile(generated / "game" / "final-fantasy-vii" / "cloud-strife.yaml", "Cloud Strife", "Final Fantasy VII", "game")
            write_profile(
                generated / "game" / "crossover-icons" / "cloud-strife-crossover-icons.yaml",
                "Cloud Strife - Crossover Icons",
                "Crossover Icons",
                "game",
            )

            rows = await search_characters(
                "cloud",
                limit=5,
                generated_dir=generated,
                needs_review_dir=Path(temp_dir) / "missing-review",
                rosters_dir=Path(temp_dir) / "missing-rosters",
            )

        self.assertTrue(rows)
        self.assertEqual(rows[0]["canonical_name"], "Cloud Strife")
        self.assertNotIn("Cloud Strife - Crossover Icons", [row["canonical_name"] for row in rows])

    async def test_search_hides_roster_stubs_by_default(self):
        with TemporaryDirectory() as temp_dir:
            rosters = Path(temp_dir) / "rosters"
            rosters.mkdir()
            (rosters / "dragon-ball.csv").write_text(
                "name,franchise,category\nSon Goku (Ultra Instinct),Dragon Ball,anime\n",
                encoding="utf-8",
            )

            rows = await search_characters(
                "ultra instinct",
                limit=5,
                generated_dir=Path(temp_dir) / "missing-generated",
                needs_review_dir=Path(temp_dir) / "missing-review",
                rosters_dir=rosters,
            )

        self.assertEqual(rows, [])

    async def test_search_can_include_stubs_when_requested(self):
        with TemporaryDirectory() as temp_dir:
            rosters = Path(temp_dir) / "rosters"
            rosters.mkdir()
            (rosters / "dragon-ball.csv").write_text(
                "name,franchise,category\nSon Goku (Ultra Instinct),Dragon Ball,anime\n",
                encoding="utf-8",
            )

            rows = await search_characters(
                "ultra instinct",
                limit=5,
                include_stubs=True,
                generated_dir=Path(temp_dir) / "missing-generated",
                needs_review_dir=Path(temp_dir) / "missing-review",
                rosters_dir=rosters,
            )

        self.assertEqual(rows[0]["status"], "roster_stub")


if __name__ == "__main__":
    unittest.main()

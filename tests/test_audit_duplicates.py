import unittest

from battlebot.profiles.audit_duplicates import audit_duplicate_rows


def row(name, franchise="Test", category="anime", sources=0):
    return {
        "name": name,
        "canonical_name": name,
        "franchise": franchise,
        "category": category,
        "status": "generated",
        "battle_eligible": True,
        "profile_path": f"profiles/generated/{name}.yaml",
        "profile_json": {
            "name": name,
            "franchise": franchise,
            "category": category,
            "sources": [{"title": f"source-{index}"} for index in range(sources)],
        },
    }


class DuplicateAuditTests(unittest.TestCase):
    def test_duplicate_audit_groups_same_form_duplicates(self):
        report = audit_duplicate_rows(
            [
                row("Cloud Strife", "Final Fantasy VII", "game", sources=3),
                row("Cloud Strife - Crossover Icons", "Crossover Icons", "game", sources=1),
            ]
        )

        self.assertEqual(report["summary"]["groups"], 1)
        group = report["duplicate_groups"][0]
        self.assertEqual(group["group"], "cloud strife")
        self.assertEqual(group["universe"], "final fantasy")
        self.assertEqual(group["suggested_canonical_default"]["name"], "Cloud Strife")
        self.assertEqual(group["suggested_archive_or_merge_candidates"][0]["name"], "Cloud Strife - Crossover Icons")

    def test_duplicate_audit_preserves_true_form_variants(self):
        report = audit_duplicate_rows(
            [
                row("Son Goku (Base)", "Dragon Ball"),
                row("Son Goku (Super Saiyan)", "Dragon Ball"),
                row("Son Goku (Ultra Instinct)", "Dragon Ball"),
            ]
        )

        self.assertEqual(report["summary"]["groups"], 0)
        self.assertEqual(report["summary"]["likely_variants"], 3)

    def test_zero_different_franchises_are_homonyms_not_duplicates(self):
        report = audit_duplicate_rows(
            [
                row("Zero", "Drakengard", "game"),
                row("Zero", "Mega Man", "game"),
            ]
        )

        self.assertEqual(report["summary"]["groups"], 0)
        self.assertEqual(report["summary"]["homonyms"], 1)
        self.assertEqual(report["homonym_groups"][0]["group"], "zero")

    def test_thor_different_franchises_are_homonyms_not_duplicates(self):
        report = audit_duplicate_rows(
            [
                row("Thor", "Marvel", "comic"),
                row("Thor", "God of War", "game"),
            ]
        )

        self.assertEqual(report["summary"]["groups"], 0)
        self.assertEqual(report["summary"]["homonyms"], 1)
        self.assertEqual(report["homonym_groups"][0]["group"], "thor")

    def test_v_different_franchises_are_homonyms_not_duplicates(self):
        report = audit_duplicate_rows(
            [
                row("V", "Cyberpunk 2077", "game"),
                row("V", "Devil May Cry", "game"),
            ]
        )

        self.assertEqual(report["summary"]["groups"], 0)
        self.assertEqual(report["summary"]["homonyms"], 1)
        self.assertEqual(report["homonym_groups"][0]["group"], "v")

    def test_fake_variant_is_flagged(self):
        report = audit_duplicate_rows([row("Cloud Strife (DC Comics)", "Final Fantasy", "game")])

        self.assertEqual(report["summary"]["invalid_variants"], 1)
        self.assertEqual(report["invalid_variants"][0]["name"], "Cloud Strife (DC Comics)")


if __name__ == "__main__":
    unittest.main()

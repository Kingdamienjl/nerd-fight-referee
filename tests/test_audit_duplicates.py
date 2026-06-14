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


if __name__ == "__main__":
    unittest.main()

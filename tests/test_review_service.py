import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import yaml

from battlebot.review import service
from battlebot.schemas.profile import CharacterProfile


def minimal_profile(name="Batman", *, missing_core=False):
    text = None if missing_core else "Building level"
    return {
        "name": name,
        "franchise": "DC",
        "category": "comic",
        "profile_type": "needs_review",
        "status": "needs_review",
        "battle_eligible": False,
        "generation": {
            "confidence": 0.4 if missing_core else 0.8,
            "ineligible_reasons": ["needs_review"],
        },
        "power_scale": {
            "attack_potency": {
                "text": text,
                "source_ids": [] if missing_core else ["source-1"],
                "confidence": 0.8,
            },
            "speed": {
                "text": None if missing_core else "Supersonic",
                "source_ids": [] if missing_core else ["source-1"],
                "confidence": 0.8,
            },
            "durability": {
                "text": None if missing_core else "Building level",
                "source_ids": [] if missing_core else ["source-1"],
                "confidence": 0.8,
            },
        },
        "abilities": [] if missing_core else [{"id": "ability-1", "description": "Uses tools."}],
        "weaknesses": [{"id": "weakness-1", "description": "Human limits."}],
        "sources": [
            {
                "id": "source-1",
                "title": name,
                "source_type": "mediawiki",
                "revision_id": "123",
                "url": "https://example.test/wiki",
            }
        ],
        "review": {},
    }


def write_profile(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


class ReviewServiceTests(unittest.TestCase):
    def test_list_needs_review_profiles_finds_temporary_batman_superman(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            needs_review = root / "profiles" / "needs_review"
            write_profile(needs_review / "comic" / "dc" / "batman.yaml", minimal_profile("Batman"))
            write_profile(needs_review / "comic" / "dc" / "superman.yaml", minimal_profile("Superman"))

            profiles = service.list_profiles(
                generated_dir=root / "profiles" / "generated",
                needs_review_dir=needs_review,
                rejected_dir=root / "profiles" / "rejected",
                kind="needs_review",
            )

        self.assertEqual([profile["name"] for profile in profiles], ["Batman", "Superman"])

    def test_inspect_profile_returns_missing_core_fields(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "profiles" / "needs_review" / "comic" / "dc" / "batman.yaml"
            write_profile(path, minimal_profile("Batman", missing_core=True))

            inspection = service.inspect_profile(path)

        self.assertEqual(
            inspection["missing_core_fields"],
            ["attack_potency", "speed", "durability"],
        )
        self.assertIn("missing_attack", inspection["review_reasons"])

    def test_approve_refuses_missing_core_fields_unless_forced(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            needs_review = root / "profiles" / "needs_review"
            generated = root / "profiles" / "generated"
            notes = root / "profiles" / "review_notes.yaml"
            path = needs_review / "comic" / "dc" / "batman.yaml"
            write_profile(path, minimal_profile("Batman", missing_core=True))

            result = service.approve_profile(
                path,
                needs_review_dir=needs_review,
                generated_dir=generated,
                notes_path=notes,
            )
            forced = service.approve_profile(
                path,
                force=True,
                needs_review_dir=needs_review,
                generated_dir=generated,
                notes_path=notes,
            )

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "approval_blockers")
        self.assertIn("missing_attack_potency", result["approval_blockers"])
        self.assertTrue(forced["ok"])

    def test_approve_copies_profile_to_generated_path(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            needs_review = root / "profiles" / "needs_review"
            generated = root / "profiles" / "generated"
            path = needs_review / "comic" / "dc" / "batman.yaml"
            write_profile(path, minimal_profile("Batman"))

            result = service.approve_profile(
                path,
                needs_review_dir=needs_review,
                generated_dir=generated,
                notes_path=root / "profiles" / "review_notes.yaml",
            )
            destination = Path(result["destination"])
            approved = yaml.safe_load(destination.read_text(encoding="utf-8"))

        self.assertTrue(result["ok"])
        self.assertEqual(destination, generated / "comic" / "dc" / "batman.yaml")
        self.assertEqual(approved["status"], "approved_override")
        self.assertTrue(approved["battle_eligible"])

    def test_reject_copies_profile_to_rejected_path(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            needs_review = root / "profiles" / "needs_review"
            rejected = root / "profiles" / "rejected"
            path = needs_review / "comic" / "dc" / "batman.yaml"
            write_profile(path, minimal_profile("Batman"))

            result = service.reject_profile(
                path,
                note="wrong page",
                needs_review_dir=needs_review,
                rejected_dir=rejected,
                notes_path=root / "profiles" / "review_notes.yaml",
            )
            rejected_path_exists = (rejected / "comic" / "dc" / "batman.yaml").exists()

        self.assertTrue(result["ok"])
        self.assertTrue(rejected_path_exists)

    def test_review_note_storage_appends_notes_safely(self):
        with TemporaryDirectory() as temp_dir:
            notes = Path(temp_dir) / "profiles" / "review_notes.yaml"

            service.add_review_note("profiles/needs_review/batman.yaml", note="first", notes_path=notes)
            service.add_review_note("profiles/needs_review/batman.yaml", note="second", notes_path=notes)
            data = yaml.safe_load(notes.read_text(encoding="utf-8"))

        self.assertEqual([note["note"] for note in data["notes"]], ["first", "second"])

    def test_add_source_appends_source(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "profiles" / "needs_review" / "comic" / "dc" / "batman.yaml"
            notes = Path(temp_dir) / "profiles" / "review_notes.yaml"
            write_profile(path, minimal_profile("Batman"))

            result = service.add_source(
                path,
                title="Batman",
                url="https://example.test/batman",
                source_type="mediawiki",
                revision_id="9348088",
                notes_path=notes,
            )
            data = yaml.safe_load(path.read_text(encoding="utf-8"))

        self.assertTrue(result["ok"])
        self.assertEqual(data["sources"][-1]["revision_id"], "9348088")

    def test_set_core_field_refuses_unknown_field(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "profiles" / "needs_review" / "comic" / "dc" / "batman.yaml"
            write_profile(path, minimal_profile("Batman"))

            result = service.set_core_field(
                path,
                field="unknown",
                text="City level",
                source_id="source-1",
                confidence=0.75,
            )

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "unknown_core_field")

    def test_set_core_field_writes_source_ids(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "profiles" / "needs_review" / "comic" / "dc" / "batman.yaml"
            notes = Path(temp_dir) / "profiles" / "review_notes.yaml"
            write_profile(path, minimal_profile("Batman", missing_core=True))

            result = service.set_core_field(
                path,
                field="attack_potency",
                text="Building level",
                source_id="source-1",
                confidence=0.75,
                note="Manual review repair",
                notes_path=notes,
            )
            data = yaml.safe_load(path.read_text(encoding="utf-8"))

        self.assertTrue(result["ok"])
        self.assertEqual(data["power_scale"]["attack_potency"]["source_ids"], ["source-1"])
        self.assertEqual(data["power_scale"]["attack_potency"]["confidence"], 0.75)

    def test_add_ability_appends_valid_ability_shape(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "profiles" / "needs_review" / "comic" / "dc" / "batman.yaml"
            write_profile(path, minimal_profile("Batman", missing_core=True))

            result = service.add_ability(
                path,
                name="Detective skill",
                description="Uses investigation and preparation.",
                source_id="source-1",
                confidence=0.75,
                tags="prep, intelligence",
            )
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            ability = data["abilities"][-1]

        self.assertTrue(result["ok"])
        self.assertEqual(ability["source_ids"], ["source-1"])
        self.assertEqual(ability["activation_requirements"], [])
        self.assertEqual(ability["tags"], ["prep", "intelligence"])

    def test_approve_refuses_profile_with_missing_ability(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            needs_review = root / "profiles" / "needs_review"
            generated = root / "profiles" / "generated"
            path = needs_review / "comic" / "dc" / "batman.yaml"
            profile = minimal_profile("Batman")
            profile["abilities"] = []
            write_profile(path, profile)

            result = service.approve_profile(
                path,
                needs_review_dir=needs_review,
                generated_dir=generated,
                notes_path=root / "profiles" / "review_notes.yaml",
            )

        self.assertFalse(result["ok"])
        self.assertIn("missing_ability", result["approval_blockers"])

    def test_approve_allows_repaired_profile(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            needs_review = root / "profiles" / "needs_review"
            generated = root / "profiles" / "generated"
            path = needs_review / "comic" / "dc" / "batman.yaml"
            write_profile(path, minimal_profile("Batman"))

            result = service.approve_profile(
                path,
                needs_review_dir=needs_review,
                generated_dir=generated,
                notes_path=root / "profiles" / "review_notes.yaml",
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["approval_blockers"], [])

    def test_manual_edits_append_review_notes(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "profiles" / "needs_review" / "comic" / "dc" / "batman.yaml"
            notes = Path(temp_dir) / "profiles" / "review_notes.yaml"
            write_profile(path, minimal_profile("Batman", missing_core=True))

            service.set_core_field(
                path,
                field="speed",
                text="Peak human",
                source_id="source-1",
                confidence=0.75,
                note="Manual review repair",
                notes_path=notes,
            )
            data = yaml.safe_load(notes.read_text(encoding="utf-8"))

        self.assertEqual(data["notes"][-1]["issue_type"], "manual_repair")
        self.assertEqual(data["notes"][-1]["source_id"], "source-1")
        self.assertEqual(data["notes"][-1]["field_path"], "power_scale.speed.text")

    def test_approving_profile_with_repair_metadata_writes_generated_without_repair(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            needs_review = root / "profiles" / "needs_review"
            generated = root / "profiles" / "generated"
            source_profile = yaml.safe_load(
                Path("profiles/generated/anime/dragon-ball/son-goku.yaml").read_text(encoding="utf-8")
            )
            source_profile["repair"] = {"attempted_at": "2026-01-01T00:00:00Z"}
            path = needs_review / "anime" / "dragon-ball" / "son-goku.yaml"
            write_profile(path, source_profile)

            result = service.approve_profile(
                path,
                needs_review_dir=needs_review,
                generated_dir=generated,
                notes_path=root / "profiles" / "review_notes.yaml",
            )
            approved = yaml.safe_load(Path(result["destination"]).read_text(encoding="utf-8"))
            original = yaml.safe_load(path.read_text(encoding="utf-8"))

        self.assertTrue(result["ok"])
        self.assertNotIn("repair", approved)
        self.assertIn("repair", original)

    def test_generated_yaml_validates_after_approval(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            needs_review = root / "profiles" / "needs_review"
            generated = root / "profiles" / "generated"
            source_profile = yaml.safe_load(
                Path("profiles/generated/anime/naruto/naruto-uzumaki.yaml").read_text(encoding="utf-8")
            )
            source_profile["repair"] = {"source_attempts": []}
            path = needs_review / "anime" / "naruto" / "naruto-uzumaki.yaml"
            write_profile(path, source_profile)

            result = service.approve_profile(
                path,
                needs_review_dir=needs_review,
                generated_dir=generated,
                notes_path=root / "profiles" / "review_notes.yaml",
            )
            approved = yaml.safe_load(Path(result["destination"]).read_text(encoding="utf-8"))

        self.assertEqual(CharacterProfile.model_validate(approved).status, "approved_override")


if __name__ == "__main__":
    unittest.main()

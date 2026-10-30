import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import yaml

from services.verification_progress import main


class VerificationProgressTests(unittest.TestCase):
    def test_progress_report_tracks_verified_and_flagged_counts(self):
        with TemporaryDirectory() as folder:
            tmp_path = Path(folder)
            generated = tmp_path / "generated"
            needs_review = tmp_path / "needs_review"
            state = tmp_path / "state"
            generated.mkdir()
            needs_review.mkdir()
            state.mkdir()
            (generated / "ready.yaml").write_text(yaml.safe_dump({"battle_eligible": True, "status": "ready"}))
            (generated / "blocked.yaml").write_text(yaml.safe_dump({"battle_eligible": False, "status": "review"}))
            (needs_review / "candidate.yaml").write_text("name: Candidate\n")
            (state / "preview-state.json").write_text(json.dumps({"a": {"status": "needs_review", "blockers": ["speed"]}}))
            (state / "apply-state.json").write_text(json.dumps({"b": {"status": "promoted"}}))
            output = tmp_path / "progress.json"
            history = tmp_path / "progress.jsonl"
            with patch("sys.argv", [
                "verification_progress",
                "--generated-root", str(generated),
                "--needs-review-root", str(needs_review),
                "--state-root", str(state),
                "--output", str(output),
                "--history", str(history),
                "--target", "10",
                "--skip-database",
            ]):
                self.assertEqual(main(), 0)
            report = json.loads(output.read_text())
            self.assertEqual(report["generated_profiles"], 2)
            self.assertEqual(report["stored_battle_eligible_yaml"], 1)
            self.assertEqual(report["source_verified_repair_promotions"], 1)
            self.assertEqual(report["needs_review_files"], 1)
            self.assertIsNone(report["database_battle_eligible"])
            self.assertIsNone(report["remaining_to_target_by_database_eligible"])
            self.assertEqual(report["preview_blockers"], {"speed": 1})


if __name__ == "__main__":
    unittest.main()

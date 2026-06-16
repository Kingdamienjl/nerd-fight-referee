import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import yaml

from battlebot.review.repair_malformed_yaml import repair_malformed_yaml


class RepairMalformedYAMLTests(unittest.TestCase):
    def test_repair_malformed_yaml_produces_report(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            generated = root / "profiles" / "generated"
            needs_review = root / "profiles" / "needs_review"
            good = generated / "anime" / "x" / "good.yaml"
            bad = needs_review / "comic" / "dc" / "bad.yaml"
            report_path = root / "report.json"
            quarantine = root / "profiles" / "quarantined" / "malformed_yaml"
            good.parent.mkdir(parents=True)
            bad.parent.mkdir(parents=True)
            good.write_text(yaml.safe_dump({"name": "Good"}), encoding="utf-8")
            bad.write_text("name: [unterminated\n", encoding="utf-8")

            report = repair_malformed_yaml(
                generated_dir=generated,
                needs_review_dir=needs_review,
                quarantine_dir=quarantine,
                report_path=report_path,
            )
            written = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertFalse(bad.exists())
            self.assertTrue(Path(report["malformed"][0]["quarantine_path"]).exists())

            self.assertEqual(report["scanned"], 2)
            self.assertEqual(report["quarantined"], 1)
            self.assertEqual(written["report_path"], str(report_path))


if __name__ == "__main__":
    unittest.main()

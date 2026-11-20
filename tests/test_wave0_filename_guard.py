"""Wave 0: filename-too-long crash fix for the harvester.

Two parts, tested separately:
1. ``safe_profile_filename`` caps every profile filename at 250 bytes
   (255 minus the YAML writer's ``.<name>.tmp`` staging sibling),
   deterministically, with a hash suffix so distinct long names never
   collide into one file.
2. Per-row error containment: one poison row (e.g. an OSError from a bad
   filename, or any other per-row exception) is recorded as failed and the
   queue run / batch continues with the next row instead of dying.
"""

import unittest
from argparse import Namespace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, MagicMock, patch

from battlebot.harvest.auto_profile_harvester import (
    HarvestResult,
    ProfileHarvester,
    RosterRow,
    build_arg_parser,
    load_json_state,
    profile_output_path,
    run_once,
    run_queue_once,
    safe_profile_filename,
)

LONG_FORM_SUFFIX = "lorem ipsum dolor sit amet " * 40


def long_scoped_name() -> str:
    return f"Aranea (Summary: {LONG_FORM_SUFFIX}Powers and Stats)"


class SafeProfileFilenameTests(unittest.TestCase):
    def test_short_name_unchanged(self):
        self.assertEqual(safe_profile_filename("Murray"), "murray.yaml")
        self.assertEqual(safe_profile_filename("Monkey D. Luffy"), "monkey-d-luffy.yaml")

    def test_long_name_truncated_to_255_bytes(self):
        filename = safe_profile_filename(long_scoped_name())
        # 250-byte cap: the YAML writer stages through a ".<name>.tmp"
        # sibling, which must itself stay within the 255-byte limit.
        self.assertLessEqual(len(filename.encode()), 250)
        self.assertLessEqual(len(f".{filename}.tmp".encode()), 255)
        self.assertTrue(filename.endswith(".yaml"))

    def test_long_name_deterministic(self):
        name = long_scoped_name()
        self.assertEqual(safe_profile_filename(name), safe_profile_filename(name))

    def test_two_long_names_do_not_collide(self):
        first = long_scoped_name() + " alpha"
        second = long_scoped_name() + " omega"
        self.assertNotEqual(safe_profile_filename(first), safe_profile_filename(second))
        for name in (first, second):
            filename = safe_profile_filename(name)
            self.assertLessEqual(len(filename.encode("utf-8")), 250)

    def test_profile_output_path_caps_scoped_form_filename(self):
        row = RosterRow(
            category="game",
            franchise="Dungeons & Dragons",
            name=long_scoped_name(),
        )
        target = profile_output_path(Path("/tmp/out"), row)
        self.assertLessEqual(len(target.name.encode("utf-8")), 250)
        self.assertEqual(target.parent.name, "dungeons-dragons")

    def test_profile_output_path_short_row_byte_identical(self):
        row = RosterRow(category="anime", franchise="Test", name="Murray")
        target = profile_output_path(Path("/tmp/out"), row)
        self.assertEqual(target, Path("/tmp/out/anime/test/murray.yaml"))


def _write_roster_csv(path: Path) -> None:
    path.write_text(
        "category,franchise,name,aliases,wiki_title,wiki_url\n"
        "game,Test,Poison,,, \n"
        "game,Test,Next,,, \n",
        encoding="utf-8",
    )


def _queue_args(tmpdir: str, csv_path: Path) -> Namespace:
    parser = build_arg_parser()
    return parser.parse_args(
        [
            "--input",
            str(csv_path),
            "--output",
            str(Path(tmpdir) / "generated"),
            "--needs-review",
            str(Path(tmpdir) / "needs_review"),
            "--state-file",
            str(Path(tmpdir) / "state.json"),
            "--cache-dir",
            str(Path(tmpdir) / "cache"),
            "--max-per-cycle",
            "8",
        ]
    )


async def _fake_harvest_row(self, row: RosterRow) -> HarvestResult:
    if row.name == "Poison":
        raise OSError(36, "File name too long")
    return HarvestResult(
        row=row,
        output_path=Path("/tmp/out/game/test/next.yaml"),
        status="needs_review",
    )


async def _passthrough_revid(rows, **kwargs):
    return (rows, {})


class PerRowContainmentTests(unittest.IsolatedAsyncioTestCase):
    async def test_poison_row_fails_without_killing_queue_run(self):
        with TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "roster.csv"
            _write_roster_csv(csv_path)
            args = _queue_args(tmpdir, csv_path)
            gate = MagicMock()
            gate.filter_rows = AsyncMock(side_effect=_passthrough_revid)
            with (
                patch(
                    "battlebot.harvest.revid_checker.RevidGate",
                    return_value=gate,
                ),
                patch(
                    "battlebot.harvest.auto_profile_harvester.drain_recentchanges_feed",
                    return_value=([], 0),
                ),
                patch.object(ProfileHarvester, "harvest_row", new=_fake_harvest_row),
            ):
                results, processed = await run_queue_once(args, 0)
            self.assertEqual(processed, 2)
            self.assertEqual(
                [result.status for result in results],
                ["failed", "needs_review"],
            )
            self.assertIn("File name too long", results[0].errors[0])
            state = load_json_state(Path(tmpdir) / "state.json")
            rosters = state.get("rosters", {})
            _, roster_state = next(iter(rosters.items()))
            failed = roster_state.get("failed", {})
            self.assertEqual(len(failed), 1)
            self.assertIn("game-test-poison", failed)

    async def test_poison_row_fails_without_killing_run_once(self):
        with TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "roster.csv"
            _write_roster_csv(csv_path)
            parser = build_arg_parser()
            args = parser.parse_args(
                [
                    "--input",
                    str(csv_path),
                    "--output",
                    str(Path(tmpdir) / "generated"),
                    "--needs-review",
                    str(Path(tmpdir) / "needs_review"),
                    "--cache-dir",
                    str(Path(tmpdir) / "cache"),
                ]
            )
            with patch.object(ProfileHarvester, "harvest_row", new=_fake_harvest_row):
                results = await run_once(args)
            self.assertEqual(
                [result.status for result in results],
                ["failed", "needs_review"],
            )
            self.assertIn("File name too long", results[0].errors[0])

"""Slug-collision fix: the fast path must see collapsed source ids.

enrich_sources records title-spelling variants ("Batman DC" and
"Batman (DC)") that slugify to the same source id. readiness flags two
URLs under one id as ambiguous_source_identity, and the full path's
duplicate-id collapse runs only after the fast-path check -- so the fast
path could never fire on enriched content. repair_profile now collapses
duplicate ids (the same _collapse_duplicate_source_ids the full path
already runs) before the fast-path check, evaluated on a copy so the full
path still sees the profile exactly as loaded.
"""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import yaml

from battlebot.review import auto_repair, enrich_sources, service

FIXTURE = Path("tests/fixtures/review_repair/batman_table.wikitext")


def write_profile(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def gate_clean_batman() -> dict:
    """A profile an earlier repair pass already stamped battle-ready:
    provisional + eligible, complete core fields, one usable linked
    ability, one resolved mediawiki source. Only the enrich-introduced
    duplicate source ids stand between it and the fast path."""
    return {
        "name": "Batman",
        "franchise": "DC",
        "category": "comic",
        "profile_type": "needs_review",
        "status": "provisional",
        "battle_eligible": True,
        "generation": {"confidence": 0.9, "ineligible_reasons": []},
        "power_scale": {
            "tier": {"text": "9-A", "source_ids": ["source-1"], "confidence": 0.8},
            "attack_potency": {
                "text": "Small Building level",
                "source_ids": ["source-1"],
                "confidence": 0.8,
            },
            "speed": {"text": "Superhuman", "source_ids": ["source-1"], "confidence": 0.8},
            "durability": {
                "text": "Small Building level",
                "source_ids": ["source-1"],
                "confidence": 0.8,
            },
        },
        "abilities": [
            {
                "name": "Martial Arts",
                "description": "Master martial artist with extensive training.",
                "source_ids": ["source-1"],
            }
        ],
        "equipment": [],
        "weaknesses": [],
        "sources": [
            {
                "id": "source-1",
                "title": "Batman",
                "url": "https://vsbattles.fandom.com/wiki/Batman",
                "source_type": "mediawiki",
                "revision_id": "9348088",
                "revision_timestamp": "2026-01-01T00:00:00Z",
            }
        ],
        "review": {},
    }


def needs_repair_batman() -> dict:
    """Same shape as gate_clean_batman but unstamped and missing core
    fields, so it must take the full path."""
    data = gate_clean_batman()
    data["status"] = "needs_review"
    data["battle_eligible"] = False
    data["generation"] = {"confidence": 0.35, "ineligible_reasons": ["needs_review"]}
    for field in ("attack_potency", "speed", "durability"):
        data["power_scale"][field] = {"text": None, "source_ids": [], "confidence": 0.0}
    data["abilities"] = []
    return data


async def fake_fetch_source_fields(source):
    return auto_repair.parse_source_content(FIXTURE.read_text(encoding="utf-8")), {
        "title": source.get("title") or "Batman",
        "url": source.get("url"),
        "revision_id": "9348088",
        "revision_timestamp": "2026-01-01T00:00:00Z",
        "source_type": "mediawiki",
        "note": "ok",
    }


def duplicate_id_groups(profile: dict) -> dict[str, set[str]]:
    by_id: dict[str, set[str]] = {}
    for source in profile.get("sources") or []:
        if isinstance(source, dict) and source.get("id"):
            by_id.setdefault(str(source["id"]), set()).add(str(source.get("url") or ""))
    return {sid: urls for sid, urls in by_id.items() if len(urls) > 1}


class SlugCollisionTests(unittest.TestCase):
    def test_enrich_adds_both_spellings_under_one_id(self):
        data, added, _ = enrich_sources.enrich_profile_sources(gate_clean_batman())
        groups = duplicate_id_groups(data)

        self.assertGreater(added, 0)
        self.assertIn("vsbattles-batman-dc", groups)
        self.assertEqual(
            groups["vsbattles-batman-dc"],
            {
                "https://vsbattles.fandom.com/wiki/Batman_DC",
                "https://vsbattles.fandom.com/wiki/Batman_%28DC%29",
            },
        )
        self.assertIn("ambiguous_source_identity", service.approval_blockers(data))

    def test_collapse_removes_the_ambiguity_keeping_parenthetical_url(self):
        data, _, _ = enrich_sources.enrich_profile_sources(gate_clean_batman())
        dropped = auto_repair._collapse_duplicate_source_ids(data)

        self.assertGreater(dropped, 0)
        self.assertEqual(duplicate_id_groups(data), {})
        survivors = [
            source
            for source in data["sources"]
            if source.get("id") == "vsbattles-batman-dc"
        ]
        self.assertEqual(len(survivors), 1)
        self.assertEqual(
            survivors[0]["url"],
            "https://vsbattles.fandom.com/wiki/Batman_%28DC%29",
        )
        self.assertNotIn("ambiguous_source_identity", service.approval_blockers(data))

    def test_collapse_keeps_resolved_entries_and_matching_stubs(self):
        profile = {
            "sources": [
                {
                    "id": "dup",
                    "url": "https://example.test/wiki/Plain",
                    "revision_id": "7",
                },
                {"id": "dup", "url": "https://example.test/wiki/Plain"},
                {"id": "dup", "url": "https://example.test/wiki/Other"},
            ]
        }

        dropped = auto_repair._collapse_duplicate_source_ids(profile)

        self.assertEqual(dropped, 1)
        self.assertEqual(
            [source["url"] for source in profile["sources"]],
            ["https://example.test/wiki/Plain", "https://example.test/wiki/Plain"],
        )

    def test_collapse_ignores_same_url_groups(self):
        profile = {
            "sources": [
                {"id": "dup", "url": "https://example.test/wiki/Same"},
                {"id": "dup", "url": "https://example.test/wiki/Same"},
            ]
        }

        dropped = auto_repair._collapse_duplicate_source_ids(profile)

        self.assertEqual(dropped, 0)
        self.assertEqual(len(profile["sources"]), 2)

    def test_collapse_leaves_non_duplicate_sources_alone(self):
        profile = {
            "sources": [
                {"id": "one", "url": "https://example.test/wiki/One"},
                {"id": "two", "url": "https://example.test/wiki/Two"},
            ]
        }

        dropped = auto_repair._collapse_duplicate_source_ids(profile)

        self.assertEqual(dropped, 0)
        self.assertEqual(len(profile["sources"]), 2)


class FastPathCollapseTests(unittest.IsolatedAsyncioTestCase):
    async def test_fast_path_fires_on_enriched_colliding_profile_without_fetching(self):
        async def no_fetch(source):
            raise AssertionError("fast path must not fetch")

        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "profiles"
            needs_review = root / "needs_review"
            generated = root / "generated"
            path = needs_review / "comic" / "dc" / "batman.yaml"
            write_profile(path, gate_clean_batman())
            # Replicate batch_promote: enrich in place, then repair.
            enrich_sources.enrich_path(path)

            with patch(
                "battlebot.review.auto_repair.fetch_source_fields", no_fetch
            ):
                result = await auto_repair.repair_profile(
                    path,
                    promote_if_valid=True,
                    needs_review_dir=needs_review,
                    generated_dir=generated,
                    notes_path=root / "review_notes.yaml",
                    debug_dir=Path(temp_dir) / "debug",
                )

            generated_exists = (generated / "comic" / "dc" / "batman.yaml").exists()
            on_disk = service.load_yaml(path)

        self.assertTrue(result.promoted)
        self.assertEqual(result.source_attempts, [])
        self.assertTrue(generated_exists)
        # The collapse was persisted: one record left for the colliding id.
        self.assertEqual(duplicate_id_groups(on_disk), {})

    async def test_fast_path_without_collision_leaves_file_byte_identical(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "profiles"
            needs_review = root / "needs_review"
            generated = root / "generated"
            path = needs_review / "comic" / "dc" / "batman.yaml"
            write_profile(path, gate_clean_batman())
            before = path.read_bytes()

            result = await auto_repair.repair_profile(
                path,
                promote_if_valid=True,
                needs_review_dir=needs_review,
                generated_dir=generated,
                notes_path=root / "review_notes.yaml",
                debug_dir=Path(temp_dir) / "debug",
            )
            after = path.read_bytes()

        self.assertTrue(result.promoted)
        self.assertEqual(before, after)

    async def test_dry_run_does_not_fast_path_or_rewrite(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "profiles"
            needs_review = root / "needs_review"
            path = needs_review / "comic" / "dc" / "batman.yaml"
            write_profile(path, gate_clean_batman())
            enrich_sources.enrich_path(path)
            before = path.read_bytes()

            with patch(
                "battlebot.review.auto_repair.fetch_source_fields",
                fake_fetch_source_fields,
            ):
                result = await auto_repair.repair_profile(
                    path,
                    dry_run=True,
                    promote_if_valid=True,
                    needs_review_dir=needs_review,
                    generated_dir=root / "generated",
                    notes_path=root / "review_notes.yaml",
                    debug_dir=Path(temp_dir) / "debug",
                )
            after = path.read_bytes()

        self.assertFalse(result.promoted)
        self.assertEqual(after, before)

    async def test_full_path_still_runs_for_profiles_needing_repair(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "profiles"
            needs_review = root / "needs_review"
            generated = root / "generated"
            path = needs_review / "comic" / "dc" / "batman.yaml"
            write_profile(path, needs_repair_batman())
            enrich_sources.enrich_path(path)

            with patch(
                "battlebot.review.auto_repair.fetch_source_fields",
                fake_fetch_source_fields,
            ):
                result = await auto_repair.repair_profile(
                    path,
                    promote_if_valid=True,
                    needs_review_dir=needs_review,
                    generated_dir=generated,
                    notes_path=root / "review_notes.yaml",
                    debug_dir=Path(temp_dir) / "debug",
                    max_source_candidates=1,
                )
            generated_exists = (generated / "comic" / "dc" / "batman.yaml").exists()

        self.assertTrue(result.promoted)
        self.assertTrue(result.source_attempts)
        self.assertTrue(result.repaired_fields)
        self.assertTrue(generated_exists)

    async def test_full_path_sees_profile_uncollapsed(self):
        seen_counts: list[int] = []
        original = auto_repair.profile_source_candidates

        def spy(profile, *args, **kwargs):
            seen_counts.append(len(profile.get("sources") or []))
            return original(profile, *args, **kwargs)

        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "profiles"
            needs_review = root / "needs_review"
            path = needs_review / "comic" / "dc" / "batman.yaml"
            write_profile(path, needs_repair_batman())
            enrich_sources.enrich_path(path)
            enriched_count = len(service.load_yaml(path).get("sources") or [])

            with (
                patch(
                    "battlebot.review.auto_repair.fetch_source_fields",
                    fake_fetch_source_fields,
                ),
                patch(
                    "battlebot.review.auto_repair.profile_source_candidates", spy
                ),
            ):
                await auto_repair.repair_profile(
                    path,
                    promote_if_valid=True,
                    needs_review_dir=needs_review,
                    generated_dir=root / "generated",
                    notes_path=root / "review_notes.yaml",
                    debug_dir=Path(temp_dir) / "debug",
                    max_source_candidates=1,
                )

        self.assertTrue(seen_counts)
        self.assertEqual(seen_counts[0], enriched_count)

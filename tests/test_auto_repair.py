import unittest
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import yaml

from battlebot.review import auto_repair, service


FIXTURE = Path("tests/fixtures/review_repair/batman_table.wikitext")
PARSE_FIXTURE = Path("tests/fixtures/review_repair/mediawiki_parse_superman.json")
SEARCH_FIXTURE = Path("tests/fixtures/review_repair/mediawiki_search_superman.json")
NO_FIELDS_FIXTURE = Path("tests/fixtures/review_repair/fetched_no_fields.html")
YAMI_EMBEDDED_STATS_FIXTURE = Path("tests/fixtures/review_repair/yami_embedded_stats_excerpt.wikitext")


def profile_data(*, missing_core=True):
    text = None if missing_core else "Existing attack"
    return {
        "name": "Batman",
        "franchise": "DC",
        "category": "comic",
        "profile_type": "needs_review",
        "status": "needs_review",
        "battle_eligible": False,
        "generation": {"confidence": 0.35, "ineligible_reasons": ["needs_review"]},
        "power_scale": {
            "tier": {"text": None, "source_ids": [], "confidence": 0.0},
            "attack_potency": {"text": text, "source_ids": ["source-1"] if text else [], "confidence": 0.8},
            "speed": {"text": None, "source_ids": [], "confidence": 0.0},
            "durability": {"text": None, "source_ids": [], "confidence": 0.0},
        },
        "abilities": [],
        "equipment": [],
        "weaknesses": [],
        "sources": [
            {
                "id": "source-1",
                "title": "Batman",
                "url": "https://vsbattles.fandom.com/wiki/Batman",
                "source_type": "mediawiki",
                "revision_id": "9348088",
            }
        ],
        "review": {},
    }


def character_profile(name: str, franchise: str, category: str) -> dict:
    data = profile_data(missing_core=True)
    data["name"] = name
    data["franchise"] = franchise
    data["category"] = category
    data["sources"] = []
    return data


def write_profile(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


async def fake_fetch_source_fields(source):
    return auto_repair.parse_source_content(FIXTURE.read_text(encoding="utf-8")), {
        "title": source.get("title") or "Batman",
        "url": source.get("url"),
        "revision_id": "9348088",
        "revision_timestamp": "2026-01-01T00:00:00Z",
        "source_type": "mediawiki",
        "note": "ok",
    }


async def fake_fetch_no_fields(source):
    content = NO_FIELDS_FIXTURE.read_text(encoding="utf-8")
    return {}, {
        "title": source.get("title") or "Batman",
        "url": source.get("url"),
        "revision_id": "1",
        "source_type": "mediawiki",
        "note": "fetched_but_no_fields",
        "fetch_status": "fetched",
        "http_status": 200,
        "content_length": len(content),
        "content_kind": "html",
        "headings_detected": auto_repair.detected_headings(content),
        "stat_labels_detected": auto_repair.detected_stat_labels(content),
    }


class AutoRepairTests(unittest.IsolatedAsyncioTestCase):
    def test_repair_detects_missing_core_fields(self):
        profile = profile_data(missing_core=True)

        self.assertEqual(
            auto_repair.missing_targets(profile),
            ["attack_potency", "speed", "durability", "abilities"],
        )

    def test_mediawiki_parser_extracts_core_fields_from_fixture(self):
        fields = auto_repair.parse_source_content(FIXTURE.read_text(encoding="utf-8"))

        self.assertEqual(fields["attack_potency"], "Building level with standard equipment")
        self.assertEqual(fields["speed"], "Peak Human combat speed")
        self.assertEqual(fields["durability"], "Wall level physically, higher with armor")

    def test_parser_normalizes_common_stat_label_variants(self):
        content = """
        | Tier = 9-A
        | AP = Building level
        | Speed = Peak Human
        | Durability = Wall level
        | Powers/Abilities = Martial Arts, Stealth
        | Stamina = High
        | Range = Extended melee
        """

        fields = auto_repair.parse_source_content(content)

        self.assertEqual(fields["tier"], "9-A")
        self.assertEqual(fields["attack_potency"], "Building level")
        self.assertEqual(fields["speed"], "Peak Human")
        self.assertEqual(fields["durability"], "Wall level")
        self.assertEqual(fields["powers_and_abilities"], "Martial Arts, Stealth")
        self.assertEqual(fields["stamina"], "High")
        self.assertEqual(fields["range"], "Extended melee")

    def test_parser_normalizes_attack_potency_and_powers_and_abilities_labels(self):
        content = """
        Attack Potency: City level
        Powers and Abilities: Flight, Energy Projection
        """

        fields = auto_repair.parse_source_content(content)

        self.assertEqual(fields["attack_potency"], "City level")
        self.assertEqual(fields["powers_and_abilities"], "Flight, Energy Projection")

    def test_parser_normalizes_plain_abilities_label(self):
        fields = auto_repair.parse_source_content("Abilities: Precognition, Telepathy")

        self.assertEqual(fields["powers_and_abilities"], "Precognition, Telepathy")

    def test_parser_extracts_embedded_delimiterless_stats_from_table_excerpt(self):
        fields = auto_repair.parse_source_content(YAMI_EMBEDDED_STATS_FIXTURE.read_text(encoding="utf-8"))

        self.assertIn("Dark Magic", fields["powers_and_abilities"])
        self.assertEqual(
            fields["attack_potency"],
            "Large Mountain level (Able to damage Patry) | Country level+ (Damaged Zagred)",
        )
        self.assertEqual(fields["speed"], "Massively Hypersonic (Can keep up with Patry)")
        self.assertEqual(fields["durability"], "Large Mountain level (Comparable to his Attack Potency)")
        self.assertEqual(fields["stamina"], "Very high")
        self.assertEqual(fields["range"], "Extended melee range, hundreds of meters with ranged attacks")

    def test_parser_uses_first_useful_abilities_section_when_table_field_is_missing(self):
        content = """
        == Summary ==
        Short profile text.
        == Abilities ==
        * Flight
        * Energy Projection
        == Gallery ==
        image.jpg
        """

        fields = auto_repair.parse_source_content(content)

        self.assertEqual(fields["powers_and_abilities"], "* Flight * Energy Projection")

    async def test_existing_values_are_not_overwritten_by_default(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "profiles" / "needs_review" / "comic" / "dc" / "batman.yaml"
            write_profile(path, profile_data(missing_core=False))

            with patch("battlebot.review.auto_repair.fetch_source_fields", fake_fetch_source_fields):
                await auto_repair.repair_profile(path, notes_path=Path(temp_dir) / "notes.yaml")
            repaired = service.load_yaml(path)

        self.assertEqual(repaired["power_scale"]["attack_potency"]["text"], "Existing attack")
        self.assertEqual(repaired["power_scale"]["speed"]["text"], "Peak Human combat speed")

    async def test_overwrite_replaces_values(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "profiles" / "needs_review" / "comic" / "dc" / "batman.yaml"
            write_profile(path, profile_data(missing_core=False))

            with patch("battlebot.review.auto_repair.fetch_source_fields", fake_fetch_source_fields):
                await auto_repair.repair_profile(
                    path,
                    overwrite=True,
                    notes_path=Path(temp_dir) / "notes.yaml",
                )
            repaired = service.load_yaml(path)

        self.assertEqual(
            repaired["power_scale"]["attack_potency"]["text"],
            "Building level with standard equipment",
        )

    async def test_extracted_ability_has_valid_schema_shape(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "profiles" / "needs_review" / "comic" / "dc" / "batman.yaml"
            write_profile(path, profile_data(missing_core=True))

            with patch("battlebot.review.auto_repair.fetch_source_fields", fake_fetch_source_fields):
                await auto_repair.repair_profile(path, notes_path=Path(temp_dir) / "notes.yaml")
            ability = service.load_yaml(path)["abilities"][0]

        self.assertIn("id", ability)
        self.assertIn("description", ability)
        self.assertEqual(ability["source_ids"], ["source-1"])
        self.assertEqual(ability["activation_requirements"], [])

    async def test_review_notes_are_appended(self):
        with TemporaryDirectory() as temp_dir:
            notes = Path(temp_dir) / "review_notes.yaml"
            path = Path(temp_dir) / "profiles" / "needs_review" / "comic" / "dc" / "batman.yaml"
            write_profile(path, profile_data(missing_core=True))

            with patch("battlebot.review.auto_repair.fetch_source_fields", fake_fetch_source_fields):
                await auto_repair.repair_profile(path, notes_path=notes)
            data = yaml.safe_load(notes.read_text(encoding="utf-8"))

        self.assertEqual(data["notes"][0]["issue_type"], "auto_repair")
        self.assertEqual(data["notes"][0]["source_id"], "source-1")

    async def test_promote_if_valid_copies_to_generated_when_blockers_are_gone(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "profiles"
            needs_review = root / "needs_review"
            generated = root / "generated"
            path = needs_review / "comic" / "dc" / "batman.yaml"
            write_profile(path, profile_data(missing_core=True))

            with patch("battlebot.review.auto_repair.fetch_source_fields", fake_fetch_source_fields):
                result = await auto_repair.repair_profile(
                    path,
                    promote_if_valid=True,
                    needs_review_dir=needs_review,
                    generated_dir=generated,
                    notes_path=root / "review_notes.yaml",
                    max_source_candidates=1,
                )
            generated_exists = (generated / "comic" / "dc" / "batman.yaml").exists()

        self.assertTrue(result.promoted)
        self.assertTrue(generated_exists)

    async def test_invalid_repaired_profile_remains_in_needs_review(self):
        async def no_fields(source):
            return {}, {"note": "no_fields"}

        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "profiles"
            needs_review = root / "needs_review"
            generated = root / "generated"
            path = needs_review / "comic" / "dc" / "batman.yaml"
            write_profile(path, profile_data(missing_core=True))

            with patch("battlebot.review.auto_repair.fetch_source_fields", no_fields):
                result = await auto_repair.repair_profile(
                    path,
                    promote_if_valid=True,
                    needs_review_dir=needs_review,
                    generated_dir=generated,
                    notes_path=root / "review_notes.yaml",
                )
            needs_review_exists = path.exists()
            generated_exists = (generated / "comic" / "dc" / "batman.yaml").exists()

        self.assertFalse(result.promoted)
        self.assertTrue(needs_review_exists)
        self.assertFalse(generated_exists)

    async def test_dry_run_writes_nothing(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "profiles" / "needs_review" / "comic" / "dc" / "batman.yaml"
            write_profile(path, profile_data(missing_core=True))
            before = path.read_text(encoding="utf-8")

            with patch("battlebot.review.auto_repair.fetch_source_fields", fake_fetch_source_fields):
                result = await auto_repair.repair_profile(
                    path,
                    dry_run=True,
                    notes_path=Path(temp_dir) / "notes.yaml",
                )
            after = path.read_text(encoding="utf-8")

        self.assertTrue(result.changed)
        self.assertEqual(before, after)

    async def test_repair_report_json_is_written(self):
        with TemporaryDirectory() as temp_dir:
            debug_dir = Path(temp_dir) / "debug"
            path = Path(temp_dir) / "profiles" / "needs_review" / "comic" / "dc" / "batman.yaml"
            write_profile(path, profile_data(missing_core=True))

            with patch("battlebot.review.auto_repair.fetch_source_fields", fake_fetch_source_fields):
                await auto_repair.repair_profile(path, debug_dir=debug_dir, notes_path=Path(temp_dir) / "notes.yaml")
            report = json.loads((debug_dir / "batman.json").read_text(encoding="utf-8"))

        self.assertEqual(report["profile_path"], str(path))
        self.assertIn("source_attempts", report)

    async def test_report_records_fetched_but_no_fields_case(self):
        with TemporaryDirectory() as temp_dir:
            debug_dir = Path(temp_dir) / "debug"
            path = Path(temp_dir) / "profiles" / "needs_review" / "comic" / "dc" / "batman.yaml"
            write_profile(path, profile_data(missing_core=True))

            with patch("battlebot.review.auto_repair.fetch_source_fields", fake_fetch_no_fields):
                await auto_repair.repair_profile(path, debug_dir=debug_dir, notes_path=Path(temp_dir) / "notes.yaml")
            report = json.loads((debug_dir / "batman.json").read_text(encoding="utf-8"))

        self.assertEqual(report["source_attempts"][0]["extraction_failure_reason"], "fetched_but_no_fields")
        self.assertEqual(report["source_attempts"][0]["content_kind"], "html")
        self.assertGreaterEqual(report["failure_reasons"]["fetched_but_no_fields"], 1)

    def test_mediawiki_api_parse_fixture_extracts_core_fields(self):
        body = json.loads(PARSE_FIXTURE.read_text(encoding="utf-8"))
        rendered = auto_repair.rendered_text_from_parse(body)
        wikitext = body["parse"]["wikitext"]["*"]
        fields = auto_repair.parse_source_content(rendered)
        fields.update({k: v for k, v in auto_repair.parse_source_content(wikitext).items() if k not in fields})

        self.assertEqual(fields["attack_potency"], "Solar System level")
        self.assertEqual(fields["speed"], "Massively FTL+")
        self.assertEqual(fields["durability"], "Solar System level")

    def test_mediawiki_search_fixture_creates_multiple_candidate_titles(self):
        body = json.loads(SEARCH_FIXTURE.read_text(encoding="utf-8"))

        self.assertEqual(
            auto_repair.mediawiki_search_titles_from_body(body),
            ["Superman", "Superman (Post-Crisis)", "Superman (Post-Flashpoint)"],
        )

    def test_search_candidate_prefers_iron_man_marvel_over_dc(self):
        providers = auto_repair.source_registry.enabled_providers(["vsbattles"])
        provider = providers["vsbattles"]
        profile = character_profile("Iron Man", "Marvel", "comic")

        candidates = auto_repair.mediawiki_search_candidates(
            profile,
            provider,
            ["Iron Man (DC Comics)", "Iron Man (Marvel Comics)", "Iron Man"],
            query="Iron Man Marvel",
        )

        self.assertEqual(candidates[0]["title"], "Iron Man (Marvel Comics)")
        self.assertFalse(any(candidate["title"] == "Iron Man (DC Comics)" for candidate in candidates))

    def test_search_candidate_rejects_cloud_strife_marvel(self):
        providers = auto_repair.source_registry.enabled_providers(["vsbattles"])
        provider = providers["vsbattles"]
        profile = character_profile("Cloud Strife", "Final Fantasy", "game")

        candidates = auto_repair.mediawiki_search_candidates(
            profile,
            provider,
            ["Cloud Strife (Marvel Comics)"],
            query="Cloud Strife Final Fantasy",
        )

        self.assertEqual(candidates, [])

    def test_variant_source_queries_include_parent_and_keyword(self):
        profile = character_profile("Iron Man (Hulkbuster)", "Marvel", "comic")

        queries = auto_repair.source_search_queries(profile, Path("missing"))

        self.assertIn("Iron Man (Hulkbuster)", queries)
        self.assertIn("Iron Man Hulkbuster", queries)
        self.assertIn("Iron Man Hulkbuster Marvel", queries)

    def test_fake_cross_franchise_variant_remains_rejected(self):
        profile = character_profile("Iron Man", "Marvel", "comic")
        source = {"title": "Iron Man (DC Comics)", "extracted_fields": ["attack_potency"]}

        self.assertFalse(auto_repair.valid_source_candidate(profile, source))
        self.assertEqual(source["rejection_reason"], "wrong_franchise")

    def test_search_candidate_accepts_cloud_strife_final_fantasy(self):
        providers = auto_repair.source_registry.enabled_providers(["vsbattles"])
        provider = providers["vsbattles"]
        profile = character_profile("Cloud Strife", "Final Fantasy", "game")

        candidates = auto_repair.mediawiki_search_candidates(
            profile,
            provider,
            ["Cloud Strife", "Cloud Strife (Final Fantasy)"],
            query="Cloud Strife Final Fantasy",
        )

        self.assertEqual(candidates[0]["title"], "Cloud Strife (Final Fantasy)")

    def test_candidates_with_core_fields_rank_above_no_core_candidates(self):
        profile = character_profile("Iron Man", "Marvel", "comic")
        core = {
            "title": "Iron Man (Marvel Comics)",
            "authority": "high",
            "extracted_fields": ["attack_potency", "speed", "durability", "powers_and_abilities"],
        }
        no_core = {
            "title": "Iron Man",
            "authority": "high",
            "extracted_fields": [],
        }

        self.assertGreater(
            auto_repair.rank_source_candidate(profile, core),
            auto_repair.rank_source_candidate(profile, no_core),
        )
        self.assertFalse(auto_repair.valid_source_candidate(profile, no_core))

    def test_source_candidate_overrides_prioritize_batman_variants(self):
        candidates = auto_repair.profile_source_candidates(profile_data(missing_core=True), Path("missing"))
        titles = [candidate.get("title") for candidate in candidates[:4]]

        self.assertIn("Batman (Post-Crisis)", titles)
        self.assertIn("Batman (Post-Flashpoint)", titles)

    async def test_ambiguous_candidates_select_primary_and_auto_promote_provisional(self):
        async def variant_fetch(source):
            return await fake_fetch_source_fields(source)

        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "profiles"
            needs_review = root / "needs_review"
            generated = root / "generated"
            path = needs_review / "comic" / "dc" / "batman.yaml"
            write_profile(path, profile_data(missing_core=True))

            with patch("battlebot.review.auto_repair.fetch_source_fields", variant_fetch):
                result = await auto_repair.repair_profile(
                    path,
                    promote_if_valid=True,
                    needs_review_dir=needs_review,
                    generated_dir=generated,
                    debug_dir=Path(temp_dir) / "debug",
                    notes_path=root / "review_notes.yaml",
                    max_source_candidates=3,
                )
            generated_exists = (generated / "comic" / "dc" / "batman.yaml").exists()
            generated_profile = service.load_yaml(generated / "comic" / "dc" / "batman.yaml") if generated_exists else {}

        self.assertFalse(result.needs_human_source_choice)
        self.assertTrue(result.promoted)
        self.assertTrue(generated_exists)
        self.assertEqual(generated_profile["status"], "provisional")
        self.assertGreaterEqual(generated_profile["generation"]["confidence"], 0.60)

    async def test_second_independent_source_upgrades_to_verified(self):
        async def independent_fetch(source):
            fields, metadata = await fake_fetch_source_fields(source)
            if source.get("provider_id") == "character_stats_profiles":
                metadata["provider_id"] = "character_stats_profiles"
                metadata["url"] = "https://character-stats-and-profiles.fandom.com/wiki/Batman"
                metadata["revision_id"] = "charstats-1"
            return fields, metadata

        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "profiles"
            needs_review = root / "needs_review"
            generated = root / "generated"
            path = needs_review / "comic" / "dc" / "batman.yaml"
            write_profile(path, profile_data(missing_core=True))

            with patch("battlebot.review.auto_repair.fetch_source_fields", independent_fetch):
                result = await auto_repair.repair_profile(
                    path,
                    promote_if_valid=True,
                    needs_review_dir=needs_review,
                    generated_dir=generated,
                    notes_path=root / "review_notes.yaml",
                    provider_ids=["vsbattles", "character_stats_profiles"],
                    max_source_candidates=10,
                )
            generated_profile = service.load_yaml(generated / "comic" / "dc" / "batman.yaml")

        self.assertTrue(result.promoted)
        self.assertEqual(generated_profile["status"], "verified")
        self.assertGreaterEqual(generated_profile["generation"]["confidence"], 0.80)

    async def test_duplicate_same_revision_does_not_count_as_corroboration(self):
        async def duplicate_fetch(source):
            return await fake_fetch_source_fields(source)

        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "profiles"
            needs_review = root / "needs_review"
            generated = root / "generated"
            path = needs_review / "comic" / "dc" / "batman.yaml"
            write_profile(path, profile_data(missing_core=True))

            with patch("battlebot.review.auto_repair.fetch_source_fields", duplicate_fetch):
                result = await auto_repair.repair_profile(
                    path,
                    promote_if_valid=True,
                    needs_review_dir=needs_review,
                    generated_dir=generated,
                    notes_path=root / "review_notes.yaml",
                    provider_ids=["vsbattles"],
                    max_source_candidates=4,
                )
            generated_profile = service.load_yaml(generated / "comic" / "dc" / "batman.yaml")

        self.assertTrue(result.promoted)
        self.assertEqual(generated_profile["status"], "provisional")

    async def test_unrelated_character_page_is_rejected_for_primary(self):
        source = auto_repair.SourceAttempt(
            "wrong",
            "https://character-stats-and-profiles.fandom.com/wiki/Guts_(Canon)/ElJoaki5",
            True,
            "ok",
            ["attack_potency", "speed", "durability", "powers_and_abilities"],
            normalized_page_title="Guts (Canon)/ElJoaki5",
            fetch_status="fetched",
            provider_id="character_stats_profiles",
            authority="high",
            promotion_allowed=True,
        )
        auto_repair.annotate_attempt_quality(character_profile("Zodd", "Berserk", "anime"), source)

        self.assertFalse(source.identity_match)
        self.assertEqual(auto_repair.eligible_primary_attempts([source]), [])

    def test_identity_matching_ignores_local_franchise_suffixes_and_title_variants(self):
        cases = [
            ("rukia-kuchiki-bleach", "Rukia Kuchiki"),
            ("kaname-tosen-bleach", "Kaname Tōsen"),
            ("ichigo-kurosaki-bleach", "Ichigo Kurosaki (Post-Timeskip)"),
        ]
        for local_name, page_title in cases:
            with self.subTest(local_name=local_name, page_title=page_title):
                attempt = auto_repair.SourceAttempt(
                    "source",
                    f"https://vsbattles.fandom.com/wiki/{page_title.replace(' ', '_')}",
                    True,
                    "ok",
                    ["attack_potency", "speed", "durability", "powers_and_abilities"],
                    normalized_page_title=page_title,
                    fetch_status="fetched",
                    provider_id="vsbattles",
                    authority="high",
                    promotion_allowed=True,
                )

                auto_repair.annotate_attempt_quality(
                    character_profile(local_name, "Bleach", "anime"),
                    attempt,
                )

                self.assertTrue(attempt.identity_match)

    def test_identity_matching_keeps_wrong_character_rejection_strict(self):
        attempt = auto_repair.SourceAttempt(
            "wrong",
            "https://vsbattles.fandom.com/wiki/Guts",
            True,
            "ok",
            ["attack_potency", "speed", "durability", "powers_and_abilities"],
            normalized_page_title="Guts",
            fetch_status="fetched",
            provider_id="vsbattles",
            authority="high",
            promotion_allowed=True,
        )

        auto_repair.annotate_attempt_quality(character_profile("zodd", "Berserk", "anime"), attempt)

        self.assertFalse(attempt.identity_match)
        self.assertEqual(auto_repair.eligible_primary_attempts([attempt]), [])

    async def test_provider_exception_is_recorded_without_crashing(self):
        async def broken_fetch(source):
            raise AttributeError("'NoneType' object has no attribute 'get'")

        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "profiles" / "needs_review" / "comic" / "dc" / "batman.yaml"
            write_profile(path, profile_data(missing_core=True))

            with patch("battlebot.review.auto_repair.fetch_source_fields", broken_fetch):
                result = await auto_repair.repair_profile(
                    path,
                    notes_path=Path(temp_dir) / "notes.yaml",
                    provider_ids=["vsbattles"],
                    max_source_candidates=1,
                )

        self.assertFalse(result.promoted)
        self.assertEqual(result.source_attempts[0].exception_class, "AttributeError")
        self.assertFalse(result.source_attempts[0].retryable)

    async def test_chosen_source_bypasses_ambiguity_when_valid(self):
        async def variant_fetch(source):
            return await fake_fetch_source_fields(source)

        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "profiles"
            needs_review = root / "needs_review"
            generated = root / "generated"
            path = needs_review / "comic" / "dc" / "batman.yaml"
            write_profile(path, profile_data(missing_core=True))

            with patch("battlebot.review.auto_repair.fetch_source_fields", variant_fetch):
                result = await auto_repair.repair_profile(
                    path,
                    choose_source_id="source-1",
                    promote_if_valid=True,
                    needs_review_dir=needs_review,
                    generated_dir=generated,
                    debug_dir=Path(temp_dir) / "debug",
                    notes_path=root / "review_notes.yaml",
                    max_source_candidates=3,
                )
            generated_exists = (generated / "comic" / "dc" / "batman.yaml").exists()

        self.assertFalse(result.needs_human_source_choice)
        self.assertTrue(result.promoted)
        self.assertTrue(generated_exists)

    async def test_chosen_source_not_found_returns_clear_error(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "profiles" / "needs_review" / "comic" / "dc" / "batman.yaml"
            write_profile(path, profile_data(missing_core=True))

            result = await auto_repair.repair_profile(
                path,
                choose_source_id="missing-source",
                debug_dir=Path(temp_dir) / "debug",
                notes_path=Path(temp_dir) / "notes.yaml",
            )

        self.assertIn("choose_source_id_not_found: missing-source", result.errors)
        self.assertFalse(result.promoted)

    async def test_chosen_source_with_missing_fields_does_not_promote(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "profiles"
            needs_review = root / "needs_review"
            generated = root / "generated"
            path = needs_review / "comic" / "dc" / "batman.yaml"
            write_profile(path, profile_data(missing_core=True))

            with patch("battlebot.review.auto_repair.fetch_source_fields", fake_fetch_no_fields):
                result = await auto_repair.repair_profile(
                    path,
                    choose_source_id="source-1",
                    promote_if_valid=True,
                    needs_review_dir=needs_review,
                    generated_dir=generated,
                    debug_dir=Path(temp_dir) / "debug",
                    notes_path=root / "review_notes.yaml",
                )

        self.assertFalse(result.promoted)
        self.assertTrue(any(error.startswith("chosen_source_missing_required_fields") for error in result.errors))

    def test_list_candidates_reads_debug_report(self):
        with TemporaryDirectory() as temp_dir:
            debug_dir = Path(temp_dir) / "debug"
            debug_dir.mkdir()
            path = Path(temp_dir) / "profiles" / "needs_review" / "comic" / "dc" / "batman.yaml"
            write_profile(path, profile_data(missing_core=True))
            report = {
                "candidate_sources": [
                    {
                        "source_id": "vsbattles-batman-post-crisis",
                        "title": "Batman (Post-Crisis)",
                        "url": "https://vsbattles.fandom.com/wiki/Batman_(Post-Crisis)",
                        "rank": 50,
                        "extracted_fields": ["attack_potency", "speed", "durability"],
                    }
                ]
            }
            (debug_dir / "batman.json").write_text(json.dumps(report), encoding="utf-8")

            rows = auto_repair.candidate_rows_from_report(auto_repair.load_debug_report(path, debug_dir))

        self.assertEqual(rows[0]["source_id"], "vsbattles-batman-post-crisis")
        self.assertIn("speed", rows[0]["extracted_fields"])

    async def test_debug_report_appears_in_review_service_inspection(self):
        with TemporaryDirectory() as temp_dir:
            debug_dir = Path(temp_dir) / "data" / "repair_debug"
            path = Path(temp_dir) / "profiles" / "needs_review" / "comic" / "dc" / "batman.yaml"
            write_profile(path, profile_data(missing_core=True))

            with patch("battlebot.review.auto_repair.fetch_source_fields", fake_fetch_no_fields):
                await auto_repair.repair_profile(path, debug_dir=debug_dir, notes_path=Path(temp_dir) / "notes.yaml")
            with patch("battlebot.review.service.DEFAULT_REPAIR_DEBUG_DIR", debug_dir):
                inspection = service.inspect_profile(path)

        self.assertTrue(inspection["repair_debug"])
        self.assertEqual(inspection["repair_attempts"][0]["extraction_failure_reason"], "fetched_but_no_fields")

    async def test_needs_review_with_missing_fields_promoted_after_source_repair(self):
        """Test that a needs_review profile with missing core fields becomes battle_eligible and is promoted when sources provide repairs."""
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "profiles"
            needs_review = root / "needs_review"
            generated = root / "generated"
            path = needs_review / "comic" / "dc" / "batman.yaml"
            
            # Create a profile with missing core fields
            write_profile(path, profile_data(missing_core=True))

            # Verify initial state: profile is missing fields
            initial_profile = service.load_yaml(path)
            self.assertFalse(initial_profile.get("battle_eligible"))
            initial_missing = auto_repair.missing_targets(initial_profile)
            self.assertIn("attack_potency", initial_missing)
            self.assertIn("speed", initial_missing)
            self.assertIn("durability", initial_missing)
            self.assertIn("abilities", initial_missing)

            # Run repair with mocked source fetch that provides all fields
            with patch("battlebot.review.auto_repair.fetch_source_fields", fake_fetch_source_fields):
                result = await auto_repair.repair_profile(
                    path,
                    promote_if_valid=True,
                    needs_review_dir=needs_review,
                    generated_dir=generated,
                    notes_path=root / "review_notes.yaml",
                    provider_ids=["vsbattles"],
                    max_source_candidates=1,
                )

            # Verify repair was successful
            self.assertTrue(result.changed, "Profile should show as changed")
            self.assertGreater(len(result.repaired_fields), 0, "Should have repaired at least one field")
            
            # Load the repaired profile
            repaired_profile = service.load_yaml(path)
            
            # Verify fields were applied
            self.assertIsNotNone(auto_repair.service.power_text(repaired_profile, "attack_potency"))
            self.assertIsNotNone(auto_repair.service.power_text(repaired_profile, "speed"))
            self.assertIsNotNone(auto_repair.service.power_text(repaired_profile, "durability"))
            self.assertGreater(len(repaired_profile.get("abilities") or []), 0)
            
            # Verify eligibility was recomputed
            remaining_missing = auto_repair.missing_targets(repaired_profile)
            self.assertNotIn("attack_potency", remaining_missing, "attack_potency should be satisfied by repair")
            self.assertNotIn("speed", remaining_missing, "speed should be satisfied by repair")
            self.assertNotIn("durability", remaining_missing, "durability should be satisfied by repair")
            
            # Verify promotion occurred
            self.assertTrue(result.promoted, "Profile should be promoted after repair")
            
            # Verify generated profile was created
            generated_path = generated / "comic" / "dc" / "batman.yaml"
            self.assertTrue(generated_path.exists(), "Generated profile should be created")
            generated_profile = service.load_yaml(generated_path)
            self.assertTrue(generated_profile.get("battle_eligible"), "Generated profile should be battle_eligible")


if __name__ == "__main__":
    unittest.main()

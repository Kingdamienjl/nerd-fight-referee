import json
from pathlib import Path

import yaml

from battlebot.review import duplicate_audit


def write_profile(root: Path, relative: str, *, name: str, franchise: str = "Marvel", category: str = "comic", status: str = "verified") -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(
            {
                "id": duplicate_audit.normalized_text(name).replace(" ", "-"),
                "name": name,
                "franchise": franchise,
                "category": category,
                "status": status,
                "battle_eligible": status == "verified",
                "sources": [{"id": "source-1", "title": name}],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return path


def clusters_by_key(report):
    return {cluster["cluster_key"]: cluster for cluster in report["clusters"]}


def audit_tmp(generated: Path, needs: Path):
    records = [
        *duplicate_audit.scan_yaml_profiles(generated, "generated"),
        *duplicate_audit.scan_yaml_profiles(needs, "needs_review"),
    ]
    return duplicate_audit.audit_records(records)


def db_record(
    *,
    name: str,
    profile_path: str,
    profile_id: str,
    character_id: str,
    franchise: str = "Marvel",
    category: str = "comic",
    status: str = "verified",
):
    return duplicate_audit.ProfileRecord(
        source="db:character_profiles",
        sources=("db:character_profiles",),
        profile_path=profile_path,
        canonical_name=name,
        franchise=franchise,
        category=category,
        status=status,
        profile_id=profile_id,
        character_id=character_id,
        battle_eligible=status == "verified",
    )


def test_spider_man_earth_616_and_classic_cluster_together(tmp_path):
    generated = tmp_path / "profiles/generated"
    needs = tmp_path / "profiles/needs_review"
    write_profile(generated, "comic/marvel/spider-man-earth-616.yaml", name="Spider-Man Earth-616")
    write_profile(needs, "comic/marvel/spider-man-classic.yaml", name="Spider-Man classic", status="needs_review")

    report = audit_tmp(generated, needs)
    cluster = clusters_by_key(report)["spider man"]

    assert set(cluster["canonical_names"]) == {"Spider-Man Earth-616", "Spider-Man classic"}
    assert cluster["suggested_action"] in {"keep_all_variants", "review_variant_split"}


def test_scarlet_witch_modern_composite_and_earth_616_cluster_together(tmp_path):
    generated = tmp_path / "profiles/generated"
    needs = tmp_path / "profiles/needs_review"
    write_profile(generated, "comic/marvel/scarlet-witch-modern.yaml", name="Scarlet Witch modern")
    write_profile(generated, "comic/marvel/scarlet-witch-composite.yaml", name="Scarlet Witch composite")
    write_profile(needs, "comic/marvel/scarlet-witch-earth-616.yaml", name="Scarlet Witch Earth-616", status="needs_review")

    cluster = clusters_by_key(audit_tmp(generated, needs))["scarlet witch"]

    assert set(cluster["canonical_names"]) == {
        "Scarlet Witch modern",
        "Scarlet Witch composite",
        "Scarlet Witch Earth-616",
    }


def test_ambiguous_title_bearers_are_review_variant_split_not_auto_merge(tmp_path):
    generated = tmp_path / "profiles/generated"
    needs = tmp_path / "profiles/needs_review"
    write_profile(generated, "comic/marvel/captain-marvel-carol.yaml", name="Captain Marvel Carol Danvers", franchise="Marvel")
    write_profile(needs, "comic/dc/captain-marvel-billy.yaml", name="Captain Marvel Billy Batson", franchise="DC", status="needs_review")
    write_profile(generated, "comic/dc/green-lantern-hal.yaml", name="Green Lantern Hal Jordan", franchise="DC")
    write_profile(needs, "comic/dc/green-lantern-john.yaml", name="Green Lantern John Stewart", franchise="DC", status="needs_review")

    clusters = clusters_by_key(audit_tmp(generated, needs))

    assert clusters["captain marvel"]["suggested_action"] == "review_variant_split"
    assert clusters["green lantern"]["suggested_action"] == "review_variant_split"


def test_user_request_skeleton_profiles_are_excluded_by_default(tmp_path):
    generated = tmp_path / "profiles/generated"
    needs = tmp_path / "profiles/needs_review"
    write_profile(generated, "comic/marvel/spider-man.yaml", name="Spider-Man")
    user_request = write_profile(
        needs,
        "mixed/user-requests/spider-man.yaml",
        name="Spider-Man",
        franchise="User Requests",
        category="mixed",
        status="needs_review",
    )
    data = yaml.safe_load(user_request.read_text(encoding="utf-8"))
    data["approval_blockers"] = ["user_request_skeleton_schema_incomplete"]
    data["generation"] = {"ineligible_reasons": ["queued_user_request"]}
    user_request.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    report = audit_tmp(generated, needs)

    assert report["clusters"] == []


def test_audit_is_read_only_without_write_report(tmp_path):
    generated = tmp_path / "profiles/generated"
    needs = tmp_path / "profiles/needs_review"
    first = write_profile(generated, "comic/marvel/spider-man-earth-616.yaml", name="Spider-Man Earth-616")
    second = write_profile(needs, "comic/marvel/spider-man-classic.yaml", name="Spider-Man classic", status="needs_review")
    before = {
        first: first.read_text(encoding="utf-8"),
        second: second.read_text(encoding="utf-8"),
    }

    report = audit_tmp(generated, needs)

    assert report["clusters"]
    assert first.read_text(encoding="utf-8") == before[first]
    assert second.read_text(encoding="utf-8") == before[second]
    assert not (tmp_path / "data/reports/duplicate_character_audit.json").exists()


def test_write_report_writes_only_requested_report_path(tmp_path):
    report = {"summary": {"clusters": 0}, "clusters": []}
    target = tmp_path / "data/reports/duplicate_character_audit.json"

    duplicate_audit.write_report(report, path=target)

    assert json.loads(target.read_text(encoding="utf-8")) == report


def test_generated_and_db_same_profile_collapse_into_one_distinct_profile(tmp_path):
    generated = tmp_path / "profiles/generated"
    yaml_path = write_profile(generated, "game/kingdom-hearts/xion.yaml", name="Xion", franchise="Kingdom Hearts", category="game")
    records = [
        *duplicate_audit.scan_yaml_profiles(generated, "generated"),
        db_record(
            name="Xion",
            profile_path=yaml_path.as_posix(),
            profile_id="xion",
            character_id="xion",
            franchise="Kingdom Hearts",
            category="game",
        ),
    ]

    report = duplicate_audit.audit_records(records)

    assert report["summary"]["raw_records_scanned"] == 2
    assert report["summary"]["distinct_profiles_scanned"] == 1
    assert report["clusters"] == []


def test_profile_paths_are_unique_in_each_cluster(tmp_path):
    generated = tmp_path / "profiles/generated"
    yaml_path = write_profile(generated, "game/kingdom-hearts/xion.yaml", name="Xion", franchise="Kingdom Hearts", category="game")
    write_profile(generated, "game/kingdom-hearts/xion-game.yaml", name="Xion Game", franchise="Kingdom Hearts", category="game")
    records = [
        *duplicate_audit.scan_yaml_profiles(generated, "generated"),
        db_record(
            name="Xion",
            profile_path=yaml_path.as_posix(),
            profile_id="xion",
            character_id="xion",
            franchise="Kingdom Hearts",
            category="game",
        ),
    ]

    cluster = clusters_by_key(duplicate_audit.audit_records(records))["xion"]

    assert len(cluster["profile_paths"]) == len(set(cluster["profile_paths"]))


def test_identical_generated_db_duplicate_alone_does_not_produce_cluster(tmp_path):
    generated = tmp_path / "profiles/generated"
    yaml_path = write_profile(generated, "comic/marvel/spider-man.yaml", name="Spider-Man")
    records = [
        *duplicate_audit.scan_yaml_profiles(generated, "generated"),
        db_record(name="Spider-Man", profile_path=yaml_path.as_posix(), profile_id="spider-man", character_id="spider-man"),
    ]

    assert duplicate_audit.audit_records(records)["clusters"] == []


def test_xion_generated_game_and_needs_review_copy_is_likely_bad_duplicate(tmp_path):
    generated = tmp_path / "profiles/generated"
    needs = tmp_path / "profiles/needs_review"
    write_profile(generated, "game/kingdom-hearts/xion.yaml", name="Xion", franchise="Kingdom Hearts", category="game")
    write_profile(generated, "game/kingdom-hearts/xion-game.yaml", name="Xion Game", franchise="Kingdom Hearts", category="game")
    write_profile(
        needs,
        "game/kingdom-hearts/xion-game.yaml",
        name="Xion Game",
        franchise="Kingdom Hearts",
        category="game",
        status="needs_review",
    )

    cluster = clusters_by_key(audit_tmp(generated, needs))["xion"]

    assert cluster["suggested_action"] == "likely_bad_duplicate"


def test_yuna_variants_are_review_variant_split(tmp_path):
    generated = tmp_path / "profiles/generated"
    needs = tmp_path / "profiles/needs_review"
    write_profile(generated, "game/final-fantasy/yuna.yaml", name="Yuna", franchise="Final Fantasy", category="game")
    write_profile(generated, "game/final-fantasy/yuna-game.yaml", name="Yuna Game", franchise="Final Fantasy", category="game")
    write_profile(needs, "game/final-fantasy/yuna-classic.yaml", name="Yuna Classic", franchise="Final Fantasy", category="game")

    cluster = clusters_by_key(audit_tmp(generated, needs))["yuna"]

    assert cluster["suggested_action"] == "review_variant_split"


def test_zero_across_franchises_is_review_variant_split(tmp_path):
    generated = tmp_path / "profiles/generated"
    needs = tmp_path / "profiles/needs_review"
    write_profile(generated, "game/mega-man/zero.yaml", name="Zero", franchise="Mega Man", category="game")
    write_profile(needs, "game/drakengard/zero.yaml", name="Zero", franchise="Drakengard", category="game")

    cluster = clusters_by_key(audit_tmp(generated, needs))["zero"]

    assert cluster["suggested_action"] == "review_variant_split"


def test_summary_includes_raw_and_distinct_profile_counts(tmp_path):
    generated = tmp_path / "profiles/generated"
    yaml_path = write_profile(generated, "game/kingdom-hearts/xion.yaml", name="Xion", franchise="Kingdom Hearts", category="game")
    records = [
        *duplicate_audit.scan_yaml_profiles(generated, "generated"),
        db_record(
            name="Xion",
            profile_path=yaml_path.as_posix(),
            profile_id="xion",
            character_id="xion",
            franchise="Kingdom Hearts",
            category="game",
        ),
    ]

    summary = duplicate_audit.audit_records(records)["summary"]

    assert summary["raw_records_scanned"] == 2
    assert summary["distinct_profiles_scanned"] == 1
    assert {"likely_bad_duplicate", "review_variant_split", "merge_duplicate", "keep_all_variants"} <= set(summary)


def test_cli_accepts_source_filter():
    parser = duplicate_audit.build_arg_parser()

    args = parser.parse_args(["--source", "generated"])

    assert args.source == "generated"

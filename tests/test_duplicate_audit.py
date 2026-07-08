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


def test_needs_review_duplicate_of_generated_profile_becomes_safe_auto_archive(tmp_path):
    generated = tmp_path / "profiles/generated"
    needs = tmp_path / "profiles/needs_review"
    write_profile(generated, "game/kingdom-hearts/xion.yaml", name="Xion", franchise="Kingdom Hearts", category="game")
    write_profile(needs, "game/kingdom-hearts/xion-copy.yaml", name="Xion", franchise="Kingdom Hearts", category="game", status="needs_review")

    plan = duplicate_audit.build_apply_plan(audit_tmp(generated, needs))
    action = plan["actions"][0]

    assert action["cluster_key"] == "xion"
    assert action["safety_level"] == "safe_auto_archive"
    assert action["keep_profile"]["profile_path"].endswith("profiles/generated/game/kingdom-hearts/xion.yaml")
    assert [profile["profile_path"] for profile in action["archive_profiles"]] == [
        (needs / "game/kingdom-hearts/xion-copy.yaml").as_posix()
    ]


def test_verified_profile_is_chosen_over_auto_generated(tmp_path):
    generated = tmp_path / "profiles/generated"
    needs = tmp_path / "profiles/needs_review"
    verified = write_profile(generated, "comic/marvel/thor.yaml", name="Thor", status="verified")
    write_profile(needs, "comic/marvel/thor-copy.yaml", name="Thor", status="auto_generated")

    action = duplicate_audit.build_apply_plan(audit_tmp(generated, needs))["actions"][0]

    assert action["keep_profile"]["profile_path"] == verified.as_posix()


def test_review_variant_split_plan_is_manual_review_only(tmp_path):
    generated = tmp_path / "profiles/generated"
    needs = tmp_path / "profiles/needs_review"
    write_profile(generated, "game/final-fantasy/yuna.yaml", name="Yuna", franchise="Final Fantasy", category="game")
    write_profile(needs, "game/final-fantasy/yuna-classic.yaml", name="Yuna Classic", franchise="Final Fantasy", category="game")

    action = duplicate_audit.build_apply_plan(audit_tmp(generated, needs))["actions"][0]

    assert action["action"] == "manual_review"
    assert action["safety_level"] == "manual_review"
    assert action["archive_profiles"] == []


def test_cross_franchise_same_name_plan_is_manual_review(tmp_path):
    generated = tmp_path / "profiles/generated"
    needs = tmp_path / "profiles/needs_review"
    write_profile(generated, "game/mega-man/zero.yaml", name="Zero", franchise="Mega Man", category="game")
    write_profile(needs, "game/drakengard/zero.yaml", name="Zero", franchise="Drakengard", category="game")

    action = duplicate_audit.build_apply_plan(audit_tmp(generated, needs))["actions"][0]

    assert action["safety_level"] == "manual_review"
    assert action["archive_profiles"] == []


def test_write_plan_writes_expected_json_shape(tmp_path):
    generated = tmp_path / "profiles/generated"
    needs = tmp_path / "profiles/needs_review"
    write_profile(generated, "game/kingdom-hearts/xion.yaml", name="Xion", franchise="Kingdom Hearts", category="game")
    write_profile(needs, "game/kingdom-hearts/xion-copy.yaml", name="Xion", franchise="Kingdom Hearts", category="game", status="needs_review")
    plan = duplicate_audit.build_apply_plan(audit_tmp(generated, needs))
    target = tmp_path / "data/reports/duplicate_character_apply_plan.json"

    duplicate_audit.write_plan(plan, path=target)
    payload = json.loads(target.read_text(encoding="utf-8"))

    assert {"summary", "actions"} <= set(payload)
    assert payload["actions"][0]["keep_profile"]
    assert "archive_profiles" in payload["actions"][0]
    assert "safety_level" in payload["actions"][0]


def test_apply_plan_dry_run_does_not_modify_files(tmp_path, capsys):
    generated = tmp_path / "profiles/generated"
    needs = tmp_path / "profiles/needs_review"
    keep = write_profile(generated, "game/kingdom-hearts/xion.yaml", name="Xion", franchise="Kingdom Hearts", category="game")
    archive = write_profile(needs, "game/kingdom-hearts/xion-copy.yaml", name="Xion", franchise="Kingdom Hearts", category="game", status="needs_review")
    before = {keep: keep.read_text(encoding="utf-8"), archive: archive.read_text(encoding="utf-8")}
    report = audit_tmp(generated, needs)

    print(duplicate_audit.format_apply_plan_dry_run(duplicate_audit.build_apply_plan(report)))

    output = capsys.readouterr().out
    assert "would archive" in output
    assert keep.read_text(encoding="utf-8") == before[keep]
    assert archive.read_text(encoding="utf-8") == before[archive]

"""Audit pipeline tests (2026-11-20 audit build).

Pure-logic tests use fixtures; DB-touching functions take a fake
connection object with fetch/fetchrow. The re-judge caller is always
injected -- no test spends a real LLM call.
"""

import json

import yaml

from battlebot.audit.cache_audit import (
    audit_cache,
    build_rejudge_messages,
    check_cached_row,
    compare_verdicts,
    names_agree,
    rejudge_row,
    select_rejudge_sample,
    stale_check,
)
from battlebot.audit.profile_audit import (
    audit_one_profile,
    debris_scan,
    rank_fighters,
)
from battlebot.audit.runner import _cap, _fights, summarize, write_report

PROMPT_VERSION = "9a1f7a3048e1e0dfb9c2a0715c9a8c8e"


def _draft_rs(winner="Goku", difficulty="Low Diff"):
    return {
        "quick_verdict": "Goku wins the early exchanges.",
        "phase_1": "Goku lands the first clean hit. Vegeta answers with a fast strike.",
        "phase_2": "Goku keeps the pressure on. Vegeta cannot find an opening.",
        "phase_3": "Goku ends it with one clean shot. It is a spark against a campfire.",
        "difficulty": difficulty,
        "confidence": "high",
        "predicted_winner": winner,
    }


def _row(row_id=1, **over):
    base = {
        "id": row_id,
        "fighter_a": "mixed-crossover-icons-goku",
        "form_a": "base",
        "fighter_b": "anime-dragon-ball-vegeta",
        "form_b": "base",
        "prompt_version": PROMPT_VERSION,
        "profile_hash_a": "aaa",
        "profile_hash_b": "bbb",
        "verdict_winner": "Goku",
        "difficulty": "Low Diff",
        "confidence": "high",
        "draft_json": {"referee_structured_draft": _draft_rs()},
        "rewritten_json": _draft_rs(),
        "hit_count": 0,
    }
    base.update(over)
    return base


# --- checker re-run -------------------------------------------------


def test_checker_rerun_passes_good_row():
    result = check_cached_row(_row())
    assert result["fail"] == []


def test_checker_rerun_catches_banned_word():
    bad = _draft_rs()
    bad["phase_1"] = "Goku controls the tempo of the fight."
    result = check_cached_row(_row(rewritten_json=bad))
    assert "banned" in result["fail"]


def test_checker_rerun_catches_winner_change():
    bad = _draft_rs(winner="Vegeta")
    result = check_cached_row(_row(rewritten_json=bad))
    assert "winner_changed" in result["fail"]


def test_checker_rerun_catches_missing_keys():
    bad = {"quick_verdict": "Goku wins."}
    result = check_cached_row(_row(rewritten_json=bad))
    assert any(f.startswith("missing_keys:") for f in result["fail"])


# --- staleness -------------------------------------------------------


def test_stale_check_fresh_row():
    live = {
        "mixed-crossover-icons-goku": "aaa",
        "anime-dragon-ball-vegeta": "bbb",
    }
    assert stale_check(_row(), live) == []


def test_stale_check_flags_changed_hash():
    live = {
        "mixed-crossover-icons-goku": "aaa",
        "anime-dragon-ball-vegeta": "DIFFERENT",
    }
    findings = stale_check(_row(), live)
    assert any(f.startswith("stale_hash_b:") for f in findings)


def test_stale_check_flags_missing_fighter():
    findings = stale_check(_row(), {"mixed-crossover-icons-goku": "aaa"})
    assert any(f.startswith("fighter_b_not_in_db:") for f in findings)


def test_stale_check_flags_prompt_drift():
    live = {
        "mixed-crossover-icons-goku": "aaa",
        "anime-dragon-ball-vegeta": "bbb",
    }
    findings = stale_check(_row(prompt_version="old-version"), live)
    assert any(f.startswith("prompt_version_drift:") for f in findings)


# --- re-judge sampling + comparison ----------------------------------


def test_rejudge_sample_all_when_small():
    rows = [_row(i) for i in range(1, 20)]
    assert len(select_rejudge_sample(rows, 25)) == 19


def test_rejudge_sample_caps_by_hit_count_when_large():
    rows = [_row(i, hit_count=i) for i in range(1, 80)]
    sample = select_rejudge_sample(rows, 25)
    assert len(sample) == 25
    assert sample[0]["id"] == 79  # most-served first
    assert sample[-1]["id"] == 55


def test_names_agree_subset():
    assert names_agree("Goku", "Son Goku")
    assert names_agree("Son Goku", "Goku")
    assert not names_agree("Goku", "Vegeta")
    assert not names_agree("Goku", "")


def test_compare_verdicts_agreement():
    assert (
        compare_verdicts(
            "Goku",
            "Low Diff",
            {"winner": "Son Goku", "difficulty": "Low Diff"},
        )
        == []
    )


def test_compare_verdicts_winner_disagreement():
    findings = compare_verdicts(
        "Goku",
        "Low Diff",
        {"winner": "Vegeta", "difficulty": "Low Diff"},
    )
    assert any(f.startswith("winner_disagree:") for f in findings)


def test_compare_verdicts_difficulty_disagreement():
    findings = compare_verdicts(
        "Goku",
        "Low Diff",
        {"winner": "Goku", "difficulty": "Mid Diff"},
    )
    assert any(f.startswith("difficulty_disagree:") for f in findings)


async def _fake_caller_agree(messages, **kwargs):
    return json.dumps(
        {
            "winner": "Goku",
            "difficulty": "Low Diff",
            "confidence": "high",
        }
    )


async def _fake_caller_disagree(messages, **kwargs):
    return json.dumps(
        {
            "winner": "Vegeta",
            "difficulty": "Mid Diff",
            "confidence": "high",
        }
    )


async def test_rejudge_row_agreement():
    out = await rejudge_row(_row(), caller=_fake_caller_agree)
    assert out["error"] is None
    assert out["disagreements"] == []
    assert out["rejudged"]["winner"] == "Goku"


async def test_rejudge_row_disagreement_flagged():
    out = await rejudge_row(_row(), caller=_fake_caller_disagree)
    assert out["error"] is None
    assert len(out["disagreements"]) == 2


async def test_rejudge_row_unparseable_is_error_not_disagreement():
    async def _bad(messages, **kwargs):
        return "not json at all"

    out = await rejudge_row(_row(), caller=_bad)
    assert out["error"] is not None
    assert out["disagreements"] == []
    assert out["rejudged"] is None


def test_rejudge_prompt_uses_display_names_not_ids():
    """Regression: the first run fed fighter IDs to the model, which
    echoed an ID back as the winner -- 19/19 false disagreements.
    The prompt must carry canonical display names."""
    messages = build_rejudge_messages(_row(), "Goku", "Vegeta")
    user = messages[1]["content"]
    assert "Fighter A: Goku" in user
    assert "Fighter B: Vegeta" in user
    assert "mixed-crossover-icons-goku" not in user
    assert "anime-dragon-ball-vegeta" not in user


async def test_rejudge_row_agrees_on_display_name():
    seen: list[dict[str, str]] = []

    async def _capture(messages, **kwargs):
        seen.append(messages[1])
        return json.dumps({"winner": "Goku", "difficulty": "Low Diff", "confidence": "high"})

    out = await rejudge_row(_row(), caller=_capture, display_a="Goku", display_b="Vegeta")
    assert "Fighter A: Goku" in seen[0]["content"]
    assert out["error"] is None
    assert out["disagreements"] == []


def test_fights_pluralization_and_debris_cap():
    assert _fights(1) == "1 fight"
    assert _fights(8) == "8 fights"
    assert _cap(["a", "b"]) == "a; b"
    assert _cap([f"item{i}" for i in range(7)]) == (
        "item0; item1; item2; item3; item4; …and 2 more"
    )


# --- ranking ---------------------------------------------------------


def test_ranking_picks_true_top_fighters():
    rows = [
        {"contender_a": "piccolo", "contender_b": "kratos"},
        {"contender_a": "Piccolo", "contender_b": "ryu"},
        {"contender_a": "kratos", "contender_b": "ryu"},
        {"contender_a": "goku", "contender_b": "vegeta"},
        {"contender_a": "KRATOS", "contender_b": "goku"},
    ]
    ranked = rank_fighters(rows)
    assert ranked[0]["name"] == "kratos" and ranked[0]["fights"] == 3
    # goku / piccolo / ryu tie at 2 fights; ties break by name asc.
    assert ranked[1]["name"] == "goku" and ranked[1]["fights"] == 2
    assert ranked[2]["name"] == "piccolo" and ranked[2]["fights"] == 2
    assert ranked[3]["name"] == "ryu" and ranked[3]["fights"] == 2
    # "Piccolo" and "piccolo" collapse to one fighter.
    assert sum(1 for r in ranked if r["name"] == "piccolo") == 1


# --- debris scan -----------------------------------------------------


def test_debris_scan_clean_profile():
    profile = {
        "abilities": [
            {"name": "Flight", "description": "Can fly."},
            {"name": "Superhuman Physical Characteristics", "description": "Strong and fast."},
        ],
        "weaknesses": [{"name": "Overconfidence", "description": ""}],
    }
    assert debris_scan(profile) == []


def test_debris_scan_star_residue():
    profile = {
        "abilities": [
            {
                "name": "Stealth Mastery (Was taught to be a thief by Ace "
                "and Sabo) *Supernatural Willpower (As a child",
                "description": "Was taught to be a thief by Ace and Sabo",
            }
        ],
    }
    findings = debris_scan(profile)
    assert any(f.startswith("star_residue:") for f in findings)


def test_debris_scan_overlong_name():
    profile = {"abilities": [{"name": "x" * 121, "description": ""}]}
    findings = debris_scan(profile)
    assert any(f.startswith("overlong_name:") for f in findings)


def test_debris_scan_h1_footer():
    profile = {
        "weaknesses": [
            {
                "name": "etc. You can judge a person's power by their feats.",
                "description": "",
            }
        ]
    }
    findings = debris_scan(profile)
    assert "h1_footer_instruction:weaknesses" in findings


# --- audit_cache orchestration (fake conn) ---------------------------


class _FakeConn:
    def __init__(self, rows, live_hashes):
        self._rows = rows
        self._live = live_hashes

    async def fetch(self, sql, *args):
        if "cached_fight_results" in sql:
            return self._rows
        if "character_profiles" in sql:
            wanted = args[0] if args else []
            return [
                {"character_id": k, "profile_hash": v} for k, v in self._live.items() if k in wanted
            ]
        return []

    async def fetchrow(self, sql, *args):
        return None


async def test_audit_cache_flags_bad_and_stale_rows():
    rows = [
        _row(1),
        _row(2, rewritten_json={**_draft_rs(), "phase_1": "Goku controls the tempo."}),
        _row(3, profile_hash_b="CHANGED"),
    ]
    conn = _FakeConn(
        rows,
        {
            "mixed-crossover-icons-goku": "aaa",
            "anime-dragon-ball-vegeta": "bbb",
        },
    )
    out = await audit_cache(conn, rejudge=False)
    assert out["rows_checked"] == 3
    assert [r["row_id"] for r in out["checker_failed"]] == [2]
    assert [r["row_id"] for r in out["stale"]] == [3]
    assert out["rejudge_sampled"] == 0


# --- audit_one_profile (fake conn, real YAML file) -------------------


async def test_audit_one_profile_clean(tmp_path, monkeypatch):
    profile_json = {
        "name": "Goku",
        "franchise": "Dragon Ball",
        "abilities": [{"name": "Flight", "description": "Can fly.", "source_ids": ["s1"]}],
        "power_scale": {
            "attack_potency": {"text": "Strong", "source_ids": ["s1"]},
            "speed": {"text": "Fast", "source_ids": ["s1"]},
            "durability": {"text": "Tough", "source_ids": ["s1"]},
        },
        "sources": [{"id": "s1", "url": "https://example.com/goku"}],
    }
    (tmp_path / "goku.yaml").write_text(yaml.safe_dump(profile_json), encoding="utf-8")

    class _Conn(_FakeConn):
        async def fetchrow(self, sql, *args):
            return {"profile_path": "goku.yaml"}

    resolution = {
        "status": "resolved",
        "matched_by": "canonical_exact",
        "profile": {
            "character_id": "c1",
            "profile_id": "p1",
            "canonical_name": "Goku",
            "battle_eligible": True,
            "profile_hash": "aaa",
            "profile_json": profile_json,
        },
    }
    out = await audit_one_profile(
        _Conn([], {}),
        resolution,
        repo_root=tmp_path,
        fight_count=7,
        query="goku",
    )
    assert out["canonical_name"] == "Goku"
    assert out["battle_ready"] is True
    assert out["blockers"] == []
    assert out["debris"] == []
    assert out["yaml"] == []


# --- runner report ---------------------------------------------------


def _results():
    return {
        "date": "2026-11-20",
        "generated_at": "2026-11-20T06:00:00+00:00",
        "cache": {
            "rows_checked": 2,
            "checker_failed": [{"row_id": 2, "pair": "A vs B", "fail": ["banned"], "flags": []}],
            "stale": [],
            "rejudged": [{"row_id": 1, "pair": "A vs C"}],
            "disagreements": [],
            "rejudge_errors": [],
            "est_cost_usd": 0.0123,
        },
        "profiles": {
            "ranked_total": 40,
            "top_n": 20,
            "audited": [
                {
                    "canonical_name": "Goku",
                    "query": "goku",
                    "fights": 7,
                    "profile_path": "profiles/goku.yaml",
                },
                {
                    "canonical_name": "Piccolo",
                    "query": "piccolo",
                    "fights": 5,
                    "profile_path": "profiles/piccolo.yaml",
                    "blockers": ["ambiguous_source_identity"],
                    "missing_core_fields": [],
                    "debris": [],
                    "yaml": [],
                },
            ],
            "unresolved": [],
            "flagged": [
                {
                    "canonical_name": "Piccolo",
                    "query": "piccolo",
                    "fights": 5,
                    "profile_path": "profiles/piccolo.yaml",
                    "blockers": ["ambiguous_source_identity"],
                    "missing_core_fields": [],
                    "debris": [],
                    "yaml": [],
                },
            ],
            "clean": 1,
        },
        "counts": {
            "cache_rows_checked": 2,
            "cache_checker_failed": 1,
            "cache_stale": 0,
            "cache_rejudged": 1,
            "cache_disagreements": 0,
            "cache_rejudge_errors": 0,
            "profiles_ranked": 40,
            "profiles_audited": 2,
            "profiles_unresolved": 0,
            "profiles_flagged": 1,
            "profiles_clean": 1,
        },
    }


def test_report_roundtrip(tmp_path):
    results = _results()
    path = write_report(results, tmp_path)
    assert path.name == "2026-11-20.md"
    text = path.read_text(encoding="utf-8")
    assert "Cache checker failures" in text
    assert "row 2 (A vs B): banned" in text
    assert "Piccolo" in text and "ambiguous_source_identity" in text
    assert "Goku" in text  # clean list
    summary = summarize(results)
    assert "2 cached rows" in summary
    assert "1 checker failures" in summary
    assert "1 flagged" in summary
    assert "data/audit_reports/2026-11-20.md" in summary

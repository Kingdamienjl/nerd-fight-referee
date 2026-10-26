"""Part 1 design probe #2 (READ-ONLY): quarantine coverage, other
populations, character join, progress consumers, dry-run safety.
Runs inside referee-harvester-1 (/app). Writes only its own report
under /app/data/expand_20261025/.
"""
import asyncio
import inspect
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

import yaml

from battlebot.common.db import connect_database
from battlebot.review import auto_repair, service

OUT = Path("/app/data/expand_20261025")
report: dict = {}

QUAR9 = [
    "profiles/needs_review/mixed/steven-universe/steven-universe.yaml",
    "profiles/needs_review/mixed/invincible/omni-man.yaml",
    "profiles/needs_review/mixed/the-boys/soldier-boy.yaml",
    "profiles/needs_review/mixed/the-boys/black-noir.yaml",
    "profiles/needs_review/mixed/the-boys/starlight.yaml",
    "profiles/needs_review/mixed/the-boys/stormfront.yaml",
    "profiles/needs_review/mixed/steven-universe/amethyst.yaml",
    "profiles/needs_review/recentchanges/unknown/asmoday.yaml",
    "profiles/needs_review/recentchanges/unknown/ronova.yaml",
]

# verbatim quarantined item names per profile (from frag-11 quarantine
# scripts + frag-11 report). Section is weaknesses for all.
QUAR_ITEMS = {
    "profiles/needs_review/recentchanges/unknown/asmoday.yaml": [
        "Chapter VII", "Act III: Night White",
        "as the scenes depicting Ronova permanently killing living beings",
        "Rhinedottir freely creating life",
        "and Asmoday creating numerous worlds within her pocket space",
    ],
    "profiles/needs_review/recentchanges/unknown/ronova.yaml": [
        "Chapter VII", "Act III: Night White",
        "as the scenes depicting Ronova permanently killing living beings",
        "Rhinedottir freely creating life",
        "and Asmoday creating numerous worlds within her pocket space",
    ],
    "profiles/needs_review/mixed/the-boys/soldier-boy.yaml": [
        "The Boys", "Season 1", "Episode 2", "Season 4", "Episode 8",
        '"Season Four Finale" Additionally',
    ],
    "profiles/needs_review/mixed/invincible/omni-man.yaml": [
        "Episode 2 - I'll Give You The Grand Tour",
        "Episode 7 - Don't Do Anything Rash",
    ],
    "profiles/needs_review/mixed/the-boys/black-noir.yaml": [
        "Black Noir has the following",
    ],
    "profiles/needs_review/mixed/the-boys/starlight.yaml": [
        "Starlight has the following",
    ],
    "profiles/needs_review/mixed/the-boys/stormfront.yaml": [
        "Stormfront has the following",
    ],
    "profiles/needs_review/mixed/steven-universe/amethyst.yaml": [
        "Amethyst's upgraded whip.",
    ],
    # steven-universe: 24 ability-passage items; names reconstructed from
    # the frag-11 audit corpus below (capability descriptions).
    "profiles/needs_review/mixed/steven-universe/steven-universe.yaml": [],
}


async def main():
    # --- 1. the 9 quarantined: current blockers + cohort membership
    q = {}
    for rel in QUAR9:
        p = Path("/app") / rel
        if not p.exists():
            q[rel] = {"exists": False}
            continue
        prof = yaml.load(p.open(), Loader=yaml.CSafeLoader) or {}
        q[rel] = {
            "exists": True,
            "blockers": service.approval_blockers(prof),
            "battle_eligible": bool(prof.get("battle_eligible")),
            "status": prof.get("status"),
            "weakness_count": len(prof.get("weaknesses") or []),
        }
    report["quarantined_current"] = q

    # --- 2. G-screen coverage on verbatim items
    sig = str(inspect.signature(auto_repair.fragment_item_reasons))
    report["fragment_item_reasons_sig"] = sig
    # load audit corpus for steven-universe items (full name+description)
    # corpus.json is a DICT: profile rel path -> list of items with keys
    # section/name/desc/truncated_at_80 (18 profiles).
    corpus = {}
    cpath = Path("/app/data/frag12_20261025/corpus.json")
    if cpath.exists():
        corpus = json.loads(cpath.read_text())
    report["corpus_profiles"] = len(corpus)
    report["corpus_items"] = sum(len(v) for v in corpus.values()) if corpus else 0
    first_items = next(iter(corpus.values()), []) if corpus else []
    report["corpus_sample_keys"] = list(first_items[0].keys()) if first_items else []
    steven_items = []
    for prof_key, items in corpus.items():
        if "steven" in prof_key.lower():
            steven_items.extend(items)
    report["corpus_steven_items"] = len(steven_items)

    def check_item(name, description=""):
        item = {"name": name, "description": description}
        try:
            reasons = auto_repair.fragment_item_reasons(item, section="weaknesses")
        except TypeError:
            reasons = auto_repair.fragment_item_reasons(item)
        return [str(r) for r in (reasons or [])]

    cov = {}
    for rel, names in QUAR_ITEMS.items():
        cov[rel] = [{"name": n, "reasons": check_item(n)} for n in names]
    # steven-universe: check corpus items that look like ability passages
    su = []
    for prof_key, items in corpus.items():
        if "steven-universe.yaml" in prof_key:
            for it in items:
                nm = str(it.get("name") or "")
                su.append({"name": nm,
                           "description": str(it.get("desc") or "")[:200],
                           "reasons": check_item(nm, str(it.get("desc") or ""))})
    cov["profiles/needs_review/mixed/steven-universe/steven-universe.yaml"] = su
    report["g_coverage"] = cov
    # summarize: which verbatim items get NO reason (uncovered)
    uncovered = []
    for rel, items in cov.items():
        for it in items:
            if not it.get("reasons"):
                uncovered.append({"profile": rel, "name": it.get("name")})
    report["g_uncovered_items"] = uncovered

    # --- 3. other on-disk populations
    prof_root = Path("/app/profiles")
    pops = {}
    for d in ["approved", "rejected", "quarantined", "review_archive",
              "request_recovery_v2", "expansion_staging", "request_recovery",
              "generated"]:
        sub = prof_root / d
        if not sub.exists():
            pops[d] = {"exists": False}
            continue
        files = sorted(sub.rglob("*.yaml"))
        samples = []
        for f in files[:3]:
            try:
                prof = yaml.load(f.open(), Loader=yaml.CSafeLoader) or {}
                samples.append({"rel": str(f.relative_to("/app")),
                                "blockers": service.approval_blockers(prof)})
            except Exception as exc:  # noqa: BLE001
                samples.append({"rel": str(f.relative_to("/app")), "error": str(exc)})
        pops[d] = {"exists": True, "yaml_count": len(files), "samples": samples}
    report["other_populations"] = pops
    # rosters dir content
    rosters = prof_root / "rosters"
    if rosters.exists():
        report["rosters_files"] = sorted(p.name for p in rosters.iterdir())[:20]

    # --- 4. character join + universe ceiling
    async with connect_database() as conn:
        sample = await conn.fetch(
            "SELECT character_id, profile_id FROM character_profiles LIMIT 5")
        report["character_profiles_id_sample"] = [
            {"character_id": r["character_id"], "profile_id": r["profile_id"]}
            for r in sample]
        cols = await conn.fetch(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name='character_profiles'")
        report["character_profiles_columns"] = [
            (r["column_name"], r["data_type"]) for r in cols]
        # try join on character_id = characters.id::text and on canonical_name
        try:
            n1 = await conn.fetchval(
                "SELECT count(*) FROM characters c WHERE NOT EXISTS "
                "(SELECT 1 FROM character_profiles p "
                "WHERE p.character_id = c.id::text)")
            report["characters_no_db_profile_by_id_text"] = n1
        except Exception as exc:  # noqa: BLE001
            report["characters_no_db_profile_by_id_text_error"] = str(exc)
        # franchise distribution of characters
        fr = await conn.fetch(
            "SELECT franchise, count(*) AS n FROM characters "
            "GROUP BY franchise ORDER BY n DESC LIMIT 15")
        report["characters_by_franchise_top15"] = {r["franchise"]: r["n"] for r in fr}
        # needs_review jobs whose profile is in generated/approved (promoted out?)
        gj = await conn.fetchval(
            "SELECT count(*) FROM profile_jobs WHERE status='needs_review' "
            "AND profile_path LIKE 'profiles/generated/%'")
        report["jobs_pointing_at_generated"] = gj

    # --- 5. progress-file consumers in src
    import subprocess
    grep = subprocess.run(
        ["grep", "-rn", "recovery_progress", "/opt/referee/src",
         "--include=*.py"], capture_output=True, text=True)
    report["progress_consumers_src"] = grep.stdout.strip().splitlines()[:20]
    grep2 = subprocess.run(
        ["grep", "-rn", "recovery_progress", "/opt/referee/data/*.py",
         "/opt/referee/data/*.sh"], capture_output=True, text=True)
    report["progress_consumers_data"] = grep2.stdout.strip().splitlines()[:20]

    # --- 6. dry-run safety: re-processing previously-recovered profiles
    sig2 = str(inspect.signature(auto_repair.recover_profile_evidence))
    report["recover_sig"] = sig2
    dry = {}
    picks = [
        ("profiles/needs_review/anime/chainsaw-man/yoru.yaml", "recovered_before"),
        ("profiles/needs_review/anime/demon-slayer/giyu-tomioka.yaml", "recovered_before"),
        ("profiles/needs_review/anime/digimon/gabumon.yaml", "recovered_before"),
        ("profiles/needs_review/anime/chainsaw-man/fami.yaml", "identity_mismatch_before"),
        ("profiles/needs_review/anime/demon-slayer/doma.yaml", "identity_mismatch_before"),
    ]
    for rel, kind in picks:
        p = Path("/app") / rel
        if not p.exists():
            dry[rel] = {"exists": False}
            continue
        prof = yaml.load(p.open(), Loader=yaml.CSafeLoader) or {}
        cur_abilities = [str((a or {}).get("name") or "") for a in (prof.get("abilities") or [])]
        try:
            rep = await auto_repair.recover_profile_evidence(
                p, notes_path=service.DEFAULT_REVIEW_NOTES_PATH, dry_run=True)
            merges = rep.get("merges") or []
            merge_names = []
            for m in merges:
                if isinstance(m, dict):
                    merge_names.append(str(m.get("name") or m.get("item") or "")[:80])
                else:
                    merge_names.append(str(m)[:80])
            dups = [n for n in merge_names if n in cur_abilities]
            dry[rel] = {
                "kind": kind,
                "blockers_before": rep.get("blockers_before"),
                "recovered_fields": rep.get("recovered_fields"),
                "identity_mismatch": bool(rep.get("identity_mismatch")),
                "merges_count": len(merges),
                "merge_names_sample": merge_names[:10],
                "duplicate_names_vs_current": dups,
                "error": rep.get("error") or "",
            }
        except TypeError as exc:
            dry[rel] = {"kind": kind, "dry_run_type_error": str(exc)}
        except Exception as exc:  # noqa: BLE001
            dry[rel] = {"kind": kind, "error": f"{type(exc).__name__}: {exc}"}
    report["dry_run_safety"] = dry

    Path("/app/data/expand_20261025/design_part2.json").write_text(
        json.dumps(report, indent=1, default=str))
    print(json.dumps(report, indent=1, default=str))
    print("DESIGN-PART2 DONE")


if __name__ == "__main__":
    asyncio.run(main())

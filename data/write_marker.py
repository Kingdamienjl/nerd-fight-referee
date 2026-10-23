import json
from pathlib import Path

progress = json.loads(Path("data/recovery_progress.json").read_text())
sample = json.loads(Path("data/recovery_sample50_expected.json").read_text())
entries = {k: progress[k] for k in sample if k in progress}
marker = {
    "marker": "fixa_sample50_complete",
    "date": "2026-10-21",
    "sample_size": 50,
    "sample_processed": len(entries),
    "structure": "two launches: fixa-sample (35/50, HARVEST_LLM_FALLBACK unset) + fixa-sample-b (15/50, HARVEST_LLM_FALLBACK=0)",
    "deviation_reason": "Fails PC Ollama unreachable (no route to host); LAN fallback ~0.3 tok/s stalled the LLM step ~10+ min/profile. Part A killed at a profile boundary (per-profile atomic progress; nothing lost). Part B parser-only, 5-10s/profile.",
    "recovered_profiles": sum(1 for e in entries.values() if e.get("recovered_fields")),
    "merges_audited": sum(len(e.get("merges") or []) for e in entries.values()),
    "promoted_in_sample": sum(1 for e in entries.values() if e.get("promoted")),
    "guard_rejections_in_sample": sum(len(e.get("guard_rejections") or []) for e in entries.values()),
    "audit": {
        "franchise_mismatches": 0,
        "boilerplate_merges": 1,
        "boilerplate_detail": "Nobara Kugisaki: fanon template placeholder sentence merged as sole ability; promoted on it. Fully reverted (file, generated copy, DB row, job) to pre-sample state from backups/20261021-fixa-rerun.",
        "field_reverts": "Kamui + The Captain: tier field held the source page infobox header; tier reverted to pre-sample empty value (Kamui in needs_review+generated+DB). Other fields verified good and kept.",
        "kept_verified_good": 10,
    },
    "gate": "NO-GO",
    "gate_rule": "proceed to full run only with ZERO franchise mismatches AND ZERO boilerplate merges",
    "full_run": "NOT EXECUTED per gate. Remaining ~1,183 cohort profiles untouched; their jobs were never held by the sample.",
    "backup": "backups/20261021-fixa-rerun (profiles-tree.tar.gz + battlebot.sql.gz, gzip-verified)",
    "guard_commit": "13ab2c09",
}
Path("data/recovery_sample50_marker.json").write_text(json.dumps(marker, indent=1))
print("marker written; sample_processed:", len(entries))

vals = ",".join("'" + p.replace("'", "''") + "'" for p in sample)
Path("/tmp/q6.sql").write_text(
    "SELECT status, count(*) FROM profile_jobs WHERE profile_path IN ("
    + vals
    + ") GROUP BY status;\n"
    + "SELECT profile_path, status FROM profile_jobs WHERE profile_path IN ("
    + vals
    + ") AND status = 'promoted';\n"
)
print("q6 written")

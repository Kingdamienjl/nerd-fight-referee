"""Adapt the expand-gate scripts for frag-13 (run on the box).
Copies prep/capture/audit/manual-review/backup from expand_20261025
to frag13_20261027, retargets paths, and adds the quarantined_expand
reset rule to the prep (the H-screens now exist, which is the exact
condition the expand report set for re-queueing those 3 profiles).
"""
import sys
from pathlib import Path

SRC = Path("/opt/referee/data/expand_20261025")
OUT = Path("/opt/referee/data/frag13_20261027")
OUT.mkdir(parents=True, exist_ok=True)

# --- prep ---
prep = (SRC / "prep_expand.py").read_text()
prep = prep.replace(
    '"""Expand gate prep (Part 2, step 1): snapshot + reset + manifest.',
    '"""Frag-13 gate prep: snapshot + reset + manifest.\n'
    '- Same as the expand prep, plus: entries flagged quarantined_expand\n'
    '  are RESET (the H-screens now exist, which is the exact condition\n'
    '  the expand report set for re-queueing those 3 profiles).',
)
prep = prep.replace(
    'OUT = Path("/app/data/expand_20261025")',
    'OUT = Path("/app/data/frag13_20261027")',
)
old_branch = '''        if entry.get("quarantined_frag11"):
            classes["quarantined_flagged"] += 1
            reset_keys.append(rel)'''
new_branch = '''        if entry.get("quarantined_frag11"):
            classes["quarantined_flagged"] += 1
            reset_keys.append(rel)
        elif entry.get("quarantined_expand"):
            classes["quarantined_expand"] += 1
            reset_keys.append(rel)'''
assert prep.count(old_branch) == 1, "prep quarantine branch anchor"
prep = prep.replace(old_branch, new_branch, 1)
prep = prep.replace("expand_expected.json", "frag13_expected.json")
prep = prep.replace("expand_manifest.json", "frag13_manifest.json")
# targeted-8 list in the manifest
old_manifest = '''        "first50": todo[:50],'''
new_manifest = '''        "first50": todo[:50],
        "targeted8": [p for p in TARGETED8 if p in todo],
        "targeted8_in_cohort": [p for p in TARGETED8 if p in cohort],'''
assert prep.count(old_manifest) == 1, "prep manifest anchor"
prep = prep.replace(old_manifest, new_manifest, 1)
targeted = '''
TARGETED8 = [
    "profiles/needs_review/comic/dc/animal-man-rebirth.yaml",
    "profiles/needs_review/comic/dc/harley-quinn-post-flashpoint.yaml",
    "profiles/needs_review/comic/dc/superman-prime-earth.yaml",
    "profiles/needs_review/anime/dragon-ball/son-goku-ultra-instinct-sign.yaml",
    "profiles/needs_review/mixed/invincible/omni-man.yaml",
    "profiles/needs_review/mixed/user-requests/omni-man.yaml",
    "profiles/needs_review/recentchanges/unknown/asmoday.yaml",
    "profiles/needs_review/recentchanges/unknown/ronova.yaml",
]
'''
anchor = 'OUT = Path("/app/data/frag13_20261027")'
prep = prep.replace(anchor, anchor + targeted, 1)
(OUT / "frag13_prep.py").write_text(prep)

# --- capture (generic; only docstring mentions expand) ---
cap = (SRC / "capture_expand.py").read_text()
cap = cap.replace("Expand capture:", "Frag-13 capture:")
(OUT / "frag13_capture.py").write_text(cap)

# --- audit (argv-driven; only docstring mentions expand) ---
aud = (SRC / "audit_expand.py").read_text()
aud = aud.replace("Expand gate-50q strict audit", "Frag-13 gate-50q strict audit")
aud = aud.replace("prep snapshot (expand_expected.json)", "prep snapshot (frag13_expected.json)")
aud = aud.replace("(expand_actual.json)", "(frag13_actual.json)")
(OUT / "frag13_audit.py").write_text(aud)

# --- manual review (parameterize the three paths + first50 key) ---
man = (SRC / "manual_review.py").read_text()
man = man.replace(
    '"""Expand manual-review dump: for each of the 9 mass-run recovered\nprofiles, print EVERY new item (abilities/weaknesses/equipment) and every\nnew/changed stat with FULL text (no truncation), plus source titles.\nDiffs expected (expand_expected.json) vs actual (expand_actual_mass.json),\nkeyed the same way as the audit (item id or normalized name).\nRead-only.\n"""',
    '"""Frag-13 manual-review dump: for each recovered profile in the\ngiven manifest sample, print EVERY new item\n(abilities/weaknesses/equipment) and every new/changed stat with FULL\ntext (no truncation), plus source titles. Diffs expected vs actual,\nkeyed the same way as the audit (item id or normalized name).\nUsage: frag13_manual_review.py <expected_json> <actual_json> <manifest_json>\nRead-only.\n"""',
)
man = man.replace(
    'expected = json.loads(Path("/app/data/expand_20261025/expand_expected.json").read_text())',
    'expected = json.loads(Path(sys.argv[1]).read_text())',
)
man = man.replace(
    'actual = json.loads(Path("/app/data/expand_20261025/expand_actual_mass.json").read_text())',
    'actual = json.loads(Path(sys.argv[2]).read_text())',
)
man = man.replace(
    'mass = json.loads(Path("/app/data/expand_20261025/expand_manifest_mass.json").read_text())',
    'mass = json.loads(Path(sys.argv[3]).read_text())',
)
man = man.replace('for rel in mass["sample"]:', 'for rel in (mass.get("first50") or mass.get("sample") or mass.get("targeted8") or []):')
assert "expand_20261025" not in man, "manual review still references expand dir"
(OUT / "frag13_manual_review.py").write_text(man)

# --- backup script ---
bak = (SRC / "backup_expand.sh").read_text()
bak = bak.replace("LABEL=${1:-expand-gate50q}", "LABEL=${1:-frag13-gate50q}")
bak = bak.replace("20261025-$LABEL", "20261027-$LABEL")
bak = bak.replace("Expand gate-50q backup", "Frag-13 gate-50q backup")
(OUT / "frag13_backup.sh").write_text(bak)

print("ADAPT DONE")
for f in sorted(OUT.iterdir()):
    print(" ", f.name, f.stat().st_size)

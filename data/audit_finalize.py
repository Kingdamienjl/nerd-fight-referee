import json, sys
from pathlib import Path
sys.path.insert(0, "/app/src"); sys.path.insert(0, "/app")
from battlebot.review import service

NOTES = {
 "profiles/needs_review/anime/jujutsu-kaisen/nobara-kugisaki.yaml": (
  "Audit revert 2026-10-21 (Fix A sample gate): the guarded recovery merged a fanon "
  "template placeholder (A list of the character general abilities - Please add links...) "
  "as the only ability and promoted on it. Boilerplate merge; profile file, generated "
  "copy, DB row and job were restored to the exact pre-sample state from "
  "backups/20261021-fixa-rerun. Sample gate FAILED on this merge; full cohort run not executed."),
 "profiles/needs_review/anime/gintama/kamui.yaml": (
  "Audit fix 2026-10-21 (Fix A sample gate): recovery merged the source page infobox "
  "header as the tier text. Tier reverted to its pre-sample (empty) value in needs_review, "
  "generated and DB. All other recovered fields verified correct-franchise and kept; "
  "promotion stands."),
 "profiles/needs_review/anime/hellsing/the-captain.yaml": (
  "Audit fix 2026-10-21 (Fix A sample gate): recovery merged the source page infobox "
  "header as the tier text. Tier reverted to its pre-sample (empty) value; other recovered "
  "fields verified correct-franchise and kept."),
}
for rel, text in NOTES.items():
    service.add_review_note(rel, field_path="evidence_recovery", issue_type="audit_revert", note=text, source_id="fixa_sample_audit")
    print("note added:", rel)

progress_path = Path("data/recovery_progress.json")
progress = json.loads(progress_path.read_text())
AUDIT = {
 "profiles/needs_review/anime/jujutsu-kaisen/nobara-kugisaki.yaml": "REVERTED: boilerplate ability merge (fanon template placeholder); full pre-sample state restored",
 "profiles/needs_review/anime/gintama/kamui.yaml": "tier field reverted (infobox header residue); other fields verified good; promotion kept",
 "profiles/needs_review/anime/hellsing/the-captain.yaml": "tier field reverted (infobox header residue); other fields verified good",
}
for rel, verdict in AUDIT.items():
    if rel in progress:
        progress[rel]["audit_20261021"] = verdict
progress_path.write_text(json.dumps(progress, indent=1))
print("progress annotated; total entries:", len(progress))

"""Frag-10 gate FAIL revert: remove the bad merges item/field-level from the
gate backup (20261025-frag10-gate), keep audited-good merges, drop progress
keys for the 3 reverted profiles. Writes a JSON report of what changed.
Gate verdict: FAIL (manual review found battery-clean debris in 3 of 6
recovered profiles; cohort does NOT run).
Frag-9 lesson applied: profile_hash is NOT recomputed — left for the drain.
Bad merges (verbatim):
- isaac (7 ability items): tab-key headers 'Battle ID Types', 'Bird ID Types',
  'Mage ID Types'; mid-word truncated 'Absorption (With Healing Drop and
  Deadly Absorp)'; section headers 'Dark Lord abilities (4-D - Baseline)',
  'Creatures of Chaos (4-D - Baseline)'; header-bleed 'Forcefield Creation
  (Via Protective Field...)' whose description ends with the next section
  header 'Dark Lord resistances (4-D - Baseline)'.
- oryx (2 stats): speed 'Lifting Strength: Striking Strength:' and range
  'Standard Equipment: Intelligence: Above Average' — values composed only
  of following-field labels (infobox label bleed).
- maliketh (5 items): bare character name 'Radagon' (insubstantive);
  split-sentence halves 'but after the Night of the black knives' and
  'he was limited.'; glued composite 'Durability Negation ... Death
  Manipulation ...'; weakness 'Frost Damage and the Blasphemous Claw ...'
  whose description is feats content, not weakness content.
Kept (audited-good): rodimus-prime tier, soundwave tier, shanoa all,
isaac's other 34 abilities + 6 stats, oryx's ability/weakness/attack_potency/
intelligence/tier, maliketh's other 8 abilities + 6 stats.
The 4 audit unbalanced_parenthesis flags are the known 120-char name-
truncation false-positive class (descriptions complete and balanced)."""
import copy
import hashlib
import json
import os
import tarfile

import yaml

BK = "/app/backups/20261025-frag10-gate/profiles.tar.gz"
PROG = "/app/data/recovery_progress.json"
REPORT = "/app/data/frag10_20261025/revert_report.json"

# name -> prefix to match (live names are capped at 120 chars)
REVERTS = {
    "profiles/needs_review/game/castlevania/isaac.yaml": {
        "abilities": [
            "Battle ID Types",
            "Bird ID Types",
            "Mage ID Types",
            "Absorption (With Healing Drop and Deadly Absorp)",
            "Dark Lord abilities (4-D - Baseline)",
            "Creatures of Chaos (4-D - Baseline)",
            "Forcefield Creation (Via Protective FieldCastlevania",
        ],
    },
    "profiles/needs_review/game/destiny/oryx.yaml": {
        "power_scale": ["speed", "range"],
    },
    "profiles/needs_review/game/elden-ring/maliketh.yaml": {
        "abilities": [
            "Radagon",
            "but after the Night of the black knives",
            "he was limited.",
            "Durability Negation Destined Death lowers and burns HP. Death Manipulation Maliketh could manipulate Death",
        ],
        "weaknesses": [
            "Frost Damage and the Blasphemous Claw",
        ],
    },
}


def md5(path):
    return hashlib.md5(open(path, "rb").read()).hexdigest()


tf = tarfile.open(BK, "r:gz")
names = tf.getnames()


def find_member(path):
    for n in names:
        if n.endswith(path):
            return n
    return None


report = {"reverted": {}, "aborted": {}, "progress_removed": {}}
os.chdir("/app")

for path, spec in REVERTS.items():
    m = find_member(path)
    pre = yaml.safe_load(tf.extractfile(m))
    live = yaml.safe_load(open(path))
    # full top-level diff guard: only merge fields + promotion effects +
    # profile_hash/repair may differ (promotion changed battle_eligible/
    # status/generation on isaac; profile_hash is left untouched).
    allowed = {"abilities", "weaknesses", "power_scale", "profile_hash",
               "repair", "battle_eligible", "status", "generation",
               "profile_type", "review"}
    diffkeys = [k for k in set(list(pre.keys()) + list(live.keys()))
                if pre.get(k) != live.get(k) and k not in allowed]
    if diffkeys:
        report["aborted"][path] = {"unexpected_diff_keys": diffkeys}
        print("ABORT %s unexpected diff keys: %s" % (path, diffkeys))
        continue
    before_md5 = md5(path)
    removed = {}
    ok = True
    for section in ("abilities", "weaknesses"):
        prefixes = spec.get(section, [])
        if not prefixes:
            continue
        live_items = live.get(section) or []
        removed[section] = []
        for prefix in prefixes:
            hits = [it for it in live_items
                    if str(it.get("name", "")).startswith(prefix)]
            if len(hits) != 1:
                report["aborted"][path] = {"section": section,
                                           "match": prefix,
                                           "hits": len(hits)}
                print("ABORT %s %s match %r hits=%d"
                      % (path, section, prefix, len(hits)))
                ok = False
                break
            live_items.remove(hits[0])
            removed[section].append(str(hits[0].get("name")))
        if not ok:
            break
        live[section] = live_items
    if not ok:
        continue
    restored = {}
    pre_ps = pre.get("power_scale") or {}
    live_ps = live.get("power_scale") or {}
    for field in spec.get("power_scale", []):
        if field in pre_ps:
            live_ps[field] = copy.deepcopy(pre_ps[field])
        else:
            live_ps.pop(field, None)
        restored[field] = pre_ps.get(field)
    live["power_scale"] = live_ps
    # NOTE: profile_hash deliberately NOT recomputed (frag-9 lesson).
    with open(path, "w") as f:
        yaml.safe_dump(live, f, sort_keys=False, allow_unicode=False)
    report["reverted"][path] = {
        "md5_before": before_md5,
        "md5_after": md5(path),
        "removed": removed,
        "restored_power_scale": restored,
        "profile_hash_touched": False,
    }
    print("REVERTED %s removed=%s restored=%s"
          % (path.split("/")[-1], removed, list(restored.keys())))

progress = json.loads(open(PROG).read())
for path in REVERTS:
    if path not in report["reverted"]:
        print("PROGRESS-KEPT %s (revert did not complete)" % path.split("/")[-1])
        continue
    if path in progress:
        report["progress_removed"][path] = progress.pop(path)
        print("PROGRESS-REMOVED %s" % path.split("/")[-1])
    else:
        # Keys were already removed by the aborted first run; record that.
        report["progress_removed"][path] = "already_removed_by_aborted_run"
        print("PROGRESS-ALREADY-REMOVED %s" % path.split("/")[-1])
tmp = PROG + ".tmp"
open(tmp, "w").write(json.dumps(progress, indent=1, sort_keys=True))
os.replace(tmp, PROG)

json.dump(report, open(REPORT, "w"), indent=1, default=str)
print("REPORT: %s" % REPORT)
print("reverted=%d aborted=%d progress_removed=%d"
      % (len(report["reverted"]), len(report["aborted"]),
         len(report["progress_removed"])))

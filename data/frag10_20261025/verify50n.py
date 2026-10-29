"""Frag-10 gate FAIL revert verification (one-off container):
for each of the 3 reverted profiles: bad items/fields absent, good merges
intact, oryx speed/range restored to pre-gate state, profile_hash UNTOUCHED
by the revert (equals the post-gate actual snapshot value — frag-9 lesson:
never recompute it), files validate. For the 3 clean recovered profiles:
merged content still present. Writes verify50n.json."""
import json
import sys
import tarfile
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

import yaml
from battlebot.ingest.import_profiles import validate_profile_path

OUT = Path("/app/data/frag10_20261025/verify50n.json")
ACTUAL = json.loads(Path("/app/data/recovery_sample50n_actual.json").read_text())
GATE_TAR = "/app/backups/20261025-frag10-gate/profiles.tar.gz"

BAD = {
    "profiles/needs_review/game/castlevania/isaac.yaml": {
        "abilities": ["Battle ID Types", "Bird ID Types", "Mage ID Types",
                      "Deadly Absorp", "Dark Lord abilities (4-D - Baseline)",
                      "Creatures of Chaos (4-D - Baseline)",
                      "Forcefield Creation (Via Protective FieldCastlevania"]},
    "profiles/needs_review/game/destiny/oryx.yaml": {},
    "profiles/needs_review/game/elden-ring/maliketh.yaml": {
        "abilities": ["Radagon", "but after the Night of the black knives",
                      "he was limited.",
                      "Durability Negation Destined Death lowers and burns HP. Death Manipulation"],
        "weaknesses": ["Frost Damage and the Blasphemous Claw"]},
}

# (profile, section, expected count after revert, a must-still-be-present item)
GOOD = [
    ("profiles/needs_review/game/castlevania/isaac.yaml", "abilities", 34,
     "Extrasensory Perception (Can sense Demonic Energy"),
    ("profiles/needs_review/game/castlevania/isaac.yaml", "abilities", 34,
     "Resurrection & Regeneration Negation"),
    ("profiles/needs_review/game/destiny/oryx.yaml", "abilities", 1,
     "Abstract Existence (Aurash is noted"),
    ("profiles/needs_review/game/destiny/oryx.yaml", "weaknesses", 1,
     "Her curiosity draws her away from her work."),
    ("profiles/needs_review/game/elden-ring/maliketh.yaml", "abilities", 9,
     "Conceptual Manipulation (Type 1;"),
    ("profiles/needs_review/game/elden-ring/maliketh.yaml", "abilities", 9,
     "Soul Manipulation Even a small fragment"),
    ("profiles/needs_review/game/elden-ring/maliketh.yaml", "weaknesses", 0, None),
]

# clean recovered profiles: (profile, field, expected text fragment)
CLEAN = [
    ("profiles/needs_review/comics/transformers/rodimus-prime.yaml",
     "tier", "At least High 5-A, far higher with the Matrix of Leadership"),
    ("profiles/needs_review/comics/transformers/soundwave.yaml",
     "tier", "At least 7-A"),
    ("profiles/needs_review/game/castlevania/shanoa.yaml",
     "tier", "2-C, higher with Dominus"),
]

fails = []
report = {"checks": []}


def check(name, ok, detail=""):
    report["checks"].append({"name": name, "ok": ok, "detail": detail})
    if not ok:
        fails.append(name + ": " + detail)
    print(("OK  " if ok else "BAD ") + name + (" " + detail if detail else ""))


def load(rel):
    return yaml.safe_load(open("/app/" + rel))


# 1. bad items absent
for rel, sections in BAD.items():
    d = load(rel)
    for section, frags in sections.items():
        names = [str(i.get("name")) for i in (d.get(section) or [])]
        for frag in frags:
            check(f"bad absent {rel.split('/')[-1]} [{section}] {frag[:40]}",
                  not any(frag in n for n in names))

# 2. good merges intact (counts + spot items)
for rel, section, count, frag in GOOD:
    d = load(rel)
    items = d.get(section) or []
    names = [str(i.get("name")) for i in items]
    check(f"good count {rel.split('/')[-1]} [{section}] == {count}",
          len(items) == count, f"got {len(items)}")
    if frag:
        check(f"good present {rel.split('/')[-1]} {frag[:40]}",
              any(frag in n for n in names))

# 3. oryx speed/range restored to pre-gate state
tf = tarfile.open(GATE_TAR, "r:gz")
names = tf.getnames()
m = [n for n in names if n.endswith("profiles/needs_review/game/destiny/oryx.yaml")][0]
pre = yaml.safe_load(tf.extractfile(m))
live = load("profiles/needs_review/game/destiny/oryx.yaml")
for field in ("speed", "range"):
    pre_v = (pre.get("power_scale") or {}).get(field)
    live_v = (live.get("power_scale") or {}).get(field)
    check(f"oryx {field} restored to pre-gate",
          pre_v == live_v, f"pre={str(pre_v)[:80]!r} live={str(live_v)[:80]!r}")

# 4. profile_hash untouched by the revert (== post-gate actual snapshot)
for rel in BAD:
    live = load(rel)
    snap_hash = ACTUAL[rel].get("profile_hash")
    check(f"profile_hash untouched {rel.split('/')[-1]}",
          live.get("profile_hash") == snap_hash)

# 5. clean profiles' merges intact
for rel, field, frag in CLEAN:
    d = load(rel)
    text = str(((d.get("power_scale") or {}).get(field) or {}).get("text") or "")
    check(f"clean kept {rel.split('/')[-1]} [{field}]",
          frag in text, text[:60])

# 6. shanoa fully intact (2 weaknesses + 6 stats)
d = load("profiles/needs_review/game/castlevania/shanoa.yaml")
check("shanoa weaknesses == 2", len(d.get("weaknesses") or []) == 2)
filled = [k for k, v in (d.get("power_scale") or {}).items()
          if isinstance(v, dict) and v.get("text")]
check("shanoa stats filled == 6", len(filled) == 6, str(filled))

# 7. all 6 recovered profiles validate
for rel in list(BAD) + [c[0] for c in CLEAN]:
    try:
        validate_profile_path(Path("/app/" + rel))
        check(f"validates {rel.split('/')[-1]}", True)
    except Exception as exc:  # noqa: BLE001
        check(f"validates {rel.split('/')[-1]}", False, str(exc)[:200])

report["fails"] = fails
OUT.write_text(json.dumps(report, indent=1))
print("FAILS: %s" % (fails if fails else "none"))

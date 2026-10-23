import sys, json, glob
sys.path.insert(0, "/app/src")
import yaml
from battlebot.review.service import approval_blockers

paths = sorted(glob.glob("/app/profiles/needs_review/**/*.yaml", recursive=True))
vs_only, vs_any, other = [], [], []
examples = {}
for p in paths:
    try:
        prof = yaml.load(open(p), Loader=yaml.CSafeLoader) or {}
    except Exception:
        continue
    b = approval_blockers(prof)
    vs = [x for x in b if x.startswith("unresolved_version_scope")]
    if vs and len(vs) == len(b):
        vs_only.append(p)
        if len(examples) < 3: examples[p] = prof
    elif vs:
        vs_any.append(p)
print("total needs_review:", len(paths))
print("ONLY version_scope blockers:", len(vs_only))
print("version_scope + others:", len(vs_any))
json.dump({"vs_only": vs_only, "vs_any": vs_any}, open("/app/data/cohort_b.json", "w"))
for p, prof in examples.items():
    print("=" * 30, p)
    print("name:", prof.get("name"), "| franchise:", prof.get("franchise"))
    print("version_scope:", json.dumps(prof.get("version_scope"))[:300])
    print("forms:", json.dumps(prof.get("forms"))[:600])
    ps = prof.get("power_scale") or {}
    for axis in ("tier", "attack_potency", "speed", "durability"):
        e = ps.get(axis)
        print(axis, "->", json.dumps(e)[:260])
    print("sources:", [s.get("id") for s in prof.get("sources") or [] if isinstance(s, dict)])

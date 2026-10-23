import sys, json, glob, collections
sys.path.insert(0, "/app/src")
import yaml
from battlebot.review.service import approval_blockers

def keyforms(prof):
    return [f for f in prof.get("forms") or [] if isinstance(f, dict) and f.get("source_field") == "keys"]

stats = collections.Counter()
variant_vals = collections.Counter()
mismatch_examples = []
single_key_pipes = []
for p in sorted(glob.glob("/app/profiles/needs_review/**/*.yaml", recursive=True)):
    try: prof = yaml.load(open(p), Loader=yaml.CSafeLoader) or {}
    except Exception: continue
    b = approval_blockers(prof)
    if not any(x.startswith("unresolved_version_scope") for x in b): continue
    forms = keyforms(prof)
    variant_vals[json.dumps(prof.get("variant"))[:60]] += 1
    ps = prof.get("power_scale") or {}
    piped = {}
    for axis in ("attack_potency", "speed", "durability", "tier"):
        e = ps.get(axis)
        t = e.get("text") if isinstance(e, dict) else e
        if t and "|" in str(t): piped[axis] = len(str(t).split("|"))
    if not piped:
        stats["no_piped_axis_but_multi_keys_blocker"] += 1
        continue
    if len(forms) == 1:
        stats["single_form_piped"] += 1
        if len(single_key_pipes) < 3: single_key_pipes.append((p, len(forms), piped, [f.get("name") for f in forms]))
    elif all(c == len(forms) for c in piped.values()):
        stats["segments_eq_forms_all_piped_axes"] += 1
    else:
        stats["segments_ne_forms"] += 1
        if len(mismatch_examples) < 4: mismatch_examples.append((p, len(forms), piped, [f.get("name") for f in forms][:6]))
print(stats)
print("\nvariant values (top 10):")
for v, c in variant_vals.most_common(10): print(" ", c, v)
print("\nsingle-form piped examples:")
for e in single_key_pipes: print(" ", e)
print("\nmismatch examples:")
for e in mismatch_examples: print(" ", e)

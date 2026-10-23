import sys, json, glob
sys.path.insert(0, "/app/src")
import yaml

prof = yaml.load(open("/app/profiles/needs_review/anime/demon-slayer/genya-shinazugawa.yaml"), Loader=yaml.CSafeLoader)
print("=== genya top-level keys ===")
print(sorted(prof.keys()))
for k in ("version_scope", "key", "selected_key", "primary_form", "default_form", "tier"):
    if k in prof: print(k, "->", json.dumps(prof[k])[:200])
print("review:", json.dumps(prof.get("review"))[:400])
print("generation:", json.dumps(prof.get("generation"))[:300])

# find a generated profile with >1 key-form and scope set
print("\n=== generated multi-form profiles ===")
n = 0
for p in sorted(glob.glob("/app/profiles/generated/**/*.yaml", recursive=True)):
    try: g = yaml.load(open(p), Loader=yaml.CSafeLoader) or {}
    except Exception: continue
    forms = [f for f in g.get("forms") or [] if isinstance(f, dict) and f.get("source_field") == "keys"]
    if len(forms) > 1:
        n += 1
        if n <= 2:
            print(p)
            print(" forms:", [f.get("name") for f in forms])
            print(" version_scope:", json.dumps(g.get("version_scope"))[:200])
            ps = g.get("power_scale") or {}
            for axis in ("attack_potency", "speed", "durability"):
                e = ps.get(axis)
                print(" ", axis, "->", (e.get("text") if isinstance(e, dict) else e))
print("generated multi-form count:", n)

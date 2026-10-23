import sys
sys.path.insert(0, "/app/src")
import yaml
prof = yaml.load(open("/app/profiles/needs_review/anime/demon-slayer/genya-shinazugawa.yaml"), Loader=yaml.CSafeLoader)
ps = prof["power_scale"]
for ax in ("stamina", "range", "intelligence"):
    e = ps.get(ax)
    t = e.get("text") if isinstance(e, dict) else e
    print(ax, "segments:", len(str(t).split("|")) if t else 0)
    print("   ", str(t)[:400])

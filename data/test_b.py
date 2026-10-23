import sys, copy
sys.path.insert(0, "/app/src")
import yaml
from battlebot.review.auto_repair import apply_version_scope_default
from battlebot.review.service import approval_blockers

def load(p):
    return yaml.load(open(p), Loader=yaml.CSafeLoader)

for name, path in [
    ("GENYA (4 forms, 4 segs, no variant)", "/app/profiles/needs_review/anime/demon-slayer/genya-shinazugawa.yaml"),
    ("ASA (2 forms, tier2/dur3 segs)", "/app/profiles/needs_review/anime/chainsaw-man/asa-mitaka.yaml"),
    ("CRONA (1 form, 4 segs, variant key)", "/app/profiles/needs_review/anime/soul-eater/crona-pre-timeskip.yaml"),
]:
    prof = load(path)
    before = [b for b in approval_blockers(prof) if "version_scope" in b]
    rep = apply_version_scope_default(prof)
    after = [b for b in approval_blockers(prof) if "version_scope" in b]
    print("=" * 20, name)
    print(" fired:", rep["fired"], "| key:", rep["key"], "via", rep["key_origin"], "| axes:", list(rep["axes"]), "| refused:", rep["refused"])
    print(" vs blockers before:", before)
    print(" vs blockers after: ", after)
    if rep["fired"]:
        ps = prof["power_scale"]
        for ax in rep["axes"]:
            e = ps[ax]
            print("  ", ax, "->", (e.get("text") if isinstance(e, dict) else e)[:90])
        print("  version_scope:", {k: prof["version_scope"][k] for k in ("evidence_scoped", "scoped_key", "scoped_by")})

# synthetic: labelled sections
synth = {
    "name": "Test", "forms": [{"name": "Alpha", "source_field": "keys"}, {"name": "Beta", "source_field": "keys"}],
    "variant": {"source_key": "Beta"},
    "power_scale": {"attack_potency": {"text": "Alpha = Wall level | Beta = City level", "source_ids": ["s1"]}},
    "sources": [{"id": "s1", "url": "https://x.test/p"}],
}
rep = apply_version_scope_default(copy.deepcopy(synth))
print("SYNTH labelled:", rep["fired"], rep["axes"], "->", synth and apply_version_scope_default(synth) and synth["power_scale"]["attack_potency"]["text"])
# synthetic: refuse when no key info at all
synth2 = {"name": "T2", "forms": [], "power_scale": {"speed": {"text": "Fast | Faster"}}}
print("SYNTH no-key refuse:", apply_version_scope_default(synth2))

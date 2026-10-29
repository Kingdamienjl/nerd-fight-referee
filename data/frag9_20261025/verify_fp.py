import yaml, os
os.chdir("/opt/referee")

def load(p):
    with open(p) as f:
        return yaml.safe_load(f)

def bal(s):
    return s.count("(") == s.count(")")

checks = [
 ("profiles/needs_review/comics/teenage-mutant-ninja-turtles/bebop.yaml","abilities","Invisibility (Using his suit"),
 ("profiles/needs_review/comics/teenage-mutant-ninja-turtles/karai.yaml","abilities","Status Effect Inducement"),
 ("profiles/needs_review/comics/teenage-mutant-ninja-turtles/leatherhead.yaml","abilities","Natural Weaponry"),
 ("profiles/needs_review/comics/transformers/arcee.yaml","abilities","Immortality (Type 1 and 2"),
 ("profiles/needs_review/comics/transformers/galvatron.yaml","abilities","Immortality (Type 1 and 2"),
 ("profiles/needs_review/comics/transformers/galvatron.yaml","abilities","Resistances to Fire"),
 ("profiles/needs_review/comics/transformers/wheeljack.yaml","abilities","Large Size (Type 0"),
 ("profiles/needs_review/comics/transformers/wheeljack.yaml","abilities","Space Survival"),
 ("profiles/needs_review/comics/transformers/wheeljack.yaml","abilities","Self-Sustenance (Type 1"),
 ("profiles/needs_review/comics/transformers/wheeljack.yaml","abilities","Immortality (Type 2"),
 ("profiles/needs_review/comics/transformers/wheeljack.yaml","abilities","Bodily Weaponry"),
 ("profiles/needs_review/comics/transformers/wheeljack.yaml","abilities","Statistics Amplification"),
 ("profiles/needs_review/game/castlevania/death.yaml","abilities","Resurrection and Regeneration Negation"),
 ("profiles/needs_review/game/castlevania/death.yaml","abilities","Conceptual Manipulation"),
 ("profiles/needs_review/game/castlevania/death.yaml","abilities","Subjective Reality"),
 ("profiles/needs_review/game/castlevania/death.yaml","abilities","Telekinesis"),
 ("profiles/needs_review/game/castlevania/death.yaml","abilities","Energy Absorption"),
 ("profiles/needs_review/game/castlevania/hector.yaml","abilities","Weapon Mastery"),
 ("profiles/needs_review/game/castlevania/hector.yaml","abilities","Extrasensory Perception"),
 ("profiles/needs_review/game/castlevania/hector.yaml","abilities","Resurrection and Regeneration Negation"),
 ("profiles/needs_review/game/castlevania/hector.yaml","abilities","Absolute Zero"),
 ("profiles/needs_review/game/castlevania/hector.yaml","abilities","Sleep Manipulation"),
]
bad = []
for path, field, prefix in checks:
    d = load(path)
    items = d.get(field, []) or []
    hit = [it for it in items if str(it.get("name", "")).startswith(prefix)]
    if not hit:
        bad.append((path, prefix, "NOT FOUND"))
        print("BAD-NOTFOUND %s %s" % (path.split("/")[-1], prefix))
        continue
    it = hit[0]
    n, ds = str(it.get("name", "")), str(it.get("description", ""))
    ok = len(n) == 120 and bal(ds)
    tag = "OK" if ok else "BAD"
    print("%s %s name_len=%d desc_bal=%s name_tail=%r desc_tail=%r" % (tag, path.split("/")[-1], len(n), bal(ds), n[-20:], ds[-25:]))
    if not ok:
        bad.append((path, prefix, "name_len=%d desc_bal=%s" % (len(n), bal(ds))))

print("BARE-NAME checks:")
for path, nm in [("profiles/needs_review/comics/teenage-mutant-ninja-turtles/bebop.yaml","Stealth"),
 ("profiles/needs_review/comics/teenage-mutant-ninja-turtles/metalhead.yaml","Flight"),
 ("profiles/needs_review/comics/transformers/arcee.yaml","Flight"),
 ("profiles/needs_review/comics/transformers/galvatron.yaml","Flight"),
 ("profiles/needs_review/comics/transformers/starscream.yaml","Flight"),
 ("profiles/needs_review/game/castlevania/death.yaml","Flight")]:
    d = load(path)
    names = [str(i.get("name")) for i in (d.get("abilities") or [])]
    print("  %s: %r present=%s" % (path.split("/")[-1], nm, nm in names))

print("DEVASTATOR live range: %r" % (load("profiles/needs_review/comics/transformers/devastator.yaml").get("range"),))
print("TIERS live:")
for p in ["arcee","blackarachnia","galvatron","ironhide","predaking"]:
    d = load("profiles/needs_review/comics/transformers/%s.yaml" % p)
    print("  %s: tier=%r" % (p, d.get("tier")))
print("BAD: %s" % (bad if bad else "none"))

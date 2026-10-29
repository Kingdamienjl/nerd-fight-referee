import tarfile, yaml, os, json

BK = "/opt/referee/backups/20261025-frag9-gate/profiles.tar.gz"
OUT = "/tmp/frag9_pre"
os.makedirs(OUT, exist_ok=True)

BAD = {
 "profiles/needs_review/comics/teenage-mutant-ninja-turtles/casey-jones.yaml": {
   "weak_bad": ["yet believes himself to be and thus can be overwhelmed by the stronger mutants they may face. In general"]},
 "profiles/needs_review/comics/teenage-mutant-ninja-turtles/leatherhead.yaml": {
   "weak_bad": ["especially when anything related to the Kraang is brought up"]},
 "profiles/needs_review/comics/teenage-mutant-ninja-turtles/shredder.yaml": {
   "weak_bad": ["where he is ticklish."]},
 "profiles/needs_review/comics/transformers/arcee.yaml": {
   "tier_bad": "likely higher. with swords"},
 "profiles/needs_review/comics/transformers/blackarachnia.yaml": {
   "weak_bad": ["insane and is very self loathing."],
   "tier_bad": "At most , possibly far higher"},
 "profiles/needs_review/comics/transformers/devastator.yaml": {
   "weak_bad": ["Devastator is hardly slow. He is",
                "rather easy to outmaneuver. His lacking intelligence offers little combat adaptability. As the Constructicons'"],
   "range_bad": "Extended Melee Range, likely several hundreds of meters with the Solar Beam Rifle SolarBeamRifleDevastation.png DrillMisslesDevastation.jpg DrillsDevastation.jpg"},
 "profiles/needs_review/comics/transformers/galvatron.yaml": {
   "tier_bad": "At least , higher with the Heart of Darkness"},
 "profiles/needs_review/comics/transformers/ironhide.yaml": {
   "weak_bad": ["As Ironhide ages"],
   "tier_bad": "At most . higher with Stealth Force, even higher with Heavy Iron 2.0"},
 "profiles/needs_review/comics/transformers/predaking.yaml": {
   "tier_bad": "At least , likely higher, even higher with Beast Mode"},
 "profiles/needs_review/comics/transformers/rodimus-prime.yaml": {
   "weak_bad": ["feeling he don't ever live up to Optimus Prime. Without the Matrix of Leadership"]},
 "profiles/needs_review/comics/transformers/soundwave.yaml": {
   "weak_bad": ["as he passes up a chance to kill Wheeljack in order to save Laserbeak."]},
 "profiles/needs_review/comics/transformers/starscream.yaml": {
   "weak_bad": ["very short tempered (If something doesn't go his way he will throw a tantrum). If the allspark shard in his head is remo"]},
 "profiles/needs_review/comics/transformers/ultra-magnus.yaml": {
   "weak_bad": ["to the point where it could potentially impede his judgement"]},
}

tf = tarfile.open(BK, "r:gz")
names = tf.getnames()
print("tar members sample:", names[:3])
# find the member name matching each profile path (tar may have a prefix)
def find_member(path):
    for n in names:
        if n.endswith(path):
            return n
    return None

for path, spec in BAD.items():
    m = find_member(path)
    if not m:
        print("MISSING IN BACKUP:", path)
        continue
    f = tf.extractfile(m)
    pre = yaml.safe_load(f)
    live = yaml.safe_load(open("/opt/referee/" + path))
    pre_w = [str(i.get("name")) for i in (pre.get("weaknesses") or [])]
    live_w = [str(i.get("name")) for i in (live.get("weaknesses") or [])]
    pre_ps = pre.get("power_scale") or {}
    live_ps = live.get("power_scale") or {}
    print("=" * 100)
    print(path)
    print("  pre-run weaknesses (%d): %s" % (len(pre_w), pre_w))
    print("  live  weaknesses (%d): %s" % (len(live_w), live_w))
    print("  added weaknesses: %s" % ([w for w in live_w if w not in pre_w],))
    print("  removed weaknesses: %s" % ([w for w in pre_w if w not in live_w],))
    for k in sorted(set(list(pre_ps.keys()) + list(live_ps.keys()))):
        pv = pre_ps.get(k)
        lv = live_ps.get(k)
        pt = pv.get("text") if isinstance(pv, dict) else pv
        lt = lv.get("text") if isinstance(lv, dict) else lv
        if pt != lt:
            print("  power_scale.%s PRE=%r LIVE=%r" % (k, pt, lt))
    # bad items present in live? (prefix match: names are capped at 120 chars)
    for b in spec.get("weak_bad", []):
        in_live = any(w.startswith(b) or b.startswith(w) for w in live_w)
        in_pre = any(w.startswith(b) or b.startswith(w) for w in pre_w)
        print("  weak_bad present in live: %s -> %s" % (b[:50], in_live))
        print("  weak_bad present in pre : %s -> %s" % (b[:50], in_pre))
    if "tier_bad" in spec:
        print("  tier_bad live match: %s" % (live_ps.get("tier", {}).get("text") == spec["tier_bad"] if isinstance(live_ps.get("tier"), dict) else False))
        print("  tier pre-run: %r" % (pre_ps.get("tier"),))
    if "range_bad" in spec:
        print("  range_bad live match: %s" % (live_ps.get("range", {}).get("text") == spec["range_bad"] if isinstance(live_ps.get("range"), dict) else False))
        print("  range pre-run: %r" % (pre_ps.get("range"),))
    # progress markers: repair block
    print("  live repair.repaired_fields: %s" % (live.get("repair", {}).get("repaired_fields"),))
    print("  pre  repair.repaired_fields: %s" % (pre.get("repair", {}).get("repaired_fields"),))
    print("  live repair.attempted_at: %s pre: %s" % (live.get("repair", {}).get("attempted_at"), pre.get("repair", {}).get("attempted_at")))

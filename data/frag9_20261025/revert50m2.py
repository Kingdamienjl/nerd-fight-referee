"""Frag-9 gate FAIL revert (v2): surgical item/field-level only.
Removes the bad weakness items and restores the bad power_scale tier/range
slots to their exact pre-run (empty) values from the gate backup.
Leaves everything else (abilities, good stats, good weaknesses, derived
fields like battle_eligible/status/generation/review) exactly as the gate
left them. Progress keys were already removed in v1 run.
Gate verdict: FAIL; cohort does NOT run."""
import tarfile, yaml, os, json, hashlib, copy

BK = "/opt/referee/backups/20261025-frag9-gate/profiles.tar.gz"
REPORT = "/opt/referee/data/frag9_20261025/revert_report.json"

REVERTS = {
 "profiles/needs_review/comics/teenage-mutant-ninja-turtles/casey-jones.yaml": {
   "weak": ["yet believes himself to be and thus can be overwhelmed by the stronger mutants they may face. In general"]},
 "profiles/needs_review/comics/teenage-mutant-ninja-turtles/leatherhead.yaml": {
   "weak": ["especially when anything related to the Kraang is brought up"]},
 "profiles/needs_review/comics/teenage-mutant-ninja-turtles/shredder.yaml": {
   "weak": ["where he is ticklish."]},
 "profiles/needs_review/comics/transformers/arcee.yaml": {
   "tier": "likely higher. with swords"},
 "profiles/needs_review/comics/transformers/blackarachnia.yaml": {
   "weak": ["insane and is very self loathing."],
   "tier": "At most , possibly far higher"},
 "profiles/needs_review/comics/transformers/devastator.yaml": {
   "weak": ["Devastator is hardly slow. He is",
            "rather easy to outmaneuver. His lacking intelligence offers little combat adaptability. As the Constructicons'"],
   "range": "Extended Melee Range, likely several hundreds of meters with the Solar Beam Rifle SolarBeamRifleDevastation.png DrillMisslesDevastation.jpg DrillsDevastation.jpg"},
 "profiles/needs_review/comics/transformers/galvatron.yaml": {
   "tier": "At least , higher with the Heart of Darkness"},
 "profiles/needs_review/comics/transformers/ironhide.yaml": {
   "weak": ["As Ironhide ages"],
   "tier": "At most . higher with Stealth Force, even higher with Heavy Iron 2.0"},
 "profiles/needs_review/comics/transformers/predaking.yaml": {
   "tier": "At least , likely higher, even higher with Beast Mode"},
 "profiles/needs_review/comics/transformers/rodimus-prime.yaml": {
   "weak": ["feeling he don't ever live up to Optimus Prime. Without the Matrix of Leadership"]},
 "profiles/needs_review/comics/transformers/soundwave.yaml": {
   "weak": ["as he passes up a chance to kill Wheeljack in order to save Laserbeak."]},
 "profiles/needs_review/comics/transformers/starscream.yaml": {
   "weak": ["very short tempered (If something doesn't go his way he will throw a tantrum). If the allspark shard in his head is remo"]},
 "profiles/needs_review/comics/transformers/ultra-magnus.yaml": {
   "weak": ["to the point where it could potentially impede his judgement"]},
}

def json_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True, default=str).encode("utf-8")).hexdigest()

def stable_hash(profile):
    clone = json.loads(json.dumps(profile, sort_keys=True, default=str))
    clone["profile_hash"] = ""
    return json_hash(clone)

def md5(path):
    return hashlib.md5(open(path, "rb").read()).hexdigest()

tf = tarfile.open(BK, "r:gz")
names = tf.getnames()
def find_member(path):
    for n in names:
        if n.endswith(path):
            return n
    return None

report = {"reverted": {}, "aborted": {}}
os.chdir("/opt/referee")

for path, spec in REVERTS.items():
    m = find_member(path)
    pre = yaml.safe_load(tf.extractfile(m))
    live = yaml.safe_load(open(path))
    pre_ps = pre.get("power_scale") or {}
    live_ps = live.get("power_scale") or {}
    before_md5 = md5(path)
    removed_weak = []
    live_w = live.get("weaknesses") or []
    ok = True
    for prefix in spec.get("weak", []):
        hits = [it for it in live_w if str(it.get("name", "")).startswith(prefix)]
        if len(hits) != 1:
            report["aborted"][path] = {"weak_match": prefix, "hits": len(hits)}
            print("ABORT %s weak match %r hits=%d" % (path, prefix, len(hits)))
            ok = False
            break
        live_w.remove(hits[0])
        removed_weak.append(str(hits[0].get("name")))
    if not ok:
        continue
    live["weaknesses"] = live_w
    restored = {}
    # tier / range: live text must equal the manifest value; pre-run must be the empty slot
    if "tier" in spec:
        live_tier = live_ps.get("tier") or {}
        if (live_tier.get("text") if isinstance(live_tier, dict) else live_tier) != spec["tier"]:
            report["aborted"][path] = {"tier_live_mismatch": live_tier}
            print("ABORT %s tier live mismatch: %r" % (path, live_tier))
            continue
        pre_tier = pre_ps.get("tier")
        if not (isinstance(pre_tier, dict) and pre_tier.get("text") is None):
            report["aborted"][path] = {"tier_pre_not_empty": pre_tier}
            print("ABORT %s tier pre-run not empty: %r" % (path, pre_tier))
            continue
        live_ps["tier"] = copy.deepcopy(pre_tier)
        restored["tier"] = pre_tier
    if "range" in spec:
        live_range = live_ps.get("range") or {}
        if (live_range.get("text") if isinstance(live_range, dict) else live_range) != spec["range"]:
            report["aborted"][path] = {"range_live_mismatch": live_range}
            print("ABORT %s range live mismatch: %r" % (path, live_range))
            continue
        pre_range = pre_ps.get("range")
        if not (isinstance(pre_range, dict) and pre_range.get("text") is None):
            report["aborted"][path] = {"range_pre_not_empty": pre_range}
            print("ABORT %s range pre-run not empty: %r" % (path, pre_range))
            continue
        live_ps["range"] = copy.deepcopy(pre_range)
        restored["range"] = pre_range
    live["power_scale"] = live_ps
    live["profile_hash"] = stable_hash(live)
    with open(path, "w") as f:
        yaml.safe_dump(live, f, sort_keys=False, allow_unicode=False)
    report["reverted"][path] = {
        "md5_before": before_md5,
        "md5_after": md5(path),
        "removed_weaknesses": removed_weak,
        "restored_power_scale": restored,
        "weaknesses_now": [str(i.get("name")) for i in (live.get("weaknesses") or [])],
        "abilities_now": len(live.get("abilities") or []),
    }
    print("REVERTED %s removed_weak=%d restored=%s" % (path.split("/")[-1], len(removed_weak), list(restored.keys())))

json.dump(report, open(REPORT, "w"), indent=1, default=str)
print("REPORT: %s" % REPORT)
print("reverted=%d aborted=%d" % (len(report["reverted"]), len(report["aborted"])))

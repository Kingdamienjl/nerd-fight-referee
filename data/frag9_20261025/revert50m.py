"""Frag-9 gate FAIL revert: remove the bad merges item/field-level from the
gate backup (20261025-frag9-gate), keep audited-good merges, drop progress
keys for the 13 reverted profiles. Writes a JSON report of what changed.
Gate verdict: FAIL (manual review found battery-clean debris in 13 of 23
recovered profiles; cohort does NOT run)."""
import tarfile, yaml, os, json, hashlib, copy

BK = "/opt/referee/backups/20261025-frag9-gate/profiles.tar.gz"
PROG = "/opt/referee/data/recovery_progress.json"
REPORT = "/opt/referee/data/frag9_20261025/revert_report.json"

# name -> prefix to match (live names are capped at 120 chars; starscream's is truncated)
REVERTS = {
 "profiles/needs_review/comics/teenage-mutant-ninja-turtles/casey-jones.yaml": {
   "weak": ["yet believes himself to be and thus can be overwhelmed by the stronger mutants they may face. In general"]},
 "profiles/needs_review/comics/teenage-mutant-ninja-turtles/leatherhead.yaml": {
   "weak": ["especially when anything related to the Kraang is brought up"]},
 "profiles/needs_review/comics/teenage-mutant-ninja-turtles/shredder.yaml": {
   "weak": ["where he is ticklish."]},
 "profiles/needs_review/comics/transformers/arcee.yaml": {
   "tier": True},
 "profiles/needs_review/comics/transformers/blackarachnia.yaml": {
   "weak": ["insane and is very self loathing."],
   "tier": True},
 "profiles/needs_review/comics/transformers/devastator.yaml": {
   "weak": ["Devastator is hardly slow. He is",
            "rather easy to outmaneuver. His lacking intelligence offers little combat adaptability. As the Constructicons'"],
   "range": True},
 "profiles/needs_review/comics/transformers/galvatron.yaml": {
   "tier": True},
 "profiles/needs_review/comics/transformers/ironhide.yaml": {
   "weak": ["As Ironhide ages"],
   "tier": True},
 "profiles/needs_review/comics/transformers/predaking.yaml": {
   "tier": True},
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

report = {"reverted": {}, "aborted": {}, "progress_removed": {}}
os.chdir("/opt/referee")

for path, spec in REVERTS.items():
    m = find_member(path)
    pre = yaml.safe_load(tf.extractfile(m))
    live = yaml.safe_load(open(path))
    # full top-level diff guard: only weaknesses/power_scale/profile_hash/repair may differ
    allowed = {"weaknesses", "power_scale", "profile_hash", "repair"}
    diffkeys = [k for k in set(list(pre.keys()) + list(live.keys())) if pre.get(k) != live.get(k) and k not in allowed]
    if diffkeys:
        report["aborted"][path] = {"unexpected_diff_keys": diffkeys}
        print("ABORT %s unexpected diff keys: %s" % (path, diffkeys))
        continue
    before_md5 = md5(path)
    removed_weak = []
    live_w = live.get("weaknesses") or []
    for prefix in spec.get("weak", []):
        hits = [it for it in live_w if str(it.get("name", "")).startswith(prefix)]
        if len(hits) != 1:
            report["aborted"][path] = {"weak_match": prefix, "hits": len(hits)}
            print("ABORT %s weak match %r hits=%d" % (path, prefix, len(hits)))
            break
        live_w.remove(hits[0])
        removed_weak.append(str(hits[0].get("name")))
    else:
        live["weaknesses"] = live_w
        restored = {}
        pre_ps = pre.get("power_scale") or {}
        live_ps = live.get("power_scale") or {}
        if spec.get("tier"):
            live_ps["tier"] = copy.deepcopy(pre_ps.get("tier"))
            restored["tier"] = pre_ps.get("tier")
        if spec.get("range"):
            live_ps["range"] = copy.deepcopy(pre_ps.get("range"))
            restored["range"] = pre_ps.get("range")
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
        }
        print("REVERTED %s removed=%d restored=%s" % (path.split("/")[-1], len(removed_weak), list(restored.keys())))

# progress keys: drop the 13 reverted profiles so they re-queue for a fixed run
progress = json.loads(open(PROG).read())
for path in REVERTS:
    if path in progress:
        report["progress_removed"][path] = progress.pop(path)
        print("PROGRESS-REMOVED %s entry=%s" % (path.split("/")[-1], json.dumps(report["progress_removed"][path])[:200]))
    else:
        print("PROGRESS-ABSENT %s (not in progress file)" % path)
tmp = PROG + ".tmp"
open(tmp, "w").write(json.dumps(progress, indent=1, sort_keys=True))
os.replace(tmp, PROG)

json.dump(report, open(REPORT, "w"), indent=1, default=str)
print("REPORT: %s" % REPORT)
print("reverted=%d aborted=%d progress_removed=%d" % (len(report["reverted"]), len(report["aborted"]), len(report["progress_removed"])))

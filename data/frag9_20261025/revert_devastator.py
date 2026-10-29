"""Frag-9 gate FAIL revert: devastator only (v2 aborted on a one-char prefix
mismatch — the live name has NO trailing apostrophe after 'Constructicons').
Removes both bad weakness items, restores power_scale.range to the exact
pre-run empty slot from the gate backup. Leaves all else untouched."""
import tarfile, yaml, os, json, hashlib, copy

BK = "/opt/referee/backups/20261025-frag9-gate/profiles.tar.gz"
PATH = "profiles/needs_review/comics/transformers/devastator.yaml"
REPORT = "/opt/referee/data/frag9_20261025/revert_report_devastator.json"

def json_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True, default=str).encode("utf-8")).hexdigest()

def stable_hash(profile):
    clone = json.loads(json.dumps(profile, sort_keys=True, default=str))
    clone["profile_hash"] = ""
    return json_hash(clone)

def md5(path):
    return hashlib.md5(open(path, "rb").read()).hexdigest()

tf = tarfile.open(BK, "r:gz")
member = [n for n in tf.getnames() if n.endswith(PATH)][0]
pre = yaml.safe_load(tf.extractfile(member))
os.chdir("/opt/referee")
live = yaml.safe_load(open(PATH))
before = md5(PATH)

# confirm the two bad items are present (exact names from the live file)
live_names = [str(i.get("name")) for i in (live.get("weaknesses") or [])]
print("live weaknesses:", live_names)
assert "Devastator is hardly slow. He is" in live_names, "first bad item missing"
second = [n for n in live_names if n.startswith("rather easy to outmaneuver")]
assert len(second) == 1, "second bad item match count %d" % len(second)
print("second bad item exact name: %r (len %d)" % (second[0], len(second[0])))

live["weaknesses"] = [it for it in (live.get("weaknesses") or [])
                      if str(it.get("name")) not in ("Devastator is hardly slow. He is", second[0])]
pre_range = (pre.get("power_scale") or {}).get("range")
assert isinstance(pre_range, dict) and pre_range.get("text") is None, "pre-run range not empty: %r" % (pre_range,)
live_range = (live.get("power_scale") or {}).get("range") or {}
assert live_range.get("text", "").startswith("Extended Melee Range, likely several hundreds of meters with the Solar Beam Rifle"), "live range unexpected: %r" % (live_range,)
live["power_scale"]["range"] = copy.deepcopy(pre_range)
live["profile_hash"] = stable_hash(live)
with open(PATH, "w") as f:
    yaml.safe_dump(live, f, sort_keys=False, allow_unicode=False)

out = {"md5_before": before, "md5_after": md5(PATH),
       "removed_weaknesses": ["Devastator is hardly slow. He is", second[0]],
       "restored_range": pre_range,
       "weaknesses_now": [str(i.get("name")) for i in (live.get("weaknesses") or [])],
       "abilities_now": len(live.get("abilities") or [])}
json.dump(out, open(REPORT, "w"), indent=1, default=str)
print("REVERTED devastator:", json.dumps(out, indent=1, default=str))

"""Frag-9 gate FAIL revert: blackarachnia re-revert (the drain's in-flight
write re-merged the bad items 9s after the first revert). Same surgical
revert: remove 'insane and is very self loathing.', restore tier to the
exact pre-run empty slot. Then report current mtime/md5 for a stability watch."""
import tarfile, yaml, os, json, hashlib, copy

BK = "/opt/referee/backups/20261025-frag9-gate/profiles.tar.gz"
PATH = "profiles/needs_review/comics/transformers/blackarachnia.yaml"
REPORT = "/opt/referee/data/frag9_20261025/revert_report_blackarachnia2.json"

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
print("live weaknesses before:", [str(i.get("name")) for i in (live.get("weaknesses") or [])])
print("live tier before:", repr((live.get("power_scale") or {}).get("tier")))
assert "insane and is very self loathing." in [str(i.get("name")) for i in (live.get("weaknesses") or [])], "bad weakness not present (already reverted?)"
live["weaknesses"] = [it for it in (live.get("weaknesses") or []) if str(it.get("name")) != "insane and is very self loathing."]
pre_tier = (pre.get("power_scale") or {}).get("tier")
assert isinstance(pre_tier, dict) and pre_tier.get("text") is None
live["power_scale"]["tier"] = copy.deepcopy(pre_tier)
live["profile_hash"] = stable_hash(live)
with open(PATH, "w") as f:
    yaml.safe_dump(live, f, sort_keys=False, allow_unicode=False)
out = {"md5_before": before, "md5_after": md5(PATH),
       "weaknesses_now": [str(i.get("name")) for i in (live.get("weaknesses") or [])],
       "tier_now": (live.get("power_scale") or {}).get("tier")}
json.dump(out, open(REPORT, "w"), indent=1, default=str)
print("RE-REVERTED blackarachnia:", json.dumps(out, indent=1, default=str))

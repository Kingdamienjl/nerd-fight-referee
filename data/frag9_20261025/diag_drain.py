import yaml, json, hashlib, os
from datetime import datetime

def json_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True, default=str).encode("utf-8")).hexdigest()

def stable_hash(profile):
    clone = json.loads(json.dumps(profile, sort_keys=True, default=str))
    clone["profile_hash"] = ""
    return json_hash(clone)

os.chdir("/opt/referee")
print("now UTC:", datetime.utcnow().strftime("%H:%M:%S"))
# hash-function check on gate-written, never-reverted files
for path in ["profiles/needs_review/game/castlevania/death.yaml",
             "profiles/needs_review/game/castlevania/hector.yaml",
             "profiles/needs_review/comics/teenage-mutant-ninja-turtles/april-o-neil.yaml"]:
    d = yaml.safe_load(open(path))
    mine = stable_hash(d)
    print("HASH-CHECK %s stored==mine: %s" % (path.split("/")[-1], d.get("profile_hash") == mine))
    # what types are the timestamp fields?
    print("   attempted_at type=%s val=%r" % (type(d.get("repair", {}).get("attempted_at")).__name__, d.get("repair", {}).get("attempted_at")))
    print("   generated_at type=%s val=%r" % (type(d.get("generation", {}).get("generated_at")).__name__, d.get("generation", {}).get("generated_at")))

# drain-touched reverted files: metadata now
for path in ["profiles/needs_review/comics/transformers/blackarachnia.yaml",
             "profiles/needs_review/comics/transformers/ironhide.yaml",
             "profiles/needs_review/comics/transformers/predaking.yaml",
             "profiles/needs_review/comics/transformers/starscream.yaml"]:
    d = yaml.safe_load(open(path))
    mine = stable_hash(d)
    print("DRAIN-TOUCHED %s mtime=%s stored==mine: %s" % (
        path.split("/")[-1],
        datetime.utcfromtimestamp(os.path.getmtime(path)).strftime("%H:%M:%S"),
        d.get("profile_hash") == mine))
    print("   attempted_at=%r gen_conf=%r battle_eligible=%r status=%r" % (
        d.get("repair", {}).get("attempted_at"),
        (d.get("generation") or {}).get("confidence"),
        d.get("battle_eligible"), d.get("status")))
    print("   weaknesses=%s" % ([str(i.get("name")) for i in (d.get("weaknesses") or [])],))
    print("   tier=%r range=%r" % ((d.get("power_scale") or {}).get("tier", {}).get("text") if isinstance((d.get("power_scale") or {}).get("tier"), dict) else (d.get("power_scale") or {}).get("tier"),
                                   (d.get("power_scale") or {}).get("range", {}).get("text") if isinstance((d.get("power_scale") or {}).get("range"), dict) else (d.get("power_scale") or {}).get("range")))

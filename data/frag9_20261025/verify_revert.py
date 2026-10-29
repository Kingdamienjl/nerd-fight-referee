"""Frag-9 gate FAIL revert verification (run inside the one-off container):
for each of the 13 reverted profiles: validate_profile_path passes,
profile_hash recomputes, bad items absent, good merges intact, tier/range
restored to empty. For the 10 clean profiles: merged content still present.
"""
import sys, json, hashlib
sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")
import yaml
from pathlib import Path
from battlebot.ingest.import_profiles import validate_profile_path

def json_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True, default=str).encode("utf-8")).hexdigest()

def stable_hash(profile):
    clone = json.loads(json.dumps(profile, sort_keys=True, default=str))
    clone["profile_hash"] = ""
    return json_hash(clone)

# expected good weaknesses remaining after revert (from the manifest, minus bad)
EXPECTED_WEAK = {
 "profiles/needs_review/comics/teenage-mutant-ninja-turtles/casey-jones.yaml": ["Casey isn't as skilled as the other Turtles", "Casey suffers from overconfidence."],
 "profiles/needs_review/comics/teenage-mutant-ninja-turtles/leatherhead.yaml": ["Loses control of his emotions", "though he manages to gain some control over this as time goes on."],
 "profiles/needs_review/comics/teenage-mutant-ninja-turtles/shredder.yaml": ["The Shredder has a weak spot behind his right leg"],
 "profiles/needs_review/comics/transformers/arcee.yaml": [],
 "profiles/needs_review/comics/transformers/blackarachnia.yaml": ["Overconfident from time to time"],
 "profiles/needs_review/comics/transformers/devastator.yaml": [],
 "profiles/needs_review/comics/transformers/galvatron.yaml": ["Overconfidence coupled with insanity makes him liable to do almost anything in a fight"],
 "profiles/needs_review/comics/transformers/ironhide.yaml": ["it gets harder and harder for him to continue fighting."],
 "profiles/needs_review/comics/transformers/predaking.yaml": ["Predaking was formerly just a mindless beast that could not properly strategize on its own", "though this weakness was overcome when he gradually evolved. Extreme cold can also halt him as it does regular Transform"],
 "profiles/needs_review/comics/transformers/rodimus-prime.yaml": ["Rodimus bears heavy amounts of self-doubt and insecurity over his position as leader", "Rodimus Prime will revert back to Hot Rod."],
 "profiles/needs_review/comics/transformers/soundwave.yaml": ["It is shown that he cares deeply about his cassettes"],
 "profiles/needs_review/comics/transformers/starscream.yaml": ["he will die."],
 "profiles/needs_review/comics/transformers/ultra-magnus.yaml": ["He is extremely strict with following protocol"],
}
BAD_FRAGMENTS = ["yet believes himself", "especially when anything related to the Kraang",
 "where he is ticklish", "insane and is very self loathing", "Devastator is hardly slow",
 "rather easy to outmaneuver", "As Ironhide ages",
 "feeling he don't ever live up", "as he passes up a chance to kill Wheeljack",
 "very short tempered", "to the point where it could potentially impede"]
TIER_REVERTED = ["profiles/needs_review/comics/transformers/arcee.yaml",
 "profiles/needs_review/comics/transformers/blackarachnia.yaml",
 "profiles/needs_review/comics/transformers/galvatron.yaml",
 "profiles/needs_review/comics/transformers/ironhide.yaml",
 "profiles/needs_review/comics/transformers/predaking.yaml"]
CLEAN = ["profiles/needs_review/comics/teenage-mutant-ninja-turtles/april-o-neil.yaml",
 "profiles/needs_review/comics/teenage-mutant-ninja-turtles/bebop.yaml",
 "profiles/needs_review/comics/teenage-mutant-ninja-turtles/karai.yaml",
 "profiles/needs_review/comics/teenage-mutant-ninja-turtles/metalhead.yaml",
 "profiles/needs_review/comics/teenage-mutant-ninja-turtles/rocksteady.yaml",
 "profiles/needs_review/comics/transformers/bumblebee.yaml",
 "profiles/needs_review/comics/transformers/shockwave.yaml",
 "profiles/needs_review/comics/transformers/wheeljack.yaml",
 "profiles/needs_review/game/castlevania/death.yaml",
 "profiles/needs_review/game/castlevania/hector.yaml"]

fails = []
for path, exp_weak in EXPECTED_WEAK.items():
    d = yaml.safe_load(open(path))
    names = [str(i.get("name")) for i in (d.get("weaknesses") or [])]
    ok = names == exp_weak
    if not ok:
        fails.append((path, "weaknesses mismatch: %s vs expected %s" % (names, exp_weak)))
    for frag in BAD_FRAGMENTS:
        if any(frag in n for n in names):
            fails.append((path, "bad fragment still present: %s" % frag))
    ps = d.get("power_scale") or {}
    if path in TIER_REVERTED:
        t = ps.get("tier") or {}
        if (t.get("text") if isinstance(t, dict) else t) is not None:
            fails.append((path, "tier not restored to empty: %r" % (t,)))
    if "devastator" in path:
        r = ps.get("range") or {}
        if (r.get("text") if isinstance(r, dict) else r) is not None:
            fails.append((path, "range not restored to empty: %r" % (r,)))
    if d.get("profile_hash") != stable_hash(d):
        fails.append((path, "profile_hash mismatch"))
    try:
        validate_profile_path(Path(path))
        valid = "valid"
    except Exception as e:
        valid = "INVALID: %s" % (e,)
        fails.append((path, valid))
    filled = [k for k, v in ps.items() if isinstance(v, dict) and v.get("text")]
    print("%s %s weak=%d abilities=%d stats_filled=%s" % ("OK " if ok and valid == "valid" else "BAD", path.split("/")[-1], len(names), len(d.get("abilities") or []), filled))

for path in CLEAN:
    d = yaml.safe_load(open(path))
    names = [str(i.get("name")) for i in (d.get("weaknesses") or [])]
    ps = d.get("power_scale") or {}
    filled = [k for k, v in ps.items() if isinstance(v, dict) and v.get("text")]
    try:
        validate_profile_path(Path(path))
        valid = "valid"
    except Exception as e:
        valid = "INVALID: %s" % (e,)
        fails.append((path, valid))
    print("CLEAN %s weak=%d abilities=%d stats_filled=%d %s" % (path.split("/")[-1], len(names), len(d.get("abilities") or []), len(filled), valid))

print("FAILS: %s" % (fails if fails else "none"))

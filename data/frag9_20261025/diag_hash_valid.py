"""Frag-9 revert diagnostics (container):
1. validate_profile_path on the PRE-RUN (backup) versions of the 13 reverted
   profiles -> are the validation failures pre-existing?
2. sanitize_generated_profile hash vs stored hash, for the 13 live reverted
   files -> is the drain's hash the sanitized one, and is mine wrong?
"""
import sys, tarfile, yaml, json
sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")
from pathlib import Path
from battlebot.ingest.import_profiles import validate_profile_path
from battlebot.review.service import sanitize_generated_profile, load_yaml

BK = "/app/backups/20261025-frag9-gate/profiles.tar.gz"
PRE_DIR = Path("/app/data/frag9_20261025/pre")
PRE_DIR.mkdir(exist_ok=True)

PATHS = [
 "profiles/needs_review/comics/teenage-mutant-ninja-turtles/casey-jones.yaml",
 "profiles/needs_review/comics/teenage-mutant-ninja-turtles/leatherhead.yaml",
 "profiles/needs_review/comics/teenage-mutant-ninja-turtles/shredder.yaml",
 "profiles/needs_review/comics/transformers/arcee.yaml",
 "profiles/needs_review/comics/transformers/blackarachnia.yaml",
 "profiles/needs_review/comics/transformers/devastator.yaml",
 "profiles/needs_review/comics/transformers/galvatron.yaml",
 "profiles/needs_review/comics/transformers/ironhide.yaml",
 "profiles/needs_review/comics/transformers/predaking.yaml",
 "profiles/needs_review/comics/transformers/rodimus-prime.yaml",
 "profiles/needs_review/comics/transformers/soundwave.yaml",
 "profiles/needs_review/comics/transformers/starscream.yaml",
 "profiles/needs_review/comics/transformers/ultra-magnus.yaml",
]
tf = tarfile.open(BK, "r:gz")
names = tf.getnames()
for path in PATHS:
    member = [n for n in names if n.endswith(path)][0]
    data = tf.extractfile(member).read()
    out = PRE_DIR / Path(path).name
    out.write_bytes(data)
    try:
        validate_profile_path(out)
        print("PRE-RUN VALID  %s" % Path(path).name)
    except Exception as e:
        msg = str(e).split("\n")[1].strip() if "\n" in str(e) else str(e)[:160]
        print("PRE-RUN INVALID %s :: %s" % (Path(path).name, msg[:160]))
    # generation ineligible_reasons pre vs live
    pre = yaml.safe_load(data)
    live = load_yaml(Path(path))
    print("   gen.ineligible pre=%r live=%r" % (
        (pre.get("generation") or {}).get("ineligible_reasons"),
        (live.get("generation") or {}).get("ineligible_reasons")))
    print("   sources pre=%d live=%d" % (len(pre.get("sources") or []), len(live.get("sources") or [])))
    # sanitized hash vs stored (live)
    san = sanitize_generated_profile(live)
    print("   live stored==sanitized-hash: %s" % (live.get("profile_hash") == san["profile_hash"]))

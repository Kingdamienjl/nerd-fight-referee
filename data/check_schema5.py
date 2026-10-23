import sys
sys.path.insert(0, "/app/src")
from battlebot.schemas.profile import CharacterProfile
from pydantic import ValidationError
import yaml, glob

base = None
for p in sorted(glob.glob("/app/profiles/generated/**/*.yaml", recursive=True))[:50]:
    d = yaml.load(open(p), Loader=yaml.CSafeLoader)
    if isinstance(d, dict) and d.get("name"):
        base = d; break
print("base profile:", base.get("name"), "| has version_scope key:", "version_scope" in base, "| value:", base.get("version_scope"))
for label, mutate in [
    ("as-is", lambda d: d),
    ("version_scope=None", lambda d: {**d, "version_scope": None}),
    ("version_scope=dict", lambda d: {**d, "version_scope": {"evidence_scoped": True}}),
    ("version_scope absent", lambda d: {k: v for k, v in d.items() if k != "version_scope"}),
]:
    try:
        CharacterProfile.model_validate(mutate(dict(base)))
        print(label, "-> VALID")
    except ValidationError as e:
        print(label, "-> INVALID:", [(err["loc"], err["type"]) for err in e.errors()][:3])
# how many generated files carry the key?
n_key = n_null = n_dict = 0
for p in glob.glob("/app/profiles/generated/**/*.yaml", recursive=True):
    d = yaml.load(open(p), Loader=yaml.CSafeLoader) or {}
    if "version_scope" in d:
        n_key += 1
        if d["version_scope"] is None: n_null += 1
        elif isinstance(d["version_scope"], dict): n_dict += 1
print("generated files with version_scope key:", n_key, "| null:", n_null, "| dict:", n_dict)

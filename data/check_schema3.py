import sys
sys.path.insert(0, "/app/src")
import yaml
from battlebot.schemas.profile import CharacterProfile
from pydantic import ValidationError
fields = CharacterProfile.model_fields
print("declared fields containing 'version' or 'scope':", [f for f in fields if "version" in f or "scope" in f])
import inspect
src = inspect.getsource(CharacterProfile)
for line in src.splitlines():
    if "version" in line or "scope" in line:
        print("  ", line.strip())
prof = yaml.load(open("/app/profiles/needs_review/anime/digimon/beelzemon.yaml"), Loader=yaml.CSafeLoader)
print("version_scope in beelzemon file:", prof.get("version_scope"))
try:
    CharacterProfile.model_validate(prof)
    print("validates OK")
except ValidationError as e:
    for err in e.errors():
        print("ERR", err["loc"], err["type"], err["msg"], "| input type:", type(err.get("input")).__name__)

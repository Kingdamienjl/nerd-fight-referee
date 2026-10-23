import sys
sys.path.insert(0, "/app/src")
import yaml
from battlebot.review.service import sanitize_generated_profile, schema_validation_blockers
g = yaml.load(open("/app/profiles/needs_review/anime/demon-slayer/genya-shinazugawa.yaml"), Loader=yaml.CSafeLoader)
print("genya raw version_scope:", g.get("version_scope", "<absent>"))
print("genya raw schema blockers:", schema_validation_blockers(g))
s = sanitize_generated_profile(g)
print("genya sanitized version_scope:", s.get("version_scope", "<absent>"))
print("genya sanitized schema blockers:", schema_validation_blockers(s))
b = yaml.load(open("/app/profiles/needs_review/anime/digimon/beelzemon.yaml"), Loader=yaml.CSafeLoader)
print("beelzemon sanitized schema blockers:", schema_validation_blockers(sanitize_generated_profile(b)))
import inspect
src = inspect.getsource(sanitize_generated_profile)
print(src[:1800])

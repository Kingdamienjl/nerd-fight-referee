import logging, sys
sys.path.insert(0, "/app/src")
logging.basicConfig(level=logging.INFO, format="LOG %(levelname)s %(message)s")
from battlebot.harvest.fallback_parsers import extract_with_llm, llm_fallback_enabled

print("llm_fallback_enabled:", llm_fallback_enabled())
text = (
    "Anos Voldigoad is the protagonist of The Misfit of Demon King Academy. "
    "Tier: Low 2-C. Attack Potency: Low Complex Multiverse level. Speed: Infinite. "
    "Durability: Low Complex Multiverse level. Powers and Abilities: Superhuman "
    "Physical Characteristics, Magic, Immortality (Types 1, 3, 4 and 8), Regeneration "
    "(High-Godly), Existence Erasure, Conceptual Manipulation (Type 1)."
)
stats = extract_with_llm(text, title="Anos Voldigoad")
print("result type:", type(stats).__name__)
if stats is not None:
    fields = stats.to_canonical_fields()
    print("canonical fields:", sorted(fields.keys()))
    print("tier:", fields.get("tier"), "| ap:", str(fields.get("attack_potency"))[:50])
print("LLM STEP TEST DONE")

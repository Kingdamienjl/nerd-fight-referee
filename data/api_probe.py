import sys

sys.path.insert(0, "/app/src")
from battlebot.review import auto_repair as ar

names = [
    "_resolve_mediawiki_page", "_canonical_text", "_tokens", "_text",
    "_title_continuity", "profile_continuity_scope", "continuity_check",
    "placeholder_item_reasons", "stat_field_rejection_reasons",
    "normalize_text", "recover_profile_evidence", "repair_profile",
    "normalized_identity_text", "title_from_wiki_url",
]
print({n: hasattr(ar, n) for n in names})
print("resolve-ish:", [n for n in dir(ar) if "resolve" in n or "mediawiki" in n])
print("page-ish:", [n for n in dir(ar) if "page" in n and not n.startswith("__")][:20])

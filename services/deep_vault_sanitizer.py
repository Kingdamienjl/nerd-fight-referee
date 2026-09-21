#!/usr/bin/env python3
"""
Nerd Referee Deep Vault Sanitizer
==================================
Purges wiki category sludge, MediaWiki templates, navigation footers,
and non-combat metadata across:
  1. All YAML profiles in /opt/referee/profiles/generated/
  2. PostgreSQL database `battlebot` (character_profiles and relational tables)
"""

import os
import sys
import re
import json
import logging
from pathlib import Path
import yaml
import asyncpg
import asyncio

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
LOGGER = logging.getLogger("DeepVaultSanitizer")

PROFILES_DIR = Path("/opt/referee/profiles/generated")

PURE_SLUDGE_PATTERNS = [
    re.compile(r"^\s*category:\s*[a-zA-Z]", re.I),
    re.compile(r"^\s*\{\{\s*(?:border|scroll|#tag|reflist|discussions|!)", re.I),
    re.compile(r"^\s*\{\{", re.I),
    re.compile(r"\}\}\s*$", re.I),
    re.compile(r"^\s*(?:content|padding|visible|scroll)\s*=", re.I),
    re.compile(r"^\s*==\s*(?:notable matchups|notes/explanations|references|sources|statistics values)\s*==", re.I),
    re.compile(r"^\s*\b(?:victories|losses|inconclusive)\s*[:=]", re.I),
    re.compile(r"power-scaling rules for", re.I),
    re.compile(r"before making any changes to this page", re.I),
    re.compile(r"feats timeline project note", re.I),
    re.compile(r"^[\s\d\}\{\:\=\-\|]+$", re.I),
]

CUTOFF_PATTERNS = re.compile(
    r"(?i)(?:category:\s*[a-zA-Z]|==\s*(?:notable matchups|notes/explanations|references|sources|statistics values|trivia)\s*==|\{\{\s*(?:reflist|discussions|notes))"
)

TEMPLATE_STRIP_PATTERNS = [
    (re.compile(r"(?i)\{\{Border\s*\|(?:[^{}]*?\|)?Content\s*=\s*"), ""),
    (re.compile(r"(?i)\{\{#tag:tabber\s*\|\s*[^=|]+=\s*"), ""),
    (re.compile(r"(?i)\{\{Scroll box[^}]*\}\}"), ""),
    (re.compile(r"<ref[^>]*>.*?</ref>", re.DOTALL | re.I), ""),
    (re.compile(r"<ref[^/>]*/>", re.I), ""),
    (re.compile(r"<[^>]+>"), ""),
    (re.compile(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]"), r"\1"),
    (re.compile(r"[\{\}]+"), ""),
]

def clean_text_field(text: str) -> str:
    """Strips wiki markup and truncates at sludge boundaries."""
    if not text or not isinstance(text, str):
        return ""
    
    # 1. Truncate at category or wiki section footer
    cleaned = CUTOFF_PATTERNS.split(text)[0]
    
    # 2. Strip mediawiki template tags
    for pat, repl in TEMPLATE_STRIP_PATTERNS:
        cleaned = pat.sub(repl, cleaned)
        
    cleaned = cleaned.replace("'''", "").replace("''", "").strip()
    # Normalize excessive whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned

def is_pure_sludge(name: str, desc: str) -> bool:
    """Returns True if the item is purely wiki metadata/sludge with no combat substance."""
    combined = f"{name} {desc}".strip()
    if len(combined) < 4:
        return True
    
    # Check against pure sludge regexes
    for pat in PURE_SLUDGE_PATTERNS:
        if pat.search(name) or pat.search(combined):
            # If name is a sludge trigger (e.g. Category: or {{Border), it's sludge
            if pat.search(name):
                return True
    
    # If more than 3 'Category:' in the text, it is a category dump
    if len(re.findall(r"(?i)category:", combined)) >= 2:
        return True
        
    return False

def sanitize_enriched_items(items: list[dict]) -> tuple[list[dict], int]:
    """Sanitizes a list of EnrichedItem dicts (abilities, weaknesses, equipment, etc.)."""
    cleaned_items = []
    removed_count = 0
    
    for item in items:
        if not isinstance(item, dict):
            continue
            
        name = str(item.get("name") or "")
        desc = str(item.get("description") or "")
        
        # Check for pure sludge
        if is_pure_sludge(name, desc):
            removed_count += 1
            continue
            
        # Clean text
        clean_name = clean_text_field(name)
        clean_desc = clean_text_field(desc)
        
        # If after cleaning, nothing meaningful remains
        if len(clean_name) < 3 and len(clean_desc) < 3:
            removed_count += 1
            continue
            
        item_copy = dict(item)
        item_copy["name"] = clean_name if clean_name else clean_desc[:80]
        item_copy["description"] = clean_desc if clean_desc else clean_name
        
        # Filter tags that are raw categories
        if "tags" in item_copy and isinstance(item_copy["tags"], list):
            item_copy["tags"] = [t for t in item_copy["tags"] if not str(t).lower().startswith("category:")]
            
        cleaned_items.append(item_copy)
        
    return cleaned_items, removed_count

def sanitize_profile_dict(data: dict) -> tuple[dict, int]:
    """Sanitizes an entire character profile dictionary."""
    total_removed = 0
    target_keys = ["abilities", "weaknesses", "equipment", "claims", "resistances", "summons"]
    
    for key in target_keys:
        if key in data and isinstance(data[key], list):
            cleaned, count = sanitize_enriched_items(data[key])
            data[key] = cleaned
            total_removed += count
            
    return data, total_removed

def sanitize_all_yamls() -> dict:
    """Sanitizes all YAML profiles on disk."""
    LOGGER.info(f"Scanning YAML profiles in {PROFILES_DIR}...")
    files = list(PROFILES_DIR.rglob("*.yaml"))
    modified_files = 0
    total_items_removed = 0
    
    for idx, p in enumerate(files):
        try:
            content = p.read_text(encoding="utf-8", errors="ignore")
            data = yaml.safe_load(content)
            if not isinstance(data, dict):
                continue
                
            cleaned_data, removed = sanitize_profile_dict(data)
            if removed > 0:
                p.write_text(yaml.safe_dump(cleaned_data, sort_keys=False, allow_unicode=True), encoding="utf-8")
                modified_files += 1
                total_items_removed += removed
                if removed >= 5:
                    LOGGER.info(f"Purged {removed} sludge items from {p.name}")
        except Exception as e:
            LOGGER.error(f"Error processing {p.name}: {e}")
            
    LOGGER.info(f"YAML Sanitize Complete: Cleaned {modified_files}/{len(files)} files. Removed {total_items_removed} sludge items.")
    return {"total_scanned": len(files), "modified": modified_files, "items_removed": total_items_removed}

async def sanitize_postgres_db():
    """Sanitizes character_profiles in PostgreSQL and synchronizes normalized tables."""
    db_url = os.getenv("DATABASE_URL", "postgresql://battlebot:change_me@postgres:5432/battlebot")
    LOGGER.info(f"Connecting to PostgreSQL: {db_url}...")
    conn = await asyncpg.connect(db_url)
    
    try:
        rows = await conn.fetch("SELECT profile_id, profile_json FROM character_profiles;")
        LOGGER.info(f"Found {len(rows)} profiles in PostgreSQL.")
        
        updated_count = 0
        total_items_removed = 0
        
        for row in rows:
            pid = row["profile_id"]
            try:
                pj = json.loads(row["profile_json"]) if isinstance(row["profile_json"], str) else row["profile_json"]
                cleaned_pj, removed = sanitize_profile_dict(pj)
                
                if removed > 0:
                    await conn.execute(
                        "UPDATE character_profiles SET profile_json = $1, updated_at = NOW() WHERE profile_id = $2",
                        json.dumps(cleaned_pj), pid
                    )
                    updated_count += 1
                    total_items_removed += removed
            except Exception as e:
                LOGGER.error(f"Error updating profile {pid}: {e}")
                
        LOGGER.info(f"PostgreSQL Purge Complete: Updated {updated_count}/{len(rows)} profiles. Removed {total_items_removed} sludge items.")
        
        # Clean relational tables of orphaned or sludge items
        for table in ["profile_abilities", "profile_weaknesses", "profile_equipment"]:
            res = await conn.execute(f"DELETE FROM {table} WHERE name ILIKE '%category:%' OR name ILIKE '{{%' OR description ILIKE '%category:%';")
            LOGGER.info(f"Purged raw sludge rows from {table}: {res}")
            
    finally:
        await conn.close()

def main():
    LOGGER.info("==================================================")
    LOGGER.info(" Nerd Referee Deep Vault Sanitizer Starting")
    LOGGER.info("==================================================")
    yaml_results = sanitize_all_yamls()
    asyncio.run(sanitize_postgres_db())
    LOGGER.info("Deep Vault Sanitization Finished Successfully.")

if __name__ == "__main__":
    main()

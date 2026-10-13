# Nerd Referee Pipeline Audit — 2026-10-12

## Holes Found and Fixed

### 1. Parser Fragmentation (CRITICAL — FIXED)
**Location:** `battlebot/harvest/auto_profile_harvester.py` → `split_listish()`
**Problem:** The live `battlebot/` copy had a naive regex splitter with no paren-depth
tracking. Text like `"Immortality (Types 1 and 3)"` split on commas/newlines inside
parens, producing fragments: `"Immortality (Types 1"` + `"and 3)"`.
**Impact:** 1,390 of 2,893 profiles (48%) had fragmented abilities.
**Fix:** Replaced with paren-aware splitter (depth tracking). Unbalanced parens treated
as literals instead of discarding the field.
**Status:** Fixed in both `src/battlebot/` and `battlebot/` copies. 1,269 profiles
repaired (4,136 clean merges). 839 severely corrupted flagged `needs_reharvest`.

### 2. Fan-Wiki Sources Presented as Canonical (HIGH — FIXED)
**Location:** `build_profile()` in harvester; fight card in `bot/commands/fight.py`
**Problem:** Profiles sourced from VS Battles Wiki (fan powerscaling) showed
"Canonical base; no additional form selected" on fight cards. VS Battles interpretations
are fan-made, not direct canon.
**Fix:** `build_profile()` now sets `variant.variant_type="fan_interpretation"` with
`variant_name="{Wiki} interpretation"` when primary source is vsbattles.fandom.com
or character-stats-and-profiles.fandom.com. Fight card displays the variant name.
**Retroactive:** `scripts/stamp_fan_variants.py` stamps 1,591 existing profiles.
**Status:** Fixed for new harvests. Retroactive stamp in progress.

### 3. Contaminated Fallback Sources (MEDIUM — FIXED)
**Location:** Source search in `providers/mediawiki.py`
**Problem:** When the primary title search failed, fallback sources from wrong characters
were attached (e.g., Sumika Hoshikawa and Yoshi sources in Raphael's profile).
**Impact:** 89+ profiles had wrong-character sources.
**Fix:** `scripts/repair_profiles.py` removes sources where title has zero word overlap
with character name. 27 removed in first pass; broader detection catches more.
**Status:** Repaired. Needs second pass with broadened detector.

### 4. No Retroactive Validation (MEDIUM — ADDRESSED)
**Location:** `profiles/readiness.py` → `assess_readiness()`
**Problem:** The `fragmented_ability_evidence` guardrail was added in policy 2026-09-22,
but 2,893 profiles generated in June 2026 were never re-validated. Guardrails only
applied to new harvests.
**Fix:** Created `scripts/revalidate_profiles.py` to run validation on all existing profiles.
**Status:** Script created. 1,141 profiles have blockers (839 fragmented + contaminated sources).

### 5. Mock Duel Quality Gate Blind Spot (LOW — FIXED)
**Location:** `services/mock_duel_quality_gate.py`
**Problem:** Checked fight output for bad patterns (`{{`, `}}`, `null`) but not for
unbalanced parentheses indicating parser corruption.
**Fix:** Added paren-balance check to `judge_text()`. Flags `unbalanced_parentheses_fragment`.
**Status:** Fixed.

## Holes Found (Not Yet Fixed)

### 6. Franchise Misattribution (MEDIUM)
**Problem:** ~15% of profiles have wrong franchise. Roster categories ("User Requests",
"Crossover Icons") override actual franchise from source. E.g., Raphael (Supernatural)
has franchise="Crossover Icons".
**Impact:** Fight matchmaking and filtering by franchise is unreliable.
**Suggested fix:** Extract franchise from source title parenthetical or infobox;
fall back to roster only if source has no franchise info.

### 7. DB Staleness After YAML Repair (HIGH)
**Problem:** Postgres DB has 2,337 profiles with OLD corrupted data. YAML files were
repaired, but DB was not re-imported.
**Impact:** Live fights use DB data, not YAML. All repairs are invisible until re-import.
**Suggested fix:** Re-import repaired YAMLs to DB, or add DB sync to repair pipeline.

### 8. 839 Profiles Need Re-harvest (HIGH)
**Problem:** Heuristic repair couldn't safely fix severely corrupted profiles.
They're flagged `needs_reharvest` but no re-harvest has run.
**Suggested fix:** Run harvester on flagged profiles with fixed parser.

### 9. No YAML Schema Validation (LOW)
**Problem:** Malformed YAML files (e.g., string instead of dict) cause crashes in
repair/validation scripts. No schema check on harvest output.
**Suggested fix:** Validate against `CharacterProfile` pydantic schema after `build_profile()`.

### 10. Duplicate Profiles (UNKNOWN)
**Problem:** Not checked. Same character may exist in multiple franchise categories.
**Suggested fix:** Deduplicate by normalized name + franchise.

## Pipeline Flow with Fixes

```
Roster → Source Search → Fetch → Parse (FIXED) → Build Profile (FIXED: fan variant)
  → Validate (readiness.py) → [NEW: revalidate_profiles.py for retroactive]
  → Import to DB → Fight (quality gate FIXED)
```

## Recommended Next Steps (Priority Order)
1. Re-import repaired YAMLs to Postgres DB (fixes live fights)
2. Re-harvest 839 flagged profiles with fixed parser
3. Run stamp_fan_variants.py on live (1,591 profiles)
4. Fix franchise attribution
5. Add YAML schema validation to harvester
6. Deduplicate profiles
7. Push all to GitHub

# Codex Pivot Patch

The current scaffold appears to implement the older manual-profile/no-scraping MVP.

Keep what works:
- Dockerfile
- docker-compose.yml
- Python package scaffold
- Postgres
- Redis
- Ollama
- LiteLLM
- Discord slash command structure
- Worker structure
- Profile importer if useful

Now pivot the next phase.

Required changes:
1. Add automated profile harvesting:
   - scripts/auto_profile_harvester.py or src/battlebot/ingest/auto_profile_harvester.py
   - Uses AniList for anime/manga identity.
   - Uses IGDB for game identity if IGDB credentials exist.
   - Uses MediaWiki API for wiki evidence.
   - Saves raw API responses under data/cache.
   - Respects cooldowns, 429s, backoff, and existing cache.

2. Add enriched profile schema:
   - power_scale
   - abilities
   - equipment
   - summons
   - resistances
   - weaknesses
   - win_conditions
   - loss_conditions
   - battlefield_dependencies
   - interaction_tags
   - scope_limitations
   - resource_dependencies
   - sources
   - claims

3. Add generated profile states:
   - roster_stub
   - auto_evidence_profile
   - needs_review
   - approved_override
   - rejected

4. Add profile output folders:
   - profiles/generated
   - profiles/needs_review
   - profiles/approved_overrides
   - profiles/rosters

5. Add controlled enrichment config:
   - config/combat_tags.yaml
   - config/interaction_rules.yaml

6. Add deterministic battle cache:
   - cache key uses sorted character IDs, profile hashes, battle rules hash, prompt version, model name, model settings hash.
   - Batman vs Superman and Superman vs Batman must hit same cache.
   - Store winner by stable character_id.
   - Add refresh:true option to /fight.

7. Discord must render human-readable verdicts.
   - JSON is internal only.
   - Public response includes winner, confidence, verdict type, turning point, why winner wins, how loser can counter, source cards, cached indicator.

Do not implement a public web dashboard.
Do not hardcode secrets.
Do not use PowerShell syntax.
Use WSL/Linux paths only.

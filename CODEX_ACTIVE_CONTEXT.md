# Active Project Context

Project: AI Nerd Fight Decision Bot Discord

Goal:
Build a Dockerized Discord bot that lets users run fights like:

/fight contender_a:"Venom" contender_b:"Iron Man"

The bot should:
1. Resolve both characters.
2. Load their generated YAML combat profiles.
3. Apply battle rules.
4. Check deterministic cache.
5. If no cache hit, send an evidence packet to a local LLM.
6. Validate structured JSON internally.
7. Render an exciting human-readable Discord verdict.
8. Store/cache the result.

Current shell environment:
- WSL/Linux
- Project path:
  /mnt/d/Projects/trae_projects/AI nerd fight decision bot discord
- Do not use PowerShell syntax.
- Do not use Windows D:\ paths in scripts.

Host hardware:
- Ryzen 7 8700F
- 32GB RAM
- RTX 4070 SUPER 12GB
- This machine also runs other AI workloads, so keep model/resource assumptions conservative.

Core stack:
- Python 3.12
- Docker Compose
- Discord slash commands only
- No privileged message_content intent
- Postgres
- Redis
- Ollama
- LiteLLM
- Local LLM referee

Important data strategy:
We are not manually approving thousands of YAMLs.

Use an automated profile harvester:
- AniList for anime/manga identity.
- IGDB for game identity if credentials exist.
- MediaWiki-compatible APIs for wiki evidence, especially VS Battles-style pages.
- Generate YAML profiles automatically.
- Store source URLs, revision IDs, timestamps, and retrieval metadata.
- Respect rate limits and cooldowns.
- Cache raw API responses.
- Never invent feats, powers, claims, or stats.

Profile states:
- roster_stub
- auto_evidence_profile
- needs_review
- approved_override
- rejected

Generated profiles can be battle_eligible only if validation passes.
Weak profiles go to profiles/needs_review.

Character YAML must support deeper combat logic, not just attack/speed/durability.

Required profile sections:
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

Automated enrichment:
- Tags, scope limitations, counters, dependencies, and activation requirements should be generated from source-backed ability/equipment/weakness descriptions.
- Generated tags are metadata only.
- Generated tags cannot create new feats or claims.
- Use deterministic keyword/rule matching first.
- Add local LLM fallback later only if useful.
- Only use tags from controlled config files.

Required config files:
- config/combat_tags.yaml
- config/interaction_rules.yaml

Battle rules:
- Strongest consistent canonical form.
- Both fighters prepared and battle-ready.
- Standard equipment included.
- Standard summons/familiars included.
- No outside help unless explicitly part of standard kit.
- Unsupported fan-wiki claims cannot be decisive alone.
- Missing fields should become null or [].

Verdict style:
The LLM may return JSON internally, but Discord users must see human-readable fight commentary.

Discord result should include:
- headline winner
- confidence
- verdict type
- turning point
- why winner wins
- how loser could counter
- decisive abilities/equipment
- source cards
- cached result indicator

Verdict types:
- clear_win
- conditional_win
- stalemate
- mutual_destruction
- inconclusive
- battlefield_dependent
- first_move_dependent

Caching:
Cache generated fight results deterministically.

Cache key must include:
- sorted character IDs
- both profile hashes
- battle rules hash
- prompt version
- model name
- model settings hash

Batman vs Superman and Superman vs Batman must hit the same cache entry.
Store winner by stable character_id, not character_a/character_b position.
Add /fight refresh:true to bypass cache.

MVP priority:
1. Scaffold Docker/Python app.
2. Implement YAML profile schema and validator.
3. Implement auto_profile_harvester.py script.
4. Implement profile importer into Postgres.
5. Implement /fight command.
6. Implement Redis worker.
7. Implement deterministic cache.
8. Implement local LLM referee call through LiteLLM.
9. Render Discord verdict.
10. Add tests.

Do not build polished scraping dashboards yet.
Do not build a public web UI yet.
Do not add cloud model APIs.
Do not hardcode secrets.

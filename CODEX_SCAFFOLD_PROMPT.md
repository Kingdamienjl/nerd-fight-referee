You are scaffolding a Dockerized Python Discord bot project.

Project root:
./

Read all markdown files in ./docs before writing code. Treat them as product requirements.

Build a minimal but production-shaped MVP for an anime/video game battle arbiter Discord bot.

Hard requirements:
- Python 3.12.
- Discord bot uses slash commands only.
- No privileged message_content intent.
- Use discord.py app_commands.
- Use Postgres as source of truth.
- Use Redis queue for fight jobs.
- Use a separate worker process for inference.
- The Discord bot must not block on model calls.
- Use LiteLLM-compatible OpenAI client interface for model calls.
- Target local Ollama behind LiteLLM.
- Default model alias: referee-default.
- Local model files may live in ./models.
- Docker Compose stack must include postgres, redis, ollama, litellm, bot, worker.

Bot MVP:
- /fight character_a character_b
- Immediately defer response.
- Create a battle_request row.
- Enqueue battle job.
- Return queued status.

Worker MVP:
- Consume Redis queue jobs.
- Load character evidence from Postgres.
- Call local model through LiteLLM.
- Validate JSON response with Pydantic.
- Compute deterministic confidence score outside the LLM.
- Store battle_result in Postgres.

Evidence policy:
- Only DB/wiki source records are admissible.
- Fan-wiki claims can be stored but cannot decide verdict unless corroborated.
- Strongest canonical form/feat only.
- Prepared battle-ready characters.
- Standard equipment and standard summons allowed.
- No hallucinated feats.

Transparency:
- Result must include verdict, confidence score, decisive factors, and source card IDs.

Do not implement scraping yet. Add stubs only.
Do not add cloud APIs.
Do not hardcode Discord token.
Use environment variables and Docker secrets where appropriate.
Use WSL/Linux-compatible paths and commands only.
Do not use PowerShell syntax.
Do not use Windows D:\ paths in scripts.

Create or update:
- docker-compose.yml
- Dockerfile
- pyproject.toml
- config/litellm_config.yaml
- README.md
- src/battlebot/common/config.py
- src/battlebot/common/db.py
- src/battlebot/common/models.py
- src/battlebot/common/queue.py
- src/battlebot/common/llm.py
- src/battlebot/schemas/verdict.py
- src/battlebot/db/schema.sql
- src/battlebot/bot/main.py
- src/battlebot/worker/main.py
- src/battlebot/ingest/import_profile.py
- profiles/example_character.yaml
- tests/

Implementation notes:
- Prefer async Python.
- Use asyncpg or SQLAlchemy async.
- Use redis.asyncio.
- Use Pydantic for strict JSON validation.
- Use httpx for LiteLLM calls.
- Keep code simple and explicit.
- Add TODO markers for future refresh/research mode.
- Add seed/import command for YAML profiles.
- Add tests for:
  - verdict JSON validation
  - fan-wiki uncorroborated decisive claim penalty
  - missing character behavior

First produce a proposed file tree and implementation plan.
After that, implement the scaffold.

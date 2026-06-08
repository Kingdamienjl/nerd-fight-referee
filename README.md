# AI Nerd Fight Decision Bot Discord

Phase 1 scaffold for a Dockerized Python Discord battle bot.

This phase only establishes the project structure, Docker Compose services, package metadata,
configuration placeholders, profile directories, and empty Python entrypoints. The actual bot,
worker, profile harvester, database schema, cache, and LLM referee logic are intentionally left
for later phases.

## Stack Targets

- Python 3.12
- Discord slash commands only
- Postgres
- Redis
- Ollama
- LiteLLM
- Local worker and harvester processes

## Phase 1 Check

```bash
docker compose config
```

The command should render a valid Compose configuration without starting services.

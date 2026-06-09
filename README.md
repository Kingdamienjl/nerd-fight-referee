# AI Nerd Fight Decision Bot Discord

Dockerized Python scaffold for a Discord battle bot.

Current implemented pieces include the automated profile harvester, enriched YAML profile
validation, and a Postgres profile compiler/importer. Discord fight commands, worker battle
execution, battle result caching, and LLM referee calls are intentionally deferred.

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

## Profile Validation And Import

Validate generated profiles:

```bash
.venv/bin/python -m battlebot.ingest.validate_profile profiles/generated
```

Compile generated profiles without writing to Postgres:

```bash
.venv/bin/python -m battlebot.ingest.import_profiles profiles/generated --dry-run
docker compose run --rm profile-importer python -m battlebot.ingest.import_profiles profiles/generated --dry-run
```

Import into Postgres:

```bash
docker compose up -d postgres
docker compose run --rm profile-importer python -m battlebot.ingest.import_profiles profiles/generated
```

Build a non-LLM fight debug packet from imported profiles:

```bash
DBURL="postgresql://battlebot:change_me@127.0.0.1:55432/battlebot"
.venv/bin/python -m battlebot.fight.debug "Son Goku" "Sephiroth" --database-url "$DBURL" --summary
```

The Discord `/fight` command currently uses the same resolver and packet builder, but only returns
debug profile summaries. It does not call an LLM or use the battle result cache yet.

If an existing local Postgres volume was initialized with the old placeholder schema, reset it
before importing:

```bash
docker compose down
docker volume rm ainerdfightdecisionbotdiscord_pgdata
docker compose up -d postgres
```

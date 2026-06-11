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

The Discord `/fight` command currently uses the same resolver and packet builder with a
deterministic smoke judge. It does not call an LLM or use the battle result cache yet.
Discord profile and fight responses intentionally hide raw source URLs, provider IDs, revision
IDs, and local profile paths. Those details remain available in YAML, Postgres, the review UI,
and admin CLIs for validation and repair.

Audit imported profile quality and locate missing characters across local files:

```bash
.venv/bin/python -m battlebot.profiles.audit --database-url "$DBURL" --character "Son Goku"
.venv/bin/python -m battlebot.profiles.locate "Batman"
```

Preferred profile quality overrides live in `profiles/overrides/preferred_profiles.yaml`. These
overrides currently add warnings to fight packets instead of blocking resolution.

## Local Profile Review UI

Run the local review UI separately from the Discord bot:

```bash
.venv/bin/python -m battlebot.review.app --host 127.0.0.1 --port 8090
```

Then open `http://127.0.0.1:8090` and filter to `needs_review`. Batman and Superman can be
inspected from `profiles/needs_review/comic/dc/`, annotated with review notes, approved into
`profiles/generated`, rejected into `profiles/rejected`, or requeued with fix notes.

CLI helpers are available for the same file-backed workflow:

```bash
.venv/bin/python -m battlebot.review.service list --limit 5
.venv/bin/python -m battlebot.review.service inspect profiles/needs_review/comic/dc/batman.yaml
.venv/bin/python -m battlebot.review.service approve profiles/needs_review/comic/dc/batman.yaml
.venv/bin/python -m battlebot.review.service reject profiles/needs_review/comic/dc/batman.yaml --note "wrong page"
```

Practical Batman/Superman repair flow:

```bash
.venv/bin/python -m battlebot.review.service inspect profiles/needs_review/comic/dc/batman.yaml
.venv/bin/python -m battlebot.review.service add-source profiles/needs_review/comic/dc/batman.yaml --title "Batman" --url "https://vsbattles.fandom.com/wiki/Batman" --source-type mediawiki --revision-id "9348088"
.venv/bin/python -m battlebot.review.service set-core profiles/needs_review/comic/dc/batman.yaml --field attack_potency --text "Manual source-backed value" --source-id "batman" --confidence 0.75 --note "Manual review repair"
.venv/bin/python -m battlebot.review.service set-core profiles/needs_review/comic/dc/batman.yaml --field speed --text "Manual source-backed value" --source-id "batman" --confidence 0.75 --note "Manual review repair"
.venv/bin/python -m battlebot.review.service set-core profiles/needs_review/comic/dc/batman.yaml --field durability --text "Manual source-backed value" --source-id "batman" --confidence 0.75 --note "Manual review repair"
.venv/bin/python -m battlebot.review.service add-ability profiles/needs_review/comic/dc/batman.yaml --name "Manual source-backed ability" --description "Describe only what the cited source supports." --source-id "batman" --confidence 0.75
.venv/bin/python -m battlebot.review.service approve profiles/needs_review/comic/dc/batman.yaml
```

Use the source panel in the UI to confirm the source ID and whether each source is used by core
fields, abilities, equipment, or weaknesses before approving.

Batch repair and promote valid `needs_review` profiles:

```bash
.venv/bin/python -m battlebot.review.batch_promote profiles/needs_review --max-profiles 25 --providers vsbattles,character_stats_profiles,superherodb,kaggle_superherodb --debug-dir data/repair_debug
```

Scale the local roster queue toward 1000+ battle-ready profiles:

```bash
.venv/bin/python -m battlebot.rosters.expand --target-total 1500
.venv/bin/python -m battlebot.harvest.auto_profile_harvester --input profiles/rosters/backfill_roster_003_comics.csv --output profiles/generated --needs-review profiles/needs_review --cache-dir data/cache --queue-mode --quiet-skips --skip-needs-review-existing --max-per-cycle 25
.venv/bin/python -m battlebot.review.batch_promote profiles/needs_review --max-profiles 100 --providers vsbattles,character_stats_profiles,superherodb,kaggle_superherodb --debug-dir data/repair_debug
.venv/bin/python -m battlebot.ingest.import_profiles profiles/generated --database-url "$DBURL" --changed-only --import-state-file data/import_state.json
find profiles/generated -name '*.yaml' | wc -l
find profiles/needs_review -name '*.yaml' | wc -l
```

After approving profiles, import changed generated YAML into Postgres:

```bash
DBURL="postgresql://battlebot:change_me@127.0.0.1:55432/battlebot"
.venv/bin/python -m battlebot.ingest.import_profiles profiles/generated --database-url "$DBURL" --changed-only --import-state-file data/import_state.json
```

If an existing local Postgres volume was initialized with the old placeholder schema, reset it
before importing:

```bash
docker compose down
docker volume rm ainerdfightdecisionbotdiscord_pgdata
docker compose up -d postgres
```

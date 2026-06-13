# Nerd Fight Referee Rules

## Environment

- Project runs under WSL.
- Use Linux paths and Bash commands.
- Python environment: `.venv`
- Stack: Python 3.12, discord.py, PostgreSQL, Redis, Ollama, Pydantic, YAML.
- Local database URL:
  `postgresql://battlebot:change_me@127.0.0.1:55432/battlebot`

## Workflow

1. Run `git status --short` before editing.
2. Inspect relevant code before proposing changes.
3. Identify the verified root cause.
4. Make the smallest coherent patch.
5. Do not overwrite unrelated dirty files.
6. Run focused tests before the full suite.
7. Run Ruff after Python edits.
8. Report exact commands and results.
9. Never claim success without command output.
10. Do not commit unless explicitly instructed.

## Protected data

Never expose or commit:

- `secrets/`
- `.env`
- Discord tokens
- `models/*.gguf`
- `.venv/`
- runtime logs and caches

## Profile rules

- Never invent feats, powers, statistics, equipment, or sources.
- Keep source details internal.
- Do not bulk-modify profile corpora without a smoke test.
- Stop bulk processing when failure reasons repeat systematically.

## Current verified state

- 741 generated profiles.
- 1,285 needs-review profiles.
- Current generated corpus imported.
- Discord accepted:
  fight, search, characters, profile, needs_review, repair_queue.
- Current repair blocker:
  enriched candidates are added, but batch promotion still reports
  `missing_mediawiki_title`.
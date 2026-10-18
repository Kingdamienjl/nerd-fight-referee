# Revid Gate — harvester integration

`src/battlebot/harvest/revid_checker.py` implements revision-ID change
detection as a standalone module. It is **not yet wired into the harvest
cycle** because `auto_profile_harvester.py` currently carries uncommitted
parser work from another process (per task constraints it was left
untouched). Apply the patch below once that work lands.

## What the gate does

Before the harvester spends a full MediaWiki content fetch + parse on a
roster row, the gate batch-checks the page's live `revid`
(`prop=revisions&rvprop=ids|timestamp`, 50 titles per request, grouped by
wiki) against `character_profiles.revid`:

- live == stored → **skip** (debug log; counted in `revid_skipped`)
- changed, missing stored revid, or missing live revid → **harvest**
  (counted in `revid_changed`)
- every title actually compared → counted in `revid_checked`

The check bypasses `RawCache` on purpose (the cache has no expiry; a cached
revid would freeze change detection forever). Storing the new revid after a
harvest is already wired: `battlebot.ingest.import_profiles` sets
`character_profiles.revid/rev_timestamp` from the profile's primary
mediawiki source on every import, and `loop.py` runs the importer with
`--changed-only` after each harvest subprocess.

## Patch for `src/battlebot/harvest/auto_profile_harvester.py`

### 1. Extend `QueueCycleSummary` (metrics)

```python
@dataclass
class QueueCycleSummary:
    roster_rows: int = 0
    ...
    revid_checked: int = 0      # ADD
    revid_skipped: int = 0      # ADD
    revid_changed: int = 0      # ADD
```

### 2. Print the metrics in `print_queue_summary`

```python
    print(f"  failed_this_cycle: {summary.failed_this_cycle}")
    print(f"  revid_checked: {summary.revid_checked}")      # ADD
    print(f"  revid_skipped: {summary.revid_skipped}")      # ADD
    print(f"  revid_changed: {summary.revid_changed}")      # ADD
```

### 3. Gate the selected rows in `run_queue_once`

Insert after the `harvester = ProfileHarvester(...)` block, before
`results = []`:

```python
    # --- revid change detection: skip pages whose wiki revision is unchanged ---
    from battlebot.harvest.revid_checker import RevidGate
    revid_gate = RevidGate(harvester.mw)
    to_harvest, _revid_decisions = await revid_gate.filter_rows(
        [row for _index, row in selected],
        output_dir=args.output,
        needs_review_dir=args.needs_review,
    )
    keep_ids = {id(row) for row in to_harvest}
    selected = [(index, row) for index, row in selected if id(row) in keep_ids]
    revid_gate.log_summary()
    # --- end revid gate ---
```

The existing per-row loop, `mark_queue_result`, and the final summary are
unchanged. After the loop, before `print_queue_summary(final_summary)`:

```python
    final_summary.revid_checked = revid_gate.stats["revid_checked"]
    final_summary.revid_skipped = revid_gate.stats["revid_skipped"]
    final_summary.revid_changed = revid_gate.stats["revid_changed"]
```

Notes:

- `filter_rows` already skips rows whose profile YAML exists (no API call
  spent; not counted in revid stats) — `harvest_row`'s own
  `skipped_existing` check remains as a backstop.
- Rows are matched back by object identity (`id()`), so roster ordering and
  the `(index, row)` tuples are preserved exactly.
- `RevidGate` opens its own short-lived DB connections via
  `battlebot.common.db.connect_database`; no connection is held across the
  cycle.
- Optional direct store (if a flow ever harvests without the importer):
  `await revid_gate.store_revid(profile_id, revid, rev_timestamp)`.

## Expected throughput win

Today every re-harvest pass re-fetches full page content for every selected
row (content + optional parse fallback). With the gate, a re-check of N
pages costs ~N/50 lightweight revision queries (e.g. 2,063 profiles ≈ 42
requests, or 1–2 requests per 8-row queue cycle), and only genuinely changed
pages pay the full fetch+parse+LLM cost.

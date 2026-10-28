# Frag-13 — H1/H2/H5 screens + gate 50q + targeted H-profile pass (2026-10-27)

## Verdict
- **Gate 50q: PASS.** 50/50 processed, 0 errors, 0 promoted, 1 recovered
  (berserk-verse, 2 stat merges), audit 0 flagged, manual review clean.
- **H1 screen proven live:** the exact footer sentence that merged in the
  expand run was fetched again from both harley-quinn-post-flashpoint and
  superman-prime-earth sources and dropped with reason
  `footer_instruction` — both profiles now recover nothing from those
  sources. The targeted pass re-ran all 4 H-profiles: 0 recovered,
  0 promoted, 0 errors, 4/4 identity mismatches (same wall as before).
- **Commit: local only (DO NOT PUSH — no push authorized for frag-13).**

## Part 1 — screens shipped (in `fragment_item_reasons`, all sections)
- **H1 `footer_instruction`**: the vsbattles footer sentence merged as a
  weakness ("etc. You can judge a person's power by their feats.").
- **H2 `editor_note_unfinished`**: the Animal Man editor note ("This
  profile is so far from done but i am sleepy (Last issue recorded
  Issue #14 of Animal Man 1988)"), merged as an ability on
  animal-man-rebirth in the expand run. `clean_item_tails` only strips
  "Note:" markers / "before making any changes", so this note escapes it.
- **H5 `episode_hyphen_title`**: episode/chapter label + hyphen + real
  title ("Episode 2 - I'll Give You The Grand Tour", "Episode 7 -
  Don't Do Anything Rash"). G1's label-title rule covers colon/dot
  separators only. Title cap <=6 words (the Episode 2 title has 6);
  title words matched case-insensitively (real titles contain lowercase
  function words, "A New Kind of Fear").
- 6 new guard tests (`ThirteenthGenFrag13ScreenTests`, verbatim + controls).

## Part 2 — calibration (frag13_calib{1,2,3}.py; 8,376 profiles / 174,710 items)
- H1: item-level raw 15, already-caught 14 (template tail), residual 1
  (son-goku-ultra-instinct-sign bare sentence). All 15 genuine footer
  debris. Line level: 53 files / 112 lines (the Oct 26 report's 147/314
  predates drain/intake churn; most occurrences live in
  field_candidates `value:` records, not list items — the screen guards
  the merge path, it does not clean stored files).
- H2: 34 lines corpus-wide, all the same Animal Man note (standalone +
  glued forms); zero legit occurrences in 174,710 items.
- H5: raw 15, already-caught 9 (G1 prefix rule), residual 6, all
  genuine. The omni-man Episode 2/7 titles exist in the corpus only
  glued to following prose (a G7 glue composite, kept); bare-form
  coverage is forward-looking.
- **NO CODE (calibrated, documented in the source):**
  - H3a as-led verbless ("as the scenes depicting..."): residual 74,
    mostly legit ("as well as to Sleep Manipulation", "as a magi",
    "As a robot").
  - H3b participial ("Rhinedottir freely creating life", "and Asmoday
    creating numerous worlds..."): broad rule residual 196 with legit
    FPs ("Incomplete training", "Aura sensing"); verb-blocklist variant
    raw=0 (the target shards do not exist as stored item names — they
    are comma-splits of one long stored claims passage in
    asmoday/ronova), so it is untestable. The asmoday/ronova profiles
    refuse at identity, so the shards cannot re-merge; manual audit
    stays the backstop.
  - H4 bare series name ("The Boys"): residual 75, of which 73 are
    legit equipment ("The Elessar", "The Elendilmir", "The Colt")
    vs 2 "The Boys" — needs franchise context, as frag-12 concluded.
- Screen proof (merge-path filter on the real H texts): **12/12 PASS**
  (frag13_screen_proof.py) — all H-shapes dropped with their H reason,
  all legit controls kept.

## Part 3 — tests
- Guard: **260/260 OK** (254 baseline + 6 new H-tests).
- Full discover: **604 tests, 13F + 11E + 1 skipped** — the failure set
  is IDENTICAL to the expand job's recorded discover log (zero new
  failures). Failures are the pre-existing band (LLM judge, bot fight
  command, review/import service).

## Part 4 — gate 50q (backup 20261027-frag13-gate50q)
- Backup: profiles.tar.gz ~300 MB + db.sql.gz ~20 MB, both gzip-OK;
  progress + cohort copies saved; free 1,824 -> 1,462 MB.
- Prep: cohort rebuilt (1,289); progress keys 1,323 -> 212 after reset
  (1,111 removed: identity_mismatch 872, no_recovery 229, error 8,
  quarantined_expand 2, recovered_KEEP 34, stale untouched 178,
  no_entry_todo 144). Todo 1,255; expected snapshot 1,255 profiles.
  (The quarantined_expand reset is new in frag-13: the H-screens now
  exist, which is the exact condition the expand report set for
  re-queueing those profiles.)
- Gate run (parser-only, HARVEST_LLM_FALLBACK=0, llm_profiles 0):
  50/50 processed, 0 errors, 0 promoted, 1 recovered, 40 identity
  mismatches, 268.6s. Parsers: mwparserfromhell 25, wikitextparser 9.
- The 1 recovered profile: **berserk-verse.yaml** — 2 stat merges from
  "Berserk (Verse)": attack_potency (780-char verse feat chain) +
  speed ("Subsonic (92.0653 m/s) Ganishka's walking"). Audit: 1 audited,
  0 flagged. Manual review: KEPT — the AP value is a verse-page feat
  chain (G7-class glue, coarse-but-correct, sourced, audit-clean);
  mixed outcome (identity_mismatch True on another source), same shape
  as the expand run's kept merges. Not promoted (blockers remain:
  missing_ability, missing_durability, etc.).
- Verdict: **PASS** (zero tolerance held; no bad merges exist to revert).
  Honest note: like the expand gate, this gate is near-vacuous (1 of 50
  recovered) — it proves the screens don't break the pipeline and the
  one merge is clean; the H-proof lives in the targeted pass below.

## Part 5 — targeted H-profile pass (4 profiles, same runner, parser-only)
- Cohort: harley-quinn-post-flashpoint, superman-prime-earth, asmoday,
  ronova (the 4 targeted-8 profiles that are in the cohort and in todo).
  The other 4 are not in the cohort (animal-man-rebirth: remaining
  blockers are unresolved_version_scope, not TARGET_BLOCKERS;
  omni-man files: unclassified_defensive_evidence; son-goku: current
  disk blockers no longer match) — their H-proof rests on unit tests +
  screen proof + calibration, not on a runner pass.
- Result: 4/4 processed, 0 recovered, 0 promoted, 0 errors, 4/4
  identity mismatches, 20.2s, llm_profiles 0.
- **H1 proven live** (from the per-source dropped_items records):
  - harley-quinn (source Harley Quinn (Canon, DC Comics)/Amaterasu,
    guard accepted): weaknesses dropped include "etc. You can judge a
    person's power by their feats." with reason `footer_instruction`.
    In the expand run this exact item MERGED; now it is dropped.
  - superman-prime-earth (source Superman (Canon, DC Comics, Prime
    Earth)/ItsSoba, guard accepted): same item, same reason.
  - Both profiles' other sources guard-rejected (Punchline /
    Prime Earth name_mismatch) → identity_mismatch, recovered=[].
  - All 4 files verified UNCHANGED vs the prep snapshot; the footer
    sentence is absent from both profiles' weaknesses (0 items).
- Asmoday/ronova: the lore passage's comma-split pieces were dropped by
  existing screens (label_fragment on "Chapter VII" / "Act III: Night
  White", prose_sentence_shard on "Like a Dream Upon WakingArchon
  Quest"); the three lore-prose shards themselves did not surface as
  items in this pass. Both refuse at identity on the other sources.
- Targeted audit: audited=0, flagged=0 (vacuous — 0 recovered, nothing
  to audit; stated, not hidden). Standard cohort file restored (1,289).

## Commit (local only)
- **Frag-13 commit** — "Frag-13: H1/H2/H5 screens for expand-gate debris
  (footer instruction, editor note, episode-hyphen title)". One commit:
  auto_repair.py + test_recovery_guard.py + data/frag13_20261027/
  (scripts, calib, logs, manifest, actuals, report). EXCLUDED from the
  commit (kept on disk only, as in the expand job):
  frag13_expected.json (~110 MB), recovery_progress.before_reset.json,
  recovery_cohort.standard.json, .pre-frag13 copies,
  frag12_calib1_decoded.py. (The SHA is in `git log -1`; this report
  was amended into the commit once to fill in its own section.)
- DO NOT PUSH — no push authorized for frag-13. Unpushed: 1.
  Origin/main is d4d25e06 (Part 1 push, verified two ways).

## Pending decisions for Chris
- Push the frag-13 commit? (local only until stamped)
- Corpus cleanup of the H1 files (Oct 26 extent 147 files / 314 occ;
  fresh count 53 files / 112 lines) — separate stamp, NOT done here.
- Mass run stamp (NOT run in this job).

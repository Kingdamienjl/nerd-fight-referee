# Nerd Referee release validation — 2026-09-22

This is a development checkpoint, not a deployed release.

## Completed staging
- Shared web/Discord presentation; actual phases and difficulty, compact linked citations.
- Evidence conditions preserved, selected-model routing corrected, explicit version evidence required.
- Structural readiness separated from factual verification.
- Resistance lists retained as defense, passed separately into model evidence.
- Incomplete generated profiles remain discoverable with readiness warnings.
- 486 discovery targets across 58 franchises; these are not promoted profiles.
- Portable read-only model evaluation command.

## Validation
54 focused tests pass across production readiness, search, profile sheets, harvesting extraction, profile store and fight packets.
Before the final search fix, the broader suite ran 312 tests with 28 failures and 4 errors. The unchanged deployed baseline ran 300 tests with 11 failures and 2 errors. Search regressions are now fixed; remaining changed-contract failures still need review. Do not treat the full suite as passing.

## Model findings
Qwen/Hermes took about 63 seconds and was rejected for grouped citations. Qwen/Qwen took about 45 seconds and passed the syntactic guard, but manual review found unsupported counter interactions. Both returned Unresolved. These results do not establish production-quality reasoning or justify changing the default model. Earlier Mistral 24B evaluation timed out at 150 seconds.

## Release blockers
- Validate existing source profiles and repair resistance/continuity contamination, not just newly harvested profiles.
- Grounding must check claim support; valid citation numbers alone are insufficient.
- Normalize grouped citations and verify rendering without weakening grounding checks.
- Review remaining regression failures and verify browser behavior.
- Audit tool has not changed live readiness flags or queued repairs; verify provider and queue behavior first.
- Verify production source revision, preserve concurrent edits, deploy, test runtime imports and functional outputs, then report live counts.

Production remains on 37590d5996feffe66fc9e9f7e438b45c1c98b0ed. No profile migration or default model switch was applied by this checkpoint.

## Process hardening follow-up
- Numeric citation groups normalize without losing unknown IDs; linked destinations come exclusively from the stored source catalog. This is syntax/reference validation, not factual entailment.
- Added legacy extraction blockers for broken parenthetical clauses, defenses mixed into attacks, and conflicting URLs sharing a source ID.
- Read-only database audit: 2,202 profiles, 40 structurally ready, 2,162 provisional under the new policy. These are not independently source-verified counts. Live flags were not changed.
- Re-extracted Luke Cage (Marvel Comics), stable MediaWiki page ID 2236/revision 9490799, into the isolated repair trial. Four complete offensive/general ability entries; one intact defensive resistance list; no offensive attack tags on that resistance list. Combat-inapplicable durability qualifier preserved. Replayed from cache with networking disabled and asserted these properties.
- Source artifacts and audit remain under /opt/referee/backups/improvements-20260922, outside Git. Repaired profiles are not yet imported into production.
- Ready-looking identities such as Future Trunks (Rebirth) still require stronger franchise/source identity validation. Structural readiness must not be labeled factual verification.

# Harvest and legacy repair deployment — 2026-09-22

Harvest and worker imports now resolve to /app/src, verified in their running containers. The harvester requests batches of eight with a 60-second idle interval; source request pacing remains two seconds. Actual throughput depends on source latency and validation failures. Four expansion rosters add 486 discovery targets, not ready profiles.

The legacy repair timer is enabled for boot and repeats five minutes after a cycle completes. Each cycle previews up to 16 profiles, then promotes only candidates whose preview fingerprint matches. Reviewed profiles are preserved; mismatched or insufficient evidence stays in review. Source identities, schema, readiness, database/file drift and rollback are checked. Original files and database snapshots are archived under backups/legacy-repair-20260922. Harvester and worker pause during a cycle to avoid concurrent profile writes and resume afterward.

Initial live repairs: Levi Ackerman, Mikasa Ackerman, Casca, Retsu Unohana. These repairs correct extraction and pass structural checks; they do not constitute independent verification of every source assertion. The remaining backlog is not declared fixed. No bulk eligibility demotion was applied.

The reported Goku verdict relying on hypothetical time resistance now triggers hypothetical_winning_ability and returns an unresolved verdict with no winner probability. Three regression checks pass, and this result was verified inside the restarted live bot. This targeted guard is not a general proof of source entailment. Existing Discord messages are unchanged.

Validation: 53 focused staging tests passed for the first repair release; 15 targeted checks passed on production before restart; three verdict-guard tests passed. The larger presentation/model revision remains on the development branch and is not included in this deployment.

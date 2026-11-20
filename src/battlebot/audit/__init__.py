"""Read-only audit pipeline for the referee.

Two parts, both flag-only -- nothing here writes to the database, the
fight cache, or any profile:

- cache_audit: re-checks every cached_fight_results row against the
  repo's SB checker, flags rows whose stored profile hashes no longer
  match the live character_profiles hashes (stale), and spot re-judges
  a sample with DeepSeek via the referee-rewrite-together LiteLLM
  group, flagging verdict disagreements.
- profile_audit: ranks fighters by Discord fight count and runs
  assess_readiness + a debris scan over the most-fought profiles,
  because one bad profile poisons every duel it fights.

Entry point: battlebot.audit.runner (``python -m battlebot.audit.runner``).
"""

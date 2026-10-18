-- Migration 001: revision-ID change detection for the profile harvester.
-- Idempotent: safe to run multiple times and on fresh installs.
-- Stores the MediaWiki revision ID the profile was last harvested from so
-- the harvest cycle can skip pages whose live revid is unchanged.

ALTER TABLE character_profiles
    ADD COLUMN IF NOT EXISTS revid bigint;

ALTER TABLE character_profiles
    ADD COLUMN IF NOT EXISTS rev_timestamp timestamptz;

CREATE INDEX IF NOT EXISTS idx_character_profiles_revid
    ON character_profiles(revid);

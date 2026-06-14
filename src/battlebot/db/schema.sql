CREATE TABLE IF NOT EXISTS characters (
    id text PRIMARY KEY,
    canonical_name text NOT NULL,
    franchise text NOT NULL,
    category text NOT NULL,
    created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS character_aliases (
    character_id text REFERENCES characters(id) ON DELETE CASCADE,
    alias text NOT NULL,
    normalized_alias text NOT NULL,
    PRIMARY KEY (character_id, normalized_alias)
);

CREATE TABLE IF NOT EXISTS character_profiles (
    profile_id text PRIMARY KEY,
    character_id text REFERENCES characters(id) ON DELETE CASCADE,
    profile_type text NOT NULL,
    status text NOT NULL,
    battle_eligible boolean NOT NULL,
    profile_hash text NOT NULL,
    profile_path text,
    profile_json jsonb NOT NULL,
    generated_at timestamptz,
    imported_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS profile_sources (
    source_id text NOT NULL,
    profile_id text REFERENCES character_profiles(profile_id) ON DELETE CASCADE,
    title text,
    url text,
    source_type text,
    license text,
    page_id text,
    revision_id text,
    revision_timestamp text,
    retrieved_at text,
    admissible boolean DEFAULT true,
    PRIMARY KEY (profile_id, source_id)
);

CREATE TABLE IF NOT EXISTS profile_claims (
    claim_id text NOT NULL,
    profile_id text REFERENCES character_profiles(profile_id) ON DELETE CASCADE,
    axis text NOT NULL,
    claim_text text NOT NULL,
    source_ids jsonb NOT NULL DEFAULT '[]',
    decisive boolean DEFAULT false,
    confidence numeric DEFAULT 0,
    policy_flags jsonb NOT NULL DEFAULT '[]',
    PRIMARY KEY (profile_id, claim_id)
);

CREATE TABLE IF NOT EXISTS profile_power_scale (
    profile_id text REFERENCES character_profiles(profile_id) ON DELETE CASCADE,
    axis text NOT NULL,
    text text,
    source_ids jsonb NOT NULL DEFAULT '[]',
    confidence numeric DEFAULT 0,
    PRIMARY KEY (profile_id, axis)
);

CREATE TABLE IF NOT EXISTS profile_abilities (
    ability_id text NOT NULL,
    profile_id text REFERENCES character_profiles(profile_id) ON DELETE CASCADE,
    name text,
    description text,
    source_ids jsonb NOT NULL DEFAULT '[]',
    tags jsonb NOT NULL DEFAULT '[]',
    targets jsonb NOT NULL DEFAULT '[]',
    activation_requirements jsonb NOT NULL DEFAULT '[]',
    counters jsonb NOT NULL DEFAULT '[]',
    resource_dependencies jsonb NOT NULL DEFAULT '[]',
    scope_limitations jsonb NOT NULL DEFAULT '{}',
    enrichment jsonb NOT NULL DEFAULT '{}',
    confidence numeric DEFAULT 0,
    PRIMARY KEY (profile_id, ability_id)
);

CREATE TABLE IF NOT EXISTS profile_equipment (
    equipment_id text NOT NULL,
    profile_id text REFERENCES character_profiles(profile_id) ON DELETE CASCADE,
    name text,
    description text,
    function text,
    source_ids jsonb NOT NULL DEFAULT '[]',
    tags jsonb NOT NULL DEFAULT '[]',
    targets jsonb NOT NULL DEFAULT '[]',
    activation_requirements jsonb NOT NULL DEFAULT '[]',
    counters jsonb NOT NULL DEFAULT '[]',
    resource_dependencies jsonb NOT NULL DEFAULT '[]',
    scope_limitations jsonb NOT NULL DEFAULT '{}',
    enrichment jsonb NOT NULL DEFAULT '{}',
    confidence numeric DEFAULT 0,
    PRIMARY KEY (profile_id, equipment_id)
);

CREATE TABLE IF NOT EXISTS profile_weaknesses (
    weakness_id text NOT NULL,
    profile_id text REFERENCES character_profiles(profile_id) ON DELETE CASCADE,
    description text,
    source_ids jsonb NOT NULL DEFAULT '[]',
    tags jsonb NOT NULL DEFAULT '[]',
    counters jsonb NOT NULL DEFAULT '[]',
    resource_dependencies jsonb NOT NULL DEFAULT '[]',
    scope_limitations jsonb NOT NULL DEFAULT '{}',
    enrichment jsonb NOT NULL DEFAULT '{}',
    confidence numeric DEFAULT 0,
    PRIMARY KEY (profile_id, weakness_id)
);

CREATE TABLE IF NOT EXISTS profile_jobs (
    id bigserial PRIMARY KEY,
    profile_path text UNIQUE NOT NULL,
    target text NOT NULL,
    providers text NOT NULL,
    status text NOT NULL DEFAULT 'pending',
    priority integer NOT NULL DEFAULT 100,
    attempts integer NOT NULL DEFAULT 0,
    max_attempts integer NOT NULL DEFAULT 3,
    next_attempt_at timestamptz NOT NULL DEFAULT now(),
    locked_at timestamptz,
    worker_id text,
    last_error text,
    last_summary jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_characters_canonical_name ON characters(canonical_name);
CREATE INDEX IF NOT EXISTS idx_characters_franchise ON characters(franchise);
CREATE INDEX IF NOT EXISTS idx_character_aliases_normalized_alias
    ON character_aliases(normalized_alias);
CREATE INDEX IF NOT EXISTS idx_character_profiles_character_id
    ON character_profiles(character_id);
CREATE INDEX IF NOT EXISTS idx_character_profiles_battle_eligible
    ON character_profiles(battle_eligible);
CREATE INDEX IF NOT EXISTS idx_character_profiles_profile_hash
    ON character_profiles(profile_hash);
CREATE INDEX IF NOT EXISTS idx_profile_sources_revision_id ON profile_sources(revision_id);
CREATE INDEX IF NOT EXISTS idx_profile_power_scale_axis ON profile_power_scale(axis);
CREATE INDEX IF NOT EXISTS idx_profile_abilities_tags
    ON profile_abilities USING GIN (tags);
CREATE INDEX IF NOT EXISTS idx_profile_equipment_tags
    ON profile_equipment USING GIN (tags);
CREATE INDEX IF NOT EXISTS idx_profile_weaknesses_tags
    ON profile_weaknesses USING GIN (tags);
CREATE INDEX IF NOT EXISTS idx_character_profiles_profile_json
    ON character_profiles USING GIN (profile_json);
CREATE INDEX IF NOT EXISTS idx_profile_jobs_claim
    ON profile_jobs (status, next_attempt_at, priority, id);

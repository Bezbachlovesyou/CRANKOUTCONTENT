-- Apply once to a new Postgres database before starting settings editing.
CREATE TABLE IF NOT EXISTS copilot_settings (
    owner_id BIGINT PRIMARY KEY,
    values_json JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Each format revision is immutable; new versions are inserted separately.
CREATE TABLE IF NOT EXISTS content_formats (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    owner_id BIGINT NOT NULL,
    name TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version > 0),
    description TEXT NOT NULL,
    active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (owner_id, name, version),
    UNIQUE (owner_id, id)
);

CREATE TABLE IF NOT EXISTS content_plan (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    owner_id BIGINT NOT NULL,
    format_id BIGINT NOT NULL,
    body TEXT NOT NULL,
    normalized_hash TEXT NOT NULL,
    scheduled_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'approved', 'scheduled', 'publishing', 'published', 'failed', 'cancelled')),
    platform_post_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    FOREIGN KEY (owner_id, format_id) REFERENCES content_formats(owner_id, id),
    UNIQUE (owner_id, normalized_hash)
);
CREATE INDEX IF NOT EXISTS content_plan_schedule ON content_plan(owner_id, status, scheduled_at);

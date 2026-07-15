-- ============================================================================
-- JobPilot Platform — canonical PostgreSQL 16 schema (Phase 2)
-- Becomes Alembic migration 0001 in Phase 4. Requires the pgvector extension.
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;        -- gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS citext;          -- case-insensitive emails/names

-- ---------------------------------------------------------------------------
-- Enumerated types
-- ---------------------------------------------------------------------------
CREATE TYPE user_role            AS ENUM ('USER', 'ADMIN');
CREATE TYPE compliance_mode      AS ENUM ('OFFICIAL_API', 'PUBLIC_FEED', 'SEARCH_LINK',
                                          'USER_AUTHORIZED_AUTOMATION');
CREATE TYPE employment_type      AS ENUM ('FULL_TIME', 'PART_TIME', 'CONTRACT', 'INTERNSHIP',
                                          'TEMPORARY', 'UNKNOWN');
CREATE TYPE contract_arrangement AS ENUM ('W2', 'C1099', 'C2C', 'UNSPECIFIED');
CREATE TYPE workplace_type       AS ENUM ('REMOTE', 'HYBRID', 'ONSITE', 'UNKNOWN');
CREATE TYPE sponsorship_flag     AS ENUM ('SPONSOR_FRIENDLY', 'NO_SPONSOR', 'UNKNOWN');
CREATE TYPE seniority_level      AS ENUM ('ENTRY', 'MID', 'SENIOR', 'LEAD', 'PRINCIPAL', 'UNKNOWN');
CREATE TYPE job_status           AS ENUM ('ACTIVE', 'CLOSED', 'EXPIRED', 'DUPLICATE');
CREATE TYPE application_status   AS ENUM ('SAVED', 'INTERESTED', 'RESUME_GENERATED', 'APPLIED',
                                          'RECRUITER_CONTACTED', 'OA_RECEIVED',
                                          'INTERVIEW_SCHEDULED', 'REJECTED', 'OFFER',
                                          'ACCEPTED', 'DECLINED');
CREATE TYPE apply_method         AS ENUM ('MANUAL', 'API', 'AUTOMATED_FORM', 'EMAIL', 'REFERRAL');
CREATE TYPE actor_type           AS ENUM ('USER', 'SYSTEM', 'ASSISTANT');
CREATE TYPE document_type        AS ENUM ('TAILORED_RESUME', 'COVER_LETTER', 'RECRUITER_EMAIL',
                                          'LINKEDIN_MESSAGE', 'COLD_EMAIL');
CREATE TYPE extraction_method    AS ENUM ('LLM', 'HEURISTIC', 'MIXED');
CREATE TYPE message_role         AS ENUM ('USER', 'ASSISTANT', 'SYSTEM', 'TOOL');
CREATE TYPE notification_channel AS ENUM ('EMAIL', 'SLACK', 'DISCORD');
CREATE TYPE delivery_status      AS ENUM ('PENDING', 'SENT', 'FAILED', 'SKIPPED');
CREATE TYPE run_status           AS ENUM ('RUNNING', 'SUCCESS', 'FAILED', 'PARTIAL');

-- updated_at maintenance
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END $$ LANGUAGE plpgsql;

-- ===========================================================================
-- IDENTITY
-- ===========================================================================
CREATE TABLE users (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email         citext NOT NULL UNIQUE,
    password_hash text,                          -- NULL for OAuth-only accounts
    full_name     text NOT NULL,
    role          user_role NOT NULL DEFAULT 'USER',
    is_active     boolean NOT NULL DEFAULT true,
    email_verified_at timestamptz,
    timezone      text NOT NULL DEFAULT 'America/Chicago',
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE oauth_accounts (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider         text NOT NULL,              -- 'google' | 'github'
    provider_user_id text NOT NULL,
    created_at       timestamptz NOT NULL DEFAULT now(),
    UNIQUE (provider, provider_user_id)
);

CREATE TABLE refresh_tokens (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash   text NOT NULL UNIQUE,
    expires_at   timestamptz NOT NULL,
    revoked_at   timestamptz,
    replaced_by  uuid REFERENCES refresh_tokens(id),
    created_ip   inet,
    user_agent   text,
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_refresh_tokens_user ON refresh_tokens (user_id) WHERE revoked_at IS NULL;

CREATE TABLE password_reset_tokens (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash text NOT NULL UNIQUE,
    expires_at timestamptz NOT NULL,
    used_at    timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE audit_events (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id     uuid REFERENCES users(id) ON DELETE SET NULL,
    actor       actor_type NOT NULL DEFAULT 'USER',
    event_type  text NOT NULL,                   -- 'auth.login', 'apply.submitted', ...
    entity_type text,
    entity_id   text,
    detail      jsonb NOT NULL DEFAULT '{}',
    ip          inet,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_audit_events_user_time ON audit_events (user_id, created_at DESC);
CREATE INDEX ix_audit_events_type_time ON audit_events (event_type, created_at DESC);

-- ===========================================================================
-- PROFILE
-- ===========================================================================
CREATE TABLE preferences (
    user_id               uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    desired_titles        text[] NOT NULL DEFAULT '{}',
    employment_types      employment_type[] NOT NULL DEFAULT '{FULL_TIME}',
    contract_arrangements contract_arrangement[] NOT NULL DEFAULT '{}',
    workplace_types       workplace_type[] NOT NULL DEFAULT '{}',
    locations             jsonb NOT NULL DEFAULT '[]',   -- [{city,state,country,radius_mi}]
    countries             text[] NOT NULL DEFAULT '{US}',
    seniority             seniority_level,
    years_experience      numeric(4,1),
    visa_status           text,
    work_authorization    text,
    needs_sponsorship     boolean NOT NULL DEFAULT false,
    open_to_staffing      boolean NOT NULL DEFAULT true,
    salary_min            integer,
    salary_max            integer,
    salary_currency       char(3) NOT NULL DEFAULT 'USD',
    availability_date     date,
    notice_period_days    integer,
    auto_apply_enabled    boolean NOT NULL DEFAULT false,
    auto_apply_min_score  numeric(5,2) NOT NULL DEFAULT 70,
    auto_apply_daily_cap  integer NOT NULL DEFAULT 25,
    updated_at            timestamptz NOT NULL DEFAULT now()
);
CREATE TRIGGER trg_preferences_updated BEFORE UPDATE ON preferences
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE skills (
    id       integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name     citext NOT NULL UNIQUE,
    category text                                 -- language | framework | cloud | ...
);

CREATE TABLE user_skills (
    user_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    skill_id    integer NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
    years       numeric(4,1),
    proficiency smallint CHECK (proficiency BETWEEN 1 AND 5),
    PRIMARY KEY (user_id, skill_id)
);

CREATE TABLE resumes (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name        text NOT NULL,
    is_default  boolean NOT NULL DEFAULT false,
    file_path   text,
    mime_type   text,
    raw_text    text,
    structured  jsonb,                            -- parsed sections/experience/skills
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, name)
);
CREATE UNIQUE INDEX ux_resumes_one_default ON resumes (user_id) WHERE is_default;
CREATE TRIGGER trg_resumes_updated BEFORE UPDATE ON resumes
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE resume_chunks (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    resume_id       uuid NOT NULL REFERENCES resumes(id) ON DELETE CASCADE,
    section         text NOT NULL,                -- summary | experience | skills | ...
    content         text NOT NULL,
    embedding       vector(768),
    embedding_model text,
    created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_resume_chunks_resume ON resume_chunks (resume_id);
CREATE INDEX ix_resume_chunks_embedding ON resume_chunks
    USING hnsw (embedding vector_cosine_ops);

CREATE TABLE notification_settings (
    user_id             uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    email_enabled       boolean NOT NULL DEFAULT true,
    daily_report_hour   smallint NOT NULL DEFAULT 21 CHECK (daily_report_hour BETWEEN 0 AND 23),
    slack_webhook_enc   text,                     -- AES-GCM encrypted
    discord_webhook_enc text,
    updated_at          timestamptz NOT NULL DEFAULT now()
);
CREATE TRIGGER trg_notification_settings_updated BEFORE UPDATE ON notification_settings
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ===========================================================================
-- CATALOG
-- ===========================================================================
CREATE TABLE companies (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name             text NOT NULL,
    normalized_name  citext NOT NULL UNIQUE,      -- lowercased, suffix-stripped
    website          text,
    industry         text,
    size_range       text,
    is_staffing_firm boolean NOT NULL DEFAULT false,
    ats_type         text,                        -- greenhouse | lever | ashby | ...
    careers_url      text,
    created_at       timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE recruiters (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id    uuid REFERENCES companies(id) ON DELETE SET NULL,
    discovered_by uuid REFERENCES users(id) ON DELETE SET NULL,
    name          text,
    email         citext,
    linkedin_url  text,
    phone         text,
    source        text,                           -- 'jd_extraction' | 'manual' | ...
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_recruiters_company ON recruiters (company_id);
CREATE UNIQUE INDEX ux_recruiters_email ON recruiters (email) WHERE email IS NOT NULL;

CREATE TABLE connector_settings (
    id                 integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    connector_id       text NOT NULL UNIQUE,      -- 'greenhouse', 'dice', 'linkedin_links'
    display_name       text NOT NULL,
    compliance_mode    compliance_mode NOT NULL,
    enabled            boolean NOT NULL DEFAULT true,
    rate_limit_per_min integer NOT NULL DEFAULT 30,
    config             jsonb NOT NULL DEFAULT '{}',  -- API keys encrypted at field level
    updated_by         uuid REFERENCES users(id) ON DELETE SET NULL,
    updated_at         timestamptz NOT NULL DEFAULT now()
);
CREATE TRIGGER trg_connector_settings_updated BEFORE UPDATE ON connector_settings
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE company_watchlist (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      uuid REFERENCES users(id) ON DELETE CASCADE,  -- NULL = global seed
    company_id   uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    connector_id text NOT NULL REFERENCES connector_settings(connector_id),
    config       jsonb NOT NULL DEFAULT '{}',     -- {slug: "teksystems"} etc.
    enabled      boolean NOT NULL DEFAULT true,
    created_at   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, company_id, connector_id)
);

-- ===========================================================================
-- JOBS
-- ===========================================================================
CREATE TABLE jobs (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    connector_id         text NOT NULL REFERENCES connector_settings(connector_id),
    external_id          text,
    company_id           uuid REFERENCES companies(id) ON DELETE SET NULL,
    title                text NOT NULL,
    description_md       text,
    url                  text NOT NULL,
    dedupe_hash          text NOT NULL UNIQUE,    -- sha1(canonical url | title+company)
    location_text        text,
    city                 text,
    state                text,
    country              char(2),
    workplace            workplace_type NOT NULL DEFAULT 'UNKNOWN',
    employment           employment_type NOT NULL DEFAULT 'UNKNOWN',
    arrangement          contract_arrangement NOT NULL DEFAULT 'UNSPECIFIED',
    salary_min           integer,
    salary_max           integer,
    salary_currency      char(3),
    salary_period        text,                    -- yearly | hourly
    posted_at            timestamptz,
    first_seen_at        timestamptz NOT NULL DEFAULT now(),
    last_seen_at         timestamptz NOT NULL DEFAULT now(),
    status               job_status NOT NULL DEFAULT 'ACTIVE',
    raw                  jsonb NOT NULL DEFAULT '{}',
    UNIQUE (connector_id, external_id)
);
CREATE INDEX ix_jobs_posted ON jobs (posted_at DESC) WHERE status = 'ACTIVE';
CREATE INDEX ix_jobs_company ON jobs (company_id);
CREATE INDEX ix_jobs_title_trgm ON jobs USING gin (to_tsvector('english', title));

CREATE TABLE job_extractions (
    job_id            uuid PRIMARY KEY REFERENCES jobs(id) ON DELETE CASCADE,
    skills            text[] NOT NULL DEFAULT '{}',
    tech_stack        text[] NOT NULL DEFAULT '{}',
    responsibilities  text[],
    benefits          text[],
    sponsorship       sponsorship_flag NOT NULL DEFAULT 'UNKNOWN',
    seniority         seniority_level NOT NULL DEFAULT 'UNKNOWN',
    recruiter_name    text,
    recruiter_contact text,
    method            extraction_method NOT NULL,
    model             text,
    created_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_job_extractions_skills ON job_extractions USING gin (skills);

CREATE TABLE job_embeddings (
    job_id          uuid PRIMARY KEY REFERENCES jobs(id) ON DELETE CASCADE,
    embedding       vector(768) NOT NULL,
    embedding_model text NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_job_embeddings_hnsw ON job_embeddings
    USING hnsw (embedding vector_cosine_ops);

CREATE TABLE match_scores (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id        uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    job_id         uuid NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    resume_id      uuid NOT NULL REFERENCES resumes(id) ON DELETE CASCADE,
    overall        numeric(5,2) NOT NULL,          -- 0..100
    ats_pct        numeric(5,2),
    resume_pct     numeric(5,2),
    salary_score   numeric(5,2),
    location_score numeric(5,2),
    visa_score     numeric(5,2),
    skill_gap      jsonb NOT NULL DEFAULT '[]',    -- [{skill, required, have}]
    reasoning      text,
    model          text,
    created_at     timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, job_id, resume_id)
);
CREATE INDEX ix_match_scores_user_overall ON match_scores (user_id, overall DESC);

-- ===========================================================================
-- TRACKER
-- ===========================================================================
CREATE TABLE applications (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id        uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    job_id         uuid NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    resume_id      uuid REFERENCES resumes(id) ON DELETE SET NULL,
    status         application_status NOT NULL DEFAULT 'SAVED',
    method         apply_method,
    applied_at     timestamptz,
    deadline_at    timestamptz,
    next_action_at timestamptz,
    salary_offered integer,
    notes          text,
    deleted_at     timestamptz,                    -- soft delete
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, job_id)
);
CREATE INDEX ix_applications_user_status ON applications (user_id, status)
    WHERE deleted_at IS NULL;
CREATE INDEX ix_applications_next_action ON applications (user_id, next_action_at)
    WHERE next_action_at IS NOT NULL AND deleted_at IS NULL;
CREATE TRIGGER trg_applications_updated BEFORE UPDATE ON applications
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE application_events (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    application_id uuid NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    from_status    application_status,
    to_status      application_status NOT NULL,
    actor          actor_type NOT NULL DEFAULT 'USER',
    note           text,
    created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_application_events_app ON application_events (application_id, created_at);

CREATE TABLE application_contacts (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    application_id uuid NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    recruiter_id   uuid REFERENCES recruiters(id) ON DELETE SET NULL,
    role           text,                           -- recruiter | hiring manager | referral
    email          citext,
    notes          text,
    created_at     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE generated_documents (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id        uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    job_id         uuid REFERENCES jobs(id) ON DELETE SET NULL,
    application_id uuid REFERENCES applications(id) ON DELETE SET NULL,
    doc_type       document_type NOT NULL,
    content_md     text,
    file_path      text,                           -- rendered docx/pdf when applicable
    source_resume  uuid REFERENCES resumes(id) ON DELETE SET NULL,
    prompt_key     text,
    prompt_version integer,
    model          text,
    created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_generated_documents_user ON generated_documents (user_id, created_at DESC);

-- ===========================================================================
-- AI
-- ===========================================================================
CREATE TABLE prompts (
    id               integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    key              text NOT NULL,               -- 'job_extraction', 'resume_tailor', ...
    version          integer NOT NULL,
    template         text NOT NULL,
    variables_schema jsonb NOT NULL DEFAULT '{}',
    active           boolean NOT NULL DEFAULT true,
    created_by       uuid REFERENCES users(id) ON DELETE SET NULL,
    created_at       timestamptz NOT NULL DEFAULT now(),
    UNIQUE (key, version)
);
CREATE UNIQUE INDEX ux_prompts_one_active ON prompts (key) WHERE active;

CREATE TABLE ai_invocations (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id     uuid REFERENCES users(id) ON DELETE SET NULL,
    provider    text NOT NULL,
    model       text NOT NULL,
    prompt_key  text,
    tokens_in   integer,
    tokens_out  integer,
    latency_ms  integer,
    status      text NOT NULL,                    -- ok | error | fallback
    error       text,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_ai_invocations_user_time ON ai_invocations (user_id, created_at DESC);

CREATE TABLE ai_conversations (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title      text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TRIGGER trg_ai_conversations_updated BEFORE UPDATE ON ai_conversations
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE ai_messages (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id uuid NOT NULL REFERENCES ai_conversations(id) ON DELETE CASCADE,
    role            message_role NOT NULL,
    content         text NOT NULL,
    tool_calls      jsonb,
    embedding       vector(768),
    embedding_model text,
    created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_ai_messages_conv ON ai_messages (conversation_id, created_at);
CREATE INDEX ix_ai_messages_embedding ON ai_messages
    USING hnsw (embedding vector_cosine_ops);

-- ===========================================================================
-- OPS
-- ===========================================================================
CREATE TABLE notifications (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    channel    notification_channel NOT NULL,
    template   text NOT NULL,                     -- 'daily_report', 'weekly_analytics'
    subject    text,
    payload    jsonb NOT NULL DEFAULT '{}',
    status     delivery_status NOT NULL DEFAULT 'PENDING',
    error      text,
    sent_at    timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_notifications_user_time ON notifications (user_id, created_at DESC);

CREATE TABLE scheduled_tasks (
    id          integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    key         text NOT NULL UNIQUE,             -- 'ingest.full', 'report.daily'
    cron        text NOT NULL,
    timezone    text NOT NULL DEFAULT 'America/Chicago',
    enabled     boolean NOT NULL DEFAULT true,
    description text,
    updated_at  timestamptz NOT NULL DEFAULT now()
);
CREATE TRIGGER trg_scheduled_tasks_updated BEFORE UPDATE ON scheduled_tasks
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE scheduled_runs (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    task_key    text NOT NULL REFERENCES scheduled_tasks(key) ON DELETE CASCADE,
    status      run_status NOT NULL DEFAULT 'RUNNING',
    started_at  timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    stats       jsonb NOT NULL DEFAULT '{}',      -- {scraped: n, applied: n, ...}
    error       text
);
CREATE INDEX ix_scheduled_runs_task_time ON scheduled_runs (task_key, started_at DESC);

CREATE TABLE analytics_snapshots (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    snapshot_date date NOT NULL,
    metrics       jsonb NOT NULL,                 -- funnel, distributions, trends
    created_at    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, snapshot_date)
);

-- ===========================================================================
-- Seed data (connectors + default schedules)
-- ===========================================================================
INSERT INTO connector_settings (connector_id, display_name, compliance_mode, rate_limit_per_min) VALUES
    ('greenhouse',      'Greenhouse Job Board API',   'OFFICIAL_API', 60),
    ('lever',           'Lever Postings API',         'OFFICIAL_API', 60),
    ('ashby',           'Ashby Posting API',          'OFFICIAL_API', 60),
    ('smartrecruiters', 'SmartRecruiters Posting API','OFFICIAL_API', 60),
    ('adzuna',          'Adzuna API',                 'OFFICIAL_API', 25),
    ('jooble',          'Jooble API',                 'OFFICIAL_API', 25),
    ('usajobs',         'USAJOBS API',                'OFFICIAL_API', 30),
    ('dice',            'Dice public search feed',    'PUBLIC_FEED',  20),
    ('remoteok',        'RemoteOK public API',        'PUBLIC_FEED',  10),
    ('remotive',        'Remotive public API',        'PUBLIC_FEED',  10),
    ('workday',         'Workday tenant feeds',       'PUBLIC_FEED',  20),
    ('careers_page',    'Company careers pages',      'PUBLIC_FEED',  10),
    ('jobspy',          'JobSpy aggregation',         'PUBLIC_FEED',  10),
    ('linkedin_links',  'LinkedIn search links',      'SEARCH_LINK',  0),
    ('indeed_links',    'Indeed search links',        'SEARCH_LINK',  0),
    ('monster_links',   'Monster search links',       'SEARCH_LINK',  0),
    ('zip_links',       'ZipRecruiter search links',  'SEARCH_LINK',  0),
    ('ats_autofill',    'ATS form auto-apply',        'USER_AUTHORIZED_AUTOMATION', 2);

INSERT INTO scheduled_tasks (key, cron, timezone, description) VALUES
    ('ingest.full',        '0 6 * * *',      'America/Chicago', 'Full daily ingestion + rank + recommendations'),
    ('ingest.incremental', '0 8-18/2 * * *', 'America/Chicago', 'Incremental new-posting sweep'),
    ('report.daily',       '0 21 * * *',     'America/Chicago', 'Daily summary email + dashboard refresh'),
    ('analytics.weekly',   '0 18 * * 0',     'America/Chicago', 'Weekly analytics + resume/skill recommendations');

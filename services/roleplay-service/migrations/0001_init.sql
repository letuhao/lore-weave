-- roleplay-service initial schema (spec §3 / detailed-design §4).
--
-- Three tables on the platform plane (single owner-scoped pool):
--   roleplay_scripts — authored scripts (System + Per-user; book tier is
--                      forward-schema, nullable, unused in v1).
--   rp_sessions      — one row per acting session (session_id = the
--                      chat_sessions id created in chat-service).
--   rp_memory        — the durable, bounded per-actor memory: frozen `charter`
--                      + mutable `state` (charter-anchor only in v1).
--
-- Tenancy (CLAUDE.md user-boundary rules): System rows have owner_user_id IS
-- NULL and are admin-seeded/read-only to users; Per-user rows are owner-scoped.
-- Uniqueness is per-tier via two partial unique indexes (the prior single-index
-- gap fix): System unique-by-code; Per-user unique-by (owner, book, code) with
-- NULLS NOT DISTINCT so a NULL book_id still collides (PG15+).

CREATE TABLE roleplay_scripts (
    script_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id  UUID,                       -- NULL => System tier
    tier           VARCHAR(10)  NOT NULL DEFAULT 'user',
    code           VARCHAR(100) NOT NULL,
    name           VARCHAR(255) NOT NULL,
    description    TEXT,
    system_prompt  TEXT         NOT NULL,
    model_source   VARCHAR(20),                -- e.g. 'user_model' (resolved per provider-registry)
    model_ref      UUID,                       -- user_model_id; NULL => caller must override at /start
    rubric         JSONB,                      -- debrief rubric (chat-service M6 /evaluate consumes)
    scenario       JSONB        NOT NULL DEFAULT '{}',  -- premise/beats/phases/… (charter superset)
    genre          VARCHAR(40)  NOT NULL DEFAULT 'roleplay',
    book_id        UUID,                       -- forward-schema (book tier), unused in v1
    reality_id     UUID,                       -- forward-schema (game plane); NULL = general reality
    attachment_key VARCHAR(512),               -- forward-schema (file attach), unused in v1
    is_active      BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT rp_tier_owner_chk CHECK (
        (tier = 'system' AND owner_user_id IS NULL) OR
        (tier = 'user'   AND owner_user_id IS NOT NULL AND book_id IS NULL) OR
        (tier = 'book'   AND owner_user_id IS NOT NULL AND book_id IS NOT NULL)
    )
);

-- System tier: unique by code across the (single, NULL-owner) System namespace.
CREATE UNIQUE INDEX uq_rp_system_code
    ON roleplay_scripts (code)
    WHERE owner_user_id IS NULL;

-- Per-user / Per-book tier: unique by (owner, book, code). NULLS NOT DISTINCT so
-- a Per-user row (book_id NULL) still collides on (owner, code) — the per-book
-- index gap fix.
CREATE UNIQUE INDEX uq_rp_user_code
    ON roleplay_scripts (owner_user_id, book_id, code)
    NULLS NOT DISTINCT
    WHERE owner_user_id IS NOT NULL;

CREATE TABLE rp_sessions (
    session_id        UUID PRIMARY KEY,        -- = chat_sessions.session_id (created chat-side first, EC-3)
    script_id         UUID NOT NULL REFERENCES roleplay_scripts (script_id),
    owner_user_id     UUID NOT NULL,
    reality_id        UUID,                     -- forward-schema; NULL = general reality
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    debrief_output_id UUID                      -- the chat-service scorecard ChatOutput id (set after debrief)
);

CREATE INDEX ix_rp_sessions_owner ON rp_sessions (owner_user_id);

CREATE TABLE rp_memory (
    session_id UUID PRIMARY KEY REFERENCES rp_sessions (session_id) ON DELETE CASCADE,
    charter    JSONB NOT NULL,                  -- frozen at /start (the durable anchor)
    state      JSONB NOT NULL DEFAULT '{"phase":"","covered":[]}',  -- bounded, mutable (executive = v2)
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- System seed — the 3 interview presets mirrored from chat-service M7
-- (genre='interview'; interview becomes a preset genre of roleplay). Idempotent
-- ON CONFLICT DO NOTHING on the System partial unique index. Users CLONE these
-- into their own tier; they never mutate the System rows.
INSERT INTO roleplay_scripts (owner_user_id, tier, code, name, description, system_prompt, scenario, rubric, genre)
VALUES
  (NULL, 'system', 'faang_swe',
   'FAANG SWE Interview',
   'A senior software-engineer loop: a brief warm-up, a coding/problem-solving round, then wrap-up.',
   'You are a senior engineer running a FAANG-style software interview. Be professional, concise, and probing. Ask ONE question at a time, let the candidate drive, and follow up on their reasoning (edge cases, complexity, trade-offs). Do not lecture or solve it for them. Keep the interview moving through the phases.',
   '{"goal":"Assess senior software-engineering skill through a coding/problem-solving interview","phases":["warmup","coding","followup","wrap"],"checklist":["clarifies the problem before coding","states an approach and its complexity","handles edge cases","writes correct working logic"],"time_budget_min":45,"language":"en"}'::jsonb,
   '{"dimensions":["problem clarification","algorithmic approach","code correctness","communication"]}'::jsonb,
   'interview'),
  (NULL, 'system', 'behavioral_hr',
   'Behavioral (HR) Interview',
   'A behavioral interview focused on STAR stories: motivation, teamwork, conflict, and impact.',
   'You are a thoughtful HR / hiring-manager interviewer running a behavioral interview. Ask open-ended questions that invite STAR (Situation, Task, Action, Result) stories, one at a time. Gently probe for specifics — the candidate''s own actions and measurable results. Stay warm but keep them on track.',
   '{"goal":"Assess behavioral fit through STAR stories on teamwork, conflict, and impact","phases":["warmup","stories","followup","wrap"],"checklist":["gives a concrete Situation and Task","describes their own Actions specifically","states a measurable Result","tells a genuine conflict / failure story"],"time_budget_min":40,"language":"en"}'::jsonb,
   '{"dimensions":["STAR structure","specificity","ownership","reflection"]}'::jsonb,
   'interview'),
  (NULL, 'system', 'system_design',
   'System Design Interview',
   'A senior system-design interview: requirements, high-level design, deep-dives, and trade-offs.',
   'You are a staff engineer running a system-design interview. Start from requirements and scale, then guide the candidate through a high-level design and one or two deep-dives. Push on trade-offs, bottlenecks, and failure modes. Ask one prompt at a time; let the candidate lead the design.',
   '{"goal":"Assess senior system-design skill: requirements, architecture, scaling, and trade-offs","phases":["requirements","high_level","deep_dive","wrap"],"checklist":["clarifies functional and scale requirements","proposes a clear high-level architecture","reasons about a data store and partitioning","discusses bottlenecks and failure modes"],"time_budget_min":50,"language":"en"}'::jsonb,
   '{"dimensions":["requirements","architecture","scalability","trade-off reasoning"]}'::jsonb,
   'interview')
ON CONFLICT (code) WHERE owner_user_id IS NULL DO NOTHING;

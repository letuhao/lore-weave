# F0 — FOUNDATION (detailed design) · narrative-motif-library

> **Workstream:** F0 (Wave 0, serial, lands first → **FROZEN**) · **Service:** composition-service (Python/FastAPI) · **Phase:** P1 gate-zero
> **Authoritative inputs:** spec [`2026-06-26-narrative-motif-library.md`](../../specs/2026-06-26-narrative-motif-library.md) **§R1.4 (schema) + §R1.1/R1.3 (locked tenancy) + §R2.8 (MCP meta)** · master plan [`2026-06-26-motif-library-master-plan.md`](../2026-06-26-motif-library-master-plan.md) **§3 F0**.
> **Grounded against real code:** `services/composition-service/app/db/migrate.py` (DDL house style + seed), `db/repositories/structure_templates.py` + `references.py` (repo + brute-force cosine), `db/models.py` (Pydantic), `config.py`, `deps.py`, `mcp/server.py`, `db/repositories/__init__.py` (shared error types), `tests/integration/db/test_migrate.py` (test house style).
> **Rule:** architecture is DECIDED. This is the file-by-file freeze. Do not re-litigate R1/R2.

---

## 1. Scope — what F0 freezes for every other workstream

F0 is the **shared contract** Wave-1 (W1–W7) and Wave-2 (W8–W11, W-STITCH) build against. It ships **compiling, interface-tested stubs** so the fan-out never blocks on vapor. F0 owns these files **exclusively** (then hands `motif_repo.py` ownership to W1 after the foundation merges — §3 of master plan):

| Freeze | Artifact | Consumed by |
|---|---|---|
| **Schema** (the 5 tables + guards) | `db/migrate.py` (additive `_MOTIF_SCHEMA_SQL` + seed hook) | every WS |
| **Models** (Pydantic + `ForbidExtra` arg models) | `db/models.py` (additive) | every WS (shared types) |
| **Repo CRUD + clone contract** | `db/repositories/motif_repo.py` (impl CRUD + clone) | W1 (extends), W2/W4 (consume) |
| **Retriever contract** | `db/repositories/motif_retrieve.py` (interface stub) | W3 (impl), W2 (consume) |
| **Config** | `config.py` (the new motif settings) | W1/W2/W3/W4/W5 |
| **Wiring** | `deps.py` (DI factories) | every router/WS |
| **Cross-cutting contracts** | this doc §F0.5 (critic-dim, MCP meta kit, clone primitive) | W4/W5 |
| **DTO/API shapes** | this doc §F0.6 (request/response JSON) | W6 frontend |
| **Risk-guard tests** | `tests/integration/db/test_motif_migrate.py` + `tests/contracts/` | the gate |

**What F0 does NOT do** (explicitly out of scope — owned by Wave-1):
- HTTP routers (`routers/motif.py` → W1) · the `retrieve()` impl + embed pipeline (W3) · MCP tool bodies (W4) · planner L2 (W2) · conformance judge (W5) · seed pack JSON content (W7). F0 ships the *signatures* these implement, plus a no-op `NotImplementedError` stub for `MotifRetriever.retrieve` and the clone method **fully implemented** (it is pure DB + a copy of the embedding vector — W1/W3 depend on it being real, not a stub).

**The freeze invariant:** once F0 merges, **field names, method signatures, the critic-dim shape, and the confirm descriptors do not change.** A WS that needs a new field files it as a follow-up against F0, never edits F0 mid-wave (would break every concurrent worktree).

---

## 2. Files (sole owner)

### 2.1 `app/db/migrate.py` — the §R1.4 DDL (additive, idempotent house style)

**Pattern match (from the real file):** one big `_SCHEMA_SQL` string of `CREATE TABLE IF NOT EXISTS` + `CREATE [UNIQUE] INDEX IF NOT EXISTS`; named-constraint adds wrapped in idempotent `DO $$ … pg_constraint probe … $$` blocks; triggers added the same way; `uuidv7()` PG18 builtin for PKs; cross-DB ids carry **no FK** (book_id, project_id, glossary entity ids), in-DB ids **do** FK (`outline_node`, self-FK on `motif`). Seed via deterministic UUIDs + `ON CONFLICT (id) DO NOTHING`.

Add a **new module-level constant `_MOTIF_SCHEMA_SQL`** and execute it in `run_migrations` **after** `_SCHEMA_SQL` (so `outline_node` exists before `motif_application` FKs it). The seed-pack rows (W7) are **NOT** seeded here — W7 owns `db/seed_motifs.py` and `run_migrations` calls an injected hook; F0 adds the call site, W7 fills the data. F0 leaves `_seed_builtin_templates` untouched.

```python
# appended to migrate.py — executed after _SCHEMA_SQL in run_migrations()
_MOTIF_SCHEMA_SQL = """
-- ════════════════════════════════════════════════════════════════════════════
-- NARRATIVE MOTIF LIBRARY (spec §R1.4). 2-tier (User-owned + System), NO book_id.
-- A motif is book-INDEPENDENT and survives book deletion; per-book customization =
-- clone the template (variant_of). Tenancy is enforced at the DB (the partials +
-- the motif_user_owned CHECK + the cross-tier link trigger) — audit B-2/H-2.
-- ════════════════════════════════════════════════════════════════════════════

-- ── motif: the library unit (system tier = owner_user_id NULL, seed/migrate-only;
-- user tier = owner set). `language` is first-class + part of the dedup/embed key
-- (R1.1.3). ONE platform embedding model for ALL motif vectors (embedding_model is
-- a fixed platform id, NOT a per-row/per-user choice — R1.1.2/B-1).
CREATE TABLE IF NOT EXISTS motif (
  id              UUID PRIMARY KEY DEFAULT uuidv7(),
  owner_user_id   UUID,                                   -- NULL = system (seed/migrate-only)
  code            TEXT NOT NULL,
  language        TEXT NOT NULL DEFAULT 'en',             -- part of the dedup/embed key (R1.1.3)
  visibility      TEXT NOT NULL DEFAULT 'private'
                    CHECK (visibility IN ('private','unlisted','public')),
  kind            TEXT NOT NULL DEFAULT 'sequence'
                    CHECK (kind IN ('sequence','situation','hook','emotion_arc','trope','pattern','scheme')),
  category        TEXT,
  name            TEXT NOT NULL,
  summary         TEXT NOT NULL DEFAULT '',               -- the embedded text
  genre_tags      TEXT[] NOT NULL DEFAULT '{}',
  roles           JSONB NOT NULL DEFAULT '[]'::jsonb,     -- [{key, actant, label, constraints}]
  beats           JSONB NOT NULL DEFAULT '[]'::jsonb,     -- [{key, label, intent, tension_target, order, reversal?, alliance_shift?}]
  preconditions   JSONB NOT NULL DEFAULT '[]'::jsonb,     -- [{text}]
  effects         JSONB NOT NULL DEFAULT '[]'::jsonb,     -- [{text}]
  info_asymmetry  JSONB,                                  -- §15.1 scheme {knows,deceived,gap} (nullable)
  tension_target  SMALLINT,                               -- overall 1..5
  emotion_target  TEXT,
  examples        JSONB NOT NULL DEFAULT '[]'::jsonb,     -- [{text}] — STRIPPED on imported-derived publish (trigger below)
  abstraction_confidence TEXT,                            -- mined: high|med|low
  source          TEXT NOT NULL DEFAULT 'authored'
                    CHECK (source IN ('authored','mined','adopted','imported')),
  source_ref      TEXT,                                   -- lineage; opaque token on imported-derived publish (B-3)
  source_version  INT,                                    -- N-4 upstream 3-way-diff version pin
  embedding       REAL[],                                 -- brute-force cosine (reference_source precedent)
  embedding_model TEXT NOT NULL DEFAULT '',               -- ONE platform model (B-1); no per-row choice
  embedding_dim   INT,
  embedded_summary_hash TEXT,                             -- re-embed staleness guard (motifs are mutable)
  judge_score     NUMERIC(4,3),
  mining_support  INT,
  status          TEXT NOT NULL DEFAULT 'active'
                    CHECK (status IN ('draft','active','archived')),
  version         INT NOT NULL DEFAULT 1,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  -- B-2: a both-NULL (system) row must be a published/system row, never a private
  -- orphan. The user-write path additionally server-stamps owner_user_id (app code);
  -- this CHECK is the DB backstop that a private row ALWAYS has an owner.
  CONSTRAINT motif_user_owned CHECK (owner_user_id IS NOT NULL OR visibility <> 'private')
);
-- 2 tenancy partials (NO book tier), keyed incl. language (R1.1.1 + R1.1.3):
CREATE UNIQUE INDEX IF NOT EXISTS uq_motif_user
  ON motif(owner_user_id, code, language) WHERE owner_user_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_motif_system
  ON motif(code, language)                WHERE owner_user_id IS NULL;
CREATE INDEX IF NOT EXISTS idx_motif_owner  ON motif(owner_user_id) WHERE owner_user_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_motif_public ON motif(visibility, updated_at DESC) WHERE visibility = 'public';
CREATE INDEX IF NOT EXISTS idx_motif_genre  ON motif USING GIN (genre_tags);
-- retrieval pre-filter (genre ∩ + status + tier predicate) runs in SQL BEFORE loading
-- vectors (audit data-R1). The composite supports the active-status list scan.
CREATE INDEX IF NOT EXISTS idx_motif_retrieve
  ON motif(status, language) WHERE status = 'active';

-- ── motif_link: composition + legal succession + variant (ATU + plot-graph). Cycle
-- guard on precedes/composed_of (H-2) + user edges may not touch system motifs (H-2).
CREATE TABLE IF NOT EXISTS motif_link (
  id            UUID PRIMARY KEY DEFAULT uuidv7(),
  from_motif_id UUID NOT NULL REFERENCES motif(id) ON DELETE CASCADE,
  to_motif_id   UUID NOT NULL REFERENCES motif(id) ON DELETE CASCADE,
  kind          TEXT NOT NULL CHECK (kind IN ('composed_of','precedes','variant_of')),
  ord           INT,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT motif_link_distinct CHECK (from_motif_id <> to_motif_id),
  UNIQUE (from_motif_id, to_motif_id, kind)
);
CREATE INDEX IF NOT EXISTS idx_motif_link_from ON motif_link(from_motif_id, kind, ord);
CREATE INDEX IF NOT EXISTS idx_motif_link_to   ON motif_link(to_motif_id, kind);

-- H-2 same-tier guard + cycle guard (BEFORE INSERT trigger on motif_link). A
-- user-created edge may not span into a system motif (a user must not reshape the
-- shared graph), and a precedes/composed_of insert may not close a cycle. The
-- function is idempotent via CREATE OR REPLACE; the trigger is (re)attached in a
-- guarded DO-block.
CREATE OR REPLACE FUNCTION motif_link_guard() RETURNS trigger AS $$
DECLARE
  from_owner UUID;
  to_owner   UUID;
  cyc        BOOLEAN;
BEGIN
  SELECT owner_user_id INTO from_owner FROM motif WHERE id = NEW.from_motif_id;
  SELECT owner_user_id INTO to_owner   FROM motif WHERE id = NEW.to_motif_id;
  -- same-tier rule: both system, or both the SAME user. A user edge touching a
  -- system motif (or two different users' motifs) is rejected.
  IF from_owner IS DISTINCT FROM to_owner THEN
    RAISE EXCEPTION 'motif_link cross-tier: from(%) to(%) differ', from_owner, to_owner
      USING ERRCODE = 'check_violation';
  END IF;
  -- cycle guard for the ordered edge kinds (variant_of is symmetric-ish, skip).
  IF NEW.kind IN ('precedes','composed_of') THEN
    WITH RECURSIVE walk(node) AS (
      SELECT NEW.to_motif_id
      UNION
      SELECT ml.to_motif_id FROM motif_link ml
        JOIN walk w ON ml.from_motif_id = w.node
       WHERE ml.kind = NEW.kind
    )
    SELECT EXISTS (SELECT 1 FROM walk WHERE node = NEW.from_motif_id) INTO cyc;
    IF cyc THEN
      RAISE EXCEPTION 'motif_link cycle on % via %', NEW.kind, NEW.from_motif_id
        USING ERRCODE = 'check_violation';
    END IF;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'motif_link_guard_trg') THEN
    CREATE TRIGGER motif_link_guard_trg
      BEFORE INSERT ON motif_link
      FOR EACH ROW EXECUTE FUNCTION motif_link_guard();
  END IF;
END $$;

-- ── motif_application: what was applied where (binding ledger). Per-BOOK scope
-- (R1.1.4 — the anti-repetition cap + "why this scene" trace aggregate ACROSS a
-- book's collaborators, the kinds-bug lesson applied). FK SET NULL keeps history if
-- the motif is archived (data-R3). motif_version pins what was bound (edge-F3).
CREATE TABLE IF NOT EXISTS motif_application (
  id              UUID PRIMARY KEY DEFAULT uuidv7(),
  user_id         UUID NOT NULL,
  project_id      UUID NOT NULL,
  book_id         UUID NOT NULL,                          -- R1.1.4 per-book scope
  motif_id        UUID REFERENCES motif(id) ON DELETE SET NULL,
  motif_version   INT,                                    -- the bound version (trace shows bound, not live)
  outline_node_id UUID REFERENCES outline_node(id) ON DELETE CASCADE,
  role_bindings   JSONB NOT NULL DEFAULT '{}'::jsonb,     -- {role_key: glossary_entity_id}
  annotations     JSONB NOT NULL DEFAULT '{}'::jsonb,     -- data-R7 bound info_asymmetry/reversal/alliance_shift
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_motif_application_book_motif ON motif_application(book_id, motif_id);  -- data-R6 anti-repetition hot read
CREATE INDEX IF NOT EXISTS idx_motif_application_node       ON motif_application(outline_node_id);
CREATE INDEX IF NOT EXISTS idx_motif_application_project    ON motif_application(project_id, created_at DESC);
-- H-5 app-guard: outline_node_id MUST belong to project_id (a cross-project bind is
-- rejected). The in-DB FK only proves the node EXISTS, not that it is in THIS project
-- (the ReferenceViolationError lesson) — a BEFORE INSERT trigger closes it at the DB.
CREATE OR REPLACE FUNCTION motif_application_scope_guard() RETURNS trigger AS $$
DECLARE node_project UUID;
BEGIN
  IF NEW.outline_node_id IS NOT NULL THEN
    SELECT project_id INTO node_project FROM outline_node WHERE id = NEW.outline_node_id;
    IF node_project IS NULL OR node_project <> NEW.project_id THEN
      RAISE EXCEPTION 'motif_application outline_node % not in project %',
        NEW.outline_node_id, NEW.project_id USING ERRCODE = 'check_violation';
    END IF;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'motif_application_scope_guard_trg') THEN
    CREATE TRIGGER motif_application_scope_guard_trg
      BEFORE INSERT ON motif_application
      FOR EACH ROW EXECUTE FUNCTION motif_application_scope_guard();
  END IF;
END $$;

-- ── arc_template: multi-thread × motifs over a chapter span (§12.2). SAME 2-tier
-- tenancy as motif (owner set | NULL=system). layout stores a RESOLVED motif_id
-- alongside motif_code (R1.4 — so a clone/apply walks ids, not codes); publish/adopt
-- clones the member subgraph (audit H-3, W11). ONE platform embedding model.
CREATE TABLE IF NOT EXISTS arc_template (
  id            UUID PRIMARY KEY DEFAULT uuidv7(),
  owner_user_id UUID,                                     -- NULL = system (seed/migrate-only)
  code          TEXT NOT NULL,
  language      TEXT NOT NULL DEFAULT 'en',
  visibility    TEXT NOT NULL DEFAULT 'private'
                  CHECK (visibility IN ('private','unlisted','public')),
  name          TEXT NOT NULL,
  summary       TEXT NOT NULL DEFAULT '',
  genre_tags    TEXT[] NOT NULL DEFAULT '{}',
  chapter_span  INT,
  threads       JSONB NOT NULL DEFAULT '[]'::jsonb,       -- [{key,label}] parallel tracks
  layout        JSONB NOT NULL DEFAULT '[]'::jsonb,       -- [{motif_code, motif_id, thread, span_start, span_end, ord, role_hints, triggers?}]
  pacing        JSONB NOT NULL DEFAULT '[]'::jsonb,
  arc_roster    JSONB NOT NULL DEFAULT '[]'::jsonb,
  source        TEXT NOT NULL DEFAULT 'authored'
                  CHECK (source IN ('authored','mined','imported')),
  source_ref    TEXT,
  source_version INT,
  embedding     REAL[],
  embedding_model TEXT NOT NULL DEFAULT '',
  embedding_dim INT,
  embedded_summary_hash TEXT,
  status        TEXT NOT NULL DEFAULT 'active'
                  CHECK (status IN ('draft','active','archived')),
  version       INT NOT NULL DEFAULT 1,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT arc_template_user_owned CHECK (owner_user_id IS NOT NULL OR visibility <> 'private')
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_arc_template_user
  ON arc_template(owner_user_id, code, language) WHERE owner_user_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_arc_template_system
  ON arc_template(code, language)                WHERE owner_user_id IS NULL;
CREATE INDEX IF NOT EXISTS idx_arc_template_owner  ON arc_template(owner_user_id) WHERE owner_user_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_arc_template_public ON arc_template(visibility, updated_at DESC) WHERE visibility = 'public';
CREATE INDEX IF NOT EXISTS idx_arc_template_genre  ON arc_template USING GIN (genre_tags);

-- ── import_source: the 拆文 deconstruct INPUT (§12.3/§12.6). Per-user/per-book tier
-- ONLY — STRUCTURALLY un-shareable: there is NO visibility column (audit B-3 / the
-- copyright split). Raw imported text stays in the user's own store; only the DERIVED
-- abstract template (arc_template/motif) is ever shareable.
CREATE TABLE IF NOT EXISTS import_source (
  id            UUID PRIMARY KEY DEFAULT uuidv7(),
  owner_user_id UUID NOT NULL,                            -- NEVER NULL (no system import; un-shareable)
  project_id    UUID,                                     -- optional book/project scope (cross-DB, no FK)
  title         TEXT NOT NULL DEFAULT '',
  content       TEXT NOT NULL,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_import_source_owner ON import_source(owner_user_id, created_at DESC);

-- ── B-3 trigger: strip examples[] + opaque-ize source_ref when a motif derived from
-- an import is published. An imported-derived motif going public/unlisted must carry
-- NO source prose (examples) and NO back-readable foreign id. This is a DB trigger,
-- not a prompt — it cannot be bypassed by the LLM/router. Fires on the visibility
-- transition INTO a shared state.
CREATE OR REPLACE FUNCTION motif_publish_strip() RETURNS trigger AS $$
BEGIN
  IF NEW.visibility IN ('public','unlisted')
     AND NEW.source = 'imported'
     AND (TG_OP = 'INSERT' OR OLD.visibility = 'private'
          OR OLD.visibility IS DISTINCT FROM NEW.visibility) THEN
    NEW.examples := '[]'::jsonb;                          -- no source passages leave the workspace
    -- replace any back-readable foreign id with an opaque lineage token.
    IF NEW.source_ref IS NOT NULL AND NEW.source_ref NOT LIKE 'lineage:%' THEN
      NEW.source_ref := 'lineage:' || encode(digest(NEW.source_ref, 'sha256'), 'hex');
    END IF;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'motif_publish_strip_trg') THEN
    CREATE TRIGGER motif_publish_strip_trg
      BEFORE INSERT OR UPDATE OF visibility ON motif
      FOR EACH ROW EXECUTE FUNCTION motif_publish_strip();
  END IF;
END $$;
"""
```

> **`digest()` note:** `encode(digest(…,'sha256'),'hex')` needs the `pgcrypto` extension. F0 adds `CREATE EXTENSION IF NOT EXISTS pgcrypto;` at the top of `_MOTIF_SCHEMA_SQL` (idempotent). If the deploy DB role can't create extensions, the **micro-decision §6-E** covers the fallback (opaque token minted in app code on the publish path, W11) — but the DB trigger is the B-3 backstop, so F0 prefers the extension. The seeded `pgcrypto` is already a common LoreWeave dependency; confirm at BUILD.

**`run_migrations` change (minimal, additive):**
```python
async def run_migrations(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await conn.execute(_SCHEMA_SQL)
        await conn.execute(_MOTIF_SCHEMA_SQL)          # F0: motif library DDL
        await _seed_builtin_templates(conn)
        await _seed_motif_packs(conn)                  # F0 adds the CALL; W7 fills the body
    logger.info("composition migrate: schema applied + %d built-in templates seeded", len(BUILTIN_TEMPLATES))
```
F0 ships `_seed_motif_packs` as a **no-op stub** (`async def _seed_motif_packs(conn): return`) so the call site is frozen; W7 replaces the body (W7 owns the data, F0 owns the call site — disjoint).

### 2.2 `app/db/models.py` — Pydantic row + arg models (additive)

**Pattern match:** capped-text aliases (`_Title`/`_Short`/`_Long`), `Literal` type aliases for enums, `Field(default_factory=...)` for JSONB, cross-DB ids as plain `UUID`, nullable `created_at/updated_at`. **New for F0:** a `ForbidExtra` base for the *create/patch arg* models (audit S2 — the LLM/router cannot smuggle `owner_user_id`). Row models are the read shape; arg models are the write shape.

```python
# ── enums (type aliases, top of file with the others)
MotifKind = Literal["sequence", "situation", "hook", "emotion_arc", "trope", "pattern", "scheme"]
MotifSource = Literal["authored", "mined", "adopted", "imported"]
MotifVisibility = Literal["private", "unlisted", "public"]
MotifStatus = Literal["draft", "active", "archived"]
MotifLinkKind = Literal["composed_of", "precedes", "variant_of"]
Actant = Literal["subject", "object", "sender", "receiver", "helper", "opponent"]
ArcSource = Literal["authored", "mined", "imported"]

# ── ForbidExtra base for write-arg models (mirror loreweave_mcp.ForbidExtra; a
# local alias so non-MCP callers/routers share it). extra='forbid' is the S2 guard.
class _ForbidExtra(BaseModel):
    model_config = {"extra": "forbid"}

# ── sub-shapes (validated JSONB members)
class MotifRole(BaseModel):
    key: Annotated[str, StringConstraints(max_length=100)]
    actant: Actant
    label: _Title = ""
    constraints: list[_Short] = Field(default_factory=list)

class MotifBeat(BaseModel):
    key: Annotated[str, StringConstraints(max_length=100)]
    label: _Title = ""
    intent: _Short = ""
    tension_target: int | None = None            # 1..5
    order: int = 0
    reversal: dict[str, Any] | None = None        # §15.2 {thread, from, to}
    alliance_shift: dict[str, Any] | None = None  # §15.2 {a, b, from, to}

class InfoAsymmetry(BaseModel):
    knows: list[str] = Field(default_factory=list)
    deceived: list[str] = Field(default_factory=list)
    gap: _Long = ""

# ── row models (the repo return shape; embedding is NEVER projected — stays server-side)
class Motif(BaseModel):
    id: UUID
    owner_user_id: UUID | None = None             # NULL = system tier
    code: Annotated[str, StringConstraints(max_length=200)]
    language: Annotated[str, StringConstraints(max_length=20)] = "en"
    visibility: MotifVisibility = "private"
    kind: MotifKind = "sequence"
    category: Annotated[str, StringConstraints(max_length=200)] | None = None
    name: _Title
    summary: _Long = ""
    genre_tags: list[Annotated[str, StringConstraints(max_length=100)]] = Field(default_factory=list)
    roles: list[dict[str, Any]] = Field(default_factory=list)        # validated via MotifRole on write
    beats: list[dict[str, Any]] = Field(default_factory=list)        # validated via MotifBeat on write
    preconditions: list[dict[str, Any]] = Field(default_factory=list)
    effects: list[dict[str, Any]] = Field(default_factory=list)
    info_asymmetry: dict[str, Any] | None = None
    tension_target: int | None = None
    emotion_target: Annotated[str, StringConstraints(max_length=100)] | None = None
    examples: list[dict[str, Any]] = Field(default_factory=list)
    abstraction_confidence: Literal["high", "med", "low"] | None = None
    source: MotifSource = "authored"
    source_ref: _Short | None = None
    source_version: int | None = None
    embedding_model: _Title = ""                  # the vector itself is omitted from the projection
    embedding_dim: int | None = None
    judge_score: Decimal | None = None
    mining_support: int | None = None
    status: MotifStatus = "active"
    version: int = 1
    created_at: datetime | None = None
    updated_at: datetime | None = None

class MotifLink(BaseModel):
    id: UUID
    from_motif_id: UUID
    to_motif_id: UUID
    kind: MotifLinkKind
    ord: int | None = None
    created_at: datetime | None = None

class MotifApplication(BaseModel):
    id: UUID
    user_id: UUID
    project_id: UUID
    book_id: UUID
    motif_id: UUID | None = None                  # SET NULL if the motif is archived
    motif_version: int | None = None
    outline_node_id: UUID | None = None
    role_bindings: dict[str, Any] = Field(default_factory=dict)
    annotations: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None

class ArcPlacement(BaseModel):                     # one layout[] entry
    motif_code: Annotated[str, StringConstraints(max_length=200)]
    motif_id: UUID | None = None                   # resolved id (R1.4)
    thread: Annotated[str, StringConstraints(max_length=100)]
    span_start: int
    span_end: int
    ord: int = 0
    role_hints: dict[str, Any] = Field(default_factory=dict)
    triggers: list[str] = Field(default_factory=list)   # §15.3 other-placement ids

class ArcTemplate(BaseModel):
    id: UUID
    owner_user_id: UUID | None = None
    code: Annotated[str, StringConstraints(max_length=200)]
    language: Annotated[str, StringConstraints(max_length=20)] = "en"
    visibility: MotifVisibility = "private"
    name: _Title
    summary: _Long = ""
    genre_tags: list[Annotated[str, StringConstraints(max_length=100)]] = Field(default_factory=list)
    chapter_span: int | None = None
    threads: list[dict[str, Any]] = Field(default_factory=list)
    layout: list[dict[str, Any]] = Field(default_factory=list)
    pacing: list[dict[str, Any]] = Field(default_factory=list)
    arc_roster: list[dict[str, Any]] = Field(default_factory=list)
    source: ArcSource = "authored"
    source_ref: _Short | None = None
    source_version: int | None = None
    embedding_model: _Title = ""
    embedding_dim: int | None = None
    status: MotifStatus = "active"
    version: int = 1
    created_at: datetime | None = None
    updated_at: datetime | None = None

class ImportSource(BaseModel):
    id: UUID
    owner_user_id: UUID
    project_id: UUID | None = None
    title: _Title = ""
    content: _Long
    created_at: datetime | None = None

# ── retrieval result (the FROZEN contract W3 produces / W2 + the MCP suggest consume)
class MotifCandidate(BaseModel):
    motif: Motif
    score: float
    match_reason: dict[str, Any] = Field(default_factory=dict)   # {tension, genre, precond, cosine}

# ── WRITE-ARG models (ForbidExtra — owner is NEVER an arg; the repo stamps it)
class MotifCreateArgs(_ForbidExtra):
    code: Annotated[str, StringConstraints(max_length=200)]
    name: _Title
    language: Annotated[str, StringConstraints(max_length=20)] = "en"
    kind: MotifKind = "sequence"
    category: Annotated[str, StringConstraints(max_length=200)] | None = None
    summary: _Long = ""
    genre_tags: list[Annotated[str, StringConstraints(max_length=100)]] = Field(default_factory=list)
    roles: list[MotifRole] = Field(default_factory=list)
    beats: list[MotifBeat] = Field(default_factory=list)
    preconditions: list[dict[str, Any]] = Field(default_factory=list)
    effects: list[dict[str, Any]] = Field(default_factory=list)
    info_asymmetry: InfoAsymmetry | None = None
    tension_target: Annotated[int, Field(ge=1, le=5)] | None = None
    emotion_target: Annotated[str, StringConstraints(max_length=100)] | None = None
    examples: list[dict[str, Any]] = Field(default_factory=list)
    visibility: MotifVisibility = "private"            # public/unlisted allowed at create; system is migrate-only

class MotifPatchArgs(_ForbidExtra):
    # every field optional (PATCH semantics); owner/code/language/source are NOT
    # patchable here (identity/lineage are immutable post-create — clone to re-key).
    name: _Title | None = None
    kind: MotifKind | None = None
    category: Annotated[str, StringConstraints(max_length=200)] | None = None
    summary: _Long | None = None
    genre_tags: list[Annotated[str, StringConstraints(max_length=100)]] | None = None
    roles: list[MotifRole] | None = None
    beats: list[MotifBeat] | None = None
    preconditions: list[dict[str, Any]] | None = None
    effects: list[dict[str, Any]] | None = None
    info_asymmetry: InfoAsymmetry | None = None
    tension_target: Annotated[int, Field(ge=1, le=5)] | None = None
    emotion_target: Annotated[str, StringConstraints(max_length=100)] | None = None
    examples: list[dict[str, Any]] | None = None
    visibility: MotifVisibility | None = None
    status: MotifStatus | None = None
```

### 2.3 `app/db/repositories/motif_repo.py` — interface + CRUD + clone (F0 IMPLEMENTS)

**Pattern match (from `references.py`/`structure_templates.py`):** `__init__(pool)`; `_SELECT_COLS` that **omits `embedding`** (the vector stays server-side); `_row_to_motif` that `json.loads` any str JSONB then `Motif.model_validate`; `caller_id` first arg on every method, **every query filters the read predicate or the owner**; JSONB written with `json.dumps(...)::jsonb`; raise the shared `VersionMismatchError`/`ReferenceViolationError` from `db.repositories.__init__`.

```python
"""motif repository — the library unit CRUD + the ONE clone primitive (=adopt).

TENANCY (the kinds-bug fix + R1.1): a motif is system (owner_user_id NULL,
seed/migrate-only) or user-owned (owner set). The read predicate (R1.1) lives in
get_visible/list_for_caller SELECTs — a motif is visible IFF
  owner_user_id IS NULL (system) OR visibility = 'public' OR owner_user_id = caller.
The user-write path (create) SERVER-STAMPS owner_user_id = caller and can never
write a both-NULL (system) row (the DB motif_user_owned CHECK is the backstop).

EMBEDDING: ONE platform model for ALL motif vectors (R1.1.2/B-1). create() inserts
a NULL embedding (W3's embed pipeline fills it transactionally on the summary);
clone() COPIES the source vector (same space → cross-tier cosine stays correct).
The `embedding` column is NEVER projected into a returned Motif (stays server-side,
reference_source precedent).
"""
from __future__ import annotations
import json
from uuid import UUID
import asyncpg
from app.db.models import Motif, MotifCreateArgs, MotifPatchArgs
from app.db.repositories import VersionMismatchError

# vector + hash deliberately excluded — projection is the model shape only.
_SELECT_COLS = """
  id, owner_user_id, code, language, visibility, kind, category, name, summary,
  genre_tags, roles, beats, preconditions, effects, info_asymmetry, tension_target,
  emotion_target, examples, abstraction_confidence, source, source_ref, source_version,
  embedding_model, embedding_dim, judge_score, mining_support, status, version,
  created_at, updated_at
"""
_JSONB_FIELDS = ("roles", "beats", "preconditions", "effects", "info_asymmetry", "examples")

def _row_to_motif(row: asyncpg.Record) -> Motif:
    data = dict(row)
    for f in _JSONB_FIELDS:
        v = data.get(f)
        if isinstance(v, str):
            data[f] = json.loads(v)
    return Motif.model_validate(data)

class MotifRepo:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def create(self, user_id: UUID, args: MotifCreateArgs) -> Motif:
        """Create a USER-tier motif. owner_user_id is STAMPED = user_id (never an
        arg → a both-NULL/system row is impossible from this path; the DB CHECK is
        the backstop). embedding starts NULL (W3 fills it). UNIQUE(owner,code,lang)
        violation → asyncpg.UniqueViolationError (router maps to 409)."""

    async def get_visible(self, caller_id: UUID, motif_id: UUID) -> Motif | None:
        """THE read predicate (R1.1): returns the motif IFF system | public | owned
        by caller. A foreign PRIVATE motif returns None (IDOR-safe — the router maps
        None → the H13 uniform 'not found or not accessible', no existence oracle)."""

    async def patch(
        self, caller_id: UUID, motif_id: UUID, args: MotifPatchArgs, *, expected_version: int,
    ) -> Motif:
        """Optimistic-lock edit, OWNER-only (WHERE owner_user_id = caller_id — a
        system or foreign motif is never patchable here). Bumps version, sets
        updated_at. On a summary change the caller (W3) clears embedded_summary_hash
        so the re-embed fires; F0's signature reserves that (the hash reset is W3's
        transactional concern). Raises VersionMismatchError(current) on a stale
        expected_version; returns None-equivalent via raise if the row isn't the
        caller's (router → H13)."""

    async def archive(self, caller_id: UUID, motif_id: UUID) -> None:
        """Soft-archive (status='archived'), OWNER-only. Idempotent. A foreign/
        missing id is a no-op the router maps to H13 (no oracle). NOT a hard delete
        — motif_application FK is SET NULL, so history survives (data-R3)."""

    async def list_for_caller(
        self, caller_id: UUID, *, scope: str = "all", genre: str | None = None,
        kind: str | None = None, status: str | None = "active", q: str | None = None,
        language: str | None = None, limit: int = 100,
    ) -> list[Motif]:
        """Tier-merged list under the read predicate (system | public | owner).
        `scope` narrows the predicate: 'system' (owner NULL), 'user' (owner=caller),
        'public' (visibility=public), 'all' (the full predicate). genre filters the
        GIN array (genre = ANY(genre_tags)); q is an ILIKE on name/summary; language
        + status + kind are exact. System rows sort first (NULLS FIRST), then name."""

    async def clone(
        self, caller_id: UUID, src_motif_id: UUID, *, target_owner: UUID,
        retag_genres: list[str] | None = None,
    ) -> Motif:
        """The ONE clone primitive (= adopt = clone-to-customize = cross-genre retag;
        R1.1.1). Reads the SOURCE under get_visible (so you may only clone what you
        can see — public/system/own), then INSERTs a NEW row:
          - new id/version=1/created_at/updated_at (reset);
          - owner_user_id = target_owner (always a user; system is migrate-only);
          - visibility = 'private' (a clone is private until the owner republishes);
          - source = 'adopted'; source_ref = 'lineage:'||src.id; source_version = src.version;
          - genre_tags = retag_genres if given (R2.2 cross-genre clone), else src;
          - embedding COPIED from the source (same platform space → cosine valid);
          - code: src.code, UNLESS it collides in target's tier → suffix (handled by
            the caller/W1 adopt; F0's clone raises UniqueViolationError on collision
            so the caller decides the rename policy).
        Returns the new Motif. This is pure DB + a vector copy — fully implemented in
        F0 (W1/W3 depend on it being real)."""
```

### 2.4 `app/db/repositories/motif_retrieve.py` — interface STUB (W3 implements)

F0 ships the class + the **frozen signature** + a `NotImplementedError` body so W2 can import and mock it, and the contract test asserts the signature shape. W3 fills the SQL-pre-filter + brute-force cosine.

```python
"""motif retrieval — the planner's select-candidates core (R1.4 / W3 implements).

The signature is FROZEN in F0 so W2 (planner) builds against it concurrently and
mocks retrieve() until W3 lands. W3's impl: SQL pre-filter (genre ∩ + status='active'
+ the read predicate + language) BEFORE loading vectors (audit data-R1), then
brute-force cosine top-K in app code (reference_source precedent), then the
match_reason breakdown. ONE platform embedding model for all vectors (B-1)."""
from __future__ import annotations
from uuid import UUID
import asyncpg
from app.db.models import MotifCandidate

class MotifRetriever:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def retrieve(
        self, caller_id: UUID, *, book_id: UUID, project_id: UUID,
        genre_tags: list[str], language: str,
        beat_role: str | None, tension: int | None,
        prev_effects: list[str] | None = None, limit: int = 10,
    ) -> list[MotifCandidate]:
        """Tier-merged, SQL-pre-filtered, cosine-ranked motif candidates for a
        chapter's beat. Returns up to `limit` MotifCandidate (motif + score +
        match_reason={tension,genre,precond,cosine}), highest score first. W3 impl."""
        raise NotImplementedError("W3 implements motif retrieval")
```

### 2.5 `app/config.py` — the new motif settings (additive)

Append to `Settings` (all optional-with-defaults — same block style as `plan_*`):

```python
    # ── Narrative motif library (F0). ONE platform embedding model for ALL motif
    # vectors (R1.1.2/B-1) — NOT the user's BYOK model — so cross-tier cosine is
    # correct and a clone can copy the vector. This is a (source, ref) pair resolved
    # via provider-registry /internal/embed (the embedding_client), exactly like
    # reference_source but PLATFORM-fixed, not per-Work. Required to be non-empty
    # before W3's embed pipeline runs (W3 fails closed if unset).
    motif_embed_model_source: str = "platform_model"
    motif_embed_model_ref: str = ""              # e.g. a platform embedding model id; W3 asserts non-empty
    # Retrieval (W3/W2): top-K candidates loaded after the SQL pre-filter, and the
    # minimum cosine for a candidate to be a planner-bindable match.
    motif_retrieve_top_k: int = 10
    motif_min_score: float = 0.30
    # Anti-repetition (W2): max times one motif may be applied within a single book
    # before the planner/UX warns (the cowrite craft-nudge made structural — §11).
    motif_max_reapply: int = 3
    # Mining gate (P3/W8): mined drafts below this judge score are shown, never
    # silently added (no silent drop — §11).
    motif_mine_min_judge: float = 0.60
    # Per-user quotas (B-4 — mirror D-MCP-BOOK-CREATE-QUOTA). The publish/adopt
    # ceilings the W1 router + W4 MCP pre-check; 0 = unlimited (dev default off).
    motif_max_public: int = 0
    motif_max_adopt: int = 0
```

> `plan_*_scenes_per_chapter` and `plan_high_tension_threshold` **already exist** — F0 does not re-add them. The §16 `style_profile.target_words` dial is **W2/W-STITCH** scope, not F0.

### 2.6 `app/deps.py` — DI factories (additive)

Mirror the existing `get_references_repo` factories. F0 adds the repo + retriever; W1 will reuse `get_motif_repo` (it extends the same class).

```python
from app.db.repositories.motif_repo import MotifRepo
from app.db.repositories.motif_retrieve import MotifRetriever

async def get_motif_repo() -> MotifRepo:
    """F0 — the motif library CRUD + clone primitive. W1 extends it with the HTTP
    surface (adopt/publish/catalog); the engine/MCP consume the same instance."""
    return MotifRepo(get_pool())

async def get_motif_retriever() -> MotifRetriever:
    """F0 frozen signature; W3 implements. The planner (W2) and the MCP
    _suggest_for_chapter (W4) both resolve candidates through this one core."""
    return MotifRetriever(get_pool())
```

### 2.7 `tests/contracts/` + `tests/integration/db/test_motif_migrate.py` (F0 owns)

- **New package** `tests/contracts/__init__.py` + `tests/contracts/test_motif_contract.py` — pure-unit signature/shape tests (no DB), runnable in the standard suite (mirrors how `test_mcp_server.py` does direct handler shape tests). Asserts: every frozen method exists with the documented parameter names (via `inspect.signature`); `ForbidExtra` rejects an extra key on every arg model; `MotifCandidate` shape; the model round-trips `model_validate`/`model_dump(mode="json")`.
- **New integration test** `tests/integration/db/test_motif_migrate.py` — gated on `TEST_COMPOSITION_DB_URL` (the real-Postgres pattern from `test_migrate.py`); drops the 5 motif tables on setup/teardown; the §4 risk-guard assertions.

---

## 3. The frozen repo contract (write these EXACTLY)

These signatures are the parallelization contract. Wave-1 builds against them; they do not change post-merge.

```python
# motif_repo.py  (F0 implements CRUD + clone; W1 extends with adopt/publish/catalog)
class MotifRepo:
    async def create(self, user_id: UUID, args: MotifCreateArgs) -> Motif: ...
    async def get_visible(self, caller_id: UUID, motif_id: UUID) -> Motif | None: ...
    async def patch(self, caller_id: UUID, motif_id: UUID, args: MotifPatchArgs, *, expected_version: int) -> Motif: ...
    async def archive(self, caller_id: UUID, motif_id: UUID) -> None: ...
    async def list_for_caller(self, caller_id: UUID, *, scope: str = "all", genre: str | None = None,
                              kind: str | None = None, status: str | None = "active", q: str | None = None,
                              language: str | None = None, limit: int = 100) -> list[Motif]: ...
    async def clone(self, caller_id: UUID, src_motif_id: UUID, *, target_owner: UUID,
                    retag_genres: list[str] | None = None) -> Motif: ...

# motif_retrieve.py  (W3 implements; W2 + the MCP suggest consume — frozen HERE)
class MotifRetriever:
    async def retrieve(self, caller_id: UUID, *, book_id: UUID, project_id: UUID,
                       genre_tags: list[str], language: str, beat_role: str | None,
                       tension: int | None, prev_effects: list[str] | None = None,
                       limit: int = 10) -> list[MotifCandidate]: ...

# MotifCandidate = {motif: Motif, score: float, match_reason: {tension, genre, precond, cosine}}
```

**Contract notes that bind the WSs:**
- `caller_id` is **always** the first positional arg → always derived from the JWT/envelope `sub`, **never** a request/tool field. `owner_user_id` is **never** a parameter on any write (create stamps it; clone takes `target_owner` which the caller sets = its own user id for adopt).
- `get_visible` is the **single read chokepoint** — W1's GET, W4's `_motif_get`, and the planner's by-id reads all go through it (no WS re-implements the predicate). A None result → H13 uniform error at the caller.
- `clone` returns a **private** row (visibility reset) owned by `target_owner`, vector copied, `source_ref='lineage:'||src.id`, `version=1`. It raises `UniqueViolationError` on a code collision in the target tier so the caller owns the rename policy (W1 adopt suffixes; the contract just guarantees the raise).

---

## 4. Tests (the gate)

### 4.1 Migration-idempotent (mirror `test_migrate.py::test_migrate_idempotent_and_seeds_once`)
`run_migrations` runs **twice** clean: the 5 tables, all partials, both triggers, and the publish-strip trigger exist after the second run with no error and no double-create. The `_TABLES` drop list extends with `motif_application, motif_link, arc_template, import_source, motif` (in FK-dependency order — children first).

### 4.2 The 2 tenancy partials + `motif_user_owned` CHECK (B-2)
- `uq_motif_user`: two user rows same `(owner, code, language)` → `UniqueViolationError`; **same code+lang but different language** → BOTH insert (the language axis, N-1). **same code, different owner** → both insert (per-user tier).
- `uq_motif_system`: two system rows (owner NULL) same `(code, language)` → `UniqueViolationError`.
- `motif_user_owned` CHECK: insert `owner_user_id=NULL, visibility='private'` → **`CheckViolationError`** (a both-NULL private orphan is rejected at the DB — B-2). Insert `owner_user_id=NULL, visibility='public'` → **OK** (a published/system row may be ownerless).

### 4.3 `get_visible` IDOR (the master-plan F0 eval-gate)
Seed: a **system** motif (owner NULL, private — seeded directly), a **public** user motif (owner=U2, public), an **owned** private motif (owner=U1, private), a **foreign-private** motif (owner=U2, private). `get_visible(U1, …)` returns the system, public, and owned rows; returns **None** for the foreign-private row (the IDOR assertion). `list_for_caller(U1)` includes the first three, **excludes** the foreign-private.

### 4.4 `motif_link` cycle + same-tier (H-2)
- **Cycle:** `A precedes B`, `B precedes C` insert OK; `C precedes A` → `CheckViolationError` (the recursive walk catches it). Same for `composed_of`.
- **Same-tier:** a user motif `→ precedes →` a **system** motif → `CheckViolationError` (cross-tier rejected). Two of the SAME user's motifs → OK. (`variant_of` is exempt from the cycle walk but still same-tier-gated.)

### 4.5 `motif_application` book-scope + the outline-node∈project guard (H-5)
- Insert with `outline_node_id` whose `outline_node.project_id != motif_application.project_id` → `CheckViolationError` (the scope-guard trigger — H-5). Matching project → OK.
- `book_id` is `NOT NULL` (the per-book aggregate key) → a NULL book_id insert → `NotNullViolationError`.
- The FK `ON DELETE SET NULL`: archive/delete the referenced `motif` → the application row survives with `motif_id = NULL` (data-R3 history retention).

### 4.6 N-1 language in the dedup key (folded into 4.2)
Explicit: the **same `code` in `en` and `vi`** are **separate rows** in BOTH tiers (this is the §6-A recommendation, locked by the partial key shape). The test inserts `('cultivation.fortuitous_encounter','en')` and `(…,'vi')` for the same owner and asserts both persist.

### 4.7 B-1 one platform embedding model (column-shape assertion)
There is exactly **one** `embedding_model` column on `motif` and **no per-row model-choice column** (no `embedding_model_source`/`_ref` on the row). The contract test asserts `MotifCreateArgs` has **no** embedding-model field (the model is platform config, never a write arg — B-1). W3's deeper "all vectors share one model" runtime assertion is W3-owned; F0 guards the **schema/arg shape** that makes per-row choice impossible.

### 4.8 B-3 publish-strip trigger
Insert an `imported`-source motif with `examples=[{text:…}]` and `source_ref='import:<uuid>'`, `visibility='private'`; UPDATE `visibility='public'` → re-SELECT shows `examples = []` and `source_ref LIKE 'lineage:%'` (no back-readable id). A non-imported (`authored`) public motif keeps its examples (the strip is import-only).

### 4.9 Contract tests (every signature)
Each frozen method (§3) has a `tests/contracts/` test asserting it exists with the documented parameter names and that the arg models reject extra keys (`ForbidExtra`). `MotifRetriever.retrieve` raises `NotImplementedError` in F0 (the stub contract) — W3 replaces that test with a behavior test.

---

## 5. Audit risk-guards as failing-tests-first

Per master-plan §7, each blocker is a **failing test written before the code**. F0 owns these five (others are W1/W2/W3/W4/W5):

| Guard | Test (write RED first) | Made green by |
|---|---|---|
| **B-2** both-NULL write rejected at DB | 4.2 — `INSERT owner=NULL,visibility='private'` → `CheckViolationError` | the `motif_user_owned` CHECK |
| **H-2** motif_link cycle + same-tier | 4.4 — cycle insert + cross-tier insert → `CheckViolationError` | `motif_link_guard()` trigger |
| **H-5** application book-scope + node∈project | 4.5 — cross-project node + NULL book_id rejected | `motif_application_scope_guard()` trigger + `book_id NOT NULL` |
| **N-1** language in the dedup key | 4.6/4.2 — same code en+vi = 2 rows | the `(…,language)` partial unique keys |
| **B-1** one platform embedding model | 4.7 — one `embedding_model` col, no per-row choice, no embed arg on `MotifCreateArgs` | the schema (single column) + arg-model shape |

**TDD order for F0:** write the `tests/integration/db/test_motif_migrate.py` assertions (4.1–4.8) against the not-yet-written DDL → run RED → write `_MOTIF_SCHEMA_SQL` → GREEN. Then the `tests/contracts/` shape tests (4.9) against the not-yet-written models/repo → RED → write models + repo CRUD + clone → GREEN.

---

## 6. Open micro-decisions + recommendation

| # | Decision | Recommendation (LOCK at F0 BUILD) |
|---|---|---|
| **A** | **Language in the unique key** — is the same `code` in `en` + `vi` two separate rows, or one row with a language column that's just metadata? | **Two separate rows.** The partials are keyed `(…, language)` (R1.1.3 makes language part of the dedup/embed key). An `en` and a `vi` "fortuitous encounter" embed differently and retrieve under different `language` filters → they MUST be distinct rows. This is already the §R1.4 shape; §4.6 locks it as a test. **No further choice — recommend confirming and moving on.** |
| **B** | **System-write chokepoint** — how is "system rows are migrate/seed-only" enforced, given the DB allows an ownerless public row? | **App-layer + DB-CHECK split (R1.3).** The DB `motif_user_owned` CHECK only forbids a both-NULL **private** orphan; it deliberately ALLOWS an ownerless public/system row (so the seed pack — W7 — can write owner NULL). The "no regular user writes a system row" rule is enforced in the **write path**: `MotifRepo.create` stamps `owner=caller` and has no owner param, so a user CRUD call **cannot** produce an owner-NULL row. Seeds bypass `create()` and INSERT owner NULL directly in the migration (the chokepoint = "only migrate/seed code touches owner NULL", same as `structure_template`). **Recommend: keep the CHECK as the backstop, document the seed-only INSERT path, no extra trigger.** |
| **C** | **`pgcrypto` for the opaque lineage token** (B-3 trigger uses `digest()`) | **Prefer `CREATE EXTENSION IF NOT EXISTS pgcrypto`** in `_MOTIF_SCHEMA_SQL` (idempotent; pgcrypto is widely available on RDS/postgres:18). **Fallback** if the DB role can't create extensions: the trigger sets `source_ref = 'lineage:' || NEW.id::text` (the motif's OWN id is already opaque to the consumer — it reveals nothing about the source), and the *true* source link is dropped entirely. **Recommend the `::text`-of-own-id fallback as the DEFAULT** — it needs no extension, leaks nothing, and the upstream-diff (W11) tracks lineage via `source_version` + a separate private column if ever needed. Drop the `digest()` dependency unless W11 proves it needs a source-derived token. |
| **D** | **`info_asymmetry` / `reversal` / `alliance_shift` — column vs pure-JSONB** | **`info_asymmetry` = its own nullable JSONB column on `motif`** (it's queried by the conformance judge — §15.1 — and is motif-level); **`reversal`/`alliance_shift` = members of a `beats[]` entry** (beat-level, never queried relationally). This matches §15.2 ("annotations on a `beats[]` entry"). Already the §2.2 shape above. **Recommend: lock; no `motif_beat_annotation` table.** |
| **E** | **`arc_template` + `import_source` in F0 vs deferred to W9/W10** | **Ship the DDL + models in F0** (they're cheap, and freezing them now means W9/W10 don't fork the migration mid-wave — the whole point of F0). **Do NOT ship their repos** (W9 owns `import_source` repo, W10 owns `arc_template` repo). F0 ships only the *tables + Pydantic row models*. **Recommend: tables+models in F0, repos in their WS.** |
| **F** | **Clone code-collision policy** — does `clone()` rename on collision or raise? | **Raise `UniqueViolationError`; the caller owns the rename.** Adopt (W1) wants a deterministic suffix (`code-2`); a cross-genre retag (W1/R2.2) may want the same code in a different genre (which doesn't collide — genre isn't in the key). Pushing the policy to the caller keeps F0's `clone` a pure primitive. **Recommend: raise; document that W1 adopt catches it and suffixes.** |

---

## 7. Ordered task list (loom-sized)

F0 is **one coherent effort** (M size — schema migration + models + a repo + config/deps wiring; risk floor = M for the DDL/migration side effects). Run continuously; checkpoint at the **schema-frozen** and **contract-frozen** risk boundaries (the two things other WSs depend on).

1. **T1 — RED: migration risk-guard tests.** Write `tests/integration/db/test_motif_migrate.py` (§4.1–4.8) against the not-yet-written DDL. Extend the `_TABLES` drop list. Confirm RED (tables don't exist).
2. **T2 — DDL.** Add `_MOTIF_SCHEMA_SQL` (the §2.1 block: 5 tables, 2×2 partials, the 3 triggers, the retrieve index, optional `pgcrypto` per §6-C). Wire it into `run_migrations` after `_SCHEMA_SQL`; add the `_seed_motif_packs` no-op stub + its call site. → T1 GREEN. **[checkpoint: schema frozen]**
3. **T3 — Models.** Add the enums, `_ForbidExtra`, sub-shapes (`MotifRole`/`MotifBeat`/`InfoAsymmetry`/`ArcPlacement`), row models (`Motif`/`MotifLink`/`MotifApplication`/`ArcTemplate`/`ImportSource`), `MotifCandidate`, and the write-arg models (`MotifCreateArgs`/`MotifPatchArgs`) to `db/models.py`.
4. **T4 — RED: contract/shape tests.** Write `tests/contracts/test_motif_contract.py` (§4.9): signatures via `inspect.signature`, `ForbidExtra` rejection, model round-trips, `MotifCandidate` shape. Confirm RED (repo/retriever absent).
5. **T5 — Repo CRUD + clone.** Write `db/repositories/motif_repo.py` — `_SELECT_COLS` (no vector), `_row_to_motif`, and the six methods (§3). `create`/`get_visible`/`patch`/`archive`/`list_for_caller`/`clone` fully implemented (clone is real — copies the vector). Raise the shared `VersionMismatchError`.
6. **T6 — Retriever stub.** Write `db/repositories/motif_retrieve.py` — the class + frozen `retrieve` signature + `NotImplementedError` body. → T4 GREEN.
7. **T7 — Config + deps.** Append the §2.5 settings to `Settings`; add `get_motif_repo` + `get_motif_retriever` to `deps.py`.
8. **T8 — VERIFY.** Run the unit suite (contract tests) + the gated integration suite against `TEST_COMPOSITION_DB_URL`. Evidence: migration idempotent, B-2/H-2/H-5/N-1/B-1/B-3 guards green, IDOR green, every signature contract green. Single-service change → no cross-service live-smoke required (F0 ships no cross-service call); note `live infra: integration suite on throwaway DB`. **[checkpoint: contract frozen → fan out Wave 1]**

**Hand-off:** after F0 merges, master-plan §3 transfers `motif_repo.py` ownership to **W1** (it extends CRUD with adopt/publish/catalog). All other F0 files (`migrate.py`, `models.py`, `config.py`, `deps.py`, `motif_retrieve.py`, the F0 tests) stay F0-frozen; a WS needing a change files a follow-up, never edits them mid-wave.

---

### Appendix — house-style conformance checklist (so the BUILD matches the codebase)

- [x] DDL is `IF NOT EXISTS` + guarded `DO $$ … pg_constraint/pg_trigger probe … $$` (idempotent on every boot) — matches `migrate.py`.
- [x] `uuidv7()` PK default; cross-DB ids (book_id, project_id, glossary entity ids) carry **no FK**; in-DB ids (`outline_node`, self-FK on `motif`) **do**.
- [x] Repos: `__init__(pool)`, `caller_id`-first, `_SELECT_COLS` **excludes `embedding`**, JSONB via `json.loads`/`json.dumps(...)::jsonb`, raise shared `VersionMismatchError`/`ReferenceViolationError` — matches `references.py`.
- [x] Pydantic: capped-text aliases, `Literal` enums, `Field(default_factory=…)`, nullable timestamps, `model_validate`/`model_dump(mode="json")` — matches `models.py`.
- [x] Arg models extend a `ForbidExtra` base (`extra='forbid'`) — matches the MCP kit's `ForbidExtra` (audit S2).
- [x] Config: optional-with-defaults block, fail-closed only for genuinely-required secrets — matches `config.py`.
- [x] Tests: integration gated on `TEST_COMPOSITION_DB_URL` with a drop-on-setup/teardown fixture; unit/contract tests run unconditionally — matches `test_migrate.py` + `test_mcp_server.py`.

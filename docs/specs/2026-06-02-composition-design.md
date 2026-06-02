# Composition Service — DESIGN spec

> **Date:** 2026-06-02 · **Phase:** DESIGN (building on [vision](2026-06-02-composition-service-vision.md) + [requirements](2026-06-02-composition-requirements.md) + [UX](2026-06-02-composition-studio-ux.md)).
> **Status:** living — §1 DB schema (V0) approved 2026-06-02. To come: §2 RAG packer · §3 agent loop · §4 prose-judge dims · §5 API contract · §6 sequences.
> **Scope:** V0 = lore-grounded co-writer **+ visual planning** (Editor · Co-writer · Grounding · Critic · Canon Rules · Outline · Scene Graph · engine · co-writing/stream only). 同人 = V2.

---

## §1 DB schema (V0)

Composition owns its own Postgres DB (NFR-1). **Prose + revisions stay in book-service chapters** (reused via the existing TipTap editor); composition stores the *structure + canon + generation* layer. All FKs to other services are **cross-DB → no DB FK, app-level integrity** (mirrors knowledge-service). `user_id` is **denormalized** onto every table for authz + anti-leak (404-not-403), matching `knowledge_projects`.

### §1.1 Scene ↔ chapter anchoring (consequence of granularity = sub-chapter)
A book chapter (book-service) contains **N scenes** as **anchored ranges** in its TipTap content. A new FE extension — **`SceneAnchor`** (a ProseMirror node carrying `scene_id`, see FR-B9) — delimits scenes inside the chapter doc. So:
- `outline_node(kind='scene').chapter_id` = the book chapter it lives in; its **prose = the content between its anchor and the next** in that chapter.
- **Source of truth for intra-chapter scene order = anchor order in content** (prose is linear). `outline_node.rank` orders arc/chapter grouping; scene order is read from anchors. (Avoids two-sources-of-truth.)
- Retrieval/critic resolve a scene's text by: `scene → chapter_id → book-chapter content → SceneAnchor(scene_id) range`.

### §1.2 DDL

```sql
-- ── composition_work: the Work marker + work-level settings (1:1 with a book-typed project)
CREATE TABLE IF NOT EXISTS composition_work (
  project_id          UUID PRIMARY KEY,                  -- = knowledge_projects.project_id (no FK, cross-DB)
  user_id             UUID NOT NULL,                     -- no FK; denormalized for authz/anti-leak
  book_id             UUID NOT NULL,                     -- no FK; the book-typed project's book
  active_template_id  UUID,                              -- → structure_template.id
  status              TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','archived')),
  settings            JSONB NOT NULL DEFAULT '{}'::jsonb, -- style defaults, prefs
  version             INT NOT NULL DEFAULT 1,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_composition_work_user ON composition_work(user_id);

-- ── structure_template: pluggable story-structure library (global built-ins + user-custom)
CREATE TABLE IF NOT EXISTS structure_template (
  id            UUID PRIMARY KEY DEFAULT uuidv7(),
  owner_user_id UUID,                                    -- NULL = global/built-in
  name          TEXT NOT NULL,
  kind          TEXT NOT NULL DEFAULT 'generic',         -- save_the_cat|hero_journey|story_circle|kishotenketsu|web_novel|generic
  beats         JSONB NOT NULL DEFAULT '[]'::jsonb,       -- [{key,label,purpose,order}]
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_structure_template_owner ON structure_template(owner_user_id);

-- ── outline_node: Arc→Chapter→Scene→Beat tree (also = Scene-Graph nodes). One tree, many views.
CREATE TABLE IF NOT EXISTS outline_node (
  id                 UUID PRIMARY KEY DEFAULT uuidv7(),
  user_id            UUID NOT NULL,
  project_id         UUID NOT NULL,
  parent_id          UUID REFERENCES outline_node(id) ON DELETE CASCADE,   -- in-DB FK (same DB) OK
  kind               TEXT NOT NULL CHECK (kind IN ('arc','chapter','scene','beat')),
  rank               TEXT NOT NULL,                       -- fractional/LexoRank, ordered within parent
  title              TEXT NOT NULL DEFAULT '',
  pov_entity_id      UUID,                                -- → glossary entity (no FK)
  present_entity_ids UUID[] NOT NULL DEFAULT '{}',        -- scene cast (authored/AI-suggested, refined by extraction)
  goal               TEXT NOT NULL DEFAULT '',
  beat_role          TEXT,                                -- key into active template's beats (scenes only)
  status             TEXT NOT NULL DEFAULT 'empty' CHECK (status IN ('empty','outline','drafting','done')),
  chapter_id         UUID,                                -- book chapter (no FK); required on kind in (chapter,scene)
  tension            SMALLINT,                            -- 0..100 (scenes)
  story_order        INT,                                 -- in-world chronology (≠ rank reading-order); spoiler-cutoff axis, aligns with knowledge chronological_order — supports flashback/dual-timeline
  synopsis           TEXT NOT NULL DEFAULT '',
  version            INT NOT NULL DEFAULT 1,
  is_archived        BOOLEAN NOT NULL DEFAULT false,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT outline_chapter_required  CHECK (kind NOT IN ('chapter','scene') OR chapter_id IS NOT NULL),
  CONSTRAINT outline_beatrole_scene    CHECK (beat_role IS NULL OR kind = 'scene')
);
CREATE INDEX IF NOT EXISTS idx_outline_node_project ON outline_node(project_id) WHERE NOT is_archived;
CREATE INDEX IF NOT EXISTS idx_outline_node_parent  ON outline_node(parent_id, rank);
CREATE INDEX IF NOT EXISTS idx_outline_node_chapter ON outline_node(chapter_id) WHERE kind = 'scene';

-- ── scene_link: ONLY non-derivable edges. sequence = rank; thread = derived from present_entity_ids.
CREATE TABLE IF NOT EXISTS scene_link (
  id           UUID PRIMARY KEY DEFAULT uuidv7(),
  user_id      UUID NOT NULL,
  project_id   UUID NOT NULL,
  from_node_id UUID NOT NULL REFERENCES outline_node(id) ON DELETE CASCADE,
  to_node_id   UUID NOT NULL REFERENCES outline_node(id) ON DELETE CASCADE,
  kind         TEXT NOT NULL DEFAULT 'setup_payoff' CHECK (kind IN ('setup_payoff','custom')),
  label        TEXT NOT NULL DEFAULT '',
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT scene_link_distinct CHECK (from_node_id <> to_node_id),
  UNIQUE (from_node_id, to_node_id, kind)
);
CREATE INDEX IF NOT EXISTS idx_scene_link_project ON scene_link(project_id);
CREATE INDEX IF NOT EXISTS idx_scene_link_from    ON scene_link(from_node_id);

-- ── canon_rule: author-declared invariants. from/until_order on the SAME axis as knowledge timeline.
CREATE TABLE IF NOT EXISTS canon_rule (
  id          UUID PRIMARY KEY DEFAULT uuidv7(),
  user_id     UUID NOT NULL,
  project_id  UUID NOT NULL,
  text        TEXT NOT NULL,
  scope       TEXT NOT NULL DEFAULT 'world' CHECK (scope IN ('world','entity','reveal_gate')),
  entity_id   UUID,                                       -- → glossary entity (scope entity/reveal_gate)
  from_order  INT,                                        -- chronological_order axis (knowledge timeline)
  until_order INT,
  kind        TEXT,                                       -- tag: invariant|death|item_lost|reveal|...
  active      BOOLEAN NOT NULL DEFAULT true,
  version     INT NOT NULL DEFAULT 1,
  is_archived BOOLEAN NOT NULL DEFAULT false,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_canon_rule_project ON canon_rule(project_id) WHERE active AND NOT is_archived;
CREATE INDEX IF NOT EXISTS idx_canon_rule_entity  ON canon_rule(entity_id) WHERE entity_id IS NOT NULL;

-- ── generation_job: AI generation + critic tracking. critic anchored to a book-chapter revision (anti-stale).
CREATE TABLE IF NOT EXISTS generation_job (
  id                 UUID PRIMARY KEY DEFAULT uuidv7(),
  user_id            UUID NOT NULL,
  project_id         UUID NOT NULL,
  outline_node_id    UUID REFERENCES outline_node(id) ON DELETE SET NULL,
  operation          TEXT NOT NULL,                       -- continue|rewrite|expand|describe|draft_scene|...
  mode               TEXT NOT NULL DEFAULT 'cowrite' CHECK (mode IN ('cowrite','auto')),
  status             TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','running','completed','failed','cancelled')),
  llm_job_id         UUID,                                -- → llm-gateway job
  input              JSONB NOT NULL DEFAULT '{}'::jsonb,   -- packed context summary + params
  result             JSONB,                               -- generated text + meta
  critic             JSONB,                               -- {coherence,voice,pacing,canon_consistency,issues[]}
  target_chapter_id  UUID,                                -- book chapter the critic scored
  target_revision_id UUID,                                -- book-chapter revision (anti-staleness)
  cost_usd           NUMERIC(10,4) NOT NULL DEFAULT 0,    -- display only; usage-billing is authoritative
  idempotency_key    TEXT,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_generation_job_idem ON generation_job(idempotency_key) WHERE idempotency_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_generation_job_project ON generation_job(project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_generation_job_node    ON generation_job(outline_node_id);

-- ── outbox_events: standard (matches knowledge-service); relayed by worker-infra → loreweave:events:composition
CREATE TABLE IF NOT EXISTS outbox_events (
  id             UUID PRIMARY KEY DEFAULT uuidv7(),
  aggregate_type TEXT NOT NULL DEFAULT 'composition',
  aggregate_id   UUID NOT NULL,
  event_type     TEXT NOT NULL,
  payload        JSONB NOT NULL DEFAULT '{}',
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  published_at   TIMESTAMPTZ,
  retry_count    INT NOT NULL DEFAULT 0,
  last_error     TEXT
);
CREATE INDEX IF NOT EXISTS idx_outbox_pending ON outbox_events(created_at) WHERE published_at IS NULL;
```

### §1.3 Derivations (NOT stored — computed)
- **Scene sequence** = `rank` order (+ anchor order within a chapter). **Character thread** for entity E = scenes where `E = ANY(present_entity_ids)`, in order. **Beat→scene** = `outline_node.beat_role` ↔ active template's beat keys.

### §1.4 Cross-DB anchors (app-level integrity)
`project_id`→knowledge · `book_id`/`chapter_id`/`target_revision_id`→book · `pov_entity_id`/`present_entity_ids[]`/`canon_rule.entity_id`→glossary · `llm_job_id`→gateway. Validated in app code / cross-service calls; no DB FK (different DBs).

### §1.5 Forward-compat (V1/V2 — schema already leaves room)
- **V1 non-linear:** add `branch_id UUID` to `outline_node` (NULL = canonical); new `scene_variant` (FK `outline_node`, holds alternate prose for takes); `style_profile`/`voice_profile`/`reference_source`.
- **V2 同人:** `derivative_work(source_work_id, divergence_spec)` · `entity_override` · 2-layer COW retrieval merged in the packer (no knowledge-service change, per COMP-A6).

---

## §2 RAG packer (generation retrieval core)

Assembles **constraint-shaped** context for one target scene (`outline_node`). Runs in COMP (per COMP-A6 — self-pack); all reads reuse existing HTTP surfaces; the orchestration + budget policy is the new module.

### §2.1 Lenses
| Lens | Content | Source |
|---|---|---|
| **L0 Canon** | active `canon_rule` applying at the scene position (`from_order ≤ pos ≤ until_order`) + world rules | COMP DB |
| **L1 Present state** | each `present_entity_ids` + POV → state + 1-hop relations (`valid_until IS NULL`, ≤ cutoff) | knowledge entity/relations |
| **L2 Structural** | beat purpose (template) + goal + POV + synopsis + `setup_payoff` threads touching the scene | COMP DB |
| **L2′ Planned** | synopses of *unwritten* scenes ≤ position — so non-linear / out-of-order drafting has planned context, not just extracted facts | COMP DB (`outline_node.synopsis`) |
| **L3 Recent prose** | last K paragraphs before the scene (prev-scene tail / chapter-so-far) | book chapter content (via `SceneAnchor`) |
| **L4 Semantic refs** | relevant lore/style passages | knowledge `drawers/search` |
| **L5 Long-term** | hierarchical chapter/part/book summaries (anti-drift) | knowledge summaries / `summarize_level` |

### §2.2 Spoiler cutoff
All time-aware lenses (L1 events · L4 · L5) filter `chronological_order ≤ scene.story_order`, via `timeline?before_order=`. **Cutoff = the scene's `story_order`** (in-world time on `outline_node`, ≠ reading order `rank`) — so a Ch.12 **flashback** with a low `story_order` correctly sees only canon up to that in-world moment (non-linear / dual-timeline safe). Aligns with knowledge's `chronological_order`. *(V2 derivative: also ≤ `branch_point`.)*

### §2.3 Priority ladder (budget trim — drop lowest first)
- **Never drop:** L0 canon · L1 core state · L2 beat/goal · L3 immediate-preceding prose.
- **Drop order:** L4 refs → L5 summaries (chapter first, book last) → L2 stale threads → L1 2-hop → L3 older prose.
- Mirrors knowledge `_enforce_budget` but with a **generation** priority (canon-first), not Q&A.

### §2.4 Assembly (structured prompt)
`<canon>` (hard constraints) · `<present>` (who + state) · `<threads>` (open setups due) · `<beat goal POV synopsis>` · `<recent>` (last K paras) · `<lore>` · `<memory>` · `<guide>` (author steer).

### §2.5 Runtime
Parallel gather of lenses with per-lens timeout + graceful degrade (mirrors `app/context/modes/full.py` `_safe_*`). Stable parts (canon, beat, voice) cacheable; volatile (recent prose) not. Budget = configured token target.

---

## §3 Agent loop

V0 = co-writing (stream) only; **no autonomous planner** (the outline IS the plan). Light orchestration: RAG + stream + advisory critic.

### §3.1 Co-write loop (V0)
```
Trigger (Continue / selection tool + guide)
 → Retrieve  (packer §2)
 → Draft     (stream via /v1/llm/stream, operation=chat) → ghost in editor
 → Author    Accept / Edit / Regenerate
 → Critique  (advisory) — judge_prose on accepted text vs canon → flag inline
 → Commit    text → book chapter (book-service auto-save + revision)
 → Flywheel  approved chapter → existing extraction → graph → next-scene grounding;
             refresh outline_node.status + present_entity_ids (from extraction)
```
- `generation_job`: `pending → running(stream) → completed(accepted) / cancelled`.
- Critic is **advisory** in co-write (flags inline; never blocks) — U2 default.
- Selection tools (rewrite/expand/describe, V1) reuse this loop with a different `operation` + the selection as input.

### §3.2 Autonomous loop (V1 — reference)
`Plan → for each beat: [Retrieve → Draft(job) → Critique GATE → Revise ≤N → Commit]`; critic = **hard gate** (`canon_consistency` below threshold → revise). N takes/branches = N parallel `completion` jobs; progress streamed to FE via the WS gateway.

---

## §4 Prose-judge dimensions

Reuse the `loreweave_eval` harness (JudgeLLMClient via gateway · EvalResult · sink · calibration). New function **`judge_prose`** — same harness, new prompts (`judge_precision` scores "item vs source"; prose scores craft + canon-consistency).

| Dim | Question |
|---|---|
| **coherence** | logical flow; no non-sequiturs |
| **voice_match** | matches the POV voice profile (V1; V0 inferred/default) + work style |
| **pacing** | appropriate to the beat (tension / scene type) |
| **canon_consistency** ★ | does the passage break any active `canon_rule` / contradict present-state · timeline? |

★ differentiator. The canon check passes `{active rules, present-entity facts, passage}` → **per-violation verdict** `[{rule_id, violated, span, why}]` (same mechanism as `judge_precision`, for contradiction).

- Output → `generation_job.critic` `{coherence, voice_match, pacing, canon_consistency, violations[]}`, anchored to `target_revision_id`.
- Surfaced **inline** (continuity linter, NFR-8); persisted for human-correction **calibration**.
- **Co-write:** advisory display. **Autonomous (V1):** `canon_consistency` < threshold → gate fail → revise.

---

## §5 API contract

Gateway `/v1/composition/*` (catch-all proxy, like chat); contract-first → new `contracts/api/composition/v1/openapi.yaml` (additive). **Prose I/O goes FE↔composition (decision B):** composition exposes a thin **prose-source** that proxies book-service for canonical content — so the reused editor never reworks its backend when V1 adds sandbox branch/take prose. Generation / outline / canon / grounding = FE↔composition. JWT user-scoped; cross-user = 404.

**Work** (COMP-A2/A5):
- `GET /books/{book_id}/work` — resolve. **Prefers the book-typed project that has a `composition_work` row** (marker-by-presence); else `{candidates}` (>1 project) or `{none}`.
- `POST /books/{book_id}/work` — confirm-create (ensure book-typed project via knowledge `ProjectCreate`, then `composition_work`).
- `GET / PATCH /works/{project_id}` (If-Match).

**Prose (source proxy — decision B):**
- `GET / PUT /works/{project_id}/chapters/{chapter_id}/prose` — canonical content proxied to book-service (+ revisions). *(V1 adds `?variant=` / `?branch=` to serve sandbox take/branch prose from `scene_variant`.)*

**Outline / Scene Graph:**
- `GET /works/{project_id}/outline` (tree + scene_links).
- `POST /works/{project_id}/outline/nodes` · `PATCH / DELETE /outline/nodes/{id}` (If-Match).
- `POST / DELETE /works/{project_id}/scene-links`.

**Canon / Templates:** `GET/POST/PATCH/DELETE /works/{project_id}/canon-rules[/{id}]` · `GET /templates`.

**Engine:**
- `POST /works/{project_id}/generate` `{outline_node_id, operation, mode, guide, selection?}` → **budget pre-check** → streams tokens (co-write) → returns `job_id`. On budget exhaustion: stop + partial-save.
- `POST /works/{project_id}/scenes/{node_id}/suggest-cast` → AI-suggest `present_entity_ids` from beat/guide.
- `GET /jobs/{id}` · `POST /jobs/{id}/critique {target_revision_id}` → `judge_prose`.
- `POST /jobs/{id}/dismiss-violation {rule_id}` → mark a critic flag intended (feeds calibration).
- `GET /works/{project_id}/scenes/{node_id}/grounding` → packed-context preview (Grounding panel).

---

## §6 Sequence diagrams

### §6.1 Co-write a scene (core)
```
FE → gateway → composition POST /generate
  packer: ← knowledge (drawers/search · timeline?before_order=story_order · entity/relations)
          ← glossary (select-for-context) ← book (chapter via SceneAnchor) ← COMP DB (outline · canon)
  budget pre-check → composition → /v1/llm/stream(packed) → tokens → FE (ghost)
FE: Accept → composition prose-source PUT → book-service (canonical) + provenance mark
FE → composition POST /jobs/{id}/critique{revision} → judge_prose(gateway) → critic → FE inline
book-service: chapter approved → event → (existing) knowledge extraction → graph
  → next /generate grounding is richer   ← flywheel closed
```

### §6.2 Resolve / create a Work
```
FE open Composition tab → GET /books/{id}/work
  composition: pick book-typed project WITH a composition_work row
     found                        → return work
     1 book project, not yet a Work→ ensure composition_work → return
     no book project              → {none} → FE "create?" → POST /work → ProjectCreate + composition_work
     >1 marked                    → {candidates} → FE select
```

---

## §7 Benchmark outcomes — V0 limitations & risks (2026-06-02)

Stress-tested by scenario. **Applied inline:** `story_order` (§1, non-linear chronology) · L2′ planned-synopsis lens (§2) · resolve-prefers-marked + budget pre-check + `suggest-cast` + `dismiss-violation` (§5).

**V0 limitations (deferred, not bugs):**
- **Retroactive edits** — editing an early-chapter fact after later chapters exist does NOT re-validate downstream prose. A **"consistency sweep"** (re-run `judge_prose` on affected later chapters) = **V1**.
- **Voice drift** — V0 voice = best-effort (recent prose + critic flag); explicit `voice_profile` enforcement = **V1**.

**Design-carefully risk:**
- **`SceneAnchor` ↔ `outline_node` sync** under concurrent edits (the cost of sub-chapter granularity, D1=b): content-order is the source of truth for intra-chapter scene order; metadata uses version/If-Match — the reconciliation logic must handle both. BUILD covers this with care + tests.

---

## §8 V1 design

V1 = full studio + non-linear exploration. **Prose backend = decision B** (composition prose-source): canonical proxies book-service; sandbox take/branch prose lives in `scene_variant` — so the editor never reworks its data layer.

### §8.1 V1 schema (approved 2026-06-02)
```sql
-- branch: what-if sandbox (in-work fork that collapses)
CREATE TABLE IF NOT EXISTS branch (
  id                 UUID PRIMARY KEY DEFAULT uuidv7(),
  user_id            UUID NOT NULL,
  project_id         UUID NOT NULL,
  name               TEXT NOT NULL,
  divergence_node_id UUID NOT NULL REFERENCES outline_node(id) ON DELETE CASCADE,
  prompt             TEXT NOT NULL DEFAULT '',
  status             TEXT NOT NULL DEFAULT 'exploring' CHECK (status IN ('exploring','promoted','discarded')),
  judge_summary      JSONB,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- scene_variant: alternate prose — "takes" of a canonical scene AND prose of branch scenes
CREATE TABLE IF NOT EXISTS scene_variant (
  id              UUID PRIMARY KEY DEFAULT uuidv7(),
  user_id         UUID NOT NULL,
  project_id      UUID NOT NULL,
  outline_node_id UUID NOT NULL REFERENCES outline_node(id) ON DELETE CASCADE,
  branch_id       UUID REFERENCES branch(id) ON DELETE CASCADE,  -- NULL = a take of the canonical scene
  label           TEXT NOT NULL DEFAULT '',
  content         JSONB NOT NULL DEFAULT '{}'::jsonb,             -- TipTap doc (sandbox prose)
  critic          JSONB,
  is_selected     BOOLEAN NOT NULL DEFAULT false,                 -- selected take → promoted to book chapter
  source          TEXT NOT NULL DEFAULT 'ai' CHECK (source IN ('ai','human')),
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_scene_variant_node ON scene_variant(outline_node_id);
CREATE INDEX IF NOT EXISTS idx_scene_variant_branch ON scene_variant(branch_id) WHERE branch_id IS NOT NULL;

-- outline_node gains branch tagging (NULL = canonical)
ALTER TABLE outline_node ADD COLUMN IF NOT EXISTS branch_id UUID REFERENCES branch(id) ON DELETE CASCADE;
CREATE INDEX IF NOT EXISTS idx_outline_node_branch ON outline_node(branch_id) WHERE branch_id IS NOT NULL;

-- style / voice / references
CREATE TABLE IF NOT EXISTS style_profile (
  id UUID PRIMARY KEY DEFAULT uuidv7(), user_id UUID NOT NULL, project_id UUID NOT NULL,
  name TEXT NOT NULL, params JSONB NOT NULL DEFAULT '{}'::jsonb,   -- density, pace, interiority, tone…
  is_active BOOLEAN NOT NULL DEFAULT false,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS voice_profile (
  id UUID PRIMARY KEY DEFAULT uuidv7(), user_id UUID NOT NULL, project_id UUID NOT NULL,
  entity_id UUID,                                                  -- → glossary (POV character/narrator)
  traits JSONB NOT NULL DEFAULT '{}'::jsonb, samples JSONB NOT NULL DEFAULT '[]'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS reference_source (
  id UUID PRIMARY KEY DEFAULT uuidv7(), user_id UUID NOT NULL, project_id UUID NOT NULL,
  title TEXT NOT NULL, kind TEXT NOT NULL DEFAULT 'comp', content TEXT NOT NULL DEFAULT '',
  embedding_model_ref TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- generation_run: groups autonomous per-scene jobs for a chapter/arc run (§8.3)
CREATE TABLE IF NOT EXISTS generation_run (
  id UUID PRIMARY KEY DEFAULT uuidv7(), user_id UUID NOT NULL, project_id UUID NOT NULL,
  target_node_id UUID REFERENCES outline_node(id) ON DELETE SET NULL,   -- chapter/arc to write
  mode TEXT NOT NULL DEFAULT 'auto',
  status TEXT NOT NULL DEFAULT 'running' CHECK (status IN ('planning','running','paused','completed','failed','cancelled')),
  progress JSONB NOT NULL DEFAULT '{}'::jsonb,   -- {scenes_total, scenes_done, scenes_failed}
  cap JSONB NOT NULL DEFAULT '{}'::jsonb,         -- {max_scenes, max_cost_usd}
  cost_usd NUMERIC(10,4) NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE generation_job ADD COLUMN IF NOT EXISTS run_id UUID REFERENCES generation_run(id) ON DELETE SET NULL;
```

### §8.2 Fork engine (what-if branch + alternate takes)

**Alternate takes** (one scene, N executions): generate N = N parallel `completion` jobs → N `scene_variant` (branch_id=NULL) → each judged → author compares → select one → `is_selected`, content → book chapter (via prose-source); prune the rest.

**What-if branch** (divergent downstream): from `divergence_node` + "what if X?" → a `branch` row + AI generates `outline_node`(branch_id=B) + prose (`scene_variant` branch_id=B); each branch scene judged; `judge_summary` aggregates (esp. canon-consistency vs the work's canon).

**Branch grounding = packer COW-merge (branch mode):**
```
ground a branch scene = canonical graph/canon ≤ divergence_node.story_order
                      + branch's own prior scenes (read from scene_variant — sandbox, NOT extracted to the real graph)
```
→ **Two COW-merge modes, designed once:** branch delta = raw `scene_variant`; derivative (V2) delta = real delta-graph. (Unifies branch ↔ derivative.)

**Lifecycle:** **Promote (collapse)** `status=promoted` → branch scenes replace canonical from the divergence point (canonical downstream archived · `outline_node.branch_id→NULL` · content → book chapters via prose-source) · **Discard** archived · **→ 同人 (V2 bridge)** "promote-as-derivative" → seed `derivative_work` from the branch delta.

**Takes = a degenerate branch** (one scene, no downstream) — same engine, judge, and prune-lifecycle (avoids History-card rot, the Sudowrite lesson).
### §8.3 Autonomous loop (generator–critic–revise, hard gate)

V0 = co-write (human in loop). V1 auto = AI drafts whole scenes/chapters with the critic as a **hard gate**.

**Planner (new agent):** target (chapter/arc) + outline + template → generates/refines the beat→scene plan (`outline_node`: beat/goal/present_entities/synopsis); drafts the outline if empty. **Human checkpoint:** review/edit the plan before drafting. (Reuses the extraction structured-output pattern.)

**Per-scene loop:**
```
for each scene in order:
  Retrieve (packer §2)
  Draft    (completion JOB, not stream)
  Critique (judge_prose) — GATE:
     canon_consistency < threshold (or coherence too low)
        → Revise: re-draft with the violation injected as a hard constraint, ≤ N times
        → still failing after N → flag human + skip/stop
  Commit (pass) → book chapter (prose-source) → flywheel → next-scene grounding richer
```

**Run grouping:** `generation_run` (§8.1) groups the per-scene child `generation_job`s (`run_id`); tracks `progress`, `cap` (max_scenes/max_cost), `cost`. Progress → FE via WS gateway (`job.chapter_done`/`status`), like translation jobs.

**Checkpoints (U3, configurable):** per-scene gate · **per-chapter review (default)** · fully-auto-review-after. **Budget:** pre-check + per-run cap; stop on cap.

**vs co-write:** co-write `Retrieve→Draft(stream)→human accept→Critique(advisory)`; auto `Plan→[Retrieve→Draft(job)→Critique GATE→Revise≤N→Commit]→human checkpoint`.
### §8.4 Style / voice / references — integration

**Authoring:** `style_profile` (active per work; sliders density/pace/interiority/tone) · `voice_profile` (per POV entity; traits + samples; **AI-suggest** = analyze existing prose → infer voice, à la NovelCrafter) · `reference_source` (comps + sample passages; embedded via knowledge embedding infra for semantic retrieval).

**Into the PACKER (extends §2.4 assembly):**
```
<style>   active style_profile.params
<voice>   POV's voice_profile (traits + 1-2 samples)   ← POV scene only
<lore>    + reference_source retrieved (extends L4: "influences", never copied)
```
Stable parts (style, voice) are **cacheable** (rarely change) — good for prompt cache.

**Into the CRITIC (§4):** `voice_match` scores output vs `voice_profile` (traits + samples) + style. V0 used inferred/recent-prose voice; V1 uses explicit `voice_profile` → **closes V0-limit G6 (voice drift)**.

`voice_profile.entity_id` → glossary character; a POV change pulls that character's voice; derivative (V2) POV-shift overrides map here too. → 3 new prompt sources + 1 critic input, no new mechanism.
### §8.5 Layout / composability engine

Studio's dock/float/pop-out system. **Server = truth; layout = per-device UI.**

**FE:** **PanelManager** (hook/context) — registry of panels (Co-writer/Grounding/Critic/Outline/Canon/Cast/Threads/Style…) + placement + dock/float/pop-out; extends `useEditorPanels` from 2 panels → N tabs. **Panel registry** — each declares `id`/`title`/`default-dock`/`can-popout`. **Views** (Scene Graph/Timeline/Beat Sheet) = opt-in full-width overlays, separate from panels.

**Pop-out (multi-window):** standalone route `/composition/panel/{type}?work={id}` renders one panel in a new window. **Sync** = server state (same composition API) **+** `BroadcastChannel('composition:{workId}')` for soft selection/context only. Server authoritative; conflicts → optimistic If-Match (§1). **Persist** layout → localStorage per-device (NFR-4). **BE impact ≈ zero** (pop-out calls existing APIs; selection sync is client-side).
### §8.6 Consistency sweep (closes V0-limit G3 — retroactive edits)

**Trigger** (canon changes): chapter edit/re-extract changes a fact · `canon_rule` added/edited · entity correction · **branch promote** (VS1).
**Scope — CRITICAL (avoid cost-bomb, VS7):** re-validate ONLY scenes whose grounding *depended on* the changed item = scenes with the changed entity in `present_entity_ids` **or** mentioning it, **and** `story_order ≥` the change. **Never sweep the whole book.**
**Re-validate:** `judge_prose` (canon-consistency dimension only — cheap) on affected scenes vs the NEW canon → flag.
**Run:** `generation_run(mode='sweep')` + `generation_job(operation='canon_check')`; async, budget-capped.
**Surface:** consistency report (chapters with new contradictions) → author fixes (manual / AI-rewrite).

### §8.7 V1 benchmark

| # | Scenario | Verdict | Handling |
|---|---|---|---|
| VS1 | Promote a branch replacing scenes 3–5; canonical scene 6 referenced something the branch changed | **fold** | promote **triggers a consistency sweep** on canonical scenes after the branch range (§8.6) |
| VS2 | Autonomous gate fails N times | PASS | N-cap → flag human + stop; no budget burn |
| VS3 | Generate 5 takes, keep 1 | PASS | cheap multiplicity + budget cap + prune-lifecycle |
| VS4 | Long branch — later branch scenes ground on raw `scene_variant` (sandbox, un-extracted) | **LIMIT** | branch grounding degrades when long → nudge "promote / spin-off to 同人 past ~K scenes" |
| VS5 | POV switch mid-chapter (2 POVs) | PASS | voice is per-scene-POV |
| VS6 | Pop-out a panel, close the main window | PASS | popped-out still works (server state); loses selection sync only |
| VS7 | Sweep after editing Ch.2 of a 200-chapter book | **fold** | sweep MUST be dependency-scoped (§8.6), not whole-book |

**Folded:** VS1 → promote triggers sweep · VS7 → scoped sweep (§8.6) · VS4 → V1-limit "long branch → promote/spin-off".

---

## §9 V2 design (同人 / derivative)

Architecture in [vision §9](2026-06-02-composition-service-vision.md) + UX in [studio-ux §7](2026-06-02-composition-studio-ux.md). This adds DDL + the packer's 3rd mode + benchmark.

### §9.1 V2 schema
```sql
-- a derivative = its own Work (own project+book → own composition_work) pointing at the source
ALTER TABLE composition_work ADD COLUMN IF NOT EXISTS source_project_id UUID;                                  -- NULL = original
ALTER TABLE composition_work ADD COLUMN IF NOT EXISTS divergence_spec   JSONB NOT NULL DEFAULT '{}'::jsonb;     -- {branch_point, pov_anchor, au_template}

CREATE TABLE IF NOT EXISTS entity_override (
  id               UUID PRIMARY KEY DEFAULT uuidv7(),
  user_id          UUID NOT NULL,
  project_id       UUID NOT NULL,                 -- the derivative's project
  source_entity_id UUID NOT NULL,                 -- → source glossary entity
  field            TEXT NOT NULL,                 -- gender | name | alignment | pronoun | ...
  new_value        JSONB NOT NULL,
  kind             TEXT NOT NULL CHECK (kind IN ('genderbend','dark_turn','role_reversal','attribute','pov')),
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_entity_override_project ON entity_override(project_id);
```

### §9.2 Packer — 3rd mode (2-layer COW)
The packer now has **3 modes, one shape** (`base + delta [+ overrides]`):
- **canonical** (V0) — one project graph.
- **branch** (V1) — canonical + branch `scene_variant` delta (raw prose).
- **derivative** (V2) — `source-graph(≤ branch_point.story_order)` **with `entity_override` applied** + the derivative's own project graph (delta).
Override applied **at retrieve** (fetch source entity → apply override). Cache the read-only source layer.

### §9.3 V2 benchmark
| # | Scenario | Verdict | Handling |
|---|---|---|---|
| DS1 | "Kael→female" + a relation "Kael is *son* of X" | **LIMIT** | override is attribute-level; gendered relations/cascades = **AI rewrite at gen** (vision §9.4), not auto |
| DS2 | Original edits a PRE-branch fact after the derivative forked | **NOTE** | COW reads source live ≤ branch → pre-branch edits flow into the derivative base (offer "snapshot-at-fork" later) |
| DS3 | Derivative's own flywheel | PASS | derivative = own project → own graph; its chapters extract into IT |
| DS4 | Delete a source that has derivatives | **fold** | **block source deletion** while derivatives reference it |
| DS5 | 2-layer retrieval cost | PASS | bounded; cache read-only source layer |

**Folded:** DS4 → guard source deletion.

---

## §10 Full-design cross-version review (2026-06-02)

V0 + V1 + V2 compose without contradiction:
- **Packer unification holds** — 3 modes are one shape (`base + delta [+overrides]`). **Finding:** design the packer as an **N-layer merge** (a stack of layers, each optionally overridden), *not* hardcoded 2-layer — so a **what-if branch *inside* a derivative** (source+override + derivative-delta + branch-delta) composes. (Branches/takes are per-project → derivatives, being Works, inherit the full V1 toolkit.)
- **One judge** (`judge_prose`) across V0 critic / V1 gate+sweep / V2 derivative — always scores against "the effective canon the packer assembled" → no per-mode special-casing.
- **One job model** (`generation_job`/`generation_run`) across co-write / auto / sweep / branch / take / derivative (modes + operations).
- **prose-source (B)** serves canonical (book) + sandbox (`scene_variant`) + derivative (own book) uniformly → editor stays uniform.
- **Flywheel** consistent: V0 book→graph · branch sandbox (no extract) · derivative own-book→own-graph.
- **Forward-compat verified:** V0 `story_order` → V1 `branch_id` → V2 `entity_override`/`source_project_id` layer cleanly; no V0 schema rework.

**Net:** one engine (packer **N-layer merge** + judge + flywheel + studio) parameterized across canonical / branch / derivative. Design is internally consistent.

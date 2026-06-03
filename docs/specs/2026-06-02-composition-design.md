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
  base_revision_id   UUID,                                -- book-chapter revision the draft was GROUNDED on (accept-staleness guard, OI-2)
  target_revision_id UUID,                                -- book-chapter revision the critic scored (anti-staleness)
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

> **Entity-id stability rule (§13 DI3, verified).** Always store the **glossary `entity_id`** (a stable uuidv7 — glossary has no destructive merge and no id-redirect; delete is a reversible soft-delete). **Never** store the knowledge-service `canonical_id` — it is content-hash-derived and **changes on entity rename**. Resolve knowledge↔glossary via the knowledge entity's stable `glossary_entity_id` anchor. A held id that stops resolving = **soft-absent** (entity trashed): the packer skips it gracefully, it is never an integrity error.

### §1.5 Forward-compat (V1/V2 — schema already leaves room)
- **V1 non-linear:** add `branch_id UUID` to `outline_node` (NULL = canonical); new `scene_variant` (FK `outline_node`, holds alternate prose for takes); `style_profile`/`voice_profile`/`reference_source`.
- **V2 同人:** `derivative_work(source_work_id, divergence_spec)` · `entity_override` · 2-layer COW retrieval merged in the packer (no knowledge-service change, per COMP-A6).

---

## §2 RAG packer (generation retrieval core)

Assembles **constraint-shaped** context for one target scene (`outline_node`). Runs in COMP (per COMP-A6 — self-pack); all reads reuse existing HTTP surfaces; the orchestration + budget policy is the new module.

### §2.1 Lenses
> **⚠️ Contract reality-check (§12, 2026-06-03).** L1/L4/L5 were re-spec'd after verifying the ACTUAL knowledge-service handlers (the design's original assumptions were wrong — exactly the enrichment "trust-the-doc" bug class). Verified facts: **timeline** carries `chronological_order` + accepts `before_chronological`/`before_order` (true in-world cutoff ✅); **relations** carry only wall-clock `valid_until` datetime, NOT narrative order ❌; **drawers/search** hits carry NO `chronological_order` and `chapter_index` is `None` on the prod ingest path ❌ (only `source_id`=chapter UUID); **hierarchical summaries are NOT served over HTTP** ❌ (only L0/L1 free-text bios). The lens table below reflects what is actually buildable.

| Lens | Content | Source | Spoiler axis |
|---|---|---|---|
| **L0 Canon** | active `canon_rule` applying at the scene position (`from_order ≤ pos ≤ until_order`) + world rules | COMP DB | in-world `story_order` (COMP-owned) |
| **L1a Present state** | each `present_entity_ids` + POV → entity current state + **currently-valid** 1-hop relations (`valid_until IS NULL`) | knowledge `entities/{id}` | *not* chrono-filterable (relations are wall-clock only) — see §2.2 |
| **L1b Timeline** ★ | in-world events touching the scene's entities, `chronological_order ≤ story_order` | knowledge `timeline?before_chronological=` | **in-world (true cutoff) ✅** — the real spoiler-safe event source |
| **L2 Structural** | beat purpose (template) + goal + POV + synopsis + `setup_payoff` threads touching the scene | COMP DB | — |
| **L2′ Planned** | synopses of *unwritten* scenes ≤ position — so non-linear / out-of-order drafting has planned context, not just extracted facts | COMP DB (`outline_node.synopsis`) | — |
| **L3 Recent prose** | last K paragraphs before the scene (prev-scene tail / chapter-so-far) | book chapter content (via `SceneAnchor`) | reading-order (local) |
| **L4 Semantic refs** | relevant lore/style passages | knowledge `drawers/search` (`project_id` REQUIRED) | **reading-order approximation** — resolve hit `source_id`→book-service chapter `sort_order`; drop hits from chapters at/after the scene's reading position. NOT in-world (flashback residual, §2.2). Requires the knowledge-ingest `chapter_index` fix (§12 / plan §4). |
| **L5 Long-term** | hierarchical chapter/part/book summaries (anti-drift) | knowledge summaries / `summarize_level` | **DEFERRED — not exposed over HTTP.** `summarize_level` is a job-only write; no public read route exists. V0 ships without L5; revisit when a knowledge summaries read-endpoint exists (separate touch-point from the `chapter_index` fix). |

### §2.2 Spoiler cutoff — TWO axes, both populated by the Canon Model (revised §12→Canon Model, 2026-06-03)

> **Update:** the original "one cutoff via `before_order`" was found inert — verification (§12) showed `chronological_order`/`event_order` are **never written** (NULL ~100%), so `before_chronological=story_order` matched zero events (a no-op that *looked* spoiler-safe). The durable fix is the **Canon Model prerequisite (Cycle 0, Primitive 3)**: it **populates both order axes** — `event_order`/`reading_order` from chapter `sort_order`, and `chronological_order` ranked from the already-extracted `event_date_iso`. So once Cycle 0 lands, BOTH axes below are real (the earlier "reading-order approximation only / flashback residual" caveat is **lifted** — in-world flashback-safety becomes genuine, bounded by `event_date_iso` quality). Composition does NOT build the order population itself; it consumes the Canon Model primitive.

The spoiler guard is **two-axis** — and honest about which lens enforces which:

- **In-world axis (true cutoff) — L1b Timeline + L0 Canon.** `timeline?before_chronological=story_order` filters events to in-world chronology (verified: `chronological_order` on every Event, strict `<` predicate). A Ch.12 **flashback** with a low `story_order` correctly sees only events up to that in-world moment (non-linear / dual-timeline safe). L0 `canon_rule` uses COMP-owned `from_order/until_order` on the same axis. **This is the real spoiler-safety guarantee.**
- **Reading-order axis (approximation) — L3 + L4.** Prose passages (recent prose L3, semantic refs L4) have NO in-world chronology in the KG — a passage only knows its **chapter** (`source_id`). So L4 filters by **reading-order**: resolve `source_id`→book-service chapter `sort_order`, drop any hit from a chapter at/after the scene's reading position. **Residual (documented, not a bug):** for a flashback scene (low `story_order`, high reading position) this is *more permissive* than in-world — it admits prose from earlier-written chapters that are in-world-future. V0 accepts this; closing it would need per-passage in-world tagging at extraction (knowledge-service work, deferred).
- **L1a relations are NOT chrono-filtered.** Relations carry only wall-clock `valid_until` (write timestamp), not narrative order — so L1a contributes *currently-valid* state (`valid_until IS NULL`) and the in-world cutoff is delegated to L1b events. Do not pretend relations are spoiler-filtered.

> **Semantic-lens spoiler guard (OI-A2, revised).** `drawers/search` (L4) returns no chronological cutoff and COMP cannot add a param (COMP-A6). The fix has **two halves**: (1) a **knowledge-service ingest fix** (thread chapter `sort_order` into `chapter_index` at `chapter.saved` ingest — currently dropped at `handlers.py:237`; reclassifies the slice as touching knowledge-service, plan §4); (2) COMP **post-filters** every L4 hit by resolving its `source_id`→chapter reading position and dropping hits at/after the scene's chapter. **Conservative-drop + LOG** on any hit missing position (so a dead filter is *visible*, not silent — the enrichment "inert check / no-silent-caps" lesson). Without (1), every hit lacks position → conservative-drop empties L4 → log surfaces it as `l4_dropped_no_position=N` rather than a silent no-op. *(V2 derivative: also ≤ `branch_point`.)*

### §2.3 Priority ladder (budget trim — drop lowest first)
- **Never drop:** L0 canon · L1a core state · L1b in-window events · L2 beat/goal · L3 immediate-preceding prose.
- **Drop order:** L4 refs → ~~L5 summaries~~ *(L5 deferred — not exposed)* → L2 stale threads → L1a 2-hop relations → L1b older events → L3 older prose.
- Mirrors knowledge `_enforce_budget` but with a **generation** priority (canon-first), not Q&A.

### §2.4 Assembly (structured prompt)
`<canon>` (hard constraints) · `<present>` (who + state) · `<threads>` (open setups due) · `<beat goal POV synopsis>` · `<recent>` (last K paras) · `<lore>` · `<memory>` · `<guide>` (author steer).

> **Injection guard (§13 SEC3).** `<lore>` (retrieved passages) and `<guide>` (author free-text) are **untrusted input** — extracted/imported prose can carry "ignore instructions…" payloads. Sanitize both before assembly (neutralize/tag, the enrichment `sanitize.py` tag-not-delete pattern; bound `<guide>` length). Easy to miss because the lore is "ours", but it originates from arbitrary book text.

### §2.5 Runtime
Parallel gather of lenses with per-lens timeout + graceful degrade (mirrors `app/context/modes/full.py` `_safe_*`). Stable parts (canon, beat, voice) cacheable; volatile (recent prose) not. Budget = configured token target.

**Isolation invariant (OI-A1).** EVERY lens read is scoped by `project_id` (+ `user_id`) — no global/unscoped semantic search (a cross-project `drawers/search` would leak another Work's lore). **Mode purity:** canonical-mode reads `branch_id IS NULL` strictly; sandbox `scene_variant` enters only in branch mode (V1). A canonical pack must never include sandbox prose.

> **A1 sharpening (§12).** Verified: `drawers/search` *requires* `project_id` (safe), but `timeline` + `entities-browse` make `project_id` **optional** — omitting it returns rows across **every project the user owns** (cross-PROJECT, same user). So the isolation invariant is not just "don't search globally" — `assemble.py` MUST **assert `project_id` is present and non-null on every lens call** (a chokepoint assertion, the enrichment Q3-scoping lesson), not trust the endpoint default.

> **Ownership chokepoint (§13 SEC2).** The glossary/knowledge **internal** read surfaces (`select-for-context`, `entities`, …) are **book-scoped ONLY — they do NOT re-check the user** (`X-Internal-Token` trust; verified). So composition MUST verify the JWT user owns the `book_id`/`project_id` **before** issuing any internal read. The internal token is a service-trust boundary, NOT a per-user authz boundary — without the upfront check, a crafted request reads another user's lore.

### §2.6 Book profile / language threading (de-bias — bake in from M0)

**Lesson (lore-enrichment, paid over 3 XL de-bias cycles):** a generation+verify pipeline silently inherits the *demo book's* universe (language/era/genre/entity-kind) unless worldview is an explicit per-book object threaded everywhere. The fix pattern: a `BookProfile` with a **NEUTRAL default** that a missing row resolves to (never raises), threaded through ONE context object into every prompt builder + judge + resolver. Composition is a *prose generator* — the highest-exposure surface for this bug (English illustrative phrases in a prompt bias a CJK/VN draft to English; a genre-assuming judge mis-scores voice). We build it in from day one instead of retrofitting.

- **Shape (V0, lives in `composition_work.settings`):** `{ source_language (default 'auto' → resolved per-book from book-service, like enrichment `_book_language`), voice (free text, V0 default ''), structure_pref (active template kind), tone/density hints }`. NEUTRAL = `source_language='auto'` + no voice + generic template.
- **Threaded into:** (1) the **draft prompt** (§3.1) — language + voice + structure instructions; assembly blocks (§2.4) stay structural, the *wrapper* carries language; (2) **`judge_prose`** (§4) — `voice_match` + `coherence` prompts must judge in `source_language`, never assume English; (3) any structured-output instruction.
- **Rule:** NO English-only illustrative phrases in any multilingual prompt (memory: "English illustrative phrases bias CJK summary to English"). Use abstract phrasing or symmetric multilingual examples.

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
 → Flywheel  **reviewed** chapter → existing extraction → graph → next-scene grounding;
             refresh outline_node.status + present_entity_ids (from extraction)
```
- `generation_job`: `pending → running(stream) → completed(accepted) / cancelled`.
- Critic is **advisory** in co-write (flags inline; never blocks) — U2 default.
- **Canonization gate (OI-1).** The flywheel fires the authoritative graph extraction on chapter **review-state** (`outline_node.status='done'` / AI-unreviewed provenance marks cleared), **NOT** on bare accept. **Accept ≠ canon; human review = canon** — otherwise a fabricated fact in accepted-but-unread AI prose is extracted as ground truth, then the critic *enforces* it forever (defends its own hallucination). Richer fact-provenance tiers (author_declared > human_prose > ai_provisional, with provisional-fact contradictions scored soft) = **V1**.
- Selection tools (rewrite/expand/describe, V1) reuse this loop with a different `operation` + the selection as input.
- **Token metering (enrichment `complete.py` lesson).** The budget pre-check (§5) + cost display harvest the **real `usage` SSE frame** from `/v1/llm/stream`; treat an **absent OR zero** frame as "not measured" → fall back to an over-estimating char model + clamp counts ≥0. Never meter a stream as 0 tokens (silently weakens the cap).
- **Best-effort cross-store on accept (memory `cross_store_best_effort_writes`).** Accept = book-chapter PUT (authoritative, If-Match per OI-2) + provenance mark + outbox emit. The **book write is authoritative**; the outbox emit + any sister-store write are best-effort `try/except` — their failure must NOT 500 an otherwise-saved accept.

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
- **Judge-prompt language (§2.6):** all four dims judge in the book's `source_language`; `voice_match` reads the work profile/`voice_profile` (V1). Never English-default the rubric.
- **Anti-self-reinforcement (§12, enrichment LE-056 lesson).** The critic must NOT be the same model that drafted — a model rubber-stamps its own `canon_consistency`. **V0:** critic uses a distinct model/config from the drafter (advisory, so single-judge is acceptable but still a different model). **V1 hard gate:** the `canon_consistency` gate requires ≥2 judges from **≥2 distinct model families** (case-normalized) + a κ floor before it may *block* — reuse `loreweave_eval`'s `JudgeSpec.family`/`family_key` + the ensemble-acceptable rule, do not invent a new mechanism.
- **Schema tolerance (enrichment `repair.py` lesson).** `judge_prose` returns `violations[] = [{rule_id, violated, span, why}]`. Parse **tolerantly**: deterministic repair (strip fences, extract balanced JSON) + per-item Optional + **filter at postprocess** — one malformed verdict must not discard the whole critique. Never strict-reject the batch.

---

## §5 API contract

Gateway `/v1/composition/*` (catch-all proxy, like chat); contract-first → new `contracts/api/composition/v1/openapi.yaml` (additive). **Prose I/O goes FE↔composition (decision B):** composition exposes a thin **prose-source** that proxies book-service for canonical content — so the reused editor never reworks its backend when V1 adds sandbox branch/take prose. Generation / outline / canon / grounding = FE↔composition. JWT user-scoped; cross-user = 404.

**Work** (COMP-A2/A5):
- `GET /books/{book_id}/work` — resolve. **Prefers the book-typed project that has a `composition_work` row** (marker-by-presence); else `{candidates}` (>1 project) or `{none}`.
- `POST /books/{book_id}/work` — confirm-create (ensure book-typed project via knowledge `ProjectCreate`, then `composition_work`).
- `GET / PATCH /works/{project_id}` (If-Match).

**Prose (source proxy — decision B):**
- `GET / PUT /works/{project_id}/chapters/{chapter_id}/prose` — canonical content proxied to book-service (`chapter_drafts` content + `chapter_revisions`). **`PUT` MUST carry `expected_draft_version`** (read from the prior `GET`) → book-service returns 409 `CHAPTER_DRAFT_CONFLICT` on a concurrent edit (§11 OI-2 / §13 PS2); composition treats the field as mandatory even though book-service allows omitting it. *(V1 adds `?variant=` / `?branch=` to serve sandbox take/branch prose from `scene_variant`.)*

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

---

## §11 Operational & integrity benchmark (2026-06-02)

§7–§10 stress-tested the **creative/structural** axis (chronology, out-of-order grounding, COW-merge composition). This pass exercises three untested **operational/integrity** classes: flywheel integrity, concurrency/multi-device, cross-work isolation. **Applied inline:** OI-1 review-gate (§3.1) · OI-2 `base_revision_id` (§1.2) · A1 isolation invariant (§2.5) · A2 semantic spoiler-filter (§2.2).

| # | Class | Scenario | Verdict | Handling |
|---|---|---|---|---|
| **OI-1** | Flywheel | AI fabricates a fact in prose; author bulk-accepts without reading → extraction canonizes it → critic then **enforces** the hallucination on every later scene (defends its own error) | **STRUCTURAL via Canon Model** | ~~gates on `status=done`~~ — review (§12/§13) verified there is no draft/published distinction and extraction fires on *every* draft save, so a feature-level gate was impossible. **Resolved by the Canon Model prerequisite (Cycle 0, [canon-model spec](2026-06-03-canon-model.md)):** accept → `draft` chapter (no canonization); review/done → **publish** → `chapter.published` → extraction. "Accept ≠ canon; publish = canon" is now a data-model invariant. Provenance tiers = Canon Model Primitive 4 (composition slice). **Publish granularity = chapter-gate (sweep §13.x):** book-service publishes per-CHAPTER but composition reviews per-SCENE → composition enables "publish chapter" **ONLY when ALL its scenes are `status='done'`** (so no unreviewed scene is canonized — OI-1 holds intra-chapter). Next-scene context within an unpublished chapter comes from **L3 recent-prose + L2′ planned-synopsis** (no graph needed); the graph flywheel is per-chapter. |
| **OI-2** | Concurrency | Co-write streams into Ch.X grounded on revision R; another device edits Ch.X → R′; author accepts → blind PUT clobbers the concurrent edit (violates server-SSOT/multi-device) | **fold V0** | `generation_job.base_revision_id` = grounding revision (§1.2). **Mechanism (corrected §13): book-service uses a body field `expected_draft_version` (BIGINT on `chapter_drafts`) → 409 `CHAPTER_DRAFT_CONFLICT`, NOT HTTP If-Match.** The field is OPTIONAL server-side (→ blind clobber if omitted), so composition's prose-source **always reads current `draft_version` and echoes it as a MANDATORY `expected_draft_version`**; mismatch → 409 → conflict surface (re-ground/merge), never blind overwrite. Streamed ghost tokens stay editor-local — excluded from the (client-side; no server autosave exists) autosave until accepted. |
| **OI-3** | Concurrency | Two devices reorder scenes / split a SceneAnchor / edit the same node concurrently | **PASS** | LexoRank `rank` (concurrent inserts → distinct ranks) + If-Match on node metadata + content-order-wins for anchors (§7 risk). No new mechanism. |
| **A1** | Isolation | Work-A's packer issues an unscoped `drawers/search` → returns Work-B's lore; or a canonical pack pulls sandbox `scene_variant` | **fold V0** | Isolation invariant (§2.5): every lens read `project_id`(+`user_id`)-scoped; canonical mode reads `branch_id IS NULL` strictly. |
| **A2** ★ | Isolation | Spoiler-cutoff holds for L1/L5 but **L4 semantic search has no chronological filter** → retrieves a future-chapter lore drawer → spoiler leak through the headline feature | **fold V0** | COMP post-filters L4/L5 hits by source `chronological_order ≤ story_order`; missing-position → conservative drop (§2.2). Can't add a param to `drawers/search` (A6) → filter COMP-side. |
| **A3** | Isolation | 同人 forks **another user's** shared work → derivative packer reads cross-user source prose | **defer V2** | V2 guard: derivative source MUST be same-user; cross-user public-work forks gated by sharing-service visibility (later). |
| **A4** | Isolation | Long branch / promote leaks sandbox prose into the canonical graph via the flywheel | **defer V1** | Covered by A1 mode-purity (canonical reads `branch_id IS NULL`; sandbox never extracted, §8.2). Re-verify at V1 build. |

**Folded into V0:** OI-1 (review-gate the flywheel) · OI-2 (accept-staleness + ghost-not-autosaved) · A1 (isolation invariant) · A2 (semantic spoiler-filter). **Deferred guards:** A3 (V2 same-user source) · A4 (V1 re-verify sandbox isolation).

**Sharpest finding = A2.** Spoiler-safety is the differentiator, and the *semantic* lens was the one place the cutoff didn't reach — exactly the kind of architectural hole that is cheap to close now and expensive after the packer ships. Benchmark goal met.

---

## §12 Architecture review — bug-classes ported from lore-enrichment + contract reality-check (2026-06-03)

The sibling **lore-enrichment-service** reached its current design by benchmarking and fixing a set of recurring bug **classes** (not one-off bugs). This review maps each class onto composition's design and verifies the load-bearing assumptions against the **actual** knowledge-service handlers (two sub-agents read the real code; findings are file:line-grounded). Composition had already proactively folded several enrichment-class lessons (OI-1, OI-2, A1, the A2 *intent*); this pass corrects the ones that rested on unverified contracts and bakes in the de-bias lesson from day one.

### §12.1 Verified knowledge-service contracts (the reality the packer must build on)
| Capability | Design assumed | **Verified reality** | Effect |
|---|---|---|---|
| `drawers/search` hit position | hit carries `chronological_order` | **No chrono field; `chapter_index` is `None` on the prod ingest path** (`handlers.py:237` drops the `sort_order` it already fetched). Only `source_id`=chapter UUID. | A2 as designed = inert → re-spec'd (§2.2): reading-order via book-service + a knowledge-ingest fix |
| `timeline` cutoff | `before_order` | **`before_chronological` + `before_order` both exist** (`timeline.py:64,80`), true in-world | L1b is the real spoiler-safe lens (§2.1) |
| relation temporal filter | `valid_until ≤ cutoff` (narrative) | **`valid_until` is wall-clock datetime, not narrative order** | L1a = currently-valid only; cutoff delegated to L1b (§2.2) |
| hierarchical summaries | readable (`summarize_level`) | **Not served over HTTP** (job-only write) | L5 deferred (§2.1) |
| scoping | project-scoped | drawers requires `project_id`; **timeline/entities widen to all-projects if `project_id` omitted** | A1 must assert `project_id` at the chokepoint (§2.5) |

### §12.2 Bug-class → composition exposure → fix
| # | Class (enrichment paid for it) | Composition exposure | Folded fix |
|---|---|---|---|
| C1 | **Built-but-not-wired / inert check, fail-open** (contradiction check gated on a JWT read the worker ran as `jwt=""` → always degraded; `_canon_lookup=[]`) | **A2 spoiler-filter** — the headline differentiator — rested on a field that doesn't exist → would silently contribute nothing | §2.2 two-axis cutoff + **knowledge-ingest `chapter_index` fix** (plan §4) + **conservative-drop + LOG** (`l4_dropped_no_position`) so a dead filter is visible. Spoiler-safety **fails closed**. |
| C2 | **Hardcoded universe** (封神/商周/中文/地点; 3 XL de-bias cycles) | Composition *generates prose* — highest exposure; no profile/language threading in the original design | §2.6 **`BookProfile` + `source_language` threaded from M0** into draft + judge + assembly; NEUTRAL default; no English-only illustrative phrases |
| C3 | **Cross-service contract drift** (glossary EAV vs authored column; gateway `messages[0].content`) | L1/L4/L5 all assumed wrong shapes | §12.1 + §2.1 re-spec from real handlers; read keys with fallbacks at the client boundary |
| C4 | **Anti-self-reinforcement / judge diversity** (LE-056: ≥2 families + κ floor) | `judge_prose` critic could be the drafting model rubber-stamping itself; V1 makes it a hard gate | §4 critic ≠ drafter (V0); V1 gate reuses `loreweave_eval` family+κ |
| C5 | **Token metering real-not-estimate** (harvest usage frame; absent/zero → over-estimate; clamp ≥0) | §5 budget pre-check could meter 0 on a missing frame → weak cap | §3.1 reuse `complete.py` pattern |
| C6 | **LLM schema tolerance** (repair + Optional + filter, not strict-reject-batch) | `judge_prose` `violations[]` strict-parse kills critique on one bad item | §4 tolerant parse |
| C7 | **Isolation / IDOR scope-drift** (Q3) | timeline/entities widen cross-project if `project_id` omitted | §2.5 chokepoint assertion |
| C8 | **Best-effort cross-store needs try/except** | accept = book PUT + provenance + outbox; emit failure could 500 a saved accept | §3.1 book-write authoritative, emit best-effort |
| C9 | **Stale-image / multi-image deploy** (F-LIVE-1 ×3) | composition adds service **+ worker** | plan §4: build BOTH images via `scripts/build-stack.sh` + freshness guard |

### §12.3 Decisions (PO, 2026-06-03) — superseded by the Canon Model (see §12.4)
- ~~**Spoiler-scope:** fix knowledge-service ingest (thread `sort_order`→`chapter_index`).~~ → folded into the broader Canon Model prerequisite (§12.4).
- **L5** deferred until a knowledge summaries read-endpoint exists (separate future touch-point).
- **De-bias** baked in from M0 (do not pay enrichment's retrofit tax).
- Boundary: composition touches only its own files + additive infra; the cross-service canon work lives in the **Canon Model** spec; **never** lore-enrichment.

### §12.4 Resolution — the Canon Model prerequisite (Cycle 0)
A deeper /review-impl pass (2026-06-03) found the two sharpest holes were **platform-level, not composition-level**, and could not be fixed soundly from composition's side:
- **HIGH-1 (OI-1):** no draft/published distinction exists; extraction fires on every draft save → "accept ≠ canon" was unenforceable.
- **HIGH-2 (spoiler):** `chronological_order`/`event_order` are never written → the headline spoiler cutoff was a no-op returning empty.

**PO decision: solve them durably, once, as platform primitives** — the **[Canon Model spec](2026-06-03-canon-model.md)** (Cycle 0 prerequisite, built + verified before composition M0). Its four primitives — (1) editorial lifecycle, (2) **canon = published** (extraction on `chapter.published`, pinned revision), (3) **dual ordering populated** (reading_order from `sort_order`, chronological_order from `event_date_iso`), (4) **provenance** (aligned with enrichment H0, no enrichment edits) — make composition's OI-1 **structural** (§11) and the spoiler cutoff **real** (§2.2). Composition **depends on** Canon Model CM1–CM4; it does not re-implement them. The standalone `chapter_index` ingest fix (old Mk) is absorbed into Canon Model CM4.

---

## §13 Extended benchmark — editor · streaming · cold-start · scale · canon · critic · failure · security · integrity · prose-source (2026-06-03)

§7/§11/§12 stressed chronology, integrity, and contracts. This pass exercises the **remaining operational axes**, with verdicts grounded in two more contract-verification sub-agents (book-service, sharing-service, glossary lifecycle). **Verified load-bearing facts this pass:**
- **Concurrency is a body field, not a header.** book-service chapter content lives in `chapter_drafts` with a monotonic `draft_version BIGINT`; the update echoes `expected_draft_version` → **409 `CHAPTER_DRAFT_CONFLICT`** on mismatch — **but the field is OPTIONAL (nil-gated) → blind clobber if omitted.** No HTTP `If-Match`/`ETag` exists. (`book-service server.go:1491-1534`.) → **OI-2 mechanism corrected (§11).**
- **`chapter_revisions` is real** (immutable UUIDv7 rows, full REST, `author_user_id` per row) → `base/target_revision_id` backable. No parent-lineage FK (COMP tracks lineage).
- **`chapter.saved` fires on draft edit + restore only** (NOT on create/import → that emits `chapter.created`, which knowledge does **not** consume), payload = `{book_id}` only (no author). knowledge's flywheel handler **silently skips if no `knowledge_projects` row exists for the book** (`handlers.py:118`).
- **No server-side autosave** — every client save = 1 revision row + 1 `chapter.saved` + 1 extraction enqueue.
- **Books are single-owner; no collaboration feature** (sharing = read-only private/unlisted/public). → composition's cross-user→404 model locks out nobody.
- **Glossary `entity_id` never dies/remaps** (no destructive merge, no redirect; delete = reversible soft-delete + non-physical purge) → held ids become **soft-absent**, never corrupting. **But knowledge `canonical_id` is rename-sensitive (content-hash)** → cache the **glossary** id, resolve knowledge via its `glossary_entity_id` anchor.
- **Internal glossary/knowledge reads are book-scoped ONLY (no user check)** — `X-Internal-Token` trust; **user-ownership is the CALLER's responsibility.**

| # | Class | Scenario | Verdict | Handling |
|---|---|---|---|---|
| **E1** | Editor/anchor | Author deletes a `SceneAnchor` → its `outline_node` loses its prose range | **PASS** | content-order is SoT for scene order (§1.1); orphaned node → prose folds into the previous scene; node metadata reconciled via version; node not auto-deleted (author decides) |
| **E2** | Editor/anchor | Author splits/merges a scene while a generation streams into it | **fold V0** | ghost tokens are FE-local & anchored to the node id captured at `/generate`; on accept, re-resolve the anchor by id — if the target anchor vanished, **block accept → conflict surface** (never write to a stale range) |
| **E3** | Editor/anchor | Two devices reorder scenes / move an anchor concurrently | **PASS** | LexoRank `rank` (distinct concurrent ranks) + content-order-wins for anchors + If-equivalent on node metadata (§11 OI-3) |
| **S1** | Streaming | Connection drops mid-stream | **PASS** | job stays `running`; ghost is FE-local (never autosaved); V0 has no resume → re-trigger regenerates; cost reconciled from the last `usage` frame |
| **S2** | Streaming | 2nd `/generate` fired while the 1st streams | **fold V0** | `idempotency_key` per compose action; a new generate on the same node **cancels** the in-flight job first (`cancelled`), never two ghosts on one anchor |
| **S3** | Streaming | Budget exhausts mid-stream | **PASS** | stop + partial-save **to the job** (`§5`), partial ghost stays FE-local until the author accepts; usage-frame reconcile (§3.1) |
| **C3a** | Cold-start | Book has chapters but **no knowledge project** | **fold V0** | knowledge flywheel silently skips (verified); packer L1/L4 return empty. **Detect "no knowledge project for book" and surface "grounding unavailable — initialise?"** rather than shipping silently-thin grounding (the enrichment no-silent-degrade lesson) |
| **C3b** | Cold-start | Brand-new work: no prose, no KG, no canon | **PASS (thin)** | pack = L0 canon (maybe empty) + L2 beat/goal + **L2′ planned synopses**; `_safe_*` degrade; draft from outline. Honestly thin, not broken |
| **SC1** | Scale | 200-chapter book; huge candidate context | **PASS** | priority ladder trims lowest-first (§2.3); L1b uses `before_chronological` window; L4 top-k + reading-order drop |
| **SC4** | Scale | Autosave volume | **fold V0 + Canon Model** | **client-side debounced autosave** (no server autosave exists); NEVER autosave ghost tokens. **With the Canon Model (canon=published), draft saves no longer trigger extraction** — so autosave is no longer an extraction storm (only `publish` canonizes). Each draft save still writes a revision row (history); debounce keeps that bounded |
| **CR1** | Canon | Two active `canon_rule`s contradict each other | **LIMIT** | packer includes both; critic surfaces the unsatisfiable pair as an advisory conflict (author resolves). V0 does not auto-arbitrate |
| **CR2** | Canon | `canon_rule.entity_id` points at a soft-deleted glossary entity | **PASS** | soft-absent (verified); the rule still applies by its `text`; flag the dangling entity for author cleanup |
| **CR4** | Canon | `from_order > until_order` (author typo) | **fold V0** | validate at canon-rule write → 400; normalise or reject (don't persist an empty/inverted window) |
| **CC2** | Critic | Critic would flag a `canon_rule` the author **deleted** after the draft | **fold V0** | critique **re-resolves the ACTIVE rule set at critique time** (anchored to `target_revision_id`); a deleted/archived rule is never enforced |
| **CC4** | Critic | Critic times out / gateway 402 | **PASS** | advisory → degrade silently (no critic panel), **never block accept**; catch permanent SDK errors (402/auth) before generic (enrichment SDK-exception lesson) |
| **F1** | Failure | knowledge-service down | **PASS** | packer degrades to L0/L2/L2′/L3 (COMP DB + book) via `_safe_*` (return-empty-continue; imports stay OUTSIDE try/except so wiring errors surface loud — verified `full.py`) |
| **F2** | Failure | book-service down on accept | **PASS** | accept fails (book is authoritative); ghost stays FE-local; no data loss; retry |
| **F5** | Failure | outbox emit fails after the book PUT on accept | **PASS** | best-effort `try/except` (§3.1 C8); book write already committed → do not 500 |
| **SEC2** | Security | composition calls glossary/knowledge **internal** reads which are **book-scoped only, no user check** | **fold V0** | **ownership chokepoint:** composition verifies the JWT user owns the `book_id`/`project_id` BEFORE any internal read (the internal token would otherwise let a crafted request read another user's lore). Mirrors A1; verified the internal endpoints will not catch this themselves |
| **SEC3** | Security | Prompt-injection via **retrieved lore** — a malicious passage in the KG ("ignore instructions, …") flows into the draft prompt as grounding | **fold V0** | **sanitize retrieved passages + the author `guide`** before assembly (tag-not-delete / neutralize, the enrichment `sanitize.py` pattern); bound `guide` length |
| **SEC5** | Security | `project_id` omitted on a `timeline`/`entities` lens call → widens to all the user's projects | **PASS** | A1 chokepoint asserts `project_id` non-null on every lens (§2.5/§12) |
| **DI3** | Integrity | `present_entity_ids` references a soft-deleted/renamed glossary entity | **PASS** | cache the **stable glossary `entity_id`** (verified), treat "no longer returned" as soft-absent → packer skips it, no crash; knowledge resolved via the `glossary_entity_id` anchor (rename-safe) |
| **DI5** | Integrity | Imported chapters (`chapter.created`) are never extracted (only `chapter.saved` is consumed) | **LIMIT** | imported prose isn't in the KG until first edit; V0 grounds on what's extracted + L2′ planned synopses; document (a backfill/extract-on-import is a knowledge-service follow-up, out of scope) |
| **PS2** | Prose-source | Composition prose-source PUT omits `expected_draft_version` → blind clobber of a concurrent edit | **fold V0** | the prose-source proxy **always reads current `draft_version` and echoes it as a MANDATORY `expected_draft_version`** → 409 on mismatch → conflict surface (the BE makes it optional; composition makes it required — this IS the OI-2 mechanism, §11) |

**Folded into V0:** E2 (anchor-id re-resolve on accept) · S2 (cancel-in-flight + idempotency) · C3a (no-knowledge-project surface) · SC4 (debounced client autosave, never ghost) · CR4 (canon-rule window validation) · CC2 (re-resolve active rules at critique) · SEC2 (ownership chokepoint before internal reads) · SEC3 (sanitize retrieved lore + guide) · PS2 (mandatory `expected_draft_version`). **Deferred:** DI5 (extract-on-import — knowledge follow-up) · CR1 auto-arbitration (V1) · L5 lens.

**Sharpest findings this pass:** (1) **OI-2's concurrency primitive is `expected_draft_version`+409, not If-Match** — and the BE leaves it optional, so composition must make it mandatory or silently clobber multi-device edits (PS2). (2) **Internal glossary/knowledge reads are book-scoped only** — composition owns the user-ownership check (SEC2); the internal token is not an authz boundary. (3) **Retrieved lore is an injection vector** into the draft prompt (SEC3) — easy to miss because the lore is "ours", but imported/extracted text is untrusted.

> **Two platform-level findings escalated to the Canon Model (§12.4):** a follow-up /review-impl found OI-1 (no draft/published gate → accept canonizes) and the spoiler cutoff (chronological_order never written → no-op) were unfixable from composition's side. Both are resolved by the **[Canon Model](2026-06-03-canon-model.md)** Cycle-0 prerequisite (canon=published + dual-order populated). Composition builds on it.

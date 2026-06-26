# Narrative Motif Library — DESIGN SPEC (CLARIFY stage)

> **Track:** LOOM / composition-service · **Size:** **XL** (schema migration + planner rework + cross-service mining + publish/adopt tenancy + MCP tools) → spec + plan required; subagent recommended.
> **Status:** DESIGN — **REVISED R1 (2026-06-26) after the [consolidated pre-build audit](../reports/2026-06-26-motif-library-audit.md)**. Read **§R1 (below) FIRST** — it carries the LOCKED PO decisions + the corrections that **supersede** conflicting text in §2/§3/§4/§6/§12/§13/§14/§17.
> **Research basis:** [`docs/research/2026-06-26-narrative-control-formalisms.md`](../research/2026-06-26-narrative-control-formalisms.md) (formalism survey) + [`docs/research/2026-06-02-ai-novel-composition-prior-art.md`](../research/2026-06-02-ai-novel-composition-prior-art.md) (product/system prior art).
> **Workflow note:** A1/A2/A3 (`decompose` planner) are the substrate this extends — see [`2026-06-06-a3-decompose-planner.md`](2026-06-06-a3-decompose-planner.md).

---

## §R1 — POST-AUDIT REVISION (2026-06-26) · LOCKED decisions + corrections (SUPERSEDES the body where they conflict)

> The original draft (§0-§17 below) is kept for context, but the following **supersede** it. Source: [consolidated audit](../reports/2026-06-26-motif-library-audit.md) (8 adversarial reviews).

### R1.1 — LOCKED PO decisions
1. **2-tier + clone-to-customize (drop the Book tier).** `motif`/`arc_template` are **User-owned (owner set) + System (owner NULL, seed/migrate-only)**, with `visibility ∈ private|unlisted|public`. **`motif.book_id` is REMOVED.** Templates are **book-independent** and survive book deletion. Per-book customization = **clone the template into a new user-template** (`variant_of` the original), edit the clone, reuse it forever. **`adopt` and `clone-to-customize` are ONE primitive** (clone-down): public→user, system→user, user→user-variant all clone. → §2/§4/§12 tier text is superseded by R1.4. **Read predicate (answers the audit's blocking Q1):** a motif is visible IFF `owner_user_id IS NULL` (system) `OR visibility='public' OR owner_user_id = caller`. No book-grant branch (kills IDOR-1's book dimension).
2. **One platform embedding model for ALL motif vectors** (a fixed `motif_embed_model` platform config — NOT the user's BYOK model). Makes cross-tier cosine correct; clone copies the vector (same space). Supersedes §3.4's "reuse the Work's `*_embed_model_ref`".
3. **`language` is a first-class axis on `motif`** (P1) and part of the dedup/embedding key. The platform is multilingual; retrofitting after embed+dedup is a re-key migration.
4. **`motif_application` is per-book/project scope** (carries `book_id`): the anti-repetition cap + the "why this scene" trace aggregate **across a book's collaborators**, not per-user (the kinds-bug lesson applied to the application table).

### R1.2 — CORRECTIONS to false "reuse" claims (the audit's highest-confidence findings)
- **F-1 — the flywheel substrate does NOT exist.** knowledge-service has **no `(:Event)-[:CAUSES|:HAPPENS_BEFORE]` edges** (only scalar `event_order`/`chronological_order`). §3.2/§12.4/research-§4 are **wrong** to call it production. → **drop "frequent-subgraph mining"**; re-base mining on the NEW `motif_beat` extractor + scalar-order sequences; arc-conformance extract-diff (§14.4) needs **new knowledge-service work** and is **P4+**, not free.
- **F-2 — STITCH already ships.** `engine/stitch.py` + `worker/operations.py:run_stitch()` exist (with the canon re-check). §17's "NEW" is wrong. → §17 is a **delta**: add a structured cross-scene repetition signal + respect §16 dials + **fix the two known failure modes** (it **no-ops on ≤2-scene chapters** and **elides the middle** via a head+tail char cap). Re-size §17 from "P2 greenfield" to **S/M enhancement**.
- **F-3 — there is NO narrative-quality judge.** `loreweave_eval` scores **extraction precision/recall** (binary, gold = human extraction corrections). `motif_conformance`/`plot_density`/freshness are **new graded subjective** judgments with **no gold set**. → ship `motif_conformance` **binary-first** (`beat_realized` y/n + `tension_band_match` y/n) so it plugs into the existing binary `calibrate_judge`; **build a 30-50 scene PO-labeled gold set** (the PO already hand-judged the POCs) OR ship as **uncalibrated advisory and say so in the UI**. *(Gold-set ownership = remaining OPEN decision.)* Stop calling any of this "reuse the calibrated judge."

### R1.3 — Blocker design rules (B-2/B-3/B-4) folded in
- **System-tier writes are migrate/seed-time ONLY** (like `structure_template`). The user CRUD path **server-stamps `owner_user_id = JWT.sub` unconditionally and rejects both-NULL**; add a DB `CHECK (owner_user_id IS NOT NULL)` on the user-write path. The ONE read predicate (R1.1) lives in the repo SELECT, not the handler.
- **`import_source` gets a real schema** (R1.4) with scope keys and **NO `visibility` column** (structurally un-shareable). On publish/adopt of an **imported-derived** motif: **strip `examples[]`** (DB trigger, not a prompt) and **replace `source_ref` with an opaque lineage token** (no back-readable foreign id). The **catalog projection is an explicit allow-list** (never `motif.*` — excludes `embedding`, raw `source_ref`, `examples[]`).
- **Per-user quotas** on publish/adopt/mine-runs (mirror `D-MCP-BOOK-CREATE-QUOTA`); **a real usage-billing pre-check** in the mine/import confirm effect (it is **net-new** — `_execute_generate` has none). Mining/import run as **202+poll worker jobs**, not in-process confirm effects.

### R1.4 — Corrected schema (SUPERSEDES §2.1 `motif` + §2.3 `motif_application`)
```sql
CREATE TABLE motif (
  id              UUID PRIMARY KEY DEFAULT uuidv7(),
  owner_user_id   UUID,                          -- NULL = system (seed/migrate-only). NO book_id. [R1.1]
  code            TEXT NOT NULL,
  language        TEXT NOT NULL DEFAULT 'en',     -- [R1.1.3] part of the dedup/embed key
  visibility      TEXT NOT NULL DEFAULT 'private' CHECK (visibility IN ('private','unlisted','public')),
  kind            TEXT NOT NULL DEFAULT 'sequence'
                    CHECK (kind IN ('sequence','situation','hook','emotion_arc','trope','pattern','scheme')),
  category        TEXT, name TEXT NOT NULL, summary TEXT NOT NULL DEFAULT '', genre_tags TEXT[] NOT NULL DEFAULT '{}',
  roles JSONB NOT NULL DEFAULT '[]', beats JSONB NOT NULL DEFAULT '[]',
  preconditions JSONB NOT NULL DEFAULT '[]', effects JSONB NOT NULL DEFAULT '[]',
  tension_target SMALLINT, emotion_target TEXT,
  examples JSONB NOT NULL DEFAULT '[]', abstraction_confidence TEXT,
  source TEXT NOT NULL DEFAULT 'authored' CHECK (source IN ('authored','mined','adopted','imported')),
  source_ref TEXT, source_version INT,            -- [N-4] version pin for the upstream 3-way diff
  embedding REAL[], embedding_model TEXT NOT NULL DEFAULT '',  -- ONE platform model [R1.1.2]; no per-user choice
  embedded_summary_hash TEXT,                     -- re-embed staleness guard (motifs are mutable, unlike reference_source)
  judge_score NUMERIC(4,3), mining_support INT,
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('draft','active','archived')),
  version INT NOT NULL DEFAULT 1, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT motif_user_owned CHECK (owner_user_id IS NOT NULL OR visibility <> 'private')  -- a both-NULL row must be a published/system row, never a private orphan
);
-- 2 tenancy partials (NO book tier), keyed incl. language [R1.1.1 + R1.1.3]:
CREATE UNIQUE INDEX uq_motif_user   ON motif(owner_user_id, code, language) WHERE owner_user_id IS NOT NULL;
CREATE UNIQUE INDEX uq_motif_system ON motif(code, language)                WHERE owner_user_id IS NULL;
CREATE INDEX idx_motif_owner  ON motif(owner_user_id) WHERE owner_user_id IS NOT NULL;
CREATE INDEX idx_motif_public ON motif(visibility, updated_at DESC) WHERE visibility = 'public';
CREATE INDEX idx_motif_genre  ON motif USING GIN (genre_tags);
-- retrieval pre-filter (genre ∩ + status + tier predicate) runs in SQL BEFORE loading vectors (audit data-R1).

CREATE TABLE motif_application (
  id UUID PRIMARY KEY DEFAULT uuidv7(),
  user_id UUID NOT NULL, project_id UUID NOT NULL,
  book_id UUID NOT NULL,                          -- [R1.1.4] per-book scope for anti-repetition + trace
  motif_id UUID REFERENCES motif(id) ON DELETE SET NULL,  -- [data-R3] FK + SET NULL (not the no-FK+NOT-NULL+deletable combo)
  motif_version INT,                              -- [edge-F3] pin the bound version (trace shows what was bound, not live)
  outline_node_id UUID REFERENCES outline_node(id) ON DELETE CASCADE,
  role_bindings JSONB NOT NULL DEFAULT '{}',
  annotations JSONB NOT NULL DEFAULT '{}',        -- [data-R7] bound info_asymmetry / reversal / alliance_shift
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
  -- app guard [edge-G2]: outline_node_id MUST belong to project_id (cross-project bind rejected)
);
CREATE INDEX idx_motif_application_book_motif ON motif_application(book_id, motif_id);  -- [data-R6] anti-repetition hot read
CREATE INDEX idx_motif_application_node       ON motif_application(outline_node_id);
```
`motif_link` (§2.2) gains a **cycle guard** on `precedes`/`composed_of` insert and a rule that **user-created edges may not touch system motifs** (audit H-2). `arc_template.layout` stores a **resolved `motif_id`** alongside `motif_code`, and publish/adopt **clones the member subgraph** (audit H-3). `import_source` (NEW): `(id, owner_user_id, project_id, title, content, created_at)` — **no visibility column** (audit B-3).

### R1.5 — Re-phasing
- **P1 is XL** (absorbs §15 `scheme`+`info_asymmetry`, §16 `target_words`, §11 `match_reason`, §14 binary `motif_conformance`). Re-classify §7's "P1 (L)" → **XL**.
- **Import/deconstruct (was P4) runs BEFORE graph-mining (P3)** — import is self-contained text analysis, not blocked on the missing causal-event graph (F-1); it bootstraps the library immediately.
- **§14 arc extract-diff** ships **coarse `chapter_id` only** near-term; full extract-diff is **P4+** (rides F-1 + full re-extraction cost).

### R1.6 — Superseded/corrected sections map
| Body section | Status after R1 |
|---|---|
| §2.1 `motif`, §2.3 `motif_application` | **superseded by R1.4** (drop book_id, +language, +source_version, FK SET NULL, 2 partials, platform embed) |
| §3.4 embedding ("Work's BYOK model / share one space") | **superseded by R1.1.2** (one platform model) |
| §3.2, §12.4, research §4 (flywheel "ALREADY PRODUCTION") | **corrected by R1.2 F-1** (no causal graph; re-base on motif_beat + scalar order) |
| §4 tenancy/publish/adopt (3-tier, book tier) | **superseded by R1.1.1** (2-tier + clone primitive) |
| §6, §14 ("reuse the calibrated judge") | **corrected by R1.2 F-3** (new judge dims; binary-first; gold set needed) |
| §13 MCP tiers (adopt Tier-A; bind undo; in-process mine) | **corrected by audit H-6** (adopt=Tier-W confirm; bind undo via archive-not-delete; mine=202+poll) |
| §17 STITCH ("NEW") | **corrected by R1.2 F-2** (delta on existing `engine/stitch.py`) |

### R1.7 — Still-OPEN before PLAN
- **Gold-set ownership (F-3):** who labels the 30-50 narrative scenes for `motif_conformance` calibration, or do we ship uncalibrated-advisory? *(PO)*
- **F-1 path:** fund causal-edge extraction in knowledge-service, or accept scalar-order + `motif_beat` mining only? *(decides whether P3 is reachable)* *(PO)*
- **N-3 derivative inheritance:** do motifs carry into a dị bản Work (a `motif_override` parallel to `entity_override`), or start empty? *(PO)*
- **N-2 genre as filter vs soft prior** (the POC's cross-genre re-skin is suppressed by a hard `genre_tags ∩` filter). *(recommend: soft re-ranking prior + cross-genre clone re-tags)*

---

## §R2 — Open-question resolutions (2026-06-26 deep-dive) — clears R1.7 + 3 unclear concerns

> Each below is now DECIDED. Only a small PO effort remains (R2.1 labeling).

### R2.1 — Conformance calibration: binary-first + bootstrap gold set (resolves F-3)
P1 ships **`motif_conformance` binary** (`beat_realized` y/n + `tension_band_match` y/n) as **advisory** (never a hard commit gate). Calibrate via: (a) a **small PO seed** — ~25-30 scenes the PO labels (they already hand-read the POC scenes); (b) a **strong-model-as-gold bootstrap** — a frontier BYOK model labels a larger set; the *local* judge is validated against it through the **existing binary `calibrate_judge`** (kappa ≥ 0.4, balanced-acc ≥ 0.75). The signal stays "unverified self-report" until calibration passes (and the UI says so — honest, per AI-quality R1). `plot_density` (graded) needs **ordinal** calibration (QWK) → deferred to **P1.5**. **Actuator against flag-and-ignore (AI-quality R3):** surface conformance *in the author's work/trace view*, make **"regenerate to beat" one-click** (the §11 scene-regenerate delta), and **instrument the act-on-flag rate** so we know if it's used. → **P1** (binary advisory + seed calibration). *Residual: PO labels ~25 scenes, OR we ship pure-advisory + uncalibrated and label later.*

### R2.2 — Genre = bounded filter; cross-genre = clone-and-retag (resolves N-2)
Genre stays a **bounded SQL filter** for *default* retrieval — fast, correct for the common case, and it **avoids the unbounded cross-tier cosine scan** (audit data-R1). The POC's cross-genre transfer is reproduced as a **deliberate clone-and-retag**: the author clones a motif and the clone's `genre_tags` are remapped to the target genre (then it matches as same-genre). This **uses the locked clone primitive** (R1.1.1) instead of a soft-prior-over-everything (which would reintroduce the scale problem). A "show cross-genre matches" toggle can surface candidates to clone. → **P1** (filter) + the cross-genre clone rides the adopt path (**P2**). *Better than the earlier "soft prior" recommendation — it bounds the candidate set AND reuses clone.*

### R2.3 — Mining: scalar-order + `motif_beat`, drop the causal graph (resolves F-1)
**Option B.** PrefixSpan runs over the **ordered beat-label sequence per book** — the NEW `motif_beat` extractor emits per-scene `{beat, thread, tension, roles}`; **`event_order` (which exists) supplies the order**. A frequent beat-subsequence across books **is** a motif — **no causal graph needed**. "Frequent-subgraph mining" is **dropped** (it required `:CAUSES` edges that don't exist). The `motif_beat` extractor is a **knowledge-service `loreweave_extraction` change** (cross-service; its own extractor-version/cache concerns — track it there, NOT as a composition deliverable). Causal-edge (`:CAUSES`) extraction is a **future knowledge-service track**, needed only if cross-thread/branching motif mining (§15.3, already deferred) is ever wanted. → **P3** (the `motif_beat` extractor lands first, in knowledge-service).

### R2.4 — Derivative inheritance: templates auto-inherited; applications forked at derive-time (resolves N-3)
The 2-tier decision (R1.1.1) **already solves template inheritance** — templates are **user-owned**, so a dị bản Work of the same user sees the *same library* (no project-scoping). What isn't inherited is the **applications** (project-scoped). Add an **optional "fork applications" derive-time step**: clone the source's `motif_application` rows into the derivative's project, applying the existing `entity_override` remap to `role_bindings` (parallel to how `entity_override` re-skins entities). **No `motif_override` is needed.** → **P4** (with the dị bản track); the cloneable-application schema doesn't block it.

### R2.5 — B≠C arc reconciliation algorithm (clears H-1)
Apply an arc_template to a target chapter count via **proportional placement-rescale**: map each placement's `[span_start, span_end]` from `[0, chapter_span]` → `[0, target]`, then resolve collisions — multiple placements in one chapter → keep as a **multi-scene chapter** or **merge adjacent same-thread placements**; `target < span` → merge/drop **lowest-priority** placements; `target > span` → spread. **Every drop/merge is surfaced in the preview** → the conformance loop can distinguish **"reconciled-away" from "drifted"** (clears edge-B6 false-drift). → **P4** (arc apply); not a P1 blocker (P1 is single motifs).

### R2.6 — Swap-motif-after-generation lifecycle (clears H-4 / MCP-R2)
Swapping a chapter's motif after scenes have prose **archives (never deletes)** the affected scene nodes + their `generation_job` links (reuse the existing `archive_node`/`restore_node`), instantiates the new motif's scenes, and **flags the orphaned `narrative_thread` promises for author review** (never auto-closes). **Undo = restore the archived nodes** — so the Tier-A `composition_motif_bind` undo is now *honored* (clears the MCP-R2 unhonored-undo finding). → **P1/P2**.

### R2.7 — §17 STITCH is a delta on the shipping pass (clears F-2 scope)
Enhance `engine/stitch.py`: (a) feed the **4-gram/cosine cross-scene repetition signal** (POC 5) into the stitch prompt; (b) **respect §16 style/voice dials** (no voice-homogenization); (c) fix the **≤2-scene no-op** (short chapters get a lighter single-pass polish, not skipped); (d) fix **middle-elision** — replace the head+tail char cap with **overlapping-window stitching** for long chapters so the middle is actually seen. Add the missing **eval-gate**: repetition-reduction + voice-preservation (embedding distance vs the per-scene voice profile) + **no-canon-regression** (the gone-character re-introduction the code already warns about). → **S/M, P2**.

### R2.8 — Remaining MCP fixes (folds audit H-6, no further PO input)
`_motif_adopt` → **Tier-W confirm-card** (matches the glossary precedent); `_motif_mine`/`_arc_import_analyze` → **enqueue a 202+poll worker job** (not in-process) + a **consumed-token ledger** (no replay double-spend); `_motif_create` → **closed `target: Literal['book'(n/a now)|'user']` enum + `ForbidExtra`**, owner stamped from the envelope (never an arg); every by-id tool replicates the **project-scope IDOR assertion**; `_meta.scope='user'` + `require_user_scope` for user-tier tools; add `status?` to `_motif_search` (surface drafts) + `composition_conformance_run` to the §13 catalog.

---

## §0 Goal (one line)

Add the **meso layer** the planner is missing: a queryable, multi-tenant, self-enriching **motif library** so the planner's chapter→scene step becomes **"retrieve a motif chain + bind its roles to this book's cast"** instead of **"invent scenes from a blank beat"** — making even a weak self-host model produce structurally sound plans, and letting the system **mine its own corpus to grow the library**.

**Why now (the pain):** the A3 planner's L2 asks the LLM to invent `S` scenes per chapter from `beat purpose + premise + cast`. Empirically ("Style over Story", arXiv:2510.02025) an uninstructed LLM under-weights plot 1.67× vs style — so a weak planner produces bland, plot-thin scenes. The motif library is the **control surface that forces plot structure**.

**Locked framing (PO):** this is a *data + software architecture* problem, not a prompt-pack. Motifs are **rows**, never hardcoded into service code. The "analyze→template" miner is **mandatory** — the library must enrich itself. The library is scoped **per-book and per-user**, and **publishable to system/public the same way books are**.

---

## §1 Where it lives (service + language) — DECISION: extend `composition-service`

Motifs live in **composition-service** (Python), as a sibling to `structure_template` / `outline_node` / `narrative_thread`. Rationale:

- **Cohesion with the consumer** — the planner ([engine/plan.py](../../services/composition-service/app/engine/plan.py)) is the primary reader; co-locating avoids a cross-DB hop on the hot path.
- **In-DB FK to `outline_node`** — `motif_application` references `outline_node(id)` in the same DB (the codebase convention; cross-DB ids carry no FK, per [migrate.py](../../services/composition-service/app/db/migrate.py) §1.4).
- **Reuses two existing precedents verbatim** — `structure_template` (built-in + per-user tiering, JSONB body) and `reference_source` (embed-via-provider-registry, `REAL[]` brute-force cosine retrieval).
- **Language rule** — composition-service is the Python AI/LLM service; motif *mining + abstraction* is LLM logic → Python fits.

**Rejected:** a new `narrative-patterns-service` (splits planner from its data → cross-DB, latency, no FK); folding into glossary-service (Go; glossary owns *entities*, not *narrative sequences*; the planner doesn't live there).

---

## §2 Data architecture

Three new tables + one column-light application ledger. All idempotent DDL, single-`_SCHEMA_SQL` house style (like the existing migrate.py).

### §2.1 `motif` — the library unit (system/user/book tiers + visibility)

```sql
CREATE TABLE IF NOT EXISTS motif (
  id              UUID PRIMARY KEY DEFAULT uuidv7(),
  -- TENANCY (the kinds-bug fix: every row carries a scope key; tier is DERIVED)
  owner_user_id   UUID,                 -- NULL = system tier (admin/seed only)
  book_id         UUID,                 -- set = book tier; NULL = user/system tier
  project_id      UUID,                 -- the composition Work, when book-scoped (cross-DB, no FK)
  code            TEXT NOT NULL,        -- stable cross-tier identity (shadow-resolution key)
  visibility      TEXT NOT NULL DEFAULT 'private'
                    CHECK (visibility IN ('private','unlisted','public')),
  -- CLASSIFICATION (§2.4 formalism backbone)
  kind            TEXT NOT NULL DEFAULT 'sequence'
                    CHECK (kind IN ('sequence','situation','hook','emotion_arc','trope','pattern','scheme')),  -- 'scheme' = §15 intrigue primitive (POC-validated)
  category        TEXT,                 -- hierarchical motif-index-style id, e.g. 'cultivation.fortuitous_encounter'
  name            TEXT NOT NULL,
  summary         TEXT NOT NULL DEFAULT '',   -- abstract NL description (this is what gets embedded)
  genre_tags      TEXT[] NOT NULL DEFAULT '{}',
  -- THE MESO CONTENT (Propp-function + Greimas-role + plot-graph conditions)
  roles           JSONB NOT NULL DEFAULT '[]', -- [{key, actant: subject|object|sender|receiver|helper|opponent, label, constraints}]
  beats           JSONB NOT NULL DEFAULT '[]', -- [{key, label, intent, tension_target(1..5), order}]  ordered sub-beats
  preconditions   JSONB NOT NULL DEFAULT '[]', -- [{text}]  world/character state required BEFORE
  effects         JSONB NOT NULL DEFAULT '[]', -- [{text}]  state produced AFTER (feeds legal succession)
  tension_target  SMALLINT,             -- overall 1..5; the adaptive-K signal
  emotion_target  TEXT,                 -- e.g. 'catharsis','dread','triumph','vindication'
  -- PROVENANCE + FLYWHEEL
  source          TEXT NOT NULL DEFAULT 'authored'
                    CHECK (source IN ('authored','mined','adopted')),
  source_ref      TEXT,                 -- 'system:<id>' | 'user:<id>' | 'mined:<run_id>' (clone/mining lineage)
  mining_support  INT,                  -- frequent-sequence support count (mined only)
  judge_score     NUMERIC(4,3),         -- loreweave_eval quality-gate score (mined/published)
  examples        JSONB NOT NULL DEFAULT '[]', -- [{text}] concrete instantiations (author + model grounding) [UX-delta §11]
  abstraction_confidence TEXT,          -- mined only: high|med|low — low routes to manual, never auto-add [UX-delta §11]
  -- RETRIEVAL (reference_source precedent: brute-force cosine, no pgvector)
  embedding       REAL[],
  embedding_model TEXT NOT NULL DEFAULT '',
  embedding_dim   INT,
  status          TEXT NOT NULL DEFAULT 'active'
                    CHECK (status IN ('draft','active','archived')),
  version         INT NOT NULL DEFAULT 1,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Tenancy uniqueness — EXACTLY the kinds-bug fix (UNIQUE per scope, never global):
CREATE UNIQUE INDEX IF NOT EXISTS uq_motif_book   ON motif(book_id, code)       WHERE book_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_motif_user   ON motif(owner_user_id, code) WHERE book_id IS NULL AND owner_user_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_motif_system ON motif(code)                WHERE book_id IS NULL AND owner_user_id IS NULL;
CREATE INDEX IF NOT EXISTS idx_motif_user    ON motif(owner_user_id) WHERE owner_user_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_motif_book    ON motif(book_id)       WHERE book_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_motif_public  ON motif(visibility, updated_at DESC) WHERE visibility = 'public';
CREATE INDEX IF NOT EXISTS idx_motif_genre   ON motif USING GIN (genre_tags);
```

**Tier derivation (no separate column — derived, like books):** `book_id` set → **book tier**; else `owner_user_id` set → **user tier**; else (both NULL) → **system tier**. System rows are seed/admin-only (regular users never write a both-NULL row — enforced in app code, mirroring the "users never mutate system" rule).

### §2.2 `motif_link` — composition + legal succession (ATU + plot-graph)

```sql
CREATE TABLE IF NOT EXISTS motif_link (
  id            UUID PRIMARY KEY DEFAULT uuidv7(),
  from_motif_id UUID NOT NULL REFERENCES motif(id) ON DELETE CASCADE,
  to_motif_id   UUID NOT NULL REFERENCES motif(id) ON DELETE CASCADE,
  kind          TEXT NOT NULL CHECK (kind IN ('composed_of','precedes','variant_of')),
  ord           INT,                    -- order within a composed_of pattern / a precedes-chain
  CONSTRAINT motif_link_distinct CHECK (from_motif_id <> to_motif_id),
  UNIQUE (from_motif_id, to_motif_id, kind)
);
CREATE INDEX IF NOT EXISTS idx_motif_link_from ON motif_link(from_motif_id, kind, ord);
```
- **`composed_of`** — a `kind='pattern'` (large, e.g. "Revenge Arc") → its member motifs (ATU: a tale-type *is* a named composition of motifs).
- **`precedes`** — legal succession: "fall-from-cliff" precedes "acquire-legacy" (plot-graph edge; the planner walks these so a motif's `effects` satisfy the next's `preconditions`).
- **`variant_of`** — genre variants of one abstract motif.

### §2.3 `motif_application` — what was applied where (binding ledger)

```sql
CREATE TABLE IF NOT EXISTS motif_application (
  id              UUID PRIMARY KEY DEFAULT uuidv7(),
  user_id         UUID NOT NULL,
  project_id      UUID NOT NULL,
  motif_id        UUID NOT NULL,        -- cross-tier ref (no cascade — keep history if motif archived)
  outline_node_id UUID REFERENCES outline_node(id) ON DELETE CASCADE,  -- the arc/chapter it was bound to
  role_bindings   JSONB NOT NULL DEFAULT '{}',  -- {role_key: glossary_entity_id}
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_motif_application_node    ON motif_application(outline_node_id);
CREATE INDEX IF NOT EXISTS idx_motif_application_project ON motif_application(project_id, created_at DESC);
```
Records that motif M was bound to chapter C with `{protagonist: <entity>, mentor: <entity>}`. Powers: planner traceability, the author "why this scene" view, and an **anti-repetition signal** (don't re-apply the same motif too often within a book — the cowrite.py craft-nudge made structural).

### §2.4 Formalism → field mapping (so the schema is grounded, not invented)

| Field | Formalism (research §2/§6) |
|---|---|
| `roles[].actant` | Greimas 6 actants / Propp 7 dramatis personae |
| `kind` / `category` | Propp 31 functions · Polti 36 situations · Thompson Motif-Index hierarchy |
| `beats[]` | Propp function-chain / oh-story 情节节点 |
| `preconditions`/`effects` | MEXICA pre/post-conditions · plot-graph edges |
| `motif_link.composed_of` | ATU tale-type = composition of motifs |
| `tension_target`/`emotion_target` | Lehnert plot units · oh-story emotion −9…+9 · existing `outline_node.tension` |
| `genre_tags` + seed packs | web-novel 套路/爽点/打脸 · cultivation tropes |

---

## §3 Software architecture (exploitation)

### §3.1 Planner rework — the core value (`engine/plan.py` L2)

L2 changes from **invent** to **select + bind**:

```
for each chapter (beat_role + intent, from L1):
  1. RETRIEVE candidate motifs  (motif_repo.retrieve):
       tier-merge system→user→book (book shadows by `code`)
       filter: genre_tags ∩ book genres · tension fits beat · legal succession (prev motif.effects ⊨ this.preconditions)
       rank: cosine(summary embedding, chapter-intent embedding)  [reference_source brute-force pattern]
  2. SELECT  (adaptive-K aware):
       high-tension beat → bind a motif; connective beat → may stay free-form (no forced motif)
       auto mode picks top-1; co-write mode returns top-N for the author to choose (preview)
  3. BIND:
       map motif.roles[] → book cast (reuse the present_entity name→id resolution already in plan.py)
       instantiate motif.beats[] → scene nodes (title/intent/tension_target), check preconditions vs canon_rule + open narrative_thread
       write a motif_application row (provenance)
  4. OUTPUT the SAME preview tree shape as A3 — each scene now carries motif_id + role_bindings (traceable)
```

**Why this fixes the weak planner:** selection + binding is a *constrained* task (pick from a list, map names to slots) a 7B model handles; invention is not. The motif supplies the plot structure the model was failing to generate.

**Backward-compatible:** a chapter with no matching motif falls back to today's invent-path (no regression); motifs are *additive* constraints.

### §3.2 Self-enrichment flywheel — the miner (`worker/operations.py` new op `mine_motifs`)

Reuses the **entire existing extraction + eval stack** — only a mining stage + abstraction are new:

```
Neo4j (:Event)-[:CAUSES|:HAPPENS_BEFORE]->(:Event)   [knowledge-service, ALREADY PRODUCTION]
   → frequent-sequence mining (PrefixSpan/SPADE) over event-function chains  [new, in-worker]
   → candidate concrete chains (+ support count)
   → LLM ABSTRACTION (gateway): lift concrete chain → roles + pre/post-conditions + sub-beats   [new]
   → judge gate (loreweave_eval): score coherence/reusability, dedup vs existing (cosine)        [reuse]
   → insert motif (source='mined', status='draft', book/user tier, mining_support, judge_score)
   → author reviews drafts → promote (publish/adopt up a tier)
```

**Cold-start (LOCKED):** mining needs a corpus; on 1–2 books it yields noise → **Phase 1 ships hand-seeded motifs only; mining is Phase 3.** The hard part is *abstraction* (concrete→roles), not the mining algorithm — that step is LLM + judge-gated.

**Trigger:** on-demand (`POST /motifs/mine` over a book or the user's corpus) — NOT auto-on-every-chapter (mining is expensive; cost-guard like the planner). Scheduled mining is a later option.

### §3.3 MCP tools (MCP-first invariant) vs HTTP

The MCP-first invariant: **any AI *agent* capability** (an LLM deciding to discover/pick/bind/author a motif — e.g. the glossary-assistant or chat assistant helping the user) MUST be an MCP tool. The **planner's internal motif consumption is a pipeline step** (exempt, like decompose/translation) — not an agent loop. Full catalog + tiering in **§13**; summary:
- **Tier R (agentic discovery)** — `composition_motif_search` / `_get` / `_suggest_for_chapter` / `_arc_suggest`, on the composition MCP server ([app/mcp/server.py](../../services/composition-service/app/mcp/server.py)).
- **Tier A (agentic authoring, auto-write + Undo)** — `composition_motif_create` / `_bind` / `_adopt` (the assistant authoring/binding a motif carries `_meta.undo_hint`).
- **Tier W (cost-gated, confirm-token)** — `composition_motif_mine` / `_arc_import_analyze` (LLM spend → mint confirm-token, effect in `/v1/composition/actions/*`, mirrors `composition_generate`).
- **Pure CRUD / visibility / catalog stay HTTP** (§5) — non-agentic.

### §3.4 Provider invariant

Motif `summary` embedding (retrieval) + the mining abstraction LLM call go through **provider-registry** (`/internal/embed` + the gateway `llm_client`) — no SDK import, no hardcoded model. The `reference_source` table already embeds this exact way; reuse its `work.settings.*_embed_model_ref` write-through so all motif vectors of a Work share one space.

---

### §3.5 Authoring modes — manual is the baseline (AI is additive)

Every motif and arc_template is **authorable by hand from blank** — that is the primary path; the AI surfaces (mine §3.2, import/deconstruct §12.3) only *enrich* it. Locked principles (mockup [06-manual-build.html](../../design-drafts/motif-library/06-manual-build.html)):
- **Manual create is first-class, not a fallback.** A user can build a motif (form: roles + ordered beats + conditions — §2.1) or an arc_template (the thread×chapter **timeline canvas** — add thread → place/drag motif → set pacing → define `arc_roster`) entirely without AI. The "+ New motif" / "New arc" entry points are peers to "Mine" / "Import".
- **AI output is an editable DRAFT, never auto-committed.** Mined/imported candidates land as `status='draft'` in the **same** editor/timeline canvas the user authors in (§11 review-queue) — the human always reviews + edits before it becomes `active`.
- **One shared timeline editor.** The arc-template canvas is a single FE component used by BOTH manual-build (blank) and AI-review (the import draft, §12.3) — build once.
- **Inline motif create.** Placing a motif on an arc offers "create new motif inline" (a mini-editor, subset of §2.1) so arc authoring doesn't force a context switch.

This is the tenancy principle applied to authoring: the user *owns* their tier and must be able to compose it directly; AI assists, never gatekeeps.

---

## §4 Tenancy & publish/adopt (mirror books, reuse glossary clone)

### §4.1 The three tiers (resolution merges lowest-precedence first)

```
System (seed/admin, read-only to users)  →  Per-user (my reusable library)  →  Per-book (this book's motifs)
                              shadow by `code`, higher tier wins        [the kinds-bug-correct merge]
```

### §4.2 Publish — mirror `sharing_policies` (instant, no moderation)

`PATCH /v1/composition/motifs/{id}` `{visibility: 'public'}` → instant, owner-only, no approval (book parity: sharing-service does zero checks before going public). A `kind='pattern'` published carries its `composed_of` members.

**DECISION (§9-A): motif visibility lives LOCALLY on `motif.visibility`**, NOT in sharing-service. Rationale: `sharing_policies` is keyed `book_id PRIMARY KEY` — strictly per-book; overloading it for a non-book resource needs a `(resource_type,resource_id)` re-key (invasive, touches the catalog projection). `structure_template` already keeps tiering local to composition-service. *Alternative considered:* generalize sharing-service to any resource — worth it only once a **second** publishable non-book resource exists; track as a deferred refactor if so.

**Catalog:** `GET /v1/composition/motifs/catalog?genre=&q=&sort=` — projection query over `visibility='public'` (mirrors catalog-service's read-only projection, but served by composition for MVP; promote to a real catalog-service extension if cross-service discovery is wanted).

### §4.3 Adopt — mirror glossary `adoptBookOntology` (clone-down with provenance)

A published/system motif is **adopted (cloned) into your tier**, not referenced in place (so your edits never mutate the shared original — the core tenancy rule). `POST /v1/composition/motifs/{id}/adopt` `{target: 'user' | {book_id}}`:

```sql
INSERT INTO motif (owner_user_id, book_id, project_id, code, ...all content..., source, source_ref)
SELECT $user, $book, $project, m.code, ...m.*..., 'adopted', 'system:'||m.id   -- or 'user:'||m.id
FROM motif m WHERE m.id = $1 AND (m.visibility='public' OR m.owner_user_id IS NULL)
ON CONFLICT (book_id, code) DO NOTHING;   -- idempotent, like adopt
-- pg_advisory_xact_lock(hash(book_id)) to serialize concurrent adopts (glossary precedent)
```
Edits to the adopted copy stay in your tier; the source is untouched. `source_ref` preserves lineage (provenance + future "update available" diffs).

### §4.4 Grant gating

Book-tier motif writes require **`grantclient.GrantManage`** on the book (glossary adopt precedent — only owner + manage-grantees reshape a book's motif set). Reads require `view+`. Cross-DB grant check via the existing `grantclient.ResolveGrant()` (Go SDK; composition calls book-service `/internal/books/{id}/access` — confirm the Python client equivalent at BUILD, or add one).

---

## §5 API contract (composition-service, gateway-proxied `/v1/composition`)

| Method + path | Purpose | Tier/auth |
|---|---|---|
| `GET /motifs?scope=book\|user\|system&genre=&q=` | list/search (tier-merged) | view+ |
| `GET /motifs/{id}` | read one | view+ |
| `POST /motifs` | create (book or user tier) | manage (book) / self (user) |
| `PATCH /motifs/{id}` | edit / flip visibility | owner |
| `DELETE /motifs/{id}` | archive | owner |
| `POST /motifs/{id}/adopt` | clone-down to user/book tier | manage (book) / self (user) |
| `GET /motifs/catalog` | public discovery projection | any authed |
| `POST /motifs/mine` *(Phase 3)* | mine a book/corpus → draft motifs | manage |
| `POST /works/{project}/outline/decompose` | **A3 endpoint, extended** to bind motifs in L2 (returns per-scene `motif_id` + `match_reason`) | manage |
| ★ `PATCH /works/{project}/outline/{node}/motif` | swap/clear a chapter's bound motif → re-derive scenes + re-bind roles (UX-delta §11) | manage |
| `POST /works/{project}/outline/{node}/scenes/{scene}/regenerate` | regenerate one scene *within* its motif beat (UX-delta §11) | manage |
| MCP `composition_motif_search` / `_get` / `_suggest_for_chapter` | agentic reads (return `match_reason`) | R + grant |

Decompose preview response (§A3) gains per-scene `motif_id`, `motif_name`, `role_bindings`, `motif_source` so the author sees *which motif drove each scene* and can swap it.

---

## §6 Eval-gate (ship only if it beats A3)

`scripts/eval_motif_planner.py` (mirrors `eval_a3_decompose.py`): same premise + book, compare **motif-planner** vs **A3 decompose** (no motifs) on disjoint-judge **coherence** + **outline-relevance** + a new **plot-density** dim (does the scene carry actual plot events vs filler — the "Style over Story" failure the motif is meant to fix). Report wall-clock + K spend. **Honest-finding stance:** if motifs help plot-density but not coherence-median, report that — plot-density is the discriminating signal the research predicts.

---

## §7 Phasing (XL → ship in value-ordered slices)

| Phase | Scope | Value | Gate |
|---|---|---|---|
| **P1** (L) | `motif` + `motif_link` + `motif_application` schema · hand-seeded **tu-tiên + báo-thù** pack (system tier, abstracted onto schema) · planner L2 **select+bind** · author preview/swap · eval-gate | **Directly fixes the weak-planner pain; independently shippable** | eval ≥ A3 on plot-density |
| **P2** (M) | Tenancy: user-tier library · publish (`visibility`) · adopt (clone-down) · catalog projection · grant gating | book/user/system + publish parity | tenancy tests (no cross-tenant write) |
| **P3** (L) | Miner: Neo4j event-chain → frequent-sequence → LLM abstraction → judge → draft motifs · `POST /motifs/mine` | **self-enrichment flywheel** | judge-gate + dedup; mined draft review UX |

P1 is the spine and the only phase that *must* land first; P2/P3 are independently valuable and separately gated.

---

## §8 Files (estimate)

**New (P1):** `db/migrate.py` (+3 tables, +seed pack) · `db/models.py` (Motif/MotifLink/MotifApplication) · `db/repositories/motif.py` (tier-merge retrieve + cosine rank) · `engine/motif_select.py` (retrieve+select+bind) · `routers/motif.py` (CRUD) · `scripts/eval_motif_planner.py` · `scripts/seed_motif_packs/` (cultivation/revenge JSON) · tests.
**Changed (P1):** `engine/plan.py` (L2 select+bind) · `engine/adaptive_k.py` (motif tension_target signal) · `routers/plan.py` (preview gains motif fields) · `config.py` (motif_retrieve_top_k, motif_min_score) · `deps.py`.
**P2:** `routers/motif.py` (+adopt/publish/catalog) · `clients/` (grant check) · gateway pathFilter (confirm `/v1/composition/motifs/*` proxies) · MCP `app/mcp/server.py` (+3 read tools) · tenancy tests.
**P3:** `worker/operations.py` (mine_motifs) · `clients/knowledge_client.py` (event-chain read) · `engine/motif_mine.py` (PrefixSpan + abstraction + judge) · `clients/eval_client.py` (reuse).

---

## §9 CLARIFY — decisions needed from PO before PLAN

| # | Decision | Recommendation |
|---|---|---|
| **A** | Motif visibility: composition-local vs generalize sharing-service? | **Local `motif.visibility`** (sharing-service is book-keyed; don't overload until a 2nd publishable resource exists) |
| **B** | Adopt model: clone-down vs reference-in-place? | **Clone-down** (glossary precedent; protects the tenancy rule — edits never touch the shared original) |
| **C** | P1 scope: planner+seed only, defer publish (P2) + mining (P3)? | **Yes** — P1 is the value spine and the only must-first; it's independently eval-gateable |
| **D** | Seed pack genres for P1? | **Cultivation (tu-tiên) + Revenge (báo-thù)** — the PO's own genres, richest motif corpus |
| **E** | Mining trigger: on-demand vs scheduled? | **On-demand** (`POST /motifs/mine`, cost-guarded); scheduling later |
| **F** | Motif default granularity (one beat vs a full arc)? | **Mid-grain chain** (3–6 sub-beats, e.g. "fortuitous-encounter"); `kind='pattern'` composes chains for arc-scale |

**Open risks:** (1) **abstraction quality** — mined concrete→roles lift is the hard LLM step (judge-gate it); (2) **formulaic output** — over-applied motifs read as cliché → cap re-application per book + keep the anti-slop judge; (3) **granularity** is an empirical design loop, not a one-shot decision; (4) **interiority** — motifs govern plot/action only; prose/voice stay under `style_profile`/`voice_profile` (research §0.5).

---

## §10 Acceptance (P1)

- [ ] 3 tables migrate idempotently; seed pack (cultivation+revenge) loads as system-tier motifs.
- [ ] Planner L2 binds a motif to ≥1 high-tension chapter and writes a `motif_application` row with role→entity bindings.
- [ ] Author preview shows per-scene motif + can swap/clear it (co-write); auto mode picks top-1.
- [ ] No-match chapter falls back to the A3 invent-path (no regression).
- [ ] `eval_motif_planner.py` shows motif-planner ≥ A3 on plot-density (coherence non-inferior).
- [ ] Tenancy: a user cannot write a system-tier (both-NULL) motif; book writes require manage grant.

---

## §11 UX-surfaced deltas (from `design-drafts/motif-library/` mockups, 2026-06-26)

Drawing the UX (5 mockups: index · library · editor · planner-binding · mining) surfaced features the data/API model was missing. Grouped + Phase-tagged; the two **★** are load-bearing — the spec would have built the wrong thing without them.

### Schema additions (`motif`)
- **`examples[]`** (added to §2.1) — concrete instantiations; ground author + model. [P1]
- **`abstraction_confidence`** (added to §2.1) — mined-only high|med|low; low → manual, never auto-add. [P3]
- richer **`source_ref`** → back-links to the chapters/events a mined motif came from. [P3]
- *(decision)* catalog social fields `adopt_count`/rating — **DEFER** to P2+ unless discovery needs them.

### API additions (some folded into §5)
- ★ **`PATCH …/outline/{node}/motif`** — swap/clear a chapter's bound motif + re-derive scenes + re-bind roles. The single biggest miss — the A3 preview was read-only. [P1]
- **`POST …/scenes/{scene}/regenerate`** — regenerate one scene *within* its motif beat. [P1]
- ★ retrieval returns a **`match_reason`** (tension/genre/precondition/cosine breakdown), not just a ranked id — the "why this motif" UX + author trust. [P1]
- **adopt target picker** — `POST /motifs/{id}/adopt {target:'user'|{book_id}}` (a modal), not assumed. [P2]
- **usage aggregate** — "used in N books" over `motif_application` (cross-book). [P2]
- **upstream-diff / sync** — adopted+edited motif needs an "update available" signal + 3-way diff (glossary D8 parity). [P2]
- **knowledge-service event-chain client** — mining reads `(:Event)-[:CAUSES|:HAPPENS_BEFORE]` per book (internal-token). [P3]
- **dedup + merge-as-variant** — near-dup cosine vs existing + a `variant_of` merge action. [P3]
- **chain-it** — accept a legal-succession suggestion → pre-seed the next chapter's motif. [P1/P2]

### Config additions
- **`motif_max_reapply`** — anti-repetition cap per book (the overuse warning). [P1]
- **`motif_mine_min_judge`** — judge-gate threshold; below-gate shown, not added (no silent drop). [P3]
- mining **cost-guard** — usage-billing pre-check + $ estimate before a run. [P3]

### Behaviors / enforcement
- mined-draft (`status='draft'`) = distinct visual + a review queue, not mixed into the active list. [P3]
- **system read-only** — hard-disable edits on a both-NULL row + "clone to edit" (glossary system-kind lock parity). [P1]
- **re-embed** on `summary` edit (reference_source write-through). [P1]
- **conditions = free-text NL for v1** (a predicate DSL is over-engineering; the planner matches semantically). [P1, **DECIDED**]
- **unresolved-role** → inline cast-picker + "create entity" shortcut (mirrors `present_entity_names_unresolved`). [P1]

---

## §12 Arc-level templates + import/deconstruct (scenario-driven extension)

> Surfaced by the stress-test "import 斗破苍穹 → propose an arc template → write a new arc." The motif layer (§2) handles a **single-thread, chapter-scale chain**. An *arc* is **multi-chapter + multi-thread (combat ∥ cultivation ∥ romance) + interleaved** — bigger than `pattern`/`composed_of`. This section adds the arc layer and the import/deconstruct path, and answers "is the data architecture good enough for arc analysis given context windows?" — **yes, by riding the existing P1/P2/P3 map-reduce extraction rails.**

### §12.1 Granularity — templates are TWO levels (decided)

| Level | Shape | Table | Example |
|---|---|---|---|
| **Motif** (§2) | single thread, 3–6 beats, chapter-scale | `motif` | "face-slap the arrogant genius" |
| **Arc template** (NEW) | multi-thread × motifs placed over a chapter span, with pacing | `arc_template` | 斗破's "three-year pact" arc |

The scenario needs the **arc** level. An arc template *composes* motifs (reuses §2 as its placed units) onto parallel threads across a chapter span.

### §12.2 `arc_template` schema (reuses motif tenancy verbatim)

```sql
CREATE TABLE IF NOT EXISTS arc_template (
  id            UUID PRIMARY KEY DEFAULT uuidv7(),
  owner_user_id UUID, book_id UUID, project_id UUID, code TEXT NOT NULL,   -- SAME tenancy/keys as motif (§2.1)
  visibility    TEXT NOT NULL DEFAULT 'private' CHECK (visibility IN ('private','unlisted','public')),
  name          TEXT NOT NULL, summary TEXT NOT NULL DEFAULT '', genre_tags TEXT[] NOT NULL DEFAULT '{}',
  chapter_span  INT,           -- ~N chapters the arc spans (a hint; reconciled to target at apply, like A3 B≠C)
  threads       JSONB NOT NULL DEFAULT '[]',  -- [{key:'combat'|'cultivation'|'romance', label}]  parallel tracks
  layout        JSONB NOT NULL DEFAULT '[]',  -- [{motif_code, thread, span_start, span_end, ord, role_hints}]  placements (a motif may recur)
  pacing        JSONB NOT NULL DEFAULT '[]',  -- overall tension/escalation curve across the span
  arc_roster    JSONB NOT NULL DEFAULT '[]',  -- arc-level role roster (bind protagonist ONCE → propagate to all placements)
  source        TEXT NOT NULL DEFAULT 'authored' CHECK (source IN ('authored','mined','imported')),  -- 'imported' = §12.3
  source_ref    TEXT, embedding REAL[], embedding_model TEXT NOT NULL DEFAULT '', embedding_dim INT,
  status        TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('draft','active','archived')),
  version       INT NOT NULL DEFAULT 1, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- same tenancy uniqueness as motif: UNIQUE(book_id,code) / UNIQUE(owner_user_id,code) / UNIQUE(code) partials.
```
- **`threads` = content tracks** (combat/cultivation/romance) — distinct from `narrative_thread` (promise/payoff ledger), but applying an arc MAY spawn `narrative_thread` rows (the romance thread's promises).
- **`layout` = placements** on (thread × chapter-span); JSONB (mirrors `structure_template.beats` house style). Relational `arc_placement` is the alternative if heavy querying is needed — **decision deferred**, JSONB for v1.
- **`arc_roster`** fixes the "bind protagonist once for the whole arc" sub-gap (a role recurs across many placements).

### §12.3 Import / deconstruct path (text + web search) — the 拆文 mode

Distinct from "mine my own graph" (§3.2). An **external** work (斗破) is NOT in the user's Neo4j → needs ingest + analysis that doesn't assume prior extraction.

```
import: paste/upload chapters  +  web-search snippets (arc summaries, wiki)
   → import_source rows (raw text, PRIVATE/transient — see §12.6 copyright)
   → analyze_reference (the deconstruct op, §12.4)
   → proposed arc_template (+ member motifs)  [status='draft', source='imported']
   → author reviews on a thread×chapter timeline → saves into book/user tier
```
- **Web search role:** for a famous work, web summaries give the **canonical arc boundaries + thread skeleton** that anchor the reduce (cuts hallucination). For an obscure / the user's own work, no web → rely on chunked extraction alone.

### §12.4 The context-window answer — ride the P1/P2/P3 map-reduce rails

**An arc exceeds any context window. The project ALREADY solved this for 50 MB novels** ([`2026-05-23-p3-hierarchical-reduce.md`](2026-05-23-p3-hierarchical-reduce.md) + p1/p2): chunk → per-leaf extract (MAP, cached in `extraction_leaves`) → `tree_merge` bottom-up scene→chapter→part→book + per-level LLM summaries (REDUCE). Arc analysis is the **same shape with new payloads** — no new infrastructure:

| Stage | Existing (entities/events) | Arc analysis (NEW payload, SAME rails) |
|---|---|---|
| **Chunk** (P1) | book → parts → scenes | identical |
| **Map** (P2, per-leaf, fits window) | 4 extractors: entity/relation/event/fact | **+5th extractor `motif_beat`**: per scene/chapter emit {beat, thread, tension, role-mentions} |
| **Reduce** (P3, on summaries not raw) | `tree_merge` dedup → `:Scene→:Chapter→:Part→:Book` + summaries | **+arc-reduce**: cluster beats → segment arcs → assemble `arc_template` (threads + placements). Works on per-chapter beat extractions (fits window), NOT raw text |
| **Arc tier already exists** | `:Part` nodes + `summary_parts` | an "arc" ≈ a `:Part` / chapter-span; part summaries already synthesize across chapters |
| **Retrieve** | Mode-3 "abstract" → part/book summary index | the same abstract-intent path surfaces arc structure |

**Key point:** the REDUCE consumes the **map outputs (extracted beats per chunk), never the raw arc text** — so it fits the window exactly as the existing book-summary reduce does (P3 D1: part/book merge sees summaries, not raw entities). Caching (`md5`), async Redis-stream jobs, idempotent re-run — all reused.

**What is genuinely NEW (not free):**
1. **`motif_beat` map extractor** — a 5th prompt/schema in `loreweave_extraction` (the 4-extractor pattern is the template). [build]
2. **Arc segmentation** — the existing hierarchy uses the author's **structural** parts; arcs are **semantic** (斗破's arcs ≠ its volume breaks). Need semantic arc-boundary detection (GraphRAG community-style over the event/beat sequence) OR take boundaries from web-search summaries for known works. (The P3 "P4 semantic chunking" P-FUTURE is the same need.) [the hard new piece]
3. **Multi-thread arc-reduce** — the existing reduce emits one summary; the arc-reduce must cluster beats into threads + place them on a timeline. The `tree_merge` scaffold (bottom-up, canonical dedup) is reusable; the output shape is richer. [build]

### §12.5 Apply an arc template — planner at arc scale

"Write a new arc from this template" = decompose (§3.1) **at arc scale**: reconcile `chapter_span` → the user's target chapter count (the A3 B≠C reconciliation), bind `arc_roster` once to the new book's cast, place each thread's motifs across target chapters, interleave per chapter, emit the multi-chapter outline (each scene still traceable via `motif_application`).

### §12.6 New risks (scenario-specific)

- **Copyright / ToS — PO DECIDED (2026-06-26):** two separable layers, and the schema *enforces* the split.
  1. **Raw imported data stays in the user's OWN store, never shareable.** `import_source` rows are **per-user/per-book tier only** — there is **no `visibility='public'/'unlisted'` path** for `import_source` (unlike `motif`/`arc_template`). It is analysis input the user supplied to their own workspace, not platform content.
  2. **The derived template is an idea/structure, not the source expression — so it does not infringe.** A `motif`/`arc_template` stores **role slots** (subject/sender/object) + **abstract beats** ("isolation by disaster") + pacing — by construction it carries **no source proper nouns and no source prose**. The idea/expression line is held *by the data model*, not just by policy.
  - **Engineering guardrail (makes #2 robust):** the `analyze_reference` deconstruct step MUST abstract — strip proper nouns / entity names / verbatim phrasing into role slots + generic beats — so a "template" can never smuggle a near-verbatim chapter-by-chapter retelling (which could still be substantial similarity). The role-slot schema already forces this; the deconstruct prompt + a post-check enforce it. `examples[]` (§11) on an *imported-derived* motif must be author-written or synthetic, **not** copied source passages.
- **Semantic arc segmentation** is the real new R&D risk (not the context window — that's solved). De-risk by leaning on web-search boundaries for famous works first.
- **Cross-chapter coreference at arc scale** is bounded by what per-chapter maps surface (inherits P3 R1 / `D-P3-WHOLE-BOOK-MERGE-FOR-COREF`); the `arc_roster` + web anchors mitigate.
- **Scale mismatch** — a 60-chapter source arc compressed onto a 10-chapter target needs lossy reconciliation; surface dropped/merged motifs, never silently.

### §12.7 Phasing impact

Arc templates are a **second XL** on top of the motif core — do NOT merge into P1. Suggested: **P4 (arc templates + import/deconstruct)** after P1–P3. But the **import/deconstruct path may deserve priority over graph-mining (P3)**, since it lets a user bootstrap a rich library from admired works immediately rather than waiting for their own corpus. PO to weigh P3 (mine mine) vs P4 (import theirs) ordering.

---

## §13 MCP surface — full catalog (MCP-first invariant)

Motif/arc-template logic is **agent-facing**: the glossary-assistant, the chat assistant, and any ai-gateway-federated agent help the user *discover, pick, bind, and author* motifs — that is agentic, so it MUST be MCP tools (not bespoke HTTP), per the invariant. The **domain owns its tools** (composition-service's `make_stateless_fastmcp("composition")` server); ai-gateway only federates/routes. All tools reuse the **exact existing composition MCP pattern** ([app/mcp/server.py](../../services/composition-service/app/mcp/server.py)): identity from the **envelope only** (`build_tool_context` → X-Internal-Token constant-time check + X-User-Id), arg models extend **`ForbidExtra`** (the LLM can't smuggle a `user_id`/ownership id), every call gates through **`require_book_owner`** (VIEW reads / EDIT writes) → **`uniform_not_accessible`** (H13, no enumeration oracle), and each carries validated **`require_meta(tier, "book", synonyms=[…])`** feeding `find_tools` recall.

### §13.1 Tool catalog

| Tool | Tier | Args (≈) | Purpose | Gate |
|---|---|---|---|---|
| `composition_motif_search` | **R** | `genre?, kind?, q?, scope?` | tier-merged search (system→user→book) → list + `match_reason` | VIEW |
| `composition_motif_get` | **R** | `motif_id` | one motif (roles/beats/conditions/examples) | VIEW |
| `composition_motif_suggest_for_chapter` | **R** | `project_id, node_id` | rank motifs for a chapter's beat/intent/tension → candidates + `match_reason` (powers the planner-binding "why this motif") | VIEW |
| `composition_arc_suggest` | **R** | `project_id, premise?, genre?` | rank arc_templates for a premise | VIEW |
| `composition_motif_create` | **A** | `args(book\|user, code, name, roles, beats, …)` | assistant authors a motif from the conversation; `_meta.undo_hint` = delete | EDIT |
| `composition_motif_bind` | **A** | `project_id, node_id, motif_id, role_bindings` | bind/swap a motif onto a chapter + re-derive scenes; `undo_hint` = restore prior binding | EDIT |
| `composition_motif_adopt` | **A** | `motif_id, target:{book\|user}` | clone-down a public/system motif into the caller's tier; `undo_hint` = delete the clone | EDIT |
| `composition_motif_mine` | **W** | `args(scope, min_support, promote_to)` | kick the mining job (LLM spend) → **confirm-token**; effect in `/v1/composition/actions/*` | EDIT + confirm |
| `composition_arc_import_analyze` | **W** | `args(import_source_id, use_web, arc_hint?)` | kick the import/deconstruct job (LLM spend) → **confirm-token** | EDIT + confirm |

### §13.2 Tier semantics (mirror the existing composition tiers)

- **R** — reads; VIEW gate; no side effect. The discovery/suggest surface every assistant uses.
- **A** — auto-write, **reversible**; EDIT gate; result carries `_meta.undo_hint` (a verified reverse op the FE activity strip offers as Undo). `create`/`bind`/`adopt` are all reversible → A, not W.
- **W** — **cost-gated** (token spend); EDIT gate **+ `mint_confirm_token`** (descriptor e.g. `composition.motif_mine` / `composition.arc_import`), the actual spend runs in the confirm-route effect (`app/routers/actions.py`) after a usage-billing pre-check — exactly how `composition_generate` is gated. Mining/import are NOT silent; the confirm step shows the $ estimate.

### §13.3 Agentic vs pipeline (the invariant line, explicit)

- **MCP (agentic):** an LLM *deciding* to surface/bind/author a motif while helping the user — glossary-assistant ("this chapter fits a face-slap motif — bind it?"), chat assistant, ai-gateway agents. These call the tools above.
- **Pipeline (exempt):** the decompose planner's *internal* retrieve→select→bind during a `/generate auto` run is a deterministic pipeline step (like translation/decompose), not an agent loop — it calls the **repo/engine directly**, not the MCP tool. (The MCP `_suggest_for_chapter` and the pipeline share the same `motif_repo.retrieve` core; only the *entry* differs.)
- **HTTP (non-agentic):** pure CRUD, visibility flip, catalog projection (§5) — user-driven forms, no agent.

### §13.4 Cross-surface federation

ai-gateway federates the composition MCP server, so motif discovery/binding is available **wherever the agent runs** (chat, glossary-assistant, the composition studio's own assistant) without duplicating logic — the "domain owns tools, gateway federates" rule. `find_tools` recall is seeded by each tool's `synonyms` (e.g. `["motif","trope","pattern","plot beat","cliché","套路"]`) so an assistant surfaces them on intent, not just exact name.

### §13.5 Deltas to fold elsewhere
- §5 (API) keeps the 3 read-tool summary row; §13 is the authoritative catalog.
- The Tier-W confirm descriptors (`composition.motif_mine`, `composition.arc_import`) extend the C-CONFIRM domain map (alongside `composition.publish` / `composition.generate`).
- `_suggest_for_chapter` returning `match_reason` is the same payload the planner-binding UX (mockup 03) needs — one retrieval core, two entries (§13.3).

---

## §14 Conformance & traceability — closing the control loop

> Surfaced by "how do we KNOW the AI wrote according to the arc, and what did each scene compose?" (mockup [07-trace-conformance.html](../../design-drafts/motif-library/07-trace-conformance.html)). Control is a **closed loop**: plan → generate → **verify-against-plan** → correct. The plan→prose link exists; the *verify* step is the gap.

### §14.1 Two questions, two answers

- **"What did each scene compose?"** — answerable **today from a data join** (the trace chain already exists). §14.2.
- **"Did the AI follow the arc?"** — **NOT yet answerable**; needs a conformance layer (a judge dimension + the extract-diff). §14.4. Outlines conform *by construction* (the planner places motifs per template), but the **generated prose can drift** from the plan, and nothing currently checks that.

### §14.2 The trace chain (already in the schema — just needs a read + a view)

```
arc_template.layout (planned motif placements)
  └─ outline_node (scene)        : beat_role, goal, synopsis, tension, present_entity_ids   [PLANNED]
       ├─ motif_application      : motif_id (which beat) + role_bindings (sender→Sword-Ghost)
       └─ generation_job         : input (context) · result (PROSE) · critic (judge) · target_revision_id   [REALIZED]
```
"What scene ② composed" = join `outline_node` (planned beat) ⋈ `motif_application` (motif beat + bindings) ⋈ `generation_job.result` (the prose). The DATA is sufficient; the **per-scene trace VIEW** (planned │ realized │ conformance, mockup 07-A) is the new surface.

### §14.3 The plan↔realized link (the technical crux)

To check conformance we must map a **realized `(:Event)`** (extracted from the generated prose, the flywheel) back to the **planned `outline_node`/beat**. Two tiers:

- **Coarse — works TODAY, no new field:** both the planned `outline_node` and the realized extraction events carry the same **`chapter_id`** (extraction anchors entities/events by chapter; `outline_node.chapter_id` is the same id). → chapter-level + arc-level conformance (thread progress, pacing, succession) computes on this shared key now.
- **Fine — scene→event attribution (NEW anchor):** to attribute a specific realized event to a specific planned scene/beat, record the realized scene's **character offset-span in the chapter revision** on `generation_job` (`scene_span INT[]` or a `scene_realization` row keyed `(outline_node_id, target_revision_id, start, end)`). Extraction (which chunks by scene, P1) then attributes each event-chunk to the overlapping `outline_node_id`. This is the precise plan↔realized key the per-scene conformance needs. *Coarse ships first; fine is an additive anchor.*

### §14.4 Conformance at three altitudes (= the three data layers)

1. **Scene** — NEW judge dimension **`motif_conformance`** in `loreweave_eval` (reuses the production calibrated judge): given the scene's planned beat (intent + tension target + present roles), does the realized prose **realize that beat**? Score + flags (`beat realized` / `tension match` / `sender present`). Stored in `generation_job.critic` (JSONB — no schema change). A drift (mockup 07-A scene ③: planned "trial" → realized "rest") flags + offers **"regenerate to beat"** (reuses the §11 scene-regenerate within the motif).
2. **Chapter** — do the chapter's scenes cover the motif's beats in order at the planned tension curve? A reduce over the chapter's `outline_node` + `generation_job.critic`.
3. **Arc — the flywheel CLOSES the loop:** run **generate→extract** (existing pipeline) over the arc's chapters → diff the **realized arc structure** vs the **`arc_template`**: thread progression (did combat/cultivation/romance advance where placed?), pacing (realized tension curve vs planned), **legal succession** (each motif's realized effects ⊨ the next's preconditions?), **promise ledger** (`narrative_thread` open/paid across the arc). The **same map-reduce that builds templates (§12.4) verifies them** — extract the output, compare to the plan.

### §14.5 Additions

- Judge: `motif_conformance` dimension (loreweave_eval prompt + calibration); written into `generation_job.critic`.
- Anchor: `generation_job.scene_span` (or `scene_realization` table) — the fine plan↔realized key (§14.3).
- Read/job: `GET /works/{project}/conformance?scope=chapter|arc` — assembles the trace + runs the extract-diff (arc scope is a cost-gated job → Tier-W MCP `composition_conformance_run`, confirm-token like mine/generate).
- The arc-conformance report may be persisted (`arc_conformance_report`) or computed on demand (start on-demand; persist if recomputation cost bites).

### §14.6 Advisory, not a hard gate

Conformance **surfaces drift for the author to accept or fix** — it never auto-blocks a commit (mirrors `narrative_thread`'s advisory stance and the eval-judge-as-gate-not-blocker philosophy). The author stays in control; the system makes drift *visible* rather than *forbidden*. (A user may intentionally diverge from the arc — that's authoring, not error.)

### §14.7 Phasing

Scene-level `motif_conformance` is **P1-adjacent** (it's the eval-gate dimension the planner already needs — §6). The per-scene trace VIEW is P1/P2. The **arc-level extract-diff** depends on the import/extract path → **P4** (with arc templates). The fine offset-span anchor lands when scene-level attribution is needed (P2/P4).

---

## §15 Complex-genre primitives — intrigue / drama (POC-validated)

> The §2 motif model fits linear arcs (revenge-cultivation). The **complexity stress test** ([`docs/research/2026-06-26-motif-prompt-control-poc.md`](../research/2026-06-26-motif-prompt-control-poc.md) §6) ran a **12-beat, 5-thread palace-intrigue (宫斗) arc** re-skinned to a corporate drama on the same weak model — and it **held**, *because* the template carried genre primitives the base model lacks. These are the additions that let the architecture express intrigue/drama (cung đấu, psychological-social). All additive; mostly JSONB so no migration churn.

### §15.1 `scheme` motif kind + information-asymmetry (the heart of intrigue)
- **`kind='scheme'`** (added to §2.1) — a scheme is a mini-motif: `setup → bait → victim acts on a FALSE belief → reveal → counter` (its `beats[]` carry these).
- **`info_asymmetry` JSONB** on a scheme motif / its application: `{knows:[entity_or_role], deceived:[entity_or_role], gap:"what the deceived believes vs the truth"}`. This is **dramatic irony made first-class** — the 信息差 the POC captured verbatim (*"KNOWS: Maren, Noah · DECEIVED: Ada, Sylvie, Sterling · gap: the Board thinks she's exposing fraud; she's exposing the cover-up"*). The conformance judge (§14) checks the realized scene actually *exploits* the gap.
- A scheme's **`effects`** flip a thread's advantage (feeds the next scheme's preconditions — schemes *chain* and *nest* via `motif_link.precedes`/`composed_of`).

### §15.2 `reversal` and `alliance_shift` beat annotations
Optional annotations on a `beats[]` entry (or a `motif_application`):
- **`reversal: {thread, from, to}`** — this beat flips a thread's advantage (the sawtooth the POC produced: mid-betrayal peak + final peak).
- **`alliance_shift: {a, b, from: 'ally'|'enemy'|'neutral', to: …}`** — a relationship changes polarity (POC ch6: patron Holt **ally→threat**). At apply-time these write through to glossary relations / `narrative_thread` so the shift is tracked downstream.

### §15.3 Cross-thread triggers (optional, richer)
An arc_template `layout` placement may carry **`triggers: [other_placement_id]`** — a causal edge: a scheme's reveal in thread T3 *causes* the alliance shift in T4. The POC handled this **implicitly** (it tagged which threads advance but not the causal link); making it explicit lets the planner + conformance check thread *interactions*, not just thread *presence*. Nice-to-have; defer until the implicit handling proves insufficient.

### §15.4 Pacing = sawtooth / multi-peak (no change)
Already expressible — `arc_template.pacing` is a freeform JSONB curve. The POC's double-peak sawtooth confirms it; no new field.

### §15.5 What stays OUT of scope — interiority
The control layer scaffolds **plot/scheme structure**, NOT **interiority**. The POC scene *produced* strong interiority ("*I see you… I'm not going down like Lia did*") because the **prose** prompt carried the emotional stakes — the architecture neither supplies nor suppresses it (research §0.5 / §6.3). **Do not model "emotion control" as a motif primitive** — it belongs to `style_profile`/`voice_profile` + the prose step, with the human in the loop for voice-heavy passages. Over-claiming plot control as emotional control is the trap to avoid.

### §15.6 Phasing
`scheme` + `info_asymmetry` ship with the motif core if the user's genres are intrigue-heavy (**P1**, since it's a `kind` + a JSONB field — cheap and high-value for cung-đấu/drama). `reversal`/`alliance_shift` annotations are **P1/P2**. Cross-thread triggers are **P4** (with arc templates). Novel-scale arc-chaining (dozens of episodic scheme cycles) rides §12.4 map-reduce + `composed_of` — **P4+**.

---

## §16 Control surface — the scene is the unit, parameters are scoped dials (POC-validated)

> Answers "do we control by the scene, or by adding parameters?" — **both, and they are the same mechanism.** The **scene (`outline_node`) is the atomic control unit**; **parameters are dials attached to it**, scoped **work → chapter → scene**, **most-specific wins** — the exact `style_profile` precedent already in the schema. You set a parameter globally and override it per scene. Confirmed end-to-end: each POC scene was steered purely by its packed parameters (beat + roles + length + density), and the packer's `style_profile` already resolves most-specific-per-scene.

### §16.1 Two dial families — and they are ORTHOGONAL
A scene's control params split in two, and the POC proved they're independent (a 350-word **terse** render still fully realized the scheme beat + info-asymmetry — you compress the *prose*, you don't drop the *beat*):

| Family | Dials | Question | Checked by |
|---|---|---|---|
| **Structural** (what happens) | beat/motif (`motif_application`), `info_asymmetry`, `tension`, present cast (`present_entity_ids`), POV (`pov_entity_id`), `goal`/`synopsis`, grounding (`scene_grounding_pins`), canon (`canon_rule`) | *What must occur?* | the `motif_conformance` judge (§14) |
| **Stylistic** (how it reads) | **length/`target_words`**, density + pace (`style_profile`), voice (`voice_profile`) | *How long / what texture?* | a length/style check (advisory) |

→ Compressing length does **not** threaten conformance; over-constraining structure does **not** dictate prose texture. Keep the two dial families separate.

### §16.2 What already exists vs the one to add
Most dials are **already in the schema, already scene-scoped**: `outline_node.tension` (1-5), `style_profile` (density/pace 0-100, scope work|chapter|scene, most-specific wins), `voice_profile` (per character, applied when present), `pov_entity_id`, `present_entity_ids`, `scene_grounding_pins`, `canon_rule`. The **one missing dial is length** — add **`style_profile.target_words INT` (nullable)** (or a band `flash|short|standard|long`), scoped + resolved exactly like density/pace. Do **not** invent a new ad-hoc parameter mechanism — extend the existing scoped-profile so all stylistic dials resolve through one chokepoint.

### §16.3 How a dial actually controls output
The **packer** resolves each scene's most-specific parameters and threads them into the **per-scene generation prompt** (the POC's scene prompts carried beat + roles + length + density → output tracked). Empirical length adherence on the weak model: target 350→**322** (-8%), 700→**771** (+10%), 1300→**1682** (+29%). **Monotonic + good at typical targets, overshoots long.** → pair `target_words` with a derived **`max_tokens` cap** + an optional **post-gen trim** + an **advisory length flag** when out of band (weak models ramble on "long/lush"). The dial is directionally reliable; the cap enforces the ceiling.

### §16.4 Who sets the dials
- **Planner sets defaults** — beat-derived, like adaptive-K already keys K on tension (a climax scene → longer/`target_words` higher + higher tension; a connective scene → shorter). The planner emits per-scene `tension` today; it emits `target_words` the same way.
- **Author overrides any scene** — the most-specific scope (a per-scene `style_profile` row) shadows the chapter/work default. Manual control is a peer to the planner's defaults (the §3.5 authoring principle).
- **Chapter length = Σ scene `target_words`** → to hit the ~3,000-word standard (§7.2 research), the planner picks `scenes_per_chapter` × `target_words` to sum to the work's chapter-length goal — a derived budget, not a magic number.

### §16.5 Phasing
`style_profile.target_words` + the `max_tokens`-cap/trim is **P1** (small, high-value — it's the chapter-length control the §7 POC flagged). Planner-emits-`target_words` is **P1/P2** (mirrors the existing per-scene tension emission). The advisory length flag folds into the §14 conformance surface.

---

## §17 Long-form composition — decompose → generate → assemble → STITCH (lost-in-the-middle control)

> A standard-or-long, detailed chapter (web-novel ~3k, or 仙逆/Renegade-Immortal scale) is **NOT** generated by a longer single prompt — that triggers **lost-in-the-middle**: the model rushes, rations attention, and the middle beats thin/repeat. POC 5 ([research §8](../research/2026-06-26-motif-prompt-control-poc.md#L1)) measured it: a one-shot ~3000-word ask **undershot to 2,357** and rationed ~393 words/beat; the **scene-decomposed** version **hit 3,241** with uniform ~540 words/beat and full middle-beat depth. **This is the architecture that controls long chapters** — and it's why the engine is scene-based, not chapter-based.

### §17.1 The pipeline (the engine already does 1-3; 4 is new)
```
1. DECOMPOSE  : chapter → fine motif sub-beats. A LONGER/more DETAILED chapter = MORE/finer scenes,
                NOT longer scenes. (planner `scenes_per_chapter` + §16 `target_words` per scene.)
2. GENERATE   : each scene SHORT, at full attention (no middle to lose), with bible + plan + prior-tail
                (the packer: canon + present-entities + prior context).  [cowrite engine, exists]
3. ASSEMBLE   : concatenate scenes into the chapter.
4. STITCH     : a chapter-level consistency/revise pass over the assembled scenes.  [NEW]
```
**Why short scenes win:** a ~550-word scene has no "middle" for attention to sag in; each is generated beginning-to-end at full quality. Length is reached by **count of well-attended scenes**, not by stretching one generation past the model's coherent span.

### §17.2 The STITCH pass (the new architectural piece)
Independently-generated scenes leave **seams** (POC 5: higher cross-scene repetition; a crisis scene drifting into the breakthrough; reused imagery across the boundary). The stitch pass is a **chapter-scoped revise op** that:
- **smooths transitions** between adjacent scenes (the joins read continuously);
- **dedups repeated imagery / phrasing** across scene boundaries (the cross-scene repetition signal);
- **fixes over-resolving** (a scene that completed a beat the next scene must still do — re-scope it);
- **checks scene-to-scene continuity** (props/positions/time-of-day carried), feeding/reusing the **§14 conformance** signals.

**Implementation:** reuse the **generate→critique→revise** loop the prior-art doc validated (Re3/Dramaturge) — a `generation_job` with `operation='stitch'`, scope = chapter, input = the assembled scenes + their plan + the cross-scene repetition/continuity findings; it emits a revised chapter (or per-seam edits). **Advisory + author-gated** (§14.6 stance): the stitch proposes; the author accepts/edits — it never silently rewrites committed prose.

### §17.3 How length + detail are dialed (ties §16)
- **Longer chapter** → planner raises `scenes_per_chapter` (more beats) — *not* a bigger per-scene `target_words` (which re-invites the middle sag). Each scene stays in the model's coherent span.
- **More detailed** (仙逆 slow-burn) → finer beat granularity (split a beat into setup/turn/aftermath sub-scenes) + a higher per-scene `target_words` within the coherent span (~500-900w, where adherence held — §16.3).
- **Chapter length goal** = Σ scene `target_words`; the planner solves `scenes × target_words` to the goal (§16.4).

### §17.4 Honest limits
- **Stitch adds a pass** (cost + latency) — gate it (auto for `/generate auto`, on-demand in co-write); cache by assembled-chapter hash (the extraction/summary md5 precedent).
- **Long-range drift** beyond a chapter is still the L0-L3 memory + §14 arc-conformance job's domain, not the stitch pass (which is chapter-local).
- **Over-stitching** could flatten deliberate motifs/voice — the stitch must respect `style_profile`/`voice_profile` and the structural dials (§16.1); it smooths *seams*, it does not re-homogenize prose.

### §17.5 Phasing
Scene-decompose + per-scene generation **exist** (A3 + cowrite). **`scenes_per_chapter`-for-length** is a planner config tweak — **P1**. The **STITCH pass** is **P2** (it needs the assembled-chapter revise op + the cross-scene repetition/continuity check). The arc-scale long-range drift guard is **P4** (§14 arc-conformance).

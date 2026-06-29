# Narrative Motif Library — Master Plan (parallel-execution)

> **Date:** 2026-06-26 · **Spec:** [`2026-06-26-narrative-motif-library.md`](../specs/2026-06-26-narrative-motif-library.md) (read **§R1 + §R2** — locked decisions + resolutions) · **Audit:** [`2026-06-26-motif-library-audit.md`](../reports/2026-06-26-motif-library-audit.md).
> **Shape:** long-run, **clear-everything-before-build**. This plan is the **parallelization contract**: a serialized **F0 foundation** that *freezes the shared interfaces*, then **disjoint workstreams** (one file-owner each → git/worktree-parallel-safe) that build concurrently against those frozen contracts.
> **Rule of disjointness:** no two workstreams edit the same file. Shared/existing files have **exactly one** workstream owner (listed per WS). New files are namespaced per WS. This is what makes the fan-out safe.

---

## §1 Parallelization strategy

```
WAVE 0 (serial)         WAVE 1 (parallel, P1)              WAVE 2 (parallel, P2+)
┌──────────────┐        ┌──────────────────────┐          ┌────────────────────┐
│ F0 FOUNDATION│───────▶│ W1 CRUD+clone/adopt   │          │ W8 Mining (P3)     │
│ freeze:      │        │ W2 Planner select+bind│          │ W9 Import (P4, but │
│ • schema     │        │ W3 Retrieval+embed    │          │    before W8)      │
│ • models     │        │ W4 MCP tools          │          │ W10 Arc templates  │
│ • repo iface │        │ W5 Conformance        │          │ W-STITCH (§17)     │
│ • config/deps│        │ W6 Frontend/UX        │          │ W11 Publish/adopt  │
│ • contracts  │        │ W7 Seed packs         │          │     sync + quotas  │
└──────────────┘        └──────────────────────┘          └────────────────────┘
   1 owner, lands         6-7 owners, concurrent             concurrent, gated on
   first, FROZEN          (W7 needs only schema)             W1-W5 contracts
```

**Why F0 first:** every WS consumes one of {the schema, a model type, a repo method signature, the `retrieve()` contract, the judge-dim shape, the MCP envelope}. Freeze those once → the WSs never block on each other. F0 ships **stubs + signatures** (compiling, tested-as-interface) so WSs build against a green contract, not vapor.

**Integration = contract tests, not big-bang merge.** Each WS ships against F0's frozen signatures + a contract test. The reconciliation node (§6) is a live-smoke that exercises the assembled P1 path; it should be near-trivial if the contracts held.

---

## §2 Dependency DAG (P1)

```
F0 ─┬─▶ W3 retrieval ─┐
    │                 ├─▶ W2 planner select+bind ─┐
    ├─▶ W1 CRUD ──────┘                           ├─▶ R-NODE (P1 live-smoke)
    ├─▶ W1 ──▶ W4 MCP ────────────────────────────┤
    ├─▶ W5 conformance ───────────────────────────┤
    ├─▶ W7 seed packs ────────────────────────────┘   (W7 needs only the schema)
    └─▶ W6 frontend ──(consumes W1/W2/W4 API contracts, frozen in F0 §3.6)
```
- **W2 depends on W3** (the `retrieve()` result shape) — but only the *signature*, frozen in F0, so they build concurrently; W2 mocks `retrieve()` until W3 lands.
- **W4 depends on W1** (the repo + the clone/adopt primitive) — same: signature frozen in F0.
- **W6 (frontend)** consumes the API/contract shapes frozen in F0 §3.6 — starts immediately against the mockups + frozen DTOs.

---

## §3 F0 — FOUNDATION (serial, lands first, then FROZEN)

**Owner:** 1 agent. **Files (sole owner):** `db/migrate.py`, `db/models.py`, `config.py`, `deps.py`, `db/repositories/motif_repo.py` (interface + CRUD stub), `db/repositories/motif_retrieve.py` (interface stub), `tests/contracts/`. **Phase:** P1 gate-zero.

### F0.1 Schema (authoritative = spec §R1.4)
Ship the migration exactly as spec §R1.4: `motif` (no book_id, +`language`, +`source_version`, platform `embedding_model`, `embedded_summary_hash`, 2 tenancy partials keyed `(owner,code,language)`/`(code,language)`, the `motif_user_owned` CHECK), `motif_application` (+`book_id`, `motif_id` FK `ON DELETE SET NULL`, +`motif_version`, +`annotations`, index `(book_id, motif_id)`, the app-guard that `outline_node_id ∈ project_id`), `motif_link` (+ cycle guard + same-tier-only rule), `arc_template` (layout stores resolved `motif_id`), `import_source` (scope keys, **NO visibility column**). Idempotent single-DDL house style. **Tenancy guards are DB-level** (the CHECK + the partials) — audit B-2.

### F0.2 Models (`db/models.py`)
Pydantic: `Motif`, `MotifBeat`, `MotifRole`, `MotifLink`, `MotifApplication`, `ArcTemplate`, `ArcPlacement`, `ImportSource`. **`ForbidExtra` on every create/patch arg model** (audit S2). These are the shared types every WS imports — freeze field names now.

### F0.3 Repo interfaces (signatures frozen; F0 ships CRUD, W3 fills retrieve)
```python
# motif_repo.py  (F0 implements CRUD; W1 extends with clone/adopt/publish)
class MotifRepo:
  async def create(user_id, *, code, language, **fields) -> Motif        # stamps owner=user_id, rejects both-NULL
  async def get_visible(caller_id, motif_id) -> Motif | None             # THE read predicate (R1.1): system|public|owner
  async def patch(caller_id, motif_id, *, expected_version, **fields)    # optimistic-lock; re-embeds on summary change
  async def archive(caller_id, motif_id) -> None
  async def list_for_caller(caller_id, *, scope, genre, kind, status, q, language) -> list[Motif]
  async def clone(caller_id, src_motif_id, *, target_owner, retag_genres=None) -> Motif  # the ONE clone primitive (=adopt)
# motif_retrieve.py  (W3 implements; W2 consumes — signature frozen HERE)
class MotifRetriever:
  async def retrieve(caller_id, *, book_id, project_id, genre_tags, language,
                     beat_role, tension, prev_effects) -> list[MotifCandidate]   # tier-merged, SQL-pre-filtered, cosine-ranked
# MotifCandidate = {motif: Motif, score: float, match_reason: dict}   # match_reason = {tension, genre, precond, cosine}
```

### F0.4 Config (`config.py`)
`motif_embed_model` (the **fixed platform** embed model id — R1.1.2), `motif_retrieve_top_k`, `motif_min_score`, `motif_max_reapply`, `plan_*_scenes_per_chapter` (exists), `motif_mine_min_judge` (P3), per-user quotas (`motif_max_public`, `motif_max_adopt`).

### F0.5 Cross-cutting contracts (frozen interfaces other WSs implement)
- **Conformance dim shape** (W5): `critic.motif_conformance = {beat_realized: bool, tension_band_match: bool, calibrated: bool}` written into `generation_job.critic` JSONB.
- **MCP tool meta** (W4): reuse the existing `make_stateless_fastmcp("composition")` + `require_meta`/`require_book_owner`/`require_user_scope`/`mint_confirm_token`/`ForbidExtra`/`uniform_not_accessible` — no new kit.
- **The clone primitive** (F0.3 `clone()`) is the single mechanism for adopt + cross-genre-retag + customize (R1.1.1).

### F0.6 API/DTO contracts (frozen for W6 frontend)
Freeze the request/response JSON shapes for: motif list/get/create/patch/clone/catalog, the decompose-preview `+motif_id/match_reason/role_bindings`, the conformance trace payload, the swap `PATCH …/motif`. W6 builds against these immediately.

**F0 eval-gate:** migration applies idempotently on a throwaway DB; the 2 tenancy partials + the `motif_user_owned` CHECK reject a both-NULL private insert; `get_visible` returns system/public/owner and **NOT** another user's private (the IDOR test); contract tests for every signature compile + pass against the stubs.

---

## §4 WORKSTREAMS (Wave 1 = P1, parallel)

Each: **scope · depends · exposes · owns-files (disjoint) · eval-gate**.

### W1 — Motif CRUD + clone/adopt/publish + catalog + quotas
- **Scope:** the HTTP surface (§5 corrected): list/get/create/patch/archive, **clone** (=adopt, the one primitive), publish (visibility flip), catalog projection (**allow-list**, no embedding/examples/raw source_ref — audit B-3), per-user quotas (B-4).
- **Depends:** F0 (repo CRUD + clone). **Exposes:** the catalog + clone API (W6 consumes).
- **Owns:** `routers/motif.py`, `db/repositories/motif_repo.py` (extends F0's CRUD with clone/adopt/publish — F0 hands ownership to W1 after foundation), `tests/unit/test_motif_router.py`.
- **Eval-gate:** clone is idempotent + resets id/owner/timestamps/version + strips `examples[]` on imported-derived publish (trigger test); catalog never leaks a non-allow-list field; quota rejects the N+1 publish; tenancy IDOR test green.

### W2 — Planner select+bind (the core value)
- **Scope:** §3.1 rework of `plan.py` L2: `retrieve → select (adaptive-K aware) → bind (role→cast) → motif_application`; the **no-match fallback** to invent-path; the **tension 1-5 ↔ 0-100 reconcile** (audit R3); cost re-estimate after binding; **swap-after-gen = archive-not-delete** (R2.6); `match_reason` surfaced.
- **Depends:** F0 (`retrieve()` signature, `MotifApplication`), W3 (impl — mock until landed). **Exposes:** the decompose-preview `+motif` fields.
- **Owns:** `engine/motif_select.py` (new), `engine/plan.py` (the L2 edit — sole owner), `engine/adaptive_k.py` (tension reconcile — sole owner), `routers/plan.py` (preview fields), `tests/unit/test_motif_select.py`.
- **Eval-gate:** `scripts/eval_motif_planner.py` — **3-way** motif-planner vs A3-invent vs A3-invent+plot-nudge (audit AI-quality), primary metric = plot-density on the labeled seed; **fallback-path non-regression** (no-match → A3 coherence non-inferior); reproducible top-1 (tie-break by `mining_support`/`judge_score`/`code`).

### W3 — Retrieval + platform embedding
- **Scope:** implement `MotifRetriever.retrieve()`: **SQL pre-filter** (`genre ∩ + status='active' + tier predicate + language`) **before** loading vectors (audit data-R1), brute-force cosine top-K in app code, the `match_reason` breakdown. The **platform-embed pipeline** (`motif_embed_model` via provider-registry `/internal/embed`), `embedded_summary_hash` staleness + transactional re-embed-on-summary/clone.
- **Depends:** F0. **Exposes:** `retrieve()` (W2) + the embed helper (W1 clone uses it).
- **Owns:** `db/repositories/motif_retrieve.py`, `engine/motif_embed.py` (new), `tests/unit/test_motif_retrieve.py`.
- **Eval-gate:** pre-filter bounds the candidate set (no full-table vector load); cosine ranking correct; **cross-model contamination is impossible** (one platform model — assert all motif vectors share `embedding_model`); re-embed-on-summary-edit is transactional (no stale-vector window in the same tx).

### W4 — MCP tools (§13 corrected + R2.8)
- **Scope:** R-tier (`_search`+`status`, `_get`, `_suggest_for_chapter`, `_arc_suggest`), A-tier (`_create`, `_bind`), **W-tier confirm** (`_adopt` [now Tier-W], `_mine`, `_arc_import_analyze`, `_conformance_run`) → **202+poll worker enqueue + consumed-token ledger** (R2.8); per-tool IDOR project-scope assertion; `_meta.scope='user'`+`require_user_scope` for user-tier tools; `ForbidExtra` closed-enum tier.
- **Depends:** F0 (envelope contract), W1 (repo). **Exposes:** the agentic surface.
- **Owns:** `mcp/server.py` (the motif tool additions — sole owner of this file for the feature), `routers/actions.py` (the new confirm descriptors + consumed-token ledger — sole owner), `tests/unit/test_motif_mcp.py`.
- **Eval-gate:** IDOR (foreign motif_id → `uniform_not_accessible`); tier-W replay blocked by the ledger; `_create` cannot construct a both-NULL row; user-scope guard runs for user-tier tools.

### W5 — Conformance (binary, advisory) + calibration harness
- **Scope:** the `motif_conformance` binary judge dim (R2.1) written to `generation_job.critic`; the **calibration harness** (binary `calibrate_judge` against the PO seed + strong-model bootstrap); the **trace read** (`outline_node ⋈ motif_application ⋈ generation_job`); the **coarse chapter_id** conformance only (arc extract-diff is P4).
- **Depends:** F0 (the critic-dim shape), generation_job (exists). **Exposes:** the trace payload (W6).
- **Owns:** `engine/motif_conformance.py` (new), `scripts/calibrate_motif_conformance.py`, `routers/conformance.py` (the trace read), `tests/unit/test_motif_conformance.py`.
- **Eval-gate:** the binary judge calibrates (kappa ≥ 0.4) on the seed OR ships labeled "uncalibrated-advisory"; the trace join returns planned│realized│conformance per scene; advisory never hard-gates a commit.

### W6 — Frontend / UX (studio-integrated)
- **Scope:** resolve **audit H-8** — integrate into the composition studio (not a separate app), add the missing states (empty/loading/error/permission/cost-confirm), the library/editor/planner-binding/manual-build/trace screens, the **mobile fallback + a11y** for the timeline (P1 = motif screens; arc-timeline is P4 with W10). **Simple-mode** (plain-language, hide narratology jargon) for the beginner persona.
- **Depends:** F0 §3.6 DTOs (frozen) + the mockups. **Exposes:** nothing back-end.
- **Owns:** `frontend/src/features/composition/**` motif subtree (new components/hooks/api/types — disjoint from existing composition FE by namespace), i18n ×4.
- **Eval-gate:** tsc + vitest green; empty/error/permission states render; a11y (ARIA, keyboard, focus) on the motif screens; mobile stack-down.

### W7 — Seed packs (data-only, fully parallel)
- **Scope:** author the **tu-tiên + báo-thù** system-tier motif packs (R1.4 schema), abstracted to roles+beats+conditions+examples (author-written, not source prose); the seed migration (deterministic uuids, `owner_user_id NULL`, migrate-only — the system-write chokepoint).
- **Depends:** F0 schema **only** (starts immediately, no code deps). **Exposes:** the seed data.
- **Owns:** `scripts/seed_motif_packs/*.json`, `db/seed_motifs.py`, `tests/unit/test_seed_motifs.py`.
- **Eval-gate:** seeds load idempotently as system-tier; every seed validates against the `Motif` model; the PO reviews the pack content.

---

## §5 WORKSTREAMS (Wave 2 = P2-P4, parallel after Wave 1 contracts)

- **W8 — Mining (P3):** `motif_beat` extractor in **knowledge-service** `loreweave_extraction` (cross-service; its own extractor-version) + PrefixSpan over `event_order`-ordered beat sequences + LLM abstraction + binary judge → `status='draft'` motifs (R2.3). **Owns:** knowledge-service extraction files + `worker/operations.py:mine_motifs` + `engine/motif_mine.py`.
- **W9 — Import/deconstruct (P4, runs BEFORE W8):** `import_source` ingest + web-search augment + `analyze_reference` (LLM-direct deconstruct, riding P1/P2/P3 map-reduce) → `arc_template`+motifs `source='imported'`. **Owns:** `routers/import.py` + `engine/motif_deconstruct.py` + the import_source repo.
- **W10 — Arc templates (P4):** `arc_template` CRUD + the **thread×chapter timeline editor** (W6 extends FE) + **apply** (proportional placement-rescale R2.5) + arc-conformance coarse. **Owns:** `routers/arc.py` + `engine/arc_apply.py` + the FE timeline subtree.
- **W-STITCH (P2):** the §17 delta on `engine/stitch.py` (R2.7: repetition signal + dial-respect + ≤2-scene fix + overlapping-window + eval-gate). **Owns:** `engine/stitch.py` (sole owner) + `tests/unit/test_stitch_motif.py`.
- **W11 — Publish/adopt sync + quotas (P2):** upstream-diff (3-way via `source_version`) + the per-user ceilings + the consumed-token billing. **Owns:** `routers/motif_sync.py`.

---

## §6 Reconciliation nodes (live-smoke gates)

- **R-NODE-P1 (after Wave 1):** stack-up live-smoke — create a user motif (W1) → seed pack present (W7) → decompose a chapter that binds a seed motif (W2+W3) → `motif_application` written + `match_reason` surfaced → conformance trace shows planned│realized (W5) → MCP `_suggest_for_chapter` returns the same candidate (W4) → FE renders it (W6). Token: `live smoke: motif bound + traced on a real stack-up`.
- **R-NODE-P3/P4:** mining produces a draft → promote → reuse; import a work → arc_template → apply → conformance.

---

## §7 Build-time risk guards (carry the audit blockers as tests, not memory)

Every audit BLOCKER becomes a **failing test first**: B-1 cross-model-cosine-impossible (W3); B-2 both-NULL-write-rejected + IDOR-read (F0/W1/W4); B-3 examples-stripped-on-publish + catalog-allow-list (W1); B-4 quota + usage-billing-precheck (W1/W4/W11); H-2 motif_link cycle + same-tier (F0); H-4 swap-archives-not-deletes (W2); H-5 application per-book aggregate (F0/W5); F-3 conformance-binary-calibrates-or-says-uncalibrated (W5).

---

## §8 Execution model (how to actually run it parallel)
1. **F0 lands serially** (1 agent/worktree), reviewed, **merged** → the contract is frozen.
2. **Wave 1 fans out** — W1-W7 each in its own **worktree** (disjoint files → no merge conflicts); each builds against frozen F0 + a contract test; each `/loom`-sized internally.
3. **R-NODE-P1 live-smoke** reconciles Wave 1.
4. **Wave 2 fans out** (W8-W11 + W-STITCH) against the now-real P1.
5. Each WS = its own detailed-design doc (next step: fan out one design agent per WS) → then `/warp` or per-WS `/loom` to build.

**Next step:** fan out **one detailed-design sub-agent per Wave-1 workstream** (W1-W7) — each produces a full file-by-file design + task list + tests against the frozen F0 contract. Synthesize into per-WS plan docs, then build.

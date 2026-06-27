# ▶ NEXT SESSION — Narrative Motif Library BUILD (handoff)

## STATUS (2026-06-27 PM) — WAVE 2 IN PROGRESS · W2-F0 + Batch A landed · Batch B next

**Wave-2 foundation + Batch A are built, verified, committed on `feat/narrative-pattern-library`:**
- **W2-F0 worker-seam freeze** `1330b1b4` — the three Tier-W motif ops (`mine_motifs`/
  `analyze_reference`/`conformance_run`) already enqueue via the confirm effects
  (`routers/actions.py`); the gap was the worker handler. Froze the 3-way collision zone
  (`worker/constants.py` + `worker/job_consumer.py`) once: each op dispatches to a WS-owned
  stub engine module (`engine/motif_mine.py` W8 · `motif_deconstruct.py` W9 ·
  `motif_conformance_run.py` W5-wiring) with frozen signatures + input envelopes; stubs raise
  a terminal `ValueError` until filled. All Wave-2 config knobs pre-added. Freeze test +
  `Wave2-RECONCILE.md`. (23 green.)
- **W-STITCH** `94bc3aeb` (§17.2 R2.7) — seam repetition signal + overlapping-window +
  dial-respect + ≤2-scene over-resolve fix + no-flatten eval-gate on `engine/stitch.py`. (43 green.)
- **W11 sync** `6485017e` — `routers/motif_sync.py`: upstream-diff + apply-merge. HONEST
  **2-way** (not 3-way): the motif table keeps only the current row (no history), so the
  pinned-version base text is unrecoverable → `diff_mode="two_way"`, never a fabricated base.
  Owner-scoped patch + re-pin (H13). (42 green; 1074 collected.)

**⚠️ WORKTREE-BASE HAZARD (lesson — carry forward):** `isolation:"worktree"` agents in this
repo intermittently branch off the **concurrent `feat/composition-debt` track HEAD `0cc8ff6c`**
(merged PR #47), which **predates the entire motif library** (no `motif_repo.py`, no motif
schema, no W2-F0 seam) — NOT off `feat/narrative-pattern-library`. A branch-merge would drag the
whole other track in. **Mitigation in force:** build Wave-2 WSs with **non-isolated agents in the
main tree** (correct base, commit directly); if a worktree must be used, add a **base-guard**
(assert `motif_repo.py` + `mine_motifs` seam exist, else STOP) and reconcile by **cherry-picking
the WS's own commit**, never merging its branch.

**W10 arc — BACKEND LANDED** (`feat/narrative-pattern-library`): `db/repositories/arc_template_repo.py`
(CRUD + clone/adopt + `list_public` allow-list + `count_shared_by_owner`, mirrors `motif_repo`
verbatim — same 2-tier read predicate, same conditional-param binding that does NOT bind an unused
`$1` for scope=system/public, optimistic-lock patch), `routers/arc.py` (`/v1/composition/arc-templates`
list/catalog/get/create/patch/archive/adopt **+ `apply`-preview**), `engine/arc_apply.py` (PURE
deterministic apply: R2.5 proportional placement-rescale into [1..target] with endpoints anchored +
arc_roster bound ONCE → propagated to every placement + a §12.6 drop/merge report that is NEVER
silent), `deps.get_arc_template_repo()`, `main.py` +1 include, models `ArcTemplateCreateArgs`/
`ArcTemplatePatchArgs`/`ArcThread`/`ArcRosterEntry`/`ArcApplyArgs`/`ArcApplyPlan`/`ResolvedPlacement`/
`DropMergeEntry`. Tests: `tests/unit/test_arc_template_repo.py` (18) + `test_arc_apply.py` (16) = 34
green; 1108 collected; provider-gate clean. NO migration (arc_template F0-frozen). NO LLM/DB in apply.

**▶ NEXT — Batch B continues:** W9 import (`import_source` ingest + `engine/motif_deconstruct.py`
fills the W2-F0 stub; consumes W10's frozen `arc_template_repo` to write deconstructed arc rows) →
W8 mine (cross-service `motif_beat` extractor in knowledge-service + `engine/motif_mine.py`). Plus
the W10 follow-ups below. LLM/cross-service live-smoke (W8/W9 deconstruct+mine, W5 conformance
extract-diff) defers to an lm_studio + embedding-credential stack-up (R-NODE-P3/P4), mirroring the
R-NODE-P1 LLM-slice deferral.

**Deferred — W10 (NEW, gate-passing):**
- **`D-W10-FE-TIMELINE`** (gate 1 out-of-scope · target W10-FE / W6 extends): the FE thread×chapter
  arc-timeline subtree (the shared timeline editor, spec §10) — explicitly fenced out of this
  backend slice; the apply-preview JSON (`ArcApplyPlan`) is its data contract.
- **`D-W10-APPLY-PLANNER-MATERIALIZE`** (gate 2 large/structural · target Batch-B live-smoke): the
  apply endpoint returns the PURE plan only — it does NOT materialize `outline_node` rows, write a
  `motif_application` ledger, or invoke the LLM decompose planner. That deep planner integration
  (turn the rescaled placements into a committed multi-chapter outline, §12.5) rides the existing
  `engine/plan.py` decompose path + needs a stack-up live-smoke; build when W9/W8 bring the LLM rails up.
- **`D-W10-ARC-CONFORMANCE`** (gate 3 naturally-next · target P4 with W5 arc-diff): coarse
  arc-conformance (thread-progress / pacing / succession diff of realized arc vs template, §14.4 altitude 3)
  depends on the import/extract path (W9) + W5's deferred arc-diff dimension — implementable only once
  those land. Master-plan §5 W10 lists it; not in the backend-CRUD/apply slice.

Carried: `D-MOTIF-SYNC-3WAY-BASE` (W11 schema), `D-WSTITCH-LIVE-SMOKE`.

---

## (historical) STATUS (2026-06-27 AM) — WAVE 1 BUILT + MERGED + RECONCILED · Wave 2 is next

**All 7 Wave-1 workstreams (W1–W7) built in parallel worktrees, merged into
`feat/narrative-pattern-library`, and reconciled.** Merge was clean (only `main.py`
touched by 2 branches — W1+W5 router includes, union-resolved). Merged-branch VERIFY:
**843 unit + 130 DB-integration + contracts green**; the 26 MCP-loopback errors are the
pre-existing `StreamableHTTPSessionManager` test-infra flake (69 pass in isolation),
tracked as `D-W2-MCP-SESSION-ISOLATION`. Provider-gate clean.

**Per-WS commits (pre-merge):** W1 `420b82a0` · W2 `6a7e456d` · W3 `402ade85` ·
W4 `c8b06df4` · W5 `73674b49` · W6 `5d66136d` · W7 `210f4305`. Merged via 7 merge
commits + the reconcile commit on `feat/narrative-pattern-library`.

**Reconcile actions taken:**
- F0 additive follow-ups applied (deps/config were frozen during the wave): `deps.py`
  `get_motif_application_repo()` (W2/W5 need it); `config.py` `motif_connective_floor_margin=0.08` (W2 MD-3).
- W2↔W5 seams verified CLEAN: W2 writes `beat_key` into `motif_application.annotations`
  (W5 reads `annotations->>'beat_key'`); W2 never touches `generation_job.critic` (no clobber).
- W1↔W3 seam CLEAN: adopt copies the vector + `embedded_summary_hash` (no re-embed).
- W1↔W6 library CRUD paths MATCH (`/v1/composition/motifs*`); W6 adopt/conformance use the
  Tier-W `/actions/{op}/estimate|confirm` flow (adopt=Tier-W per RECONCILE §3).

**Deferred — Wave-1 reconcile seams (NEW; fix in a focused follow-up or Wave 2):**
- **`D-MOTIF-MCP-BIND-WIRING`** (gate #2 structural): W4's MCP `composition_motif_bind`/
  `_unbind` were authored against a `bind_motif(...)→dict` / application_id-undo contract;
  W2's engine landed exposing `apply_motif_swap`/`undo_motif_swap` (token-based undo). The
  tools now VALIDATE (work/gate/IDOR) then degrade cleanly (`reason: pending_bind_wiring`)
  pointing at the working HTTP twin. Reconcile the response-shape + undo model (token vs
  application_id) + rewrite the 2 bind tests. **HTTP bind/swap + planner auto-bind work now.**
- **`D-MOTIF-CONFORMANCE-ENGINE-WIRING`** (gate #3 naturally-next): W5's `judge_motif_conformance`
  functions exist + are unit-tested; the `engine.py` producer call-site is unwired. Conformance
  is advisory + OFF by default + uncalibrated, so it's intentionally dormant — wire when it
  graduates (needs `D-MOTIF-CONFORMANCE-GOLD-SET` first). The trace READ endpoint works.
- **`D-MOTIF-FE-PLANNERVIEW-WIRING`** (gate #3): W6 ships `useMotifBinding`+`MotifBindingCard`;
  the 1-line `selectTab`/`setSceneId` wiring in `PlannerView.tsx` (W2's FE seam) is unwired.
  The W6 dock panel provides the motif UI; this is the inline-in-planner enhancement (H-8 path).
- **`D-MOTIF-FE-CATALOG-ENDPOINT`** (HIGH, gate #2 — found by /review-impl): the W6 library's
  `catalog` tab calls `motifApi.list({scope:'public'})` → `GET /motifs`, which (a) 422s (the router
  accepts only `mine|system|all`) and (b) would BYPASS the B-3 allow-list (`list_for_caller` returns
  full rows). The catalog tab must call `motifApi.catalog` (`GET /motifs/catalog` = `list_public`,
  the `_CATALOG_COLS` allow-list) and the hook must handle the `CatalogMotif` shape (the tier facet
  reads `owner_user_id`/`visibility`, which the allow-list omits). Fix in the FE-integration pass
  (`D-MOTIF-FE-LIVE-SMOKE`). The companion `limit: 200 → 100` 422 (every list call) was fixed in-commit.
  NOTE: W7 seed packs now live in `app/db/seed_motif_packs/` (not `scripts/`); the W7 design doc's
  path refs are stale — code + this handoff are authoritative.

**Deferred — WS-reported (carried; many target R-NODE-P1):** `D-MOTIF-RETRIEVE-LIVE-SMOKE`,
`D-MOTIF-PGVECTOR-TRIGGER` (perf, ceiling=500), `D-W4-MINE-WORKER-LIVE-SMOKE` (Wave-2 compute),
`D-MOTIF-CONFORMANCE-GOLD-SET` (PO ~25-scene labeling), `D-MOTIF-CONFORMANCE-LIVE-SMOKE`,
`D-MOTIF-FE-LIVE-SMOKE`, `D-W7-VI-PACK` (vi seed packs — additive data), `D-W7-PO-REVIEW`
(genre-faithfulness sign-off), plus W5's P2/P4 scope-fenced dims (arc-diff, fine-anchor,
plot-density, act-rate).

**R-NODE-P1 — VERIFIED (data plane + live HTTP) ✅.** Two layers proven:
1. **Data plane** (committed guard `tests/integration/db/test_rnode_p1_dataplane.py`): all 7 WSs'
   code against a real seeded DB — W7 seeds (44/19) → W1 create → W3 retrieve (R4 degrade) → W2
   motif_application (beat_key in annotations) → W5 trace → W2 anti-repetition.
2. **Live HTTP** (composition-service REBUILT from this branch, ran against shared `loreweave_composition`):
   - W1 surface: `GET /motifs?scope=system` (44 seeds), create/get, `/motifs/catalog` (B-3 allow-list,
     no leaked examples/embedding/source_ref), `POST /motifs/{seed}/adopt` (clone, lineage set).
   - W2 bind: `PATCH .../outline/{node}/motif` → derived scenes + motif_application written + undo_token.
   - W5 trace: `GET .../conformance?scope=chapter` → references the bound motif.

**R-NODE-P1 caught 3 real DEPLOYMENT/RUNTIME bugs the 843+130 tests could NOT (all fixed + committed):**
- **Container boot crash** — W7 seed JSON lived in `scripts/` but the prod Dockerfile COPYs only
  `app/`; moved the packs into `app/db/seed_motif_packs/` (commit on branch).
- **HIGH: `GET /motifs?scope=system` 500** — `list_for_caller` bound `caller_id` as an UNUSED `$1`
  for system/public scopes → asyncpg `IndeterminateDatatypeError`; the default `all` scope masked it
  in every test. Fixed + a real-DB regression test over all scopes (`87004a8d`).
- **Stale-image gotcha** — a normal `docker compose build` reused a cached pre-Wave-1 image; needed
  `build --no-cache` + `up -d --force-recreate`. NB: this is a SHARED env — another track can recreate
  `infra-composition-service` from cache; re-`--no-cache` if `/openapi.json` lacks `/v1/composition/motifs`.

**▶ NEXT — only the LLM/semantic slice of R-NODE-P1 remains (optional, not a blocker):** real
LLM-decompose auto-bind (needs lm_studio up) + W3 semantic cosine (needs `motif_embed_model_ref`/
`_owner_id` → a provider-registry embedding credential, e.g. bge-m3) + the W4 MCP envelope path + W6 FE.
The data flow they exercise is already proven via the swap-bind path. **Wave 2 is unblocked:**
W8 mine · W9 import · W10 arc · W-STITCH · W11 sync. The `ws/w*` refs remain as per-WS history pointers.

---

## (historical) STATUS (2026-06-26) — F0 BUILD COMPLETE + FROZEN · Wave 1 is next

**F0 is built, verified, and committed.** The shared contract is frozen. Wave 1
(W1–W7) may now fan out in worktrees (disjoint per `00-RECONCILE §4`).

**F0 delivered** (`services/composition-service`): `db/migrate.py` (5 tables —
`motif`/`motif_link`/`motif_application`/`arc_template`/`import_source` — + `consumed_tokens`,
2×2 tenancy partials, the `motif_user_owned` CHECK, and 3 triggers: cycle/same-tier,
cross-project scope, publish-strip); `db/models.py` (row + `ForbidExtra` arg models);
`db/repositories/motif_repo.py` (CRUD + the real `clone`); `db/repositories/motif_retrieve.py`
(frozen stub, W3 impls); `config.py` + `deps.py`; `tests/contracts/` + `tests/integration/db/test_motif_migrate.py` + `test_motif_repo.py`.

**6 reconcile deltas folded:** D1 `motif.annotations`; D2 `motif_embed_owner_id` +
`motif_candidate_ceiling`; D3 `consumed_tokens` + `usage_billing_service_url`; D4 seeds
embed NULL (retriever tolerates NULL); D5 no-extension lineage (`'lineage:'||id`); D6
system seeds `unlisted`.

**`/review-impl` ran on F0 — 4 findings, all fixed in-commit (none deferred):**
- #1 no write-method behavior tests → added `test_motif_repo.py` (create/patch/archive/clone).
- #2 `clone` NULLed `embedded_summary_hash`, forcing W3 to redundantly re-embed → now copies it.
- #3 **B-3 bypass**: publish-strip keyed on `source='imported'` only, so an *adopted* clone
  of an imported motif would leak source passages on publish — matched W1 §1's documented
  expectation of `('imported','adopted'-from-imported)`. **Fixed** with an `imported_derived`
  lineage-taint column that `clone()` propagates and the trigger checks (adopted-from-AUTHORED
  stays false, so the strip is not over-broad). **W1's publish test should assert this path.**
- #4 foreign-`unlisted` IDOR not covered → added to the behavior test.

**Frozen-contract note for Wave 1:** the `Motif` model + `motif` table now carry
`imported_derived BOOLEAN` (B-3 taint) and `annotations JSONB` (D1) — additive; consume them,
do not re-add. `MotifRepo.patch` returns `Motif | None` (None = not-found/not-owned) and raises
`VersionMismatchError` on stale version (house convention).

**VERIFY:** `27 passed` on a throwaway DB (`infra-postgres-1`, PG18) — existing migrate (3, no
regression) + motif migrate risk-guards (6) + motif repo behavior (10) + contracts (8). Guards
green: B-1/B-2/B-3/H-2/H-5/N-1 + `get_visible` IDOR.

---

Paste the block below into the new session. Design+plan phase is COMPLETE + committed; next is BUILD (F0 first).

---

```
Continue the Narrative Motif Library build on branch `feat/narrative-pattern-library`
(repo d:\Works\source\lore-weave-mcp-fanout). The DESIGN + PLAN phase is COMPLETE and
committed (HEAD ~f4458bda, 6 motif-library commits). Nothing is built yet — the next
step is BUILD, starting with F0.

READ FIRST (in order; do NOT re-litigate locked decisions):
- Spec §R1 + §R2 (locked decisions + resolutions): docs/specs/2026-06-26-narrative-motif-library.md
- Master plan (parallel structure + DAG): docs/plans/2026-06-26-motif-library-master-plan.md
- Reconciliation (the 6 F0 contract deltas to fold + the cross-WS seams):
  docs/plans/2026-06-26-motif-library-ws/00-RECONCILE.md
- F0 detailed design: docs/plans/2026-06-26-motif-library-ws/F0-foundation.md
  (and W1-W7 *.md in that folder for the workstreams)

LOCKED (do not reopen): 2-tier + clone-to-customize (NO book tier; motif.book_id removed;
per-book customization = clone into a user-variant); ONE platform embedding model for all
motif vectors; `language` axis on motif (P1); motif_application per-book/project scope.
CORRECTIONS already folded: the flywheel causal-event graph does NOT exist (mining = scalar
event_order + a new motif_beat extractor, drop subgraph mining); STITCH already ships
(engine/stitch.py — §17 is a delta, not new); "the calibrated judge" scores extraction not
narrative (motif_conformance is binary-first, advisory, needs its own small gold set).

NEXT ACTION — BUILD F0 (serial; lands first, then FROZEN as the shared contract):
1. Fold the 6 deltas from 00-RECONCILE §1 into F0: D1 add motif.annotations JSONB; D2
   config motif_embed_model + motif_embed_owner_id; D3 consumed_tokens table + billing
   precheck; D4 seeds embed NULL + W3 lazy back-fill (retriever tolerates NULL-embedding);
   D5 no-extension lineage default ('lineage:'||id); D6 system seeds visibility='unlisted'.
2. Build F0 per F0-foundation.md: db/migrate.py (5 tables motif/motif_link/motif_application/
   arc_template/import_source + the cycle/same-tier/cross-project/publish-strip triggers),
   db/models.py (Pydantic + ForbidExtra), db/repositories/motif_repo.py (CRUD + clone),
   db/repositories/motif_retrieve.py (stub), config.py, deps.py, tests/contracts/.
3. VERIFY on a throwaway DB: migration idempotent; the 2 tenancy partials + motif_user_owned
   CHECK reject a both-NULL private insert; get_visible IDOR test (system/public/owner
   returned, another user's private NOT). This is F0's risk-boundary checkpoint + commit.
4. F0 is then the FROZEN contract → fan out Wave 1 (W1 W2 W3 W4 W5 W6 W7), each in its own
   git worktree (files are provably disjoint per 00-RECONCILE §4 → parallel-safe), each per
   its W*.md detailed design.
5. R-NODE-P1 live-smoke (create a user motif → seed pack present → decompose a chapter that
   binds a seed motif → motif_application written + match_reason → conformance trace), then
   Wave 2 (W8 mine · W9 import · W10 arc · W-STITCH · W11 sync).

WORKFLOW: this is XL; F0 is the first milestone. Run the loom/v2.2 gates per workstream
(VERIFY evidence, 2-stage review, live-smoke ≥2 services). Use worktrees for Wave-1
parallelism. Every audit blocker is a failing-test-first guard inside its WS doc — write the
RED test first.

PO RESIDUAL (does NOT block F0/Wave-1): label ~25 scenes for motif_conformance calibration
(per W5-conformance.md) OR ship conformance as pure-advisory and label later.

CONSTRAINTS: stage only the exact files you changed (NEVER git add -A — shared-tree hazard);
do NOT touch docs/sessions/SESSION_HANDOFF.md (it belongs to the concurrent
feat/composition-service track). Provider-gateway invariant (every LLM/embed/rerank call via
provider-registry) + MCP-first invariant (agentic logic as MCP tools) apply.

START: read the docs above, fold the 6 F0 deltas, then build F0 (schema → models → repo →
config → contract tests → VERIFY), and stop at the F0 checkpoint for review before Wave 1.
```

---

**Quick map of what's committed on this branch (design+plan, all docs):**
- `docs/research/2026-06-26-narrative-control-formalisms.md` · `…-motif-prompt-control-poc.md` (5 POCs)
- `docs/specs/2026-06-26-narrative-motif-library.md` (§R1/§R2 authoritative)
- `docs/reports/2026-06-26-motif-library-audit.md` (8 reviews)
- `docs/plans/2026-06-26-motif-library-master-plan.md`
- `docs/plans/2026-06-26-motif-library-ws/{00-RECONCILE, F0-foundation, W1…W7}.md`
- `design-drafts/motif-library/*.html` (8 mockups)
- POC scripts in scratchpad (throwaway, NOT committed).

# ▶ NEXT SESSION — Narrative Motif Library BUILD (handoff)

## STATUS (2026-06-27) — WAVE 1 BUILT + MERGED + RECONCILED · Wave 2 is next

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

**Deferred — WS-reported (carried; many target R-NODE-P1):** `D-MOTIF-RETRIEVE-LIVE-SMOKE`,
`D-MOTIF-PGVECTOR-TRIGGER` (perf, ceiling=500), `D-W4-MINE-WORKER-LIVE-SMOKE` (Wave-2 compute),
`D-MOTIF-CONFORMANCE-GOLD-SET` (PO ~25-scene labeling), `D-MOTIF-CONFORMANCE-LIVE-SMOKE`,
`D-MOTIF-FE-LIVE-SMOKE`, `D-W7-VI-PACK` (vi seed packs — additive data), `D-W7-PO-REVIEW`
(genre-faithfulness sign-off), plus W5's P2/P4 scope-fenced dims (arc-diff, fine-anchor,
plot-density, act-rate).

**R-NODE-P1 DATA PLANE — VERIFIED ✅** (committed as `tests/integration/db/test_rnode_p1_dataplane.py`,
the cross-WS regression guard). Ran all 7 WSs' code together against a real seeded DB via the
actual repo/engine paths: W7 seeds (44 motifs/19 links) → W1 create → W3 retrieve (R4 degrade,
genre+tension, no embed model) → W2 motif_application (beat_key in annotations) → W5 trace read
→ W2 anti-repetition aggregate. The W2→W5 `beat_key` seam is now verified DYNAMICALLY, not just
statically. (The full dev stack is up, but `infra-composition-service` runs the PRE-Wave-1 image —
NOT rebuilt, to avoid disrupting the shared healthy service + migrating the shared dev DB.)

**▶ NEXT — the remaining R-NODE-P1 surface (the Wave-2 entry gate):** the FULL HTTP + LLM-decompose
+ semantic-embed smoke. Needs: rebuild + restart `composition-service` from this branch (runs the
motif migration + W7 seeds on its DB — confirm the shared-env impact first), a platform embed model
configured (`motif_embed_model_ref`/`_owner_id` → a provider-registry embedding credential, e.g.
bge-m3) for W3's cosine path, and the test account driving auth → create book/project → decompose
(real LLM via lm_studio) → bind → trace via HTTP + the W4 MCP path + W6 FE. Run once at the Wave-2
stack stand-up, then Wave 2 (W8 mine · W9 import · W10 arc · W-STITCH · W11 sync). The `ws/w*`
branch refs remain as per-WS history pointers (worktrees pruned).

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

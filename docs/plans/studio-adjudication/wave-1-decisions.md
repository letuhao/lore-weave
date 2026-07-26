# Wave 1 — Quality Completion — adjudicated decisions

> 53 items · 49 DECIDED · 3 not-a-question · 1 deferred · 0 escalated.

> **These are INSTRUCTIONS, not suggestions.** Each was settled by reading source. Do not re-open a
> decided question. Where this contradicts the wave plan, **this file wins.**

---

## Deferred (tracked, non-blocking)

### BE-31-Q4-COST-DESCRIPTORS
DEFER the BE-Q4 cost GATE (confirmed: the spec's own v2/OQ-3 call is correct on the code) — but the wave MUST ship one guard now.

DO NOW (wave 31 / quality-heal, ~3 lines + 1 test): in the ported Polish/Quality/Coverage panels, do NOT render `job.cost_usd` from the `GET /v1/composition/jobs/{job_id}` poll response. It is a STRUCTURAL ZERO for `self_heal_propose`/`quality_report`: `engine.py:1415` returns the whole `job.model_dump()` (so `cost_usd`, db/models.py:377, IS on the wire), but `job_consumer.py:278` completes the job WITHOUT passing `cost_usd`, and `config.py:213-215` documents the unmetered seam ("the inline path leaves generation_job.cost_usd at 0"). Wiring it up ships a confident "$0.00" — the repo's own silent-success / fixture-seeds-what-the-writer-never-sets bug class. Add a test asserting the ported panels render no cost figure, and a code comment at the poll-hook pointing at config.py:213-215. Instead show a static "this action spends LLM tokens" warning (copy the string from the existing `requires` field: "human confirmation — this spends LLM tokens").

DO NOT DO NOW: the `composition.self_heal_propose` / `.quality_report` descriptors themselves. Confirmed NOT "missing infrastructure" (the generic spine exists, actions.py:96-101, with 11 descriptors and a proven paid-async template at actions.py:635/714) — I checked before deferring. It still clears defer gate #2 on four code facts: (1) these two ops enqueue via `get_generation_jobs_repo().create()` + `enqueue_job(redis)` (plan.py:246/312), NOT `_enqueue_motif_job`, so the spine needs a new generation-job enqueue variant; (2) a truthful estimate needs a chapter-scoped estimator (`_mine_estimate(scope="book")` is book-scoped and wrong); (3) real cost is not metered on this seam AT ALL, so "show the cost" is an unmetered-seam problem, not a display fix; (4) it converts three ALREADY-SHIPPED panels from one-click-POST to propose→preview→confirm, while spec 31 line 592 says this wave PORTS the self-heal route VERBATIM — changing the ported behavior mid-port is scope creep, and it drags in 2 new MCP propose tools + the frontend-tools/confirm_action contract.

NOT a critical blocker under the PO's narrow list: self-heal DELIVERS its result — the user gets what they pay for. This is a cost-visibility gap, NOT the "charge the user for nothing" class (the motif-mine-poll-404 precedent). So: defer row + keep going, exactly per PO policy 3. Contradicts none of §0 PO-1..4.

DEFAULT THE PO CAN VETO: when BE-Q4 is built in v2, fix the unmetered seam FIRST (thread real cost from the LLM client into `set_status(..., cost_usd=)` at job_consumer.py:278) — otherwise the confirm gate shows an estimate that can never be reconciled against an actual, and `authoring_unit_estimate_usd` stays a flat 0.05 guess forever.

**Defer row:** | **BE-31-Q4-COST-DESCRIPTORS** (= OQ-3) | Origin: Wave "quality-heal" (spec 31_quality_completion.md, BE-Q4 / QC-7) | **What:** The three paid quality actions (Run Polish / self-heal, Analyze quality, Coverage) have NO pre-spend cost estimate and NO billing precheck — plan.py:246/312 enqueue straight to a generation_job with zero `_precheck_or_402`. The fix is `composition.self_heal_propose` + `composition.quality_report` descriptors on the EXISTING generic `GET /v1/composition/actions/preview` → `POST /v1/composition/actions/confirm` spine (actions.py:96-101), mirroring `_execute_motif_mine` (actions.py:635) / `_execute_conformance_run` (actions.py:714). ⚠ **Do NOT invent `/self-heal/estimate`** — three such per-action routes already 404 in production (plan-30 §3.3). ⚠ The confirm effects **cannot** reuse `_enqueue_motif_job` — these ops enqueue via `get_generation_jobs_repo().create()` + `enqueue_job(redis)`, so the spine needs a generation-job enqueue variant. ⚠ Needs a NEW chapter-scoped estimator (`_mine_estimate(scope="book")` is book-scoped and wrong). ⚠ **Do the unmetered-seam fix FIRST**: thread real cost into `set_status(..., cost_usd=)` at worker/job_consumer.py:278 (today `generation_jobs.cost_usd` is a structural 0 for these ops — config.py:213-215). | **Gate reason: #2 (large / structural)** — cross-service contract (2 new MCP propose tools + the frontend-tools/`confirm_action` contract) + converts 3 ALREADY-SHIPPED panels from one-click-POST to propose→preview→confirm, while spec 31:592 mandates a VERBATIM port this wave. NOT gate #4 — the spine exists and this is buildable, just not here. | **Target: v2 cost-gate wave** (trigger: the LLM-seam per-job cost metering lands, or the first user complaint about blind spend). | **Not blocking.** Real cost-visibility gap across 3 already-shipped panels ⇒ a pre-existing gap, not this wave's regression. NOT the "charge the user for nothing" critical class — the action delivers its result. |

## Decisions

### Q-31-OQ2-HEAL-CORRECTION-KIND
NO — self-heal accept/reject is NOT a `generation_correction` in v1. Ratify QC-5 as written; do NOT add `heal_accept`/`heal_reject`; do NOT touch the CHECK constraint. Builder instructions, exactly:

(1) NO MIGRATION. Leave `generation_correction.kind`'s CHECK at `('edit','pick_different','regenerate','reject')` (services/composition-service/app/db/migrate.py:369). No new enum value ⇒ the `migration-check-constraint-must-backfill-all-historical-blocks` law is never triggered.

(2) M3 (quality-heal panel) writes ZERO corrections. Accepting or rejecting a proposed self-heal fix applies/discards the patch on the chapter text and nothing else — no call into `GenerationCorrectionsRepo.create`, no `composition_record_correction` invocation from the heal path. Add a unit test on the heal accept/reject handler asserting the corrections repo `create` is never called (spy/mock, count == 0).

(3) M4 (BE-9c) EXCLUDES self-heal from the flywheel denominator. In `services/composition-service/app/db/repositories/generation_corrections.py`, define ONE module-level constant `CORRECTABLE_OPERATIONS = ("draft_scene", "draft_chapter", "stitch_chapter")` and add `AND j.operation = ANY($2)` to `correction_stats`' WHERE (the query at generation_corrections.py:170-201, which today filters only on `j.project_id`), KEEPING the existing `NOT coalesce((j.input->>'selection_edit')::boolean, false)` predicate — defense in depth per F-Q3a. `self_heal_propose` is deliberately absent from the tuple. Never inline the literal at the call site.

(4) TEST THE EXCLUSION BY NAME. In the composition repo integration tests, seed a completed job with `operation='self_heal_propose', mode='auto'` (the exact pair `plan.py:246` writes) alongside a real `draft_chapter` job, and assert `correction_stats` returns `generations` counting ONLY the draft job — i.e. the self-heal job does not move `accept_rate`. This is the regression test that keeps the two halves of this decision (no heal correction + heal excluded from the denominator) from silently diverging.

(5) RECORD IT so it stops re-surfacing: one defer row, gate #5 (conscious won't-fix), with the revisit trigger being real user demand for heal-quality analytics — at which point the correct design is a SEPARATE signal (a `heal_outcome` table or a distinct stats surface keyed on `operation='self_heal_propose'`), NOT a new `kind` on `generation_correction`. Rationale the builder can quote: correcting a *fix* and correcting a *draft* are different signals; `self_heal_propose` runs `mode='auto'`, so any correction on it lands in the very `auto` column the flywheel's auto-vs-cowrite A/B compares — it would corrupt the denominator BE-9c exists to make honest.

PO default note (veto-able): this is the sane default — it costs nothing to reverse later (adding a kind is additive), while shipping the kind now permanently poisons the flywheel's only trustworthy number.

*Evidence:* services/composition-service/app/db/migrate.py:369 — `kind TEXT NOT NULL CHECK (kind IN ('edit','pick_different','regenerate','reject'))` (closed set; a new value = CHECK migration + the backfill-all-historical-blocks law). services/composition-service/app/routers/plan.py:246 — `create_job(project_id, created_by=user_id, operation="self_heal_propose", mode="auto", ...)` (the self-heal job IS mode='auto'). services/composition-service/app/db/repositories/generation_corrections.py:170-201 — `correction_stats` selects `j.mode` FROM `generation_job j` WHERE only `j.project_id = $1`, with NO `operation` filter ⇒ every self-heal/plan-pass/quality-report job already inflates the `auto` denominator; BE-9c's `AND j.operation = ANY($2)` goes here.

### Q-31-OQ1-PROPOSE-EDIT-NO-JOB
ADOPT (c) — the correction flywheel learns ONLY from structured generation (composition `generation_job`: engine runs + authoring runs). Studio-Compose `propose_edit` Apply/Dismiss records NO `generation_correction`, in v1 and by design. The code already made this call once: composition's own inline-edit path (`POST /works/{pid}/selection-edit`, engine.py:703, which DOES mint a real job) is explicitly EXCLUDED from the flywheel at generation_corrections.py:200-206 ("selection edits ... are NOT part of the draft-correction flywheel ... they'd inflate the cowrite `generations` denominator and drag its correction rate down — corrupting the cowrite-vs-auto eval signal"). Chat-authored prose is the same class of work (inline edit-assist) with strictly LESS structure, so options (a) and (b) both re-introduce the exact corruption BE-9c exists to prevent: (a) minting a `generation_job` for a chat turn puts non-draft turns into the `auto`/`cowrite` denominator; (b) a nullable `chat_run_id` + relaxed FK produces correction rows with NO denominator at all — `correction_stats` is a JOIN whose denominator is `count(DISTINCT j.id) FILTER (status='completed')` per `j.mode` (generation_corrections.py:181-206), so a job-less correction is uncountable and breaks the "numerator ⊆ denominator" invariant a prior /review-impl already had to fix.

BUILDER INSTRUCTIONS (concrete, no further thought needed):
1. DO NOT add a capture leg to `propose_edit` in Wave 1 / M4. `PROPOSE_EDIT_TOOL` keeps exactly `{operation, text, rationale}` (services/chat-service/app/services/frontend_tools.py:66-103). Do NOT add `job_id`/`correlation_id`/`chat_run_id` params — any arg change drifts contracts/frontend-tools.contract.json + the FE resolver (ProposeEditCard.tsx) for zero signal.
2. DO NOT touch the schema: `generation_correction.job_id UUID NOT NULL REFERENCES generation_job(id)` stays (services/composition-service/app/db/migrate.py:368). BE-9's ONLY schema work remains `ALTER TABLE authoring_run_units ADD COLUMN job_id UUID` (nullable) + `DraftOutcome.job_id`, per plan-30 BE-9. No FK relax, no second FK.
3. Make the scope EXPLICIT (the "and say so" half of (c)) — three edits:
   a. Docstring header of services/composition-service/app/db/repositories/generation_corrections.py: add "SCOPE (OQ-1, SEALED): the flywheel learns from STRUCTURED generation only — engine + authoring-run `generation_job` rows. Chat-authored prose (Studio Compose `propose_edit`) and inline selection-edits are OUT by design. Do NOT relax the `job_id` NOT NULL FK to admit a chat run."
   b. FE copy in the Wave-1 `quality-corrections` panel (header subtitle + empty state), one line: "Counts drafts from the engine and authoring runs. Inline chat edits (Compose) and selection edits aren't counted." — so the author cannot read `accept_rate` as covering all AI prose.
   c. Test, in the BE-9c allowlist test file alongside the required "a `plan_pass` job cannot move `accept_rate`" case (services/composition-service/tests/integration/db/test_repositories.py, GenerationCorrectionsRepo block): assert `create()` raises on a `job_id` that is not a `generation_job` row (FK holds ⇒ no chat-run backdoor), and assert a job with `input.selection_edit = true` does not move `accept_rate`.
4. Tracking (conscious won't-fix, CLAUDE.md gate #5 — NOT gate #2 "needs a design"; the design call is now made): file row `D-STUDIO-CHAT-PROSE-OUT-OF-FLYWHEEL` in SESSION_HANDOFF Deferred — "Studio Compose `propose_edit` prose is not captured as a `generation_correction` (OQ-1 decided (c)). If a future track wants the signal, the ONLY sanctioned shape is: route the Compose prose edit through the EXISTING composition selection-edit job path (engine.py:703) so it carries a real `generation_job.id`, then separately decide whether selection-edit jobs enter the denominator — never a nullable-FK/chat_run_id hack. Trigger: a spec for Compose's prose path."
DEFAULT-VETO NOTE for the PO: this is the spec's own recommendation (31 §OQ-1) and contradicts no sealed §0 decision (PO-1..4 are about panels/tool naming/spec ordering). Veto only if you want inline chat prose counted in the accept-rate — which would require re-opening BE-9c's denominator design.

*Evidence:* services/composition-service/app/db/repositories/generation_corrections.py:200-206 (correction_stats explicitly excludes `input.selection_edit` jobs: "selection edits run mode='cowrite' but are NOT part of the draft-correction flywheel (no correction is captured), so they'd inflate the cowrite `generations` denominator ... corrupting the cowrite-vs-auto eval signal") + :181-199 (denominator = `count(DISTINCT j.id) FILTER (WHERE j.status='completed')` FROM generation_job, LEFT JOIN generation_correction ON c.job_id=j.id — a job-less correction has no denominator); services/composition-service/app/db/migrate.py:368 (`job_id UUID NOT NULL REFERENCES generation_job(id) ON DELETE CASCADE`); services/chat-service/app/services/frontend_tools.py:66-103 (PROPOSE_EDIT_TOOL params = operation/text/rationale, no id); services/composition-service/app/routers/engine.py:703 (the existing `selection-edit` route that DOES mint a job — the only sanctioned future path); docs/specs/2026-07-01-writing-studio/30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md §0 PO-1..4 (none constrain this).

### Q-31-OQ3-PAID-ACTION-COST-GATE
**v1 = ZERO estimate routes. Port the three existing routes verbatim, and mechanically forbid a fourth.** The code confirms the spec's QC-7 is not merely a preference — it is what the architecture already implies.

**1 · Builder instruction (M2/M3, `quality-heal` + `quality-critic` + `quality-coverage`):** call the routes that already exist and are already wired:
- Run Polish → `POST /v1/composition/works/{project_id}/self-heal/propose` (`services/composition-service/app/routers/plan.py:199`), FE call site already present at `frontend/src/features/composition/api.ts:500` (`usePolishProposals` consumes it).
- Analyze quality → `POST .../quality-report` (`plan.py:267`; FE `api.ts:524`).
- Coverage → `POST .../promise-coverage` (`plan.py:364`; FE `api.ts:545`).
**Backend work for the cost gate in this wave: none.** Do NOT add `/self-heal/estimate`, `/quality-report/estimate`, `/coverage/estimate`, or any per-action estimate/preview route. Adding one is a `/review-impl` finding and must be reverted in the wave it appears.

**2 · Why no route is the RIGHT answer, from the code (this is the part a builder must internalise so they don't 'helpfully' add one):** on the generic spine the estimate is **not a route — it is a field in the signed confirm-token payload**. `_mine_estimate()` (`services/composition-service/app/mcp/server.py:271-277`) is computed *inside the MCP propose tool*, stuffed into the minted token as `estimate_usd` (`server.py:3020`), returned to the card as `estimate` (`server.py:3034`), surfaced verbatim by `GET /actions/preview` — which just decodes the token and returns `{descriptor, resource_id, payload, expires_at}` (`app/routers/actions.py:186-211`) — and re-read by the confirm effect's fail-closed billing precheck (`actions.py:640,691,721` → `_precheck_or_402`, `actions.py:517`). So a per-action estimate endpoint is architecturally *dead weight*: the spine that would carry the number needs a **descriptor + a propose tool**, never a new HTTP path. That is exactly BE-Q4.

**3 · The v1 cost controls (already shipped, sufficient, do not gold-plate):** an explicit button, an explicit `ModelPicker`, and the opt-in `rerank` toggle labelled "auto-tick (AI, costs more)". This is **not** the repo's "charge the user for nothing" defect class — all three routes return a real result (or a 202 + `job_id`); they merely lack a *pre*-estimate, which `quality-critic` and `quality-coverage` **already ship without today**. So this is a pre-existing gap across shipped panels, not a regression Wave 1 introduces, and it is not a CRITICAL blocker under the PO's stop-and-ask policy.

**4 · Make QC-7 mechanical, not a promise (cheap, do it in M2 — "a checklist item is DONE only when a test asserts its effect"):** add one test to the composition suite that introspects `app.main:app.routes` and asserts **no** route path under `/v1/composition/` contains `estimate` (the same FastAPI-introspection technique plan-30 §2 used to find the `add_api_route` blind spot a `@router.` grep misses). That single test is what actually stops the fourth 404 route from being born at 3am, and it costs ~10 lines.

**5 · BE-Q4 stays deferred (v2), already tracked — do not re-raise it, do not build it in Wave 1.** Row (already in spec 31 §BE table line 529 + OQ-3 line 737; restate it in the wave's defer register verbatim): `D-QUALITY-COST-GATE` · origin Wave 1 / M2 · *the three paid quality actions (self-heal propose, quality report, promise coverage) expose no pre-run $ estimate; fix = add `composition.self_heal_propose` + `composition.quality_report` (+ `.promise_coverage`) descriptors to `_ALL_DESCRIPTORS` (`actions.py:95-101`) with MCP propose tools that mint a confirm token carrying `estimate_usd`, mirroring `composition_motif_mine` exactly, and route the panels' Run buttons through the existing `confirm_action` card* · **gate #2 (large/structural)** — it is a new *interaction pattern* for dock panels (which today call REST directly and have no confirm-card path), plus replay-ledger + billing-precheck + contract-test surface across 3 panels and 2 services · **target: v2 / the wave that gives a Studio panel its first propose→confirm card.**

**Default I am picking (PO may veto):** ship v1 with no estimate rather than delay Wave 1 to build the descriptor spine — because the three panels involved are *already live with no estimate*, so v1 changes nothing about the user's cost exposure, and the correct fix is a whole interaction pattern rather than a route.

*Evidence:* services/composition-service/app/mcp/server.py:271-277 (`_mine_estimate` — the estimate is computed in the PROPOSE TOOL) → server.py:3020,3034 (it rides in the minted confirm-token payload as `estimate_usd`) → services/composition-service/app/routers/actions.py:186-211 (`GET /actions/preview` merely decodes the token and returns `payload` — it is NOT a per-action estimate endpoint) → actions.py:640,691,721 + actions.py:517 (`_precheck_or_402` re-reads `payload["estimate_usd"]` for the fail-closed billing gate). The three paid quality routes already exist and are already consumed: services/composition-service/app/routers/plan.py:199 (self-heal/propose), plan.py:267 (quality-report), plan.py:364 (promise-coverage); FE call sites frontend/src/features/composition/api.ts:500,524,545. `_ALL_DESCRIPTORS` (actions.py:95-101) contains publish/generate/motif_adopt/motif_mine/arc_import/conformance_run/5×authoring_run — and NO quality descriptor, which is precisely the BE-Q4 hole.

### BE-31-11b-INCLUDE-ARCHIVED
BUILD AS WRITTEN — but the spec over-states the work: half of it already exists. Exact builder instruction (XS, ~4 edits, no migration, no model change):

(1) REPO — `services/composition-service/app/db/repositories/canon_rules.py:88-97`. Change `list_all(self, project_id: UUID)` to `list_all(self, project_id: UUID, *, include_archived: bool = False)` and build the predicate exactly like the sibling repos already do (`outline.py:743` / `structure.py:232`):
    archived_pred = "" if include_archived else " AND NOT is_archived"
    query = f"SELECT {_SELECT_COLS} FROM canon_rule WHERE project_id = $1{archived_pred} ORDER BY created_at, id"
Keep `list_active()` UNCHANGED — it is the M6 critic's enforceable set (`active AND NOT is_archived`, line 81) and must never see archived rows.

(2) REST — `services/composition-service/app/routers/canon.py:108-120`. Add `include_archived: bool = False` next to the existing `active_only: bool = False` (keep `active_only`, per spec). Body becomes:
    rules = await (canon.list_active(project_id) if active_only
                   else canon.list_all(project_id, include_archived=include_archived))
Precedence rule (pick this default; PO can veto): `active_only=true` WINS and ignores `include_archived` — "enforceable only" and "include archived" are contradictory; no combined 4th mode. Mirrors `outline.py:179` param style. Gate stays `_require_work(..., GrantLevel.VIEW)` — unchanged.

(3) MCP PARITY (do it in the same slice — REST/MCP drift on the same repo call is the bug class this repo has already been bitten by) — `services/composition-service/app/mcp/server.py:508-520`, tool `composition_list_canon_rules`: add `include_archived: Annotated[bool, "Include soft-archived rules."] = False` and pass it through identically. Mirror of `composition_list_outline` (server.py:379/387). The `@mcp_server.tool` decorator here derives its schema from the signature (no separate JSON schema for this tool) — no other schema source to update.

(4) `is_archived` ON THE PAYLOAD IS ALREADY DONE — do NOT "add" it. `_SELECT_COLS` already selects `is_archived` (canon_rules.py:25-28) and `CanonRule` already declares `is_archived: bool = False` (app/db/models.py:293), and the route returns `r.model_dump(mode="json")`. Backend needs zero model work. The REAL missing consumer half is the FRONTEND TYPE: `frontend/src/features/composition/types.ts:350-359` `CanonRule` has no `is_archived` field — add `is_archived: boolean;` there, and thread `include_archived` through `compositionApi.listCanonRules` (`frontend/src/features/composition/api.ts:567-568`, which today calls the URL with no query string) + `useCanonRules` (hooks/useCanonRules.ts:13) so the M1 "Show archived (N)" toggle can pass it and badge archived rows. Without step 4 the toggle is un-buildable even with a perfect route.

TESTS (Definition of Done): in `services/composition-service/tests/unit/test_outline_canon_routers.py` add two cases against the canon list route — (a) archive a rule then `GET .../canon-rules` ⇒ rule absent (default unchanged, regression guard); (b) same rule with `?include_archived=true` ⇒ rule present AND its payload contains `is_archived: true` (assert the field, not just the row — that is what F-Q5's badge reads); (c) `?active_only=true&include_archived=true` ⇒ archived rule absent (the precedence decision above is asserted, not assumed). Mirror the existing include_archived test shape in `tests/unit/test_outline_children.py`. Run: `python -m pytest tests -q -n auto --dist loadgroup`.

*Evidence:* services/composition-service/app/db/repositories/canon_rules.py:88-97 (`list_all` hardcodes `AND NOT is_archived`, no param) · canon_rules.py:25-28 (`_SELECT_COLS` ALREADY includes `is_archived`) · app/db/models.py:293 (`CanonRule.is_archived: bool = False` — already carried) · app/routers/canon.py:108-120 (route has only `active_only`) · app/mcp/server.py:508-520 (MCP tool calls the same `list_all`, same gap) · existing pattern to copy: app/db/repositories/outline.py:739-743 + app/routers/outline.py:179,187 (`include_archived: bool = False` → `archived_pred = "" if include_archived else " AND NOT is_archived"`) · the F-Q5 symptom: frontend/src/features/studio/panels/QualityCanonPanel.tsx:174 renders `'A rule that no longer exists'` when `r.rule_text` is null · the blocking FE gap: frontend/src/features/composition/types.ts:350-359 (`CanonRule` type lacks `is_archived`) and api.ts:567-568 (listCanonRules sends no query params).

### BE-31-11a-CANON-RESTORE-ROUTE
BUILD AS SPEC'D — the spec's claim is verified true at HEAD; nothing to escalate, nothing to defer. Two files, ~20 lines, no gateway change, no migration.

(1) REPO — `services/composition-service/app/db/repositories/canon_rules.py`, append after `archive()` (file currently ends at line 166):

```python
    async def restore(self, project_id: UUID, rule_id: UUID) -> CanonRule | None:
        """Un-archive — the exact inverse of `archive`. Returns the row, or None if
        missing / another project's / NOT archived (nothing to restore)."""
        query = f"""
        UPDATE canon_rule
        SET is_archived = false, updated_at = now()
        WHERE project_id = $1 AND id = $2 AND is_archived
        RETURNING {_SELECT_COLS}
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(query, project_id, rule_id)
        return _row_to_rule(row) if row else None
```
Two constraints, both to keep symmetry with `archive` (canon_rules.py:155-166): do NOT bump `version` (archive doesn't, so the FE's If-Match ETag stays stable across an archive→undo round-trip), and do NOT add `is_archived` to `_UPDATABLE_COLUMNS` (line 30) — PATCH must remain unable to un-archive; restore is its own verb with its own route.

(2) ROUTE — `services/composition-service/app/routers/canon.py`, append after `delete_canon_rule` (ends line 186), mirroring it line-for-line:

```python
@router.post("/canon-rules/{rule_id}/restore", status_code=200)
async def restore_canon_rule(
    rule_id: UUID,
    user_id: UUID = Depends(get_current_user),
    works: WorksRepo = Depends(get_works_repo),
    canon: CanonRulesRepo = Depends(get_canon_rules_repo),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    """Inverse of DELETE. By-id route: resolve the rule's scope from the ROW ITSELF,
    gate on ITS book (PM-8) — so the gate can never check a different book than the
    row mutated."""
    project_id = await _rule_project_id(rule_id)
    await _require_work(works, grant, user_id, project_id, GrantLevel.EDIT)
    rule = await canon.restore(project_id, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="canon rule not found or not archived")
    return rule.model_dump(mode="json")
```
Response shape = the full `CanonRule` row (follow `outline.py:648`'s restore, NOT `arc.py:528`'s `{id, archived}` stub) — the FE undo-toast needs `version` back to keep issuing If-Match PATCHes. Error mapping falls out of the existing helpers for free: `_rule_project_id` (canon.py:92-104) 404s on a missing rule; `_require_work`→`_gate_book` (canon.py:67-76) 404s no-grant (anti-oracle) and 403s under-tier; `restore()` returning None 404s not-in-scope / not-archived. That satisfies the spec's "404 missing/not-in-scope/not-archived · 403 under-tier" exactly.

(3) TESTS (DoD — the wave does not close without these):
- Router: `services/composition-service/tests/unit/test_outline_canon_routers.py` (the DELETE case is at line 404) — add: archive→restore returns 200 + `is_archived=false`; restore of a never-archived rule → 404; restore under VIEW-only grant → 403; restore of an unknown id → 404.
- Repo: `services/composition-service/tests/integration/db/test_repositories.py` (carries `xdist_group("pg")`) — archive→restore round-trip returns the row; second restore returns None (idempotent-guard, mirrors `archive`'s `NOT is_archived` guard); restore with a foreign `project_id` returns None (tenancy).

NO gateway work: `services/api-gateway-bff/src/gateway-setup.ts:354` proxies by prefix (`pathname.startsWith('/v1/composition')`), so the new path is reachable the moment it exists.

BUILDER NOTE (scope fence — do not silently fold these in, they are their own spec rows): BE-11b (`include_archived` on the list) and BE-11c (`composition_canon_rule_restore` MCP tool) are separate items. But spec 31 line 604 is binding — "Do not ship the human half alone" — so 11a must land in the SAME milestone as 11c. When 11c lands, also flip `services/composition-service/app/mcp/server.py:1197-1200`, whose comment currently reads "there is no un-archive repo method, so there is no verified reverse op to surface. Honest: undo unavailable" and sets `undo_hint = None` — that comment becomes false the instant `CanonRulesRepo.restore` exists, and a stale `undo_hint: None` on delete is exactly the "silent no-op / dishonest capability" bug class this repo has shipped before.

*Evidence:* services/composition-service/app/db/repositories/canon_rules.py:155-166 (`archive()` is the last method; no `restore`; `_UPDATABLE_COLUMNS` at :30 excludes `is_archived` so PATCH can't un-archive either) · services/composition-service/app/routers/canon.py:175-186 (`delete_canon_rule`, no restore sibling) + :92-104 (`_rule_project_id`) + :78-89 (`_require_work`) — the exact gate helpers to reuse · services/composition-service/app/mcp/server.py:1197-1200 ("there is no un-archive repo method … Honest: undo unavailable" → `undo_hint = None`) · Sibling patterns to mirror: services/composition-service/app/routers/outline.py:648-664 (`POST /outline/nodes/{node_id}/restore`, returns the row) and services/composition-service/app/routers/arc.py:528-537 (`POST /arcs/{node_id}/restore`) · services/api-gateway-bff/src/gateway-setup.ts:354 (prefix proxy — no gateway change) · Tests: services/composition-service/tests/unit/test_outline_canon_routers.py:404 (existing DELETE case)

### Q-31-OQ5-BY-CHAPTER-BUILD-OR-DROP
**DROP BE-P1 from v1** (adopt the spec's own stated fallback: "The panel ships without it"). This is a conscious v1 scope call, not a blocker — recorded so it stops re-surfacing. PO may veto; if they want it, the build recipe is at the bottom of this row.

**WHY, from the code (not taste):** the wire shape the spec proposes — `by_chapter: [{chapter_id, words}]` — is *unrenderable* on its own. Composition-service does not own chapter titles/numbers: they live in book-service and are only reachable via a cross-service call (`services/composition-service/app/clients/book_client.py:330` `list_chapters(book_id, bearer)`), and `GET /works/{pid}/progress` (`services/composition-service/app/routers/progress.py:102-127`) is today a **pure-SQL read with no bearer dep and no cross-service failure mode** (it takes only `works` + `grant` + `progress`). The FE side is no better: `frontend/src/features/composition/components/ProgressPanel.tsx:24` receives only `{bookId, projectId, settings, token}` and holds **no chapter map**; the only place chapter titles are loaded in the studio is the Manuscript panel's own lazy/paged `useManuscriptTree` (`frontend/src/features/studio/manuscript/useManuscriptTree.ts:11-22`), which the progress panel cannot read. So rendering the wireframe's `Ch 88 · 1,204` costs EITHER (a) a best-effort `book_client.list_chapters` enrichment bolted onto a read path that currently cannot 502, OR (b) N extra FE chapter fetches per mount. That is a cross-service coupling on a hot read, i.e. **not the "S" the row claims** — bought for a stat the panel's own TODAY tile (`today_words`) already summarizes, for the chapter the editor already has open.

**CONCRETE BUILDER INSTRUCTIONS (M2 / BE-P1):**
1. **Do NOT touch** `DailyProgressRepo.read_aggregate` (`services/composition-service/app/db/repositories/daily_progress.py:82`) — leave the chapter dimension collapsed. **Do NOT widen** the `get_progress` response (`services/composition-service/app/routers/progress.py:113-127`); its keys stay exactly `{today, today_words, book_total, daily_goal, current_streak, sparkline}` **+ only** BE-P2's `daily_goal_source`.
2. In `docs/specs/2026-07-01-writing-studio/31_quality_completion.md`: flip the **BE-P1** row (line ~527) from `MUST-BUILD *or* DROP` to **`DROPPED (v1) — PO/PLAN 2026-07-13, OQ-5`** with a one-line pointer to this rationale; resolve **OQ-5** (line ~739) to "DROPPED"; delete the `▸ by chapter (today)` line from the Panel-B wireframe (line ~383) and the `plus by_chapter[]` clause from its **Reads** paragraph (line ~389); in the **M2** build list (line ~655) replace `→ BE-P1 *(or drop it — decide in PLAN)*` with `→ (BE-P1 DROPPED — OQ-5)`.
3. M2's DoD is therefore **unchanged minus by_chapter**: BE-P2 (`composition_progress_goal` + `PUT …/progress/goal` + read-through fallback + `daily_goal_source`), `useSetDailyGoal` rewritten off `patchWork`, `progress` panel + registration, contract guards `59 == 59 == 59`. No `by_chapter` test, no FE section, no chapter-title fetch.
4. Track it, don't silently drop it: add to SESSION_HANDOFF Deferred — **`D-PROGRESS-BY-CHAPTER`** · origin: spec 31 / M2 BE-P1 · what: per-chapter breakdown of today's words on `GET /works/{pid}/progress` · gate reason: **5 (conscious won't-fix for v1)** · trigger: a user actually asks "where did today's words go" per chapter.
5. **If the PO vetoes and wants it built**, the exact recipe (so no one re-derives it): reuse the existing per-chapter `s` CTE in `read_aggregate` (`daily_progress.py:98-110` — it already `PARTITION BY d.chapter_id`), add a sibling query `SELECT chapter_id, GREATEST(words - prev_words, 0) … WHERE snapshot_date = $3` returning `list[tuple[UUID,int]]` on `ProgressAggregate`; router adds `bearer` (mirror `plan.py:161`) and enriches titles **best-effort inside try/except** via `book_client.list_chapters` (a book-service failure must degrade to `title=None`, never 502 the progress read); FE renders a collapsible section keyed on `title ?? '#'+sort_order`. Size: S+ (cross-service).

*Evidence:* services/composition-service/app/db/repositories/daily_progress.py:82-138 (`read_aggregate` groups the per-chapter `s` CTE by `snapshot_date` only — chapter dimension collapsed) · services/composition-service/app/routers/progress.py:102-127 (`get_progress` returns 6 keys, deps = works/progress/grant only, NO bearer / NO cross-service call) · services/composition-service/app/db/migrate.py:475-486 (`composition_daily_progress` PK does carry `chapter_id`) · services/composition-service/app/clients/book_client.py:330 (`list_chapters` — the only source of chapter titles, cross-service, needs bearer) · frontend/src/features/composition/components/ProgressPanel.tsx:8-24 (props carry no chapter map) · frontend/src/features/studio/manuscript/useManuscriptTree.ts:11-22 (titles live only in the Manuscript panel's own paged hook) · docs/specs/2026-07-01-writing-studio/31_quality_completion.md:246-251 (F-Q8), :383 (wireframe marks it DROPPABLE), :527 (BE-P1 "MUST-BUILD *or* DROP"), :739 (OQ-5)

### BE-31-9a-JOBID-COLUMN
BUILD IT AS SPECIFIED — the spec's diagnosis is confirmed by the code; Plan-30's "BE-9 = no schema change" is false. `authoring_run_units` has no job_id, `DraftOutcome` discards the job_id the seam already reads, and `generation_correction.job_id` is NOT NULL + project-verified — so BE-9b's reject_unit has no way to name the rejected generation. Not a defer (in-scope, root-cause-clear, ~5 files). Exact build instruction:

1) DDL — `services/composition-service/app/db/migrate.py`: in the `authoring_run_units` CREATE TABLE (line ~1493) add `job_id UUID,` after `chapter_id`, AND (because the CREATE is IF NOT EXISTS and does not evolve migrated DBs) add the additive line next to the D5 one at line 1519:
   `ALTER TABLE authoring_run_units ADD COLUMN IF NOT EXISTS job_id UUID;`
   NULLABLE by design. Carry the mandated comment verbatim: `-- NULL = drafted before D-31 M4. Never backfill a guess.` No FK to generation_job here (the row survives job cascade-delete; generation_correction already holds the FK) and no index needed.

2) `app/services/authoring_run_service.py`:
   - `DraftOutcome` (:195) gains `job_id: UUID | None = None`.
   - `_poll_job` (:395): return `DraftOutcome(ok=True, cost_usd=..., job_id=job_id)` on the completed branch (:408). Leave the failed/cancelled/vanished/timeout branches with job_id=None (a failed unit is never corrected).
   - `draft_chapter` completed-branch (:380-391): only set `job_id=job.id` when the job loaded AND `job.project_id == project_id` — i.e. inside the existing in-project guard at :388. NEVER return an unverified `job_id_raw`: generation_corrections.create verifies job-in-project (D-COMP-M2-XREF-OWNERSHIP), so an out-of-partition id would only strand BE-9b.
   - Update the `DraftingSeam` Protocol docstring (:205) to say the seam reports the generation_job it drafted through (None = engine ran inline/no job).

3) `app/db/repositories/authoring_runs.py`:
   - `_UNIT_SELECT` (:39) add `u.job_id,`.
   - `transition_unit` (:388) gains `job_id: UUID | None = None` and appends `job_id = $n` to `sets` when not None (same conditional-set pattern as post_revision_id).
   - `mark_drafted` (:329) gains `job_id: UUID | None = None` and passes it through.
   - `upsert_pending` ON CONFLICT DO UPDATE (:316-320): add `job_id = NULL,` alongside `post_revision_id = NULL` — a resumed/re-run unit must NOT inherit the previous attempt's job_id (that would name the wrong generation in a correction).

4) `app/db/models.py`: `AuthoringRunUnit` (:761) gains `job_id: UUID | None = None  # the generation_job this unit drafted through (NULL = pre-D-31-M4)`.

5) Driver call site `authoring_run_service.py:1186` — pass `job_id=outcome.job_id` into `self._units.mark_drafted(...)`.

Scope guard (default, veto-able): do NOT add job_id to the public Run Report / units API DTO in this slice — it has no FE consumer; BE-9b consumes it server-side from the repo row. Add it to the wire only if BE-9b's UI actually needs it.

Tests (all in services/composition-service): unit — `tests/unit/test_authoring_runs_service.py`: (a) a fake engine returning `{status:"completed", job_id:J}` for an in-project job ⇒ mark_drafted is called with job_id=J; (b) same but job.project_id != run's project ⇒ job_id=None; (c) the 202/pending path ⇒ _poll_job's completed outcome carries the polled job id. Integration — `tests/integration/db/test_repositories.py`: mark_drafted persists job_id and get_for_run/list_for_run return it; upsert_pending on an existing drafted row resets job_id to NULL.

*Evidence:* services/composition-service/app/db/migrate.py:369 (`job_id UUID NOT NULL REFERENCES generation_job(id)` on generation_correction) + migrate.py:1493-1519 (authoring_run_units DDL — no job_id column) + services/composition-service/app/services/authoring_run_service.py:377,386-391,408 (seam reads job_id, loads+bills the job, then discards the id) + app/services/authoring_run_service.py:195-201 (DraftOutcome carries only ok/cost_usd/error) + app/db/repositories/authoring_runs.py:39-43,316-320,329-350,388-434 (_UNIT_SELECT, upsert_pending ON CONFLICT reset, mark_drafted → transition_unit conditional-set pattern) + app/db/repositories/generation_corrections.py:14-17 (create verifies the job is in THIS project — the in-DB FK only proves existence)

### Q-31-UNVERIFIED-DAILYGOAL-CONSUMERS
VERIFIED AT CODE — the spec's UNVERIFIED flag is now CLEARED, with one correction: there IS a second consumer, and it is not `progress.py`.

**(1) Semantic readers of `work.settings["daily_goal"]`: exactly ONE — `progress.py:68` `_coerce_goal` (used at `:124`).** That is the reader BE-P1/BE-P2 rewrites anyway, so BE-P2 breaks nothing. Proven exhaustively against all three grep-hostile paths: (a) every other `work.settings` consumer (engine.py, plan.py, worker/operations.py, grounding.py, pack.py) reads through `packer/profile.py:71-78` `from_settings`, which allowlists exactly 5 keys (source_language, voice, structure_pref, tone, density) — `daily_goal` never reaches a prompt; (b) ZERO `settings->>` / `settings->` JSONB accessors against `composition_work.settings` repo-wide (the only `->>` hit is book-service's unrelated `wiki_settings`); (c) ZERO cross-service readers (no Go/TS service reads the Work's settings) and `daily_goal` appears in NO OpenAPI contract.

**(2) THE FINDING the grep could not see — `composition_get_work` hands the whole blob to the LLM.** `services/composition-service/app/mcp/server.py:333` ends with `return work.model_dump(mode="json")`, dumping the entire settings blob verbatim. After BE-P2 an agent asked "what's my daily goal?" calls `composition_get_work`, reads the FROZEN legacy `settings.daily_goal` (e.g. 400), and reports it — while the authoritative per-user goal (e.g. 600) lives in `composition_progress_goal`. A stale SECOND HOME surfaced to the model: exactly the SET-3 "one home, one name" violation QC-6 exists to close. It is also sticky — the three surviving full-blob writers (`useWork.ts:134-135`, `useChapterAssembly.ts:32-33`, both → `patchWork` → `works.py:311-313` `settings = $n::jsonb`, a full REPLACE) spread `...currentSettings` from `GET /works`, so they re-write the legacy key forever; it never ages out.

**BUILDER INSTRUCTION (M2 / BE-P2, do all three; 3 lines + 1 test, FIX-NOW — not a defer row):**

**a. Delete the patchWork writer as planned, with no further re-grep.** Rewrite `frontend/src/features/composition/hooks/useProgress.ts:76-80` (`useSetDailyGoal`) to call the new per-user goal route instead of `compositionApi.patchWork`. No other consumer depends on the write. Update the two assertions at `frontend/src/features/composition/hooks/__tests__/useProgress.test.tsx:88,98` (they currently assert the `patchWork` full-blob call) to assert the new route.

**b. Redact the legacy key at the MCP boundary.** In `composition_get_work` (`services/composition-service/app/mcp/server.py:333`), before returning, strip `daily_goal` from the dumped settings so the model can never see the stale second home:
```python
out = work.model_dump(mode="json")
# SET-3 (one home, one name): the daily goal lives in `composition_progress_goal`
# (per-user), NOT in this shared per-book blob. A legacy `settings.daily_goal` is
# kept ONLY as the read-through fallback in GET /works/{pid}/progress — never
# surfaced here, or an agent reports a frozen goal that contradicts the real one.
if isinstance(out.get("settings"), dict):
    out["settings"].pop("daily_goal", None)
return out
```
Add ONE test in composition-service's MCP suite: seed a Work with `settings={"daily_goal": 400, "voice": "wry"}`, call `composition_get_work`, assert `"daily_goal" not in result["settings"]` AND `result["settings"]["voice"] == "wry"` (the redaction must not eat the blob).

**c. ANTI-INSTRUCTION — do NOT write a migration that deletes `daily_goal` from `composition_work.settings`.** That column IS the read-through fallback the spec's QC-6 relies on ("no existing user loses a goal", `daily_goal_source: 'work_legacy'`). Dropping it is data loss and would trip the CRITICAL-blocker rule. Leave the stored key alone; close the window in the WRITER (a) and hide it at the MCP read (b). Keep `services/composition-service/tests/unit/test_progress_router.py:125-129,145-156` GREEN — those encode the legacy fallback that BE-P1 must preserve.

*Evidence:* services/composition-service/app/routers/progress.py:68 (`g = settings.get("daily_goal")` — the ONLY semantic reader; used at :124) · services/composition-service/app/packer/profile.py:71-78 (`from_settings` 5-key allowlist ⇒ daily_goal never reaches a prompt) · **services/composition-service/app/mcp/server.py:333 (`return work.model_dump(mode="json")` — the grep-hostile SECOND consumer: whole settings blob → LLM)** · services/composition-service/app/db/repositories/works.py:311-313 (`settings = ${n}::jsonb` — PATCH is a full REPLACE, so the surviving `...currentSettings` writers keep the legacy key alive forever) · frontend/src/features/composition/hooks/useProgress.ts:76-80 (the writer BE-P2 deletes); useWork.ts:134-135 + useChapterAssembly.ts:32-33 (the two full-blob writers that STAY) · negative evidence: `grep -rn "settings *->>" services/ frontend/ contracts/` = 0 hits on composition_work.settings; `grep -rn daily_goal contracts/` = 0 hits

### Q-31-F-Q3a-ALLOWLIST-TRAP
CONFIRMED — the spec's answer is correct against the code, and BE-9c is buildable exactly as written. Builder instruction (M4 / BE-9c, composition-service):

1. In `services/composition-service/app/db/repositories/generation_corrections.py`, directly under `_DASHBOARD_MODES` (line 34), add ONE named constant:
   `CORRECTABLE_OPERATIONS: tuple[str, ...] = ("draft_scene", "draft_chapter", "stitch_chapter")`
   with a comment stating verbatim: "mode and operation are ORTHOGONAL. There is NO SUCH THING as a 'cowrite op'. draft_scene carries mode='cowrite' (GenerateBody, engine.py:97-98) and IS the Stream column. rewrite/expand/describe (SelectionEditBody, engine.py:122) are selection edits, are NOT draft generations, and MUST NEVER be added here."

2. In `correction_stats`, ADD `AND j.operation = ANY($2::text[])` to the WHERE clause and pass `list(CORRECTABLE_OPERATIONS)` as the 2nd bind param. **KEEP line 206's `AND NOT coalesce((j.input->>'selection_edit')::boolean, false)` — do NOT replace it.** The two predicates are defense in depth: `operation` is an open `str` on both draft bodies, so the allowlist filters what the server writes today but does not constrain what a client may post tomorrow.

3. Ship BE-9c′ in the same slice: narrow `GenerateBody.operation` (engine.py:97) and `GenerateChapterBody.operation` (engine.py:135) from `str` to `Literal["draft_scene"]` / `Literal["draft_chapter"]` — the same LOOM-39 missing-enum lesson already cited in engine.py:118-121 and already applied to SelectionEditBody.

4. THREE tests must land — the first two assert the behavior, the third is the anti-trap tripwire (a behavior test alone would still be green while the allowlist lies):
   a. `tests/integration/db/test_repositories.py` (carries `pytestmark = pytest.mark.xdist_group("pg")`): seed a COMPLETED `operation='plan_pass', mode='auto'` job → `auto.generations` is unchanged and `accept_rate` does not move.
   b. same file: seed a COMPLETED `operation='rewrite', mode='cowrite', input={'selection_edit': True}` job → `cowrite.generations == 0`; AND seed a COMPLETED `operation='draft_scene', mode='cowrite'` job with no selection_edit flag → it DOES land in the cowrite/Stream column (proves the allowlist did not amputate Stream).
   c. a pure unit tripwire on the constant itself: `assert set(CORRECTABLE_OPERATIONS) == {"draft_scene","draft_chapter","stitch_chapter"}` and `assert not ({"rewrite","expand","describe"} & set(CORRECTABLE_OPERATIONS))`, with the failure message "F-Q3a: mode and operation are orthogonal — rewrite/expand/describe are selection edits, never draft ops. See spec 31 F-Q3a." A future agent enumerating "the cowrite ops from engine.py" reds this test with the explanation attached.

Default I am picking (veto-able): the tripwire test (4c) is a hard requirement, not optional — it is the only mechanism that turns the spec's prose warning into a mechanical gate, per CLAUDE.md's "checklist ⇒ test the effect" rule.

*Evidence:* services/composition-service/app/db/repositories/generation_corrections.py:201-206 (the existing `/review-impl` `NOT selection_edit` predicate + its rationale comment) · :34 (`_DASHBOARD_MODES`, where the new constant goes) · services/composition-service/app/routers/engine.py:97-98 (`GenerateBody.operation: str = "draft_scene"` + `mode: Literal["cowrite","auto"] = "cowrite"` — proves draft_scene IS the Stream column) · engine.py:122 (`SelectionEditBody.operation: Literal["rewrite","expand","describe"]` — the exact grep an agent would hit) · engine.py:825-827 and :846-848 (selection-edit job hardcodes `mode="cowrite"` + `input.selection_edit=True`) · engine.py:118-121 (the in-code "LOOM-39 missing-enum lesson" comment that BE-9c′ extends to the draft bodies) · docs/specs/2026-07-01-writing-studio/31_quality_completion.md:524-525 (BE-9c / BE-9c′ rows)

### Q-31-OQ4-DISMISS-VIOLATION-NO-MCP
DO NOT DEFER — BUILD IT IN M1, in the same slice as BE-11c. New row **BE-11d · `composition_dismiss_violation` (Tier A, XS)**. Rationale (quote in the plan): spec 31 already MUST-BUILDs two GG-2 parity tools in this wave, in this exact file, under its own rule "Do not ship the human half alone; a one-sided restore is the GG-2 inverse defect, immediately" (31:521, 31:601). Dismiss is the same shape and is ~25 lines of logic that ALREADY EXISTS in the REST handler — it clears none of CLAUDE.md's 5 defer gates ("a route you could write is unbuilt work, not a blocker"). Writing + carrying the defer row costs more than the tool.

BUILDER STEPS (exact):

1. NEW FILE `services/composition-service/app/engine/critic_dismiss.py` — one pure helper so the two doors cannot drift (the css-var-duplicated-across-two-consumers class):
```python
from typing import Any
def apply_dismissal(critic: dict[str, Any] | None, rule_id: str) -> tuple[dict[str, Any], bool]:
    """Mark every violation for `rule_id` dismissed. Returns (new_critic, found).
    Copy-then-return (no mutation of the caller's dict) — the motif_conformance.py:221 convention."""
    out = dict(critic or {})
    violations = [dict(v) if isinstance(v, dict) else v for v in (out.get("violations") or [])]
    found = False
    for v in violations:
        if isinstance(v, dict) and str(v.get("rule_id")) == rule_id:
            v["dismissed"] = True
            found = True
    out["violations"] = violations
    return out, found
```

2. `services/composition-service/app/routers/engine.py:1684-1709` — replace the inline loop in `dismiss_violation` with `critic, found = apply_dismissal(job.critic, body.rule_id)`; keep the existing `_gate_work(..., GrantLevel.EDIT)`, the `404 "violation not found"` on `not found`, and the `{"critic": critic}` response byte-for-byte. Behavior unchanged.

3. `services/composition-service/app/mcp/server.py` — add the tool in the Tier-A section, immediately after `composition_canon_rule_delete` (ends :1201), copying that decorator shape:
```python
@mcp_server.tool(
    name="composition_dismiss_violation",
    description=(
        "Dismiss a FALSE-POSITIVE canon violation on ONE generation job's critic verdict — "
        "the agent-side twin of the human's dismiss button on the quality-canon panel. It "
        "silences that rule's finding on THIS job only; it does not change or archive the "
        "rule (that is composition_canon_rule_update/_delete). EDIT required (auto-applied). "
        "Not reversible today — there is no un-dismiss."
    ),
    meta=require_meta(
        "A", "book",
        synonyms=["dismiss violation", "false positive", "the critic is wrong",
                  "ignore this violation", "silence finding", "not a real violation"],
        tool_name="composition_dismiss_violation",
    ),
)
async def composition_dismiss_violation(
    ctx: MCPContext,
    project_id: Annotated[str, "The Work's project_id."],
    job_id: Annotated[str, "The generation job whose critic verdict carries the violation."],
    rule_id: Annotated[str, "The canon rule id of the violation to dismiss."],
) -> dict:
    tc = _ctx(ctx)
    works = WorksRepo(get_pool())
    pid = UUID(project_id)
    await _book_or_deny(works, tc, pid, GrantLevel.EDIT)
    jobs = GenerationJobsRepo(get_pool())
    job = await jobs.get(UUID(job_id))
    # Project-scope BEFORE mutating (same reason as get_generation_job / canon_rule_delete):
    # jobs.get() is by-id only, so a job from another Work must not be writable under this gate.
    if job is None or job.project_id != pid:
        raise uniform_not_accessible()
    critic, found = apply_dismissal(job.critic, rule_id)
    if not found:
        raise uniform_not_accessible()
    await jobs.update_status(UUID(job_id), job.status, critic=critic)
    # No un-dismiss exists at any layer ⇒ honest: no undo hint (the canon_rule_delete precedent).
    return {"critic": critic, "_meta": {"undo_hint": None}}
```
(⚠ 3-schema-source FastMCP caveat: keep the arg docs in the `Annotated[...]` params — do not rely on a docstring.)

4. `services/mcp-public-gateway/src/scope/tool-policy.ts:236` — add `composition_dismiss_violation: { tier: 'write_auto', domains: ['composition'] },` beside `composition_canon_rule_delete`. Omitting it is fail-closed (the public key silently cannot call it), which is the exact half-dark shape this row exists to kill.

5. `frontend/src/features/studio/agent/handlers/compositionEffects.ts` (the NEW file spec 31's registration checklist step 8 already mandates) — add `registerEffectHandler(/^composition_dismiss_violation$/, …)` invalidating the rule-violations / canon-issues query keys, so an agent dismiss refreshes the human's `quality-canon` panel. Without it the panel shows a violation the agent just silenced.

6. TESTS (`services/composition-service/tests/unit/test_mcp_actions.py` + a new `tests/unit/test_critic_dismiss.py`):
   a. tool marks the matching violation `dismissed: true` and calls `update_status(job_id, job.status, critic=…)` with the job's status unchanged;
   b. job belonging to ANOTHER project → `uniform_not_accessible()` (no existence oracle) and NO write;
   c. unknown `rule_id` → `uniform_not_accessible()` and NO write;
   d. parity test: `apply_dismissal` fed the same critic produces the identical dict for the REST route and the MCP tool (the anti-drift lock);
   e. VIEW-only grant → denied (EDIT is required).

7. SPEC EDITS: in `docs/specs/2026-07-01-writing-studio/31_quality_completion.md`, change line 605 ("Records: … not this wave's job") and the OQ-4 row (line 738) to "**RESOLVED → BE-11d, MUST-BUILD in M1 alongside BE-11c**", and add BE-11d to the BE table next to BE-11c. QC-9 (human dismiss) and BE-11d (agent dismiss) ship in the SAME commit — never the human half alone.

Default I am picking (veto-able): dismiss stays NOT reversible for both doors in M1 (no `undismiss` arg, `undo_hint: None`) — adding an agent-only un-dismiss would open the inverse gap in the other direction, since the GUI has no un-dismiss control.

*Evidence:* services/composition-service/app/routers/engine.py:1684-1709 (POST /jobs/{job_id}/dismiss-violation — the full logic is 25 lines: gate EDIT on the job's own project, set v["dismissed"]=True, jobs.update_status(job_id, job.status, critic=critic)) · services/composition-service/app/mcp/server.py:1167-1201 (composition_canon_rule_delete — the Tier-A auto-write template: require_meta("A","book"), _book_or_deny(EDIT), project-scope check before mutate, uniform_not_accessible(), honest undo_hint None) · services/composition-service/app/mcp/server.py:522-555 (composition_get_generation_job — the exact `job is None or job.project_id != pid` no-oracle check to reuse) · services/composition-service/app/db/repositories/outline.py:1338 (`(e.value -> 'dismissed') IS DISTINCT FROM 'true'::jsonb` — the canon-issues lens already consumes the flag, so the tool's effect is immediately visible; nothing else must be built) · services/mcp-public-gateway/src/scope/tool-policy.ts:236 (default-deny scope map — a new tool needs a row or the public key cannot call it) · docs/specs/2026-07-01-writing-studio/31_quality_completion.md:521,601 (BE-11c + "Do not ship the human half alone; a one-sided restore is the GG-2 inverse defect, immediately" — the same wave already builds the identical parity tool in the same file)

### Q-31-UNVERIFIED-LEARNING-BURST
VERIFIED — the learning-service consumer copes with a Revert-All burst. DO NOT rate-limit or batch the capture in `revert_all`. Instead, fix the real gap the read exposed: `revert_all` bypasses `reject_unit`, so BE-9b's capture would record NOTHING for a Revert-All.

WHY NO RATE LIMIT IS NEEDED (the UNVERIFIED claim is now closed):
The transport is a Redis Streams consumer group (`learning-collector`) on `loreweave:events:composition`, built on `loreweave_jobs.BaseProjectionConsumer` — a durable log with backlog replay (`start_id="0"`), batched `XREADGROUP` (`count=10`, `block=5000ms`), per-message XACK, bounded retry (3) → DLQ, and periodic XAUTOCLAIM reclaim. A burst is not "pressure": unconsumed events simply sit in the stream and drain at the consumer's own pace. Nothing is dropped, nothing back-pressures the producer, and stream MAXLEN is ~10000 approximate (`services/composition-service/app/worker/events.py:30`) — three orders of magnitude above "dozens".
The per-event work is bounded and cheap: `handle_generation_corrected` (`services/learning-service/app/events/handlers.py:500-546`) does a kind-gate, two pure functions (`split_snapshot`, `derive_diff_class`), then ONE `INSERT ... ON CONFLICT (origin_service, origin_event_id) DO NOTHING` (`handlers.py:102-124`). No LLM call, no HTTP fan-out, no unbounded loop. (The LLM-judge path is a DIFFERENT consumer on a DIFFERENT stream — `LLMJudgeConsumer` on `loreweave:events:llm_job_terminal`, `app/events/llm_judge_consumer.py:31-33` — and only wakes for an existing `llm_judges` row, so a correction burst causes ZERO token spend. This was the only cost-shaped risk and it does not exist.) 50 corrections = ~5 XREADGROUP loops and 50 single-row inserts. Rate-limiting this would be pure ceremony.

WHAT THE BUILDER MUST ACTUALLY DO (M4 / BE-9b):
1. `services/composition-service/app/services/authoring_run_service.py` — `revert_all` (lines 960-1019) does NOT call `reject_unit`; it calls `self._units.transition_unit(...)` directly at line 1001. So a capture written only inside `accept_unit`/`reject_unit` (BE-9b as worded, spec 31 line 523) captures nothing on a Revert-All — the flywheel would silently lose the single richest bulk-rejection signal. ADD the capture inside `revert_all`'s existing per-unit loop, immediately after the successful `transition_unit` (i.e. inside the `if updated is not None:` branch at lines 1005-1006), one `GenerationCorrectionsRepo.create(project_id=run.project_id, job_id=u.job_id, created_by=<caller>, kind="reject")` per reverted unit.
2. Fire-and-forget, per BE-9b: wrap each capture in `try/except Exception` → `logger.warning` → CONTINUE. A capture failure must never fail or abort the revert sweep (the restore already happened; the unit is already rejected).
3. `job_id IS NULL` on the unit ⇒ skip the capture (do not fabricate a job_id) — same rule BE-9b states.
4. Keep the captures SEQUENTIAL inside the existing loop (do NOT `asyncio.gather` them). Each `create()` (`app/db/repositories/generation_corrections.py:66-172`) opens its own `pool.acquire()` + transaction (row INSERT + outbox emit are txn-local together); dozens of sequential acquisitions on an asyncpg pool is a non-issue, whereas a gather would burst the pool. This — not the consumer — is the only place the "transaction storm" phrasing has any bite, and sequential-in-loop already neutralizes it.
5. Emission is per-unit and each outbox row gets its own id, so each event carries a distinct `outbox_id` → N units yield N distinct `corrections` rows (the ON CONFLICT key is `(origin_service, origin_event_id)`, `handlers.py:117`). No collapse, no dedup hazard.

TESTS (name them in the slice):
- `services/composition-service/tests/` — `revert_all` over 3 drafted units emits 3 `composition.generation_corrected` outbox rows with `kind='reject'` (assert on the outbox table, not a spy — the emit is txn-local).
- Same file — a capture that raises does NOT abort the sweep: all units still reach `rejected` and `revert_all` still returns `closed=True`.
- `services/learning-service/tests/test_generation_corrected_handler.py` — extend: N events with distinct `outbox_id`s persist N `corrections` rows (proves no burst-collapse).

DEFAULT THE PO MAY VETO: I am declining to add any throttle/batch/debounce anywhere. If the PO later wants Revert-All to record ONE aggregate "bulk_reject" signal instead of N per-unit rejects, that is a signal-semantics choice (it changes what the flywheel learns), not a throughput fix — and it is not needed to ship M4.

Consistent with plan-30 §0: this adds no new global flag, no new env knob, no new route, and does not contradict PO-1..4.

*Evidence:* services/learning-service/app/events/consumer.py:42-67 (Redis Streams group `learning-collector`, retry→DLQ) · sdks/python/loreweave_jobs/projection_consumer.py:64-68 (`start_id="0"`, `max_retries=3`, `count=10` — durable backlog, batched read, per-msg ack) · services/learning-service/app/events/handlers.py:500-546 + :102-124 (one INSERT ... ON CONFLICT DO NOTHING per event; no LLM, no HTTP) · services/learning-service/app/events/llm_judge_consumer.py:31-33 (LLM path is a SEPARATE stream/group — zero token spend on a correction burst) · services/composition-service/app/worker/events.py:30 (`STREAM_MAXLEN = 10000`, approximate) · services/composition-service/app/services/authoring_run_service.py:1001 (`revert_all` calls `self._units.transition_unit` DIRECTLY — bypasses `reject_unit` at :919, so BE-9b's capture seam misses it) · services/composition-service/app/db/repositories/generation_corrections.py:66-172 (`create` = own acquire + txn, row INSERT + outbox.emit atomic) · docs/specs/2026-07-01-writing-studio/31_quality_completion.md:523 (BE-9b), :740 (the UNVERIFIED row this closes)

### BE-31-9d-PER-JOB-CORRECTIONS-LIST
SKIP BE-9d — candidate (a). Do NOT build `GET /v1/composition/works/{pid}/jobs/{job_id}/corrections` in M4, and do NOT widen learning-service's route either. Builder action: strike the BE-9d row from the M4 build set (spec 31 §BE table line 526) and delete the "Optionally … BE-9d" sentence at 31_quality_completion.md:430-432 so it cannot be re-picked-up at 3am; leave `GenerationCorrectionsRepo.list_for_job()` in place, test-only, as the primitive a future drill-down would use (do not delete it, do not "wire it up for completeness").

WHY (three code facts, all verified):
1. NO CALLER. Panel C's spec is an aggregate-only table: the wireframe (31_quality_completion.md:410-427) renders per-MODE columns (Diverge vs Stream: generations / accept-as-is / edited / picked-other / regenerated / rejected / avg-edit-blocks), and QC-3 (line 303) locks the panel to an extracted `CorrectionStatsTable`. There is no per-job row in the UI to click, so a per-job list endpoint would ship with zero consumers — the "built but unreachable" bug class. `GET /works/{pid}/correction-stats` (engine.py:1793) is the panel's ONLY read.
2. The spec's ⚠ ("learning-service may already serve this") is FALSE — I grepped it. `GET /v1/learning/corrections` (services/learning-service/app/routers/corrections.py:64-73) accepts ONLY `project_id`, `target_type`, `diff_class`, `limit`, `cursor`. There is NO `target_id`/`job_id` filter, even though the handler writes `target_id=str(job_id)` (handlers.py:528). It physically cannot answer "the corrections on THIS job" without being widened. So there was never a duplicate-route risk to avoid.
3. And it must NOT be widened for this purpose anyway. Learning's copy is redact-by-default: composition's outbox payload is structural-only (`outbox.emit(...)` in services/composition-service/app/db/repositories/generation_corrections.py — it sends `has_guidance` / `has_raw_prose` BOOLEANS, never the text), and learning drops non-gold kinds (`_COMPOSITION_GOLD_KINDS` = edit/pick_different/regenerate/reject, handlers.py:460). A drill-down wants exactly what learning does not have: `guidance`, `raw_before`/`raw_after`, `chosen_candidate_index`. Those live only in composition's `generation_correction` row (SSOT).

DEFAULT THE PO CAN VETO: if a per-row drill-down is ever requested in a later wave, build it in COMPOSITION (`GET /v1/composition/works/{pid}/jobs/{job_id}/corrections`, XS, on top of the existing `list_for_job()`, gated by the same `_require_work` E0 grant as its siblings) — NOT by adding a `target_id` filter to `/v1/learning/corrections`. The two lists are different concepts, not one name twice: composition's = the author's own Work, full fidelity, prose included; learning's = a cross-project, redacted, gold-only training corpus. Nothing about skipping BE-9d blocks BE-9a/9b/9c, which are the load-bearing half of G-CORRECTION-FLYWHEEL and still MUST-BUILD.

*Evidence:* services/learning-service/app/routers/corrections.py:64-73 (`list_corrections` params = project_id/target_type/diff_class/limit/cursor — NO job/target_id filter ⇒ cannot serve a per-job drill-down) · services/learning-service/app/events/handlers.py:460,528 (gold-kinds-only; target_id=job_id is written but never queryable) · services/composition-service/app/db/repositories/generation_corrections.py (`outbox.emit` payload is structural-only: `has_guidance`/`has_raw_prose` flags, no prose ⇒ learning is redacted; `list_for_job()` at the file's end is the composition-side primitive, test-only) · services/composition-service/app/routers/engine.py:1793 (`GET /works/{pid}/correction-stats` — the panel's only read) · docs/specs/2026-07-01-writing-studio/31_quality_completion.md:303 (QC-3: panel mounts CorrectionStatsTable), :410-427 (wireframe is per-mode aggregate, no per-job row), :526 (the BE-9d row being struck)

### BE-31-P2-PER-USER-GOAL
BUILD IT AS SPECCED — the spec is right and the code confirms the defect. Two under-determined details I decide below (PO may veto).

1) DDL — append to `services/composition-service/app/db/migrate.py` immediately after `composition_progress_baseline` (ends line 504), same idempotent style:
```sql
CREATE TABLE IF NOT EXISTS composition_progress_goal (
  user_id    UUID NOT NULL,
  project_id UUID NOT NULL,
  daily_goal INT  NOT NULL CHECK (daily_goal > 0),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, project_id)
);
```
NO `book_id` — the two siblings at migrate.py:475-504 carry none and the book grant is enforced at the router. No index (PK covers the only read).

2) Repo — new `ProgressGoalRepo` (own file `app/db/repositories/progress_goal.py`, or two methods on `DailyProgressRepo`): `get(user_id, project_id) -> int | None`; `set(user_id, project_id, goal)` = INSERT … ON CONFLICT (user_id, project_id) DO UPDATE SET daily_goal=EXCLUDED.daily_goal, updated_at=now(); `clear(user_id, project_id)` = DELETE. Repos do NO access checks (PM-8).

3) Router `app/routers/progress.py`:
- Add `_resolve_goal(user_row_goal, work.settings) -> tuple[int|None, Literal['user','work_legacy','none']]`: user row wins; else `_coerce_goal(work.settings or {})` (existing helper, :65) → `work_legacy`; else `(None, 'none')`. **Keep `_coerce_goal` — it is the fallback reader, not dead code.**
- `GET /works/{project_id}/progress` (:103): replace `"daily_goal": _coerce_goal(...)` (:124) with the resolved pair and ADD `"daily_goal_source"` to the response dict (SET-1: effective value + source tier).
- NEW `PUT /v1/composition/works/{project_id}/progress/goal`, body `class ProgressGoalBody(BaseModel): goal: int = Field(ge=0, le=1_000_000)` (ge=0 ⇒ FastAPI 422 on negative, satisfying "422 on goal<0"; upper cap prevents an INT overflow 500, same rationale as `words` at :132). Handler: `work = await works.get(project_id)` → 404 if None → `await _gate_book(grant, work.book_id, user_id, GrantLevel.VIEW)` (**DECISION: VIEW, not EDIT** — the row is the caller's OWN per-user preference, exactly like `/progress/report` and `/progress/baseline` which already gate at VIEW, progress.py:157,185; requiring EDIT would deny a legitimate viewer their own goal). Then `goal>0 ⇒ repo.set(...)`, `goal==0 ⇒ repo.clear(...)`. **The WRITER never touches `work.settings`.**
- **DECISION: the PUT response is the RESOLVER's output, not an echo** — return `{"goal": <resolved>, "source": <'user'|'work_legacy'|'none'>}` using the same `_resolve_goal`. So a clear (goal=0) that falls back to a stale `work.settings.daily_goal` returns `{goal: 1000, source: 'work_legacy'}` and the FE shows the truth instead of "cleared" (no silent hidden default). Do NOT invent a NULL sentinel row — the CHECK stays `> 0`.
- Wire the repo via a `get_progress_goal_repo` dep in `app/deps.py`, mirroring `get_daily_progress_repo`.

4) Frontend:
- `api.ts`: add `setDailyGoal(projectId, goal, token): Promise<{goal: number|null; source: string}>` → `PUT /v1/composition/works/{projectId}/progress/goal`.
- `types.ts:275-281`: add `daily_goal_source: 'user' | 'work_legacy' | 'none'` to `ProgressStats`; update the stale comment ("read from work.settings").
- `hooks/useProgress.ts:71-84`: **rewrite `useSetDailyGoal`** — drop the `bookId`/`currentSettings` params entirely, call `compositionApi.setDailyGoal(projectId, goal, token)`, and on success invalidate ONLY `['composition','progress']` (the work query no longer carries the goal). This deletes the `patchWork` caller here.
- `ProgressPanel.tsx:28,35`: drop the `settings` and `bookId` props; render the source tier when it is `work_legacy` (e.g. "goal inherited from work settings"). Update the ONE mount at `CompositionPanel.tsx:847` (it passes `bookId`/`settings` today) and the new Studio `progress` panel wrapper.

5) Tests (all three are required, none is optional):
- `services/composition-service/tests/unit/test_progress_router.py`: PUT sets → GET returns `source:'user'`; PUT 0 → GET falls back to `work_legacy` when `work.settings.daily_goal` is set, else `none`; PUT `-1` → 422; PUT with no grant → 404/403 (mirror the existing `_gate_book` cases).
- **TENANCY test (the point of the whole item):** user A PUTs goal=500 on project P; user B (a grantee on the same book) GETs → B does NOT see 500 (sees its own row, or the legacy/none fallback). Assert on the SQL predicate, not a mock.
- `frontend/.../hooks/__tests__/useProgress.test.tsx:82-98`: replace the two `patchWork` assertions with `setDailyGoal` assertions, and assert `patchWork` is NOT called.

6) DoD: `/review-impl` at wave close (tenancy boundary). Note the item's "closes BE-18" claim is scoped: `patchWork` full-blob callers REMAIN at `useChapterAssembly.ts:33` and `useWork.ts:135` — this wave closes the goal's exposure only; do not mark BE-18 resolved.

*Evidence:* services/composition-service/app/routers/progress.py:65-71 (`_coerce_goal` reads the goal from `work.settings`) and :124 (GET returns it) — `composition_work` is a per-BOOK shared row whose PATCH gates at EDIT (services/composition-service/app/routers/works.py:581-601), so today any EDIT-grant collaborator's goal overwrites every collaborator's goal = the tenancy defect. Writer: frontend/src/features/composition/hooks/useProgress.ts:71-84 (`patchWork` full-blob settings REPLACE). "No book_id" is confirmed by the siblings: services/composition-service/app/db/migrate.py:475-504 (`composition_daily_progress`, `composition_progress_baseline` are keyed on user_id+project_id+chapter_id only); the book grant is already the router's job — services/composition-service/app/routers/progress.py:44-51 (`_gate_book`) and the reusable pattern at services/composition-service/app/routers/canon.py:81-91 (`_require_work`). Per-user progress writes already gate at VIEW: progress.py:157 (report), :185 (baseline).

### Q-31-PROGRESS-TODAY-TIMEZONE
CLAMP SERVER-SIDE — keep the client-supplied local date (it is required: streaks must honor the writer's midnight, not UTC), but bound it to the only window a real local clock can legitimately occupy: ±1 day from the server's current UTC date (real offsets span UTC-12..UTC+14, so a valid local date is always within one day of the UTC date). Reject anything outside that window with 422. This kills the hand-crafted-`date` streak-inflation vector and any wildly-skewed device clock, while leaving legitimate multi-device/multi-timezone writing working (the snapshot model already converges: rows are keyed (user, project, chapter, date) with last-write-wins, and the stat is per-user, so no other user's data can be affected — this is NOT a tenancy issue and does NOT gate the build).

BUILDER INSTRUCTION (one file + its test; do this in M2, ~30 min, do NOT defer):

1. `services/composition-service/app/routers/progress.py` — replace the existing `_parse_local_date` (line 56-62) with a clamping validator:

```python
from datetime import date, datetime, timedelta, timezone

_MAX_LOCAL_SKEW_DAYS = 1  # real UTC offsets span UTC-12..UTC+14 ⇒ a genuine local
                          # date is always within ±1 day of the current UTC date.

def _parse_local_date(raw: str) -> date:
    """Parse + BOUND a client-supplied local date (YYYY-MM-DD). The client owns the
    date so streaks honor the writer's midnight (not UTC), but an unbounded client
    date lets a hand-crafted `today`/`date` fabricate or inflate a streak. Any real
    local clock is within ±1 day of the UTC date, so anything further out is a bad
    clock or a forged value → 422 (never silently written on a wrong day)."""
    try:
        d = date.fromisoformat(raw)
    except ValueError:
        raise HTTPException(status_code=422, detail="date must be YYYY-MM-DD")
    utc_today = datetime.now(timezone.utc).date()
    if abs((d - utc_today).days) > _MAX_LOCAL_SKEW_DAYS:
        raise HTTPException(
            status_code=422,
            detail="date must be within 1 day of the server date (UTC)",
        )
    return d
```

Both existing call sites already funnel through it — `get_progress` (progress.py:117, the `today` query param) and `report_progress` (progress.py:157, `body.date`) — so no other edit is needed. `POST /progress/baseline` takes no date; leave it alone.

2. Update the router docstring (progress.py:17-18): after "The client supplies its local date so streaks honor the writer's midnight, not UTC" add "— bounded server-side to ±1 day of the UTC date so a forged/skewed date cannot fabricate a streak."

3. `services/composition-service/tests/unit/test_progress_router.py` — add 3 tests:
   - `test_report_rejects_far_future_date` — POST /progress/report with `date` = (utc_today + 5 days) → 422, and assert the repo's `report` was NOT called (a forged row must never reach the table).
   - `test_report_rejects_far_past_date` — same with utc_today - 5 days → 422.
   - `test_get_progress_accepts_plus_and_minus_one_day` — GET `?today=` utc_today+1 and utc_today-1 both → 200 (the legit UTC+14 / UTC-12 writer must not be broken).
   Mirror the existing mocked-deps/grant-stub pattern already used in that file.

4. Frontend: NO change. `frontend/src/features/composition/api.ts:304`/`:311` already send the device's local date, which by construction lands inside the window.

Note for the PO (veto if you disagree): 422 rather than a silent clamp-to-nearest — silently rewriting the date would write the snapshot to a day the user didn't write on, which is worse than a loud reject the FE can ignore (the report is already best-effort/advisory and never blocks editing).

*Evidence:* services/composition-service/app/routers/progress.py:56-62 (`_parse_local_date` — validates FORMAT only, no bound); :105 (`today: str = Query(...)` taken verbatim from the client); :117 (`anchor = _parse_local_date(today)` → :125 `_current_streak(by_date, anchor)`); :136 (`ProgressReportBody.date: str` — unbounded) → :157-158 (`snapshot_date = _parse_local_date(body.date)` → `progress.report(...)` writes the row on that arbitrary date). Repo confirms the row is per-user and upserts on (user, project, chapter, date): services/composition-service/app/db/repositories/daily_progress.py:47-66 — so the blast radius is the caller's own streak only (no tenancy/cost defect). Streak is derived purely from those dates: progress.py:76-90. Existing tests: services/composition-service/tests/unit/test_progress_router.py. FE call sites: frontend/src/features/composition/api.ts:304,311.

### Q-31-P2-CLEAR-SEMANTICS
**UPSERT the row with `daily_goal = NULL`. Never DELETE the row; never bind literal `0` into the column.** The row's EXISTENCE is the per-user tier claim; its VALUE is the goal. A NULL row is an explicit "I have no goal" that SHADOWS the legacy per-book value — which is the whole point of BE-P2 (F-Q7). DELETE is not a valid option: it re-exposes `work.settings.daily_goal`, so Bob clearing his goal would resurrect Alice's shared book goal and measure his counter against it — the exact tenancy defect BE-P2 exists to kill, re-entered through the clear path. Answering the spec's own question: **deleting the row re-exposing a legacy goal is NOT intended.**

**1 · DDL — unchanged from BE-P2 as written.** `daily_goal INT CHECK (daily_goal > 0)` has no `NOT NULL`, and a Postgres CHECK passes unless it evaluates FALSE (`NULL > 0` → UNKNOWN → passes). NULL is already admitted. Add only a comment: `-- NULL = the user explicitly CLEARED their goal; the row still SHADOWS work.settings.daily_goal (never DELETE — a delete re-exposes the legacy per-book goal, F-Q7).`

**2 · Router `PUT /v1/composition/works/{pid}/progress/goal` (new, in `progress.py`).** Body `{goal: int}` with `Field(ge=0, le=5_000_000)` (mirrors `ProgressReportBody.words` at progress.py:134) ⇒ `goal < 0` → 422 (SET-5). Then coerce ONCE at the route boundary, before the repo: `stored: int | None = body.goal if body.goal > 0 else None`. Pass `stored` (never `body.goal`) to the repo. Gate with `_require_work(...)` before the repo, exactly as the sibling progress routes do.

**3 · Repo write — one statement, both set and clear:**
```sql
INSERT INTO composition_progress_goal (user_id, project_id, daily_goal, updated_at)
VALUES ($1, $2, $3, now())
ON CONFLICT (user_id, project_id)
DO UPDATE SET daily_goal = EXCLUDED.daily_goal, updated_at = now()
```
`$3` is `None` on clear. (Note this is `DO UPDATE`, NOT `DO NOTHING` — do not copy `composition_progress_baseline`'s ON CONFLICT DO NOTHING; a goal is re-settable.)

**4 · Resolution in `GET /progress` — gate on ROW PRESENCE, not on NOT NULL:**
- row exists AND `daily_goal IS NOT NULL` → `{daily_goal: N, daily_goal_source: 'user'}`
- row exists AND `daily_goal IS NULL` → `{daily_goal: null, daily_goal_source: 'none'}` ← the clear; **does NOT fall through to legacy**
- no row AND `_coerce_goal(work.settings)` is a positive int → `{daily_goal: N, daily_goal_source: 'work_legacy'}`
- else → `{daily_goal: null, daily_goal_source: 'none'}`
Fetch the row as a distinguishable tri-state (e.g. `fetchrow` → `None` for no-row vs a record whose `daily_goal` is `None`). Do NOT collapse it with a `COALESCE`/`or` — `row.daily_goal or legacy` silently reintroduces the DELETE bug.

**5 · Source enum stays CLOSED at 3** — `'user' | 'work_legacy' | 'none'`. Do NOT add a 4th value for "cleared": under SET-1 the effective value IS none, so `'none'` is honest, and the FE needs zero new branching (`ProgressPanel.tsx:65,104` already gate on `goal != null`, so the bar and the `ReferenceLine` simply vanish). `PUT` with `{goal: 0}` returns `{goal: null, source: 'none'}`.

**6 · FE:** rewrite `useSetDailyGoal` to call the new route and delete the `patchWork` caller; keep its existing `goal > 0 ? goal : null` intent but send the raw int — the server coerces. Invalidate `['composition','progress']`.

**7 · The two tests that make this real (real-SQL, per M2's DoD — a mock would encode the bug):**
- **The regression test DELETE would fail:** seed `work.settings.daily_goal = 2000` → `GET` returns `2000/'work_legacy'` → `PUT {goal: 500}` → `GET` returns `500/'user'` → `PUT {goal: 0}` → `GET` returns **`daily_goal: null, source: 'none'`** and explicitly **NOT** `2000/'work_legacy'`.
- **The CHECK-violation test:** `PUT {goal: 0}` returns 200 (not a 500 from `daily_goal_check`) and `SELECT daily_goal` for that PK `IS NULL` and a row still EXISTS (`SELECT count(*) = 1`).

*Evidence:* services/composition-service/app/routers/progress.py:65-73 (`_coerce_goal`: `0`/non-positive already → `None` — `0` is an established sentinel, never a stored value); frontend/src/features/composition/hooks/useProgress.ts:78 (`daily_goal: v.goal > 0 ? v.goal : null` — "0 → NULL" is already the repo's convention, so SET-5's "0 = clear (→ NULL)" is unambiguous about the value); services/composition-service/app/db/migrate.py:475,496 (sibling per-user tables — the shape BE-P2 mirrors; note `composition_progress_baseline`'s ON CONFLICT DO NOTHING must NOT be copied); docs/specs/2026-07-01-writing-studio/31_quality_completion.md:626 (SET-5) + :528 (BE-P2 DDL — already nullable: no NOT NULL, and Postgres CHECK passes on NULL) + F-Q7 §:230-240 (the fallback-to-legacy path that DELETE would re-open); frontend/src/features/composition/components/ProgressPanel.tsx:65,104 (`goal != null` gates — null needs no FE branching).

### BE-31-11c-MCP-RESTORE-TOOL
BUILD AS SPEC'D (MUST-BUILD, XS) — but mirror the EXISTING outline-node pair, and ignore the spec's ⚠ caveat (it is wrong for this service). BE-11c is a mechanical clone of a precedent that already ships. Four edits:

1. REPO — `services/composition-service/app/db/repositories/canon_rules.py`, add after `archive()` (ends :166):
   `async def restore(self, project_id: UUID, rule_id: UUID) -> CanonRule | None:` — copy `archive()` (:155-166) and invert: `SET is_archived = false, updated_at = now() WHERE project_id = $1 AND id = $2 AND is_archived RETURNING {_SELECT_COLS}`. Returns None if missing / other project / not archived. (Shared with BE-11a's REST route — build BE-11a/b/c together, one repo method serves both.)

2. MCP TOOL — `services/composition-service/app/mcp/server.py`, insert `composition_canon_rule_restore` after `composition_canon_rule_delete` (ends :1202). Copy `composition_outline_node_restore` (:957-992) verbatim, substituting canon: `@mcp_server.tool(name="composition_canon_rule_restore", description="Un-archive a previously deleted canon rule (the inverse of delete). EDIT required (auto-applied; Undo re-deletes it).", meta=require_meta("A","book", synonyms=["restore canon rule","undelete invariant","unarchive rule"], tool_name="composition_canon_rule_restore"))`. Body: bare `Annotated[str,...]` params `project_id`/`rule_id` (NO pydantic model — delete/outline-restore both use bare Annotated params); `_ctx` → `_book_or_deny(works, tc, pid, GrantLevel.EDIT)` → `prior = await canon.get(pid, UUID(rule_id))`; `if prior is None or prior.project_id != pid: raise uniform_not_accessible()`; `rule = await canon.restore(pid, UUID(rule_id))`; `if rule is None: raise uniform_not_accessible()`; return `rule.model_dump(mode="json")` + `out["_meta"] = {"undo_hint": _undo("composition_canon_rule_delete", project_id=project_id, rule_id=rule_id)}`. The project-scope pre-check needs NO new repo method: `CanonRulesRepo.get()` (:99-103) has no `is_archived` predicate, so it already returns archived rows (same property `get_node` relies on).

3. FIX THE DELETE HALF (the GG-2 inverse) — `server.py:1199-1201`: delete the comment "archive() only flips a NOT-archived row; there is no un-archive repo method… Honest: undo unavailable" and replace `out["_meta"] = {"undo_hint": None}` with `out["_meta"] = {"undo_hint": _undo("composition_canon_rule_restore", project_id=project_id, rule_id=rule_id)}`. Mirrors `outline_node_delete` :951-953. The comment's stated reason is now false, so it MUST go with the code.

4. ⚠ THE SURFACE THE SPEC MISSED (do not skip — this is the real trap) — `services/mcp-public-gateway/src/scope/tool-policy.ts`: add `composition_canon_rule_restore: { tier: 'write_auto', domains: ['composition'] },` after :236. This file is DEFAULT-DENY / fail-closed (:9 "default-deny unknown / fail-closed"; :340 "True iff the tool has an explicit policy entry (i.e. is classified, not unknown)"; `filterTools` :368 drops unclassified tools). `composition_outline_node_restore` carries its row at :231. Without this row the tool is registered, unit-green, and SILENTLY UNREACHABLE at the public edge — the repo's known built-but-unreachable bug class. There is no parity test guarding this (I grepped mcp-public-gateway for one; none exists), so nothing will catch the omission.

CORRECTION TO THE SPEC — the ⚠ "3-schema-source FastMCP caveat" does NOT apply to composition-service. That caveat is knowledge-service-specific: knowledge has a bespoke `TOOL_DEFINITIONS` hand-schema (`tools/definitions.py`) PLUS a pydantic arg model PLUS the FastMCP signature. Composition-service has NO `definitions.py` (verified: `find services/composition-service -name definitions.py` → nothing) — the `@mcp_server.tool` decorator is the single schema source. A builder chasing three schema sources here will hunt two files that do not exist. The real second surface is tool-policy.ts (#4).

TESTS (Definition of Done): (a) add `"composition_canon_rule_restore"` to `EXPECTED_TOOLS` in `services/composition-service/tests/unit/test_mcp_server.py` (Tier-A block, next to `composition_canon_rule_delete` :60) — this set is the registration drift guard and will red until the tool exists; (b) `test_canon_rule_restore_returns_undo_hint` asserting `undo["tool"] == "composition_canon_rule_delete"` (mirror the existing delete-side assertion at :789-791); (c) `test_canon_rule_restore_foreign_project_refused` raising `NotAccessibleError` (mirror :987-996); (d) AMEND the existing delete test to assert `undo["tool"] == "composition_canon_rule_restore"` instead of None — a stale `assert undo_hint is None` would otherwise lock the bug in; (e) repo test: restore of a NOT-archived rule returns None → `uniform_not_accessible`. tool-liveness.json (3 identical copies — contracts/, chat-service/, agent-registry-service/) is a SWEEP-GENERATED artifact, not a hand-authored schema; it picks the tool up on the next sweep — do not hand-edit it.

No PO call is embedded here: tier (A), scope (book), args, gate, and undo shape are all fixed by the outline-node precedent, and PO-sealed MCP-first parity forbids shipping the human restore (BE-11a) without the agent verb.

*Evidence:* services/composition-service/app/mcp/server.py:1199-1201 — the spec's premise verbatim: "archive() only flips a NOT-archived row; there is no un-archive repo method, so there is no verified reverse op to surface. Honest: undo unavailable." → `out["_meta"] = {"undo_hint": None}`. | PRECEDENT TO CLONE: server.py:957-992 (`composition_outline_node_restore`) + server.py:919-954 (`composition_outline_node_delete`) — each carries the other as `undo_hint` (:951-953, :989-991); backed by `OutlineRepo.restore_node` at app/db/repositories/outline.py:1409 ("Un-archive a node — the inverse of `archive_node`"). | REPO GAP: app/db/repositories/canon_rules.py:155-166 `archive()` is the file's LAST method — no inverse; `get()` :99-103 has no `is_archived` filter so it already returns archived rows (the gate pre-check needs nothing new). | MISSED SURFACE: services/mcp-public-gateway/src/scope/tool-policy.ts:236 (`composition_canon_rule_delete`) vs :231 (`composition_outline_node_restore`) — file is default-deny (:9, :340 `isClassified`, :368 `filterTools`), so an unlisted tool is silently unreachable at the public edge. | CAVEAT REFUTED: `find services/composition-service -name definitions.py` → no results (no bespoke TOOL_DEFINITIONS; the 3-schema-source caveat is knowledge-service-only). | DRIFT GUARD: services/composition-service/tests/unit/test_mcp_server.py:47-60 `EXPECTED_TOOLS` set; delete-side undo assertion at :789-791; foreign-project refusal at :987-996.

### BE-31-18-PATCHWORK-BLOB
CONFIRMED: do NOT fix this in spec-31's M2 — but the row text is WRONG and must be corrected, because it mis-scopes the future work.

(1) M2 builder instruction (binding): touch NOTHING in `PATCH /works/{pid}` — not the router, not `WorksRepo.update`, not `compositionApi.patchWork`. BE-P2 deletes `useSetDailyGoal` (frontend/src/features/composition/hooks/useProgress.ts:71-87) and with it this wave's only exposure. Any If-Match/blob-merge edit appearing in an M2 diff is scope creep and `/review-impl` should reject it at the wave gate.

(2) Correct the row (edit BOTH `30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md:312` and `31_quality_completion.md:530`): the claim "NO If-Match" is FALSE at HEAD. Server-side OCC is already shipped — `routers/works.py:588` accepts the `If-Match` header, `:597` parses it, `:603-607` maps `VersionMismatchError` → `412 {"code":"WORK_VERSION_CONFLICT","current":…}`; `db/repositories/works.py:319-324` gates `WHERE version = $n` and bumps it. So BE-18 is **FE-only** and needs **no backend change and no jsonb `||` merge** — full-blob replace *under OCC* is the correct semantics (it is what lets `daily_goal: null` actually delete a key; a `settings = settings || $n` merge would silently make key-deletion impossible — do NOT do that).

(3) BE-18's real, reduced scope, to be built in plan-30 **Wave 6** (spec `36_editor_craft_ports.md`, gap G-WORK-SETTINGS, where the Composition-settings panel becomes the caller) — new row text:
  - `frontend/src/features/composition/api.ts:443` — add `ifMatch?: number` to `patchWork(projectId, patch, token, ifMatch?)`; when present send header `If-Match: String(ifMatch)`; drop the "server REPLACES the whole blob — caller MUST merge" warning comment (:439-442) and replace it with "read-modify-write under If-Match; a 412 means someone else wrote — refetch and retry".
  - The two surviving callers pass `work.version` (already on `Work`, `types.ts:10`): `useWork.ts:135` (`useSetWorkSettings`) and `useChapterAssembly.ts:33` (`setAssemblyMode`). Both keep hand-merging `{...currentSettings, ...patch}` — that stays correct; If-Match is what makes it *safe*.
  - On `412`: invalidate/refetch `['composition','work',bookId]`, re-merge the patch onto the fresh `settings`, retry ONCE with the new `version`; a second 412 surfaces a toast ("settings changed elsewhere — reloaded"). Keep it in the mutation's `mutationFn`/`onError`, not a `useEffect`.
  - Tests: `useWork.test.tsx` — (a) asserts `patchWork` was called with the work's `version` and the request carries `If-Match`; (b) mock a 412 once → asserts refetch + single retry with the bumped version and no key loss. BE side needs no new test (`expected_version` path is already covered by the repo's 412 behavior).

*Evidence:* services/composition-service/app/routers/works.py:588,597,603-607 (If-Match header → 412 WORK_VERSION_CONFLICT) · services/composition-service/app/db/repositories/works.py:311-312 (settings = $n::jsonb) and :319-324,:337 (version gate + bump + VersionMismatchError) · frontend/src/features/composition/api.ts:439-446 (patchWork sends NO If-Match — the actual residual defect) · frontend/src/features/composition/types.ts:10 (Work.version already exposed) · callers: hooks/useProgress.ts:77 (deleted by BE-P2), hooks/useWork.ts:135, hooks/useChapterAssembly.ts:33 · ownership: docs/specs/2026-07-01-writing-studio/30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md:312 + Wave 6 "BE prereqs" (spec 36, G-WORK-SETTINGS)

### BE-31-9b-RECORD-CORRECTION
BUILD IT — MUST-BUILD confirmed. Table, repo, outbox emit, and the learning consumer are all live; nothing is blocked. The one open bit (edit-detection) is decided below, and the naive version the spec implies is WRONG — build the normalized version.

1) PREREQ (BE-9a, separate item): `authoring_run_units.job_id UUID` (nullable) + `DraftOutcome.job_id` + driver write. BE-9b CONSUMES `unit.job_id`. `job_id IS NULL` (unit drafted pre-migration) ⇒ skip capture, return `correction_recorded:false, reason:"no_job_id"`. Never fabricate.

2) PUT THE CAPTURE IN THE SERVICE, NOT THE ROUTERS. `AuthoringRunService.__init__` already takes `critic: CriticSeam | None = None` defaulting to the real `EngineCriticSeam()` (authoring_run_service.py:635,651). Mirror it exactly: add `corrections: CorrectionCaptureSeam | None = None` → defaults to the real seam; tests inject a fake. Both doors (REST authoring_runs.py:352/382, MCP server.py:1919/1970) then call `svc.accept_unit`/`reject_unit` UNCHANGED and neither can forget to wire it. Do NOT use a per-call injected param like `restore` — that is 2 call sites and one of them will silently no-op.

3) reject_unit (authoring_run_service.py:919): capture `kind='reject'` AFTER the drafted→rejected transition succeeds (the restore can raise → 502 with the unit left drafted; never record a correction for a reject that did not happen).

4) accept_unit (authoring_run_service.py:896): after drafted→accepted, run EDIT-DETECTION:

   THE MECHANIC (this is the answer to the open question). Compare in ONE normal form:
     from app.engine.prose_doc import text_to_tiptap_doc, tiptap_doc_to_text
     baseline = tiptap_doc_to_text(text_to_tiptap_doc(job.result.get("text") or ""))
     current  = tiptap_doc_to_text(draft.get("body") or draft.get("doc") or draft.get("content"))
     changed  = count_changed_blocks(baseline, current)
   changed == 0 ⇒ accept-as-is ⇒ RECORD NOTHING (H2), `correction_recorded:false`.
   changed  > 0 ⇒ corrections.create(kind='edit', changed_blocks=changed, raw_after=current).

   DO NOT write `count_changed_blocks(job.result["text"], current)` — the round-trip is NOT identity. Generated prose carries ATX `### <scene title>` lines (F4 D-SCENEMARKER-EMIT); `text_to_tiptap_doc` lifts them to heading nodes whose `_text` DROPS the `### ` prefix (prose_doc.py:48,107) and `tiptap_doc_to_text` reads `_text` back (prose_doc.py:127). The raw comparison therefore reports a diff on every heading line of an UNTOUCHED chapter ⇒ false `kind='edit'` on every accept-as-is ⇒ the self-reinforcement H2 forbids, and it BYPASSES the EDIT_NO_CHANGE guard (engine.py:1755) because changed_blocks > 0. `tiptap_doc_to_text ∘ text_to_tiptap_doc` is idempotent (a stripped heading re-parses as a plain paragraph), so normalizing the baseline makes an untouched chapter compare equal.

   Read the chapter via the LIVE precedent (EngineCriticSeam, authoring_run_service.py:586-590): `mint_service_bearer(run.created_by, settings.jwt_secret)` → `get_book_client().get_draft(run.book_id, unit.chapter_id, bearer)`. accept/reject are creator-only (`_require_own_run`, server.py:1916) so caller == run.created_by; the row's `created_by` is unambiguous.

5) project_id: `AuthoringRun` has NO project_id (models.py:723-727; migrate.py:1417-1421). Resolve from the run's book: `WorksRepo(get_pool()).resolve_by_book(run.book_id)` (precedent authoring_run_service.py:600). Pass `corrections.create(work.project_id, unit.job_id, ...)` and let the repo's in-txn "job in THIS project" check (generation_corrections.py:88-95) raise `ReferenceViolationError` on a foreign job. Do NOT read `project_id` off a bare-id `jobs.get()` (worker-loaded-id-needs-parent-scoping).

6) Raw prose stays OPT-IN: only set raw_before/raw_after when `work.settings.get("capture_correction_prose", False)` (mirror engine.py:1766). For reject, `raw_before = baseline` only. Structural fields (kind, changed_blocks) always.

7) FIRE-AND-FORGET: wrap the capture in try/except → logger.warning + continue. A capture failure must NEVER fail the accept/reject (the transition is already committed). Surface the truth on the payload so the agent cannot hallucinate success: `{success, unit_index, status, correction_recorded: bool, correction_skipped_reason?: "no_job_id"|"no_change"|"capture_failed"}`.

8) MCP tool `composition_record_correction` (Tier A), in mcp/server.py beside the accept/reject tools (~:1885). Args `{project_id, job_id, kind, guidance?, edited_text?, chosen_candidate_index?}` → `{correction_id}`. `kind` is a CLOSED SET ⇒ `Literal["edit","pick_different","regenerate","reject"]` (Frontend-Tool-Contract IN-1), never a free string. Resolve book from project via WorksRepo then `_gate(tc, book_id, GrantLevel.EDIT)`. Errors return MCP error payloads, not HTTPExceptions (server.py:1920-1924): job not in project → ReferenceViolationError → `{"success":false,"error":...}`; `kind='edit'` with identical text → refuse with EDIT_NO_CHANGE.

9) ANTI-DRIFT: do NOT "mirror" engine.py:1712-1790. EXTRACT its body into `app/services/correction_capture.py::capture_correction(...)` and call it from all three consumers (the REST route, the new MCP tool, the accept/reject seam) so the 422 rule, the opt-in-prose rule, and winner_index/candidate_count have ONE home. A mirrored copy is a guaranteed drift.

TESTS (required, name them):
- test_accept_untouched_chapter_with_scene_headings_records_nothing — job.result.text contains `### Scene One`; chapter = that text round-tripped, human never edited. Asserts changed==0 and ZERO correction rows. THIS TEST MUST FAIL against the naive comparison — it is the regression pin for the heading-stripping trap.
- test_accept_as_is_records_nothing (H2)
- test_accept_after_real_edit_records_kind_edit_with_changed_blocks
- test_reject_records_kind_reject
- test_capture_failure_never_fails_accept (seam raises → unit still accepted, correction_recorded false)
- test_unit_without_job_id_skips_capture (no_job_id)
- test_rest_accept_captures AND test_mcp_accept_captures — proves the ctor-default seam fires through BOTH doors (no-silent-no-op).
- test_mcp_record_correction_edit_identical_text_refused (mirrors the 422).

DEFAULT I PICKED (veto-able): accept-as-is records NOTHING, per H2 — the spec already says this, and the normalized diff is what makes it true in practice rather than only on paper.

*Evidence:* services/composition-service/app/engine/prose_doc.py:48,107,127 (round-trip is NOT identity — `_heading_node` strips the `### ` prefix, `tiptap_doc_to_text` reads `_text` back) · engine.py:307-311 (draft persisted as text_to_tiptap_doc) · engine.py:1712,1737,1748,1755,1766 (the REST correction route to extract: winner_text, count_changed_blocks, EDIT_NO_CHANGE 422, capture_correction_prose opt-in) · db/repositories/generation_corrections.py:42 (count_changed_blocks), :88-95 (job-in-project check → ReferenceViolationError) · services/authoring_run_service.py:197-202 (DraftOutcome has no job_id — BE-9a), :586-590 (mint_service_bearer→get_draft→tiptap_doc_to_text precedent), :600 (resolve_by_book), :625-651 (ctor seam-default pattern to copy), :896 accept_unit, :919 reject_unit · mcp/server.py:1903,1916,1948 (accept/reject tools, _require_own_run creator-only) · db/models.py:723-727 + db/migrate.py:1417-1421,1493 (AuthoringRun has no project_id; authoring_run_units has no job_id)

### BE-31-9c-prime-LITERAL-NARROWING
BUILD IT (MUST-BUILD with BE-9c) — but NOT to the one-value set the spec's framing implies. The spec's own pre-flight ("check for any existing caller posting a non-standard `operation` before narrowing") has a POSITIVE HIT: two shipped FE features already post ops other than `draft_scene` on the scene route. `Literal["draft_scene"]` would 422 them. The correct closed set is the drafter's OWN registry (`_OPERATION_INSTRUCTIONS`, cowrite.py:28-48), partitioned by route.

EXACT CHANGES

(1) `services/composition-service/app/engine/cowrite.py` — after `_OPERATION_INSTRUCTIONS` (ends :48), add the named constants (one home, one name — no literals at call sites):
    DRAFT_OPERATIONS     = ("draft_scene", "continue", "adapt_scene")   # /works/{pid}/generate
    CHAPTER_OPERATIONS   = ("draft_chapter",)                            # /works/{pid}/chapters/{cid}/generate
    SELECTION_OPERATIONS = ("rewrite", "expand", "describe")             # /selection-edit (already Literal)

(2) `app/routers/engine.py:98` → `operation: Literal["draft_scene", "continue", "adapt_scene"] = "draft_scene"`
(3) `app/routers/engine.py:141` → `operation: Literal["draft_chapter"] = "draft_chapter"`
    (Literal args must be literal — the tuples in (1) are the drift-assertion target, not the type source.)

(4) THIRD OPEN SURFACE THE SPEC DID NOT NAME — `app/mcp/server.py:1356`, `_GenerateArgs.operation: str | None = None`. It feeds these exact bodies at the confirm-execute seam (`app/routers/actions.py:453` GenerateBody / `:462` GenerateChapterBody). Close it to the union: `operation: Literal["draft_scene","continue","adapt_scene","draft_chapter"] | None = None`, and fix the comment at server.py:1351-1355 — it already CLAIMS "Literals mirror the engine's GenerateBody", which is false for exactly this field. Leaving it open means a bad op survives propose AND the user's paid confirm, then dies as a 400 at execute — the repo's paid-action-defect shape.

TESTS (`tests/unit/test_engine_router.py`, mirroring the existing `test_selection_edit_rejects_unknown_operation` at :244-249):
  - `test_generate_rejects_unknown_operation` — POST /works/{pid}/generate `operation:"summarize"` ⇒ 422
  - `test_generate_accepts_continue_and_adapt_scene` — both 200 (regression guard for the two live callers)
  - `test_chapter_generate_rejects_unknown_operation` — `operation:"draft_scene"` on the CHAPTER route ⇒ 422
  - drift guard (the LOOM-39 lesson made mechanical): `set(get_args(GenerateBody.model_fields["operation"].annotation)) == set(DRAFT_OPERATIONS)` and `set(DRAFT_OPERATIONS)|set(CHAPTER_OPERATIONS)|set(SELECTION_OPERATIONS) <= set(_OPERATION_INSTRUCTIONS)`

BREAKING-CHANGE SURFACE = EMPTY IN PRACTICE. Every caller in the repo posts a value inside the new closed set: 10 eval scripts post `draft_scene`; api.ts:406 defaults `draft_scene`; api.ts:448 chapter defaults `draft_chapter`; `authoring_run_service.py:337` (`params.get("operation") or "draft_chapter"`) already wraps construction in a try/except that catches ValidationError → clean `DraftOutcome(ok=False, "invalid seam params")` — NO change needed there, the narrowing just upgrades a silent weak-prompt draft into a clean failure. The only tests carrying `operation="x"` (test_engine_router.py:371,381) put it in a FAKE GenerationJob DB row, not a request body — they stay green. So the only client that 422s after this lands is one posting an op the drafter never recognized, which today silently falls back to the generic "Write the next passage of the scene." (cowrite.py:101) — i.e. exactly the bug.

DEFAULT I AM SETTING (PO may veto): `continue` and `adapt_scene` are now first-class typed API values but are deliberately NOT in BE-9c's `CORRECTABLE_OPERATIONS = ("draft_scene","draft_chapter","stitch_chapter")` — they are not plan-grounded from-a-beat drafts, so folding them into `accept_rate` would mix signals. Make the exclusion VISIBLE, not accidental: add an assertion that `(set(DRAFT_OPERATIONS)|set(CHAPTER_OPERATIONS)) - set(CORRECTABLE_OPERATIONS) == {"continue","adapt_scene"}`, so any future op added to the route forces a conscious in/out call on the denominator.

*Evidence:* services/composition-service/app/engine/cowrite.py:28-48 (`_OPERATION_INSTRUCTIONS` registry — `continue`:29, `draft_scene`:30, `draft_chapter`:34, `expand`:36, `rewrite`:37, `describe`:38, `adapt_scene`:44) + cowrite.py:101 (`_OPERATION_INSTRUCTIONS.get(operation, "Write the next passage of the scene.")` — the silent fallback that makes an open `str` a bug). Open fields: services/composition-service/app/routers/engine.py:98 (`operation: str = "draft_scene"`), :141 (`operation: str = "draft_chapter"`); contrast :122 (`SelectionEditBody.operation: Literal[...]` with the LOOM-39 comment at :118-121). LIVE NON-DEFAULT CALLERS (this is the finding — the spec's pre-flight is a POSITIVE hit): frontend/src/features/composition/hooks/useInlineGhost.ts:60 posts `operation: 'continue'`, and frontend/src/features/composition/components/ComposeView.tsx:73 posts `operation: 'adapt_scene' as const` — both to `generateUrl` = `/works/{pid}/generate` (frontend/src/features/composition/api.ts:389-390, and the diverge/auto path api.ts:399 hits the SAME URL/body), which is `GenerateBody` (engine.py:329). THIRD OPEN SURFACE the spec omits: services/composition-service/app/mcp/server.py:1356 (`operation: str | None = None` in `_GenerateArgs`, whose comment at :1351-1355 falsely claims "Literals mirror the engine's GenerateBody") → payload at server.py:1419 → services/composition-service/app/routers/actions.py:425,453,462 rebuilds GenerateBody/GenerateChapterBody at confirm-execute. Spec row under adjudication: docs/specs/2026-07-01-writing-studio/31_quality_completion.md:525.

### Q-31-QC8-GCTIME-EVICTION
Set an explicit `gcTime: Infinity` on the QC-8 shared key, declared on BOTH sides, and document the (accepted) reload-loses-it boundary.

CONCRETE INSTRUCTION (M3 BUILD):

1) `frontend/src/features/composition/hooks/usePolishProposals.ts` — when the hook is rewritten from `useState` to the react-query cache (spec 31 line 62), the writer-side observer MUST declare both options:
```ts
const QK = (projectId: string, chapterId: string) =>
  ['composition', 'self-heal', projectId, chapterId] as const;

const { data } = useQuery({
  queryKey: QK(projectId, chapterId),
  queryFn: skipToken,            // never fetches — the paid run is a useMutation that setQueryData's
  staleTime: Infinity,
  gcTime: Infinity,              // QC-8: default is 5min (App.tsx:10) → entry evicted once BOTH panels close
  initialData: undefined,
});
```
The paid PROPOSE run stays a `useMutation` whose `onSuccess` does `queryClient.setQueryData(QK(pid, cid), payload)` (payload = `{proposals, sourceText, draftVersion, stats}` — keep the current return shape so `PolishPanel` is unchanged).

2) `quality-critic`'s reader (the hook feeding `QualityReportSection`'s `proposals` prop — `frontend/src/features/composition/components/QualityReportSection.tsx:39`) reads the SAME key with `useQuery({ queryKey: QK(pid,cid), queryFn: skipToken, enabled: false, staleTime: Infinity, gcTime: Infinity })`. Declare `gcTime: Infinity` here too — do not rely on the writer alone. (v5 `Removable.updateGcTime` takes the MAX across observers, so a reader that inherits the 5-min default cannot lower it — but if the reader is the only mounted observer at some point, an explicit Infinity is what keeps the guarantee readable and local. Same value in both places, one shared `QK()` helper exported from `usePolishProposals.ts` so the key literal exists ONCE.)

3) Memory: bounded and negligible — one entry per (projectId, chapterId) the author actually ran Polish on in this browser session; each is a handful of span/replacement strings. No eviction policy needed.

4) Accepted boundary, WRITE IT IN THE SPEC (31 §QC-8) as one line: "proposals live in the in-memory query cache; a full page reload clears them, so the `violation-has-fix` badge is session-scoped. Cache miss ⇒ `[]` ⇒ no badge — a FALSE badge remains impossible." No persistence layer, no localStorage (Data Persistence Rules forbid it for user data anyway).

5) DoD test that actually catches the shape the panel-pair test misses — add to `frontend/src/features/composition/hooks/__tests__/usePolishProposals.test.tsx`, with ONE `QueryClient` created using the app's real defaults (`gcTime: 5*60*1000`) and `vi.useFakeTimers()`:
   render writer → mutate → assert proposals present → **unmount BOTH observers** → `vi.advanceTimersByTime(6 * 60 * 1000)` → mount ONLY the critic-side reader → assert `proposals.length > 0`. Name it `it('survives gc after both panels close (QC-8 gcTime: Infinity)')`. Without the fix this test reds; with it, it greens. This is the assertion the "open both panels in one session" DoD test cannot make.

PO veto hook: if the PO would rather bound memory than keep the badge, the alternative is `gcTime: 24 * 60 * 60 * 1000` — same test, different constant. Infinity is the default I picked because the entry is per-chapter, tiny, and dying with the tab anyway.

*Evidence:* frontend/src/App.tsx:10 — `gcTime: 5 * 60 * 1000, // 5min — garbage collect after 5min` is the app-wide QueryClient default, so the QC-8 key (docs/specs/2026-07-01-writing-studio/31_quality_completion.md:308, which specifies `staleTime: Infinity` and is silent on gcTime) IS evicted 5 minutes after quality-heal + quality-critic both unmount. Today the state is `useState` (frontend/src/features/composition/hooks/usePolishProposals.ts:22-29) and the reader prop is `proposals?: SelfHealProposal[]` (frontend/src/features/composition/components/QualityReportSection.tsx:20,39), i.e. the cache-backed version is unbuilt — so this is a fresh option value, not a change to shipped code.

### BE-31-P1-BY-CHAPTER
**BUILD IT. BE-P1 is MUST-BUILD; OQ-5 is answered "yes, it is worth the route change." Do NOT drop it.** (This overrides the spec's stated "default = drop" — PO may veto, but the cost is ~35 lines and the drop cost is permanent.)

WHY (grounded, not taste): `DailyProgressRepo.read_aggregate` ALREADY computes the per-chapter delta — `daily_progress.py:98` partitions the LAG `BY d.chapter_id` — and then throws the dimension away at `daily_progress.py:111` (`GROUP BY snapshot_date`). Meanwhile `report()` (`daily_progress.py:56-64`) writes `chapter_id` into the PK on EVERY save. So today the chapter dimension is written forever and read at that grain by nobody — exactly the "data-generation with no reader" (GG-4 / write-only) class spec 31 §"Why this exists" item 2 exists to close. Dropping BE-P1 enshrines it. The wire change is purely ADDITIVE (a new key existing clients ignore), the panel draft already draws the row, and re-adding it later costs a second route change + contract churn.

EXACT BUILD (do this, no further thought needed):

1. `services/composition-service/app/db/repositories/daily_progress.py`
   a. Extend the dataclass (default keeps every existing constructor + the FakeRepo at `tests/unit/test_progress_router.py:53` compiling unchanged):
      `by_chapter: list[tuple[UUID, int]] = field(default_factory=list)`  # (chapter_id, words authored ON the anchor date), words DESC
   b. Add a THIRD query inside `read_aggregate` (same acquired connection, after `book_total_q`):
      ```sql
      WITH s AS (
        SELECT d.chapter_id, d.snapshot_date, d.words,
               COALESCE(
                 LAG(d.words) OVER (PARTITION BY d.chapter_id ORDER BY d.snapshot_date),
                 b.words
               ) AS prev_words
        FROM composition_daily_progress d
        LEFT JOIN composition_progress_baseline b
          ON b.user_id = d.user_id AND b.project_id = d.project_id
             AND b.chapter_id = d.chapter_id
        WHERE d.user_id = $1 AND d.project_id = $2 AND d.snapshot_date <= $3
      )
      SELECT chapter_id,
             (CASE WHEN prev_words IS NULL THEN 0
                   ELSE GREATEST(words - prev_words, 0) END)::int AS words
      FROM s
      WHERE snapshot_date = $3
        AND (CASE WHEN prev_words IS NULL THEN 0
                  ELSE GREATEST(words - prev_words, 0) END) > 0
      ORDER BY words DESC
      ```
      🔴 **THE TRAP — do not "optimize" it away:** the `snapshot_date = $3` filter MUST stay OUTSIDE the CTE. Push it into the CTE's WHERE and `LAG` loses the previous day, so every chapter's today-delta silently becomes its baseline-diff — i.e. the panel reports the WHOLE chapter as written today. Same `<= $3` history window as the other two queries (no future-dated rows). Rows with a 0 delta are omitted (a chapter merely OPENED today must not appear); a first-snapshot/baseline row (`prev_words IS NULL`) contributes 0 and is omitted, matching `day_words`'s formula exactly.
   c. Return `by_chapter=[(r["chapter_id"], r["words"]) for r in rows3]`.

2. `services/composition-service/app/routers/progress.py:124-131` — add ONE key to the `get_progress` dict:
   `"by_chapter": [{"chapter_id": str(cid), "words": w} for cid, w in agg.by_chapter],`
   No new query param (the list is at most a handful of rows — always included). No chapter titles on the wire: composition-service does not own chapters and the router today touches only `works` + the grant client (`progress.py:110-117`) — do NOT add a book-service call here.

3. `frontend/src/features/composition/types.ts:277-284` — `ProgressStats` gains `by_chapter: { chapter_id: string; words: number }[];`

4. `frontend/src/features/composition/components/ProgressPanel.tsx` — render the collapsible "▸ by chapter (today)" row from the spec's §M2 ASCII, guarded on `stats.by_chapter?.length` (absent/empty ⇒ render nothing; legacy page is unaffected). Map `chapter_id → title` by MIRRORING the sibling panel that already does it: `QualityCriticPanel.tsx:33-41` (`booksApi.listChapters(token, bookId, { sort: 'sort_order', limit: CHAPTER_PICKER_LIMIT })`). Two hazards, both already bitten in this repo: (i) `limit > 100` falls back to 20 in `parseLimitOffset` — reuse the same `CHAPTER_PICKER_LIMIT` constant, do not invent a bigger one; (ii) the list is PAGED, so a chapter_id NOT in the fetched page is "not-yet-loaded", NOT "deleted" — render the raw short id (`chapter_id.slice(0, 8)`) as fallback, never hide the row and never label it missing.

TESTS (all three are required):
- `services/composition-service/tests/integration/db/test_repositories.py` (next to the existing `read_aggregate` cases at :2206-2293): a chapter with snapshots on D-1 and D (anchor) reports `by_chapter == [(ch, D_words - D-1_words)]` — and a second test seeding a THIRD earlier snapshot proves the LAG still sees D-1 (the trap in 1b).
- Same file: **the invariant** — `sum(w for _, w in agg.by_chapter) == dict(agg.day_words)[anchor]`. by_chapter must never disagree with `today_words`.
- `services/composition-service/tests/unit/test_progress_router.py`: the FakeRepo returns a `ProgressAggregate` with `by_chapter`; assert the response body carries `by_chapter` with stringified UUIDs, and that an empty `by_chapter` serializes to `[]` (not omitted).

SIZE: S (spec's own estimate confirmed). Wave/milestone: M2, alongside the `progress` panel port. Update the OQ-5 + BE-P1 rows in `31_quality_completion.md` from "droppable / decide in PLAN" to "MUST-BUILD — decided".

*Evidence:* services/composition-service/app/db/repositories/daily_progress.py:98 (`LAG(d.words) OVER (PARTITION BY d.chapter_id ORDER BY d.snapshot_date)` — the chapter dimension is already computed) vs :111 (`GROUP BY snapshot_date` — the single line that collapses it, = F-Q8); :56-64 (`report()` writes chapter_id into the PK on every save ⇒ written-never-read at that grain). Router seam: services/composition-service/app/routers/progress.py:118-131 (re-shapes agg only; no cross-service call ⇒ additive field is free). FE title source precedent: frontend/src/features/studio/panels/QualityCriticPanel.tsx:33-41 (booksApi.listChapters). Existing tests to extend: services/composition-service/tests/integration/db/test_repositories.py:2206-2293 and services/composition-service/tests/unit/test_progress_router.py:53. No conflict with plan-30 §0 PO-1..4 (docs/specs/2026-07-01-writing-studio/30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md:19-22 — none touch progress).

### X-31-2-CATEGORY-ORDER-QUALITY
CONFIRMED BUG — fix it as step 0 of the wave, before M1. The spec's diagnosis is right but its fix is incomplete (it misses the i18n half) and it patches the symptom rather than the cause. Do these four edits, in this order, as one commit:

(1) MAKE THE ORDER THE SSOT — `frontend/src/features/studio/panels/catalog.ts:81-91`. The union type and CATEGORY_ORDER are two hand-maintained lists of the same closed set; that is WHY they drifted. Replace the standalone union with a const array + derived type (keep the union's existing order — `quality` sits between `knowledge` and `translation`):
    export const STUDIO_PANEL_CATEGORIES = [
      'editor', 'storyBible', 'knowledge', 'quality', 'translation',
      'enrichment', 'sharing', 'platform', 'discovery', 'jobs',
    ] as const;
    export type StudioPanelCategory = (typeof STUDIO_PANEL_CATEGORIES)[number];

(2) DERIVE CATEGORY_ORDER — `frontend/src/features/studio/palette/useStudioCommands.ts:4` and `:20-22`. Change the type-only import to a value import and delete the hand-written array:
    import { STUDIO_PANEL_CATEGORIES, type StudioPanelDef, type StudioPanelCategory } from '../panels/catalog';
    export const CATEGORY_ORDER: readonly StudioPanelCategory[] = STUDIO_PANEL_CATEGORIES;
  No import cycle (useStudioCommands already depends on catalog; catalog does not import useStudioCommands). `readonly` is safe for all three consumers: `.indexOf` (useStudioCommands.ts:55-57), `.filter`/`.includes` + `(typeof CATEGORY_ORDER)[number]` (UserGuidePanel.tsx:24-25).

(3) CLOSE THE TEST HOLE — `frontend/src/features/studio/panels/__tests__/panelCatalogContract.test.ts`. The existing test (:40-43) asserts only that a category EXISTS, never that it is a MEMBER of the order — exactly the hole this bug fell through. Add, importing `CATEGORY_ORDER` from '../../palette/useStudioCommands' and `STUDIO_PANEL_CATEGORIES` from '../catalog':
    it('every palette-openable panel category is in CATEGORY_ORDER (else indexOf → -1 and it sorts ABOVE editor)', () => {
      const orphan = OPENABLE_STUDIO_PANELS.filter((p) => !CATEGORY_ORDER.includes(p.category!)).map((p) => p.id);
      expect(orphan).toEqual([]);
    });
    it('CATEGORY_ORDER covers the whole category set exactly once', () => {
      expect([...new Set(CATEGORY_ORDER)]).toEqual([...STUDIO_PANEL_CATEGORIES]);
    });

(4) i18n — THE HALF THE SPEC MISSED. `frontend/src/i18n/locales/en/studio.json` → `palette.group` currently holds 13 keys and has NO `quality`, so the `group(p.category, p.category)` fallback (useStudioCommands.ts:61-63) renders the 5 quality panels under a raw lowercase `quality` header while every sibling gets a real label. Add `"quality": "Quality"` under `palette.group`, then propagate to the other 17 locales with `python scripts/i18n_translate.py`. en-only is acceptable if that tool is unavailable — `frontend/src/i18n/index.ts:48` sets `fallbackLng: 'en'`.

WHY BEFORE M1: M1 adds three more rows to the `quality` category, which deepens the mis-sort; and because CATEGORY_ORDER's -1 hoists Quality to the TOP of the palette while UserGuidePanel's `rest` bucket appends it to the BOTTOM, the two surfaces disagree today. The fix aligns both. This is a ~10-line change with zero product judgement in it — no PO call needed.

VERIFY: `cd frontend && npx vitest run src/features/studio/panels/__tests__/panelCatalogContract.test.ts src/features/studio/palette/__tests__/useStudioCommands.test.ts`. Both new assertions must go red if you revert edit (1)'s `'quality'` entry — prove that before moving on, or the test is decorative.

*Evidence:* frontend/src/features/studio/palette/useStudioCommands.ts:20-22 — CATEGORY_ORDER has 9 entries, no 'quality'; vs frontend/src/features/studio/panels/catalog.ts:81-91 — StudioPanelCategory union has 10, including 'quality'. Bites at useStudioCommands.ts:55-57 (`CATEGORY_ORDER.indexOf(a.category)` → -1, sorts above editor's 0) and inconsistently at UserGuidePanel.tsx:24-25 (unknown category falls into `rest`, appended LAST). Five panels carry category:'quality' (catalog.ts:266-270). Test hole: panelCatalogContract.test.ts:40-43 asserts a category exists but never that it is in CATEGORY_ORDER. i18n hole: frontend/src/i18n/locales/en/studio.json `palette.group` has 13 keys, no 'quality' → raw-string group header via the defaultValue fallback at useStudioCommands.ts:61-63; fallbackLng:'en' at frontend/src/i18n/index.ts:48.

### Q-31-ACCEPT-AFTER-EDIT-DETECTION
DETECT BY REVISION-ID COMPARE, USING THE SAME CAPTURE SEAM THAT WROTE post_revision_id. The two texts that feed count_changed_blocks are the TEXT OF post_revision_id (before) and the TEXT OF the chapter's CURRENT latest revision (after) — NOT job.result["text"], NOT the live draft body.

BUILD (BE-9b, accept leg). In `AuthoringRunService.accept_unit` (services/composition-service/app/services/authoring_run_service.py:896), AFTER the drafted→accepted transition succeeds, call a new private `_capture_accept_correction(run, unit)` wrapped in `try/except Exception: logger.warning(...)` — fire-and-forget; a capture failure NEVER fails the accept (BE-9b). Steps, in order:

1. `unit.job_id is None` (BE-9a's nullable column, historical units) ⇒ skip, log `correction_skipped=no_job_id`. Never fabricate.
2. `unit.post_revision_id is None` (the POST capture is best-effort, authoring_run_service.py:1165-1178) ⇒ skip, log `correction_skipped=no_post_revision_id`. ⚠ Do NOT fall back to comparing `job.result["text"]` against the live chapter text: the job result is LLM plain text and the chapter is TipTap `_text`, so that fallback reports a phantom diff on EVERY accept — the exact "every accept records a spurious edit" failure this question names.
3. `current_rev = await self._revisions.latest_revision_id(created_by=run.created_by, book_id=run.book_id, chapter_id=unit.chapter_id)` — the SAME `RevisionCapture`/`BookRevisionCapture` (authoring_run_service.py:222-259) the driver used at :1169 to produce `post_revision_id`. Same producer on both sides of the compare (the mirror-producer / cross-service-normalization rule). Exception ⇒ skip + log.
4. `current_rev == unit.post_revision_id` ⇒ **RECORD NOTHING** (H2 — accept-as-is; mirrors engine.py:1727 "`accept` is deliberately not an action here").
5. Else the chapter moved since the draft landed ⇒ fetch BOTH texts through ONE extractor:
   `before = await book.get_chapter_revision_text(run.book_id, unit.chapter_id, unit.post_revision_id)`
   `after  = await book.get_chapter_revision_text(run.book_id, unit.chapter_id, current_rev)`
   ADD `get_chapter_revision_text()` to services/composition-service/app/clients/book_client.py — mirror services/knowledge-service/app/clients/book_client.py:602 verbatim (internal-token GET `/internal/books/{b}/chapters/{c}/revisions/{r}/text` → `text_content`; composition's BookClient already carries `_internal_token`, see get_chapter_sort_orders at book_client.py:142). This route EXISTS (book-service server.go:3372) and returns TipTap-extracted plain text. It is unbuilt work in composition, NOT a blocker — write it.
   Either text `None` ⇒ skip, log `correction_skipped=revision_text_unavailable` (never record an `edit` whose magnitude cannot be confirmed).
6. `changed = count_changed_blocks(before, after)` — existing signature, UNCHANGED (generation_corrections.py:42).
7. `changed == 0` ⇒ **RECORD NOTHING**. A no-op autosave / whitespace-only PATCH still mints a revision (server.go:2496), so a divergent revision id alone is not proof of an edit. This is engine.py:1753's `EDIT_NO_CHANGE` guard re-expressed as a SKIP (the accept path is fire-and-forget; it must never 422 the accept). Revision-id divergence is the TRIGGER; `changed_blocks > 0` is the CONFIRMATION — both required.
8. `changed > 0` ⇒ resolve `job = await jobs.get(unit.job_id)` and re-scope it to the run's Work (drop it if `job.project_id` isn't the run's Work — worker-loaded-id-needs-parent-scoping), then `corrections.create(job.project_id, unit.job_id, created_by=run.created_by, kind="edit", changed_blocks=changed, guidance=None, raw_before=before, raw_after=after ONLY when works.get(project_id).settings["capture_correction_prose"] is true — mirror engine.py:1766)`.

DEFAULT THE PO MAY VETO: any writer's divergence counts. If a self-heal apply / agent `propose_edit` apply (not the human's keystrokes) changed the chapter between draft and accept, it still records `kind='edit'` — the signal being mined is "the author did not take the draft as-is", and the before/after prose is honest regardless of who typed it. Do NOT filter on `chapter_revisions.author_user_id`; that adds an attribution axis the flywheel does not use.

TESTS (services/composition-service/tests/unit/test_authoring_runs_service.py, stubbed RevisionCapture + BookClient + a spy corrections repo):
- accept, capture returns `post_revision_id` ⇒ `corrections.create` NEVER called (the H2 test — this is the one that stops the corrupted signal).
- accept, capture returns a NEW rev, texts "a\nb" vs "a\nB" ⇒ create called ONCE with `kind="edit"`, `changed_blocks=1`, `job_id=unit.job_id`.
- accept, NEW rev but IDENTICAL text (no-op autosave) ⇒ create NEVER called.
- `post_revision_id=None` ⇒ never called; `job_id=None` ⇒ never called.
- book client raises ⇒ unit is STILL accepted (route 200) and create never called.
- Wave DoD live smoke: draft 2 units; edit chapter A in the editor, leave B untouched; accept both ⇒ exactly ONE `generation_correction` row (`kind='edit'`, on A's job).

*Evidence:* services/composition-service/app/db/repositories/generation_corrections.py:42 (`count_changed_blocks(before: str, after: str) -> int`, difflib line-blocks, identical→0) · services/composition-service/app/routers/engine.py:1727 (`accept` deliberately not an action — H2) and :1748-1756 (`count_changed_blocks(winner_text, edited_text)`; changed_blocks==0 ⇒ 422 EDIT_NO_CHANGE) and :1766 (raw prose is opt-in per Work) · services/composition-service/app/services/authoring_run_service.py:896 (accept_unit — the insertion point), :222-259 (RevisionCapture / BookRevisionCapture.latest_revision_id), :1167-1191 (the driver writes post_revision_id from that same capture, best-effort ⇒ may be NULL) · services/book-service/internal/api/server.go:2496 (every PATCH /draft INSERTs a chapter_revisions row ⇒ a human editor save always mints a new latest revision) · services/book-service/internal/api/server.go:3364-3405 (`GET /internal/books/{b}/chapters/{c}/revisions/{r}/text` → `text_content`, TipTap-extracted plain text) · services/knowledge-service/app/clients/book_client.py:602 (the client wrapper to mirror into composition's book_client.py)

### BE-31-9c-DENOMINATOR-ALLOWLIST
BUILD IT AS SPEC'D — with ONE code-grounded amendment: the constant is FOUR ops, not three. Add `adapt_scene`.

**1 · The constant** — `services/composition-service/app/db/repositories/generation_corrections.py`, module level, right after `_DASHBOARD_MODES` (line 34):
```python
# BE-9c — the ONLY ops whose output the author can accept/edit/regenerate/reject
# (i.e. the only ops that can ever produce a generation_correction row). Every
# other op composition runs is mode='auto' machinery (plan_pipeline, plan_pass,
# plan_forge_propose/_refine, quality_report, promise_coverage, decompose_preview,
# self_heal_propose) or an uncaptured cowrite ghost ('continue' — useInlineGhost.ts:60
# captures NO correction), and must never enter the denominator.
CORRECTABLE_OPERATIONS: tuple[str, ...] = (
    "draft_scene", "draft_chapter", "stitch_chapter", "adapt_scene",
)
```
Never a literal at the call site; the router imports nothing new.

**2 · The query** — in `correction_stats` (generation_corrections.py:180-210): KEEP `AND NOT coalesce((j.input->>'selection_edit')::boolean, false)` (line 206) and ADD immediately after it `AND j.operation = ANY($2::text[])`, binding `list(CORRECTABLE_OPERATIONS)` as the 2nd param. Two predicates = defense in depth (F-Q3a: `operation` is an open `str` until BE-9c′ lands). `generation_job.operation` is `TEXT NOT NULL` (migrate.py:271) → no NULL branch needed. Nothing else in the method changes (shape, zero-fill, `_rate` all stay).

**3 · WHY the 4th op (the amendment).** The spec says "EXACTLY three", but `adapt_scene` is a live, FE-issued, fully-correctable draft op: `ComposeView.tsx:73` posts it on the SAME `/generate` route (cowrite ghost or auto K-cards, `diverge ? auto.mutate(p) : stream.start(p)`), and the SAME capture handlers fire on it — `correct()` at `ComposeView.tsx:107` (auto: regenerate/reject/pick_different/edit) and `cowriteCorrect()` at `:137` (regenerate/discard). With a 3-op allowlist the correction ROWS still get written, but their JOB rows are filtered out of the FROM side of the join → both numerator and denominator drop them, so a derivative Work drafted via Adapt-from-source renders the cold-start "no generations" panel for an author who drafted an entire branch, while learning-service (fed by the outbox event, unfiltered) has the corrections. That is the same bug class, inverted — and it is exactly what the spec's own root-cause argument demands ("fixed with a flag on one operation instead of an allowlist of the correctable ones"). **Default is: ship the 4. PO veto = delete the 4th tuple entry; nothing else changes.**

**4 · Tests** (add beside the existing ones in `services/composition-service/tests/integration/db/test_repositories.py:2012-2100`, same `xdist_group("pg")` file):
- `test_correction_stats_excludes_non_correctable_operations` — seed completed `plan_pass`, `quality_report`, `plan_pipeline` jobs (mode='auto', no corrections) + ONE completed `draft_scene` auto job with an `edit` correction → assert `auto.generations == 1` and `accept_rate == 0.0` (today it would be 0.75 — the "reassuring, false number").
- `test_correction_stats_selection_edit_and_allowlist_are_independent` — a completed `rewrite` cowrite job WITH `input.selection_edit=true` is excluded (existing test at :2052 stays green), AND a `rewrite` job WITHOUT the flag is ALSO excluded (proves the allowlist, not just the flag).
- `test_correction_stats_includes_adapt_scene` — completed `adapt_scene` cowrite job + a `reject` correction → `cowrite.generations == 1`, `reject_rate == 1.0`.
- `test_correction_stats_excludes_inline_continue` — completed `continue` cowrite job (no correction; useInlineGhost never captures one) → does NOT drag `cowrite.accept_rate`.

**5 · Sequencing.** Build FIRST, ALONE, before the `quality-corrections` panel, and ship it in the SAME milestone (M4) — the panel on the current query is a chart on a lie.

**6 · Carry-over for BE-9c′ (its sibling row, do not confuse the two sets).** When closing `GenerateBody.operation` (engine.py:98) and `GenerateChapterBody.operation` (engine.py:141) to a `Literal`, the Literal must enumerate ALL SEVEN registered ops in `cowrite._OPERATION_INSTRUCTIONS` (`continue, draft_scene, draft_chapter, expand, rewrite, describe, adapt_scene`) — NOT the 4 correctable ones — or the inline ghost (`useInlineGhost.ts:60` sends `continue`) and Adapt-from-source start 422-ing. Also close the MCP twin `_GenerateArgs.operation` (`mcp/server.py:1356`, today `str | None`), respecting the 3-schema-source FastMCP caveat.

**7 · Known residual — track, do NOT expand scope.** `useWhatIfTakes.ts:36` generates ephemeral takes as `operation:'draft_scene'`, mode auto, and deliberately captures NO correction — those jobs still inflate the auto denominator, and `operation` alone cannot distinguish them. This is the pre-existing H2 conflation the repo already documents ("accepted as-is (or abandoned — conflated)", generation_corrections.py:227). Open a defer row rather than widening BE-9c: **D-QUAL-WHATIF-DENOMINATOR · origin M4/BE-9c · what-if takes post `draft_scene` and never capture a correction, so they enter the auto denominator as false accepts · gate 2 (large/structural — needs an `input.ephemeral=true` flag written by the FE + a 3rd predicate, i.e. an FE+BE contract change) · target: the wave that touches the what-if/scene-graph surface.**

*Evidence:* services/composition-service/app/db/repositories/generation_corrections.py:180-210 (the query: groups by `j.mode` over every job, ONE exclusion at :206) · migrate.py:271 (`operation TEXT NOT NULL`) · inflating auto-mode job creators: routers/plan.py:246 self_heal_propose, :312 quality_report, :417 promise_coverage, :548 plan_pipeline, :612 decompose_preview; services/plan_forge_service.py:236/525/1170/1359 plan_forge_propose/_refine/plan_pass/plan_pipeline · correctable job creators: engine.py:1048/1079 (body.operation, chapter), engine.py:1278/1306 (stitch_chapter, mode='auto'), engine.py:484 (scene generate) · the 4th op: frontend/src/features/composition/components/ComposeView.tsx:73 (`operation: 'adapt_scene'` on the same /generate path) with corrections captured at ComposeView.tsx:107 and :137 · the op that must stay OUT: frontend/src/features/composition/hooks/useInlineGhost.ts:60 (`operation: 'continue'`, no correction.mutate anywhere in the hook) · existing tests to extend: services/composition-service/tests/integration/db/test_repositories.py:2012-2100

### QC-31-8-POLISHPROPOSALS-QUERYCACHE
BUILD IT AS SPEC'D — with 3 mandatory corrections the code forces. QC-8's design is sound and confirmed by the code (QualityReportSection ALREADY takes `proposals?: SelfHealProposal[]` and defaults to `[]` — QualityReportSection.tsx:20,39; the badge logic exists at :90; the only missing link is that QualityCriticPanel.tsx:80 never passes the prop). Do NOT redesign. Exact instructions:

(1) SHARED KEY FACTORY — no free-string keys on two sides (drift = silent miss). In `frontend/src/features/composition/hooks/usePolishProposals.ts` export:
    `export const selfHealKey = (projectId: string | null, chapterId: string | null) => ['composition','self-heal', projectId, chapterId] as const;`
    Both `usePolishProposals` and `QualityCriticPanel` import THIS. (One name, one concept.)

(2) REWRITE `usePolishProposals` — storage only, return shape byte-identical:
  - Cache VALUE = the whole run result, INCLUDING acceptance:
    `type SelfHealCache = { proposals: SelfHealProposal[]; sourceText: string; draftVersion: number | null; stats: SelfHealProposalResponse['stats']; acceptedIds: string[] }`
    (acceptedIds goes in the cache too — otherwise a dock-panel remount restores `proposals` + `ran:true` but resets acceptance to empty ⇒ `healedText === sourceText` ⇒ Apply burns an OCC draft bump writing back unchanged prose. Half-cached state is a bug, not a smaller diff.)
  - Reader: `const q = useQuery({ queryKey: selfHealKey(projectId, chapterId), enabled: false, staleTime: Infinity, gcTime: Infinity })`. If TS complains about the missing `queryFn`, pass `queryFn: skipToken` (imported from `@tanstack/react-query`) — never a real fetcher; this cache is write-only-by-mutation.
  - **`gcTime: Infinity` is NOT optional** — App.tsx:10 sets a global `gcTime: 5 * 60 * 1000`. If the user runs Polish in `quality-heal` and opens `quality-critic` >5 min later (no observer in between), the entry is garbage-collected and the badge silently never appears. `staleTime: Infinity` does not prevent GC. Set `gcTime: Infinity` on BOTH useQuery calls.
  - Writer: `const run = useMutation({ mutationFn: () => compositionApi.proposeSelfHeal(projectId!, {chapterId: chapterId!, modelRef, rerank}, token!), onSuccess: (r) => qc.setQueryData(selfHealKey(projectId, chapterId), { proposals: r.proposals ?? [], sourceText: r.source_text ?? '', draftVersion: r.draft_version ?? null, stats: r.stats, acceptedIds: (r.proposals ?? []).filter(p => p.recommended ?? p.tier === 'deterministic').map(p => p.id) }) })`. Keep the `if (!projectId || !chapterId || !token || !modelRef) return;` guard in the exposed `run` wrapper.
  - `toggle` / `bulk` become `qc.setQueryData(key, prev => prev && {...prev, acceptedIds: <next array>})` (no-op when `prev` is undefined). Preserve the tier-scoped `bulk(on, tier?)` signature exactly (usePolishProposals.ts:74-87).
  - Derived, unchanged for callers: `proposals = q.data?.proposals ?? []`, `sourceText = q.data?.sourceText ?? ''`, `draftVersion = q.data?.draftVersion ?? null`, `stats = q.data?.stats`, `acceptedIds = useMemo(() => new Set(q.data?.acceptedIds ?? []), [q.data])` (still a `Set<string>` — PolishPanel calls `.has()`), `ran = !!q.data`, `loading = mut.isPending`, `error = mut.error ? (mut.error as Error).message || 'Polish failed' : null`, `healedText = useMemo(() => applySelfHealEdits(sourceText, proposals, acceptedIds), …)` (identical to :89). `rerank`/`setRerank` STAY `useState` — a per-panel input toggle, not shared run output.

(3) READER SIDE — in `QualityCriticPanel.tsx`: add
    `const healQ = useQuery({ queryKey: selfHealKey(work.projectId, chapterId), enabled: false, staleTime: Infinity, gcTime: Infinity });`
    …but note `work` is only narrowed to `ready` AFTER the early return at :39 — so either hoist the key off `work.kind === 'ready' ? work.projectId : null`, or (cleaner, and it keeps hook order legal) extract the ready-branch body into an inner `<QualityCriticReady projectId=… />` component. Then `<QualityReportSection … proposals={healQ.data?.proposals ?? []} />` at :80. Cache miss ⇒ `[]` ⇒ no badge, per spec.
    HARD CONSTRAINT: `quality-heal` MUST derive its projectId from `useQualityWork(host.bookId)` (useQualityWork.ts:34) — the SAME gate `quality-critic` uses (QualityCriticPanel.tsx:29). Any other projectId source (e.g. reading `work.candidates[1]`, or a hoist field) makes the two keys disagree and the badge never fires. And copy the chapter picker verbatim per QC-10, so both panels' `chapterId` are the same book-service `chapter_id` string.

(4) TESTS (these are the DoD, not extras):
  - **`PolishPanel.test.tsx` renders BARE today (`render(<PolishPanel …/>)` at :32 and :45 — no provider).** The instant the hook touches `useQuery`/`useMutation` those tests throw "No QueryClient set". Wrap both renders in `<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}>` (the pattern already used in CompositionPanel.test.tsx:87). The spec's "legacy PolishPanel still passes its own tests" gate depends on this edit — it is part of the slice, not a surprise.
  - New cross-panel test: render `quality-heal` + `quality-critic` under ONE `QueryClientProvider`, run Polish on chapter C, assert `violation-has-fix` appears in `studio-quality-critic-panel` for chapter C and does NOT appear when the critic's picker is on chapter D (the key-miss ⇒ `[]` path).
  - A hook test asserting the return shape is unchanged (keys + `acceptedIds instanceof Set`).

Default I am picking that the PO may veto: acceptedIds lives in the cache value (not local state). Rationale above — it costs 3 lines and removes a paid-no-op-apply footgun.

*Evidence:* frontend/src/App.tsx:10 (`gcTime: 5 * 60 * 1000` — global default; staleTime:Infinity does NOT stop eviction, so the spec's `staleTime: Infinity` alone silently loses the proposals after 5 min with no observer) · frontend/src/features/composition/components/QualityReportSection.tsx:20,39,90 (`proposals?: SelfHealProposal[] = []` + `_hasProposedFix` + the `violation-has-fix` badge ALREADY exist — nothing to build there) · frontend/src/features/studio/panels/QualityCriticPanel.tsx:80 (renders `<QualityReportSection projectId chapterId token modelRef />` — the `proposals` prop is simply not passed; that one prop is the whole link) · frontend/src/features/studio/panels/QualityCriticPanel.tsx:29 + useQualityWork.ts:34-52 (projectId source that `quality-heal` must match) · frontend/src/features/composition/hooks/usePolishProposals.ts:22-32,74-87,89-109 (the 8 useStates + bulk/toggle/healedText + the return shape to preserve) · frontend/src/features/composition/components/__tests__/PolishPanel.test.tsx:32,45 (renders with NO QueryClientProvider — will throw once the hook moves to react-query; must be wrapped, pattern at CompositionPanel.test.tsx:87)

### QC-31-4-APPLYHEALEDDOCUMENT
BUILD IT AS SPECCED — the spec's QC-4 shape is correct and buildable today; the code adds ONE hard constraint the spec does not state, and the builder must not miss it.

**THE TRAP (read first): `TiptapEditorHandle.setContent` CANNOT be the write.** `setContentHandler` sets `isExternalUpdate.current = true` around `editor.commands.setContent(...)` (TiptapEditor.tsx:251-256), and `onUpdate` early-returns on that flag (TiptapEditor.tsx:248-250). So a heal applied via `setContent` NEVER reaches the hoist's `setBody` → the doc never goes dirty → the QC-4 `{kind:'applied'}` contract ("the doc becomes dirty, the user saves ⌘S") silently fails and the heal is lost on the next external content push. The heal must flow through a real editor transaction, exactly like `insertAtCursor`/`replaceSelection` do (TiptapEditor.tsx:290-305; see the comment at :282-284 "through editor.chain() (NOT setContent), so onUpdate fires and the doc dirties/autosaves exactly like typing").

**Slice 1 — new handle method (frontend/src/components/editor/TiptapEditor.tsx).**
Add to `TiptapEditorHandle` (after `replaceSelection`, :68): `replaceDocument: (text: string, provenance?: ProvenanceAttrs) => boolean;` — doc-comment it as "whole-document replace for AI self-heal; flows through editor.chain() (NOT setContent) so onUpdate fires and the doc dirties; one chained transaction = one undo".
Impl in the `useImperativeHandle` block (alongside :290-305):
```ts
replaceDocument: (text: string, provenance?: ProvenanceAttrs) => {
  if (!editor || !text) return false;
  editor.chain().focus().selectAll().insertContent(text).run();
  if (provenance) applyProvenanceOver(editor, 0, editor.state.doc.content.size, provenance);
  return true;
},
```
(`applyProvenanceOver` is already imported at :30.)

**Slice 2 — the hoist verb (frontend/src/features/studio/manuscript/unit/ManuscriptUnitProvider.tsx).**
Export the discriminated result type and add the verb to `ManuscriptUnitApi` right below `applyProposedEdit` (interface :93-99; impl :303-320; deps list :332-339 — add it to BOTH the object and the useMemo dep array or it goes stale on every keystroke):
```ts
export type ApplyHealedResult =
  | { kind: 'applied' }
  | { kind: 'no-editor' }
  | { kind: 'stale'; reason: 'chapter' | 'version' | 'dirty' };

applyHealedDocument: (params: {
  text: string; chapterId: string; expectedDraftVersion?: number | null;
  provenance?: ProvenanceAttrs;
}) => ApplyHealedResult;
```
Guard order is EXACTLY the spec's 5-row table (31_quality_completion.md §"The write — and the guard that makes it safe", lines 490-496) and is evaluated against `stateRef.current`, not the closed-over `state`:
1. `s.chapterId !== params.chapterId` → `{kind:'stale', reason:'chapter'}`
2. `params.expectedDraftVersion != null && s.version !== params.expectedDraftVersion` → `{kind:'stale', reason:'version'}`
3. `isDirtyState(s)` → `{kind:'stale', reason:'dirty'}`
4. `editorRef.current == null` → `{kind:'no-editor'}`
5. else `handle.replaceDocument(text, provenance ?? {AI provenance, same shape ProposeEditCard passes})` → `true ⇒ {kind:'applied'}`; a `false` return from the handle also maps to `{kind:'no-editor'}` (never a bare boolean escapes the hoist).
NEVER expose a raw `editorRef`/`setBody` path to `quality-heal` — this verb is the chokepoint the doc-comment at :86-92 demands.

**Slice 3 — checkpoint the replace (it is the single most destructive AI write in the app).** Extend `useManuscriptCheckpoints.ts`: widen `ManuscriptCheckpoint.kind` to `'insert' | 'replace' | 'heal'` (:40) and add an `applyHealedDocument` wrapper mirroring the existing `applyProposedEdit` wrapper (capture the pre-revision restore point, then delegate; only capture when the result is `{kind:'applied'}`). Carry it to the sibling dock panel the SAME way `applyProposedEdit` already reaches ProposeEditCard: add an optional `applyHealedDocument` to `EditorTarget` in `frontend/src/features/chat/context/editorBridge.ts` (:32, :39, :60) and register the checkpoint-wrapped fn in `EditorPanel.tsx:97-102`. `QualityHealPanel` reads `useManuscriptUnit()` for the precondition state (chapterId / version / isDirty → disable Apply + render the copy) and applies via `getEditorTarget()?.applyHealedDocument ?? unit.applyHealedDocument` — the exact preference pattern ProposeEditCard.tsx:177 already uses.

**Slice 4 — wire the panel.** `PolishPanel.onApply(healedText: string)` (PolishPanel.tsx:16,137) is reused as-is; `QualityHealPanel` passes `onApply={(text) => apply({ text, chapterId: p.chapterId, expectedDraftVersion: p.draftVersion })}` — `draftVersion` is already captured and returned by `usePolishProposals` (:24, :97) and has never been read (F-Q6). Render the exact user-facing copy from the spec's 5-row table for each of `stale:chapter` / `stale:version` / `stale:dirty` / `no-editor`, and DISABLE Apply in those states (no silent no-op, no silent clobber).

**Tests (DoD):** (a) `TiptapEditor` test: `replaceDocument` fires `onUpdate` (assert the onUpdate spy is called — this is the regression test for the setContent trap); (b) 5 `ManuscriptUnitProvider` tests, one per precondition row, asserting the discriminated `kind`/`reason`; (c) a `QualityHealPanel` test per stale reason asserting the copy renders AND Apply is disabled; (d) checkpoint test: a successful heal pushes a `kind:'heal'` checkpoint. Nothing new is needed backend-side — this is a pure FE seam.

*Evidence:* frontend/src/components/editor/TiptapEditor.tsx:248-256 (`onUpdate` early-returns on `isExternalUpdate`; `setContentHandler` sets it ⇒ setContent CANNOT dirty the doc) · TiptapEditor.tsx:290-305 (`insertAtCursor`/`replaceSelection` = the transaction pattern to mirror; `applyProvenanceOver` imported :30) · frontend/src/features/studio/manuscript/unit/ManuscriptUnitProvider.tsx:86-99 (the "ONE chokepoint for 'an AI wrote into this chapter'" doc-comment + the only AI write verb), :303-320 (`applyProposedEdit` impl to mirror), :332-339 (api useMemo + deps) · frontend/src/features/chat/context/editorBridge.ts:32,39,60 (optional hoist-action carrier precedent) · frontend/src/features/studio/panels/EditorPanel.tsx:97-102 (registers the CHECKPOINT-WRAPPED verb) · frontend/src/features/chat/components/ProposeEditCard.tsx:177 (`target.applyProposedEdit ?? raw handle` preference pattern) · frontend/src/features/composition/hooks/usePolishProposals.ts:24,97 (`draftVersion` captured, never read) · frontend/src/features/composition/components/PolishPanel.tsx:16,137 (`onApply(healedText)`) · docs/specs/2026-07-01-writing-studio/31_quality_completion.md:488-496 (QC-4's 5-row precondition table + exact copy)

### Q-31-JOBID-BACKFILL-TEMPTATION
CONFIRM the spec's answer — never backfill — but ship it as THREE mechanical artifacts, not one comment. A comment is self-report; this repo's own rule is "an item is DONE only when a test asserts its effect."

(1) DDL + comment — `services/composition-service/app/db/migrate.py`, immediately after line 1519 (`ALTER TABLE authoring_run_units ADD COLUMN IF NOT EXISTS critic_verdict JSONB;`), mirroring that D5 additive-column block exactly:
```sql
-- D-31 M4 (BE-9a): the generation_job that drafted this unit — the correction
-- flywheel's anchor (generation_correction.job_id is UUID NOT NULL, so a unit
-- with NULL here records NO correction, and the Run Report says so).
-- NULLABLE BY DESIGN. NULL = drafted before D-31 M4, or the seam returned no
-- job id. NEVER BACKFILL A GUESS — inferring a unit's job from its timestamp
-- attributes the author's rejection to someone else's generation and poisons
-- the very learning signal this column exists to feed.
ALTER TABLE authoring_run_units ADD COLUMN IF NOT EXISTS job_id UUID;
```
No FK to `generation_job` (matches BE-9a as specced; a guessed id would be a real job id anyway, so an FK buys nothing here and adds ON DELETE coupling). Use a `--` block, NOT `COMMENT ON COLUMN` — `COMMENT ON` has zero precedent under `services/`, and duplicating the same prose in two places is a drift hazard. (Default; PO may veto if they want the comment visible in `\d+`.)

(2) The report STATES the gap — in `unit_report` (`authoring_run_service.py:878-893`) add `"job_id": str(u.job_id) if u and u.job_id else None` to the row dict, alongside the identical `critic_verdict` None-means-absent precedent, and surface it in the report row schema. A unit with no job is VISIBLE, not silently zero.

(3) The guard test (this is what makes it real) — add to composition-service's migration tests:
  - `test_no_job_id_backfill_in_migrations`: read `migrate.py` and assert **zero** regex matches for `UPDATE\s+authoring_run_units\s+SET[^;]*job_id` (case-insensitive). A future agent's "helpful" backfill then cannot land silently — it reds the suite.
  - `test_job_id_ddl_carries_never_backfill_warning`: assert the literal string `NEVER BACKFILL A GUESS` appears within the `job_id` ALTER block, so a comment-stripping edit reds too.
  - `test_reject_unit_with_null_job_id_records_no_correction`: a `drafted` unit with `job_id IS NULL` → `reject_unit` writes NO `generation_correction` row, emits NO `GENERATION_CORRECTED` event, and the report row shows `job_id: None`. This is BE-9b's "skip + report, never fabricate" asserted as behavior.

Builder rule, one line: `job_id` is nullable, written ONLY by the driver from `DraftOutcome.job_id` at `mark_drafted`, and is NEVER derived, inferred, or backfilled from any other column.

*Evidence:* services/composition-service/app/db/migrate.py:1493-1519 (authoring_run_units DDL + the D5 `critic_verdict` additive-column block whose `--`-comment shape BE-9a's job_id must copy; `COMMENT ON` = 0 hits repo-wide under services/) · services/composition-service/app/services/authoring_run_service.py:858-894 (unit_report row dict — where "no job" must be stated, next to critic_verdict's identical None-means-absent precedent) · services/composition-service/app/services/authoring_run_service.py:197-203 (DraftOutcome has no job_id today — BE-9a is real unbuilt work)

### Q-31-SIZE-SUPERSEDES-PLAN30
SIZE THE WAVE AS **L**. The spec wins over plan-30; do not re-derive the M estimate. Concretely:

1) **Gate command (exact):** `python scripts/workflow-gate.py size L <files> 9 5 <context_pct>` — where `<files>` is the REAL file count (≥10; realistically ~20+ for 4 panels + catalog + i18n + repos + routes + migrate). Pass `L` **deliberately**.

2) ⚠ **The gate will NOT enforce L — the spec's stated reason is wrong.** Spec line 4 says "side_effects = 5 ⇒ **risk floor L**". FALSE: `_expected_size` (scripts/workflow-gate.py:357-363) caps the risk floor at **M** (`side_effects >= 2 → floor = 2`); there is no L floor at any side-effect count, and undersizing ABOVE the floor is advisory only (`fail()` fires only `if chosen_idx < floor`, line 384). So `size M 20 9 5` would be silently ACCEPTED. **L is correct, but it comes from the LOGIC axis** (`logic ≈ 9` → `logic <= 12` → base = L, line 349), not from the side-effect floor. Builder: type `L`; the gate will not catch you if you type `M`.

3) **Keep `<files>` ≥ 10.** The breadth bump (`if files >= 6 and logic >= files: base += 1`, line 355) would escalate to **XL** if you pass files in 6..9 with logic=9. With the real count (~20) no bump fires and expected == L exactly, so the gate prints a clean OK with no advisory.

4) **The supersession is CORRECT and grounded in code, not taste** — I verified F-Q2 at HEAD: `generation_correction.job_id` is `UUID NOT NULL REFERENCES generation_job(id)` (migrate.py:368); `authoring_run_units` has **no `job_id` column** (migrate.py:1493-1512); `DraftOutcome` is `{ok, cost_usd, error}` (authoring_run_service.py:195-202) and `EngineDraftingSeam.draft_chapter` reads `payload["job_id"]` for cost then **discards it** (authoring_run_service.py:389). Plan-30 BE-9's "No schema change" cannot be built. BE-9a's `ALTER TABLE authoring_run_units ADD COLUMN job_id UUID` is real, and BE-P2's `composition_progress_goal` table is real. Two schema changes, five side effects — as the spec states.

5) **FIX-NOW (one-line doc edit, cheaper than a defer row):** correct spec line 4 of `31_quality_completion.md` — replace "side_effects = **5** … ⇒ **risk floor L**" with "side_effects = **5** ⇒ risk floor **M**; **L is set by the logic axis** (logic ≈ 9). NOTE: the gate will accept M — pass L deliberately." Leaving the false claim in place is how a later agent 'corrects' the size back down to M and passes the gate.

6) **At PLAN, reconcile plan-30's rows** (do not silently diverge): mark plan-30's BE-9 row "No schema change" as **SUPERSEDED by 31 F-Q2/BE-9a" and its `propose_edit` capture leg as **SUPERSEDED by 31 F-Q4 → OQ-1 (deferred, gate #2 large/structural)**. Nothing here contradicts §0 PO-1..4 — those sealed decisions say nothing about this wave's size; PO-4 only sequences specs before build.

*Evidence:* services/composition-service/app/db/migrate.py:368 (`job_id UUID NOT NULL REFERENCES generation_job(id) ON DELETE CASCADE`) · migrate.py:1493-1512 (`authoring_run_units` — no job_id column) · services/composition-service/app/services/authoring_run_service.py:195-202 (`DraftOutcome{ok,cost_usd,error}`) and :389 (`return DraftOutcome(ok=True, cost_usd=cost)` — job_id read then discarded) · scripts/workflow-gate.py:349 (logic<=12 → base L), :357-363 (risk floor caps at M — `floor = max(floor, 2)`), :384 (`if chosen_idx < floor: fail()` — undersizing above the floor is advisory) · docs/specs/2026-07-01-writing-studio/31_quality_completion.md:4 (the "risk floor L" claim being corrected)

### Q-31-FIREFORGET-VS-SAME-TX
NO CONTRADICTION — the two clauses name two different transactions, and the code already forces the topology. Build it exactly this way:

**TOPOLOGY (locked): TXN-1 = the FSM transition (autocommit UPDATE). TXN-2 = the correction INSERT + its outbox row, atomic with each other, opened AFTER TXN-1 has committed. A TXN-2 failure NEVER touches TXN-1.**

1. **Do NOT thread a `conn` into the correction write, and do NOT wrap accept/reject in a transaction.** `GenerationCorrectionsRepo.create` self-acquires a pool connection and opens its own `conn.transaction()`, emitting the outbox row inside it (generation_corrections.py:88-89 + :137). Leave that signature alone — it takes no `conn=` param and must not gain one. `AuthoringRunsRepo.transition_unit` is a bare autocommit UPDATE on its own pooled connection (authoring_runs.py:427-429); `reject_unit` additionally makes a cross-service HTTP `restore` call to book-service mid-sequence (authoring_run_service.py:919-949). There is no ambient transaction to join, and opening one across that HTTP call would be a defect. M4's DoD phrase "the outbox emits GENERATION_CORRECTED **in the same transaction**" means **the same transaction as the correction row INSERT** — which is already true and already enforced. It does NOT mean the accept/reject transaction.

2. **The outbox law is NOT violated by fire-and-forget.** The law (`transactional-outbox-must-not-swallow-and-fake-tx-must-rollback`) forbids swallowing the emit failure *inside* the transaction (`try: emit(); except: pass`) — that would commit a domain row with no event. Here, if `outbox.emit` raises, `conn.transaction()` rolls back and the `generation_correction` row vanishes with it: no capture without an event, no event without a capture. The caller then catches the exception of the whole already-rolled-back atomic unit. That is catching a *failed unit*, not swallowing an *emit*. Both invariants hold simultaneously.

3. **WHERE the write goes (one chokepoint, covers REST + MCP):** inside `AuthoringRunService.accept_unit` (authoring_run_service.py:896) and `reject_unit` (:919), on the SUCCESS path AFTER `transition_unit` returns a non-None unit (and, for reject, after `restore` succeeded). Both the REST routes (routers/authoring_runs.py:352, :382) and the MCP tools (mcp/server.py:1919, :1970) go through the service — write it once there, never in the routers. Thread `actor_user_id: UUID` into both service methods (routers pass `Depends(get_current_user)`; MCP passes its auth context) — `create` needs it for `created_by`.

4. **The exact guard — copy this shape:**
```python
# after the guarded transition has committed (TXN-1 is DONE):
correction_id: UUID | None = None
capture_status = "skipped_no_job_id"      # or "captured" | "failed"
if unit.job_id is not None:               # M4's new authoring_run_units.job_id column
    try:
        corr = await self._corrections.create(   # opens TXN-2 itself
            run.project_id, unit.job_id, created_by=actor_user_id,
            kind=kind, changed_blocks=..., raw_before=..., raw_after=...,
        )
        correction_id, capture_status = corr.id, "captured"
    except Exception:                      # noqa: BLE001 — telemetry, never blocks the review
        logger.warning(
            "correction capture failed run=%s unit=%s job=%s — review stands",
            run_id, unit_index, unit.job_id, exc_info=True,
        )
        capture_status = "failed"
```
`except Exception` (broad, deliberate) — a `ReferenceViolationError`, a dead pool, an outbox-table failure, all identical here: log + continue. NEVER re-raise. NEVER `raise` out of accept/reject because of a correction.

5. **NO SILENT SUCCESS (repo law `silent-success-is-a-bug`):** the accept/reject response MUST surface the capture outcome, not hide it. Add to the serialized accept/reject payload (routers/authoring_runs.py `_serialize_unit` call-sites, and the MCP tool result): `"correction": {"status": "captured"|"skipped_no_job_id"|"failed", "correction_id": <uuid|null>}`. This is what BE-9b's "`job_id IS NULL` ⇒ skip + **report**, never fabricate" requires. The FE `quality-corrections`/review UI shows nothing on `captured`, and a quiet "not recorded" note on `failed`/`skipped_no_job_id` — the review itself still succeeded (200).

6. **H2 stays:** `reject_unit` → always `kind='reject'`. `accept_unit` → records `kind='edit'` ONLY when the unit was edited before accept (pass the edit through; `changed_blocks == 0` ⇒ capture NOTHING, mirroring routers/engine.py:1750-1756's `EDIT_NO_CHANGE` 422 — but at this seam it is a silent skip with `status="skipped_no_change"`, not a 422, because it must not fail the accept). Accept-as-is records nothing at all.

7. **THREE tests, all mandatory at M4:**
   - (a) *fire-and-forget proven*: patch `corrections.create` to raise → call `accept_unit` → assert the unit row in the DB is `accepted` (read it back, do NOT trust the return value) AND the response carries `correction.status == "failed"`. This is the test that proves the review did not roll back.
   - (b) *outbox law proven* (integration, real PG): patch `outbox.emit` to raise inside `create` → assert `SELECT count(*) FROM generation_correction WHERE job_id=$1` is **0** (the INSERT rolled back with it) and `outbox_events` has no row. No half-state.
   - (c) *happy path atomicity*: one accept → exactly ONE `generation_correction` row AND exactly ONE `outbox_events` row with `event_type='composition.generation_corrected'`, in the same commit.

**Default the PO can veto:** the capture outcome is reported in the response (item 5) rather than being wholly invisible. If the PO would rather keep the accept/reject response shape frozen, drop the `correction` key and keep only the log line — but then a persistently-failing flywheel is undetectable from the product, which is the exact bug class this repo just shipped. Recommend keeping it.

*Evidence:* services/composition-service/app/db/repositories/generation_corrections.py:88-89 (`async with self._pool.acquire() as conn:` / `async with conn.transaction():`) + :137 (`await outbox.emit(conn, …)`) — `create()` self-acquires and opens its OWN transaction; it has no `conn=` param, so the correction+event are atomic with each other and CANNOT be enrolled in a caller's transaction. services/composition-service/app/db/repositories/outbox.py:33-48 — `emit` is "Intentionally NOT best-effort and NOT self-acquiring" (the outbox law, already satisfied inside create()). services/composition-service/app/db/repositories/authoring_runs.py:427-429 — `transition_unit` runs its guarded UPDATE as a bare autocommit statement on its own pooled connection: there IS no accept/reject transaction. services/composition-service/app/services/authoring_run_service.py:896 (`accept_unit`) and :919-949 (`reject_unit` — makes a cross-service HTTP `restore` call to book-service between reads and the transition, so a wrapping DB txn is impossible by design). Callers converge on the service: services/composition-service/app/routers/authoring_runs.py:352, :382 and services/composition-service/app/mcp/server.py:1919, :1970. Precedent for the create()-raises→HTTP-error mapping (the legacy dedicated route, which is NOT fire-and-forget because there the correction IS the request): services/composition-service/app/routers/engine.py:1774-1789.

### Q-31-F-Q7-TENANCY-DEFECT
CONFIRMED DEFECT — build BE-P2 exactly as spec 31 line 528 states. The concern is real and reproducible from code, not a preference debate; CLAUDE.md User Boundaries settles it (a user-editable shared row must become a per-user tier). No escalation, no defer.

BUILDER INSTRUCTION (M2 / progress, wave that owns BE-P2):

1. SCHEMA — services/composition-service/app/db/migrate.py, immediately after the composition_progress_baseline block (ends :503):
   CREATE TABLE IF NOT EXISTS composition_progress_goal (
     user_id UUID NOT NULL, project_id UUID NOT NULL,
     daily_goal INT NOT NULL CHECK (daily_goal > 0),
     updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
     PRIMARY KEY (user_id, project_id));
   NO book_id column — neither sibling (composition_daily_progress :475, composition_progress_baseline :496) has one; the book grant is gated at the router BEFORE the repo, and the row is never read by book_id. Adding one is a column written and never read.

2. REPO — app/db/repositories/daily_progress.py (DailyProgressRepo, same file as its siblings): add `set_goal(user_id, project_id, goal)` (goal>0 → INSERT … ON CONFLICT (user_id, project_id) DO UPDATE SET daily_goal=EXCLUDED.daily_goal, updated_at=now(); goal==0 → DELETE) and `get_goal(user_id, project_id) -> int | None`. user_id is the first arg and is filtered on, matching the file's stated M5 isolation rule.

3. WRITE ROUTE — app/routers/progress.py: PUT /v1/composition/works/{project_id}/progress/goal, body {goal: int = Field(ge=0)} (0 clears), 422 on goal<0. Reuse the EXISTING chokepoint in this file — `work = await works.get(project_id)`; 404 if None; `await _gate_book(grant, work.book_id, user_id, GrantLevel.VIEW)` — then write the CALLER'S row. (Spec 31 calls this `_require_work`; the real helper in this file is `_gate_book` at progress.py:38 — use it, do not invent a new name.) VIEW, not EDIT: the goal is the caller's own stat, exactly like report/baseline. Returns {goal, source}.

4. READ-THROUGH — progress.py get_progress (currently line 124 `"daily_goal": _coerce_goal(work.settings or {})`): resolve per-user FIRST, fall back to legacy. daily_goal = await progress.get_goal(user_id, project_id); if None → _coerce_goal(work.settings or {}). Add `daily_goal_source: 'user' | 'work_legacy' | 'none'` to the response (SET-1: expose effective value + source tier). Keep _coerce_goal — it is the legacy reader and still guards the untyped blob.
   ⚠ THE WRITER ONLY EVER WRITES THE NEW TABLE. work.settings.daily_goal becomes read-only legacy; never write it again. Do NOT dual-write "for compatibility" — that keeps the shared row live and the defect survives the fix.

5. FRONTEND — delete the patchWork goal path. frontend/src/features/composition/hooks/useProgress.ts:67-85 (useSetDailyGoal): replace the compositionApi.patchWork(projectId, {settings: {...currentSettings, daily_goal}}) call with a new compositionApi.setDailyGoal(projectId, {goal}, token) hitting PUT …/progress/goal; drop `currentSettings` from the mutation variables; keep the invalidation of ['composition','progress']. Then ProgressPanel.tsx: `settings` becomes unused (only use is line 43 `currentSettings: settings`) → remove it from Props (:11), the signature (:25), and its sole call site CompositionPanel.tsx:847. Add daily_goal_source to the ProgressData type (types.ts:275-281).

6. TESTS — DoD demands REAL SQL; a mock would encode the bug. Add to services/composition-service/tests/integration/db/test_repositories.py (the file already exercises DailyProgressRepo against a live pool, :2193+; register composition_progress_goal in its truncate list at :46): a two-user test on ONE project — user A set_goal(2000), user B get_goal → None (NOT 2000), user B set_goal(500), user A get_goal → still 2000. Plus a router test that A's goal never appears in B's GET /progress and that daily_goal_source flips 'work_legacy' → 'user' once the per-user row exists, and goal=0 clears to source 'none'. Update tests/unit/test_progress_router.py:145-156 (asserts daily_goal==400 from work.settings) to assert the per-user row WINS over the legacy blob.

7. /review-impl at wave close (DoD #6), specifically checking that no code path still WRITES work.settings.daily_goal.

*Evidence:* services/composition-service/app/routers/progress.py:124 — `"daily_goal": _coerce_goal(work.settings or {})` reads the goal from the SHARED per-book row, while services/composition-service/app/db/repositories/daily_progress.py keys every progress row `PRIMARY KEY (user_id, project_id, chapter_id, snapshot_date)` (per-user). The shared row is user-writable: services/composition-service/app/db/migrate.py:35-45 defines `composition_work (project_id PK, book_id, settings JSONB)` with NO user scope key, and services/composition-service/app/routers/works.py `patch_work` gates only `GrantLevel.EDIT` on the book before replacing `settings` wholesale — so every EDIT grantee writes one goal for everyone. FE writer: frontend/src/features/composition/hooks/useProgress.ts:79 `patchWork(v.projectId, { settings: { ...v.currentSettings, daily_goal: ... } })`. Fix already sealed as MUST-BUILD: docs/specs/2026-07-01-writing-studio/31_quality_completion.md:528 (BE-P2) + QC-6 at :306.

### Q-31-OCC-CHIP-SERIALIZATION
DO NOT build instant-commit chips; DO build the 412 conflict banner. Two concrete instructions for M1:

(1) NO CHIPS — kill the race by construction, do not chain. `scope` and `active` stay exactly where they are: fields inside the submit-gated `CanonRuleForm` (`CanonRuleForm.tsx:37,41` useState → `:48-59` one full payload → one PATCH per Save). This is the memory lesson's own sanctioned cheap mitigation ("buffer them on blur like the text fields"), and the code already satisfies the spec's second clause — `CanonRuleForm.tsx:46` (`canSubmit = !!text.trim() && !windowInverted && !pending`) fed by `pending={patch.isPending}` (`CanonRulesPanel.tsx:58`) disables Save while its own write is in flight, and `CanonRulesPanel.tsx:18` keeps a single `editingId` so only ONE form (⇒ one in-flight PATCH) exists at a time. Panel A's ASCII already draws `scope` as a read-only badge and inactive as an `(inactive)` label — no chip. **Builder action: DELETE the ⚠ "the active toggle and the scope select are chips … writes chain (mutateAsync serialized per rule id)" clause from spec 31 §Panel A (line ~349-352) and from §OCC (line ~630).** It mandates a mitigation for a control the spec does not build; leaving it in makes the builder invent chips (scope creep) or hunt for phantom code. If a future slice DOES add an instant-commit chip over a canon rule, the mandated pattern is the existing one at `useSceneInspector.ts:46,99-100` (`chainRef.current = chainRef.current.then(run, run)` + a `nodeRef` mirror read for the FRESH version) — cite it, do not reinvent it. Note for PO veto: the default I picked is "no chips in v1"; if you want a one-click active toggle on the row, it is a separate slice that must copy useSceneInspector's chain.

(2) THE 412 HANDLER IS THE REAL FIX (this part of the spec stands, unchanged). Replace the bare `onError = (e) => toast.error((e as Error).message)` at `CanonRulesPanel.tsx:20`:
 - The thrown error already carries what's needed — `api.ts:159-163` does `Object.assign(new Error(...), { status, body })`, and `canon.py:167-169` raises `HTTPException(412, detail={"code":"CANON_VERSION_CONFLICT","current": exc.current.model_dump(mode="json")})`. So read: `const err = e as { status?: number; body?: { detail?: { code?: string; current?: CanonRule } } }`.
 - On `err.status === 412 && err.body?.detail?.code === 'CANON_VERSION_CONFLICT'`: (a) `setConflict({ ruleId: id, current: err.body.detail.current })`; (b) call the list `invalidate()` (add it to `useCanonRules`'s return — today `useCanonRules.ts:9` only invalidates `onSuccess`, so a 412 leaves a stale `version` and the retry 412s forever); (c) **do NOT call `setEditingId(null)`** — the current `saveEdit` (`CanonRulesPanel.tsx:25-29`) only clears it `onSuccess`, which is right; keep `CanonRuleForm` MOUNTED and do not change its `key`, because its draft lives in `useState` seeded from `initial` at mount only (`CanonRuleForm.tsx:36-41`) — a remount silently destroys the user's draft, which is the exact thing this fix exists to prevent.
 - Render a banner ABOVE the still-open form (`data-testid="composition-canon-conflict"`): the server's `current.text` / `current.scope` / `current.active`, + "This rule changed elsewhere — showing the current version. Re-apply your edit?" with a "Re-apply" button that calls `saveEdit(r.id, r.version, draftPayload)` — `r` re-renders from the invalidated list so `r.version` is fresh, and the re-apply lands.
 - Everything else (non-412) keeps `toast.error`.
 - TEST (this is M1's DoD line "a 412 test that asserts the panel shows `current` and keeps the user's draft"): in `CanonRulesPanel.test.tsx`, mock `patchCanonRule` to reject with `Object.assign(new Error('...'), { status: 412, body: { detail: { code: 'CANON_VERSION_CONFLICT', current: {...id, version: 7, text: 'server text'} } } })`; assert (a) `composition-canon-conflict` renders "server text", (b) the form is still open and its text input still holds the user's typed draft (NOT reset to `initial`), (c) the second Save sends `If-Match: 7`.

*Evidence:* frontend/src/features/composition/components/CanonRuleForm.tsx:37,41,46,48-59 (scope+active are submit-gated form state, one PATCH per Save, Save disabled while pending) · frontend/src/features/composition/components/CanonRulesPanel.tsx:18 (single `editingId` ⇒ one in-flight PATCH), :20 (`onError = (e) => toast.error(...)` — the bare toast being fixed), :25-29,:58 · services/composition-service/app/routers/canon.py:167-169 (412 body `{code:'CANON_VERSION_CONFLICT','current':<rule>}`) · frontend/src/api.ts:159-163 (`Object.assign(new Error(...), {status, body})` — the body is already on the error, just unread) · frontend/src/features/composition/hooks/useCanonRules.ts:9,22-26 (invalidate is `onSuccess`-only ⇒ a 412 leaves a stale version) · frontend/src/features/studio/panels/useSceneInspector.ts:46,99-100 (the chain pattern to copy IF a chip is ever added) · docs/specs/2026-07-01-writing-studio/31_quality_completion.md:56 ("reused as-is"), :322-332 (ASCII draws scope as a badge, not a chip), :349-352 (the ⚠ clause to delete)

### X-31-4-LANE-B-HANDLERS
BUILD AS SPEC'D, with one correction the code forces: drop `projectId` from the query keys and invalidate by PREFIX.

Create `frontend/src/features/studio/agent/handlers/compositionEffects.ts`, mirroring `knowledgeEffects.ts` exactly (exported pattern consts + module-level idempotency guard + `_resetCompositionEffectHandlers()` test escape hatch):

```ts
import { registerEffectHandler, type EffectContext } from '../effectRegistry';

export const CANON_RULE_WRITE_PATTERN = /^composition_canon_rule_/;      // create|update|delete only
export const CORRECTION_WRITE_PATTERN = /^composition_record_correction$/;

export function canonRuleEffect({ queryClient }: EffectContext): void {
  queryClient.invalidateQueries({ queryKey: ['composition', 'canon'] });            // useCanonRules.ts:8
  queryClient.invalidateQueries({ queryKey: ['studio', 'quality-canon', 'rules'] }); // useQualityCanon.ts:84
}
export function correctionEffect({ queryClient }: EffectContext): void {
  queryClient.invalidateQueries({ queryKey: ['composition', 'correction-stats'] });  // useCorrectionStats.ts:11
}

let registered = false;
export function registerCompositionEffectHandlers(): void {
  if (registered) return;
  registered = true;
  registerEffectHandler(CANON_RULE_WRITE_PATTERN, canonRuleEffect);
  registerEffectHandler(CORRECTION_WRITE_PATTERN, correctionEffect);
}
export function _resetCompositionEffectHandlers(): void { registered = false; }
```

WHY NO projectId (the spec's step-8 text is unbuildable as literally written): `EffectContext` (effectRegistry.ts:9-24) carries `bookId`, `host`, `queryClient` — there is NO composition `projectId` in it (projectId is resolved from bookId only *inside* useQualityCanon via useQualityWork). Do NOT plumb one in: a null-projectId race at mount would make the handler silently no-op (the `silent-success-is-a-bug` class). React-query partial-matches keys ELEMENT-WISE, so `['composition','canon']` matches `['composition','canon',pid]` and does NOT over-match `['composition','canon-at-chapter',…]` (useCanonAtChapter.ts:67) or `['composition','canon-draft',…]` (useVsCanonDelta.ts:85) — element[1] differs. Over-invalidating a second Work's cache is a harmless refetch. This is exactly what knowledgeEffects.ts:29 already does (bare `['knowledge-projects']`).

Use RegExp, never a bare string — `registerEffectHandler`'s string branch is `tool === p || tool.startsWith(p)` (effectRegistry.ts:41), not a pattern match (spec 36's warning).

No `unwrapToolResult` needed: both handlers are result-agnostic pure invalidation, so the `{ok,result}` envelope / flat-mock trap that bit glossaryEffects cannot bite here.

REGISTER: `frontend/src/features/studio/agent/useStudioEffectReconciler.ts` — add the import beside the other four (:17-21) and call `registerCompositionEffectHandlers();` in the idempotent `useEffect` (:32-38).

DELETE THE FALSE COMMENT: at useStudioEffectReconciler.ts:9-10, delete the clause "authoring_run has no MCP tools at all, REST-only, no Studio consumer to go stale". It is provably false — `composition_authoring_run_start` is server.py:1723, alongside _create/_gate/_resume/_pause/_close/_accept_unit/_reject_unit/_revert_all/_list/_get (11 tools). Keep the `composition_generate` clause (still true).

TEST: new `frontend/src/features/studio/agent/__tests__/compositionEffects.test.ts`, mirroring knowledgeEffects.test.ts. Drive through `runEffectHandlers({tool, …})` — NOT by calling the handler directly (injecting the handler proves the mechanism, not that it's wired). Assert: (a) `composition_canon_rule_create|update|delete` each invalidate BOTH `['composition','canon']` and `['studio','quality-canon','rules']`; (b) the READ `composition_list_canon_rules` fires NOTHING (regex-verified: `/^composition_canon_rule_/.test('composition_list_canon_rules') === false`); (c) `composition_record_correction` invalidates `['composition','correction-stats']`.

SEQUENCING: `composition_record_correction` does not exist yet (0 hits in composition-service/app/mcp/server.py) — it is BE-9b MUST-BUILD in this same wave (31_quality_completion.md:523). Land BE-9b before or with this handler. If BE-9b slips, the handler is inert-but-harmless (the registry simply never matches) — so this step is NOT blocked on it, and its pattern test passes standalone. The canon-rule half is live TODAY and delivers value immediately.

*Evidence:* frontend/src/features/studio/agent/effectRegistry.ts:9-24 (EffectContext has bookId/host/queryClient — NO projectId; the spec's `['composition','canon',projectId]` is unbuildable) · effectRegistry.ts:41 (string branch = `tool === p || tool.startsWith(p)`, not pattern) · frontend/src/features/composition/hooks/useCanonRules.ts:8 (`['composition','canon',projectId]`) · frontend/src/features/studio/panels/useQualityCanon.ts:84 (`['studio','quality-canon','rules',projectId]` — the rule-violations key, under `studio` not `composition`) · frontend/src/features/composition/hooks/useCorrectionStats.ts:11 (`['composition','correction-stats',projectId]`) · services/composition-service/app/mcp/server.py:1080/1121/1168 (canon_rule create/update/delete) · server.py:1723 (`composition_authoring_run_start` — PROVES useStudioEffectReconciler.ts:9-10's comment false) · server.py grep `correction` = 0 hits (record_correction is BE-9b, unbuilt) · frontend/src/features/studio/agent/handlers/knowledgeEffects.ts:29,52-57 (the prefix-invalidation + idempotency-guard + _reset pattern to mirror) · useStudioEffectReconciler.ts:17-21,32-38 (registration sites)

### Q-31-PANEL-COUNT-DRIFT
The premise is already false in code: NO guard asserts a panel count. Keep it that way — never introduce one.

INSTRUCTION TO THE BUILDER (mechanical, per new panel):

1. NEVER write a count literal into a test. The two guards are RELATIONAL and concurrency-proof by construction:
   - panelCatalogContract.test.ts:36-38 asserts sorted-set equality: contract `ui_open_studio_panel.args.panel_id.enum` == `OPENABLE_STUDIO_PANELS.map(p=>p.id)`.
   - panelCatalogContract.test.ts:29-31 asserts every advertised id is a buildable `STUDIO_PANEL_COMPONENTS` key.
   - test_frontend_tools_contract.py:126-140 asserts the committed JSON == the live py schemas.
   - test_frontend_tools.py:168-172 asserts non-empty / all-string / no-duplicate — no count.
   If a concurrent track lands a panel, ALL FOUR stay green automatically. A `== 58` would be the ONLY thing that reds — i.e. the bug would be self-inflicted.

2. Each milestone's DoD asserts MEMBERSHIP of its OWN new ids, never a total. Add to panelCatalogContract.test.ts, per milestone:
   `it('M1: quality-canon-rules is advertised, openable, and buildable', () => { for (const id of ['quality-canon-rules','progress','quality-corrections','quality-heal']) { expect(enumIds).toContain(id); expect(Object.keys(STUDIO_PANEL_COMPONENTS)).toContain(id); expect(OPENABLE_STUDIO_PANELS.map(p=>p.id)).toContain(id); } })`
   Membership is invariant under a concurrent panel landing; a count is not. (If a delta assertion is ever wanted, use the spec-36 form `N_before + k == N_after` computed at runtime — never a literal.)

3. THE 3-FILE ATOMIC COMMIT (all in ONE commit — this is what actually prevents drift):
   a. `services/chat-service/app/services/frontend_tools.py:402` — append the new id(s) to the hand-maintained `panel_id` `enum` array, AND add a `'<id>' = …` clause to the description prose block (lines 404-483; it is the model's only affordance doc).
   b. `frontend/src/features/studio/panels/catalog.ts` — add a `STUDIO_PANELS` row (`{ id, component, titleKey, descKey, category, guideBodyKey }`); `OPENABLE_STUDIO_PANELS` (catalog.ts:279) and `STUDIO_PANEL_COMPONENTS` (:276) derive from it. Omit `hiddenFromPalette` (all 4 Wave-1 panels are bare-id openable).
   c. `contracts/frontend-tools.contract.json` — REGENERATE, never hand-edit: from `services/chat-service/`, run `WRITE_FRONTEND_CONTRACT=1 python -m pytest tests/test_frontend_tools_contract.py` and commit the emitted JSON.

4. MERGE-CONFLICT RULE (the real shared-checkout hazard, and it is NOT the count): `contracts/frontend-tools.contract.json` is a generated artifact and a conflict hotspot. On any conflict/rebase against a concurrent track that also added a panel: take the incoming `frontend_tools.py` + `catalog.ts` merges, then RE-RUN `WRITE_FRONTEND_CONTRACT=1 pytest` to regenerate the JSON. Never hand-merge the enum array.

5. DOC HYGIENE (do this once, in Wave 1's commit): the "58==58==58 / 59 / 60 / 61" ladder in spec 31's DoD is stale prose that plan-30 §8 item 6 already superseded (it flagged that six specs each computed from the same 57 baseline; waves are cumulative; true end state 71). Strike the per-milestone literals from 31's DoD and replace with "the N new ids are present in all three sets"; the cumulative baseline table in plan-30 §8 (57→61 after Wave 1) is the only place a number belongs, and it is documentation, not an assertion.

DEFAULT THE PO MAY VETO: no test in this track ever asserts a panel count, in any form.

*Evidence:* frontend/src/features/studio/panels/__tests__/panelCatalogContract.test.ts:36-38 (`expect([...(enumIds ?? [])].sort()).toEqual(openable)` — set equality, zero count literals); :29-31 (enum ⊆ STUDIO_PANEL_COMPONENTS). frontend/src/features/studio/panels/catalog.ts:276,279 (STUDIO_PANEL_COMPONENTS + OPENABLE_STUDIO_PANELS both DERIVE from STUDIO_PANELS:113). services/chat-service/app/services/frontend_tools.py:402 (the hand-maintained 57-value panel_id enum) + :404-483 (the description block that must be extended too). services/chat-service/tests/test_frontend_tools_contract.py:126-140 (contract JSON == live schemas; regen via WRITE_FRONTEND_CONTRACT=1) and tests/test_frontend_tools.py:168-172 (non-empty/unique — no count). docs/specs/2026-07-01-writing-studio/30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md:574-586 (§8 item 6: "All specs are amended to the delta form… never a literal"; cumulative baseline 57→61 after Wave 1, end state 71).

### Q-31-M4-LIVESMOKE-BOOK-SERVICE
"book-service" is a COPY-PASTE TYPO in spec 31's M4 DoD — book-service is not in the correction path at all, and the word "restore" leaked in from M1's BE-11a canon-rule restore (a composition-service route). The M4 live-smoke crosses THREE processes: composition-service → worker-infra (the outbox relay) → learning-service. Fix the two lines in docs/specs/2026-07-01-writing-studio/31_quality_completion.md that name book-service:

(1) Line 683-684 (M4 DoD): replace "**cross-service live-smoke** (composition ↔ book-service restore ↔ the outbox relay)" with:
"**cross-service live-smoke** (composition-service → the worker-infra outbox relay → learning-service's `corrections`)".

(2) Line 720-721 (Definition of Done §5): replace "(composition + book-service + the outbox relay ⇒ ≥2 services)" with:
"(composition-service + worker-infra's outbox relay + learning-service ⇒ 3 services)".

The smoke the builder runs at M4 VERIFY, on a rebuilt stack (composition-service, worker-infra, learning-service, Postgres, Redis all up), signed in as claude-test@loreweave.dev:
  a. Reject one unit of an authoring run (or call MCP `composition_record_correction` with kind='reject') on a real work.
  b. Assert a `generation_corrections` row landed in loreweave_composition AND an `outbox_events` row with event_type='composition.generation_corrected', aggregate_type='composition' landed in the SAME transaction.
  c. Wait for the relay tick; assert the row's relayed/sent marker flips and the event appears on Redis stream `loreweave:events:composition` (XRANGE, or just proceed to (d) — (d) subsumes it).
  d. Assert BY EFFECT at an API boundary, not by peeking at SQL: `GET /v1/learning/corrections` as the same user returns a row with `target_type='generation'`, `origin_service='composition'`, `op='reject'`, `target_id=<the job_id>`. (Route exists: services/learning-service/app/routers/corrections.py:64.)

VERIFY evidence token to paste, filled with real ids:
`live smoke: reject_unit on run <run_id> → generation_corrections row + outbox composition.generation_corrected (same txn) → worker-infra relay XADD loreweave:events:composition → learning-service corrections row visible via GET /v1/learning/corrections (target_type=generation, op=reject, target_id=<job_id>)`

Default I am picking (veto-able): assert step (d) via the learning-service REST route rather than a direct SQL SELECT on loreweave_learning — it proves the consumer persisted AND the row is reachable by the user whose panel will read it. Note this route is also the one BE-9d (spec 31 line 526) says to check before minting a second per-job corrections list.

No book-service work is added to M4, and BE-11a/restore stays in M1 exactly as specced.

*Evidence:* services/composition-service/app/db/repositories/generation_corrections.py:140 (create() emits outbox.GENERATION_CORRECTED in the caller's txn) · services/composition-service/app/db/repositories/outbox.py:31 (GENERATION_CORRECTED = "composition.generation_corrected", aggregate_type='composition') · services/worker-infra/internal/tasks/outbox_relay.go:220 (streamKey := "loreweave:events:" + aggregateType) · services/learning-service/app/main.py:61 (dispatcher.register("composition.generation_corrected", handle_generation_corrected)) · services/learning-service/app/events/handlers.py:500 (persists a `corrections` row, origin_service='composition') · services/learning-service/app/routers/corrections.py:64 (GET /v1/learning/corrections — the effect assertion) · services/worker-infra/internal/config/config.go:37 ("composition never writes book-service's DB, SCOPE-2") · grep -ri "generation_corrected" across services/ returns ZERO hits in services/book-service. Typo source: 31_quality_completion.md:519 (BE-11a restore = POST /v1/composition/canon-rules/{id}/restore, a composition route in M1).

### Q-31-I18N-GAPFILL-TRAP
ADD-ONLY is the law; here is the exact builder procedure (no further thought required).

(1) ADD, NEVER EDIT. All ~28 new `quality.*` / `progress.*` strings and `panels.<id>.{title,desc,guideBody}` x4 go into `frontend/src/i18n/locales/en/studio.json` as NEW keys. Do NOT change the VALUE of any existing key in `en/studio.json` (or any other en namespace) that already has translations — `scripts/i18n_translate.py:347-357` carries any existing non-empty, placeholder-faithful target value verbatim and never compares it to the en source, so an edited en string leaves 17 locales permanently stale with no error.

(2) IF A WORDING CHANGE IS GENUINELY NEEDED for an existing key: add a NEW key (e.g. `quality.canonIntroV2`), point the component at it, and LEAVE the old key in place (it is harmless — i18next `fallbackLng: 'en'`, `frontend/src/i18n/index.ts:13`). Never hand-write a translation into a non-en locale file.

(3) GENERATE (once per wave, at the wave's DoD, after the en keys land):
    python scripts/i18n_translate.py --ns studio
    (LM Studio on :1234 / gemma-4-26b-a4b-qat; runs all 17 targets; gap-fill means ONLY the new keys cost tokens.) Do NOT pass `--force` — `:396` re-translates the ENTIRE namespace x 17 langs and clobbers hand-authored strings.

(4) VERIFY (a literal DoD step in EVERY wave that adds a string — the components use `t(key, {defaultValue: '...'})`, so a locale that silently missed the key still renders English and looks fine; only a key-set diff catches it):
    a. key-set parity: for each of the 17 locales, the flattened key set of `locales/<lang>/studio.json` must be a superset of `locales/en/studio.json`'s (a ~10-line python check; red = re-run the tool).
    b. `python scripts/i18n_translate.py --check <lang>/studio.json` on a spot sample (e.g. ru, ar, zh-CN) => "0 hard".
    c. no new rows for `studio.json` in any `frontend/src/i18n/locales/*/_FAILED.json`.

(5) ESCAPE HATCH (documented so nobody reaches for `--force`): if an existing en value truly must change, delete that dotted key from all 17 `locales/<lang>/studio.json` files (a small python/jq sweep), THEN run step 3 — `plan_namespace` now sees it as missing and re-translates exactly that key, leaving every other translation untouched. Equivalent alternative: list the key under `studio.json` in each `locales/<lang>/_FAILED.json` (the `retry_keys` path, `:429-438`).

DEFAULT the PO can veto: old/superseded keys are LEFT in the locale files (dead keys are free; pruning them risks a bad `--force` run).

*Evidence:* scripts/i18n_translate.py:339-357 (plan_namespace `carry` = keep any existing non-empty placeholder-faithful value; `to_translate` = only keys MISSING from the target file; no en-source comparison) · :396 (`--force` = re-translate everything, whole-namespace blast radius) · :429-438 (`_FAILED.json` -> `retry_keys` = the only key-level re-translate hook) · frontend/src/features/studio/panels/QualityCanonPanel.tsx:48-55 (the "learned this the hard way" in-code warning) · frontend/src/i18n/index.ts:13 (fallbackLng en => a missing key is SILENT) · docs/specs/2026-07-01-writing-studio/31_quality_completion.md:560

### Q-31-GG4-RETIREMENT-ORDER
GG-4 is SATISFIED BY CONSTRUCTION. Do NOT add a scheduling gate, a defer row, or a "flag to whoever schedules spec 16" hand-off — spec 16 is CLOSED and nothing is scheduled to delete the reader. Three concrete actions:

(1) BUILD Wave 1 / spec 31 M2 (`progress`) EXACTLY AS SPECCED, and note that this IS the fix for GG-4. The new `frontend/src/features/studio/panels/ProgressPanel.tsx` (spec 31 §557, category `editor`, QC-2) is the Studio-side reader for the loop `ManuscriptUnitProvider.tsx:239` already writes. Wave 1 runs before Wave 6 in plan 30's own DAG (§7 sequencing), so the "retire before the port" ordering violation is not reachable in this plan.

(2) PIN THE LOOP WITH A TEST, not a prose banner (this repo's `checklist⇒test the effect` + `built-mounted-unreachable` lessons; and it is literally what plan 30's Wave 6 block asks for — "a mechanical guard, not the current 18-line prose banner"). Add to spec 31 M2's Definition of Done: `frontend/src/features/studio/panels/__tests__/ProgressPanel.test.tsx` must assert the panel RENDERS `today_words` / `daily_goal` fetched from `GET /works/{pid}/progress` (i.e. the reader is proven by EFFECT, not by the presence of a `catalog.ts` row). That single test is the mechanical guard: from the moment it is green, deleting `ChapterEditorPage` can no longer orphan the progress loop.

(3) FIX-NOW the stale doc text at Wave 1 close-out (a ~3-line edit; CLAUDE.md says a defer row costs more than the fix). Two places in `docs/specs/2026-07-01-writing-studio/30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md` still describe retirement as PENDING and contradict spec 16's actual sealed outcome:
  - §7 Wave 6 block ("🔴 GG-4 GATE: when this wave closes, and ONLY then, spec 16's `ChapterEditorPage` retirement may proceed") → replace with: "GG-4 is CLOSED by Wave 1's `progress` panel — the Studio now has its own reader for the save-time word-count loop. `ChapterEditorPage` is NOT scheduled for deletion: spec 16 Phase 4b (2026-07-05, user's call, superseding M9) keeps it indefinitely as an unlinked direct-URL fallback. The mechanical guard Wave 6 asked for is the `progress` panel's own render test."
  - GG-3's table row ("reachable only from a page spec 16 has a user-approved decision to RETIRE") → soften to "…a page spec 16 has DEPRECATED (banner-marked, unlinked from the UI) but explicitly decided to KEEP (Phase 4b)". The PORT framing of GG-3 is unaffected and stays.
  - Also strike spec 31's own Risk row (`31_quality_completion.md:753`) and its `:402` "GG-4: ChapterEditorPage may not be retired until this ships" line, replacing both with a one-liner pointing at spec 16 Phase 4b.

DEFAULT THE PO CAN VETO: I am deciding that `ChapterEditorPage.tsx` stays (no deletion is scheduled, now or after Wave 6) — because that is the last explicit user decision on record (spec 16 Phase 4b), and the risk it was avoiding (an undiscovered live dependency on a dead-code removal) is unchanged. If the PO now WANTS the page deleted, that is a new decision, and the correct gate is then: Wave 6 close + the M2 progress-panel test green + the canon/heal/corrections panels shipped (all of which Wave 1+6 deliver anyway) — i.e. even under a veto, the hard ordering the spec proposed (31 before 16's M1) is already what the wave DAG does. No plan change is needed in EITHER branch.

*Evidence:* PREMISE CONFIRMED (write with no Studio reader): writer at frontend/src/features/studio/manuscript/unit/ManuscriptUnitProvider.tsx:209 (`const reportProgress = useReportProgress(...)`) and :239 (`reportProgress(s.chapterId, wordCount(freshText))`). Sole reader today: `grep -rn "useProgress" frontend/src --include=*.tsx --include=*.ts | grep -v __tests__` → only frontend/src/features/composition/components/ProgressPanel.tsx:27, which is mounted ONLY at frontend/src/features/composition/components/CompositionPanel.tsx:847 (the legacy page). No studio/panels/** consumer exists.

RISK IS DEAD (no retirement is scheduled): docs/specs/2026-07-01-writing-studio/16_chapter_editor_parity_and_retirement.md:3 ("Status: ✅ COMPLETE 2026-07-05 … Phase 4b (M9 — kept `ChapterEditorPage.tsx`, marked deprecated, not deleted)") and :133-135 ("Phase 4b — M9 resolved: keep, don't delete … User's call (2026-07-05), superseding M9's original 'delete after a soak period' plan: `ChapterEditorPage.tsx` is kept indefinitely, not deleted. No route change either."). The code agrees: frontend/src/pages/ChapterEditorPage.tsx:1-18 banner — "a decision to keep it around, not a decision pending removal (spec 16 Phase 4b, 2026-07-05: kept indefinitely, not deleted)" — and the route is still live at frontend/src/App.tsx:134.

STALE TEXT TO FIX: docs/specs/2026-07-01-writing-studio/30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md §7 Wave 6 ("🔴 GG-4 GATE … spec 16's `ChapterEditorPage` retirement may proceed") + GG-3's dock table ("a page spec 16 has a user-approved decision to RETIRE"), and docs/specs/2026-07-01-writing-studio/31_quality_completion.md:402 and :753.

ORDERING ALREADY HOLDS: plan 30 §7 sequencing DAG puts Wave 1 (quality/spec 31) immediately after Wave 0 and Wave 6 (editor-craft + any spec-16 retirement) strictly downstream of Waves 1/2/3 — so "31 before 16" is the plan's existing shape, not a new constraint. Consistent with SEALED §0 PO-1..4 (none of which touch spec 16).

### Q-31-F-Q6-STALE-DATA-LOSS
BUILD THE THREE GUARDS AS SPEC'D (QC-4 stands, unamended) — the code confirms every premise. Concrete build instruction, M3:

(1) ONE pure guard function, consumed twice (this is what makes "rendered AND enforced" impossible to drift). New file `frontend/src/features/studio/manuscript/unit/healGuard.ts`:
`export type HealGuard = {kind:'ok'} | {kind:'stale', reason:'chapter'|'version'|'dirty'} | {kind:'no-editor'}`
`export function evaluateHealGuard(args:{unitChapterId:string|null; unitVersion:number|undefined; unitIsDirty:boolean; hasEditor:boolean; proposalChapterId:string|null; proposalDraftVersion:number|null}): HealGuard`
Precedence, FIXED (do not re-derive): 1. `proposalChapterId==null` OR `unitChapterId!==proposalChapterId` -> stale/chapter. 2. `unitIsDirty` -> stale/dirty. 3. `proposalDraftVersion==null || unitVersion==null || unitVersion!==proposalDraftVersion` -> stale/version (FAIL CLOSED: an unverifiable version is stale, never "probably fine"). 4. `!hasEditor` -> no-editor. else ok.
Unit-test this function directly, one case per branch + the two null/fail-closed cases.

(2) NEW hoist verb in `ManuscriptUnitProvider.tsx` (add to `ManuscriptUnitApi` next to `applyProposedEdit` at :93):
`applyHealedDocument: (p:{text:string; chapterId:string; expectedDraftVersion:number|null}) => HealGuard`
Body: `const g = evaluateHealGuard({unitChapterId: stateRef.current.chapterId, unitVersion: stateRef.current.version, unitIsDirty: isDirtyState(stateRef.current), hasEditor: editorRef.current!=null, proposalChapterId:p.chapterId, proposalDraftVersion:p.expectedDraftVersion}); if (g.kind!=='ok') return g;` then build the doc, `editorRef.current!.setContent(doc)`, AND **`setBody(doc, p.text)`**, then `return {kind:'ok'}`.
*** The `setBody` call is NOT optional and is the bug the spec did not catch: `TiptapEditorHandle.setContent` flips `isExternalUpdate=true` (TiptapEditor.tsx:252-256) and `onUpdate` early-returns on it (TiptapEditor.tsx:172). EditorPanel.tsx:394 is the ONLY caller of `setBody`. So a setContent-only heal leaves `workingBody===null` -> `isDirty===false` -> the heal is never saved and is silently discarded on the next chapter switch/reload. That is a second data-loss path in the "success" branch. A test MUST assert: after `applyHealedDocument` returns ok, `unit.isDirty === true` and `unit.state.workingBody` contains the healed text. ***
Doc-builder: extract ChapterEditorPage.tsx:593-598's paragraph/`_text` shape into `textToTiptapDoc(text)` in `@/lib/tiptap-utils` and call it from BOTH sites (legacy keeps working, one impl).
PROVENANCE — deliberate deviation from the spec table's "provenance = AI" row (PO may veto): do NOT mark the doc. A whole-doc replace can only mark the ENTIRE document as AI-written, which is a lie about the ~99% of prose the author wrote. Instead capture an undo point exactly as legacy does (`useManuscriptCheckpoints.capture(chapterId, healedText, 'polish', revId)` — ChapterEditorPage.tsx:592). Per-span provenance on a heal needs a per-edit transaction path; note it, do not build it here.

(3) `usePolishProposals.ts` must PIN what it proposed against. Today it reads `chapterId` from its argument, so in a persistent dock tab the arg silently becomes the NEW chapter. Add `const [ranFor, setRanFor] = useState<{chapterId:string; draftVersion:number|null}|null>(null)`, set it inside `run()` (alongside the existing `setDraftVersion` at :48), derive `healedText` from the entry keyed by `ranFor`, and return `proposalChapterId`/`proposalDraftVersion` from `ranFor` — never from the live prop. Proposals stay VISIBLE after a chapter switch, wearing the stale banner; they are never re-keyed away and never applied to the wrong chapter.

(4) `PolishPanel.tsx` gains ONE additive optional prop (it must stay legacy-compatible per QC-1): `applyGuard?: { guard: HealGuard; onRerun: () => void; onSaveAndRerun: () => void; onOpenProposalChapter: () => void }`. When `applyGuard.guard.kind !== 'ok'`, render a banner (`data-testid="polish-stale-<reason>"` / `polish-no-editor`) AND set the Apply button `disabled`. Banner copy + action per reason: chapter -> "These fixes were proposed for a different chapter" + [Open that chapter] (`host.focusManuscriptUnit(proposalChapterId)`); dirty -> "You have unsaved edits — these fixes are against the saved draft and would revert them" + [Save & re-run Polish] (`unit.save()` then `run()`); version -> "The chapter changed since Polish ran" + [Re-run Polish]; no-editor -> "Open the editor to apply." Legacy passes no `applyGuard` -> zero behavior change.

(5) New `frontend/src/features/studio/panels/QualityHealPanel.tsx` wires it: reads `useManuscriptUnit()`, computes `evaluateHealGuard(...)` from live unit state + the hook's pinned `ranFor`, passes `applyGuard` down, and passes `onApply={(text)=>{ const r = unit.applyHealedDocument({text, chapterId: proposalChapterId, expectedDraftVersion: proposalDraftVersion}); if (r.kind!=='ok') toast.error(...); }}` — the hoist re-checks at click time (state can change between render and click), so the guard is enforced, not merely displayed.

(6) FIX-NOW while you are here (one line, cheaper than a defer row): `CompositionPanel.tsx:861` is `onApply={onApplyPolish ?? (() => {})}` — a literal silent no-op on the popout route. Make `PolishPanel.onApply` optional and, when absent, disable Apply with the same no-editor banner. Never a silent no-op.

TESTS (each guard RENDERED and TESTED, per the spec's own bar): healGuard.test.ts (5 branch cases); ManuscriptUnitProvider test — applyHealedDocument returns stale/chapter, stale/dirty, stale/version, no-editor, and on ok sets isDirty=true + workingBody=healed (the setContent-suppresses-onUpdate regression guard); PolishPanel test — each guard kind renders its banner AND disables Apply; QualityHealPanel test — click-time re-check (render ok, mutate unit to dirty, click, assert no write + error surfaced).

*Evidence:* CONFIRMS the spec's uncited assertions: frontend/src/features/studio/manuscript/unit/ManuscriptUnitProvider.tsx:47 (`version: number | undefined` — "draft_version for optimistic concurrency"), :167 (`version: draft.draft_version`), :44 (`chapterId`), :67 + :114-116 + :333 (`isDirty` via `isDirtyState`). Versions are comparable across services: services/composition-service/app/routers/plan.py:237 sends `"draft_version": draft.get("draft_version")` from the same `book.get_draft` the FE hoist reads. THE BUG: frontend/src/features/composition/hooks/usePolishProposals.ts:24+48 (stores draftVersion), :97 (returns it), :89-92 (`healedText = applySelfHealEdits(sourceText,...)` off the propose-time snapshot) — zero readers (`grep -rn "draftVersion" frontend/src` hits only this file). Its fail-safe is not a mitigation: frontend/src/features/composition/api.ts:708 compares each edit's `before` against the SAME stale sourceText. THE SECOND, UNSPOTTED DATA-LOSS PATH: frontend/src/components/editor/TiptapEditor.tsx:252-256 (`setContentHandler` sets `isExternalUpdate.current = true`) + :172 (`onUpdate: ({editor}) => { if (isExternalUpdate.current) return; ... }`), while frontend/src/features/studio/panels/EditorPanel.tsx:394 (`onUpdate={(json,text) => setBody(json,text)}`) is the sole `setBody` caller — so a setContent-only `applyHealedDocument` never dirties the hoist and the heal is dropped on the next switch. THE SILENT NO-OP: frontend/src/features/composition/components/CompositionPanel.tsx:861 `onApply={onApplyPolish ?? (() => {})}` (and its own :853-854 comment already admits the stale-chapter corruption class). Doc-builder to extract: frontend/src/pages/ChapterEditorPage.tsx:591-601. Chokepoint to extend: ManuscriptUnitProvider.tsx:93-104 (`applyProposedEdit`, whose doc-comment demands ONE chokepoint for "an AI wrote into this chapter").

### Q-31-LEGACY-POLISHPANEL-REGRESSION
The additive-only policy is RIGHT, but the stated regression gate is FALSE and must be replaced — the legacy PolishPanel tests cannot gate the hook rewrite, because they mock the hook away. Builder does exactly this:

(1) M3, BEFORE touching the hook — WRITE THE MISSING GATE. Create `frontend/src/features/composition/hooks/__tests__/usePolishProposals.test.tsx` as a CHARACTERIZATION test against the CURRENT useState impl (renderHook + `vi.mock('../../api')` stubbing `compositionApi.proposeSelfHeal`; keep `applySelfHealEdits` REAL — do not mock it). Pin the full 14-key return shape and 5 behaviors: (a) `run()` populates proposals/sourceText/draftVersion/stats and flips `ran`; (b) `acceptedIds` is seeded from `p.recommended ?? p.tier === 'deterministic'`; (c) `toggle(id)` flips one id; (d) `bulk(on, tier?)` is tier-scoped; (e) **`healedText === sourceText` when `acceptedIds` is empty, and `healedText !== ''` whenever `sourceText !== ''`**. Run it GREEN on the old impl, commit, THEN rewrite. The same file must be green after the rewrite. THAT is the regression gate — not PolishPanel.test.tsx.

(2) Cache the WHOLE `SelfHealProposalResponse` as ONE atom under `['composition','self-heal', projectId, chapterId]` — proposals + source_text + draft_version + stats together. NEVER proposals alone. Reason (this is the data-loss path the spec's mitigation would have shipped): `applySelfHealEdits` bases its output on `sourceText` (`let out = sourceText`, api.ts:706). If proposals come from the cache while `sourceText` stays in `useState`, a cache-hit remount yields `healedText === ''` → `onApply('')` REPLACES THE CHAPTER WITH AN EMPTY DOCUMENT, and QC-4's `expectedDraftVersion` does not catch it because the cached draft_version still matches.

(3) Derive `ran` from cache presence (`data !== undefined`), not a `useState` flag, and seed `acceptedIds` from the cached response on first data (not only inside `run()`) — otherwise a remounted `quality-heal` renders proposal rows with zero pre-checks and a disabled Apply.

(4) Keep `chapterId` IN the cache key and keep the `key={chapterId}` remount at CompositionPanel.tsx:856 — its comment ("stale Ch-A edits would Apply onto Ch-B (corruption)") is a live invariant the cache must preserve.

(5) M1 CanonRules — additive-only, as specced, is correct and already self-gating. Add `restore` mutation + `includeArchived` list arg to the `useCanonRules` return (hooks/useCanonRules.ts:31); make `showArchived`/`onRestore` OPTIONAL props whose absence reproduces today's exact behavior; `kind` optional on CanonRuleForm. No new hook test needed (list queryKey unchanged, change is purely additive) — but ADD one case to CanonRulesPanel.test.tsx: "with showArchived/onRestore omitted, no archived UI renders and no restore call fires". Note CanonRulesPanel.test.tsx:19 mocks `useCanonRules` with an object literal, so a component that unconditionally calls `canon.restore.mutate` REDS the suite — that mock is a genuine gate here, unlike PolishPanel's.

(6) DoD for BOTH M1 and M3 (literal step in each wave): `npx vitest run src/features/composition` fully green (CompositionPanel*.test.tsx, PolishPanel.test.tsx, CanonRulesPanel.test.tsx) AND the new usePolishProposals.test.tsx green AND `/review-impl` clean. Per PO policy 2, `/review-impl` runs at the completion of every wave and any bug it finds is fixed before the wave closes.

DEFAULT I PICKED (veto-able): I did not defer the missing hook test as "unbuilt infrastructure" — writing it is ~60 lines and it is the only thing standing between this rewrite and a chapter-blanking bug, so it is FIX-NOW per CLAUDE.md's defer gate.

*Evidence:* frontend/src/features/composition/components/__tests__/PolishPanel.test.tsx:8-11 — `vi.mock('../../hooks/usePolishProposals', () => ({ usePolishProposals: () => state.value }))` mocks the hook module out entirely, so the panel suite is structurally blind to ANY hook rewrite. Corroborating: `frontend/src/features/composition/hooks/__tests__/` contains 27 hook tests and NO usePolishProposals test — the hook has zero direct coverage. The data-loss path: frontend/src/features/composition/api.ts:700-707 (`applySelfHealEdits`: `let out = sourceText` ⇒ returns '' when sourceText is '') combined with frontend/src/features/composition/hooks/usePolishProposals.ts:26-27 (`sourceText`/`draftVersion` held in useState, i.e. NOT in the cache atom) and PolishPanel.tsx:153 (`onApply(p.healedText)`). Safe-by-contrast: frontend/src/features/composition/components/__tests__/CanonRulesPanel.test.tsx:19 mocks `useCanonRules` with an object literal lacking `restore`, so an unconditional `canon.restore.mutate` call reds the suite. Remount invariant: frontend/src/features/composition/components/CompositionPanel.tsx:853-856 (`key={chapterId}` — "stale Ch-A edits would Apply onto Ch-B (corruption)").

### Q-31-F-Q11-DOUBLE-PAID-ACTION
CONFIRMED by code — the spec's answer stands: EXTRACT `CorrectionStatsTable`, NEVER mount `QualityPanel` in the Studio. Do not touch `FlywheelPanel`. Builder steps (M4, quality-corrections):

1. NEW `frontend/src/features/composition/components/CorrectionStatsTable.tsx` — MOVE verbatim from `QualityPanel.tsx`: the `pct`/`num` helpers (:13-14) and the whole `CorrectionStatsTable` fn (:37-92), now `export function CorrectionStatsTable({ stats }: { stats: NonNullable<ReturnType<typeof useCorrectionStats>['data']> })`. Keep i18n ns `composition` and every existing data-testid (`composition-quality-coldstart`, `stat-auto`, `stat-cowrite`) — the Studio panel inherits them.
2. `QualityPanel.tsx` — delete the moved fn, `import { CorrectionStatsTable } from './CorrectionStatsTable'`. Zero behavior change; `__tests__/QualityPanel.test.tsx` must stay green untouched (that is the extraction's regression proof for the legacy page).
3. NEW `frontend/src/features/studio/panels/QualityCorrectionsPanel.tsx` — copy the SHAPE of `QualityCoveragePanel.tsx` (`useStudioPanel('quality-corrections', props.api)` + `useQualityWork(host.bookId, accessToken)` + `if (work.kind !== 'ready') return <QualityWorkGate state={work} testIdPrefix="quality-corrections" />`), root `data-testid="studio-quality-corrections-panel"`. Body = `useCorrectionStats(work.projectId, accessToken)` → loading/error hint or `<CorrectionStatsTable stats={stats.data} />`. **NO `ModelPicker`, NO `BookPromiseCoverageSection`, no `modelRef` prop, no Run button** — spec 31:637 says this panel triggers no LLM call; the paid coverage pass stays solely in `quality-coverage`.
4. Registration (a panel not on the hub is unreachable): `panels/catalog.ts` row after the `quality-coverage` row (:269); `QualityHubPanel.tsx` `CARDS` += `{ panelId: 'quality-corrections', icon: '📈', … }`; `services/chat-service/app/services/frontend_tools.py` `panel_id` enum + description clause; regenerate `contracts/frontend-tools.contract.json`.
5. TEST THE EFFECT (this is what makes the decision enforced, not a comment): in `panels/__tests__/QualityCorrectionsPanel.test.tsx` assert BOTH (a) the stats table renders, and (b) the paid surface is ABSENT — mock `@/features/composition/components/BookPromiseCoverageSection` and assert `queryByTestId('book-promise-coverage')` (its root) is null and no model-picker is rendered. Also add a guard in `panels/catalog.ts`'s existing panel test or a one-liner in this test: `QualityPanel` never appears in `STUDIO_PANEL_COMPONENTS`.
6. Ship BE-9c (correction-stats operation allowlist) in the same milestone — an extracted table over the current denominator renders a false accept_rate.
7. `FlywheelPanel.tsx` / `useFlywheel.ts` / `knowledgeApi.getFlywheel`: OUT OF SCOPE, do not modify. It is KG-growth (+N entities from the last extraction), not the correction flywheel.

BONUS FIX (one line, fix-now, do it while extracting): spec `36_editor_craft_ports.md:653` maps `flywheel: 'quality-corrections'` in the `legacyParityContract` map. That is WRONG by the code — `CompositionPanel.tsx:850` puts `QualityPanel` under sub-tab `quality` and `:865` puts `FlywheelPanel` under sub-tab `flywheel`. Correct the spec row to `quality: 'quality-corrections'`, and give `flywheel` its own row pointing at the KG wave (spec 38 / Wave 8) — leaving it as-is makes the GG-4 gate green while the KG-growth view is silently unported, which is exactly the `built-mounted-unreachable` bug class.

DEFAULT the PO can veto: `quality-corrections` is read-only and free; if they want the coverage audit reachable from the corrections panel, add a link to `quality-coverage`, never a second Run button.

*Evidence:* frontend/src/features/composition/components/QualityPanel.tsx:27,32 (renders CorrectionStatsTable + BookPromiseCoverageSection) · QualityPanel.tsx:37 (CorrectionStatsTable is module-private, not exported ⇒ must be extracted) · frontend/src/features/studio/panels/QualityCoveragePanel.tsx:33,40 (Studio already mounts ModelPicker + BookPromiseCoverageSection = the paid pass) · frontend/src/features/composition/hooks/useFlywheel.ts:13 → frontend/src/features/knowledge/api.ts:1250 `getFlywheel` (KG growth, not corrections) · frontend/src/features/composition/components/CompositionPanel.tsx:850 (subtab `quality` → QualityPanel) vs :865 (subtab `flywheel` → FlywheelPanel), which contradicts docs/specs/2026-07-01-writing-studio/36_editor_craft_ports.md:653

### Q-31-QC2-PROGRESS-CATEGORY
FOLLOW QC-2 VERBATIM; the Wave-1 shorthand and the line-65 file-fate row are both superseded. Concrete build instruction:

(1) catalog.ts — 4 new STUDIO_PANELS rows, all with a mandatory `guideBodyKey` (X-3):
    • `progress` → `category: 'editor'`, placed in the editor cluster next to `chapter-browser`/`scene-browser` (catalog.ts:183-185). NOT `quality`.
    • `quality-canon-rules`, `quality-corrections`, `quality-heal` → `category: 'quality'`, appended after catalog.ts:270.
    (Wave-0 X-2 must land first: `CATEGORY_ORDER` in palette/useStudioCommands.ts:20-22 lists 9 categories and is MISSING `'quality'` — the existing quality rows already sort at index -1.)

(2) QualityHubPanel.tsx CARDS (currently 4 rows at :13-18) → exactly 7: append `{panelId:'quality-canon-rules', icon:'⚖️'}`, `{panelId:'quality-corrections', icon:'📈'}`, `{panelId:'quality-heal', icon:'✨'}`. DO NOT add a `progress` card. A word-count streak is not a quality judgment; `progress` is reachable via the palette/editor category and pairs with the existing `WordCountStatusItem` status-bar contribution (StudioStatusContributions.tsx:19).

(3) ModelPicker: ONLY `QualityHealPanel.tsx` imports `@/components/model-picker`, holds `modelRef` state and passes it down — because `PolishPanel.tsx:19` takes `modelRef` as a required prop and `usePolishProposals(...)` (:21) drives the paid `self-heal/propose` run with it. `QualityCanonRulesPanel`, `ProgressPanel` (studio wrapper) and `QualityCorrectionsPanel` mount NO ModelPicker — their inner components (`CanonRulesPanel.tsx`, composition `ProgressPanel.tsx`) accept no `modelRef` and make no paid call, so a picker there would be a control wired to nothing (a SET-* "stored-but-unread" defect). Consequently only `quality-heal` is gated on Wave-0 X-1 (AddModelCta/DOCK-7).

(4) All four wrappers still call `useQualityWork(host.bookId, token)` + `QualityWorkGate` — one gate, one name (QC-2), even for `progress` in the `editor` category. Category ≠ gate.

(5) Spec hygiene (do this in the same slice so the next reader isn't misled): edit 31_quality_completion.md line 65 to read "thin wrappers, `useQualityWork` gate (+ the shared `ModelPicker` on `quality-heal` only — the other three make no paid call)".

Tests that make it true (a checklist item is done only when a test asserts its effect):
  • panelCatalogContract.test.ts: assert `catalog.find(p=>p.id==='progress').category === 'editor'` and the 3 new panels' category === 'quality'; keep/extend the X-2 assertion `every(p => CATEGORY_ORDER.includes(p.category))`.
  • QualityHubPanel.test.tsx: assert 7 `quality-hub-card-*` testids render AND `queryByTestId('quality-hub-card-progress')` is null.
  • Wrapper tests: assert the ModelPicker renders in QualityHealPanel and is ABSENT (queryByTestId/queryByRole null) in QualityCanonRulesPanel / studio ProgressPanel / QualityCorrectionsPanel; assert all four render the Work gate when `useQualityWork` is not `ready`.

*Evidence:* frontend/src/features/studio/panels/catalog.ts:266-270 (quality = hub + 4 rows) and :183-185 (chapter-browser/scene-browser/scene-inspector are category 'editor' — progress's neighbourhood); frontend/src/features/studio/panels/QualityHubPanel.tsx:13-18 (CARDS = 4 → 7); frontend/src/features/studio/palette/useStudioCommands.ts:20-22 (CATEGORY_ORDER missing 'quality' — X-2); ModelPicker mounted only where a paid run exists: QualityCriticPanel.tsx:71, QualityCoveragePanel.tsx:33; frontend/src/features/composition/components/PolishPanel.tsx:19,21,152 (takes modelRef prop ⇒ quality-heal's wrapper owns the picker), while grep for modelRef/ModelPicker in composition/components/ProgressPanel.tsx and CanonRulesPanel.tsx returns ZERO hits ⇒ no picker on those wrappers. Spec: docs/specs/2026-07-01-writing-studio/31_quality_completion.md:302 (QC-2), :563 (CARDS 4→7, progress NOT a card), :558 (category 'quality' ×3 + 'editor' ×1) vs the stale :65 file-fate row.

### Q-31-QC10-CHAPTER-PICKER-CONVENTION
CONVENTION (one, not two): every quality panel that needs a chapter owns a picker seeded from the manuscript hoist's active chapter, and never silently caps the list. IMPLEMENTATION: do NOT copy-paste 40 lines into quality-heal — extract the ONE shape that exists today into a shared component and have both panels consume it. Concretely:

1. NEW FILE `frontend/src/features/studio/panels/ChapterPicker.tsx` — lift QualityCriticPanel.tsx:20,33-70 verbatim: `const CHAPTER_PICKER_LIMIT = 500`, the `useQuery(['studio', <testIdPrefix>, 'chapters', bookId] , () => booksApi.listChapters(token, bookId, { sort: 'sort_order', limit: CHAPTER_PICKER_LIMIT }), { enabled: !!token })`, the `<select>` (option label `c.title || c.original_filename || '#'+c.sort_order`), and the truncation notice (`typeof data.total === 'number' && data.total > items.length` → `t('quality.chaptersTruncated', …)`). Props: `{ bookId, value, onChange, testIdPrefix }`. Test-ids stay parameterised: `${testIdPrefix}-chapter-picker`, `${testIdPrefix}-chapters-truncated` — so the existing assertion `quality-critic-chapter-picker` (QualityCriticPanel.test.tsx:81) keeps passing unchanged. Reuse the SAME i18n keys (`quality.pickChapter`, `quality.chaptersTruncated`) — one name for one concept.

2. FIX THE SPEC'S FACTUAL SLIP — QC-10 says the shape "defaults to the manuscript hoist's active chapter", but the code does NOT: `QualityCriticPanel.tsx:31` inits `useState('')` and renders the `quality-critic-no-chapter` hint. Build the default INTO the shared ChapterPicker (not into quality-heal alone — that is exactly the "two conventions" AN-8 forbids): inside ChapterPicker, `const busChapterId = useStudioBusSelector((s) => s.activeChapterId)` (host/types.ts:36; StudioHostProvider.tsx:161) and SEED-ONCE — when `value === ''` and the user has not yet picked (a `pickedRef` set in `onChange`) and `busChapterId` is present in the loaded `items`, call `onChange(busChapterId)`. After an explicit user pick the panel STOPS following the bus (a picker that yanks itself every time the editor scrolls to another chapter is a bug, not a default). If the bus has no active chapter, keep today's empty state + `quality.pickChapterHint`.

3. `QualityCriticPanel.tsx` becomes `<ChapterPicker bookId={host.bookId} value={chapterId} onChange={setChapterId} testIdPrefix="quality-critic" />`; the new `QualityHealPanel.tsx` uses the identical line with `testIdPrefix="quality-heal"`, and so does any further quality panel that operates per-chapter. Invent nothing else — no per-panel picker variants, no separate confirmation convention.

4. TESTS — new `frontend/src/features/studio/panels/__tests__/ChapterPicker.test.tsx`: (a) seeds from bus `activeChapterId` when it is in the list; (b) an explicit user selection is NOT overridden by a later bus change; (c) the truncation notice renders when `total > items.length` and is absent otherwise; (d) no bus chapter ⇒ empty value. Existing QualityCriticPanel/QualityHealPanel tests keep asserting their own prefixed test-ids.

WHY extract rather than "copy verbatim": this repo's own gate hook states the rule — `useQualityWork.ts:1-2,20-22` ("One implementation, for every consumer… three independent re-derivations of one gate is exactly what SDK-First exists to stop"). A duplicated picker is the same class of drift AN-8 is aiming at; extraction preserves the convention with ONE implementation. PO default (veto-able): seed-once-then-stop-following.

*Evidence:* frontend/src/features/studio/panels/QualityCriticPanel.tsx:20-70 (the picker shape to lift; note :31 `useState('')` — the hoist default the spec claims exists does NOT) · frontend/src/features/studio/panels/__tests__/QualityCriticPanel.test.tsx:81 (asserts `quality-critic-chapter-picker` — keep the id) · frontend/src/features/studio/panels/useQualityWork.ts:1-2,20-22 ("One implementation, for every consumer… three independent re-derivations of one gate is exactly what SDK-First exists to stop") · frontend/src/features/studio/host/types.ts:36 + host/StudioHostProvider.tsx:161 (`activeChapterId` on the bus via `useStudioBusSelector`) · frontend/src/features/studio/manuscript/unit/ManuscriptUnitProvider.tsx:321 (the hoist reads the same slice)

### Q-31-DOD7-SESSION-BOOKKEEPING
Do the bookkeeping PER-MILESTONE (not saved up for M4's SESSION), in `docs/sessions/SESSION_HANDOFF.md` only (default v2.2 mode — `docs/deferred/DEFERRED.md` is the AMAW-mode file; do not touch it). Four concrete edits:

(1) AT M3 SESSION — CORRECT, don't just move, the `D-QUALITY-CRITIC-HEAL-LINK` row at SESSION_HANDOFF.md:3371. It is ALREADY struck as "RESOLVED 2026-07-01" and that is FALSE: the fix shipped only on the legacy `PolishPanel`; the Studio's `QualityCriticPanel.tsx:80` mounts `<QualityReportSection>` with NO `proposals` prop, so `_hasProposedFix()` cannot fire for a Studio user. Rewrite that bullet to: "~~D-QUALITY-CRITIC-HEAL-LINK~~ — **RESOLVED (legacy) 2026-07-01; RESOLVED (Studio) at spec-31 M3.** The 2026-07-01 fix shipped the consumer on the legacy PolishPanel only — `QualityCriticPanel.tsx` mounted `QualityReportSection` without `proposals`, so the badge was dead code in the Studio. M3's `quality-heal` panel + passing `proposals` into `QualityCriticPanel` closes it. Proven by effect: Playwright `studio-quality.spec.ts` asserts `[data-testid="violation-has-fix"]` visible after Apply." Do NOT write this line before the Playwright assertion actually passes — a second false RESOLVED on the same row is the bug this repo already shipped once.

(2) AT M1 SESSION — flip the 00C Q-3 row (`00C_POST_ARCHITECTURE_QUEUE.md:35`) status cell from "📐 superseded by spec 31" to "✅ **CLEARED** — (a) `progress` + (b) `quality` correction-stats ported to Studio panels by spec 31 (M1/M4); (c) `threads` deleted, not ported, per 21's audit", and add to the writing-studio track's *Recently cleared* line: "00C **Q-3(a)** (progress port, M1) · **Q-3(b)** (corrections port, M4)". Q-3(a) clears at M1, Q-3(b) only at M4 — file each when its milestone lands, not both early.

(3) AT M4 SESSION (or earlier as each is confirmed) — append these FOUR rows verbatim to the EXISTING `### Deferred (from plan 30 — consciously parked, each with its gate reason)` table at SESSION_HANDOFF.md:95 (same `| ID | What | Gate |` shape; no new section):

| **D-31-OQ1-COMPOSE-PROPOSE-EDIT-CORRECTION** | Spec 31 OQ-1 (origin: M4/BE-9). A Studio-Compose `propose_edit` Apply/Dismiss records NO correction: it has no `job_id` and its prose came from a **chat-service** turn, not a composition `generation_job`. **v1 answer = option (c): the flywheel learns only from STRUCTURED generation** (engine + authoring runs); Compose prose is out. Revisit when Compose's prose path is itself specced. | #2 large/structural — (a) minting a `generation_job` for a chat turn is cross-service; (b) a nullable `chat_run_id` + FK relax is a migration. Target: the Compose-prose spec. |
| **D-31-OQ2-HEAL-CORRECTION-KIND** | Spec 31 OQ-2 / QC-5 (origin: M3). Self-heal accept/reject is NOT a `generation_correction` in v1. The CHECK is closed on `('edit','pick_different','regenerate','reject')`; adding `heal_accept`/`heal_reject` is a migration AND correcting *a fix* is a different signal from correcting *a draft* — folding it into the draft flywheel corrupts the denominator BE-9c exists to fix. | #5 conscious won't-fix for v1. Trigger: a decision that the heal-gate signal is worth its own table/denominator. |
| **D-31-OQ3-QUALITY-ACTION-COST-ESTIMATE** | Spec 31 OQ-3 / QC-7 / BE-Q4 (origin: M3). Run Polish · Analyze quality · Coverage are PAID with no cost estimate — a live gap across three already-shipped panels, not this wave's regression. Fix = `composition.self_heal_propose` (+ `.quality_report`) descriptors on the **generic** `GET /actions/preview` → `POST /actions/confirm` spine. **Do NOT invent `/self-heal/estimate`** — three such per-action routes already 404 in production (plan-30 §3.3). | #2 large/structural — a descriptor spine, not a route. Target: BE-Q4 / v2 cost-gate wave. |
| **D-31-OQ4-DISMISS-VIOLATION-MCP-TOOL** | Spec 31 OQ-4 (origin: M1/QC-9). After QC-9 the human can dismiss a false-positive canon violation; the agent cannot — `composition_dismiss_violation` has REST only, no MCP tool (a GG-2 inverse gap, one row). | #1 out of scope — this wave closes GUI-for-tool gaps, not tool-for-GUI. Target: the GG-2 inverse-gap sweep (with D-WIKI-INVERSE-GAP). |

(4) OQ-5 and the two UNVERIFIED rows are NOT deferred and must NOT be filed here: OQ-5 is decided at PLAN (the panel ships either way) and the two UNVERIFIEDs are BUILD-time checks (grep `daily_goal`; read learning-service's corrections consumer for burst behavior) — resolve them in M4's BUILD, and if either turns out to be a real defect, file it then as its own `D-31-*` row.

Rule for all four edits: no row is written before the thing it claims is true (a defer row states what is NOT done; a cleared row states what IS done and names the test that proves it). Work not recorded does not exist — and work falsely recorded as done is worse, which is exactly what line 3371 is today.

*Evidence:* frontend/src/features/studio/panels/QualityCriticPanel.tsx:80 — `<QualityReportSection projectId={work.projectId} chapterId={chapterId} token={accessToken} modelRef={modelRef} />` has NO `proposals` prop, so `_hasProposedFix()` is dead in the Studio — yet docs/sessions/SESSION_HANDOFF.md:3371 already reads `~~D-QUALITY-CRITIC-HEAL-LINK~~ — RESOLVED 2026-07-01`. Corroborated by docs/specs/2026-07-01-writing-studio/30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md:269 ("QualityCriticPanel.tsx:80 mounts <QualityReportSection> without the proposals prop, so _hasProposedFix() can never fire for a Studio user"). Target table for the OQ rows already exists at docs/sessions/SESSION_HANDOFF.md:95 (`### Deferred (from plan 30 …)`, `| ID | What | Gate |`); the 00C Q-3 row is docs/specs/2026-07-01-writing-studio/00C_POST_ARCHITECTURE_QUEUE.md:35; the OQ texts + gates are docs/specs/2026-07-01-writing-studio/31_quality_completion.md:735-738 and the DoD itself is :726-727.

### Q-31-F-Q10-KIND-INVERSE-GAP
CONFIRMED as stated, with one design call the spec left open: `kind` is a FREE-TEXT label, NOT an enum — render a plain text input, do NOT invent a closed set.

Evidence for that call: the column is `kind TEXT` with **no CHECK constraint** (`services/composition-service/app/db/migrate.py:254` — contrast `outline_node.kind` at :196 and `motif.kind` at :704, which DO carry CHECKs); the Pydantic model is `kind: Annotated[str, StringConstraints(max_length=100)] | None` (`app/db/models.py:290`); the router accepts `kind: str | None` (`app/routers/canon.py:41`, `:48`); the MCP tool takes free `str | None` (`app/mcp/server.py:1069-1076`). Nothing downstream reads it — `packer/lenses.py:92-100 gather_canon` packs rule *text*, never `kind`. So the Frontend-Tool-Contract "closed-set arg ⇒ enum" rule does **not** apply here (there is no closed set to enforce), and a `<select>` would fabricate a taxonomy the backend does not have.

BUILD INSTRUCTION (zero backend, ~30 lines, one wave slice — belongs to M1 Lane-B canon handler per 31 §"Closes"):

1. `frontend/src/features/composition/types.ts` — in `export type CanonRule` (currently ends at `version: number;` around :345-354) add the two fields the BE has always returned (`_SELECT_COLS` in `app/db/repositories/canon_rules.py:26-28` includes both):
   ```ts
   kind: string | null;
   is_archived: boolean;
   ```
   (`is_archived` is also the field M1's showArchived/restore work needs — spec 31 line 58.)

2. `frontend/src/features/composition/components/CanonRuleForm.tsx`
   - `CanonRulePayload` (:11-18) += `kind: string | null;`
   - add `const [kind, setKind] = useState<string>(initial?.kind ?? '');`
   - render, in the existing `flex flex-wrap items-center gap-2` row right after the scope `<select>`:
     ```tsx
     <input
       data-testid="composition-canon-kind"
       list="composition-canon-kind-options"
       className="rounded border border-neutral-300 bg-transparent px-2 py-1 text-xs dark:border-neutral-600"
       maxLength={100}
       value={kind}
       onChange={(e) => setKind(e.target.value)}
       aria-label={t('kind', { defaultValue: 'Kind' })}
       placeholder={t('kindPlaceholder', { defaultValue: 'kind (optional)' })}
     />
     <datalist id="composition-canon-kind-options">
       {knownKinds.map((k) => <option key={k} value={k} />)}
     </datalist>
     ```
     with a new prop `knownKinds: string[]` (default `[]`). `CanonRulesPanel.tsx` supplies it from the rules it already has: `Array.from(new Set(rules.map(r => r.kind).filter((k): k is string => !!k))).sort()`. The datalist is a *suggestion* list only — it must not restrict input (free-text stays free-text; this just stops label drift).
   - in `submit()` add `kind: kind.trim() || null,`. Sending `null` on edit is correct and intentional: `kind` is in `_NULLABLE_UPDATE_COLUMNS` (`canon_rules.py:33-35`), so an empty field CLEARS the label rather than being ignored.

3. Nothing else changes: `compositionApi.createCanonRule/patchCanonRule` already take `Partial<CanonRule>` (`frontend/src/features/composition/api.ts:570-577`) and `useCanonRules` already forwards the payload verbatim — widening the type is enough to carry `kind` end-to-end.

4. TEST (Definition of Done for the slice): extend `frontend/src/features/composition/components/__tests__/CanonRulesPanel.test.tsx` with two cases — (a) type into `composition-canon-kind`, submit, assert the `create` mutation was called with `kind: 'magic-system'`; (b) edit an existing rule whose `kind` is set, clear the input, submit, assert the PATCH body carries `kind: null` (the clear path). Plus `/review-impl` at wave close per the run policy.

Contradicts no §0 sealed decision: this is a FE-only type+form widening over an API surface that already exists.

*Evidence:* services/composition-service/app/db/migrate.py:254 (`kind TEXT` — nullable, NO CHECK, unlike outline_node.kind:196 / motif.kind:704) · app/db/models.py:290 (`kind: str max_len 100 | None`) · app/routers/canon.py:41,48 (CanonRuleCreate.kind / CanonRulePatch.kind) · app/db/repositories/canon_rules.py:26-35 (kind in _SELECT_COLS, _UPDATABLE_COLUMNS and _NULLABLE_UPDATE_COLUMNS ⇒ null clears) · app/mcp/server.py:1074 (agent CAN set it) · app/packer/lenses.py:92-100 (gather_canon packs text only — no consumer of `kind`) · frontend/src/features/composition/types.ts:345-354 (CanonRule omits kind + is_archived) · frontend/src/features/composition/components/CanonRuleForm.tsx:11-18 (CanonRulePayload drops it)

### Q-31-GATEWAY-ZERO-CHANGES
CLAIM CONFIRMED — the spec is correct: ZERO gateway work for BE-11a / BE-P2 / BE-9d, or any other new route in this wave. The whole chain is prefix-generic with no per-route registration: vite dev proxy `/v1` -> :3123 (frontend/vite.config.ts:33); nginx prod `location /v1/` -> api-gateway-bff:3000 (frontend/nginx.conf:30); the BFF's composition proxy uses `pathFilter: (pathname) => pathname.startsWith('/v1/composition')` with NO `pathRewrite` key present (gateway-setup.ts:350-354) and is dispatched at gateway-setup.ts:657. A new route is auto-proxied the moment it exists.

BINDING RULE FOR EVERY BUILDER IN THIS WAVE (this is the condition the claim silently depends on):
1. MOUNT UNDER THE PREFIX. Any new FE-reachable Studio route MUST live on a router declared `APIRouter(prefix="/v1/composition")` (or a sub-prefix such as `/v1/composition/actions`), and MUST be registered via `app.include_router(...)` in services/composition-service/app/main.py (the block at lines 215-245). Do NOT invent `/v1/studio/*` or `/v1/quality/*` — the gateway matches the LITERAL prefix, so such a route falls through to `next()` at gateway-setup.ts:666 and 404s at the edge while every composition-service unit test stays green. This is the only way to get the "no gateway work" claim wrong.
2. AUTH IS PER-ROUTE, IN THE SERVICE — NOT AT THE GATEWAY. The proxy forwards the `Authorization` header raw and verifies nothing. Every new `/v1/composition/*` route MUST declare `Depends(get_current_user)` (app/middleware/jwt_auth.py) and, where a book/project is addressed, `authorize_book` (app/grant_deps.py) — mirror services/composition-service/app/routers/conformance.py:57-58. Omitting them ships a PUBLIC UNAUTHENTICATED route (a tenancy defect), and no gateway layer will catch it.
3. SSE needs no work — `selfHandleResponse: false` (gateway-setup.ts:353) already streams composition SSE un-buffered; new SSE routes inherit it. Edge rate-limiting (gateway-setup.ts:568) is global and also applies automatically.
4. `/internal/*` IS DELIBERATELY NOT PROXIED — the dispatcher has no `/internal` branch. If BE-9d needs an FE-reachable route it must be `/v1/composition/*`, NOT `/internal/composition/*`. (`/v1/jobs` has its own generic proxy at gateway-setup.ts:663, so jobs-service polling is likewise covered with zero work.)

TEST TO PIN IT (M1 BUILD, ~10 lines, cheap): add a case to the gateway proxy spec asserting `pathFilter('/v1/composition/<new-route>')` is true AND that the composition proxy config exposes no `pathRewrite`; plus, in composition-service, a route-table test asserting every router in main.py's public include_router list carries a path starting `/v1/composition`. That converts this verified-once claim into a standing guard against rule #1.

*Evidence:* services/api-gateway-bff/src/gateway-setup.ts:350-354 — `createProxyMiddleware({ target: urls.compositionUrl, changeOrigin: true, selfHandleResponse: false, pathFilter: (pathname: string) => pathname.startsWith('/v1/composition'), ... })` — no `pathRewrite` key in the object. Dispatch: gateway-setup.ts:657-659 `if (req.path.startsWith('/v1/composition')) return compositionProxyFn(req, res, next);`. Fall-through: gateway-setup.ts:666 `return next();`. Prefix contract upstream: services/composition-service/app/main.py:215-245 (include_router block) + `grep 'APIRouter(prefix=' app/routers/*.py` shows all 25 public routers on `/v1/composition` (only internal_eval.py:26 / ping.py:7 use `/internal`). Edge proxies: frontend/vite.config.ts:33 (`'/v1' -> localhost:3123`), frontend/nginx.conf:30 (`location /v1/ -> api-gateway-bff:3000`). Auth-in-service (not gateway): services/composition-service/app/routers/conformance.py:57-58 (`from app.grant_deps import authorize_book`; `from app.middleware.jwt_auth import get_current_user`).

### Q-31-QC9-DISMISS-VIOLATION
The "ZERO backend" claim is TRUE — verified against the route, its body model, the read query, and the MCP lane. Build it as a FE-only additive affordance in M1.

WHY ZERO BACKEND (all four legs check out):
1. Request shape = exactly what RuleRow already holds. `POST /jobs/{job_id}/dismiss-violation` (engine.py:1684) takes ONE path param (`job_id`) and `DismissBody{rule_id: str}` (engine.py:194-195). Nothing else. `RuleViolationItem` carries both `job_id` and `rule_id` (frontend/src/features/composition/types.ts:92-102), and the panel already destructures them (QualityCanonPanel.tsx:108).
2. The read path ALREADY honours a dismiss. `OutlineRepo.rule_violations` filters `(e.value -> 'dismissed') IS DISTINCT FROM 'true'::jsonb` in BOTH the exact-count query and the row query (outline.py ~1305 and ~1337). So a refetch removes the row AND fixes `ruleCount`/`ruleCapped`. No new column, no new route, no migration.
3. Agent parity is free: `composition_diagnostics` reads the same repo (mcp/server.py:4040), so a human dismiss also silences the agent's `broken_canon_rule` diagnostic. No second write path.
4. Auth already correct: the route gates `_gate_work(..., GrantLevel.EDIT)` on the job's OWN project→book (PM-8), which the Studio book owner has.

BUILDER INSTRUCTIONS (M1, FE only):
A. `frontend/src/features/studio/panels/useQualityCanon.ts` — add a `useMutation` calling `compositionApi.dismissViolation(jobId, ruleId, accessToken!)` (frontend/src/features/composition/api.ts:562). `onSuccess` → `queryClient.invalidateQueries({ queryKey: ['studio','quality-canon','rules', projectId] })` (the exact key at useQualityCanon.ts:84). Expose on `QualityCanonView`: `dismissRule(jobId, ruleId)`, `dismissPending`, `dismissError`. Do NOT reuse `useCritique`'s `dismiss` (features/composition/hooks/useCritique.ts:10) — it is CriticPanel-scoped and does not invalidate the studio key (the `invalidateQueries-cannot-reach-hand-rolled-state` class).
B. `QualityCanonPanel.tsx` — in `RuleRow` (lines 164-182) add a `DismissButton` beside `JumpButton`, `data-testid="quality-canon-dismiss"`, label `t('quality.dismissViolation', { defaultValue: 'Dismiss' })`, disabled while pending. Render it only when `r.rule_id` is truthy (defensive: `critic._filter_violations` at critic.py:85 already drops any violation with an empty/missing `rule_id`, so in practice it is always present — the `| null` in the TS type is belt-and-braces). Wire it from the `.map` at lines 107-111.
C. NO optimistic row removal. The backend loops and marks EVERY violation in that job matching that `rule_id` (engine.py:1700-1706), while rows are flat per (scene × violation) — one click can legitimately clear two rows. Invalidate + refetch is the only correct refresh.
D. Fail LOUD, never silent: the route 404s `violation not found` when a newer critique overwrote `critic` (engine.py:1707) and 403s for a VIEW-only grantee. On mutation error render an explicit banner (`data-testid="quality-canon-dismiss-error"`, reuse the existing `WARN` class) and keep the row visible — a dismiss that appears to work but didn't is the repo's `silent-success-is-a-bug` class.
E. Tests — `frontend/src/features/studio/panels/__tests__/QualityCanonPanel.test.tsx`: (1) click dismiss → `compositionApi.dismissViolation` called with `(job_id, rule_id, token)` and the rules query refetches; (2) mutation rejects → error banner shown AND the row still rendered; (3) a row with `rule_id: null` renders no dismiss button. Backend needs no new test — `services/composition-service/tests/unit/test_engine_router.py:804` (200 + `dismissed:true`) and `:811` (404 on unknown rule) already cover it.
F. i18n: `quality.*` keys in this panel all pass `defaultValue`, so the button is functional immediately; still add `quality.dismissViolation` to the `en` studio locale and gap-fill with `scripts/i18n_translate.py`.

DEFAULT THE PO CAN VETO: dismiss is a plain button with no confirm dialog and no undo (a re-critique re-raises the violation anyway, since `critic` is overwritten on the next `POST /critique`).

*Evidence:* services/composition-service/app/routers/engine.py:1684-1710 (route) + :194-195 (`DismissBody{rule_id: str}` — the entire request body); services/composition-service/app/db/repositories/outline.py:1257-1372 (`rule_violations` already filters `(e.value -> 'dismissed') IS DISTINCT FROM 'true'::jsonb` in both count and rows); services/composition-service/app/engine/critic.py:78-93 (`_filter_violations` guarantees a non-empty `rule_id` on every stored violation); frontend/src/features/composition/api.ts:562-566 (`dismissViolation` client already exists); frontend/src/features/studio/panels/QualityCanonPanel.tsx:107-111,164-182 (RuleRow has `r.job_id` + `r.rule_id`, no dismiss button); frontend/src/features/studio/panels/useQualityCanon.ts:83-87 (the query key to invalidate); services/composition-service/app/mcp/server.py:4040 (diagnostics reads the same repo ⇒ agent parity free); services/composition-service/tests/unit/test_engine_router.py:804,811 (BE already tested)

### Q-31-QC7-NO-BESPOKE-ESTIMATE-ROUTE
HOLD THE TRAP — ship M3 `quality-heal` with NO cost-estimate route, and add ZERO new backend routes in this wave.

Builder instruction (no further thought needed):
1. `quality-heal` is a pure FE port. Create `frontend/src/features/studio/panels/QualityHealPanel.tsx` by porting `frontend/src/features/composition/components/PolishPanel.tsx` + `frontend/src/features/composition/hooks/usePolishProposals.ts`, calling the EXISTING `compositionApi.selfHealPropose` (`frontend/src/features/composition/api.ts:487-500`) → `POST /v1/composition/works/{project_id}/self-heal/propose` (`services/composition-service/app/routers/plan.py:199`). The 202+poll path is already sound — `GET /jobs/{job_id}` exists (`services/composition-service/app/routers/engine.py:1415`), so this paid action does NOT reproduce the motif-mine "pay + spin forever 404" defect. Verified, so the critical-blocker gate is not tripped.
2. Do NOT create `/self-heal/estimate`, `/actions/self_heal_propose/estimate`, or any other per-action estimate route. The composition action spine has exactly two routes — `GET /v1/composition/actions/preview` (`actions.py:183`) and `POST /v1/composition/actions/confirm` (`actions.py:213`) — and the FE already ships a call to an invented `POST /v1/composition/actions/conformance_run/estimate` that 404s (plan-30 §3.3 line 152). A fourth invented route is the exact bug class.
3. The v1 cost controls the panel MUST carry (they ARE the answer to "no estimate"), all already present in the source panel: (a) an explicit "Run Polish" button — no auto-run on mount or on chapter change; (b) the explicit `ModelPicker` — `model_source` + `model_ref` are REQUIRED fields (`plan.py:185-196`), never defaulted silently; (c) the `rerank` toggle defaulting OFF (`plan.py:196` `rerank: bool = False`) with its existing label "auto-tick (AI, costs more)". Port all three verbatim; a reviewer finding any of them missing or auto-enabled fails the wave.
4. Permitted (and the only) concession: one STATIC helper line of copy under the button, e.g. "Runs LLM passes on this chapter — costs tokens." Literal text only, no fetch, no route, no number.
5. Track the real fix, do not silently drop it. Defer row to add to `docs/deferred/DEFERRED.md` + SESSION_HANDOFF:
   `BE-Q4 / OQ-3 — origin: Studio Wave M3 (quality-heal) — the paid quality actions (self-heal propose, quality-report, coverage) have no cost estimate. Fix = add `composition.self_heal_propose` (+ `.quality_report`) Tier-W descriptors to the GENERIC confirm spine (`actions.py` `_ALL_DESCRIPTORS`, line ~96) so the existing `GET /actions/preview` $-dialog covers them — NOT a per-action route. Gate reason: #2 large/structural (new descriptors + propose-tool minting + billing precheck across 3 shipped panels; it is a pre-existing gap, not a regression this wave introduces). Target: v2 / the next composition cost-gate wave.`

Default I am picking on the PO's behalf (veto if you disagree): v1 users see no dollar figure before Run Polish. That matches the three already-shipped panels' behavior today, so the Studio port introduces no new cost-visibility regression.

*Evidence:* services/composition-service/app/routers/actions.py:183 + :213 — the spine has ONLY `GET /preview` and `POST /confirm` (no per-action estimate); plan-30 §3.3 line 152 shows the FE already calling a non-existent `POST /v1/composition/actions/conformance_run/estimate` (404 in prod). The action being ported: services/composition-service/app/routers/plan.py:199 `POST /works/{project_id}/self-heal/propose` with `rerank: bool = False` (plan.py:196) and required `model_source`/`model_ref` (plan.py:187-188); FE caller frontend/src/features/composition/api.ts:487-500; poll target services/composition-service/app/routers/engine.py:1415 `GET /jobs/{job_id}` (exists ⇒ not a pay-for-nothing defect).

### Q-31-DOD4-LIVE-BROWSER-SMOKE
DoD #4 STAYS MANDATORY — it is buildable work, not a question, and the "environmental prerequisites" it worries about are already solved in this repo. Build it exactly like this (the spec's own wording is corrected on 3 points, all grounded in code):

**(1) FILE PATH — the spec's path is WRONG and would silently never run.** `frontend/playwright.config.ts:9` sets `testDir: './tests/e2e/specs'`. A file at `frontend/e2e/studio-quality.spec.ts` is NOT collected → a green run that tested nothing (exactly the false-green class this DoD exists to kill). The file is **`frontend/tests/e2e/specs/studio-quality.spec.ts`**. Amend the DoD text in `31_quality_completion.md:699` (and grep the other seven specs 32–38 for the same `frontend/e2e/` string and fix them too — they were written from the same wrong template).

**(2) THE 4-PANEL AGENT TURN — do NOT drive a live lm_studio model; use the repo's SEALED injection pattern.** `frontend/tests/e2e/helpers/frontendToolInject.ts:11-21` states the rule this repo already adopted: *"We must NOT depend on a local model *choosing* to emit a given frontend tool (S06 showed that choice is non-deterministic). So this helper INJECTS a suspended frontend-tool call … The FE then runs its REAL executor/resolver/card … The only simulated part is the *trigger*; every line of FE execution under test is real."* That preserves 100% of the property the PO is protecting — the panel_id-enum bug shipped because `shown:true` was asserted instead of the DOM; injection still asserts the DOM. Concretely, for each of the 4 new ids (`quality-canon-rules`, `progress`, `quality-corrections`, `quality-heal`):
```ts
await installFrontendToolSuspend(page, { tool: 'ui_open_studio_panel', args: { panel_id: '<id>' } });
await sendChat(page, 'open <name>');
await expect(page.getByTestId('studio-<id>-panel')).toBeVisible({ timeout: 15000 });
```
(testid convention confirmed at `QualityCriticPanel.tsx:44` → `data-testid="studio-quality-critic-panel"`; each of the 4 new panels MUST carry `studio-<panel-id>-panel`.) Model-choice correctness (the model can't invent `panel:"editor"`) is proven deterministically by the closed-set enum + the 61==61==61 three-way contract guard already in DoD #2 — that is the right tool for that risk, not a flaky LLM turn. **Default I am setting (PO may veto): the "$0 local lm_studio agent turn" is dropped as a hard prerequisite** — removing the "lm_studio must be running" dependency is precisely what makes this DoD actually get run instead of skipped for the third time. Copy the spec pattern from `frontend/tests/e2e/specs/frontend-tools-liveness.spec.ts` (login, `createBook`/`createChapter`, seeded session with the `last_message_at` bump — the fresh-session-NULLS-LAST trap is already handled there at :62-71).

**(3) THE MODEL-LESS ACCOUNT (f) — no second account.** `useUserModels.ts:40` → `aiModelsApi.listUserModels` → `frontend/src/features/ai-models/api.ts:124` = `GET /v1/model-registry/user-models`. Simulate zero models with `await page.route('**/v1/model-registry/user-models*', r => r.fulfill({ json: { items: [] } }))` before opening `quality-heal`, then click the `AddModelCta` link (`ModelPicker.tsx:388`) and assert `studio-dock` is still visible (dock NOT torn down = X-1's DOCK-7 guard).

**(4) The other four legs are written as-is, all as DOM-effect assertions:** canon round-trip (create→edit→archive→Show archived→restore, via `StudioPage.openPanel('quality-canon-rules', …)` — the palette path already exists at `StudioPage.ts:41-51`); the `quality-canon` → *Edit rule* → `quality-canon-rules` focused-on-rule-id deep link (extend the existing `focusRuleId` seam, do not rebuild it); the heal loop ending in `await expect(page.getByTestId('violation-has-fix')).toBeVisible()` inside `quality-critic` (= D-QUALITY-CRITIC-HEAL-LINK closed by effect); the stale guard (Polish → type in editor → Apply → stale banner visible AND editor text unchanged).

**(5) The rebuilt-image prerequisite is REAL and stays** — `frontend/tests/e2e/README.md:36-40`: the container serves a baked bundle, so the wave's VERIFY step is literally `cd infra && docker compose build frontend && docker compose up -d frontend` before `npm run e2e -- studio-quality`, and the evidence string must name the image build. A host `vite dev` on :5174 SHADOWS the baked image — if the builder uses vite dev instead, say so explicitly in the evidence rather than claiming the built image was tested.

**Wave 1 DoD is not satisfiable without this spec file existing and passing; it is not a defer candidate** (it fails all 5 gates — in scope, small, buildable today with helpers that already exist).

*Evidence:* frontend/playwright.config.ts:9 (`testDir: './tests/e2e/specs'` — the spec's `frontend/e2e/…` path would never be collected) · frontend/tests/e2e/helpers/frontendToolInject.ts:11-21 (sealed repo rule: do NOT depend on a local model choosing to emit the tool; inject the suspended call, assert the real FE effect) · frontend/tests/e2e/specs/frontend-tools-liveness.spec.ts:88-103 (the working template: inject → sendChat → assert effect + resume round-trip) · frontend/src/features/studio/panels/QualityCriticPanel.tsx:44 (`data-testid="studio-quality-critic-panel"` — the panel-testid convention to mirror) · frontend/src/components/model-picker/useUserModels.ts:40 + frontend/src/features/ai-models/api.ts:124 (`GET /v1/model-registry/user-models` — the single route to stub `{items:[]}` for the DOCK-7 model-less case) · frontend/src/components/model-picker/ModelPicker.tsx:388 (AddModelCta call site) · frontend/tests/e2e/pages/StudioPage.ts:41-51 (`openPanel` via Command Palette) · frontend/tests/e2e/README.md:36-40 (rebuild-the-image prerequisite) · docs/specs/2026-07-01-writing-studio/31_quality_completion.md:699 (the wrong path to amend)

### Q-31-DOD6-REVIEW-IMPL
UPHELD, and made mechanical — but the spec's live-smoke recipe names the WRONG second service and the gate that was supposed to catch that will stay silent. Three concrete builder instructions:

(1) /review-impl scope — the PO run policy is STRICTER than DoD #6 and supersedes it: "/review-impl runs at the completion of EVERY wave, and any bug it finds is fixed before the wave closes." Bake it in as a literal DoD step in EACH of M1..M4 (not only M4/BE-P2), i.e. the last line of every milestone's DoD becomes: "`/review-impl` run at milestone close; every finding fixed or filed as a defer row before the milestone commits." M2 (BE-P2, tenancy boundary — `composition_progress_goal` PK `(user_id, project_id)`) and M4 (DDL column on `authoring_run_units` + a cross-service write path) are the two where it is non-negotiable per the spec; the other two get it per the run policy. No PO checkpoint is added — /review-impl is a self-run subagent gate, not a human stop.

(2) M4's live-smoke token will NOT be prompted for — type it anyway. `scripts/workflow-gate.py::_check_live_smoke_evidence` only warns when `git diff --name-only HEAD` touches ≥2 distinct `services/<name>/` prefixes. M4's diff touches ONLY `services/composition-service/` (+ `frontend/`, `contracts/`) — frontend/contracts are explicitly not counted — so the gate emits nothing and a builder who trusts it will ship M4 mock-only. The `live smoke:` token in the VERIFY evidence string for M4 is therefore a HAND-TYPED, hard DoD item, not a gate output.

(3) Fix the recipe: M4's cross-service seam is composition-service → the generic outbox relay → **learning-service**, NOT "book-service" as DoD #5 / M4's DoD currently says (book-service has no part in `composition.generation_corrected`; it appears only in M1's canon-rule E0 grant check). The M4 live-smoke one-liner the builder must actually run and paste:
  a. stack up (rebuilt composition-service image — stale image = false green), sign in as `claude-test@loreweave.dev`;
  b. drive an authoring-run unit `reject_unit` through the real API (or `composition_record_correction` MCP tool);
  c. assert in `loreweave_composition`: exactly ONE `generation_correction` row with `kind='reject'` and a non-NULL `job_id`, plus ONE `outbox_events` row `event_type='composition.generation_corrected'` written in the same txn;
  d. assert the relay drained it → `XRANGE loreweave:events:composition` shows the message carrying an `outbox_id` field;
  e. assert learning-service's `learning-collector` group consumed it → a row landed in learning-service's `corrections` table keyed on that `outbox_id`.
  Evidence string: `live smoke: reject_unit → generation_correction(job_id=…) + outbox row same-txn → loreweave:events:composition XADD(outbox_id=…) → learning-service corrections row <id>`.
  Also settle the spec's own UNVERIFIED note here: run a Revert-All over ≥5 units in the same smoke and confirm the burst does not DLQ (learning consumer retries→DLQ, it does not ack-on-error).
If (d) or (e) cannot be brought up at dev time, the ONLY acceptable fallbacks are the gate's other two tokens — `LIVE-SMOKE deferred to D-M4-CORRECTION-LIVE-SMOKE` (with the row written) or `live infra unavailable: <reason>`. A green mock test is not one of them.

*Evidence:* scripts/workflow-gate.py:234-241 — `re.match(r"^services/([^/]+)/", path)` over `git diff --name-only HEAD`, `if len(services) < 2: return` ⇒ M4 (composition-service + frontend only) never triggers the live-smoke WARN; it is soft/advisory anyway ("This is a soft warning only; the verify phase IS marked complete", :255). services/composition-service/app/db/repositories/generation_corrections.py:89,137-140 — `async with conn.transaction():` … `await outbox.emit(event_type=outbox.GENERATION_CORRECTED)` (row + event, one txn) — the thing a mock test cannot prove. services/learning-service/app/events/consumer.py:44-49 — `STREAMS = [… "loreweave:events:composition" …]`, `GROUP_NAME = "learning-collector"` ⇒ the real second service on M4's write path is learning-service, not book-service (docs/specs/2026-07-01-writing-studio/31_quality_completion.md:721 and M4's DoD say "book-service").

### Q-31-DEEPLINK-EXTEND-NOT-REBUILD
EXTEND the existing seam — confirmed by code, do not rebuild. Build in 6 slices:

S1 (BE, composition-service — the ONE missing piece; `[show archived]` is NOT possible today): DELETE is a soft-archive (`app/db/repositories/canon_rules.py` `archive()` → `SET is_archived = true`) and BOTH list paths filter it out (`list_active`: `WHERE project_id=$1 AND active AND NOT is_archived`; `list_all:88`: `WHERE project_id=$1 AND NOT is_archived`). The `active_only` param at `app/routers/canon.py:108` toggles active-vs-all-NON-ARCHIVED — nothing returns an archived rule. Fix: `list_all(self, project_id, *, include_archived: bool = False)` — drop the `AND NOT is_archived` predicate when true; add `include_archived: bool = False` to the route (precedence unchanged: `active_only` still wins). No model/SQL work needed — `_SELECT_COLS` already selects `is_archived` and `db/models.py:293` already exposes it. TEST (`tests/unit/test_...canon*`): archived rule ABSENT by default, PRESENT with `?include_archived=true` carrying `is_archived: true`.

S2 (FE plumbing): `features/composition/types.ts:350` `CanonRule` gains `is_archived: boolean`; `api.ts:567` `listCanonRules(projectId, token, opts?: { includeArchived?: boolean })` appends `?include_archived=true`.

S3 (new panel `quality-canon-rules`): port `features/composition/components/CanonRulesPanel.tsx` + `hooks/useCanonRules.ts` (CRUD already complete — list/create/patch/remove) to `features/studio/panels/QualityCanonRulesPanel.tsx` + `useQualityCanonRules.ts`. Resolve `projectId` via `useQualityWork(bookId, token)` EXACTLY as `useQualityCanon.ts:79` does — do not re-derive the Work (that hook exists because this panel's sibling got it wrong once). REUSE the exported `CanonFocusParams` from `useQualityCanon.ts:27` — do NOT declare a second focus-param type or a second param name (one name, one concept). Lift `hoist()` (`useQualityCanon.ts:64`) into a shared `panels/focus.ts` and import it in both.

S4 (focus banner — copy the honesty rule verbatim from `QualityCanonPanel.tsx:136-162`, three branches, never an empty list that reads as success): (a) `focusRuleId` resolves to a live rule → hoist + highlight it, "Showing the rule you came from."; (b) resolves to NOTHING in the non-archived list → refetch with `includeArchived: true`; if found → "That rule was archived — [Show archived]" (the button flips `includeArchived`, rendering the row read-only; no restore — X-11); if still not found → "That rule no longer exists."; (c) list errored / work is `unknown` → "could not be checked" — never a not-found claim over an unconsulted list.

S5 (IN link): `QualityCanonPanel.tsx` `RuleRow` (:164) gains an "Edit rule" button, rendered ONLY when `r.rule_id` is non-null (`RuleViolationItem.rule_id` is nullable — `types.ts:96` — an unattributed violation has no rule to edit) → `host.openPanel('quality-canon-rules', { focus: true, params: { bookId: host.bookId, focusRuleId: r.rule_id } })`. Same param name = extension, not rebuild.

S6 (OUT badge + the honesty gate I am DECIDING, since the spec left it open — PO may veto): each rule row in `quality-canon-rules` shows "⚠ N broken" derived by grouping `compositionApi.getRuleViolations(projectId)` (`api.ts:600`) items by `rule_id`; click → `host.openPanel('quality-canon', { focus: true, params: { bookId, focusRuleId: rule.id } })`. BUT that payload is CAPPED at `RULE_VIOLATIONS_CAP = 200` (`repositories/outline.py:35`, `routers/outline.py:543`) and its exact `count` is the BOOK-WIDE total, not per-rule — so a per-rule count from a `capped: true` page is a LOWER BOUND. Rule: hits > 0 → the ⚠ badge; hits === 0 AND `capped` → a MUTED "not in the shown {{shown}} of {{total}}" chip that still deep-links (never "0 broken", never a green/clean affordance); hits === 0 AND NOT capped → render nothing (genuinely clean). Same suppression when the violations query errors or the Work is unknown. This is the paged-join-mislabels-absent bug class and is the exact false-clean `QualityCanonPanel` was built to avoid.

Also register `quality-canon-rules` in the studio panel registry + the DOCK-8 quality hub sibling list, add the `studio` i18n defaults, and add it to the `panel_id` ENUM in `chat-service/app/services/frontend_tools.py` + regenerate `contracts/frontend-tools.contract.json` (`WRITE_FRONTEND_CONTRACT=1 pytest`) — a closed-set arg with no enum is the silent-no-op bug. Tests: `features/studio/panels/__tests__/QualityCanonRulesPanel.test.tsx` mirroring the existing focus cases at `__tests__/QualityCanonPanel.test.tsx:190,205,280` (focused-hit / focused-resolves-to-nothing / focused-id-not-found), plus a capped-page test asserting NO "0 broken" is rendered for a rule missing from a truncated page.

*Evidence:* Seam exists (extend, don't rebuild): frontend/src/features/studio/panels/useQualityCanon.ts:27-31 (`CanonFocusParams`), :74 (`focusRuleId`), :107 (`hoist` on `r.rule_id === focusRuleId`), :115-123 (`ruleFocusHits`/`focusRuleText`); frontend/src/features/studio/panels/QualityCanonPanel.tsx:136-162 (three-branch honesty banner); frontend/src/features/studio/panels/PlanHubPanel.tsx:74 (first hop already ships). CRUD to port: frontend/src/features/composition/components/CanonRulesPanel.tsx + hooks/useCanonRules.ts. `[show archived]` blocked by a 6-line gap I am ordering built: services/composition-service/app/db/repositories/canon_rules.py:88 (`list_all` → `WHERE project_id = $1 AND NOT is_archived`) + :155 (`archive()` = soft delete) + services/composition-service/app/routers/canon.py:108-120 (only `active_only`, no `include_archived`), while app/db/models.py:293 already exposes `is_archived`. Capped OUT badge: frontend/src/features/composition/api.ts:600 + services/composition-service/app/routers/outline.py:526-546 + app/db/repositories/outline.py:35 (`RULE_VIOLATIONS_CAP = 200`, exact book-wide `count`, `capped` flag).

## Not a question (already answered by code / a sealed decision)
- **X-31-1-ADDMODELCTA-DOCK7** — NOT A QUESTION — an ordering prerequisite already sealed by plan 30 §8 X-1 ("fix at the shared component, not the ~8 call sites"), and the code confirms X-1 is unbuilt. Nothing for M3 to decide; the builder just has to land X-1 in Wave 0 before M3 (quality-heal) ships. Concrete instruction (no further thought needed):

X-1 — ONE FILE: frontend/src/components/shared/AddModelCta.tsx.
1. Add `import { useOptionalStudioHost } from '@/features/studio/host/StudioHostProvider';`.
2. In `AddModelCta()` (line 33), call `const studioHost = useOptionalStudioHost();` (returns null outside a dock — the hook is already null-safe, see StepConfig.tsx:44).
3. If `studioHost` is non-null, render a `<button type="button">` (NOT a `<Link>`) with the SAME classNames as the existing variant branches, whose onClick is `studioHost.openPanel('settings', { params: { tab: 'providers' } })` — this is plan 30 line 334's literal shape. (Equivalently `followStudioLink('/settings/providers', studioHost, { bookId: studioHost.bookId })`; studioLinks.ts:27+110-111 resolves `/settings/providers` to exactly that openPanel call. Either is fine — prefer the direct openPanel, it needs no ctx.) Ignore `returnTo` in the studio branch: there is no page to return to, and the `?return=` round-trip is meaningless inside a dock.
4. Keep the existing `<Link to={to}>` (with `?return=`) UNCHANGED as the else-branch — DefaultModelsCard.tsx:50, BuildGraphDialog.tsx:647, EmbeddingModelPicker.tsx:97, RerankModelPicker.tsx:58 all render it on legacy full pages and must keep the return-path behavior (verify-cycle-0.sh:31-34 greps for `/settings/providers` + `return=` in this file — do not delete either token or that gate reds).
5. TOUCH NO CALL SITE. ModelPicker.tsx:388 keeps `<AddModelCta capability={capability} variant="link" />` verbatim; every panel (quality-heal, PlannerPanel, the Pass Rail, Arc Deconstruct, Issues Feed) inherits the fix for free. Do NOT hand quality-heal a custom `emptyState` as a workaround — that forks the bug into 8 places.

TEST (add to the existing frontend/src/components/shared/__tests__/AddModelCta.test.tsx — the dockablePanelHygiene.test.ts grep is scoped to features/studio/panels/** and will NOT catch components/shared/, so the assertion must live here):
- existing 3 cases stay green (MemoryRouter, no host → anchor with href containing `/settings/providers?return=`);
- NEW: render inside a mocked StudioHostProvider (or `vi.mock('@/features/studio/host/StudioHostProvider', () => ({ useOptionalStudioHost: () => host }))` with `host = { openPanel: vi.fn(), bookId: 'b1' }`), assert (a) `container.querySelector('a')` is null — no router Link is rendered, and (b) clicking the CTA calls `host.openPanel` with `('settings', expect.objectContaining({ params: { tab: 'providers' } }))`. Run both `button` and `link` variants.

SEQUENCING for M3 (quality-heal): X-1 is Wave 0, M3 is Wave 3 — the wave gate ("Wave 0 gate: X-1, X-2, X-4, X-5, X-7 green", plan 30:345) already orders them. M3's DoD #4 DOCK-7 regression smoke (open quality-heal with zero BYOK chat models → click the Run-Polish empty-state CTA → assert the dockview layout survives and a `settings` panel opened with tab=providers) is then satisfiable as written. NO defer row, NO M3 scope change, and specifically do NOT ship M3's Run button gated-off (37_issues_feed.md:626's fallback) — X-1 is ~15 lines in one file, it is cheaper than carrying the workaround.
- **X-31-3-GUIDEBODYKEY** — NOT A QUESTION — it is X-3's Wave-0 work item, and the code already fixes its shape. Build it EXACTLY as follows (three edits, one slice, XS):

(1) TEST — extend `frontend/src/features/studio/panels/__tests__/panelCatalogContract.test.ts` (append inside the existing `describe('studio open-panel tool ↔ dock catalog contract')`, right after the `category` test at line 40-43). Do NOT write only the field-presence check the spec sketches — write BOTH assertions, because presence alone does not close the bug class:

```ts
// X-3 — every palette-openable panel must declare a guideBodyKey, or UserGuidePanel
// falls back to the terse descKey and the panel ships with no User-Guide copy.
it('every palette-openable panel has a guideBodyKey (X-3)', () => {
  const missing = OPENABLE_STUDIO_PANELS.filter((p) => !p.guideBodyKey).map((p) => p.id);
  expect(missing).toEqual([]);
});

// X-3 (part 2) — a guideBodyKey that resolves to nothing is the SAME bug wearing a
// field: UserGuidePanel.tsx:120 calls t(key, { defaultValue: '' }) → a dangling key
// renders an empty string, silently. Resolve every key against the en locale.
it('every guideBodyKey resolves to non-empty copy in en/studio.json (X-3)', () => {
  const studio = JSON.parse(
    readFileSync(resolve(process.cwd(), 'src/i18n/locales/en/studio.json'), 'utf-8'),
  );
  const lookup = (key: string) =>
    key.split('.').reduce<unknown>((o, k) => (o as Record<string, unknown> | undefined)?.[k], studio);
  const dangling = OPENABLE_STUDIO_PANELS
    .filter((p) => typeof lookup(p.guideBodyKey!) !== 'string' || !(lookup(p.guideBodyKey!) as string).trim())
    .map((p) => p.id);
  expect(dangling).toEqual([]);
});
```
(`readFileSync`/`resolve` are already imported at lines 1-2. `process.cwd()` is `frontend/` — the existing test reads `../contracts/...` from there.)

(2) FIX THE ONE PRE-EXISTING VIOLATOR — the assertion REDS ON MAIN as written, and that is not a surprise, it is X-3's whole point ("agent-mode already shipped without one", plan 30 line 336). Of 68 catalog rows, 12 lack `guideBodyKey`; 11 are `hiddenFromPalette: true` (correctly excluded — `OPENABLE_STUDIO_PANELS` filters them, catalog.ts:279). Exactly ONE openable row is missing it: `agent-mode` at `catalog.ts:258`. Add `guideBodyKey: 'panels.agent-mode.guideBody'` to that row, and add the matching `"guideBody": "…"` string to `frontend/src/i18n/locales/en/studio.json` under `panels."agent-mode"` (currently lines 472-475: `title` + `desc` only, no `guideBody`). Copy: one plain-language sentence on what the panel does + one on when to open it — match the voice of the neighbouring entries (e.g. `panels.compose.guideBody`, studio.json:22). Non-en locales are generated by `scripts/i18n_translate.py`; do not hand-author them, and do NOT let the test read anything but `en`.

(3) KEEP THE TYPE OPTIONAL — leave `guideBodyKey?: string` optional in `StudioPanelDef` (`catalog.ts:105`). Making it required would break the 11 legitimate `hiddenFromPalette` rows (wiki-editor, job-detail, book-reader, skill-editor, json-editor, media-version-history, original-source, translation-versions, translation-review, chapter-revision-compare, welcome). The mandate is enforced at the TEST layer, scoped to `OPENABLE_STUDIO_PANELS` — exactly like the `category` assertion above it.

Downstream consequence for M1–M4 registration (spec 31 line 558; plan 30 line 511): the "registration checklist step 2" is now MECHANICALLY ENFORCED — each of the 4 new rows (`quality-heal`, the 2 other `category: 'quality'` rows, and `progress` with `category: 'editor'`) must ship BOTH the `guideBodyKey: 'panels.<id>.guideBody'` field AND the `panels.<id>.guideBody` string in `en/studio.json` in the SAME commit, or `panelCatalogContract.test.ts` reds. Same for every panel added in specs 32-38. No further decision needed.

DoD for X-3: `cd frontend && npx vitest run src/features/studio/panels/__tests__/panelCatalogContract.test.ts` is green with 6 tests, and reverting the `agent-mode` guideBodyKey line reds test #4 (prove the guard bites — a guard that cannot fail is not a guard). Then `/review-impl` per the Wave-0 DoD.
- **Q-31-H2-ACCEPT-IS-NOT-A-CORRECTION** — H2 is already LAW IN CODE at three independent points — there is nothing to decide, only to obey. The `accept` kind does not exist and MUST NOT be added: (1) DB CHECK `kind IN ('edit','pick_different','regenerate','reject')` — services/composition-service/app/db/migrate.py:369; (2) type `CorrectionKind = Literal["edit","pick_different","regenerate","reject"]` — app/db/models.py:49; (3) the existing REST correction route's own docstring: "`accept` is deliberately not an action here (H2 — it trains the reranker on its own pick)" — app/routers/engine.py:1726-1727. Adding an `accept` value would need a migration + a CHECK-constraint backfill (migration-check-constraint-must-backfill-all-historical-blocks) for zero signal value. DO NOT.

CONCRETE BUILDER INSTRUCTION for M4 / BE-9b (this is the part that would otherwise stall at 3am — accept_unit today has NO edit signal at all: authoring_run_service.py:896-916 is a pure `drafted→accepted` status transition, it never reads chapter text):

A. `reject_unit` (authoring_run_service.py:919) — after the successful `transition_unit(... to_status="rejected")` and the restore, fire-and-forget `GenerationCorrectionsRepo.create(project_id=run.project_id, job_id=unit.job_id, created_by=caller, kind="reject", raw_before=<job.result["text"]> if the work opted into capture_correction_prose else None)`. `unit.job_id IS NULL` (pre-BE-9a rows) ⇒ write NOTHING and say so in the run report — never fabricate a job id.

B. `accept_unit` — do NOT write a correction unconditionally, and do NOT invent `kind='accept'`. Give `accept_unit` a `draft: DraftFn` callable bound in the router exactly like `restore: RestoreFn` is for reject (BookClient.get_draft with the CALLER's bearer — book_client.py:111). After the drafted→accepted transition:
   1. `unit.job_id IS NULL` ⇒ write nothing, report it. Done.
   2. `before = (await jobs.get(unit.job_id)).result.get("text") or ""` (the AI's drafted prose — the same field engine.py:1737 uses). If empty ⇒ write nothing.
   3. `after = (await draft(run.book_id, unit.chapter_id))["body"]` (current chapter draft text).
   4. `changed = count_changed_blocks(before, after)` (generation_corrections.py:42 — the existing chokepoint).
   5. `changed == 0` ⇒ **accept-AS-IS ⇒ write NOTHING** (this IS H2; it is the same rule engine.py:1750-1757 enforces as the `EDIT_NO_CHANGE` 422 — "a zero-change edit is an accept-as-is wearing an edit costume").
   6. `changed > 0` ⇒ the human edited before accepting ⇒ `corrections.create(..., kind="edit", changed_blocks=changed, raw_before/raw_after only if work.settings["capture_correction_prose"])`.
   The whole A/B capture is wrapped in `try/except Exception: logger.warning(...)` — a capture failure must NEVER fail the accept/reject (CandidatesView.tsx:9's own rule, restated in spec 31 §BE-9b).

C. MCP `composition_record_correction` (BE-9b Tier A): declare `kind` as a closed `enum` of exactly the 4 values and register it in `CLOSED_SET_ARGS` (mcp-tool-io IN-x). An agent sending `kind="accept"` must get a schema rejection / `result.error` ("accept-as-is is not a correction — nothing is recorded"), never a silent no-op and never a fabricated row.

D. Tests (already named in M4 DoD, make them literal): (i) rejecting a unit writes EXACTLY ONE row with `kind='reject'` + the right `job_id`; (ii) accepting a unit whose draft text is byte-identical to `job.result["text"]` writes **ZERO** rows; (iii) accepting a unit whose chapter draft diverged writes exactly one `kind='edit'` with `changed_blocks == count_changed_blocks(before, after)`; (iv) a unit with `job_id IS NULL` writes zero rows and the run report says so; (v) a repo/DB test asserts `INSERT ... kind='accept'` raises a CHECK violation (the enum stays closed — a drift-lock against a future builder "completing the enum").

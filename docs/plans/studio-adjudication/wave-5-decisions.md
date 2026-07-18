# Wave 5 — PlanForge — adjudicated decisions

> 47 items · 44 DECIDED · 2 not-a-question · 1 deferred · 0 escalated.

> **These are INSTRUCTIONS, not suggestions.** Each was settled by reading source. Do not re-open a
> decided question. Where this contradicts the wave plan, **this file wins.**

---

## Deferred (tracked, non-blocking)

### Q-35-OQ5-EXISTING-STATE
CONFIRMED PARKED — Wave 5 changes ZERO engine code for this. The gap is real at HEAD (propose_spec takes only the parsed braindump doc; propose_spec_llm only a raw file path; PlanRunCreate carries only source_markdown/mode/model_ref/force/genre_tags — the book_id is grant-gated but never read for state), and plan 30 §7's "Consciously OUT OF SCOPE" table already rules on it: "Belongs with Wave 5's spec, but it is a generation-quality defect, not a GUI gap. Track it; don't inflate Wave 5 with it." The tracking row ALREADY EXISTS — D-PLANFORGE-PROPOSE-BLIND at docs/sessions/SESSION_HANDOFF.md:102, gate #2. Builder instructions, exactly three, none of them an engine change: (1) DO NOT add an `existing_state` / chapter-context input to propose.py, propose_llm.py, propose_llm_async.py, or PlanRunCreate during Wave 5 — an attempt to "helpfully" wire it is scope creep against a PO-approved plan row and must be rejected at /review-impl. (2) One-line doc edit in docs/specs/2026-07-01-writing-studio/35_planforge_studio.md:595 — amend the OQ-5 cell to name the row: "Tracked as **D-PLANFORGE-PROPOSE-BLIND** (SESSION_HANDOFF.md Deferred, gate #2)." A "tracked elsewhere" with no ID is how a row becomes an orphan; the ID makes the claim verifiable. (3) DEFAULT I AM PICKING (veto-able): since the Wave-5 Planner panel is the human surface for a proposer that is blind to the manuscript, ship ONE honesty string in the new-run form — e.g. "Proposed from this braindump only. Existing chapters are not read." This is a copy string in the Planner panel, not the engine fix; it costs nothing, it is the repo's silent-success-is-a-bug law applied to a known blindness, and it does not inflate the wave. If the PO would rather ship no copy at all, drop item (3) — items (1) and (2) stand regardless.

**Defer row:** **D-PLANFORGE-PROPOSE-BLIND** (already exists — SESSION_HANDOFF.md:102; re-affirmed here, do not duplicate). Origin: spec 21-G2, re-flagged as spec 35 OQ-5 (Wave 5). What: PlanForge propose has no `existing_state` input — `propose_spec(doc)` (propose.py:412), `propose_spec_llm(raw_path, …)` (propose_llm.py:156) and `PlanRunCreate` (plan_forge.py:41) all read only the braindump, so proposing a plan for a book with 200 written chapters ignores every one of them; the plan is generated as if the manuscript did not exist. Gate: **#2 — large/structural** (a real engine change: a book-state gather lens + prompt/contract change across the rules path, the 2-step LLM path, the async path and the run schema; it is a generation-quality redesign, not a GUI gap, and no wave owns it). Target trigger: its own spec, scheduled when the PlanForge v2 compiler work (spec 27) next opens — NOT Wave 5. Wave 5 must not touch it (plan 30 §7).

## Decisions

### Q-35-X1-ADDMODELCTA
Answer (b): X-1 has NOT landed — build it as slice M4-PRE (a pre-slice of this wave, before any Pass Rail code). It is ~30 lines and fully unblocked; do NOT defer, do NOT ship M4 first.

EXACT WORK (one file + one test file):

1) frontend/src/components/shared/AddModelCta.tsx — add the studio branch AT THE SHARED COMPONENT (never at the ~8 call sites):
   - import { useOptionalStudioHost } from '@/features/studio/host/StudioHostProvider';
   - inside AddModelCta(), after `const location = useLocation()`: `const studioHost = useOptionalStudioHost();`
   - if (studioHost) → render a `<button type="button" onClick={() => studioHost.openPanel('settings', { params: { tab: 'providers' } })}>` carrying the SAME className strings as today's link/button variants (lines 46-49 for variant==='link', lines 60-63 for the default) and the same `<Plus/>` + `text` children. No `<a>` is rendered in the studio — that is the whole point (the anchor is what tears the dock down).
   - else → keep today's `<Link to={to}>` verbatim, including the `?return=` round-trip (that behavior is load-bearing outside the studio; ProvidersTab reads `?return=`).
   - Copy the DOCK-7 rationale comment from frontend/src/pages/book-tabs/TranslateModal.tsx:69-78 (the shipped precedent — same openPanel call, same panel, same params).

2) frontend/src/components/shared/__tests__/AddModelCta.test.tsx — keep the 2 existing MemoryRouter tests unchanged (they now assert the NON-studio branch), and ADD a studio test:
   - render inside StudioHostProvider (mirror the harness in frontend/src/features/studio/statusbar/__tests__/statusItems.test.tsx:55, which does `vi.spyOn(hostRef!, 'openPanel')`).
   - assert: `screen.queryByRole('link')` is null (regression guard: an anchor in-studio = the DOCK-7 bug), and clicking the button calls openPanel with exactly ('settings', { params: { tab: 'providers' } }).

3) Definition of Done for M4-PRE: `npx vitest run src/components/shared src/components/model-picker` green + a live-browser check (open Studio → any panel whose ModelPicker empty state shows the CTA → click → a `settings` dock TAB opens on the Providers tab and the dock layout survives). Then M4 (Pass Rail) may start. `/review-impl` at wave close per the PO policy.

No new infrastructure is needed: the studio `settings` panel is registered (catalog.ts:120), it honors `params.tab` (SettingsPanel.tsx:35-46), and 'providers' is a valid SettingsTabId (settings/tabs.tsx:26,39). Fixing the shared component fixes all 8 call sites (ModelPicker.tsx:388 is the one the Rail hits).

*Evidence:* frontend/src/components/shared/AddModelCta.tsx:33-68 — still `<Link to={REGISTRATION_PATH...}>` in BOTH variants, no useOptionalStudioHost import anywhere in the file (grep 'useOptionalStudioHost' frontend/src → 8 hits, none in components/shared/). Precedent to copy: frontend/src/pages/book-tabs/TranslateModal.tsx:73-78 (`if (studioHost) studioHost.openPanel('settings', { params: { tab: 'providers' } }); else navigate('/settings');`). Target panel exists: frontend/src/features/studio/panels/catalog.ts:120 (`{ id: 'settings', component: SettingsPanel, ... }`) + SettingsPanel.tsx:35-46 (params.tab deep-link) + frontend/src/features/settings/tabs.tsx:26,39 ('providers'). Blast radius: frontend/src/components/model-picker/ModelPicker.tsx:388 renders AddModelCta in its zero-models empty state — the exact surface every paid Pass Rail action mounts.

### Q-35-BE21-LIST-NPLUS1
NONE OF (a)/(b)/(c) — the N+1 does not exist. BE-21 adds ZERO queries on both the detail and the LIST path, because the package artifact id is ALREADY fetched in `_serialize_run`. Do NOT add `latest_artifact(..., PACKAGE_KIND)` to the serializer, and do NOT write a batch query.

BUILDER INSTRUCTION (exact):

File: services/composition-service/app/services/plan_forge_service.py

1. Line 21 — extend the existing module-level import:
   `from app.services.plan_pass_service import PACKAGE_KIND, derive_view`
   (module-level is safe: `derive_view` is already imported there; the local `from app.services.plan_pass_service import ...` idiom at :618/:1002/:1033/:1132 is incidental, not cycle-avoidance.)

2. In `_serialize_run` (:340-389), immediately after the existing line 348
   `artifacts = await self._runs.list_artifact_refs(run.book_id, run.id)`
   add:
   ```python
   # BE-21: the package pointer is ALREADY in `artifacts` — `list_artifact_refs` is
   # `DISTINCT ON (kind) ... ORDER BY kind, created_at DESC` (plan_runs.py:351), i.e. the
   # latest artifact id PER KIND, which is exactly what `latest_artifact(kind=PACKAGE_KIND)`
   # returns. Reading it from the list we already hold keeps LIST at its current query count:
   # no per-run package lookup, no N+1, no batch query.
   package_artifact_id = next(
       (a["artifact_id"] for a in artifacts if a["kind"] == PACKAGE_KIND), None,
   )
   ```

3. Line 383 — replace `**derive_view(run),` with:
   `**derive_view(run, package_artifact_id=package_artifact_id),`
   (Pass the raw asyncpg UUID, not `str(...)`: `derive_view` accepts `UUID | str | None` and coerces via `str(package_artifact_id or "")` at plan_pass_service.py:181 — identical normalization to the `package.id` that `pass_status` passes at :1016. Do not stringify; an empty-string-vs-None divergence is how this bug class starts.)

This fixes GET /runs/{id}, GET /runs (LIST), POST /checkpoint and PATCH /novel-system-spec in one edit — all four route through `_serialize_run` (:326, :337, :409, :611, :684).

TEST (mandatory, replaces the source-text pin):
File: services/composition-service/tests/unit/test_genre_tags_plumbing.py:88 — DELETE `assert "**derive_view(run)" in src` (it asserts the presence of the bug and will RED). Replace `test_the_serialized_run_RETURNS_genre_tags_and_the_derived_pass_view` with a BEHAVIOURAL assertion: build a run that has completed >=1 package-reading pass against a real `package` artifact, then assert `(await svc.get_run_detail(...))["pass_cursor"] == (await svc.pass_status(...))["pass_cursor"]` and that the same passes report `fresh: True` in both — i.e. the two producers of the same truth agree. Keep the `'"genre_tags": run.genre_tags' in src` line or convert it to a behavioural round-trip assertion too.

ADDITIONAL (do not scope-creep, just be aware): LIST is *already* N+1 by 3 queries per run (`self._jobs.get` :345, `list_artifact_refs` :348, `latest_artifact("spec")` for `arcs` :357). BE-21 does not make that worse and this decision does not ask you to fix it. If a builder later wants to cut it, the `arcs` `latest_artifact("spec")` call is the one worth batching — file it as a perf row only if profiling shows pain (CLAUDE.md defer gate #4), not now.

DEFAULT NOTED FOR PO VETO: none needed — this is a pure code fact, not a taste call.

*Evidence:* services/composition-service/app/services/plan_forge_service.py:348 (`artifacts = await self._runs.list_artifact_refs(run.book_id, run.id)`) + services/composition-service/app/db/repositories/plan_runs.py:351-363 (`SELECT DISTINCT ON (a.kind) a.kind, a.id AS artifact_id ... ORDER BY a.kind, a.created_at DESC` = latest id per kind, incl. `package`) prove the package id is already in hand. plan_pass_service.py:100 (`PACKAGE_KIND = "package"`), :294-296 (`derive_view(run, *, package_artifact_id: UUID | str | None)`), :181 (`out.append(str(package_artifact_id or ""))`) prove the type is accepted and normalizes identically to plan_forge_service.py:1007-1016's `latest_artifact(...).id`. plan_runs.py:246-262 shows `latest_artifact` uses the same JOIN + `created_at DESC` ordering, so the two resolve the same row. Broken call site: plan_forge_service.py:383 (`**derive_view(run),`). Pinning test to replace: services/composition-service/tests/unit/test_genre_tags_plumbing.py:88.

### Q-35-BE3-ARTIFACT-READ
BUILD IT — thin wrapper over `artifacts_by_ids`, exactly as the spec's candidate says. Size S. No new table, no new repo method, no gateway change (FE `api.ts` BASE `/v1/composition` already proxies). Recipe, verbatim:

(1) SERVICE — `services/composition-service/app/services/plan_forge_service.py`, add next to `get_run_detail` (after line 326):
```python
async def get_artifact(self, created_by: UUID, book_id: UUID, run_id: UUID,
                       artifact_id: UUID) -> dict[str, Any] | None:
    """BE-3. Scoped through the run join (plan_artifact has no book_id) — a foreign id is
    simply NOT in the returned dict, so unknown-id and cross-book id collapse to the SAME
    None ⇒ same 404. No enumeration oracle (H13). `created_by` is an actor stamp, never a
    filter (PM-5)."""
    loaded = await self._runs.artifacts_by_ids(book_id, run_id, [artifact_id])
    art = loaded.get(str(artifact_id))
    if art is None:
        return None
    return {"artifact_id": str(art.id), "kind": art.kind, "content": art.content,
            "created_at": art.created_at.isoformat() if art.created_at else None}
```

(2) ROUTER — `services/composition-service/app/routers/plan_forge.py`, insert immediately after `get_plan_run` (line 157), mirroring it:
```python
@router.get("/books/{book_id}/plan/runs/{run_id}/artifacts/{artifact_id}")
async def get_plan_artifact(
    book_id: UUID, run_id: UUID, artifact_id: UUID,
    user_id: UUID = Depends(get_current_user),
    grant: GrantClient = Depends(get_grant_client_dep),
    svc: PlanForgeService = Depends(get_plan_forge_service),
):
    await _gate_book(grant, book_id, user_id, GrantLevel.VIEW)   # VIEW, not EDIT
    art = await svc.get_artifact(user_id, book_id, run_id, artifact_id)
    if art is None:
        raise HTTPException(status_code=404, detail="artifact not found")
    return art
```
HARD RULES the builder must not "improve": (a) do NOT pre-check that the run exists and do NOT branch on cross-book — ONE 404 covers run-not-found + artifact-not-found + cross-book-artifact. Emitting 403 for a foreign artifact_id is an enumeration oracle and violates H13. (b) Path params stay typed `UUID` ⇒ malformed id 422s at FastAPI before touching the DB. (c) READ-ONLY: no PATCH/PUT/DELETE on this path (FE-1 opens `json-editor` read-only). (d) Body is `content` as-is (a dict) — do NOT re-serialize to a string.

(3) FRONTEND — `frontend/src/features/plan-forge/api.ts`: add `getPlanArtifact(bookId, runId, artifactId, token)` → `apiJson<PlanArtifact>(`${BASE}/books/${bookId}/plan/runs/${runId}/artifacts/${artifactId}`, { token })`, mirroring the `getPlanRun` line (api.ts:50). Add `export interface PlanArtifact { artifact_id: string; kind: string; content: unknown; created_at: string | null }` to `frontend/src/features/plan-forge/types.ts`.

(4) TESTS — `services/composition-service/tests/unit/test_plan_forge_router.py` (extend the existing fake-svc harness at its top; `test_get_plan_run` at line 93 is the template), THREE cases, all required:
  - 200: returns exactly `{artifact_id, kind, content, created_at}` — assert the key set, not just status.
  - 404 unknown artifact_id (fake repo returns `{}`).
  - **404 cross-book** — fake `artifacts_by_ids` returns `{}` when `book_id` != the run's owner; assert `resp.status_code == 404` AND `resp.status_code != 403`, with a comment naming H13. This is the test that pins the no-oracle property.
  Run: `python -m pytest tests -q -n auto --dist loadgroup` from `services/composition-service`.

SCOPE FENCE: BE-3b (`_serialize_run` also returns `run.source_markdown`) is a SEPARATE one-line fix — do not couple it to this route, and do not let it block. The inverse gap (no `plan_get_artifact` MCP tool for the agent) stays OQ-3, out of this slice, per spec 35 PS-11. Consistent with plan 30 §0 (PO-1..4) — nothing here touches a sealed decision.

*Evidence:* services/composition-service/app/db/repositories/plan_runs.py:265-286 (`artifacts_by_ids` — `JOIN plan_run r ON r.id = a.run_id WHERE a.run_id=$1 AND r.book_id=$2 AND a.id=ANY($3::uuid[])`; foreign id absent from the returned dict ⇒ 404 falls out, no 403 branch needed) · services/composition-service/app/db/models.py:689-695 (PlanArtifact: id/run_id/created_by/kind/content/created_at — response is a projection, no new fields) · services/composition-service/app/services/plan_forge_service.py:385-388 (run detail emits `{kind, artifact_id}` refs ONLY — the hole) · services/composition-service/app/routers/plan_forge.py:24-30 + 144-156 (`_gate_book` VIEW pattern + `get_plan_run`, the exact shape to mirror) · grep of app/routers/plan_forge.py + app/mcp/server.py: zero `artifacts/{artifact_id}` route and zero `plan_get_artifact` tool ⇒ transport genuinely absent · frontend/src/features/plan-forge/api.ts:50 (getPlanRun — the FE client line to mirror; BASE already reaches composition through the gateway)

### Q-35-PANEL-COUNT-BASELINE
§7's PRINCIPLE wins; §10 DoD item 1's literal is a drafting slip — but so is §7's own "65". Strike EVERY literal (57/58/65). Grounding fact: no drift-lock test counts panels. `panelCatalogContract.test.ts:26-35` asserts SET-EQUALITY (`expect([...enumIds].sort()).toEqual(openable)`) + membership (`toContain(id)`); the chat-service contract test is regeneration-based (zero `len(`/numeric literals). So the builder never writes a panel count anywhere, and there is no assertion that can pin a phantom.

BUILDER, DO EXACTLY THIS in M4:

1. ADD NO NEW COUNT TEST. The existing set-equality guard is strictly STRONGER than `N == N == N` (it catches a swap that keeps the count constant). Adding a count assertion would be a weaker check that must be hand-bumped every wave — i.e. it would MANUFACTURE the drift this question is about. (Default I picked; PO may veto.)

2. EDIT the spec, two lines, before building:
   - `35_planforge_studio.md` §10 DoD item 1: replace "**py enum 58 == contract enum 58 == openable 58.**" with: "**The three-way lockstep holds by SET equality (`panelCatalogContract.test.ts` green — it asserts sets, not counts), and the enum grew by exactly +1 whose sole new member is `plan-passes`. No count literal appears in any test or DoD check.**"
   - §7: replace "so the baseline here is **65**, not 57" with "**so the baseline here is N_before, computed at wave start — NOT 57, and NOT 65 (65 presumes waves 1-4 each land exactly one panel; if any wave slips or lands two, 65 is as phantom as 58).**" Keep §7's "(:402, currently 57 entries)" but mark it "at HEAD 9262ed53e — stale after Wave 1; APPEND to the enum, never count it."

3. The M4 delta gate is a 2-command shell check the builder RUNS (it is not a test file):
   - at M4 start: `N_before=$(jq '.ui_open_studio_panel.args.panel_id.enum | length' contracts/frontend-tools.contract.json)` — record N_before in the run-state.
   - after regenerating the contract (§7 step 6): assert `N_after == N_before + 1` AND that the set difference is exactly `["plan-passes"]`:
     `jq -r '.ui_open_studio_panel.args.panel_id.enum[]' contracts/frontend-tools.contract.json | sort > /tmp/after.txt` and diff against the pre-wave list — the ONLY added line must be `plan-passes`, with zero removals. A removal here means another wave's panel was clobbered by a hand-edit of the JSON (§7 step 6's exact failure mode).

4. Everything else in §7's 9-step checklist stands unchanged. The three files that must move in ONE commit remain: `frontend_tools.py:402` (append `"plan-passes"` to the enum), `catalog.ts` (append the row after `plan-hub`), `contracts/frontend-tools.contract.json` (REGENERATED via `WRITE_FRONTEND_CONTRACT=1 python -m pytest tests/test_frontend_tools_contract.py`, never hand-edited).

Net: the "internal contradiction" is real but harmless-by-construction — §10 describes a check the code does not implement. Fix the prose, keep the set-equality guard, gate on the delta.

*Evidence:* frontend/src/features/studio/panels/__tests__/panelCatalogContract.test.ts:32-35 — `const openable = OPENABLE_STUDIO_PANELS.map((p) => p.id).sort(); expect([...(enumIds ?? [])].sort()).toEqual(openable);` (SET equality, count-agnostic) and :26-30 `expect(Object.keys(STUDIO_PANEL_COMPONENTS)).toContain(id)`. Supporting: frontend/src/features/studio/panels/catalog.ts:279 (`OPENABLE_STUDIO_PANELS = STUDIO_PANELS.filter((p) => !p.hiddenFromPalette)`); services/chat-service/app/services/frontend_tools.py:402 (panel_id enum, 57 entries at HEAD 9262ed53e); contracts/frontend-tools.contract.json `ui_open_studio_panel.args.panel_id.enum` = 57 (verified by jq/python). `grep -rn "len(\|== 5[0-9]\|count" services/chat-service/tests/test_frontend_tools_contract.py` → NO MATCHES: no count assertion exists in either drift-lock.

### Q-35-BE2-AUTOFIX-ROUTE
BUILD THE ROUTE (XS) — but NOT with the ack shape the spec proposes. The spec's "202 {run_id, job_id, status} mirroring /refine" contradicts the service: `handoff_autofix` (plan_forge_service.py:817) returns `{"rounds": [{round,targets,result}...], "run": <run detail>}` and is SYNCHRONOUS on the default worker-off path (it only breaks early, still returning that dict, when the worker is on and round 1 enqueues). Mirror the SERVICE, not a guessed envelope.

FILE 1 — services/composition-service/app/routers/plan_forge.py

(a) After `class PlanRefineRequest` (line 58) add:

class PlanAutofixRequest(BaseModel):
    """HTTP mirror of MCP `plan_handoff_autofix` (mcp/server.py:3490). model_ref is
    OPTIONAL — the service resolves the author's default planner model
    (plan_forge_service.py:123 _resolve_model_ref)."""
    model_ref: UUID | None = None
    max_rounds: int = Field(default=3, ge=1, le=5)   # closed range -> 422, not a silent clamp

(b) Immediately after `refine_plan_run` (ends line 222) add:

@router.post("/books/{book_id}/plan/runs/{run_id}/autofix")
async def autofix_plan_run(
    book_id: UUID,
    run_id: UUID,
    body: PlanAutofixRequest,
    user_id: UUID = Depends(get_current_user),
    grant: GrantClient = Depends(get_grant_client_dep),
    svc: PlanForgeService = Depends(get_plan_forge_service),
):
    await _gate_book(grant, book_id, user_id, GrantLevel.EDIT)   # 403 insufficient / 404 no book
    try:
        out = await svc.handoff_autofix(
            user_id, book_id, run_id,
            model_ref=body.model_ref, max_rounds=body.max_rounds,
        )
    except ValueError as exc:            # "no spec to refine" / no default planner model
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if out is None:                      # service returns None when the run isn't in this book
        raise HTTPException(status_code=404, detail="run not found")
    run = out.get("run") or {}
    # 202 ONLY when the worker path enqueued round 1 and the loop stopped (run carries a live job);
    # the default worker-off path already finished the loop -> 200. run_id/job_id/status the spec
    # asked for are all inside `run` (id, active_job_id, job_status) — plus `rounds`, which M3's R3
    # Repair strip needs to render WHAT was fixed. A bare ack would throw that away and would lie
    # about being async on the sync path.
    if run.get("active_job_id"):
        return JSONResponse(status_code=202, content=out)
    return out                           # 200 {"rounds": [...], "run": {...}}

FILE 2 — contracts/api/composition-service/plan-forge.v1.yaml (contract-first rule): add path `/books/{book_id}/plan/runs/{run_id}/autofix` next to `/refine` (line 151), requestBody `PlanAutofixRequest` (model_ref: uuid nullable; max_rounds: integer min 1 max 5 default 3), responses 200 (rounds[] + run: PlanRunDetail), 202 (same body, job in flight), 400, 403, 404.

FILE 3 — services/composition-service/tests/unit/test_plan_forge_router.py: add to `StubPlanForge` an `async def handoff_autofix(self, owner_user_id, book_id, run_id, **kwargs)` that returns None when run_id != RUN, else `{"rounds": [{"round": 1, "targets": 2, "result": "applied"}], "run": await self.get_run_detail(...)}`. Tests: (1) POST autofix -> 200, body["rounds"][0]["result"]=="applied"; (2) unknown run_id -> 404; (3) max_rounds=0 and =6 -> 422; (4) stub whose run detail has active_job_id set -> 202; (5) StubGrant returning GrantLevel.VIEW -> 403.

OUT OF SCOPE for BE-2: the FE client (frontend/src/features/plan-forge/api.ts) — M3's R3 Repair strip adds it and consumes `rounds`.

*Evidence:* services/composition-service/app/services/plan_forge_service.py:817-847 (`handoff_autofix` -> `return {"rounds": applied, "run": detail}`; returns None on missing run; loop breaks when `mode == "async"`) · services/composition-service/app/mcp/server.py:3490-3517 (MCP tool: `_gate(EDIT)` + call + `uniform_not_accessible()` on None; max_rounds 1–5) · services/composition-service/app/routers/plan_forge.py:199-222 (`/refine` route = the pattern: `_gate_book(EDIT)`, LookupError→404, ValueError→400, 202 only when service says async) · plan_forge_service.py:535 (refine's async ack `{"run_id","job_id","status":"pending"}` — the shape the spec wrongly assumed autofix returns) · contracts/api/composition-service/plan-forge.v1.yaml:151 (`/refine` path to mirror)

### Q-35-BE22-PHANTOM-TOOL
Take the spec's candidate, with one correction: KEEP the existing leading clause (a test asserts it) and replace only the phantom parenthetical, naming the real recovery — re-running the `cast` pass.

1) `services/composition-service/app/services/plan_forge_service.py:702-705` — replace:
```python
            raise ValueError(
                "cast cannot be accepted before its glossary seed proposal exists "
                "(call plan_bootstrap_seed for this pass first)",
            )
```
with:
```python
            raise ValueError(
                "cast cannot be accepted before its glossary seed proposal exists — re-run the "
                "'cast' pass (plan_run_pass with pass_id='cast') to propose it. The proposal is "
                "opened by the pass job itself; there is no standalone seeding call.",
            )
```
(Keep it under 300 chars: `plan_run_pass` truncates `detail` at `[:300]`, mcp/server.py:3629.)

2) `services/composition-service/tests/unit/test_plan_pass_checkpoint.py:106-111` (`test_a_missing_proposal_REFUSES_rather_than_silently_accepting`) — keep the two existing asserts and add the anti-phantom guard:
```python
    assert "plan_bootstrap_seed" not in src  # phantom: the recovery is re-running the cast pass
    assert "plan_run_pass" in src
```

Grounding for the wording (do NOT invent a new tool/route): `bootstrap_proposal_id` is written in exactly one place — `job_consumer.py:209-215` (`_propose_pass_seed` → `record_pass(bootstrap_proposal_id=...)`) — which only runs as a side effect of the plan-pass job. `plan_run_pass` (mcp/server.py:3567) is the sole entry point. Do not add a seeding tool/route: BE-22 is explicitly "no new route", and the seed-on-pass design is deliberate (job_consumer.py:199-208 documents PF-7: one approval mechanism, not two).

Leave the OTHER two branches alone — `plan_forge_service.py:708` (proposal vanished) and `:709-713` (status != 'applied', "apply it first (PF-7)") already name real recoveries; the apply path exists at `routers/plan_bootstrap.py:113` (`POST /books/{book_id}/plan/bootstrap/{proposal_id}/apply`).

Scope: XS, one message + one test file. No contract, no migration, no FE change.

*Evidence:* services/composition-service/app/services/plan_forge_service.py:702-705 (the phantom message) · job_consumer.py:209-215 + 199-208 (`_propose_pass_seed` is the ONLY writer of `bootstrap_proposal_id`, and it fires only inside `_finalize_plan_pass_job`) · mcp/server.py:3567 `plan_run_pass` (sole way to run the cast pass; ValueError detail truncated at [:300], line 3629) · routers/plan_bootstrap.py:113 (the real apply route) · tests/unit/test_plan_pass_checkpoint.py:111 asserts the substring "before its glossary seed proposal exists" — the rewrite must preserve it · `grep -rn plan_bootstrap_seed` → 1 code hit (the string) + spec 35 line 434 + design-drafts/screens/studio/screen-planforge-pass-rail.html:833.

### Q-35-BE21-TEST-PIN
Confirmed from code, and it is a work item, not an open question — but the spec's one-line framing under-specifies the test, so here is the builder-ready form. Do BOTH edits in the SAME M1 slice (BE-21).

(1) THE FIX — services/composition-service/app/services/plan_forge_service.py:
- line 21: extend the existing module-level import to `from app.services.plan_pass_service import PACKAGE_KIND, derive_view` (do NOT add a third local import; :1002 already imports PACKAGE_KIND locally — leave that alone or drop it in favour of the module-level one).
- in `_serialize_run`, beside the spec-artifact fetch already at :356, add:
      package = await self._runs.latest_artifact(run.book_id, run.id, PACKAGE_KIND)
- line 383: `**derive_view(run),` → `**derive_view(run, package_artifact_id=package.id if package else None),`
This makes `_serialize_run` (:383) identical to `pass_status` (:1016), which is already correct.

(2) THE TEST — tests/unit/test_genre_tags_plumbing.py:82-89: DELETE `test_the_serialized_run_RETURNS_genre_tags_and_the_derived_pass_view` (both source-text asserts: the `**derive_view(run)` one asserts the BUG, and the `"genre_tags": run.genre_tags` one is the same anti-pattern) and replace with ONE behavioural async test:

```python
@pytest.mark.asyncio
async def test_the_run_detail_reports_the_SAME_pass_cursor_as_the_passes_endpoint():
    PKG = uuid4()
    run = PlanRun(
        id=uuid4(), created_by=USER, book_id=BOOK, mode="llm", status="proposed",
        active_job_id=None, genre_tags=["xianxia"],
        pass_state={"motifs": {"status": "completed", "decision": "auto",
                               "artifact_id": str(uuid4()), "params": {}}},
    )
    # record motifs' fingerprint exactly as the worker does: WITH the package id
    run.pass_state["motifs"].input_fingerprint = fingerprint(          # attribute, NOT subscript:
        input_artifact_ids=input_pointers(run, "motifs", package_artifact_id=PKG),  # pass_state is
        params={},                                                     # dict[str, PassEntry]
    )
    runs = AsyncMock()
    runs.get_for_book.return_value = run
    runs.list_artifact_refs.return_value = []
    async def _latest(book_id, run_id, kind):
        return SimpleNamespace(id=PKG) if kind == PACKAGE_KIND else None
    runs.latest_artifact.side_effect = _latest
    svc = PlanForgeService(runs, AsyncMock(), AsyncMock(), llm=AsyncMock())

    detail = await svc.get_run_detail(USER, BOOK, run.id)
    passes = await svc.pass_status(USER, BOOK, run.id)

    assert passes["pass_cursor"] == 1                       # /passes: right by construction
    assert detail["pass_cursor"] == passes["pass_cursor"]   # …and the detail must AGREE
    assert {p["pass_id"]: p["fresh"] for p in detail["passes"]}["motifs"] is True
    assert detail["genre_tags"] == ["xianxia"]              # PF-15 round-trip, behaviourally
```

WHY THIS FIXTURE (do not simplify it): `motifs` is the FIRST pass in PASS_ORDER and has reads_package=True (plan_pass_service.py:56-59), and `input_pointers` (:180-181) prepends `str(package_artifact_id or "")` to the fingerprint inputs. So without the fix the recomputed fingerprint is taken against "" → is_fresh(motifs)=False → pass_cursor collapses to 0 at pass #1, i.e. the detail reports an un-compiled plan. Hence:
- MANDATORY: `assert passes["pass_cursor"] == 1` — the equality assertion ALONE is VACUOUS (0 == 0 passes happily if the fixture is wrong and the package is never seen). Pinning the non-zero value is what makes this test actually red without BE-21. Verify it: comment out the fix, run it, watch it fail 0 != 1.
- Harness notes (all verified): `sync_from_job` early-returns on active_job_id=None, so `jobs` needs no setup; `_serialize_run` iterates `list_artifact_refs`, so it must return [] not a bare AsyncMock; `latest_artifact` must dispatch on `kind` because `_serialize_run` asks for "spec" too (None ⇒ arcs=[]).
Imports to add to the test file: `from types import SimpleNamespace`, `from unittest.mock import AsyncMock`, `from uuid import uuid4`, `import pytest`, `from app.services.plan_pass_service import PACKAGE_KIND, fingerprint, input_pointers`, plus USER/BOOK uuid4() consts (mirror tests/unit/test_plan_forge_default_model.py:41-64, the existing fake-repo harness).

NOTE (not a blocker): this adds one `latest_artifact` call per run inside `_serialize_run`, which `list_runs` (:337) calls in a loop — an N+1, but it exactly mirrors the spec-artifact fetch already there at :356, so it is no new pattern. Fix only if a LIST latency finding appears (defer gate #4, profiling evidence).

*Evidence:* services/composition-service/app/services/plan_forge_service.py:383 (`**derive_view(run),` — the bug: no package_artifact_id) vs :1016 (`**derive_view(run, package_artifact_id=package.id if package else None)` — pass_status, correct) and :356 (the sibling latest_artifact fetch already in _serialize_run to mirror). Root mechanism: services/composition-service/app/services/plan_pass_service.py:180-181 (`if spec.reads_package: out.append(str(package_artifact_id or ""))`) + :56-59 (`motifs` = first in PASS_ORDER, reads_package=True) + :259-274 (pass_cursor breaks at the first non-fresh pass) ⇒ omitting the id makes pass_cursor 0. The pinning test: services/composition-service/tests/unit/test_genre_tags_plumbing.py:88 (`assert "**derive_view(run)" in src`) — :383 is the file's only occurrence of that exact substring, so BE-21 REDs it. Harness to copy: tests/unit/test_plan_forge_default_model.py:41-64. Fixture constraint: services/composition-service/app/db/models.py:683 (`pass_state: dict[str, PassEntry]` ⇒ attribute assignment, not subscript).

### Q-35-FE1-READONLY-PROVIDER
BUILD FE-1 FIRST in M3, before PS-9 — the spec's candidate answer is CORRECT and is confirmed by code. It is a ~20-line, purely-additive, zero-migration widening. Exact builder instruction:

(1) `frontend/src/features/studio/documents/types.ts` — add ONE optional field to `JsonDocumentProvider` (after `titleKey?`, line ~51):
    /** The doc type is immutable output (e.g. a plan artifact). The json-editor renders it as a VIEWER: no Save, no Revert, no CMD-S. Default false = today's editable behavior. */
    readOnly?: boolean;
  Do NOT put it on DocumentHandle/DocumentSnapshot. It is a property of the TYPE, not of a resource instance — `plan-artifact` is read-only for every artifact. (Default chosen; veto if you want per-resource.)

(2) NO CHANGES to the 2 existing call sites. `entityDocument.ts:203` and `manuscriptUnitDocument.ts:228` both pass plain object literals with no spread/satisfies — an optional field cannot break them. `readOnly` absent => undefined => falsy => identical behavior. Do not touch these files.

(3) `frontend/src/features/studio/panels/JsonEditorPanel.tsx` — derive `const readOnly = provider?.readOnly === true;` next to `const provider = ...` (line 42), then FOUR edits:
  a. CM6 (line 164-171): add `editable={!readOnly}` and `readOnly={readOnly}`. @uiw/react-codemirror 4.25.10 exposes BOTH as first-class props (node_modules/@uiw/react-codemirror/esm/index.d.ts:39 + :44) — do NOT hand-roll an `EditorState.readOnly` Compartment/extension; the spec's "+ readOnly extension" is redundant.
  b. CMD-S (line 93-99): the keydown listener is WINDOW-level, so it must not be REGISTERED at all when read-only — `useEffect(() => { if (readOnly) return; ... }, [onSave, readOnly])`. Do not merely early-return inside onSave: a live window listener that swallows the browser's CMD-S is a side effect on the whole app.
  c. Toolbar (line 152-161): HIDE Save and Revert entirely (`{!readOnly && (<>...</>)}`), do not merely `disabled`. A disabled Save reads as "nothing to save yet" — a lie about an immutable doc. Plan 30 line 580 requires CMD-S to do nothing "visibly and deliberately", so also render a `read-only` chip in the status span. Keep the Format button (it is buffer-local and harmless).
  d. `onChange` (line 71-81): `if (readOnly) return;` as defense-in-depth before `handle?.update(parsed)` (a programmatic/paste path could still fire).

(4) Tests — `frontend/src/features/studio/panels/__tests__/JsonEditorPanel.test.tsx` (mock at line 17 already returns a provider object; add a readOnly variant). Assert: (i) provider `{readOnly:true}` => `queryByTestId('json-editor-save')` and `'json-editor-revert'` are BOTH null; (ii) firing `keydown` {key:'s', ctrlKey:true} on window does NOT call `handle.save()`; (iii) REGRESSION: a provider WITHOUT `readOnly` still renders Save and still saves on CMD-S (this is the test that protects the 2 shipped providers).

Then PS-9 registers `plan-artifact` with `readOnly: true` and a composite `resourceId = "{runId}:{artifactId}"` (per F-P11), and its `save()` may simply be `async () => {}` — because it is now unreachable, not silently ignored.</decision>
<parameter name="evidence">frontend/src/features/studio/documents/types.ts:45-54 (`JsonDocumentProvider` = type/schema?/titleKey?/open — no readOnly, confirming the 0-hit grep) · JsonEditorPanel.tsx:164-171 (CM6 mounted with no editable/readOnly prop), :93-99 (unconditional WINDOW-level CMD-S -> handle.save()), :152-161 (Save/Revert always rendered) — i.e. a no-op save() ships the silent-success bug exactly as claimed · frontend/src/features/glossary/documents/entityDocument.ts:203 + frontend/src/features/studio/manuscript/unit/manuscriptUnitDocument.ts:228 (both are bare object literals => an OPTIONAL field breaks neither; "must stay compiling" costs zero edits) · node_modules/@uiw/react-codemirror/esm/index.d.ts:39 (`editable?: boolean`) + :44 (`readOnly?: boolean`) — the wrapper already supports it natively · docs/specs/2026-07-01-writing-studio/30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md:19-22 (PO-1..4 SEALED — none of them touch the JSON-document standard, so no sealed decision is contradicted) and :580 (requires CMD-S to do nothing "visibly and deliberately", which is why Save is HIDDEN, not disabled).

### Q-35-BE4-ARCHIVE-MIGRATION
BUILD IT — soft-archive column + LIST filter + a JOB-TRUTH in-flight check that covers BOTH job carriers. In-flight is decided by `generation_job.status`, NEVER by `plan_run.status` or `pass_state[*].status` (those are known-lying — `sync_from_job` exists precisely because the run row goes stale when the worker hook misses).

1) MIGRATION — `services/composition-service/app/db/migrate.py`, append next to the 27 V2-A ALTERs (after line 1316):
   `ALTER TABLE plan_run ADD COLUMN IF NOT EXISTS is_archived BOOLEAN NOT NULL DEFAULT false;`
   `CREATE INDEX IF NOT EXISTS idx_plan_run_book_created_active ON plan_run(book_id, created_at DESC) WHERE NOT is_archived;`
   (mirrors outline_node/canon_rule/structure_node at migrate.py:209/257/1122. Additive; no CHECK touched.)

2) MODEL — `app/db/models.py` PlanRun (~:679): add `is_archived: bool = False`. Add `is_archived` to `_SELECT_RUN` in `app/db/repositories/plan_runs.py:23-27` (a column not selected here validates as the model default and lies).

3) REPO — `app/db/repositories/plan_runs.py`:
   - `list_for_book(..., include_archived: bool = False)` → append `AND NOT is_archived` to `where` unless include_archived (line ~133).
   - `archive(book_id, run_id) -> bool`: `UPDATE plan_run SET is_archived = true, updated_at = now() WHERE id=$1 AND book_id=$2 AND NOT is_archived RETURNING id` (canon_rules.py:160 shape). `restore(...)` is the mirror with `is_archived = false … AND is_archived`.
   - `get_for_book` MUST NOT filter archived (restore + the detail view need to read the tombstone) — add that as a comment so a later reviewer doesn't "fix" it.
   - `find_by_checksum` (:99-115) MUST add `AND NOT is_archived` — otherwise re-Proposing identical markdown dedupes onto the ARCHIVED run and the user's new Propose silently returns an invisible run (a real bug, not a nicety).
   - `plan_state_for_book` (:313-349): add `AND NOT is_archived` to all three subqueries — the per-chat-turn plan probe must not count/report an archived run.

4) IN-FLIGHT CHECK (the builder decision) — new `GenerationJobsRepo.active_among()` in `app/db/repositories/generation_jobs.py`:
   `SELECT id FROM generation_job WHERE id = ANY($1::uuid[]) AND book_id = $2 AND status = ANY($3::text[]) AND created_at > $4 LIMIT 1`
   with `$3 = list(_ACTIVE_STATUSES)` (:55) and `$4 = now() - 1800s` (same stale bound as `create_chapter_job_guarded`, :266 — a crash-orphaned job must NOT make a failed run un-archivable forever). `book_id` in the WHERE is the tenancy assert (a bare-id job read must be re-scoped to the run's book — same guard as sync_from_job's `job.book_id != book_id` at :109).
   Candidate ids = `run.active_job_id` (propose/checkpoint/compile) UNION `{e["job_id"] for e in run.pass_state.values() if e.get("job_id")}` — the pass jobs are recorded ONLY in `pass_state` (plan_forge_service.py:1190), so an `active_job_id`-only probe would happily archive a run with 7 live pass jobs. Both carriers or it's wrong.

5) SERVICE — `PlanForgeService.archive_run(created_by, book_id, run_id)`: `get_for_book` → None ⇒ 404; then `await self.sync_from_job(...)` FIRST (a completed-but-unhooked job must not 409); then `active_among(...)` → if hit, raise `PlanRunJobInFlight(job_id)`; else `repo.archive(...)`. Already-archived ⇒ still 204 (idempotent). `restore_run(...)` runs NO in-flight check (nothing to orphan).

6) ROUTER — `app/routers/plan_forge.py`: `@router.delete("/books/{book_id}/plan/runs/{run_id}", status_code=204)` with `_gate_book(..., GrantLevel.EDIT)`; 409 body `{"code": "PLAN_RUN_JOB_IN_FLIGHT", "active_job_id": str(id)}` (mirrors engine.py:1056). Ships WITH BE-4b (spec 35 PS-13): `@router.post(".../restore")` (EDIT, returns run detail) + `include_archived: bool = Query(default=False)` threaded through `list_plan_runs` (:131) → `svc.list_runs` → repo.

7) TESTS (must exist or the wave doesn't close):
   - `tests/unit/test_plan_forge_router.py`: DELETE→204; DELETE unknown run→404; VIEW-only grant→403; **DELETE with `active_job_id=None` but a `pass_state["cast"].job_id` that is `running` → 409** (this is the test that proves the two-carrier union — an active_job_id-only impl passes every other test); DELETE where the only candidate job is `running` but older than the 1800s window → 204 (no permanent lockout); POST /restore→200.
   - `tests/integration/db/test_repositories.py`: archived run absent from `list_for_book`, present with `include_archived=True`; `get_for_book` still returns it; `find_by_checksum` skips it (re-propose mints a FRESH run).

Default I am picking (veto-able): archive is a plain CRUD op, not agent logic, so it stays REST-only — no new MCP tool. The MCP/list surfaces inherit the filter for free because they go through `list_for_book`.

*Evidence:* services/composition-service/app/services/plan_forge_service.py:1190 (`record_pass(run, pass_id, status="running", job_id=job.id)` — pass jobs live ONLY in pass_state, never in active_job_id) · :100-121 (`sync_from_job`: job status is the truth, run row is the stale mirror; `job.book_id != book_id` tenancy assert) · services/composition-service/app/db/repositories/generation_jobs.py:55 (`_ACTIVE_STATUSES`) + :266-315 (stale-bounded in-flight guard, stale_secs=1800) · app/routers/engine.py:1056 (409 `{"code":"CHAPTER_JOB_IN_FLIGHT","active_job_id":…}` shape) · app/db/repositories/canon_rules.py:160 (soft-archive UPDATE precedent) · app/db/migrate.py:1256-1289 (plan_run DDL, no is_archived) + :209/257/1122 (is_archived + partial-index precedent) · app/db/repositories/plan_runs.py:23-27/99-115/128-164/313-349 (the four reads that need the filter) · grep confirms zero `@router.delete` in plan_forge.py / plan_bootstrap.py

### Q-35-BE20-LEDGER-FIELDS
MUST-BUILD, XS, exactly as the spec states — one file, one hunk, no new column, no new route, no migration.

**THE CHANGE.** In `services/composition-service/app/services/plan_pass_service.py`, inside `derive_view` (the `passes.append({...})` literal at lines 306-318), add three keys read straight off the already-normalized entry dict `e`:

```python
passes.append({
    "pass_id": pid,
    ...
    "job_id": e.get("job_id"),
    # 27 PF-7 — the glossary seed proposal this pass is waiting on. RETURNED, because
    # `_assert_seed_applied` (plan_forge_service.py:698) refuses to accept `cast` until this
    # proposal is `applied`, and the ONLY route to a proposal is
    # GET /plan/bootstrap/{proposal_id} — which needs an id the client could not see. A stored
    # field the gate reads but no transport returns is a permanent, unclearable 409.
    "bootstrap_proposal_id": e.get("bootstrap_proposal_id"),
    "decided_by": e.get("decided_by"),
    "decided_at": e.get("decided_at"),
    # DERIVED — not stored:
    "fresh": ...,
    "blockers": ...,
})
```
No conversion is needed: `_entry` (plan_pass_service.py:153-159) already `model_dump(mode="json")`s a `PassEntry`, and the JSONB path is already `str`, so all three are `str | None` on both paths.

**WHY ONE HUNK IS THE WHOLE FIX.** Every transport is a raw dict with no DTO stripping, so this single edit lights up all four surfaces simultaneously:
- HTTP `GET /v1/composition/books/{book_id}/plan/runs/{run_id}/passes` (routers/plan_forge.py:236-249 — returns `svc.pass_status()` unmodified)
- MCP `plan_pass_status` (mcp/server.py:3646-3657 — returns `out` unmodified, no output schema)
- `_serialize_run` → every run GET/PATCH/checkpoint response (plan_forge_service.py:383 `**derive_view(run)`)
- `run_pass`'s 202 body (plan_forge_service.py:1216)
- api-gateway-bff is a transparent `createProxyMiddleware` (gateway-setup.ts:350-354) — nothing to widen there.
There is no OpenAPI yaml, no gateway DTO, and no FE type that pins the pass-row shape, so nothing else must change.

**SCOPE RULING (the tempting scope creep — do NOT do it).** Do not add a "list a run's seed proposals" route, and do not JOIN the proposal's `status` into the pass row. `derive_view` is a *pure, synchronous* function over the run — a status join would force it async and drag a repo dependency into the derivation layer, which is a refactor, not an XS. The id is sufficient: the client reads `passes[i].bootstrap_proposal_id` from the ledger, then calls the existing `GET /v1/composition/books/{book_id}/plan/bootstrap/{proposal_id}` (routers/plan_bootstrap.py:62) for status/diff, and `.../approve` + `.../apply` (plan_bootstrap.py:77, 113) to clear the gate. That is the M4 cast-checkpoint card's data path, complete, with zero new backend surface. **DEFAULT NOTED FOR PO VETO:** the GUI pays one extra round-trip per seed proposal. If the PO later wants a single-fetch card, that is a follow-up that adds `bootstrap_status` via an async wrapper in `PlanForgeService.pass_status` (NOT in `derive_view`) — not this slice.

**TESTS (both required — the field must be proven RETURNED, not merely stored).**
1. Unit, in `services/composition-service/tests/unit/test_plan_pass_service.py` next to `test_derive_view_reports_every_pass_with_its_derived_freshness` (line 234): seed a run whose `cast` entry carries `bootstrap_proposal_id`/`decided_by`/`decided_at`, call `derive_view`, assert the `cast` row echoes all three verbatim; assert a never-run pass returns `None` for all three (absent ≠ dropped).
2. Transport, in `services/composition-service/tests/unit/test_plan_pass_checkpoint.py` (which already seeds `pass_state` directly, line 412): assert the `GET .../passes` response body's `cast` row contains `bootstrap_proposal_id` — a unit test on `derive_view` alone cannot prove the transport didn't strip it, and "written by the worker, returned by nothing" is precisely the bug class here (cf. the repo's own "REST mirror drops fields the MCP tool accepts" lesson).

**DoD:** both tests green, plus `/review-impl` at the close of the wave that contains this slice (PO policy #2).

*Evidence:* services/composition-service/app/services/plan_pass_service.py:302-318 (derive_view's per-pass dict — emits pass_id/checkpoint/output_kind/depends_on/status/decision/artifact_id/job_id/fresh/blockers, and NONE of the three); models.py:653-666 (PassEntry HAS all three); worker/job_consumer.py:207-221 (worker WRITES bootstrap_proposal_id via record_pass); plan_forge_service.py:698-712 (_assert_seed_applied 409s on pass_state["cast"]["bootstrap_proposal_id"] + proposal.status != "applied" — the unclearable gate); routers/plan_forge.py:236-249 + mcp/server.py:3646-3657 (both return the dict unmodified — no DTO strips it, so one hunk suffices); api-gateway-bff/src/gateway-setup.ts:350-354 (transparent proxy); routers/plan_bootstrap.py:62/77/113 (the GET/approve/apply routes that already exist once the client has the id).

### Q-35-BE4B-RESTORE-COUPLED
CONFIRMED — ship BE-4 + BE-4b as ONE slice. Neither exists today (plan_run has no is_archived column, plan_forge.py has zero delete/restore routes), so this is unbuilt work, not a question. Build exactly this, mirroring the arc.py sibling verbatim:

1. MIGRATION — migrate.py, in the additive-ALTER block beside the existing pass_state/genre_tags ALTERs (line 1315):
   ALTER TABLE plan_run ADD COLUMN IF NOT EXISTS is_archived BOOLEAN NOT NULL DEFAULT false;
   CREATE INDEX IF NOT EXISTS idx_plan_run_book_created_active ON plan_run(book_id, created_at DESC) WHERE NOT is_archived;
   (partial-index idiom mirrors idx_outline_node_project, migrate.py:216.)

2. MODEL — db/models.py:669 class PlanRun: add `is_archived: bool = False` (after error_detail). Add `is_archived` to _SELECT_RUN (plan_runs.py:24) — a column not in the SELECT validates to the default and lies.

3. REPO — db/repositories/plan_runs.py, four changes (three of them are the ones a BE-4-only build gets WRONG):
   a. NEW `archive(book_id, run_id) -> UUID | None`: UPDATE plan_run SET is_archived=true, updated_at=now() WHERE id=$1 AND book_id=$2 AND NOT is_archived RETURNING id. None ⇒ route 404 (mirrors canon_rules.py:160).
   b. NEW `restore(book_id, run_id) -> PlanRun | None`: same UPDATE with is_archived=false, WHERE ... AND is_archived, RETURNING {_SELECT_RUN}. None ⇒ 404 "run not found or not archived".
   c. `list_for_book` (:128): add kwarg `include_archived: bool = False`; when False append "NOT is_archived" to `where` (static predicate, no param — cursor numbering is unaffected).
   d. 🔴 `find_by_checksum` (:99) MUST get `AND NOT is_archived`. Today it does not: re-Propose identical markdown after archiving and the dedupe RESURRECTS the archived run into the picker — a silent un-archive the user never requested (the partial-index/tombstone bug class).
   e. 🔴 `plan_state_for_book` (:313) — its `SELECT COUNT(*) FROM plan_run WHERE book_id = $1` (:334) and the latest_status subquery (:336) MUST both get `AND NOT is_archived`. Today, archiving your only failed run leaves the chat's per-turn probe reporting has_plan=true, latest_status='failed' forever.
   f. LEAVE `get_for_book` (:117) permissive (no archive filter) — restore and the archived-run detail read both need it to resolve.

4. ROUTES — routers/plan_forge.py, copied from arc.py:515-537:
   @router.delete("/books/{book_id}/plan/runs/{run_id}") → _gate_book(grant, book_id, user_id, GrantLevel.EDIT) → repo.archive → 404 if None → {"id": str(run_id), "archived": True}
   @router.post("/books/{book_id}/plan/runs/{run_id}/restore", status_code=200) → same EDIT gate → repo.restore → 404 "run not found or not archived" → {"id": str(run_id), "archived": False}
   `list_plan_runs` (:131): add `include_archived: bool = Query(default=False)`, thread to svc.list_runs → list_for_book. Gate stays VIEW.
   services/plan_forge_service.py:328 list_runs: add the `include_archived` kwarg passthrough.
   MCP `.runs/` block (mcp/server.py:3835) needs NO change — it calls list_for_book with the default, so archived runs correctly drop out of the agent's package tree.

5. FE — frontend/src/features/plan-forge/api.ts: add archiveRun (DELETE) + restoreRun (POST .../restore); add include_archived to listRuns' querystring. Toast copy per 35:352 — "That run was archived." + an Undo that calls restoreRun. The word "deleted" MUST NOT appear in the copy (it is a soft-archive; a toast that lies about permanence is what makes users afraid of the button).

6. TESTS — tests/unit/test_plan_forge_router.py: (i) archive → LIST omits it; (ii) LIST?include_archived=true includes it; (iii) restore → LIST includes it again; (iv) restore of a never-archived run → 404; (v) VIEW-only grantee → 403 on BOTH archive and restore; (vi) 🔴 re-Propose the SAME source_markdown after archiving → a NEW run id, not the archived one (guards 3d); (vii) 🔴 archive the only run → /internal plan-state returns run_count=0, latest_status=null (guards 3e).

DoD: /review-impl runs at wave close; findings fixed before the wave closes.

*Evidence:* services/composition-service/app/db/migrate.py:1256-1276 (plan_run DDL — NO is_archived, unlike siblings outline_node:209, canon_rule:257, narrative_thread:330, structure_node:1122) · services/composition-service/app/routers/plan_forge.py:94-375 (13 routes, zero delete/restore) · services/composition-service/app/routers/arc.py:515-537 (the sibling archive+restore pair to mirror verbatim) · services/composition-service/app/db/repositories/plan_runs.py:99-113 find_by_checksum (no archive filter ⇒ dedupe resurrects an archived run) and :313-347 plan_state_for_book (`SELECT COUNT(*) FROM plan_run WHERE book_id = $1`, :334 — no archive filter ⇒ archived failed run haunts the chat probe forever) · docs/specs/2026-07-01-writing-studio/35_planforge_studio.md:416,430 (PS-13 MUST-BUILD) · docs/specs/.../30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md:305 (BE-11 files the identical defect on canon_rule)

### Q-35-BE3B-SOURCE-MARKDOWN
BUILD IT (BE-3b, XS) — the spec's diagnosis is confirmed by the code (the FE cannot resume what the API never sends), but the fix must be OPT-IN, not the literal unconditional one-liner, because `_serialize_run` is shared by the list route and the MCP tool result and `source_markdown` is capped at 262,144 chars (routers/plan_forge.py:38).

1) services/composition-service/app/services/plan_forge_service.py:340 — change the signature to `async def _serialize_run(self, created_by: UUID, run: PlanRun, *, include_source: bool = False) -> dict[str, Any]:`. Build the dict exactly as today, then before returning: `if include_source: payload["source_markdown"] = run.source_markdown` (PlanRun.source_markdown is a non-null `str` defaulting to "" — models.py:678 — so no None handling). Comment WHY it is opt-in: a 256 KiB source multiplied by a list page (and echoed back into an LLM tool result) is a payload/context blowup; the detail route is the only consumer that needs it.

2) plan_forge_service.py:326 (`get_run_detail`) is the ONLY caller that opts in: `return await self._serialize_run(created_by, run, include_source=True)`. Leave line 337 (`list_runs`, one call per item), 611 and 684 (review/pass responses) on the default False. This automatically keeps it out of MCP `plan_propose_spec` (app/mcp/server.py:3327 returns `"run": detail`) — which would otherwise echo the markdown the LLM just SENT straight back into its own tool result, a direct Context Budget Law violation on this very branch.

3) frontend/src/features/plan-forge/types.ts — in `PlanRunDetail`, after `source_checksum`, add `source_markdown?: string;` with a comment: present on GET /runs/{id} (and POST /runs → detail); omitted on PlanRunListPage.items. Optional (not `string | null`) is the honest type — the list truly omits the key, and a required field would make `PlanRunListPage.items: PlanRunDetail[]` lie.

4) TESTS. Backend: services/composition-service/tests/unit/test_plan_forge_router.py — (a) GET /runs/{id} body carries `source_markdown` byte-equal to what POST /runs was given; (b) the list-page item does NOT carry the key. Assertion (b) is what pins the flag and stops a later "helpful" widening from re-introducing the blowup. Frontend: the textarea-reseed test (PlannerPanel seeds `markdown` from `plan.run?.source_markdown` as a DERIVED default, mirroring `effectiveModelRef` at PlannerPanel.tsx:71-79 — never a useEffect chasing a prop) belongs to the M3/R2 FE slice that consumes this; BE-3b's Definition of Done is only "the field is on the wire + the list stays lean", plus /review-impl at wave close.

DEFAULT THE PO MAY VETO: the list page stays lean. If a future "runs gallery with source preview" wants it, the answer is a truncated `source_preview` field, not the full column.

*Evidence:* services/composition-service/app/db/repositories/plan_runs.py:25 (`source_markdown` IS in _SELECT_RUN) · app/db/models.py:678 (`source_markdown: str = ""`) · app/services/plan_forge_service.py:340-391 (_serialize_run returns source_checksum at :369, never source_markdown) · frontend/src/features/plan-forge/types.ts:32-47 (PlanRunDetail mirrors the omission) · the trap the spec missed: _serialize_run is shared — plan_forge_service.py:326 (get_run_detail), :337 (list_runs, per item), :611/:684 (pass responses) — and feeds app/mcp/server.py:3327 (`"run": detail` in plan_propose_spec), with the source capped at 262_144 chars by routers/plan_forge.py:38.

### Q-35-PS9-COMPOSITE-ID
CONFIRM the composite id — do NOT widen DocContext. The shipped seam already treats resourceId as an opaque string end-to-end (registry keys on `${type} ${resourceId}`; useJsonDocument passes it through; JsonEditorPanel only str()-coerces it), so a composite costs ZERO contract changes, while widening DocContext with runId would touch types.ts + useJsonDocument + every existing provider for one caller's benefit.

BUILDER INSTRUCTION (M3 R1, exact):

1) BE-3 (unbuilt work — write it): add `GET /books/{book_id}/plan/runs/{run_id}/artifacts/{artifact_id}` to `services/composition-service/app/routers/plan_forge.py` (router prefix `/v1/composition`, plan_forge.py:21; mirror the auth/grant dependency used by the sibling `GET /books/{book_id}/plan/runs/{run_id}` at plan_forge.py:144). Body: call `PlanRunsRepo.artifacts_by_ids(book_id, run_id, [artifact_id])` (plan_runs.py:265) and 404 on empty — that repo's `JOIN plan_run r ON r.id=a.run_id WHERE a.run_id=$1 AND r.book_id=$2` IS the tenancy check (plan_artifact has no book_id), so never bypass it with a bare `SELECT ... WHERE id=`. Return `{id, run_id, kind, content, created_at}`.

2) FE provider `frontend/src/features/studio/planforge/documents/planArtifactDocument.ts`, `type: 'loreweave.plan-artifact.v1'`, `readOnly: true` (depends on FE-1 first). `open(ctx, resourceId)`: split ONCE on the first ':' — `const i = resourceId.indexOf(':'); const runId = resourceId.slice(0,i); const artifactId = resourceId.slice(i+1);` — and if `i < 0` or either half is empty, THROW `new Error('plan-artifact resourceId must be "{runId}:{artifactId}"')` (useJsonDocument.ts:36 surfaces it as `openError`; never silently no-op). Fetch `GET /v1/composition/books/${ctx.bookId}/plan/runs/${runId}/artifacts/${artifactId}` with `ctx.token` — bookId comes from DocContext, runId+artifactId from the composite. Follow `manuscriptUnitDocument.ts` for handle shape; `save()` is unreachable under readOnly.

3) Call site — the spec's §4.1 line `host.openPanel('json-editor', { params })` is WRONG and must not be copied: that panelId is the SINGLETON, so opening a second artifact would retarget/replace the first tab. Use the shipped multi-instance form (EditorPanel.tsx:310-314) with the dock-id convention documented at StudioHostProvider.tsx:50 (`json-editor:{docType}:{resourceId}` — FULL docType, so the id is `json-editor:loreweave.plan-artifact.v1:{runId}:{artifactId}`, not the spec's abbreviated `json-editor:plan-artifact:...`):
   host.openPanel(`json-editor:loreweave.plan-artifact.v1:${runId}:${artifactId}`, { component: 'json-editor', title: `${kind} · ${artifactId.slice(0,8)}`, params: { docType: 'loreweave.plan-artifact.v1', resourceId: `${runId}:${artifactId}` }, focus: true });

4) TESTS (vitest, `frontend/src/features/studio/planforge/documents/__tests__/planArtifactDocument.test.ts`): (a) `open({token,bookId}, 'RUN:ART')` fetches the URL containing `/books/bookId/plan/runs/RUN/artifacts/ART`; (b) a malformed resourceId ('ART', '', ':x') REJECTS (asserts no silent no-op); (c) two different composite ids yield two distinct cached handles (`_liveHandleCount() === 2`) — proves the composite key doesn't collide. Plus a pytest in `services/composition-service/tests/` asserting the new route 404s for an artifact whose run belongs to ANOTHER book (tenancy).

*Evidence:* frontend/src/features/studio/documents/types.ts:10-13 (DocContext={token,bookId}) and :53 (open(ctx, resourceId) — one id); frontend/src/features/studio/documents/registry.ts:22 (`keyOf = ${type} ${resourceId}` — resourceId opaque, ':' safe); frontend/src/features/studio/documents/useJsonDocument.ts:31 (openJsonDocument(type, resourceId, {token, bookId})); frontend/src/features/studio/host/StudioHostProvider.tsx:50-52 (dock-id convention `json-editor:{docType}:{resourceId}` + `component` opt); frontend/src/features/studio/panels/EditorPanel.tsx:310-314 (shipped multi-instance call site — contradicts spec 35 §4.1's `openPanel('json-editor', …)`); services/composition-service/app/db/repositories/plan_runs.py:265-286 (artifacts_by_ids(book_id, run_id, ids) — run join IS the tenancy check); services/composition-service/app/routers/plan_forge.py:21,144 (prefix /v1/composition; BE-3 route slot absent = unbuilt, not blocked)

### Q-35-ARTIFACT-READONLY-WHY
CONFIRMED BY CODE — the artifact viewer is READ-ONLY, and the spec's rationale is fact, not assertion. Do NOT add an artifact-write route; do NOT let the viewer save. The ONLY sanctioned artifact mutation stays `POST …/checkpoint {approved, pass_id, edits}`.

BUILD FE-1 EXACTLY LIKE THIS (it must land BEFORE PS-9 — spec 35 line 558):

1. `frontend/src/features/studio/documents/types.ts:45-54` — add `readOnly?: boolean` to `JsonDocumentProvider` (provider-level = per document TYPE; a plan-artifact is read-only by kind, not per instance).

2. `frontend/src/features/studio/panels/JsonEditorPanel.tsx` — derive `const ro = provider?.readOnly === true` (provider is already resolved at :42) and then:
   - :157-161 Save button — render only when `!ro`.
   - :152-156 Revert button — render only when `!ro` (nothing can ever be dirty; an unreachable Revert is dead chrome).
   - :93-99 the ⌘S `window.keydown` effect — `if (ro) return;` INSIDE the effect so the listener is never registered. Do NOT register it and no-op inside `onSave()` — a swallowed ⌘S IS the `silent-success-is-a-bug` class this item exists to prevent.
   - :164-171 `<CodeMirror>` — pass `editable={!ro}` (mouse selection + copy still work, so the viewer stays copyable).
   - :71-83 `onChange` — early-return when `ro`, BEFORE `handle.update(parsed)` at :76. ⚠ THIS IS THE HOLE FE-1's OWN ONE-LINER MISSES: hiding Save while `update()` still fires lets a read-only doc go `dirty:true`, which lights the "● unsaved" chip at :145 — an unsaved-changes warning the user can never clear. `editable={false}` alone does not close it.
   - header: when `ro`, render a static `read-only` chip instead of the dirty/status text, plus the escape hatch: "To change this plan, approve the pass with edits, or re-run it." (That IS the sanctioned channel — POST /checkpoint.)

3. New `planArtifactDocument.ts` provider handle: `update()` and `revert()` are no-ops; `save()` MUST NOT resolve silently. `types.ts:38` contracts that save never throws (errors land in the snapshot), so `save()` sets `status:'error', detail:'plan artifacts are read-only — edit via the pass checkpoint'`. Defense in depth: if any FUTURE view calls save() on it, the user SEES a refusal instead of a fake success.

4. TEST (spec 35 DoD, line 559): in `JsonEditorPanel.test.tsx` — mount a readOnly provider's doc; assert `queryByTestId('json-editor-save')` is null; fire ⌘S and assert the handle's `save` spy was NEVER CALLED (not "called and returned undefined" — a no-op save is the bug); type into the buffer and assert the snapshot never goes dirty.

Default I am picking (veto-able): `readOnly` lives on the PROVIDER, not on the panel's `params`. Reason — read-only-ness is a property of the document type (there is no write route for plan artifacts, ever), not of how a given tab was opened; putting it in params would let a caller open the same artifact writable by passing a different flag.

*Evidence:* services/composition-service/app/routers/plan_forge.py:94-375 — all 13 plan-forge routes enumerated; NO artifact-write route exists (a writable viewer would have nothing to call). services/composition-service/app/services/plan_forge_service.py:645-666 — `_review_pass`: `_deep_merge(art.content, edits)` → `save_artifact(created_by, run_id, spec.output_kind, merged)` (NEW artifact row, never in-place) → `record_pass(run, pass_id, artifact_id=new_art.id, input_fingerprint=entry.get("input_fingerprint"))`; the in-code comment states the invariant: downstream stales "because their input pointer — this artifact's id — just changed. Derived, not written." (PF-3). FE gap confirming FE-1 is real: `grep -rn "readOnly|editable" frontend/src/features/studio/documents/ frontend/src/features/studio/panels/JsonEditorPanel.tsx` → 0 functional hits (only `readonly type`/`readonly resourceId` at types.ts:28-29); JsonDocumentProvider (types.ts:45-54) has no readOnly field; JsonEditorPanel.tsx:88-98 registers an unconditional ⌘S→`handle.save()` and :157-160 renders an unconditional Save button; JsonEditorPanel.tsx:71-76 `onChange` → `handle.update(parsed)` is the un-flagged dirtying hole.

### Q-35-PS9-PROVIDER-REGISTRATION
REGISTER AT MODULE IMPORT FROM `catalog.ts` — NOT from PlannerPanel's / PassRailPanel's mount. The spec's candidate answer is REJECTED: it does not fix the failure mode it names.

WHY the candidate is wrong: the dock layout is restored from localStorage (`useStudioLayout.ts:26-27`, `api.fromJSON(...)`). A `json-editor:loreweave.plan-artifact.v1:{runId}:{artifactId}` tab therefore returns on a fresh page load with NO guarantee PlannerPanel or PassRailPanel is mounted (the user can close those tabs and keep the JSON tab). JsonEditorPanel mounts -> useJsonDocument -> openJsonDocument -> throws `no JSON document provider for type` (registry.ts:31). Mount-scoped registration only NARROWS the browser-dead window; it does not close it.

WHY the two existing providers register on mount (do not cargo-cult them): they are BINDING-BRIDGE providers whose open() needs a live mount-scoped hook instance. entityDocument.ts:200-208 throws 'glossary entity unavailable — open the entity editor for it first' with no binding; manuscriptUnitDocument is the same via `_setManuscriptUnitBinding`. Registration sits at the mount because the provider is USELESS without the binding. `plan-artifact` has NO binding — it is read-only and REST-fetched from BE-3's `/plan/runs/{run_id}/artifacts/{artifact_id}`; everything it needs is in `DocContext {token, bookId}` + the composite `resourceId`. It is a `createFetchDocumentHandle` provider with zero mount-scoped state. And registry.ts:1-3 states the intended pattern verbatim: "module-level, register at feature import".

BUILDER INSTRUCTION (exact):
1. `frontend/src/features/plan-forge/documents/planArtifactDocument.ts` (NEW). Export `PLAN_ARTIFACT_DOC_TYPE = 'loreweave.plan-artifact.v1'`. Export idempotent `registerPlanArtifactDocumentProvider(): void` using the module guard pattern of entityDocument.ts:199-215 (`let registered = false; if (registered) return; registered = true;`). Inside, call `registerJsonDocumentProvider({ type: PLAN_ARTIFACT_DOC_TYPE, titleKey: 'documents.planArtifact', readOnly: true, open: (ctx, resourceId) => {...} })`. In `open`, split the composite id: `const [runId, artifactId] = resourceId.split(':')`; if either is missing, THROW a descriptive Error (never return a dead handle — no silent no-op). Build the handle with `createFetchDocumentHandle(PLAN_ARTIFACT_DOC_TYPE, resourceId, { load: () => GET .../plan/runs/{runId}/artifacts/{artifactId} using ctx.token, save: () => { throw new Error('plan artifacts are read-only'); } })`. Also export test-only `_resetPlanArtifactDocumentProvider()` that flips `registered = false` (mirrors entityDocument.ts:218).
2. `frontend/src/features/studio/panels/catalog.ts` — add at MODULE SCOPE, immediately after the import block: `import { registerPlanArtifactDocumentProvider } from '@/features/plan-forge/documents/planArtifactDocument';` then a bare top-level `registerPlanArtifactDocumentProvider();` with the comment: "Q-35-PS9: registered at module import, NOT panel mount — the dock restores a json-editor tab from localStorage (useStudioLayout.ts:26) with no guarantee PlannerPanel is mounted." catalog.ts is the correct anchor: it is the static 'every panel the studio CAN open, whether or not it's currently mounted' module (catalog.ts:1-6) and is imported by StudioDock.tsx:9 as the dockview component map, so it always loads before any panel renders.
3. Do NOT use a `useEffect` in StudioHostProvider instead: React runs CHILD effects before PARENT effects, so a parent-mount registration is an ordering race against a restored panel's own mount. Module scope has no such ambiguity.
4. Add ZERO `registerPlanArtifactDocumentProvider()` calls to PlannerPanel or PassRailPanel. M4 needs no registration change — that is the point of this decision.
5. TEST (this is what closes the unit-green/browser-dead gap — 'checklist => test the effect'): `frontend/src/features/plan-forge/documents/__tests__/planArtifactDocument.test.ts` — a case that imports ONLY `@/features/studio/panels/catalog` (renders NO panel, mounts NO PlannerPanel) and asserts `getJsonDocumentProvider('loreweave.plan-artifact.v1')` is defined. A second case asserts `openJsonDocument(PLAN_ARTIFACT_DOC_TYPE, 'run1:art1', ctx)` resolves against a mocked fetch, and a third asserts a malformed resourceId ('art1', no colon) REJECTS with a message rather than resolving.

NOTE FOR PO (veto-able default): this is a mechanical/architectural correction, not a product call — it strictly dominates the spec's answer (fixes strictly more cases, costs one fewer call-site). `readOnly` itself remains FE-1's slice (widen JsonDocumentProvider + honour it in JsonEditorPanel); this decision only fixes WHERE registration happens.

*Evidence:* frontend/src/features/studio/hooks/useStudioLayout.ts:26-27 — `const saved = localStorage.getItem(layoutKey(bookId)); if (saved) { api.fromJSON(JSON.parse(saved)); }` => a json-editor tab is restored on fresh load independent of PlannerPanel, so panel-mount registration cannot cover it. || frontend/src/features/studio/documents/registry.ts:31 — `if (!provider) throw new Error(\`no JSON document provider for type "${type}"\`)` (the browser-dead throw). || frontend/src/features/studio/documents/registry.ts:1-3 — header: "Mirrors the other studio registries (tools / status-bar items / effect handlers): module-level, register at feature import". || frontend/src/features/glossary/documents/entityDocument.ts:200-208 — mount-registration exists ONLY because open() needs the mount-scoped binding ('glossary entity unavailable — open the entity editor for it first'); plan-artifact has no binding. || frontend/src/features/studio/manuscript/unit/ManuscriptUnitProvider.tsx:343 — same binding-bridge pattern. || frontend/src/features/studio/panels/catalog.ts:1-6 + frontend/src/features/studio/components/StudioDock.tsx:9 — catalog is the always-loaded 'what CAN be opened, whether or not mounted' module backing the dockview component map => the correct registration anchor. || frontend/src/features/studio/documents/fetchHandle.ts:12 — createFetchDocumentHandle is the stock self-sufficient (binding-free) handle plan-artifact should use.

### Q-35-NO-HOLD-COPY
CONCERN IS CORRECT AND CONFIRMED BY CODE. Build the pass-card action row with THREE buttons and NO "Hold". Exact instructions:

(1) BUILD THE MISSING API METHOD. `planForgeApi` (frontend/src/features/plan-forge/api.ts, currently ends at `bootstrapApply` ~line 118) has NO checkpoint method. Add it, mirroring the existing `apiJson` convention:
```ts
checkpoint(bookId: string, runId: string, body: { approved: boolean; pass_id?: PlanPassId; edits?: Record<string, unknown> }, token: string): Promise<PlanRunDetail> {
  return apiJson<PlanRunDetail>(`${BASE}/books/${bookId}/plan/runs/${runId}/checkpoint`, { method: 'POST', body: JSON.stringify(body), token });
}
```
(route: plan_forge.py:275).

(2) BUTTON WIRING — exactly three, in this order:
- PRIMARY (rightmost, filled): label `Approve` when the artifact editor is clean, `Approve with edits` when dirty. ONE call: `{approved:true, pass_id, edits?}` — send `edits` in the SAME call when dirty; never save-then-approve. Grounded: the seed gate runs before any write (plan_forge_service.py:643, comment :634), so a refused approve mutates nothing. Disabled for `cast` until its bootstrap proposal reads `applied` (F-P4/PS-3).
- SECONDARY: `Save edits` → `{approved:false, pass_id, edits}`. Only enabled when dirty.
- TERTIARY (ghost/destructive): `Reject` → `{approved:false, pass_id}`.

(3) COPY (i18n `studio` ns via `useTranslation('studio')`, per BootstrapPanel.tsx:33 — every string gets a key + defaultValue):
- `planner.pass.approve` = "Approve"
- `planner.pass.approveWithEdits` = "Approve with edits"
- `planner.pass.approveWithEditsHint` = "Approving these {{pass}} edits will stale the {{count}} passes below it."
- `planner.pass.saveEdits` = "Save edits"
- `planner.pass.saveEditsHint` = "Saves your edits and marks {{pass}} rejected until you approve it — nothing below it can run."
- `planner.pass.reject` = "Reject"
The literal string "Hold" is FORBIDDEN in this panel (plan_forge_service.py:673 has only accepted|rejected — a "Hold" label would lie about the write).

(4) STUCK BANNER (the trap Save-edits sets): derive `stuckAt = blocked_at ?? (first BLOCKING pass whose decision is not in {accepted, auto})`. NEVER render from `blocked_at` alone — `blocked_at` only matches `decision=="pending"` (plan_pass_service.py:277), so it goes NULL the instant Save edits writes `rejected`, and a naive Rail would announce "nothing blocking" about a dead run. Derive in the panel; add no column. Render the rejected BLOCKING pass as an amber `rejected` chip with Approve + Re-run both live.

(5) TESTS (vitest, `frontend/src/features/plan-forge/components/__tests__/PassCard.test.tsx`):
(a) dirty editor + click Approve ⇒ EXACTLY ONE `planForgeApi.checkpoint` call, body `{approved:true, pass_id:'cast', edits:{…}}` — assert call count is 1 (this pins "no save-then-approve");
(b) 409 CHECKPOINT_REFUSED on that call ⇒ the card still shows the edits as unsaved/dirty and surfaces the refusal (nothing was written);
(c) Save edits ⇒ `{approved:false, pass_id, edits}` and the card flips to the amber `rejected` chip;
(d) `queryByRole('button', { name: /hold/i })` is null;
(e) run with `blocked_at: null` + cast `decision:"rejected"` ⇒ banner STILL reads "stuck at cast" and Approve is offered.

DEFAULT I AM PICKING (veto-able): the primary is ONE button whose label swaps Approve ↔ Approve with edits on dirty state, rather than two separate buttons — it keeps the action row at three and makes the one-call path the path of least resistance.

*Evidence:* services/composition-service/app/services/plan_forge_service.py:634 ("THE GATE RUNS BEFORE ANY WRITE") + :643 (`if approved: await self._assert_seed_applied(...)` precedes the `if edits:` → `save_artifact` branch) ⇒ approve-with-edits in one call is safe. plan_forge_service.py:673 (`decision = "accepted" if approved else "rejected"`) ⇒ there is no Hold; Save-edits writes rejected. services/composition-service/app/routers/plan_forge.py:275 (`POST /books/{book_id}/plan/runs/{run_id}/checkpoint`, body {approved, pass_id?, edits?}; ValueError → 409 CHECKPOINT_REFUSED). services/composition-service/app/services/plan_pass_service.py:213 (`is_accepted` = decision in accepted|auto) + :277 (`blocked_at` matches decision=="pending" only) ⇒ blocked_at goes NULL on reject; banner must be derived. frontend/src/features/plan-forge/api.ts:34-118 — `planForgeApi` has NO checkpoint method (unbuilt work, must be written). frontend/src/features/plan-forge/components/BootstrapPanel.tsx:33 — the `useTranslation('studio')` + defaultValue copy convention to follow.

### Q-35-DEPENDENCY-GRAPH-INVERSION
The registry is the SSOT and spec 35 §4.1 now transcribes it CORRECTLY — I re-verified all 7 rows, the 3 consequences, and the §4.1b wireframe blocker annotations against `PASS_REGISTRY` today. No spec edit is needed. What the builder must do is make the inversion UNREPEATABLE, in three concrete places:

(1) BE — NOTHING TO CHANGE. `PASS_REGISTRY` (plan_pass_service.py:55-87) already derives everything. `derive_view` (:294-323) returns, per pass row, `{pass_id, checkpoint, output_kind, depends_on[], status, decision, artifact_id, job_id, fresh, blockers[]}` plus top-level `pass_cursor` + `blocked_at`, served by `GET /v1/books/{book_id}/plan/runs/{run_id}/passes` (plan_forge.py:236). The gating answer is already on the wire.

(2) FE — THE PASS RAIL CARRIES ZERO DEPENDENCY KNOWLEDGE. Build `frontend/src/features/plan-forge/hooks/usePassLedger.ts` + `components/PassRail.tsx`, and add `fetchPasses`/`runPass`/`checkpointPass` to `frontend/src/features/plan-forge/api.ts` (which today has NO pass methods at all — grep for `passes|runPass|blockers|pass_cursor` over `frontend/src/features/plan-forge/` returns nothing, so this is greenfield; there is no existing hardcoded gating to unwind, only the risk of inventing one). Rules, each a `/review-impl` finding if violated:
  - Run button: `disabled = row.blockers.length > 0 || anyJobInFlight`. Derived from `row.blockers` from the envelope — NEVER from the row's index, its position in PASS_ORDER, or any FE-side dependency map.
  - Progress header: render `pass_cursor` / `passes.length` straight from the envelope. Do NOT count fresh rows client-side and do NOT hard-code "1/7" (the §4.1b mock shows `cursor 1/7` as an ILLUSTRATION of a derived value, not a constant).
  - Blocked copy: join `row.blockers` — "world needs cast (not accepted)". The `force:true` escape sits behind it; the 409 is the fallback, not the plan.
  - Row order: iterate `envelope.passes[]` as returned (it is already PASS_ORDER). `types.ts` may declare `type PlanPassId = 'motifs'|'cast'|'world'|'beats'|'character_arcs'|'scenes'|'self_heal'` mirroring models.py:624 for TYPING ONLY. A `PASS_DEPS`/`DEPENDS_ON` const in FE code is the defect this question exists to prevent — reject it in review.

(3) GUARD TESTS — the M1 DoD #3 test, added to `services/composition-service/tests/unit/test_plan_pass_service.py` in the style of :40-67. Build a PlanRun in the headline state (motifs completed + decision "auto" + a fingerprint recorded WITH the package artifact id; cast completed + decision "pending") and assert, with `package_artifact_id=pkg` passed to every call:
  - `blockers_for(run, "world") == ["cast"]`
  - `blockers_for(run, "beats") == []`
  - `blockers_for(run, "scenes") == ["cast", "beats", "character_arcs"]`  (motifs is accepted ⇒ filtered out; depends_on order preserved)
  - `pass_cursor(run) == 1`  and  `blocked_at(run) == "cast"`
  - `derive_view(run)["passes"][3]["blockers"] == []`  (index 3 = beats)
  ⚠ TRAP TO AVOID IN THIS TEST: `motifs` has `reads_package=True` (:57), so its fingerprint includes the package artifact id. Recording motifs' fingerprint without the package id — or asserting with a different one — makes motifs read NON-FRESH, the cursor collapses to 0, and the test happily "proves" the wrong number. Compute the recorded fingerprint via `fingerprint(input_artifact_ids=input_pointers(run, "motifs", package_artifact_id=pkg), params={})` and pass the SAME `pkg` at assert time.
  Plus the FE mirror: `PassRail.test.tsx` feeds a stub envelope with `world.blockers=["cast"]` and `beats.blockers=[]`, and asserts world's Run button is DISABLED while beats' is ENABLED — asserting off the fixture's `blockers[]`, never off row order.

(4) LIVE SMOKE (b): assert the enable/disable state matches what the LIVE API returns for that run; do not assert a literal cursor string unless the live ledger reports it.

DEFAULT THE PO CAN VETO: the Rail shows a blocked pass's Run button as disabled-with-tooltip (blockers named, click-to-scroll to the blocking row) rather than hiding it — the pass stays visible as part of the closed 7-pass set.

*Evidence:* services/composition-service/app/services/plan_pass_service.py:55-87 — PASS_REGISTRY: world depends_on=("cast",) [:65], beats depends_on=("motifs",) [:69], cast/beats checkpoint="blocking" [:62,:70]. :221-236 blockers_for iterates ONLY PASS_REGISTRY[pass_id].depends_on ⇒ blockers_for("beats") can only ever be ["motifs"]. :259-274 pass_cursor = contiguous is_fresh AND is_accepted, breaks at first failure ⇒ 1 in the headline state; :213 is_accepted = decision in ("accepted","auto"). :294-323 derive_view emits per-row blockers[]/fresh + pass_cursor + blocked_at, all DERIVED at serialization. services/composition-service/app/db/models.py:627 PASS_ORDER (serialization order only). services/composition-service/app/routers/plan_forge.py:236 GET …/passes serves it. FE: grep "depends_on|blockers|pass_cursor|blocked_at" over frontend/src/features/plan-forge/ ⇒ zero hits (api.ts has no pass methods) — greenfield, nothing to unwind.

### Q-35-OQ4-ARTIFACT-HISTORY
NO history/diff view in v1 — but the viewer must be made HONEST about latest-only, and that is a mandatory 4-line build item in M3/R1, not a copy suggestion.

BUILD (all inside M3's existing R1/BE-3 slice — no new route, no new panel):

1. KEEP `DISTINCT ON (a.kind)` at services/composition-service/app/db/repositories/plan_runs.py:355. Do NOT drop it. Do NOT add `?history=true`. Any builder who "improves" this into a history list is out of scope.

2. WIDEN the ref row with its timestamp (this is what makes "latest" a verifiable claim instead of a lie, and it is the signal the user needs to confirm their Save-edits landed):
   - plan_runs.py:355 — `SELECT DISTINCT ON (a.kind) a.kind, a.id AS artifact_id, a.created_at` (ORDER BY is already `a.kind, a.created_at DESC`, so nothing else changes).
   - plan_runs.py:363 — return `{"kind": ..., "artifact_id": ..., "created_at": r["created_at"]}`.
   - `_serialize_run` (plan_forge_service.py:348) passes it through unchanged; add `created_at` to the artifact-ref type in the FE plan-forge types.ts.
   - TEST: services/composition-service/tests/integration/db/test_repositories.py:2395 — extend the existing assertion: save TWO `spec` artifacts, assert `len(refs) == 1`, `refs[0]["artifact_id"] == second.id`, and `refs[0]["created_at"] == second.created_at`. That test IS the codification of "latest-per-kind, and we say which one".

3. FE copy — PlanRunView.tsx:50. Change the header string from `Artifacts` to `Latest per kind` (i18n key, e.g. `planForge.artifacts.latestPerKind`), and render `created_at` (relative, e.g. "2m ago") in each row next to the id. Add a one-line hint under the list: "Each kind shows its newest body. Editing a pass saves a new version — older versions are kept but not browsable yet." The json-editor tab opened from a row (PS-9, composite `{runId}:{artifactId}`) titles as `{kind} · latest`.
   - Also fold in spec 35 line 474's trap in the same hint area: after pass 7 (`self_heal`) runs, the `scene_plan` row is self_heal's HEALED output, not pass 6's — say so, or the user thinks their scenes vanished.
   - TEST (vitest, PlanRunView): renders "Latest per kind", renders the timestamp, and does NOT render any control implying versions (no "history", no "previous", no version dropdown).

WHY this is the right call, not just deference to the spec's recorded "Not in v1":
- Nothing is lost. `edits` is save-new-never-mutate (POST /checkpoint's deep-merge), so every version is already durable in `plan_artifact`. v1 not showing them destroys nothing.
- Adding it later is purely additive with zero rework: BE-3 is `GET …/plan/runs/{run_id}/artifacts/{artifact_id}` (spec 35:427), keyed by an explicit artifact id, and `artifacts_by_ids(book_id, run_id, ids)` (plan_runs.py:265) already takes an id array through the same book-scope join. A future `GET …/artifacts?kind=cast_plan&history=true` is a NEW route beside them — no contract break, no migration, nothing to undo. So there is no "build it now or pay later" pressure that would justify pulling it into v1.
- Conversely, the honesty fix is NOT deferrable: a panel headed "Artifacts" listing one row per kind, where the body silently changes under you every time a pass re-runs or you save an edit, is the repo's own `silent-success-is-a-bug` class pointed at a read surface. The user cannot tell whether their edit landed, and after pass 7 they cannot tell whose scene_plan they are reading. That is a defect the user meets on the first run, and it costs 4 lines.
- PO default if you disagree: the only thing you would be vetoing is "no version browser in v1". Say so and it becomes its own slice — D-PLANFORGE-ARTIFACT-HISTORY below.

DEFER ROW (write it, do not silently drop it) — see deferRow field.

*Evidence:* services/composition-service/app/db/repositories/plan_runs.py:351-363 — `list_artifact_refs` = `SELECT DISTINCT ON (a.kind) a.kind, a.id AS artifact_id ... ORDER BY a.kind, a.created_at DESC`, returning `{kind, artifact_id}` with NO timestamp. Its single caller is services/composition-service/app/services/plan_forge_service.py:348 (`_serialize_run`), so that list is the whole `run.artifacts` contract the FE sees. frontend/src/features/plan-forge/components/PlanRunView.tsx:48-59 renders it under a bare `Artifacts` header as unclickable `<li>`s (kind + truncated id) — nothing on the surface says "latest", which is exactly the "must not pretend" failure the OQ names. Additivity of a later history view is grounded in plan_runs.py:265 (`artifacts_by_ids(book_id, run_id, ids)`, book-scoped through `JOIN plan_run r ON r.id = a.run_id`) + spec 35:427 (BE-3 = `GET …/plan/runs/{run_id}/artifacts/{artifact_id}`, keyed by explicit artifact id). The self_heal/scene_plan aliasing trap is docs/specs/2026-07-01-writing-studio/35_planforge_studio.md:474; the recorded "Not in v1" is 35_planforge_studio.md:594. Existing test to extend: services/composition-service/tests/integration/db/test_repositories.py:2395.

### Q-35-PS5-REFINE-TYPE-DRIFT
CONFIRMED DRIFT — fix the TS type, and in the SAME slice that adds the Refine button, also close the silent-no-op the type fix does not cover. Three concrete edits:

(1) `frontend/src/features/plan-forge/types.ts:113-117` — replace `revision?: string` with an open dict that documents the keys the engine actually reads. Keep it open (`[k: string]: unknown`) because the backend prompt-dumps the WHOLE dict (`prompts.py:149`), so it is genuinely not a closed set:

export interface PlanRevision {
  /** free-text user instruction (apply_policy.py:41) */
  instruction?: string;
  /** slices the artifact + merges the patch back (refine.py:24, merge_refine_output) */
  focus_paths?: string[];
  /** own line in the prompt (prompts.py:152) */
  intent?: string;
  /** own block in the prompt (prompts.py:150) */
  source_excerpt?: string;
  [k: string]: unknown;   // whole dict is json.dumps'd into <plan_revision>
}
export interface RefinePlanBody {
  model_ref: string;
  revision?: PlanRevision;   // was `string` — backend wants a DICT
  focus_paths?: string[];
}

`InterpretPlanBody.user_message: string` is already correct — do NOT touch it. (`interpret` takes prose; `refine` takes a structured dict. Two different fields, and that asymmetry is the trap.)

(2) The Refine button MUST send a NON-EMPTY revision. `plan_forge_service.py:494-500`: if `rev` is empty AND `focus_paths` is empty, refine early-returns HTTP **200** `{"status":"no_change","fidelity_delta":0.0,"diagnosis":null}` — no job, no model resolve, no spend, nothing changed. So a button wired to send `{}` or to omit `revision` returns 200 and the user sees a success with zero effect (the repo's own "silent success is a bug" class). Wire the free-text box to `revision: { instruction: userText }` and hard-guard: if the box is empty and no focus_paths are selected, disable the button client-side — do not fire the request.

(3) Render `status === 'no_change'` as its OWN neutral state ("no change — nothing to refine"), never as an applied/success toast. Refine returns a union: 202 ack (async worker) | `{status:'applied'}` | `{status:'no_change'}` — the existing `PlanRefineResult | PlanRunAck` union in api.ts:70-72 must be discriminated on `status`, not assumed applied.

BONUS WIRING (free, and the reason the drift existed): `interpret` already RETURNS a ready-made revision dict — `interpret.py:141-199` builds `draft_revision` via `_build_revision_from_gap` (keys: instruction, focus_paths, intent, source_excerpt, scope, expect). So the interpret→refine chain is: take `interpretation.draft_revision` and POST it verbatim as `revision`. That is the canonical shape and the strongest proof the field is a dict. Consider typing `PlanInterpretation` (currently a bare `Record<string, unknown>` at types.ts:91) with at least `draft_revision?: PlanRevision` — its untyped-ness is precisely what let the `revision?: string` drift go unnoticed.

TEST (name it in the slice's DoD): a vitest on the Refine hook asserting the POST body's `revision` is an object with a non-empty `instruction` (never a bare string, never `{}`), plus a case asserting an empty input does not fire the request. Backend already enforces the contract twice — Pydantic 422s a string at `routers/plan_forge.py:60`, and `worker/operations.py:642` raises `ValueError("spec and revision required")` on a non-dict — so the FE test is the only side that is currently unguarded.

*Evidence:* DRIFT: frontend/src/features/plan-forge/types.ts:115 `revision?: string` VS services/composition-service/app/routers/plan_forge.py:60 `revision: dict[str, Any] | None`. DICT IS OPEN, NOT A CLOSED SET: app/engine/plan_forge/prompts.py:149 `rev_json = json.dumps(revision, ...)` dumps the whole dict into <plan_revision> → Record<string, unknown> is correct. KEYS THE ENGINE ACTS ON: refine.py:24 `paths = revision.get("focus_paths")` (slices spec, merge_refine_output merges back); apply_policy.py:41 `rev.get("instruction")`; prompts.py:152 `revision.get("intent")`; prompts.py:150 `revision.get("source_excerpt")`. SILENT-NO-OP TRAP (type fix alone does not cover): plan_forge_service.py:494-500 `if not rev: return "sync", {"status": "no_change", "fidelity_delta": 0.0, ...}` — empty revision + no focus_paths ⇒ HTTP 200, no job, no spend, no change. DOUBLE BE ENFORCEMENT: routers/plan_forge.py:60 (Pydantic 422 on a string) + worker/operations.py:642 `if not isinstance(spec, dict) or not isinstance(revision, dict): raise ValueError("spec and revision required")`. CANONICAL SHAPE ALREADY EXISTS SERVER-SIDE: interpret.py:65-73 `_build_revision_from_gap` → `draft_revision` (instruction/focus_paths/intent/source_excerpt/scope/expect), consumed at apply_policy.py:87 `revision = interpretation.get("draft_revision")`, and re-fed to refine internally at plan_forge_service.py:840-843 `revision = {"focus_paths": [...]}; await self.refine(..., revision=revision, ...)`. WHY IT WENT UNNOTICED: frontend types.ts:91 `export type PlanInterpretation = Record<string, unknown>;` — draft_revision is untyped on the FE.

### Q-35-F-P3-TWO-TRUTHS
CONFIRMED BUG — fix the producer (BE-21) AND keep the Rail on /passes. Both halves of the spec's candidate answer are correct; here is the exact build instruction.

(1) BE-21 — kill the second truth, do not just patch one call site. In `services/composition-service/app/services/plan_forge_service.py` add ONE private helper and route BOTH producers through it:

    async def _pass_view(self, run: PlanRun) -> dict[str, Any]:
        """The derived pass view, keyed on THIS run's latest package artifact (BE-21 / F-P3).
        `_serialize_run` used to call `derive_view(run)` with no package id, so the five
        `reads_package` passes re-fingerprinted against "" and read STALE forever: cursor 0,
        blockers naming upstreams that were fine. One derivation, one input."""
        from app.services.plan_pass_service import PACKAGE_KIND, derive_view
        package = await self._runs.latest_artifact(run.book_id, run.id, PACKAGE_KIND)
        return {
            "compiled": package is not None,
            **derive_view(run, package_artifact_id=package.id if package else None),
        }

  - In `_serialize_run` (plan_forge_service.py:383) replace `**derive_view(run),` with `**await self._pass_view(run),`.
  - In `pass_status` (plan_forge_service.py:1002-1016) delete the inline package fetch + derive_view and use `**await self._pass_view(run),` (it keeps its own `run_id`/`book_id`/`genre_tags` keys). `compiled` now comes from the helper — `GET /passes` keeps the exact response shape it has today.
  - Leave `run_pass` (:1216) alone — it already holds `package_id` for the PF-5 gate and derives correctly.
  - Cost: one extra `latest_artifact` per run in LIST. `_serialize_run` already does `_jobs.get` + `list_artifact_refs` + `latest_artifact("spec")` per run, so this adds no new N+1 class. Accept it; do not add a cache.

(2) Fix the pinning test — `services/composition-service/tests/unit/test_genre_tags_plumbing.py:88` asserts the literal buggy source string `"**derive_view(run)" in src` and WILL RED on this change (that is the point). Replace that one assertion with `assert "**await self._pass_view(run)" in src` for the plumbing check, and add the real behavioural guard as an integration test next to `test_get_run_detail_surfaces_arcs_for_a_picker` (`services/composition-service/tests/integration/db/test_repositories.py:2477`, which already builds a live PlanForgeService against the pool):

    test_run_detail_and_passes_report_the_SAME_freshness  (the anti-two-truths test)
    — seed a run, save a `package` artifact, `record_pass("motifs", status="completed",
      input_fingerprint=<fingerprinted WITH the package id>, decision accepted)`;
    — assert `detail = await svc.get_run_detail(...)` and `view = await svc.pass_status(...)` satisfy
      `detail["passes"] == view["passes"]` and `detail["pass_cursor"] == view["pass_cursor"] >= 1`;
    — and assert `(await svc.review_checkpoint(..., pass_id="motifs", approved=True))["pass_cursor"]`
      equals the same number (this is the `_review_pass`→`_serialize_run` path at plan_forge_service.py:684,
      which the spec's own note about POST /checkpoint is about).
    Pre-fix this test reds with cursor 0; post-fix it greens. That is the evidence for the wave's DoD.

(3) M4 data-source rule stands regardless, and for a stronger reason than belt-and-braces: `GET …/passes` is the only response that carries `compiled` (absent ≠ zero — a never-compiled run has NO package and every package-reading pass is un-runnable, which the Rail must render differently from "pending"). So: **PlanForge Pass Rail reads `GET /v1/composition/books/{bookId}/plan/runs/{runId}/passes` and nothing else. After ANY mutation (`POST /checkpoint`, `POST /passes/{id}/run`, `PATCH /novel-system-spec`), IGNORE the response's pass block and refetch `/passes`.** One producer in the BE, one consumer read in the FE. Do not thread the checkpoint response into Rail state even after BE-21 lands.

⚠ NAMING HAZARD for the builder: `BE-21` is used by TWO different specs. 35_planforge_studio.md:433 BE-21 = this `_serialize_run` fix (XS). 36_editor_craft_ports.md:437 BE-21 = the `resolve_model_role` engine reader (S), a hard prereq of M4a. They are unrelated. Reference them as `BE-21(35)` and `BE-21(36)` in the plan so the wave board cannot conflate them.

Not a defer: one file, one helper, root cause proven, fails no defer gate (CLAUDE.md FIX-NOW default). Not an escalation: no product/taste/cost call — the spec already sealed the answer and the code confirms it.

*Evidence:* services/composition-service/app/services/plan_forge_service.py:383 `**derive_view(run),` (no package id) vs the correct producer at plan_forge_service.py:1002-1016 (`pass_status` fetches PACKAGE_KIND and passes `package_artifact_id=package.id`). Why it breaks: services/composition-service/app/services/plan_pass_service.py:180 `if spec.reads_package: out.append(str(package_artifact_id or ""))` → None becomes "" → the recomputed fingerprint can never equal the one recorded against the real package id → `is_fresh` False (plan_pass_service.py:187-207) for the 5 `reads_package=True` passes (plan_pass_service.py:57,61,65,69,78: motifs/cast/world/beats/scenes); `motifs` is first in PASS_ORDER so `pass_cursor` (plan_pass_service.py:258-272) breaks on the first iteration ⇒ always 0. Blast radius of `_serialize_run`: get_run_detail (:326), list_runs (:337), patch_spec (:409 = PATCH /novel-system-spec), review_checkpoint (:611) and _review_pass (:684 = the POST /checkpoint pass-accept response). Pinning test that must be replaced: services/composition-service/tests/unit/test_genre_tags_plumbing.py:88 `assert "**derive_view(run)" in src`. Behavioural-test home: services/composition-service/tests/integration/db/test_repositories.py:2477. Spec rows: docs/specs/2026-07-01-writing-studio/35_planforge_studio.md:104,319,433 (and the BE-21 id collision with 36_editor_craft_ports.md:437).

### Q-35-PARAMS-UNSPECIFIED
Answer = (a) with a bounded exception, and (b) is FORBIDDEN as a generic form.

BUILDER INSTRUCTION (M4 Run-pass button, PlanForge studio):

1. DEFAULT: the FE omits `params` entirely. The POST body is `{ model_ref?: uuid, force: boolean }`. The route's Pydantic model already supplies `params = {}` (plan_forge.py:84), so an omitted key and `{}` are identical. Do NOT build a generic params form.

2. NEVER send a key the user did not explicitly change — in particular never pre-fill and send the engine defaults. `params` is an input to the PF-3 fingerprint (`sha256(canonical({"inputs":[...], "params": params or {}}))`, plan_pass_service.py:136-150), and `{"k_ceiling":3}` hashes DIFFERENTLY from `{}` even though behaviour is identical. A GUI that "helpfully" echoes defaults forks the fingerprint against every pass the MCP tool ran with `{}` → those passes read STALE → the paid Run-pass button charges the user to recompute an identical artifact. This is the paid-for-nothing defect class; it is the whole reason the answer is not "mirror the defaults".

3. Only two passes read `params` at all. If (and only if) you add tunables, add a collapsed "Advanced" disclosure on exactly these two passes, with exactly these six keys, typed as a CLOSED SET (no free-form JSON textarea):
   - `motifs`: `max_select` (int, default 4), `candidate_limit` (int, default 15) — plan_pass_adapters.py:126-127
   - `scenes`: `k_ceiling` (int, 3), `high_threshold` (int, 70), `min_scenes` (int, 2), `max_scenes` (int, 5) — plan_pass_adapters.py:253-256
   The five other passes (`cast`, `world`, `beats`, `character_arcs`, `self_heal`) never read `ctx.params` — they MUST NOT show a params affordance (an accepted-but-ignored input is the silent-no-op bug class).
   Render defaults as PLACEHOLDER text only. On submit, build `params` from touched-and-differing fields only; if none, send no `params` key. Show the defaults as hints so the user knows what they are overriding.

4. v1 DEFAULT I AM PICKING (PO may veto): SHIP STEP 1 ONLY — always `{}`, no Advanced disclosure. Rationale: the six knobs are expert tuning with sane engine defaults, the GUI's Run-pass already has a confirm step (PS-6) naming pass + model + spend, and every knob the GUI exposes is another way to accidentally fork the fingerprint. The knobs remain reachable via the MCP tool `plan_run_pass` (server.py:3594) for the agent path. If the PO wants the knobs in the GUI, step 3 is the exact, pre-specified build — no further design needed.

5. Keep `force` in the FE body (the GUI is the human's PF-5 override; the MCP tool deliberately has none — server.py:3599-3611). `force` is sent by the "Run anyway" affordance behind the 409 UPSTREAM_STALE blockers list, never by the plain Run button.

TEST that pins it: a vitest asserting the Run-pass request body for a `cast` pass has no `params` key, and that a `scenes` run with untouched Advanced fields also has no `params` key (guards the fingerprint-fork regression).

*Evidence:* services/composition-service/app/routers/plan_forge.py:84 (`params: dict[str, Any] = Field(default_factory=dict)` — optional, no declared fields) · services/composition-service/app/services/plan_pass_adapters.py:126-127 (motifs: max_select=4, candidate_limit=15) and :253-256 (scenes: k_ceiling=3, high_threshold=70, min_scenes=2, max_scenes=5) — the ONLY two `ctx.params` readers; grep for `params` under app/engine/plan_forge/ returns zero · services/composition-service/app/services/plan_pass_service.py:136-150 (fingerprint hashes `params` verbatim ⇒ explicit defaults ≠ `{}`) · services/composition-service/app/mcp/server.py:3594-3619 (MCP tool sends `params or {}`, no `force`) · services/composition-service/app/worker/operations.py:733,764,794,809 (params → fingerprint → PassContext → stored on the pass entry)

### Q-35-X4-PLAN-EFFECTS-HANDLER
BUILD the handler in M4 — but do NOT "mirror bookEffects.ts exactly" on the invalidation shape. As the spec writes it, step 8 is a guaranteed silent no-op for two reasons the code proves. Build it exactly like this:

(1) M4's NEW controller MUST be react-query — this is the load-bearing precondition. `frontend/src/features/plan-forge/` uses ZERO react-query today (usePlanRun.ts:39-72 = useState + setTimeout poll; usePlanRunsList.ts:4-5 comment says "no react-query dependency in this feature"; `grep queryKey frontend/src/features/plan-forge` = no hits). So `queryClient.invalidateQueries({queryKey:['plan-passes',…]})` invalidates an EMPTY CACHE — green unit test, dead live (the "invalidateQueries cannot reach hand-rolled state" bug class). Therefore `frontend/src/features/plan-forge/hooks/usePassRail.ts` (new, §7 step 1) is built on `useQuery`, NOT useState+fetch, with exactly these keys:
   - `['plan-passes', bookId, runId]` → GET /v1/books/{bookId}/plan/runs/{runId}/passes
   - `['plan-run', bookId, runId]`   → GET /v1/books/{bookId}/plan/runs/{runId}
   - `['plan-runs', bookId]`         → GET /v1/books/{bookId}/plan/runs (the in-panel run picker, PS-7)
   Do NOT refactor the shipped hand-rolled usePlanRun.ts/usePlanRunsList.ts (out of scope; leave them imperative — the Rail is the panel this handler serves).
   usePassRail ALSO sets `refetchInterval: 2000` while any pass has `status:"running"` (mirror `isRunPolling` at usePlanRun.ts:50-72). plan_run_pass is `async_job=True` (mcp/server.py:3583) — it only ENQUEUES. The effect handler's job is to KICK the first refetch; without the poll the Rail would freeze showing "running" forever.

(2) `frontend/src/features/studio/agent/handlers/planEffects.ts` (new) — PREFIX-invalidate, never key on runId:
```ts
import { registerEffectHandler, type EffectContext } from '../effectRegistry';
import { unwrapToolResult } from './resultEnvelope';

let registered = false;

/** plan_* WRITES only. Reads (plan_pass_status, plan_validate, plan_self_check) are excluded so a
 *  chatty agent read-loop doesn't thrash the cache — same discipline as KNOWLEDGE_WRITE_PATTERN. */
export const PLAN_WRITE_PATTERN =
  /^plan_(propose_spec|run_pass|review_checkpoint|link|handoff_autofix|apply_revision|interpret_feedback|compile)/;

function runIdFromResult(result: unknown): string | null {
  const p = unwrapToolResult(result);           // {ok, result} envelope; inner may be a JSON string
  if (!p || typeof p !== 'object') return null;
  const r = p as Record<string, unknown>;
  for (const k of ['run_id', 'plan_run_id', 'id']) if (typeof r[k] === 'string') return r[k] as string;
  return null;
}

export function planEffect(ctx: EffectContext): void {
  const { queryClient, bookId } = ctx;
  // BOOK-PREFIX, not exact key: EffectContext carries no tool ARGS (effectRegistry.ts:9-24) and
  // run_id is ONLY an arg — plan_run_pass's result is {job_id,status,pass_id} + derive_view's
  // {passes,pass_cursor,blocked_at} (plan_forge_service.py:1212-1217, plan_pass_service.py:319-323),
  // which carries NO run_id. An exact ['plan-passes', bookId, runId] handler could never fire.
  // react-query prefix-matches, so this covers every run under the book. Unconditional: a
  // plan_run_pass refusal returns ok:true + {success:false, blockers:[…]} and a wasted refetch is
  // strictly safer than a missed one.
  queryClient.invalidateQueries({ queryKey: ['plan-passes', bookId] });
  queryClient.invalidateQueries({ queryKey: ['plan-run', bookId] });
  queryClient.invalidateQueries({ queryKey: ['plan-runs', bookId] });   // plan_propose_spec mints a run
  const runId = runIdFromResult(ctx.result);    // opportunistic narrow when the payload has it
  if (runId) {
    queryClient.invalidateQueries({ queryKey: ['plan-passes', bookId, runId] });
    queryClient.invalidateQueries({ queryKey: ['plan-run', bookId, runId] });
  }
}

export function registerPlanEffectHandlers(): void {
  if (registered) return;
  registered = true;
  registerEffectHandler(PLAN_WRITE_PATTERN, planEffect);
}
/** Test-only: undo the idempotency guard after clearEffectHandlers(). */
export function _resetPlanEffectHandlers(): void { registered = false; }
```
Note the pattern ADDS `propose_spec` to the spec's list (mcp/server.py:3291 — it CREATES a run, so the run picker list goes stale without it).

(3) REGISTER it: `frontend/src/features/studio/agent/useStudioEffectReconciler.ts` — add the import next to :18-21 and call `registerPlanEffectHandlers();` inside the useEffect at :34-39. A handler file that is never imported is the classic dead-registration.

(4) TEST: `frontend/src/features/studio/agent/handlers/__tests__/planEffects.test.ts` — feed `runEffectHandlers` the LIVE ENVELOPE shape `{ok:true, result: JSON.stringify({job_id,'status':'running',pass_id:'cast',passes:[…]})}`, NOT the unwrapped payload (feeding it unwrapped is exactly what kept the M-E bug green — resultEnvelope.ts:1-7). Assert: (a) invalidateQueries called with `['plan-passes', bookId]`; (b) a read tool (`plan_pass_status`) matches NO handler; (c) a payload carrying `run_id` also invalidates the exact key.

(5) M4 live-smoke acceptance (add to §8 M4's DoD, alongside the existing (a)-(f)): with the Rail open, the agent calls `plan_run_pass` in chat → the Rail's cast row flips to `running` and then to `completed` WITHOUT a manual reload. A vitest-green handler proves nothing here (agent→GUI loops need a live browser smoke). Wave DoD also runs /review-impl per the PO policy.

*Evidence:* frontend/src/features/plan-forge/hooks/usePlanRun.ts:39-72 (useState + setTimeout poll — no react-query) · frontend/src/features/plan-forge/hooks/usePlanRunsList.ts:4-5 ("no react-query dependency in this feature") · `grep -rn queryKey frontend/src/features/plan-forge` = 0 hits ⇒ the spec's invalidateQueries would hit an empty cache · frontend/src/features/studio/agent/effectRegistry.ts:9-24 (EffectContext has tool/result/bookId/host/queryClient — NO tool args) · services/composition-service/app/services/plan_forge_service.py:1212-1217 + services/composition-service/app/services/plan_pass_service.py:319-323 (plan_run_pass result = job_id/status/pass_id + passes/pass_cursor/blocked_at — NO run_id) ⇒ exact-key ['plan-passes',bookId,runId] is uncomputable · frontend/src/features/studio/agent/handlers/resultEnvelope.ts:8-15 + bookEffects.ts:19-28 (unwrapToolResult) · handlers/knowledgeEffects.ts:16-17,47-57 (write-only pattern + idempotent register + _reset test hook to copy) · useStudioEffectReconciler.ts:18-21,34-39 (registration site) · mcp/server.py:3291,3567-3583,3661 (plan_propose_spec creates a run; plan_run_pass async_job=True ⇒ Rail must poll)

### Q-35-OQ2-EDITS-EDITOR-SHAPE
**ANSWER = (a). Structured forms for `cast` + `beats` ONLY. NO generic JSON-patch editor — not in v1, not ever, against this backend. And DO NOT wait for M2: the shapes are in the code today, so M4's soft dependency on M2 is FALSE and is hereby cut.**

WHY (a) is not a taste call — the code forbids (b):
`_deep_merge` (`validate.py:20-36`) is a **merge, not RFC-6902**. Its loop only ever SETS keys (`out[key] = ...`); nothing is ever popped. **`edits` CANNOT REMOVE ANY KEY, EVER.** A generic JSON editor's core gesture is "delete this field / this element, hit save" — the user does that, the PUT succeeds, and the artifact comes back unchanged. That is this repo's `silent-success-is-a-bug` class, shipped, on a surface the user paid an LLM to produce. A generic editor would advertise semantics the backend does not implement. Kill it.

BUILDER INSTRUCTIONS (M4, `PassRailPanel` checkpoint cards):

1. **The forms send the FULL list, never a partial one — this is the trap.** `_deep_merge` (`validate.py:23-31`) merges a list-of-dicts **by `id` (upsert, no delete)** iff `val[0]` has an `"id"` key, and **otherwise REPLACES THE LIST WHOLESALE**. Verified: **no list item in ANY of the 7 pass artifacts carries an `id`** (`plan_pass_adapters.py:146,186-199`). So cast/beats edits take the **replace-wholesale** branch — which is what makes add/remove/rename/role-change all work. But a form that PATCHes only the changed rows **silently deletes every character it omitted.** The forms serialize the entire edited array.

2. **CAST form** — artifact body is `{"cast": [...]}` (`plan_pass_adapters.py:146-150`). Per-item fields are exactly `{name, role, archetype, summary, is_new, attributes}`. Form = editable table (add row / remove row / rename / change `role`), emits `edits = {"cast": [<full list>]}`. Primary button = **Approve-with-edits** `{approved:true, pass_id:"cast", edits}` (one call; gate-before-write at `plan_forge_service.py:634`).

3. **BEATS form** — ⚠ **spec 35's OQ-2 wording is WRONG and must be corrected in the spec.** It says "edit a beat's **summary**/tension". There is no `summary` and no `tension` on a beat. The real body (`plan_pass_adapters.py:186-199`) is THREE parallel arrays: `chapters:[{ordinal, event_id, title, beat_role, intent}]`, `tension_curve:[{chapter_index, beat_role, tension_target}]`, `unmapped_beats:[...]`. Tension is **not** on the chapter row — it lives in `tension_curve`, joined by `chapter_index` ⇄ `ordinal`. So the form edits `title`/`beat_role`/`intent` on `chapters[]` and `tension_target` on `tension_curve[]`, and **emits BOTH full arrays** in one `edits` object. Render `unmapped_beats` read-only as a warning strip (pass 6 honours the curve verbatim — `plan_pass_adapters.py:238-247` — so an edited curve is load-bearing, and an unmapped beat is a beat the story never hits).

4. **The other 4 kinds** (`motif_plan`, `world_plan`, `char_arc_plan`, `scene_plan`) = **read-only viewer + "Re-run this pass"**, exactly as spec 35 §384-393 already mandates. Since `readOnly` does not exist at any layer today, implement it as: register the JSON document provider for these kinds with a `save()` that is **absent, not a no-op**, and have `JsonEditorPanel` hide/disable ⌘S when the handle has no `save` — a provider whose `save()` quietly does nothing is the same shipped bug as above.

5. **HAND M2 A CONSTRAINT (this replaces the fake dependency).** B2's `plan_pass_artifacts.schema.json` **MUST NOT add an `id` key to any cast/beat list item.** The instant an `id` appears, `_deep_merge` flips to upsert-by-`id`, `by_id` resurrects every omitted element, and **"remove a character" silently stops working** while every unit test stays green. Pin it with a regression test in `tests/unit/test_plan_pass_checkpoint.py` (which today only source-greps `_review_pass` and asserts NOTHING about merge semantics — lines 116-141): assert (i) `_deep_merge({"cast":[{"name":"A"},{"name":"B"}]}, {"cast":[{"name":"A"}]}) == {"cast":[{"name":"A"}]}` (removal works), and (ii) a `deep_merge` of a body carrying `id`s does NOT delete — as the executable statement of why no artifact schema may introduce `id`.

DEFAULT ON RECORD FOR PO VETO: a generic JSON editor is refused on correctness grounds, not scope. If the PO ever wants raw artifact authoring, the correct build is an artifact **REPLACE** route (PUT whole body → save-new-artifact), not a patch editor over `_deep_merge`. Separately, OQ-4's artifact history (`DISTINCT ON` + `?history=true`) is the real reversibility answer and stays out of v1 as already recorded.

*Evidence:* services/composition-service/app/engine/plan_forge/validate.py:20-36 — `_deep_merge` only ever SETS keys (`out[key] = val`), never pops ⇒ `edits` can never remove a key (kills the generic JSON editor); lines 23-31 = list-of-dicts merges by `id` (upsert, no delete) iff `val[0]` has `"id"`, ELSE replaces the list wholesale. services/composition-service/app/services/plan_pass_adapters.py:146-150 (`cast_plan` = `{"cast":[{name,role,archetype,summary,is_new,attributes}]}` — NO `id`) and :186-199 (`beat_plan` = `{chapters:[{ordinal,event_id,title,beat_role,intent}], tension_curve:[{chapter_index,beat_role,tension_target}], unmapped_beats:[]}` — NO `id`, NO `summary`, tension lives in a parallel array) ⇒ shapes are readable TODAY, so M4 does not depend on M2's B2 schema. services/composition-service/app/services/plan_forge_service.py:634 (gate-before-write) and :646-665 (`merged = _deep_merge(art.content, edits)` → save-new-artifact). services/composition-service/tests/unit/test_plan_pass_checkpoint.py:116-141 — existing tests only source-grep `_review_pass`; merge semantics are entirely unpinned. services/composition-service/app/services/plan_pass_adapters.py:238-247 — pass 6 honours the edited `tension_curve` verbatim.

### Q-35-OQ1-TIER-W-DESCRIPTOR
ANSWER = (a), and stronger than the spec states it: **NO `composition.plan_run_pass` Tier-W descriptor — not in this spec and not "eventually". Close OQ-1 as a CONSCIOUS WON'T-FIX, because the code REFUTES its premise.**

The premise "PlanForge's paid actions spend with NO pre-run guardrail claim" is FALSE at the money layer. `plan_run_pass` (`services/composition-service/app/mcp/server.py:3566-3620`, Tier-A `paid=True, async_job=True`) calls `PlanForgeService.run_pass` (`app/services/plan_forge_service.py:1111`), which creates a `plan_pass` job and enqueues it (`:1170-1196`). The worker's LLM call goes through `LLMClient.submit_and_wait` (`app/clients/llm_client.py:54`) → provider-registry `POST /v1/jobs`, whose `runGuardrailPreflight` (`services/provider-registry-service/internal/api/jobs_handler.go:203-218`) does a **fail-CLOSED usage-billing `guardrail.Reserve`** (`:415`) and returns **402 `LLM_QUOTA_EXCEEDED`** (surfaced to Python as `LLMQuotaExceeded`, `sdks/python/loreweave_llm/errors.py:32`) or **503** BEFORE a single token is spent. So every plan pass IS ledger-claimed against the user's spend guardrail. The only delta vs `motif_mine` is WHEN the refusal lands — in-worker at LLM submit, instead of pre-enqueue at confirm. That is a UX/fail-fast difference, not a spend hole; it does not justify minting a second confirmation convention for the same object class, which AN-8 (`28_agent_native_studio.md:192`) seals and which spec 35 §523 already forbids ("No new estimate route. No new `/actions/*` descriptor").

BUILDER INSTRUCTIONS (concrete, no further thought needed):
1. **Do NOT touch `services/composition-service/app/routers/actions.py`.** Do not add `_PLAN_RUN_PASS_DESCRIPTOR`, do not extend `_ALL_DESCRIPTORS` (`actions.py:96-101`), do not add a plan-pass confirm effect. `plan_run_pass` stays Tier-A `paid=True` on its shipped direct channel.
2. **GUI channel = PS-6 exactly.** The PlanForge panel's Run-pass button hits the existing route `POST /v1/composition/books/{book_id}/plan/runs/{run_id}/passes/{pass_id}/run` (`app/routers/plan_forge.py:303`) with an explicit `model_ref` from `ModelPicker` (never a silent default), behind an in-panel confirm step naming pass + model + "this spends", disabled while any pass job is in flight, disabled when `blockers[]` is non-empty. No `/actions/plan_run_pass/estimate` route — inventing one reproduces the three FE 404s of plan 30 §3.3.
3. **Capture the ONE real value OQ-1 was chasing, without changing any channel:** make the guardrail refusal HONEST in the panel. When a `plan_pass` job terminates `failed` because provider-registry denied the reserve, the job's error must carry the SDK's `LLM_QUOTA_EXCEEDED` code through to the panel, which renders "Spend limit reached — the pass did not run and you were not charged", NOT a generic "pass failed". Test: `services/composition-service/tests/unit/test_plan_pass_checkpoint.py` — make the worker's LLM stub raise `LLMQuotaExceeded` and assert the persisted job error/`pass_state` entry carries the quota code (and the pass returns to a non-`running` state so the rail is not wedged); FE test asserts the quota code renders the budget message.
4. **Edit `docs/specs/2026-07-01-writing-studio/35_planforge_studio.md:591`:** rewrite OQ-1 from an open question to `RESOLVED 2026-07-13 — (a) NO Tier-W descriptor, WON'T-FIX (CLAUDE.md defer gate 5)`, quoting the jobs_handler.go grounding above so no later agent re-opens it on the false "unguarded spend" premise. Also fix the same false claim wherever it appears in §4.3/§523 prose.

PO veto note: if the PO wants pre-enqueue fail-fast anyway, the cheap way is a `BillingClient.precheck` call inside `run_pass` BEFORE `self._jobs.create` (`plan_forge_service.py:1170`) — same client `motif_mine` already uses (`app/clients/billing_client.py:48`) — which gives fail-fast WITHOUT a new descriptor and WITHOUT changing the agent's channel. That is the fallback, not the default; the default above ships as written.

*Evidence:* services/provider-registry-service/internal/api/jobs_handler.go:203-218 + :415 (`runGuardrailPreflight` → fail-closed `guardrail.Reserve`, 402 LLM_QUOTA_EXCEEDED / 503) — the pre-spend claim that OQ-1 says does not exist; reached from services/composition-service/app/services/plan_forge_service.py:1111-1196 (`run_pass` → job → worker) via services/composition-service/app/clients/llm_client.py:54 (`submit_and_wait` → provider-registry /v1/jobs). Channel seals: services/composition-service/app/mcp/server.py:3566-3584 (Tier-A `paid=True`), services/composition-service/app/routers/actions.py:96-101 (`_ALL_DESCRIPTORS` — plan_run_pass absent by design), docs/specs/2026-07-01-writing-studio/28_agent_native_studio.md:192 (AN-8), docs/specs/2026-07-01-writing-studio/35_planforge_studio.md:175,523,591 (PS-6 / no new /actions descriptor / OQ-1).

### Q-35-PS6-COST-CONFIRM-SHAPE
YES — a confirm with no total-$ number is acceptable for v1, and it is the CORRECT answer, not a compromise. But "bare" must not mean "content-free": the code already supplies a truthful spend signal, so ship the confirm with FOUR facts and ZERO new routes.

BUILD THIS (M4 PlanForge run-pass button; the SAME component is reused by M3's interpret / refine / autofix / compile(run_pipeline) buttons):

1. New shared component `frontend/src/features/studio/panels/planforge/PaidPassConfirm.tsx` (one component, four call sites — do not fork it per button). It renders an in-panel confirm step (NOT a route, NOT a Tier-W token flow) containing:
   a. THE PASS — the human pass name + `pass_id` being run (from the pass view's `pass_id`/`checkpoint`, `plan_pass_service.py:305-312`).
   b. THE MODEL — the value the user explicitly picked in `ModelPicker` (`frontend/src/components/model-picker/ModelPicker.tsx`). The `model_ref` UUID is passed through to the POST body. NEVER fall back to a silent default: if `model_ref` is unset the confirm button is DISABLED with "pick a model" (the route accepts `model_ref: UUID` required on the run-pass body, `plan_forge.py:59,66`).
   c. THE SPEND CLASS + RATE — DO NOT invent a total. Reuse the pricing the FE ALREADY holds: `frontend/src/features/ai-models/api.ts` exposes `ModelPricing` (mirrors provider-registry `user_models.pricing` JSONB), plus the derived `isFree` (local provider kind OR explicit-zero pricing) and `isPriced` flags — ModelPicker already renders this as a "$"/local hint (`ModelPicker.tsx:466-470`). So the confirm says exactly one of:
      - free/local model → "Runs locally — no per-token cost." (i18n key reuse: `modelPicker.freeHint`)
      - priced model → "This SPENDS. <alias> bills $<in>/$<out> per 1M tokens; the final cost depends on how much of your plan this pass reads." (rate only — never a fabricated total)
      - unpriced (empty pricing table) → "This spends. This model has no pricing on file, so the cost cannot be shown." (fails-closed honesty; matches the api.ts comment "Empty object = unpriced (fails closed server-side)")
   d. A single primary "Run pass — this spends" button + Cancel.

2. HARD PROHIBITION (write this as a comment in the component): do NOT clone `_mine_estimate` (`services/composition-service/app/mcp/server.py:271-277`) — it returns a HARDCODED `0.50 if scope=="book" else 2.00`. That constant is legitimate only because it feeds a Tier-W billing precheck; rendering an equivalent made-up figure for a plan pass would be inventing a cost number with no computation behind it, which is precisely the trap F-P8 names. A confirm that shows a fake number is WORSE than one that shows none. And do NOT add `POST /actions/plan_run_pass/estimate` or any `/actions/<name>/estimate|confirm` path (plan 30 §3.3: three such invented FE calls 404 in production today).

3. DOUBLE-FIRE GUARD (the part that actually protects the wallet — build it, it is not optional): the run-pass rail is disabled whenever a job is in flight. Derive it purely from data the existing route already returns — `GET /books/{book_id}/plan/runs/{run_id}/passes` serializes per-pass `status` and `job_id` (`plan_pass_service.py:311-314`). Guard: `const inFlight = passes.some(p => p.status === 'pending' || p.status === 'running')`. While `inFlight`, EVERY paid button in the panel (run-pass, interpret, refine, autofix, compile) is `disabled` and the in-flight pass shows a spinner. Also keep the existing rule: disabled when `blockers[]` is non-empty (the 409 UPSTREAM_STALE at `plan_forge.py:322-328` is the fallback, not the plan). NOTE FOR THE BUILDER: there is NO server-side in-flight guard in `plan_pass_service.py` today — this is FE-only in v1, so the FE guard is the whole guard. Confirm-dialog open must also be single-flight (close the confirm on submit; the button cannot be re-clicked into a second POST).

4. TESTS (vitest, `PaidPassConfirm.test.tsx`): (i) confirm names the pass + the model alias; (ii) a local/free model renders the no-cost line and a priced model renders the $/1M rate line, driven by the `isFree`/`isPriced` helpers from ai-models/api.ts — assert NO total-$ string is rendered for either; (iii) with `model_ref` unset the confirm button is disabled; (iv) with any pass `status:'running'` in the pass view, every paid button is `disabled` and clicking fires no POST; (v) two rapid clicks on confirm fire exactly ONE POST.

DEFAULT ON RECORD (PO may veto): OQ-1 (a Tier-W `composition.plan_run_pass` descriptor on the generic `/actions/preview`+`/actions/confirm` spine, which WOULD give a real ledger-claim + usage-billing precheck) stays OUT of v1 — it changes the AGENT's channel too, and AN-8 seals one-channel-per-object-class. Nothing above blocks it later: the confirm component is the GUI leg either way, and adding the descriptor only swaps what the button POSTs to.

*Evidence:* frontend/src/features/ai-models/api.ts:6-7,35,60-91 — `ModelPricing` mirrors provider-registry `user_models.pricing`; derived `isFree` (local kind OR explicit-zero) / `isPriced` already exist FE-side · frontend/src/components/model-picker/ModelPicker.tsx:466-470 — ModelPicker already renders the "$" price hint / "Runs locally — no per-token cost" · services/composition-service/app/mcp/server.py:271-277 — `_mine_estimate` is a HARDCODED `0.50/2.00` constant ("Coarse … Not exact"), i.e. the only existing "$ estimate" in this service is invented, so it is not a pattern to copy for plan passes · services/composition-service/app/routers/plan_forge.py:59,66,303-330 — `POST /books/{book_id}/plan/runs/{run_id}/passes/{pass_id}/run` takes a REQUIRED `model_ref: UUID`, executes directly (Tier-A), returns 409 UPSTREAM_STALE with `blockers[]`; there is no estimate route and no in-flight guard · services/composition-service/app/services/plan_pass_service.py:305-322 — the derived pass view already returns per-pass `status` + `job_id` + `blockers` + `blocked_at`, which is everything the FE needs to disable the rail while a job is in flight · services/composition-service/app/routers/actions.py:60-101 — the Tier-W `_ALL_DESCRIPTORS` allowlist (publish/generate/motif_adopt/motif_mine/arc_import/conformance_run/authoring_run_*) contains NO `plan_*` descriptor, confirming plan passes are not on the propose→confirm spine.

### Q-35-OQ3-PLAN-GET-ARTIFACT-MCP
BUILD IT IN WAVE 5 — do NOT defer. Add `plan_get_artifact` as **BE-3c**, shipped in the same slice as BE-3, and amend 35 §PS-11 / OQ-3 in place to "RESOLVED — built as BE-3c" (do not fork the spec).

WHY the defer reason evaporates on inspection: (a) the deferral's stated cost driver — "a 3-schema-source FastMCP change" — is **knowledge-service's** shape, not composition's. composition-service registers every MCP tool through the `@mcp_server.tool` decorator ONLY (`app/mcp/server.py`; there is **no** bespoke `TOOL_DEFINITIONS`/pydantic-args second source — grep for it returns 0 hits). The function signature IS the advertised inputSchema: **one** schema source. (b) The repo method already exists and is already tenancy-hardened (`PlanRunsRepo.artifacts_by_ids`, `plan_runs.py:265`), and BE-3 is already adding the service-layer wrapper this wave. The whole tool is ~35 lines in a file the wave already opens. CLAUDE.md: "if fixing is cheaper than writing + carrying its defer row, just fix it" — and plan-30 §GG-2 makes the inverse gap in-register law, so nothing sealed blocks it.

BUILD DETAIL (autonomous, no further checkpoints):

1) `services/composition-service/app/services/plan_forge_service.py` — BE-3 already adds `get_artifact(user_id, book_id, run_id, artifact_id)` returning `(await self._runs.artifacts_by_ids(book_id, run_id, [artifact_id])).get(str(artifact_id))` (or None). **The MCP tool calls that SAME method** — one repo method, two front doors (the 23:356 mirror rule, inverted). Never re-query the repo from the tool and **never drop `run_id`**: `plan_artifact` has no `book_id`; the `JOIN plan_run r ON r.id = a.run_id WHERE r.book_id = $2` IS its tenancy boundary (`plan_runs.py:265-286`).

2) `services/composition-service/app/mcp/server.py` — in the PlanForge `plan_*` block (insert after `plan_self_check`, ~line 3380, next to the other Tier-R plan tools):
```python
@mcp_server.tool(
    name="plan_get_artifact",
    description=(
        "PlanForge: read the BODY of one plan artifact — the JSON a pass produced "
        "(spec, motif_plan, cast_plan, world_plan, beat_plan, char_arc_plan, scene_plan, "
        "link_report). Get artifact ids from `plan_pass_status` or the run detail's "
        "`artifacts` refs (latest per kind). Pass `path` (dot-path, e.g. 'characters.0') "
        "to fetch a subtree of a large body. VIEW on the book required."
    ),
    meta=require_meta("R", "book",
        synonyms=["read the plan", "show the cast plan", "artifact body",
                  "what did the pass output", "open the scene plan"],
        tool_name="plan_get_artifact"),
)
async def plan_get_artifact(
    ctx: MCPContext,
    book_id: Annotated[str, "The book (UUID)."],
    run_id: Annotated[str, "The plan run that owns the artifact (UUID) — required; the run join is the artifact's scope."],
    artifact_id: Annotated[str, "The artifact (UUID)."],
    path: Annotated[str | None, "Optional dot-path into the body (e.g. 'cast.0.name') — returns that subtree only."] = None,
    max_tokens: Annotated[int, "Cap on the returned body (clamped 500..20000)."] = 6000,
) -> dict:
    tc = _ctx(ctx); bid = UUID(book_id)
    await _gate(tc, bid, GrantLevel.VIEW)
    art = await _plan_svc().get_artifact(tc.user_id, bid, UUID(run_id), UUID(artifact_id))
    if art is None:
        raise uniform_not_accessible()   # cross-book or unknown id → SAME denial (H13, no enumeration oracle)
    ...
```
Return shape (OUT-1/OUT-2/OUT-5): `{artifact_id, kind, created_at, content}`; when the serialized body exceeds the clamped `max_tokens`, return `{..., "content": None, "oversized": True, "size_tokens": <n>, "top_level_keys": [...], "guidance": "pass path=<key> to fetch a subtree"}` — **report the cap, never a silently truncated JSON body** (OUT-5; the 146K-token `composition_list_outline` incident is the precedent). `path` resolves dot-path segments (int segment = list index) and returns that subtree; an unresolvable path returns `{"error": "PATH_NOT_FOUND", ...}`, not a silent `None`.

3) `services/composition-service/tests/unit/test_mcp_server.py` — add `"plan_get_artifact"` to the expected tool-name set (the Tier-R plan line at **:97** `"plan_validate", "plan_self_check",`) **and** to `TIER_R` (~:108-118). The existing name/tier assertions RED without both edits — that is the drift guard, and it stands up an in-process FastMCP app so it also proves the advertised inputSchema carries `run_id`/`artifact_id`/`path`/`max_tokens`.

4) New unit cases (same file or `tests/unit/test_plan_forge_mcp.py`): (a) an `artifact_id` from another book → uniform not-accessible, same shape as an unknown id; (b) an oversized body → `oversized: true`, `content is None`, `size_tokens` present (assert NOT a truncated body); (c) `path` selects a subtree.

5) Wave-5 DoD gains one live-smoke line (alongside the existing browser smoke): *"an agent turn calls `plan_get_artifact` on the same run the `json-editor` viewer reads and gets the same body"* — the GG-2 loop is only closed when both halves read the same bytes. `/review-impl` at wave close, as policy.

NOTE for the PO (veto-able default): the tool is **read-only**. There is deliberately no `plan_put_artifact` — the only sanctioned artifact write is the `edits` deep-merge on `plan_review_checkpoint`, which re-fingerprints; a second write door would be an un-fingerprinted mutation path (35 §PS-9's rationale, and the same reason the human viewer is read-only via FE-1).

`contracts/tool-liveness.json` needs no hand edit — it is a sweep OUTPUT (`docs/eval/tool-liveness/*/sweep.json`), regenerated, not a hand-maintained contract.

*Evidence:* services/composition-service/app/db/repositories/plan_runs.py:265-286 (`artifacts_by_ids` — the `JOIN plan_run r ON r.id = a.run_id WHERE r.book_id = $2` tenancy join already exists) · services/composition-service/app/mcp/server.py:3268-3360 (the `plan_*` family, `_plan_svc()`, `_gate(tc, bid, GrantLevel.VIEW)` + `uniform_not_accessible()` pattern to mirror; `require_meta` imported :60) · services/composition-service/tests/unit/test_mcp_server.py:97,104 (the expected-tool-name + TIER_R sets a new tool must join) · grep `TOOL_DEFINITIONS|definitions.py` in services/composition-service/app → **0 hits** (single FastMCP schema source — the 3-source caveat is knowledge-service's, not this service's) · docs/specs/2026-07-01-writing-studio/35_planforge_studio.md:427 (BE-3), :513 (PS-11), :593 (OQ-3) · docs/specs/2026-07-01-writing-studio/30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md §1 GG-2 (the inverse gap is in-register law; §0 PO-1..4 do not touch it)

### Q-35-PS12-STUCK-BANNER-PREDICATE
OVERRIDE the spec's "derive it in the panel" — fix `blocked_at` AT THE SOURCE. The spec's diagnosis is right; its chosen fix is under-inclusive, duplicates a predicate across two languages, and leaves the agent surface lying. Keep the "do not add a column" constraint (blocked_at stays derived at serialization, one producer).

THE INVARIANT: `blocked_at` must be defined IN TERMS OF `is_accepted`, so the "am I stuck" signal and the "may this pass's dependents run" gate CANNOT disagree by construction. Today they disagree: blocked_at matches `decision=="pending"` (plan_pass_service.py:288) while is_accepted matches `decision in ("accepted","auto")` (:218). Those are not complements; the gap is `rejected`, which is exactly what `approved:false` writes (plan_forge_service.py:673). This is the same reasoning the repo already applied at PF-7 ("the blocking gate and the mutation gate are the same gate, so they cannot disagree" — plan_forge_service.py:688).

SLICE 1 — services/composition-service/app/services/plan_pass_service.py:277-291. Replace the body of `blocked_at()`:
    for pid in PASS_ORDER:
        e = _entry(run, pid)
        if e.get("status") == "completed" and not is_accepted(run, pid):
            return pid
    return None
Drop the `checkpoint == "blocking"` clause. Docstring: "The first COMPLETED pass a human has not settled — pending OR rejected, any checkpoint class. Defined via is_accepted so the stuck-signal and the dependency gate cannot disagree. A never-run/running/failed pass is NOT blocked_at — it waits on a RUN, not on a human. DERIVED; never stored."

WHY NOT BLOCKING-ONLY (the hole spec 35 missed): `_review_pass` accepts ANY pass_id with no checkpoint-class check (plan_forge_service.py:613-622), so Save-edits on an ADVISORY pass also writes `rejected`. `character_arcs` is advisory (:72-75) and `scenes` depends_on it (:76-80) ⇒ a rejected `character_arcs` blocks `scenes` via blockers_for forever, while PS-12's blocking-only predicate names nothing. Same silent stall, one pass-class over.

SLICE 2 — services/composition-service/tests/unit/test_plan_pass_service.py. DELETE `test_an_ADVISORY_pass_pending_does_not_block` (:217) — it pins an UNREACHABLE state: job_consumer.py:220 is the only writer of a completed pass's decision and always writes default_decision(), which is "auto" for advisory, so completed-advisory-with-pending cannot exist. Replace with three tests:
  (a) test_a_REJECTED_blocking_pass_is_STILL_blocked_at: cast completed decision="rejected" ⇒ blocked_at == "cast"  [this is F-P10]
  (b) test_a_REJECTED_advisory_pass_is_blocked_at_too: character_arcs completed decision="rejected" ⇒ blocked_at == "character_arcs" AND "character_arcs" in blockers_for(run,"scenes")
  (c) test_blocked_at_AGREES_with_is_accepted: for any run, if some completed pass has not is_accepted ⇒ blocked_at is not None (pins the invariant, not the surprise)
Tests at :206 (pending⇒cast), :212 (accepted⇒None), :234/:248 (derive_view) are unchanged and must stay green.

SLICE 3 — FE Pass Rail (frontend/src/features/plan-forge/components/PlanRunView.tsx + hooks/usePlanRun.ts, and the M1 Rail panel). Render the "you are stuck here" banner from `view.blocked_at` DIRECTLY. Derive NOTHING in the panel — no FE-side copy of the predicate (a derived rule duplicated across BE+FE is this repo's known drift class). The amber "rejected" chip still comes from the per-pass `decision` field on the row. Test: given a fixture view with cast.decision="rejected" and blocked_at="cast", the Rail shows "stuck at cast" and Approve is live.

SLICE 4 — spec 35_planforge_studio.md: rewrite PS-12 (§2 :198-200), §4.4's Rejected row (:347), M1 DoD #4 (:551) and #6(f) (:581). DoD #4 flips from pinning the surprise to pinning the fix: POST /checkpoint {approved:false, pass_id:"cast", edits} ⇒ decision "rejected", blocked_at STILL "cast", downstream still lists cast in blockers[]. Optionally tighten mcp/server.py:3637's description to "(pending or rejected)".

MIGRATION RISK: none. blocked_at is computed on read, has exactly one producer (derive_view :322), no persisted copy, and NO runner consumes it (the runner gates on assert_runnable/blockers_for) — so widening it cannot change execution, only make the report truthful.

PO VETO NOTE (default I picked, say so if you disagree): this changes the wire meaning of `blocked_at` for the MCP tool too. That is deliberate — plan_pass_status (server.py:3632-3639) ships blocked_at to agents, describes it as "the pass a human must accept next", and lists "what is blocking the plan" as a synonym. Fixing only the panel means an agent asked "what is blocking the plan" on a rejected run still answers "nothing". That is GG-1's parity law failing on the agent side. If you want the wire field frozen instead, the fallback is the spec's panel-side derive — but then the agent surface stays wrong and you own that.

*Evidence:* plan_forge_service.py:673 (`decision = "accepted" if approved else "rejected"` — no hold) · plan_pass_service.py:277-291 (blocked_at matches decision=="pending") vs :213-218 (is_accepted matches decision in ("accepted","auto")) — the two predicates are not complements; the gap is `rejected` · plan_forge_service.py:613-622 (_review_pass accepts ANY pass_id, no checkpoint-class check ⇒ advisory passes can be rejected too) · plan_pass_service.py:72-80 (character_arcs is advisory; scenes depends_on it ⇒ rejected advisory hard-blocks downstream, which a blocking-only predicate never names) · job_consumer.py:211-221 (worker always writes default_decision ⇒ completed-advisory-with-"pending" is unreachable, so test_plan_pass_service.py:217 pins a phantom) · mcp/server.py:3632-3639 (plan_pass_status ships blocked_at to agents as "the pass a human must accept next")

### Q-35-B1B-VARIABLE-INITIAL
DO IT, in M2/B1b, with a WRITER — three files, ~15 lines, no migration, no runtime validator to break. It is not a design question: spec 27 PF-14 (27_planforge_v2_compiler.md:216) already sealed the same change; B1b is its M2-side execution. Single owner = whichever wave lands first; the other wave greps `_DEFAULT_VARIABLE_INITIAL` and skips if already gone.

1) SCHEMA — `contracts/plan-forge/novel_system_spec.schema.json`, `VariableDef.properties` (after `range`, line ~116): add
   `"initial": { "type": "number", "default": 0 },`
   Keep `additionalProperties: false`. Do NOT add `initial` to `required` (optional; absent ⇒ 0). Safe because nothing runtime-validates this schema (no `jsonschema` import anywhere in `services/composition-service/app`).

2) ENGINE (the read — without this it is a write-only contract) — `services/composition-service/app/engine/plan_forge/compile.py`:
   - Keep `_DEFAULT_VARIABLE_INITIAL = 0` as the FALLBACK only, and REWRITE its comment (lines 13-15 currently assert the opposite of the new truth: "a variable needing a non-zero baseline … cannot be expressed").
   - Replace the dict-comp at :65-69 with a read of the spec value, coerced defensively:
     ```python
     def _initial(v: dict) -> float | int:
         raw = v.get("initial", _DEFAULT_VARIABLE_INITIAL)
         if isinstance(raw, bool) or not isinstance(raw, (int, float)):
             return _DEFAULT_VARIABLE_INITIAL
         return raw
     planner_state = {v["code"]: _initial(v) for v in spec.get("layers", {}).get("variables", [])}
     ```
     (`isinstance(True, int)` is True — the bool guard is required.) `planner_state["tier"] = "baseline"` stays.

3) WRITER (so `initial` is not a field nothing ever sets) — `services/composition-service/app/engine/plan_forge/propose.py::_variable_defs`, at the declaration dict built at :200-206: the regex at :196-198 ALREADY captures the bracket as group(3) (`HA = Humanity_Anchor [100 → 0]` ⇒ `"100 → 0"`). Derive the baseline from the LEFT endpoint when numeric:
     ```python
     rng = (decl.group(3) or "").strip()
     m0 = re.match(r"^-?\d+(?:\.\d+)?", rng)
     current = {... "range": rng, ...}
     if m0:
         current["initial"] = float(m0.group(0)) if "." in m0.group(0) else int(m0.group(0))
     ```
     Omit the key entirely when the range has no numeric left endpoint (compile then defaults to 0). This makes the POC's `HA` start at 100 from the document itself — the exact case compile.py's comment says is inexpressible.

4) TESTS — `services/composition-service/tests/unit/test_plan_forge.py` (+ the no-fixture-constants file which already asserts state keys follow `layers.variables` at :109):
   - compile: a `VariableDef` with `"initial": 100` ⇒ `planning_package["planner_state"]["HA"] == 100`.
   - compile: a `VariableDef` with NO `initial` ⇒ `0` (regression guard on the default).
   - compile: `"initial": true` / `"initial": "100"` ⇒ `0` (the bool/str coercion guard).
   - propose: a doc line `HA = Humanity_Anchor  [100 → 0]` ⇒ the emitted VariableDef carries `initial == 100`; `PA = Perfection_Addiction [0 → 100+]` ⇒ `initial == 0`; a non-numeric range ⇒ key absent.
   - contract: assert `json.load(novel_system_spec.schema.json)["definitions"]["VariableDef"]["properties"]` contains `initial` with `type == "number"` (kills a silent revert).

DO NOT touch `scripts/plan-forge-poc/**` — the POC is frozen; its copy of compile.py stays as-is.

SCOPE NOTE (do not scope-creep): this question is `VariableDef.initial` ONLY. The sibling defect — `contracts/plan-forge/planner_state.schema.json:7` hardcoding `required: ["PA","HA","CD","THR"]` + `additionalProperties:false` (one novel's variables) — is B1a / PS-10 / BPS-21 and is adjudicated separately. If B1a lands in the same wave, land both in ONE commit (a spec-declared `initial` for a code outside PA/HA/CD/THR still wouldn't validate against the old planner_state contract).</decision>
<parameter name="evidence">contracts/plan-forge/novel_system_spec.schema.json:109-122 (VariableDef: required code/name/range/transition_rules, additionalProperties:false, no `initial`) · services/composition-service/app/engine/plan_forge/compile.py:13-16 ("a variable needing a non-zero baseline … cannot be expressed"; `_DEFAULT_VARIABLE_INITIAL = 0`) and :65-69 (`{v["code"]: _DEFAULT_VARIABLE_INITIAL for v in spec["layers"]["variables"]}`) · services/composition-service/app/engine/plan_forge/propose.py:196-207 (declaration regex already captures the range bracket → the free writer for `initial`) · docs/specs/2026-07-01-writing-studio/27_planforge_v2_compiler.md:216 (PF-14 already seals this exact change) · grep for `jsonschema`/`novel_system_spec.schema` in services/composition-service/app: zero hits ⇒ no runtime validator, widening the schema is non-breaking.

### Q-35-OQ6-CHECKPOINT-RACE
CONFIRM PS-8 — no OCC in PlanForge v1 — and do NOT invent an If-Match on the checkpoint. But fix the one real lost-update the code actually has.

(1) FE / PlanForge pass rail (spec 35): `POST review_checkpoint` sends NO version/If-Match header. After the call the panel refetches the run (`GET /v1/books/{book_id}/plan-runs/{run_id}`) and re-renders from the returned `pass_state` — derived freshness makes the winner's decision visible on the next read. Render each pass entry's `decision` / `decided_by` / `decided_at` (already persisted by `record_pass`, plan_pass_service.py:342-375) in the rail row, so a racer who lost sees "rejected by user · <ts>" instead of their own stale optimistic state. NO optimistic local mutation of `pass_state` — always render the server's returned run. No 412 handling on this route (there is no 412 to handle).

(2) The 412 → "changed elsewhere — reloaded" recovery is owed ONLY by panels that write outline / canon / motif (those routes DO carry OCC: routers/canon.py:168, routers/arc.py:219 and :505, db/repositories/outline.py:1022/1096/1506). Keep that recovery in those panels; do not generalize it to PlanForge.

(3) FIX-NOW backend slice (small, root-cause-clear, in the PlanForge wave, BEFORE the rail panel is wired): the pass ledger currently CAN lose a concurrent sibling-pass write, contradicting the repo's own comment. `plan_runs.py:209-215` merges with `pass_state = COALESCE(pass_state,'{}') || $n::jsonb` and claims "`||` cannot lose a sibling key" — but `record_pass()` (plan_pass_service.py:326-377) returns the WHOLE ledger rebuilt from a stale read snapshot, and every write site passes it whole, so the merge re-asserts sibling keys from the stale read. Concretely: a human accepting pass A (decision-only write) while the worker finalizes pass B → the worker read the run before A's write → its whole-object write re-asserts A's entry WITHOUT `decision` → the accept is silently dropped and the run stalls at a blocking checkpoint the user believes they approved. This needs no collaboration grant (human vs. WORKER), which is why OQ-6's "UNVERIFIED, needs two humans" framing is wrong.

  CHANGE — write the DELTA, not the ledger (no version column, no new convention, semantics for the target pass unchanged = still last-write-wins per pass):
  - `services/composition-service/app/services/plan_pass_service.py`: add next to `record_pass`:
        def pass_delta(run: PlanRun, pass_id: str, **kw: Any) -> dict[str, Any]:
            """The ONE-KEY jsonb delta for `pass_id`. The repo merges with `||`, so writing only the
            changed key is what actually makes `||`'s sibling-safety real — a whole-ledger write
            re-asserts siblings from a stale read and silently drops a concurrent pass's entry."""
            return {pass_id: record_pass(run, pass_id, **kw)[pass_id]}
    Keep `record_pass` as-is (pure, whole-state) so existing unit tests keep passing.
  - Switch all five write sites to `pass_state=pass_delta(...)`: `plan_forge_service.py:665-670` (edits→completed), `:674-678` (decision accepted/rejected), `:1190-1191` (status=running on dispatch); `worker/job_consumer.py:188-192` (failed), `:211-222` (completed+decision).
  - Update the now-stale comment on `PlanRunsRepo.update_run`'s `pass_state` param (plan_runs.py:176-178, "Written as a WHOLE object") to say: callers pass a ONE-KEY delta; the `||` merge is what keeps siblings safe.
  TESTS (services/composition-service/tests/unit/test_plan_pass_checkpoint.py):
  - `test_review_pass_writes_only_its_own_key`: assert the dict handed to `update_run(pass_state=...)` has exactly `{pass_id}` as its keys when the run already has 2+ pass entries (this reds today).
  - real-DB (xdist_group("pg")) `test_concurrent_pass_writes_do_not_clobber_siblings`: seed `pass_state` with cast+beats; snapshot run R0; write beats=completed from R0; then write cast decision=accepted from R0; re-read → BOTH survive (beats still `completed`, cast still `accepted`). Under the current whole-object write the second UPDATE reverts beats.

If a *same-pass* race is ever actually reported after this, the fix is a `version` column on `plan_run` + a repo-level compare-and-set — not an ad-hoc guard, and not in this build. Default chosen here: no OCC, per §0/AN-8; PO can veto by asking for the version column now.

*Evidence:* services/composition-service/app/db/repositories/plan_runs.py:209-215 (`pass_state = COALESCE(pass_state,'{}'::jsonb) || $n::jsonb`, with the comment "`||` cannot lose a sibling key") vs services/composition-service/app/services/plan_pass_service.py:346-377 (`record_pass` returns the WHOLE ledger rebuilt from `run.pass_state`, a stale read) and the five whole-object write sites: plan_forge_service.py:665-670, :674-678, :1190-1191; worker/job_consumer.py:188-192, :211-222. No version column: app/db/models.py:669-686 (`class PlanRun`). Idempotent checkpoint: plan_forge_service.py:572-611. OCC that DOES exist (the 412 the other panels owe): routers/canon.py:168, routers/arc.py:219 & :505, db/repositories/outline.py:1022, :1096, :1506.

### Q-35-SELFHEAL-SHADOWS-SCENES
DECIDED — do NOT solve this with copy alone. Make the run detail's artifact list carry PROVENANCE (which pass produced each artifact) so pass 6's scene_plan is visible and pass 7's is labelled as the healed one. The data is already on the run (pass_state pointers + PASS_REGISTRY.output_kind) — zero migration, zero new query. Owner: M3 (R1 viewer), BE half is a prerequisite slice in the same wave.

SLICE 1 (BE) — services/composition-service/app/services/plan_forge_service.py, _serialize_run (currently line 347 `artifacts = await self._runs.list_artifact_refs(...)`, emitted at lines 385-388).
Replace the `"artifacts"` block with a derived, provenance-bearing list. Import PASS_REGISTRY from app.services.plan_pass_service (already imported locally elsewhere in this file, e.g. line 1035 imports PACKAGE_KIND from it).
  a) `pass_kinds = {s.output_kind for s in PASS_REGISTRY.values()}`
  b) Walk PASS_REGISTRY in registry order (it IS pass order — asserted at plan_pass_service.py:89). For each pass whose `run.pass_state[pass_id]` has an `artifact_id`, append a ref:
     {"kind": spec.output_kind, "artifact_id": str(aid), "pass_id": pass_id, "superseded_by": None}
  c) Second loop: for each ref, if a LATER ref in the list has the same `kind`, set `superseded_by = <that later ref's pass_id>`. Write it as this GENERIC rule (any pass whose output_kind is re-emitted by a later pass), not a scenes/self_heal special case — it is the same law plan_runs.py:269 already states.
  d) Keep the existing `list_artifact_refs` rows ONLY for non-pass kinds (`a["kind"] not in pass_kinds`) — spec/graph/package/llm_io/validation_report/link_report — emitted with `"pass_id": None, "superseded_by": None`. This drops the ambiguous DISTINCT-ON scene_plan row entirely; do not dedupe by id, dedupe by "is this kind produced by a pass".
  e) Do NOT touch the `list_artifact_refs` SQL (plan_runs.py:351) — it stays the latest-per-kind read for the non-pass kinds.
TEST (BE): services/composition-service/tests/ — new test on _serialize_run with a run whose pass_state has scenes(completed, artifact A) and self_heal(completed, artifact B): assert `artifacts` contains BOTH, in order, that A has pass_id="scenes" + superseded_by="self_heal", and B has pass_id="self_heal" + superseded_by=None. Second test: with self_heal absent, A has superseded_by=None.

SLICE 2 (contract) — contracts/api/composition-service/plan-forge.v1.yaml, schema `PlanArtifactRef` (referenced at line 334): add `pass_id: {type: string, nullable: true}` and `superseded_by: {type: string, nullable: true}`.

SLICE 3 (FE) — frontend/src/features/plan-forge/types.ts (PlanArtifact, line 18-21): add `pass_id: string | null; superseded_by: string | null;`. frontend/src/features/plan-forge/components/PlanRunView.tsx lines 48-60: render the ref list with the label + the explanatory copy. USE EXACTLY THIS COPY (it is what plan_forge_service.py:1086-1090 actually does, so it is true by construction):
  - row with pass_id="scenes" AND superseded_by="self_heal": title `Scenes (pass 6)`, badge `superseded`, subtext: "Kept for reference. Self-heal (pass 7) revised these — the healed version below is what linking and drafting use."
  - row with pass_id="self_heal": title `Scenes — healed (pass 7)`, subtext: "Self-heal's revision of pass 6's scenes. This is the version Link → scene_plan reads."
  - any other superseded row (generic rule): badge `superseded`, subtext: "Superseded by the {superseded_by} pass — kept for reference."
  - rows with pass_id=null: unchanged (kind + short id).
TEST (FE): frontend/src/features/plan-forge/components/__tests__/PlanRunView.test.tsx — render a run with both scene_plan refs; assert BOTH rows appear, that the pass-6 row shows the `superseded` badge and the "Kept for reference" sentence, and that the pass-7 row is titled "Scenes — healed (pass 7)".

OUT OF SCOPE (explicit, so no one gilds it): do NOT touch the Rail. The confusion lives in the artifact list; the Rail shows pass status, which already distinguishes `scenes` from `self_heal` by pass_id. Default chosen — PO may veto: pass 6's scene_plan stays VISIBLE (not hidden) and is never deleted; we label rather than prune.

Consistent with plan 30 §0: this adds no new setting, no new global flag, no new route — it surfaces a field the run already holds, which is the same "expose the effective value + its source" rule the repo applies elsewhere. /review-impl runs at wave close and any bug it finds is fixed before the wave closes.

*Evidence:* services/composition-service/app/db/repositories/plan_runs.py:355 (`SELECT DISTINCT ON (a.kind)` — the lossy projection) → consumed at services/composition-service/app/services/plan_forge_service.py:348 and emitted at :385-388 → rendered at frontend/src/features/plan-forge/components/PlanRunView.tsx:48-60 (bare `kind` + id, no provenance). The provenance already exists and is already authoritative everywhere else: services/composition-service/app/services/plan_forge_service.py:1086-1090 (`_scenes_by_event`: "Read through the PASS POINTER, not by latest-kind: passes 6 and 7 BOTH emit `scene_plan`… We take pass 7's if it has run… else pass 6's"), services/composition-service/app/db/repositories/plan_runs.py:269 (`artifacts_by_ids` — "Never 'the latest of kind X'"), and services/composition-service/app/services/plan_pass_service.py:79-87 (both `scenes` and `self_heal` declare `output_kind="scene_plan"`). plan_artifact has no pass_id column (services/composition-service/app/db/migrate.py:1291-1301) — hence derive from `run.pass_state`, no migration. Contract schema to extend: contracts/api/composition-service/plan-forge.v1.yaml:332-334 (`PlanArtifactRef`).

### Q-35-B1-PLANNER-STATE-SCHEMA
DO IT — rewrite as an open map (PS-10 as stated), and fold in the adjacent same-root-cause violation the question missed. Three concrete edits, all in M2, no runtime risk (planner_state has ZERO readers; no code loads these contract files).

(1) REPLACE `contracts/plan-forge/planner_state.schema.json` entirely with:
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "https://loreweave.dev/contracts/plan-forge/planner_state.schema.json",
  "title": "PlannerState",
  "description": "Runtime planner variables for a book or arc entry point. One numeric slot per variable the spec declares in layers.variables[].code — the codes are per-book, NOT a fixed set.",
  "type": "object",
  "required": [],
  "additionalProperties": { "type": "number" },
  "properties": {
    "tier": { "type": ["string", "null"], "enum": ["baseline", "tier_1", "tier_2", "tier_3", "tier_4", null] }
  }
}
Notes for the builder: DELETE the four fixture codes PA/HA/CD/THR outright (do not keep them as optional `properties` — they are one POC novel's variables and `test_plan_forge_no_fixture_constants.py:21-29` already bans the string "THR" as a fixture leak). `required: []` is correct as PS-10 states: a spec may declare zero variables, and `tier` is a compiler convenience, not an obligation on future producers. Do NOT add `minimum: 0` to the additionalProperties number — HA-style variables decrease and future var_deltas may go negative; bounding it would re-create the same over-fitting bug in a new form.

(2) FIX THE SAME BUG NEXT DOOR — `contracts/plan-forge/planning_package.schema.json` is ALSO `"additionalProperties": false` (line 8) and its property list (lines 9-46) does NOT declare `arc_title`, but `compile.py:128` emits `arc_title` in EVERY package. So the PlanningPackage schema is violated by every book that compiles, not just books with non-PA/HA/CD/THR variables. Add to its `properties` block:
  "arc_title": { "type": "string" }
(leave it out of `required` — it is derived and always present, but requiring it buys nothing.) This is a one-line fix; per CLAUDE.md FIX-NOW default it is cheaper than carrying a defer row.

(3) CLOSE THE HOLE THAT LET IT ROT — nothing machine-checks producer-vs-contract, which is WHY a POC fixture could masquerade as a contract for this long. Add `jsonschema>=4.20` to `services/composition-service/requirements-test.txt` (currently only pytest/pytest-asyncio/respx; jsonschema 4.26.0 is already installed in the dev env) and append to `services/composition-service/tests/unit/test_plan_forge_no_fixture_constants.py` a test that loads BOTH contract files from `contracts/plan-forge/` (resolve via a repo-root-relative Path; register both in a jsonschema RefResolver/registry so the `$ref: planner_state.schema.json` at planning_package.schema.json:13 resolves) and validates `compile_artifacts(_romance_spec(), arc_id="arc_1")["planning_package"]` against `planning_package.schema.json`. This test MUST FAIL on today's schemas (TR/GR trip `additionalProperties:false` + the missing PA/HA/CD/THR trip `required`; `arc_title` trips the package's closed set) and pass after edits (1)+(2) — write it first and watch it red, or it proves nothing. That red-then-green is the Definition of Done for this slice.

DEFAULT THE PO CAN VETO: I kept the `tier` enum values exactly as-is (baseline/tier_1..tier_4). They look generic enough to be real contract, not fixture — but if they too came from the POC novel's tier ladder, say so and they become an open string.

*Evidence:* contracts/plan-forge/planner_state.schema.json:7-8 (`"required": ["PA","HA","CD","THR"]` + `"additionalProperties": false`) vs services/composition-service/app/engine/plan_forge/compile.py:65-69 (`planner_state = {v["code"]: 0 for v in spec["layers"]["variables"]}`; line 69 adds `tier`) — the artifact violates both clauses for any book not declaring exactly PA/HA/CD/THR. SAFE TO FIX: compile.py:15 states in-code "nothing reads `planner_state` today"; grep for `planner_state` across services/ + frontend/src/ returns only the producer and its own tests; grep for `contracts/plan-forge` outside contracts/ returns EMPTY (no runtime validator). CODE IS ALREADY CORRECT, ONLY THE CONTRACT LAGS: tests/unit/test_plan_forge_no_fixture_constants.py:108-111 already asserts `set(state) - {"tier"} == {"TR","GR"}` for a romance spec, and line 21-29 already bans "THR" as a fixture-leak string. PROVENANCE: `git log -- contracts/plan-forge/planner_state.schema.json` = one commit, e6275e257 "docs(plan-forge): ship POC complete" — it is the POC fixture, exactly as the question says. ADJACENT VIOLATION (bigger blast radius, missed by the question): contracts/plan-forge/planning_package.schema.json:8 is `"additionalProperties": false` and its properties block (lines 9-46) omits `arc_title`, while compile.py:128 emits `"arc_title"` in every package — so EVERY compiled book violates the PlanningPackage schema today, not just the non-PA/HA/CD/THR ones.

### Q-35-EMPTY-NOT-COMPILED
BUILD IT AS SPEC 35 §4.4 STATES — and go one step further than the spec: in the `compiled:false` state render ZERO pass rows, not seven greyed ones.

WHERE: new `frontend/src/features/plan-forge/components/PassRailPanel.tsx`, registered as panel id `plan-passes` in `frontend/src/features/studio/panels/catalog.ts` (next to the `planner` row at line 116).

WHAT: a strict 4-way render switch, evaluated in this order, BEFORE any pass row is rendered:
1. LOADING (runs list or ledger in flight) → render exactly 7 skeleton rows by mapping a FE-local `PASS_ORDER`. Never a spinner, never `<Spinner/>`, never `role="status"`.
2. NO RUNS (`runs.length === 0`, derived from `GET …/plan/runs` — NOT from a 404 on `/passes`) → EmptyState: "No plan run for this book yet." + primary button "Open the Planner" wired to `host.openPanel('planner', { focus: true })`. No `<Link>`, no `useNavigate()` — DOCK-7.
3. NOT COMPILED (`ledger.compiled === false`) → EmptyState: "This run has no compiled package — the passes read it. Compile it in the Planner first." + the same `host.openPanel('planner')` button. **Render no pass rows and no Run buttons at all.** Grounding: `PASS_REGISTRY` (plan_pass_service.py:56-70) gives BOTH dependency-graph roots — `motifs` and `cast`, the only two with `depends_on=()` — `reads_package=True`. With no package there is not one runnable pass in the graph, so a rail of seven "pending" rows with live Run buttons is both false and a paid-action trap (a user clicks Run on `motifs`, pays, and it cannot run).
4. ELSE → the rail.

A 404 from `GET …/passes` is a DIFFERENT state from (2) — it means "unknown/archived run": show "That run no longer exists." and fall back to the newest remaining run (§4.4 Archived-run row). Do not collapse it into "no runs".

FE `PASS_ORDER`: add `export const PASS_ORDER = ['motifs','cast','world','beats','character_arcs','scenes','self_heal'] as const;` to `frontend/src/features/plan-forge/types.ts`, mirroring `services/composition-service/app/db/models.py:627-629`.

TESTS — `frontend/src/features/plan-forge/components/__tests__/PassRailPanel.test.tsx` (vitest + RTL), 4 cases:
- loading → `getAllByTestId('pass-skeleton-row')` has length **7**; `queryByRole('status')` is null.
- no runs → clicking the CTA calls a mocked `host.openPanel` with `'planner'`; a mocked `useNavigate` is asserted **not** called (DOCK-7 regression pin).
- `compiled:false` → the copy is present; `queryAllByTestId('pass-row')` length **0**; `queryAllByRole('button', { name: /run/i })` length **0**; the CTA calls `host.openPanel('planner')`.
- `compiled:true` → 7 real `pass-row`s, no skeletons, no empty-state copy.
- drift pin: assert the FE `PASS_ORDER` array deep-equals `ledgerFixture.passes.map(p => p.pass_id)` so a backend pass added/renamed reds the FE.

BACKEND: add/confirm `test_pass_status_compiled_false_when_no_package` in composition-service unit tests asserting `pass_status()` returns `compiled: false` and still emits all 7 rows (the FE, not the service, is what suppresses them).

DEFAULT I AM PICKING (veto-able): zero rows in state 3, rather than seven disabled/greyed rows. Rationale — the service deliberately distinguishes absent from zero, and disabled rows still imply "the compiler is merely waiting to be told to go," which is exactly the impression the "Absent ≠ zero" comment was written to prevent.

*Evidence:* services/composition-service/app/services/plan_forge_service.py:1012-1016 — `# Absent ≠ zero: a run that has never compiled has NO package, and every package-reading pass is therefore un-runnable. Say so, rather than reporting seven tidy "pending" rows…` / `"compiled": package is not None`. HARDER GROUNDING (beyond the spec): services/composition-service/app/services/plan_pass_service.py:56-70 — `motifs` (`depends_on=(), reads_package=True`) and `cast` (`depends_on=(), reads_package=True`) are the ONLY roots, and BOTH read the package ⇒ with `compiled:false` no pass in the graph is runnable, so no Run button may render. Closed set: services/composition-service/app/db/models.py:627-629 `PASS_ORDER = ("motifs","cast","world","beats","character_arcs","scenes","self_heal")`. Route carrying the field: services/composition-service/app/routers/plan_forge.py:236 `GET …/plan/runs/{run_id}/passes`. DOCK-7 door exists: frontend/src/features/studio/panels/catalog.ts:116 (`{ id: 'planner', component: PlannerPanel, … }`) + frontend/src/features/studio/host/StudioHostProvider.tsx:52 (`openPanel: (panelId, opts?) => void`). Unbuilt-not-blocked: frontend/src/features/plan-forge/api.ts has no `passes`/`checkpoint` method (grep for `passes|checkpoint` → zero hits).

### Q-35-POLL-IDIOM
OVERRIDE the spec's candidate answer. Do NOT copy usePlanRun's hand-rolled setTimeout+genRef loop into usePassRail — that hook is the plan-forge one-off, not the house idiom, and copying it makes spec 35 §7 item 8 a silent no-op (queryClient.invalidateQueries cannot reach useState). Build usePassRail on the repo's DOMINANT poll idiom — react-query refetchInterval — which honours "do not invent a second poll idiom" correctly (react-query IS the first idiom; usePlanRun is the second).

BUILD (M4):
1. frontend/src/features/plan-forge/api.ts — add `getPasses(bookId, runId, token): Promise<PassLedger>` → GET /v1/composition/books/{bookId}/plan/runs/{runId}/passes.
2. frontend/src/features/plan-forge/types.ts — add `PassLedger` ({run_id, book_id, genre_tags, compiled, passes[], pass_cursor, blocked_at}) and, next to the existing `isRunPolling` (types.ts:130), export:
     export const PASS_POLL_MS = 2000;
     export function isLedgerPolling(l?: PassLedger | null): boolean {
       return !!l && l.passes.some((p) => !!p.job_id && !TERMINAL_JOB_STATUSES.includes(p.job_status ?? ''));
     }
   (i.e. "any pass has an in-flight job_id" — mirrors isRunPolling's shape, one predicate, one home.)
3. frontend/src/features/plan-forge/hooks/usePassRail.ts (new, no JSX — MVC rule):
     const passes = useQuery({
       queryKey: ['plan-passes', bookId, runId],
       queryFn: () => planForgeApi.getPasses(bookId, runId!, token!),
       enabled: !!token && !!bookId && !!runId,
       refetchInterval: (q) => (isLedgerPolling(q.state.data) ? PASS_POLL_MS : false),
     });
   The run-switch guard the spec asked for is satisfied BY CONSTRUCTION: runId is in the queryKey, so a tick for run A can never write run B's ledger and react-query drops the in-flight result on key change. No genRef ref. Mutations (POST …/passes/{id}/run, POST …/checkpoint, POST …/link) are useMutation → onSuccess: qc.invalidateQueries({ queryKey: ['plan-passes', bookId, runId] }) — mirror authoringRuns/hooks.ts:56-60.
4. frontend/src/features/studio/agent/handlers/planEffects.ts (spec §7 item 8) — invalidate with a PREFIX key so it lands regardless of the panel's selected run: qc.invalidateQueries({ queryKey: ['plan-passes', bookId] }). Its second target, ['plan-run', bookId, runId], is a DEAD KEY (usePlanRun holds no cache entry) — do not ship a no-op invalidation. Instead add `reloadPlanRun?: (runId: string) => void` to EffectContext (effectRegistry.ts:9-23, exactly mirroring the existing reloadChapter/reloadScenes escape hatches that exist for hand-rolled state), supply it from PlannerPanel's usePlanRun.loadRun in useStudioEffectReconciler, and call ctx.reloadPlanRun?.(runId) in planEffect. usePlanRun itself is NOT refactored in this wave.
5. TESTS (frontend/src/features/plan-forge/__tests__/usePassRail.test.tsx, real timers + QueryClientProvider — copy the harness in features/enrichment/hooks/__tests__/useEnrichmentJobs.test.tsx:131,155):
   (a) ledger with an in-flight pass job_id → a second fetch fires after 2s;
   (b) all-terminal ledger → refetchInterval false, NO further fetch;
   (c) run-switch: rerender with runId B while A's fetch is in flight → A's resolved ledger never renders (the stale-resurrect regression the genRef guard existed to stop);
   (d) planEffects: fire a plan_run_pass tool result → assert invalidateQueries called with ['plan-passes', bookId] AND reloadPlanRun called (spy) — the §7-8 "agent runs a pass, Rail sits stale" bug.
Default I am picking, veto-able: usePlanRun stays hand-rolled (out of scope for M4; migrating it risks the shipped Planner panel). If the PO wants one idiom repo-wide, that is a separate S-size follow-up.

*Evidence:* frontend/src/features/plan-forge/hooks/usePlanRun.ts:39-72 (hand-rolled useState+setTimeout+genRef — NO react-query cache entry) vs frontend/src/features/studio/agent/effectRegistry.ts:9-23 (EffectContext offers only `queryClient` + explicit reload* callbacks — the callbacks exist BECAUSE invalidateQueries cannot reach hand-rolled state; see bookEffects.ts:36-40) vs spec 35 §7 item 8 (line 491) which mandates invalidating ['plan-passes', bookId, runId]. House poll idiom, documented as such: frontend/src/features/composition/authoringRuns/hooks.ts:1-3 ("Polling pattern mirrors useCampaignQueries.ts (this repo's established sibling for a run-like FSM entity): refetchInterval: (query) => isActive(...) ? ms : false") and :41 — same shape in useCampaignQueries.ts:39, useEnrichmentJobs.ts:21, useResearchJobs.ts:29, useJobLogs.ts:66, useWikiGenJob.ts:54, useExtractionJobs.ts:90, useTemporalReads.ts:64, useProjectState.ts:245. Predicate to mirror: frontend/src/features/plan-forge/types.ts:130 (isRunPolling).

### Q-35-B2-PASS-ARTIFACT-SCHEMA
WRITE THE SCHEMA FOR SIX KINDS, IN ONE FILE, AND MAKE A TEST ENFORCE IT. The spec's framing is confirmed by the code; the "unnamed 7th kind" draft was wrong.

FILE 1 — CREATE `contracts/plan-forge/plan_pass_artifacts.schema.json` (draft-07, `$id: https://loreweave.dev/contracts/plan-forge/plan_pass_artifacts.schema.json`, title "PlanPassArtifacts"). Shape: a top-level object with a `definitions` block holding ONE subschema per kind, named EXACTLY as the `PlanArtifactKind` literals (models.py:636) so BE-3 can select by the artifact's stored `kind` with no mapping table: `motif_plan`, `cast_plan`, `world_plan`, `beat_plan`, `char_arc_plan`, `scene_plan`. Every subschema is `type: object`, `additionalProperties: false`. Do NOT add a `oneOf`/discriminator at the root — the artifact row already carries `kind`; BE-3 refs `#/definitions/<kind>`.

DO NOT add a `version` const, even though every sibling plan-forge schema has one (plan_document.schema.json:10 requires it). The adapters write NO version field; requiring one reds every real body. This is the single most likely builder mistake.

BODIES — copy verbatim from `services/composition-service/app/services/plan_pass_adapters.py` (the writer is the source of truth):
- `motif_plan` (run_motifs, L112-134): required `motifs` (array of {code,name,summary,why,arc_role} — all string, all required). PLUS optional `degraded` (boolean) + `warning` (string) — the no-retriever branch (L119-120) emits them and "absent != zero" is deliberate. Omit them and the degraded path fails validation.
- `cast_plan` (run_cast, L138-150): required `cast` (array of {name,role,archetype,summary: string; is_new: boolean; attributes: object with string values — `cast_attributes` maps to glossary codes `role`/`relationships`/`personality`/`description`, emits only non-empty, so `attributes` is `additionalProperties: {type: string}`, NOT a fixed key set).
- `world_plan` (run_world, L154-168): required `entities` (array of {name: string; kind: string enum ["location","faction","concept"] per WORLD_KINDS, world_plan.py:44; summary: string; is_new: boolean; attributes: object of string→string}).
- `beat_plan` (run_beats, L172-200): required `chapters` (array of {ordinal: integer; event_id: string; title: string; beat_role: string|null; intent: string}), `tension_curve` (array of {chapter_index: integer; beat_role: string|null; tension_target: integer 0..100}), `unmapped_beats` (array of string). All three required — `unmapped_beats` is surfaced-not-swallowed by design.
- `char_arc_plan` (run_character_arcs, L204-219): required `character_arcs` (array of {name,role,arc: string; introduce_at_chapter: integer|null}).
- `scene_plan` (`_decompose_to_artifact`, L308-345) — VALID FOR BOTH PRODUCERS: required `arc_title` (string), `chapters` (array of {chapter: {chapter_id,title: string; sort_order: integer; beat_role: string|null; intent: string}; scenes: array of {title,synopsis: string; tension: integer 0..100 (always coerced, plan.py:330-334 — never null); present_entity_ids: array of UUID-format string (pass 7's `_artifact_to_decompose` does `UUID(e)`, L370 — a non-UUID crashes the heal pass, so the pattern belongs here); present_entity_names_unresolved: array of string; suggested_k: integer}; warning: string|null; exit_state: null OR {characters,world,plot: string; advances: array of string}}), `unmapped_beats` (array of string), `motif_coverage` (object, free-form). PLUS **`heal` OPTIONAL** — object {findings: array of {chapter,scene: integer; type,issue,fix: string; applied: boolean; skip_reason: string|null} (required); edits_applied: integer (required); note: string (OPTIONAL — only the "no scenes to heal" branch, L279)}. THIS IS THE LOAD-BEARING RULE: pass 6 emits scene_plan WITHOUT `heal`; pass 7 emits it WITH. Under `additionalProperties: false`, `heal` present-but-optional is the only shape that validates both. Marking it required breaks pass 6; banning it breaks pass 7.

FILE 2 — CREATE `services/composition-service/tests/unit/test_plan_pass_artifact_schema.py`. Without it the schema is decorative and drifts. It must: (a) load the schema via `Path(__file__).parents[4] / "contracts" / "plan-forge" / "plan_pass_artifacts.schema.json"`; (b) assert `set(schema["definitions"]) == {spec.output_kind for spec in PASS_REGISTRY.values()}` — this is the guard that keeps the file honest when a pass is added, and it mechanically re-derives "6 kinds from 7 passes"; (c) validate REAL adapter output, not hand-written dicts — reuse the fixture from `test_plan_pass_adapters.py:84` (`test_the_scene_plan_round_trip_is_LOSSLESS`) and assert `_decompose_to_artifact(result)` validates against `#/definitions/scene_plan`; (d) THE CRITICAL TEST — assert the scene_plan subschema validates BOTH producers: pass 6's body (no `heal`) AND pass 7's body (`heal` present), reusing the existing branches at `test_plan_pass_adapters.py:143` (`test_self_heal_with_no_scenes_says_so...`, which yields the `heal.note` shape); (e) assert `run_motifs`'s degraded body (test at L127) validates against `#/definitions/motif_plan`; (f) an `exit_state: None` case AND an `exit_state` populated case — the null branch is the field that already caused a live AttributeError that three redeliveries hid (see the comment at plan_pass_adapters.py:334-338), precisely because a fixture never exercised it.

FILE 3 — ADD `jsonschema>=4.21` to `services/composition-service/requirements-test.txt`. It is NOT currently a declared dep of composition-service (only `pytest`, `pytest-asyncio`, `respx`). It happens to import on this dev host (4.26.0), so a test written without this line passes locally and fails in a clean container — a false-green.

FILE 4 — ADD a row to `contracts/plan-forge/README.md`'s table: `| PlanPassArtifacts | plan_pass_artifacts.schema.json |`.

DEFAULT THE PO CAN VETO: `motif_coverage` is left free-form (`type: object`) because its writer (`DecomposeResult.motif_coverage: dict[str, Any]`, plan.py:114) is explicitly `Any` telemetry — pinning it would over-constrain a field the engine treats as open. Everything else is closed (`additionalProperties: false`), which is what makes M4's structured edit forms (OQ-2) derivable from this file.

*Evidence:* services/composition-service/app/services/plan_pass_service.py:55-87 (PASS_REGISTRY — 7 passes; self_heal output_kind="scene_plan" at :85 identical to scenes at :79, with the by-POINTER rationale in the comment at :83-84) · services/composition-service/app/db/models.py:631-638 (PlanArtifactKind literals: the six v2 kinds are exactly motif_plan, cast_plan, world_plan, beat_plan, char_arc_plan, scene_plan; heal_report/link_report are NOT pass outputs) · services/composition-service/tests/unit/test_plan_pass_service.py:59-60 (already asserts self_heal.output_kind == scenes.output_kind == "scene_plan") · services/composition-service/app/services/plan_pass_adapters.py:112-345 (every body verbatim; :119-120 motif degraded+warning branch; :278-279 heal.note branch; :286-293 heal findings/edits_applied; :308-345 _decompose_to_artifact = the shared scene_plan writer; :370 UUID(e) forces UUID-format present_entity_ids) · app/engine/plan.py:330-334 (tension always coerced int 0..100, never null) · app/engine/world_plan.py:44 (WORLD_KINDS = location|faction|concept) · contracts/plan-forge/plan_document.schema.json:10 (the `version` const convention that must NOT be copied — adapters write no version) · services/composition-service/requirements-test.txt (jsonschema absent → must be added; grep for "jsonschema" across services/*/tests returns only chat-service, so nothing validates contracts/plan-forge/ today)

### Q-35-LINK-GATE-ASYMMETRY
Pick **(a) — honest copy, client-side strict predicate — but the strict predicate GATES A CONFIRM, NOT A DISABLE.** Hard-disable ONLY where the service genuinely refuses. Rationale (from code, not taste): `scenes` and `self_heal` are both `checkpoint="advisory"` (plan_pass_service.py:76-88), and `default_decision()` (:380-386) stamps `decision="auto"` the moment an advisory pass completes, which `is_accepted()` (:213-218) counts as accepted. So "fresh + accepted" collapses to "fresh" in every normal run — option (a) as literally written would disable Link only on STALENESS, and §4.4 already rules that stale means "do this again", not "error". Hard-disabling there deletes the user's only GUI door to an action the service permits (GG-1: every backend capability must have a human surface) and buys nothing. Build it exactly like this:

**BE: no change.** The service gate stands as-is. Do not add a freshness/acceptance check to `relink` — the linker is idempotent and never reclaims a user edit (:1030-1032), so linking a stale plan is recoverable, not destructive.

**FE — `frontend/src/features/plan-forge/api.ts`:** add `linkPlanRun(token, bookId, runId, target: 'skeleton'|'scene_plan')` → `POST /v1/composition/books/{bookId}/plan/runs/{runId}/link`. On 409 read `detail.code === 'LINK_REFUSED'` and throw an error carrying `detail.message` verbatim.

**FE — M4 foot-bar "Link to spec tree ▾" (new component under `frontend/src/features/plan-forge/components/`, fed by the `/passes` ledger the panel already polls; NO new BE route, NO second fetch):** derive, per spec 35 §4.2's single ledger read:
- `sceneSource = passes.self_heal.status==='completed' ? self_heal : (passes.scenes.status==='completed' ? scenes : null)` — MIRROR the service's pointer order (`_scenes_by_event`, plan_forge_service.py:1089: self_heal preferred, else scenes). Do not use latest-by-kind.
- `serviceWouldAccept = sceneSource !== null`
- `strict = serviceWouldAccept && sceneSource.fresh && ['accepted','auto'].includes(sceneSource.decision)`

Three states for the `scene_plan` menu item:
1. `strict` → **enabled, plain**. Click links immediately.
2. `serviceWouldAccept && !strict` → **enabled, amber "stale" chip**, click opens a confirm (reuse the same secondary-affordance shape as §4.3's "Run anyway"): *"This scene plan is stale — its inputs changed since `{sceneSource.pass_id}` ran. Linking it now puts the OLDER scenes in the spec tree. Re-run `scenes` first, or link it anyway."* Buttons: **Re-run scenes** (scrolls to that row) · **Link anyway**. Free action, no cost confirm.
3. `!serviceWouldAccept` → **disabled**, tooltip = the service's own words: *"No scene plan to link — run the `scenes` pass first."*

`skeleton` menu item: enabled iff the ledger's `compiled === true` (plan_forge_service.py:1012-1016); else disabled with *"This run has no compiled package — compile it in the Planner first."* (the service's :1047 message).

**Always** render a 409 `LINK_REFUSED` `detail.message` verbatim in a toast, in BOTH targets, even when the client predicate said go — the FE cannot see the artifact's `chapters` emptiness that :1055 refuses on, so the client predicate is an optimization, never the truth. (Repo law: mocked-client-hides-server-side-filters.)

**COPY RULE (the actual answer to the CONCERN):** no string in this panel may assert the service enforces freshness or acceptance. BANNED: "the server requires an accepted/fresh scene plan", "you must re-run before linking". REQUIRED framing: what the link WILL DO ("the spec tree will show the older scenes") and what the user SHOULD do ("re-run first"). Add this as an inline comment above the confirm copy so a later agent does not "tighten" it into a lie.

**Tests (`frontend/src/features/plan-forge/components/__tests__/`):** (1) `sceneSource` picks `self_heal` over `scenes` when both completed; (2) stale scene source ⇒ item is NOT disabled and the confirm renders; (3) no completed scenes/self_heal ⇒ item IS disabled; (4) `compiled:false` ⇒ skeleton item disabled; (5) a 409 `LINK_REFUSED` from a click the predicate allowed renders `detail.message` verbatim; (6) a copy-assertion test greps the rendered confirm for the banned phrasing ("server requires", "must be accepted") and fails on a hit.

PO veto note: if you would rather the stale case be a plain hard-disable (no "Link anyway"), say so — that is the only knob in this answer.

*Evidence:* services/composition-service/app/services/plan_forge_service.py:1053-1062 (scene_plan gate = "_scenes_by_event returned something") + :1089-1091 (`_scenes_by_event` accepts a pass entry on `status == "completed"` only — reads neither `fresh` nor `decision`); services/composition-service/app/services/plan_pass_service.py:76-88 (`scenes` + `self_heal` are `checkpoint="advisory"`), :380-386 (`default_decision` → advisory = `"auto"`), :213-218 (`is_accepted` counts `"auto"`) ⇒ "accepted" is auto-true for both scene producers, so the strict predicate is really just `fresh`; :316 (`derive_view` already ships `fresh` + `decision` per pass — the client needs no new route); services/composition-service/app/routers/plan_forge.py:272 (every `ValueError` → 409 `{code: "LINK_REFUSED", message}`); services/composition-service/app/services/plan_forge_service.py:1044-1047 (skeleton refuses without a compiled package) + :1012-1016 (ledger already exposes `compiled`).

### Q-35-CONTRACT-JSON-COLLISION
CONFIRMED — the spec's candidate answer (regenerate + same-commit + rebase-then-regenerate) is correct, and the code proves WHY. Builder procedure, verbatim:

(1) EDIT 3 FILES BY HAND, in this order — a new panel is added in exactly three places:
  a. `services/chat-service/app/services/frontend_tools.py:402` — APPEND your panel id to the END of the `panel_id` `enum` list literal (do not reorder existing ids), and append its `'<id>' = ...;` clause to the description prose below it.
  b. `frontend/src/features/studio/panels/catalog.ts` — append the `STUDIO_PANEL_COMPONENTS` entry AND the `OPENABLE_STUDIO_PANELS` row; the row MUST carry a `category` (panelCatalogContract.test.ts:40-43 fails otherwise).
  c. Your panel component file(s).

(2) GENERATE, NEVER HAND-EDIT, `contracts/frontend-tools.contract.json`:
  `cd services/chat-service && WRITE_FRONTEND_CONTRACT=1 python -m pytest tests/test_frontend_tools_contract.py -q`
  (it rewrites the file and `pytest.skip`s — a SKIP here is success). Do not open that JSON in an editor, ever.

(3) VERIFY BOTH HALVES (this is the only gate — `.githooks/pre-commit` does NOT run either guard, so a stale JSON WILL reach HEAD if you skip this):
  `cd services/chat-service && python -m pytest tests/test_frontend_tools_contract.py -q`   (no env var)
  `cd frontend && npx vitest run src/features/studio/panels/__tests__/panelCatalogContract.test.ts src/features/chat/nav/__tests__/frontendToolContract.test.ts`
  Both green is a literal Definition-of-Done line for the wave (alongside `/review-impl`).

(4) IF A REBASE/PULL BRINGS ANOTHER WAVE'S PANEL:
  - Resolve the conflict ONLY in `frontend_tools.py:402` (take the UNION of both panel ids on that one line; order is irrelevant) and in `catalog.ts` (union of the appended rows).
  - For `contracts/frontend-tools.contract.json` do NOT merge by hand and do NOT reason about the hunks — end the conflict with either side (`git checkout --ours -- contracts/frontend-tools.contract.json`), then RE-RUN step (2) and step (3). The generator overwrites the file wholesale, so whichever side you took is irrelevant.
  - WHY (code, not taste): test_frontend_tools_contract.py:130-147 asserts `on_disk == built`, and `_normalize` (line 81) carries `enum` through as a LIST — equality is ORDER-SENSITIVE. A hand-merged enum whose element order differs from the Python literal's order REDS the test even though the sets are identical. Regeneration is the only byte-exact path. (`sort_keys=True` sorts only the tool-name keys, which is why a whole NEW tool produces a clean localized insert rather than diff churn.)

(5) STAGING (shared checkout — `git add -A` is FORBIDDEN):
  `git add services/chat-service/app/services/frontend_tools.py frontend/src/features/studio/panels/catalog.ts contracts/frontend-tools.contract.json <your panel files>`
  then `git diff --cached --stat` to confirm nothing unrelated rode along (the index may carry another session's pre-staged work), then plain `git commit -m "..."` with NO pathspec (`git commit -- <path>` commits the WORKING TREE, not the index).
  All three of frontend_tools.py + catalog.ts + the regenerated JSON land in the SAME commit — a commit with two of the three is a red suite for everyone else in this checkout.

Sane default noted for PO veto: nothing here changes behavior; it is a commit-hygiene rule already implied by the guards' own code.

*Evidence:* services/chat-service/tests/test_frontend_tools_contract.py:130-147 (`assert on_disk == built`; WRITE_FRONTEND_CONTRACT=1 → `write_text(json.dumps(built, indent=2, sort_keys=True))` + `pytest.skip`) · same file:81 (`entry["enum"] = spec["enum"]` — a LIST, so contract equality is order-sensitive ⇒ hand-merging the JSON cannot be made to pass) · services/chat-service/app/services/frontend_tools.py:402 (the single-line `panel_id` enum literal — the ACTUAL merge-conflict surface) · frontend/src/features/studio/panels/__tests__/panelCatalogContract.test.ts:15-43 (FE half reads the JSON; enum ⊆ STUDIO_PANEL_COMPONENTS, enum-set == OPENABLE_STUDIO_PANELS ids, every openable panel has a category) · .githooks/pre-commit (contains NO frontend-tools/contract check — the two test suites are the only gate)

### Q-35-R3-REPAIR-STRIP-GATING
UPHOLD the concern's principle (diagnosis-gated, never an always-on row) but WIDEN the gate — the spec's literal `selfCheck.gaps.length > 0` leaves open the exact strand R3 exists to close.

**GATE.** In `frontend/src/features/plan-forge/components/PlanRunView.tsx`, insert `<RepairStrip>` immediately AFTER the `{selfCheck && …}` block (ends ~L91) and BEFORE the `{validation && …}` block (L93). Render it when a diagnosis EXISTS and is NOT clean:
```ts
const gaps = selfCheck?.gaps ?? [];
const failedRules = validation && !validation.passed ? validation.rules.filter(r => !r.passed) : [];
const diagnosed = gaps.length > 0 || failedRules.length > 0;   // {diagnosed && <RepairStrip … />}
```
Hidden when nothing has been run (`selfCheck === null && validation === null` — the Self-check/Validate buttons at PlanRunView.tsx:63-70 are the one-click path to a diagnosis) and hidden when the diagnosis is clean. WHY the widening is not scope creep: `usePlanRun.ts` holds `validation` as state SEPARATE from `selfCheck`, set by a SEPARATE button — `runValidate` never populates `selfCheck`. Spec 35 §39 says the panel "strands a user at the first failed VALIDATION"; gating on gaps alone means that user (and anyone reopening a past broken run — `loadRun`/`resetRun` both `setSelfCheck(null)`) still sees no repair tools. A failed validate IS a diagnosis.

**THE THREE CONTROLS** (all disabled when `busy || polling`; all behind ONE shared PS-6 confirm step that names the action + the ModelPicker value + "this spends"):
1. **interpret — NOT a bare button.** `PlanInterpretRequest.user_message: str = Field(min_length=1)` (plan_forge.py:65) ⇒ a zero-arg fire is a 422; and `interpret_rules` runs `detect_intent(user_message)` + `search_index(user_message, …)` (engine/plan_forge/interpret.py:112-117), so the message is what SELECTS the spec paths. Ship it as a one-line input + Send: label *"Tell the planner what's wrong, in your words"*. The gaps are already injected server-side (interpret.py:125-126, 259) — the user must not restate them.
2. **refine — copy is "Fix these gaps", NOT "Apply the suggested fix".** There is no suggestion to apply: `PlanForgeService.self_check` returns only `{"gaps","fidelity_score"}` (plan_forge_service.py:963), dropping `ranked_gaps`/`suggestions`. Do NOT plumb `suggestions` through — `suggest_fixes` emits hardcoded **Vietnamese** POC strings (engine/plan_forge/eval_fidelity.py:468-490). Instead mirror what shipped autofix already does: `revision = {focus_paths: [g.path for the ticked/top gaps]}` (plan_forge_service.py:840).
3. **autofix — keep the spec's copy verbatim** *"Fix the top gaps automatically (up to 3 rounds)"*. Needs BE-2 (the REST mirror); `max_rounds` clamps 1..5 server-side (plan_forge_service.py:832).

**FOLD IN PS-5 IN THE SAME SLICE** (else button 2 is a 422): `frontend/src/features/plan-forge/types.ts:115` — `RefinePlanBody.revision?: string` → `revision?: Record<string, unknown>` (BE wants `dict[str, Any] | None`, plan_forge.py:60).

**PS-6 details:** `model_ref` is a REQUIRED `UUID` for interpret AND refine (plan_forge.py:59, 66) — the confirm cannot submit with an empty ModelPicker (a silent default violates SET-1..8 and 422s anyway). Autofix's `model_ref` is optional (service resolves it) but pass the same explicitly-picked value. Refine may answer 202 — route it through the existing `isAck` + poll path.

**Severity:** filter/style on `('error','warn')` exactly as autofix does (plan_forge_service.py:838) — the BE emits `warn`, NOT `warning` (the `types.ts` `PlanGapSeverity` comment is drifted).

**TESTS (PlanRunView.test.tsx):** (a) no strip when `selfCheck===null && validation===null`; (b) no strip when `gaps===[] && validation.passed`; (c) **strip PRESENT when `validation.passed===false` and `selfCheck===null`** — this is the regression the naive gate fails; (d) strip present when `gaps.length>0`; (e) buttons disabled while `busy||polling`; (f) a repair click does NOT hit the api until the confirm is accepted. **usePlanRun.test.ts:** `runInterpret/runRefine/runAutofix` send the picked `model_ref`, and refine sends `revision` as an OBJECT carrying `focus_paths`.

PO veto point (default chosen, say so if you disagree): the strip appears on a failed *validate* too, not only on self-check gaps.

*Evidence:* frontend/src/features/plan-forge/hooks/usePlanRun.ts (validation + selfCheck are SEPARATE state; runValidate never sets selfCheck; loadRun/resetRun both setSelfCheck(null)) · frontend/src/features/plan-forge/components/PlanRunView.tsx:63-70 (Self-check/Validate buttons), :73-91 (selfCheck.gaps block — the strip's insertion point), :93-105 (validation block) · services/composition-service/app/services/plan_forge_service.py:963 (self_check returns ONLY {gaps, fidelity_score} — no suggestions), :832-840 (autofix clamps rounds 1..5, filters severity in ('error','warn'), builds revision={"focus_paths": [...]}) · services/composition-service/app/routers/plan_forge.py:58-60 (PlanRefineRequest: model_ref REQUIRED UUID, revision is a dict), :64-66 (PlanInterpretRequest: user_message min_length=1, model_ref REQUIRED) · services/composition-service/app/engine/plan_forge/interpret.py:112-117 (user_message drives detect_intent + search_index), :125-126,259 (gaps already fed to the prompt) · services/composition-service/app/engine/plan_forge/eval_fidelity.py:468-490 (suggest_fixes = hardcoded Vietnamese POC strings — do not surface) · frontend/src/features/plan-forge/types.ts:113-117 (RefinePlanBody.revision?: string — the PS-5 drift)

### Q-35-ARCHIVE-TOAST-COPY
BUILD IT AS SPEC'D — soft-archive copy + Undo wired to BE-4b, plus one addition so the restore route is not reachable *only* through a 4-second toast. Everything below is grounded in code that already exists; no product call is left open.

**1 · Toast mechanism (already in the repo — do not invent one).** Sonner is the app toaster (`frontend/src/App.tsx:2,81` — `<Toaster position="bottom-right" richColors closeButton />`), and the exact archive/undo shape already ships in `frontend/src/features/glossary/components/MergeCandidatePanel.tsx:106-114`: `toast.success(msg, { action: { label: t('…undo'), onClick: () => void undo(...) } })`. Copy that pattern verbatim.

**2 · Where the code goes.**
- `frontend/src/features/plan-forge/api.ts` — add next to `listRuns` (`api.ts:38`):
  `archiveRun(bookId, runId, token): Promise<void>` → `DELETE ${BASE}/books/${bookId}/plan/runs/${runId}` (BE-4);
  `restoreRun(bookId, runId, token): Promise<PlanRunDetail>` → `POST ${BASE}/books/${bookId}/plan/runs/${runId}/restore` (BE-4b);
  and widen `listRuns(bookId, token, opts)` with `opts.includeArchived?: boolean` → `?include_archived=true` (BE-4b's list half; an unread query param is dead contract).
- `frontend/src/features/plan-forge/hooks/usePlanRunsList.ts` — thread `includeArchived` into the fetch, and expose `archive(runId)` / `restore(runId)` that call the api then `refresh()`. It already owns `items` + `refresh` (`usePlanRunsList.ts:17-46`), so no new state container.
- `frontend/src/features/plan-forge/components/PlanRunsListView.tsx` — the table (`PlanRunsListView.tsx:65-97`) has no row action today; add a trailing `<td>` with an **Archive** button that uses a **two-click inline confirm** in the row (`Archive` → `Confirm?`), NOT `window.confirm` (unmockable in jsdom, and the panel is dockable). Archived rows (only visible under the toggle) render a **Restore** button instead.
- `frontend/src/features/plan-forge/components/PlannerPanel.tsx` — owns selection (`view`/`openRun` at `:31,46`). Pass an `onArchived(runId)` callback down; the fallback lives here.

**3 · The copy (the actual question). Locked strings — add to `frontend/src/i18n/locales/en/studio.json` under `planner.list.*`, and NONE of them may contain the word "delete"/"remove permanently":**
- `archiveButton`: "Archive"
- `archiveConfirm`: "Archive this run?"
- `archivedToast`: "That run was archived." (spec §4.4's exact string — keep it)
- `archivedToastDesc` (sonner `description`): "It's hidden from the list, not deleted. You can restore it any time."
- `undo`: "Undo"
- `restoredToast`: "Run restored."
- `archiveBlockedToast` (the BE-4 **409 job-in-flight** case): "That run has a pass running. Wait for it to finish, then archive it." (`toast.error`, no Undo action)
- `showArchived`: "Show archived"
- `restoreButton`: "Restore"

**4 · Behaviour on archive (R4 / §4.4 'Archived run'):**
```
onArchive(runId):
  await archive(runId)            // 409 → toast.error(archiveBlockedToast); return (row stays)
  const remaining = items.filter(r => r.id !== runId)   // items are newest-first from LIST
  if (selectedRunId === runId) {
    if (remaining.length) openRun(remaining[0].id)      // newest remaining
    else setView('list')                                // empty state, NOT a blank run view
  }
  toast.success(t('planner.list.archivedToast'), {
    description: t('planner.list.archivedToastDesc'),
    duration: 10000,                                    // sonner's 4s default is too short to hit Undo
    action: { label: t('planner.list.undo'), onClick: () => {
      void restore(runId).then(() => { openRun(runId); toast.success(t('planner.list.restoredToast')); });
    }},
  })
```
`runId` is captured in the closure, so Undo still targets the right run after the fallback re-selects another one.

**5 · The addition (my default — veto-able): a `Show archived` checkbox on the list header** that calls `listRuns(..., { includeArchived: true })` and renders archived rows greyed with a **Restore** action. Rationale: BE-4b's `GET ?include_archived=true` otherwise has zero consumers, and an Undo that exists only inside a dismissible toast means a mis-click at 3am is *effectively* permanent — which is exactly the fear §4.4 says the copy must not create. ~25 lines; ships in the same slice.

**6 · Tests (new file `frontend/src/features/plan-forge/components/__tests__/PlanRunsListView.archive.test.tsx`):**
- archive → `toast.success` called; assert the message+description **do not match `/delet|remov/i`** (this is the literal guard for this CONCERN);
- the toast options carry `action.label === 'Undo'`; invoking `action.onClick()` calls `planForgeApi.restoreRun` with that runId and re-opens it;
- archiving the **selected** run re-selects `items[0]` of the remainder; archiving the **last** run lands on the empty state;
- a 409 from `archiveRun` produces `toast.error(archiveBlockedToast)` with **no** action and leaves the row in place;
- `Show archived` re-fetches with `include_archived=true` and its rows offer Restore.

The 'deleted' wording never appears anywhere in the feature — enforce with one assertion, not a review note.

*Evidence:* docs/specs/2026-07-01-writing-studio/35_planforge_studio.md:352 (§4.4 "Archived run" — the requirement) + :412-416 (R4/PS-13: BE-4 never ships without BE-4b) · frontend/src/App.tsx:2,81 (sonner Toaster mounted) · frontend/src/features/glossary/components/MergeCandidatePanel.tsx:106-114 (existing toast+`action:{label,onClick}` Undo pattern to copy) · frontend/src/features/plan-forge/api.ts:38 (`listRuns` — where archiveRun/restoreRun/`include_archived` go) · frontend/src/features/plan-forge/hooks/usePlanRunsList.ts:17-46 (`items`/`refresh` already owned here) · frontend/src/features/plan-forge/components/PlanRunsListView.tsx:65-97 (table has no row action today) · frontend/src/features/plan-forge/components/PlannerPanel.tsx:31,46 (`view` state + `openRun` — the fallback site)

### Q-35-PS7-BARE-ID-PANEL
PS-7 STANDS AS SEALED, and the code confirms every leg of it — `plan-passes` is a BARE-ID panel. Build it exactly so:

(1) REGISTRATION (M4). Add one row to `frontend/src/features/studio/panels/catalog.ts` immediately after the `plan-hub` row (:190): `{ id: 'plan-passes', component: PassRailPanel, titleKey: 'panels.plan-passes.title', descKey: 'panels.plan-passes.desc', category: 'editor', guideBodyKey: 'panels.plan-passes.guideBody' }`. NO `hiddenFromPalette`. NO `params`. Append `"plan-passes"` to the `panel_id` enum in `services/chat-service/app/services/frontend_tools.py` (:402) AND to the tool-description prose (:403-481), then regenerate `contracts/frontend-tools.contract.json` (`WRITE_FRONTEND_CONTRACT=1 pytest`). X-12 does NOT bite this panel and it does NOT wait on plan 30's X-12 decision — X-12 governs panels that need `params`, and this one needs none.

(2) BOOTSTRAP. The panel takes `bookId` from `useStudioHost()` (exactly as `PlannerPanel.tsx:26` does) and resolves the run ITSELF in `frontend/src/features/plan-forge/hooks/usePassRail.ts` (controller, no JSX). `run_id` is in-panel state (a run picker), never an opening argument.

(3) THE DEFAULT-RUN RULE — implement it as a pure function over the FIRST page of `GET /books/{bookId}/plan/runs`; no new backend route is required, because the list response already carries the signal:
    `defaultRun = items.find(r => r.artifacts.some(a => a.kind === 'package'))`
  - `items` is ALREADY newest-first (`plan_runs.py:153` `ORDER BY created_at DESC, id DESC`), so `.find` = "newest". Do not re-sort.
  - `artifacts` is ALREADY on every list item (`plan_forge_service.py:334-348` — `list_runs` calls `_serialize_run`, which calls `list_artifact_refs`). Do not fetch each run's detail to test for a package (N+1).
  - The kind literal is exactly `'package'` — pin it to a shared const mirroring `plan_pass_service.py:100`, do not free-string it at the call site.
  - PAGINATION IS REAL: the route is `limit` default 20 / max 50 (`plan_forge.py:134`). Request `limit=50` and scan ONLY that first page. Do NOT walk `next_cursor` — a book whose 50 newest runs are all uncompiled falls to case (b) below.
  - Three states, all distinct, none a spinner: (a) a default run resolved -> render the Rail on it; (b) runs exist but NONE has a package -> render the picker + an explicit "no compiled package — compile a run first" CTA that opens/focuses `planner` via `openPanel` (this is the same truth the backend already tells at `plan_forge_service.py:1015` `"compiled": package is not None` — "absent is not zero"); (c) zero runs -> empty state + the same CTA. Case (b)/(c) rendering a spinner or a silent blank is the repo's `silent-success-is-a-bug` class and will be caught at `/review-impl`.
  - The picker's selection overrides the default and is per-panel state; selecting a run with no package renders state (b) scoped to that run.

(4) TESTS (Definition of Done for the slice): a unit test on the selector proving it picks the newest PACKAGE-BEARING run when a NEWER package-less run sits above it in `items` (the whole point of the rule — a plain "items[0]" implementation passes a naive test and fails this one); a test for each of (b) and (c); and the catalog/enum parity test (`py enum == contract enum == palette-openable`) staying green with 58 entries. Live-smoke leg: `ui_open_studio_panel {panel_id: "plan-passes"}` from the agent MOUNTS A DOCK TAB in a real browser (per spec 35 M4 §576a).

DEFAULT I AM PICKING (veto-able): scan-first-page-only rather than paginate to find an older compiled run. Rationale: the picker already exposes every run, so the cost of a miss is one click, whereas cursor-walking makes panel open latency unbounded on a book with hundreds of runs.

*Evidence:* frontend/src/features/plan-forge/components/PlannerPanel.tsx:26 (`const { bookId, openPanel } = useStudioHost()` — host supplies bookId, no param needed) · services/composition-service/app/routers/plan_forge.py:131-141 (`GET /books/{book_id}/plan/runs`, VIEW-gated) and :236 (`GET .../runs/{run_id}/passes` — the Rail's data route already exists) · services/composition-service/app/services/plan_forge_service.py:334-348 (`list_runs` → `_serialize_run` → `list_artifact_refs` ⇒ every LIST item already carries `artifacts:[{kind,artifact_id}]`) and :1015 (`"compiled": package is not None` — absent≠zero) · services/composition-service/app/services/plan_pass_service.py:100 (`PACKAGE_KIND: PlanArtifactKind = "package"` — the exact literal) · services/composition-service/app/db/repositories/plan_runs.py:153 (`ORDER BY created_at DESC, id DESC` ⇒ list is newest-first) and :149 (limit clamped to 50) · frontend/src/features/studio/panels/catalog.ts:116,190 (`planner`, `plan-hub` = bare-id siblings with category+guideBodyKey, no hiddenFromPalette) vs :144,168,173,205,208,212,216 (the 8 param-needing panels that DO carry hiddenFromPalette) · docs/specs/2026-07-01-writing-studio/35_planforge_studio.md:177-183 (F-P9/PS-7 as sealed)

### Q-35-MOCKUP-START-POINT
CONFIRM the spec's candidate answer, and make it enforceable. Three binding rules for M3/M4 UI drafting:

**1 · The HTML mockup is the layout start point for M3 (`planner` repair) ONLY — it has NO Pass Rail.** Its five panels (mockup lines 306/345/372/436/506/535) are START → couldn't-understand → UNDERSTOOD → CHECK&FIX → READY-TO-DRAFT → DONE, i.e. the `planner` flow. Grep confirms it contains zero pass-ledger/checkpoint/cast-card content. So:
 - **M3**: start the draft from the mockup. Take from it (a) the STATE MODEL and layout of the planner flow, (b) the copy voice, and above all (c) its ROOT DIAGNOSIS (mockup lines ~26-33): *"this isn't a missing-button problem, it's a LEAKY ABSTRACTION problem — the shipped panel renders raw backend vocabulary (literal `arc_2`, rule ids `pa_not_realm`, raw `var_delta`) at a novel WRITER."* That diagnosis is why §5's R3 buttons say "Explain what's wrong" / "Apply the suggested fix" and not "interpret" / "refine". Do NOT copy its raw CSS/HSL — the panel uses Tailwind + shadcn tokens.
 - Map: mockup sub-gap 2 → R1 (artifact viewer), sub-gap 3 → R2 (source resume), sub-gap 4 → R3 (interpret/refine/autofix). **Sub-gap 1 (the `arc_id` text box) is STALE — do not touch the arc picker** (already shipped: `PlanRunView.tsx:117-124`, `data-testid="plan-arc-picker"`, a `<select>` over `run.arcs`). §5's **R4 (archive + restore)** has NO mockup reference — draft it fresh from §5/PS-13.
 - **M4**: the mockup gives you nothing. The only layout reference for `plan-passes` is §4.1b's ASCII, and it is VISUAL ONLY (box order, what info appears in a row, where the checkpoint card expands).

**2 · Enable/disable/blocked state is NEVER drawn from either mock, and NEVER re-derived in the frontend.** The backend already ships the answer per pass. `GET …/plan/runs/{runId}/passes` returns, for each of the 7 passes, `{pass_id, checkpoint, output_kind, depends_on[], status, decision, artifact_id, job_id, fresh, blockers[]}` plus top-level `pass_cursor` / `blocked_at` (`plan_pass_service.py:294-323`; `blockers` at :317 is `blockers_for()` which walks `PASS_REGISTRY[pid].depends_on` and nothing else). So the panel binds directly:
 - Run button `disabled = p.blockers.length > 0 || anyJobInFlight` (409 UPSTREAM_STALE is the fallback, not the plan)
 - "blocked ⓘ" badge + its tooltip copy = `p.blockers` verbatim
 - BLOCKING badge = `p.checkpoint === 'blocking'` · "fresh" = `p.fresh` · progress = `pass_cursor` (never hard-coded — §4.1's third bullet)
 - the stuck banner = `blocked_at ?? (first pass with checkpoint==='blocking' && decision not in ('accepted','auto'))` — PS-12/F-P10, because a rejected pass makes `blocked_at` go null.

**3 · The mechanical guard that makes rule 2 stick (add it to M4's DoD).** A frontend file under `frontend/src/features/plan-forge/**` must contain NO literal dependency graph. Today `grep -rn "depends_on|PASS_ORDER|PASS_REGISTRY" frontend/src/` hits only an unrelated wiki constant — plan-forge has zero copies. Add a vitest case in the Pass Rail's test file that (a) feeds a fixture ledger where `world.blockers=["cast"]` and `beats.blockers=[]` and asserts world's Run is disabled and beats' is enabled, and (b) feeds an INVERTED fixture (`world.blockers=[]`, `beats.blockers=["motifs"]`) and asserts the enable/disable INVERTS with it. Test (b) is the one that fails if anyone hard-codes the graph from a mock — which is exactly the bug this spec's own first draft shipped in its ASCII.

Default I am picking (veto-able): the mockup is treated as a NON-NORMATIVE design draft, not a contract. Where the mockup and §5 disagree on planner behavior, **§5 wins** (the mockup predates the 2026-07-13 code re-read); where they disagree on *presentation/copy*, the mockup wins. Nobody needs to reconcile the mockup's own v1/v2 comment gaps — they were written against a 2026-07-06 tree.

*Evidence:* services/composition-service/app/services/plan_pass_service.py:55-87 (PASS_REGISTRY — world→cast, beats→motifs; matches spec §4.1 exactly) · plan_pass_service.py:294-323 (derive_view already emits per-pass `depends_on`/`fresh`/`blockers` + `pass_cursor`/`blocked_at`; :317 = `"blockers": blockers_for(...)`, :221-236 = blockers_for walks depends_on only) · design-drafts/planforge/2026-07-06-planner-panel-redesign-mockup.html:306,345,372,436,506,535 (the 5 planner panels — grep for pass/checkpoint/cast/beats content returns nothing; the mockup has NO Pass Rail) · mockup lines 16-33 (its 4 sub-gaps + the leaky-abstraction root diagnosis) · frontend/src/features/plan-forge/components/PlanRunView.tsx:117-124 (`data-testid="plan-arc-picker"` <select> over run.arcs — sub-gap 1 IS stale, shipped in 9c685c28a) · `grep -rn "depends_on|PASS_ORDER|PASS_REGISTRY" frontend/src/` → only frontend/src/features/wiki/components/WikiGenJobDetail.tsx:21 (unrelated); plan-forge holds no copy of the graph today.

### Q-35-FORCE-OVERRIDE-AFFORDANCE
Build it as the spec states — secondary affordance, inside the blocked state only — with these exact mechanics, plus one disambiguation the code forces.

**DISAMBIGUATION (binding): "the 409 state" == the BLOCKED state, derived client-side from `row.blockers[]`, NOT literally an HTTP 409 response.** `derive_view` already ships `blockers: []` on every pass row (plan_pass_service.py:317), so the panel knows a pass is blocked before it ever fires a request. §4.3 says the primary Run button is *disabled* when `blockers[]` is non-empty — which means a well-behaved panel NEVER receives a 409, and a builder reading "inside the 409 state" literally would ship a force door that no user can reach (DoD (d) becomes undeliverable). So: render ONE `<PassBlockedState>` component whenever `row.blockers.length > 0`; the 409 `UPSTREAM_STALE` catch renders the SAME component (it is only the race/stale-ledger fallback). The force button lives in that component and nowhere else.

**Files + changes:**
1. `frontend/src/features/plan-forge/types.ts` — add `RunPassBody = { model_ref?: string; params?: Record<string, unknown>; force?: boolean }`.
2. `frontend/src/features/plan-forge/api.ts` — add `runPass(bookId, runId, passId, body: RunPassBody, token)` → `POST ${BASE}/books/${bookId}/plan/runs/${runId}/passes/${passId}/run`. Do NOT default `force` in the api layer; the caller passes it explicitly.
3. `frontend/src/features/plan-forge/hooks/usePassRail.ts` (new controller, no JSX) — expose **two distinct functions**, never one boolean-parameterized one: `runPass(passId, {model_ref, params})` which sends `force: false`, and `forceRunPass(passId, {model_ref, params})` which sends `force: true`. Two call sites = the override cannot be reached by flipping a prop. Catch the 409: read `(err as {body?: {detail?: {code: string; pass_id: string; blockers: string[]}}}).body?.detail` (api.ts:158-163 attaches it) and merge its `blockers` into the row's blocked state.
4. `frontend/src/features/studio/panels/PassRailPanel.tsx` (new, per spec §7 row 1) — per pass row:
   - Primary action = `<Button data-testid={`pass-run-${passId}`}>` labelled **Run** / **Re-run**, `disabled={row.blockers.length > 0 || anyJobInFlight}`. It calls `runPass` (force:false) only.
   - When `row.blockers.length > 0`, render `<PassBlockedState>` BELOW the row: the blockers as copy (`"`world` needs `cast` (not accepted)."`), each blocker a click-to-scroll to that pass's row, and **then** the escape: `<Button variant="ghost" size="sm" data-testid={`pass-force-run-${passId}`}>Run anyway</Button>`. It must NOT be `variant="default"`/primary, must not sit in the row's primary action slot, and must render visually subordinate to the blocker copy above it.
   - Clicking "Run anyway" opens the SAME paid-confirm dialog the normal Run uses (PS-6 — force does NOT skip the cost gate), whose body copy is exactly, with names interpolated from `pass_id` / `blockers`: **"Run `{pass_id}` against a `{blockers.join('`, `')}` you have not accepted. The result may contradict the plan above it."** Only on confirm does it call `forceRunPass`.
   - a11y: real `<button>`, `aria-describedby` pointing at the warning copy id.
5. i18n keys in `frontend/src/i18n/locales/en/studio.json` under `panels.plan-passes.*` (`blocked.needs`, `blocked.forceCta`, `blocked.forceConfirmBody`), then run `scripts/i18n_translate.py` for the 17 locales.

**Do NOT touch `services/composition-service/app/mcp/server.py:3599-3611`** — `force` stays absent from `plan_run_pass`. Adding it back is the design's central inversion.

**Tests (new `frontend/src/features/studio/panels/__tests__/PassRailPanel.blocked.test.tsx`) — the checklist is enforced by assertions, not prose:**
- a run with `cast` pending ⇒ `pass-run-world` is `disabled`, and `pass-force-run-world` IS in the DOM inside the blocked block.
- a runnable pass (`beats`, blockers `[]`) ⇒ `pass-force-run-beats` is **absent from the DOM entirely** (not merely disabled) — the force door exists only in the blocked state.
- clicking `pass-force-run-world` does NOT post until the confirm dialog is accepted; after confirm, the POST body is exactly `{force: true, ...}`.
- clicking `pass-run-*` on any row posts `force: false`.
- assert the confirm-dialog body text renders the pass name and the blocker name (guards the copy from decaying into "Are you sure?").

Live-smoke DoD (d) is satisfied by driving this blocked block in Playwright: `blockers[]` renders as readable copy, and "Run anyway" is reachable behind it.

*Evidence:* services/composition-service/app/mcp/server.py:3599-3619 (force deliberately absent from the agent tool; `force=False` hard-wired) · services/composition-service/app/routers/plan_forge.py:87 + :303-330 (`PlanPassRequest.force`; 409 detail `{code:"UPSTREAM_STALE", pass_id, blockers[]}`) · services/composition-service/app/services/plan_pass_service.py:239-256 (`assert_runnable`: force is the only escape) and :306-318 (`derive_view` already emits per-row `blockers[]` — the blocked state is known WITHOUT a 409, which is why "inside the 409 state" must be read as "inside the blocked state") · frontend/src/api.ts:158-163 (thrown Error carries `.status` + `.body`, so the 409's blockers are readable) · frontend/src/features/plan-forge/api.ts:34-117 (no `runPass` exists — the whole affordance is unbuilt work, not a change to existing UI)

### Q-35-CATALOG-ROW-REQUIRED-FIELDS
FOLLOW SPEC 35 §7 VERBATIM — every field claim is confirmed against code. The catalog row is exactly:

`{ id: 'plan-passes', component: PassRailPanel, titleKey: 'panels.plan-passes.title', descKey: 'panels.plan-passes.desc', category: 'editor', guideBodyKey: 'panels.plan-passes.guideBody' }` inserted after `plan-hub` (catalog.ts:190). No `hiddenFromPalette`. Steps 7 (studioLinks) and 9 (tours) SKIPPED in v1 as the spec states; step 8 (planEffects.ts) is MANDATORY.

Three corrections/strengthenings the builder MUST carry, all grounded below:

(1) TWO of the §7 "MANDATORY" claims are NOT enforced at HEAD — they are enforced only AFTER Wave 0. `category`-present IS enforced today (panelCatalogContract.test.ts:41-43). But (a) "must be a member of CATEGORY_ORDER" has NO assertion — catalog.ts:266-270 already ships 5 `category:'quality'` panels while `'quality'` is missing from CATEGORY_ORDER (useStudioCommands.ts:20-22), so indexOf = -1 and they sort ABOVE 'editor'; that is plan 30's X-2. And (b) `guideBodyKey` has NO assertion — catalog.ts:258 (`agent-mode`) is openable with none; that is X-3. CONSEQUENCE FOR THE BUILDER: do not rely on a red test to catch a missing `guideBodyKey` unless Wave 0 (X-2 + X-3) has landed. Wave 0 precedes Wave 5, so in the planned order both assertions exist by the time this panel lands — but write the row correctly regardless. `'editor'` is already a CATEGORY_ORDER member either way, so this panel is safe on both counts.

(2) ADD THE MISSING GUARD (new, XS, fix-now — put it in Wave 0 next to X-2/X-3, call it X-3b). Step 5(b), the tool DESCRIPTION prose, is the ONLY step in the entire 9-step checklist that nothing machine-checks. A builder can add the enum entry, regenerate contracts, and go 100% green while the model never learns the panel exists — the silent-discoverability failure the enum was added to kill. It is cheaply closable: I parsed `UI_OPEN_STUDIO_PANEL_TOOL` and ALL 57 current enum ids already appear in the description string (0 missing), so this assertion is GREEN at HEAD and REDs on the next unglossed enum add. Add to services/chat-service/tests/test_frontend_tools.py: for every id in UI_OPEN_STUDIO_PANEL_TOOL['parameters']['properties']['panel_id']['enum'], assert f"'{id}'" appears in that property's 'description'. This makes the description a tested effect, not a discipline (CLAUDE.md "checklist ⇒ test the effect"). All ~9 panels in this batch then inherit it.

(3) COUNTS: assert the DELTA and the three-way equality, never a literal. Verified live at HEAD 9262ed53e: py enum = 57, contract enum = 57, sets equal. Waves 1-4 add 8 panels before this one, so the Wave-5 baseline is 65, not 57. DoD = "py enum == contract enum == OPENABLE_STUDIO_PANELS, and each grew by exactly +1 in this commit."

Everything else stands: 3 i18n keys x en + 17 locales via `python scripts/i18n_translate.py` (never hand-written); the contract JSON is REGENERATED (`cd services/chat-service && WRITE_FRONTEND_CONTRACT=1 python -m pytest tests/test_frontend_tools_contract.py`) and committed in the same commit as catalog.ts + frontend_tools.py; and the do-not-touch list is correct — I confirmed studioUiNav.ts:32-35 passes `panelId` straight through to `host.openPanel` with zero hardcoded ids, and StudioDock/StudioFrame/useStudioCommands/UserGuidePanel all derive from catalog.ts.

*Evidence:* category IS enforced today: frontend/src/features/studio/panels/__tests__/panelCatalogContract.test.ts:41-43 ("every palette-openable panel has a category"). CATEGORY_ORDER membership is NOT enforced and is live-broken: frontend/src/features/studio/palette/useStudioCommands.ts:20-22 lists 9 categories with no 'quality', while frontend/src/features/studio/panels/catalog.ts:82 defines 'quality' in the union and catalog.ts:266-270 ships 5 quality panels using it (indexOf → -1 → sorts first). guideBodyKey is NOT enforced: catalog.ts:258 `{ id: 'agent-mode', ..., category: 'editor' }` has no guideBodyKey and is palette-openable. hiddenFromPalette exclusion IS machine-enforced: catalog.ts:279 `OPENABLE_STUDIO_PANELS = STUDIO_PANELS.filter((p) => !p.hiddenFromPalette)` + panelCatalogContract.test.ts:33-36 ("the advertised set == the palette-openable set"). Enum: services/chat-service/app/services/frontend_tools.py:400-402 panel_id enum — parsed = 57 entries; contracts/frontend-tools.contract.json ui_open_studio_panel.args.panel_id.enum = 57; sets equal. Description prose: frontend_tools.py:403-481 — parsed check shows all 57 enum ids are mentioned (0 missing), so the X-3b guard is green at HEAD. Do-not-touch verified: frontend/src/features/studio/agent/studioUiNav.ts:32-35 (`const raw = args.panel_id ?? args.panel ?? args.page; ... effect: (host) => host.openPanel(panelId)`) — no hardcoded panel ids. Wave 0 items X-2/X-3 are specified at docs/specs/2026-07-01-writing-studio/30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md:336-337 and sequenced at :787.

### Q-35-MILESTONE-ORDERING
ANSWER = candidate (b), executed with (c)'s substance: **M1 → { M2 ∥ M3 } → M4. M2 is NOT required before M4.** M4 builds its cast/beats edit forms from the engine adapters, and M2 lands independently, in parallel with M3.

The dependency graph, stated in full so a builder never has to re-derive it (write this table into spec 35 §9, replacing the prose):

| Edge | Hard? | Why (from code) |
|---|---|---|
| **M1 → M3** | HARD | Every M3 slice is fed by an M1 route: R1←BE-3, R2←BE-3b, R3←BE-2, R4←BE-4+BE-4b. |
| **FE-1 (in M3) ⟂ M1** | NONE | FE-1 is pure frontend (`JsonDocumentProvider.readOnly` + `JsonEditorPanel`). It is the ONE slice that may start on day 1, in parallel with M1. It still runs FIRST within M3 (PS-9 cannot exist without it). |
| **M1 → M4** | HARD, but **only on BE-20** | `derive_view` (plan_pass_service.py:294-322) emits pass_id/checkpoint/output_kind/depends_on/status/decision/artifact_id/job_id/fresh/blockers and **not** bootstrap_proposal_id/decided_by/decided_at — though `record_pass` (:340-347) stores all three. Without BE-20 the cast Approve button 409s forever. **BE-21 is NOT an M4 gate** — the Rail reads `GET …/passes`, which already calls `derive_view` correctly; BE-21 only fixes `GET /runs/{id}`. (M1 ships them together anyway; this is stated so a partial M1 does not falsely block M4.) |
| **M3 → M4** | HARD | M4's fallback for every artifact that is NOT cast/beats **is** the read-only viewer (OQ-2 v1 rule), i.e. FE-1 + PS-9's `plan-artifact` provider, which `PassRailPanel` re-registers on mount (spec 35:389: "and from PassRailPanel's, once M4 lands"). M3 before M4. The spec's "M3 has no dependency on M4" is one-directional and correct. |
| **M2 → M4** | **NONE. Explicitly severed.** | (i) The contracts have **zero runtime consumers**: grep for `planner_state.schema` / `novel_system_spec.schema` / `plan_pass_artifacts` / `contracts/plan-forge` across `services/`, `frontend/src`, `scripts/` hits exactly ONE line — `scripts/plan-forge-poc/README.md:79`. No loader, no validator, no codegen. (ii) The two shapes M4's forms need are **fully determined in code by the adapters** (see below). A schema file that nothing reads cannot gate a panel. |
| **X-1 → M4** | HARD | Already sealed in spec 35 §9. Unchanged. |
| **M2 ⟂ M3** | NONE | Disjoint files (contracts/plan-forge/*.json + engine/plan_forge/compile.py vs frontend/**). Run them concurrently. |

BUILDER INSTRUCTION — M4's structured edit forms, concretely:
Build the `cast` form and the `beats` form directly against the adapter return dicts in `services/composition-service/app/services/plan_pass_adapters.py`. Those dicts ARE the artifact bodies (the adapter's contract is literally "returns the artifact body to store under the pass's output_kind", :10):
- **cast_plan** (`run_cast`, :138-149) → `{"cast": [{name: str, role: str, archetype: str, summary: str, is_new: bool, attributes: dict}]}`. The form: add / remove / rename a character, change `role`. Send it as the `edits` deep-merge on `POST …/checkpoint`.
- **beat_plan** (`run_beats`, :170-198) → `{"chapters": [{ordinal:int, event_id:str, title:str, beat_role:str|null, intent:str}], "tension_curve": [{chapter_index:int, beat_role:str|null, tension_target:int}], "unmapped_beats": [...]}`. The form: edit a beat's summary/intent + tension_target. NOTE `tension_curve` is read back VERBATIM by pass 6 (`run_scenes`, :246-252: "Pass 4's curve, honoured verbatim (V2-C4) — including any edit the human made"), so an edit here is load-bearing, not cosmetic — surface `unmapped_beats` in the form, it is already emitted for exactly that reason.
- Everything else → the read-only viewer + "re-run this pass" (OQ-2's v1 rule, unchanged).

ANTI-DRIFT GUARD (the one thing that must not be skipped, since M2 and M4 now share a source of truth but not an ordering):
M2's `plan_pass_artifacts.schema.json` MUST be written **from `plan_pass_adapters.py`'s return dicts**, not from the prompts or from memory — same source the M4 forms read. Add to **M2's DoD** a test in composition-service that takes a real `cast_plan` and a real `beat_plan` artifact body produced by the adapters (fixture, not hand-written JSON) and validates it against the new schema. That test is what makes the order irrelevant: if M2 lands first, M4's builder just reads the schema; if M4 lands first, M2's test proves the schema did not drift from the forms. Whichever lands second cannot silently disagree.

OQ-2's OWN question is answered separately and does NOT change this: "is a generic JSON-patch editor over an arbitrary artifact wanted?" stays **NO for v1** — the fallback is the read-only viewer. So M4 never needs a schema-driven generic editor, which is the only thing that could have made M2 a real prerequisite. (Default chosen; PO may veto — but a generic JSON patcher into the pass ledger would be a second, un-fingerprinted write channel, exactly what spec 35 §5 forbids.)

WAVE SEQUENCING (what the builder actually runs):
Wave A = M1 (backend) ∥ FE-1 (frontend, no deps). Wave B = M2 (backend contracts) ∥ M3-rest (R1–R4). Wave C = M4, gated on X-1 + BE-20 + M3. `/review-impl` at the close of every wave, per the PO's binding policy.

*Evidence:* services/composition-service/app/services/plan_pass_adapters.py:138-149 (run_cast → `{"cast":[{name,role,archetype,summary,is_new,attributes}]}`) and :170-198 (run_beats → `{"chapters":[…], "tension_curve":[…], "unmapped_beats":[…]}`) — the cast/beats artifact shapes are fully pinned IN CODE, so M4's forms need no schema file. · services/composition-service/app/services/plan_pass_service.py:294-322 (`derive_view` emits 10 fields, NOT bootstrap_proposal_id/decided_by/decided_at) vs :340-347 (`record_pass` stores all three) = BE-20 is M4's only hard M1 edge; BE-21 touches `_serialize_run` only, and the Rail reads `GET …/passes`. · `grep -rn "planner_state.schema|plan_pass_artifacts|novel_system_spec.schema|contracts/plan-forge" services/ frontend/src/ scripts/` → 1 hit, `scripts/plan-forge-poc/README.md:79` — the plan-forge JSON schemas have ZERO runtime consumers, so M2 cannot gate any panel. · docs/specs/2026-07-01-writing-studio/35_planforge_studio.md:389 ("registerPlanArtifactDocumentProvider() is called from PlannerPanel's mount (and from PassRailPanel's, once M4 lands)") + OQ-2's v1 rule (non-cast/beats ⇒ read-only viewer) = M4 depends on M3's FE-1+PS-9. · Consistent with plan 30 §0 PO-1..4 (none of which constrains milestone order).

### Q-35-LIVE-SMOKE-PREREQS
BUILD THE FIXTURE AS A COMMITTED SEED SCRIPT — it is 2 free routes + 1 local ($0) LLM call, not a blocker. Add M3-slice `services/composition-service/scripts/seed_planforge_smoke_fixture.py` (stdlib/httpx, run from the host against the GATEWAY http://localhost:3123 — never the service port, so it traverses the same auth+grant path the browser does). Exact steps: (1) POST /v1/auth/login {claude-test@loreweave.dev / Claude@Test2026} -> JWT. (2) POST /v1/books {title: f"PF-SMOKE-{label} {ts}"} -> NEW book per invocation (create_run dedupes on (book, checksum, mode) at plan_forge_service.py:176 — a fresh book guarantees a fresh run). (3) POST /v1/composition/books/{book}/plan/runs {source_markdown: read of services/composition-service/tests/fixtures/plan-forge/story-plan-v1.md, mode:"rules", genre_tags:["xianxia","cultivation"]} -> 201, status "proposed". NO LLM, $0 (plan_forge_service.py:191). (4) take arcs[0].id straight from that 201 body (the detail already carries the arc picker, plan_forge_service.py:355-362) and POST .../compile {arc_id, run_pipeline:false} -> 200, status "compiled". Still NO LLM, $0 (plan_forge_service.py:1219-1310). The ledger now reports compiled:true (plan_forge_service.py:1006-1015). (5) POST .../passes/cast/run {model_ref} with --model-ref defaulting to 019ebb72-27a2-72f3-a42d-d2d0e0ded179 (Gemma-4 26B-A4B QAT — the verified-active $0 local lm_studio chat+tool model for this account; requires lm_studio up) -> 202 job; poll GET .../passes every 3s (cap 180s) until passes[cast].status=="completed"; then ASSERT blocked_at=="cast" AND pass_cursor==0 AND cast.bootstrap_proposal_id is not null, and exit non-zero with the raw JSON if not. (6) Seed TWO fixtures per run (--count 2 / two labels): "A-headline" and "B-reject", because DoD (c) advances cast off blocked while DoD (f) needs a still-blocked run. Print {label, book_id, run_id} as JSON on stdout; the Playwright smoke consumes that. SMOKE ORDER on fixture A: (a) panel mount -> (b) 7 passes + world Run disabled / beats enabled -> (e) planner artifact read-only + source markdown resumes -> (d) click world's Run to get the real 409 UPSTREAM_STALE with blockers ["cast"] + reach force -> (c) the headline: seed proposal review->approve->apply then Approve, assert blocked_at moves off "cast" and pass_cursor increments to 1. On fixture B: (f) Save-edits on the cast checkpoint -> decision "rejected", blocked_at null on the wire, Rail still says "stuck at cast". DO NOT reuse the ad-hoc rows already in the dev DB (book 019f55c9-6f60-7944-bbc4-098218d702bd / run 019f55c9-6fb5-7682-b713-195c5bb4bf72 are in exactly the right state today, but they are residue from a prior manual smoke — its proposal row is status=failed — and composition integration tests TRUNCATE the shared dev DB). DEGRADE RULE if lm_studio is genuinely unbootable at VERIFY: proofs (a)(b)(e) still run on the compiled-but-zero-passes fixture (steps 1-4, no LLM at all); (c)(d)(f) require step 5, so bring lm_studio up. NEVER substitute gpt-4o (paid) — if the local backend truly cannot boot, the VERIFY evidence string says "live infra unavailable: lm_studio down" and the wave does not close. Prereq X-1 (AddModelCta/DOCK-7) is unchanged and still gates M4 as spec 35 states.

*Evidence:* services/composition-service/app/services/plan_forge_service.py:191 (`if mode == "rules": await self._finalize_rules_propose(...)` — deterministic, sync, no LLM) · :1219-1310 (`compile()` — compile_artifacts + skeleton link + `status="compiled"`, LLM only when run_pipeline=True) · :1006-1015 (`"compiled": package is not None` — the ledger's compiled flag is just "a `package` artifact exists") · :355-362 (run detail returns `arcs: [{id,title}]` — the compile arc_id needs no guessing) · :176 (create_run dedupe on book+checksum+mode -> seed a NEW book each run) · services/composition-service/app/routers/plan_forge.py:94 (POST /plan/runs), :375 (POST /compile), :303 (POST /passes/{pass_id}/run, 409 UPSTREAM_STALE with blockers[]) · fixture text: services/composition-service/tests/fixtures/plan-forge/story-plan-v1.md · LIVE DB PROOF (docker exec infra-postgres-1 psql -d loreweave_composition): plan_run 019f55c9-6fb5-7682-b713-195c5bb4bf72 / book 019f55c9-6f60-7944-bbc4-098218d702bd (owner 019d5e3c-…=claude-test, title "apply debug") is status=compiled with pass_state.cast = {status: completed, decision: pending, bootstrap_proposal_id: 019f55c9-84c0-…} — i.e. blocked_at="cast", pass_cursor=0 · loreweave_provider_registry.user_models: 019ebb72-27a2-72f3-a42d-d2d0e0ded179 = "Gemma-4 26B-A4B QAT (200K)", {"chat":true,"tool_calling":true}, is_active=t ($0 local).

## Not a question (already answered by code / a sealed decision)
- **Q-35-PS1-NO-DELETE** — Already answered — by the sealed spec statement AND by the code, which agrees with it. There is no delete surface anywhere in the plan-forge stack: `services/composition-service/app/routers/plan_forge.py` exposes 12 routes (5x GET/POST on runs, `/validate`, `/refine`, `/passes`, `/link`, `/checkpoint`, `/passes/{pass_id}/run`, `/interpret`, `/self-check`, `/compile`) and **zero `@router.delete`**; `plan_runs.py` and `plan_pass_service.py` contain **no delete method and no `DELETE FROM`** at all. A "Delete pass" button would have nothing to call, and building the route would create the second invalidation mechanism PF-3 exists to prevent (the ledger is DERIVED from `pass_state` — `fresh`/`pass_cursor`/`blocked_at` are computed at serialization, never stored).

BUILDER INSTRUCTION (M4 button set, Pass Rail):
1. The per-pass row action set is EXACTLY: **Run** (`POST …/passes/{pass_id}/run`, paid, confirm step PS-6), **Force-run** (same route, `force: true`, only inside the 409 `UPSTREAM_STALE` state), **Approve** / **Approve-with-edits** / **Reject / Save-edits** (all `POST …/checkpoint`, `approved` bool + optional `edits`), **Re-run** (same `/run` route on a completed pass — this IS the un-do), **Link** (`POST …/link`). NO Delete, no Archive, no Discard, no Reset on a pass — not in the row, not in an overflow menu, not behind a confirm.
2. Where a user would reach for "delete", the Rail must say what to do instead: the Re-run button's tooltip/confirm copy reads "Re-runs this pass and stales every pass below it" and the Reject copy reads "`<pass>` stays rejected until you approve it — nothing below it can run."
3. Add a guard test in the FE Pass Rail spec asserting the rendered action set for a completed pass contains no button matching /delete|remove|discard/i, so a later wave cannot reintroduce it silently.
4. Do NOT conflate with BE-4/BE-4b: archiving/restoring a **RUN** (`POST …/plan/runs/{run_id}/archive` + `/restore`) is a different object and IS a MUST-BUILD in this spec. Pass-level delete stays absent.

Non-blocking CONCERN, sealed by §0 — record and move on, no design change, no route to write.
- **Q-35-D-PLANFORGE-GUI-AUDIT-STALE** — Not a question — a work item already settled by the code, and the "stale" claim VERIFIES TRUE. Builder instruction, exactly:

1. DO NOT TOUCH THE ARC PICKER. Sub-gap 1 is closed. `frontend/src/features/plan-forge/components/PlanRunView.tsx` already has: `:31` `const arcId = pickedArcId || run.arcs[0]?.id || ''` (a real default), `:118` `<select data-testid="plan-arc-picker">` fed from `run.arcs[]` (`:121` maps them to titles), and `:111-113` an explicit no-arcs reason ("No arcs found in this plan yet — run Self-check or Validate above to see what's missing.") replacing the silently-disabled button. That closes BOTH halves of sub-gap 1 (the blind text box AND the zero-indication disable). Shipped by 9c685c28a. Any diff that re-adds an arc_id input is a regression.

2. FIX TWO WRONG CITATIONS while you are in the spec (they will send a builder to the wrong file at 3am): spec 35 §5 and plan 30 §7 (line 749) both cite `features/planforge/PlanRunView.tsx:120-128`. The real path is `features/plan-forge/` (hyphen) and the picker is at `:111-124`. Correct both refs.

3. BUILD ONLY sub-gaps 2/3/4 — they are exactly §5 R1/R2/R3, verified one-to-one: sub-gap 2 (no spec/document viewer) = R1 (35_planforge_studio.md:361, artifact row -> json-editor, BE-3, read-only per FE-1); sub-gap 3 (source markdown does not resume on reopen) = R2 (:398, BE-3b); sub-gap 4 (interpret/apply/autofix are MCP-only, no GUI affordance) = R3 (:402). R4 (archive/restore, :412) is net-new beyond the original four. Nothing from the row is orphaned by clearing it — DoD item 5(e) already asserts sub-gaps 2+3 by live browser effect.

4. AT SESSION (DoD item 7), do exactly this to `docs/sessions/SESSION_HANDOFF.md`: edit the `D-PLANFORGE-GUI-AUDIT` block at :1572 — strike sub-gap 1 (:1244-1249) in place with the amendment "Sub-gap 1 (arc_id text box + silent disable): STALE — fixed by 9c685c28a, PlanRunView.tsx:111-124. Not re-done." — then CLEAR the whole row to "Recently cleared", citing §5 R1/R2/R3 as the close for sub-gaps 2/3/4. Amend-then-clear, one edit, same commit as the code. Do not carry the row forward.

Consistent with plan 30 §0 (PO-1..4) — none of them touch this; PO-4 (specs first, no implementation) is already satisfied since 35 is on disk.

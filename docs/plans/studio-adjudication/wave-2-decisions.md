# Wave 2 — Arc Inspector — adjudicated decisions

> 47 items · 44 DECIDED · 3 not-a-question · 0 deferred · 0 escalated.

> **These are INSTRUCTIONS, not suggestions.** Each was settled by reading source. Do not re-open a
> decided question. Where this contradicts the wave plan, **this file wins.**

---

## Decisions

### Q-32-BE-A1-SPAN-SHAPE
FIX AT THE ROUTE (both doors). Do NOT touch StructureRepo.span() — the code proves the spec's trap is real.

BUILDER INSTRUCTION (exact):

1) services/composition-service/app/routers/arc.py — in get_arc(), DELETE line 455 (`out["span"] = await structures.span(node.id)`) and replace with:
    block = (await structures.derived_blocks(node.book_id)).get(node.id)
    out.update(block or {"span": None, "is_contiguous": None, "chapter_count": None, "first_story_order": None})

2) services/composition-service/app/mcp/server.py — in composition_arc_get(), DELETE line 4255 (identical `out["span"] = await structures.span(node.id)`) and apply the SAME two lines. Both doors already hold `node.book_id` (arc.py:447 via _gate_arc; server.py:4244 via _arc_or_deny).

3) SPREAD, DO NOT NEST — this is the one thing the spec text under-specifies and a builder would get wrong. `derived_blocks()` returns the FULL block `{span:{from_order,to_order}|None, is_contiguous, chapter_count, first_story_order}` (structure.py:317-327), NOT a bare span. Writing `out["span"] = block` would produce a nested `span.span` and would FAIL the spec's own `list[i].span == get(i).span` assertion. The list route spreads it (`d.update(...)`, arc.py:433) — the detail doors must spread it identically, so `span`, `is_contiguous`, `chapter_count`, `first_story_order` all sit at the payload's TOP level in all three doors.

4) ARCHIVED NODE → ALL-NULL BLOCK. derived_blocks' recursive CTE filters `NOT is_archived` (structure.py:264), so an archived node has NO key; StructureRepo.get() does not filter archived, so this state is reachable via the detail door. Emit the all-null block above — explicitly NOT the list route's `empty` literal (arc.py:429), whose `chapter_count: 0` is the "a null meaning not-computed is not a zero" trap. Include `first_story_order: None` for shape parity.

5) LEAVE StructureRepo.span() EXACTLY AS IT IS (structure.py:641-686). Its third caller is the packer: lenses.py:322 gathers span() per chain node and feeds it to _arc_position (lenses.py:247-248), which reads `min_story_order`/`max_story_order` and interpolates the scene's RAW strided `story_order` across them. Dense-ranking span() or renaming its keys corrupts EVERY generation prompt (raw 45000 vs dense hi=18 clamps pacing to ~100% forever), and gather_arc's `return_exceptions=True` (lenses.py:323) swallows the resulting error into a silently-dropped Pacing line — green suite, broken prompts. This is a REGRESSION-WITH-GREEN-TESTS edit; the route fix costs one extra query and has none of that blast radius.

TESTS (all four required, per spec M1 DoD):
 a) same node: `list_arcs()[i]["span"] == get_arc(i)["span"]` and `== composition_arc_get(i)["span"]` — assert on the full 4-key block, not just `span`, to catch the nesting mistake.
 b) archived node detail (REST + MCP) → `span is None and chapter_count is None and is_contiguous is None` — assert `is None`, never falsy, so a 0 cannot pass.
 c) MCP tool returns the same shape as REST.
 d) 🔴 a gather_arc pacing test that PINS StructureRepo.span()'s raw keys (`min_story_order`/`max_story_order`) and asserts a mid-arc scene yields a non-0/non-100 pct — so the "obvious cleanup" that would corrupt every prompt REDS instead of shipping. Mirror the existing fake-repo `span()` stubs at tests/unit/test_pack_arc.py:110 and tests/unit/test_plan_pass_checkpoint.py:235 (both already return the raw-key shape — they will need the derived_blocks stub added for the route tests).

*Evidence:* services/composition-service/app/routers/arc.py:455 + app/mcp/server.py:4255 (`out["span"] = await structures.span(node.id)`) vs app/routers/arc.py:428-433 (`derived = await structures.derived_blocks(book_id)` … `d.update(derived.get(n.id, empty))`). Shapes: app/db/repositories/structure.py:681-686 (raw `min_story_order`/`max_story_order` from `min(story_order)`/`max(story_order)` at :662-663) vs structure.py:312-327 (`{span:{from_order,to_order}, is_contiguous, chapter_count, first_story_order}` dense-ranked at :279). Repo-fix forbidden: app/packer/lenses.py:322 (`structure_repo.span(...)` per chain node, `return_exceptions=True` at :323) → lenses.py:247-248 (`lo = span.get("min_story_order"); hi = span.get("max_story_order")`) interpolating raw strided story_order. Archived-has-no-key: structure.py:264 (`WHERE book_id = $1 AND NOT is_archived` in the recursive CTE).

### Q-32-SPAN-REPO-TRAP
CONFIRM the spec's LOCKED answer — leave `StructureRepo.span()` exactly as-is — but REPLACE its DoD mitigation, which is a no-op as written. Four concrete steps:

(A) LOCK the producer. Do not dense-rank, rename, or drop keys in `StructureRepo.span()` (services/composition-service/app/db/repositories/structure.py:641-685). Keys stay `min_story_order`/`max_story_order`/`chapter_count`/`is_contiguous`; values stay RAW strided `story_order`. Add a grep-able backlink comment at the return dict (structure.py:681): "# CONSUMED BY THE PACKER — app/packer/lenses.py:247 (_arc_position) reads these exact keys against the scene's RAW strided story_order. Dense-ranking or renaming silently corrupts the Pacing line in EVERY generation prompt. See Q-32-SPAN-REPO-TRAP."

(B) THE LOAD-BEARING PIN (this is the one that actually reds). In tests/integration/db/test_structure_repo.py, ADD (do not mutate the existing contiguity test) `test_span_returns_raw_story_order_not_dense_rank`: seed a STRIDED fixture via `_seed_chapters(pool, actor, project, book, arc.id, [10, 20, 30])` and assert `span == {"min_story_order": 10, "max_story_order": 30, "chapter_count": 3, "is_contiguous": False}`, with the comment "a dense-rank would return max=2 — that silently rewrites the pacing %% in every generation prompt." The existing exact-dict assert at :317-321 CANNOT catch this: it seeds [0,1,2], which is already dense, so raw == dense-ranked.

(C) CLOSE THE ENV-GATE HOLE, or (B) pins nothing in practice. tests/integration/db/ is `skipif` on TEST_COMPOSITION_DB_URL (test_structure_repo.py:27,33) — per this repo's own lesson `env-gated-integration-tests-skip-and-the-green-suite-lies`, an unset DSN makes it vanish silently. Either set TEST_COMPOSITION_DB_URL in the CI/VERIFY run for composition-service, OR add a cheap always-runs guard in tests/unit/test_pack_arc.py: `import inspect; src = inspect.getsource(StructureRepo.span); assert '"min_story_order"' in src and '"max_story_order"' in src` with a comment that the FakeStructureRepo in this file cannot catch a producer rename. Prefer the CI DSN; the source-pin is the fallback.

(D) DO NOT make `_arc_position` strict (`span["min_story_order"]` instead of `.get()`). Verified: pack.py's outer asyncio.gather (~:338) has NO `return_exceptions=True` and the pacing block (lenses.py:322-333) is NOT inside a try — a KeyError would propagate and 500 the entire pack, breaking the documented "the arc frame THINS, never fails a pack" degrade-safe posture. Keep `.get()`.

Builder-facing rationale to carry into the wave: the M1 DoD item as literally worded ("a gather_arc pacing test that PINS span()'s raw keys") is ALREADY SATISFIED — tests/unit/test_pack_arc.py:193-194 asserts `~60% through arc "Betrayal"` / `~53% through saga "Ascension"` — and it catches NEITHER failure mode, because it drives `FakeStructureRepo.span()` (test_pack_arc.py:109-114), a hardcoded dict that never calls the real repo. Ticking that DoD box without (B) leaves the trap fully open. The pin must live against the PRODUCER (the real repo, strided fixture), not against the fake.

*Evidence:* services/composition-service/app/db/repositories/structure.py:641-685 (span() returns RAW strided min/max_story_order; return dict at :681-685) · app/packer/lenses.py:241-254 (_arc_position `.get()`s "min_story_order"/"max_story_order" → rename yields None → Pacing line silently dropped at :329-333) · app/packer/lenses.py:322 (the third caller — gather_arc's `structure_repo.span(...)` inside asyncio.gather) · app/mcp/server.py:4255 + app/routers/arc.py:455 (the two inspector callers) · tests/unit/test_pack_arc.py:109-114 (FakeStructureRepo.span = hardcoded dict — never touches the real repo) + :193-194 (the pacing asserts that ALREADY exist and catch nothing) · tests/integration/db/test_structure_repo.py:317-321 (the ONLY real-span key assert — but its fixture seeds story_order [0,1,2], already dense, so a dense-rank stays GREEN) + :330 (the strided [0,1,5] fixture asserts only chapter_count/is_contiguous, never min/max) + :27,:33 (skipif TEST_COMPOSITION_DB_URL — the whole file vanishes when unset) · app/packer/pack.py:~338 (outer asyncio.gather has NO return_exceptions=True → a strict-key KeyError would 500 the whole pack, so `.get()` must stay)

### Q-32-ARC-QUERY-KEY-DRIFT
PICK THE `plan-hub` NAMESPACE. There is no `['composition','arcs',...]` namespace in the codebase and there must not be one — the spec's §6 step 8 reference to it is a phantom key that re-introduces a bug this repo already fixed and documented. Concretely, the builder does exactly this:

1. DETAIL KEY (name it, it was unnamed): the per-arc `GET /v1/composition/arcs/{node_id}` fetch is keyed **`['plan-hub', 'arc', arcId]`** — keyed on `arcId` ALONE (no bookId; structure-node ids are globally unique, and this is a by-id read). This mirrors the shipped precedent `['plan-hub','node', nodeId]` at `frontend/src/features/plan-hub/hooks/usePlanNode.ts:60` exactly. Put the query in the new `frontend/src/features/studio/panels/useArcInspector.ts`.

2. SHELL KEY (unchanged): the inspector's picker/breadcrumb/blast-radius reads the SHARED `['plan-hub','arcs', bookId]` cache via `getArcs` — no second fetch. This is what §2/§4 already say (`usePlanHub.ts:34`, `usePlanNavigator.ts:77`, `usePlanNode.ts:67` all share it; TanStack dedupes to one call).

3. §6 STEP 8 — DELETE the `['composition','arcs', bookId]` invalidation. The new `frontend/src/features/studio/agent/handlers/arcEffects.ts` registers `registerEffectHandler(/^composition_arc_/, arcEffect)` and its body invalidates **`['plan-hub']` ONLY** — the single prefix invalidate reaches BOTH `['plan-hub','arcs',bookId]` (shell) and `['plan-hub','arc',arcId]` (detail) by prefix match, which is precisely why the detail key must live under that prefix. Copy the settle shape from `usePlanNodeWrites.ts:51`.

4. OCC RE-SEED (required, same bug class as `instant-commit-control-over-occ-entity`): the inspector's PATCH mutation must do `onSuccess: (fresh) => qc.setQueryData(['plan-hub','arc', arcId], fresh)` before `onSettled: settle`, mirroring `usePlanNodeWrites.ts:74`. Without it the controls re-enable holding the pre-write `version` and the user's next keystroke 412s against a phantom collaborator.

5. THE ONE LEGITIMATE CROSS-NAMESPACE CASE — call it out so Wave 4 does not get this wrong: arc TEMPLATES genuinely DO live in the `composition` namespace (`['composition','arc-template', arcId]` at `useArcTimeline.ts:40`; `['composition','arc-templates','all']` at `useArcLibrary.ts:10`), and the `['plan-hub']` prefix does NOT reach them. So when spec 34 (Wave 4) EXTENDS `arcEffects.ts`'s handler body for `composition_arc_apply` / `composition_arc_extract_template`, that body adds `invalidateQueries(['composition','arc-templates'])` + `['composition','arc-template']`. That is templates, not arcs — it does not resurrect `['composition','arcs',...]`.

TEST (Definition of Done for the slice): a vitest in `frontend/src/features/studio/agent/handlers/__tests__/arcEffects.test.ts` asserting that a `composition_arc_update` tool result invalidates a query registered at `['plan-hub','arc', '<id>']` (i.e. the detail query actually refetches) — the anti-phantom-key proof. A grep-guard is not enough; assert the EFFECT (the detail query is marked stale), per CLAUDE.md's "checklist ⇒ test the effect".

WHY THIS AND NOT THE OTHER BRANCH: `['composition','arcs',bookId]` has ZERO queries anywhere in `frontend/src`. Worse, the `composition` namespace's arc-shaped keys are already TAKEN by two unrelated concepts — `['composition','arc',...]` = CHARACTER arcs (`useCharacterArc.ts:46-87`) and `['composition','arc-template',...]` = arc templates. Adding structure-node arcs there would be three concepts under one name (violates the Frontend-Tool-Contract "one name for one concept" rule) AND would sit outside the `['plan-hub']` prefix every existing arc writer invalidates, which is exactly the silent-staleness the concern predicts. This is not a taste call: `usePlanNodeWrites.ts:45-49` is a code comment describing this identical bug (a dead `['composition','node']` invalidation) being removed for this identical reason.

*Evidence:* frontend/src/features/plan-hub/hooks/usePlanNodeWrites.ts:45-51 — the load-bearing comment: "An earlier version also invalidated ['composition','node'], a key no query in this codebase uses — dead code with a comment claiming it was load-bearing, which is worse than none: the next person re-keys the drawer out of the prefix, trusts the comment, and it goes silently stale." followed by the single `void qc.invalidateQueries({ queryKey: ['plan-hub'] });`. || frontend/src/features/plan-hub/hooks/usePlanNode.ts:60 — `queryKey: ['plan-hub', 'node', nodeId]` = the by-id DETAIL-key precedent (id alone, under the plan-hub prefix). || usePlanNodeWrites.ts:74 — `qc.setQueryData(['plan-hub','node', v.nodeId], fresh)` = the OCC re-seed to mirror. || Shared shell: usePlanHub.ts:34, usePlanNavigator.ts:77, usePlanNode.ts:67 all key `['plan-hub','arcs',bookId]`. || The phantom: `grep -rn "'composition', *'arcs'" frontend/src` → ZERO hits. The near-misses are different concepts: useCharacterArc.ts:46-87 (`['composition','arc','roster'|'events'|'cutoff'|'detail'|'status']` = character arcs) and useArcTimeline.ts:40 / useArcLibrary.ts:10 (`['composition','arc-template', arcId]`, `['composition','arc-templates','all']` = arc TEMPLATES — the only keys Wave 4 legitimately needs to invalidate outside the plan-hub prefix). || Handlers barrel (arcEffects.ts is the NEW file): frontend/src/features/studio/agent/handlers/ currently holds bookEffects.ts, glossaryEffects.ts, knowledgeEffects.ts, translationEffects.ts, resultEnvelope.ts.

### Q-32-BE-A2-IFMATCH-428
**428 Precondition Required (spec's pick) — confirmed by code, with ONE correction to the spec's fix.** Zero REST callers exist (`frontend/src/features/plan-hub/api.ts` only calls `/arcs/{id}/move` and `/books/{id}/arcs/assign-chapters`; no test posts a PATCH to `/v1/composition/arcs/{id}`), so making the header mandatory breaks nothing. 400 is wrong here: 400 already means "If-Match present but not an integer" (`arc.py:85`), and reusing it would collapse two distinct client errors into one; 428 is the exact semantic ("send the precondition and retry") and lets the FE distinguish "I forgot the header" (bug) from "bad header" (bug) from 412 (real conflict).

**BUILD INSTRUCTIONS (3 edits + 4 tests):**

**1 · `services/composition-service/app/routers/arc.py` — add a helper next to `_parse_if_match` (after line 85):**
```python
def _require_if_match(if_match: str | None) -> int:
    """Arc content writes are OCC-mandatory (BE-A2): a blind clobber is not a legal
    request. Absent header ⇒ 428; present-but-garbage ⇒ 400 via _parse_if_match."""
    if if_match is None:
        raise HTTPException(status_code=428, detail={
            "code": "IF_MATCH_REQUIRED",
            "message": "If-Match: <version> is required on arc writes (optimistic concurrency)",
        })
    return _parse_if_match(if_match)  # type: ignore[return-value]
```
Then in `patch_arc` (arc.py:489-512) change the call at **arc.py:501-503** to `expected_version=_require_if_match(if_match)`. **Keep the param as `str | None = Header(default=None, alias="If-Match")`** — do NOT make it a required FastAPI `Header(...)`, which would yield 422, not 428. **Do NOT touch `patch_arc_template` (arc.py:216)** — different resource, has callers, out of scope.

**2 · `services/composition-service/app/db/repositories/structure.py:376-382` — move the version bump OUT of the OCC branch (THIS IS THE PART THE SPEC GOT WRONG).** The spec says "with both doors requiring it, `expected_version=None` becomes unreachable — leave the repo branch." **False:** `services/composition-service/app/engine/arc_apply.py:497-507` calls `structure_repo.update(..., expected_version=None)` as a live in-process blind write (the post-apply template snapshot: tracks/roster/roster_bindings/arc_template_id/template_version), and today that write leaves `version` untouched — so a GUI holder of v7 still succeeds with `If-Match: 7` against content the apply engine just replaced. Closing only the REST door leaves the exact hazard BE-A2 describes. Fix:
```python
set_clauses.append("updated_at = now()")
set_clauses.append("version = version + 1")   # ← ALWAYS bump; a write is a write

version_clause = ""
if expected_version is not None:
    params.append(expected_version)
    version_clause = f" AND version = ${len(params)}"
```
(leave the `if expected_version is None: return None` / `VersionMismatchError` tail at 397-401 exactly as is — it is the 404-vs-412 discriminator).

**3 · No contract change** — `contracts/api/composition/v1/openapi.yaml` does not describe `/arcs/{node_id}`; nothing to update. MCP door already correct (`_ArcUpdateArgs.expected_version: int`, `server.py:4333`) — leave it.

**TESTS (composition-service, `tests/unit/`):**
- `PATCH /v1/composition/arcs/{id}` with **no** `If-Match` → **428**, `detail.code == "IF_MATCH_REQUIRED"`, and assert `StructureRepo.update` was **NOT called** (prove the write never reached the DB).
- `If-Match: "abc"` → **400** (preserve existing behavior).
- `If-Match: "7"` on a v7 row → **200** and the returned node's `version == 8`.
- **Repo/engine test pinning edit #2:** `StructureRepo.update(node, {...}, expected_version=None)` bumps `version` 1→2 (this is the arc_apply path; without this test the "always bump" line gets refactored back out).

**Rationale for the PO to veto if they disagree:** the alternative reading — "leave the repo branch, close only the REST door" — is cheaper by one line but leaves `arc_apply` producing rows whose version lies about their content, which is precisely the stale-token bug M3's OCC write chain depends on being impossible.

*Evidence:* services/composition-service/app/routers/arc.py:495 (`if_match: str | None = Header(default=None, alias="If-Match")`) → arc.py:501-503 (`expected_version=_parse_if_match(if_match)`) → services/composition-service/app/db/repositories/structure.py:378-382 (version clause AND `version = version + 1` both live only inside `if expected_version is not None:`). MCP door already strict: services/composition-service/app/mcp/server.py:4333 (`expected_version: int`). **Spec-correcting evidence: services/composition-service/app/engine/arc_apply.py:497-507 calls `structure_repo.update(..., expected_version=None)` — a live blind-write caller, so the repo branch is NOT unreachable and must be fixed, not merely orphaned.** Zero REST callers: frontend/src/features/plan-hub/api.ts:196 (`/arcs/{id}/move`) and :248 are the only `/arcs/` writes.

### Q-32-BE-A3-UNASSIGN
BUILD IT — take the spec's pick (nullable `structure_node_id` on the EXISTING assign-chapters route + MCP tool), NOT a separate unassign route. Rationale: the column is already nullable and the CHECK already legalizes NULL, so unassign is a schema-legal state, not a new concept; assign/unassign share every guard (book scope, kind='chapter', NOT is_archived, EDIT gate) and differ only in the SET value — a second route/tool would duplicate the gate + repo + MCP tool + FE client for one changed literal, and PO-3 ("one name for one concept") cuts against it. NO MIGRATION NEEDED.

DO ALL FOUR (both doors, per GG-2):

1. `services/composition-service/app/db/repositories/structure.py:540` — widen to `assign_chapters(self, book_id: UUID, structure_node_id: UUID | None, chapter_node_ids: list[UUID]) -> int`. **CRITICAL: branch onto a SECOND SQL statement — do NOT pass NULL as `$1` into the existing one.** The guard reads `EXISTS (SELECT 1 FROM structure_node s WHERE s.id = $1 AND s.book_id = $2)`; with `$1 = NULL` that is `s.id = NULL` → NULL → never true → EXISTS false → **0 rows updated, returns 200 `{"assigned": 0}`** — a silent no-op reported as success (this repo's "silent success is a bug" class). The `None` branch is: `UPDATE outline_node o SET structure_node_id = NULL, updated_at = now() WHERE o.book_id = $1 AND o.id = ANY($2) AND o.kind = 'chapter' AND NOT o.is_archived` — drop the EXISTS guard (there is no arc to check), KEEP book_id + kind + NOT is_archived. Keep the early `if not chapter_node_ids: return 0`.

2. `services/composition-service/app/routers/arc.py:364` — `structure_node_id: UUID | None` on `ArcAssignChapters`. **Give it NO default** (Pydantic v2: Optional-without-default is REQUIRED) so the caller must send `null` explicitly. Then at `arc.py:572` fix the response: `str(body.structure_node_id)` renders the literal string `"None"` for a null — emit `str(...) if body.structure_node_id else None` (JSON null).

3. `services/composition-service/app/mcp/server.py:4510` — `structure_node_id: str | None` on `_ArcAssignChaptersArgs`, again **no default**. This is deliberate and is my one judgment call (PO may veto): the model is `ForbidExtra`, and if omission meant "unassign", an LLM that simply forgets the arg would silently wipe arc membership. Required-but-nullable makes omission a validation error and `null` an explicit intent. Also parse it as `UUID(args.structure_node_id) if args.structure_node_id else None` at :4538, and pass it straight through in the return at :4541 (it is already `str | None` → JSON null). **Update the tool description at :4516-4522** — add that `structure_node_id: null` REMOVES the chapters from their arc, returning them to the unassigned pool, and add synonyms ["unassign chapter", "remove chapter from arc", "detach chapter"]. Without this the capability ships undiscoverable (the "built but unreachable" class).

4. `frontend/src/features/plan-hub/api.ts:241` — widen `structureNodeId: string | null`. The body at :252 already always sends the key, so no caller breaks. This is the client the M4 inspector's "remove chapter from arc" consumes.

TESTS (the round-trip is the one that proves the gap is closed):
- `tests/integration/db/test_structure_repo.py` — assign → unassign → the row is readable again via the `unassigned` axis. Assert the returned `assigned` count is the real row count, NOT 0 (this is the test that catches the NULL-into-EXISTS silent no-op).
- Same file — negative guards on the None branch: does not touch chapters in ANOTHER book; does not touch non-`chapter` kinds; does not touch archived rows.
- `tests/unit/test_arc_hub_routes.py` — POST with `structure_node_id: null` → 200 `{"assigned": N, "structure_node_id": null}` (assert JSON null, not the string "None").
- `tests/unit/test_mcp_arc_structure.py` — explicit `null` unassigns; OMITTING the field raises a validation error (proves the destructive-omission footgun is closed).
- Full-loop: `GET /v1/composition/books/{bid}/outline/children?unassigned=true` returns the chapter after the unassign — the reader/writer loop now closes.

No change to `contracts/tool-liveness.json` (its entry pins only status/executes/proven, no args).

*Evidence:* WRITER (the gap): services/composition-service/app/db/repositories/structure.py:540-564 — `assign_chapters` does `SET structure_node_id = $1` (line 554) guarded by `EXISTS (SELECT 1 FROM structure_node s WHERE s.id = $1 AND s.book_id = $2)` (lines 557-560); no NULL branch. A grep for SET/UPDATE on `structure_node_id` across services/composition-service/app/db/repositories/*.py returns exactly this one line — the only other NULL-producer in the codebase is the one-time migration app/db/arc_lift.py:164. DOORS: app/routers/arc.py:364 `structure_node_id: UUID` (non-null) and app/mcp/server.py:4510 `structure_node_id: str` (non-null). READER (shipped, renders the state no writer can produce): app/db/repositories/outline.py:886 `WHERE book_id = $1 AND structure_node_id IS NULL`, exposed by app/routers/outline.py:314+330 (`unassigned=true` axis), consumed by frontend/src/features/plan-hub/api.ts:241. SCHEMA (why no migration): app/db/migrate.py:1181 `ALTER TABLE outline_node ADD COLUMN IF NOT EXISTS structure_node_id UUID` — nullable — and migrate.py:1188 `CHECK (structure_node_id IS NULL OR kind = 'chapter')` — NULL is explicitly legal. SEALED-DECISION CHECK: docs/specs/2026-07-01-writing-studio/30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md:44 (GG-2 inverse law) supports the both-doors requirement; :21 (PO-3 "one name for one concept") supports nullable-on-existing over a separate route. Nothing in §0 bars this.

### Q-32-DRIFT-LOCK-COUNT-CONTRADICTION
§6 is right, §9 M2 is wrong — and BOTH are more literal than the code requires: **no drift-lock test asserts a panel COUNT at all.** The three "drift-lock" suites assert SET EQUALITY, which is self-adjusting to whatever the baseline is.

Proof from the suite (`panelCatalogContract.test.ts`):
- `expect(Array.isArray(enumIds) && enumIds.length > 0).toBe(true)` — non-empty, no number
- every advertised `panel_id` ∈ `STUDIO_PANEL_COMPONENTS` (buildable)
- `expect([...enumIds].sort()).toEqual(OPENABLE_STUDIO_PANELS.map(p => p.id).sort())` — advertised set == openable set
- every openable panel has a `category`
`services/chat-service/tests/test_frontend_tools_contract.py` likewise asserts only "closed-set arg MUST declare an enum" + contract-file parity (regenerated via `WRITE_FRONTEND_CONTRACT=1`), never a length. There is nothing anywhere for a builder to "hunt" — 57, 58, 61, 62 are all irrelevant to green.

**BUILDER INSTRUCTION (do exactly this in M2):**
1. Edit `docs/specs/2026-07-01-writing-studio/32_arc_inspector.md` §9, row M2: replace `The 4 drift-lock suites green (58==58==58).` with:
   `The 4 drift-lock suites green — they assert SET EQUALITY (py \`panel_id\` enum ≡ \`contracts/frontend-tools.contract.json\` enum ≡ \`OPENABLE_STUDIO_PANELS\`), NOT a count. Assert the DELTA only: the enum length is exactly (pre-wave baseline + 1) and \`arc-inspector\` is present in all three. NEVER pin a literal (not 58, not 61, not 62) — the baseline depends on how many panels spec 31 (Wave 1) has landed.`
2. Also strike the "the baseline here is **61**, not 57" sentence in §6 down to: "the baseline is whatever HEAD has when this wave starts — measure it, don't quote it." (57 was true at `9262ed53e`; 61 is a *prediction* about spec 31 that will itself go stale.)
3. In M2, the ONLY count check a builder runs is the delta, measured, not remembered:
   `git stash` (or note the pre-change value) → `python -c "import json;c=json.load(open('contracts/frontend-tools.contract.json'));print(len(c['ui_open_studio_panel']['args']['panel_id']['enum']))"` before and after; assert `after == before + 1` and that `'arc-inspector'` is the only added member.
4. Do NOT add a new count-pinning test. A literal-count assertion is exactly the anti-pattern the drift-lock design already avoids; adding one would red on every future panel.

Measured at HEAD `9262ed53e` (this run, to ground the delta): py enum = **57**, contract enum = **57**. So if spec 31 lands 4 panels first, the after-value here happens to be 62 — but nothing asserts it, and the builder must not write that number down.

*Evidence:* frontend/src/features/studio/panels/__tests__/panelCatalogContract.test.ts:22-34 (the three-way drift-lock is `expect([...enumIds].sort()).toEqual(OPENABLE_STUDIO_PANELS.map(p=>p.id).sort())` + `enumIds.length > 0` — no literal count); services/chat-service/tests/test_frontend_tools_contract.py:121-128 (asserts closed-set args declare an enum, never its length); services/chat-service/app/services/frontend_tools.py:400 (`panel_id` enum, len=57 at HEAD 9262ed53e; contracts/frontend-tools.contract.json enum len=57 — measured this run); contradiction sites: docs/specs/2026-07-01-writing-studio/32_arc_inspector.md:360-364 (§6, "never the literal 58", baseline 61) vs :465 (§9 M2, "58==58==58").

### Q-32-BE-A3-FASTMCP-3-SCHEMAS
**The "3 schema sources" caveat DOES NOT APPLY to composition-service — it has exactly ONE. The spec inherited the warning from knowledge-service, whose structure composition does not share. But there IS a real silent-drop trap on the REST door, and BE-A3 must close it. Builder: do the 7 edits below, all in one commit.**

**Why one, not three (verified against code):**
1. Composition registers tools with a **single Pydantic arg model** passed as one `args:` param to `@mcp_server.tool` (`server.py:4508-4531`). FastMCP derives the advertised `inputSchema` from that model directly (emitted as a `$defs` entry referenced by `args` — the repo's own test walks exactly this: `tests/unit/test_mcp_server.py:220-223`). **The Pydantic model IS the schema.**
2. **`services/composition-service/app/mcp/tools/` DOES NOT EXIST** (verified — `app/mcp/` holds only `server.py`, `service_bearer.py`, `__init__.py`). So knowledge's source #1 (separate arg-model module) and source #2 (bespoke `TOOL_DEFINITIONS`/`definitions.py` OpenAI hand-schema) **have no counterpart here**.
3. `_ArcAssignChaptersArgs` extends **`ForbidExtra`** (`sdks/python/loreweave_mcp/errors.py:34`, `extra="forbid"`) — an undeclared arg is **REJECTED with an error, not silently stripped**. Knowledge's exact silent-strip failure mode is structurally impossible here.
4. `contracts/tool-liveness.json` (+ the two service copies) carry only `{status, executes, proven}` — **no arg schema**. Not a source.

**The REAL trap for BE-A3 (different lesson, same family — `rest-write-mirror-drops-fields-the-mcp-tool-accepts`):** `class ArcAssignChapters(BaseModel)` (`arc.py:363-365`) is a **plain BaseModel** ⇒ pydantic's default `extra="ignore"` ⇒ **the REST door silently drops any field it doesn't declare**. The MCP door errors loudly; the GUI door no-ops silently. Loosening only one door is the actual bug BE-A3 can ship.

**THE EDIT LIST (7 sites — this is the enumeration the spec owes you):**
1. `services/composition-service/app/mcp/server.py:4510` — `structure_node_id: str` → `structure_node_id: str | None = None`. *(sole MCP schema source)*
2. `server.py:4516-4522` (tool `description`) — state that **`structure_node_id: null` ⇒ UNASSIGN** (returns the chapters to the `?unassigned=true` pool). The description is the agent's only affordance doc.
3. `server.py:4525-4528` (`require_meta` synonyms) — add `"unassign chapters"`, `"remove chapter from arc"`, `"return chapters to the unassigned pool"`.
4. `server.py:~4536` (handler) — `UUID(args.structure_node_id)` → `UUID(args.structure_node_id) if args.structure_node_id else None`.
5. `services/composition-service/app/routers/arc.py:364` — `structure_node_id: UUID` → `UUID | None = None`. **Both doors or neither** — a GUI-only unassign is the GG-2 INVERSE gap the spec forbids.
6. `arc.py:572` (response) — `str(body.structure_node_id)` → `str(body.structure_node_id) if body.structure_node_id else None` (else it returns the literal string `"None"`).
7. `services/composition-service/app/db/repositories/structure.py:540-564` — signature `structure_node_id: UUID | None`; when `None`: `SET structure_node_id = NULL` and **DROP the `EXISTS (SELECT 1 FROM structure_node …)` subquery** on that branch (it can never be satisfied by NULL), **KEEP** `o.book_id = $2 AND o.id = ANY($3) AND o.kind = 'chapter' AND NOT o.is_archived`.
8. FE mirror `frontend/src/features/plan-hub/api.ts:239-252` — `structureNodeId: string | null`; return type `{ assigned: number; structure_node_id: string | null }`.

**TESTS (the drift guard, adapted — composition's equivalent of knowledge's `test_mcp_inputschema_mirrors_bespoke_openai_schema`):**
- `tests/unit/test_mcp_server.py` — a NEW assertion against the **live** `session.list_tools()` `inputSchema`: `$defs["_ArcAssignChaptersArgs"].properties.structure_node_id` accepts **null** (an `anyOf` with `{"type":"null"}`). This is the one test that proves FastMCP actually advertises the nullable arg. It already stands up an in-process FastMCP server, so this is a ~6-line add.
- A **both-doors parity test**: REST `POST …/arcs/assign-chapters` with `structure_node_id: null` AND MCP `composition_arc_assign_chapters` with `structure_node_id: null` each land the chapter in `?unassigned=true` (`outline.py:849` = `structure_node_id IS NULL`).
- A negative test: unassign does **not** touch chapters outside `book_id`, and does not touch non-`chapter`-kind or archived nodes.

**Default I picked (veto-able):** unassign is expressed as the **existing tool with a nullable arg**, not a new `composition_arc_unassign_chapters` tool — that is exactly what spec 32 §5 BE-A3 prescribes, it keeps the catalog flat, and `ForbidExtra` makes the arg's absence a loud error rather than a silent no-op.

**Single-service change ⇒ no cross-service live-smoke required**; the in-process FastMCP `list_tools()` assertion is the real gate.

*Evidence:* services/composition-service/app/mcp/server.py:4508-4511 (`_ArcAssignChaptersArgs(ForbidExtra)` — the SOLE schema source; FastMCP derives inputSchema from it) · `services/composition-service/app/mcp/tools/` DOES NOT EXIST (ls of app/mcp/ = server.py, service_bearer.py, __init__.py — so knowledge's `tools/definitions.py` TOOL_DEFINITIONS + separate arg-model sources have no counterpart) · sdks/python/loreweave_mcp/errors.py:34 (`class ForbidExtra(BaseModel)`, extra="forbid" ⇒ undeclared arg REJECTED, never silently stripped) · services/composition-service/tests/unit/test_mcp_server.py:216-223 (walks the LIVE `list_tools()` inputSchema `$defs` — proves the pydantic model is what is advertised) · services/composition-service/app/routers/arc.py:363-365 (`class ArcAssignChapters(BaseModel)` — plain BaseModel, pydantic default extra="ignore" = the REAL silent-drop door) · services/composition-service/app/db/repositories/structure.py:540-564 (`assign_chapters` — `SET structure_node_id = $1` + the EXISTS guard to branch on) · contracts/tool-liveness.json:162 (entry = `{status, executes, proven}` only — carries NO arg schema, therefore not a schema source)

### Q-32-BUS-SLICE-ARC
BUILD IT — it is unbuilt work, not a blocker, and it is a 3-file additive change with zero cross-service surface. Ship it as an M2 slice exactly as follows.

(1) `frontend/src/features/studio/host/types.ts` — three additive edits, NULLABLE arcId (the one amendment to the spec):
  • event union (after the `planFocusNode` member, line 66): `| { type: 'arc'; arcId: string | null }`
  • snapshot (after `planFocusSeq?: number`, line 88): `/** 32 AI-1 — the arc the Plan Hub last selected (arc/saga node), or the agent's resource_ref. The arc-inspector's subject when props.params.arcId is absent. Cleared (undefined) on a 404 / revoked grant → the panel falls back to the picker. */ activeArcId?: string;`
  • `applyBusEvent` (beside `case 'planFocusNode'`, line 109): `case 'arc': return { ...base, activeArcId: e.arcId ?? undefined };`
WHY nullable (spec says `arcId: string`): spec 32 §3.4 line 254 requires the panel to "clear the bus slice" on a 404, and `arcId: string` makes clearing inexpressible. `string | null` is the cheapest expression of it and mirrors `PlanCanvas.tsx:267`'s `onSelect(null)`. No other consumer changes.

(2) `frontend/src/features/studio/panels/PlanHubPanel.tsx` — the publisher. `useStudioHost` is ALREADY imported (line 24); `view.nodeContent[id].kind` already yields `'arc'|'saga'|'chapter'|'scene'` (used at line 172-173). Add ONE callback and route BOTH existing selection entry points through it:
```ts
// 32 AI-1 — the reverse publish this file's header deferred ("no consumer reads a Hub-selection
// bus slice yet"). The arc-inspector is that consumer.
const selectNode = useCallback((id: string | null) => {
  view.select(id);
  if (!id) return;                       // deselect does NOT clear the inspector's subject (below)
  const kind = view.nodeContent[id]?.kind;
  if (kind === 'arc' || kind === 'saga') host.publish({ type: 'arc', arcId: id });
}, [view.select, view.nodeContent, host]);
```
  • line 217: `onSelect={view.select}` → `onSelect={selectNode}`
  • line 112 (inside `focusNode`): `select(nodeId)` → `selectNode(nodeId)` so a Plan-rail row focus publishes too (hoist `selectNode` above `focusNode` and add it to `focusNode`'s dep array; drop `select` from that array).
  • update the file-header comment lines 20-21 — the "reverse publish is deferred" note is now false.

(3) DEFAULTS I am picking (stated so the PO can veto without a checkpoint):
  a. **Pane-click deselect does NOT publish `arcId: null`.** Only an arc/saga SELECT publishes. Rationale: the inspector's subject persisting after a canvas deselect matches the existing `scene-inspector` behavior (`useSceneInspector.ts:25` reads `activeSceneId`, which no one ever nulls), and a disappearing inspector on a stray canvas click is worse than a slightly stale one.
  b. **`arcId: null` has exactly ONE publisher: the arc-inspector itself, on 404** (spec §3.4 line 254) — `host.publish({ type: 'arc', arcId: null })` alongside the "This arc is no longer accessible." message, which drops the panel back to the picker.
  c. **saga counts as an arc subject** (spec line 377 says "arc/saga node selection"); `PlanNodeContent.kind` is the discriminator, no new type needed.
  d. The event carries **no `bookId`** (unlike `chapter`) — the bus snapshot is already per-book (`StudioHostProvider.tsx:72` seeds `bookId` and the host remounts on book switch).

(4) TEST (the slice is not done without it) — new `frontend/src/features/studio/host/__tests__/arcBus.test.ts`, mirroring `planFocusBus.test.ts` exactly: `applyBusEvent(empty(), {type:'arc', arcId:'a1'}).activeArcId === 'a1'` and revision bumped; `{type:'arc', arcId:null}` clears it to `undefined` and still bumps revision; an `arc` publish leaves `activeChapterId`/`activeSceneId` untouched (additive, non-clobbering). Plus one `PlanHubPanel` test: clicking an arc/saga node publishes `{type:'arc'}` and clicking a CHAPTER node does not.

This is M2 registration-checklist step 7 (spec line 377) and unblocks the inspector's `bus.activeArcId` subject source (spec line 144). No BE work is implied despite the `BE_PREREQ` label — the item is 100% frontend.

*Evidence:* frontend/src/features/studio/host/types.ts:43-66 (StudioBusEvent union — no `arc` member), :70-89 (StudioBusSnapshot — no `activeArcId`), :92-114 (applyBusEvent — no `arc` case) — the spec's claim verified. frontend/src/features/studio/panels/PlanHubPanel.tsx:20-21 ("The reverse publish (planHub.selection) is deferred — no consumer reads a Hub-selection bus slice yet") — the deferral whose trigger the arc inspector now fires; :24 (useStudioHost already imported), :103-114 (focusNode → select), :172-173 (`view.nodeContent[id].kind` discriminator), :217 (onSelect={view.select} — the publish site). frontend/src/features/plan-hub/components/PlanCanvas.tsx:258-267 (onNodeClick → onSelect(node.id); onPaneClick → onSelect(null)) and docs/specs/2026-07-01-writing-studio/32_arc_inspector.md:254 ("clear the bus slice") — together they force the `arcId: string | null` amendment. Template test: frontend/src/features/studio/host/__tests__/planFocusBus.test.ts:11-38.

### Q-32-WAVE1-ORDERING-DEP
**The ordering dependency does not exist. Wave 2 may start at any time after Wave 0, before/parallel to/after Wave 1 — and NO code changes as a result.** The concern is a doc-prose bug in spec 32, not a sequencing risk. Two things ground this, and both are checkable:

(a) **Nothing in the repo asserts a panel COUNT.** The three drift-lock suites are pure set-equality guards: `panelCatalogContract.test.ts:23` only asserts `enumIds.length > 0`; `:26-30` asserts every advertised id is buildable; `:33` asserts `[...enumIds].sort()).toEqual(openable)` — a SET comparison with no number in it. `services/chat-service/tests/test_frontend_tools_contract.py` regenerates a snapshot and enforces conventions (one schema per name, closed-set args carry `enum`) — again, no count. So whether the baseline is 57 or 61 is invisible to CI. A builder who lands Wave 2 first gets 57→58; second gets 61→62; **both are green**.

(b) **Plan 30 §9's own sequencing diagram (lines 724-726) already puts Wave 1, Wave 2 and Wave 3 in PARALLEL** — three branches off Wave 0, converging into Wave 6. Wave 2 is not downstream of Wave 1. And they do not collide on files: plan 30 §7 line 614 gives Wave 2 `arcEffects.ts` (new), line 615 gives Wave 1 `compositionEffects.ts` (new). Spec 32's catalog category `'editor'` is already in `CATEGORY_ORDER`; the X-2 defect (`'quality'` missing) is a hard gate on **Wave 1 only**, so it cannot block Wave 2 either.

**BUILDER INSTRUCTIONS — three concrete edits, do them at the start of Wave 2:**

1. **`docs/specs/2026-07-01-writing-studio/32_arc_inspector.md` §6 (lines 360-365)** — delete the sentence *"`31` (Wave 1) lands **4** panels before this wave starts, so the baseline here is **61**, not 57"* and replace the paragraph with: *"Drift-lock is a SET guard, not a count guard (`panelCatalogContract.test.ts:33` compares sorted id sets; the py contract test snapshots a schema). Assert the DELTA (+1 in all three: py enum, contract JSON, `OPENABLE_STUDIO_PANELS`) and the three-way set equality. **Never write a literal count into a DoD or a test.** This wave is therefore ordering-independent of Wave 1 — it may land before, after, or in parallel."*

2. **Same file, §9 milestone M2 (line 465)** — the DoD literally says *"The 4 drift-lock suites green (58==58==58)"*, which contradicts §6's own warning three sections earlier and is exactly the phantom-regression trap it names. Replace with: *"The 4 drift-lock suites green — `enum set == contract set == openable set`, and `arc-inspector` is a member of all three. No literal count."*

3. **If Wave 1 and Wave 2 are run CONCURRENTLY in separate worktrees**, they append rows to four shared files: `frontend/src/features/studio/panels/catalog.ts`, `services/chat-service/app/services/frontend_tools.py` (`panel_id` enum, `:402`), `contracts/frontend-tools.contract.json`, and `frontend/src/i18n/locales/*/studio.json` (18 files). These are **append-only row additions → text-merge cleanly**, EXCEPT the generated contract JSON. Rule: **never hand-merge `contracts/frontend-tools.contract.json`** — after the merge, re-run `WRITE_FRONTEND_CONTRACT=1 pytest services/chat-service/tests/test_frontend_tools_contract.py` and commit the regenerated file, then run the FE suite. Enumerate files on commit (`git commit -- <paths>`); never `git add -A` (shared checkout, plan 30 §9).

**Default I am picking (veto-able):** keep plan 30 §9's stated parallelism — do NOT serialize Wave 2 behind Wave 1. The only thing Wave 1 "gives" Wave 2 was a number that no test reads.

*Evidence:* frontend/src/features/studio/panels/__tests__/panelCatalogContract.test.ts:23 (`enumIds.length > 0` — not a count) and :33 (`expect([...(enumIds ?? [])].sort()).toEqual(openable)` — SET equality, no literal); services/chat-service/tests/test_frontend_tools_contract.py:1-60 (snapshot + conventions, no count); services/chat-service/app/services/frontend_tools.py:402 (panel_id enum = 57 ids at HEAD 9262ed53e, matching spec 32's stated baseline); docs/specs/2026-07-01-writing-studio/30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md:724-726 (sequencing diagram: Wave 0 → Wave 1 ∥ Wave 2 ∥ Wave 3, all converging on Wave 6 — Wave 2 is NOT downstream of Wave 1) and :614-615 (Wave 2 creates arcEffects.ts, Wave 1 creates compositionEffects.ts — disjoint); docs/specs/2026-07-01-writing-studio/32_arc_inspector.md:360-365 (the false "baseline is 61" claim) and :465 (M2 DoD's contradictory literal "58==58==58")

### Q-32-X12-AMEND-PLAN30
AMEND plan-30 (the spec's ask is correct, and the code goes further than it claims). Doc-only edit, land it in the M2/M5 commit. Do NOT extend `ui_open_studio_panel` with a `params` arg — it stays BARE-ID ONLY.

EDIT 1 — `docs/specs/2026-07-01-writing-studio/30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md` §8.2: replace the X-12 bullet (currently ~lines 649-656, beginning "**X-12 — panels that need `params` are structurally OUTSIDE the agent enum.**") with:

- **X-12 — CORRECTED & CLOSED.** The original premise (*"a panel needing an id is structurally OUTSIDE the agent enum"*) was **FALSE**: it conflated *has a target id* with *requires params*. Two panels already in the enum refute it (`chat-service/app/services/frontend_tools.py:402` == `contracts/frontend-tools.contract.json:199`):
  - **`scene-inspector`** (`frontend/src/features/studio/panels/catalog.ts:185` — **no** `hiddenFromPalette`) needs a scene and resolves it from **ambient host state + a selection bus** (`SceneInspectorPanel.tsx:84`, `useSceneInspector(host.bookId)`) — never from `params`. A bare-id open degrades honestly: *"Select a scene to inspect its full plan."* (`SceneInspectorPanel.tsx:99`).
  - **`quality-canon`** (`catalog.ts:270` — **no** `hiddenFromPalette`) reads `props.params`, but they are **OPTIONAL** (`QualityCanonPanel.tsx:33` — `props.params as CanonFocusParams | undefined`). The in-app deep-link caller passes a focus (`PlanHubPanel.tsx:72` → `{bookId, focusRuleId, focusChapterId}`); a bare-id open renders the full book-wide list with no highlight.
  - **THE REAL PREDICATE (use this, not the old one):** a panel is **enum-eligible iff a BARE-ID OPEN IS USEFUL** — its target is ambient-resolvable (host `bookId` + a selection bus), **or** `params` are a pure focus/deep-link refinement that degrades to a sane full view. A panel is `hiddenFromPalette` / out-of-enum **only when `params` are REQUIRED** (nothing sane to render without them). That is exactly today's hidden set: `wiki-editor` (`catalog.ts:144`), `job-detail` (`:168`), `book-reader` (`:173`), `skill-editor` (`:205`), `json-editor` (`:208`).
  - **CONSEQUENCE:** `ui_open_studio_panel` is **NOT** extended with `params` — it stays **bare-id only**, and every panel in this plan is built bare-id-openable (spec 32 confirms all 14 of its batch are). The free-string `panel` + free-form `args` escape hatch is `ui_show_panel` (`contracts/frontend-tools.contract.json:265-277`), which **PO-3 RETIRES** — do not resurrect its shape on `ui_open_studio_panel`.
  - **NOT a Wave 0 decision any more.** Its former partner X-5 is sealed as **PO-3**. `motif-editor` still earns its own bare-id-openability judgment in its own spec (it will almost certainly pass by the `scene-inspector` route: list + selection). **`workflow-editor` is MOOT — G-WORKFLOWS is DROPPED (PO-2, Track C owns it)** — it is struck from this row's examples.

EDIT 2 — same file, §11 (~line 773): mark still-open PO decision **(a) X-5 / X-12 as CLOSED**. Both halves are now answered: the `ui_show_panel` half by **PO-3 (RETIRE)**, the `ui_open_studio_panel`-params half by this row (**NO — bare id only**). Nothing is left for the PO to decide on (a).

No code change, no test change. Rationale for the default, so the PO can veto: adding `params` to `ui_open_studio_panel` would re-create the exact free-form arg shape that PO-3 is deleting, and the two shipped precedents prove it is unnecessary.

*Evidence:* chat-service/app/services/frontend_tools.py:402 — panel_id enum contains BOTH `scene-inspector` and `quality-canon` (mirrored in contracts/frontend-tools.contract.json:199). frontend/src/features/studio/panels/catalog.ts:185 (scene-inspector) + :270 (quality-canon) — neither carries `hiddenFromPalette`, so both are palette-visible AND agent-openable while needing a target. Mechanism A (ambient/bus): SceneInspectorPanel.tsx:84 `useSceneInspector(host.bookId)`, degrade at :99. Mechanism B (optional params): QualityCanonPanel.tsx:33 `props.params as CanonFocusParams | undefined`, deep-link caller PlanHubPanel.tsx:72. Contrast — the genuinely params-REQUIRED panels are the hidden ones: catalog.ts:144/168/173/205/208. Sealed-decision ties: plan-30 §0 PO-3 (RETIRE ui_show_panel — the free-form `args` tool, contracts/frontend-tools.contract.json:265-277) and PO-2 (G-WORKFLOWS DROPPED ⇒ `workflow-editor` is out of plan). Row to amend: 30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md:649-656; §11 item (a) at :773.

### Q-32-BE-A1-MCP-CONTRACT-BREAK
SHIP THE SHAPE CHANGE. No dual-emit, no deprecation window, no tool version bump. The "breaking change to an agent-facing contract" has ZERO consumers: a repo-wide grep for min_story_order/max_story_order finds only (a) StructureRepo.span() itself (structure.py:682-683), and (b) packer/lenses.py:247-248 (_arc_position) — and the packer calls StructureRepo.span() DIRECTLY on the repo, never through composition_arc_get or the REST door. No agent prompt, skill, workflow rail, agent-registry catalog entry, frontend file, or contract file reads the tool's span keys. contracts/tool-liveness.json:182 pins only {status, executes, proven} for composition_arc_get — no output schema. scripts/eval/tool_liveness/project_chain.py:311 only builds {node_id} args and never reads span. MCP tools in this repo carry no output-schema version and the model re-reads tools/list each session, so there is no cached consumer to break. Dual-emit would be actively WRONG: the old keys are raw strided units (STORY_ORDER_CHAPTER_STRIDE=1000), so every value they emit is garbage ("Chapters 41000-58000") — a deprecation window on a field that is always wrong just keeps serving the bug, and an LLM handed both key sets will pick arbitrarily.

BUILDER INSTRUCTION (M1, both doors):
1) services/composition-service/app/mcp/server.py:4255 AND services/composition-service/app/routers/arc.py:455 — replace `out["span"] = await structures.span(node.id)` with the list route's derived block, spread at top level exactly as arc.py:432 does:
     blk = (await structures.derived_blocks(node.book_id)).get(node.id)
     out.update(blk or {"span": None, "is_contiguous": None, "chapter_count": None, "first_story_order": None})
   For an archived node derived_blocks returns NO key -> all-null (NOT the list route's `empty` block, whose chapter_count:0 is the computed-looking-zero trap).
2) THE ONLY REAL AGENT-FACING BREAK IS THE DESCRIPTION STRING — fix it. server.py:4226-4227 currently advertises "the DERIVED `span` (min/max story_order + chapter_count + warn-only is_contiguous ...)". That string IS the contract the model reads. Rewrite to: "the DERIVED `span` (`from_order`/`to_order` — human chapter ORDINALS, e.g. chapters 1-3, NOT raw story_order) + `chapter_count` + warn-only `is_contiguous`; all three are `null` for an archived arc (not computed)."
3) Do NOT touch StructureRepo.span() (structure.py:641) — lenses.py:322 -> _arc_position needs the raw strided axis; spec 32 already mandates the pacing test that pins its raw keys.
4) Tests: retarget tests/unit/test_mcp_arc_structure.py:171 (its AsyncMock on structures.span becomes a mock on derived_blocks) and add the M1 equality assert list[i].span == get(i).span == composition_arc_get(i)["span"], plus the archived -> null (not 0) assert.

DEFAULT NOTED FOR PO VETO: this is a clean break of a shipped shape with no in-repo consumer. If the PO knows of an out-of-repo agent prompt reading min_story_order, that changes the call — nothing in this repo does.

*Evidence:* grep -rn "min_story_order|max_story_order" (excl. node_modules/__pycache__/docs) => ONLY: services/composition-service/app/db/repositories/structure.py:682-683 (span() itself, untouched by BE-A1); services/composition-service/app/packer/lenses.py:247-248 (_arc_position — calls StructureRepo.span() DIRECTLY at lenses.py:322, not via the tool); plus tests. Zero agent/FE/contract consumers. The two doors to change: services/composition-service/app/mcp/server.py:4255 and services/composition-service/app/routers/arc.py:455. Stale description to fix: services/composition-service/app/mcp/server.py:4226-4227. Correct block source: services/composition-service/app/db/repositories/structure.py:244-327 (derived_blocks -> {span:{from_order,to_order}|None, is_contiguous, chapter_count, first_story_order}); list route precedent: services/composition-service/app/routers/arc.py:428-433. No output schema pinned: contracts/tool-liveness.json:182.

### Q-32-AI1-ADDRESSING
AFFIRM AI-1 as written. `arc-inspector` ships as a palette-openable, enum-listed detail-pane-over-a-selection, exactly like `scene-inspector`. X-12 is REFUTED by the code and is superseded — do not build to it. This is not a taste call: the repo mechanically forbids X-12's shape (see evidence), so no PO escalation is warranted.

BUILDER INSTRUCTIONS (all 5 are required; skipping any one reds a test):
1. `frontend/src/features/studio/panels/catalog.ts` — add ONE row, NO `hiddenFromPalette`, WITH a category (both are enforced): `{ id: 'arc-inspector', component: ArcInspectorPanel, titleKey: 'panels.arc-inspector.title', descKey: 'panels.arc-inspector.desc', category: 'editor', guideBodyKey: 'panels.arc-inspector.guideBody' }`. Place it next to the `scene-inspector` row (catalog.ts:185).
2. `services/chat-service/app/services/frontend_tools.py:402` — append `"arc-inspector"` to the `panel_id` enum, AND append its one-clause gloss to the description prose (~:448, next to `plan-hub`). Then regenerate the contract: `WRITE_FRONTEND_CONTRACT=1 pytest` in chat-service. Steps 1 and 2 must land in the SAME commit — `panelCatalogContract.test.ts:32` asserts `enum set == OPENABLE_STUDIO_PANELS` by exact set equality, so either half alone is a red.
3. DO NOT add a `params` arg to `ui_open_studio_panel`. This also answers the params half of plan-30 §11's open PO decision (a): NO. Reason: `host.openPanel(panelId, { params })` (StudioHostProvider.tsx:52) already carries params for the IN-STUDIO deep-link path (studioLinks.ts:80), and the agent path lands on the panel via the bus (`resource_ref` → `bus.publish({type:'arc', arcId})`), so extending the tool schema buys nothing and would drag CLOSED_SET_ARGS + both resolvers into the change for no capability.
4. Subject resolution, in this exact precedence, in `ArcInspectorPanel.tsx` / `useArcInspector.ts`: (1) `props.params.arcId` (in-studio deep-link, e.g. PlanDrawer's arc variant); (2) `bus.activeArcId` — add `activeArcId?: string` to both the snapshot and the event union in `frontend/src/features/studio/host/types.ts` (mirror `activeSceneId` at types.ts:37/74 and the `case 'scene'` at :97-98 with `case 'arc': return { ...base, activeArcId: e.arcId }`); (3) if neither yields an id, render an in-panel arc PICKER (not scene-inspector's dead empty-state string) — reuse `getArcs(bookId, token)` from `frontend/src/features/plan-hub/api.ts:20` (DOCK-2: reuse, do not fork a new arcs fetch) and select-on-click by publishing the `arc` bus event.
5. Tests (Definition of Done for the slice): (a) `panelCatalogContract.test.ts` stays green (proves enum↔catalog parity); (b) a new `ArcInspectorPanel.test.tsx` asserting all three precedence tiers — params wins over bus; bus alone loads the arc; neither ⇒ the picker renders (`data-testid="arc-inspector-picker"`) and clicking an arc loads it. Tier (3)'s test is the anti-dead-panel guard that makes the bare-id enum open honest.

Note for the PO (veto-able default): the only place AI-1 goes BEYOND shipped precedent is the picker — `scene-inspector` shows a passive "Select a scene…" string instead. I am keeping the picker because the bare-id agent/palette open is precisely the path that would otherwise land on a dead panel, and the list route already exists, so it costs one hook.

*Evidence:* frontend/src/features/studio/panels/__tests__/panelCatalogContract.test.ts:32-35 — `expect([...enumIds].sort()).toEqual(OPENABLE_STUDIO_PANELS.map(p=>p.id).sort())` makes X-12's "hiddenFromPalette but agent-openable" shape mechanically impossible, and plan-30 §0 PO-3 (line 21) requires this very test green. X-12's premise is refuted by the shipped twin: `scene-inspector` is subject-dependent yet IS in the enum (services/chat-service/app/services/frontend_tools.py:402) and IS palette-openable (frontend/src/features/studio/panels/catalog.ts:185), resolving its subject from the bus (frontend/src/features/studio/panels/useSceneInspector.ts:24) with an empty state at SceneInspectorPanel.tsx:93-97 — no tool `params` arg anywhere. In-studio params already flow without a schema change: StudioHostProvider.tsx:52 + studioLinks.ts:80, while the agent interceptor opens by bare id at StudioHostProvider.tsx:121. Picker source already exists: frontend/src/features/plan-hub/api.ts:20 `getArcs`.

### Q-32-AI2-CASCADE-OWN-VS-INHERITED
AI-2 stands as LOCKED, but it is NOT implementable from today's payload — the FE cannot name the source ancestor. Build a BE provenance sidecar (additive, both doors), then render off it. NO new table, NO migration, NO settings.

**BE — slice M1 (additive, ~40 LOC, zero contract break):**
1. `services/composition-service/app/db/repositories/structure.py` — add ONE method next to the other resolvers (after `resolve_roster_bindings`, line 616):
   `async def resolve_provenance(self, node_id: UUID) -> dict[str, Any]` — walks the SAME `ancestor_chain(node_id)` (structure.py:568) and applies the SAME root→leaf shadow rule as `_merge_by` (structure.py:586-597). Returns:
   `{"tracks": {<key>: {"node_id","title","kind","is_own","shadows_node_id","shadows_title"}}, "roster": {<key>: {…}}, "roster_bindings": {<role_key>: {…}}}`
   where `is_own = (winner node_id == node_id)`; `shadows_*` is populated when the winner overwrote an ancestor entry with the same key (⇒ the FE can offer "Revert to inherited"), else null. Entries whose key is MISSING or "" get NO provenance row (they are AI-3's un-shadowable garbage — see FE rule 4).
   🔴 **Do NOT add provenance keys INTO the entry dicts.** `resolve_tracks` output feeds `arc_apply.py:563` (tracks → `threads`) and `packer/lenses.py:284` (→ the generation prompt), and PATCH round-trips the array back to jsonb — an injected `_source_node_id` would poison prompts AND persist into the DB. It is a SIBLING MAP, keyed by key, never a field on the entry.
2. Wire it into BOTH doors (spec 32's both-doors rule): `routers/arc.py:450-454` → `out["resolved"]["provenance"] = await structures.resolve_provenance(node.id)`, AND `mcp/server.py:4251` (`composition_arc_get`) → the identical line. One of the two alone is an INVERSE gap.
3. Test (composition pytest): build saga→arc→sub-arc with track key `"K"` on the saga only ⇒ `provenance.tracks["K"].is_own is False` and `.title == <saga title>`; then set `"K"` on the sub-arc ⇒ `is_own True`, `shadows_title == <saga title>`, and `len(resolved.tracks) == 1` (shadowed, not doubled). Plus an anti-leak assert: `all("node_id" not in t and "is_own" not in t for t in resolved["tracks"])` — pins that the entries stay clean for arc_apply/lenses.

**FE — slice M2 (read) + M3 (the write), Arc Inspector panel:**
1. Each of the 3 sections (Tracks / Roster / Roster bindings) iterates `resolved.<x>` (the EFFECTIVE set) and looks each key up in `resolved.provenance.<x>` — the FE NEVER re-merges the cascade and never diffs key-sets itself.
2. `is_own === true` ⇒ editable in place (normal inline edit → PATCH).
3. `is_own === false` ⇒ **greyed, read-only, no input focusable**, with a badge reading `Inherited from "<provenance.title>"` and exactly ONE action: **[Override here]**. It deep-clones the resolved entry into `node.tracks` (same `key` ⇒ it shadows) and PATCHes the FULL own array (`If-Match: version`, chained per §8's write-serialization rule) — because `update()` is a whole-array replace (structure.py:369-372). The confirm/toast SAYS SO verbatim: *"Overridden here. This arc now has its own copy of \"<key>\" — it no longer follows \"<ancestor title>\"."*
4. An own entry with `shadows_node_id != null` renders a second action **[Revert to inherited]** — removes it from own `tracks` and PATCHes the array; the row then re-renders as inherited. (This is the escape hatch from an accidental fork; without it the fork is one-way.)
5. An entry with a missing/empty `key` (no provenance row) renders read-only with the AI-3 inline warning *"This entry has no key — it cannot be overridden or shadowed. Add a key to edit it."* Do not offer Override on it.
6. The section header counts `resolved.<x>.length` — the EFFECTIVE set, i.e. exactly what `gather_arc` injects (NOT the own array's length, NOT own+inherited double-counted). Sub-caption: `N effective · M own · K inherited`.

**Default I am picking (veto-able):** the provenance sidecar lives under `resolved.provenance` (not as a top-level `provenance` key, not inlined on entries) so that everything the cascade produces stays under one roof and the existing `resolved.tracks|roster|roster_bindings` contract is byte-identical for every current consumer (arc_apply, lenses, pack, the MCP tool) — a purely additive key, so no test/tool anywhere reds.

*Evidence:* services/composition-service/app/routers/arc.py:450-454 (`out["resolved"] = {tracks/roster/roster_bindings}` — no provenance) · services/composition-service/app/db/repositories/structure.py:586-597 `_merge_by` (returns bare entry dicts, `merged[k] = it`, no source marker) + 599-616 `resolve_tracks/roster/roster_bindings` + 568 `ancestor_chain` · services/composition-service/app/db/repositories/structure.py:369-372 (`_JSONB_UPDATE_COLUMNS` → `tracks = $n::jsonb` — PATCH is a WHOLE-ARRAY replace, so an "edit" of an inherited track forks a copy exactly as AI-2 predicts) · services/composition-service/app/engine/arc_apply.py:563 + app/packer/lenses.py:284 (resolve_tracks output flows into `threads` and into the prompt ⇒ provenance must be a sidecar, never a key on the entry) · services/composition-service/app/mcp/server.py:4251 (`composition_arc_get` duplicates the same `resolved` block — the second door)

### Q-32-OQ3-DELETE-BLAST-RADIUS-COUNT
DO BOTH — they answer different moments, and the spec's "second consumer" trigger is ALREADY met in code (StructureRepo.archive() has exactly two callers: the REST route AND the MCP tool composition_arc_delete, which is auto-applied for the agent and has no tree to derive from).

1) BE — `services/composition-service/app/db/repositories/structure.py:404` `async def archive(self, node_id) -> None`: change the signature to `-> list[UUID]`. Inside, append `RETURNING id` to the existing recursive-CTE UPDATE and swap `await c.execute(...)` for `rows = await c.fetch(...)`; `return [r["id"] for r in rows]`. Do NOT touch the CTE itself (it already walks the subtree and threads book_id). Leave `restore()` alone.

2) BE — `services/composition-service/app/routers/arc.py:517-525` `delete_arc`: `ids = await structures.archive(node.id)` → return `{"id": str(node.id), "archived": True, "archived_ids": [str(i) for i in ids], "archived_count": len(ids)}`. Purely ADDITIVE (no test asserts exact dict equality on this route — the `r.json() == {...}` equality test at tests/unit/test_motif_router.py:248 is the motif route, not arcs).

3) BE — `services/composition-service/app/mcp/server.py:4418-4429` `composition_arc_delete`: same two additive keys (`archived_ids`, `archived_count`) alongside the existing `node_id`/`archived`/`_meta.undo_hint`. This is the OUT-5 fix that actually matters: the agent cannot client-derive, so today it says "archived the arc" while having silently archived N sub-arcs. Update the tool description to say it reports the archived subtree ids.

4) FE (M3 archive confirm) — STILL client-derive the descendant count from the shell tree the panel already holds, because the confirm renders BEFORE the call and the response does not exist yet: `Archive "Book One" and its 2 sub-arcs?` plus OQ-8's honest stranding line ("N chapters stay bound to the archived arc; unassign them first"). Then use the RESPONSE's `archived_count` in the post-action toast/undo affordance ("Archived 3 arcs — Undo"), NOT the client estimate — so a concurrent write that changed the subtree is reported truthfully.

5) Tests (all three, none optional): (a) integration DB test that `archive(saga_id)` returns the ids of the saga + both sub-arcs; (b) unit test on `DELETE /arcs/{id}` asserting `archived_count == 3` and `archived_ids` contains the two descendants; (c) FE test that the confirm string is derived from the tree (client-derive) while the toast reads `archived_count` from the response.

Default the PO can veto: this is a ~10-line additive backend change, no contract break, no migration. If they'd rather keep the route frozen, the FE half (4) still stands on its own — but the agent-facing silent blast radius stays.

*Evidence:* services/composition-service/app/db/repositories/structure.py:404 (`async def archive(...) -> None` — the recursive-CTE subtree UPDATE returns nothing); its ONLY two callers are services/composition-service/app/routers/arc.py:524 (`await structures.archive(node.id)` → `{"id":…, "archived": True}` at :525) and services/composition-service/app/mcp/server.py:4425 (`composition_arc_delete` → `{"node_id":…, "archived": True}` at :4426-4429). The MCP tool IS the "second consumer" the spec (docs/specs/2026-07-01-writing-studio/32_arc_inspector.md:521) said would justify `archived_ids[]`, and it holds no tree to derive from.

### Q-32-OQ1-ARC-SUGGEST
CONFIRM THE SPEC'S PICK: Wave 2's `arc-inspector` does NOT ship a "Suggest an arc" button. Builder instructions, exactly:

(1) WAVE 2 (spec 32) — reserve the slot, ship nothing behind it. In the new `ArcInspectorPanel` header row (the one that already carries the arc picker + `+ New arc` / `+ New saga` per spec 32 §206), render a right-aligned actions container `<div className="ml-auto flex items-center gap-1" data-testid="arc-inspector-header-actions">` containing ONLY the Wave-2 actions. Do not add any suggest button, any `composition_arc_suggest` call, any `POST /v1/ai/tools/execute` bridge call, and do NOT add `'composition_arc_suggest'` to `FE_BRIDGE_TOOL_ALLOWLIST` (`services/api-gateway-bff/src/**/tools.controller.ts:24-30`). Wave 2's panel stays single-service (composition REST only) and needs no cross-service live-smoke.

(2) WAVE 4 (spec 34 / BE-7a) — the button lands WITH its backend, and it lands as REST, not via the bridge:
  - BE: add `POST /v1/composition/arc-templates/suggest`, body `{project_id, premise?, genre?, limit=5, detail="full"|"summary"}` — mirroring `composition_arc_suggest` (`services/composition-service/app/mcp/server.py:2287-2298`) field-for-field, incl. the `limit=5` default and the `Literal["summary","full"]` enum. Handler: `_book_or_deny(..., GrantLevel.VIEW)` then `MotifRetriever.retrieve_arcs(user_id, book_id, project_id, premise, genre, limit)` + `apply_response_contract`, i.e. the same body the tool runs. Retriever is already wired (`app/deps.py:205`).
  - FE: mount the "Suggest an arc" button into the reserved `arc-inspector-header-actions` slot; render the ranked candidates + `match_reason` breakdown the engine already returns.

(3) CORRECTION TO THE SPEC'S RATIONALE (keep the answer, fix the reason before it propagates into spec 34): `composition_arc_suggest` is `require_meta("R", "book")` (`server.py:2279`) — a Tier-R **read**, NOT a propose→confirm tool. It does not "drag the propose→confirm cost spine" anywhere; the only real blockers are (a) it has no REST route and (b) it is absent from `FE_BRIDGE_TOOL_ALLOWLIST`, so the browser fails closed. And per plan 30 BE-6 (line 299) it must NEVER be added to that allowlist — that surface's own contract is spend-adjacent propose/poll ("NOTHING here writes or deletes"), and a free read belongs on REST. Rewrite spec 32's OQ-1 answer cell to say "no REST route + not in the allowlist ⇒ 403, fails closed" and drop the "paid / propose→confirm" clause.

Also note the ownership de-dupe is already sealed upstream: plan 30 line 299 assigns arc-suggest to **BE-7 / spec 34 alone** (BE-6 is motif-suggest only), and kills the wrong `GET /books/{bid}/arcs/suggest?limit=10` shape — the tool takes `project_id`, not a `book_id` path segment. Builder must not resurrect that route shape.

Default I am picking (veto-able): reserve the header slot with a `data-testid` container in Wave 2 rather than leaving the header untouched, so Wave 4 is a pure additive mount with no header re-layout.

*Evidence:* services/api-gateway-bff/src/**/tools.controller.ts:24-30 — `FE_BRIDGE_TOOL_ALLOWLIST` = {composition_conformance_run, composition_motif_mine, composition_motif_adopt, composition_arc_import_analyze, composition_get_mine_job}; `composition_arc_suggest` is NOT a member ⇒ 403 fail-closed. services/composition-service/app/mcp/server.py:2271-2298 — tool exists, `require_meta("R","book")` (a READ, not a propose), args `(project_id, premise?, genre?, limit=5, detail)`; no REST route exists (composition has no `app/api/` handler for it). docs/specs/2026-07-01-writing-studio/30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md:299-300 — BE-6 de-dupe ("Arc-suggest belongs to BE-7 / spec 34 alone… REST, not the bridge") and BE-7 contract `POST /v1/composition/arc-templates/suggest {project_id, premise?, genre?, limit=5, detail}`. docs/specs/2026-07-01-writing-studio/32_arc_inspector.md:519 — OQ-1 as written.

### Q-32-ARCEFFECTS-ONE-HOME
CONFIRMED as stated — ONE HOME, with two corrections the builder MUST apply (the spec's own query key is a no-op).

BUILD (Wave 2, spec 32 §6 step 8):

1) NEW FILE `frontend/src/features/studio/agent/handlers/arcEffects.ts` — model it byte-for-byte on `knowledgeEffects.ts` (exported pattern const + module-level `registered` guard + `_reset*` test hook):

```ts
import { registerEffectHandler, type EffectContext } from '../effectRegistry';

// Reads excluded — same rationale as GLOSSARY_WRITE_PATTERN (glossaryEffects.ts:18) and
// KNOWLEDGE_WRITE_PATTERN (knowledgeEffects.ts:16): a chatty read loop must not thrash the cache.
// Excluded = the four require_meta("R", …) tools: list/get/suggest/template_drift (server.py:4192,
// 4221, 2272, 4673). Covered writes: create, update, delete, restore, move, assign_chapters, apply,
// extract_template (server.py:4290-4628) + import_analyze (a W PROPOSE; harmless refresh).
export const ARC_WRITE_PATTERN = /^composition_arc_(?!list|get|suggest|template_drift)/;

let registered = false;

export function arcEffect(ctx: EffectContext): void {
  // Prefix-invalidate the WHOLE plan-hub family in one call — it covers ['plan-hub','arcs',bookId]
  // (usePlanHub.ts:34 / usePlanNavigator.ts:77 / usePlanNode.ts:67), ['plan-hub','node',id]
  // (usePlanNode.ts:60) and overlay/scene-links/conformance (usePlanHub.ts:39-51). This is what
  // refreshes the OCC `version` the inspector saves against (the 412-against-an-unseen-version bug).
  ctx.queryClient.invalidateQueries({ queryKey: ['plan-hub'] });
  // ⬇ Wave 4 (spec 34 §6 step 8) EXTENDS THIS BODY — add ['composition','arc-templates'] +
  //   ['composition','arc-template'] + ['composition','arc-conformance'] here. NEVER a 2nd
  //   registerEffectHandler for an overlapping composition_arc_* pattern.
}

export function registerArcEffectHandlers(): void {
  if (registered) return; registered = true;
  registerEffectHandler(ARC_WRITE_PATTERN, arcEffect);
}
export function _resetArcEffectHandlers(): void { registered = false; }
```

2) CORRECTION A — do NOT invalidate `['composition','arcs', bookId]`. That key does not exist anywhere in the FE (grep is empty); invalidating it is a silent no-op. Use the `['plan-hub']` prefix above. BINDING COROLLARY for spec 32 step 1c: `useArcInspector.ts` MUST key its arc detail read under the `['plan-hub', …]` prefix — reuse `['plan-hub','arcs',bookId]` (shell) + `['plan-hub','node', arcId]` exactly as `usePlanNode.ts:60,67` does (DOCK-2, one fetch). If a builder invents any other key, they must add it to `arcEffect`'s invalidation set in the SAME commit. DoD: "the key arcEffect invalidates == the key the inspector reads", asserted by test.

3) CORRECTION B — do NOT import `unwrapToolResult`. This handler needs no id from the payload (bookId + prefix invalidation covers everything), so the import would be unused (lint error). The rule stands conditionally: IF Wave 4's extended body needs an id (e.g. `arcTemplateId` for `['composition','arc-template', arcId]`, useArcTimeline.ts:40), it MUST read it via `unwrapToolResult` (resultEnvelope.ts:8), never a bare `ctx.result.x` — that is the M-E live bug class.

4) BARREL — `useStudioEffectReconciler.ts`: add `import { registerArcEffectHandlers } from './handlers/arcEffects';` beside lines 18-21, and call it in the `useEffect` at lines 34-39. Delete the now-false comment at lines 7-10 (it asserts which families "DON'T need a handler").

5) TEST — NEW `frontend/src/features/studio/agent/__tests__/arcEffects.test.ts`, mirroring `knowledgeEffects.test.ts`. Three assertions, the third is the machine-check of the ONE HOME rule:
   a. ARC_WRITE_PATTERN matches create/update/delete/restore/move/assign_chapters/apply/extract_template; does NOT match composition_arc_list / _get / _suggest / _template_drift.
   b. After clearEffectHandlers() + _resetArcEffectHandlers() + registerArcEffectHandlers(), `runEffectHandlers({tool:'composition_arc_update', …})` calls invalidateQueries with `['plan-hub']`.
   c. DOUBLE-FIRE GUARD: register bookEffects + compositionEffects + arcEffects together, then assert `matchEffectHandlers('composition_arc_update').length === 1`. This is the only thing that can catch a future second home.

6) KNOWN UNCOVERED EDGE (do not silently drop): `composition_arc_import_analyze` returns only a `confirm_token`; its actual write dispatches through the shared `confirm_action` tool, so NO `composition_arc_*` name reaches the reconciler for it — identical to the class translationEffects.ts:1-8 already recorded for resume/retry. arcEffects cannot close it. Write the defer row: **D-ARC-CONFIRM-EFFECT** — Lane-B has no handler for the confirm_action-dispatched arc-import write; the 拆文 panel must refresh off job completion instead. Gate 3 (naturally-next-phase) · target Wave 4 (spec 34).

PO veto note: plan 30 §8.0b says "one broad `/^composition_arc_/` registration" — the load-bearing word is ONE (one file, one pattern), which this honours. I narrowed it with a read-exclusion lookahead to match the established precedent in glossaryEffects.ts:18 / knowledgeEffects.ts:16. If the PO prefers the literal broad regex, the only cost is a plan-hub refetch on every agent arc READ; everything else in this instruction is unchanged.

*Evidence:* frontend/src/features/studio/agent/effectRegistry.ts:45-53 (matchEffectHandlers returns EVERY match; runEffectHandlers awaits ALL ⇒ two registrations double-fire — spec premise confirmed) · bookEffects.ts:59-62 (registers /^composition_.*(prose|draft)/ + /^composition_(outline_node|scene_link)_/ — NEITHER matches composition_arc_*, so no collision at HEAD; arcEffects will be sole matcher) · usePlanHub.ts:34 + usePlanNode.ts:60,67 + usePlanNavigator.ts:77 (the arcs/node keys are ['plan-hub',…]; grep for ['composition','arcs'] returns ZERO hits ⇒ the spec's key is a silent no-op) · glossaryEffects.ts:18 + knowledgeEffects.ts:16-17 (read-exclusion precedent) · resultEnvelope.ts:8 (unwrapToolResult) · useStudioEffectReconciler.ts:18-21,34-39 (the barrel) + :7-10 (the now-false comment to delete) · services/composition-service/app/mcp/server.py:2272,3055,4192,4221,4290,4348,4405,4433,4473,4515,4578,4628,4673 (13 composition_arc_* tools; list/get/suggest/template_drift are require_meta("R")) · server.py:3070-3073 (import_analyze returns confirm_token only — real write dispatches via confirm_action) · docs/specs/2026-07-01-writing-studio/30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md:605-614 (§8.0b — ONE FILE PER DOMAIN; arcEffects.ts owned by spec 32, Wave 2 creates / Wave 4 extends)

### Q-32-OQ5-STATUS-DERIVED
SHIP HAND-SET. `structure_node.status` stays an author-written label. Do NOT derive, auto-compute, or "suggest" it from member chapters — now or later — and do not add a client-side derivation either.

Builder instruction (M3, arc-inspector header):
1. Render a `<select data-testid="arc-status-select">` with EXACTLY the 4 closed-set values from `NodeStatus` (`services/composition-service/app/db/models.py:38`): `empty|outline|drafting|done`. Its value comes from the arc row returned by `GET /v1/composition/arcs/{node_id}` (`app/routers/arc.py:438`) — from nothing else.
2. On change, commit instantly via `PATCH /v1/composition/arcs/{node_id}` body `{status}` with `If-Match: <version>`, going through the serialized-write chain (mirror `frontend/src/features/composition/panels/useSceneInspector.ts:43-45`) and the 412 → "changed elsewhere — reloaded" + `setQueryData` re-seed handling (mirror `frontend/src/features/plan-hub/hooks/usePlanNodeWrites.ts:55-78`). `status` is already in the server's patchable set (`app/db/repositories/structure.py:53`), so zero backend work.
3. The DERIVED/actual signals stay SEPARATE and adjacent — never fused into `status`: the derived `span` (chapter min/max story_order) and the conformance badge `ConformanceStatus.arcs[].{dirty, dirty_reasons, stale_chapters}` from `panels/useConformanceStatus.ts`. This is PH16's two-chip desired-vs-actual header, applied one layer up.
4. Put a one-line comment at the select: `// OQ-5 (DECIDED): status is the AUTHOR'S INTENT, never derived from member chapters — see models.py:180 (PH16). Actual state = span + conformance badge, rendered separately.`
5. Regression guard (the point of the whole item): add a backend test asserting that assigning/unassigning chapters to an arc (`POST /books/{bid}/arcs/assign-chapters`) leaves `structure_node.status` byte-identical, and an FE unit test asserting the select's value is read from the arc row only (not computed from `chapters`/conformance). That test is what stops a future agent from "helpfully" auto-computing it.

Rationale (why this is not a guess): (a) no engine consumer — `gather_arc`, the ONLY path `structure_node` takes into a prompt, resolves title/goal/tracks/roster_bindings/span/open_promises and never reads `status`; the one `status == "done"` branch in that file is on `outline_node`, a different table. (b) The identical question is ALREADY SEALED in code one layer down: `models.py:178-183` — "Distinct from `status`, which is the AUTHOR'S INTENT: PH16 locks a two-chip desired-vs-actual header, and fusing them would mean marking a scene 'done' makes an UNWRITTEN scene render as written." Deriving the arc's status commits exactly that banned fusion, and would also make it impossible for an author to mark an arc `drafting` before any chapter is assigned. Contradicts no §0 sealed PO decision (PO-1..4 are about GUI surfaces, tool naming, and spec-first sequencing).

*Evidence:* services/composition-service/app/db/models.py:178-183 (PH16: status = AUTHOR'S INTENT; actual state is a separate maintained field; "fusing them" is the named bug) · models.py:38 (`NodeStatus = Literal["empty","outline","drafting","done"]`) · services/composition-service/app/packer/lenses.py:257-360 (`gather_arc` — the only prompt path for structure_node; never reads `status`; the `n.status == "done"` at lenses.py:230 is `outline_node` inside `gather_structural`) · services/composition-service/app/db/repositories/structure.py:53 (`_UPDATABLE_COLUMNS` includes `status` alongside title/summary/goal — already author-writable) · services/composition-service/app/engine/arc_apply.py:465 (only writes status="outline" on new outline nodes; no derivation from children anywhere)

### Q-32-OQ8-ARCHIVE-STRANDS-CHAPTERS
**archive() does NOT cascade an unassign. Ever. Close the cascade question as CONSCIOUS WON'T-FIX (gate #5) — do not carry it as an open defer row.**

WHY (settled by code, not taste): `restore()` (structure.py:449) is archive's verified inverse, and it is lossless on membership TODAY *precisely because* `archive()` leaves `outline_node.structure_node_id` alone. A cascade would NULL the binding with no lift map to rebind from, so restore could never put the chapters back — archive becomes an irreversible destructive write on user rows (PO policy §3's stop class) and breaks the archive/restore pair the FE already asserts (`PlanDrawerEdit.test.tsx:158,165`). The binding stays. The escape hatch is BE-A3.

ALSO REJECTED (do not "helpfully" do this instead): a read-side fix making `?unassigned=true` mean `structure_node_id IS NULL OR arc is_archived`. It silently redefines 24-PH21's named axis, shows a chapter in the tray *while it is still bound*, and makes it vanish again on restore. `list_unassigned_chapters` (outline.py:853) stays literally `structure_node_id IS NULL`.

BUILDER INSTRUCTIONS — 4 concrete items:

(1) M3 — ARCHIVE CONFIRM COPY (FE only; NO backend work needed). The number is already on the wire: `derived_blocks()` (structure.py:244) computes `chapter_count` per node and `GET /books/{bid}/arcs` already returns it (arc.py:428). Read `chapter_count` from the **LIVE** arc row *before* the archive call. Copy, verbatim:
  • N > 0 → title "Archive this arc?" / body: "{N} chapters stay bound to this arc. Archiving does NOT return them to the Unassigned tray — they will appear in neither the arc lane nor the tray until you unassign them. Restoring the arc brings it back with its chapters exactly as they are now." / buttons: "Archive anyway" · "Cancel".
  • N = 0 → "Archive this arc? You can restore it later via Show archived."
  The copy MUST NOT contain any pool-return promise ("chapters return to the pool", "chapters are freed", etc.) — no writer performs it.

(2) M3 — FALSE-ZERO GUARD (found while adjudicating; fix in the same slice, it is one line of FE logic). `arc.py:429` serves `empty = {"span": None, "is_contiguous": True, "chapter_count": 0, ...}` for archived nodes, because `derived_blocks()` is deliberately live-only. So an archived arc reports **chapter_count 0 while N chapters are still bound**. The inspector/drawer MUST gate the "—" render on `node.is_archived`, NOT on falsiness (`chapter-blocks-null-nontext-coalesce`; §3.4 already says this — this is the concrete site). Never print "0 chapters" for an archived arc.

(3) M4 — BE-A3 unassign, both doors, exactly as 32 §5 BE-A3 specs it: `ArcAssignChapters.structure_node_id: UUID | None` (arc.py:363) AND `_ArcAssignChaptersArgs.structure_node_id: str | None` (server.py:4508 — apply the 3-schema-source FastMCP caveat, update all 3). In `StructureRepo.assign_chapters` (structure.py:540): when `structure_node_id is None` → `SET structure_node_id = NULL`, DROP the `EXISTS` guard on that branch only, KEEP the `book_id` + `kind='chapter' AND NOT is_archived` guards. Then in M4 the archive confirm gains a secondary button "Unassign {N} chapters first" (M3 ships copy-only; the button is gated on BE-A3 existing — that is the M3/M4 slice boundary).

(4) PIN THE LAW WITH A TEST (this is what converts the won't-fix into an enforced contract so a future agent cannot "improve" archive into a cascade): add a BE test in the composition suite asserting that after `POST /arcs/{id}` archive (`arc.py:516` delete_arc → `structures.archive`), every member chapter's `outline_node.structure_node_id` is STILL the archived arc's id (non-null), and that the chapter does NOT appear in `?unassigned=true`. Name it for the contract, e.g. `test_archive_does_not_cascade_unassign_restore_stays_lossless`. Add an FE unit test asserting the confirm copy renders the live `chapter_count` and contains no pool-return promise.

DEFER-ROW DISPOSITION: `D-ARC-ARCHIVE-CHAPTER-STRANDING` is CLOSED as gate #5 (conscious won't-fix), not carried forward. Revisit ONLY if a future spec introduces a persisted arc-membership lift map that would make restore able to rebind — absent that, the cascade is strictly a data-loss regression.

PO VETO NOTE: the default I picked is "keep the binding, ship honest copy + BE-A3" — which is what spec 32 OQ-8 already proposed as the ship-now. The only thing I added beyond it is *closing* the cascade question rather than leaving it open, plus the false-zero guard (2) and the pinning test (4). If the PO wants archive to cascade, that must come with a membership-restore table first; veto here would be a schema decision, not a copy tweak.

*Evidence:* services/composition-service/app/db/repositories/structure.py:404 (`archive()` — recursive CTE flips `is_archived` on the `structure_node` subtree ONLY; `outline_node` never touched) · structure.py:449 (`restore()` — the inverse; lossless on membership *because* the binding survives, so a cascade would break it irrecoverably) · structure.py:244-257 (`derived_blocks()` — `chapter_count` per node, ONE query, "Returns a row ONLY for keys of LIVE (non-archived) nodes") · services/composition-service/app/routers/arc.py:428-429 (LIST already serves `chapter_count`; `empty = {..."chapter_count": 0...}` is the archived-node fallback = the false zero) · arc.py:516-525 (`delete_arc` → `structures.archive(node.id)`) · services/composition-service/app/db/repositories/outline.py:849,853 (`list_unassigned_chapters` = `structure_node_id IS NULL`) · arc.py:363 (`ArcAssignChapters.structure_node_id: UUID` non-null) + structure.py:540-563 (`assign_chapters` `SET structure_node_id = $1` + EXISTS guard) + services/composition-service/app/mcp/server.py:4508 (`_ArcAssignChaptersArgs`) = the BE-A3 seam · frontend/src/features/plan-hub/components/__tests__/PlanDrawerEdit.test.tsx:158,165 (FE already asserts archive XOR restore — the pair a cascade would void)

### Q-32-OQ7-SUMMARY-ROSTER-NO-PACKER
Ship editors for all fields, but SPLIT the panel into two labelled groups and make the split MACHINE-CHECKED, not a prose warning (prose warnings rot; this repo's "checklist⇒test the effect" lesson applies).

1) ONE HOME FOR THE TRUTH. Create `frontend/src/features/arc-inspector/fieldClasses.ts`:
   `export const PROMPT_BEARING = ['title','goal','tracks','roster_bindings'] as const;`
   `export const REFERENCE_ONLY = ['summary','status','roster'] as const;`
   Every section header/badge in `ArcInspectorPanel.tsx` reads its badge from this module — no per-section literal. (Mirrors gather_arc, lenses.py:282-285.)

2) UI COPY (verbatim — do not paraphrase into a generation claim):
   - Badge on Title / Goal / Tracks / Cast bindings sections: "Reaches the prompt".
   - Badge on Summary + Status: "Reference only — not sent to the model." Summary create-form placeholder: "A note for you and the Plan Hub. Not sent to the model." (This kills the near-defect: the earlier draft + the mock's create form said summary reaches the prompt.)
   - Badge on the Roster (slot list) section: "Reference only — defines the roles that Cast bindings fill; read when extracting a template." NEVER "roster reaches the prompt" — `roster_bindings` does.
   - Goal editor, when the node is NOT a leaf (has children in the loaded tree): inline note "Only the leaf arc's goal reaches the prompt — this saga's goal is not injected." (lenses.py:303 takes chain[-1].goal.)

3) DoD #5 TESTS — exactly two pack-effect tests, one template test, ZERO for summary/status:
   - `services/composition-service/tests/unit/test_pack_arc.py` (extend; it already asserts 'Arc chain: …' at :189): add `test_arc_tracks_change_changes_prompt` and `test_roster_binding_renders_cast_bindings` (mirror the assertion shape at `tests/unit/test_plan_pass_checkpoint.py:257`, `assert "Cast bindings:" in frame`).
   - `roster` (slots): prove it against its REAL consumer — a slot added in the panel appears in the template from `extract_template_from_arc` (`arc_apply.py:564`), NOT against the packer.
   - `summary`/`status`: no pack-effect test. FE render test only.

4) THE ANTI-DRIFT GUARD (new, cheap, one test — this is what makes the copy stay honest): add to `test_pack_arc.py` a `test_gather_arc_reads_only_prompt_bearing_fields` that (a) spies the structure_repo and asserts `resolve_roster` is NEVER called during `gather_arc`, and (b) mutates only `summary` and `status` and asserts the returned arc frame string is byte-identical. If a future change starts injecting summary/roster, this test reds and forces the UI copy to be updated with it.

Default I am picking (veto-able): all seven fields keep an editor — none is dropped. The fix is labelling + test selection, exactly as spec 32's own OQ-7 disposition states; this decision just converts that prose into a constant + a guard test.

*Evidence:* services/composition-service/app/packer/lenses.py:282-285 (gather_arc gathers ancestor_chain + resolve_tracks + resolve_roster_bindings — resolve_roster absent); lenses.py:303 (goal = chain[-1].goal, leaf only); lenses.py:337-344 ("Cast bindings:" from roster_bindings); services/composition-service/app/engine/arc_apply.py:564 (the only engine caller of resolve_roster, via extract_template_from_arc); app/routers/arc.py:452 + app/mcp/server.py:4252 (resolve_roster only for the GET-enrichment payload); grep confirms structure_node.summary/.status have no packer/engine reader (structure.py:723's status filter is the promise ledger's, not the node's); existing assertions to mirror: tests/unit/test_pack_arc.py:189, tests/unit/test_plan_pass_checkpoint.py:257

### Q-32-NO-COST-GATE
CONFIRMED BY CODE — the arc-inspector panel ships with NO cost gate, and adding one is a defect. Builder instruction (three literal steps):

(1) BUILD THE PANEL AS PURE CRUD. Every arc-inspector action calls the existing deterministic REST routes in `services/composition-service/app/routers/arc.py`: `GET /books/{book_id}/arcs` (:413), `GET /arcs/{node_id}` (:438), `POST /books/{book_id}/arcs` (:466), `PATCH /arcs/{node_id}` (:489, OCC via `If-Match`), `DELETE /arcs/{node_id}` (:516), `POST /arcs/{node_id}/restore` (:528), `POST /arcs/{node_id}/move` (:540), `POST /books/{book_id}/arcs/assign-chapters` (:560). Each is grant-gated (`_gate_arc`/`_gate_book` → GrantLevel.EDIT), OCC'd, and contains ZERO token-mint / usage-precheck / LLM call — verified by grep (`confirm|token|spend|llm|estimate` in arc.py hits only the JWT bearer dep at :587). So: NO `ConfirmCard`, NO propose→confirm, NO `/estimate` fetch, NO spend preview, NO "this will cost $X" copy anywhere in the arc-inspector FE. Write the panel's mutations as direct fetch → optimistic/invalidate, Tier-A with Undo. If a reviewer asks "where is the cost gate for this panel?", the answer is "there is none by construction" — cite arc.py:466-582.

(2) THE ONE ESCAPE HATCH, PRE-WIRED. If a later wave adds an LLM-spending action to this panel (e.g. "suggest sub-arcs", "auto-fill tracks from prose"), it does NOT get a new route. It gets (a) a new descriptor constant in `services/composition-service/app/routers/actions.py` next to the existing block at :64-91, (b) an entry appended to `_ALL_DESCRIPTORS` (:96-100 — the closed allowlist that `/actions/confirm` checks at :251), (c) an `_execute_*` effect fn mirroring `_execute_generate` (:388), and (d) an MCP Tier-W propose tool that MINTS a confirm token and executes nothing. The FE then drives the EXISTING generic pair only: `GET /v1/composition/actions/preview?token=` → `POST /v1/composition/actions/confirm`. Precedent already in the allowlist: `composition.arc_import` — the one arc-adjacent Tier-W op — is descriptor-routed exactly this way, proving the spine already accommodates arc-domain paid actions with zero new routes.

(3) MAKE IT MECHANICAL, NOT ADVISORY (this is the anti-404 guard; add both to Wave 2's DoD). Test A (BE), `services/composition-service/tests/unit/test_mcp_actions.py`: assert no descriptor in `actions._ALL_DESCRIPTORS` matches `^composition\.arc_(create|update|delete|restore|move|assign)` — arc CRUD must never become confirm-gated. Test B (FE), a vitest over the new arc-inspector api module: assert every URL literal it issues matches `^/v1/composition/(books/[^/]+/arcs|arcs)` and that the module source contains NO `/estimate` and no `actions/` path other than the two generic ones. Test B is the one that would have caught the four routes that 404 in production today (plan-30 §3.3 line 152: `POST /v1/composition/actions/conformance_run/estimate` — a per-action estimate route that has never existed in actions.py). Do not make it five.

Rationale is sealed, not mine to re-open: plan-30 §8.1 (line 634) — "A panel drives them through the generic GET /actions/preview → POST /actions/confirm pair — never a per-action route"; and plan-30 BE-5 (line 298) already REFUTED a bespoke `regenerate-to-beat` route on exactly these grounds ("a per-action route for a Tier-W op — the exact §8.1 violation the two live 404s already committed").

*Evidence:* services/composition-service/app/routers/arc.py:466-582 (create/patch/delete/restore/move/assign-chapters — grant-gated + OCC'd deterministic CRUD; grep for `confirm|token|spend|llm|estimate` across the file returns only the JWT bearer dep at :587 → panel is $0 by construction) · services/composition-service/app/routers/actions.py:96-100 (`_ALL_DESCRIPTORS` closed Tier-W allowlist, enforced at :251 `if claims.descriptor not in _ALL_DESCRIPTORS`; contains `composition.arc_import` — an arc-domain paid op ALREADY on the generic spine — and no arc-CRUD descriptor) · services/composition-service/app/routers/actions.py:7-8 (the only two action routes that exist: `GET /v1/composition/actions/preview`, `POST /v1/composition/actions/confirm`) · docs/specs/2026-07-01-writing-studio/30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md:634 (§8.1 law) and :152 (the live `actions/conformance_run/estimate` 404) and :298 (BE-5 REFUTED — do not build a bespoke per-action route)

### Q-32-OQ4-FIND-REFERENCES-STALE-COPY
FIX THE COPY NOW (one line, in-file). Do NOT build the REST route. Do NOT leave the lie.

The spec's "leave it" is overridden on one point only: its stated reason was "do not fix the copy from the RUN-STATE alone." That caution is satisfied — the fix below is grounded in CODE, not in the RUN-STATE. The tool provably exists; the emptiness provably remains. Correct the REASON, keep the EMPTINESS.

WHICH FILE: frontend/src/features/plan-hub/components/PlanDrawer.tsx, lines 284-290 (the "References" Section inside the outline-node facets — NOT ArcFacets).

WHAT CHANGE — replace exactly this:

      <Section title="References" testid="plan-drawer-section-references">
        <EmptyFacet>
          Back-references (where else this node's entities appear) need
          <code className="mx-1">composition_find_references</code> — spec 28 AN-3, not built yet.
          The cast above is this node's own roster.
        </EmptyFacet>
      </Section>

with this:

      {/* The tool SHIPPED (composition-service/app/mcp/server.py:3867, EntityReferencesRepo). The old
          copy's "not built yet" was a live lie that talked users OUT of a feature they already have.
          What is missing is only the FE path: MCP-only, no REST route (plan-30 §5.2 G-DIAGNOSTICS),
          so this facet still cannot fetch. Wave 7 / spec 37 replaces this with the right-click
          backlinks LENS on an entity badge (plan-30 PO-1) — not a facet, not a panel. Until then an
          honest gap names its REAL blocker. */}
      <Section title="References" testid="plan-drawer-section-references">
        <EmptyFacet>
          Back-references (where else this node's entities appear) come from
          <code className="mx-1">composition_find_references</code> — the assistant can already run
          this for you; ask it in chat. It has no GUI surface yet, so this panel can't show them.
          The cast above is this node's own roster.
        </EmptyFacet>
      </Section>

WHICH TEST: none to add or change. frontend/src/features/plan-hub/components/__tests__/PlanDrawer.test.tsx:74 asserts only getByTestId('plan-drawer-section-references') — the testid is preserved, so the existing test stays green. Copy-only change, zero behavior change, zero risk. Run the existing PlanDrawer suite as the VERIFY evidence.

EXPLICITLY OUT OF SCOPE for spec 32 (do not do these):
- Do NOT add a REST route for entity backlinks. Wave 7 owns it (plan-30 BE table + spec 37), and PO-1 sealed the surface as a right-click lens on an entity badge, NOT a PlanDrawer facet. A route built here would be the wrong surface AND would collide: /works/{pid}/references is ALREADY TAKEN by the research shelf (services/composition-service/app/routers/references.py:79).
- Do NOT touch PlanDrawer.tsx:298 ("23-C3 arc-inspector not built yet") — that comment sits on ArcFacets, which spec 32 M5 DELETES outright.

DEFAULT NOTED FOR PO VETO: I chose "tell the user the assistant can run it" over a bare "not available." Rationale — the capability is live and reachable today via chat; copy that says "not built" is worse than an empty facet because it suppresses use of a shipped feature. If the PO would rather the drawer not advertise the agent path, cut that clause and keep the rest of the correction.

*Evidence:* TOOL EXISTS (kills "not built yet"): services/composition-service/app/mcp/server.py:3867 — @mcp_server.tool(name="composition_find_references"), handler at :3883, fully implemented over EntityReferencesRepo (8 sources, exact counts, E0 VIEW gate at _gate(tc, bid, GrantLevel.VIEW)). Repo: services/composition-service/app/db/repositories/entity_references.py:56.

NO REST ROUTE (keeps the facet empty): `grep -rn "EntityReferencesRepo" services/composition-service/app` returns hits ONLY in app/mcp/server.py and app/db/repositories/entity_references.py — no router consumes it. services/composition-service/app/routers/references.py:1 is a DIFFERENT concept ("the author's per-Work reference shelf", LOOM T3.6) and already owns /works/{project_id}/references (:79). Corroborated by plan-30 §5.2 G-DIAGNOSTICS: "no REST route for any of the three."

THE LIE: frontend/src/features/plan-hub/components/PlanDrawer.tsx:287 — "— spec 28 AN-3, not built yet."

SEALED CONSTRAINT (kills "build the route"): docs/specs/2026-07-01-writing-studio/30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md:19 (PO-1) — find_references is "a right-click lens on an entity badge — no new dock panel"; owned by Wave 7 (:444, :557, spec 37_issues_feed.md).

TEST-SAFE: frontend/src/features/plan-hub/components/__tests__/PlanDrawer.test.tsx:74 asserts the testid only, not the copy string.

SELF-INDICTING PRECEDENT: PlanDrawer.tsx:281-282 — the file's own comment says the previous stale copy ("loads in H4") "was simply false once H4 landed; an honest gap names its real blocker" — then repeats the mistake at :287.

### Q-32-PLANDRAWER-BOOKID-PROP
CONFIRMED and mechanical — do exactly this in M5, in `frontend/src/features/plan-hub/components/PlanDrawer.tsx` (one added prop + one pass-through, ~2 lines):

1. Add `bookId: string;` to `DrawerBody`'s inline prop type (currently PlanDrawer.tsx:360-374, which takes only view/overlay/onOpenRef/writes/chapters/onOpenInEditor) and destructure it in the signature.
2. At the `<DrawerBody …>` call site (PlanDrawer.tsx:445-452) add `bookId={bookId}` — `bookId` is already destructured from `PlanDrawerProps` in `PlanDrawer(...)` at :401, so it is in scope with no further plumbing.
3. The arc branch becomes:
   ```tsx
   if (view.kind === 'arc' || view.kind === 'saga') {
     if (!view.arcNode) return <Centered testid="plan-drawer-empty">Arc not found in the shell.</Centered>;
     return <ArcInspectorBody arcId={view.arcNode.id} bookId={bookId} embedded />;
   }
   ```
   `view.arcNode.id` is the arc id and the branch already narrows it non-null, so `selectedId` is NOT needed in `DrawerBody` — do not add it (a second prop carrying the same fact is the DA-10 smell the file's own comment at :44-46 calls out).

⚠ CORRECTION TO THE SPEC SNIPPET (32_arc_inspector.md:275) — do NOT pass `writes={writes}` into `ArcInspectorBody`. `PlanDrawer`'s `writes` (PlanDrawer.tsx:49-55) is the PH20 **outline-node** bundle: `edit(nodeId, version, patch: NodeEdit)` / `archive(nodeId)` / `restore(nodeId)`, keyed on `outline_node` ids with an `outline` patch shape. Arc CRUD is a different object, a different REST surface (`composition_arc_update/_delete/_restore`, OCC on `structure_node.version`), and a different error contract (STRUCTURE_VERSION_CONFLICT 412 carrying `current`). `ArcInspectorBody` OWNS its arc mutations internally via the arc api/hooks it already ships for the dock panel (§4 / files-table row 1b) — that is what makes it "one implementation, two hosts" (DOCK-2). Threading the outline `writes` in would fork the write path and would not typecheck against `NodeEdit`.

So `ArcInspectorBody`'s props are exactly `{ arcId: string; bookId: string; embedded?: boolean }` — the dock panel passes the id from its picker, the drawer passes it from `view.arcNode.id`, and `embedded` suppresses panel chrome + the picker. If a read-only host ever needs to disable editing, gate it inside `ArcInspectorBody` on the grant it already resolves, not on a host-supplied writes bundle.

Test that pins it (M5 DoD): in `PlanDrawer.test.tsx`, render `<PlanDrawer kind="arc" bookId="b1" selectedId="arc-1" …/>` with `writes` OMITTED, and assert the ArcInspectorBody mount receives `bookId="b1"` and `arcId="arc-1"` (spy/mock the module) — that both proves the thread and locks in that the embed does not depend on the outline `writes` prop. Plus the existing M5 gate: `grep -rn "plan-drawer-arc-gap" frontend/src` returns zero hits.

*Evidence:* frontend/src/features/plan-hub/components/PlanDrawer.tsx:35 (`bookId: string` on PlanDrawerProps) · :49-55 (`writes` = PH20 OUTLINE bundle: `edit(nodeId, version, patch: NodeEdit)`, not arc CRUD) · :360-374 (DrawerBody prop type — no `bookId`, no `selectedId`) · :391-393 (arc branch already guards `view.arcNode`, so `view.arcNode.id` is available) · :401 (`bookId` destructured in PlanDrawer) · :445-452 (the `<DrawerBody …>` call site to add `bookId={bookId}` to). Spec snippet under correction: docs/specs/2026-07-01-writing-studio/32_arc_inspector.md:275.

### Q-32-ARCLISTNODE-WIDENING
DO THE WIDENING — it is a bounded FE-only type change, no BE work (the "BE_PREREQ" label is wrong: the wire ALREADY carries all 20 fields; `list_arcs` returns `StructureNode.model_dump(mode="json")` + the derived block, and Pydantic emits every declared field, so nothing on the server changes).

Builder instructions (exact):

1. `frontend/src/features/plan-hub/types.ts:36-57` — extend `interface ArcListNode` with the 8 wire fields it currently omits, all REQUIRED (the server always emits them; `model_dump` has no `exclude_unset`), typed against `StructureNode` (services/composition-service/app/db/models.py:206-235):
   - `book_id: string;`
   - `created_by: string | null;`
   - `tracks: { key: string; label?: string }[];`            // wire: list[dict] [{key,label}]
   - `roster: { key: string; actant?: string; label?: string; constraints?: string[] }[];`  // [{key,actant,label,constraints[]}]
   - `roster_bindings: Record<string, string>;`              // {role_key: glossary_entity_id}
   - `is_archived: boolean;`
   - `created_at: string | null;`
   - `updated_at: string | null;`
   Keep the existing 12 + the 4-field derived block (span / first_story_order / is_contiguous / chapter_count) exactly as-is — the derived block is B1-only, NOT on `StructureNode`, and must stay. Leave `arc_template_id?`/`template_version?` optional as they are (do not churn them). Update the doc-comment above the interface: it currently says "Extra spec fields (goal/tracks/roster/…) ride along for the drawer" — replace with "full StructureNode wire shape + the B1 derived block (24 OQ-2)".

2. `frontend/src/features/plan-hub/components/PlanDrawer.tsx:305-310` — DELETE the lying cast. Replace
   `const extra = arc as ArcListNode & { tracks?: unknown; roster?: unknown };`
   `const rosterKeys = rosterKeysOf(extra.roster);` / `const trackKeys = rosterKeysOf(extra.tracks);`
   with `const rosterKeys = rosterKeysOf(arc.roster);` / `const trackKeys = rosterKeysOf(arc.tracks);`
   and delete the two-line "The wire carries tracks/roster … read them defensively" comment. `rosterKeysOf(roster: unknown)` may keep its `unknown` param (it is a defensive normalizer, not a type lie) — no other change needed.

3. `laneLayout`'s `ArcShellNode` and `planHubMappers.ts:42 toArcShellNode` are UNAFFECTED (structural subset projection) — do not touch them.

4. Test fixtures: the 4 factories that build a full `ArcListNode` base object must gain the 8 keys or they will red on typecheck — `components/__tests__/PlanDrawer.test.tsx:36`, `components/__tests__/PlanNavigatorRail.test.tsx:16`, `hooks/__tests__/planHubMappers.test.ts:13`, `hooks/__tests__/usePlanMoves.test.tsx`. Give them defaults (`book_id: 'b1'`, `created_by: null`, `tracks: []`, `roster: []`, `roster_bindings: {}`, `is_archived: false`, `created_at: null`, `updated_at: null`).

5. TEST (proves the widening is real, not cosmetic): in `PlanDrawer.test.tsx`, add a case that passes an arc with `tracks: [{key:'romance',label:'Romance'}]` and `roster: [{key:'mentor',actant:'…'}]` through the factory WITHOUT any cast, and asserts the drawer renders the roster/track keys. It must compile with `tsc --noEmit` — a cast-free fixture is the regression guard. Gate: `npx tsc --noEmit` + `npx vitest run src/features/plan-hub` both green.

No BE change, no migration, no contract change. Nothing else in the repo constructs an `ArcListNode` literal (only `api.ts:20 getArcs` deserializes it), so blast radius is exactly the 2 source files + 4 test fixture files.

*Evidence:* services/composition-service/app/routers/arc.py:426-434 — `list_arcs` does `d = n.model_dump(mode="json"); d.update(derived...)` ⇒ the wire is the FULL StructureNode (services/composition-service/app/db/models.py:206-235: id, book_id, created_by, parent_id, kind, depth, rank, title, summary, goal, status, tracks, roster, roster_bindings, arc_template_id, template_version, version, is_archived, created_at, updated_at) + {span, first_story_order, is_contiguous, chapter_count}. FE declares only 12+4 at frontend/src/features/plan-hub/types.ts:36-57; the lie is worked around at frontend/src/features/plan-hub/components/PlanDrawer.tsx:308 (`const extra = arc as ArcListNode & { tracks?: unknown; roster?: unknown }`). Only consumer of the type that projects is frontend/src/features/plan-hub/hooks/planHubMappers.ts:42 (structural subset — unaffected).

### Q-32-AI4-PLANDRAWER-EMBED
PROCEED with AI-4 exactly as scoped (delete + one-line mount; DOCK-2 one component, two hosts). The ownership risk is settled — DBT-06 is HANDED to us ("#4 genuinely-upstream", book-package RUN-STATE:216), PlanDrawer.tsx is clean in the working tree, no concurrent edit. But the LOCKED snippet has two defects the code proves; build it as follows.

M5 BUILD INSTRUCTION (file-by-file):

(1) frontend/src/features/plan-hub/components/PlanDrawer.tsx
  - DELETE `rosterKeysOf` (:299-303) and `ArcFacets` (:305-357) entirely — this also removes the `arc as ArcListNode & {tracks;roster}` cast (:308) and the raw-UUID Provenance field (:346).
  - DELETE the `ArcListNode` import from `../types` if it becomes unused (keep `PlanOverlay`/`PlanOverlayRef`).
  - Add `bookId: string` to `DrawerBody`'s prop type (:360-374) and pass `bookId={bookId}` at the call site (:445-452).
  - Arc branch (:391-394) becomes EXACTLY:
      if (view.kind === 'arc' || view.kind === 'saga') {
        if (!view.arcNode) return <Centered testid="plan-drawer-empty">Arc not found in the shell.</Centered>;
        return <ArcInspectorBody arcId={view.arcNode.id} bookId={bookId} embedded canEdit={!!writes} />;
      }
  - ⚠ CORRECTION TO THE LOCKED SNIPPET — do NOT pass `writes={writes}`. `PlanDrawerProps.writes` is `PlanNodeWrites` (usePlanNodeWrites.ts:22-32) whose callbacks hit the OUTLINE routes: patchNode → PATCH ${COMP}/outline/nodes/{id} (api.ts:136), archiveNode → DELETE ${COMP}/outline/nodes/{id} (api.ts:148), restoreNode → ${COMP}/outline/nodes/{id}/restore (api.ts:154), with a `NodeEdit` patch shape. Arc writes are PATCH /arcs/{id} + If-Match (spec 32 §5). Passing it would route ARC edits at the OUTLINE endpoint. ArcInspectorBody OWNS its arc write hook (the same one the dock panel uses); the drawer only tells it the GRANT: `canEdit={!!writes}` — `writes` omitted means "no EDIT grant / no token" per PlanDrawer.tsx:47-55, which is precisely spec 32 §3.4's 403 row ("never render a control that would 403"). ArcInspectorBody's props are therefore `{ arcId, bookId, embedded?: boolean, canEdit?: boolean }` — no panel chrome and no picker when `embedded`.
  - Update the file's header comment block (:13-14), which currently states the arc inspector "does not exist yet" — that line becomes a lie the moment the mount lands.

(2) KEEP `usePlanNode`'s arc shell query and `arcNode` (usePlanNode.ts:66-70, :84-87). Spec point 3 is true of the BODY only: the drawer HEADER still reads `view.arcNode?.title` / `?.status` (PlanDrawer.tsx:414-415) and the `!view.arcNode` guard above depends on it. Deleting `arcNode` blanks the drawer header for every arc. No change to usePlanNode.ts in M5.

(3) frontend/src/features/plan-hub/components/__tests__/PlanDrawer.test.tsx — MANDATORY, same commit. The test at :91-114 ("arc/saga: renders the minimal arc summary + the reuse-gap note") asserts every testid this deletion removes (`plan-drawer-section-structure`, `-section-roster`, `-f-chaptercount`, `-f-span`, `-noncontiguous`, `-arc-gap`) and WILL red. Replace that whole `it(...)` block with: mock `ArcInspectorBody` (vi.mock the module), assert the arc branch renders it with `arcId="A1"`, `bookId="b"`, `embedded`, and `canEdit === false` when `writes` is omitted / `true` when supplied. Also DELETE the negative assertion at :88 (`plan-drawer-arc-gap` toBeNull) — the testid is gone repo-wide, so the assertion is vacuous; keep :87's roster negative only if the shared body's roster section uses a different testid (it does — it lives in ArcInspectorBody), otherwise drop it too.

DoD for the slice: `grep -rn "plan-drawer-arc-gap\|rosterKeysOf\|ArcFacets" frontend/src` → zero hits; FE vitest green; the drawer and the dock panel import the SAME `ArcInspectorBody`; live browser smoke: select an arc on the Plan Hub canvas → the drawer body shows resolved tracks/roster/span/open_promises (fields the SHELL does not carry — that is the proof the body fetched GET /arcs/{id} itself, not `view.arcNode`); `/review-impl` at wave close.

Process (per the spec's own risk row): ANNOUNCE before touching PlanDrawer.tsx; enumerate the exact 2 files on commit; NEVER `git add -A`.

*Evidence:* frontend/src/features/plan-hub/api.ts:136,148,154 (patchNode/archiveNode/restoreNode all hit ${COMP}/outline/nodes/{id} — NOT /arcs/{id}, so `writes={writes}` cross-wires entity families) · frontend/src/features/plan-hub/hooks/usePlanNodeWrites.ts:22-32 (PlanNodeWrites = the outline write contract, patch shape `NodeEdit`) · frontend/src/features/plan-hub/components/PlanDrawer.tsx:47-55 (`writes` omitted ⇒ read-only / no EDIT grant — the source of `canEdit={!!writes}`), :299-357 (rosterKeysOf + ArcFacets + the :351 arc-gap note to delete), :360-374 + :445-452 (DrawerBody has no `bookId` prop today), :414-415 (header reads view.arcNode?.title/status ⇒ arcNode must survive) · frontend/src/features/plan-hub/hooks/usePlanNode.ts:66-70,84-87 (arc shell query — keep) · frontend/src/features/plan-hub/components/__tests__/PlanDrawer.test.tsx:87-88,91-114 (the test that WILL red on the deletion; not named in M5's DoD) · docs/plans/2026-07-12-book-package-RUN-STATE.md DBT-06 row ("#4 genuinely-upstream" ⇒ handed over, not contested) · git status: frontend/src/features/plan-hub/ clean, no concurrent edit

### Q-32-AI3-KEY-VALIDATION
REJECT the either/or. Ship BOTH — the panel check stays, AND a narrow server-side KEY-INVARIANT guard lands. This is NOT OQ-2 (the full typed schema), so OQ-2 stays deferred. Rationale the builder must not re-litigate: the corruption is BACKEND-ONLY and reaches the PROMPT (`lenses.py:282-284` gather_arc -> resolve_tracks -> `_merge_by`), so the panel is not and cannot be "the only thing standing between the user and a corrupt cascade" — it sits ABOVE the bug. Two blank-keyed tracks in ONE node collide on "" within a single level (no ancestor needed) and one is silently dropped from the generation prompt. Three doors write these blobs (REST, MCP, arc-template apply), and the panel guards none of them.

BUILD (3 parts; parts a+b+c move to M1, the existing backend slice — the packer bug exists today with no panel involved. AI-3's panel validation stays in M3 exactly as specced, unchanged.)

(a) HARDEN `_merge_by` — services/composition-service/app/db/repositories/structure.py:591-595. Replace `k = it.get(key_field, id(it))` with:
    k = it.get(key_field)
    if not isinstance(k, str) or not k.strip():
        k = id(it)          # unmergeable: kept, never shadows, never shadowed
    else:
        k = k.strip()
    merged[k] = it
This turns SILENT DATA LOSS (leaf eats root's track; two blanks collapse to one) into the benign, already-documented "kept, can't be shadowed" behavior. It rejects nothing and migrates nothing — it is the ONLY thing that protects rows ALREADY in the DB, which no write-time validator can retroactively fix. The `.strip()` also kills the " romance" vs "romance" near-miss (cross-service-normalization class). Update the docstring, which currently only promises the missing-key case.

(b) TYPE BOTH ARC DOORS by reusing schema this service ALREADY SHIPS. In app/db/models.py add `ConfigDict` to the pydantic import (line 29 — it is NOT imported today) and define next to ArcThread/ArcRosterEntry:
    class TrackEntry(BaseModel):
        model_config = ConfigDict(extra="allow")   # blob passthrough — see the trap below
        key: Annotated[str, StringConstraints(min_length=1, max_length=100, strip_whitespace=True)]
        label: _Title = ""
    class RosterEntry(TrackEntry):
        actant: Actant | None = None
        constraints: list[_Short] = Field(default_factory=list)
Then swap `list[dict[str, Any]]` -> `list[TrackEntry]` / `list[RosterEntry]` at all FOUR sites: app/routers/arc.py:339-341 (ArcCreate) and :351-353 (ArcPatch); app/mcp/server.py:4281-4283 (_ArcCreateArgs) and :4338-4340 (_ArcUpdateArgs).
*** THE TRAP — do not use plain BaseModel here. *** Pydantic's default `extra="ignore"` would SILENTLY DROP any undeclared field agents write on a track entry today. That is this repo's exact `rest-write-mirror-drops-fields-the-mcp-tool-accepts` bug. `extra="allow"` is mandatory: validate the load-bearing `key`, pass the rest of the free-form blob through untouched. This is what makes the guard narrow enough NOT to be OQ-2.

(c) UNIQUENESS (AI-3's third clause — nothing enforces it anywhere today). Add a `@field_validator("tracks", "roster")` on all four arg models rejecting a duplicate `key` within the list -> 422 / MCP validation error, message naming the index and the key: "track[2].key 'romance' is already used in this arc".

DEFAULT I PICKED (flagged for veto): a corrupt-by-construction write now 422s instead of silently losing a track. The "it breaks the agent's existing writes" objection in OQ-2 only bites writes that are ALREADY corrupt — ones that silently drop a plot line from the prompt. A legible 422 is strictly better than a silent drop and is what the repo's own `silent-success-is-a-bug` law demands. Existing DB rows are NOT rejected: only writes validate, and reads are protected by (a).

MIGRATION EDGE the builder must handle in M3: a PATCH round-tripping a legacy bad row (panel loads an arc with a blank-keyed track -> user edits only the title -> save resends tracks -> 422). This is CORRECT and is the only way a legacy row ever gets cleaned — but AI-3's inline message must point at the offending entry, not at the field the user touched. In M1's DoD, run the audit query first so the build knows the real blast radius instead of guessing: SELECT id FROM structure_node WHERE EXISTS (SELECT 1 FROM jsonb_array_elements(tracks) t WHERE COALESCE(t->>'key','') = '');

TESTS (name them; the first three RED before the fix):
- test_merge_by_blank_key_does_not_shadow — saga track {"key":"","label":"root"} + sub-arc {"key":"","label":"leaf"} -> resolve_tracks(sub) returns 2 (today: 1)
- test_merge_by_two_blank_keys_same_node_both_survive — ONE node, two blank keys -> 2 entries (proves no cascade is needed to lose data)
- test_pack_arc_keeps_both_blank_keyed_tracks — the gather_arc proof the PROMPT no longer loses a track
- test_merge_by_strips_key_whitespace — " romance" in leaf shadows "romance" in root
- test_arc_create_rejects_blank_track_key / test_arc_create_rejects_duplicate_track_key — 422 at REST + validation error at MCP (both doors)
- test_arc_create_preserves_unknown_track_fields — the extra="allow" passthrough guard against the drop-fields regression

SPEC EDITS: in 32_arc_inspector.md, amend AI-3 to say the panel is the UX layer, not the enforcement layer (server enforces the key invariant at both doors). Correct OQ-2's rationale — "roster carries constraints[] whose vocabulary is unsettled" does NOT block validating `key`, and the models are not unwritten. Re-scope the defer row D-ARC-TRACKS-ROSTER-SCHEMA to: "key invariant ENFORCED (M1); the remaining deferral is typing of the NON-KEY fields only (actant enum, constraints vocabulary)" — gate #2, structural.

*Evidence:* services/composition-service/app/db/repositories/structure.py:591-595 — `k = it.get(key_field, id(it))`: key="" collides on "" across the whole chain AND within one level. | services/composition-service/app/packer/lenses.py:282-284 — gather_arc calls resolve_tracks, so the collision DROPS A TRACK FROM THE GENERATION PROMPT (backend-only bug; the panel sits above it). | services/composition-service/app/db/models.py:839-848 — ArcThread(key,label) + ArcRosterEntry(key,actant,label,constraints: list[_Short]) ALREADY EXIST and are already applied to these exact shapes at the arc-template door (models.py:858,861,872,875) — refutes OQ-2's "needs its own small spec" and its "constraints vocabulary is unsettled" rationale. | services/composition-service/app/db/models.py:456 — `_Key = Annotated[str, StringConstraints(max_length=100)]` has NO min_length, so key="" passes even the TYPED door; app/engine/arc_apply.py:495 copies template.threads straight into structure_node.tracks = a THIRD write door the panel never guards. | Free-form blob doors: app/routers/arc.py:339-341,351-353 and app/mcp/server.py:4281-4283,4338-4340. | Precedent for non-rejecting key repair already in repo: app/engine/motif_deconstruct.py:466 `_slug(t.get("key"), f"thread-{i}")`.

### Q-32-KIND-CLOSED-SET-TWO
CONFIRMED BY CODE — the concern is exactly right, and it is now a binding build rule. `kind` is a closed set of TWO on the wire (`'saga' | 'arc'`); "sub-arc" is a DEPTH LABEL derived client-side, never a value. Builder instructions:

1) FE TYPE (M2, `frontend/src/features/arc-inspector/types.ts`): `export type ArcKind = 'saga' | 'arc'`. The literal string `sub_arc` MUST NOT appear in any FE type, picker option, request body, contract JSON, or i18n VALUE. Add a grep-guard unit test in the feature's `__tests__` asserting the arc-inspector source contains no `sub_arc`/`'subarc'` token (mirrors the CLOSED_SET_ARGS discipline of docs/standards/mcp-tool-io.md IN-1..8).

2) M3 CREATE FORM — two SEPARATE controls, never one three-way picker:
   - `Kind`: 2-option segmented control {Saga, Arc}, default `'arc'` (mirrors `ArcCreate.kind` default, arc.py:333).
   - `Parent arc` (optional, separate): sets `parent_arc_id`.
   Client-side rules enforced BEFORE the POST:
   - `kind === 'saga'` ⇒ parent control is DISABLED and cleared; send `parent_arc_id: null` (DB `structure_saga_is_root`, migrate.py:1126 — otherwise the verbatim 400 STRUCTURE_CONSTRAINT).
   - Parent options = nodes from `GET /books/{bid}/arcs` filtered to `!n.is_archived && n.depth <= 1`. A depth-2 node is EXCLUDED (a child of it would be depth 3 → the trigger's `RAISE EXCEPTION`, migrate.py:1156 → 400). Picking a saga (depth 0) or an arc (depth 0/1) is legal; the resulting node IS the "sub-arc" when it lands at depth 2.
   - `kind === 'arc' && parent_arc_id != null && parent.depth === 1` ⇒ the form's live preview label reads "Sub-arc" — but the POST body still sends `kind: 'arc'`.

3) LABEL DERIVATION (M2 breadcrumb / navigator rail / picker) — one pure helper, `arcKindLabel(node: {kind, depth}): 'Saga' | 'Arc' | 'Sub-arc'`:
   `kind === 'saga' → 'Saga'; kind === 'arc' && depth >= 2 → 'Sub-arc'; else → 'Arc'`.
   No backend change: `depth` and `parent_id` already ship on every read (`_SELECT_COLS` structure.py:41-45 → `StructureNode` models.py:222-226 → `model_dump(mode="json")` in `list_arcs` arc.py:432 and `get_arc` arc.py:450).

4) M3 PATCH FORM: no Kind field and no Parent field. `kind`, `parent_id`, `rank`, `depth` are NOT in `_UPDATABLE_COLUMNS` (structure.py:51-55); reparenting is `POST /arcs/{node_id}/move` (arc.py:540) only. A kind/parent input on the PATCH form would silently no-op — a Frontend-Tool-Contract-class bug.

5) i18n × 18: THREE display labels (`studio.arc.kind.saga`, `studio.arc.kind.arc`, `studio.arc.label.subArc`) but only TWO form option VALUES. `label.subArc` is display-only and must never be fed back as a `kind`.

6) ERROR PATH stays: keep the toast for `400 {code:'STRUCTURE_CONSTRAINT'}` (arc.py:397-407) — the client-side filters make it unreachable in the happy path, but `move()` and a concurrent-reparent race can still fire it.

7) TESTS (vitest, M3 DoD): (a) selecting Saga clears+disables the parent picker and the POST body carries `parent_arc_id: null`; (b) the parent picker's options exclude every `depth === 2` node; (c) `arcKindLabel({kind:'arc', depth:2}) === 'Sub-arc'` while the submitted body is still `kind:'arc'`; (d) the no-`sub_arc` grep-guard.

DEFAULT NOTED FOR PO VETO: I chose "Kind default = arc" (matching the BE default at arc.py:333) rather than forcing an explicit choice.

*Evidence:* services/composition-service/app/db/migrate.py:1102 (`kind TEXT NOT NULL CHECK (kind IN ('saga','arc'))`), :1126 (`CONSTRAINT structure_saga_is_root CHECK (kind <> 'saga' OR parent_id IS NULL)`), :1156 (depth trigger `RAISE EXCEPTION 'structure_node depth % exceeds saga→arc→sub-arc'`); services/composition-service/app/routers/arc.py:333 (`kind: Literal["saga","arc"] = "arc"`), :397-407 (`_arc_conflict_http` → 400 STRUCTURE_CONSTRAINT), :432 & :450 (`model_dump(mode="json")` on reads), :489 (PATCH), :540 (POST /arcs/{node_id}/move — the only reparent door); services/composition-service/app/mcp/server.py:4268-4272 ("BA1: two kinds + nesting (a sub-arc is an arc whose parent is an arc) — no third enum"); services/composition-service/app/db/repositories/structure.py:41-45 (_SELECT_COLS ships parent_id + depth), :51-55 (_UPDATABLE_COLUMNS excludes kind/parent_id/depth/rank); services/composition-service/app/db/models.py:222-226 (StructureNode.parent_id / kind / depth).

### Q-32-DOD5-TWO-PROMPT-PROOFS
CONFIRMED — the concern is right and the code backs it exactly. M3's DoD ships THREE tests (+1 FE guard), not one. Pin them as follows; a builder should need no further thought.

**(a) tracks → prompt — ALREADY EXISTS. Do not rewrite, just re-run.**
`services/composition-service/tests/integration/db/test_pack_arc_wired.py::test_changing_tracks_changes_the_prompt_on_the_real_path` already drives real `pack()` through the production scene→chapter→arc resolution and asserts `before != after` after `StructureRepo.update(..., {"tracks": ...})`. That IS proof (a). M3 VERIFY re-runs it; no new code.

**(b) roster_bindings → prompt — NEW, same file, same `_seed`/`_pack_prompt` harness:**
```python
async def test_binding_a_role_puts_a_cast_line_in_the_prompt(pool):
    seed = await _seed(pool, tracks=[{"key": "loyalty", "label": "loyalty stays true"}])
    before = await _pack_prompt(pool, seed)
    assert "Cast bindings:" not in before
    entity = uuid.uuid4()
    await StructureRepo(pool).update(          # roster_bindings ONLY — no tracks in the patch
        seed["arc"].id, {"roster_bindings": {"protagonist": str(entity)}},
        expected_version=seed["arc"].version)
    after = await _pack_prompt(pool, seed)
    assert before != after, "the packer did not react to a roster_bindings change"
    assert f"Cast bindings: protagonist → {entity}" in after      # lenses.py:344
```
Two details the builder WILL get wrong otherwise: (1) `gather_arc` prints `role_key → the raw entity_id string` (lenses.py:336-344) — assert the **UUID**, not the glossary display name; name resolution is FE-only (`useGlossaryRoster`). (2) Patch `roster_bindings` **alone** (no `tracks` in the same PATCH) — that is what catches a write-model that drops the field (`rest-write-mirror-drops-fields` class). Both `roster_bindings` and `roster` are in `_UPDATABLE_COLUMNS` (structure.py:52-56), so no repo change is needed.

**(c) roster (slots) → the TEMPLATE, and explicitly NOT the prompt — NEW.** Put it in `services/composition-service/tests/integration/db/test_arc_apply_roundtrip.py` (same DSN-gated harness): seed an arc, `StructureRepo.update(arc.id, {"roster": [{"key": "traitor", "actant": "shifter"}]}, expected_version=…)`, call `extract_template_from_arc(pool, arc_node=<reloaded node>, owner_user_id=actor, code=…, name=…)` (`app/engine/arc_apply.py:652`; it wraps the pure `arc_extract_template`, def at :528, whose line 564 is `roster = await structure_repo.resolve_roster(structure_node.id)`), then load the created row via `ArcTemplateRepo(pool)` and assert `arc_roster` contains `{"key": "traitor", …}`.
PLUS a **negative** assertion back in `test_pack_arc_wired.py`: an arc with `roster` set but NO `roster_bindings` packs a prompt containing neither `"Cast bindings"` nor `"traitor"` — this pins that `roster` is deliberately not a prompt input, so a future "helpful" packer edit that injects it reds and forces a spec change instead of silently doubling the arc frame.

**Do NOT** write a pack-effect test for `summary` or `status` (no engine consumer; `grep` finds none). Their proof is the Hub/drawer rendering them, and the UI copy must label them as human-read, not generation knobs.

**FE guard (cheap, and it closes the panel→route leg the pytest cannot):** in the arc-inspector hook's vitest, assert the role-bind mutation's PATCH body carries `roster_bindings` and the track editor's carries `tracks`. Without it, a Pydantic write model that omits `roster_bindings` leaves the panel a silent no-op while BOTH backend tests stay green.

**VERIFY evidence rule (non-negotiable):** all three tests sit under `pytest.mark.skipif(not TEST_COMPOSITION_DB_URL)`. The M3 evidence string must paste counts from a run with `TEST_COMPOSITION_DB_URL` **set** — a skipped file is not a proof (`env-gated-integration-tests-skip-and-the-green-suite-lies`).

**Spec correction to land with M3:** DoD #5 and §1 cite `arc_apply.py:564` for `extract_template_from_arc`. At HEAD, :564 is a line *inside* `arc_extract_template` (def :528); the persisting seam `extract_template_from_arc` is at **:652**. Fix both cites in `32_arc_inspector.md` so the builder doesn't hunt.

This contradicts no §0 sealed decision (PO-1..4 are about Wave 7 GUI, G-WORKFLOWS ownership, `ui_show_panel` retirement, and spec-first sequencing — none touch DoD #5).

*Evidence:* services/composition-service/app/packer/lenses.py:344 (`lines.append("Cast bindings: " + …)`, role_key → raw entity_id, block at 336-344) · lenses.py:257-360 `gather_arc` calls only `resolve_tracks` + `resolve_roster_bindings` — `resolve_roster` (structure.py:605) is never called by the packer · services/composition-service/tests/integration/db/test_pack_arc_wired.py:152-168 (`test_changing_tracks_changes_the_prompt_on_the_real_path` = proof (a), already shipped; no roster_bindings test exists anywhere: `grep -rn "roster_bindings" services/composition-service/tests` → only test_arc_apply_roundtrip/test_mcp_server) · app/engine/arc_apply.py:528 `arc_extract_template` + :564 `roster = await structure_repo.resolve_roster(...)`, persisting seam `extract_template_from_arc` at :652 · app/db/repositories/structure.py:52-56 `_UPDATABLE_COLUMNS` already contains tracks/roster/roster_bindings.

### Q-32-OQ2-TRACKS-ROSTER-SCHEMA
TIGHTEN THE SERVER SCHEMA NOW — in Wave 2, as a small slice inside spec 32 (do NOT carry D-ARC-TRACKS-ROSTER-SCHEMA; DELETE that row). The defer rationale is refuted by the code: the typed models already exist and are already enforced one door over, and the "migration audit of existing rows" it asked for is done and clean (dev PG: 4 structure_node rows, ZERO non-empty tracks/roster arrays, 0 bad actants, 0 missing keys, all roster_bindings values are strings). There are no agent writes to reject. Follow the repo's own lesson `close-legacy-window-in-writer-not-base-schema`: tighten the WRITERS, keep the READ model permissive.

SLICE AI-2b (fold into spec 32, ~5 files):

1. `services/composition-service/app/db/models.py` — promote the existing shapes to the shared spec vocabulary. `ArcThread` (models.py:839 — `key: _Key`, `label: _Title`) and `ArcRosterEntry` (models.py:844 — `key: _Key`, `actant: Actant|None` where `Actant` is the closed 6-value Literal at models.py:452, `label: _Title`, `constraints: list[_Short]`) MOVE above `StructureNode` (they are currently declared below it, in the arc-template block). Add `ArcTrack = ArcThread` as an alias so the arc-template code (models.py:858-861) is untouched. Give BOTH `model_config = ConfigDict(extra="forbid")` — today they are plain BaseModels, so an unknown key is SILENTLY DROPPED (the repo's `rest-write-mirror-drops-fields` bug class); with zero legacy rows, `forbid` is free and turns a silent drop into a loud 422.

2. LEAVE `StructureNode.tracks`/`roster` as `list[dict[str, Any]]` (models.py:232-233) — the READ model stays permissive so any row written before this lands still loads. Only the write doors close.

3. Swap the two write doors to the typed models (serialize with `model_dump(mode="json")` before handing to `StructureRepo.create_node`/`update` — the repo json.dumps `_JSONB_UPDATE_COLUMNS`, structure.py:56):
   - REST: `app/routers/arc.py:339-340` (`ArcCreate.tracks/roster`) and `arc.py:351-352` (`ArcPatch.tracks/roster`) → `list[ArcTrack] | None` / `list[ArcRosterEntry] | None`.
   - MCP: `app/mcp/server.py:4281-4282` (`_ArcCreateArgs`) and `server.py:4338-4339` (`_ArcUpdateArgs`) → the same two types.
   - `roster_bindings` → `dict[str, str] | None` at all four sites (the audit proves every stored value is already a string).

4. Tests (composition-service):
   - Router: PATCH `roster:[{"key":"traitor","actant":"villain"}]` → 422; `{"key":"traitor","actant":"opponent","constraints":["must betray by ch.40"]}` → 200 and round-trips through `GET /v1/composition/arcs/{id}` → `resolved.roster`; a track with no `key` → 422; an unknown extra key → 422.
   - MCP schema (the `knowledge-mcp-three-schema-sources-fastmcp-strips` lesson): assert `composition_arc_create`'s advertised inputSchema exposes `roster.items.properties.actant.enum == ["subject","object","sender","receiver","helper","opponent"]` — FastMCP must not strip the nested object.
   - Regression: an arc whose roster came through the NEW door extracts cleanly via `arc_extract_template` (arc_apply.py:628-635) — the door that today explodes on a bad actant.

5. FE (spec 32's ROSTER section): render `actant` as a `<select>` over the 6 actants (export the closed set into `frontend/src/features/composition/types.ts` — one name for one concept) and `constraints[]` as a free-text string-list editor. `constraints` STAYS free text — its content vocabulary is genuinely open and nothing downstream reads it as an enum; only `key` and `actant` are constrained. That is the whole of OQ-2's "unsettled vocabulary" concern and it is satisfied without a spec.

6. Update spec 32 OQ-2 → "RESOLVED 2026-07-13: tightened at both write doors (ArcTrack/ArcRosterEntry); read model stays permissive; migration audit clean (0 non-empty rows)." Remove the DEFERRED row.

DEFAULT NOTED FOR PO VETO: `extra="forbid"` on the roster/track entry means an agent sending an undeclared field gets a 422 instead of a silent drop. If the PO would rather agents be able to stash arbitrary annotations on a roster slot, flip to `extra="allow"` — one line, same slice.

*Evidence:* services/composition-service/app/db/models.py:844 — `ArcRosterEntry(key:_Key, actant:Actant|None, label:_Title, constraints:list[_Short])` ALREADY EXISTS and is already enforced at the arc-template door (models.py:858-861); `Actant` is the closed 6-value Literal at models.py:452. The free-form doors are only routers/arc.py:339-340,351-352 and mcp/server.py:4281-4283,4338-4340 (`list[dict[str, Any]]`). arc_apply.py:495-497 writes structure_node.tracks/roster FROM template.threads/arc_roster and arc_apply.py:628-635 reads them back INTO `ArcRosterEntry(...)` — so a free-form `actant:"villain"` written today is a latent ValidationError inside composition_arc_extract_template. Live audit (docker exec infra-postgres-1 psql -U loreweave -d loreweave_composition): `SELECT count(*) FROM structure_node` → 4; `jsonb_agg(DISTINCT k) FROM structure_node, jsonb_array_elements(tracks) t, jsonb_object_keys(t) k` → NULL (no entries); same for roster → NULL; bad actants → 0; entries missing `key` → 0; non-string constraints → 0; `DISTINCT jsonb_typeof(v) FROM jsonb_each(roster_bindings)` → `string`. Nothing in plan 30 §0 (PO-1..4) touches this.

### Q-32-X2-CATEGORY-ORDER
FIX IT NOW (one line + one guard test) — do NOT carry it as a defer row, and do NOT let it grow past these two edits.

X-2 is real and is a two-surface inconsistency, not a cosmetic gap:
- `useStudioCommands.ts:55-56` does `CATEGORY_ORDER.indexOf(p.category)` → for 'quality' that is **-1**, so the 5 Quality panels sort FIRST in the Command Palette, ABOVE 'editor'.
- `UserGuidePanel.tsx:24-26` puts categories NOT in `CATEGORY_ORDER` into `rest`, appended LAST — so the User Guide renders Quality after 'jobs'.
Same constant, opposite placement. That defeats the stated purpose of exporting it (`useStudioCommands.ts:19`: "Exported so the #19 User Guide panel groups by the exact same order instead of duplicating it").

BUILDER INSTRUCTION (2 edits, ~6 lines total; belongs to the FIRST wave that touches the studio panel catalog or palette — the arc-inspector panel registration wave):

1. `frontend/src/features/studio/palette/useStudioCommands.ts:20-22` — add `'quality'` to `CATEGORY_ORDER`, positioned to mirror the canonical union order in `catalog.ts:81-91` (i.e. after `'knowledge'`, before `'translation'`):
   export const CATEGORY_ORDER: StudioPanelCategory[] = [
     'editor', 'storyBible', 'knowledge', 'quality', 'translation', 'enrichment', 'sharing', 'platform', 'discovery', 'jobs',
   ];

2. `frontend/src/features/studio/panels/__tests__/panelCatalogContract.test.ts` — add a recurrence guard next to the existing "#18 B6 every palette-openable panel has a category" test (line ~40). Import `CATEGORY_ORDER` from `../../palette/useStudioCommands` and assert BOTH directions so a future new category (e.g. one the arc/motif panels might add) reds immediately instead of silently top-ranking itself:
   it('every category used by a palette-openable panel is a member of CATEGORY_ORDER (X-2)', () => {
     const used = [...new Set(OPENABLE_STUDIO_PANELS.map((p) => p.category!))];
     const missing = used.filter((c) => !CATEGORY_ORDER.includes(c));
     expect(missing).toEqual([]);            // -1 from indexOf would sort the group ABOVE 'editor'
     expect(new Set(CATEGORY_ORDER).size).toBe(CATEGORY_ORDER.length);  // no dupes
   });

NOT IN SCOPE (do not scope-creep): no i18n key work beyond confirming `palette.group.quality` resolves (it falls back to the raw 'quality' string via `group(p.category, p.category)` at useStudioCommands.ts:61-63 — if a `palette.group.quality` key already exists in the studio locale, nothing to do; if not, add that ONE key and stop). No re-ordering of any other category. No refactor of `groupByCategory`.

DEFAULT THE PO CAN VETO: I placed 'quality' after 'knowledge' (mirroring the union declaration order) rather than, say, right after 'editor'. If the PO wants Quality more prominent in the palette, move the string — it is a one-token change with no other consequence.

Note for the spec: §6 step 2's "not ours to fix here" was written on the belief that X-2 does not block us. That remains true — `'editor'` IS a member, so the arc-inspector work is unblocked either way. But "does not block" is not "defer": per CLAUDE.md, a one-line root-cause-clear fix is fix-now, and a defer row would cost more to write and carry than the fix.

*Evidence:* frontend/src/features/studio/palette/useStudioCommands.ts:20-22 (CATEGORY_ORDER = 9 entries, no 'quality') vs frontend/src/features/studio/panels/catalog.ts:81-91 (StudioPanelCategory = 10 members, 'quality' at :85) and catalog.ts:266-270 (5 palette-openable panels with category:'quality'). Divergent consumers: useStudioCommands.ts:55-56 (indexOf → -1 ⇒ sorts FIRST) vs UserGuidePanel.tsx:24-26 (not in CATEGORY_ORDER ⇒ `rest` ⇒ renders LAST). Guard-test home: frontend/src/features/studio/panels/__tests__/panelCatalogContract.test.ts:37-41 (the existing "#18 B6 every palette-openable panel has a category" test).

### Q-32-PLANDRAWER-TEMPLATE-UUID
RESOLVE THE UUID IN WAVE 2; SHIP THE [open] DEEP-LINK IN WAVE 4 (it has no target until then).

**A · Wave 2 (spec 32 M2) — the Provenance section of `ArcInspectorBody`** (the component that replaces the deleted `ArcFacets`, per spec 32 AI-4; `PlanDrawer.tsx:305-357` + `rosterKeysOf` (:299) + the `plan-drawer-arc-gap` note (:351) all go away, and with them the `arc.arc_template_id` Field at :346).

1. RENDER THE SECTION UNCONDITIONALLY. Delete the `{(arc.arc_template_id || arc.template_version != null) && (…)}` guard at `PlanDrawer.tsx:344`. Today a NULL provenance HIDES the whole section — BA13's normal state has no surface at all. In the inspector, `Provenance` is always one of the sections (testid `arc-inspector-section-provenance`).

2. RESOLVE THE TITLE. In the inspector hook (`useArcInspector`, alongside the other reads), add:
   `useQuery({ queryKey: ['composition','arc-template', arcTemplateId], queryFn: () => arcApi.get(arcTemplateId!, token), enabled: !!arcTemplateId, staleTime: 300_000 })`
   using the EXISTING `arcApi.get` (`frontend/src/features/composition/motif/arcApi.ts:26`) — reuse the API layer only, no legacy-page coupling (spec 32 §2 reuse table already blesses this).

3. FOUR STATES, and THE 36-CHAR HEX IS NEVER THE VISIBLE VALUE IN ANY OF THEM:
   - `arc_template_id == null` (BA13) → the muted line `Authored from conversation (no template)`. Normal tone. NOT an error, NOT amber, no `role="alert"`, no "missing"/"unknown" wording.
   - loading → a skeleton / `Loading…` in the name slot. Never the UUID as a placeholder.
   - resolved → `From template: {template.name} · v{arc.template_version}`.
     ⚠ The version printed is the ARC NODE's `template_version` (the `structure_node` column, `plan-hub/types.ts:46`), NOT `template.version` (the template's CURRENT version). Printing the live version would silently relabel a stale arc as fresh. (Template-vs-arc version drift is Wave 4's drift view — out of scope here.)
   - `arcApi.get` rejects (404 — `repo.get_visible()` returns the uniform 404 for a foreign/private/deleted template, `services/composition-service/app/routers/arc.py:163-165`) → `From template: — no longer visible to you — · v{arc.template_version}`. Not an error state, not a panel-level error boundary, not a retry loop. The raw UUID may appear ONLY as a `title=` tooltip attribute (+ optional copy-id affordance) on that fallback line, for support/debug — never as rendered text.

4. i18n: 3 new keys under the spec-32 `panels.arc-inspector.provenance.*` namespace (`fromTemplate`, `authored`, `unavailable`) × 18 locales (M2 already requires the i18n×18 sweep — fold these in, don't add a 19th step).

**B · The `[open]` link-out — Wave 4, not Wave 2. DO NOT RENDER A DEAD BUTTON.**
The wireframe's `[open]` (spec 32 §4, line ~199) targets the `arc-templates` panel, which DOES NOT EXIST in Wave 2: `frontend/src/features/studio/panels/catalog.ts` has no `arc-templates` row, and plan 30 assigns it to Wave 4 / spec 34 (§ panel table: `| 8 | arc-templates | 34 | 4 | storyBible |`). Calling `host.openPanel('arc-templates', …)` against an unregistered id is precisely the silent-no-op class the Frontend-Tool Contract forbids. So:
   - WAVE 2 ships the resolved title as PLAIN TEXT — no `[open]` control at all. Leave a one-line code comment pointing at the defer row.
   - WAVE 4 (spec 34, in the SAME slice that registers `arc-templates` in `catalog.ts` + the `panel_id` enum + the contract) adds the control:
     `host.openPanel('arc-templates', { title: …, params: { arcTemplateId } })` — the `params` deep-link seam from `frontend/src/features/studio/host/studioLinks.ts:80`, consumed panel-side via `props.params` exactly as `panels/QualityCanonPanel.tsx:34` does (`props.params as CanonFocusParams`).
     Make this a LITERAL line in Wave 4's Definition of Done: *"the arc-inspector Provenance `[open]` button opens `arc-templates` focused on the template — proven by a test that asserts `openPanel` was called with `('arc-templates', {params:{arcTemplateId}})`, not by a screenshot."*

**C · Tests (Wave 2, in the spec-32 panel suite):** four cases, all asserting the negative too —
   1. template resolves → renders name + `v{template_version}`; AND `expect(screen.queryByText(/[0-9a-f]{8}-[0-9a-f]{4}-/i)).toBeNull()` (no UUID anywhere in the panel).
   2. `arc_template_id === null` → the exact BA13 string is present, the section IS rendered, and no `role="alert"` / error-tone class is present.
   3. `arcApi.get` rejects 404 → the "no longer visible to you" fallback renders, panel does NOT enter its error state, and again NO visible UUID.
   4. `arc_template_id === null` → `arcApi.get` is NOT called (the `enabled` gate) — a wasted fetch on every template-less arc is the regression this pins.

**Defer row to write (this is the only deferral, and it is gate-3, naturally-next-phase — the target panel genuinely does not exist yet):**
`D-ARC-PROVENANCE-DEEPLINK` | origin: Wave 2 / spec 32 M2 | Provenance renders the resolved template title as plain text; the `[open]` deep-link to the `arc-templates` panel is not wired because that panel is first registered in Wave 4. | gate 3 (naturally-next-phase) | target: Wave 4 / spec 34 — wire it in the same slice that adds the `arc-templates` catalog row; it is a DoD line of that slice.

**PO veto point (my default, stated so you can overrule):** I chose "no button in Wave 2" over "a button that opens the legacy composition page (`/books/:bookId/chapters/:chapterId/edit` → `ArcTemplateLibraryView.tsx`)". Deep-linking into a page spec 16 slates for RETIREMENT would tear down the dock and create a second, dying entry point 2 waves before it dies. If you'd rather the novelist have SOME way to see the template in Wave 2, the cheap alternative is a hover-popover showing `template.summary` + `genre_tags` from the SAME `arcApi.get` response (zero new fetch) — say the word and it goes in M2.

*Evidence:* frontend/src/features/plan-hub/components/PlanDrawer.tsx:344-347 (`<Field label="Arc template" value={arc.arc_template_id} …>` — raw UUID; and the `&&` guard that HIDES the section when provenance is NULL, so BA13's normal state has no surface today) · frontend/src/features/composition/motif/arcApi.ts:26 (`get(arcId, token) → ArcTemplate`) · frontend/src/features/composition/motif/arcTypes.ts:39-60 (`ArcTemplate.name`, `.summary`, `.version`) · frontend/src/features/plan-hub/types.ts:46 (`arc_template_id?: string | null; template_version?: number | null` — the arc-side version, the one to print) · services/composition-service/app/routers/arc.py:157-166 (`repo.get_visible(user_id, arc_id)` → uniform 404 ⇒ the resolve can legitimately fail; fallback state is mandatory) · frontend/src/features/studio/panels/catalog.ts (NO `arc-templates` row — the link-out target does not exist; plan 30 §Wave 4 table row `| 8 | arc-templates | 34 | 4 | storyBible |`) · frontend/src/features/studio/host/studioLinks.ts:80 (`host.openPanel(panelId, { title, params })` — the Wave-4 deep-link seam) · frontend/src/features/studio/components/panels/QualityCanonPanel.tsx:34 (`props.params` consumption precedent) · docs/specs/2026-07-01-writing-studio/32_arc_inspector.md:110,199-200,294-296 (reuse verdict "arcApi.get", the `[open]` wireframe, BA13)

### Q-32-STRUCTURE-CONSTRAINT-VERBATIM
ADOPT AS STATED — and the plumbing already exists, so this is ~0 new code. Builder instructions for M3 (Arc Inspector create + move/re-parent):

1) RENDER VERBATIM = render `err.message`. `apiJson` (frontend/src/api.ts:144-158) already unwraps FastAPI's object-shaped `detail` and picks `detail.message` into the thrown Error. The server's `_arc_conflict_http` (arc.py:397-407) sets `detail = {code:"STRUCTURE_CONSTRAINT", message:"a saga cannot have a parent, nesting is capped at saga→arc→sub-arc (depth 2), no cycles, and a parent must be in the same book", detail:<raw trigger text>}`. So in the inspector's create/move mutations, `onError: (e) => setStructureError(e.message)` and render that string as-is in an inline error under the form. Do NOT map it, rewrite it, prettify it, or switch on its text. Mirror the existing shape in usePlanMoves.ts (`onError: onFailed` → `moveError`, lines 187-303).

2) THE ONE TRAP — to style it as a constraint violation vs a generic 400, branch on `(err as {body?: any}).body?.detail?.code === 'STRUCTURE_CONSTRAINT'`, NOT `err.code`. `err.code` is assigned from TOP-LEVEL `body.code` (api.ts:127 `const err = body as ApiError`), which FastAPI never sets — the code lives at `body.detail.code`. `if (err.code === 'STRUCTURE_CONSTRAINT')` is a silently-dead branch. (`body` is attached to the Error at api.ts:159-162, so it is reachable.)

3) DO NOT PRE-VALIDATE (the corollary). The parent picker lists every non-archived arc/saga in the book shell; do NOT filter or gray out options by depth, by kind (saga), or by cross-book. No client depth counter, no client cycle walk that produces an error message. The rules are DB-trigger-enforced; a client copy is a second SSOT that drifts.

4) THE ONE SANCTIONED CLIENT-SIDE SKIP STAYS — and is NOT a violation of (3), because it emits no message and fabricates no rule: a guaranteed-pointless GESTURE (dropping an arc on ITSELF, or into its OWN subtree) is skipped with no write and no error (usePlanMoves.ts:307-311, whose comment already draws this line). If the inspector grows a drag affordance, mirror that skip. Do NOT extend it to depth, cross-book, or parented-saga — those must round-trip.

5) DEFAULT I AM PICKING (PO may veto): render only `detail.message`; do NOT surface `detail.detail` — that is the raw Postgres trigger text (`str(exc)[:300]`), developer-facing noise. Consequence to accept: the message is one lumped sentence naming all four rules, so it does not tell the user WHICH rule they broke. That is the server's wording and we render it as-is rather than inventing a client-side per-rule message (which would be exactly the re-implementation this item forbids). If per-rule precision is later wanted, fix it SERVER-side in `_arc_conflict_http`, never in the client.

6) TEST (mirror usePlanMoves.test.tsx:211-216): reject the mutation with `Object.assign(new Error('a saga cannot have a parent, nesting is capped at saga→arc→sub-arc (depth 2), no cycles, and a parent must be in the same book'), {status:400, body:{detail:{code:'STRUCTURE_CONSTRAINT', message:'<same sentence>'}}})` and assert the panel's DOM contains that exact sentence, sourced from the error object — not from a client-side constant (asserting against a client constant is circular and would pass even if the client authored the text itself).

*Evidence:* services/composition-service/app/routers/arc.py:397-407 — `_arc_conflict_http` returns HTTP 400 with dict detail `{"code":"STRUCTURE_CONSTRAINT","message":"a saga cannot have a parent, nesting is capped at saga→arc→sub-arc (depth 2), no cycles, and a parent must be in the same book","detail":str(exc)[:300]}`. || frontend/src/api.ts:144-158 — apiJson already handles the object-shaped `detail`: `const detail = (body as {detail?: unknown})?.detail; ... : detail && typeof detail === 'object' ? (o.message ?? o.code) ...` then `throw Object.assign(new Error(err?.message || detailMessage || res.statusText), {status, code: err?.code, body})`. Hence `err.message` IS the server sentence verbatim; `err.code` is undefined (it reads top-level body.code, api.ts:127); the full envelope is on `err.body`. || frontend/src/features/plan-hub/hooks/usePlanMoves.ts:282-284 + 307-311 — the existing precedent: "Cycle / depth>2 / parented-saga are the server's rules (clean 4xx → moveError); we only skip the two calls that are guaranteed-pointless: dropping an arc on itself, or into its own subtree." || frontend/src/features/plan-hub/hooks/__tests__/usePlanMoves.test.tsx:211-216 — the test precedent asserting a server rejection's message surfaces. || frontend/src/features/plan-hub/api.ts:186-190 — moveArc's contract comment already states the client "need not re-implement those rules".

### Q-32-UNIFORM-404
CONFIRMED BY CODE — the uniform 404 is intentional and STAYS. No backend change. Do NOT add an existence-probe route, an `exists` flag, or a distinct 410/403 for "gone" — that IS the oracle H13 forbids and it leaks cross-tenant row existence (a tenancy control, not an ergonomics wart). The whole fix is frontend. Build it exactly like this:

(1) `frontend/src/features/studio/host/types.ts` — declare the new arc bus event with an OPTIONAL id so the slice is CLEARABLE: `| { type: 'arc'; arcId?: string }`, reducer `case 'arc': return { ...base, activeArcId: e.arcId };` (undefined ⇒ slice cleared). Precedent for an optional-payload event: `startGuidedTour`'s `tourId?` (types.ts:59). Add `activeArcId?: string` to `StudioBusSnapshot`.

(2) `frontend/src/features/studio/panels/useArcInspector.ts` (mirror `useSceneInspector.ts`) — expose a THIRD state field `gone: boolean`, distinct from `error: string | null`. 404 is a terminal empty state, not a retryable error, and must not render as an error toast. In the `load()` catch (mirroring useSceneInspector.ts:55-59) read `const status = (e as { status?: number }).status` — `frontend/src/api.ts:159-160` already attaches `status: res.status` to the thrown Error, the same channel useSceneInspector.ts:78 uses for 412. If `status === 404`: `setNode(null); setGone(true); publish({ type: 'arc', arcId: undefined })`. Any other status → the existing generic `setError(...)` path, and `gone` stays false. GUARD the whole 404 branch with the generation token (`if (myGen === gen.current)`, useSceneInspector.ts:54-58) — otherwise a stale in-flight 404 clears a bus slice the user has already moved on from.

(3) SAME 404 branch in `patch()`'s catch, alongside the existing 412 branch. `useSceneInspector` only handles 412 there, but arc UPDATE and DELETE raise the identical uniform 404 (arc.py:512, arc.py:556) — an arc archived/revoked mid-edit must flip the panel to `gone`, not print a raw "not found or not accessible" save error.

(4) Panel render: when `gone`, render ONLY the i18n string `studio.arcInspector.gone` = "This arc is no longer accessible." with the arc picker as the sole affordance (i.e. it degrades into §3.4's "no selection" state). Never render "deleted", "archived", or "you don't have permission" — the panel has no oracle. NOTE the ARCHIVED state is a DIFFERENT, reachable state and must not be confused with this one: `StructureRepo.get()` does not filter archived, so an archived node returns **200 with `is_archived: true`** (spec §3.4 line 256) and gets the dim+Restore banner. A 404 therefore genuinely means gone-or-denied, never archived.

(5) Test — `frontend/src/features/studio/panels/__tests__/useArcInspector.test.ts`: (a) mock the arc GET to reject with `Object.assign(new Error('not found or not accessible'), { status: 404 })` → assert `gone === true`, `node === null`, and `publish` was called with `{ type: 'arc', arcId: undefined }`; (b) mock a 500 → assert `gone === false`, `error` set, and `publish` NOT called (the bus slice survives a transient failure — clearing it on a 502 would evict a perfectly live arc); (c) a 404 from `patch()` flips `gone` too.

Sane default I am picking (veto-able): the 404 CLEARS the bus slice rather than leaving the dead id parked. Rationale — the slice is what an agent `resource_ref` deep-link lands on and what a panel reopen reseeds from; leaving a dead id there makes every subsequent open of the panel re-404 forever with no way back to the picker.

*Evidence:* services/composition-service/app/routers/arc.py:383-393 (`_gate_arc`: `node is None` → 404 NOT_ACCESSIBLE_MESSAGE, then `_gate_book` maps OwnershipError → the SAME 404 at arc.py:377-378 — docstring: "A missing node returns the SAME uniform 404 as a denied grant (no oracle)"); same uniform 404 on write paths arc.py:512 + arc.py:556; sdks/python/loreweave_mcp/errors.py:31 (`NOT_ACCESSIBLE_MESSAGE = "not found or not accessible"`); mirrored in outline.py:137/153/172. FE plumbing already present: frontend/src/api.ts:159-160 (`throw Object.assign(new Error(...), { status: res.status })`) consumed at frontend/src/features/studio/panels/useSceneInspector.ts:78 for its 412 branch; optional-payload bus-event precedent at frontend/src/features/studio/host/types.ts:59 (`startGuidedTour`'s `tourId?`). Archived-is-200-not-404 verified: spec 32_arc_inspector.md §3.4:256.

### Q-32-ARCHIVED-NULL-NOT-ZERO
CONFIRMED against code, and it is buildable now — implement it as part of M1/BE-A1. The contract is: **archived ⇒ every derived metric is `null` ("not computed"); live-with-no-chapters ⇒ `0` ("computed, and it is zero"). The two must never collapse.**

BACKEND (composition-service) — 4 edits:

1. `services/composition-service/app/routers/arc.py:455` (`get_arc`) — delete `out["span"] = await structures.span(node.id)` and replace with the derived_blocks lookup (one query, `node.book_id` is already in hand):
```python
    block = (await structures.derived_blocks(node.book_id)).get(node.id)
    # An ARCHIVED node has NO key: derived_blocks seeds its CTE from live nodes only
    # (structure.py:262-268). A missing key means NOT COMPUTED — emit null, never 0.
    out["span"]              = block["span"]              if block else None
    out["is_contiguous"]     = block["is_contiguous"]     if block else None
    out["chapter_count"]     = block["chapter_count"]     if block else None
    out["first_story_order"] = block["first_story_order"] if block else None
```
Keys go at the TOP LEVEL with exactly the list route's names/shape (`span:{from_order,to_order}` dense ordinals). Do NOT keep `span()`'s raw `min_story_order`/`max_story_order` keys; do NOT nest under a `derived` object.

2. `services/composition-service/app/mcp/server.py` (`composition_arc_get`, the `out["span"] = await structures.span(node.id)` line ~4255) — identical replacement, so the agent door and the REST door return the same shape AND the same unit.

3. `StructureRepo.span()` (`app/db/repositories/structure.py:641`) — **LEAVE EXACTLY AS IS.** Its third caller is the packer (`lenses.py:322` → `_arc_position`), which compares its RAW strided keys against a scene's raw `story_order`; dense-ranking it silently corrupts every generation prompt. Keep the `gather_arc` pacing test that pins `min_story_order`/`max_story_order`.

4. `arc.py` `list_arcs` (~line 429) — change the `empty` fallback from `{"span": None, "is_contiguous": True, "chapter_count": 0, "first_story_order": None}` to all-null `{"span": None, "is_contiguous": None, "chapter_count": None, "first_story_order": None}`. This is SAFE and REQUIRED: `derived_blocks` emits a row for EVERY live node — including a 0-chapter one (`structure.py:300-327` builds one row per CTE root via LEFT JOIN) — so the fallback is reached ONLY for archived rows, i.e. only under `?include_archived=true` (the picker's "Show archived"). Today those rows LIE: they report `chapter_count: 0` + `is_contiguous: true` for an arc that still has all its chapters bound (`archive()` at `structure.py:404` flips `is_archived` only; it never nulls `outline_node.structure_node_id`). After the change LIST and GET agree, and the Hub shell (which never passes `include_archived`) sees zero behavior change. *(This 4th edit is my chosen default beyond the literal BE-A1 text — veto-able, but without it the picker keeps rendering a fabricated 0.)*

TESTS (M1 Definition of Done):
- `services/composition-service/tests/unit/test_arc_hub_routes.py`
  - `test_get_arc_archived_derived_block_is_null` — archive an arc that HAS member chapters → `GET /v1/composition/arcs/{id}` still 200 (`StructureRepo.get()` at structure.py:213 has no archived predicate — the state IS reachable) and assert `body["chapter_count"] is None and body["span"] is None and body["is_contiguous"] is None` (assert `is None`, never `not body[...]`).
  - `test_get_arc_live_empty_arc_is_zero_not_null` — a LIVE arc with no chapters → `chapter_count == 0`, `span is None`, `is_contiguous is True`. This pair IS the null≠zero proof; a falsy implementation passes one and fails the other.
  - `test_list_and_get_agree` — same live node: list block == get block; with `include_archived=true` the archived node's LIST block is all-null too.
  - MCP parity: `composition_arc_get(node)["span"] == ` the REST body's `span` for the same node.

FRONTEND (`frontend/src/features/studio/panels/ArcInspectorBody.tsx` + `useArcInspector.ts`):
- ONE formatter used for every derived metric — nullish, never falsy:
  `const fmtMetric = (v: number | null | undefined) => (v == null ? '—' : String(v));`
  BANNED in this panel: `v || '—'`, `!v ? '—' : …`, `v ? … : '—'`. A live arc with `chapter_count: 0` MUST render "0 chapters".
- Gate the archived presentation on the FLAG, not on falsiness: `arc.is_archived` ⇒ dim the body, banner *"Archived — restore to edit."* + **Restore**, and render span/chapters as "—" carrying `title`/`aria-label` "Not computed while archived". Never a computed 0.
- Panel test `frontend/src/features/studio/panels/__tests__/ArcInspector.test.tsx`: case A `{is_archived:true, chapter_count:null, span:null}` renders "—"; case B `{is_archived:false, chapter_count:0, span:null}` renders "0". A falsiness impl reds case B.
- Archive-confirm copy stays honest per §3.4/OQ-8 (chapters stay bound to the archived arc; BE-A3 unassign is the only escape hatch). No change to `archive()` — that stays `D-ARC-ARCHIVE-CHAPTER-STRANDING`.

*Evidence:* services/composition-service/app/db/repositories/structure.py:244-268 (`derived_blocks` recursive CTE seeds `WHERE book_id=$1 AND NOT is_archived` → archived nodes get NO key; docstring: "Returns a row ONLY for keys of LIVE (non-archived) nodes … never a computed value") · structure.py:300-327 (a row IS built for every live node, `cc == 0` ⇒ `chapter_count: 0, span: None, is_contiguous: True` — the legit zero) · structure.py:213-222 (`StructureRepo.get()` = `SELECT … WHERE id = $1`, no archived predicate ⇒ the detail route serves an archived node 200) · services/composition-service/app/routers/arc.py:455 (`out["span"] = await structures.span(node.id)` — the raw-strided detail-route defect) · arc.py:429-434 (`empty = {"span": None, "is_contiguous": True, "chapter_count": 0, "first_story_order": None}` + `derived.get(n.id, empty)` — the fabricated 0 for archived rows) · services/composition-service/app/mcp/server.py ~4255 (same `structures.span(node.id)` line in `composition_arc_get`) · structure.py:404 (`archive()` flips `is_archived` only; chapters stay bound) · structure.py:641 (`span()` — the packer's raw-unit consumer via lenses.py:322; do not touch)

### Q-32-CREATE-BODY-NO-TRACKS
AFFIRMED as specced — the arc-inspector create form posts EXACTLY six fields and nothing else. Build it like this:

1) API layer — add `createArc(bookId, body)` next to the existing arc calls in `frontend/src/features/plan-hub/api.ts` (`getArcs`:20, move:190, assign-chapters:241). Type the body as a CLOSED TS type: `type ArcCreateBody = { kind: 'saga' | 'arc'; parent_arc_id: string | null; title: string; summary: string; goal: string; status: ArcStatus }`. Do NOT include `tracks`, `roster`, `roster_bindings`, `arc_template_id`, or `template_version` in this type — the backend accepts them (`arc.py:339-343`), so the TS type is the only thing stopping a later "helpful" addition. POST → `/v1/composition/books/{bid}/arcs`.

2) The form (header `+ New arc` / `+ New saga`, and the empty-state CTA): Kind (closed set {saga, arc} — NO `sub_arc`; a sub-arc is an `arc` with an `arc` parent, per spec §3.2 and the DB CHECK at `migrate.py:1102`); Parent (picker over the shell tree, forced to `null` and disabled when kind=saga, since `structure_saga_is_root` 400s otherwise); Title (REQUIRED, trim, non-empty — the BE defaults `title: str = ""` (`arc.py:335`) and will happily create a nameless node, so the guard is client-side); Goal + Summary (optional textareas); Status (select, default `outline`).

3) After the 201: seed/invalidate `['plan-hub','arcs',bookId]`, publish the bus event `{ type: 'arc', arcId: node.id }` (the new slice from §3.1) so the inspector immediately selects the created arc, and land the user on the TRACKS section with its `[+ track]` affordance visible. That is what makes "tracks are edited AFTER create" a complete flow rather than a dead end — the create→select→author-tracks path is one continuous motion, no second navigation.

4) DO NOT add a template dropdown to the create form. Creating from a template is a separate, already-built flow (`POST /arc-templates/{id}/apply` — apply-preview with rescale/roster-bind/drop-merge plan). Two paths writing `arc_template_id` would fork provenance.

5) Machine-check the decision (checklist⇒test-the-effect): in the arc-inspector vitest, assert the create mutation's request body keys are exactly `['goal','kind','parent_arc_id','status','summary','title']` (sorted). A future agent bolting a nested track editor onto the create form then reds the suite instead of shipping a form nobody finishes.

Default noted for PO veto: if a "create from template" entry point is later wanted, it goes in the ARC-TEMPLATE library panel (apply-preview), never as a field on this create form.

*Evidence:* services/composition-service/app/routers/arc.py:332-343 (ArcCreate accepts tracks/roster/roster_bindings/arc_template_id — all optional, so omitting them is legal and the restriction is FE-side by choice); arc.py:466-486 (POST /books/{book_id}/arcs → 201, full node returned, created_by server-stamped); arc.py:333 (kind Literal['saga','arc'], status default 'outline'); arc.py:335 (title defaults to "" — blank-title create is legal at the BE, hence the client-side required guard); docs/specs/2026-07-01-writing-studio/32_arc_inspector.md:206 (the Create paragraph being adjudicated); frontend/src/features/plan-hub/api.ts:20 (the arcs cache key the create must invalidate)

### Q-32-DOD6-BOOKKEEPING
DoD #6 is a WORK ITEM, not an open design question — but the spec's wording ("move DBT-06 to 'Recently cleared'") does not match the target file's actual convention, so pin it exactly. In the SAME commit as Wave 2's last slice (M4), do these 5 edits and nothing more:

(1) RUN-STATE — docs/plans/2026-07-12-book-package-RUN-STATE.md:216. There is NO "Recently cleared" section in this file (§ headers are: 5 Slice board, 6 Decisions, 7 Parked, 8 Debt, 9 Drift, 10 Completeness, 11 Final audit). The file's own convention for a cleared debt row is STRIKE-THROUGH IN PLACE inside §8 with a CLEARED note (see ~~DBT-08~~ line 220, ~~DBT-12~~ line 221, ~~DBT-10~~/~~DBT-11~~ lines 222-223). So edit line 216 to: `| ~~DBT-06~~ | **CLEARED 2026-07-<dd> (Wave 2 / spec 32, `<sha>`)** — the `arc-inspector` panel ships (identity · tracks · roster+bindings · derived span · promises rollup · provenance) and PlanDrawer's arc variant embeds it; the `plan-drawer-arc-gap` note at `PlanDrawer.tsx:351` is DELETED. ~~`23`-C3 arc inspector does not exist…~~ | `PlanDrawer.tsx:191` | — |`. Do NOT invent a "Recently cleared" heading, and do NOT touch §5's D2 row (line 160) or §11 — that run is closed.

(2) SESSION_HANDOFF — docs/sessions/SESSION_HANDOFF.md, the Writing-Studio track block's table "### Deferred (from plan 30 — consciously parked, each with its gate reason)" (line 95). This is the ONE home for these rows: docs/deferred/DEFERRED.md does NOT carry the plan-30 rows (grep: 0 hits for D-WIKI-INVERSE-GAP / D-ARC-DECOMPILER) — that file is the AMAW list; do not double-file. Append exactly two rows, same 3-column shape (ID | What | Gate):
  • `| **D-ARC-TRACKS-ROSTER-SCHEMA** | Spec 32 OQ-2 (Wave 2). `tracks`/`roster` are `list[dict[str, Any]]` — a free-form blob at BOTH doors (REST + MCP). AI-3 makes the *panel* safe; a server-side schema would reject writes the agent already makes, and `roster[].constraints[]` has an unsettled vocabulary. Needs its own small spec + a migration audit of existing rows. | #2 large/structural |`
  • `| **D-ARC-ARCHIVE-CHAPTER-STRANDING** | Spec 32 OQ-8 (Wave 2). `archive()` does not null `outline_node.structure_node_id`, so an archived arc's chapters appear in neither the arc lane nor the `?unassigned=true` tray. Mitigated in Wave 2: BE-A3's unassign is the escape hatch and the archive confirm SAYS what happens. Whether archive should *cascade* an unassign is open — it changes restore's contract (restore could not put them back). | #2 large/structural |`
Also update that track's header/NEXT line (line 49, currently "AUDIT + SPECS DONE, BUILD NOT PLANNED") to record Wave 2 shipped + the live-smoke evidence string.

(3) plan-30 Wave 2 row closed = THREE edits in docs/specs/2026-07-01-writing-studio/30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md, not one: (a) §5.1 gap row `**G-ARC-SPEC-CRUD**` (line 238) — prefix the row's first cell with `✅ SHIPPED 2026-07-<dd> (`<sha>`, spec 32)` and strike the "CONFIRMED … not built" status cell; (b) the `### Wave 2 — THE SPEC TREE` block (lines 364-371) — stamp `**Status: ✅ SHIPPED**` under the heading, and note that BE-A1/A2/A3 landed; (c) Appendix B (line 816) — `| ~~`DBT-06`~~ (23-C3 arc inspector) | ✅ G-ARC-SPEC-CRUD (Wave 2) — SHIPPED |`.

(4) OQ-6 amendment: rewrite plan-30 §8.2's X-12 bullet (lines 649-654). Its premise ("a panel that needs an id is structurally OUTSIDE the agent enum ⇒ must be `hiddenFromPalette`") is REFUTED by two SHIPPED precedents — name them: `scene-inspector` (takes its target over the studio BUS) and `quality-canon` (takes it via `props.params` deep-link, shipped in `d662bd97d`). Replace "must be `hiddenFromPalette`" with: "`arc-inspector` is openable by a BARE ID (it self-resolves its target from the bus/selection, per spec 32 AI-1) and therefore stays IN the enum, IN the palette, IN the User Guide — as `scene-inspector` and `quality-canon` already do. X-12 is CLOSED for id-resolving panels. It may still bite `motif-editor` / `workflow-editor` — decide those in their own specs, on their own evidence." Leave §11's other half (X-5: `ui_show_panel` retire-vs-enum) untouched and still open.

(5) Do NOT add a `params` arg to `ui_open_studio_panel` while making these edits — spec 32 AI-1 answers plan-30 §11(a) as "do NOT extend it", and that is the whole point of the amendment.

Default I am picking (PO may veto): all 5 edits land in the Wave-2 final commit, not a separate docs commit — CLAUDE.md's COMMIT phase requires the SESSION update to land in the same commit as the code.

*Evidence:* docs/specs/2026-07-01-writing-studio/32_arc_inspector.md:510-511 (DoD #6 text) · docs/plans/2026-07-12-book-package-RUN-STATE.md:216 (DBT-06 row) + :207-223 (§8 Debt register — cleared rows are struck IN PLACE: ~~DBT-08~~/~~DBT-12~~/~~DBT-10~~/~~DBT-11~~; the file has NO "Recently cleared" section — its only §-headers are 1-11) · docs/sessions/SESSION_HANDOFF.md:95 ("### Deferred (from plan 30 …)" table = the one home; docs/deferred/DEFERRED.md has 0 hits for any plan-30 row) · 30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md:238 (G-ARC-SPEC-CRUD gap row), :364-371 (Wave 2 block), :816 (Appendix B DBT-06→Wave 2), :649-654 (§8.2 X-12 bullet to amend) · 32_arc_inspector.md:520 (OQ-2 ⇒ D-ARC-TRACKS-ROSTER-SCHEMA, gate #2), :524 (OQ-6), :526 (OQ-8 ⇒ D-ARC-ARCHIVE-CHAPTER-STRANDING, gate #2) · frontend/src/features/studio/panels/PlanDrawer.tsx:351 (the visible `plan-drawer-arc-gap` note that DBT-06's clearing must delete)

### Q-32-LIVE-BROWSER-SMOKE
MANDATORY — the concern is upheld and turned into a concrete, buildable slice. It is NOT a design question and NOT deferrable: the E2E harness this needs already exists (Playwright config + helpers + StudioPage page-object), so writing the spec is unbuilt work, not a blocker. The claim that grounds the concern is TRUE: `grep -rn "plan-hub" frontend/tests/e2e` returns ZERO hits — spec 24's H8.2 "smoke" never touched a browser.

BUILDER INSTRUCTION (verbatim, no further thought required):

1) FILE TO CREATE: `frontend/tests/e2e/specs/arc-inspector.spec.ts`. Copy the skeleton of `frontend/tests/e2e/specs/studio-editor-craft.spec.ts:1-30` — same imports (`loginViaUI` from `../helpers/auth`; `getAccessToken, createBook, createChapter, trashBook` from `../helpers/api`; `StudioPage` from `../pages/StudioPage`), same `beforeAll` (token → createBook → createChapter ×3) / `afterAll` (trashBook) / `beforeEach(loginViaUI)` shape. Do NOT invent a new harness.

2) EIGHT `test(...)` BLOCKS, one per leg, each named for its leg:
   L1 `⌘⇧P → Arc Inspector mounts`: `await new StudioPage(page).openPanel('arc-inspector', 'Arc Inspector')` (StudioPage.ts:43 — palette entry testid is `palette-entry-studio.openPanel.arc-inspector`, which requires the panel be registered via `useStudioPanel` with `commandId studio.openPanel.arc-inspector`), then `expect(page.getByTestId('arc-inspector-panel')).toBeVisible()`.
   L2 `create saga → plan-hub lanes update with NO reload`: open plan-hub in a second dock tab FIRST, create the saga from the inspector, then assert the plan-hub lane row appears WITHOUT `page.reload()` (a `page.reload()` anywhere in this test is an automatic fail — the whole point is cache invalidation reaching the hand-rolled loader; see memory `invalidateQueries-cannot-reach-hand-rolled-state`).
   L3 `sub-arc inherits parent track`: create sub-arc + add a track on the saga; assert the sub-arc row shows the INHERITED badge and that `GET /v1/composition/arcs/{subArcId}` (routers/arc.py:438) returns the track inside `resolved.tracks`.
   L4 `edit title → save → edit again immediately → NO 412`: two `fill`+save cycles back-to-back with no wait between; assert zero 412 in `page.on('response')` capture (memory: `instant-commit-control-over-occ-entity-needs-write-serialization`).
   L5 `out-of-band write → 'changed elsewhere — reloaded' → retry SUCCEEDS`: with the panel open holding a stale version, drive an out-of-band `PATCH /v1/composition/arcs/{node_id}` (services/composition-service/app/routers/arc.py:489) from the test's `request` context, then save in the panel → assert the reload toast/testid `arc-inspector-conflict-reloaded` appears AND the automatic retry lands 200. DEFAULT I AM PICKING (veto if you disagree): the conflict is driven by the REST PATCH rather than an MCP `composition_arc_update` round-trip — the MCP tool delegates to the same handler, so the conflict source is identical and the test avoids MCP-auth plumbing. The real agent path is still proven by L8.
   L6 `assign then REMOVE a chapter → lands in unassigned tray`: use `POST /books/{book_id}/arcs/assign-chapters` (arc.py:560) only to seed; do the REMOVE through the UI and assert the chapter row appears under `arc-inspector-unassigned-tray`.
   L7 `archive → confirm names REAL sub-arc count → restore brings back subtree AND ancestors`: assert the confirm dialog text contains the actual descendant count (not a hardcoded/0), then `POST /arcs/{node_id}/restore` (arc.py:528) via the UI and assert both the sub-arc rows and the ancestor lane reappear.
   L8 `agent leg — ui_open_studio_panel {panel_id:'arc-inspector'} mounts a DOCK TAB`: copy the injection pattern from `frontend/tests/e2e/specs/frontend-tools-liveness.spec.ts` (`installFrontendToolSuspend` from `../helpers/frontendToolInject`). Assert BY EFFECT — `expect(page.getByTestId('arc-inspector-panel')).toBeVisible()` and a `.dv-default-tab` with text "Arc Inspector" — NEVER `shown:true` in the raw stream.

3) PREREQUISITE THE SAME WAVE MUST SHIP (L8 is a silent no-op without it): add `"arc-inspector"` to the `panel_id` enum at `services/chat-service/app/services/frontend_tools.py:401`, add it to the panel-purpose description string, keep it in `CLOSED_SET_ARGS`, and regenerate `contracts/frontend-tools.contract.json` (`WRITE_FRONTEND_CONTRACT=1 pytest`) + wire the FE resolver case. Un-enumerated panel_id is the exact shipped bug the Frontend-Tool Contract rule exists to kill.

4) HOW IT IS RUN (this is the DoD, not a suggestion): rebuild the FE image first — :5174 is the BAKED nginx prod build, a stale image is a false-green (memory `live-smoke-rebuild-stale-images-first`, `frontend-5174-is-baked-prod-nginx-not-vite`). Then `cd frontend && npx playwright test tests/e2e/specs/arc-inspector.spec.ts` (config: frontend/playwright.config.ts:3, baseURL http://localhost:5174, override with PLAYWRIGHT_BASE_URL=http://localhost:5199 if using vite dev). Signed in as claude-test@loreweave.dev via `loginViaUI`. Drive dockview via `evaluate` + `data-testid` where snapshot refs go stale.

5) DoD WORDING for the final wave (replace DoD #4): "The transcript contains the PASTED output of `npx playwright test tests/e2e/specs/arc-inspector.spec.ts` showing 8 passed against a REBUILT image. Claiming the smoke passed without pasting its output does NOT satisfy this DoD." No `live infra unavailable` escape hatch is granted for this one — the stack is bootable in this repo; if a leg is genuinely unrunnable, the spec file still ships with that leg written and `test.fixme()` + a tracked defer row naming the leg, never a silent omission. `/review-impl` runs at the close of the wave, per the run policy.

*Evidence:* frontend/tests/e2e/specs/studio-editor-craft.spec.ts:1-30 (harness to copy) · frontend/tests/e2e/pages/StudioPage.ts:43 (`openPanel` → `palette-entry-studio.openPanel.<panelId>`) · frontend/playwright.config.ts:3 (baseURL 5174) · frontend/tests/e2e/specs/frontend-tools-liveness.spec.ts:1-16 + helpers/frontendToolInject (agent-leg pattern) · services/chat-service/app/services/frontend_tools.py:401 (panel_id enum — 'arc-inspector' ABSENT today) · services/composition-service/app/routers/arc.py:438/489/528/560 (get / patch / restore / assign-chapters — all legs drivable) · `grep -rn "plan-hub" frontend/tests/e2e` → 0 hits (confirms spec 24 H8.2 was never browser-smoked)

### Q-32-CHAPTERS-VIRTUALIZATION
REUSE — do not add a virtualization library. `@tanstack/react-virtual` is already a direct FE dependency and is already used for exactly this shape (a keyset-paged, lazily-growing chapter list) in `ManuscriptNavigator.tsx`. Builder instructions for M4 (Chapters section of `arc-inspector`):

1. DATA — new hook `frontend/src/features/studio/panels/useArcChapters.ts`. Mirror the keyset loop of `plan-hub/hooks/usePlanWindows.ts:120-143` (`fetchArc`): call `getChildren(bookId, { structureNodeId: arcId }, { cursor, limit: 100, token })` from `plan-hub/api.ts:33`; hold `{ items: SummaryNode[]; cursor: string | null; loading: boolean }`; on `loadMore()` re-fetch with `cursor` and APPEND (`cursor ? [...cur.items, ...page.items] : page.items`), stop when `next_cursor === null`. Carry the `gen.current` stale-response guard (usePlanWindows.ts:113,124,131) so an arc switch cannot land a late page from the previous arc. Do NOT reuse `usePlanWindows` itself — it is coupled to the Hub canvas (expanded-arc map → `laneLayout`).

2. VIEW — in the Chapters section, copy the virtualizer block from `ManuscriptNavigator.tsx`:
   - `import { useVirtualizer } from '@tanstack/react-virtual';` (ManuscriptNavigator.tsx:18)
   - `const virtualizer = useVirtualizer({ count: rows.length, getScrollElement: () => parentRef.current, estimateSize: () => ROW_H, overscan: 12 })` with `const ROW_H = 28;` (mirrors :39, :70-76)
   - render a `<div style={{ height: virtualizer.getTotalSize(), position: 'relative' }}>` and absolutely-position each row via `transform: translateY(${vi.start}px)` (:214-220)
   - infinite paging: an effect over `virtualizer.getVirtualItems()` that calls `loadMore()` when the trailing `more` sentinel row enters the window (:80-86), guarded in the hook so it never double-fetches.

3. THE TRAP — the scroll element MUST be its own bounded box. `ManuscriptNavigator`'s `parentRef` is a flex-sized `min-h-0 flex-1 overflow-y-auto` div (:174); the arc inspector's Chapters section instead lives inside the panel's own scrolling column, so an auto-height div gives the virtualizer no viewport to measure and windowing silently degrades to rendering every row. Give the list its own `ref={parentRef}` div with `max-h-[320px] overflow-y-auto`.

4. VIRTUALIZE UNCONDITIONALLY — drop the spec's "above ~200 rows" threshold. A conditional virtualize/plain-list branch means two render paths and remounts a stateful hook at the crossing; `ManuscriptNavigator` virtualizes at any size. The spec's "~200" is a perf rationale, not a required branch. (Default chosen here — PO can veto, but there is no cost to always-on.)

5. TEST — `frontend/src/features/studio/panels/__tests__/ArcInspector.test.tsx` must mock the virtualizer exactly as `ManuscriptNavigator.test.tsx:6-12` does (jsdom gives the scroll element zero size, so the real virtualizer renders zero rows and every assertion reds): `vi.mock('@tanstack/react-virtual', () => ({ useVirtualizer: (opts) => ({ getTotalSize: () => opts.count * 28, getVirtualItems: () => Array.from({ length: opts.count }, (_, index) => ({ index, start: index * 28, key: index })) }) }))`. Assert (a) member-chapter rows render, (b) the sentinel row firing calls `loadMore` once, (c) `getChildren` was called with the `{ structureNodeId }` axis.

*Evidence:* frontend/package.json:32 — `"@tanstack/react-virtual": "^3.14.5"` (already a direct dep). frontend/src/features/studio/manuscript/ManuscriptNavigator.tsx:18 (import), :39 (`const ROW_H = 26`), :70-76 (`useVirtualizer({count, getScrollElement, estimateSize, overscan: 12})`), :80-86 (virtual-window-driven `loadMore` infinite paging), :174 (bounded `min-h-0 flex-1 overflow-y-auto` scroll parent), :214-220 (`getTotalSize()` spacer + `translateY(vi.start)` rows). frontend/src/features/studio/manuscript/__tests__/ManuscriptNavigator.test.tsx:6-12 (the required jsdom mock of `@tanstack/react-virtual`). frontend/src/features/plan-hub/api.ts:33 (`getChildren`, `structure_node_id` axis, keyset `cursor`/`limit`). frontend/src/features/plan-hub/hooks/usePlanWindows.ts:14 (`CHILD_PAGE = 100`), :120-143 (`fetchArc` keyset accumulate + `gen.current` stale guard) — the loop to mirror. Counter-evidence that no new lib is needed: the only other virtualization mention in the FE is a stale TODO at frontend/src/features/knowledge/components/JobLogsPanel.tsx:17-18 suggesting react-window — ignore it; the repo already standardized on @tanstack/react-virtual.

### Q-32-X6-RESOURCE-REF-UNWRITTEN
REJECT BOTH CANDIDATES. Do not block on X-6, and do NOT split the panel ("core now, resource_ref leg later"). Arc-inspector ships the panel core AND the agent-deep-link leg in the SAME wave (Wave 2), because (a) X-6 is a SPEC SECTION to write, landing in the Wave 0 gate which precedes Wave 2 (plan-30:339, :345, :370, :784 "this is the first thing to write") — it is unbuilt work, not an external dependency (CLAUDE.md anti-laziness rule), and (b) every code seam already exists and is proven by a shipped twin. Delete OQ-X6 from 32 §7 and replace it with this instruction.

BUILDER STEPS (exact files/lines/tests):

1. AN-12 (X-6), Wave 0, into `docs/specs/2026-07-01-writing-studio/28_agent_native_studio.md` (do NOT fork it): `resource_ref = { kind: 'structure'|'outline'|'motif_application'|'canon_rule'|'thread', id: string, version?: number }`. `kind` is a CLOSED SET ⇒ it MUST be registered in `CLOSED_SET_ARGS` (Frontend-Tool-Contract IN-rule) and the resolver MUST return `result.error` on an unknown kind — never a silent no-op (the `panel_id` bug class; the shipped error shape is `studioUiNav.ts:34`).

2. Carry it on `ui_open_studio_panel`, NOT a new tool — PO-3 sealed "one name for one concept" (plan-30 §0). In `services/chat-service/app/services/frontend_tools.py`: add an optional `resource_ref` object arg to `UI_OPEN_STUDIO_PANEL_TOOL` (:391 — today it has `panel_id` ONLY), add `arc-inspector` to the `panel_id` enum (:404), then regenerate `contracts/frontend-tools.contract.json` via `WRITE_FRONTEND_CONTRACT=1 pytest`.

3. Bus event — mirror `planFocusNode` VERBATIM. `frontend/src/features/studio/host/types.ts:66`: add `| { type: 'arc'; arcId: string; version?: number }` to `StudioBusEvent`; in `applyBusEvent` (:109-110) add `case 'arc': return { ...base, arcFocusId: e.arcId, arcFocusVersion: e.version, arcFocusSeq: (s.arcFocusSeq ?? 0) + 1 }`. THE SEQ BUMP IS LOAD-BEARING — without it, the agent pointing at the SAME arc twice is a silent no-op (exactly why `planFocusSeq` exists; asserted at `planFocusBus.test.ts:19-21`).

4. Resolver — `frontend/src/features/studio/agent/studioUiNav.ts:27-38` (`ui_open_studio_panel` case): today it calls `host.openPanel(panelId)` and DROPS opts (:37). Pass params through (the host already accepts them), and when `resource_ref.kind === 'structure'` the effect ALSO runs `host.publish({ type: 'arc', arcId: ref.id, version: ref.version })` (+ openPanel('arc-inspector') if closed). Unknown or malformed kind → `{ result: { opened: false, error: ... } }`, no effect.

5. Consumer — `ArcInspectorPanel` subscribes via `useStudioBusSelector((s) => s.arcFocusId)` + the seq, exactly as `PlanHubPanel.tsx:121-127` does.

6. TESTS (write these three): (a) new `frontend/src/features/studio/host/__tests__/arcFocusBus.test.ts` — clone `planFocusBus.test.ts` including the same-arc-twice-still-bumps-seq case; (b) extend `frontend/src/features/studio/agent/__tests__/studioUiNav.test.ts` — `resource_ref` kind `structure` opens the panel AND publishes; an UNKNOWN kind returns `result.error` with NO effect (the silent-no-op guard); (c) `frontendToolContract.test.ts` stays green (py enum == contract enum == openable set, per PO-3).

7. Wave DoD: `/review-impl` at wave close (PO run policy #2).

FALLBACK (default the PO may veto): if Wave 2 opens and the AN-12 section still is not on disk, do NOT stall and do NOT file a defer row — arc-inspector consumes exactly ONE variant (`kind:'structure'`), so implement steps 2-6 with that single enum member and write the AN-12 section from the shipped shape. A spec paragraph is never a blocker.

*Evidence:* frontend/src/features/studio/host/StudioHostProvider.tsx:52 — `openPanel: (panelId, opts?: { focus?, title?, params?: Record<string, unknown>, component? })` — params ALREADY supported (live precedents: `openPanel('agent-mode', { runId })`, `openPanel('settings', { tab })` in frontend/src/features/studio/host/studioLinks.ts). · frontend/src/features/studio/host/types.ts:66 + :109-110 — the `planFocusNode` one-shot focus event + `applyBusEvent`'s `planFocusSeq` bump = the exact `bus.publish({type:'arc', arcId})` pattern, already shipped. · frontend/src/features/studio/panels/PlanHubPanel.tsx:121-127 — the consumer side (`useStudioBusSelector`). · frontend/src/features/studio/agent/studioUiNav.ts:37 — `effect: (host) => host.openPanel(panelId)` DROPS opts (the only real code hole, ~10 lines). · services/chat-service/app/services/frontend_tools.py:391-404 — `UI_OPEN_STUDIO_PANEL_TOOL` carries `panel_id` only; no `params`/`resource_ref`, and `arc-inspector` is absent from the enum. · docs/specs/2026-07-01-writing-studio/30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md:339 (X-6 = "Write spec 28's AN-12 resource_ref section", size S), :345 (Wave 0 gate), :370 (Wave 2 = arc-inspector, consumes X-6), :784 ("This is the first thing to write") — Wave 0 precedes Wave 2, so X-6 exists before the panel builds. · plan-30 §0 PO-3 — RETIRE `ui_show_panel`, fold into `ui_open_studio_panel` ⇒ the deep-link arg belongs on `ui_open_studio_panel`.

### Q-32-NONCONTIGUOUS-WARN-ONLY
CONFIRMED warn-only — and the "N" in the chip must come from the SERVER, not the client. Three concrete instructions:

(1) BACKEND — add `gap_count` to the derived block, in the SAME edit as BE-A1 (M1). In `services/composition-service/app/db/repositories/structure.py` `derived_blocks()` (the per-row loop at :300-328, which already has `cc`/`min_so`/`max_so`/`ordered`/`distinct` from the dense_rank CTE), emit one additive key alongside `is_contiguous`:
    if cc == 0 or is_contig:            gap_count = 0
    elif ordered < cc or distinct < cc:  gap_count = None   # unordered / duplicate positions — NOT countable, never fabricate an N
    else:                               gap_count = (max_so - min_so + 1) - cc
`gap_count` is in dense-ranked ORDINALS (positions missing from the arc's span in the book's reading order), the same unit as `span.{from_order,to_order}`. It ships to BOTH doors for free, because BE-A1 already replaces `out["span"] = await structures.span(node.id)` with `(await structures.derived_blocks(node.book_id)).get(node.id)` at `arc.py:455` AND `mcp/server.py:4255`. ⚠ Do NOT touch `StructureRepo.span()` (:641-686) — the packer (`lenses.py:322`) depends on its RAW keys; BE-A1 already locks this.

(2) FRONTEND — widen `ArcDerived` in `frontend/src/features/plan-hub/types.ts:52-57` with `gap_count: number | null` (additive; `laneLayout.ts:34` keeps using the boolean for the segmented band). The Chapters section of `ArcInspectorBody.tsx` renders, from the detail payload only:
    is_contiguous === true             → render nothing
    is_contiguous === false, gap_count > 0 → "⚠ Non-contiguous — {{count}} gaps in the reading order" (i18n plural)
    is_contiguous === false, gap_count === null → "⚠ Non-contiguous — some chapters have no reading position, or share one"
It renders as a muted/amber chip in the section header — NEVER an error banner, never a red state, never a blocking dialog.
⚠ FORBIDDEN: deriving the gap count in the client from the loaded chapter window. The children route is keyset-paged (`plan-hub/api.ts:33`) and `laneLayout.ts:118` segments are LOADED-only; a paged join against the complete set reports not-yet-loaded chapters as gaps. And raw `story_order` is strided ×1000 (`structure.py:270-277`), so a client min/max diff reports every arc as non-contiguous.

(3) WARN-ONLY IS ENFORCED BY A TEST, not by a comment. `useArcInspector.ts` must not read `is_contiguous`/`gap_count` in any write path: no disabled button, no confirm-gate, no validation refusal on assign-chapters, remove-chapter (BE-A3), PATCH, archive, restore, or create. Add to the M4 vitest suite: render the panel with a fixture whose `is_contiguous: false, gap_count: 3`, assert the chip is present AND that "+ assign chapters", "remove", and the identity/status controls are all enabled and their mutations fire. Backend stays as-is — grep confirms no repo/route/engine write path reads `is_contiguous` today, and none may be added.

Milestones: gap_count → M1 (with BE-A1). Chip + states → M2. The no-block write test → M4.

*Evidence:* services/composition-service/app/db/repositories/structure.py:244-328 (derived_blocks; docstring :252 "is_contiguous is warn-only (BA6)"; dense_rank rationale :270-277; per-row derivation :300-328 — boolean only, no gap count on the wire) · structure.py:641-686 (span(): RAW strided keys, "contiguity is a warning signal, not an error" :646-647 — packer-owned, do not touch: lenses.py:322) · services/composition-service/app/routers/arc.py:429 (list route emits the derived block), arc.py:455 (out["span"] = await structures.span(node.id) — the BE-A1 site) · services/composition-service/app/mcp/server.py:4227 ("warn-only is_contiguous"), server.py:4255 (same BE-A1 site, MCP door) · frontend/src/features/plan-hub/types.ts:55 (is_contiguous: boolean — the only FE field) · frontend/src/features/plan-hub/layout/laneLayout.ts:34,117-118 ("false ⇒ segmented lane + warn chip"; segments are "the lane's LOADED chapters" — the paged-window trap) · docs/specs/2026-07-01-writing-studio/23_book_architecture.md:165 (BA6) · 32_arc_inspector.md:192. Grep for is_contiguous across services/composition-service/app: zero hits in any write path (update/move/archive/restore/assign_chapters) — warn-only holds today.

### Q-32-OCC-SERIALIZE-WRITE-CHAIN
CONFIRMED AS STATED — every premise checks out against code, and both patterns already exist to copy. It is a work item for M3, not an open design question. Build `frontend/src/features/studio/panels/useArcInspector.ts` with these exact mechanics (3 refinements the spec left implicit):

(1) SERIALIZE — copy the shape of useSceneInspector.ts:38-45,63-101 verbatim: a `nodeRef` live mirror of the arc (`useEffect(() => { nodeRef.current = node }, [node])`), a `chainRef = useRef<Promise<void>>(Promise.resolve())`; `patch(p)` captures `targetId = nodeRef.current?.id` NOW, and the inner `run()` re-reads `nodeRef.current` for the version (never a closure) and aborts if `current.id !== targetId` (selection moved ⇒ drop, never apply to the new arc). Chain with `const next = chainRef.current.then(run, run); chainRef.current = next; return next;` — `.then(run, run)` (both handlers) so a FAILED link does not break the chain.

(2) RE-SEED SYNCHRONOUSLY ON SUCCESS — `nodeRef.current = updated; setNode(updated)` before `saving` flips false. If the inspector reads the react-query arc cache (it does — spec §2 says reuse `['plan-hub','arcs',bookId]`), ALSO `qc.setQueryData` the arc detail key in `onSuccess`, not only `onSettled`'s invalidate (usePlanNodeWrites.ts:69-75 — invalidate is async, controls re-enable first, next edit sends a stale If-Match).

(3) 412 RECOVERY = READ THE ERROR BODY, DO NOT RE-GET. `apiJson` already attaches the parsed body to the thrown error (`frontend/src/api.ts:156-162` — `{status, code, body}`), and composition raises FastAPI `HTTPException(detail={...})`, so the shape on the client is `err.body.detail = {code:'STRUCTURE_VERSION_CONFLICT', current:{…}}` (arc.py:504-508). Handler:
    const status = (e as {status?: number}).status;
    const detail = (e as {body?: {detail?: {code?: string; current?: ArcNode}}}).body?.detail;
    if (status === 412 && detail?.code === 'STRUCTURE_VERSION_CONFLICT' && detail.current) {
      nodeRef.current = detail.current; setNode(detail.current);
      setError('This arc changed elsewhere — reloaded. Re-apply your edit.');
    } else { setError(e instanceof Error ? e.message : 'Failed to save'); }
Keep a one-line defensive `GET /arcs/{id}` fallback ONLY when `detail.current` is missing. (useSceneInspector's re-GET predates D-K8-03 — do not copy it.)

(4) "KEEP THE USER'S IN-PROGRESS TEXT" — the re-seed in (3) replaces the row and WOULD clobber a textarea bound straight to `node.<field>`. So: text fields (title/summary/goal/synopsis) hold LOCAL draft state (`useState` seeded from the node, commit on debounce/blur), and their resync-from-prop effect is gated on `!dirty`; the field `key` must NOT include `version` (a version-keyed remount IS the clobber). Only non-dirty fields re-sync from the fresh row. Instant-commit controls (status `<select>`, roster chips) carry no draft text and simply re-render from the fresh row. The debounced text commit must bind its target arc id (`debounced-write-must-bind-its-target-entity`).

(5) NO VERSION on move/archive/restore/assign-chapters — confirmed at arc.py:516,528,540,560 (no `If-Match` param) and mirrored FE-side at plan-hub/api.ts:186-249. Send no header; do not invent one. `If-Match` becomes REQUIRED (428) on PATCH /arcs/{id} only — that is BE-A2, a separate slice.

M3 DoD TESTS (frontend/src/features/studio/panels/__tests__/useArcInspector.test.ts — mirror useSceneInspector.test.ts:64 and :77):
 a. 'serializes rapid back-to-back edits so the 2nd sends the version the 1st bumped' — fire `patch(a)` and `patch(b)` synchronously WITHOUT awaiting; patchArc mock returns v1→v2; assert call#2 carried version 2, both writes landed, zero 412s, nothing dropped.
 b. '412 seeds `current` from the error body, keeps the in-progress text, and the retry succeeds' — patchArc rejects once with `Object.assign(new Error('Precondition Failed'), {status:412, body:{detail:{code:'STRUCTURE_VERSION_CONFLICT', current:{…, version:9}}}})`; assert (i) error string is exactly 'This arc changed elsewhere — reloaded. Re-apply your edit.', (ii) `node.version === 9` and the getArc mock was NEVER called (no second round-trip), (iii) the next `patch` sends version 9 and RESOLVES.
 c. component test: a dirty/focused textarea keeps its text across a 412 re-seed (the clobber guard in (4)).
 d. BE (composition-service): PATCH /arcs/{id} with no If-Match ⇒ 428 (BE-A2); move/archive/restore/assign-chapters each succeed with no If-Match header.

*Evidence:* services/composition-service/app/routers/arc.py:504-508 (412 detail = {code:'STRUCTURE_VERSION_CONFLICT', current:{…}}); arc.py:516,528,540,560 (move/delete/restore/assign-chapters declare no If-Match Header param); frontend/src/api.ts:156-162 (D-K8-03: thrown error carries {status, code, body} — the 412 `current` is readable without a re-GET); frontend/src/features/studio/panels/useSceneInspector.ts:38-45,63-101 (nodeRef mirror + chainRef.then(run,run) serialization; its 412 path re-GETs — do not copy that half); frontend/src/features/plan-hub/hooks/usePlanNodeWrites.ts:69-75 (synchronous qc.setQueryData re-seed in onSuccess, because onSettled invalidate is async); frontend/src/features/plan-hub/api.ts:186-249 (moveArc/archiveNode/restoreNode/assignChapters send no If-Match); docs/specs/2026-07-01-writing-studio/32_arc_inspector.md §8 + §3.4 (spec already locks seed-and-say + the two hard rules); spec §5 BE-A2 (If-Match optional on PATCH /arcs ⇒ make it 428-required).

### Q-32-DOD-GREP-GATES
KEEP both grep gates — they are cheap tripwires and DoD #4 (browser smoke) + #5 (pack-effect tests) carry the real behavioral proof — but REWRITE them, because as written they are broken three ways (all verified against code). Builder: replace §10 DoD #2 and #3 of 32_arc_inspector.md with the text below, and fix M5's row.

REPLACE DoD #2 WITH:
"2. `rg -nF "plan-drawer-arc-gap" frontend/src` -> ZERO hits. Scope is `frontend/src` ONLY. M5's 'zero grep hits repo-wide' is a SPEC BUG (corrected here): the token legitimately survives in 30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md:238, in this spec (:69,:270,:468,:475), in design-drafts/screens/studio/screen-arc-inspector.html (6 hits), and in .playwright-mcp/*.yml snapshots — do NOT edit prose/snapshots to chase a repo-wide zero. Reaching zero takes TWO edits, not one:
  (a) delete the `<p data-testid=\"plan-drawer-arc-gap\">` note at frontend/src/features/plan-hub/components/PlanDrawer.tsx:351, together with ArcFacets + rosterKeysOf (per §3.5);
  (b) frontend/src/features/plan-hub/components/__tests__/PlanDrawer.test.tsx — drop the negative assertion at :88, and REWRITE the test case at :110 ('arc/saga: renders the minimal arc summary + the reuse-gap note, not outline facets') into 'arc/saga: embeds the arc inspector', asserting the embedded inspector's root data-testid renders. Deleting the assertion alone is a FAIL of this DoD item: it leaves a test whose NAME lies and silently drops the only arc-variant coverage PlanDrawer has."

REPLACE DoD #3 WITH:
"3. The 5 NO-FE-CONSUMER routes have a consumer — proven BY EXPORTED FUNCTION, not by URL. The spec's original `grep -rn \"arcs/\\${\" frontend/src` is broken twice: (i) it can NEVER match `create` — the route is book-keyed `POST /books/{book_id}/arcs` (services/composition-service/app/routers/arc.py:466), so its FE literal is `${COMP}/books/${bookId}/arcs`, which ends in `arcs` and contains no `arcs/${` (same for assign-chapters); (ii) run verbatim under ripgrep it ERRORS ('regex parse error: repetition quantifier expects a valid decimal' — `$` is an anchor in Rust regex), so it only ever 'worked' under GNU grep. Gates:
  - `rg -n 'export (async )?function (createArc|getArc|updateArc|archiveArc|restoreArc)\\b' frontend/src` -> exactly 5 hits, all in the arc-inspector api layer.
  - tripwire: `rg -nF 'arcs/${' frontend/src` -> >=5 hits = get + patch + delete + restore + the pre-existing moveArc (plan-hub/api.ts:196). Note -F (fixed string) is REQUIRED.
  - `create` is proven by DoD #4.2 (browser: create a saga -> it appears in plan-hub's lanes without a reload), which already covers it end-to-end. The grep never had to.
  NAMING: do NOT reuse `archiveNode`/`restoreNode` (plan-hub/api.ts:147,153) — those call `/outline/nodes/{id}` (chapters/scenes), a DIFFERENT route family. Use `archiveArc`/`restoreArc`. (The '5 NO-FE-CONSUMER' premise itself is CONFIRMED correct: no FE code touches /arcs/{id} today except moveArc.)"

FIX M5's DoD cell: change "`plan-drawer-arc-gap` returns zero grep hits repo-wide" to "...zero grep hits in `frontend/src` (see DoD #2 — repo-wide is unsatisfiable and not the gate)".

Rationale for keeping rather than dropping the gates: they cost one command each, they are the tripwire that catches a builder who ships the panel but forgets to remove the "not built yet" lie (the exact GG-1 failure this wave closes), and they cannot be talked past the way a checklist item can. They are not a substitute for DoD #4/#5 and this rewrite says so explicitly.

*Evidence:* frontend/src/features/plan-hub/api.ts:196 — the ONLY `arcs/${` hit in frontend/src today (moveArc). services/composition-service/app/routers/arc.py:466 — `@router.post("/books/{book_id}/arcs")`: create is book-keyed, so DoD #3's pattern can never match it. frontend/src/features/plan-hub/components/PlanDrawer.tsx:351 — the gap note. frontend/src/features/plan-hub/components/__tests__/PlanDrawer.test.tsx:88,110 — the two test refs that also must go (:110's case asserts the note EXISTS). frontend/src/features/plan-hub/api.ts:147,153 — archiveNode/restoreNode hit /outline/nodes/{id}, not /arcs/{id} (name-collision hazard; also confirms the 5-route premise). Verified live: `rg -n 'arcs/${' frontend/src` -> "regex parse error: repetition quantifier expects a valid decimal"; `rg -nF` works. Repo-wide grep for plan-drawer-arc-gap returns hits in docs/specs/2026-07-01-writing-studio/30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md:238, 32_arc_inspector.md:69/270/468/475, design-drafts/screens/studio/screen-arc-inspector.html, .playwright-mcp/*.yml.

### Q-32-EMPTY-STATE-DECOMPILER-CTA
WIRE THE LINK — the plan-hub decompiler CTA exists and is live today. Do NOT drop it.

Build the Arc Inspector §3.4 empty state (M2) as follows.

WHERE: the arc-inspector panel's empty branch (new file `frontend/src/features/studio/panels/ArcInspectorEmptyState.tsx`, rendered by the arc-inspector panel when its arc list resolves with zero arcs — gate on `isSuccess && arcs.length === 0`, NEVER on `!data`, so it cannot flash over an unfinished read; mirror `PlanHubPanel.tsx:144-171` which orders "loading" before "empty").

RENDER exactly three things, never a blank pane:
1. Headline + body: "No arcs yet — the spec tree is what steers generation."
2. PRIMARY CTA "Create the first saga" — the in-panel write (the arc-create path M2 already builds).
3. SECONDARY LINK (this is the answer to the question):
   label: "Open the Plan Hub to extract it from the manuscript →"
   action: `openPanel('plan-hub', { focus: true, params: { bookId } })`
   — use the studio host's `openPanel` (`StudioHostProvider.tsx:52`), NEVER `navigate()` (PH24/DOCK-7, same rule PlanHubPanel already follows at lines 68-74/164/191).

CRITICAL — word the link for the DESTINATION, not the outcome. Do not label it "Extract the plan" / "Run the decompiler". Reason (from code): plan-hub only renders `plan-hub-extract-cta` when `specEmpty`, and `specEmpty = zero arcs AND zero unassigned chapters` (`usePlanHub.ts:224-228`). "No arcs" is a STRICTLY WEAKER condition. In the normal post-decompile state (scenes/chapters extracted, arc-grouping LLM step not yet run) the arc list is empty but the spec is NOT — plan-hub then renders the canvas + the "N chapters in no arc" notice (`PlanHubPanel.tsx:241-252`) and the extract button is ABSENT. A link promising that button would dead-end there — exactly the PH7 visible-fallback bug this repo already fixed once. Naming the destination is truthful in BOTH worlds, and plan-hub self-selects the correct state on arrival (extract CTA when there is no spec; unassigned strip when there is).

OPTIONAL REFINEMENT (do it only if the arc-inspector panel already has an unassigned/unplanned count in hand — do NOT add a new query for it): when that count > 0, swap the secondary line to "{{count}} chapters are extracted but grouped into no arc — ask the agent to group them into arcs" and keep the same `openPanel('plan-hub', …)` action. Arc grouping is `composition_arc_import_analyze`, a Tier-W MCP tool by design (documented at `frontend/src/features/plan-hub/api.ts:92-100`) — it is an agent ask, not a button, so do not invent an HTTP endpoint for it (MCP-first invariant).

TEST (`frontend/src/features/studio/panels/__tests__/ArcInspectorEmptyState.test.tsx`):
- renders the headline + both CTAs when arcs resolve empty (never a blank pane);
- renders NOTHING (or the loading state) while the arc query is still in flight — assert the empty state is absent, guarding absent≠empty;
- clicking the secondary link calls `openPanel` with exactly `('plan-hub', { focus: true, params: { bookId } })` — assert the panel id string, since it is the openable-catalog id (`catalog.ts:190`) and a typo is a silent no-op;
- clicking "Create the first saga" calls the arc-create handler.

Default I am picking that the PO can veto: the secondary link is a plain text link (not a second filled button), so "Create the first saga" stays the single visual primary.

*Evidence:* EXISTS — plan-hub decompiler CTA: frontend/src/features/plan-hub/components/PlanEmptyState.tsx:60-70 (button data-testid="plan-hub-extract-cta", "Extract the plan from the manuscript") → frontend/src/features/plan-hub/hooks/useExtractPlan.ts:39 (materializeScenes) → frontend/src/features/plan-hub/api.ts:101-108 (POST {COMP}/books/{bookId}/materialize-scenes, the SC6 decompiler; deterministic/$0/EDIT-gated). Rendered at frontend/src/features/studio/panels/PlanHubPanel.tsx:159-171, gated on view.specEmpty.

LINK MECHANISM: panel id 'plan-hub' is in the openable catalog — frontend/src/features/studio/panels/catalog.ts:190; host API openPanel(panelId, {focus, params}) — frontend/src/features/studio/host/StudioHostProvider.tsx:52; existing precedent for openPanel-not-navigate deep links — PlanHubPanel.tsx:65-78 and :164.

THE WRINKLE (why the label must name the destination): frontend/src/features/plan-hub/hooks/usePlanHub.ts:224-228 — `specEmpty = arcsQuery.isSuccess && shell.length === 0 && windowsResult.unassignedLoaded && layout.unassigned.length === 0`. Zero arcs alone does NOT satisfy it, so post-decompile the extract CTA is not rendered (PlanHubPanel.tsx:241-252 shows the unassigned notice instead). Arc grouping is an MCP tool, not an endpoint — frontend/src/features/plan-hub/api.ts:92-100.

### Q-32-INVERSE-GAP-ARC-APPLY
CONFIRMED AS WRITTEN — do NOT build arc apply/template-drift agent parity in spec 32 (Wave 2). Spec 32 §7's claim is true at HEAD and the panel has zero dependency on those two tools (its every action is deterministic REST CRUD). Wave 2 builders: change nothing; leave §7's wording; the ONE thing Wave 2 must still do is create `frontend/src/features/studio/agent/handlers/arcEffects.ts` with the single broad `/^composition_arc_/` registration (spec 32 §6 step 8) so Wave 4 extends it rather than registering a second pattern. Ownership stays: BE-8 → spec 34 M5, tracked by the existing defer row D-ARC-APPLY-MCP-WRAPPER. No new defer row.

BUT one AMENDMENT the Wave-4 builder must have, because plan 30 and spec 34 both mis-state it and the mis-statement would cause a duplicate engine (the css-var-duplicated-across-two-consumers bug class the plan itself warns about):

plan 30 line 302 and spec 34 §5 BE-8 / §M5 say `apply_arc_to_spec` is "genuinely unwritten ⇒ M (a real engine: rescale + roster-bind + pacing→tension + ledger)". FALSE. The engine EXISTS and is tested: `app/engine/arc_apply.py:325 async def arc_apply(template, structure_node, *, created_by, structure_repo, outline_repo, applications_repo, resolve_motifs, cast_index, cast_names, roster_bindings, k_ceiling, high_threshold, min_scenes, max_scenes, replace)`. It materializes a scene per distributed beat, writes tension FROM the rescaled pacing curve, emits the motif_application ledger, and STAMPS `structure_node.arc_template_id` + `template_version` (the exact provenance the shipped `?scope=arc_template_drift` read keys on) — all in one transaction, with ArcApplyConflict/replace semantics. It has NO production caller today (only `build_apply_plan` is wired: routers/arc.py:56, routers/plan.py:49); it is dead-but-green code.

So BE-8 / M5 is, concretely:
1. ADD `async def apply_arc_to_spec(pool, *, book_id, project_id, arc_template, roster_bindings, replace, idempotency_key, created_by) -> dict` to `app/engine/arc_apply.py` as a THIN ADAPTER (mirror `extract_template_from_arc` at arc_apply.py:652, which is the already-working sibling seam — note `composition_arc_extract_template` is therefore NOT a stub; only apply + drift are). It must: resolve/create the target arc `structure_node` for `book_id` (reuse StructureRepo; if the Work has no arc node, create one and stamp provenance — do not mint chapters), build the repos (StructureRepo/OutlineRepo/MotifApplicationRepo(pool)), build `resolve_motifs`/`cast_index`/`cast_names` the way `routers/plan.py`'s materialize + `engine/grounded_plan.py:135` do, pull `k_ceiling=settings.compose_diverge_k, high_threshold=settings.plan_high_tension_threshold, min_scenes=settings.plan_min_scenes_per_chapter, max_scenes=settings.plan_max_scenes_per_chapter`, then `await arc_apply(...)` and map `ArcApplyConflict` → `{success:false, outcome:"applied_conflict"}`. DO NOT write a second rescale/pacing/ledger engine.
2. ADD `build_template_drift(pool, *, arc_node, user_id)` to `app/engine/arc_conformance.py` as a delegate into the already-shipped `compute_arc_report(..., by_structure=False)` that `routers/conformance.py:390` uses. Do not write a second drift engine.
3. Because (1) is an adapter, BE-8 re-sizes S+S (not S+M). Its M5 DoD is unchanged and is the parity assertion: both MCP tools stop returning `pending_dependency`, and an agent-driven apply + drift returns the SAME answer as the panel on the same arc.
4. Follow-through spec 34 already flags: once `apply_arc_to_spec` lands, DELETE the AT-6 FE provenance stamp (the 2-call create-arc-then-assign-chapters workaround) — do not leave a second writer of `structure_node.arc_template_id`.

*Evidence:* services/composition-service/app/mcp/server.py:4602-4605 (getattr "apply_arc_to_spec" → _pending_engine) and :4698-4700 (getattr "build_template_drift" → _pending_engine) — both symbols absent, so spec 32 §7 is accurate. Counter-evidence to the sizing claim: services/composition-service/app/engine/arc_apply.py:325 `async def arc_apply(...)` (full spec-layer engine incl. provenance stamp of arc_template_id + template_version), tested at services/composition-service/tests/integration/db/test_arc_apply_roundtrip.py:167 and :295-301 (conflict → replace), with zero production callers (grep "engine.arc_apply" over app/ → only build_apply_plan at routers/arc.py:56 + routers/plan.py:49). Working sibling seam to mirror: app/engine/arc_apply.py:652 extract_template_from_arc. Drift orchestrator to delegate to: app/routers/conformance.py:390 + app/engine/arc_conformance_orchestrate.py:38 compute_arc_report(by_structure=False).

### Q-32-403-READONLY-GRANT-SOURCE
REUSE THE GRANT THE SERVER ALREADY SENDS — no probe, no new BE route, no new prop plumbing beyond the existing `writes`.

**The fact:** `GET /v1/books/{book_id}` already returns a per-caller `access_level` ∈ `owner|manage|edit|view|none` (book-service `internal/api/server.go:957` computes it, `:987` emits it; the list route does the same at `:857`/`:885`). The FE **drops it**: `Book` (frontend/src/features/books/api.ts:6-24) does not declare `access_level`, and `grep -rn "access_level" frontend/src` returns ZERO hits. This is the `rest-write-mirror-drops-fields` bug class in read form — the grant is on the wire, nobody reads it.

**Builder instructions (exact):**

1. `frontend/src/features/books/api.ts:6` — add to `type Book`:
   `access_level?: 'owner' | 'manage' | 'edit' | 'view' | 'none';`  (server-computed; never sent by the client.)

2. NEW `frontend/src/features/books/hooks/useBookGrant.ts`:
```ts
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { booksApi, type Book } from '../api';

export type BookGrant = NonNullable<Book['access_level']>;

/** The E0 grant the caller holds on this book. Reads `access_level` off the book
 *  detail the studio ALREADY caches under ['book', bookId] — no extra fetch, no probe.
 *  FAILS CLOSED: while unresolved (loading/error/undefined) canEdit === false, so a
 *  control that would 403 is never rendered even for one frame. */
export function useBookGrant(bookId: string | null) {
  const { accessToken } = useAuth();
  const q = useQuery({
    queryKey: ['book', bookId],
    queryFn: () => booksApi.getBook(accessToken!, bookId!),
    enabled: !!accessToken && !!bookId,
    staleTime: 5 * 60_000,
  });
  const level = q.data?.access_level;
  return {
    level,
    canEdit: level === 'owner' || level === 'manage' || level === 'edit',
    resolved: q.isSuccess && level !== undefined,
    loading: q.isLoading,
  };
}
```
   The key `['book', bookId]` is the SAME key `BookSettingsPanel.tsx:32` and `GlossaryPanel.tsx:34` already use with `booksApi.getBook` — so inside the studio this is a cache hit, not a second request. Do not invent a new key.

3. DOCK PANEL host (`ArcInspectorPanel.tsx`, the new panel): `const { canEdit, resolved } = useBookGrant(host.bookId);` (`host.bookId` is the studio host's book — same source `QualityCanonPanel.tsx:33` uses). Render `<ArcInspectorBody … writes={canEdit ? arcWrites : undefined} />`. `ArcInspectorBody` keeps PlanDrawer's contract verbatim (`PlanDrawer.tsx:47-55`): `writes` omitted ⇒ every mutation control (New arc/saga, field inputs, Override-here, Archive, Restore, save chips) is UNMOUNTED — not disabled — plus the single line *"You have view access to this book."* (§3.4's 403 row). Because it fails closed, a `view` grant and an unresolved grant render identically read-only; controls appear only once `canEdit` is true.

4. DRAWER host: unchanged contract — `PlanDrawer` gets `writes` from `usePlanHub` (`usePlanHub.ts:208`, `usePlanNodeWrites`) and passes it into `ArcInspectorBody` exactly as spec §3.5 AI-4 shows. ONE-LINE hardening while you're there (same hook, keeps the two hosts from disagreeing): in `usePlanHub.ts` return `writes: canEdit ? nodeWrites : undefined` using `useBookGrant(bookId)`.

**Tests (name them in the slice DoD):**
- `useBookGrant.test.tsx` — `access_level:'view'` ⇒ `canEdit=false`; `'edit'|'manage'|'owner'` ⇒ true; query still loading ⇒ `canEdit=false` (fail-closed).
- `ArcInspectorPanel.test.tsx` — with `['book',id]` seeded `access_level:'view'`, `queryByTestId('arc-inspector-archive' | '-new-arc' | '-save')` are ALL null and `arc-inspector-readonly-note` is present; with `'edit'` they are present.

**Rejected alternatives:** (a) a *probe request* — it learns the grant only AFTER a 403, which is exactly what §3.4 forbids ("never render a control that would 403"); (b) a NEW `writes` source threaded from the studio host — the grant is not a prop, it is a server fact, and duplicating it would be a second name for one concept; (c) `useCollaborators` / `GET /v1/books/{id}/collaborators` — owner-only (book-service `collaborators.go`, server.go:290 "owner-only collaborator management"), so it 403s for the very users we need to detect; (d) `GET /internal/books/{id}/access` (`server.go:190`) — internal S2S token only, not reachable from the browser.

**PO veto point (default chosen, say so if wrong):** `manage` is treated as edit-capable (it is ≥ EDIT in book-service's ordered `GrantLevel`, `collaborators.go:23-27`, and composition's arc PATCH gates on `GrantLevel.EDIT` at `arc.py:498`). If the PO wants `manage` to be admin-only-not-author, flip one line in `useBookGrant`.

*Evidence:* services/book-service/internal/api/server.go:957 + :987 — `GET /v1/books/{id}` computes and returns `access_level` (owner|manage|edit|view|none) for the caller; frontend/src/features/books/api.ts:6-24 — `type Book` omits `access_level` and `grep -rn "access_level" frontend/src` = 0 hits (the fact is on the wire, unread); frontend/src/features/studio/panels/BookSettingsPanel.tsx:31-35 — the studio already caches that exact payload under `['book', bookId]` via `booksApi.getBook`, so the hook is a cache hit; frontend/src/features/plan-hub/components/PlanDrawer.tsx:47-55 — the `writes`-omitted read-only contract to mirror; services/composition-service/app/routers/arc.py:498 — arc PATCH gates on `GrantLevel.EDIT`, so edit|manage|owner are exactly the write-capable levels.

## Not a question (already answered by code / a sealed decision)
- **Q-32-UI-SHOW-PANEL-X5** — **RETIRE `ui_show_panel`. This is not open — it is SEALED as PO-3** (`30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md:21`: "RETIRE `ui_show_panel` — fold it into `ui_open_studio_panel` (one name for one concept) … X-5 becomes a retirement, not an enum-add"). Spec 36 already depends on it in that form (`36_editor_craft_ports.md:8` — "X-5 (`ui_show_panel` retirement)"). "Add it to the enum" is dead; do NOT re-open it. Spec 32 is correct that it does not depend on the outcome — no change to spec 32 is needed beyond deleting the "retire vs enum" phrasing from OQ-6 and citing PO-3.

CONCRETE BUILD INSTRUCTION (Wave 0 / X-5 — the whole retirement, so nobody re-derives it at 3am):

1. `services/chat-service/app/services/frontend_tools.py` — delete `UI_SHOW_PANEL_TOOL` (:335-358, the free-string `panel` arg that caused the silent-no-op), its registry entry (:655), and `"ui_show_panel"` from the frontend-tool name set (:52); fix the stale module comment (:36).
2. `services/chat-service/app/services/tool_discovery.py:258` — remove `"ui_show_panel"` from `ALWAYS_ON_CORE_NAMES`.
3. **The "explicit non-studio path" PO-3 demands ALREADY EXISTS — do not build a new tool.** Outside the studio the only real panel surface is the book tabs, and `ui_open_book`'s `tab` arg is already a closed enum (`overview|translation|glossary|enrichment|wiki|settings`, frontend_tools.py:295-305). Inside the studio, `ui_open_studio_panel` (advertised via `frontend_tool_defs(studio=True)`, :670) is the replacement. Net: **zero capability is lost by the retirement** — that is the finding that makes this cheap.
4. `contracts/frontend-tools.contract.json` — regenerate (`WRITE_FRONTEND_CONTRACT=1 pytest`); the `ui_show_panel` block at :265-276 must disappear. The contract test (`py enum == contract enum == openable`) is the gate PO-3 names.
5. Frontend: `frontend/src/features/chat/nav/uiNav.ts` — drop `'ui_show_panel'` from `UI_TOOL_NAMES` (:19) and delete its `case` (:115-131, the `?panel=` resolver that returned `shown:true` with no dock tab). `frontend/src/features/chat/utils/serverKey.ts:37` — drop the entry. **DO NOT touch `PopoutHost.tsx:27`** — its `params.get('panel')` is the pop-out *window's own URL contract* written by `PopoutBridge`, not the agent; it is the only other `?panel=` reader in the repo and it survives the retirement untouched.
6. Keep the `panel`/`page` alias tolerance in `studioUiNav.ts:29-33` — post-retirement it is exactly the migration net for a weak model that still reaches for the old arg name.
7. Tests to update in the same commit: `frontend/src/features/chat/nav/__tests__/uiNav.test.ts:99-112` (delete the 2 cases), `frontend/src/features/studio/agent/__tests__/studioUiNav.test.ts:106-109` (keep `ui_show_panel` as the *unknown-tool* case — it now proves the retirement), `services/chat-service/tests/test_agent_surface.py:70`, `test_tool_discovery.py:632`, `test_frontend_tools.py:167`, and e2e `frontend/tests/e2e/specs/frontend-tools-liveness.spec.ts:92-94` (retarget the liveness case to `ui_open_studio_panel`).
- **Q-32-MOTIF-EDITOR-BYID** — ALREADY ANSWERED by the sibling spec, exactly where spec 32 §3.1 said it should be answered. Spec 33 (Wave 3) ships NO `motif-editor` panel at all — so there is no by-id open to decide, and all three candidate answers (bus slice / props.params / hiddenFromPalette) are moot.

THE ANSWER: motif detail/edit is a DRAWER INSIDE `motif-library`, not a panel. 33_motif_studio.md:247-252 (§3.1): "Detail is a drawer, create is an inline form, adopt is a modal, the graph is a section — none of them is a panel… Keeping detail a drawer sidesteps X-12 entirely. A future agent who 'improves' this by extracting a `motif-editor` panel has introduced the bug, not fixed it." §6 (:529-531) confirms: Wave 3's only two new panel ids are `motif-library` and `quality-conformance`, and "both are openable by a bare id (no `params`) ⇒ both go into the enum."

The code already has this shape and never had another: selection in `MotifLibraryView.tsx:40` is panel-local React state (`const [openId, setOpenId] = useState<string|null>(null)`), and `MotifDetailDrawer` takes `motif: Motif | null` — the resolved OBJECT from the parent, never an id it must resolve from a URL/bus/params. `MotifEditorForm.tsx` is a form component rendered inside that drawer. Repo-wide grep for `motif-editor|MotifEditorPanel` finds ZERO panel — only the `motif-editor-*` data-testid prefix on that form, plus 3 doc mentions (plan-30 X-12 twice, spec 32 §3.1 once).

CONCRETE BUILDER INSTRUCTION (Wave 3 / spec 33):
1. Do NOT create `frontend/src/features/studio/panels/MotifEditorPanel.tsx`. Do NOT add a `motif-editor` row to `panels/catalog.ts`, and do NOT add `"motif-editor"` to the `panel_id` enum in `services/chat-service/app/services/frontend_tools.py:402`. Wave 3's enum delta is exactly +2 (`motif-library`, `quality-conformance`) per spec 33 §6.
2. Port `MotifDetailDrawer` + `MotifEditorForm` UNCHANGED into `MotifLibraryPanel.tsx`, keeping `openId` as panel-local state (the existing `MotifLibraryView.tsx:40` shape). No bus slice, no `props.params`. `motif-library` opens by BARE ID from the palette/agent and lands on its list — never a dead panel, so it needs no addressing arg.
3. Consequence for spec 32's AI-1: `arc-inspector` needs `activeArcId` on the bus BECAUSE it is a detail-pane-over-a-selection with no list of its own. `motif-library` is the list, so it needs nothing. Do NOT mirror the arc bus slice for motifs — there is no `activeMotifId`, and adding one is a second home for a concept the drawer already owns.
4. Doc hygiene (fold into Wave 2 or Wave 3, ~4 lines, no code): plan-30 §8.2's X-12 row (`30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md:650`) still names `motif-editor` as a panel that "must be hiddenFromPalette". Strike `motif-editor` from that list and cite 33 §3.1 — spec 32 OQ-6 already schedules an amendment to that same row (to name the `scene-inspector` / `quality-canon` precedents); do both edits in one pass. Leave `workflow-editor` in X-12's list — it is Track C's (PO-2) and is not decided by either spec.
5. Guard against re-litigation: spec 33's §3.1 warning sentence IS the guard. A reviewer who finds a `motif-editor` panel id in `catalog.ts` or the `panel_id` enum has found a defect.

DEFAULT NOTED FOR PO VETO: if a future wave genuinely wants a standalone motif editor panel (it does not today), the precedent set by spec 32 AI-1 applies — bus slice + in-panel picker, IN the enum, never `hiddenFromPalette`. But that is a hypothetical; nothing in Waves 3-4 asks for it.
- **Q-32-REGISTRATION-CHECKLIST-GG8** — This is a work item (a GG-8 registration checklist), not an open question — and every claim in it verifies TRUE against HEAD. Build it exactly as written, with three precisions the spec left loose (a 3am builder would stall on all three):

VERIFIED AS STATED (no change):
- Step 2 category 'editor' IS a member of CATEGORY_ORDER (palette/useStudioCommands.ts:20 — `['editor','storyBible','knowledge','translation','enrichment','sharing','platform','discovery','jobs']`). X-2 confirmed real but not ours: catalog.ts:270 (`quality-canon`) declares `category: 'quality'`, which is in the StudioPanelCategory union but NOT in CATEGORY_ORDER.
- Step 5 both edits land where stated: panel_id enum at frontend_tools.py:402 (57 ids, ending `…,"quality-canon"`), description prose with the per-panel gloss clauses running to ~:479 (the 'plan-hub' clause is at :448). Append the arc-inspector clause right after the plan-hub clause.
- Step 6 regen-not-hand-edit is real: test_frontend_tools_contract.py:135 writes the JSON only under WRITE_FRONTEND_CONTRACT=1 and reds otherwise (:141).
- Step 4 = exactly 17 non-en locales (ar bn de es fr hi id ja ko ms pt-BR ru th tr vi zh-CN zh-TW).
- StudioPanelDef supports every field the step-2 row uses, incl. `guideBodyKey` (catalog.ts:93-111).
- Steps 1/1b/1c shape has exact prior art to copy: QualityCanonPanel.tsx:33 (`useQualityCanon(host.bookId, accessToken, props.params as CanonFocusParams | undefined)`) + useQualityCanon.ts:27 (`export interface CanonFocusParams`). Mirror it: ArcInspectorPanel → useArcInspector + `export interface ArcFocusParams`.

THREE PRECISIONS (bind these):
1. Step 8's "same barrel" is NOT a barrel file — it is `frontend/src/features/studio/agent/useStudioEffectReconciler.ts` and it takes TWO edits: (a) add `import { registerArcEffectHandlers } from './handlers/arcEffects';` alongside the four imports at :18-21; (b) call `registerArcEffectHandlers();` inside the once-only `useEffect` at :34-38 next to `registerTranslationEffectHandlers()`. Miss (b) and the handler file exists, unit-tests green, and NOTHING fires at runtime (the "built but unwired" bug class). Add `useStudioEffectReconciler.ts` to the touch-list; it is NOT on the DO-NOT-TOUCH list and must be edited.
2. Do NOT add any count assertion. The drift-lock is already SET equality, not a count: panelCatalogContract.test.ts:32-34 asserts `[...enumIds].sort() === OPENABLE_STUDIO_PANELS.map(p=>p.id).sort()`. So the three-way lock is enforced automatically by adding the catalog row + the enum id + regenerating the contract. Writing a `58==58==58` (or `62==62`) literal anywhere is the phantom-regression trap the spec warns about — the existing set-equality test is the whole DoD for the lock.
3. Insert the step-2 catalog row immediately after catalog.ts:190 (the `plan-hub` row) — same 'editor' cluster, same field shape: `{ id: 'arc-inspector', component: ArcInspectorPanel, titleKey: 'panels.arc-inspector.title', descKey: 'panels.arc-inspector.desc', category: 'editor', guideBodyKey: 'panels.arc-inspector.guideBody' }`. No `hiddenFromPalette` (arc-inspector is openable by bare id per AI-1), and `tourAnchor` stays omitted (step 9 skip: tours.ts).

Step 7 (host/types.ts): follow the existing `scene` precedent verbatim — `StudioBusEvent` union (:43-45), `StudioBusSnapshot` (:70-74), `applyBusEvent` switch (:92-98). Add `| { type: 'arc'; arcId: string }`, `activeArcId?: string`, and the `case 'arc': return { ...base, activeArcId: e.arcId };`.

DO NOT TOUCH list stands as written (StudioDock.tsx, StudioFrame.tsx, useStudioCommands.ts, UserGuidePanel.tsx, studioUiNav.ts, useStudioUiToolExecutor.ts) — all four of the first derive from catalog.ts, verified. Steps 9 (tours.ts) and studioLinks.ts stay skipped.

Commit steps 2+5+6 in ONE commit (the contract JSON is generated from the py enum; splitting them reds CI on either side).

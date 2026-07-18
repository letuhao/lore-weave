# Wave 2 — Arc Inspector · IMPLEMENTATION PLAN (BUILD DETAIL)

> **Wave:** 2 of `docs/specs/2026-07-01-writing-studio/30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md` §7
> **Spec:** [`32_arc_inspector.md`](../specs/2026-07-01-writing-studio/32_arc_inspector.md) · **Mock:** [`design-drafts/screens/studio/screen-arc-inspector.html`](../../design-drafts/screens/studio/screen-arc-inspector.html)
> **Closes:** **G-ARC-SPEC-CRUD** (P0, CONFIRMED) · **DBT-06** (`docs/plans/2026-07-12-book-package-RUN-STATE.md:216`) · **23-C3**
> **Unblocks:** `24_plan_hub_v2.md` **H3.1** (PlanDrawer's arc branch) · Wave 4 (`34_arc_templates…` extends `arcEffects.ts`)
> **Size:** **L** (logic ≈ 14 · side-effects: 1 CONTRACT slice + 3 changed REST contracts + 2 changed MCP tool schemas + 1 changed agent-tool schema (`resource_ref`) + the frontend-tool contract · files ≈ 28)
> **Type:** FS — 1 contract slice + 5 backend slices (**ONE service: `composition-service`, Python — there is NO Go work; see §0.1 LA-1**), 7 frontend slices.
> **Written:** 2026-07-13 · against HEAD `9262ed53e`, branch `feat/context-budget-law`.
> **RECONCILED:** 2026-07-13 against **`docs/plans/studio-adjudication/wave-2-decisions.md`** (47 adjudicated
> decisions). **That register OVERRIDES this plan wherever they disagree** — see §0.1 and the fold-in ledger §12.
> **Author:** LEAD. **Every fact below was read from source, not from a doc.** Where a doc and the code
> disagreed, the code won and the doc's claim is flagged inline.

---

## 0 · The policy this plan is written under (PO, binding — quoted verbatim)

1. **This plan is written ONCE, in full, at BUILD DETAIL.** After the QC gate, implementation proceeds
   **autonomously with no further design checkpoints.** So anything left vague becomes a stall or a
   guess at 3am. A slice that says "wire the panel" is a FAILURE; a slice says WHICH FILE, WHAT CHANGE,
   WHICH TEST.
2. **`/review-impl` runs at the completion of EVERY wave**, and any bug it finds is fixed before the
   wave closes. It is step 3 of the Wave DoD (§8).
3. **DEFERRAL POLICY — "blocked ≠ stopped".** When the build hits a blocker: write a tracked defer row
   and **KEEP GOING**. Do **not** stop, do **not** ask. A blocker is treated as a DEFER by default.
   **Stop and ask ONLY for a CRITICAL blocker**, defined narrowly as exactly one of:
   - a destructive / irreversible action (data loss, a migration that drops or rewrites user rows),
   - a **sealed decision proven wrong** by the code (§0 PO-1..4 of plan 30),
   - a **tenancy / security breach** (cross-user data exposure),
   - a **paid-action defect that would charge the user for nothing.**
   Everything else — a missing route, an awkward refactor, a failing third-party thing, an ugly seam —
   is a **defer row + continue**.
4. Every defer row carries: ID, wave/slice of origin, what, the gate reason (CLAUDE.md's 5 gates),
   target wave/trigger. A defer row is never a silent drop. Starting rows: §9.
5. **CLAUDE.md's anti-laziness rule is in force:** "missing infrastructure is NOT blocked — it is unbuilt
   work to implement." A route that does not exist is a route you WRITE. **W2-S0 exists because of this
   rule** — see §2.0.

### 0.1 🔴 THE ADJUDICATION REGISTER EXISTS. IT IS BINDING. IT OVERRIDES THIS PLAN.

> **`docs/plans/studio-adjudication/wave-2-decisions.md`** — 47 items, 44 DECIDED against **source code**.
>
> When this plan was first written the register was believed missing, so the LEAD improvised three
> adjudications (LA-1..LA-3). **The register has since been recovered, and it REFUTES two of them.**
> This plan has been reconciled against it (2026-07-13). **Where this plan and the register disagree,
> THE REGISTER WINS — it was adjudicated against source; the plan was written blind.** Read it before
> the first commit. Do not re-open a decided question.
>
> The fold-in ledger (which decision landed in which slice) is **§12**. Every `Q-32-*` id below is a
> row in that register — cite it, don't re-derive it.

| # | Question the code forced | Status after reconciliation |
|---|---|---|
| ~~**LA-1**~~ | *"There is NO grant read on the frontend at all, so the VIEW-only state is unbuildable — BUILD a new `GET /v1/books/{book_id}/my-access` in book-service."* | 🔴 **REFUTED — `Q-32-403-READONLY-GRANT-SOURCE`. The grant is ALREADY ON THE WIRE and the FE drops it.** `GET /v1/books/{book_id}` computes and returns a per-caller **`access_level` ∈ `owner\|manage\|edit\|view\|none`** (verified this run: `services/book-service/internal/api/server.go:957` computes it, `:987` emits it; the list route does the same at `:857`/`:885`). `grep -rn "access_level" frontend/src` → **ZERO hits** — the `rest-write-mirror-drops-fields` bug class, in read form. **W2-S0 IS DELETED. Write no Go. There is no new route in this wave.** The fix is `frontend/src/features/books/hooks/useBookGrant.ts` reading `access_level` off the `['book', bookId]` cache the studio **already holds** (`BookSettingsPanel.tsx:32`, `GlossaryPanel.tsx:34`) — a cache hit, not a request. See **W2-S5 · step 3**. |
| ~~**LA-2**~~ | *"DO NOT touch the list route's `empty` fallback — `ArcListNode.chapter_count` is declared non-null and `laneLayout` reads it."* | 🔴 **REFUTED — `Q-32-ARCHIVED-NULL-NOT-ZERO` (edit 4).** The `empty` fallback is reached **ONLY for archived rows** — `derived_blocks()` emits a row for **every LIVE node including a 0-chapter one** (`structure.py:300-327`), so a live arc never hits it. And archived rows **LIE**: `chapter_count: 0` + `is_contiguous: true` for an arc that still has all its chapters bound (`archive()` never nulls `outline_node.structure_node_id`). Only the picker's *Show archived* ever sees them (the Hub shell never passes `include_archived`), so the Hub sees **zero behavior change**. **Change the fallback to all-null and widen the FE type** — see W2-S1 edit 3. |
| **LA-3** | Where does the arc-detail API layer live? | ✅ **STANDS** (consistent with `Q-32-DOD-GREP-GATES`, whose route gate greps `frontend/src` for the five exported fns). **Extend `frontend/src/features/plan-hub/api.ts`** — it ALREADY owns every `/v1/composition/arcs/*` route string (`moveArc:190`, `assignChapters:241`); one owner per route string (DOCK-2). ⚠ Not `features/composition/motif/arcApi.ts`, which owns `/v1/composition/arc-**templates**/*` — a different resource. We *consume* its `get()` for provenance and add nothing to it. |

**File-home harmonization (do this once, then stop thinking about it).** Several register rows name
`frontend/src/features/arc-inspector/…` for new FE files. **That directory does not exist** (verified —
`ls frontend/src/features/`), and creating it would fork the panel away from the studio catalog that
registers it. **Every new arc FE file lives under `frontend/src/features/studio/panels/` (section
components under `…/panels/arc/`).** The register's *content* is binding; its *directory guesses* for
files that do not exist yet are not. Nothing else about those rows changes.

---

## 1 · Pre-flight — run these BEFORE the first commit. Each must print what is stated.

The wave's hard gates. If one disagrees with what is claimed here, **the code has moved — re-read it and
adjust the affected slice**, do not proceed on the doc's word.

```bash
cd d:/Works/source/lore-weave-mvp

# G1 — the packer STILL reads span()'s RAW strided keys. If this is empty, BE-A1's whole
#      "fix at the route, never in the repo" premise has changed. MUST be non-empty.
grep -rn "structure_repo.span(\|min_story_order" services/composition-service/app/packer/lenses.py
#   expect: lenses.py:248-249 (lo/hi = span.get("min_story_order"/"max_story_order"))
#           lenses.py:322     (spans = await asyncio.gather(*(structure_repo.span(...))))

# G2 — the 5 arc routes still have ZERO frontend consumers (so changing their contracts is free).
grep -rn "arcs/\${\|/arcs/" frontend/src --include=*.ts --include=*.tsx
#   expect: ONLY plan-hub/api.ts (moveArc → /arcs/{id}/move, assignChapters, getArcs).
#           NO GET /arcs/{id}, no POST /books/{id}/arcs, no PATCH, no DELETE, no /restore.

# G3 — 🔴 StructureRepo.update()'s THIRD caller. THE ORIGINAL PLAN GOT THIS WRONG.
#      It said "expect only the 2 doors; if a THIRD caller passes expected_version=None, leave the
#      repo branch alone." There IS a third caller, and leaving the branch alone is the BUG.
grep -rn "structure_repo.update(\|structures.update(\|\.update(.*expected_version" services/composition-service/app/
#   expect THREE: app/routers/arc.py:501 (REST door) · app/mcp/server.py:4379 (MCP door) ·
#          🔴 app/engine/arc_apply.py:497-507 — `structure_repo.update(..., expected_version=None)`,
#             a LIVE in-process BLIND write (the post-apply template snapshot: tracks/roster/
#             roster_bindings/arc_template_id/template_version). Today that write leaves `version`
#             UNTOUCHED, so a GUI holder of v7 still succeeds with `If-Match: 7` against content the
#             apply engine just replaced. Closing only the REST door leaves the exact hazard BE-A2
#             names. => W2-S2 MOVES the `version = version + 1` bump OUT of the OCC branch
#             (Q-32-BE-A2-IFMATCH-428, part 2). If this grep shows arc_apply is gone, re-read S2.

# G8 — 🔴 the grant is ALREADY on the wire and the FE drops it. This is why there is NO new Go route.
grep -rn "access_level" services/book-service/internal/api/server.go frontend/src
#   expect: server.go:957 (computes) + :987 (emits) on GET /v1/books/{id}; server.go:857/:885 on LIST.
#           frontend/src => ZERO hits.  If the FE now has hits, someone landed useBookGrant already —
#           reuse it, do not fork a second grant reader (Q-32-403-READONLY-GRANT-SOURCE).

# G9 — the tracks/roster migration audit. W2-S3b tightens the WRITE doors; this proves the blast
#      radius is zero before you type. (Q-32-OQ2-TRACKS-ROSTER-SCHEMA ran it: 4 rows, 0 non-empty.)
docker exec infra-postgres-1 psql -U loreweave -d loreweave_composition -c "SELECT count(*) FROM structure_node;" \
  -c "SELECT id FROM structure_node WHERE EXISTS (SELECT 1 FROM jsonb_array_elements(tracks) t WHERE COALESCE(t->>'key','') = '');" \
  -c "SELECT id FROM structure_node WHERE EXISTS (SELECT 1 FROM jsonb_array_elements(roster) r WHERE r->>'actant' IS NOT NULL AND r->>'actant' NOT IN ('subject','object','sender','receiver','helper','opponent'));"
#   expect: the 2nd and 3rd queries return ZERO rows. If they DON'T, extra='forbid' would reject a
#   legacy row on PATCH round-trip — say so in the slice, keep the guard, and make AI-3's inline
#   message point at the OFFENDING ENTRY (not at the field the user touched). Do NOT skip the slice.

# G4 — the enum drift-lock baseline. Record the number; the DoD asserts BASELINE + 1, never a literal.
python -c "import re,json;s=open('services/chat-service/app/services/frontend_tools.py',encoding='utf-8').read();print('py enum:',len(json.loads(re.search(r'\"enum\": (\[\"compose\".*?\]),',s,re.S).group(1))))"
#   at HEAD 9262ed53e: 57.  If Wave 1 (spec 31) has landed first: 61.  EITHER IS FINE.
#   ⚠ Plan 30 §8.0 note 6: six of eight specs computed from 57 as if they were the only wave.
#      They are SEQUENTIAL and CUMULATIVE. Assert the DELTA (+1) and the three-way equality.

# G5 — the PlanDrawer gap note is still there (it is what Wave 2 deletes).
grep -rn "plan-drawer-arc-gap" frontend/src
#   expect: PlanDrawer.tsx:351 (one hit). At the end of the wave: ZERO hits.

# G6 — nobody else is mid-edit in our files (shared checkout, 3 live tracks — plan 30 §9).
git status --short -- services/composition-service services/book-service frontend/src/features/studio frontend/src/features/plan-hub
#   ⚠ PlanDrawer.tsx is owned by the Book-Package track (DECLARED COMPLETE 2026-07-12; DBT-06 is
#     handed to us — "#4 genuinely-upstream", not contested). If it shows as modified by someone else:
#     DEFER W2-S9 to the END of the wave and KEEP GOING (run policy §0.3 — a blocker is a defer row,
#     never a stop). Do NOT stop and ask; W2-S9 is a deletion + a one-line mount and reverts cleanly.
#   ⚠ DO NOT TOUCH (Track C is mid-edit, plan 30 §9): chat-service/app/services/stream_service.py,
#     chat-service/app/routers/tool_permissions.py, frontend/src/features/chat/components/ToolApprovalCard.tsx,
#     frontend/src/features/chat/hooks/useChatMessages.ts.
#     We DO edit chat-service/app/services/frontend_tools.py — a DIFFERENT file, not contested.

# G7 — the test harness. Composition suites need the SDK path (memory: knowledge-local-tests-need-pythonpath-sdks).
cd services/composition-service && python -m pytest tests -q -n auto --dist loadgroup 2>&1 | tail -3
#   Record the baseline pass count. Every BE slice's DoD is "baseline + N passed".
```

**NEVER `git add -A`.** Three tracks share this checkout. Enumerate files on every commit
(`git commit -- <paths>`), and remember **`git commit -- <path>` commits the WORKING TREE, not the
index** (memory: `git-commit-pathspec-reads-working-tree-not-index`), and **the index may already carry
someone else's pre-staged changes** — check `git diff --cached --name-only` first.

---

## 2 · Backend prerequisites (slices FIRST — no panel slice may precede its route slice)

### 2.0 · Route contract summary

🔴 **CONTRACT-FIRST (CLAUDE.md, non-negotiable): "API contract frozen before frontend flow."** Every row
below whose Δ is not `unchanged` lands in **`contracts/api/composition/v1/openapi.yaml`** in **W2-S0 —
BEFORE any FE slice.** Verified this run: that file has **17 paths and NOT ONE of them is an `/arcs` path**
(`grep -n "^  /" contracts/api/composition/v1/openapi.yaml`). The eight arc routes have been shipping,
uncontracted, since B1. W2-S0 closes that.
⚠ The file's `servers:` is `/v1/composition`, so paths in it are written **WITHOUT** the `/v1/composition`
prefix (`/arcs/{node_id}`, `/books/{book_id}/arcs`). ⚠ **`contracts/api/composition-service/plan-forge.v1.yaml`
is a DIFFERENT file — that one is Wave 5's. Do not touch it.**

| Method | Path (as written in the spec file) | Δ | Request | Response | Errors |
|---|---|---|---|---|---|
| `GET` | `/books/{book_id}/arcs` | **CONTRACT-NEW** (route ships) | `?include_archived` | `{arcs: ArcListNode[]}` — each = node dump **+ the derived block** | `403` · `404` uniform |
| `GET` | `/arcs/{node_id}` | **CHANGED** | — | node dump **+** `resolved{tracks,roster,roster_bindings,`**`provenance`**`}` **+** `open_promises[]` **+ (changed)** `span:{from_order,to_order}\|null`, `chapter_count:int\|null`, `is_contiguous:bool\|null`, `first_story_order:int\|null`, **`gap_count:int\|null`** | `404` uniform · `403` under-tier |
| `POST` | `/books/{book_id}/arcs` | **CHANGED** (typed `tracks`/`roster`) | `ArcCreate` | `201` node dump | **`422`** blank/dup track key, bad `actant` · `400` `STRUCTURE_CONSTRAINT` · `403` |
| `PATCH` | `/arcs/{node_id}` | **CHANGED** | body `ArcPatch` (typed `tracks`/`roster`) · header **`If-Match: <version>` NOW REQUIRED** | the updated node dump | **`428`** `IF_MATCH_REQUIRED` · `412` `{code:"STRUCTURE_VERSION_CONFLICT", current:{…}}` · **`422`** key invariant · `400` `STRUCTURE_CONSTRAINT` · `404` uniform |
| `DELETE` | `/arcs/{node_id}` | **CHANGED** | — | `{id, archived:true, `**`archived_ids:[uuid], archived_count:int`**`}` | `404` uniform |
| `POST` | `/arcs/{node_id}/restore` | **CONTRACT-NEW** (route ships) | — | `{id, archived:false}` | `404` uniform |
| `POST` | `/arcs/{node_id}/move` | **CONTRACT-NEW** (route ships) | `{parent_arc_id, rank}` | node dump | `400` `STRUCTURE_CONSTRAINT` · `404` |
| `POST` | `/books/{book_id}/arcs/assign-chapters` | **CHANGED** | `{structure_node_id: UUID \| **null** (REQUIRED, nullable), chapter_node_ids: UUID[]}` | `{assigned:int, structure_node_id: str\|null}` | `422` field omitted · `403` · `404` uniform |

**🔴 There is NO new route in this wave and NO Go work.** The `my-access` route the first draft invented is
**deleted** — `GET /v1/books/{book_id}` already carries `access_level` (§0.1 LA-1). Book-service is untouched.

**MCP tools:** `composition_arc_get` (BE-A1: derived block + `gap_count` + `provenance`),
`composition_arc_delete` (`archived_ids`/`archived_count`), `composition_arc_assign_chapters` (BE-A3:
nullable `structure_node_id`), `composition_arc_create` / `_update` (typed `tracks`/`roster`) all change **in
lockstep with their REST twins** — *both doors or neither* (GG-2 inverse law). **No new MCP tool.** All 8 arc
tools exist (`server.py:4191-4543`); the *human* side was the hole.

**Agent-tool contract:** `ui_open_studio_panel` gains an optional **`resource_ref {kind, id, version?}`**
(`kind` is a **closed set ⇒ `enum` ⇒ `CLOSED_SET_ARGS`**) — W2-S4b, per `Q-32-X6-RESOURCE-REF-UNWRITTEN`.
⚠ **This is NOT the free-form `params` arg**, which stays **FORBIDDEN** (`Q-32-X12-AMEND-PLAN30`,
`Q-32-AI1-ADDRESSING`): free-form args are the `ui_show_panel` shape PO-3 is deleting. A closed-set
`resource_ref` is the sanctioned addressing arg; a free-string `params` is not. Both are true; do not confuse them.

**Zero gateway work** — the composition proxy's `pathFilter` is generic (`gateway-setup.ts:354`).

### 2.1 · MIGRATIONS: **NONE. Do not write one.**

No new table, no new column, no new enum value, no backfill. `structure_node` already carries every field
this wave reads or writes (`app/db/models.py:194-228`). **If you find yourself reaching for a migration,
you have misread the design — stop and re-read §3.**

For the record, so a later agent does not "helpfully" add one, the three CLAUDE.md migration scars that
would bite if they did: `ADD COLUMN IF NOT EXISTS` **never revisits a bad default** on an already-migrated
DB; a new enum value must backfill **every** historical CHECK block; a partial UNIQUE index must exempt
soft-delete tombstones and its `ON CONFLICT` must repeat the partial index's predicate. **None apply
here, because there is no migration.**

---

## 3 · The slices

Each slice = **one commit**. `dependsOn` is a hard ordering constraint.

---

### **W2-S0 · CONTRACT · the eight arc routes enter `contracts/api/composition/v1/openapi.yaml`**
**dependsOn:** — · 🔴 **THIS SLICE COMES FIRST. No FE slice may precede it.**

> **CLAUDE.md: "Contract-first: API contract frozen before frontend flow."** This wave changes 5 arc route
> contracts and gives 8 of them their first FE consumer. **Not one `/arcs` path is in the contract today.**
> Freeze them here, then build against the frozen shape.
>
> ⚠ The original W2-S0 (a new `GET /v1/books/{book_id}/my-access` Go route) is **DELETED** — §0.1 LA-1.
> `access_level` was already on the wire. **Do not write Go this wave.**

**File — EDIT (one file, additive only):** `contracts/api/composition/v1/openapi.yaml`

- ⚠ **`servers: /v1/composition`** ⇒ write paths **without** that prefix.
- ⚠ Reuse the existing components — do **not** redefine them: `#/components/parameters/BookId`,
  `…/NodeId`, `#/components/responses/NotFound`, `…/VersionConflict`.
- ⚠ **`#/components/parameters/IfMatch` is `required: false`.** `PATCH /arcs/{node_id}` needs a
  **required** one. Add a sibling parameter, do **not** mutate the shared optional one (`/canon-rules/{rule_id}`
  still uses it):
  `IfMatchRequired: { name: If-Match, in: header, required: true, schema: { type: integer }, description: "OCC version — MANDATORY on arc writes (BE-A2). Absent ⇒ 428 IF_MATCH_REQUIRED." }`
- Add `- name: arc` to the `tags:` list.

**Add these 8 paths** (tag `arc`), with request/response schemas + error codes, exactly matching §2.0's table:

| Path | Ops | Notes that MUST appear in the spec |
|---|---|---|
| `/books/{book_id}/arcs` | `get`, `post` | `get`: `?include_archived` query. `post` → `201` `StructureNode`; `422` on the key invariant (W2-S3b); `400` `STRUCTURE_CONSTRAINT` |
| `/arcs/{node_id}` | `get`, `patch`, `delete` | `get` → `ArcDetail`. `patch` → `$ref: IfMatchRequired`, `428`/`412`/`422`/`400`/`404`. `delete` → `ArcArchiveResult` |
| `/arcs/{node_id}/restore` | `post` | `{id, archived: false}` |
| `/arcs/{node_id}/move` | `post` | `{parent_arc_id, rank}` → `400 STRUCTURE_CONSTRAINT` |
| `/books/{book_id}/arcs/assign-chapters` | `post` | body `ArcAssignChapters`: `structure_node_id` is **REQUIRED and NULLABLE** (`null` ⇒ UNASSIGN). Omitting it is a `422` — say so in the description |

**Add these `components/schemas`** (mirror `services/composition-service/app/db/models.py:206-235` +
`app/routers/arc.py`):

```yaml
    ArcTrack:            # models.py ArcThread — extra: FORBID (W2-S3b)
      type: object
      required: [key]
      additionalProperties: false
      properties:
        key:   { type: string, minLength: 1, maxLength: 100, description: "the CASCADE key — _merge_by shadows by it. Blank/duplicate ⇒ 422." }
        label: { type: string }
    ArcRosterEntry:
      type: object
      required: [key]
      additionalProperties: false
      properties:
        key:    { type: string, minLength: 1, maxLength: 100 }
        actant: { type: string, nullable: true, enum: [subject, object, sender, receiver, helper, opponent] }   # models.py:452 — CLOSED SET
        label:  { type: string }
        constraints: { type: array, items: { type: string } }   # deliberately free text
    ArcDerivedBlock:     # 🔴 ALL FIVE ARE NULLABLE. null = NOT COMPUTED (archived). It is NOT a zero.
      type: object
      properties:
        span:              { nullable: true, type: object, properties: { from_order: { type: integer }, to_order: { type: integer } }, description: "READING-POSITION ordinals — NOT raw strided story_order" }
        chapter_count:     { type: integer, nullable: true }
        is_contiguous:     { type: boolean, nullable: true, description: "warn-only (BA6). Never blocks a write." }
        first_story_order: { type: integer, nullable: true }
        gap_count:         { type: integer, nullable: true, description: "positions missing from the span. null = not countable (unordered/duplicate positions) — never fabricate an N." }
    ArcProvenanceEntry:   # the AI-2 sidecar — a SIBLING MAP, never a field on the entry
      type: object
      properties:
        node_id: { type: string, format: uuid }
        title:   { type: string }
        kind:    { type: string, enum: [saga, arc] }
        is_own:  { type: boolean }
        shadows_node_id: { type: string, format: uuid, nullable: true }
        shadows_title:   { type: string, nullable: true }
    ArcDetail:
      allOf:
        - $ref: '#/components/schemas/StructureNode'
        - $ref: '#/components/schemas/ArcDerivedBlock'
        - type: object
          properties:
            resolved:
              type: object
              properties:
                tracks:          { type: array, items: { $ref: '#/components/schemas/ArcTrack' } }
                roster:          { type: array, items: { $ref: '#/components/schemas/ArcRosterEntry' } }
                roster_bindings: { type: object, additionalProperties: { type: string } }
                provenance:      # AI-2 — keyed by the SAME key as the entry it describes
                  type: object
                  properties:
                    tracks:          { type: object, additionalProperties: { $ref: '#/components/schemas/ArcProvenanceEntry' } }
                    roster:          { type: object, additionalProperties: { $ref: '#/components/schemas/ArcProvenanceEntry' } }
                    roster_bindings: { type: object, additionalProperties: { $ref: '#/components/schemas/ArcProvenanceEntry' } }
            open_promises: { type: array, items: { type: object } }
    ArcArchiveResult:
      type: object
      properties:
        id:            { type: string, format: uuid }
        archived:      { type: boolean }
        archived_ids:  { type: array, items: { type: string, format: uuid }, description: "the WHOLE archived subtree (OQ-3). The agent cannot client-derive it." }
        archived_count:{ type: integer }
```
(`StructureNode` and `ArcAssignChapters` likewise — every column of `models.py:206-235`; `tracks`/`roster`
on the **read** model stay permissive (`items: {type: object}`) because the read model is deliberately
looser than the write doors — `close-legacy-window-in-writer-not-base-schema`.)

**Test / DoD** — the contract must be **machine-valid**, not eyeballed:

```bash
npx --yes @redocly/cli lint contracts/api/composition/v1/openapi.yaml
# (or: python -c "import yaml,sys; d=yaml.safe_load(open('contracts/api/composition/v1/openapi.yaml',encoding='utf-8')); \
#   ps=d['paths']; req=['/books/{book_id}/arcs','/arcs/{node_id}','/arcs/{node_id}/restore','/arcs/{node_id}/move','/books/{book_id}/arcs/assign-chapters']; \
#   missing=[p for p in req if p not in ps]; assert not missing, missing; \
#   assert ps['/arcs/{node_id}']['patch']['responses'].get('428'), 'BE-A2 428 not contracted'; \
#   assert '\$ref' in str(ps['/arcs/{node_id}']['patch']['parameters']), 'If-Match not contracted'; print('contract OK', len(ps),'paths')")
```

**DoD evidence:** the pasted lint output (**0 errors**) **and** the pasted python assertion printing
`contract OK <N> paths` where `N == 17 + 5`. 🔴 **This slice's commit lands BEFORE W2-S4.** If a later slice
changes a shape, **the contract is edited in that same commit** — a contract that drifts from the code is
worse than none (it is a doc that lies, and this repo has been bitten by exactly that twice).

---

### **W2-S1 · BE · BE-A1 — the `span` shape+unit fix, at BOTH detail doors**
**dependsOn:** — · 🔴 **The single most dangerous slice in the wave.** Read the warning box before typing.

> 🔴 **DO NOT TOUCH `StructureRepo.span()`.** It has THREE callers, and the third is **the packer**:
> `lenses.py:322` gathers `span()` per chain node and feeds `min_story_order`/`max_story_order` to
> `_arc_position` (`lenses.py:241-254`), which compares them against the scene's **raw strided**
> `story_order` (`STORY_ORDER_CHAPTER_STRIDE = 1000`). **Dense-ranking `span()`, or renaming/removing its
> raw keys, silently corrupts EVERY generation prompt** — a `story_order` of 45000 against a dense-ranked
> `hi` of 18 clamps to *"~100% through arc X"* forever, or (via `_arc_position`'s `.get`) drops the Pacing
> line entirely. `gather_arc`'s degrade-safe posture (`except Exception: return ""`, `:287`) would swallow
> it, **and the unit suite would stay green.** Fix the **ROUTES**. Leave the repo exactly as it is.

**The defect (verified in source):** `arc.py:455` and `server.py:4255` both do
`out["span"] = await structures.span(node.id)` → `{min_story_order, max_story_order, chapter_count,
is_contiguous}` in **raw strided units**. The LIST route (`arc.py:428`) returns `derived_blocks()` →
`{span:{from_order,to_order}, is_contiguous, chapter_count, first_story_order}` in **dense-ranked
ordinals**, *and its own SQL comment says why* (`structure.py:270-277`: *"raw min/max would report a
3-chapter arc as span 1000..3000 … every arc would read non-contiguous"*). Same field name. Different
shape. Different unit. An inspector rendering the detail route prints **"Chapters 41000–58000"**.

**Files**

1. **EDIT** `services/composition-service/app/routers/arc.py` → `get_arc` (`:438-460`). Replace **line 455**
   (`out["span"] = await structures.span(node.id)`) with:

```python
    # BE-A1 — the DERIVED block, in the SAME shape and the SAME unit as the LIST route
    # (arc.py:428). `StructureRepo.span()` returns RAW STRIDED story_orders
    # (STORY_ORDER_CHAPTER_STRIDE = 1000) — an inspector rendering it prints "Chapters
    # 41000–58000". `derived_blocks()` dense-ranks to the ordinal a reader means
    # (structure.py:270-277). One query; `node.book_id` is already in hand.
    #
    # ⚠ The fix is HERE, at the door — NEVER in span(). Its third caller is the PACKER
    # (lenses.py:322 → _arc_position), which NEEDS the raw strided axis to place a scene's
    # pacing. Dense-ranking span() would clamp every scene to "~100% through its arc" in
    # every generation prompt, degrade-safely, with a green unit suite.
    derived = (await structures.derived_blocks(node.book_id)).get(node.id)
    if derived is None:
        # derived_blocks() returns rows for LIVE nodes ONLY (structure.py:255). An archived
        # node therefore has NO block — and a null that means "not computed" is NOT a zero
        # (chapter-blocks-null-nontext-coalesce). Emit nulls, never the list route's `empty`
        # block, whose `chapter_count: 0` is exactly that trap.
        out["span"] = None
        out["chapter_count"] = None
        out["is_contiguous"] = None
        out["first_story_order"] = None
    else:
        out.update(derived)   # span{from_order,to_order}|None · is_contiguous · chapter_count · first_story_order
```

2. **EDIT** `services/composition-service/app/mcp/server.py` → `composition_arc_get` (`:4238-4260`). Replace
   **line 4255** with the **identical** block (same comment — the agent must read the same unit the human
   does, or they will disagree about what "chapter 41" means).

3. **EDIT** `services/composition-service/app/mcp/server.py` → the `composition_arc_get` **description**
   (`:4222-4230`). It currently tells the model the span is *"min/max story_order"* — **a lie after this
   fix**. Change that clause to:

   > `"the DERIVED block (`span` = the member chapters' READING-POSITION range {from_order, to_order} — "`
   > `"the ordinal a reader means, NOT the raw strided story_order — plus chapter_count, gap_count and "`
   > `"warn-only is_contiguous; all five are null for an archived arc, which means NOT-COMPUTED, not zero), "`

4. 🔴 **EDIT** `services/composition-service/app/routers/arc.py` → **`list_arcs`, the `empty` fallback (`:429`)**
   (`Q-32-ARCHIVED-NULL-NOT-ZERO` edit 4 — **this REVERSES the original plan's LA-2**, which said "do not
   touch the list route"; see §0.1):

```python
    # Q-32-ARCHIVED-NULL-NOT-ZERO. Was: {"span": None, "is_contiguous": True, "chapter_count": 0, …}
    # — a FABRICATED ZERO. derived_blocks() emits a row for EVERY LIVE node, including a 0-chapter one
    # (structure.py:300-327), so this fallback is reached ONLY by an ARCHIVED node (its CTE filters
    # `NOT is_archived`, structure.py:264) — i.e. only under ?include_archived=true. And those rows LIED:
    # `chapter_count: 0` for an arc that still has all 18 chapters bound (archive() flips is_archived on
    # structure_node ONLY — it never nulls outline_node.structure_node_id). null = NOT COMPUTED. It is
    # not a zero. LIST and GET now agree; the Hub shell never passes include_archived, so it sees no change.
    empty = {"span": None, "is_contiguous": None, "chapter_count": None,
             "first_story_order": None, "gap_count": None}
```
   ⚠ **This makes `ArcListNode.chapter_count` / `.is_contiguous` NULLABLE on the FE.** W2-S5 widens the type
   (`chapter_count: number | null`, `is_contiguous: boolean | null`, `gap_count: number | null`).
   `laneLayout.ts:34` reads `is_contiguous` for the segmented band — it only ever sees **live** nodes
   (the Hub never requests archived), but **type it nullable and treat `null` as `true`** (no warn band for
   a node whose contiguity was never computed). Do not let a `null` render as a warning.

5. **EDIT** `services/composition-service/app/db/repositories/structure.py` → **`derived_blocks()`**, the
   per-row loop (`:300-328`, which already has `cc` / `min_so` / `max_so` / `ordered` / `distinct` in hand).
   Emit **one additive key** beside `is_contiguous` (`Q-32-NONCONTIGUOUS-WARN-ONLY`):

```python
        if cc == 0 or is_contig:
            gap_count = 0
        elif ordered < cc or distinct < cc:
            gap_count = None      # unordered / duplicate positions — NOT countable. NEVER fabricate an N.
        else:
            gap_count = (max_so - min_so + 1) - cc
```
   `gap_count` is in the **same dense-ranked ordinal unit** as `span.{from_order,to_order}`. It ships to
   BOTH doors for free (they now spread the block). 🔴 **The client MUST NOT derive this.** The children
   route is keyset-paged, so a client count over the *loaded* window reports not-yet-loaded chapters as gaps
   (memory `paged-join-against-complete-set-mislabels-not-yet-loaded-as-absent`), and raw `story_order` is
   strided ×1000, so a client min/max diff calls **every** arc non-contiguous.

6. 🔴 **EDIT** `services/composition-service/app/db/repositories/structure.py:681` — **LOCK THE PRODUCER.**
   Do not change `span()`'s behavior; add the grep-able backlink at its return dict
   (`Q-32-SPAN-REPO-TRAP` step A):

```python
        # ⚠ CONSUMED BY THE PACKER — app/packer/lenses.py:247 (_arc_position) reads these EXACT keys
        # against the scene's RAW STRIDED story_order. Dense-ranking or renaming them silently corrupts
        # the Pacing line in EVERY generation prompt (and gather_arc's degrade-safe `except` swallows it,
        # so the unit suite stays GREEN). The INSPECTOR's span comes from derived_blocks(), not from here.
        # See Q-32-SPAN-REPO-TRAP. Do not "clean this up."
```
   **And do NOT make `_arc_position` strict** (`span["min_story_order"]` instead of `.get()`) —
   `Q-32-SPAN-REPO-TRAP` step D: `pack.py`'s outer `asyncio.gather` (~`:338`) has **no**
   `return_exceptions=True` and the pacing block is **not** inside a `try`, so a `KeyError` would propagate
   and **500 the entire pack**, breaking the documented *"the arc frame THINS, never fails a pack"* posture.
   **Keep `.get()`.**

**Tests** (TDD: write these first; #1 and #3 red before the edit)

| # | File | Test name | Asserts |
|---|---|---|---|
| 1 | `services/composition-service/tests/unit/test_arc_hub_routes.py` (**EDIT** — mock-based, no DB) | `test_arc_detail_span_matches_the_list_route_shape` | `structures.derived_blocks = AsyncMock(return_value={ARC: {"span": {"from_order": 41, "to_order": 58}, "is_contiguous": False, "chapter_count": 18, "first_story_order": 41000}})`; `structures.span = AsyncMock()`. `GET /arcs/{ARC}` ⇒ `body["span"] == {"from_order":41,"to_order":58}`, `body["chapter_count"] == 18`, and **`structures.span.await_count == 0`** ← the regression guard: the raw unit must never reach a client again |
| 2 | same | `test_arc_detail_of_an_archived_node_is_null_not_zero` | `derived_blocks` returns `{}` (no key for the archived node) ⇒ `body["span"] is None` **and** `body["chapter_count"] is None` **and** `body["is_contiguous"] is None`. **Explicitly assert `is not 0` / `is not True`** — a computed `0` here is the bug |
| 3 | `services/composition-service/tests/unit/test_mcp_arc_structure.py` (**EDIT** — `test_arc_get_enriches_resolved_span_and_promises`, `:163-177`, currently mocks `structures.span`) | `test_arc_get_span_is_the_derived_block_not_the_raw_axis` | the MCP tool returns the **same** `{from_order,to_order}` shape as REST, and does **not** call `structures.span` |
| 4 | `services/composition-service/tests/integration/db/test_structure_repo.py` (**EDIT** — real PG, already carries `pytestmark = pytest.mark.xdist_group("pg")`; **verify the mark is still at module scope**) | `test_span_keeps_the_RAW_strided_keys_the_packer_needs` | 🔴 **the anti-cleanup pin.** Seed an arc + 3 chapters at `story_order` 1000/2000/3000. Assert `await repo.span(arc)` **==** `{"min_story_order": 1000, "max_story_order": 3000, "chapter_count": 3, "is_contiguous": False}` — the **exact key names** and the **raw** values. Then `from app.packer.lenses import _arc_position` and assert `_arc_position(2000, span) == 50`. Docstring: *"BE-A1 fixed the ROUTES. If a future 'cleanup' dense-ranks span() to match, this test reds — instead of silently clamping every generation prompt's Pacing line to ~100%."* |
| 5 | `services/composition-service/tests/unit/test_pack_arc.py` (**verify only, no edit expected**) | existing `test_arc_frame_injects_chain_pacing_cast_and_promises` (`:176`) | still green — it pins `~60% through the arc` off a `FakeStructureRepo` whose `spans` use `min_story_order`/`max_story_order` (`:110`). 🔴 **This test CANNOT catch the trap** — it drives a hardcoded fake and never touches the real repo (`Q-32-SPAN-REPO-TRAP`). Ticking it as "the pacing pin" is the exact box-ticking the register calls out. The real pin is #4 + #6 |
| 6 | `services/composition-service/tests/unit/test_pack_arc.py` (**ADD**) | `test_span_producer_still_declares_the_raw_keys` | 🔴 **THE ALWAYS-RUNS FALLBACK** (`Q-32-SPAN-REPO-TRAP` step C). Test #4 lives in `tests/integration/db/`, which is `skipif TEST_COMPOSITION_DB_URL` — **an unset DSN makes the whole pin vanish silently** (memory `env-gated-integration-tests-skip-and-the-green-suite-lies`). So ALSO pin the producer's source, in a test that always runs: `import inspect; from app.db.repositories.structure import StructureRepo; src = inspect.getsource(StructureRepo.span); assert '"min_story_order"' in src and '"max_story_order"' in src` — with the comment *"the FakeStructureRepo in this file cannot catch a producer rename."* **Prefer the DSN; this is belt-and-braces, not a substitute** |
| 7 | `services/composition-service/tests/unit/test_arc_hub_routes.py` | `test_list_of_an_archived_arc_is_null_not_zero` | `?include_archived=true` ⇒ the archived node's LIST block is **all-null** (`chapter_count is None`), matching GET. Pins edit 4. **Assert `is None`, never falsy** |
| 8 | same | `test_live_arc_with_no_chapters_is_zero_not_null` | 🔴 **the inverse — the whole point.** A LIVE arc with 0 chapters ⇒ `chapter_count == 0`, `span is None`, `is_contiguous is True`, `gap_count == 0`. A falsiness implementation passes #7 and **fails this one** |
| 9 | `services/composition-service/tests/integration/db/test_structure_repo.py` | `test_gap_count_is_null_when_positions_are_unordered_or_duplicated` | contiguous ⇒ `0`; one hole ⇒ `1`; duplicate/absent positions ⇒ **`None`** (never a fabricated N) |

**DoD evidence:** `cd services/composition-service && python -m pytest tests -q -n auto --dist loadgroup`
→ `<baseline+9> passed`, **and** the pasted output of
`python -m pytest tests/integration/db/test_structure_repo.py -q -k "raw_strided or gap_count"` showing
`2 passed`.
🔴 **`TEST_COMPOSITION_DB_URL` MUST BE SET and the output MUST read `passed`, not `skipped`.** A skipped
env-gated test is not a passing test — it is a green suite lying about a pin that does not exist
(`Q-32-SPAN-REPO-TRAP` step C). If the DSN genuinely cannot be set, test #6 (the always-runs source-pin) is
the fallback and you **say so in the evidence string** — never claim #4 passed.

---

### **W2-S1b · BE · the AI-2 PROVENANCE SIDECAR + the OQ-3 archive BLAST RADIUS**
**dependsOn:** W2-S0 · **Origin:** `Q-32-AI2-CASCADE-OWN-VS-INHERITED` + `Q-32-OQ3-DELETE-BLAST-RADIUS-COUNT`

> 🔴 **BOTH OF THESE WERE MISSING FROM THE FIRST DRAFT.** The draft planned to derive the cascade
> **client-side** (`arcCascade.ts` walking ancestors). **The register forbids it:** *"AI-2 stands as LOCKED,
> but it is NOT implementable from today's payload — the FE cannot name the source ancestor. Build a BE
> provenance sidecar, then render off it… the FE NEVER re-merges the cascade and never diffs key-sets
> itself."* One merge rule, one home — a second implementation in TypeScript is a second SSOT that drifts
> from `_merge_by` the first time the shadow rule changes.
> **⇒ `arcCascade.ts`'s `splitCascade` is DELETED from this plan.** W2-S5 consumes `resolved.provenance`.

**Files**

1. **CREATE** `StructureRepo.resolve_provenance()` — `services/composition-service/app/db/repositories/structure.py`,
   next to the other resolvers (after `resolve_roster_bindings`, `:616`). ~40 LOC, **no new table, no
   migration, no settings.** It walks the **SAME** `ancestor_chain(node_id)` (`:568`) and applies the
   **SAME** root→leaf shadow rule as `_merge_by` (`:586-597`) — reuse, do not re-derive:

```python
    async def resolve_provenance(self, node_id: UUID) -> dict[str, Any]:
        """AI-2 — WHO owns each effective cascade entry, and what it shadows.

        Returns a SIBLING MAP keyed by the same key the entry is merged on:
          {"tracks": {<key>: {node_id,title,kind,is_own,shadows_node_id,shadows_title}},
           "roster": {...}, "roster_bindings": {<role_key>: {...}}}
        `is_own` = (winner node_id == node_id). `shadows_*` is populated when the winner
        overwrote an ancestor entry with the SAME key (⇒ the FE can offer "Revert to inherited"),
        else null. An entry whose key is MISSING or "" gets NO provenance row — it is
        un-shadowable (AI-3); the FE renders it read-only with the no-key warning.
        """
```
   🔴 **DO NOT add provenance keys INTO the entry dicts.** `resolve_tracks`'s output feeds
   `arc_apply.py:563` (tracks → `threads`) **and** `packer/lenses.py:284` (→ the generation prompt), and a
   PATCH round-trips the array straight back to jsonb — an injected `_source_node_id` would **poison every
   prompt AND persist into the DB**. It is a **sibling map**, keyed by key, **never a field on the entry**.

2. **WIRE IT INTO BOTH DOORS** (GG-2 — one alone is an INVERSE gap):
   - `app/routers/arc.py:450-454` → `out["resolved"]["provenance"] = await structures.resolve_provenance(node.id)`
   - `app/mcp/server.py:4251` (`composition_arc_get`) → the **identical** line.

3. **`archive()` returns what it archived** — `structure.py:404`, `async def archive(self, node_id) -> None`
   becomes `-> list[UUID]`. Append `RETURNING id` to the existing recursive-CTE UPDATE, swap
   `await c.execute(...)` for `rows = await c.fetch(...)`, `return [r["id"] for r in rows]`.
   **Do NOT touch the CTE itself** (it already walks the subtree and threads `book_id`). **Leave `restore()`
   alone.**

4. **Both delete doors report the radius** (purely ADDITIVE — no test asserts exact dict equality on this
   route; the `r.json() == {...}` equality test at `test_motif_router.py:248` is the **motif** route):
   - `app/routers/arc.py:517-525` → `{"id":…, "archived": True, "archived_ids": [str(i) for i in ids], "archived_count": len(ids)}`
   - `app/mcp/server.py:4418-4429` (`composition_arc_delete`) → the same two keys. **This is the one that
     matters:** the agent holds no tree and cannot client-derive, so today it says *"archived the arc"*
     having silently archived N sub-arcs (an OUT-5 silent blast radius). **Update the tool description** to
     say it reports the archived subtree ids.

**Tests**

| # | File | Test | Asserts |
|---|---|---|---|
| 1 | `tests/integration/db/test_structure_repo.py` | `test_provenance_marks_inherited_and_names_its_source` | saga→arc→sub-arc, track key `"K"` on the **saga** only ⇒ `provenance.tracks["K"].is_own is False` and `.title == <saga title>`. Then set `"K"` on the sub-arc ⇒ `is_own True`, `shadows_title == <saga title>`, and `len(resolved["tracks"]) == 1` (**shadowed, not doubled**) |
| 2 | same | `test_provenance_never_leaks_into_the_entries` | 🔴 `all("node_id" not in t and "is_own" not in t for t in resolved["tracks"])` — pins that the entries stay **clean** for `arc_apply` / `lenses`. This is the prompt-poisoning guard |
| 3 | same | `test_an_unkeyed_entry_has_no_provenance_row` | a track with `key: ""` ⇒ no provenance row (the FE renders it read-only, AI-3) |
| 4 | same | `test_archive_returns_the_whole_subtree` | `archive(saga_id)` returns the ids of the saga **+ both sub-arcs** |
| 5 | `tests/unit/test_arc_hub_routes.py` | `test_delete_arc_reports_the_blast_radius` | `DELETE /arcs/{saga}` ⇒ `archived_count == 3` and `archived_ids` contains the two descendants |
| 6 | `tests/unit/test_mcp_arc_structure.py` | `test_arc_delete_tool_reports_archived_ids` | the MCP door returns the same two keys (GG-2 parity) |
| 7 | 🔴 `tests/integration/db/test_structure_repo.py` | `test_archive_does_not_cascade_unassign_restore_stays_lossless` | **`Q-32-OQ8-ARCHIVE-STRANDS-CHAPTERS` step 4 — this converts a won't-fix into an ENFORCED contract.** After archiving an arc, every member chapter's `outline_node.structure_node_id` is **STILL** the archived arc's id (non-null), and the chapter does **NOT** appear under `?unassigned=true`. **A future agent who "helpfully" makes archive cascade an unassign reds this test** — which is the point, because `restore()` is lossless *precisely because* the binding survives; a cascade would make archive an irreversible destructive write with no lift map to rebind from |

**DoD evidence:** `python -m pytest tests -q -n auto --dist loadgroup` → `<baseline+16> passed`, plus the
pasted `-k "provenance or archive_does_not_cascade"` integration output showing **`passed`, not `skipped`**.

---

### **W2-S2 · BE · BE-A2 — `If-Match` becomes REQUIRED (absent ⇒ 428)**
**dependsOn:** W2-S0

**The defect (verified):** `arc.py:495` — `if_match: str | None = Header(default=None)` → `_parse_if_match(None)`
→ `None` → `StructureRepo.update(expected_version=None)` (`structure.py:379`) skips the version clause
**and — worse — never appends `version = version + 1`** (that `set_clause` lives *inside* the
`expected_version is not None` branch, `:379-382`). So a blind write **does not bump the version at all**:
a concurrent holder of v7 then still succeeds with `If-Match: 7` against a row whose *content* someone else
replaced. Meanwhile the **MCP door requires it** (`_ArcUpdateArgs.expected_version: int`, `server.py:4333`,
non-optional). **The REST door is weaker than the MCP door, on the object that steers every prompt.**

**Files** — **EDIT** `services/composition-service/app/routers/arc.py` → `patch_arc` (`:489-513`). Insert
**immediately after the signature, BEFORE `_gate_arc`**:

```python
    # BE-A2 — If-Match is REQUIRED. It was optional, and `expected_version=None` makes
    # StructureRepo.update() skip the version clause AND skip the `version = version + 1`
    # bump (structure.py:379-382) — so a blind clobber was a legal request, and it left the
    # version stale so the NEXT writer's stale If-Match also succeeded. The MCP door has
    # always required it (_ArcUpdateArgs.expected_version, server.py:4333); the REST door
    # was the weak one. Zero existing FE callers (NO-FE-CONSUMER, verified 2026-07-13), so
    # this breaks nobody.
    #
    # Checked BEFORE the grant gate on purpose: it is a pure protocol error, it costs no DB
    # round-trip, and it is returned uniformly for EVERY node_id — so it is not an existence
    # oracle (it tells a caller nothing about whether the node exists or is theirs).
    if if_match is None:
        raise HTTPException(status_code=428, detail={
            "code": "IF_MATCH_REQUIRED",
            "message": (
                "If-Match: <version> is required. Read `version` from "
                "GET /v1/composition/arcs/{node_id} and send it back."
            ),
        })
```

🔴 **AND YOU *MUST* CHANGE `StructureRepo.update()`. THE FIRST DRAFT GOT THIS EXACTLY BACKWARDS.**
It said: *"With both doors requiring the header, `expected_version=None` becomes unreachable — leave the
branch."* **FALSE** (`Q-32-BE-A2-IFMATCH-428`, part 2, and pre-flight **G3**):
**`services/composition-service/app/engine/arc_apply.py:497-507` calls
`structure_repo.update(..., expected_version=None)`** — a **live, in-process, blind write** (the post-apply
template snapshot: tracks / roster / roster_bindings / arc_template_id / template_version). The branch is
**not** unreachable. And because the `version = version + 1` bump lives **inside** the OCC branch, that write
**leaves `version` untouched** — so a GUI holder of **v7** still succeeds with `If-Match: 7` against content
the apply engine **just replaced**. **Closing only the REST door leaves the exact hazard BE-A2 exists to kill.**

**EDIT `services/composition-service/app/db/repositories/structure.py:376-382` — move the bump OUT of the branch:**

```python
    set_clauses.append("updated_at = now()")
    set_clauses.append("version = version + 1")   # ← ALWAYS bump. A WRITE IS A WRITE.
    # BE-A2: this used to live inside `if expected_version is not None`, so a blind write
    # (engine/arc_apply.py:497 — the post-apply template snapshot) replaced the row's CONTENT
    # while leaving its VERSION a lie. The next OCC holder then wrote over it with a stale
    # If-Match and got a 200. The version must move whenever the content moves.

    version_clause = ""
    if expected_version is not None:
        params.append(expected_version)
        version_clause = f" AND version = ${len(params)}"
```
Leave the `if expected_version is None: return None` / `VersionMismatchError` tail (`:397-401`) **exactly as
is** — it is the 404-vs-412 discriminator.

**Tests** — **EDIT** `services/composition-service/tests/unit/test_arc_hub_routes.py`:

| Test name | Asserts |
|---|---|
| `test_patch_arc_without_if_match_is_428` | `client.patch(f"/arcs/{ARC}", json={"title": "x"})` (no header) ⇒ `428`, `body["detail"]["code"] == "IF_MATCH_REQUIRED"`, **and `structures.update.await_count == 0`** (it never reached the repo) |
| `test_patch_arc_with_if_match_writes` | `headers={"If-Match": "7"}` ⇒ `200`, `structures.update` awaited with `expected_version=7`, and the returned node's `version == 8` |
| `test_patch_arc_stale_if_match_is_412_with_the_current_row` | `structures.update` raises `VersionMismatchError(current=<node v8>)` ⇒ `412`, `body["detail"]["code"] == "STRUCTURE_VERSION_CONFLICT"`, and **`body["detail"]["current"]["version"] == 8`** (the FE seeds this straight into cache — if it is absent, the panel's whole 412 recovery is dead) |
| `test_patch_arc_bad_if_match_is_400` | `If-Match: "not-a-number"` ⇒ `400` (existing `_parse_if_match` behaviour — pin it) |
| 🔴 `test_blind_repo_write_still_bumps_the_version` (**`tests/integration/db/test_structure_repo.py`**) | **the pin for the repo edit.** `StructureRepo.update(node, {"title": "x"}, expected_version=None)` bumps `version` **1 → 2**. This is the `arc_apply` path. **Without this test the "always bump" line gets refactored back out** by the next agent who reads "both doors require it, so None is unreachable" — the same wrong inference this plan already made once |
| `test_arc_apply_snapshot_bumps_the_version` (same file, if the apply harness is cheap to reach — else fold into the above) | after `arc_apply(...)`, the target `structure_node.version` is **greater** than it was before |

**DoD evidence:** `python -m pytest tests -q -n auto --dist loadgroup` → `<baseline+22> passed`.
🔴 **Do NOT touch `patch_arc_template` (`arc.py:216`)** — different resource, it *has* callers, out of scope.
🔴 **Keep the FastAPI param as `str | None = Header(default=None, alias="If-Match")`.** Making it a required
FastAPI `Header(...)` yields **422**, not **428**. The 428 is raised by hand.

---

### **W2-S3 · BE · BE-A3 — UNASSIGN (there is none, at any layer)**
**dependsOn:** —

**The defect (verified):** `ArcAssignChapters.structure_node_id: UUID` (`arc.py:364`, non-null),
`_ArcAssignChaptersArgs.structure_node_id: str` (`server.py:4510`, non-null), and
`StructureRepo.assign_chapters` (`structure.py:540`) does `SET structure_node_id = $1` guarded by an
`EXISTS`. A chapter, once bound, can only be **moved to another arc** — never returned to the pool. Yet
the children route **reads** that pool (`?unassigned=true` ⇒ `structure_node_id IS NULL`,
`outline.py:314/330`) and the Hub renders it. **We can read a state no writer can produce.**

**Files**

1. **EDIT** `services/composition-service/app/db/repositories/structure.py` → `assign_chapters` (`:540-564`).
   Widen the param and branch the SQL:

```python
    async def assign_chapters(
        self, book_id: UUID, structure_node_id: UUID | None, chapter_node_ids: list[UUID],
    ) -> int:
        """Attach CHAPTER-kind outline nodes to a spec node (sets
        `outline_node.structure_node_id`), or — with `structure_node_id=None` — UNASSIGN
        them back to the pool (BE-A3).

        Book-scoped both sides: only chapters in `book_id` are touched, and an ASSIGN is a
        no-op unless `structure_node_id` is itself in `book_id` (the EXISTS guard — a spec
        node never adopts chapters from another book). An UNASSIGN has no node to check, so
        it drops that guard and keeps the book_id + kind='chapter' + NOT is_archived guards
        — it can only ever null a chapter of THIS book.

        The unassign half is why `?unassigned=true` (outline.py:330) is finally a state a
        writer can produce: it was READ-ONLY reachable (post-decompile) and nothing could
        put a chapter back. Returns the count updated.
        """
        if not chapter_node_ids:
            return 0
        if structure_node_id is None:
            async with self._pool.acquire() as c:
                status = await c.execute(
                    """
                    UPDATE outline_node o
                    SET structure_node_id = NULL, updated_at = now()
                    WHERE o.book_id = $1 AND o.id = ANY($2)
                      AND o.kind = 'chapter' AND NOT o.is_archived
                    """,
                    book_id, chapter_node_ids,
                )
            return rows_changed(status)
        async with self._pool.acquire() as c:
            status = await c.execute(
                """
                UPDATE outline_node o
                SET structure_node_id = $1, updated_at = now()
                WHERE o.book_id = $2 AND o.id = ANY($3)
                  AND o.kind = 'chapter' AND NOT o.is_archived
                  AND EXISTS (
                    SELECT 1 FROM structure_node s
                    WHERE s.id = $1 AND s.book_id = $2
                  )
                """,
                structure_node_id, book_id, chapter_node_ids,
            )
        return rows_changed(status)
```

2. **EDIT** `services/composition-service/app/routers/arc.py` → `ArcAssignChapters` (`:363-365`):
   🔴 **`structure_node_id: UUID | None` — WITH NO DEFAULT.** (Pydantic v2: *Optional-without-default is
   REQUIRED*.) **Not `= None`.** (`Q-32-BE-A3-UNASSIGN` step 2/3 — the deliberate judgment call.) If omission
   meant *"unassign"*, a caller (or an LLM) that simply **forgets** the arg would **silently wipe arc
   membership**. Required-but-nullable makes **omission a 422** and **`null` an explicit intent**. The field
   is required today, so nothing breaks.
   Docstring line: *"`null` ⇒ UNASSIGN (return the chapters to the `?unassigned=true` pool)."*
   And in `assign_arc_chapters` (`:560-572`) fix the response — `str(body.structure_node_id)` renders the
   literal string **`"None"`** for a null:
   `{"assigned": count, "structure_node_id": str(body.structure_node_id) if body.structure_node_id else None}`

3. **EDIT** `services/composition-service/app/mcp/server.py` → `_ArcAssignChaptersArgs` (`:4508-4511`):
   `structure_node_id: str | None` — **again NO default**. Handler (`:4537`):
   `UUID(args.structure_node_id) if args.structure_node_id else None`. Response passes it straight through
   (already `str | None` → JSON null).
   **Undo hint stays `None`** — an unassign's true inverse needs the chapters' *prior* arcs, which the call
   does not carry. Honest `None` beats a wrong token (AN-8).

4. **EDIT** the `composition_arc_assign_chapters` **description** (`:4516-4522`) and its **`require_meta`
   synonyms** (`:4525-4528`) — *the description is the agent's only affordance doc; without it the capability
   ships **undiscoverable** (the "built but unreachable" class)*:

   > `" Pass structure_node_id=null to UNASSIGN the chapters instead: they return to the book's "`
   > `"unassigned pool (the state the Plan Hub reads via ?unassigned=true), which nothing could "`
   > `"produce before. This is the ONLY way a chapter leaves an arc — archiving the arc does NOT "`
   > `"unassign its chapters."`

   Synonyms to add: `"unassign chapters"`, `"remove chapter from arc"`, `"detach chapter"`,
   `"return chapters to the unassigned pool"`.

   ⚠ 🔴 **THE "3 SCHEMA SOURCES" CAVEAT DOES NOT APPLY HERE — the first draft inherited it from
   knowledge-service, which has a structure composition does not share** (`Q-32-BE-A3-FASTMCP-3-SCHEMAS`,
   verified): composition registers tools with a **single Pydantic arg model** and FastMCP derives the
   advertised `inputSchema` **from that model** (`test_mcp_server.py:220-223` walks exactly this).
   **`services/composition-service/app/mcp/tools/` DOES NOT EXIST**, so knowledge's separate
   `TOOL_DEFINITIONS` / hand-written OpenAI schema have **no counterpart**. And `_ArcAssignChaptersArgs`
   extends **`ForbidExtra`** (`sdks/python/loreweave_mcp/errors.py:34`, `extra="forbid"`) ⇒ an undeclared arg
   is **REJECTED LOUDLY, never silently stripped**. **The Pydantic model IS the schema. There is exactly ONE.**

   **THE REAL TRAP IS THE REST DOOR** (same bug family, opposite direction —
   `rest-write-mirror-drops-fields-the-mcp-tool-accepts`): **`class ArcAssignChapters(BaseModel)`
   (`arc.py:363`) is a PLAIN BaseModel** ⇒ pydantic's default `extra="ignore"` ⇒ **the REST door silently
   drops any field it does not declare.** The MCP door errors loudly; the GUI door no-ops silently.
   **Loosening only one door is the actual bug this slice can ship.** Both doors, every time.

**Tests**

| # | File | Test name | Asserts |
|---|---|---|---|
| 1 | `tests/unit/test_arc_hub_routes.py` | `test_assign_chapters_with_null_node_unassigns` | `POST /books/{B}/arcs/assign-chapters` body `{"structure_node_id": null, "chapter_node_ids": [C1]}` ⇒ `200 {"assigned": 1, "structure_node_id": null}` — **assert JSON `null`, NOT the string `"None"`** — and `structures.assign_chapters` awaited with `structure_node_id=None` |
| 2 | `tests/unit/test_mcp_arc_structure.py` | `test_arc_assign_chapters_accepts_null_for_unassign` | the MCP tool accepts `structure_node_id=None` and passes `None` to the repo |
| 2b | 🔴 same | `test_omitting_structure_node_id_is_a_validation_error` | **the destructive-omission footgun.** OMITTING the field (REST **and** MCP) raises a **validation error**, not a silent unassign. This is what "no default" buys — without this test, someone adds `= None` back and a forgetful caller wipes arc membership |
| 2c | 🔴 `tests/unit/test_mcp_server.py` | `test_assign_chapters_inputschema_advertises_nullable` | assert against the **LIVE** `session.list_tools()` `inputSchema`: `$defs["_ArcAssignChaptersArgs"].properties.structure_node_id` accepts **null** (an `anyOf` carrying `{"type":"null"}`) **and is still in `required`**. ~6-line add — the file already stands up an in-process FastMCP server (`:216-223`). **This is the one test that proves FastMCP actually advertises what we declared** |
| 3 | `tests/integration/db/test_structure_repo.py` (real PG, `xdist_group("pg")`) | `test_unassign_returns_the_chapter_to_the_unassigned_pool` | assign 2 chapters to an arc. Then `assign_chapters(book, None, [c1])` ⇒ **returns `1`, NOT `0`** (the NULL-into-`EXISTS` silent-no-op guard); `member_chapter_ids(arc) == [c2]`; and a direct `SELECT id FROM outline_node WHERE book_id=$1 AND kind='chapter' AND structure_node_id IS NULL` contains `c1` — **the exact predicate `outline.py:849`'s `?unassigned=true` axis uses.** Prove the READ can see what the WRITE produced (a mocked client cannot: memory `mocked-client-hides-server-side-default-filters`) |
| 4 | same | `test_unassign_cannot_touch_another_books_chapter` | `assign_chapters(bookA, None, [chapter_of_bookB])` ⇒ returns `0`, and B's chapter keeps its arc. **The `EXISTS` guard is gone on this branch — the `book_id` guard is what stands in its place, so it gets a test.** |
| 4b | same | `test_unassign_skips_non_chapter_kinds_and_archived_rows` | the other two guards that survive on the `None` branch |
| 5 | 🔴 same | `test_both_doors_land_the_chapter_in_the_unassigned_pool` | **GG-2 parity**: REST `assign-chapters` with `null` **and** MCP `composition_arc_assign_chapters` with `null` **each** land the chapter under `?unassigned=true`. One door alone is the INVERSE gap the spec forbids |

> 🔴 **THE SILENT-NO-OP THIS SLICE EXISTS TO AVOID.** Do **not** pass `NULL` as `$1` into the existing
> statement. The guard reads `EXISTS (SELECT 1 FROM structure_node s WHERE s.id = $1 …)`; with `$1 = NULL`
> that is `s.id = NULL` → NULL → never true → **EXISTS false → 0 rows updated → `200 {"assigned": 0}`** — a
> silent no-op reported as success (this repo's `silent-success-is-a-bug` class). **Branch onto a SECOND SQL
> statement**, which is what the code above does. Test #3's `assigned == 1` assertion is the guard.

**DoD evidence:** `python -m pytest tests -q -n auto --dist loadgroup` → `<baseline+31> passed`, plus the
pasted `-k unassign` integration output showing **`passed`, not `skipped`**.
**Single-service change ⇒ no cross-service live-smoke required**; the in-process FastMCP `list_tools()`
assertion (#2c) is the real gate. No change to `contracts/tool-liveness.json` (its entry pins only
`{status, executes, proven}` — **it is not a schema source**).

---

### **W2-S3b · BE · AI-3 + OQ-2 — the KEY INVARIANT, enforced at the doors AND in the merge**
**dependsOn:** W2-S0 · **Origin:** `Q-32-AI3-KEY-VALIDATION` + `Q-32-OQ2-TRACKS-ROSTER-SCHEMA`

> 🔴 **THE FIRST DRAFT DEFERRED THIS (`D-ARC-TRACKS-ROSTER-SCHEMA`). THE REGISTER DELETES THAT ROW.**
> Its defer rationale — *"tightening the server rejects writes the agent already makes, and `constraints[]`
> has an unsettled vocabulary, so it needs its own spec + a migration audit"* — **is refuted by the code and
> by a live audit**:
> - The typed models **ALREADY EXIST** and are **already enforced one door over**: `ArcThread` (`models.py:839`)
>   and `ArcRosterEntry` (`models.py:844` — `key`, `actant: Actant|None` where `Actant` is the **closed
>   6-value Literal** at `models.py:452`, `label`, `constraints: list[_Short]`) are applied at the
>   **arc-template** door (`models.py:858-861`) today. *"Needs its own small spec"* is false — the vocabulary
>   is settled, in this file.
> - **The migration audit is DONE and CLEAN** (`Q-32-OQ2`, live `psql`): 4 `structure_node` rows, **ZERO**
>   non-empty `tracks`/`roster` arrays, 0 bad actants, 0 missing keys. **There are no agent writes to reject.**
>   (Pre-flight **G9** re-runs it — if it comes back dirty, keep the guard and make the message point at the
>   offending entry.)
> - And the panel **cannot** be the guard: the corruption is **BACKEND-ONLY and it reaches the PROMPT**
>   (`lenses.py:282-284` → `resolve_tracks` → `_merge_by`). **Three doors** write these blobs (REST, MCP,
>   arc-template apply). AI-3's panel check sits **above** the bug, not in front of it.
>
> Follow the repo's own lesson `close-legacy-window-in-writer-not-base-schema`: **tighten the WRITERS, keep
> the READ model permissive.**

**Files**

1. 🔴 **HARDEN `_merge_by`** — `structure.py:591-595`. **This is the only edit that protects rows ALREADY IN
   THE DB, which no write-time validator can retroactively fix.** Replace `k = it.get(key_field, id(it))`:

```python
            k = it.get(key_field)
            if not isinstance(k, str) or not k.strip():
                k = id(it)          # unmergeable: KEPT, never shadows, never shadowed
            else:
                k = k.strip()       # kills the " romance" vs "romance" near-miss
            merged[k] = it
```
   **What this fixes:** today `key: ""` collides on `""` **across the whole ancestor chain AND within one
   node** — so **two blank-keyed tracks in ONE arc silently collapse to one, and a plot line vanishes from
   the generation prompt.** No cascade needed. This turns **silent data loss** into the benign,
   already-documented *"kept, can't be shadowed"* behavior. It **rejects nothing** and **migrates nothing**.
   Update the docstring (it currently promises only the missing-key case).

2. **TYPE BOTH WRITE DOORS** — reuse the shapes this service already ships. Move `ArcThread` /
   `ArcRosterEntry` above `StructureNode` in `models.py`, add `ArcTrack = ArcThread` as an alias so the
   arc-template code (`models.py:858-861`) is untouched, and give both
   **`model_config = ConfigDict(extra="forbid")`** (`ConfigDict` is **not** imported today — add it at `:29`).
   Then swap `list[dict[str, Any]]` → `list[ArcTrack]` / `list[ArcRosterEntry]` and
   `roster_bindings → dict[str, str] | None` at **all four sites**:
   `routers/arc.py:339-341` (`ArcCreate`) · `arc.py:351-353` (`ArcPatch`) ·
   `mcp/server.py:4281-4283` (`_ArcCreateArgs`) · `server.py:4338-4340` (`_ArcUpdateArgs`).
   ⚠ **`_Key` (`models.py:456`) has NO `min_length`** — `key: ""` passes even the typed door today. The new
   entry models must carry `min_length=1` (+ `strip_whitespace=True`).
   ⚠ **Serialize with `model_dump(mode="json")`** before handing to `create_node`/`update` (the repo
   `json.dumps` the `_JSONB_UPDATE_COLUMNS`, `structure.py:56`).

3. **LEAVE `StructureNode.tracks`/`roster` as `list[dict[str, Any]]`** (`models.py:232-233`) — **the READ
   model stays permissive** so any row written before this lands still loads. **Only the write doors close.**

4. **UNIQUENESS** (AI-3's third clause — nothing enforces it anywhere today): a
   `@field_validator("tracks", "roster")` on all four models rejecting a **duplicate `key` within the list**
   ⇒ 422 / MCP validation error, **naming the index and the key**:
   `"track[2].key 'romance' is already used in this arc"`.
   ⚠ **An own key that equals an INHERITED key is LEGAL — that IS the override.** Uniqueness is **within the
   node's own array only**. Never across the chain.

> **`extra="forbid"` vs `extra="allow"` — the ONE place the register disagrees with itself.**
> `Q-32-AI3-KEY-VALIDATION` says `extra="allow"` (fear of dropping agent fields);
> `Q-32-OQ2-TRACKS-ROSTER-SCHEMA` says `extra="forbid"` and **backs it with the live audit** (zero rows carry
> any extra field, so `forbid` costs nothing and turns a **silent drop** into a **loud 422** — the
> `rest-write-mirror-drops-fields` bug class, killed). **BUILD `forbid`** — the audit is decisive and both
> rows flag the choice as a one-line PO flip. If pre-flight **G9** comes back **dirty**, flip to `allow`,
> keep the `key` validation, and say so in the slice evidence.

**The migration edge — handle it, don't be surprised by it.** A PATCH round-tripping a **legacy bad row**
(panel loads an arc with a blank-keyed track → user edits only the **title** → save resends `tracks` → 422)
is **CORRECT** and is the only way a legacy row ever gets cleaned. But **AI-3's inline message must point at
the OFFENDING ENTRY, not at the field the user touched.**

**Tests** (the first three RED before the fix)

| # | File | Test | Asserts |
|---|---|---|---|
| 1 | `tests/integration/db/test_structure_repo.py` | `test_merge_by_blank_key_does_not_shadow` | saga track `{"key":"","label":"root"}` + sub-arc `{"key":"","label":"leaf"}` ⇒ `resolve_tracks(sub)` returns **2** (today: **1** — a plot line silently eaten) |
| 2 | same | `test_merge_by_two_blank_keys_in_ONE_node_both_survive` | 🔴 ONE node, two blank keys ⇒ 2 entries. **Proves no cascade is needed to lose data** |
| 3 | `tests/integration/db/test_pack_arc_wired.py` | `test_pack_arc_keeps_both_blank_keyed_tracks` | the `gather_arc` proof that **the PROMPT no longer loses a track** |
| 4 | same as 1 | `test_merge_by_strips_key_whitespace` | `" romance"` in the leaf shadows `"romance"` in the root (cross-service-normalization class) |
| 5 | `tests/unit/test_arc_hub_routes.py` + `tests/unit/test_mcp_arc_structure.py` | `test_arc_create_rejects_blank_track_key` · `test_arc_create_rejects_duplicate_track_key` | **422 at REST + validation error at MCP** — both doors |
| 6 | `tests/unit/test_arc_hub_routes.py` | `test_arc_patch_rejects_a_bad_actant` | `roster:[{"key":"traitor","actant":"villain"}]` ⇒ **422**; `{"key":"traitor","actant":"opponent","constraints":["must betray by ch.40"]}` ⇒ **200**, and it round-trips through `GET /arcs/{id}` → `resolved.roster` |
| 7 | 🔴 `tests/unit/test_mcp_server.py` | `test_arc_create_inputschema_exposes_the_actant_enum` | the LIVE `list_tools()` `inputSchema` exposes `roster.items.properties.actant.enum == ["subject","object","sender","receiver","helper","opponent"]` — **FastMCP must not strip the nested object** |
| 8 | `tests/integration/db/test_arc_apply_roundtrip.py` | `test_a_roster_from_the_new_door_extracts_cleanly` | the regression this closes: a free-form `actant:"villain"` written today is a **latent ValidationError inside `composition_arc_extract_template`** (`arc_apply.py:628-635`) |

**DoD evidence:** `python -m pytest tests -q -n auto --dist loadgroup` → `<baseline+40> passed`, plus the
pasted **G9 audit output** showing the blast radius (expected: zero rows).
**SPEC EDIT (fold into W2-S10):** amend spec 32 **AI-3** — *"the panel is the UX layer, not the enforcement
layer; the server enforces the key invariant at both doors."* And **RESOLVE OQ-2**:
*"RESOLVED 2026-07-13 — tightened at both write doors (`ArcTrack`/`ArcRosterEntry`, `extra="forbid"`); the
read model stays permissive; migration audit clean (0 non-empty rows)."*
**DELETE the `D-ARC-TRACKS-ROSTER-SCHEMA` defer row** (see §9).

---

### **W2-S4 · CONTRACT+FE · panel skeleton + the full GG-8 registration + the `arc` bus slice**
**dependsOn:** — (independent of the BE slices; the skeleton reads nothing yet)

This is the **drift-lock** slice. All of §6's steps land in **ONE commit** (the contract JSON must be
regenerated in the same commit as the catalog row + the `frontend_tools.py` enum, or the two machine
guards red).

**Files — in this exact order**

1. **CREATE** `frontend/src/features/studio/panels/useArcInspector.ts` — the controller **stub** for this
   slice: it owns only *subject resolution* (no fetches yet).

```ts
// 32 AI-1 — the arc-inspector's controller. A DETAIL-PANE-OVER-A-SELECTION, exactly like
// scene-inspector (useSceneInspector.ts:24 reads bus.activeSceneId). NOT an X-12 panel:
// plan-30 §8.2 claims a panel needing an id is structurally outside the agent enum and names
// arc-inspector — REFUTED here, by two shipped precedents (scene-inspector takes its subject
// from the bus; quality-canon is enum-listed AND accepts props.params.focusRuleId,
// QualityCanonPanel.tsx:34). So this panel is enum-listed, palette-openable by a BARE id, and
// resolves its subject in this precedence:
//   1. props.params.arcId  — an in-studio deep-link (plan-hub row → inspector)
//   2. bus.activeArcId     — the new bus slice (host/types.ts); where an agent resource_ref lands
//   3. the in-panel PICKER — so a bare-id open is NEVER a dead panel
// ⚠ Do NOT add a `params` arg to ui_open_studio_panel for this. That is a Frontend-Tool-Contract
// change (schema + CLOSED_SET_ARGS + regen + BOTH resolvers) with a real free-string hazard, and
// this panel does not need it.
export interface ArcFocusParams { bookId?: string; arcId?: string }
```
   Plus the `useStudioBusSelector((s) => s.activeArcId)` read, a local `pickedArcId` state, and
   `const arcId = params?.arcId ?? busArcId ?? pickedArcId ?? null;`. (S5 fills in the fetches.)

2. **CREATE** `frontend/src/features/studio/panels/ArcInspectorBody.tsx` — the **shared** body (dock panel
   **and** the PlanDrawer embed — AI-4/DOCK-2: ONE implementation, two hosts). No panel chrome, no picker.
   In this slice it renders only the empty / no-selection states. Props:
   `{ arcId: string | null; bookId: string; canEdit: boolean; embedded?: boolean }`.

3. **CREATE** `frontend/src/features/studio/panels/ArcInspectorPanel.tsx` — the dock panel.
   Root `data-testid="studio-arc-inspector-panel"`. Calls `useStudioPanel('arc-inspector', props.api)`.
   Reads `props.params as ArcFocusParams | undefined`. Renders header (⊕ new · ⟳ reload) + the **picker**
   + `<ArcInspectorBody/>`. **≤100 lines** (React-MVC).

4. **EDIT** `frontend/src/features/studio/panels/catalog.ts` — import + **one row**, placed next to
   `scene-inspector` (`:185`) / `plan-hub` (`:190`):

```ts
  // 32 / DBT-06 / 23-C3 — the SPEC tree's detail pane. structure_node is what gather_arc
  // (packer/lenses.py:257) injects into EVERY generation prompt; until this panel the agent had
  // full CRUD over it (8 MCP tools) and the human had none (3 of 8 routes consumed). GG-1.
  { id: 'arc-inspector', component: ArcInspectorPanel, titleKey: 'panels.arc-inspector.title', descKey: 'panels.arc-inspector.desc', category: 'editor', guideBodyKey: 'panels.arc-inspector.guideBody' },
```
   ✅ Place it **immediately after the `plan-hub` row (`catalog.ts:190`)** — same `'editor'` cluster.
   No `hiddenFromPalette` (bare-id-openable, AI-1). No `tourAnchor`.
   ✅ `'editor'` **is** a member of `CATEGORY_ORDER` (`useStudioCommands.ts:20` — verified), so X-2 does not
   *gate* this wave.

4b. 🔴 **EDIT `frontend/src/features/studio/palette/useStudioCommands.ts:20-22` — FIX X-2 NOW.**
   **The first draft said *"X-2 is Wave 1's gate, not ours. Do not fix it here."* The register OVERRIDES
   that** (`Q-32-X2-CATEGORY-ORDER`): *"'does not block' is not 'defer'. Per CLAUDE.md a one-line,
   root-cause-clear fix is fix-now — a defer row would cost more to write and carry than the fix."*
   X-2 is a live **two-surface inconsistency**, not a cosmetic gap:
   - `useStudioCommands.ts:55-56` does `CATEGORY_ORDER.indexOf(p.category)` → for `'quality'` that is **-1**,
     so the 5 Quality panels sort **FIRST** in the Command Palette, **above `'editor'`**.
   - `UserGuidePanel.tsx:24-26` puts categories *not* in `CATEGORY_ORDER` into `rest`, appended **LAST**.
   **Same constant, opposite placement** — defeating the stated purpose of exporting it.

```ts
   export const CATEGORY_ORDER: StudioPanelCategory[] = [
     'editor', 'storyBible', 'knowledge', 'quality', 'translation', 'enrichment', 'sharing', 'platform', 'discovery', 'jobs',
   ];   // 'quality' inserted after 'knowledge', mirroring the union order in catalog.ts:81-91 (X-2)
```
   Plus a **recurrence guard** in `panelCatalogContract.test.ts` (next to the existing "every
   palette-openable panel has a category" test, ~`:40`) — a NEW category must red immediately instead of
   silently top-ranking itself:
```ts
   it('every category used by a palette-openable panel is a member of CATEGORY_ORDER (X-2)', () => {
     const used = [...new Set(OPENABLE_STUDIO_PANELS.map((p) => p.category!))];
     expect(used.filter((c) => !CATEGORY_ORDER.includes(c))).toEqual([]);   // indexOf -1 sorts ABOVE 'editor'
     expect(new Set(CATEGORY_ORDER).size).toBe(CATEGORY_ORDER.length);      // no dupes
   });
```
   **NOT IN SCOPE — do not scope-creep:** no re-ordering of any other category, no `groupByCategory`
   refactor. Confirm `palette.group.quality` resolves (it falls back to the raw string at
   `useStudioCommands.ts:61-63`); if the key is absent, add **that one key** and stop.

5. **EDIT** `frontend/src/i18n/locales/en/studio.json` — add under `panels`:

```json
    "arc-inspector": {
      "title": "Arc Inspector",
      "desc": "Read and edit one arc or saga of the book's spec tree — the structure that steers generation",
      "guideBody": "The Arc Inspector is the detail pane for a single arc or saga. It shows the arc's identity (title, goal, summary, status), its cascade-resolved plot tracks and cast roster — marking which entries the arc owns and which it inherits from its saga — its chapter span, the open promises its chapters opened, and the template it came from. Title, goal, tracks and cast bindings are read into every generation prompt for the chapters in this arc; summary and status are labels for you and the Plan Hub. Everything here is free — no model runs, no cost. Select an arc from the picker, from the Plan Hub, or ask the agent to open one.",
      "none": "Pick an arc, or create the first one — the spec tree is what steers generation.",
      "empty": "No arcs yet — the spec tree is what steers generation.",
      "createFirst": "Create the first saga",
      "loading": "Loading…",
      "notAccessible": "This arc is no longer accessible.",
      "loadFailed": "Couldn't load this arc.",
      "retry": "Retry",
      "readOnly": "You have view access to this book.",
      "archivedBanner": "Archived — restore to edit.",
      "restore": "Restore",
      "showArchived": "Show archived",
      "conflict": "This arc changed elsewhere — reloaded. Re-apply your edit.",
      "section": {
        "identity": "Identity",
        "tracks": "Tracks",
        "roster": "Roster",
        "chapters": "Chapters",
        "promises": "Open promises",
        "provenance": "Provenance",
        "danger": "Danger"
      },
      "f": {
        "kind": "Kind",
        "title": "Title",
        "goal": "Goal",
        "summary": "Summary",
        "status": "Status",
        "parent": "Parent"
      },
      "hint": {
        "goal": "Reaches the prompt — this arc's goal only (an ancestor saga's goal is dropped).",
        "summary": "For you and the Plan Hub. Not a prompt input.",
        "roster": "The slots are the schema the bindings fill. The BINDINGS reach the prompt; the slots do not.",
        "free": "Free — no model runs, no cost."
      },
      "cascade": {
        "own": "own",
        "inherited": "inherited",
        "from": "from {{kind}} “{{title}}”",
        "override": "Override here",
        "overrideDone": "Copied into this arc — it now shadows the inherited entry.",
        "effective": "effective {{n}} · own {{own}} ⊕ inherited {{inherited}}"
      },
      "keyError": "A key is required, must not be empty, and must be unique in this arc.",
      "nonContiguous": "Non-contiguous — gaps in the reading order.",
      "unbound": "— not bound —",
      "bind": "Bind…",
      "unbind": "Unbind",
      "change": "Change",
      "addTrack": "+ track",
      "addRole": "+ role",
      "assignChapters": "+ assign chapters…",
      "removeChapter": "Remove from arc",
      "noTemplate": "Authored from conversation (no template)",
      "archive": "Archive arc",
      "archiveConfirm_one": "Archive “{{title}}” and its {{count}} sub-arc?",
      "archiveConfirm_other": "Archive “{{title}}” and its {{count}} sub-arcs?",
      "archiveConfirmLeaf": "Archive “{{title}}”?",
      "archiveChaptersNote_other": "{{count}} chapters stay bound to the archived arc. Unassign them first if you want them back in the unassigned pool.",
      "newArc": "New arc",
      "newSaga": "New saga",
      "create": "Create arc",
      "cancel": "Cancel"
    },
```
   ⚠ **Never edit an existing `en` string that already has 17 translations** — `i18n_translate.py`
   gap-fills only, so an edited `en` leaves the 17 permanently stale (the note at
   `QualityCanonPanel.tsx:52`). These are all NEW keys, so we are safe.

6. **GENERATE** `frontend/src/i18n/locales/{ar,bn,de,es,fr,hi,id,ja,ko,ms,pt-BR,ru,th,tr,vi,zh-CN,zh-TW}/studio.json`
   — **`python scripts/i18n_translate.py`** (needs LM Studio on :1234). **Never hand-write.** If the tool
   cannot run, **defer the 17 locales as `D-ARC-I18N-LOCALES` (gate #4 — blocked on a local model) and
   ship `en`**; the FE falls back to `en`, so this is a cosmetic gap, not a broken panel. Do not block the
   wave on it.

7. **EDIT** `services/chat-service/app/services/frontend_tools.py` — **two edits**:
   - **(a)** append `"arc-inspector"` to the `panel_id` **enum** (`:402`).
   - **(b)** append a clause to the tool **description** prose, next to `'plan-hub'` (~`:449`) — *that gloss
     is the model's only hint the panel exists*:

     > `"'arc-inspector' = read/edit ONE arc or saga of the book's spec tree — its title/goal/status, "`
     > `"the cascade-resolved plot tracks and cast roster (marking what it owns vs inherits from its "`
     > `"saga), its chapter span, its open promises, and its template provenance. This is the structure "`
     > `"that steers every generation; "`

8. **REGENERATE** `contracts/frontend-tools.contract.json` — **NEVER hand-edit**:
   ```bash
   cd services/chat-service && WRITE_FRONTEND_CONTRACT=1 python -m pytest tests/test_frontend_tools_contract.py
   ```
   Commit the regenerated JSON **in this same commit** as steps 4 + 7.

9. **EDIT** `frontend/src/features/studio/host/types.ts` — three additive edits (AI-1). 🔴 **`arcId` IS
   NULLABLE** (`Q-32-BUS-SLICE-ARC` — the one amendment to the spec). Spec 32 §3.4 requires the panel to
   **clear the bus slice** on a 404, and `arcId: string` makes clearing **inexpressible**. The first draft's
   workaround (*"publish `arcId: ''` and treat `''` as none"*) is a magic-string sentinel — **do not ship
   it.** Mirror `PlanCanvas.tsx:267`'s `onSelect(null)`:
   ```ts
   // StudioBusEvent — 32 AI-1: the arc slice. plan-hub publishes it on an arc/saga selection; the
   // arc-inspector subscribes. Same one-line-per-slice shape as `scene`. `null` CLEARS the slice —
   // its ONE publisher is the inspector itself, on a 404 (spec §3.4), which drops it back to the picker.
   | { type: 'arc'; arcId: string | null }

   // StudioBusSnapshot
   /** 32 AI-1 — the arc the Plan Hub last selected (arc/saga node), or the agent's resource_ref.
    *  The arc-inspector's subject when props.params.arcId is absent. Cleared on a 404 / revoked grant. */
   activeArcId?: string;

   // applyBusEvent
   case 'arc':
     return { ...base, activeArcId: e.arcId ?? undefined };
   ```
   **Defaults, stated so the PO can veto without a checkpoint** (`Q-32-BUS-SLICE-ARC` §3):
   (a) a **pane-click deselect does NOT publish `null`** — only an arc/saga **select** publishes. The
   inspector's subject persisting after a stray canvas click matches `scene-inspector` (nobody ever nulls
   `activeSceneId`); a disappearing inspector is worse than a slightly stale one.
   (b) **`arcId: null` has exactly ONE publisher: the inspector, on 404.**
   (c) **a `saga` counts as an arc subject** (`PlanNodeContent.kind` is the discriminator — no new type).
   (d) the event carries **no `bookId`** (unlike `chapter`) — the snapshot is already per-book and the host
   remounts on a book switch (`StudioHostProvider.tsx:72`).

9b. 🔴 **EDIT `frontend/src/features/studio/panels/PlanHubPanel.tsx` — THE PUBLISHER.** Without it the bus
   slice has **no producer** and the whole AI-1 hand-off is dead code. `useStudioHost` is **already
   imported** (`:24`) and `view.nodeContent[id].kind` already yields `'arc'|'saga'|'chapter'|'scene'`
   (used at `:172-173`). Add ONE callback and route **BOTH** existing selection entry points through it:
   ```ts
   // 32 AI-1 — the reverse publish this file's header deferred ("no consumer reads a Hub-selection
   // bus slice yet"). The arc-inspector is that consumer. Delete that header note (lines 20-21).
   const selectNode = useCallback((id: string | null) => {
     view.select(id);
     if (!id) return;                       // deselect does NOT clear the inspector's subject (default a)
     const kind = view.nodeContent[id]?.kind;
     if (kind === 'arc' || kind === 'saga') host.publish({ type: 'arc', arcId: id });
   }, [view.select, view.nodeContent, host]);
   ```
   - `:217` — `onSelect={view.select}` → `onSelect={selectNode}`
   - `:112` (inside `focusNode`) — `select(nodeId)` → `selectNode(nodeId)`, so a **Plan-rail row focus**
     publishes too. Hoist `selectNode` above `focusNode`, add it to `focusNode`'s dep array, drop `select`.
   - Update the file-header comment (`:20-21`) — the *"reverse publish is deferred"* note is now **false**.

10. **SKIP** `frontend/src/features/studio/onboarding/tours.ts` (not a role-tour step in v1) and
    `frontend/src/features/studio/host/studioLinks.ts` (no external URL resolves to an arc).
    **Do NOT touch** `StudioDock.tsx`, `StudioFrame.tsx`, `useStudioCommands.ts`, `UserGuidePanel.tsx`
    (all derive from `catalog.ts`), or `studioUiNav.ts` / `useStudioUiToolExecutor.ts` (panel-id-agnostic).

**Tests**

| File | Test | Asserts |
|---|---|---|
| `frontend/src/features/studio/panels/__tests__/panelCatalogContract.test.ts` (**existing — must stay green**) | all 4 | `enum == openable`, every enum id is buildable, every openable has a `category` |
| `frontend/src/features/studio/host/__tests__/busEvents.test.ts` (**CREATE** — grep for an existing `applyBusEvent` test first and extend it if one exists) | `applyBusEvent reduces an arc event onto activeArcId` | `applyBusEvent(snap, {type:'arc', arcId:'A'}).activeArcId === 'A'` and `revision` bumped by 1 |
| `frontend/src/features/studio/panels/__tests__/ArcInspectorPanel.test.tsx` (**CREATE**) | `renders the picker, never a blank pane, with no selection` | with no `params` and an empty bus, the root `[data-testid="studio-arc-inspector-panel"]` renders **and** contains `[data-testid="arc-picker"]` — asserting the *absence of a dead panel* |
| same | `props.params.arcId wins over the bus` | render with `params={{arcId:'A'}}` and bus `activeArcId='B'` ⇒ the detail fetch is keyed on `'A'` |

**DoD evidence** — the pasted output of all four drift-locks, and the delta:
```bash
cd services/chat-service && python -m pytest tests/test_frontend_tools_contract.py tests/test_frontend_tools.py -q
cd frontend && npx vitest run \
  src/features/studio/panels/__tests__/panelCatalogContract.test.ts \
  src/features/studio/panels/__tests__/UserGuidePanel.test.tsx \
  src/features/studio/palette/__tests__/useStudioCommands.test.ts \
  src/features/chat/nav/__tests__/frontendToolContract.test.ts
```
> 🔴 **Assert the DELTA and the three-way equality — NEVER the literal.** `py enum == contract enum ==
> OPENABLE_STUDIO_PANELS`, and the count is **pre-flight-G4 baseline + 1**. Six of the eight Wave specs
> got this wrong by each computing from 57 as if it were the only wave (plan 30 §8.0 note 6). If Wave 1
> landed first the number is 62; if not, 58. **The test asserts equality, not a number.**
>
> 🔴 **DO NOT ADD A COUNT-PINNING TEST** (`Q-32-DRIFT-LOCK-COUNT-CONTRADICTION`, `Q-32-WAVE1-ORDERING-DEP`).
> Verified: **nothing in the repo asserts a panel COUNT.** `panelCatalogContract.test.ts:23` asserts only
> `enumIds.length > 0`; `:33` is `expect([...enumIds].sort()).toEqual(openable)` — a **SET** comparison with
> no number in it. `test_frontend_tools_contract.py` snapshots a schema and enforces conventions — again, no
> count. So **57 / 58 / 61 / 62 are all irrelevant to green**, and **Wave 2 is ORDERING-INDEPENDENT of Wave 1**
> (plan 30 §9 already puts Waves 1‖2‖3 in parallel, and they touch disjoint new files: `arcEffects.ts` vs
> `compositionEffects.ts`). A builder who lands Wave 2 first gets 57→58; second gets 61→62; **both green.**
> ⚠ **If Wave 1 and Wave 2 run CONCURRENTLY in separate worktrees** they append rows to four shared files
> (`catalog.ts`, `frontend_tools.py`, `contracts/frontend-tools.contract.json`, the 18 `studio.json` locales).
> Those are append-only ⇒ they text-merge — **EXCEPT the generated contract JSON. NEVER hand-merge it:**
> after the merge, re-run `WRITE_FRONTEND_CONTRACT=1 pytest …/test_frontend_tools_contract.py`, commit the
> **regenerated** file, then run the FE suite.

---

### **W2-S4b · CONTRACT+FE · `resource_ref` — the agent's deep-link leg (X-6 / AN-12)**
**dependsOn:** W2-S4 · **Origin:** `Q-32-X6-RESOURCE-REF-UNWRITTEN`

> **The first draft shipped the panel core and left the agent with no way to POINT AT AN ARC.** The register
> refuses the split: *"Do not block on X-6, and do NOT split the panel ('core now, resource_ref leg later').
> X-6 is a SPEC SECTION TO WRITE — unbuilt work, not an external dependency (CLAUDE.md anti-laziness). Every
> code seam already exists and is proven by a shipped twin."*
>
> 🔴 **`resource_ref` IS NOT `params`. Do not conflate them.**
> - **`params` (free-form `Record<string, unknown>`) stays FORBIDDEN** on `ui_open_studio_panel`
>   (`Q-32-X12-AMEND-PLAN30`, `Q-32-AI1-ADDRESSING`): it would re-create the exact free-string shape of
>   `ui_show_panel`, which **PO-3 is RETIRING**. The in-studio deep-link path already carries params through
>   `host.openPanel(panelId, { params })` — no tool-schema change needed for it.
> - **`resource_ref { kind, id, version? }` is a CLOSED-SET arg** — `kind` gets an `enum`, gets registered in
>   `CLOSED_SET_ARGS`, and the resolver **returns `result.error`** on an unknown kind. That is exactly what
>   the Frontend-Tool Contract *demands*, not what it forbids. Both statements are true.

**Files**

1. **SPEC (Wave 0's row, but write it here rather than stall — `Q-32-X6` step 1 + its FALLBACK clause):**
   `docs/specs/2026-07-01-writing-studio/28_agent_native_studio.md` — add the **AN-12** section:
   `resource_ref = { kind: 'structure'|'outline'|'motif_application'|'canon_rule'|'thread', id: string, version?: number }`.
   ⚠ **If the AN-12 section is not on disk when this slice opens: DO NOT STALL and DO NOT FILE A DEFER ROW.**
   arc-inspector consumes exactly **one** variant (`kind: 'structure'`) — implement steps 2-5 with that single
   enum member and **write the AN-12 section from the shipped shape.** *A spec paragraph is never a blocker.*

2. **EDIT** `services/chat-service/app/services/frontend_tools.py` — add the optional `resource_ref` **object**
   arg to `UI_OPEN_STUDIO_PANEL_TOOL` (`:391` — today it carries `panel_id` **only**). `kind` MUST declare an
   `enum` and MUST be registered in **`CLOSED_SET_ARGS`**. Then **regenerate**
   `contracts/frontend-tools.contract.json` (`WRITE_FRONTEND_CONTRACT=1 pytest`).

3. **EDIT** `frontend/src/features/studio/agent/studioUiNav.ts:27-38` (the `ui_open_studio_panel` case) —
   today it calls `host.openPanel(panelId)` and **DROPS opts** (`:37`). Pass them through, and when
   `resource_ref.kind === 'structure'` the effect **ALSO** publishes:
   `host.publish({ type: 'arc', arcId: ref.id })` (+ `openPanel('arc-inspector', { focus: true })` if closed).
   🔴 **An unknown or malformed `kind` returns `{ result: { opened: false, error: … } }` — NEVER a silent
   no-op** (the shipped error shape is `studioUiNav.ts:34`). The silent-no-op is the exact bug the
   Frontend-Tool Contract exists to kill (`panel_id` had no enum → gemma sent `panel:"editor"` → silent
   no-op → hallucinated success).

> **The ONE place the register disagrees with itself — resolved here, do not re-open.**
> `Q-32-X6` step 3 proposes bus fields `arcFocusId` / `arcFocusVersion` / **`arcFocusSeq`** (mirroring
> `planFocusNode`, whose seq bump is load-bearing so that pointing at the SAME node twice is not a no-op).
> **Three other rows** (`Q-32-BUS-SLICE-ARC`, `Q-32-AI1-ADDRESSING`, `Q-32-REGISTRATION-CHECKLIST-GG8`) name
> **`activeArcId`**, mirroring the shipped `activeSceneId`. **BUILD `activeArcId`** (W2-S4 step 9) — it is
> the majority shape, it mirrors the shipped twin, and it is what the panel's *subject* semantics need.
> **The seq concern is real and is satisfied without a second field:** re-pointing at the same arc is
> **idempotent for a detail pane** (it already shows that arc), and the *focus* half — raise the tab, scroll
> it into view — is carried by **`openPanel(id, { focus: true })`**, which the resolver calls anyway.
> **Do NOT add `arcFocusSeq`. Do NOT add a second arc slice.** One name for one concept.

**Tests**

| File | Test | Asserts |
|---|---|---|
| `frontend/src/features/studio/host/__tests__/arcBus.test.ts` (**CREATE** — mirror `planFocusBus.test.ts:11-38`) | reducer | `applyBusEvent(empty(), {type:'arc', arcId:'a1'}).activeArcId === 'a1'` and `revision` bumped · `{type:'arc', arcId:null}` **clears it to `undefined`** and **still bumps `revision`** · an `arc` publish leaves `activeChapterId`/`activeSceneId` **untouched** (additive, non-clobbering) |
| `frontend/src/features/studio/panels/__tests__/PlanHubPanel.test.tsx` (**EDIT**) | the publisher | clicking an **arc/saga** node publishes `{type:'arc'}`; clicking a **CHAPTER** node does **not** |
| `frontend/src/features/studio/agent/__tests__/studioUiNav.test.ts` (**EDIT**) | the resolver | `resource_ref {kind:'structure', id}` **opens the panel AND publishes** · 🔴 an **unknown kind** returns `result.error` with **NO effect** (the silent-no-op guard) |
| `frontend/src/features/chat/nav/__tests__/frontendToolContract.test.ts` | drift-lock | stays green (py enum == contract enum == openable set) |

**DoD evidence:** `npx vitest run src/features/studio/host src/features/studio/agent` → `N passed`, plus the
chat-service contract test green. **The LIVE proof is W2-S10 leg 8 — verify by EFFECT (a dock TAB), never a
`shown:true` in the raw stream.**

---

### **W2-S5 · FE · the panel, READ-ONLY — every section, every state**
**dependsOn:** W2-S0 (contract), **W2-S1** (the derived block + `gap_count`), **W2-S1b** (`resolved.provenance`
— the panel cannot render the cascade without it), W2-S4

**Files**

1. **EDIT** `frontend/src/features/plan-hub/types.ts` — **widen `ArcListNode` (the type that lies)**. It
   declares 12 of the wire's 20 fields (`app/db/models.py:194-228`); the missing 8 are exactly the ones this
   wave edits. Add: `book_id: string`, `created_by: string | null`, `tracks: ArcTrack[]`,
   `roster: ArcRole[]`, `roster_bindings: Record<string, string>`, `is_archived: boolean`,
   `created_at: string`, `updated_at: string`. And add the new types:

```ts
/** A parallel plot line. `key` is the CASCADE key — StructureRepo._merge_by shadows by it
 *  (structure.py:586-597). A missing key can never be shadowed; an empty key collides on "" across
 *  the whole ancestor chain. Neither door validates it — the panel does (AI-3). */
export interface ArcTrack { key: string; label?: string; [k: string]: unknown }
/** An abstract cast SLOT. NOT a packer input (resolve_roster is never called by the packer) — it is
 *  the schema `roster_bindings` fills, and what extract_template_from_arc reads (arc_apply.py:564). */
export interface ArcRole { key: string; actant?: string; label?: string; constraints?: unknown[]; [k: string]: unknown }
/** GET /v1/composition/arcs/{node_id} — the enriched detail (arc.py:438). */
export interface ArcDetail extends ArcListNode {
  resolved: { tracks: ArcTrack[]; roster: ArcRole[]; roster_bindings: Record<string, string> };
  open_promises: { id: string; kind: string; summary: string; priority: number; status: string }[];
  // The derived block, AFTER BE-A1: the same shape + unit as the LIST route. All four are null for
  // an ARCHIVED arc — which means NOT-COMPUTED, not zero. Gate the "—" on `is_archived`, never on
  // falsiness (chapter-blocks-null-nontext-coalesce).
  span: { from_order: number; to_order: number } | null;
  chapter_count: number | null;
  is_contiguous: boolean | null;
  first_story_order: number | null;
}
```
   🔴 **AND MAKE THE DERIVED BLOCK NULLABLE** (W2-S1 edit 4 — the list route now emits all-null for an
   archived node): `chapter_count: number | null`, `is_contiguous: boolean | null`,
   `first_story_order: number | null`, **`gap_count: number | null`** (new). `laneLayout.ts:34` only ever
   sees **live** nodes (the Hub never requests archived), but **type it nullable and treat `null` as `true`**
   — a node whose contiguity was never computed must **not** render a warn band.

   **Test-fixture fallout — 4 factories will red on typecheck** (`Q-32-ARCLISTNODE-WIDENING` step 4). Give
   them defaults (`book_id:'b1'`, `created_by:null`, `tracks:[]`, `roster:[]`, `roster_bindings:{}`,
   `is_archived:false`, `created_at:null`, `updated_at:null`):
   `components/__tests__/PlanDrawer.test.tsx:36` · `components/__tests__/PlanNavigatorRail.test.tsx:16` ·
   `hooks/__tests__/planHubMappers.test.ts:13` · `hooks/__tests__/usePlanMoves.test.tsx`.
   **Add the cast-free regression test:** pass an arc with `tracks:[{key:'romance',label:'Romance'}]` through
   the factory **without any cast** and assert the drawer renders it. **`npx tsc --noEmit` is the gate** — a
   cast-free fixture is what proves the widening is real and not cosmetic.

   ⚠ `PlanDrawer.tsx:308`'s defensive cast (`arc as ArcListNode & { tracks?: unknown; roster?: unknown }`)
   is a **type lie** that only existed because the type was wrong. **W2-S9 deletes it** along with `ArcFacets`
   and `rosterKeysOf`. `laneLayout`'s `ArcShellNode` subset and `planHubMappers.ts:42 toArcShellNode` are
   **unaffected** (structural subset projection) — do not touch them.

2. **EDIT** `frontend/src/features/plan-hub/api.ts` — the ONE owner of `/v1/composition/arcs/*` (LA-3). Add
   **five** typed fetches next to `moveArc`/`assignChapters`:

```ts
/** 32 — the enriched arc detail. `resolved` is the root→leaf cascade (structure.py:599-616), the
 *  top-level tracks/roster/roster_bindings are the node's OWN. Rendering only `resolved` is the
 *  shadow-copy bug (AI-2) — the panel needs both. */
export function getArc(nodeId: string, token: string): Promise<ArcDetail> {
  return apiJson<ArcDetail>(`${COMP}/arcs/${nodeId}`, { token });
}

/** 32 — create a saga or arc. `kind` is a CLOSED SET OF TWO: 'saga' | 'arc'. There is NO `sub_arc`
 *  kind (the DB CHECK is `kind IN ('saga','arc')`, migrate.py:1102; the body is
 *  Literal["saga","arc"], arc.py:333). A sub-arc is an ARC whose parent is an arc (depth 2) — a
 *  depth label, not a kind. A picker offering `sub_arc` 422s. */
export function createArc(
  bookId: string,
  body: { kind: 'saga' | 'arc'; parent_arc_id?: string | null; title: string; summary?: string; goal?: string; status?: string },
  token: string,
): Promise<ArcDetail> {
  return apiJson<ArcDetail>(`${COMP}/books/${bookId}/arcs`, { method: 'POST', token, body: JSON.stringify(body) });
}

/** 32 — patch an arc's content. OCC: `If-Match: <version>` is REQUIRED after BE-A2 (absent ⇒ 428).
 *  A 412 carries the CURRENT row in `detail.current` — seed it, never clobber. */
export function updateArc(          // 🔴 NOT `patchArc` — DoD #3's route gate greps for this exact name
  nodeId: string,
  body: Partial<Pick<ArcDetail, 'title' | 'summary' | 'goal' | 'status' | 'tracks' | 'roster' | 'roster_bindings'>>,
  version: number,
  token: string,
): Promise<ArcDetail> {
  return apiJson<ArcDetail>(`${COMP}/arcs/${nodeId}`, {
    method: 'PATCH', token, headers: { 'If-Match': String(version) }, body: JSON.stringify(body),
  });
}

/** 32 — soft-archive an arc AND its sub-arc subtree (structure.py:404). After W2-S1b the response
 *  carries `archived_ids` + `archived_count`. ⚠ The CONFIRM still client-derives the count from the
 *  shell (it renders BEFORE the call, when no response exists); the TOAST reads `archived_count`
 *  from the RESPONSE, so a concurrent write that changed the subtree is reported truthfully (OQ-3). */
export function archiveArc(nodeId: string, token: string):
  Promise<{ id: string; archived: boolean; archived_ids: string[]; archived_count: number }> {
  return apiJson(`${COMP}/arcs/${nodeId}`, { method: 'DELETE', token });
}

/** 32 — the verified inverse: restores the subtree AND reconnects the archived ancestor chain. */
export function restoreArc(nodeId: string, token: string): Promise<{ id: string; archived: boolean }> {
  return apiJson(`${COMP}/arcs/${nodeId}/restore`, { method: 'POST', token });
}
```
   And **widen the existing `assignChapters`** (`:241`) to `structureNodeId: string | null` (BE-A3), with the
   comment: *"`null` ⇒ UNASSIGN — the only way a chapter leaves an arc. Archiving the arc does NOT unassign
   its chapters (structure.py:404 flips is_archived on structure_node only)."*

3. 🔴 **CREATE** `frontend/src/features/books/hooks/useBookGrant.ts` — **NOT** `useBookAccess`, and it
   consumes **NO new route.** (`Q-32-403-READONLY-GRANT-SOURCE`; §0.1 LA-1.) **The grant is already on the
   wire and the FE throws it away**: `GET /v1/books/{book_id}` returns a per-caller
   **`access_level` ∈ `owner|manage|edit|view|none`** (`server.go:957`/`:987`), and
   `grep -rn "access_level" frontend/src` → **ZERO hits**. This is `rest-write-mirror-drops-fields` in read
   form. **Read the field. Do not build a route.**

   3a. **EDIT** `frontend/src/features/books/api.ts:6` — add to `type Book`:
   `access_level?: 'owner' | 'manage' | 'edit' | 'view' | 'none';` *(server-computed; never sent by the client.)*

```ts
// The E0 grant the caller holds on this book. Reads `access_level` off the book detail the studio
// ALREADY caches under ['book', bookId] (BookSettingsPanel.tsx:32, GlossaryPanel.tsx:34 — the SAME
// key + the SAME booksApi.getBook) ⇒ a CACHE HIT, not a second request. Do not invent a new key.
//
// FAILS CLOSED: while unresolved (loading / error / undefined) canEdit === false, so a control that
// would 403 is never rendered — not even for one frame (memory: spend-causing-setting-fails-closed).
export type BookGrant = NonNullable<Book['access_level']>;
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
    // `manage` is edit-capable: it is >= EDIT in book-service's ordered GrantLevel
    // (collaborators.go:23-27) and composition's arc PATCH gates on GrantLevel.EDIT (arc.py:498).
    canEdit: level === 'owner' || level === 'manage' || level === 'edit',
    resolved: q.isSuccess && level !== undefined,
    loading: q.isLoading,
  };
}
```
   **Rejected alternatives — do not "improve" this back into one of them:** (a) a **probe request** — it
   learns the grant only *after* a 403, which is exactly what §3.4 forbids; (b) a **new `writes` source**
   threaded from the studio host — the grant is a **server fact**, not a prop, and a second copy is a second
   name for one concept; (c) `GET /books/{id}/collaborators` — **owner-only** (`server.go:290`), so it 403s
   for the very users we need to detect; (d) `GET /internal/books/{id}/access` — **internal S2S token only**,
   unreachable from a browser.

   3b. 🔴 **`ArcInspectorBody` RESOLVES ITS OWN GRANT.** Props are exactly
   **`{ arcId: string; bookId: string; embedded?: boolean }`** — **no `canEdit` prop, and above all NO
   `writes` prop.** (`Q-32-PLANDRAWER-BOOKID-PROP`: *"gate inside `ArcInspectorBody` on the grant it already
   resolves, not on a host-supplied writes bundle."*) One grant reader ⇒ the dock panel and the drawer
   **cannot disagree**. ⚠ **NEVER pass `PlanDrawer`'s `writes` in**: that is the **PH20 OUTLINE** bundle
   (`patchNode → PATCH /outline/nodes/{id}`, `api.ts:136`) with a `NodeEdit` patch shape — threading it into
   an ARC body would **route arc edits at the outline endpoint** and would not even typecheck.

   3c. **ONE-LINE HARDENING while you are in there** (`Q-32-403` step 4): in
   `frontend/src/features/plan-hub/hooks/usePlanHub.ts:208`, return
   `writes: canEdit ? nodeWrites : undefined` using `useBookGrant(bookId)`. Today `PlanHubPanel.tsx:289`
   **unconditionally** passes `writes`, so the Hub's drawer renders EDIT controls to a VIEW-only
   collaborator. It is one line, it is root-cause-clear, and it is in a file this wave already opens.

4. **EDIT** `frontend/src/features/studio/panels/useArcInspector.ts` — the full controller (**≤200 lines**;
   split the cascade merge into a pure helper file if it grows). It owns:

   - **shell** — `useQuery({queryKey: ['plan-hub','arcs',bookId], queryFn: () => getArcs(bookId, token)})`
     — the **same** key `usePlanHub`/`usePlanNode` use, so TanStack dedupes to **one** fetch and the picker,
     the breadcrumb and the blast radius all come free. Also fetch a second, archived-inclusive shell
     **only when the picker's "Show archived" is on** (`getArcs` needs an `includeArchived` param — add it:
     `?include_archived=true`, key `['plan-hub','arcs',bookId,'archived']`).
   - **detail** — `useQuery({queryKey: ['plan-hub','arc', arcId], queryFn: () => getArc(arcId, token), enabled: !!arcId})`.
     🔴 **The key MUST be under the `['plan-hub']` prefix** — `usePlanNodeWrites.settle()` (`:52`) and the
     Wave-2 `arcEffects` handler both invalidate that prefix. A key outside it goes silently stale.
     (`['plan-hub','node',id]` is the *outline* node — do not collide.)
   - **conformance badge** — `useConformanceStatus(bookId)` → `status.arcs.find(a => a.structure_node_id === arcId)`
     → `{dirty, dirty_reasons, stale_chapters.length}`. **Zero new backend.**
   - **member chapters** — `getChildren(bookId, {structureNodeId: arcId}, {cursor, limit: 100, token})`,
     keyset-paged (`plan-hub/api.ts:33`). **Virtualize above ~200 rows.**
   - **roster names** — `useGlossaryRoster(bookId, token)` → `Map<entity_id, display_name>`. Shared cache
     with `scene-inspector`. An unresolved id renders the **raw id**, never a silent blank (PH26).
   - **template provenance** — `arcApi.get(arc.arc_template_id, token)` when non-null, keyed
     `['composition','arc-template', arcTemplateId]`, `enabled: !!arcTemplateId`, `staleTime: 300_000`.
     A **null** `arc_template_id` is NORMAL (BA13) → *"Authored from conversation (no template)"* — **not an
     error, not amber, no `role="alert"`.** See the Provenance section below.
   - **grant** — `useBookGrant(bookId)` → `canEdit` (fail-closed).
   - **member chapters** — a dedicated hook, **`useArcChapters.ts`** (see W2-S7).

   **The cascade (AI-2) — 🔴 READ IT OFF THE SERVER. DO NOT RE-DERIVE IT IN TYPESCRIPT.**

> **The first draft planned a pure client helper (`arcCascade.ts::splitCascade`) that walked the shell's
> ancestors and diffed key-sets. THE REGISTER FORBIDS IT** (`Q-32-AI2-CASCADE-OWN-VS-INHERITED`):
> *"the FE NEVER re-merges the cascade and never diffs key-sets itself."*
> **Why this matters more than it looks:** the shadow rule lives in `_merge_by` (`structure.py:586-597`) and
> W2-S3b is **changing it this very wave** (blank/whitespace keys). A TypeScript copy of that rule is a
> **second SSOT** that would already be wrong on the day it shipped — the
> `css-var-duplicated-across-two-consumers-drifts` class, in the one place where drift silently forks a
> user's plot track away from its saga.
> **⇒ `splitCascade` is DELETED. W2-S1b's `resolved.provenance` sidecar is the source.**

   Each of the 3 sections (**Tracks / Roster / Roster bindings**) iterates **`resolved.<x>`** — the
   **EFFECTIVE** set, i.e. exactly what `gather_arc` injects — and looks each key up in
   **`resolved.provenance.<x>`**. That is the whole algorithm. A thin presenter
   (`frontend/src/features/studio/panels/arc/cascadeRows.ts`) may zip the two into render rows; it contains
   **no merge logic, no key diffing, no ancestor walk**.

| `provenance[key]` | Render |
|---|---|
| `is_own === true`, `shadows_node_id === null` | editable in place (inline edit → PATCH) |
| `is_own === true`, `shadows_node_id !== null` | editable, **plus a second action: [Revert to inherited]** — removes it from the own array and PATCHes; the row then re-renders as inherited. **Without this the fork is ONE-WAY** (the first draft had no escape hatch) |
| `is_own === false` | **greyed, read-only, no input focusable**, badge `Inherited from "<provenance.title>"`, and **exactly ONE action: [Override here]** |
| **no provenance row** (key missing/empty) | read-only + the AI-3 inline warning *"This entry has no key — it cannot be overridden or shadowed. Add a key to edit it."* **Do NOT offer Override.** |

   **Section header counts the EFFECTIVE set** — `resolved.<x>.length`, i.e. exactly what reaches the prompt.
   **Not** the own array's length; **not** own+inherited double-counted. Sub-caption:
   `N effective · M own · K inherited`.

5. **EDIT** `ArcInspectorBody.tsx` — the six read sections, exactly as the mock (`screen-arc-inspector.html`
   ①), each with a `data-testid`:

| Section | testid | Renders | Prompt provenance (state it in the UI — §1 of the spec) |
|---|---|---|---|
| Header/subject | `arc-inspector-subject` | breadcrumb (`ancestor_chain` from the shell), status `<select>`, `v{version}`, the conformance badge, `created_by` + `updated_at` | — |
| Identity | `arc-inspector-identity` | Kind (badge + `depth`), Title, Goal, Summary | Title → **every node of the chain**; Goal → **this leaf's only** (an ancestor saga's goal is DROPPED, `lenses.py:303`); Summary + Status → **not in the prompt**, human-read labels |
| Tracks | `arc-inspector-tracks` | own rows (editable) + inherited rows (greyed, read-only, one action: **Override here**). Header counts the **effective** set | `resolved.tracks` → **PROMPT** (`lenses.py:307-316`) |
| Roster | `arc-inspector-roster` | effective SLOTS (key · actant · label) each with its effective BINDING chip (name via `useGlossaryRoster`) or *"— not bound —"* | **`roster_bindings` → PROMPT** (`lenses.py:337-344`). **`roster` (the slots) → NOT a packer input** — its consumer is `extract_template_from_arc` (`arc_apply.py:564`). ⚠ **Do not tell the user the slots steer generation.** |
| Chapters | `arc-inspector-chapters` | `span.from_order–span.to_order` + `chapter_count`; the **`gap_count` chip** (below); the virtualized member list (W2-S7) | derived |
| Open promises | `arc-inspector-promises` | the rollup, priority-sorted, each deep-linking to `quality-promises` via `openPanel('quality-promises', {focus:true, params:{bookId, focusThreadId: p.id}})` (the **exact** call `PlanHubPanel.tsx:73` already makes) | derived, read-only |
| Provenance | `arc-inspector-section-provenance` | **RENDERED UNCONDITIONALLY** — 4 states, below. **NO raw UUID in any of them.** **NO `[open]` button in Wave 2.** | — |

**🔴 THE `gap_count` CHIP — from the SERVER, never derived** (`Q-32-NONCONTIGUOUS-WARN-ONLY`). The first
draft rendered client-derived *"gap rows"* (`— gap: 43–44 unassigned —`). **Forbidden:** the children route
is **keyset-paged**, so a client count over the loaded window reports **not-yet-loaded chapters as gaps**;
and raw `story_order` is strided ×1000, so a client min/max diff calls **every** arc non-contiguous. Render
from the detail payload only:

| `is_contiguous` / `gap_count` | Render |
|---|---|
| `true` | nothing |
| `false`, `gap_count > 0` | `⚠ Non-contiguous — {{count}} gaps in the reading order` (i18n plural) |
| `false`, `gap_count === null` | `⚠ Non-contiguous — some chapters have no reading position, or share one` |

A **muted/amber chip in the section header. NEVER an error banner, never a red state, never a blocking
dialog.** **WARN-ONLY IS ENFORCED BY A TEST, NOT A COMMENT** (W2-S7): with `is_contiguous:false, gap_count:3`,
*"+ assign chapters"*, *"remove"*, and every identity/status control are **enabled and their mutations fire.**

**🔴 THE PROVENANCE SECTION — 4 states, and the 36-char hex is NEVER the visible value in any of them**
(`Q-32-PLANDRAWER-TEMPLATE-UUID`). Today `PlanDrawer.tsx:344` **hides the whole section** when provenance is
null — so **BA13's NORMAL state has no surface at all** — and `:346` renders the raw `arc_template_id` **UUID**
to a novelist. Both die with `ArcFacets` (W2-S9). Delete the `&&` guard; the section is **always** one of:

| State | Render |
|---|---|
| `arc_template_id == null` (**BA13 — the normal case**) | muted line *"Authored from conversation (no template)"*. **Normal tone.** Not an error, not amber, no `role="alert"`, no "missing"/"unknown" wording |
| loading | a skeleton in the name slot. **Never the UUID as a placeholder** |
| resolved | `From template: {template.name} · v{arc.template_version}` — ⚠ **the version printed is the ARC NODE's `template_version`** (the `structure_node` column), **NOT `template.version`** (the template's *current* version). Printing the live version would silently relabel a **stale** arc as fresh |
| `arcApi.get` rejects (404 — a foreign/private/deleted template returns the uniform 404, `arc.py:163-165`) | `From template: — no longer visible to you — · v{arc.template_version}`. **Not** a panel error state, **not** a retry loop. The raw UUID may appear **only** as a `title=` tooltip on that fallback line (support/debug), **never as rendered text** |

🔴 **NO `[open]` CONTROL IN WAVE 2 — DO NOT RENDER A DEAD BUTTON.** The wireframe's `[open]` targets the
`arc-templates` panel, which **does not exist until Wave 4** (`catalog.ts` has no such row). Calling
`host.openPanel('arc-templates', …)` against an unregistered id is precisely the **silent no-op** the
Frontend-Tool Contract forbids. Ship the resolved title as **plain text**, leave a one-line comment pointing
at **`D-ARC-PROVENANCE-DEEPLINK`** (§9), and Wave 4 adds the control in the same slice that registers the panel.

**🔴 ONE HOME FOR "DOES THIS FIELD REACH THE PROMPT?"** — **CREATE**
`frontend/src/features/studio/panels/arc/fieldClasses.ts` (`Q-32-OQ7-SUMMARY-ROSTER-NO-PACKER`; prose
warnings rot — a constant + a guard test does not):

```ts
/** Mirrors gather_arc (packer/lenses.py:282-285). EVERY section badge reads its label from HERE —
 *  no per-section literal. If the packer changes, this file changes, and the copy follows. */
export const PROMPT_BEARING = ['title', 'goal', 'tracks', 'roster_bindings'] as const;
export const REFERENCE_ONLY = ['summary', 'status', 'roster'] as const;
```
**UI copy — VERBATIM, do not paraphrase into a generation claim:**
- Title / Goal / Tracks / Cast **bindings**: **"Reaches the prompt"**
- Summary + Status: **"Reference only — not sent to the model."** Summary placeholder: *"A note for you and
  the Plan Hub. Not sent to the model."* *(This kills the near-defect: an earlier draft and the mock's create
  form both said summary reaches the prompt.)*
- The **Roster (slot list)**: **"Reference only — defines the roles that Cast bindings fill; read when
  extracting a template."** 🔴 **NEVER "roster reaches the prompt"** — `roster_bindings` does; `roster` does
  not (`resolve_roster` is **never called by the packer**; its consumer is `extract_template_from_arc`).
- Goal editor, when the node is **NOT a leaf**: inline note *"Only the leaf arc's goal reaches the prompt —
  this saga's goal is not injected."* (`lenses.py:303` takes `chain[-1].goal`.)

6. **Every state in §3.4 — RENDERED, not described.** Each gets a `data-testid` so the live smoke and the
   unit tests can assert it:

| State | testid | Render |
|---|---|---|
| empty (book has no arcs) | `arc-inspector-empty` | **CREATE `ArcInspectorEmptyState.tsx`** (`Q-32-EMPTY-STATE-DECOMPILER-CTA`). Gate on **`isSuccess && arcs.length === 0`**, 🔴 **NEVER on `!data`** — otherwise it flashes over an unfinished read (`PlanHubPanel.tsx:144-171` orders *loading* before *empty*; mirror it). Render exactly three things, never a blank pane: **(1)** *"No arcs yet — the spec tree is what steers generation."* **(2)** primary CTA **"Create the first saga"**. **(3)** secondary **plain text link** (not a second button) — *"Open the Plan Hub to extract it from the manuscript →"* → `openPanel('plan-hub', { focus: true, params: { bookId } })` (host `openPanel`, **never `navigate()`** — PH24/DOCK-7). 🔴 **WORD IT FOR THE DESTINATION, NOT THE OUTCOME.** Do **not** label it *"Extract the plan"* / *"Run the decompiler"*: plan-hub only renders `plan-hub-extract-cta` when `specEmpty = zero arcs **AND** zero unassigned chapters` (`usePlanHub.ts:224-228`). "No arcs" is **strictly weaker** — in the normal post-decompile state the arc list is empty but the spec is **not**, plan-hub shows the *"N chapters in no arc"* notice and **the extract button is ABSENT**. A link promising that button would **dead-end** there (the PH7 visible-fallback bug this repo already fixed once). Naming the destination is truthful in **both** worlds |
| no selection | `arc-picker` (focused) | the picker. **Not an error.** |
| loading | `arc-inspector-loading` | skeleton over the sections; the header keeps the picker live |
| error (5xx/network) | `arc-inspector-error` | the message + **Retry**. **Never an empty inspector that reads like an empty arc.** |
| **403 / VIEW-only** | `arc-inspector-readonly-note` | `canEdit === false` ⇒ **every control UNMOUNTED — not disabled** (no Save, no `+ track`, no Override, no Archive, no New arc) + one line: *"You have view access to this book."* **Never render a control that would 403.** Because `useBookGrant` **fails closed**, a `view` grant and an **unresolved** grant render identically read-only; controls appear only once `canEdit` is **true** |
| **404 / gone** | `arc-inspector-gone` | 🔴 **A THIRD STATE — `gone: boolean`, DISTINCT from `error`** (`Q-32-UNIFORM-404`). A 404 is a **terminal empty state, not a retryable error**, and must not render as an error toast with a Retry that will 404 forever. Read `status` off the thrown error (`api.ts:159-160` already attaches it). On `404`: `setNode(null); setGone(true); publish({ type: 'arc', arcId: null })` — clearing the slice, so a reopen lands on the picker instead of re-404ing forever. 🔴 **GUARD THE WHOLE BRANCH WITH THE GENERATION TOKEN** (`if (myGen === gen.current)`, `useSceneInspector.ts:54-58`) — a stale in-flight 404 must not clear a slice the user has already moved on from. 🔴 **The SAME branch goes in `patch()`'s catch**, beside the 412 — an arc archived/revoked *mid-edit* must flip the panel to `gone`, not print a raw *"not found or not accessible"* save error. Copy: *"This arc is no longer accessible."* + the picker as the sole affordance. **NEVER say "deleted", "archived", or "you don't have permission" — the panel has no oracle.** A 5xx does **NOT** set `gone` and does **NOT** clear the bus slice (clearing it on a 502 would evict a perfectly live arc) |
| **archived** | `arc-inspector-archived` | the body dims; banner *"Archived — restore to edit."* + **Restore**. Reachable via the picker's **Show archived** (`?include_archived=true`); `StructureRepo.get()` does **not** filter archived, so the detail route serves it `200`. 🔴 **span/chapters render "—", gated on `is_archived`, NOT on falsiness** (LA-2). The archive-confirm copy must **not** promise a chapter-pool return that no writer performs (OQ-8) |
| **cost gate** | — | **NONE. This panel spends nothing.** Every action is deterministic CRUD, $0, no LLM. There is no propose→confirm here — **adding one would be a defect.** ⚠ If a later agent adds an LLM button, it goes through the **generic** `GET /v1/composition/actions/preview` → `POST /v1/composition/actions/confirm` spine — **never** a bespoke per-action estimate route. **Three such invented routes 404 in production today** (plan 30 §3.3). Do not make it four. |

**🔴 ONE FORMATTER FOR EVERY DERIVED METRIC — NULLISH, NEVER FALSY** (`Q-32-ARCHIVED-NULL-NOT-ZERO`):
```ts
const fmtMetric = (v: number | null | undefined) => (v == null ? '—' : String(v));
```
**BANNED in this panel: `v || '—'` · `!v ? '—' : …` · `v ? … : '—'`.** A live arc with `chapter_count: 0`
**MUST** render *"0 chapters"*. Gate the archived presentation on the **FLAG** (`arc.is_archived`), never on
falsiness: dim the body, banner *"Archived — restore to edit."* + **Restore**, and render span/chapters as
`—` carrying `title`/`aria-label` *"Not computed while archived"*.

**Tests** — **CREATE** `frontend/src/features/studio/panels/__tests__/ArcInspectorBody.test.tsx`,
`__tests__/useArcInspector.test.ts`, `__tests__/ArcInspectorEmptyState.test.tsx`:

| Test | Asserts |
|---|---|
| `an inherited track is greyed, badged with its source, and offers ONLY Override` | fixture: `resolved.tracks=[{key:'romance'}]` + `resolved.provenance.tracks={romance:{is_own:false, title:'Quyển I', kind:'saga'}}` ⇒ the row is read-only, reads `Inherited from "Quyển I"`, and has **no edit / no remove** |
| `an OWN entry that shadows an ancestor offers Revert to inherited` | `is_own:true, shadows_title:'Quyển I'` ⇒ **both** actions render. **The fork must not be one-way** |
| `an entry with NO provenance row is read-only and offers no Override` | the AI-3 no-key warning renders |
| 🔴 `the FE never re-merges the cascade` | grep-guard: the arc panel sources contain **no** ancestor walk / key-set diff — `expect(src).not.toMatch(/parent_id/)` in the section components. The merge lives in `_merge_by`, once |
| `section headers count the EFFECTIVE set` | `resolved.tracks.length`, with the `N effective · M own · K inherited` sub-caption |
| `body labels roster_bindings as a prompt input and the roster SLOTS as not one` | reads its badges from `fieldClasses.ts`; asserts the Roster section does **NOT** claim the slots steer generation |
| `an ARCHIVED arc renders "—" for span, not 0` | `{is_archived:true, span:null, chapter_count:null}` ⇒ shows `—`; **assert the string `0` is absent** |
| 🔴 `a LIVE arc with chapter_count 0 renders "0", not "—"` | the inverse — **the falsiness trap.** `{is_archived:false, chapter_count:0, span:null}` ⇒ shows `0`. **A falsy impl passes the previous test and fails this one** |
| `VIEW-only unmounts every control` | `['book',id]` seeded `access_level:'view'` ⇒ `queryByTestId('arc-inspector-save' \| '-archive' \| '-add-track' \| '-new-arc')` are **all null**, and `arc-inspector-readonly-note` is present. With `'edit'` they are present |
| `canEdit fails closed while the grant is loading` | grant `undefined` ⇒ **no controls** |
| 🔴 `a 404 sets gone, clears the bus slice, and does NOT set error` | reject with `Object.assign(new Error('not found or not accessible'), {status:404})` ⇒ `gone === true`, `node === null`, `publish` called with `{type:'arc', arcId:null}` |
| 🔴 `a 500 does NOT set gone and does NOT clear the bus slice` | ⇒ `gone === false`, `error` set, `publish` **NOT** called. **A transient failure must not evict a live arc** |
| `a 404 from patch() also flips gone` | the mid-edit revoke path |
| `an error renders Retry, never an empty inspector` | — |
| `provenance: a resolved template renders name + the ARC's template_version, and NO UUID` | `expect(screen.queryByText(/[0-9a-f]{8}-[0-9a-f]{4}-/i)).toBeNull()` — **no UUID anywhere in the panel** |
| `provenance: arc_template_id === null renders the BA13 line, the section IS rendered, and there is no role="alert"` | the normal state has a surface, in a normal tone |
| `provenance: a 404 from arcApi.get renders the fallback, and the panel does NOT enter its error state` | still no visible UUID |
| 🔴 `provenance: arc_template_id === null ⇒ arcApi.get is NEVER called` | the `enabled` gate. A wasted fetch on every template-less arc is the regression this pins |
| `emptyState: renders the headline + both CTAs when arcs resolve empty` | never a blank pane |
| 🔴 `emptyState: renders NOTHING while the arc query is in flight` | **absent ≠ empty** |
| `emptyState: the secondary link calls openPanel('plan-hub', {focus:true, params:{bookId}})` | assert the **panel-id string** — a typo is a silent no-op |

**DoD evidence:** `cd frontend && npx vitest run src/features/studio/panels/__tests__/` → `N passed`.
A manual "I looked at it" note is **NOT** acceptable — the live proof is W2-S10.

---

### **W2-S6 · FE · the WRITES — create · patch (OCC) · archive · restore · override · key validation**
**dependsOn:** W2-S2, W2-S5

**Files** — **EDIT** `useArcInspector.ts` (+ a `useArcWrites.ts` if it exceeds 200 lines) and
`ArcInspectorBody.tsx` / a new `ArcCreateForm.tsx`.

**1 · The OCC write chain — MIRROR, do not re-derive.** Two shipped fixes in sibling hooks:

- **Serialize the chain** (`useSceneInspector.ts:43-45`): a `chainRef = useRef<Promise<void>>(Promise.resolve())`
  plus a `nodeRef` live mirror, so a chained patch reads the **fresh** version, not its closure's stale one.
  **Why this is mandatory here:** the status `<select>` and the roster chips **commit instantly**. Two rapid
  edits would both send `If-Match: v7`, the second 412s, and we'd blame a phantom collaborator for the
  user's own keystroke (memory `instant-commit-control-over-occ-entity-needs-write-serialization`).
- **Re-seed synchronously on success** (`usePlanNodeWrites.ts:73-75`): `qc.setQueryData(['plan-hub','arc', id], fresh)`
  in `onSuccess`, because `invalidateQueries` is async but `saving` flips false the instant the mutation
  resolves.
- **Capture the target entity** (`useSceneInspector.ts:66-70`): the debounced/chained write must bind WHICH
  arc it was for; if the selection moves before the link runs, **drop it** (memory
  `debounced-write-must-bind-its-target-entity`).
- **The empty patch is dropped in code, loudly** (`usePlanNodeWrites.ts:100`): firing it would bump the
  version and 412 the next real edit.

- **Chain with BOTH handlers:** `const next = chainRef.current.then(run, run); chainRef.current = next;`
  🔴 **`.then(run, run)` — not `.then(run)`.** A **failed** link must not break the chain for every write
  after it (`Q-32-OCC-SERIALIZE-WRITE-CHAIN` step 1).
- **NO `If-Match` on move / archive / restore / assign-chapters** — confirmed at `arc.py:516,528,540,560`
  (they declare no such Header param) and mirrored FE-side at `plan-hub/api.ts:186-249`. **Send no header;
  do not invent one.** `If-Match` becomes REQUIRED on **`PATCH /arcs/{id}` ONLY** (BE-A2).

**2 · The 412 recovery — seed-and-say, never clobber. DO NOT RE-GET.**
`apiJson` already attaches the parsed body to the thrown error (`api.ts:156-162` → `{status, code, body}`),
and composition raises `HTTPException(detail={...})` — so the current row is **already in hand**:
```ts
const status = (e as { status?: number }).status;
const detail = (e as { body?: { detail?: { code?: string; current?: ArcDetail } } }).body?.detail;
if (status === 412 && detail?.code === 'STRUCTURE_VERSION_CONFLICT' && detail.current) {
  nodeRef.current = detail.current; setNode(detail.current);       // seed — no second round-trip
  qc.setQueryData(['plan-hub','arc', id], detail.current);
  setError('This arc changed elsewhere — reloaded. Re-apply your edit.');
} else { /* the generic path */ }
```
Keep a one-line defensive `GET /arcs/{id}` fallback **ONLY** when `detail.current` is missing.
⚠ **`useSceneInspector`'s 412 path re-GETs — that predates D-K8-03. Do NOT copy that half.**

🔴 **THE TRAP (`Q-32-STRUCTURE-CONSTRAINT-VERBATIM` step 2) — this is a SILENTLY-DEAD BRANCH if you get it
wrong.** To branch on an error code you must read **`err.body?.detail?.code`**, **NOT `err.code`**.
`api.ts:127` assigns `err.code` from the **TOP-LEVEL** `body.code`, which **FastAPI never sets** — the code
lives at `body.detail.code`. `if (err.code === 'STRUCTURE_VERSION_CONFLICT')` **compiles, type-checks, and
never fires.** The same applies to `STRUCTURE_CONSTRAINT` (see §5 below).

**Copy:** *"This arc changed elsewhere — reloaded. Re-apply your edit."* **Never** *"your edit was lost"*,
never a silent overwrite, never blame the user.

🔴 **KEEPING THE USER'S IN-PROGRESS TEXT — the re-seed WOULD clobber it** (`Q-32-OCC-SERIALIZE` step 4).
The mock (③) shows the draft **preserved** while the rest of the panel shows v8. So:
- **Text fields** (title/summary/goal) hold **LOCAL draft state** (`useState` seeded from the node, committed
  on debounce/blur), and their resync-from-prop effect is **gated on `!dirty`**. Only non-dirty fields
  re-sync from the fresh row.
- 🔴 **The field's `key` MUST NOT include `version`.** A version-keyed remount **IS** the clobber.
- **Instant-commit controls** (the status `<select>`, roster chips) carry no draft text and simply re-render
  from the fresh row.
- The debounced text commit **must bind its target arc id** (memory
  `debounced-write-must-bind-its-target-entity`).

**3 · AI-3 — key validation (the panel is the only guard).** `StructureRepo._merge_by` (`structure.py:586-597`)
keys on `it.get(key_field, id(it))`:
- a **missing** key ⇒ the entry is kept but **can never be shadowed or overridden** — permanent
  un-editable-by-cascade garbage;
- an **empty-string** key ⇒ every empty-keyed entry across the whole ancestor chain **collides on `""`** and
  the leaf silently eats the root's.

Neither the REST schema (`ArcCreate.tracks: list[dict[str, Any]]`, `arc.py:339`) nor the MCP tool validates
this. So `useArcWrites.validateKey(key, ownEntries)` returns an inline error and **refuses the write** when:
key is absent · `key.trim() === ''` · key duplicates **another OWN entry's** key.
⚠ **An own key that equals an INHERITED key is LEGAL — that IS the override.** Do not reject it.
(Tightening the server schema is `D-ARC-TRACKS-ROSTER-SCHEMA`, §9 — it would break the agent's existing writes.)

**4 · AI-2 — the two cascade actions.**
- **"Override here"** deep-clones the **inherited** entry into this node's **own** array (same `key` ⇒ it
  shadows) and PATCHes the **FULL own array** (`If-Match`, through the serialized chain) — because `update()`
  is a **whole-array replace** (`structure.py:369-372`). Confirm/toast says so **verbatim**: *"Overridden
  here. This arc now has its own copy of "&lt;key&gt;" — it no longer follows "&lt;ancestor title&gt;"."*
  Inherited rows have **no** edit and **no** remove — **one action only.**
- 🔴 **"Revert to inherited"** — on an **own** entry whose `provenance.shadows_node_id != null`. Removes it
  from the own array and PATCHes; the row re-renders as inherited. **The first draft had no escape hatch —
  without this the fork is ONE-WAY** and an accidental Override can never be undone.
⚠ **A BINDING and a SLOT are two different writes.** Binding a role writes `roster_bindings[role_key]` on
this node (shadowing by `role_key` — correct cascade behaviour, *not* a fork). **Override here** on an
inherited SLOT copies the slot into own `roster`. Do not conflate them; the mock shows both on one row.

**4b · Status — HAND-SET. NEVER DERIVED.** (`Q-32-OQ5-STATUS-DERIVED` — **the question is CLOSED, and the
defer row is deleted.**) A `<select data-testid="arc-status-select">` over **exactly** the 4 closed-set values
of `NodeStatus` (`models.py:38`): `empty|outline|drafting|done`. Its value comes from the **arc row** returned
by `GET /arcs/{node_id}` — **from nothing else.** Instant-commit through the serialized chain.
```ts
// OQ-5 (DECIDED): status is the AUTHOR'S INTENT, never derived from member chapters — see
// models.py:178-183 (PH16). Actual state = span + the conformance badge, rendered SEPARATELY.
```
**Do NOT derive, auto-compute, or "suggest" it from member chapters — now or later — and do not add a
client-side derivation either.** `gather_arc` never reads it (the one `status == "done"` branch in that file
is on `outline_node`, a different table), and `models.py:178-183` **already seals the identical question one
layer down**: fusing intent with actual state would mean *"marking a scene 'done' makes an UNWRITTEN scene
render as written."* Deriving the arc's status commits exactly that banned fusion — and would make it
impossible to mark an arc `drafting` before any chapter is assigned.
**Regression guard (the point of the whole item):** a BE test asserting that assign/unassign leaves
`structure_node.status` **byte-identical**, and an FE test asserting the select's value is read from the arc
row **only** (not computed from `chapters`/conformance). *That test is what stops a future agent from
"helpfully" auto-computing it.*

**5 · Create** (mock ②) — the body is **EXACTLY SIX FIELDS AND NOTHING ELSE** → `POST /books/{bid}/arcs`.
- **Type the body as a CLOSED TS type** (`Q-32-CREATE-BODY-NO-TRACKS`):
  `type ArcCreateBody = { kind: 'saga'|'arc'; parent_arc_id: string|null; title: string; summary: string; goal: string; status: ArcStatus }`.
  🔴 **Do NOT include `tracks`, `roster`, `roster_bindings`, `arc_template_id`, or `template_version`.** The
  **backend accepts them** (`arc.py:339-343`), so **the TS type is the only thing stopping a later "helpful"
  addition.** Tracks/roster are edited **AFTER** create — a create form with a nested cascade editor is a
  form nobody finishes.
- 🔴 **`kind` is a CLOSED SET OF TWO: `'saga' | 'arc'`.** There is **no `sub_arc`** (DB CHECK
  `kind IN ('saga','arc')`, `migrate.py:1102`; body `Literal["saga","arc"]`, `arc.py:333`). A **sub-arc is an
  `arc` whose parent is an `arc`** (`depth >= 2`) — **a depth LABEL, not a kind.** A picker offering
  `sub_arc` **422s**. **Two SEPARATE controls, never one three-way picker:** a 2-option segmented control
  {Saga, Arc} (default `'arc'`, matching `arc.py:333`), and a separate optional **Parent arc** picker.
  **The literal string `sub_arc` must not appear in ANY FE type, picker option, request body, contract JSON,
  or i18n VALUE** — pinned by a grep-guard test. Display-only label helper:
  `arcKindLabel({kind, depth}) → kind==='saga' ? 'Saga' : depth >= 2 ? 'Sub-arc' : 'Arc'`. i18n carries
  **three display labels but only TWO form option VALUES**; `label.subArc` is display-only and **must never
  be fed back as a `kind`.**
- **`kind === 'saga'` ⇒ the parent control is DISABLED and cleared; send `parent_arc_id: null`** (the DB's
  `structure_saga_is_root` CHECK, `migrate.py:1126`). This is a structural fact about the form, not a
  re-implemented rule, and it emits no message.
- 🔴 **DO NOT FILTER THE PARENT PICKER BY DEPTH.** (`Q-32-STRUCTURE-CONSTRAINT-VERBATIM` step 3/4 — which
  **overrides** `Q-32-KIND-CLOSED-SET-TWO`'s `depth <= 1` filter suggestion; the two register rows disagree
  and the dedicated error-contract row wins.) *"Do NOT pre-validate… no client depth counter, no client cycle
  walk. The rules are DB-trigger-enforced; a client copy is a second SSOT that drifts."* Depth, cross-book and
  parented-saga violations **must round-trip** and surface the server's verbatim 400. The **one sanctioned**
  client-side skip stays: a **guaranteed-pointless GESTURE** (dropping an arc on itself or into its own
  subtree) is skipped with **no write and no error** (`usePlanMoves.ts:307-311`) — it fabricates no message.
- **400 `STRUCTURE_CONSTRAINT`** (`arc.py:397`) is rendered **VERBATIM** = render `err.message` (which
  `apiJson` has already unwrapped from FastAPI's object-shaped `detail`). `onError: (e) => setStructureError(e.message)`.
  **Do NOT map it, rewrite it, prettify it, or switch on its text.** Do **not** surface `detail.detail` —
  that is the raw Postgres trigger text (developer noise). ⚠ To *style* it as a constraint violation, branch
  on **`err.body?.detail?.code === 'STRUCTURE_CONSTRAINT'`**, **never `err.code`** (see §2's trap).
  *Accepted consequence:* the message is one lumped sentence naming all four rules, so it does not say WHICH
  rule broke. **That is the server's wording, rendered as-is.** If per-rule precision is wanted later, fix it
  **SERVER-side** in `_arc_conflict_http` — never in the client.
- **After the 201:** seed/invalidate `['plan-hub','arcs',bookId]`, **publish `{type:'arc', arcId: node.id}`**
  so the inspector immediately selects the new arc, and **land the user on the TRACKS section with its
  `[+ track]` affordance visible.** That is what makes *"tracks are edited after create"* a continuous motion
  rather than a dead end.
- **NO template dropdown on this form.** Creating from a template is a separate, already-built flow
  (`POST /arc-templates/{id}/apply`). **Two paths writing `arc_template_id` would fork provenance.**

**5b · The reserved header-actions slot** (`Q-32-OQ1-ARC-SUGGEST`). The header row (picker + `+ New arc` /
`+ New saga`) renders a right-aligned
`<div className="ml-auto flex items-center gap-1" data-testid="arc-inspector-header-actions">` containing
**ONLY the Wave-2 actions**. 🔴 **NO "Suggest an arc" button, no `composition_arc_suggest` call, no
`POST /v1/ai/tools/execute` bridge call, and DO NOT add `'composition_arc_suggest'` to
`FE_BRIDGE_TOOL_ALLOWLIST`** (`tools.controller.ts:24-30`) — plan 30 BE-6 says it must **never** go there
(that surface's contract is spend-adjacent propose/poll; *"NOTHING here writes or deletes"*), and a free
**read** belongs on REST. Wave 4 mounts the button **with its backend** (`POST /v1/composition/arc-templates/suggest`).
Reserving the slot now makes Wave 4 a pure additive mount with **no header re-layout**.
*(Correction to carry into spec 34: `composition_arc_suggest` is `require_meta("R","book")` — a **Tier-R
read**, NOT a propose→confirm tool. It drags no cost spine anywhere. The real blockers are simply: no REST
route + not in the allowlist ⇒ **403, fails closed**.)*

**6 · Archive — the confirm CLIENT-derives, the toast reads the RESPONSE** (`Q-32-OQ3` step 4).
The confirm renders **BEFORE** the call, when no response exists — so count the descendants **from the shell
tree we already hold**: *"Archive 'Quyển I' and its 2 sub-arcs?"* **Then** use the **response's**
`archived_count` (new in W2-S1b) in the post-action toast — *"Archived 3 arcs — Undo"* — **not** the client
estimate, so a concurrent write that changed the subtree is reported **truthfully**.
🔴 **The confirm must tell the truth about the chapters** (`Q-32-OQ8`, copy **verbatim**):
- **N > 0** → title *"Archive this arc?"* / body: *"{N} chapters stay bound to this arc. Archiving does NOT
  return them to the Unassigned tray — they will appear in neither the arc lane nor the tray until you
  unassign them. Restoring the arc brings it back with its chapters exactly as they are now."* / buttons
  *"Archive anyway"* · *"Cancel"*.
- **N = 0** → *"Archive this arc? You can restore it later via Show archived."*
**The copy MUST NOT contain any pool-return promise** (*"chapters return to the pool"*, *"chapters are
freed"*) — **no writer performs it.**
🔴 **THE FALSE-ZERO GUARD (one line of FE logic, do it here):** read `chapter_count` from the **LIVE** arc row
*before* the archive call. An **archived** arc reports `chapter_count: null` (after W2-S1 edit 4) — **gate the
"—" render on `is_archived`, NOT on falsiness.** **Never print "0 chapters" for an archived arc that still
has 18.**
*(The M4 secondary button "Unassign {N} chapters first" is gated on BE-A3 existing — that is the W2-S6/W2-S7
slice boundary.)*

**7 · Restore** — `POST /arcs/{id}/restore`. It restores the subtree **and reconnects the archived ancestor
chain** (`structure.py:426`). Say so. **`archive()` does NOT cascade an unassign — ever** (`Q-32-OQ8`, gate #5
**conscious won't-fix, CLOSED**): `restore()` is lossless on membership *precisely because* the binding
survives. A cascade would null the binding with **no lift map to rebind from**, so restore could never put
the chapters back — archive would become an **irreversible destructive write** on user rows. **The pinning
test is W2-S1b #7.** *(Also REJECTED: "helpfully" redefining `?unassigned=true` to mean
`structure_node_id IS NULL OR arc is_archived` — it silently redefines 24-PH21's named axis, shows a chapter
in the tray **while it is still bound**, and makes it vanish again on restore.)*

**Tests** — `__tests__/useArcWrites.test.ts` + `ArcInspectorWrites.test.tsx`:

| Test | Asserts |
|---|---|
| `two rapid edits SERIALIZE — the second sends the bumped version` | patch A (v7 → returns v8), then immediately patch B ⇒ B's `If-Match` is **8**, not 7, and **no 412**. 🔴 the exact bug the sibling hooks already fixed |
| `a 412 seeds the current row and keeps the user's text` | the mutation rejects with `{status:412, body:{detail:{current:{version:8,title:'theirs'}}}}` ⇒ the cache holds v8, the input still holds the user's draft, and `arc-inspector-conflict` is rendered |
| `the retry after a 412 SUCCEEDS` | re-fire the same patch ⇒ it sends `If-Match: 8` and resolves |
| `an empty patch never fires` | `edit(id, v, {})` ⇒ `updateArc` not called (`usePlanNodeWrites.ts:100`'s precedent — firing it would bump the version and 412 the next real edit) |
| `a write for arc A is dropped if the selection moved to B` | — |
| `validateKey rejects empty and duplicate-OWN keys` | `''` ⇒ error; a dup of another own key ⇒ error; a dup of an **inherited** key ⇒ **allowed** (that is the override) |
| `Override copies the entry into own tracks and PATCHes` | the PATCH body's `tracks` contains the inherited entry with the same `key` |
| 🔴 `Revert to inherited removes it from own tracks and the row re-renders as inherited` | the fork is **not** one-way |
| `an inherited row has no edit and no remove` | only the Override action is rendered |
| `archive confirm names the REAL sub-arc count from the SHELL` | a saga with 2 arc children ⇒ the confirm string contains `2` (the response does not exist yet) |
| 🔴 `the archive TOAST reads archived_count from the RESPONSE, not the client estimate` | response `{archived_count: 3}` ⇒ the toast says **3**, even if the shell said 2 |
| `archive confirm does NOT promise the chapters return to the pool` | the confirm copy contains **"stay bound"**; assert the strings *"return to the pool"* / *"freed"* are **absent** |
| `create offers exactly two kinds` | the options are `['saga','arc']` — **assert `sub_arc` is absent** |
| 🔴 `no FE source in the arc panel contains the token sub_arc` | the grep-guard (`Q-32-KIND-CLOSED-SET-TWO` step 1) |
| 🔴 `the create request body's keys are EXACTLY ['goal','kind','parent_arc_id','status','summary','title'] (sorted)` | `Q-32-CREATE-BODY-NO-TRACKS` step 5. **A future agent bolting a nested track editor onto the create form reds the suite instead of shipping a form nobody finishes** |
| `selecting Saga clears + disables the parent picker and POSTs parent_arc_id: null` | — |
| 🔴 `the parent picker does NOT filter out depth-2 nodes` | the anti-pre-validation pin: depth violations **round-trip** to the server's verbatim 400 |
| `arcKindLabel({kind:'arc', depth:2}) === 'Sub-arc' while the POSTed kind is still 'arc'` | display label ≠ wire value |
| `a 400 STRUCTURE_CONSTRAINT renders the server message VERBATIM, sourced from the error object` | reject with `Object.assign(new Error('<the server sentence>'), {status:400, body:{detail:{code:'STRUCTURE_CONSTRAINT', message:'<same>'}}})` and assert the DOM contains that exact sentence **from the error**, not from a client constant. 🔴 **Asserting against a client constant is circular — it passes even if the client authored the text itself** |
| 🔴 `the status select reads its value from the arc row ONLY` | not computed from `chapters` / conformance. Options are exactly `['empty','outline','drafting','done']` |
| 🔴 `the PATCH form has NO kind and NO parent field` | `kind`/`parent_id`/`rank`/`depth` are **not** in `_UPDATABLE_COLUMNS` (`structure.py:51-55`) — reparenting is `POST /arcs/{id}/move` only. **An input for them would silently no-op** — a Frontend-Tool-Contract-class bug |
| 🔴 `the arc-inspector api module issues NO cost-gated URL` | **`Q-32-NO-COST-GATE` Test B.** Every URL literal it issues matches `^/v1/composition/(books/[^/]+/arcs\|arcs)`; the module source contains **no `/estimate`** and no `actions/` path. **This is the test that would have caught the FOUR routes that 404 in production today** (plan 30 §3.3 — e.g. `POST /v1/composition/actions/conformance_run/estimate`, a per-action estimate route that **has never existed**). **Do not make it five** |

**Plus one BE test** (`Q-32-NO-COST-GATE` Test A), `services/composition-service/tests/unit/test_mcp_actions.py`:
`test_arc_crud_is_never_confirm_gated` — assert **no** descriptor in `actions._ALL_DESCRIPTORS` matches
`^composition\.arc_(create|update|delete|restore|move|assign)`. **The panel spends nothing, by construction**
(grep `confirm|token|spend|llm|estimate` across `arc.py` hits only the JWT bearer dep at `:587`). **Adding a
`ConfirmCard` / propose→confirm / `/estimate` fetch / "this will cost $X" copy to this panel is a DEFECT.**
If a later wave adds an LLM action here it goes through the **generic** `GET /actions/preview` →
`POST /actions/confirm` spine — **never** a bespoke per-action route (precedent already in the allowlist:
`composition.arc_import`).

**DoD evidence:** `npx vitest run src/features/studio/panels/__tests__/` → `N passed`, with the pasted
serialization-test line.

---

### **W2-S7 · FE · membership — assign + REMOVE (consumes BE-A3)**
**dependsOn:** W2-S3, W2-S6

**Files** — `ArcInspectorBody.tsx` (the Chapters section) + `useArcInspector.ts`.

- **`+ assign chapters…`** → a picker over the book's **unassigned** chapters
  (`getChildren(bookId, {unassigned: true}, …)` — `plan-hub/api.ts:35`) ⇒
  `assignChapters(bookId, arcId, ids, token)`.
- **`remove`** on a member row ⇒ `assignChapters(bookId, **null**, [id], token)` — **the unassign**.
  This row is **why BE-A3 exists**: before it, a chapter could only be *moved to another arc*, never returned.
- Both writes then `invalidateQueries(['plan-hub'])` — which reaches the shell (span/chapter_count), the
  detail, and the Hub's `?unassigned=true` tray in one prefix.
- **The `gap_count` chip comes from the SERVER** (W2-S1 edit 5). 🔴 **Do NOT render client-derived "gap rows"**
  — the first draft's `— gap: 43–44 unassigned —` is **forbidden**: the children route is keyset-paged, so a
  count over the *loaded* window reports **not-yet-loaded chapters as gaps**. Warn-only (BA6) — a romance
  plotline may legitimately be non-contiguous. **Never an error, never a block.**

**🔴 VIRTUALIZATION — REUSE, and virtualize UNCONDITIONALLY** (`Q-32-CHAPTERS-VIRTUALIZATION`).
**Do not add a library.** `@tanstack/react-virtual` is **already a direct dependency** (`package.json:32`) and
is already used for **exactly this shape** in `ManuscriptNavigator.tsx`. *(Ignore the stale
`react-window` TODO at `JobLogsPanel.tsx:17-18` — the repo standardized on `@tanstack/react-virtual`.)*

1. **DATA — CREATE `frontend/src/features/studio/panels/useArcChapters.ts`.** Mirror the keyset loop of
   `plan-hub/hooks/usePlanWindows.ts:120-143` (`fetchArc`): `getChildren(bookId, { structureNodeId: arcId },
   { cursor, limit: 100, token })`; hold `{items, cursor, loading}`; `loadMore()` re-fetches with `cursor` and
   **APPENDs**; stop when `next_cursor === null`. 🔴 **Carry the `gen.current` stale-response guard**
   (`usePlanWindows.ts:113,124,131`) so an **arc switch cannot land a late page from the previous arc.**
   **Do NOT reuse `usePlanWindows` itself** — it is coupled to the Hub canvas (expanded-arc map → `laneLayout`).
2. **VIEW —** copy the virtualizer block from `ManuscriptNavigator.tsx` (`:18`, `:39`, `:70-76`, `:80-86`,
   `:214-220`): `useVirtualizer({ count, getScrollElement, estimateSize: () => ROW_H, overscan: 12 })`, a
   `getTotalSize()` spacer, rows absolutely positioned via `transform: translateY(${vi.start}px)`, and
   infinite paging driven by a trailing sentinel entering the virtual window (guarded in the hook so it never
   double-fetches).
3. 🔴 **THE TRAP — the scroll element MUST be its own bounded box.** `ManuscriptNavigator`'s `parentRef` is a
   flex-sized `min-h-0 flex-1 overflow-y-auto` div; the Chapters section instead lives **inside the panel's
   own scrolling column**, so an auto-height div gives the virtualizer **no viewport to measure** and
   windowing **silently degrades to rendering every row**. Give the list its own
   `ref={parentRef}` div with **`max-h-[320px] overflow-y-auto`**.
4. 🔴 **VIRTUALIZE UNCONDITIONALLY — drop the "above ~200 rows" threshold** the first draft carried. A
   conditional virtualize/plain-list branch means **two render paths** and **remounts a stateful hook at the
   crossing**. `ManuscriptNavigator` virtualizes at any size. "~200" was a perf rationale, never a required
   branch.

**Tests** — `ArcInspectorChapters.test.tsx`. 🔴 **You MUST mock the virtualizer** exactly as
`ManuscriptNavigator.test.tsx:6-12` does — **jsdom gives the scroll element zero size, so the real
virtualizer renders ZERO rows and every assertion reds**:
```ts
vi.mock('@tanstack/react-virtual', () => ({ useVirtualizer: (opts) => ({
  getTotalSize: () => opts.count * 28,
  getVirtualItems: () => Array.from({ length: opts.count }, (_, index) => ({ index, start: index * 28, key: index })),
})}));
```

| Test | Asserts |
|---|---|
| `remove calls assignChapters with a NULL structure_node_id` | 🔴 the unassign contract, at the FE seam |
| `assign calls it with the arc id` | and `getChildren` was called with the `{ structureNodeId }` axis |
| `both invalidate the ['plan-hub'] prefix` | the Hub's unassigned tray and the shell both refresh |
| `the sentinel row entering the window calls loadMore ONCE` | no double-fetch |
| `an arc switch drops a late page from the PREVIOUS arc` | the `gen` guard |
| 🔴 `is_contiguous:false + gap_count:3 renders the chip AND BLOCKS NOTHING` | **`Q-32-NONCONTIGUOUS-WARN-ONLY` step 3 — warn-only enforced by a TEST, not a comment.** With that fixture: *"+ assign chapters"*, *"remove"*, and the identity/status controls are **all enabled and their mutations fire**. `useArcInspector` must not read `is_contiguous`/`gap_count` in **any** write path — no disabled button, no confirm-gate, no validation refusal |
| `gap_count: null renders the "no reading position" variant, never a fabricated N` | — |

**DoD evidence:** `npx vitest run … ArcInspectorChapters` → `N passed`. The **live** proof (a removed chapter
lands in the Hub's tray) is W2-S10 leg 6.

---

### **W2-S8 · FE · `arcEffects.ts` — the Lane-B effect handler (X-4, MANDATORY)**
**dependsOn:** W2-S5

> 🔴 **ONE HOME FOR `composition_arc_*` — this file, and only this file.** `matchEffectHandlers`
> (`effectRegistry.ts:45`) returns **EVERY** matching handler and `runEffectHandlers` **awaits ALL of them**
> — it does **not** shadow. So two overlapping registrations in two files **double-fire**. Plan 30 §8.0b
> reconciles it: **Wave 2 CREATES `arcEffects.ts` with the single broad `/^composition_arc_/` pattern;
> Wave 4 (spec 34) EXTENDS this file's handler BODY** (adding the `arc-templates` query keys) rather than
> registering a second pattern. **Do NOT put this in `bookEffects.ts`.**

**Files**

1. **CREATE** `frontend/src/features/studio/agent/handlers/arcEffects.ts`:

```ts
// #09 Lane B / X-4 — the effect handler for the agent's arc writes (composition_arc_create /
// _update / _delete / _restore / _move / _assign_chapters). Without it, the agent edits an arc and
// the open inspector shows the STALE row — and the user's next save 412s against a version they
// were never shown. This handler is the difference between "the agent and the human share one
// object" and "they fight over it."
//
// ONE registration for the whole family (plan 30 §8.0b). Wave 4 extends THIS handler's BODY.
// ⚠ registerEffectHandler's STRING branch is `tool === p || tool.startsWith(p)` — NOT a pattern
// match. Use a RegExp for anything with alternation, or you ship a silent no-op handler that no
// unit test (which registers and calls its own fake) can ever catch.
import { registerEffectHandler, type EffectContext } from '../effectRegistry';

// READS EXCLUDED — same rationale as GLOSSARY_WRITE_PATTERN (glossaryEffects.ts:18) and
// KNOWLEDGE_WRITE_PATTERN (knowledgeEffects.ts:16): a chatty read loop must not thrash the cache.
// Excluded = the four require_meta("R", …) tools (server.py:4192, 4221, 2272, 4673).
// Covered writes: create, update, delete, restore, move, assign_chapters, apply, extract_template
// (server.py:4290-4628) + import_analyze (a W PROPOSE; a harmless refresh).
export const ARC_WRITE_PATTERN = /^composition_arc_(?!list|get|suggest|template_drift)/;

let registered = false;

export function arcEffect(ctx: EffectContext): void {
  // The whole plan-hub prefix: the arc SHELL (['plan-hub','arcs',bookId] — span/chapter_count/the
  // tree), the arc DETAIL (['plan-hub','arc',id]), and the outline node cache. ONE prefix reaches
  // all of them because useArcInspector keys its detail INSIDE it — a key outside the prefix would
  // go silently stale. This is what refreshes the OCC `version` the inspector saves against
  // (the 412-against-a-version-you-were-never-shown bug).
  ctx.queryClient.invalidateQueries({ queryKey: ['plan-hub'] });
  // The composition outline windows the Hub renders (an assign/unassign moves chapters between
  // lanes). VERIFIED REAL, not a phantom: useOutline.ts:14 keys ['composition','outline',…].
  ctx.queryClient.invalidateQueries({ queryKey: ['composition', 'outline'] });

  // ⬇ Wave 4 (spec 34 §6 step 8) EXTENDS THIS BODY — add ['composition','arc-templates'] +
  //   ['composition','arc-template'] + ['composition','arc-conformance'] HERE. The ['plan-hub']
  //   prefix does NOT reach them (they are a different namespace). NEVER a 2nd registerEffectHandler
  //   for an overlapping composition_arc_* pattern — matchEffectHandlers returns EVERY match and
  //   runEffectHandlers awaits ALL of them. Two registrations DOUBLE-FIRE; it does not shadow.

  // Deliberately NO bus publish. Publishing {type:'arc'} here would HIJACK the user's inspector to
  // whatever arc the agent happened to touch — the same reason bookEffects refuses to publish a
  // `chapter` event (bookEffects.ts:31-33). The bus `arc` slice is user-intent focus only.
}

/** Idempotent — the reconciler calls this on every mount. */
export function registerArcEffectHandlers(): void {
  if (registered) return;
  registered = true;
  registerEffectHandler(ARC_WRITE_PATTERN, arcEffect);
}
export function _resetArcEffectHandlers(): void { registered = false; }   // the test hook
```

🔴 **TWO CORRECTIONS THE FIRST DRAFT GOT WRONG** (`Q-32-ARCEFFECTS-ONE-HOME`):

- **A · Do NOT invalidate `['composition','arcs', bookId]`.** Spec 32 §6 step 8 names that key. **It does not
  exist anywhere in the FE** (`grep -rn "'composition', *'arcs'" frontend/src` → **ZERO hits**) — invalidating
  it is a **silent no-op**. This is not hypothetical: `usePlanNodeWrites.ts:45-49` is a **code comment
  describing this exact bug being removed** (*"a key no query in this codebase uses — dead code with a comment
  claiming it was load-bearing, which is worse than none"*). **The arc keys live under `['plan-hub']`.**
  ⚠ **The ONE legitimate cross-namespace case** — so Wave 4 does not get this wrong: **arc TEMPLATES genuinely
  DO live in the `composition` namespace** (`['composition','arc-template', id]`, `['composition','arc-templates','all']`)
  and the `['plan-hub']` prefix does **not** reach them. That is **templates, not arcs** — it does not
  resurrect `['composition','arcs',…]`.
- **B · Do NOT import `unwrapToolResult`.** The first draft imported it, unwrapped a payload, and then did
  `void payload` — **the handler needs no id from the payload** (bookId + a prefix invalidate covers
  everything), so the import is **unused** (a lint error). ⚠ **The rule stands CONDITIONALLY:** IF Wave 4's
  extended body needs an id (e.g. `arcTemplateId` for `['composition','arc-template', id]`), it **MUST** read
  it via `unwrapToolResult` (`resultEnvelope.ts:8`), **never a bare `ctx.result.x`** — that is the M-E live
  bug class (the live stream nests the payload in `{ok, result}` and the inner value may still be a JSON
  **string**; a handler reading only the top level passes its unit tests and **silently no-ops LIVE**).

2. **EDIT** `frontend/src/features/studio/agent/useStudioEffectReconciler.ts` — 🔴 **TWO edits, and missing
   the second is the "built but unwired" bug class** (`Q-32-REGISTRATION-CHECKLIST-GG8` precision 1: *"the
   handler file exists, unit-tests green, and NOTHING fires at runtime"*):
   - **(a)** `import { registerArcEffectHandlers } from './handlers/arcEffects';` beside the four imports at `:18-21`
   - **(b)** 🔴 **CALL `registerArcEffectHandlers();`** inside the once-only `useEffect` (`:34-39`), next to
     `registerTranslationEffectHandlers()`.
   - **(c)** delete the now-false comment at `:7-10` (it asserts which families "DON'T need a handler").
   ⚠ **Wave 1 (spec 31) also edits this file** (it adds `registerCompositionEffectHandlers`). Additive, same
   block, different line — no conflict, but **re-read the file before editing** rather than assuming its
   contents.

**Tests** — **CREATE** `frontend/src/features/studio/agent/handlers/__tests__/arcEffects.test.ts` (mirror
`knowledgeEffects.test.ts`):

| Test | Asserts |
|---|---|
| `ARC_WRITE_PATTERN matches the writes and NOT the reads` | matches `create` / `update` / `delete` / `restore` / `move` / `assign_chapters` / `apply` / `extract_template`; **does NOT match** `composition_arc_list` / `_get` / `_suggest` / `_template_drift` (a chatty read loop must not thrash the cache) |
| `composition_arc_update invalidates the plan-hub prefix` | after `clearEffectHandlers()` + `_resetArcEffectHandlers()` + `registerArcEffectHandlers()`, a spy `queryClient.invalidateQueries` receives `['plan-hub']` |
| 🔴 `THE DOUBLE-FIRE GUARD` | register **bookEffects + compositionEffects + arcEffects together**, then assert `matchEffectHandlers('composition_arc_update')` **`.toHaveLength(1)`** — **not `toBeTruthy()`**. This is the **only** thing that can catch a future second home (`runEffectHandlers` awaits **ALL** matches; it does not shadow) |
| 🔴 `the key arcEffect invalidates == the key the inspector reads` | the anti-phantom-key proof: register a query at `['plan-hub','arc','<id>']`, run the handler for `composition_arc_update`, assert **that detail query is marked stale**. **A grep-guard is not enough — assert the EFFECT** (CLAUDE.md's *"checklist ⇒ test the effect"*) |
| `it does NOT publish an arc bus event` | a spy on `host.publish` is **not called** — the anti-hijack guard |

> 🔴 **KNOWN UNCOVERED EDGE — do not silently drop it.** `composition_arc_import_analyze` returns only a
> `confirm_token`; its **actual write dispatches through the shared `confirm_action` tool**, so **no
> `composition_arc_*` name ever reaches the reconciler for it.** `arcEffects` **cannot** close this — it is the
> same class `translationEffects.ts:1-8` already records for resume/retry. **Write the defer row:
> `D-ARC-CONFIRM-EFFECT`** (§9) — the 拆文 panel must refresh off **job completion** instead.

**DoD evidence:** `npx vitest run src/features/studio/agent/handlers/__tests__/` → `N passed`. The **live**
proof (an agent `composition_arc_update` refreshes an open inspector with **no manual reload**) is W2-S10
step 5.

---

### **W2-S9 · FE · the PlanDrawer embed (24-H3.1) + delete the gap note**
**dependsOn:** W2-S6, W2-S7

> ⚠ `PlanDrawer.tsx` is owned by the **Book-Package track (specs 22–28)**, which **declared COMPLETE
> 2026-07-12**. DBT-06 is in that track's own debt table as *"#4 genuinely-upstream"* — it is **handed to
> us**, not contested. The edit is still designed to be **surgical and revert-safe**. **Announce before
> editing. Enumerate files on commit. Never `git add -A`.**

**AI-4 (LOCKED) — the embed is a DELETION plus a one-line mount.**

**Files**

1. **EDIT** `frontend/src/features/plan-hub/components/PlanDrawer.tsx`:
   - **DELETE** `ArcFacets` (`:305-357`, ~50 lines), `rosterKeysOf` (`:299-303`), and the
     `plan-drawer-arc-gap` note (`:351-354`) — including the `arc as ArcListNode & { tracks?: unknown }`
     cast (`:308`), which only existed because the type was wrong (W2-S5 widened it). Drop the now-unused
     `ArcListNode` import if it becomes unused (keep `PlanOverlay`/`PlanOverlayRef`).
   - **REWRITE** `DrawerBody`'s arc branch (`:391-394`) to **EXACTLY**:
     ```tsx
     if (view.kind === 'arc' || view.kind === 'saga') {
       if (!view.arcNode) return <Centered testid="plan-drawer-empty">Arc not found in the shell.</Centered>;
       return <ArcInspectorBody arcId={view.arcNode.id} bookId={bookId} embedded />;
     }
     ```
     — the **same component** the dock panel renders, in its embedded variant (no panel chrome, no picker;
     the drawer supplies the id). **DOCK-2: one implementation, two hosts.**
   - 🔴 **DO NOT PASS `writes={writes}`. THE SPEC'S OWN SNIPPET (32:275) IS WRONG.**
     (`Q-32-PLANDRAWER-BOOKID-PROP` + `Q-32-AI4-PLANDRAWER-EMBED`.) `PlanDrawer`'s `writes` is the **PH20
     OUTLINE** bundle (`usePlanNodeWrites.ts:22-32`): `edit(nodeId, version, patch: NodeEdit)` → `PATCH
     ${COMP}/outline/nodes/{id}` (`api.ts:136`), `archiveNode` → `DELETE /outline/nodes/{id}` (`:148`).
     **Arc CRUD is a different object, a different REST surface (`PATCH /arcs/{id}` + `If-Match`), and a
     different error contract (412 carrying `current`).** Threading it in would **route arc edits at the
     outline endpoint** and would not typecheck against `NodeEdit`. `ArcInspectorBody` **owns its arc
     mutations internally** — that is what makes it *one implementation, two hosts*.
     🔴 **And do not pass `canEdit={!!writes}` either** (the first draft's compromise): **`writes` presence is
     not a grant.** `ArcInspectorBody` resolves the real grant itself via `useBookGrant(bookId)` (W2-S5 step
     3b), so the two hosts **cannot disagree**. Props are exactly `{ arcId, bookId, embedded? }`.
   - 🔴 **`bookId` must be THREADED into `DrawerBody`.** It is on `PlanDrawerProps` (`:33/:35`) and is
     destructured in `PlanDrawer(...)` at `:401`, but it is **NOT** a `DrawerBody` prop today (`:360-374`
     takes only `view/overlay/onOpenRef/writes/chapters/onOpenInEditor`). **One added prop + one added
     pass-through at the `<DrawerBody …>` call site (`:445-452`).**
     ⚠ **`selectedId` is NOT needed** — the branch already narrows `view.arcNode`, so `view.arcNode.id` is the
     id. **Do not add a second prop carrying the same fact** (the DA-10 smell this file's own comment at
     `:44-46` calls out).
   - Update the file's header comment: the *"the 23-C3 arc-inspector component does not exist yet"* line
     (`:13-14`) becomes a **lie** the moment the mount lands. **Delete it.**
   - 🔴 **KEEP `usePlanNode`'s arc shell query and `arcNode`** (`usePlanNode.ts:66-70, 84-87`). The spec's
     "the shell stops being the arc source" is true of the **BODY only** — the drawer **HEADER** still reads
     `view.arcNode?.title` / `?.status` (`PlanDrawer.tsx:414-415`), and the `!view.arcNode` guard above
     depends on it. **Deleting `arcNode` blanks the drawer header for every arc.** No change to `usePlanNode.ts`.
   - **Also fixed by the deletion:** `:346` renders the raw `arc_template_id` **UUID** as the Provenance value
     — an unclickable 36-char hex string, shown to a novelist. The inspector resolves it to the template's
     **title** (W2-S5). **No `[open]` button in Wave 2** — the target panel does not exist until Wave 4.

1b. 🔴 **EDIT `PlanDrawer.tsx:284-290` — FIX THE `find_references` LIE. IT IS A COPY-ONLY CHANGE, DO IT NOW.**
   **The first draft deferred this (`D-PLANDRAWER-FINDREFS-COPY`, *"leave the facet, do NOT fix the copy"*).
   The register OVERRIDES that** (`Q-32-OQ4-FIND-REFERENCES-STALE-COPY`): the deferral's stated reason was
   *"do not fix the copy from the RUN-STATE alone"* — **and that caution is satisfied, because the fix is
   grounded in CODE, not a doc.** `composition_find_references` **SHIPPED** (`mcp/server.py:3867`, handler at
   `:3883`, fully implemented over `EntityReferencesRepo` with an E0 VIEW gate). The current copy —
   *"— spec 28 AN-3, not built yet."* — is **a live lie that talks users OUT of a feature they already have.**
   *(The file **indicts itself**: its own comment at `:281-282` says the *previous* stale copy "was simply
   false once H4 landed; an honest gap names its real blocker" — and then repeats the mistake at `:287`.)*
   Replace the `<EmptyFacet>` body with:
   ```tsx
   {/* The tool SHIPPED (composition-service/app/mcp/server.py:3867, EntityReferencesRepo). The old
       copy's "not built yet" was a live lie. What is missing is only the FE path: MCP-only, no REST
       route (plan-30 §5.2 G-DIAGNOSTICS), so this facet still cannot fetch. Wave 7 / spec 37 replaces
       this with the right-click backlinks LENS on an entity badge (plan-30 PO-1) — not a facet, not a
       panel. Until then an honest gap names its REAL blocker. */}
   <Section title="References" testid="plan-drawer-section-references">
     <EmptyFacet>
       Back-references (where else this node's entities appear) come from
       <code className="mx-1">composition_find_references</code> — the assistant can already run
       this for you; ask it in chat. It has no GUI surface yet, so this panel can't show them.
       The cast above is this node's own roster.
     </EmptyFacet>
   </Section>
   ```
   **Zero behavior change, zero risk:** the `testid` is preserved, so `PlanDrawer.test.tsx:74` (which asserts
   the testid **only**, not the copy) stays green. **Run the existing PlanDrawer suite as the evidence.**
   🔴 **EXPLICITLY OUT OF SCOPE — do NOT do these instead:** do **not** add a REST route for entity backlinks
   (Wave 7 owns it, **PO-1 sealed the surface as a right-click lens on an entity badge, NOT a PlanDrawer
   facet**, and `/works/{pid}/references` is **already taken** by the research shelf, `references.py:79`).
   **Keep the EMPTINESS. Correct only the REASON.**

2. **EDIT** `frontend/src/features/studio/panels/PlanHubPanel.tsx` — two small additions:
   - **publish the bus slice** on an arc/saga selection, so the dock panel follows the Hub:
     in `focusNode`/`select`, when the selected node's `kind` is `arc`/`saga`,
     `publish({ type: 'arc', arcId: nodeId })`.
   - an **"Open in Arc Inspector ⤢"** button in the embedded body's header (embedded variant only):
     `openPanel('arc-inspector', { focus: true, params: { bookId, arcId } })` — the same `openPanel(id,
     {focus, params})` seam `PlanHubPanel.tsx:72` already uses for `quality-canon`.

**Conflict surface: one file, ~55 lines deleted, ~6 added (incl. the `bookId` pass-through), no shared
symbols moved.** If the Book-Package track re-opens, this reverts cleanly.

**Tests** — **EDIT** `frontend/src/features/plan-hub/components/__tests__/PlanDrawer.test.tsx`.
🔴 **MANDATORY, SAME COMMIT — and it is a REWRITE, not a deletion.** The existing case at **`:91-114`**
(*"arc/saga: renders the minimal arc summary + the reuse-gap note"*) asserts **every testid this deletion
removes** (`plan-drawer-section-structure`, `-section-roster`, `-f-chaptercount`, `-f-span`,
`-noncontiguous`, `-arc-gap`) and **WILL RED**. 🔴 **Deleting the assertions alone is a FAIL of this slice —
it leaves a test whose NAME lies and silently drops the only arc-variant coverage `PlanDrawer` has**
(`Q-32-AI4-PLANDRAWER-EMBED` step 3 / `Q-32-DOD-GREP-GATES`).

| Test | Asserts |
|---|---|
| **REWRITE `:91-114`** → `arc/saga: embeds the arc inspector` | `vi.mock` the `ArcInspectorBody` module; assert the arc branch renders it with **`arcId="A1"`, `bookId="b"`, `embedded`** |
| 🔴 `bookId reaches the embedded body` | the prop-threading bug guard — render `<PlanDrawer kind="arc" bookId="b1" selectedId="arc-1" …/>` **with `writes` OMITTED** and assert the mount received `bookId="b1"` / `arcId="arc-1"`. **This ALSO locks in that the embed does not depend on the outline `writes` prop** |
| `the drawer and the dock panel render the SAME component` | the DOCK-2 fork guard |
| `a VIEW-only drawer renders the body read-only` | the body's **own** `useBookGrant` returns `'view'` ⇒ no controls. **NOT** driven by `writes` |
| **DELETE `:88`** | the `plan-drawer-arc-gap` **negative** assertion — the testid is gone repo-wide, so the assertion is **vacuous** |
| **hygiene** | 🔴 `rg -nF "plan-drawer-arc-gap" frontend/src` → **ZERO hits**, and `rg -n "rosterKeysOf\|ArcFacets" frontend/src` → **ZERO hits**. ⚠ Memory `hygiene-grep-literal-token-in-comment-false-positive`: a grep **also matches the token in a COMMENT** — make sure the deleted note leaves **no prose trace** |

**DoD evidence:** `npx vitest run src/features/plan-hub` → `N passed`, **plus** `npx tsc --noEmit` green
(the cast-free fixtures), **plus** the pasted output of `rg -nF "plan-drawer-arc-gap" frontend/src` showing
**nothing**.
⚠ **SCOPE OF THAT GREP IS `frontend/src` ONLY** (`Q-32-DOD-GREP-GATES` — the spec's *"zero hits repo-wide"*
is a **SPEC BUG**): the token legitimately survives in `30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md:238`, in spec 32
itself, in `design-drafts/screens/studio/screen-arc-inspector.html` (6 hits), and in `.playwright-mcp/*.yml`
snapshots. **Do NOT edit prose or snapshots to chase a repo-wide zero.**

---

### **W2-S10 · TEST · the LIVE BROWSER SMOKE + `/review-impl` + the wave close**
**dependsOn:** all

**Files**

1. **CREATE `frontend/tests/e2e/specs/arc-inspector.spec.ts`** (Playwright). 🔴 **Copy the skeleton of
   `frontend/tests/e2e/specs/studio-editor-craft.spec.ts:1-30`** — same imports (`loginViaUI` from
   `../helpers/auth`; `getAccessToken, createBook, createChapter, trashBook` from `../helpers/api`;
   `StudioPage` from `../pages/StudioPage`), same `beforeAll` (token → createBook → createChapter ×3) /
   `afterAll` (trashBook) / `beforeEach(loginViaUI)` shape. **Do NOT invent a new harness.**
   ⚠ **`StudioPage.openPanel(id, title)` (`StudioPage.ts:43`) drives `palette-entry-studio.openPanel.<panelId>`**
   — which requires the panel be registered via `useStudioPanel` with `commandId studio.openPanel.arc-inspector`.
2. **EDIT** `docs/sessions/SESSION_HANDOFF.md` (▶ NEXT SESSION + the Deferred table — see below).
3. **EDIT** `docs/plans/2026-07-12-book-package-RUN-STATE.md` — clear **DBT-06**.
4. **EDIT** `docs/specs/2026-07-01-writing-studio/30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md` + `32_arc_inspector.md`
   — the doc edits below.

**🔴 THE BOOKKEEPING — EXACT, because the spec's wording does not match the target files**
(`Q-32-DOD6-BOOKKEEPING`). Land all of it in the **final commit** (CLAUDE.md's COMMIT phase requires the
SESSION update in the same commit as the code).

- **(a) RUN-STATE (`2026-07-12-book-package-RUN-STATE.md:216`).** 🔴 **There is NO "Recently cleared" section
  in that file** — the first draft's *"move DBT-06 to Recently cleared"* names a heading that **does not
  exist** (its §-headers are 1-11). **The file's own convention is STRIKE-THROUGH IN PLACE inside §8** (see
  `~~DBT-08~~:220`, `~~DBT-12~~:221`, `~~DBT-10~~`/`~~DBT-11~~:222-223`). So edit line 216 to
  `| ~~DBT-06~~ | **CLEARED 2026-07-<dd> (Wave 2 / spec 32, `<sha>`)** — … | `PlanDrawer.tsx:191` | — |`.
  **Do NOT invent a "Recently cleared" heading.** Do not touch §5's D2 row or §11 — that run is closed.
- **(b) SESSION_HANDOFF (`:95`)** — the Writing-Studio track's *"### Deferred (from plan 30 …)"* table is the
  **ONE home** for these rows. **`docs/deferred/DEFERRED.md` does NOT carry the plan-30 rows** (it is the AMAW
  list) — **do not double-file.** Add §9's *surviving* rows (note: **five of the first draft's rows are now
  DELETED, not carried** — see §9). Update the track's header line (`:49`, currently *"AUDIT + SPECS DONE,
  BUILD NOT PLANNED"*) with Wave 2 shipped + the live-smoke evidence string.
- **(c) plan-30 "Wave 2 row closed" = THREE edits, not one:** (i) §5.1 gap row **`G-ARC-SPEC-CRUD`** (`:238`)
  — prefix with `✅ SHIPPED 2026-07-<dd> (<sha>, spec 32)`; (ii) the `### Wave 2 — THE SPEC TREE` block
  (`:364-371`) — stamp `**Status: ✅ SHIPPED**`, note BE-A1/A2/A3 landed; (iii) Appendix B (`:816`) —
  `| ~~DBT-06~~ | ✅ G-ARC-SPEC-CRUD (Wave 2) — SHIPPED |`.
- **(d) 🔴 plan-30 §8.2's X-12 — REWRITE IT, don't just annotate** (`Q-32-X12-AMEND-PLAN30`). Its premise
  (*"a panel that needs an id is structurally OUTSIDE the agent enum ⇒ must be `hiddenFromPalette`"*) is
  **FALSE** — it conflated *has a target id* with *requires params*, and **two shipped panels refute it**:
  `scene-inspector` (resolves its subject from **ambient host state + the bus**, `SceneInspectorPanel.tsx:84`
  — never from params; degrades honestly to *"Select a scene…"*) and `quality-canon` (reads `props.params`,
  but they are **OPTIONAL** — a bare-id open renders the full book-wide list).
  **THE REAL PREDICATE, which replaces the old one:** *a panel is **enum-eligible iff a BARE-ID OPEN IS
  USEFUL*** — its target is ambient-resolvable, **or** `params` are a pure focus/deep-link refinement that
  degrades to a sane full view. `hiddenFromPalette` / out-of-enum is **only** for panels where params are
  **REQUIRED** (nothing sane to render without them) — exactly today's hidden set (`wiki-editor`,
  `job-detail`, `book-reader`, `skill-editor`, `json-editor`).
  Also: **strike `motif-editor` from X-12's example list** — spec 33 §3.1 ships **no** `motif-editor` panel
  (motif detail is a **drawer inside `motif-library`**), so there is no by-id open to decide
  (`Q-32-MOTIF-EDITOR-BYID`). And **strike `workflow-editor` — it is MOOT** (G-WORKFLOWS is **DROPPED**, PO-2,
  Track C owns it).
  **§11 item (a) → CLOSED.** Both halves are answered: the `ui_show_panel` half by **PO-3 (RETIRE)**; the
  `ui_open_studio_panel`-**params** half by **NO — bare id only** (a closed-set `resource_ref` is a different
  thing, and it lands in W2-S4b).
- **(e) spec 32 edits:** §6 — strike *"the baseline here is **61**, not 57"* → *"the baseline is whatever HEAD
  has when this wave starts — **measure it, don't quote it**"*. §9 **M2** — replace *"The 4 drift-lock suites
  green (58==58==58)"* → *"…green — they assert **SET EQUALITY**, not a count. Assert the **DELTA** (+1) and
  that `arc-inspector` is in all three. **NEVER pin a literal.**"* **AI-3** → *"the panel is the UX layer, not
  the enforcement layer."* **OQ-2** → **RESOLVED** (W2-S3b). **OQ-1** → drop the "paid / propose→confirm"
  clause (it is a **Tier-R read**; the blockers are *no REST route + not in the allowlist ⇒ 403*).
  **Fix the stale cite:** DoD #5 and §1 cite `arc_apply.py:564` for `extract_template_from_arc` — at HEAD
  `:564` is a line *inside* `arc_extract_template` (def `:528`); **the persisting seam is at `:652`.**

**The smoke — MANDATORY, not negotiable.** A green unit suite has repeatedly hidden *"the FE could not
actually execute it"* (memory `agent-gui-loop-needs-live-browser-smoke-not-raw-stream`; **spec 24's own H8.2
DoD was never met** — no Playwright targets `plan-hub` anywhere and its "smoke" was curl).

**Setup:**
```bash
# 🔴 REBUILD FIRST. :5174 is the BAKED nginx prod build — a stale image is a false green
# (memory: live-smoke-rebuild-stale-images-first, frontend-5174-is-baked-prod-nginx-not-vite).
docker compose -f infra/docker-compose.yml build frontend composition-service book-service chat-service
docker compose -f infra/docker-compose.yml up -d
# sign in as claude-test@loreweave.dev / Claude@Test2026
```
**Drive dockview via `evaluate` + `data-testid`** — Playwright refs go stale in dockview
(memory `playwright-live-dockview-automation-recipe`); use `page.mouse` for any drag.

**The legs — each is a `test(...)` block, and each is a DoD line:**

| # | Leg | The proof |
|---|---|---|
| L1 | `⌘⇧P → Arc Inspector mounts` | `await new StudioPage(page).openPanel('arc-inspector', 'Arc Inspector')` ⇒ `expect(page.getByTestId('arc-inspector-panel')).toBeVisible()` |
| L2 | `create saga → plan-hub lanes update with NO reload` | 🔴 open `plan-hub` in a **second dock tab FIRST**, create the saga from the inspector, assert the lane row appears **without** `page.reload()`. **A `page.reload()` anywhere in this test is an AUTOMATIC FAIL** — the whole point is that cache invalidation reaches the **hand-rolled** loader (memory `invalidatequeries-cannot-reach-hand-rolled-state`) |
| L3 | `sub-arc inherits the parent's track` | add a track **on the saga**, open the sub-arc ⇒ the row shows the **INHERITED** badge naming the saga, **and** `GET /arcs/{subArcId}` returns it inside `resolved.tracks` with `provenance.tracks[k].is_own === false` — the cascade + the **sidecar** proving themselves end-to-end |
| L4 | `edit title → save → edit again IMMEDIATELY → NO 412` | two `fill`+save cycles back-to-back with **no wait between**; assert **zero 412** in a `page.on('response')` capture (the serialization fix) |
| L5 | `out-of-band write → "changed elsewhere — reloaded" → the retry SUCCEEDS` | with the panel open holding a stale version, drive an out-of-band `PATCH /v1/composition/arcs/{id}` from the test's `request` context, then save in the panel ⇒ the conflict notice renders **AND the retry lands 200**. *(Default, veto-able: the conflict is driven by REST rather than an MCP round-trip — the tool delegates to the same handler, so the conflict source is identical and the test avoids MCP-auth plumbing. The real agent path is proven by L8.)* |
| L6 | `assign → then REMOVE a chapter → it lands in the unassigned tray` | seed via `POST /books/{id}/arcs/assign-chapters`; do the **REMOVE through the UI** ⇒ the chapter appears under `?unassigned=true` — **BE-A3's whole reason to exist** |
| L7 | `archive → the confirm names the REAL sub-arc count → restore brings back the subtree AND the ancestors` | assert the confirm text contains the **actual** descendant count (not `0`, not hardcoded), and the **toast** reads the response's `archived_count` |
| L8 | 🔴 `agent leg — ui_open_studio_panel {panel_id:'arc-inspector'} mounts a DOCK TAB` | copy the injection pattern from `frontend-tools-liveness.spec.ts` (`installFrontendToolSuspend` from `../helpers/frontendToolInject`). **Assert BY EFFECT** — `getByTestId('arc-inspector-panel')` visible **and** a `.dv-default-tab` reading "Arc Inspector". 🔴 **NEVER `shown:true` in the raw stream** |
| L8b | 🔴 `agent deep-link — resource_ref {kind:'structure', id} lands ON THAT ARC` | the W2-S4b leg: the panel opens **and** its subject is the referenced arc |
| L9 | `the VIEW-only leg` | sign in as a second account with a **VIEW** grant ⇒ `arc-inspector-readonly-note` renders and there is **no Save / no + track / no Archive / no Override**. *(If no second account exists, `test.fixme()` it + file `D-ARC-VIEWONLY-SMOKE` (gate #4) and **say so — never claim it passed**.)* |

🔴 **THE DoD WORDING IS LITERAL** (`Q-32-LIVE-BROWSER-SMOKE` step 5): *"The transcript contains the **PASTED
OUTPUT** of `npx playwright test tests/e2e/specs/arc-inspector.spec.ts` showing the legs passing against a
**REBUILT** image. **Claiming the smoke passed without pasting its output does NOT satisfy this DoD.**"*
**No `live infra unavailable` escape hatch is granted here** — the stack is bootable in this repo. If a leg is
genuinely unrunnable, **the spec file still ships with that leg written**, marked `test.fixme()`, **plus a
tracked defer row naming it — never a silent omission.**
*(The premise is verified: `grep -rn "plan-hub" frontend/tests/e2e` → **ZERO hits**. Spec 24's H8.2 "smoke"
never touched a browser — it was curl. That is the failure this leg exists to not repeat.)*

**The generation loop closes — THREE proofs + one FE guard, NOT one** (`Q-32-DOD5-TWO-PROMPT-PROOFS`).

1. **`tracks` → prompt — 🔴 THE TEST ALREADY EXISTS. Do not rewrite it; RE-RUN it.**
   `tests/integration/db/test_pack_arc_wired.py::test_changing_tracks_changes_the_prompt_on_the_real_path`
   already drives real `pack()` through the production scene→chapter→arc resolution and asserts
   `before != after` after `StructureRepo.update(..., {"tracks": …})`. **That IS proof (a).** No new code.
2. **`roster_bindings` → prompt — NEW**, same file, same `_seed`/`_pack_prompt` harness:
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
   🔴 **Two details a builder WILL get wrong otherwise:** (1) `gather_arc` prints `role_key → the RAW
   entity_id string` (`lenses.py:336-344`) — **assert the UUID, not the glossary display name** (name
   resolution is FE-only, `useGlossaryRoster`). (2) **Patch `roster_bindings` ALONE** (no `tracks` in the same
   PATCH) — that is what catches a write-model that **drops the field** (`rest-write-mirror-drops-fields`).
   **Each prompt-bearing write needs its OWN proof:** a `tracks`-only test would leave the entire
   Roster/binding editor — the panel's second-biggest write surface — **unproven**, which is the
   **write-only-behavior** bug CLAUDE.md bans, wearing the costume of a green suite.
3. **`roster` (the slots) → the TEMPLATE, and explicitly NOT the prompt — NEW.** In
   `tests/integration/db/test_arc_apply_roundtrip.py`: set `roster`, call **`extract_template_from_arc`
   (`arc_apply.py:652` — 🔴 **NOT `:564`**, which is a line *inside* the pure `arc_extract_template`, def
   `:528`; the spec's cite is stale), load the created row via `ArcTemplateRepo` and assert `arc_roster`
   contains it. **PLUS a NEGATIVE assertion** back in `test_pack_arc_wired.py`: an arc with `roster` set but
   **no** `roster_bindings` packs a prompt containing **neither** `"Cast bindings"` **nor** the slot key —
   *this pins that `roster` is deliberately not a prompt input, so a future "helpful" packer edit that injects
   it REDS instead of silently doubling the arc frame.*
4. 🔴 **THE ANTI-DRIFT GUARD (new, cheap, one test — this is what keeps the UI copy honest).** In
   `test_pack_arc.py`, add `test_gather_arc_reads_only_prompt_bearing_fields`: **(a)** spy the structure repo
   and assert **`resolve_roster` is NEVER called** during `gather_arc`; **(b)** mutate **only** `summary` and
   `status` and assert the returned arc frame string is **byte-identical**. If a future change starts
   injecting summary/roster, **this reds and forces the UI copy to be updated with it.**
5. **The FE guard (closes the panel→route leg the pytest cannot):** in the arc-inspector vitest, assert the
   **role-bind mutation's PATCH body carries `roster_bindings`** and the **track editor's carries `tracks`**.
   **Without it, a Pydantic write model that omits `roster_bindings` leaves the panel a silent no-op while
   BOTH backend tests stay green.**
6. ⚠ **NO pack-effect test for `summary` or `status`** — they have **no engine consumer**. Their proof is the
   Hub/drawer rendering them, and the UI copy **labels them as human-read, not generation knobs**.

🔴 **All of these are `skipif TEST_COMPOSITION_DB_URL`. The evidence string must paste counts from a run with
the DSN SET. A skipped file is not a proof.**

**Then `/review-impl` on the wave's whole diff, and FIX every bug it finds before the wave closes.**

---

## 4 · The GG-8 registration checklist (the running enum baseline)

| # | File | Change | Slice |
|---|---|---|---|
| 0 | 🔴 `contracts/api/composition/v1/openapi.yaml` | **CONTRACT-FIRST** — the 8 arc paths + schemas. **BEFORE any FE slice** | **S0** |
| 1 | `frontend/src/features/studio/panels/ArcInspectorPanel.tsx` | the panel. Root `data-testid="arc-inspector-panel"` (the id the E2E harness drives) | S4 |
| 1b | `…/panels/ArcInspectorBody.tsx` | the **shared** body (dock **and** PlanDrawer — AI-4). Props: `{arcId, bookId, embedded?}` — **no `writes`, no `canEdit`** | S4 |
| 1c | `…/panels/useArcInspector.ts` + `…/panels/arc/cascadeRows.ts` | the controller + a **presenter** that zips `resolved.*` with `resolved.provenance.*`. 🔴 **NO merge logic** (`arcCascade.ts::splitCascade` is **DELETED** — the BE sidecar is the source) | S4/S5 |
| 1d | `…/panels/arc/fieldClasses.ts` | **ONE HOME** for `PROMPT_BEARING` / `REFERENCE_ONLY`. Every badge reads from it | S5 |
| 1e | `…/panels/useArcChapters.ts` + `…/panels/ArcInspectorEmptyState.tsx` | keyset+virtualized members · the empty state with the plan-hub link | S5/S7 |
| 1f | `frontend/src/features/books/hooks/useBookGrant.ts` + `books/api.ts` | reads **`access_level`** off `['book', bookId]`. 🔴 **NO new route** | S5 |
| 2 | `…/panels/catalog.ts` | one row after `plan-hub` (`:190`), `category: 'editor'`, **no `hiddenFromPalette`** | S4 |
| 2b | 🔴 `…/palette/useStudioCommands.ts` | **X-2: add `'quality'` to `CATEGORY_ORDER`** + the recurrence guard test | S4 |
| 3 | `frontend/src/i18n/locales/en/studio.json` | `panels.arc-inspector.*` (incl. `provenance.{fromTemplate,authored,unavailable}` and the 3 kind labels / **2** kind values) | S4 |
| 4 | `…/locales/{ar,bn,de,es,fr,hi,id,ja,ko,ms,pt-BR,ru,th,tr,vi,zh-CN,zh-TW}/studio.json` | **17** locales · `python scripts/i18n_translate.py` — **never hand-written** | S4 |
| 5 | `services/chat-service/app/services/frontend_tools.py` | **(a)** `panel_id` enum `+1` (`:402`) **(b)** the description clause (after the `plan-hub` clause, `~:448`) **(c)** the `resource_ref` arg + `CLOSED_SET_ARGS` | S4/S4b |
| 6 | `contracts/frontend-tools.contract.json` | **REGENERATE** (`WRITE_FRONTEND_CONTRACT=1 pytest`), commit **with** 2 + 5. **NEVER hand-edit, NEVER hand-merge** | S4 |
| 7 | `…/studio/host/types.ts` | the `arc` bus event (**`arcId: string \| null`**) + `activeArcId?: string` + the `applyBusEvent` case | S4 |
| 7b | 🔴 `…/panels/PlanHubPanel.tsx` | **THE PUBLISHER** — without it the bus slice has no producer and AI-1 is dead code | S4 |
| 7c | `…/studio/agent/studioUiNav.ts` | `resource_ref` → `openPanel` + `publish`; unknown kind ⇒ `result.error`, **never a silent no-op** | S4b |
| 8 | `…/studio/agent/handlers/arcEffects.ts` **(NEW)** + `useStudioEffectReconciler.ts` | **MANDATORY (X-4).** ONE home for `composition_arc_*`. 🔴 **TWO edits to the reconciler — import AND call** | S8 |
| 9 | `…/studio/onboarding/tours.ts` | **skip** — not a role-tour step in v1 | — |
| — | `…/studio/host/studioLinks.ts` | **skip** — no external URL resolves to an arc | — |

**The running baseline (plan 30 §8.0):** HEAD `9262ed53e` = **57** (measured) · after Wave 1 = 61 · after
Wave 2 = 62 · … · after Wave 8 = 71.
🔴 **These are a PLANNING aid ONLY. NOTHING IN THE REPO ASSERTS A COUNT** — the drift-lock is **set equality**
(`panelCatalogContract.test.ts:33`) plus `length > 0`. **The DoD asserts `baseline + 1` and the three-way
equality, measured — never a literal, and never a new count-pinning test** (which would red on every future
panel). If a wave is re-ordered or dropped, every number above is wrong and **nothing breaks**.

---

## 5 · Compliance — stated, not assumed

**Tenancy (User Boundaries).** No new table, no new row, no new scope key. `structure_node` is **Per-book**
(BA8: `book_id` is the scope — there is no `project_id`, no `user_id`, no `owner_user_id`). Every route
gates on the **E0 book grant, resolved FROM THE ROW** (`_gate_arc`, `arc.py:383` — the
`worker-loaded-id-needs-parent-scoping` / `gate-must-derive-scope-from-the-loaded-row` pattern): VIEW to read,
EDIT to write. A missing node and a denied grant return the **SAME** uniform 404 (H13 — no existence oracle).
`created_by` is an **actor stamp, never a scope key** (`models.py:211`) — the panel **displays** it and
**never filters on it**. There is no System tier here and no shared user-editable row: an arc belongs to
exactly one book. **A collaborator with EDIT shares one spec tree with the owner** — that is BA8's deliberate
design (a team shares one `main.tf`), not a leak.
🔴 **There is NO new route in this wave** — the `my-access` route the first draft invented is **deleted**
(§0.1 LA-1), which also deletes its entire tenancy surface (no new grant oracle, no new `user_id` param, no
new fail-open path). The grant is read from **`GET /v1/books/{book_id}`'s existing `access_level`**, which is
**server-computed for the caller** and cannot be spoofed by the client. `useBookGrant` **fails closed**
(unresolved ⇒ `canEdit === false`), so a control that would 403 is never rendered — **not even for one frame.**
**The uniform 404 STAYS** (`Q-32-UNIFORM-404`): do **not** add an existence-probe route, an `exists` flag, or
a distinct 410/403 for "gone". That IS the oracle H13 forbids and it leaks cross-tenant row existence — **a
tenancy control, not an ergonomics wart.** The whole fix is frontend (the `gone` state).

**Settings (SET-1..8).** This wave introduces **zero** settings, **zero** toggles, **zero** env flags. The one
thing that *looks* like a setting — an arc's **inherited vs own** track/role — is not one: it is a **data
cascade**, and AI-2 requires the panel to show the **effective value + its source tier**
(own / inherited-from-«ancestor»), which is SET-1's spirit applied to data. A silently flattened cascade would
be the "grounding always-on / reasoning silently-off" bug in a new domain.

**Provider gateway / no hardcoded models.** **N/A — this wave makes zero LLM calls.** No provider SDK, no
model name, no embedding, no rerank. If a later agent adds an LLM button here it goes through
`provider-registry-service` and the **generic** `/actions/preview` → `/actions/confirm` spine.

**MCP-first.** **Already satisfied.** All 8 arc tools exist (`server.py:4191-4543`) and this wave **adds
none** — it changes two schemas in lockstep with their REST twins. The *human* side was the hole.
**INVERSE gaps after this ships: ✅ none for arcs** — all 8 tools gain a human equivalent, and BE-A3 gives
the **agent** an unassign it never had (a GUI-only unassign would have been a **new** GG-2 inverse gap).

**Gateway invariant.** All external traffic goes through `api-gateway-bff`. `/v1/composition/*` and
`/v1/books/*` are already proxied; the composition proxy's `pathFilter` is generic (`gateway-setup.ts:354`).
**Zero gateway work.** 🔴 **`composition_arc_suggest` must NEVER be added to `FE_BRIDGE_TOOL_ALLOWLIST`**
(`tools.controller.ts:24-30`) — plan 30 BE-6. It gets a **REST route in Wave 4**, not a bridge entry.

**Contract-first (CLAUDE.md).** 🔴 **W2-S0 is the contract slice and it lands FIRST.** The 8 arc routes have
been shipping **uncontracted** since B1 — `contracts/api/composition/v1/openapi.yaml` had **zero** `/arcs`
paths (verified). Every changed shape in this wave is frozen there **before** the FE consumes it, and a slice
that changes a shape **edits the contract in the same commit**.
⚠ **`contracts/api/composition-service/plan-forge.v1.yaml` is a DIFFERENT file — Wave 5's. Do not touch it.**
⚠ **`contracts/api/book-service/` DOES NOT EXIST** (books live at `contracts/api/books/v1/openapi.yaml`) —
and this wave touches **neither**, because there is no Go work.

**Frontend-Tool Contract.** `panel_id` is a closed set ⇒ an `enum` ⇒ machine-checked on both sides via
`contracts/frontend-tools.contract.json` (regenerated, never hand-edited). **`resource_ref.kind` is likewise a
closed set ⇒ `enum` ⇒ `CLOSED_SET_ARGS`, and its resolver returns `result.error` on an unknown kind — never a
silent no-op.** 🔴 **No free-form `params` arg on `ui_open_studio_panel`** — that is the `ui_show_panel` shape
**PO-3 is retiring**. One name for one concept (`arc-inspector`; no near-miss among the existing ids).

**Cost gates.** **NONE, by construction** — every action is deterministic REST CRUD, **$0**, no LLM (grep
`confirm|token|spend|llm|estimate` across `arc.py` hits only the JWT bearer dep at `:587`). **Adding a cost
gate to this panel is a DEFECT**, and it is **machine-checked** (W2-S6's two tests: no arc descriptor in
`_ALL_DESCRIPTORS`; no `/estimate` or `actions/` URL in the panel's api module). If a later wave adds an LLM
action here, it goes through the **generic** `/actions/preview` → `/actions/confirm` spine — **never a bespoke
per-action estimate route. Three such invented routes 404 in production today. Do not make it four.**

---

## 6 · React-MVC compliance (a violation is a review finding)

- **hooks own logic, components render.** `useArcInspector.ts` / `useArcWrites.ts` contain **no JSX**;
  `ArcInspectorPanel.tsx` / `ArcInspectorBody.tsx` contain **no API calls and no business logic**.
- **≤~100 lines per component, ≤~200 per hook.** `ArcInspectorBody` will exceed 100 if written as one
  component — **split it into the 7 section components** (`ArcIdentitySection`, `ArcTracksSection`,
  `ArcRosterSection`, `ArcChaptersSection`, `ArcPromisesSection`, `ArcProvenanceSection`, `ArcDangerSection`)
  in `frontend/src/features/studio/panels/arc/`. Each takes data + callbacks as props.
- **No `useEffect` for event handling.** The pattern `useEffect(() => { if (prev && !current) … }, [current])`
  is **always wrong**. Every write is an explicit callback handler.
- **Never conditionally unmount a stateful component.** The picker and the body stay mounted; empty/loading/
  error states branch *inside* them (`PlanDrawer.tsx:410`'s precedent: hook first, self-hide after).
- 🔴 **Never define a component inside a render body** (memory
  `component-defined-in-render-body-remounts-subtree`) — it remounts the whole subtree on every keystroke,
  which will eat the title input's focus.
- **`invalidateQueries` cannot reach hand-rolled state** (memory `invalidatequeries-cannot-reach-hand-rolled-state`).
  The Hub's window slices are hand-rolled — that is why `usePlanNodeWrites` calls `reloadWindows()` **in
  addition** to invalidating. If a write from this panel must refresh a Hub window, it must go through the
  same seam.

---

## 7 · Test parallelization (CLAUDE.md — mandatory)

- Python: `python -m pytest tests -q -n auto --dist loadgroup`.
- 🔴 **Every NEW test touching a real DB/port carries `pytestmark = pytest.mark.xdist_group("pg")`** or the
  parallel workers interleave and the counts lie. The two integration files we edit
  (`tests/integration/db/test_structure_repo.py`) **already have it at module scope — verify it is still
  there** before adding tests to them.
- 🔴 **An env-gated integration test that SKIPs is not a passing test** (memory
  `env-gated-integration-tests-skip-and-the-green-suite-lies`). `TEST_COMPOSITION_DB_URL` **must be set**
  when you run the BE DoD, and the pasted evidence must show `passed`, not `skipped`.
- Go: `cd services/book-service && go test ./...`.
- Frontend: `cd frontend && npx vitest run <paths>`.
- ⚠ Memory `vitest-beforeeach-returning-a-mock-is-treated-as-teardown` — a `beforeEach` that **returns** a
  mock is called again as teardown. Wrap it in braces.

---

## 8 · Wave Definition of Done (a literal checklist — every line pasted, not claimed)

- [ ] **1 · 🔴 CONTRACT (W2-S0), committed FIRST.** `contracts/api/composition/v1/openapi.yaml` lints clean and carries all 5 arc paths incl. the `428` on `PATCH /arcs/{node_id}`. Paste the lint + the assertion output. **(There is NO `go test` line — this wave writes no Go.)**
- [ ] **2 · `services/composition-service`** — `python -m pytest tests -q -n auto --dist loadgroup` →
      **`<pre-flight-G7 baseline> + 40 passed`**. Paste it. **Plus** the separate, pasted output of
      `python -m pytest tests/integration/db -q -k "raw_strided or gap_count or unassign or provenance or archive_does_not_cascade or blind_repo or merge_by"`
      showing **`passed`, NOT `skipped`** (`TEST_COMPOSITION_DB_URL` **must** be set — memory
      `env-gated-integration-tests-skip-and-the-green-suite-lies`).
- [ ] **3 · `services/chat-service`** — `python -m pytest tests/test_frontend_tools_contract.py tests/test_frontend_tools.py -q` green.
- [ ] **4 · The four drift-locks** — `npx vitest run panelCatalogContract.test.ts UserGuidePanel.test.tsx useStudioCommands.test.ts frontendToolContract.test.ts` green, with **`py enum == contract enum == OPENABLE_STUDIO_PANELS`** (SET equality) and the count = **pre-flight-G4 baseline + 1**. 🔴 **Assert the delta, never a literal. Add no count-pinning test.**
- [ ] **5 · Frontend suite** — `cd frontend && npx vitest run` green + **`npx tsc --noEmit` green** (the cast-free `ArcListNode` fixtures). Record the counts.
- [ ] **6 · 🔴 `rg -nF "plan-drawer-arc-gap" frontend/src` → NOTHING** (and `rg -n "rosterKeysOf|ArcFacets" frontend/src` → nothing). The UI no longer tells the user this feature is missing. **Scope is `frontend/src` ONLY** — the token legitimately survives in specs, the design mock, and `.playwright-mcp` snapshots. **Do NOT edit prose to chase a repo-wide zero.** Paste the empty output. ⚠ **The test at `PlanDrawer.test.tsx:91-114` must be REWRITTEN, not deleted** — deleting it drops the only arc-variant coverage the drawer has.
- [ ] **7 · 🔴 The NO-FE-CONSUMER routes have a consumer — proven BY EXPORTED FUNCTION, not by URL** (`Q-32-DOD-GREP-GATES`; the spec's original gate is broken **twice**):
      `rg -n 'export (async )?function (createArc|getArc|updateArc|archiveArc|restoreArc)\b' frontend/src` → **exactly 5 hits**, all in the arc api layer.
      Tripwire: **`rg -nF 'arcs/${' frontend/src`** → ≥5 hits (**`-F` is REQUIRED** — run unquoted under ripgrep it **ERRORS**: *"regex parse error: repetition quantifier expects a valid decimal"*, because `$` is an anchor in Rust regex; it only ever "worked" under GNU grep).
      ⚠ **The URL grep can NEVER match `create`** — that route is book-keyed (`POST /books/{id}/arcs`), so its literal ends in `arcs` and contains no `arcs/${`. **`create` is proven by the browser smoke (L2)** instead. ⚠ **Do NOT name the fns `archiveNode`/`restoreNode`** — those already exist and hit `/outline/nodes/{id}`, a **different route family**.
- [ ] **8 · 🔴 LIVE BROWSER SMOKE** — the **pasted output** of `npx playwright test tests/e2e/specs/arc-inspector.spec.ts` against a **REBUILT** image (`:5174` is the BAKED nginx build — a stale image is a false green), signed in as `claude-test@loreweave.dev`. **Verify by EFFECT** — a dock tab, not a `shown:true` in the raw stream. **Claiming it passed without pasting its output does NOT satisfy this item.** An unrunnable leg ships as `test.fixme()` + a defer row, never a silent omission.
- [ ] **9 · 🔴 The generation loop closes — THREE proofs + the FE guard.** `tracks` (the **existing** wired test, re-run) · `roster_bindings` → the *"Cast bindings: …"* line (**new, patched ALONE**) · `roster` → `extract_template_from_arc` **plus the negative** (`roster` alone puts nothing in the prompt) · **plus** `test_gather_arc_reads_only_prompt_bearing_fields`. **`summary`/`status` get NO pack-effect test** — do not test them as if they were prompt inputs.
- [ ] **10 · 🔴 `/review-impl` run on the wave's whole diff, and EVERY bug it finds FIXED before the wave closes.** Paste its findings + the fixes.
- [ ] **11 · `docs/sessions/SESSION_HANDOFF.md`** updated (▶ NEXT SESSION + the Deferred table at `:95` — §9's **surviving** rows only; **five of the first draft's rows are DELETED, not carried**). Do **not** double-file into `docs/deferred/DEFERRED.md`.
- [ ] **12 · Docs.** `DBT-06` **struck through IN PLACE in RUN-STATE §8** (🔴 **there is no "Recently cleared" section** — do not invent one); plan 30's **three** Wave-2 edits; **§8.2's X-12 REWRITTEN** (the real predicate: *bare-id-open is useful*), `motif-editor` struck, `workflow-editor` struck as MOOT; **§11(a) CLOSED**; spec 32's §6/§9-M2/AI-3/OQ-1/OQ-2 + the stale `arc_apply.py:564` cite fixed.
- [ ] **13 · Committed.** Files enumerated, never `git add -A` (3 tracks share this checkout). ⚠ `git commit -- <path>` commits the **WORKING TREE, not the index** — and **the index may already carry someone else's pre-staged changes**; check `git diff --cached --name-only` first.

---

## 9 · Defer register — the starting rows

### 9.0 🔴 FIVE ROWS THE FIRST DRAFT CARRIED ARE **DELETED**, NOT CARRIED

The register adjudicated each of these **against source** and found the deferral's premise false. **Do not
re-file them. Do not add them to SESSION_HANDOFF.** *(CLAUDE.md: "FIX-NOW is the default; deferral is the
exception that must EARN its row… if fixing is cheaper than writing + carrying the defer row, just fix it.")*

| Deleted row | Why it is not a defer |
|---|---|
| ~~`D-ARC-TRACKS-ROSTER-SCHEMA`~~ | **BUILT in W2-S3b.** Its rationale was refuted: the typed models **already exist** and are **already enforced one door over** (`models.py:839-861`), and the migration audit is **done and clean** (0 non-empty rows). `Q-32-OQ2-TRACKS-ROSTER-SCHEMA` says **DELETE THIS ROW**. *(A narrower successor row survives below.)* |
| ~~`D-ARC-ARCHIVE-CHAPTER-STRANDING`~~ | **CLOSED as gate #5 (conscious won't-fix)** by `Q-32-OQ8` — **not carried forward.** `archive()` does not cascade an unassign **ever**, because `restore()` is lossless *precisely because* the binding survives. Pinned by a **test** (W2-S1b #7). Revisit **only** if a persisted arc-membership lift map is ever built. |
| ~~`D-ARC-DELETE-BLAST-COUNT`~~ | **BUILT in W2-S1b.** The "second consumer" trigger the row waited for **is already met**: `archive()` has **two** callers, and the MCP tool **holds no tree to derive from** — so today the agent says *"archived the arc"* having silently archived N sub-arcs. `archived_ids`/`archived_count` ship. |
| ~~`D-ARC-STATUS-DERIVED`~~ | **CLOSED — `Q-32-OQ5` decides it: status is HAND-SET, never derived, now or later.** The identical question is **already sealed one layer down** (`models.py:178-183`, PH16). Enforced by a **regression test**, not a defer row. |
| ~~`D-PLANDRAWER-FINDREFS-COPY`~~ | **FIXED in W2-S9 (1b).** `Q-32-OQ4` overrides the deferral: the copy is a **live lie** about a **shipped** tool, and the fix is **grounded in code** (not the RUN-STATE), copy-only, zero-risk, testid preserved. **Keep the emptiness; correct the reason.** |

### 9.1 The surviving rows

| ID | Origin | What | Gate (CLAUDE.md 1–5) | Target |
|---|---|---|---|---|
| **D-ARC-NONKEY-SCHEMA** | S3b (OQ-2, **re-scoped**) | The **key invariant is now ENFORCED** at both write doors (W2-S3b). What remains is typing of the **NON-KEY** fields only — the `constraints[]` vocabulary (deliberately free text today; nothing downstream reads it as an enum). | **#2 structural** — it needs a vocabulary decision, not a bug fix. | its own spec |
| **D-ARC-CONFIRM-EFFECT** | S8 | `composition_arc_import_analyze` returns only a `confirm_token`; its real write dispatches through the shared **`confirm_action`** tool, so **no `composition_arc_*` name ever reaches the reconciler** — `arcEffects` cannot close it. (Same class `translationEffects.ts:1-8` records for resume/retry.) The 拆文 panel must refresh off **job completion** instead. | **#3 naturally-next-phase** | **Wave 4** (spec 34) |
| **D-ARC-PROVENANCE-DEEPLINK** | S5 | Provenance renders the resolved template **title as plain text**; the `[open]` deep-link to the `arc-templates` panel is **not wired because that panel is first registered in Wave 4**. Rendering a dead button would be the silent-no-op class. | **#3 naturally-next-phase** — the target genuinely does not exist yet | **Wave 4** — wire it in the **same slice** that adds the `arc-templates` catalog row; it is a **DoD line of that slice** (*"assert `openPanel` was called with `('arc-templates', {params:{arcTemplateId}})`"* — not a screenshot) |
| **D-ARC-SUGGEST-BUTTON** | S6 (OQ-1) | *"Suggest an arc for this premise"* (`composition_arc_suggest`, `server.py:2272`). **The header slot is RESERVED** (`arc-inspector-header-actions`) so Wave 4 is a pure additive mount. | **#3 next-phase** — it is **not FE-only**: the tool has **no REST route**, and it must **never** enter `FE_BRIDGE_TOOL_ALLOWLIST` (plan 30 BE-6) ⇒ the browser fails closed with a 403. It lands **WITH its backend** (`POST /v1/composition/arc-templates/suggest`). *(It is a Tier-**R read** — it drags **no** propose→confirm cost spine.)* | **Wave 4** |
| **D-BOOK-GRANT-ADOPTION** | S5 | `useBookGrant` (reading the **already-shipped** `access_level`) now exists, and W2-S5 3c hardens `usePlanHub`. But **every other panel still renders EDIT controls to a VIEW-only collaborator** — the field was on the wire and unread repo-wide. | **#1 out of scope** — a repo-wide adoption sweep touches panels three other waves own. **It is cheap; it is just not ours.** | a hygiene sweep, or **Wave 6** |
| **D-ARC-APPLY-MCP-WRAPPER** *(hand-off note, not ours)* | S8 | 🔴 **A CORRECTION Wave 4 MUST HAVE, or it builds a duplicate engine.** Plan 30 `:302` and spec 34 BE-8 say `apply_arc_to_spec` is *"genuinely unwritten ⇒ a real engine (rescale + roster-bind + pacing→tension + ledger)"*. **FALSE.** The engine **EXISTS and is tested**: `app/engine/arc_apply.py:325 async def arc_apply(...)` — it materializes a scene per beat, writes tension from the rescaled pacing curve, emits the ledger, and stamps `arc_template_id`/`template_version`, all in one transaction. It simply has **no production caller** (dead-but-green). **BE-8 is a THIN ADAPTER** (mirror `extract_template_from_arc:652`), **not a new engine** — so it re-sizes **S+S, not S+M**. Likewise `build_template_drift` **delegates** to the already-shipped `compute_arc_report(..., by_structure=False)`. **Do NOT write a second rescale/pacing/ledger engine** (the `css-var-duplicated-across-two-consumers` class). | **#1 out of scope** (Wave 4 owns it) | **Wave 4** |
| **D-ARC-I18N-LOCALES** | S4 | *(only if `scripts/i18n_translate.py` cannot run — needs LM Studio on :1234)* the 17 non-`en` locales. | **#4 blocked** on a local model being up. **The FE falls back to `en` ⇒ cosmetic. NEVER block the wave on it.** | next i18n run |
| **D-ARC-VIEWONLY-SMOKE** | S10 | *(only if a second, VIEW-granted test account is unavailable)* the live-browser proof of the read-only state. | **#4 blocked** on a fixture. **`test.fixme()` the leg and SAY SO — never claim it passed.** | when a 2nd account exists |

---

## 10 · Risks — and the tell that each has fired

| Risk | The tell | Mitigation |
|---|---|---|
| 🔴 **A future agent "cleans up" `StructureRepo.span()`** to match the routes — and **silently breaks every generation prompt.** `span()` is the **packer's** input (`lenses.py:322` → `_arc_position`), which needs the **raw strided** axis. | Every draft's Pacing line reads *"~100% through arc X"* — or vanishes. **The unit suite stays green** (`gather_arc` degrades to `""` on any failure, `:287`). | **BE-A1 forbids touching the repo** and W2-S1 test #4 **pins `span()`'s exact raw keys and values against a real DB**, so the "obvious cleanup" reds instead of shipping. **This is the one edit in this wave that could ship a generation-quality regression with a green suite.** |
| A future agent renders `span.min_story_order` and ships **"Chapters 41000–58000"**. | The mock's ①, in production. | BE-A1 stops **both detail doors** from *serving* the raw block; the parity test pins list == detail == MCP. **The unit never reaches a client.** |
| The cascade is flattened, a user "edits" an inherited track, and **silently forks a copy** of the saga's track that then stops tracking the saga. | The saga's track changes; the sub-arc's does not; nobody knows why. | **AI-2** renders own-vs-inherited **off the server's `resolved.provenance` sidecar** (W2-S1b) and makes **Override** an explicit, named action — with **Revert to inherited** as the escape hatch, so the fork is never one-way. |
| Two rapid edits 412 and **blame a phantom collaborator** for the user's own keystroke. | *"changed elsewhere"* fires when nobody else touched it. | The serialized write chain (`useSceneInspector.ts:43-45`) + the synchronous re-seed (`usePlanNodeWrites.ts:73-75`). **Both are existing, shipped fixes — mirror them, do not re-derive.** W2-S6's first test is exactly this. |
| **The Lane-B handler is registered in two files** (`bookEffects.ts` here, `arcEffects.ts` in Wave 4) ⇒ **double-fire**, two homes for one concept. | Every arc write invalidates twice; the next agent edits the wrong file. | Plan 30 **§8.0b**: Wave 2 **creates** `arcEffects.ts` with **one** broad `/^composition_arc_/`; Wave 4 **extends its body**. The S8 test asserts `matchEffectHandlers(...)` returns **exactly 1**. |
| **The effect handler silently no-ops live** while its unit test is green — because the live stream nests the payload in `{ok, result}` (and it may be a JSON **string**). | The agent writes; the open inspector shows the stale row; the user's next save 412s. **Two handlers already shipped this bug.** | `unwrapToolResult` (the shared fix) + an S8 test that feeds the **envelope**, not the unwrapped payload. And the live smoke, step 5. |
| The Book-Package track **re-opens and collides on `PlanDrawer.tsx`**. | A merge conflict, or a lost `bookId` prop. | **AI-4** makes it a **deletion + a one-line mount** (~55 out, ~6 in, **no moved symbols**) — it reverts cleanly. **Announce before editing; enumerate files on commit; never `git add -A`.** Pre-flight **G6** checks it first. |
| An **archived** arc renders `0` chapters instead of `—`, because the panel gated on falsiness. | A user sees "0 chapters" for an arc that has 18. | LA-2: **gate on `is_archived`, never on falsiness.** W2-S5 has the test **and its inverse** (a LIVE arc with 0 chapters must show `0`, not `—`). |
| **Shipping a beautiful editor for a field nothing reads** (the motif-packer-lens class). | A green suite, a happy user, and a prompt that never changed. | DoD #9 asserts the **prompt changes — twice** (`tracks` AND `roster_bindings`). And the UI copy **never dresses `roster`/`summary` as generation knobs**, because they are not. |
| A future agent adds an LLM button here and invents `/actions/arc_suggest/estimate`. | A **fourth** route that 404s in production. | §5 names the **three that already do** (plan 30 §3.3); W2-S6 **machine-checks** it (no arc descriptor in `_ALL_DESCRIPTORS`; no `/estimate` URL in the api module); `D-ARC-SUGGEST-BUTTON` sends the button to Wave 4 **with its backend**. |
| 🔴 **The builder "helpfully" invents `GET /books/{id}/my-access`** because an earlier draft of this plan told them to. | A whole Go slice, six tests, and a **second** grant reader — for a field **already on the wire**. | §0.1 **LA-1**: `access_level` ships on `GET /v1/books/{id}` today (`server.go:957/:987`) and the FE simply **dropped it**. **Pre-flight G8 checks this before you type.** **There is no Go work in this wave.** |
| 🔴 **The builder "leaves the repo branch alone" in BE-A2** (as the first draft said), because "both doors now require If-Match, so `expected_version=None` is unreachable". | `arc_apply` keeps producing rows whose **version lies about their content** — and the next OCC holder overwrites it with a stale `If-Match` **and gets a 200**. The hazard BE-A2 exists to kill, still live. | **G3 proves the third caller exists** (`arc_apply.py:497`). W2-S2 **moves the bump out of the branch** and **pins it with an integration test** (`test_blind_repo_write_still_bumps_the_version`) so the "unreachable, remove it" inference reds instead of shipping. |
| 🔴 **The cascade is re-derived in TypeScript** (the first draft's `splitCascade`) — and W2-S3b **changes `_merge_by`'s shadow rule in the same wave.** | The FE's copy of the merge rule is **wrong on the day it ships** (blank/whitespace keys), and a user's plot track silently forks from its saga. | **W2-S1b's `resolve_provenance` sidecar is the ONE source.** The FE **never** merges, **never** diffs key-sets, **never** walks ancestors — asserted by a grep-guard test. |
| **A `null` derived metric renders as `0`** (or a `0` renders as `—`). | *"0 chapters"* on an archived arc that has 18 — or *"—"* on a live, genuinely empty arc. | The **single** `fmtMetric` (`v == null ? '—' : String(v)`), the **banned** falsy idioms, and **the test AND ITS INVERSE** (W2-S5). |

---

## 11 · 🔴 The homeless legacy sub-tabs — what Wave 2 does **and does NOT** home

The **GG-4 retirement gate** deletes any legacy sub-tab that no wave gives a home. A `LEGACY_SUBTAB_HOME`
map claims which panel replaces which tab — and **a wrong row makes the machine-checked gate go GREEN on a
feature being deleted.** Two of those rows point at *this wave's* territory and are **WRONG**. Wave 2's job
here is to **refuse the false credit** and say where each one actually belongs.

### 11.1 `arc` → 🔴 **NOT HOMED BY WAVE 2. `arc-inspector` IS A DIFFERENT THING.**

`wave-6`'s map (`:1457`) says `arc: 'arc-templates'`. **Wrong.** And the tempting "fix" — repointing it at
this wave's `arc-inspector` — **is also wrong.** Three distinct concepts, one overloaded word:

| Thing | What it actually is | Owner |
|---|---|---|
| **`arc-inspector`** *(this wave)* | **G-ARC-SPEC-CRUD** — the narrative-arc **SPEC tree** (`structure_node`: saga → arc → sub-arc) over composition-service. Title/goal/tracks/roster/span. **The structure that steers generation.** | **Wave 2** |
| **`arc-templates`** | the structure-**TEMPLATE** library + 拆文 deconstruct (`arc_template` rows). | Wave 4 |
| **`arc` (CharacterArcView)** — *the homeless one* | **ONE CHARACTER's events** in `event_order` on a compact arc, **spoiler-cut at the current chapter**, with an active→gone state band and the 1-hop `ArcRelationsStrip`. It reads the **knowledge graph**, not `structure_node`. Launched with a character preselected from the **Cast codex** (`arcEntityId` is lifted into `CompositionPanel` for exactly that hand-off — **and dies with it**). | 🔴 **NOBODY** |

**Actions (neither is a Wave-2 code change):**
- **(a)** In `wave-6`'s `LEGACY_SUBTAB_HOME`, the `arc` row must **not** resolve to `arc-templates` **or** to
  `arc-inspector`. It is a **character** arc over the KG. **Leaving it pointed at either makes the gate go
  green on a deleted feature.**
- **(b)** `character-arc` belongs in **Wave 8**, beside `cast` — same knowledge-service data, same deep-link
  pair. Leaf-reuse `CharacterArcView`; `entityId` arrives via `params` so `cast` can
  `host.openPanel('character-arc', { entityId })`. **Today that hand-off is `onViewArc`/`setArcEntityId`
  inside `CompositionPanel` and it dies with it.**

### 11.2 `cast` → **Wave 8** (defensible in Wave 2 only if the PO says so — but it must land *somewhere*)

`CastCodexPanel` = the book's cast **grouped by kind**, searchable, each row showing its **spoiler-safe
current story-state** (knowledge entities ⋈ `EntityStatusEntry`). ⚠ The studio's `kg-entities` panel is
**NOT** this — it is a thin wrapper over a **flat, cross-project entity LIST** with no kind-grouping and **no
story-state join**. `cast` is the deep-link **target** of the flywheel's entity chips, the world-map, and the
Cast→Arc launcher. **Wave 8 owns the KG panels and is already editing those files.** If the PO instead wants
it here (because of the arc deep-link), that is defensible — **but silence homes it nowhere and GG-4 deletes it.**

### 11.3 The rest — **not Wave 2's, recorded so the map is not silently wrong**

`compose` (**ComposeView** — and it carries the **only** `useAdaptFromSource` affordance in the product) and
`assemble` (**ChapterAssembleView** — the **second** producer of `useCorrection` human-gate captures, which
spec 30's G-CORRECTION-FLYWHEEL row understates) → **Wave 6**, as **leaf** mounts.
`canonview` (**CanonAtChapterPanel** — a read-only canon **snapshot** at a chapter boundary; **not**
`quality-canon` = issues, **not** `quality-canon-rules` = rule authoring) → **Wave 6's DivergencePanel**
(its branch-point mount is load-bearing: *if M3's wizard port silently drops it, the writer branches BLIND*)
**+** a section inside the existing `scene-inspector`.
`worldmap` (**WorldMap** — the place-graph **VIEW**: backdrop image + spatial arrangement persisted in
`work.settings.world_map`) → 🔴 **a CIRCULAR DEFER: spec 38 sends it to "plan 30's Wave 6", and Wave 6 does
not contain it.** Wave 8 ports only the *write capability*. **It has no home. Someone must pick one.**
`flywheel` (**FlywheelPanel** — knowledge-graph **growth**, `knowledgeApi.getFlywheel`) → 🔴 **wave-6's map
false-homes it to `quality-corrections`** (= `CorrectionStatsTable`, composition correction **rates**). **Two
services, two datasets.** **Wave 1's own plan already says so in writing** (*"the name collides; the thing
does not"*). → **Wave 8** (`canon-growth`).

---

## 12 · Fold-in ledger — where each adjudicated decision landed

> Traceability for `/review-impl` and for the next agent. **47 rows in the register · 44 DECIDED.**
> **6 CONTRADICTIONS found — in every case the register won and this plan was changed.**

| Decision | Landed in | Was the plan already right? |
|---|---|---|
| `Q-32-403-READONLY-GRANT-SOURCE` | §0.1 LA-1 · G8 · **W2-S0 DELETED** · S5.3 `useBookGrant` | 🔴 **CONTRADICTED** — the plan invented a Go route for a field already on the wire |
| `Q-32-BE-A2-IFMATCH-428` | G3 · **W2-S2** (bump moved out of the OCC branch) | 🔴 **CONTRADICTED** — *"leave the repo branch"* left `arc_apply` writing version-lying rows |
| `Q-32-AI2-CASCADE-OWN-VS-INHERITED` | **W2-S1b** (`resolve_provenance`) · S5 (`splitCascade` **deleted**) · S6.4 (**Revert to inherited**) | 🔴 **CONTRADICTED** — the plan re-merged the cascade in TypeScript |
| `Q-32-ARCHIVED-NULL-NOT-ZERO` | §0.1 LA-2 · **W2-S1 edit 4** (list `empty` → all-null) · S5 `fmtMetric` | 🔴 **CONTRADICTED** — LA-2 said "do not touch the list route"; it was fabricating a `0` |
| `Q-32-OQ2-TRACKS-ROSTER-SCHEMA` + `Q-32-AI3-KEY-VALIDATION` | **W2-S3b** (new slice) · §9.0 (row **deleted**) | 🔴 **CONTRADICTED** — deferred; the models already existed and the audit is clean |
| `Q-32-X2-CATEGORY-ORDER` | **W2-S4 step 4b** | 🔴 **CONTRADICTED** — *"not ours to fix here"*; it is a one-line fix-now |
| `Q-32-OQ3-DELETE-BLAST-RADIUS-COUNT` | **W2-S1b** (`archived_ids`/`archived_count`) · §9.0 | row deleted — the "2nd consumer" trigger was already met (the MCP tool) |
| `Q-32-OQ4-FIND-REFERENCES-STALE-COPY` | **W2-S9 (1b)** · §9.0 | row deleted — fix the lie now; keep the emptiness |
| `Q-32-OQ5-STATUS-DERIVED` | **W2-S6 (4b)** + the regression guard · §9.0 | row deleted — CLOSED, hand-set forever |
| `Q-32-OQ8-ARCHIVE-STRANDS-CHAPTERS` | **W2-S6 (6/7)** copy · **W2-S1b test #7** · §9.0 | row deleted — gate #5, **pinned by a test** |
| `Q-32-BE-A3-UNASSIGN` + `-FASTMCP-3-SCHEMAS` | **W2-S3** (**no default**; the 3-schema warning corrected) | plan had the shape; **`= None` was the footgun** |
| `Q-32-BUS-SLICE-ARC` + `Q-32-UNIFORM-404` | **W2-S4 (9/9b)** (`arcId: string \| null`) · S5 (`gone`) | plan used a `''` magic-string sentinel |
| `Q-32-X6-RESOURCE-REF-UNWRITTEN` | **W2-S4b** (new slice) | **absent** — the agent had no way to point at an arc |
| `Q-32-NONCONTIGUOUS-WARN-ONLY` | **W2-S1 edit 5** (`gap_count`) · S5 chip · **S7 warn-only test** | plan derived gaps **client-side** over a paged window |
| `Q-32-CHAPTERS-VIRTUALIZATION` | **W2-S7** (`useArcChapters`, unconditional) | plan had a "~200 rows" branch |
| `Q-32-SPAN-REPO-TRAP` | **W2-S1 edit 6** · tests #4/#6 (the always-runs source-pin) | the DoD's "pacing pin" was **already satisfied and caught nothing** |
| `Q-32-ARCEFFECTS-ONE-HOME` + `-ARC-QUERY-KEY-DRIFT` | **W2-S8** (read-exclusion; **no `unwrapToolResult`**) · `D-ARC-CONFIRM-EFFECT` | plan imported an unused symbol; the confirm_action edge was undocumented |
| `Q-32-OQ7-SUMMARY-ROSTER-NO-PACKER` | **W2-S5** `fieldClasses.ts` · **S10 anti-drift test** | copy was right; **the ONE HOME + guard test were missing** |
| `Q-32-DOD5-TWO-PROMPT-PROOFS` | **W2-S10** (3 proofs + FE guard; `:652` cite fixed) | plan said "two proofs"; one **already exists**, and `roster`'s negative was missing |
| `Q-32-DOD-GREP-GATES` | **DoD #6/#7** (`rg -nF`; **by exported fn**; `updateArc` not `patchArc`) | the plan's greps **error under ripgrep** and can never match `create` |
| `Q-32-DOD6-BOOKKEEPING` | **W2-S10** (strike-through **in place**; 3 plan-30 edits) | plan named a **"Recently cleared" section that does not exist** |
| `Q-32-X12-AMEND-PLAN30` + `Q-32-MOTIF-EDITOR-BYID` | **W2-S10 (d)** — the **real predicate**; `motif-editor`/`workflow-editor` struck | plan had a 3-line annotation, not the rewrite |
| `Q-32-LIVE-BROWSER-SMOKE` | **W2-S10** (`arc-inspector.spec.ts`, 9 legs, literal DoD wording) | filename/testids drifted; no "infra unavailable" escape |
| `Q-32-CREATE-BODY-NO-TRACKS` · `Q-32-KIND-CLOSED-SET-TWO` · `Q-32-STRUCTURE-CONSTRAINT-VERBATIM` | **W2-S6 (5)** + tests | 🔴 the **`err.code` branch is silently dead** — the plan would have shipped it |
| `Q-32-OCC-SERIALIZE-WRITE-CHAIN` | **W2-S6 (1/2)** (`.then(run,run)`; no re-GET; `!dirty` gate) | plan had the shape, not the traps |
| `Q-32-EMPTY-STATE-DECOMPILER-CTA` · `Q-32-PLANDRAWER-TEMPLATE-UUID` · `Q-32-NO-COST-GATE` · `Q-32-OQ1-ARC-SUGGEST` | **W2-S5 / S6** | plan was vague; the register made each **machine-checked** |
| `Q-32-PLANDRAWER-BOOKID-PROP` · `Q-32-AI4-PLANDRAWER-EMBED` · `Q-32-ARCLISTNODE-WIDENING` | **W2-S9** + the 4 fixtures + `tsc --noEmit` | plan passed `canEdit={!!writes}`; **`writes` presence is not a grant** |
| `Q-32-INVERSE-GAP-ARC-APPLY` | §9.1 `D-ARC-APPLY-MCP-WRAPPER` | ✅ confirmed — **plus** the Wave-4 correction (the engine **exists**; BE-8 is an adapter) |
| `Q-32-WAVE1-ORDERING-DEP` · `Q-32-DRIFT-LOCK-COUNT-CONTRADICTION` · `Q-32-REGISTRATION-CHECKLIST-GG8` · `Q-32-AI1-ADDRESSING` · `Q-32-BE-A1-*` | §4 · W2-S1 · W2-S4 | ✅ the plan was **already right** — hardened with the "no literal count" rule and the reconciler's **two** edits |
| `Q-32-UI-SHOW-PANEL-X5` | *(Wave 0's — not ours)* | PO-3 SEALED: **RETIRE** `ui_show_panel`. Do not re-open. |

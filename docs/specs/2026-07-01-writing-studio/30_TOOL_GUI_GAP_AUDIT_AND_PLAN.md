# 30 · Tool↔GUI Gap — Audit & Master Plan

> **Status:** ✅ AUDIT COMPLETE · PLAN **PO-APPROVED** 2026-07-12 — the 4 blocking decisions are SEALED (§0). Now in SPEC+DRAFT phase (specs 31–38 + HTML drafts) before any implementation plan.
> **Type:** FS. Umbrella plan for a multi-session, multi-wave build. Not itself a build spec — it is the **contract** the per-wave specs (31…38) are written against.
> **Audited at:** HEAD `9262ed53e`, branch `feat/context-budget-law`, 2026-07-12.
> **Scope of the audit:** every MCP tool (8 services + the 12 frontend tools), every composition-service REST route, every composition-service table, every Writing-Studio panel, every spec in `docs/specs/2026-07-01-writing-studio/` (00–29).
> **Decision prefix:** **GG-\*** (gap-governance). Gap IDs are **G-\***, cross-cutting fixes **X-\***.

---

## 0 · PO decisions — **SEALED 2026-07-12**

Four decisions blocked this plan. All four are now made. **Do not re-litigate them from memory —
re-read this section.** Each overrides a prior sealed decision *by name*, so the override is recorded
here rather than left as an inconsistency for a later agent to "fix" back.

| # | Decision | Consequence |
|---|---|---|
| **PO-1** | **AMEND spec 28's AN-12** — the "No new GUI surface" clause is **lifted** for `composition_diagnostics` / `composition_package_tree` / `composition_find_references`. | **Wave 7 proceeds.** AN-12's *architecture* is honoured exactly: wire the **existing** `StudioBottomPanel` Issues tab (a stub string since day one), and make `find_references` a **right-click lens on an entity badge** — **no new dock panel**, so the DOCK-2/DOCK-8 fork AN-12 was actually protecting against still cannot happen. Only the "zero GUI" clause changes. **Rationale on record:** AN-12's premise was *"the human equivalents already exist"*; the audit found **~2.5 of 5** diagnostic sources have **no** human surface and **none** is ranked — the premise was false. The amendment must be written **into `28_agent_native_studio.md`** (do not fork it), citing this row. |
| **PO-2** | **G-WORKFLOWS is DROPPED from this plan — Track C owns it** (its P-5 explicitly claims *"workflow rack, binding UI"*). | **Wave 8 loses 8c.** Wave 8 = KG write holes + world maps only, and is renamed accordingly. The gap stays in the register marked **OWNED-BY-TRACK-C** so it is not re-raised as a hole. ⚠ The underlying defect remains real and is **Track C's to close**: `registry_propose_workflow`'s own description says the user approves *"in the UI"* and there is no UI, so an agent calling it today writes a row **no human can ever approve**. Hand this paragraph to Track C. |
| **PO-3** | **RETIRE `ui_show_panel`** — fold it into `ui_open_studio_panel` (one name for one concept). | **X-5 becomes a retirement, not an enum-add.** ⚠ This is a **cross-surface** change, not a delete: `ui_show_panel` is also used **outside** the studio, so retirement must (a) keep the non-studio call sites working — migrate them to `ui_open_studio_panel` + the existing studio interceptor, or give them an explicit non-studio path — and (b) land with the contract test green (`py enum == contract enum == openable`). `ui_watch_job` is **separately** fixed: add it to `STUDIO_UI_TOOLS` + the interceptor → open `job-detail` (today it route-navigates and **tears down the dock**). |
| **PO-4** | **Write ALL detail specs (31–38) + ALL HTML drafts FIRST.** No implementation this phase. | The build is planned **as one piece, with full information**, once every spec and draft is on disk. This *strengthens* GG-6 (spec+draft before plan) from a per-wave gate to a **whole-plan gate**. |

---

## 1 · Purpose & the law it enforces

**GG-1 — THE LAW.**

> **Every backend capability a user owns must have a human surface.**
> The agent is an **accelerant on the user's own capabilities — never the only door to them.**

A capability the user owns (their book, their glossary, their plan, their motifs, their canon rules)
that can be exercised **only** by asking an LLM to call a tool by name is not a feature — it is a
**tenancy defect with a chat window in front of it**. It fails on four axes at once:

| Failure | Why it is not acceptable |
|---|---|
| **Determinism** | A GUI button always works. A tool call works if the model finds the tool, guesses the args, and doesn't hallucinate success. |
| **Cost** | Reading your own arc costs $0 through a panel and a paid turn through the agent. |
| **Discoverability** | A user cannot use a capability whose existence is only discoverable by an LLM's tool-search. |
| **Honesty** | `registry_propose_workflow`'s own description tells the model *"the user must approve it in the UI"* — and that UI **does not exist**. That is the repo's own `silent-success-is-a-bug` class, shipped. |

**GG-2 — the inverse law also holds.** A GUI whose domain has *no* agent tools is also a defect
(the agent cannot help with it). The wiki is the live example: `wiki` + `wiki-editor` panels exist,
and glossary-service registers **zero `wiki_*` MCP tools**. Both halves of the loop are in scope for
this plan's register, even though the user's stated goal is the GUI half.

**GG-3 — LEGACY-ONLY ≠ UNBUILT, and this reframes the whole plan.** There are **two docks** in this
repo:

| Dock | Entry | Status |
|---|---|---|
| **Writing Studio** | `frontend/src/features/studio/panels/catalog.ts` → `StudioDock` (dockview) | the product surface |
| **Legacy composition workspace** | `frontend/src/pages/ChapterEditorPage.tsx` → `frontend/src/features/composition/components/CompositionPanel.tsx` (918 LOC, **25 sub-tabs**, 0 ported verbatim) | the pre-Studio page, still routed at `/books/:bookId/chapters/:chapterId/edit` (`App.tsx:134`) |

**10 of composition's 31 tables are LEGACY-ONLY** — a full, tested, feature-rich GUI already exists
for them (`features/composition/motif/**` alone is ~15 components + ~25 test files) and it is
reachable **only** from a page spec 16 has a user-approved decision to RETIRE. For those gaps the
work is a **PORT** (component → dock panel + catalog/enum/contract/i18n registration), **not a build**.

**GG-4 — therefore: do NOT retire `ChapterEditorPage` before the ports land.** Retiring it today
**deletes shipped features** (style/voice, references, motif library, arc templates, divergence,
progress, correction capture, polish/self-heal). Spec 16's M1 is **blocked by this plan**, not the
other way round. This is recorded as a hard sequencing constraint (§9).

---

## 2 · Method — how this audit was done

Three phases, in order. Nothing below was taken from a doc, a checkbox, or a handoff note.

**Phase 1 — INVENTORY (8 parallel sweeps, each read source, not docs).**

| Sweep | Source of truth actually read |
|---|---|
| composition MCP tools | `services/composition-service/app/mcp/server.py` (4,777 lines, read in full) |
| composition REST routes | **FastAPI app introspection** (`app.main:app.routes`) — *not* a decorator grep. This matters: `authoring_runs.py` registers 4 routes via `router.add_api_route(...)`, which a `@router.` grep MISSES. |
| composition data model | `services/composition-service/app/db/migrate.py` (1,754 lines; no alembic — one idempotent forward-only DDL) + all 29 repos |
| Studio panels | `frontend/src/features/studio/panels/catalog.ts` + every panel file |
| agent↔GUI bridge | `services/chat-service/app/services/frontend_tools.py`, `contracts/frontend-tools.contract.json`, `frontend/src/features/studio/agent/**` |
| other services' MCP | every `@mcp_server.tool` / `addTool(srv,…)` / `&mcp.Tool{Name:…}` registration across `services/` |
| design drafts | all 13 HTML files in `design-drafts/screens/studio/` |
| handoff / deferred | `docs/sessions/SESSION_HANDOFF.md` (3,485 lines), `docs/deferred/DEFERRED.md`, `00C_POST_ARCHITECTURE_QUEUE.md`, 3 live RUN-STATE files, `git worktree list` |

**Phase 2 — JOIN.** Tools × routes × tables × panels, on the resource. A capability is **GUI-covered**
only if a panel registered in `catalog.ts` (or a component it transitively renders) surfaces it.
A REST route is **NO-FE-CONSUMER** only if a repo-wide grep of `frontend/src` for its path finds nothing.

**Phase 3 — ADVERSARIAL VERIFY.** Every candidate gap was handed to a fresh agent whose *job was to
refute it*, with four explicit escape hatches: (1) a studio panel already surfaces it; (2) a non-studio
route/page surfaces it; (3) the tool is deprecated/internal-only; (4) another track already built it or
is building it (`git log --oneline -80` + the three RUN-STATE files). A gap is **CONFIRMED** only where
all four refutations failed. **4 of 22 came back PARTIAL** (the Studio-level claim held; the framing was
wrong) and are recorded with their corrections. Every refuted sub-claim is in **Appendix A (§10)** so it
is never re-raised.

**Phase 4 — COMPLETENESS CRITIC.** A final pass hunted for what the 22 gaps *missed*: orphan routes in
no gap, whole services never inventoried, missing CRUD verbs *inside* the gaps, cross-cutting
infrastructure nobody planned, and spec promises in no gap. It found **26 additional items**, 3 of
which are 🔴 landmines on the critical path of the whole batch (§8).

**Where this audit is uncertain, it says UNVERIFIED. It does not guess.**

---

## 3 · The numbers

### 3.1 Roll-up

| Surface | Total | Covered | Gap |
|---|---:|---:|---:|
| **composition-service MCP tools** | **75** | 58 | **17 AGENT-ONLY** (9 with no surface at all · 3 agent-native reads · 5+ REST-exists-but-no-FE) |
| **composition-service REST routes** | **155** (147 public · 9 internal · 3 infra) | ~104 | **~22 public NO-FE-CONSUMER** + **3 FE calls with NO backend route (404 at runtime)** |
| **composition-service tables** | **31** | 10 GUI-covered · 4 partial | **10 LEGACY-ONLY · 2 WRITE-ONLY** · 5 legitimately BE-only. ⚠ **`composition_daily_progress` is NOT one of the write-only two** — that claim is **REFUTED** (§10; §3.2): it has a mounted, reachable reader on the legacy page. The genuine write-only case in this batch is **`motif_application`** (X-7 / spec 21-G1: `pack()` never reads it). |
| **MCP tools, other services** | **173** *(⚠ see 3.4 — the real total is ≥189)* | 150 | **23 with no GUI** |
| **Studio panels** | **68** catalog rows | 57 palette-openable · 11 hidden singletons | agent enum **57 == 57** openable, **zero drift** |
| **Frontend tools (chat-service)** | **12** | 12 (contract-tested) | 2 defective (§8 X-5) |

### 3.2 The 22 verified gaps, by domain

| Domain | Gaps | Headline |
|---|---:|---|
| composition / motif | 4 | The entire narrative-craft layer (套路/爽点/打脸) is stranded on the legacy page. Biggest body of built-but-unreachable UI in the product. |
| composition / plan+arc | 5 | The SPEC tree that steers **all** generation is read-and-rearrange-only for humans, full-CRUD for the agent. |
| composition / quality | 4 | The Studio *judges* you against canon rules and gives you no way to write one. The correction flywheel is dark for every Studio user. |
| composition / editor-craft | 4 | Style, voice, references, progress — all legacy-only. ⚠ **CORRECTED 2026-07-13:** this said progress is *"**write-only**"*. **It is not.** The legacy page has a **full progress tab reading a real, shipped GET route** (`ProgressPanel.tsx`, mounted + reachable in the legacy dock — which also does the writes). The true gap is **narrower and precise: the *Studio* has no progress panel**, so a Studio user's word-count snapshots are written and never *shown to them*. It **becomes** genuinely write-only the moment 00C Q-6 retires the legacy page — which is exactly why §5's `G-PROGRESS` is marked **PARTIAL**, not CONFIRMED. §3 and §5 now agree. |
| studio / platform | 1 | 4 cross-cutting defects that would corrupt every new panel we ship. |
| knowledge / book / registry | 4 | A whole CRUD domain (world maps) reachable only by an agent; workflows the agent can propose and no human can approve. |

### 3.3 **THREE** FE calls that 404 in production today — **plus a FOURTH defect that is a 500, NOT a 404**

> 🔴🔴 **MECHANISM CORRECTED 2026-07-13 — READ THIS BEFORE YOU BUILD ANYTHING.** This section previously
> claimed a **fourth 404** (*"the motif-MINE poll 404s; the user pays for the LLM run and watches a
> spinner forever"*). **Every load-bearing clause of that was wrong** — and it prescribed a cure that
> would have **shipped GREEN over a still-broken path.** The Wave-0 adversarial QC and an independent
> live repro inside the container agree on the real trace:
>
> 1. `_execute_motif_mine` (`actions.py:644`) enqueues with **`project_id=None`** — a corpus/book mine is
>    genuinely not Work-bound. Same at `_execute_arc_import` (`:694`) ⇒ 拆文.
> 2. `_enqueue_motif_job` (`:552`) stamps a **synthetic `uuid4()`** to satisfy `NOT NULL`.
> 3. 🔴 **`GenerationJobsRepo.create()` (`generation_jobs.py:159-173`) is NOT a plain INSERT.**
>    `generation_job.book_id` is **also `NOT NULL`** (`migrate.py:269`) and the statement **derives it**:
>    `INSERT INTO generation_job … SELECT $1, $2, w.book_id, … FROM composition_work w WHERE w.project_id = $2`.
>    The synthetic id matches **ZERO rows** ⇒ zero rows inserted ⇒ `:198-206` raises
>    **`ReferenceViolationError("project … has no composition_work row")`**.
> 4. `actions.py` has **no `except ReferenceViolationError`** (grep: **0 hits**) ⇒ it escapes to the global
>    `@app.exception_handler(Exception)` (`main.py:200`) ⇒ **HTTP 500** — *after* `_claim_or_replay`
>    (`:504`) **burnt the confirm token** (a retry gets **409 `already_consumed`**).
>
> **⇒ It is a 500 at `POST /actions/confirm`, BEFORE the enqueue. The `generation_job` row is NEVER
> CREATED. The poll is NEVER REACHED** — "the poll 404s" describes a code path that never executes.
>
> **⇒ NO USER WAS EVER CHARGED.** No Redis XADD, no worker pickup, **no LLM call, no recorded spend.**
> `_precheck_or_402` (`:517`) does reserve a billing **hold** — a pre-authorization, *not* a charge — and
> the token is burnt; both are real defects. But *"the user pays for the LLM run and watches a spinner
> forever"* is **WRONG, in the user's favour**, and is **RETRACTED**. Do not re-introduce it.
>
> ✅ `_execute_conformance_run` (`:723`) passes a **real** `project_id` ⇒ **conformance is unaffected.**
> This is a **mine / arc-import-only** defect.
>
> *(§10's REFUTED row "`composition_motif_mine` has no FE reach" is still right that propose→confirm ships
> with a passing test — the test mocks the transport. It just never reaches a real confirm.)*

#### ⚠ Why the OBVIOUS fix is WRONG — name the bug class so it is not re-made

The old text (and `34`'s BE-7c row) prescribed **"an owner-scoped job read
(`GET /v1/composition/motif-jobs/{job_id}`, gate on `created_by`), size XS, built in Wave 3 (3a)"** as
*the* cure, promising it *"unbreaks mine, arc-import and the deep-conformance job in one route."*

🔴 **It does not. An owner-scoped read route CANNOT FIX THIS — it would be a route that reads a row that
does not exist.**

And it would **SHIP GREEN.** Its integration test would seed the `generation_job` row with a raw
`INSERT`, the route would read it back correctly, every assertion would pass — and ⛏ Mine / 拆文 would
**still 500 at confirm**, because nothing on the test's path ever went through the **producer**. That is
this repo's own **`fixtures-can-seed-a-field-the-writer-never-sets`** bug class, about to be committed
**on purpose**.

**The real cure is the whole Work-less job LANE** — seven legs, not one:
**(a)** DDL — `generation_job.project_id`/`.book_id` `DROP NOT NULL` + a **both-or-neither shape CHECK** +
a partial owner index · **(b)** a new **`create_unbound()`** (a plain INSERT, no `FROM composition_work`;
**do NOT touch `create()`** — the hot path for every draft) · **(c)** `GenerationJob.project_id`/`.book_id`
→ `UUID | None` · **(d)** 🔴 **`_enqueue_motif_job` — DELETE the `uuid4()` synthetic pid**, branch to
`create_unbound()` *(the only leg that actually stops the 500)* · **(e)** the owner-scoped read route ·
**(f)** `composition_get_mine_job` — drop the un-knowable `project_id` arg · **(g)** tests **forced
through the producer** (`POST /actions/confirm` → assert the row exists → read it back).

⇒ 🔴 **THE CANONICAL FIX IS [`W0-BE1`](../../plans/2026-07-13-studio-wave-0-foundations.md), AND THE
WAVE-0 PLAN ALREADY CARRIES IT IN FULL** (its Files table (a)–(g); build detail written once, verbatim,
in [`wave-3-motif`](../../plans/2026-07-13-studio-wave-3-motif.md) slice `3a-1`). It was **pulled forward
into Wave 0** — out of Wave 3a — because the defect fires **today**, on the live legacy page. **Build
from the Wave-0 plan: do not re-derive it, do not fork a second DDL, and do not "fix" it with a read
route.** ⚠ **It is NOT "XS"** — a DDL change + a new repo method + a model change + a writer change + a
route + an MCP arg is an **S/M with a schema side effect.**
See [`33_motif_studio.md`](33_motif_studio.md) §1.2 and [`34`](34_arc_templates_and_deconstruct.md) §0.1.

---

**The three genuine 404s** (below) are a **different, unrelated bug**: FE-invented URLs that were never
written on the backend. They are fixed by `W0-S7` (delete the invented paths; use the generic spine).

The gateway is a **pure path-preserving proxy** (`services/api-gateway-bff/src/gateway-setup.ts:354`,
`pathFilter: (p) => p.startsWith('/v1/composition')`, **no rewrite**) — so an FE path with no BE route
404s and nothing saves it.

| FE call | Live caller | Backend |
|---|---|---|
| `POST /v1/composition/actions/conformance_run/estimate` | `motif/api.ts:224` ← `useConformanceTrace.ts:32` | **MISSING** — `actions.py` has only `GET /actions/preview` + `POST /actions/confirm` |
| `POST /v1/composition/actions/conformance_run/confirm` | `motif/api.ts:230` ← `useConformanceTrace.ts:36` | **MISSING** (same) |
| `POST /v1/composition/works/{pid}/scenes/{nid}/regenerate-to-beat` | `motif/api.ts:301` ← `ConformanceTraceView.tsx:69`'s per-scene **Regenerate** button | **MISSING** — `regenerate-to-beat` appears **nowhere** in `services/**/*.py` (re-verified 2026-07-13: `grep -rn regenerate-to-beat services/ --include=*.py` → **0 hits**) |

Every Regenerate click issues a request to a route that was never written. Folded into
**G-CONFORMANCE-TRACE** (§5) and fixed by **`W0-S7`**.

🔴 **All three are fixed by DELETING FE code, not by writing BE routes.** The first two: delete the
hand-rolled per-action paths and mirror the sibling that already does it right
(`arcConformanceRunPropose` → `mcpExecute('composition_conformance_run')` → `POST /actions/confirm`).
The third: **delete `motifApi.regenerateToBeat`** and re-point the button at the **already-existing**
`POST /v1/composition/works/{pid}/generate` (`engine.py:328`) — see **BE-5 (§6): DO NOT BUILD —
REFUTED**, and spec [`33`](33_motif_studio.md) §5.1. **Do not "fix" any of the three by inventing the
route the FE asked for** — that would mint per-action routes for a Tier-W op, the §8.1 violation these
404s already are.

### 3.4 ⚠ Known holes in the numbers (UNVERIFIED)

Stated honestly rather than rounded away:

- **`provider-registry-service`'s 14 MCP tools were never counted** (`internal/api/mcp_server.go:59-141`
  — the `settings_*` cluster + `mcp_web_search_tool.go:70` `web_search`). Spot-check says the
  `settings_*` cluster *looks* GUI-covered by `features/settings/DefaultModelsCard.tsx` /
  `EditModelModal.tsx`, but **that was luck, not audit**.
  > 🔴 **RETRACTED 2026-07-13 — a sub-claim here was WRONG, and it claimed an authority that does not
  > exist.** This bullet used to end: *"`web_search` is registered **UNPREFIXED** while glossary-service
  > registers `glossary_web_search` — the repo's own `external-system-mcp-must-be-namespaced` **law** says
  > an unprefixed federated tool **shadows**."* Both halves fail verification:
  > 1. **There is no such law.** `grep -ni namespac docs/standards/*.md` returns **no LOCKED rule
  >    governing federated MCP tool names** — the only hits are a *cache-key* namespace registry
  >    (`README.md:110`) and an industry aside about the **MCP Registry's** namespace-auth
  >    (`agent-extensibility.md:82`). `external-system-mcp-must-be-namespaced` is a **retro lesson**
  >    (ContextHub memory), **not** a repo standard, and it is about *user-registered external* servers,
  >    not first-party federation. Citing it as "the repo's own law" **overstates it**. What *does* exist
  >    is a real mechanism: **ai-gateway's C-GW prefix gate** (`services/ai-gateway/src/config/config.ts`
  >    `DEFAULT_PREFIX_MAP` / `EXTRA_PREFIX_MAP`), which silently **drops** a federated tool whose name
  >    matches none of its provider's prefixes. Cite *that*, by path — not a "law".
  > 2. **`web_search`'s unprefixed name is DELIBERATE, documented, and does not shadow anything.**
  >    `mcp_web_search_tool.go:3-18` states it: `web_search` is the **universal** web-research tool
  >    (Track D · WS-D0 / CD5); it lives on provider-registry because that is the **only** service
  >    allowed to make the outward provider call (**Provider-gateway invariant**). It **supersedes**
  >    `glossary_web_search`, which is **demoted in place** (`visibility: legacy`,
  >    `superseded_by: web_search`) — *not* shadowed. And the prefix gate is **accommodated, not
  >    violated**: `EXTRA_PREFIX_MAP` lists **`web_`** as provider-registry's second namespace
  >    (`config.ts:118-120`), precisely so the gate does not drop it.
  > ⇒ **There is no defect here. Nothing to fix, nothing to file.** The only real item in this bullet is
  > the **uncounted-tools** sweep (X-9), which stands.
- **`catalog-service`'s 2 MCP tools were never counted** (`catalog_list_public_books`,
  `catalog_get_book`). Plausibly covered by `books`/`leaderboard-*`, **unverified**.
- ⇒ the "173 tools / 23 NO-GUI" scoreboard is a **floor, not a total**. Real total ≥ **189**.
  **Closing these two sweeps is a Wave-0 task (X-9).**

---

## 4 · Completeness audit of specs 00–29

Method: **no spec checkbox or status line was trusted.** A promise is SHIPPED only where an
implementing file is named. A promise is MISSING only where a repo-wide grep returned nothing.

| Spec | Status | What is unshipped |
|---|---|---|
| **00** OVERVIEW | 🟡 PARTIAL (as spec) · ❌ **STALE (as index)** | D16 (open Rich/Raw/**Reader** per chapter — hard-coded to `editor`; no `lw_studio_default_editor` pref). D20 session-orchestrator FSM. D27–D30 hooks (0%). **The component index and Debt stack are stale and will mislead the next agent** (rows 02/03/04/07/08/09 read ⏳/📐 but are substantially built). |
| **01** skeleton | ✅ SHIPPED (frame) | **Bottom-panel content** — Jobs / Generation / **Issues** all render `t('bottomStub.…','Feed appears here once wired.')`. *(Note: the stub IS the spec — 01 says "frame real, content stub". Not a regression.)* **Top-bar Generate / Save / model controls** (Debt #2, never cleared; also blocks 06b's deferred palette commands). |
| **02** manuscript navigator | 🟡 PARTIAL | 🔴 **New-chapter `+` is permanently dead in the shipped app** — `ManuscriptNavigator.tsx:116` renders `disabled={!onNewChapter}` and `StudioFrame.tsx` **never passes `onNewChapter`**. Also: reveal-in-tree on jump; exact arc chapter-range badge; partial-outline merge; degenerate-level collapse. |
| **03** compose panel | ✅ BUILT — **spec never written** | Code shipped without a spec (`ComposePanel.tsx`). |
| **04 / 04b** editors | 🟡 PARTIAL | `lw_studio_default_editor` pref; M2 save-or-discard prompt (auto-saves instead); Rich↔Raw live-sync round trip; json-editor Validate/Copy/Open-Rich buttons. |
| **05** story-bible navigator | ❌ **MISSING (navigator half)** | Detail-panel half superseded by 13/14/15. The **sidebar navigator** is a stub: `StudioSideBar.tsx:73` renders a per-view stub for `activeView === 'bible'` **and `'search'`**. Two Activity-Bar views lead nowhere. |
| **06a / 06b** palettes | ✅ SHIPPED | 06a: multi-row-per-chapter, recents, arc-expand. 06b: recents group; the 3 deferred commands (blocked on 01 Debt #2). |
| **07 / 07a / 07b / 07c** agent chat | 🟡 PARTIAL | 🔴 **`consumer_capabilities` is a DEAD FIELD** (`chat-service/app/models.py:502` — declared, read by **nothing**). 🔴 **`contributeContext()` is a DEAD FIELD** (`studio/host/types.ts:31` — declared, **never called**). Rack pin limits; "Studio panels" group in the add-browser. |
| **07S** agent standard | 🟡 PARTIAL | 🔴 **No microcompact tier, no `hard_truncate`, no `compaction_failed` breaker** (0 grep hits) — while Agent Mode (§10 L3/L4 autonomous runs) **has shipped**, and §3/§10 make the breaker MANDATORY for headless runs. Also: §5c hunk-level accept/reject; §4 per-server-tool approval; §3b Anthropic overlay; §4 MCP resources+prompts; §8 memory-for-canon. |
| **08** state architecture | 🟡 PARTIAL | `StudioSessionOrchestrator` **completely absent**. S7: closing a dock tab does **not** prompt save-or-discard on a dirty hoist (no `onWillClose` guard). |
| **09** agent↔GUI reconciliation | 🟡 PARTIAL | G6 `consumer_capabilities` filter (dead, above). `ui_watch_job` neither a studio tool nor intercepted → **route-navigates out of the studio and unmounts the dock**. |
| **10** agent lifecycle hooks | ❌ **0% BUILT** | Zero grep hits for `HookOrchestrator`/`agent-hook-runner`/`agent_hook_bundles`/`preToolUse`/`postToolUse` across `services/`, `frontend/src`, `infra/`. A service, a table, an orchestrator, a sandbox, a manifest format, a settings UI — none started. **The single biggest unbuilt block in 00–11.** |
| **11** dockable migration | ✅ SHIPPED | — |
| **12** json document standard | 🟡 PARTIAL | The "MANDATORY" 6-point cycle gate is **not mechanically enforced**, and item 5 (a JSON document provider) was **silently skipped** by the KG and Translation cycles. Only 2 `registerJsonDocumentProvider` call sites exist repo-wide (manuscript-unit, glossary-entity). Wiki declined it *consciously*; KG and Translation never mention it. |
| **13** glossary panels | ✅ SHIPPED | 🔴 **Its own deferred row is still open: the `AddModelCta` DOCK-7 defect** — a raw `<Link to="/settings/providers">` with no `useOptionalStudioHost()` branch, **reachable from live dock panels**, tears down the entire dockview layout. **Highest-impact unshipped item in 12–20.** |
| **14a** kg panels | ✅ SHIPPED | (spec-12 gate item 5 never scoped) |
| **14b** utility panels | 🟡 PARTIAL | The promised live E2E for Jobs / Books / Leaderboard (7 panels) was never written. |
| **15a** chapter browser | 🟡 PARTIAL | The live browser E2E its own gate named **by name** ("don't repeat it here", citing the prior gap) — and repeated it. |
| **15b** wiki panels | ✅ SHIPPED | (no responsive-regression test — self-flagged) |
| **16** chapter-editor retirement | 🟡 PARTIAL — ⚠ **headline promise REVERSED** | `ChapterEditorPage.tsx` (70,183 bytes) is still mounted at `App.tsx:134`. M1 ("Studio becomes the **sole** chapter-editing surface") is not true of the code. **P1 left the `editorBridge` singleton in place BECAUSE the page was being retired — a premise Phase 4b cancelled and nobody revisited.** The only enforcement is an 18-line prose banner: no lint rule, no hygiene test, no route assertion. **⚠ Every LEGACY-ONLY gap in §5 lives on this page — retiring it without porting them DELETES features (GG-4).** |
| **17** translation/enrichment/sharing/settings docks | ✅ SHIPPED | — |
| **18** book open + palette grouping | ✅ SHIPPED | (the cleanest closure in the set — B6 wrote the mechanical assertion) |
| **19** onboarding + user guide | ✅ SHIPPED | Wave 2's "all 47 panels have a `guideBodyKey`" claim **has already eroded by one** (`agent-mode`, `catalog.ts:258`) — because B6's assertion guards `category`, not `guideBodyKey`. |
| **20** agent mode | ✅ SHIPPED (header stale) | No Lane-B effect handler for `composition_authoring_run_*` **and a now-FALSE comment** at `useStudioEffectReconciler.ts:10` asserting there can't be one. |
| **21** plan hub (v1) | 🗄 SUPERSEDED by 24 — **but G1/G2 remain owned here and are OPEN** | 🔴 **G1 — motif is WRITE-ONLY: `motif_application` is never fed into `pack()`.** `grep -rn "motif" services/composition-service/app/packer/*.py` → **ZERO hits**. The Hub now RENDERS motif chips and generation still never CONSUMES them. Needs a `gather_motifs` lens (mirror the shipped `gather_arc` at `app/packer/lenses.py:257`). **G2** — PlanForge `propose.py` has no `existing_state` input: proposing a plan for a book with 200 chapters ignores all of them. |
| **22** scene model | ✅ SHIPPED | D1 — no OpenAPI for the new book-service scene routes. |
| **23** book architecture | ✅ SHIPPED | **C3 `arc-inspector` panel does not exist** (DBT-06; also blocks 24-H3.1). D1 — no OpenAPI for `/v1/composition/arcs/*`. |
| **24** plan hub v2 | ✅ SHIPPED | **H8.2 — the LIVE BROWSER smoke, the named pillar-24 DoD.** No Playwright targets `plan-hub` anywhere; the RUN-STATE's smoke was curl/API. This is exactly the `agent-gui-loop-needs-live-browser-smoke` lesson. |
| **25** package migration | ✅ SHIPPED (both deploys live on dev) | T3/T4 named batteries are distributed, not one suite (grep first). |
| **26** structure↔prose indexing | ✅ SHIPPED (core + D1/D2/F) | **D3 arc decompiler NOT built** (`D-ARC-DECOMPILER-STRUCTURE-NODE`) — the only path to a spec tree for an imported book with no plan. |
| **27** planforge v2 compiler | 🟡 PARTIAL | **B1 — `contracts/plan-forge/planner_state.schema.json` STILL carries `"required":["PA","HA","CD","THR"]` + `additionalProperties:false`** (the exact F5 POC-fixture taint the spec was written to remove; the service-side severing landed, the contract side did not). `VariableDef.initial` absent from `novel_system_spec.schema.json`. **B2** — `plan_pass_artifacts.schema.json` does not exist. **F3 — no Pass Rail GUI** (→ G-PLANFORGE-PASS-RAIL). |
| **28** agent-native studio | ✅ SHIPPED | **AN-C2 — the discovery scent was never added.** `stream_service.py:3714-3726`'s `book_context_note` names ids only; `grep package_tree\|composition_diagnostics` → **0 hits**. The 3 agent-native tools shipped and **the model was never told they exist** (AN-11's own risk row calls that a FAIL). **AN-12 `resource_ref`** — sketched, homed, and declared a **HARD PREREQUISITE**: *"A Phase-4 build without AN-12 is a spec violation, not a shortcut."* |
| **29** translation repair | ❌ **MISSING — 0 of T1–T10** | The whole spec. T8: `TranslationTab.tsx:300-305` renders `<TranslateModal>` with **no `preselectedChapterIds`** though the prop exists and the sibling ExtractionWizard call site passes it → the coverage matrix silently drops the chapter selection. T5: the modal wedges forever on "Loading chapters…" (no `AbortController`, no timeout, no retry, `.catch(()=>null)`). T3/D13: `target_language` is a free string on the MCP tool — a closed-set⇒enum violation of the Frontend-Tool Contract. T9: no `my_grant_level` anywhere. **00C calls this Q-1: "None — unblocked now. Disjoint files from the whole 00B cluster" — the single cleanest un-colliding build available.** |

### 4.1 Doc-hygiene defects found (fix cheaply, they are actively misleading)

- ✅ **DONE (X-8 / `W0-S10`, 2026-07-13) — two spec 14s and two 15s were on disk.** Renumbered:
  `14_kg_panels` → **`14a_kg_panels`** · `14_utility_panels` → **`14b_utility_panels`** ·
  `15_wiki_panels` → **`15a_wiki_panels`** · `15_chapter_browser` → **`15b_chapter_browser`**.
  **The a/b mapping is NOT arbitrary — do not re-litigate it, in either direction.** Rule: **`a` = the
  spec that already owns that number's `00_OVERVIEW` row; `b` = the later add-on that collided.** Every
  bare-number prose reference on disk already means exactly that (`#14` = KG at `00_OVERVIEW.md:104`,
  `21_plan_hub.md:36`, `20_agent_mode.md:43`; **`#15` = WIKI** at `00_OVERVIEW.md:105` and
  `20_agent_mode.md:65` — *"same params-retargeting pattern as **wiki-editor, #15**"*). This mapping costs
  **zero prose rewrites**; the inverse would **silently invert 6 existing references**. All 21 markdown
  cross-refs were rewritten, both missing rows (14b, 15b) were added to the `00_OVERVIEW` index, and the
  prose workaround this bullet complained about (`15b_chapter_browser.md:4`'s *"same shape as
  14_utility_panels.md"*) is now a real link.
  ⚠ **Residual, tracked (`D-X8-CODE-COMMENT-REFS`):** **127 references in 102 SOURCE files** (code
  comments, e2e specs, `book-service/internal/migrate/migrate.go:488`) still name the OLD filenames. The
  X-8 DoD grep was scoped `--include=*.md docs/` and **could not see them** — the same grep-the-wrong-scope
  miss that hid the 5th destructive-token drift (§8.3). They are comment-only (zero behavior) and several
  live in files other Wave-0 slices are editing concurrently, so they are deferred, not dropped. Fix with a
  mechanical sweep once Wave 0's code slices land.
- `29_translation_repair.md`'s H1 still reads `# 24 — Translation surfaces…` (a missed heading in the 24→29 renumber) — it now collides visually with `24_plan_hub_v2.md`.
- `00_OVERVIEW.md`'s component index + Debt stack are stale (above). `00C` Q-2 ("Agent Mode 0% frontend") is **flatly false** — the panel is in the catalog **and** the agent enum.
- Spec 20's header still says "not yet built" despite being built **and** `/review-impl`'d.

---

## 5 · The gap register

**Legend.** *Verdict:* CONFIRMED = the gap is exactly as stated · PARTIAL = the Studio-level claim
holds but the framing was wrong (correction inline; full refutation in §10).
*BE?:* **NONE** = pure FE work · **SMALL** = 1–3 thin route mirrors over already-built engines ·
**REAL** = new engine/schema/design work.

### 5.1 P0 — the sharpest asymmetries

| ID | Domain | The gap | Proposed surface | Backing tools / routes | Size | BE? | Verdict |
|---|---|---|---|---|---|---|---|
| **G-CANON-RULE-CRUD** | canon | The Studio **judges** you against canon rules (`quality-canon`, 3 read lenses) and gives you **no way to write one**. A fully-built CRUD component (`CanonRulesPanel.tsx` + `useCanonRules.ts`) exists — mounted only on the legacy page. | **`quality-canon-rules`** panel (category `quality`, DOCK-8 sibling). Deep-link IN from QualityCanonPanel's violation rows (`focusRuleId` already forwards a rule id — `d662bd97d`). | `composition_canon_rule_{create,update,delete}` · `composition_list_canon_rules` · `GET\|POST /works/{pid}/canon-rules` · `PATCH\|DELETE /canon-rules/{rule_id}` (If-Match OCC) | **S** | **NONE** *(+ one SMALL: no `restore` — see **BE-11**)* | **PARTIAL** — it IS authorable today, on the legacy page. This is a **port**, not a build. |
| **G-ARC-SPEC-CRUD** | structure | `structure_node` (saga→arc→sub-arc) — **the object `pack()`'s `gather_arc` lens injects into every generation prompt** — has full REST CRUD + 8 MCP tools. The FE consumes **3 of 8**: list, move, assign-chapters. **No create, no read-detail, no update, no delete, no restore in ANY GUI.** | **`arc-inspector`** panel (category `editor`; spec 23-C3 / **DBT-06**). Enriched detail: identity · tracks · roster + roster_bindings · derived span · open_promises rollup · template provenance. Embedded by PlanDrawer's arc variant (**24-H3.1 is explicitly blocked on this**). | `composition_arc_{create,get,update,delete,restore}` · `POST /books/{bid}/arcs` · `GET\|PATCH\|DELETE /arcs/{node_id}` · `POST /arcs/{node_id}/restore` — **all 5 NO-FE-CONSUMER** | **M** | 🔴 **CORRECTED 2026-07-13 — this said "NONE" and was WRONG.** `32_arc_inspector.md` §5 found **3 MUST-FIX defects** by reading source: **BE-A1** — `GET /arcs/{node_id}`'s `span` is `StructureRepo.span()` = **RAW strided** units (stride 1000), while the LIST route returns dense-ranked ordinals; an inspector rendering it prints *"Chapters 41000–58000"*, **and the MCP door has the same defect** (`server.py:4255`). ⚠ Fix **at the route**, never in the repo — `span()`'s third caller is the **packer** (`lenses.py:322`), and dense-ranking it silently corrupts every generation prompt. **BE-A2** — `PATCH /arcs/{node_id}`'s `If-Match` is **OPTIONAL**, and a blind write **does not bump `version`** (`structure.py:379-382`) ⇒ the REST door is weaker than the MCP door on the object that steers generation. Make it **428**. **BE-A3** — **no UNASSIGN at any layer**: a chapter, once bound to an arc, can never return to the unassigned pool the Hub already **reads** (`?unassigned=true`). | **CONFIRMED** (`PlanDrawer.tsx:351` renders a visible `plan-drawer-arc-gap` note saying the inspector "is not [built]") |
| **G-PLANFORGE-PASS-RAIL** | planforge | The 7-pass v2 compiler's **two BLOCKING human checkpoints (cast, beats) can only be accepted by the agent.** A GUI-only user **cannot advance a plan run past pass 2**. | **`plan-passes`** panel (spec 27-F3 "Pass Rail"): the 7-pass ledger + `pass_cursor`/`blocked_at`; run-one-pass (cost-gated); the cast + beat/tension checkpoint cards as approve/hold+edits forms; Link-to-spec-tree. | `plan_run_pass` (paid) · `plan_pass_status` · `plan_review_checkpoint` · `plan_link` · `plan_handoff_autofix` · 4 REST routes, **all NO-FE-CONSUMER** | **L** | **SMALL** (`plan_handoff_autofix` has **no REST route at all**) | **CONFIRMED** — `server.py:3595` literally reserves the override for a GUI that doesn't exist: *"⚠ THERE IS NO `force` HERE… a human, at the GUI, may override the PF-5 gate. The AGENT may not."* |
| **G-STUDIO-CATALOG-HOLES** | studio | 4 cross-cutting defects that **block or corrupt every panel in this plan**. See §8 (X-1, X-4, X-5). | not a panel — 4 fixes that MUST land alongside/before the panel work | `ui_show_panel`, `ui_watch_job`, `ui_open_studio_panel` | **S** | **SMALL** (only the `ui_show_panel` enum/retire decision touches chat-service) | **CONFIRMED** |

### 5.2 P1 — the narrative-craft layer, the flywheel, the problems panel

| ID | Domain | The gap | Proposed surface | Backing tools / routes | Size | BE? | Verdict |
|---|---|---|---|---|---|---|---|
| **G-MOTIF-LIBRARY** | motif | The **entire narrative motif library** (3 tiers, mine, adopt, sync, suggest, graph — 套路/爽点/打脸) is stranded on the legacy page. **~40 files, ~15 components, ~25 test files.** The Studio shows motif **titles** only, as read-only PlanHub chips. `motif_link_*` (composed_of / precedes / variant_of) has **no REST route and no GUI anywhere** — the motif graph is invisible to humans. | **`motif-library`** panel (category `storyBible`): 3-tier browse (incl. the NO-FE-CONSUMER `book_shared` tier) · create/patch/archive · adopt (propose→confirm) · mine (cost-gated async) · upstream-diff + sync · a motif-link **graph** section. | 12 `composition_motif_*` tools + `composition_get_mine_job` · 10 REST routes | **L** | **NONE** for CRUD/adopt/sync/mine/suggest *(the FE→MCP bridge `frontend/src/mcpBridge.ts` is already proven in this exact feature)*. **SMALL** for the link-graph (3 routes **or** bridge wiring) + a new graph view. | **CONFIRMED** (`D-MOTIF-LIBRARY-CRUD-GUI`) |
| **G-MOTIF-BINDING** | motif | PlanHub renders motif chips **the agent can freely rewrite** (incl. `pinned_version` vs `live_version` drift) — the human can only look at them. `NodeBadges.tsx:124-145` renders `case 'motif'` as a plain non-interactive `<span>`. **`undo_token` has ZERO frontend consumers.** | **NOT a new panel** (spec 21 classifies motifs as a *cross-ref lens*): a **Motifs section** in `scene-inspector` + a bind/unbind/re-role affordance on PlanDrawer's chapter variant. Spec 24-**PH19** already specs this verbatim; only the READ half shipped. | `composition_motif_{bind,unbind}` · `PATCH\|DELETE /works/{pid}/outline/{nid}/motif` · `PATCH …/motif/role` · `POST …/motif/chain` · `GET …/outline/motif-bindings` | **M** | **NONE** — full CRUD + the `undo_token` round-trip are reachable over REST. ⚠ `undo_token` is **CHAPTER-scope only**; a scene bind returns none — do not advertise token-undo on scene nodes. | **CONFIRMED** |
| **G-CONFORMANCE-TRACE** | quality | Conformance ("did the prose actually realize the plan?") shows the Studio a **red/green dot and nothing else**. The full coarse/deep trace is legacy-only. **AND 3 live FE calls 404** (§3.3). | **`quality-conformance`** panel (DOCK-8 sibling): beat-by-beat realized/not-realized trace, chapter + arc scope, dirty/stale freshness, propose→confirm through the **real generic** `/actions/preview` + `/actions/confirm` (NOT the two invented per-action paths), and a Regenerate action **that points at a route that exists**. | `composition_conformance_run` (Tier-W, paid) · `composition_conformance_status` · `GET /works/{pid}/conformance` · `GET /books/{bid}/conformance/status` | **M** | 🔴 **CORRECTED 2026-07-13 — this said "REAL (small): `regenerate-to-beat` must be BUILT (mirror `POST /scenes/{nid}/prose`)". It is now `BE-5 = DO NOT BUILD`, and §6 agrees.** Spec [`33`](33_motif_studio.md) §5.1 refuted it **on the code**: `engine.py`'s `persist_scene_prose` is a **divergence-promote PERSIST** — it writes a synthetic completed job and **generates nothing**; there is no per-scene generate route to mirror **because one already exists** (`POST /v1/composition/works/{pid}/generate`, `engine.py:328`, takes an `outline_node_id` = a SCENE, and is what the shipped ComposePanel already drives). Once **X-7 (`gather_motifs`)** lands, that scene-generate **IS** "regenerate to beat" — the to-beat semantics are the **packer lens, not a route**. A bespoke route here would be a **per-action route for a Tier-W op** — the exact §8.1 violation the two live 404s already committed. ⇒ **BE? = NONE.** The work is: **delete `motifApi.regenerateToBeat` and re-point the button** at the existing generate route. The 2 `/actions` 404s are likewise a **pure FE bug**, not a BE gap. | **CONFIRMED** |
| **G-ARC-TEMPLATE-LIBRARY** | arc | **Apply** exists in the GUI; **extract / drift / suggest do not.** The whole library is legacy-only — and reachable ONLY through the page spec 16 slates for deletion. **Extract is the half that makes the library grow from the user's own work, and it has no surface at all.** | **`arc-templates`** panel (category `storyBible`): browse own/catalog tiers · CRUD · adopt · apply-preview → materialize · "suggest an arc for this premise" · "save this arc as a template" · a drift view. | `composition_arc_{suggest,apply,extract_template,template_drift}` · 9 REST routes | **L** | **SPLIT** — core (browse/CRUD/adopt/apply→materialize): **NONE**. suggest + extract: **SMALL** (2 thin route wrappers; engines exist). **drift: REAL** — `build_template_drift` does not exist. ⚠ **`composition_arc_apply` and `composition_arc_template_drift` are honest-failure STUBS at HEAD** (`_pending_engine`) — the *agent* cannot apply a template even though the human can. | **CONFIRMED** (`D-ARC-TEMPLATE-CRUD-GUI` + `D-ARC-APPLY-MCP-WRAPPER`) |
| **G-MOTIF-SUGGEST** | motif | "Which trope fits this chapter" and "which arc fits this premise" are **ranked, explained (`match_reason`), and unreachable**. The only way to reach them is to ask the chat agent **by name**. | **Two action buttons, not a panel** (spec 21: *"a button, not a panel"*): *Suggest a motif* on PlanDrawer/`scene-inspector`; *Suggest an arc* on `arc-inspector`/`arc-templates`. Render the ranked list + the `match_reason` breakdown the tools already return. | `composition_motif_suggest_for_chapter` · `composition_arc_suggest` — **no REST route, no FE** | **S** | **SMALL** — 2 thin GET routes **or** 2 names added to `FE_BRIDGE_TOOL_ALLOWLIST` (`tools.controller.ts:24`). ⚠ **This LOOKS FE-only and is not** — without one of the two, the browser gets a 403 from the BFF allowlist and fails closed at integration time. | **CONFIRMED** |
| **G-CORRECTION-FLYWHEEL** | quality | `generation_correction` — the human-gate learning signal — is written **only** from the legacy ComposeView. **The Studio's Compose is Chat/MCP-based and NO MCP tool records a correction.** The flywheel that teaches the model the author's taste **structurally only accrues for users still on the legacy page.** | **`quality-corrections`** (stats, DOCK-8 sibling) **+ the load-bearing half**: a correction-capture seam on the Studio's accept/reject path (`propose_edit` Apply/Dismiss, and the agent-mode `accept_unit`/`reject_unit` path). | `POST /jobs/{job_id}/correction` · `GET /works/{pid}/correction-stats` · **plus** learning-service `GET /v1/learning/corrections` (a per-row LIST the original claim missed) | **M** | **REAL (small)** — reads are complete; the **capture seam needs a new MCP tool** (`composition_record_correction`) + a write in the `reject_unit`/`accept_unit` service path. No schema change. | **CONFIRMED** (00C Q-3(b): *"no Studio equivalent anywhere"*) |
| **G-DIAGNOSTICS-ISSUES** | quality | *"What is wrong with my book"* — the highest-value read in the product — **only answers to an LLM.** `composition_diagnostics` (ranked error→warn→info across 7 sources) is MCP-only. Meanwhile spec 01's Bottom Panel **Issues** tab has been a stub string since day one. | **Wire the EXISTING `StudioBottomPanel` Issues tab** to a new REST mirror `GET /v1/composition/books/{bid}/diagnostics`, each row deep-linking to the panel that owns the fix. **Do NOT build a new dock panel** — spec 28 **AN-12 forecloses "agent panels" as a DOCK-2/DOCK-8 fork.** `composition_find_references` becomes a **right-click lens on an entity badge**, not a panel. | `composition_diagnostics` · `composition_package_tree` · `composition_find_references` — **no REST route for any of the three** | **M** | **REAL (small)** — 1 new read-only GET (a mechanical lift of an already-shipped, already-review-hardened engine: `app/services/agent_native.py`). **Zero gateway work** (the composition proxy's pathFilter is generic). | **CONFIRMED** — but ⚠ **requires a PO decision to AMEND AN-12** (§9). Only **~2.5 of 5** diagnostic sources have any human surface, and **none** is ranked — so AN-12's premise ("the human equivalents already exist") is demonstrably only partly true. |
| **G-STYLE-VOICE** | style | Density + Pace (0-100) and per-character voice tags — **the two knobs that most directly shape prose output** (`packer/pack.py:263-279` folds them into every draft prompt) — have **no Studio surface**. Plus an **INVERSE gap**: there is no `composition_style_*` / `composition_voice_*` MCP tool at all, so the **agent cannot set them either.** | **`style-voice`** panel (category `editor`): density/pace sliders per scope with **the most-specific-wins resolution shown explicitly** (SET-1..8: effective value **+ source tier**), plus per-character voice chips bound to glossary entities. | 6 REST routes (**100% consumed — by the legacy page**) · **0 MCP tools** | **M** | **NONE** for the panel (PUT is an upsert ⇒ LIST+UPSERT+DELETE = complete CRUD). **REAL (small)** for the MCP tools (net-new on composition-service). | **CONFIRMED** |
| **G-REFERENCES-SHELF** | grounding | The author's reference corpus (title/author/url/content + embedding, top-K cosine into every generation) is legacy-only. The Studio user can **PIN** grounding blocks (`GroundingPanel` IS ported) but **cannot add the corpus those pins draw from.** `GroundingPanel.tsx:15` even comments that references *"have their own ReferencesPanel, so they're not grouped here"* — the port was **consciously skipped**. | **`reference-shelf`** panel (category `editor`): add/remove reference sources + the per-scene retrieved top-K. ⚠ **RENAMED 2026-07-13 (cross-spec sweep) — this row said `references`.** `36_editor_craft_ports.md` is right to reject that id: **`references` collides head-on with `composition_find_references`** (entity backlinks — a *different* concept, whose collision with `routers/references.py` this very plan already flags in §10). Two names for one concept is bad; **one name for two concepts is worse** — a model tool-searching "references" would have had to choose between the research shelf and the backlink lens. **The id is `reference-shelf`.** The `frontend_tools.py` description gloss must say so explicitly. | 4 REST routes (100% consumed — by the legacy page) · 0 MCP tools | **S** | **NONE** for LIST+ADD+DELETE+top-K. ⚠ **NO UPDATE ROUTE EXISTS** — fixing a typo requires delete+re-add (which **re-embeds**). ⚠ The proposed "surface `reference_embed_model_ref`" leg is **not backed** (LIST returns only `embed_model_set: bool`) — file as a separate BE slice. | **CONFIRMED** |
| **G-PROGRESS** | progress | The Studio **writes a word-count snapshot on every single save** (`ManuscriptUnitProvider` → `reportProgress` + `useEnsureBaseline`) and **no Studio panel reads it.** | **`progress`** panel: today's words (server-differenced), streak/goal, per-chapter breakdown. Pairs with the existing `WordCountStatusItem`. | 3 REST routes | **S** | **NONE** for the core. **SMALL** for the per-chapter breakdown (the chapter dimension exists in the tables and is *collapsed away* before it reaches the router). | **PARTIAL** — it is **not** orphaned write-only data: `ProgressPanel.tsx` **is** mounted + reachable in the legacy dock, which also does the writes. It **becomes** write-only the moment 00C Q-6 retires that page. |
| **G-WORKFLOWS** | agent-registry | `registry_propose_workflow`'s description says *"records a proposal the user must approve **in the UI**"* — and there is **no UI**. An agent calling it today writes a row **no human can ever approve**. `mode_bindings` is labelled **in code** as *"a USER setting"* with no settings surface (SET-1..8 write-only-behavior violation). | `workflows` + `workflow-proposals` panels (near-clones of the existing skill `ExtensionsPanel`/`ProposalsPanel` spine) + a mode-binding control in `settings`. | 4 `registry_*workflow*` tools · 6 REST routes | **M** | **REAL** — the proposals half is buildable today; the **workflows half is NOT**: the public surface is **completely empty** (LIST, GET-one, DELETE, enablement — **none exist**; only `/internal/workflows`). 3–4 new Go routes. | **CONFIRMED** — 🔴 **COLLIDES HEAD-ON with Track C's P-5.** See §9. |

### 5.3 P2 — the rest of the legacy tail + the agent-only domains

| ID | Domain | The gap | Proposed surface | Size | BE? | Verdict |
|---|---|---|---|---|---|---|
| **G-WORLD-MAPS** | book-service | **A complete CRUD domain (maps + markers + regions — 8 MCP tools) reachable ONLY by an agent, with no REST layer at all.** The `/worlds` pages have no map surface. ⚠ The one map route is **not public** — it is `POST /internal/worlds/maps/{id}/image` behind `requireInternalToken` + a `?user_id` query param, i.e. **unreachable from a browser by construction**. The true public REST surface for maps is **ZERO routes**. | `world-map` — but ⚠ **it has no host**: `/worlds` is a classic route, not a dock panel, so reaching it from the Studio is a route hop = DOCK-7 teardown. **A `world` container panel is a prerequisite.** | **L** | **REAL** — ~8–10 new REST routes. **UPDATE does not exist at ANY layer** (the tool set is add/remove-only): renaming a map, dragging a pin, reshaping a region needs **new update semantics designed**, or it degrades to delete+recreate (which churns ids and breaks glossary entity links). | **CONFIRMED** |
| **G-KG-WRITE-HOLES** | knowledge | **No Create anywhere** (`grep createEntity` across `features/knowledge/**` → EMPTY, though `knowledgeApi.createEntity` exists), **a dead delete** (`kg-overview` mounts `OverviewSection` with `onDelete={noop}` — and actually **`onArchive` + `onRestore` too: THREE dead buttons**), and 2 agent-only writes. The empty-graph state **the agent's own error message tells you to fix** has no button. | 4 additive affordances on existing panels — **no new panel**. | **M** | **MIXED** — entity/relation create: **NONE** (pure FE wiring). `kg_project_entities_to_nodes` + `memory_forget`: **SMALL** (2 thin route mirrors over already-built, already-tested engines). | **CONFIRMED** — ⚠ **one sub-claim REFUTED**: `kg_create_node` **is** REST-reachable (§10). |
| **G-IMPORT-DECONSTRUCT** | import | **拆文** (deconstructing a reference novel into reusable structure) — *a headline differentiator for the target audience* — is **100% agent-only** and its input CRUD (`/import-sources` ×4) has **zero FE consumers**. `ArcTemplateLibraryView.tsx:51`'s empty state literally advertises the flow — *"or import a story to deconstruct"* — **a dangling CTA pointing at a feature with no entry point.** | An **"Import & Deconstruct" section inside `arc-templates`** (not a standalone panel). | **M** | 🔴 **CORRECTED TWICE — read the second one.** *(1st, 2026-07-13:)* this row said BE **"NONE"** and was WRONG. *(2nd, 2026-07-13 — the mechanism itself:)* the 1st correction then said *"the POLL is not shipped ⇒ `GET /jobs/{id}` 404s always ⇒ **BE-7c**, an owner-scoped job read, **XS**"*. **That is ALSO wrong, and its cure would have shipped GREEN over a broken path.** Propose is shipped; **THE CONFIRM 500s.** `_execute_arc_import` enqueues with `project_id=None` → `_enqueue_motif_job` stamps a synthetic `uuid4()` (`actions.py:552`) → `GenerationJobsRepo.create()` **derives the `NOT NULL book_id` via `INSERT … SELECT … FROM composition_work`** → **ZERO rows** → `ReferenceViolationError` → uncaught → **HTTP 500 at `POST /actions/confirm`**, confirm token burnt. **The job row is NEVER CREATED; the poll is never reached; nobody is charged** (no XADD, no worker, no LLM). ⚠ **An owner-scoped READ cannot fix a row that was never INSERTED** — and its test would seed the row by hand and pass (`fixtures-can-seed-a-field-the-writer-never-sets`). ⇒ the real fix is the **Work-less job LANE** (nullable scope + a shape CHECK + `create_unbound()` + **the `_enqueue_motif_job` writer fix** + the read route + the MCP arg), = **[`W0-BE1`](../../plans/2026-07-13-studio-wave-0-foundations.md)**, **already carried in full by the Wave-0 plan** and **built in Wave 0** (not Wave 3/4). It also unbreaks `motifApi.mineConfirm`, which 500s for the same reason. See §3.3 and `34` §0.1. | **CONFIRMED** — ⚠ the *"mine motifs from this import source"* leg is **REFUTED** and must be dropped (§10). |
| **G-DIVERGENCE** | derivative | The whole **dị bản** (AU / what-if derivative works) feature — a DB schema, a built 4-step wizard, `source_work_id` + `branch_point` — is **absent from the Studio**. | **`divergence`** panel (category `editor`): port `DivergenceWizard` **+ `useWhatIfPromotion`/`PromoteWhatIfButton` + `DerivativeBanner`/`DerivativeGroundingLayers`** (the claim missed these). | **M** | **REAL** — what exists is **CREATE-ONCE + READ-ONE**, not CRUD. There is **no UPDATE** (the spec+overrides are written once inside the `POST /derive` txn and are thereafter immutable), **no DELETE**, and **no LIST of a book's derivatives**. The proposed *"manage entity_override rows"* is **unbuildable on today's backend.** Also: **zero divergence MCP tools.** | **CONFIRMED** |
| **G-STORY-STRUCTURE** | plan | 6 seeded story structures (Save the Cat, Hero's Journey, Story Circle, Kishōtenketsu, Web Novel Arc, Three-Act) + the chapter→scene **decompose** flow they drive — **no Studio entry point.** (The Studio's `planner` panel is **PlanForge**, a different thing.) | **Fold into `plan-hub`** (spec 21 re-map: `beats` = a **node facet**; `planner` = an **action button**): a *Decompose with a structure* action on a chapter node → preview → commit, and a beat-sheet facet in PlanDrawer. | **M** | **NONE** for the panel as proposed. ⚠ **`structure_template` is READ-ONLY on ALL transports** — the repo has exactly `list_for_user` + `get`. The "+ user-custom" tier the table advertises **is unreachable: no code can insert one.** Authoring needs 3 new routes (mirror `arc_template`'s shape) + clone-to-user tenancy. | **CONFIRMED** |
| **G-WORK-SETTINGS** | work | `composition_work.settings` (models, `capture_correction_prose`, `reference_embed_model_ref`, `critic_model_ref`) — and **`PATCH /works/{pid}` REPLACES the whole blob.** Plus 3 orphan routes: `approve`, `suggest-cast` (a real LLM capability with **zero** callers anywhere), chapter-level `GET\|PUT /prose`. | A **Composition section in the existing `book-settings` panel** (not a new panel) — each key showing **effective value + source tier** (SET-1..8). Plus a *Suggest cast* button on `scene-inspector`. | **S** | **NONE** for reads/writes. **REAL (one small fix):** `repositories/works.py:311` does `settings = $n::jsonb` — a full-blob REPLACE with a genuine **lost-update window** (`patchWork` sends no If-Match). Fix = server-side `settings \|\| $n::jsonb` **or** send If-Match. | **PARTIAL** — an editor **does** exist (`CompositionSettingsView.tsx`) for 4 of 7 keys; 3 keys (`capture_correction_prose`, `critic_model_ref`, `reference_embed_model_ref`) are **genuine SET-1..8 silent hidden defaults**. |
| **G-PLANNER-REPAIR** | planforge | The shipped `planner` panel strands a GUI-only user at the first failed validation: no artifact viewer (3–5 **unclickable** rows: kind + truncated UUID), source markdown does not resume, and `plan_handoff_autofix` is **MCP-only**. | Repair the existing panel (no new id) + an artifact viewer (open `plan_artifact` bodies in the generic `json-editor` — **this also closes spec-12 cycle-gate item 5**). | **M** | **REAL (small)** — ⚠ **there is NO artifact-read route ANYWHERE** (not REST, not even MCP: no `plan_get_artifact` tool exists). The run detail returns `{kind, artifact_id}` metadata only; the **body is unreachable by any client, agent or GUI.** Also needed: `/autofix` route; **and there is NO DELETE for plan runs at all** — failed LLM runs accumulate forever. | **PARTIAL** — **sub-gap 1 (the arc_id text box) is STALE and already FIXED** by `9c685c28a`. ✅ **Cheapest win in the whole plan:** `interpret`/`refine` have routes **and** api.ts methods and **zero callers** — they need **buttons only, zero backend.** |
| **G-POLISH-SELFHEAL** *(NEW — found by the completeness critic; in no original gap)* | quality | The **M6 Polish / self-heal review gate** — a complete, tested accept/reject "apply the AI's fix to my prose" GUI (`PolishPanel.tsx` + `usePolishProposals.ts`) — is legacy-only, has **no MCP tool at all**, and appears in **none of the 22 gaps**. Worse: it makes an **already-shipped Studio feature half-dark** — `QualityCriticPanel.tsx:80` mounts `<QualityReportSection>` **without the `proposals` prop**, so `_hasProposedFix()` (D-QUALITY-CRITIC-HEAL-LINK) **can never fire for a Studio user**. *The Studio ships the consumer of a producer it doesn't have.* | Port `PolishPanel` as a `quality-heal` sibling **and pass `proposals` into `QualityCriticPanel`.** | **M** | **NONE** (`POST /works/{pid}/self-heal/propose` exists and is consumed). MCP tool = optional follow-up. | **CONFIRMED** |

---

## 6 · Backend prerequisites — this is its own workstream

**GG-5.** A panel whose backend does not exist is not a panel task. These land **first**, in their own
slices, and each is **buildable now** (CLAUDE.md's anti-laziness rule: *"missing infrastructure is NOT
blocked — it is unbuilt work"*). None of them is blocked on an external dependency.

### 6.1 The good news (state it plainly)

- **The gateway needs ZERO changes.** `gateway-setup.ts:350-354` registers the composition proxy with a
  **generic** `pathFilter: (p) => p.startsWith('/v1/composition')`. Any new composition REST route is
  auto-proxied the moment it is added.
- **The FE reaches composition over REST, not MCP** — every sibling panel does. So a REST route is the
  currency. *Exception:* `frontend/src/mcpBridge.ts` (`mcpExecute`) **already exists and is already used**
  by `features/composition/motif/api.ts` for the three cost-gated propose→confirm flows. That precedent
  is load-bearing for G-MOTIF-LIBRARY and G-IMPORT-DECONSTRUCT — they need **no new routes**.
- **~9 of the 23 gaps need ZERO backend work.** They are pure ports.

### 6.2 The prerequisite table

| # | Prereq | Service | For | Size | Notes |
|---|---|---|---|---|---|
| **BE-1** | `GET /v1/composition/books/{book_id}/diagnostics` — REST mirror of `composition_diagnostics` | composition | G-DIAGNOSTICS-ISSUES | **S** | Engine is 100% done + review-hardened (`app/services/agent_native.py`). A near-mechanical lift of the ~120-line MCP handler. **Low-risk, high-confidence.** ⚠ gated on the AN-12 PO decision. |
| **BE-2** | `POST …/plan/runs/{run_id}/autofix` | composition | G-PLANFORGE-PASS-RAIL, G-PLANNER-REPAIR | **XS** | Service method `handoff_autofix` is **fully implemented** (`plan_forge_service.py:817`). Mirror `/refine`'s 202-ack shape. |
| **BE-3** | `GET …/plan/runs/{run_id}/artifacts/{artifact_id}` | composition | G-PLANNER-REPAIR | **S** | 🔴 **No artifact-read path exists in ANY transport.** Repo method `latest_artifact(...)` already exists. **This one route also solves the source-markdown resume.** |
| **BE-4** | `DELETE`/archive for **plan runs** | composition | G-PLANNER-REPAIR | **S** | `grep "@router.delete"` across `plan_forge.py` + `plan_bootstrap.py` → **nothing**. Failed LLM runs accumulate with no way to clear them. |
| **BE-5** | ~~`POST /works/{pid}/scenes/{node_id}/regenerate-to-beat`~~ | composition | G-CONFORMANCE-TRACE | — | 🔴 **DO NOT BUILD — REFUTED 2026-07-13 by `33_motif_studio.md` §5.1.** This row's proposed fix (*"mirror `POST /scenes/{nid}/prose` (`engine.py:1522`)"*) is **wrong on the code**: `engine.py:1522` is `persist_scene_prose`, a **WS-B3 divergence-promote PERSIST** that writes a synthetic completed job — **it generates nothing.** There is no per-scene generate route to mirror **because one already exists**: `POST /v1/composition/works/{pid}/generate` (`engine.py:326`) takes `outline_node_id` (a SCENE) and is the route the shipped ComposePanel already drives. And once **X-7 (`gather_motifs`)** lands, that scene-generate **IS** "regenerate to beat" — the to-beat semantics are the **packer lens**, not a route. Building a bespoke route here would be a **per-action route for a Tier-W op** — the exact §8.1 violation the two live 404s already committed. ⇒ **Delete `motifApi.regenerateToBeat`; re-point the button.** |
| **BE-6** | ~~2 REST GETs (or 2 `FE_BRIDGE_TOOL_ALLOWLIST` names): motif-suggest-for-chapter, arc-suggest~~ | composition | G-MOTIF-SUGGEST | **S** | 🔴 **SPLIT + DE-DUPED 2026-07-13 (cross-spec sweep).** This row and **BE-7 both specced `arc-suggest`** — and specs 33 and 34 each dutifully picked one up, producing **two different contracts for one tool** (`GET /books/{bid}/arcs/suggest?limit=10` vs `POST /arc-templates/suggest {project_id, limit=5}`). ⚠ **`composition_arc_suggest` (`server.py:2288`) takes `project_id`, NOT a `book_id` path segment, and defaults `limit=5`** — so the `GET /books/…` shape was simply wrong. ⇒ **BE-6 is now MOTIF-suggest ONLY** (`GET /v1/composition/works/{project_id}/motifs/suggest` — spec **33** BE-M4, Wave 3). **Arc-suggest belongs to BE-7 / spec 34 alone.** ⚠ **REST, not the bridge:** `FE_BRIDGE_TOOL_ALLOWLIST`'s own contract is *"NOTHING here writes or deletes"* and every member is spend-adjacent; a free read does not belong there, and going REST also keeps the wave **single-service** (no cross-service live-smoke). Engine exists; `get_motif_retriever` is wired at `app/deps.py:205`. |
| **BE-7** | 2 REST routes: **`POST /v1/composition/arc-templates/suggest`** (arc-suggest — **the ONE owner; see BE-6**) + `POST /v1/composition/arcs/{node_id}/extract-template` | composition | G-ARC-TEMPLATE-LIBRARY | **S** | Both engines exist and work (`extract_template_from_arc` @ `arc_apply.py:652`). Thin wrappers. **Contract owned by `34_arc_templates_and_deconstruct.md` §5 (BE-7a/BE-7b)** — body `{project_id, premise?, genre?, limit=5, detail}`, mirroring the tool exactly. ⚠ Extract is a **Tier-A WRITE** ⇒ REST, **never** a bridge-allowlist entry. |
| **BE-7c** → 🔴 **`W0-BE1`** | **THE WORK-LESS JOB LANE** (7 legs) — *not* "a job-read route" | composition | the **4th defect** (§3.3): motif-MINE **and** 拆文 — **a 500 at confirm, NOT a 404 at the poll** | ~~XS~~ → **S/M** *(schema side effect)* | 🔴 **RE-SCOPED, RE-SIZED, RE-WAVED 2026-07-13. BUILT IN WAVE 0 — [`W0-BE1`](../../plans/2026-07-13-studio-wave-0-foundations.md) — and the Wave-0 plan ALREADY CARRIES THE FULL FIX.** This row used to read *"`GET /v1/composition/motif-jobs/{job_id}` — the owner-scoped job read · **XS** · build in Wave 3 (3a)"*. **That cure does not work**: the `generation_job` row is **never inserted** (the confirm 500s — §3.3), so an owner-scoped read would read **a row that does not exist** — and it would **SHIP GREEN**, because its test would seed the row with a raw `INSERT` the producer can never produce (**`fixtures-can-seed-a-field-the-writer-never-sets`**). **The read route is leg (e) of seven.** The lane: **(a)** `project_id`/`book_id` `DROP NOT NULL` + a **both-or-neither shape CHECK** + a partial owner index · **(b)** **`create_unbound()`** (plain INSERT; **do NOT touch `create()`**) · **(c)** model → `UUID \| None` · **(d)** 🔴 **`_enqueue_motif_job`: delete the `uuid4()` synthetic pid** ← *the leg that stops the 500* · **(e)** the owner-scoped read (gate on `created_by`, uniform H13 404) · **(f)** `composition_get_mine_job` drops the un-knowable `project_id` · **(g)** tests **through the producer**. ⚠ **Never back-fill a real or phantom `project_id`.** Pulled into **Wave 0** because it fires **today**; Wave 3 (3a) **verifies** it and ships the first consumer (⛏ Mine), Wave 4 consumes it for 拆文. Build detail: [`wave-3-motif`](../../plans/2026-07-13-studio-wave-3-motif.md) `3a-1` (a)–(d) — **do not fork a second DDL.** |
| **BE-8** | ~~`build_template_drift` **engine fn** + its route~~ → **agent-parity only** | composition | G-ARC-TEMPLATE-LIBRARY (drift view) | ~~M~~ → **S + M, split** | 🔴 **CORRECTED 2026-07-13 by `34` §5.** *"REAL work — the function does not exist"* was **half wrong, and it mis-sized the wave.** **The drift ROUTE ALREADY EXISTS and is shipped:** `GET /v1/composition/works/{pid}/conformance?scope=arc_template_drift&arc_id=…` (0 FE consumers) ⇒ **the human's drift view is BE-NONE and must NOT be parked.** What is missing is only the **agent's** two `_pending_engine` stubs: `composition_arc_template_drift` → **point it at the already-shipped `compute_arc_report(…, by_structure=False)` the REST route uses** (do **not** write a second engine — that is the `css-var-duplicated-across-two-consumers-drifts` class) ⇒ **S**; `composition_arc_apply` → `apply_arc_to_spec` is genuinely unwritten ⇒ **M**. This is `D-ARC-APPLY-MCP-WRAPPER`, **re-scoped**: it is a **GG-2 inverse gap** (the human can, the agent cannot), sequenced **after** the panel — not a blocker of it. |
| **BE-9** | `composition_record_correction` MCP tool + a `generation_correction` write in the `accept_unit`/`reject_unit` service path | composition | G-CORRECTION-FLYWHEEL | ~~M~~ → **L** | 🔴 **"No schema change" is WRONG — corrected 2026-07-13 by `31_quality_completion.md` F-Q2.** `generation_correction.job_id` is **`UUID NOT NULL REFERENCES generation_job(id)`** (`migrate.py:368`) and the repo re-verifies the job is in the project before it will write. **The agent-mode path has a generation job and throws its id away:** `authoring_run_units` (`migrate.py:1493`) has **no `job_id` column**, and `EngineDraftingSeam.draft_chapter` **reads** `payload["job_id"]` (`authoring_run_service.py:377`) only to fetch the cost, then **discards it** (`DraftOutcome = {ok, cost_usd, error}`). ⇒ At `reject_unit` **there is no way to name the generation the human just rejected.** BE-9 as written **cannot be built.** It needs `ALTER TABLE authoring_run_units ADD COLUMN job_id UUID` (**nullable — never backfill a guess**) + `DraftOutcome.job_id` + a driver write. **That is a side effect, and it is why Wave 1 is L, not M.** ⚠ Two more holes `31` found: **BE-9c** — `correction_stats` groups by `j.mode` over **every** job, so every PlanForge pass / quality report / Polish run **inflates the `auto` denominator** ⇒ the panel would report a delighted author and a ~0% edit rate. Fix at the root with a `CORRECTABLE_OPERATIONS` allowlist, **keeping** the existing `NOT selection_edit` predicate. **F-Q4** — `propose_edit` has **no `job_id` at all** (its prose comes from a *chat-service* turn, not a composition `generation_job`), so the plan's second capture leg is **not buildable** and is scoped out (OQ-1). |
| **BE-10** | `composition_style_*` + `composition_voice_*` MCP tools | composition | G-STYLE-VOICE (inverse gap) | **S** | MCP-first invariant: domain owns its tools. ⚠ **3-schema-source FastMCP caveat** applies. |
| **BE-11** | `canon_rule` **restore** (repo + route) | composition | G-CANON-RULE-CRUD | **XS** | 🔴 Every sibling soft-delete (`outline_node`, `motif`, `structure_node`, `arc_template`) has a restore. **`canon_rule` does not.** Shipping a Delete button with no undo, on the row that *steers the critic*, is a one-way destructive action. |
| **BE-12** | `structure_template` write path (POST/PATCH/DELETE + repo methods) | composition | G-STORY-STRUCTURE (**only if authoring is in scope**) | **M** | The repo has **only** `list_for_user` + `get`. Mirror `arc_template`'s CRUD shape + **clone-to-user** tenancy (the 6 built-ins are System-tier, `owner_user_id IS NULL` — a regular user must never mutate them). **Decide in CLARIFY whether authoring is v1.** |
| **BE-13** | divergence: `GET /books/{bid}/derivatives` (LIST) · `PATCH …/divergence-spec` · `POST\|PATCH\|DELETE …/overrides` | composition | G-DIVERGENCE | **M** | ⚠ Check `D-DECOMP-KEY-COLLIDES-ON-SPEC-BRANCH` — **dormant** for a declare-spec+overrides port; it **fires** only if the builder also copies `outline_node` rows into the derivative partition. |
| **BE-14** | knowledge: `POST /projects/{pid}/project-entities` (projection) · `POST /facts/{fact_id}/invalidate` (forget) | knowledge | G-KG-WRITE-HOLES | **S** | Both engines built + idempotent (`project_glossary_entities_to_nodes`, `invalidate_fact`). ⚠ Do **not** mistake `POST /pending-facts/{id}/reject` (pre-commit queue) or `/internal/admin/…/reject-fact` for these. |
| **BE-15** | book-service: ~8–10 public REST routes for world maps + **an UPDATE design** | book-service | G-WORLD-MAPS | **L** | Tables + all query/ownership SQL already exist in the 8 tool handlers (`mcp_maps.go`); REST handlers are thin wrappers. Gateway needs **zero** changes (`worldsProxy` already forwards `/v1/worlds/*`). 🔴 **UPDATE exists at no layer** — design it. |
| **BE-16** | agent-registry: public `GET /workflows`, `GET /workflows/{slug}`, `DELETE`, enablement toggle; `DELETE /mode-bindings/{mode}` (reset-to-inherited) | agent-registry | G-WORKFLOWS | **M** | 🔴 **Coordinate with Track C P-5 BEFORE writing a line.** |
| **BE-17** | `PATCH /references/{id}` (metadata update, no re-embed) + widen the LIST response to expose `reference_embed_model_ref` | composition | G-REFERENCES-SHELF (v2) | **S** | **Not** a v1 blocker — scope the v1 panel as add/remove-only and say so. |
| **BE-18** | Fix `PATCH /works/{pid}`'s **full-blob settings REPLACE** | composition | G-WORK-SETTINGS | **XS** | Today no data is lost **only because every FE caller hand-merges**. Fragile by construction + a real lost-update window. |
| **BE-19** | 🔴 **`gather_motifs` packer lens** (spec 21-**G1**) | composition | **the entire motif cluster** | **M** | See §8 X-7. **This is a prerequisite, not a nice-to-have.** |

---

## 7 · The build plan — waves

**GG-6 — the ordering law the PO set: SPEC + HTML DRAFT before any implementation plan.**
Each wave's gate is: `spec file written` → `design draft(s) drawn` → *then* PLAN → BUILD.
No wave may start BUILD without both artifacts on disk. Drafts follow the house style extracted from
the 13 existing `design-drafts/screens/studio/*.html` (§8.3).

**GG-7 — each wave is a shippable milestone**, ends at a POST-REVIEW, and is independently revertable.

---

### Wave 0 — FOUNDATIONS (no panels; **everything else is blocked on this**)

*Nothing in this wave is a feature. Every item is a landmine on the critical path of the other 8 waves.*

| Item | What | Size | Why it is Wave 0 |
|---|---|---|---|
| **X-1** | 🔴 **Fix `AddModelCta.tsx` DOCK-7** at the **shared component** (add the `useOptionalStudioHost()` branch → `host.openPanel('settings', { params: { tab: 'providers' } })`; keep the `<Link>` fallback outside the studio). **Never at the ~8 call sites.** | **S** | Motif Mine, Conformance Run, Arc Import, and every `plan_*` LLM pass are **BYOK `model_ref`** — they **all** need a ModelPicker, whose empty state renders `AddModelCta`. Without this, **every new panel we ship contains a button that destroys the user's whole workspace.** Precedent already shipped: `glossary-translate/StepConfig.tsx`. |
| **X-2** | 🔴 **`CATEGORY_ORDER` is missing `'quality'`** (`useStudioCommands.ts:20-22` lists 9; `catalog.ts:81-91` defines 10). `indexOf` returns **-1** ⇒ quality sorts **above** `editor` (index 0). A **missing** category sorts LAST; an **unlisted** one sorts FIRST — the failure modes are **inverted**. | **XS** | Live drift **today**, and a landmine for this batch: a new `narrative`/`motif` category added to the type but not to `CATEGORY_ORDER` silently jumps to the top of the palette. `panelCatalogContract.test.ts:40` asserts a category is **present** — nothing asserts it is a **member of `CATEGORY_ORDER`**. **Spec 18's B6 guards the wrong half.** Fix + add the membership assertion. |
| **X-3** | **`guideBodyKey` is unguarded** — `agent-mode` already shipped without one. Extend `panelCatalogContract.test.ts`: `OPENABLE_STUDIO_PANELS.every(p => !!p.guideBodyKey)`. | **XS** | 15 new panels × silently missing User-Guide copy. One-line test. |
| **X-4** | 🔴 **Lane-B effect registry covers NONE of the new domains.** Registered patterns are only: `book_.*(draft\|chapter)`, `composition_.*(prose\|draft)`, `composition_(outline_node\|scene_link)_`, glossary, knowledge, `translation_job_control`. **No handler** for `composition_canon_rule_*`, `composition_motif_*`, `composition_arc_*`, `plan_*`, `composition_authoring_run_*`, `world_map_*`, `registry_*workflow*`, `kg_create_node`. **Also delete the now-FALSE comment** at `useStudioEffectReconciler.ts:10`. | **M** (~15 handlers) | **Every agent write to every new domain leaves the new panel stale.** The registration checklist calls step 8 "conditional"; **for this batch it is mandatory and ~15 handlers wide.** |
| **X-5** | 🔴 **`ui_show_panel` silently no-ops in the Studio; `ui_watch_job` unmounts it.** `ui_show_panel` is ALWAYS-ON with a **free-string `panel` arg** (excluded from `CLOSED_SET_ARGS`), resolved as a `?panel=` query param on the **classic** page, **not intercepted** by `makeStudioNavInterceptor` → `shown:true`, **no dock tab**. `ui_watch_job` is in neither `STUDIO_UI_TOOLS` nor the interceptor → route-navigates the SPA and tears down the dock, **even though `jobs-list`/`job-detail` panels exist.** | **S** | The **exact silent-success class the `panel_id` enum was added to kill, alive on the sibling tool.** Adding 15 panels multiplies the surface on which a model picks the wrong one of two overlapping tools. **PO decision needed:** give `ui_show_panel` a closed enum + a studio interceptor, **or retire it** in favour of `ui_open_studio_panel` (one name for one concept). ⚠ It is also used **outside** the studio, so retirement is a cross-surface call. |
| **X-6** | 🔴 **Write spec 28's AN-12 `resource_ref` section.** Shape sketch: `{kind: 'structure'\|'outline'\|'motif_application'\|'canon_rule'\|'thread', id, version?}`. | **S** | 28 homes it, sketches it, and declares it a **HARD PREREQUISITE**: *"A Phase-4 build without AN-12 is a spec violation, not a shortcut."* G-MOTIF-BINDING (chips→editor), G-ARC-SPEC-CRUD (deep-link), the existing PH18 canon deep-link, and **any** "agent points at this object" flow are precisely this contract. |
| **X-7** | 🔴 **`gather_motifs` packer lens (spec 21-G1).** `grep -rn "motif" services/composition-service/app/packer/*.py` → **ZERO hits.** Mirror the shipped `gather_arc` (`app/packer/lenses.py:257`). Ship it with a **BA12-style effect test** (the prompt CHANGES when a binding changes — `test_pack_arc_wired.py` is the pattern). | **M** | **This invalidates the premise of THREE gaps.** G-MOTIF-LIBRARY / G-MOTIF-BINDING / G-MOTIF-SUGGEST all ship GUIs for authoring data that **`pack()` never reads**. Building them without G1 is **shipping a beautiful editor for a field with no consumer** — the exact *stored-but-unread ⇒ write-only-behavior* bug CLAUDE.md bans. **G1 is a prerequisite of the motif cluster.** |
| **X-8** | Doc hygiene: renumber `14a/14b`, `15a/15b`; fix 29's stale H1; refresh `00_OVERVIEW`'s component index + Debt stack; clear 00C Q-2 (Agent Mode is **built**); un-stale spec 20's header. | **XS** | Every one of these is **actively misleading the next agent** right now. |
| **X-9** | Close the two un-audited MCP sweeps: **provider-registry-service (14 tools)** and **catalog-service (2 tools)**. ⚠ **The *"decide the unprefixed `web_search` namespacing violation"* leg is DELETED — there is no violation** (§3.4, retracted 2026-07-13: the unprefixed name is deliberate, `EXTRA_PREFIX_MAP` already carries `web_`, and no LOCKED namespacing law exists in `docs/standards/`). **Count the tools; decide nothing.** | **S** | The "173 / 23 NO-GUI" scoreboard is a **floor**, not a total (§3.4). We should not plan against a number we know is wrong. |
| **X-10** | **AN-C2 — the discovery scent.** One sentence in `stream_service.py`'s `book_context_note` naming `composition_package_tree` / `composition_diagnostics`. | **XS** | The tools shipped and **the model was never told they exist**. AN-11's own risk row calls "shipped but never called" a **FAIL**. ⚠ **SEQUENCE AFTER Track C lands** — `stream_service.py` is uncommitted and mid-edit (§9). |

| 🔴 **`W0-BE1`** *(added 2026-07-13 — ex-**BE-7c**, PULLED FORWARD out of Wave 3a)* | 🔴 **THE WORK-LESS JOB LANE — the paid-action defect, and it fires TODAY on the live legacy page.** ⛏ **Mine** and **拆文** both return **HTTP 500 at `POST /actions/confirm`**, before the enqueue: `_enqueue_motif_job` stamps a synthetic `uuid4()`, `GenerationJobsRepo.create()` derives the `NOT NULL book_id` via `INSERT … SELECT … FROM composition_work`, matches **zero rows**, raises an uncaught `ReferenceViolationError`. **The job row is never created** (§3.3). ⚠ **NOT a 404 at the poll, and NOBODY IS CHARGED.** ⚠⚠ **An owner-scoped read route does NOT fix this** — it would read a row that never exists, and would **ship green** on a hand-seeded fixture (`fixtures-can-seed-a-field-the-writer-never-sets`). Build **all seven legs**: DDL (nullable scope + both-or-neither CHECK + owner index) · `create_unbound()` · the model change · **the `_enqueue_motif_job` writer fix** · the owner-scoped read · the `composition_get_mine_job` arg drop · tests **through the producer**. | **S/M** *(schema side effect)* | It is **live**, it is the PO's **CRITICAL** class, and **`W0-S7` cannot fix the FE poll — or run its live smoke — without it.** Wave 3's ⛏ Mine button is its first GUI consumer; leaving it in 3a would have shipped a 500-ing paid button. **The full build is already written in [`wave-0-foundations`](../../plans/2026-07-13-studio-wave-0-foundations.md) `W0-BE1` (detail verbatim in [`wave-3-motif`](../../plans/2026-07-13-studio-wave-3-motif.md) `3a-1`) — build from it; do not re-derive it.** |
| **`W0-S7`** | Delete the **3 FE-invented URLs** (§3.3): the two per-action `conformance_run/{estimate,confirm}` paths → mirror the sibling that uses the **generic** spine; and **`motifApi.regenerateToBeat`** → re-point at the existing `POST /works/{pid}/generate` (**BE-5 = DO NOT BUILD**, §6). | **S** | All three are **FE deletions**, not BE routes. ⚠ Its live smoke **depends on `W0-BE1`** (a confirm that 500s cannot be smoked). |

**Wave 0 gate:** X-1, X-2, X-4, X-5, X-7 green + **`W0-BE1` proven THROUGH THE PRODUCER** (a live
`POST /actions/confirm` → **200 + a real `job_id`** → a resolving poll; a read-route test over a
hand-seeded row does **not** count) + the AN-12 section (X-6) written and PO-signed.
**Specs to write:** an AN-12 section **inside** `28_agent_native_studio.md` (do not fork it).
**Drafts:** none (no new UI).

---

### Wave 1 — QUALITY COMPLETION (cheap, high value, mostly FE ports)

**Panels:** `quality-canon-rules` · `progress` · `quality-corrections` · `quality-heal`
**Gaps:** G-CANON-RULE-CRUD (S) · G-PROGRESS (S) · G-CORRECTION-FLYWHEEL (M) · G-POLISH-SELFHEAL (M)
**BE prereqs:** BE-11 (canon restore, XS) · BE-9 (correction capture seam — **the load-bearing half**, M)
**Spec:** `31_quality_completion.md` **Drafts:** 1 multi-panel HTML (4 panels + the DOCK-8 hub row)
**Size:** **M** · **Why first:** it is 00C **Q-3**, explicitly *"None — unblocked now"*, it closes the
sharpest **read-without-write** asymmetry in the product, and it lights up a Studio feature that is
currently half-dark (`QualityCriticPanel`'s missing `proposals` prop).
⚠ `QualityCanonPanel.tsx` was touched **today** (`d662bd97d`) — read its history before editing.

---

### Wave 2 — THE SPEC TREE

**Panel:** `arc-inspector`
**Gap:** G-ARC-SPEC-CRUD (M) **BE prereqs:** **NONE**
**Spec:** `32_arc_inspector.md` (this is spec **23-C3**, tracked as **DBT-06**) **Drafts:** 1
**Size:** **M** · **Unblocks:** **24-H3.1** (PlanDrawer's arc variant is currently an honest minimal
summary with a visible in-UI gap note). Consumes **X-6** (`resource_ref`) for the deep-link.
⚠ Touches `PlanDrawer.tsx` — coordinate with the Book-Package track (§9).

---

### Wave 3 — THE MOTIF CLUSTER (the biggest single body of built-but-unreachable UI)

**HARD GATE: X-7 (`gather_motifs`) must be green. Without it this wave ships decoration.**

**Panels/surfaces:** `motif-library` · a Motifs section in `scene-inspector` + PlanDrawer ·
`quality-conformance` · 2 suggest buttons
**Gaps:** G-MOTIF-LIBRARY (L) · G-MOTIF-BINDING (M) · G-CONFORMANCE-TRACE (M) · G-MOTIF-SUGGEST (S)
**BE prereqs** *(AMENDED 2026-07-13 — see BE-5/BE-6/BE-7c above)***:** ~~BE-5~~ **DO NOT BUILD** (re-point
Regenerate at the existing `POST /works/{pid}/generate`) · **BE-6 = MOTIF-suggest only** (arc-suggest is
Wave 4's) · **BE-M1** (partial UNIQUE index on `motif_application`) · **BE-M3** (motif-link REST) ·
🔴 **BE-7c → `W0-BE1` — the WORK-LESS JOB LANE, BUILT IN WAVE 0 (not here).** *(Was: "the owner-scoped
job read, MOVED INTO 3a".)* This wave ports `MotifMinePanel`, whose ⛏ Mine **500s at confirm** today
(§3.3 — **not** a 404, and **nobody is charged**). **3a's job is to VERIFY the lane landed** — through the
**producer** (a live `POST /actions/confirm` → 200 + a real `job_id` → a resolving poll), **not** with a
read-route test over a hand-seeded row (`fixtures-can-seed-a-field-the-writer-never-sets`). Build it here
only if Wave 0 did not — and then **all seven legs**, not just the read route. · **fix the 3 live 404s**
(§3.3), all by **deleting FE code**
**Spec:** `33_motif_studio.md` **Drafts:** 2 (library+graph; binding lens + conformance trace)
**Size:** **XL** — split into 3 shippable milestones: (3a) library + graph **+ verify `W0-BE1`** · (3b)
binding lens + motif-suggest · (3c) conformance trace + the 404 fixes.
⚠ **This wave stays SINGLE-SERVICE** (composition only): BE-6 is a REST route, **not** a
`FE_BRIDGE_TOOL_ALLOWLIST` entry — the allowlist's own contract is *"NOTHING here writes or deletes"*
and every member is spend-adjacent. Adding to it would make the wave cross-service (⇒ mandatory
live-smoke) for no benefit.
**Nobody is in these files** — the cleanest large lane available.

---

### Wave 4 — ARC TEMPLATES + 拆文

**Panel:** `arc-templates` (with an **Import & Deconstruct** section inside it)
**Gaps:** G-ARC-TEMPLATE-LIBRARY (L) · G-IMPORT-DECONSTRUCT (M)
**BE prereqs** *(AMENDED 2026-07-13)***:** BE-7a/BE-7b (2 cheap routes — **BE-7b is the SOLE owner of
arc-suggest**; spec 33's BE-M5 duplicate is deleted) · **BE-7c → `W0-BE1` is CONSUMED here but BUILT IN
WAVE 0** *(was: "Wave 3")* — **verify through the producer, don't re-build** (a green confirm → real
`job_id` → resolving poll; **not** a read-route test over a hand-seeded row) · **BE-8 is PARKED into its
own slice** and is now **agent-parity only** (the human's
drift view is **BE-NONE** — `?scope=arc_template_drift` **already ships**; only the agent's two
`_pending_engine` stubs are missing).
**Spec:** `34_arc_templates_and_deconstruct.md` **Drafts:** 1–2
**Size:** **L** · **Drop from scope:** *"mine motifs from this import source"* (REFUTED — §10).

---

### Wave 5 — PLANFORGE MADE HUMAN

**Panels:** `plan-passes` (new) + repair of the existing `planner`
**Gaps:** G-PLANFORGE-PASS-RAIL (L) · G-PLANNER-REPAIR (M)
**BE prereqs:** BE-2 (autofix) · BE-3 (**artifact read — exists in NO transport**) · BE-4 (delete a run)
**Spec:** `35_planforge_studio.md` **Drafts:** 1 (Pass Rail + the two checkpoint cards) — *a Planner
redesign HTML mockup already exists (2026-07-06) — start from it.*
**Size:** **L** · **Free win inside this wave:** wire `interpret`/`refine` **buttons** — routes and
api.ts methods already exist, **zero backend, zero risk.**
**Also fold in:** spec 27-**B1/B2** (the `planner_state.schema.json` POC-fixture taint + the missing
pass-artifact schema) — they are contract-hygiene debt in the same files.

---

### Wave 6 — THE EDITOR-CRAFT PORTS (and only then, spec-16 retirement)

**Panels:** `style-voice` · `reference-shelf` · `divergence` · a Composition section in `book-settings` ·
a decompose action + beats facet in `plan-hub`
**Gaps:** G-STYLE-VOICE (M) · G-REFERENCES-SHELF (S) · G-DIVERGENCE (M) · G-WORK-SETTINGS (S) ·
G-STORY-STRUCTURE (M)
**BE prereqs:** BE-10 (style/voice MCP tools) · BE-13 (divergence LIST/PATCH/DELETE) · BE-18 (the
settings-blob REPLACE fix) · BE-12 **only if** structure-template authoring is in v1 scope (PO decides
at CLARIFY) · BE-17 deferred to v2
**Spec:** `36_editor_craft_ports.md` **Drafts:** 2
**Size:** **L**
🔴 **GG-4 GATE: when this wave closes, and ONLY then, spec 16's `ChapterEditorPage` retirement may
proceed.** Retiring earlier deletes shipped features. Retirement must land with a **mechanical guard**
(a route assertion / hygiene test), not the current 18-line prose banner — this repo's own
`built-mounted-unreachable-duplicated-nav-list` memory says a comment is the weakest available guard.

---

### Wave 7 — THE ISSUES FEED (and the rest of the bottom panel)

**Surface:** the **existing** `StudioBottomPanel` — Issues tab (+ Jobs + Generation, which are equally
dark, in the same file, and the same shape of fix) + a `find-references` **lens** on entity badges
**Gap:** G-DIAGNOSTICS-ISSUES (M) **BE prereq:** BE-1
**Spec:** `37_issues_feed.md` **Drafts:** 1
**Size:** **M**
🔴 **BLOCKED ON A PO DECISION:** spec **28 AN-12 explicitly seals "No new GUI surface"** for these three
capabilities. Building this **requires amending AN-12**, not just implementing it. The gap is real
(**~2.5 of 5** diagnostic sources have **no** human surface at all, and **nothing** is ranked), so
AN-12's premise is demonstrably only partly true — **but shipping without the amendment is, in this
repo's own words, "a spec violation."** The proposal *honours* AN-12's architecture (bottom panel,
not a fork; a lens, not a panel); it only amends the "zero GUI" clause.

---

### Wave 8 — OUTSIDE COMPOSITION

**Panels:** KG write affordances (4, additive) · `world` container + `world-map` · `workflows` +
`workflow-proposals` + a mode-binding control
**Gaps:** G-KG-WRITE-HOLES (M) · G-WORLD-MAPS (L) · G-WORKFLOWS (M)
**BE prereqs:** BE-14 · BE-15 (**incl. an UPDATE design — it exists at no layer**) · BE-16
**Spec:** `38_kg_and_world.md` **Drafts:** 2 — ⚠ **RENAMED** (PO-2 dropped `G-WORKFLOWS` to Track C, so the `_workflows` suffix is dead; the file on disk is `38_kg_and_world.md`)
**Size:** **XL** · Split: (8a) KG holes — cheap · (8b) world container + maps · (8c) workflows.
🔴 **8c collides head-on with Track C's P-5.** Do not start it without an explicit ownership handoff (§9).

---

### The parallel lane — spec 29, translation repair

**Independent of all 8 waves. Start it whenever a lane is free.**
00C **Q-1**: *"None — unblocked now. Disjoint files from the whole 00B cluster."* Zero collision with
any of the three live tracks. **0 of T1–T10 built.** Phase A is **frontend-only**. **P0. Size L.**
It also carries a **Frontend-Tool-Contract violation** (T3/D13: `target_language` is a free string on the
MCP tool — a closed-set⇒enum breach) that this plan's own registration discipline forbids.

---

### Consciously OUT OF SCOPE (recorded so they stop re-surfacing)

| Item | Why |
|---|---|
| **Spec 10 — agent lifecycle hooks (0% built)** | A whole service (`agent-hook-runner` sandbox), a table, an orchestrator, a manifest format, a settings UI. **XL, and not a tool↔GUI gap.** Gate #2 (large/structural — needs its own plan). |
| **Spec 07S §3 — the `compaction_failed` breaker** | 🔴 **Genuinely alarming** (Agent Mode L3/L4 autonomous runs are shipped and running **without** the breaker the standard makes MANDATORY for headless runs) — but it is a chat-service/agent-standard concern, not a GUI gap. **Raise it as its own P1 defect row, do not smuggle it into this plan.** |
| **Spec 26-D3 — the arc decompiler** | The only path to a spec tree for an imported book with no plan. **L**, and a real design decision (Tier-W mint semantics). Its own spec. |
| **Spec 21-G2 — PlanForge propose is blind to book state** | **M.** Belongs with Wave 5's spec, but it is a *generation-quality* defect, not a GUI gap. Track it; don't inflate Wave 5 with it. |
| **The wiki inverse gap (GG-2)** | Zero `wiki_*` MCP tools. Real, but it is the **mirror** of this plan's goal. **One row, its own small spec.** |
| **The 10 shipped panels with no live E2E** (14b + 15a) | Real debt. Fold each wave's panels into that wave's live-smoke; do not retro-fit the old ones here. |

---

## 8 · Cross-cutting work — the per-panel registration checklist

**GG-8 — A NEW PANEL IS NOT DONE UNTIL ALL OF THIS IS DONE.** Two machine guards already red on drift
in *either* direction (`panelCatalogContract.test.ts`: enum **==** openable, sorted equality;
`test_frontend_tools_contract.py`: `CLOSED_SET_ARGS` ⇒ must be an `enum`). Current state:
**py enum 57 == contract enum 57 == openable 57, zero drift. Keep it that way.**

> **Decision gate first — is the panel openable by a BARE ID?**
> **No** (it needs a `node_id` / `motif_id` / `workflow_id`): mark `hiddenFromPalette: true`, do steps
> 1–2 **only**, and STOP. It stays out of the enum + contract (DOCK-6's sanctioned exception;
> `json-editor` precedent).
> ⚠ **This has a consequence several gaps assumed away** (§8.2 — X-12).

| # | File | What to add |
|---|---|---|
| 1 | `frontend/src/features/studio/panels/<NewPanel>.tsx` | The component. Root `data-testid="studio-<id>-panel"` (the tour/e2e selector convention). |
| 2 | `frontend/src/features/studio/panels/catalog.ts` | One `STUDIO_PANELS` row: `{ id, component, titleKey, descKey, category, guideBodyKey }`. **`category` is MANDATORY** (test reds) and **must be a member of `CATEGORY_ORDER`** (X-2 adds this assertion). **`guideBodyKey` is now mandatory too** (X-3). → auto-feeds the dock map, the Command Palette, and the User Guide. |
| 3 | `frontend/src/i18n/locales/en/studio.json` | `panels.<id>.title` / `.desc` / `.guideBody`. |
| 4 | `frontend/src/i18n/locales/{ar,bn,de,es,fr,hi,id,ja,ko,ms,pt-BR,ru,th,tr,vi,zh-CN,zh-TW}/studio.json` | Same 3 keys × 17 locales — **generate with `python scripts/i18n_translate.py`**, never hand-write. |
| 5 | `services/chat-service/app/services/frontend_tools.py` | **Two edits** in `UI_OPEN_STUDIO_PANEL_TOOL`: (a) append the id to the `panel_id` **enum** (~line 402); (b) append a per-panel clause to the tool **description** prose (~403–481) — that gloss is the model's **only** hint about the panel. |
| 6 | `contracts/frontend-tools.contract.json` | **NEVER hand-edit — regenerate:** `cd services/chat-service && WRITE_FRONTEND_CONTRACT=1 python -m pytest tests/test_frontend_tools_contract.py`, then **commit the regenerated JSON in the same commit** as steps 2 + 5. |
| 7 *(cond.)* | `frontend/src/features/studio/host/studioLinks.ts` | Only if a URL/deep-link should resolve to this panel inside the studio. |
| 8 **(MANDATORY for this batch)** | `frontend/src/features/studio/agent/handlers/*.ts` | Register `registerEffectHandler(<tool-name pattern>, handler)` so an agent write invalidates this panel's queries. **Normally "conditional" — for this batch it is mandatory and ~15 handlers wide (X-4).** |
| 9 *(cond.)* | `frontend/src/features/studio/onboarding/tours.ts` + `tourCatalog.ts` | Only if the panel is a role-tour step (needs `tourAnchor` from step 2). |

**Verify (all four green; the first two are the drift-locks):**
```
cd services/chat-service && python -m pytest tests/test_frontend_tools_contract.py tests/test_frontend_tools.py -q
cd frontend && npx vitest run \
  src/features/studio/panels/__tests__/panelCatalogContract.test.ts \
  src/features/studio/panels/__tests__/UserGuidePanel.test.tsx \
  src/features/studio/palette/__tests__/useStudioCommands.test.ts \
  src/features/chat/nav/__tests__/frontendToolContract.test.ts
```
**Then VERIFY BY EFFECT** — a live browser smoke that `ui_open_studio_panel {panel_id:"<id>"}` actually
mounts the dock tab. **A green unit suite does not prove the loop closed**
(`agent-gui-loop-needs-live-browser-smoke-not-raw-stream`). Precedent:
`studio-compose.spec.ts` / `studio-palette.spec.ts`.

**Do NOT touch:** `StudioDock.tsx`, `StudioFrame.tsx`, `useStudioCommands.ts`, `UserGuidePanel.tsx`
(all derive from `catalog.ts`); `studioUiNav.ts` / `useStudioUiToolExecutor.ts` (panel-id-agnostic).

### 8.0 THE PANEL-ID LEDGER — every new id in the batch, in one place *(cross-spec sweep, 2026-07-13)*

Specs 31–38 were written by **eight independent agents who could not see each other's work**. This table
is the reconciliation. **It is the source of truth for panel ids and categories across the whole batch.**
A ninth agent adding a panel adds a row **here first**.

| # | Panel id | Spec | Wave | `category` | ∈ `CATEGORY_ORDER`? | Notes |
|---|---|---|---|---|---|---|
| 1 | `quality-canon-rules` | 31 | 1 | `quality` | 🔴 **ONLY AFTER X-2** | quality-hub card 5 |
| 2 | `quality-corrections` | 31 | 1 | `quality` | 🔴 **ONLY AFTER X-2** | hub card 6 |
| 3 | `quality-heal` | 31 | 1 | `quality` | 🔴 **ONLY AFTER X-2** | hub card 7 |
| 4 | `progress` | 31 | 1 | `editor` | ✅ | **NOT** a quality-hub card (QC-2) |
| 5 | `arc-inspector` | 32 | 2 | `editor` | ✅ | |
| 6 | `motif-library` | 33 | 3a | `storyBible` | ✅ | |
| 7 | `quality-conformance` | 33 | 3c | `quality` | 🔴 **ONLY AFTER X-2** | hub card **8** (not 5 — Wave 1 took the hub to 7) |
| 8 | `arc-templates` | 34 | 4 | `storyBible` | ✅ | |
| 9 | `plan-passes` | 35 | 5 | `editor` | ✅ | |
| 10 | `style-voice` | 36 | 6 | `editor` | ✅ | |
| 11 | **`reference-shelf`** | 36 | 6 | `editor` | ✅ | ⚠ **NOT `references`** — that id collides with `composition_find_references` (§5.2, amended) |
| 12 | `divergence` | 36 | 6 | `editor` | ✅ | |
| — | *(none)* | **37** | 7 | — | — | Wave 7 adds **NO panel** — it wires the **existing** `StudioBottomPanel` Issues tab + a right-click **lens** (PO-1 / AN-12) |
| 13 | `world` | 38 | 8b | `storyBible` | ✅ | self-resolving from the book's `world_id` ⇒ **bare-id openable** (this is 38's answer to X-12) |
| 14 | `world-map` | 38 | 8b | `storyBible` | ✅ | takes `params.mapId` but **still self-resolves** a default |

**Checks run, results stated:**

1. **Collisions against the 68 existing `catalog.ts` ids: ZERO.** ✅ Every one of the 14 is new.
2. **Collisions among the 14: ZERO.** ✅
3. **Near-misses (two names for one concept): ONE, now FIXED.** `references` (this plan) vs
   `reference-shelf` (spec 36). Spec 36 is right and the plan is amended (§5.2). *(`quality-canon` vs
   `quality-canon-rules` is **not** a near-miss — they are the read half and the write half, and each
   deep-links into the other by `rule_id`.)*
4. 🔴 **CATEGORY DRIFT: no spec invented a new category — but FOUR panels land in `quality`, which is
   NOT in `CATEGORY_ORDER`.** This is **X-2**, and it is **still open at HEAD** (`useStudioCommands.ts:20-22`
   lists **9**; `catalog.ts:81-91` defines **10**). The failure modes are **inverted** — a *missing*
   category sorts LAST, an *unlisted* one sorts **FIRST** (`indexOf → -1`) — so today's shipped
   `quality` hub already sorts **above `editor`**, and this batch would add **three more rows** to it.
   **X-2 is a hard gate on Wave 1.** Spec 38 §3.2 gets full marks for *explicitly refusing* to invent a
   `world` category for exactly this reason and reusing `storyBible` instead.
5. **`hiddenFromPalette` / X-12: ZERO panels need it.** All 14 are **openable by a bare id**, so all 14
   enter the `ui_open_studio_panel` enum, the Command Palette and the User Guide. Two specs earned this
   by *designing for it* (38's self-resolving `world`; 32's picker + optional `focusArcId`) rather than
   falling back to `hiddenFromPalette`. **X-12 does not bite this batch.**
6. 🔴 **ENUM-COUNT BASELINE — the batch-wide bug.** Six of the eight specs computed their target count
   from the **same 57 baseline**, as if each were the only wave (`57→61`, `57→58`, `57→59`, `57→58`,
   `57→58`, `57→59`). **The waves are sequential; the counts are cumulative.** Only spec **36** got it
   right and said why: *"assert `N_before + k == N_after` and the three-way equality — **never a
   literal**"*, because a literal *"sends a builder hunting a phantom regression."* **All specs are
   amended to the delta form.** The true end state is **57 + 14 = 71** openable == 71 py enum == 71
   contract enum.

**The running baseline, for whoever builds next:**

| After wave | Panels added | `OPENABLE` == py enum == contract enum |
|---|---|---|
| HEAD `9262ed53e` | — | **57** |
| 1 (spec 31) | 4 | **61** |
| 2 (spec 32) | 1 | **62** |
| 3 (spec 33) | 2 | **64** |
| 4 (spec 34) | 1 | **65** |
| 5 (spec 35) | 1 | **66** |
| 6 (spec 36) | 3 | **69** |
| 7 (spec 37) | **0** | **69** |
| 8 (spec 38) | 2 | **71** |

⚠ **These are a PLANNING aid, not a test assertion.** A DoD asserts the **delta + the three-way
equality**, never a literal — if a wave is re-ordered or dropped, every literal below it is wrong.

### 8.0b Lane-B effect-handler homes — ONE FILE PER DOMAIN *(cross-spec sweep, 2026-07-13)*

`matchEffectHandlers` (`frontend/src/features/studio/agent/effectRegistry.ts:45`) returns **every**
matching handler and `runEffectHandlers` **awaits all of them**. So two specs registering overlapping
patterns in two files does **not** shadow — it **double-fires**, and gives one concept two homes. Two
such collisions were found and reconciled:

| Tool family | ❌ Was | ✅ Is | Owner |
|---|---|---|---|
| `composition_arc_*` | spec **32** → `bookEffects.ts`; spec **34** → a *new* `arcEffects.ts` — **both regexes match create/update/delete/restore** | **`arcEffects.ts`, one broad `/^composition_arc_/` registration.** Wave 2 **creates** the file; Wave 4 **extends its handler body** (adds the `arc-templates` query keys) — it does **not** register a second pattern. | 32 |
| `composition_*` (canon, corrections, style, voice) | spec **31** creates `compositionEffects.ts`; spec **36** *also* marks it **"(new)"** | **`compositionEffects.ts`.** Wave 1 **creates**; Wave 6 **extends**. | 31 |
| `composition_motif_*` | — | `motifEffects.ts` | 33 |
| `plan_*` | — | `planEffects.ts` | 35 |
| `composition_diagnostics` | — | `diagnosticsEffects.ts` | 37 |
| `world_map_*` | — | `worldEffects.ts` | 38 |

⚠ **`registerEffectHandler`'s string branch is `tool === p \|\| tool.startsWith(p)` — it is NOT a pattern
match.** Spec 36's first cut wrote `registerEffectHandler('composition_(style|voice)_', …)` as a **string**,
which would have matched **nothing** and shipped a **silent no-op handler** that no unit test (which
registers and calls its own fake) could ever catch. **Use a `RegExp` for anything with alternation.**
Fixed in 36; recorded here so it is not re-introduced.

### 8.1 Constraints inherited from spec 28 — DO NOT RE-LITIGATE

- **AN-8's edit-discipline table** — every object class already has ONE agent channel, ONE tier, ONE undo
  path. *"A reviewer finding a new confirmation convention here has found a defect."* A generic
  "expose every tool" surface is exactly what breaks this. **Every panel in this plan inherits the table.**
- **Tier W** tools execute **NOTHING**. The effect lives in `app/routers/actions.py` keyed on a descriptor
  (`composition.motif_adopt`, `.motif_mine`, `.arc_import`, `.conformance_run`, `.generate`, `.publish`,
  `.authoring_run_*`). A panel drives them through the **generic** `GET /actions/preview` →
  `POST /actions/confirm` pair — **never a per-action route.** (The 3 live 404s in §3.3 are exactly this
  mistake, already shipped.)
- **Tier A** tools return `_meta.undo_hint = {tool, args}` — honestly `None` where no faithful inverse
  exists. `composition_motif_bind`'s `undo_token` is the **only** exact-inverse path for unbind.
- **OCC everywhere**: `expected_version` on outline_node / canon_rule / motif / structure_node;
  `expected_draft_version` on prose. Memory `instant-commit-control-over-occ-entity-needs-write-serialization`
  applies to **any chip/select** over these.
- **Grant gating**: every by-id tool derives the book from the **ROW** (`_arc_or_deny`), never from a body
  `book_id`. Denial and missing row return the **SAME** `uniform_not_accessible()` (H13 — no enumeration oracle).
- **AN-9's pull-not-push discovery law** and **AN-10's `GROUP_DIRECTORY`** — ~160 federated tools are
  already categorized. **This plan needs a surface OVER the registry, not a new registry.**

### 8.2 Two structural traps the gap list assumed away

- **X-12 — ✅ ANSWERED (2026-07-13): `ui_open_studio_panel` GAINS an OPTIONAL `params` object.** Build it in
  Wave 0 (`W0-S5b`), paired with X-5 exactly as this row asked.
  **This row's premise — *"panels that need `params` are structurally OUTSIDE the agent enum"* — is FALSE,
  and the code refutes it:** `quality-canon` sits **inside** the `panel_id` enum
  (`frontend_tools.py:402`) while `QualityCanonPanel.tsx:33` already reads `props.params as
  CanonFocusParams`. A params-taking panel **is** agent-openable today. §8.0 check 5 confirms the other
  half: all 14 panels in this batch are **bare-id openable** and **zero** need `hiddenFromPalette`.
  **Because `params` is OPTIONAL, nothing leaves the enum / palette / User Guide and §8.0's ledger is
  untouched.** The pipe already exists below the agent (`StudioHostProvider.tsx:52` accepts `params`;
  `studioUiNav.ts:35` is the ONE line that drops them — the agent is the only caller in the repo that
  cannot pass them). And **sealed PO-3 cannot ship without it**: it retargets `ui_watch_job` onto
  `job-detail`, *"a singleton that retargets via params"* (`JobDetailPanel.tsx:1`).
  It remains a Frontend-Tool-Contract change (schema + contract regen + **both** resolvers). `params` is
  free-form ⇒ it correctly gets **no** `CLOSED_SET_ARGS` entry. See §11 item 1 (a′).
- **X-13 — `consumer_capabilities` (spec 09 G6) is the defense against the silent-no-op class we are about
  to multiply by 15 panels.** It is declared (`chat-service/app/models.py:502`) and **read by nothing**.
  It is the field that would let chat-service **stop advertising a frontend tool the current consumer
  can't execute.** Its sibling `contributeContext()` (`studio/host/types.ts:31`) is the pull-slice every
  new panel would use to feed the agent — also declared, **never called**. Both are the
  *stored-but-unread ⇒ write-only-behavior* class, and both are **load-bearing for this batch.**
  → Wave 0 stretch, or Wave 7 at the latest.

### 8.3 Design-draft house style (mandatory for every new panel mock)

`design-drafts/screens/studio/` has **24 self-contained dark-only HTML drafts** (the original 13 + the 11
added by this batch — count re-measured 2026-07-13; the prose said "13" long after the 11 landed) with a
**byte-identical `:root` token block**, Inter + JetBrains Mono, a **half-px type scale**, and a mandatory **CSS banner
comment** (WHY / ARCHITECTURE / **BACKEND WORK IMPLIED** / STATES / SCALE). There is **no README and no
shared stylesheet** — the convention lives only as copy-paste. The full extraction (tokens, layout
skeleton, the four annotation mechanisms, a copy-paste template, and an 11-point conformance checklist)
is in the audit's design-drafts inventory and **must be followed**:

**🔴 The `:root` core block, CANONICALIZED 2026-07-13 (cross-spec sweep).** The claim *"a byte-identical
`:root` token block"* was **aspirational, not true** — an audit of all 24 drafts found the *core* hues
(background / foreground / card / border / primary / secondary / muted / accent / success / warning /
info) genuinely identical everywhere, but **the destructive red had drifted FOUR ways**:

| Was | In | |
|---|---|---|
| `--destructive: #d9584f` + `--destructive-muted: #3a1f1c` | `chapter-browser`, `scene-browser` + **all 11 new drafts** | ✅ **the canon** (13 files) |
| `--danger: #d95d5d` + `--danger-muted: #3a1f1f` | `plan-hub-panel`, `plan-navigator` | ❌ different **name** *and* value |
| `--danger: #e85a5a` | `studio-agent-hooks`, `studio-agent-mode` | ❌ third value |
| `--destructive: #dc4e4e` | `writing-studio-frame` | ❌ fourth value — and **dead** (0 usages) |
| 🔴 **`--error: #e85a5a` + `--error-muted: #3d1a1a`** (7 usages) · a raw `#e85a5a` with **no token at all** · a raw `rgba(217,93,93,.2)` (**= `#d95d5d`, spelled in decimal**) · `--warn: #e8b87e` where canon is `--warning: #e8a832` | `studio-raw-editor`, `studio-agent-gui-bridge`, `studio-agent-mode`, `studio-agent-hooks`, `plan-hub-panel` | ❌ **the FIFTH+SIXTH drifts — found 2026-07-13 (X-8), NOT by this audit** |

> 🔴 **THIS TABLE'S OWN VERDICT WAS WRONG TWICE, AND THE REASON IS THE LESSON.**
> The audit above said the red *"drifted FOUR ways"* and that *"all 24 files are now normalized"*.
> **Both were false — because the audit grepped the token NAMES (`--danger`, `--destructive`).**
> A name-based grep is structurally blind to:
> 1. a drift wearing a **third name** — `--error: #e85a5a` (7 usages, `studio-raw-editor`);
> 2. a raw hex with **no token at all** — `#e85a5a` (`studio-agent-gui-bridge:74`);
> 3. a banned value **spelled in another notation** — `rgba(217,93,93,.2)` in `plan-hub-panel:99` **is
>    `#d95d5d`**, the very value this table swore had *"ZERO occurrences"*. The string `d95d5d` does not
>    appear in the file. **The grep was looking for a spelling, not for a colour.**
>
> **Restated truth (verified 2026-07-13):** **18 of 24** drafts define the canon destructive token; the
> other **6 have no destructive affordance and need none**. There is **no `--danger`, no `--error`, and no
> `--warn` alias.** Canon: **`--destructive: #d9584f` · `--destructive-muted: #3a1f1c` ·
> `--warning: #e8a832`.**
>
> 🔴 **AND IT IS NOW MACHINE-CHECKED — because a prose checklist demonstrably did not stop it**
> (`checklist-is-self-report-enforce-by-tests`). **`scripts/design-draft-token-lint.py`**, wired into the
> pre-commit hook beside `ai-provider-gate.py`, greps **by the COLOUR (HSL), not by the name**: RULE 1 bans
> every destructive/warning alias custom property; RULE 2 computes each hex/rgba literal's hue+saturation
> and fails any non-canon *destructive-signal red* — **including one nobody has written yet.** It reds on
> **32 violations across 5 files** at the pre-fix tree and is green now. **Do not add a colour to its
> allowlist to silence a finding.**

*(The original rename also surfaced a latent bug: `studio-agent-mode` referenced `var(--danger-muted)` that
its `:root` never defined — an undefined-var silent no-op. Fixed, and re-verified 2026-07-13: every file
that USES `var(--destructive-muted)` also DEFINES it.)*

**Token verdict on the 11 NEW drafts: ZERO drift.** All 11 carry the identical core block, all are
**dark-only** (no `prefers-color-scheme`, no `data-theme`, no light theme anywhere), and all **append**
domain tokens *below* the core under a comment — never edit into it. The convention held.

- Single self-contained `.html`; only external ref = the Google Fonts link. **Dark-only**, `body` bg `#0f0c0b`.
- Panel = a `.panel` card at **explicit px size** on a `padding:24px` page — *not* the dock frame.
- **Every claimed state RENDERED**, including the bug being replaced (`Before — today` / `After` `.mini` panels with `.strike` on unreachable fields).
- **Name the bug. Flag the backend cost up front, not silently.** Pre-empt the misreading the next agent will make (`.callout.bad`: *"What this mock does NOT propose."*).
- Realistic multilingual content, real counts, real relative times. **Never lorem.**

**Not yet drafted** (specs exist, no HTML): 07a/07b/07c, 11, 12, 13, 14a/14b/15b, 16–19, 23, 24, 25–29.
**Every panel proposed in this plan needs one.**

---

## 9 · Collisions & sequencing

**All three live tracks are on THIS branch (`feat/context-budget-law`), in THIS checkout.**
This is a shared-checkout multi-agent situation. **Never `git add -A`** — enumerate files
(`git commit -- <paths>`), and remember `git commit -- <path>` commits the **WORKING TREE**, not the index.

| Track | State | Collision | Rule |
|---|---|---|---|
| 🔴 **Track C** (agent discoverability / workflow rails) — `docs/plans/2026-07-12-track-c-completion-RUN-STATE.md` | Phases 1–3 done; **P-5 PARKED / next-up** | **P-5 explicitly claims: "workflow rack, binding UI, W8 onboarding fork, W10 world container, W11 reader".** ⇒ **G-WORKFLOWS (Wave 8c) collides head-on**, and its "W10 world container" **also touches G-WORLD-MAPS's host**. | **Do not start Wave 8b/8c without an explicit ownership handoff.** Either drop them from this plan or take them over in writing. |
| 🔴 **Uncommitted, mid-edit RIGHT NOW** (Track C's D8) | `frontend/src/features/chat/components/ToolApprovalCard.tsx`, `chat/hooks/useChatMessages.ts`, `chat-service/app/routers/tool_permissions.py`, **`chat-service/app/services/stream_service.py`** | **X-10 (AN-C2) touches `stream_service.py`.** | **DO NOT TOUCH these files.** Sequence X-10 **after** Track C lands. |
| 🟡 **Book-Package track** (specs 22–28) — `docs/plans/2026-07-12-book-package-RUN-STATE.md` | **DECLARED COMPLETE 2026-07-12** | Owns `plan-hub`, `scene-browser`, `scene-inspector`, `structure_node`, the compiler. **Its arc/motif MCP surfaces are what most of this plan consumes.** **G-ARC-SPEC-CRUD and G-MOTIF-BINDING both edit `PlanDrawer.tsx`.** Its one open **PO-DECIDE (SC11/PH12)** is unresolved. | Coordinate before editing `PlanDrawer.tsx` / `plan-hub`. Do **not** re-plan 22–28 — `00B_EXECUTION_ROADMAP.md` §2's "everything else in 22–28 is unbuilt" is **STALE**. |
| 🟡 **`QualityCanonPanel.tsx`** | Touched **today** (`d662bd97d`, D-04) | Wave 1 adds a sibling under the same hub. | Read its history first. Its `focusRuleId` deep-link seam is **already there** — use it, don't rebuild it. |
| 🟡 **Work Assistant track** | Phase 1 ~40% | knowledge-service diary/fact pipeline. **WS-1.10 is an FE surface.** | Avoid knowledge-service's diary/fact files. G-KG-WRITE-HOLES touches *entity/graph* files — verify before editing. |
| 🟢 **Genuinely un-colliding** | — | **spec 29 translation repair** (00C Q-1 — "disjoint files from the whole 00B cluster") · **the motif + arc-template library ports** (nobody is in `features/composition/motif/**`) · **the Planner panel** (Track C only *reads* PlanForge tool descriptions) | These are the safe lanes. Start here. |
| ⚠ **7 stale `lane/*` worktrees** | A finished KG-ontology `/warp` fan-out, still checked out | — | **Do not reuse those branch names.** |

**Sequencing summary:**
```
Wave 0 (foundations)  ──┬─▶ Wave 1 (quality)     ──▶ ┐
                        ├─▶ Wave 2 (arc inspector) ──▶ ├─▶ Wave 6 (editor-craft ports)
   X-7 gather_motifs ───┴─▶ Wave 3 (motif cluster) ──▶ ┘        │
                                                                ▼
                            Wave 4 (arc templates + 拆文)   spec-16 RETIREMENT
                            Wave 5 (planforge)                 (GG-4 gate)
                            Wave 7 (issues feed) ◀── PO: amend AN-12
                            Wave 8 (KG / world / workflows) ◀── Track C handoff

  ∥ spec 29 (translation repair) — parallel, disjoint, start any time
```

---

## 10 · Appendix A — REFUTED claims (do not re-raise)

Each of these **looked** like a gap and is not. Recorded with its evidence so no future session
re-litigates it.

| Claim | Verdict | Evidence |
|---|---|---|
| *"Canon-rule authoring gives you no way to write one"* | **REFUTED at the app level** | It IS authorable today via the **legacy** route `/books/:bookId/chapters/:chapterId/edit` (`App.tsx:134` → `ChapterEditorPage.tsx:779` → `CompositionPanel.tsx:836` → `DockSlot slot('canon')` → `CanonRulesPanel`). `canon` is a **fully registered tab** in the SubTab union / `ALL_TABS` / the default order — **not** an orphaned file. The true gap is a **STUDIO port**, narrower and cheaper than claimed. |
| *"`composition_daily_progress` is textbook write-only data"* | **REFUTED** | `ProgressPanel.tsx` is a **real, mounted, reachable** dock panel inside the legacy composition workspace, which **also does the writes** — the loop is CLOSED there and open only in the Studio. It **becomes** write-only when 00C Q-6 retires that page. |
| *"`composition_work.settings` has NO editor"* | **REFUTED for 4 of 7 keys** | `CompositionSettingsView.tsx` (legacy `settings` sub-tab) edits `default_model_ref` / `assembly_mode` / `narrative_thread_enabled`; `useWorldMap.ts:94-108` writes `settings.world_map`. Only `capture_correction_prose`, `critic_model_ref/_source`, `reference_embed_model_ref` are genuine silent hidden defaults. |
| *"`PATCH /works` REPLACES the blob ⇒ data loss on every write"* | **PARTIALLY REFUTED** | It IS a full-blob replace (`repositories/works.py:311`), but every FE caller **hand-merges** (`useSetWorkSettings`, `api.ts:439-445` carries the explicit warning). The residual defect is a **lost-update window** (no If-Match), not loss-on-every-write. Still fix it (BE-18). |
| *"Planner's `arc_id` is a bare text input; the button silently disables"* | **REFUTED — STALE** | Already fixed by `9c685c28a`: `PlanRunView.tsx:120-128` renders a `<select data-testid="plan-arc-picker">` fed from `run.arcs[]`, and `:114-116` renders an **explicit** no-arcs reason. The deferred row `D-PLANFORGE-GUI-AUDIT` is stale on this point — **amend it, don't re-do the work.** |
| *"`interpret`/`refine` are CONSUMED by the FE"* (the REST-inventory's verdict) | **REFUTED — false positive** | They exist in `plan-forge/api.ts:73,80` but `grep interpret\|refine` across `hooks/` + `components/` returns **ZERO**. Dead API-layer methods, **no button**. The DEFERRED row was right; the inventory matched the API layer, not the call sites. *(⇒ this is the cheapest win in the plan: buttons only.)* |
| *"`kg_create_node` has no REST route"* | **REFUTED** | `_handle_kg_create_node` (`graph_schema_tools.py:1711-1738`) calls `merge_entity(source_type="manual", provenance="human_authored")` — **the exact same repo call, same flags** as `POST /v1/knowledge/entities` (`entities.py:999`). The gap for node-create is **FE-only**. *(One real residual: the MCP tool resolves via `GrantLevel.EDIT` so a **collaborator** can write into the owner's scope; the REST route writes under the raw JWT with no grant path.)* |
| *"`composition_motif_mine` feeds off `import_source`"* | **REFUTED** | `_MotifMineArgs` (`server.py:2958-2973`) is `scope: Literal["book","corpus"]` — **there is no `import_source_id` field.** motif_mine mines your OWN corpus. **Drop the "mine motifs from this import" leg from Wave 4** or spec the backend arg first. |
| *"`composition_motif_mine` has no FE reach"* | **REFUTED** | It has a **full** propose→confirm→poll GUI: `MotifMinePanel.tsx` + `useMotifMine.ts` + `motifApi.minePropose/mineConfirm`, mounted at `MotifLibraryView.tsx:89` behind the "⛏ Mine" button, with a passing test. *(Adjacent real sub-gap: the FE never sends `promote_target`, so `book_shared` mined drafts are unreachable from the GUI.)* |
| *"The Studio's conformance RUN needs new backend routes"* | **REFUTED** | The generic `/actions/preview` + `/actions/confirm` spine **already** dispatches descriptor `composition.conformance_run` (`actions.py:75, 343 → _execute_conformance_run:714`). **Two of the three 404s are a pure FE invented-URL bug**, not a BE gap. |
| *"`composition_find_references` = `routers/references.py`"* | **REFUTED — name collision** | `routers/references.py` is the author's **research reference shelf** (`reference_source`, embeddings, LOOM T3.6). `composition_find_references` is **entity backlinks** over `EntityReferencesRepo` (spec 28 AN-3). The repo itself acknowledges the collision (`entity_references.py:14`). **A new backlinks route must NOT use `/works/{pid}/references` — that path is taken.** |
| *"`enrichment-sources` covers the reference shelf"* | **REFUTED** | Different service, different concept (`/v1/enrichment/*`, a license-tagged corpus). |
| *"`useWorldMap.ts` is book-service's world maps"* | **REFUTED** | It reads `work.settings.world_map` — a **composition** scene-graph node-position blob. Entirely unrelated to book-service's `world_maps`/`map_markers`/`map_regions` tables. |
| *"`agent-mode` panel is 0% frontend"* (00C Q-2) | **REFUTED — STALE** | `AgentModePanel.tsx` is in `catalog.ts:258` **and** in the `ui_open_studio_panel` enum. **Move Q-2 to 00C §3.** |
| *"Spec 01 promised a working Issues feed"* | **REFUTED** | 01 specs it as *"Tabs Jobs/Generation/Issues, **stub bodies**… **Frame real, content stub.**"* **The stub IS the spec, not a regression.** The gap is real — but it is a *new* ask, not an unkept promise. |
| *"`quality-promises` is a half-built read-only panel"* | **REFUTED — correctly read-only** | `narrative_thread` is generation-time-detected, not user-authored: `@router.(post\|patch\|put\|delete)` on threads returns **nothing** in composition-service. Read-only on **both** sides. |
| *"`kg-proposals` is a half-built read-only panel"* | **REFUTED — a router by design** | It deep-links each row to the panel that owns its accept/reject. |
| *"`plan-hub` has zero mutations"* (the panel inventory's ⚠) | **REFUTED — STALE** | `usePlanMoves.ts` / `usePlanNodeWrites.ts` ship real writes (moves/reorder/link/archive) as of spec 24-H5. **Motif is the one decoration with no write path** — which is precisely G-MOTIF-BINDING. |
| *"`structure_template` supports user-custom templates"* (the table's own advertisement) | **REFUTED** | The repo has exactly `list_for_user` + `get`. **No code anywhere can insert one.** Every user sees exactly the 6 built-ins, forever, until BE-12 is built. |
| *"D-DECOMP-KEY-COLLIDES-ON-SPEC-BRANCH fires for a divergence port"* | **REFUTED (dormant)** | Today's `POST /derive` does **not** copy `outline_node` rows. The tripwire fires **only** if the builder also adds spec-branching. Scope the panel to declare-spec + manage-overrides and it stays dormant. |

---

## 11 · Next actions (concrete, in order)

> 🔴 **§11 WAS STALE PROSE AND IS NOW REWRITTEN (X-8 / `W0-S10`, 2026-07-13).** Its old item 1 listed
> *"PO decisions (3, all blocking)"* — **all three were already sealed in §0**, and its old item 2 said the
> `resource_ref` section was "the first thing to write" (it is now **written**: `28_agent_native_studio.md`
> §AN-12.1). **§0 SEALED wins over §11 wherever they disagree. Nothing below blocks.**

**Immediately, before any code:**

1. **PO decisions — ALL SEALED (§0). Nothing here blocks. Do NOT re-litigate; re-read §0.**
   - **(a) X-5 → PO-3: RETIRE `ui_show_panel`**, fold into `ui_open_studio_panel`. It is a **cross-surface
     migration, not a delete** — the non-studio resolver at `frontend/src/features/chat/nav/uiNav.ts:115`
     must keep working (migrate it to `ui_open_studio_panel` + the studio interceptor, or give it an
     explicit non-studio path). Land with `test_frontend_tools_contract.py` + `panelCatalogContract.test.ts`
     green. Separately: **`ui_watch_job`** → add to `STUDIO_UI_TOOLS` + the interceptor → open `job-detail`.
   - **(a′) X-12 → ANSWERED (not a PO decision): `ui_open_studio_panel` GAINS an OPTIONAL `params` object.**
     Because `params` is **optional**, all 14 panels stay bare-id openable and stay in the enum/palette/User
     Guide — §8.0's ledger is untouched. The pipe **already exists below the agent**
     (`StudioHostProvider.tsx:52` takes `params`; `studioUiNav.ts:35` is the ONE line that drops them — the
     agent is the only caller in the repo that cannot pass them). **Sealed PO-3 cannot be implemented
     without it:** it retargets `ui_watch_job` onto `job-detail`, which is *"a singleton that retargets via
     params"* (`JobDetailPanel.tsx:1`). ⚠ **This OVERRULES the contrary "do NOT add a `params` arg" reading**
     that an earlier pass recorded: that reading answered only the `hiddenFromPalette` half of X-12 and was
     silent on the deep-link half. **Build the `params` arg** (Wave 0, `W0-S5b`).
   - **(b) AN-12 → PO-1: AMENDED**, Wave 7 proceeds (bottom-panel Issues tab + right-click lens, **no new
     dock panel**). The amendment is written into `28_agent_native_studio.md`.
   - **(c) Track C P-5 → PO-2:** workflows + mode-binding UI (**8c**) = **Track C's**.
     **Wave 8 = 8a (KG write holes) + 8b (world container + world-map), and 8b STAYS IN THIS PLAN**
     (`38_kg_and_world.md` is on disk per PO-4). ⚠ **Hand Track C this note:** *"the `world` container +
     `world-map` FE surfaces (your P-5 'W10 world container') are OWNED BY plan 30 Wave 8b, specced in
     `38_kg_and_world.md`. Drop W10 from P-5."*

2. ✅ **DONE — the AN-12 `resource_ref` section is WRITTEN**: `28_agent_native_studio.md` **§AN-12.1**
   (X-6 / `W0-S10`'s sibling `W0-S8`, 2026-07-13). It closes OQ-8 and is the **hard prerequisite** for Waves
   2, 3 and 7 that spec 28 demanded. ⚠ It **overrides OQ-8's own shape sketch** (8 **table-keyed** kinds, not
   the sketch's 5 row-`kind`-keyed ones) — read §AN-12.1b before building any consumer.

3. **Land Wave 0** — X-1 (AddModelCta), X-2 (CATEGORY_ORDER + the group label + 2 guards), X-3
   (`guideBodyKey`), X-4 (Lane-B effect registry + the coverage ledger), X-5 (retire `ui_show_panel`),
   X-7 (`gather_motif` packer lens — the **hard gate on Wave 3**), X-8 (doc hygiene), X-9 (the closed MCP
   sweep + 2 code fixes), **X-10 (AN-C2 — the Track C hold is DISCHARGED: `stream_service.py` is committed
   and clean at HEAD `9262ed53e`, which IS Track C's D8. §9's "DO NOT TOUCH" row is stale)**, X-12
   (`params`), X-13, plus the backend prereqs **`W0-BE1`** (ex-BE-7c — the paid-action defect: a **500 at
   confirm**, *not* a 404, and **nobody was charged**; fixed by the **Work-less job lane**, *not* by a job-read
   route — §3.3) and **BE-11** (canon restore).

**Then, specs + drafts BEFORE implementation plans (GG-6):**

| Order | Spec to write | HTML drafts to draw |
|---|---|---|
| 1 | `31_quality_completion.md` (Wave 1) | 1 multi-panel: `quality-canon-rules` + `progress` + `quality-corrections` + `quality-heal`, with the DOCK-8 hub row |
| 2 | `32_arc_inspector.md` (Wave 2 — this **is** spec 23-C3 / DBT-06) | 1: `arc-inspector` (identity · tracks · roster+bindings · derived span · open-promises rollup · provenance) + its PlanDrawer embed |
| 3 | `33_motif_studio.md` (Wave 3) | 2: (a) `motif-library` 3-tier browse + the motif-link graph; (b) the binding lens in `scene-inspector`/PlanDrawer + `quality-conformance`'s beat trace |
| 4 | `34_arc_templates_and_deconstruct.md` (Wave 4) | 1–2: `arc-templates` + the Import & Deconstruct section |
| 5 | `35_planforge_studio.md` (Wave 5) | 1: the **Pass Rail** + the two blocking checkpoint cards *(start from the existing 2026-07-06 Planner-redesign mockup)* |
| 6 | `36_editor_craft_ports.md` (Wave 6) | 2: `style-voice` + `reference-shelf`; `divergence` + the `book-settings` Composition section |
| 7 | `37_issues_feed.md` (Wave 7) | 1: the bottom panel's three real feeds + the find-references lens |
| 8 | `38_kg_and_world.md` (Wave 8) | 2: KG write affordances; `world` container + `world-map` |

**In parallel, any time:** kick off **spec 29 (translation repair)** — it is specced, PO-decided,
frontend-only for Phase A, and provably disjoint from every live track.

---

## Appendix B — the deferred rows this plan absorbs

| Row | Becomes |
|---|---|
| `D-MOTIF-LIBRARY-CRUD-GUI` | G-MOTIF-LIBRARY (Wave 3) |
| `D-ARC-TEMPLATE-CRUD-GUI` | G-ARC-TEMPLATE-LIBRARY (Wave 4) |
| `D-ARC-APPLY-MCP-WRAPPER` | BE-8 (Wave 4, parked slice) |
| `DBT-06` (23-C3 arc inspector) | G-ARC-SPEC-CRUD (Wave 2) |
| `D-PLANFORGE-GUI-AUDIT` | G-PLANNER-REPAIR (Wave 5) — **amend it: sub-gap 1 is stale** |
| `D-WS3-BINDING-GUI` | G-WORKFLOWS (Wave 8c) — ⚠ **or Track C P-5** |
| `D-QUALITY-CRITIC-HEAL-LINK` | G-POLISH-SELFHEAL (Wave 1) |
| `D-QUALITY-MOTIF-ROLLUP` | Wave 3 (conformance trace) |
| 00C **Q-1** | spec 29 (parallel lane) |
| 00C **Q-2** | ✅ **CLEARED — stale.** Agent Mode is built. |
| 00C **Q-3** (a)(b) | Wave 1 · (c) `threads` duplicate → **delete, don't port** |
| 00C **Q-4 / Q-5 / Q-6** (retirements) | **GATED on Wave 6 (GG-4)** |
| 00C **Q-7** (bottom panels) | Wave 7 |
| `D-ARC-DECOMPILER-STRUCTURE-NODE` | **out of scope** — its own spec |

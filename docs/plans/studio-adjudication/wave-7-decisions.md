# Wave 7 — Issues feed — adjudicated decisions

> 61 items · 55 DECIDED · 5 not-a-question · 1 deferred · 0 escalated.

> **These are INSTRUCTIONS, not suggestions.** Each was settled by reading source. Do not re-open a
> decided question. Where this contradicts the wave plan, **this file wins.**

---

## Deferred (tracked, non-blocking)

### Q-37-D1-PACKAGE-TREE-WONTFIX
WON'T-FIX stands — confirmed against code, not rubber-stamped. Builder instruction: (1) Do NOT build any "book at a glance" / package-tree panel. Zero rows in frontend/src/features/studio/panels/catalog.ts, zero additions to the panel_id enum, zero churn in contracts/frontend-tools.contract.json for composition_package_tree. It stays agent-only. The drift-lock (py enum == contract enum == openable) must be byte-identical after Wave 7 — spec 37 §6. (2) The premise was CHECKED and holds, unlike the diagnostics premise that got AN-12's clause lifted: the tool is self-declaredly "summary-shaped and hard-capped — ORIENTATION, not content" (server.py:3713-3721) and routes callers to other tools for real reads, so a panel would be a read-only mirror of organs the GUI already owns = exactly the DOCK-2 fork AN-12 exists to prevent. Two of three human equivalents ship TODAY: catalog.ts:190 plan-hub (spec tree), catalog.ts:183 chapter-browser (manuscript spine). (3) ONE GUARD TO ADD, and it is the only real content in this answer: the THIRD leg — the coverage gap — is carried by spec 24's PH21 "Unplanned chapters" tray, and PH21 IS NOT BUILT. Grepping the FE for it returns only ArcConformancePanel.tsx:225 (thread-progression, unrelated). So GG-1 ("every backend capability a user owns must have a human surface") is satisfied for the coverage-gap leg only by a spec promise. Therefore: mark PH21's unplanned-chapters tray as LOAD-BEARING for this won't-fix in spec 24 — it is a must-ship, not polish, and must not be trimmed. If spec 24 ever drops PH21, the correct remedy is to RESTORE THE TRAY INSIDE plan-hub, never to build a package-tree panel. Add one line to 37_issues_feed.md D-1 and to 24_plan_hub_v2.md PH21 recording this dependency, so the next agent who trims PH21 sees what it is holding up. (4) Note on the sealed decision, so no one thinks this contradicts §0: PO-1 (30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md:19) names all three tools in the lift, but its consequence column mandates a surface only for diagnostics + find_references, and the amendment PO-1 itself ordered written into spec 28 (28_agent_native_studio.md:266-269) explicitly keeps the clause for package_tree. The lift is PERMISSIVE, not mandatory. WON'T-FIX is consistent with PO-1. Do not re-open this as a gap.

**Defer row:** D-1 / Q-37-D1-PACKAGE-TREE-WONTFIX | origin: spec 37 §7.2 IF-5 (Wave 7) | WHAT: composition_package_tree gets no human surface — no panel, no catalog row, no panel_id enum entry. Its human equivalents exist: plan-hub (catalog.ts:190) = the spec tree, chapter-browser (catalog.ts:183) = the manuscript spine, spec 24 PH21 tray = the coverage gap. A "book at a glance" panel would be the DOCK-2 duplication AN-12 exists to prevent. | GATE: #5 conscious won't-fix (premise verified against code — the tool is self-declaredly orientation-only, server.py:3713-3721 — NOT the false-premise case that got the clause lifted for diagnostics/find_references). | TARGET/TRIGGER: none — permanent non-goal, do NOT re-open as a gap. RE-OPEN ONLY IF spec 24 drops PH21's unplanned-chapters tray (currently UNBUILT — it is the sole carrier of the coverage-gap human surface, so it is load-bearing for this won't-fix and must not be trimmed as polish); in that event the remedy is to restore the tray inside plan-hub, never to build a package-tree panel. ACTION THIS WAVE: add the load-bearing note to 24_plan_hub_v2.md PH21 + 37_issues_feed.md D-1.

## Decisions

### Q-37-OQ4-INDEX-STALE-IN-FEED
KEEP `index_stale` in the feed — take the spec's own recommendation, unchanged: severity `warn`, rendered INERT per IF-4 case 1. Do NOT drop it, do NOT downgrade it to `info`.

WHY the code settles it (not taste):
1. The backend ALREADY emits it. `composition_diagnostics` builds exactly ONE `index_stale` Diagnostic per book — a rollup, not one row per chapter — and only when the count is non-zero (`if stale:` — services/composition-service/app/mcp/server.py:4002-4008). Its severity is read from the FIXED map `SEVERITY["index_stale"] = "warn"` (services/composition-service/app/services/agent_native.py:70), whose docstring (agent_native.py:58-60) states severity is "Fixed, not computed — a diagnostics tool that ranked by its own judgement would be a second opinion competing with the engines". So "drop it from the feed" is not a no-op FE choice: it is the FE adding a client-side suppression filter for a kind the BE deliberately ships, which recreates the exact "two truths for what is wrong with this book" divergence that agent_native.py:47-52 exists to prevent (agent's problems view says 3, human's says 2). It also inverts plan 30's GG-1 law (§1): a backend finding reachable only by asking the agent, with no human surface, is the defect this whole plan is closing.
2. The noise objection does not survive the code. It is capped at ONE row per book, it exists only while `stale_chapter_count > 0`, and the sweeper (arc_conformance_orchestrate.py:364-393, 466-479) drives it to zero on its own — so it is a transient, self-clearing, single-row banner, not a recurring wall of warns. And it is the ONLY thing that explains a lagging conformance number, which is otherwise mysterious (the spec's stated rationale, §11 OQ-4).

BUILDER INSTRUCTION (M1, no further thought required):
- Backend: NO CHANGE. server.py:4002-4008 and agent_native.py:70 stay exactly as they are.
- FE `IssuesTab.tsx`: `index_stale` is a first-class row kind in the render list. It renders with the `warn` chip (severity comes from the payload — the FE never recomputes it), title = the BE's `title` ("N chapter(s) have a stale prose index"), secondary line = the BE's `detail` ("the sweeper heals these; re-indexing refreshes the canon windows"). It renders with NO chevron and is NOT clickable (IF-4 case 1: no panel owns the fix). It has NO `node_ref`, so it also has no target — reuse the exact same inert-row component path as the 3 FE-1 rows.
- Routing table (§4.1.1): `index_stale` keeps its row with Target = "—" and "n/a (inert by design)". It is NOT added to the routing map at all — an absent entry in the map is what makes it inert; do not give it a fallback target.
- Anti-regression: the FE must NOT filter any kind out of the payload. Add the guard test alongside the existing 3-inert-rows test: vitest in `IssuesTab.test.tsx` — feed a payload containing one `index_stale` diagnostic + one clickable kind; assert (a) BOTH rows render (count === 2, i.e. no kind is suppressed), (b) the `index_stale` row has no chevron and `onClick` does not fire / no `openPanel` is called, (c) its detail text contains "the sweeper heals". This is the same class of guard as the FE-1 no-chevron test M1 already requires.
- Unlike the 3 FE-1 rows, `index_stale` is inert FOREVER, not until M1b. Do NOT add it to FE-1's light-up list, and do not invent a "re-index" button for it in M1 (that would be a new paid/queued action with no spec and no cost gate — out of scope; §8.4's cost-gated action is Run conformance only).

DEFAULT-NOTE for the PO (veto-able): I picked the spec's recommendation over "drop it". If you disagree and want it gone from the human feed, the correct fix is NOT an FE filter — it is deleting the emission at server.py:4003-4008 so agent and human see the same book. Say the word and that is a 6-line delete.

*Evidence:* services/composition-service/app/mcp/server.py:4002-4008 (single `index_stale` rollup Diagnostic, emitted only when `stale_chapter_count > 0`, detail already says "the sweeper heals these"); services/composition-service/app/services/agent_native.py:70 (`SEVERITY["index_stale"] = "warn"`) + agent_native.py:58-60 (severity is FIXED, not computed — an FE that re-ranks or suppresses is a second opinion); services/composition-service/app/engine/arc_conformance_orchestrate.py:364-393,466-479 (the sweeper is real and drives the count to zero — the row is self-clearing); docs/specs/2026-07-01-writing-studio/37_issues_feed.md:254,285-289 (routing table row + IF-4 case 1); docs/specs/2026-07-01-writing-studio/30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md §1 GG-1 (every backend capability a user owns must have a human surface).

### Q-37-TRACK-OWNERSHIP-HANDOFF
**Answer (a): the handoff HAS happened. Edit all three files directly in M1b and M2. No coordination step, no handoff request, no parking. This adjudication IS the handoff record — cite it and proceed.**

The Book-Package track is COMPLETE and its files are free. Verified four ways, not taken from a doc note:
1. Plan 30 §9:716 marks the track "DECLARED COMPLETE 2026-07-12", severity 🟡 (verify-then-go) — NOT the 🔴 reserved in that same table for the one genuinely live collision (Track C's D8, "DO NOT TOUCH these files"). The spec already distinguishes these two cases; a builder must not read 🟡 as 🔴.
2. All three files are CLEAN in the working tree; their last commits (d662bd97d, 09f2d29b1, 58e89720f) are merged ancestors of HEAD. Nobody is mid-edit.
3. The 7 lane/* worktrees are STALE, not active: each is 0 commits AHEAD / ~1860 behind / 0 dirty files (the finished KG-ontology /warp fan-out §9's last row already names). They hold nothing.
4. The track's one open "PO-DECIDE (SC11/PH12)" that §9 flags is NOT an ownership hold on these files — RUN-STATE:366-386 shows it is a data-derivation policy question (server- vs client-side derivation in useActualState) and it was RESOLVED ("rolls SC11's sentence back to what BPS-11 actually decided").

BUILDER INSTRUCTIONS:
- **M1b (FE-1): UNBLOCKED.** Edit PlanHubPanel.tsx and ChapterBrowserPanel.tsx directly.
- **M2 (NodeBadges half): UNBLOCKED.** Build the lens by EXTENDING the existing deep-link seam at frontend/src/features/plan-hub/components/NodeBadges.tsx:25-43 — CanonBadge already receives `onOpenRef: PlanNodeData['onOpenRef']` and deep-links through it (wired end-to-end by A5/D-04). PO-1's "right-click lens on an entity badge" hangs off that same prop. Do NOT rebuild a new deep-link mechanism; A5's post-mortem was that the seam existed and nobody tested the JOIN.
- **Bonus clearance (prevents an identical second stall):** `PlanDrawer.tsx` — the file §9 actually names for G-ARC-SPEC-CRUD / G-MOTIF-BINDING — is cleared by the SAME owner and the SAME evidence. Do not stop on it either.
- **The one constraint that DOES survive** (from §9's header, and it is unrelated to ownership): this is a shared multi-agent checkout. NEVER `git add -A`; enumerate paths, and remember `git commit -- <path>` commits the WORKING TREE, not the index.

Sane-default note for PO veto: I cleared these files on verified evidence rather than escalating, because "is that track mid-edit right now?" is a pure state question that git answers definitively — and it answers NO. If the PO knows of an off-repo reason to hold plan-hub, this is the row to veto.

*Evidence:* docs/specs/2026-07-01-writing-studio/30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md:716 — Book-Package track "DECLARED COMPLETE 2026-07-12" (🟡, vs the 🔴 "mid-edit RIGHT NOW / DO NOT TOUCH" row above it for Track C's D8). Corroborated: `git status` clean on all 3 files; last commits d662bd97d / 09f2d29b1 / 58e89720f all ancestors of HEAD; all 7 lane/* worktrees are 0-ahead / 0-dirty / ~1860-behind (stale). The SC11/PH12 PO-DECIDE §9 flags is resolved at docs/plans/2026-07-12-book-package-RUN-STATE.md:366-386 and is a derivation-policy call, not a file hold. M2's lens seam already exists at frontend/src/features/plan-hub/components/NodeBadges.tsx:25-43 (CanonBadge's `onOpenRef` deep-link).

### Q-37-OQ3-BOOK-WIDE-VS-CHAPTER
BOOK-WIDE ONLY. Confirm the spec's recommendation and close OQ-3 — this is not a taste call, the code forbids the alternative. Builder instructions, verbatim:

1. BE-1 route `GET /v1/composition/books/{book_id}/diagnostics` takes `severity`, `kind`, `limit` — and **NO `chapter_id` param**. Do not add one.
2. `useDiagnostics.ts` query key = `['diagnostics', bookId, severity, kind]`. It **must not** read `activeChapterId` from the studio bus / editor. The hook has no chapter input at all.
3. `IssuesTab` toolbar = severity chips + kind select + Refresh. **No "This chapter" toggle.**
4. **BE-1a still lands in full** — `ref_kind` + `chapter_id` (where the source has it) + `rule_id`. It is required for the DEEP-LINK (IF-2 `focusRuleId`, IF-3's scene bus event whose `chapterId` is mandatory), NOT for filtering. Do not skip it on the strength of this decision.
5. Per-row `where` column shows the chapter (the "chapter shown per row" half of the recommendation): FE resolves the label client-side from the chapter list it already has loaded — composition-service does not own chapter titles (`outline.py:1206-1213` docstring, scope-separation). For the 5 chapter-less kinds render the honest target label (`plan ▸`, `quality ▸`, `—`) — **never a blank cell**, which would read as "no chapter" rather than "not chapter-scoped".
6. Do **not** add a chapter-proximity sort/boost either: `Diagnostics.ranked` is severity→recency and `SEVERITY` is fixed-not-computed by design (`agent_native.py:58-73`). If a "your open chapter" affordance is ever wanted, it is a **non-filtering visual marker only** (a dot when `row.chapter_id === activeChapterId`) that changes neither ordering nor counts.
7. **Regression guard (M1 DoD, add it as a literal test):** a vitest asserting the diagnostics query key contains no chapter id AND that switching the editor's open chapter does not change the row set or the chip counts. This is the guard against a later agent "helpfully" adding the filter back.

PO veto note: the default chosen is book-wide. If the PO later wants chapter scoping, the correct shape is NOT a filter but a second, separate read ("issues in this chapter"), because 5 of the 8 kinds have no chapter to scope by.

*Evidence:* services/composition-service/app/mcp/server.py:4002-4008 (`index_stale` — a single book-level aggregate Diagnostic, `node_ref` omitted) · :4064-4070 (`open_thread_debt` — same, `title=f"{len(threads)} open promise(s)"`) · :3990-4000 (conformance ×2 — `node_ref={"kind":"arc","id":arc["structure_node_id"]}`, no chapter) · :4093-4108 (`prose_deleted_spec_node`, ERROR severity) whose producer `services/composition-service/app/services/coverage.py:175-178` is documented as "spec nodes whose `chapter_id` no longer resolves to an ACTIVE chapter" — its chapter is deleted, so it can never match the open chapter. Only 3 of 8 kinds carry a live chapter: `canon_contradiction`/`broken_canon_rule` via `n.chapter_id` (services/composition-service/app/db/repositories/outline.py:1214, :1338) and `unplanned_chapter` (server.py:4123). Counts: services/composition-service/app/services/agent_native.py:126,148-150 — `counts` is the EXACT book-wide total the severity chips render ("this is what the agent reasons about"), and 37_issues_feed.md:701 (D-2, SEALED) keeps the filter server-side precisely so counts stay exact. Contradiction check vs plan 30 §0: none — PO-1 (wire the existing StudioBottomPanel Issues tab, zero new panels) is unaffected.

### Q-37-OQ5-X13-REHOME
RE-HOME X-13 TO WAVE 0 — fold it into the X-5/X-12 frontend-tool-contract slice. Wave 7 (spec 37) does NOT carry it. This is the spec's own recommendation and the code backs it: spec 37 adds zero frontend tools / panel ids / contributeContext consumers, while X-5 (retire ui_show_panel) + X-12 (params arg) already reopen frontend_tools.py + the contract + both resolvers. Wave 0 is EARLIER than Wave 7, so nothing lapses — the deadline tightens. It does not contradict PO-1..4 (PO-3 in fact creates the slice this rides on).

CONCRETE BUILDER INSTRUCTION (Wave 0, new slice "X-13 — close the dead consumer-capability surface", runs in the same commit as X-5/X-12):

1. BE — give ConsumerCapabilities a real field and READ it.
   a. services/chat-service/app/models.py:474-476 — `class ConsumerCapabilities(BaseModel): pass` becomes `frontend_tools: list[str] | None = None` (None = "no filter", back-compat for every existing caller).
   b. services/chat-service/app/routers/messages.py:544 — next to the existing `studio_context=body.studio_context.model_dump() if body.studio_context else None`, add `consumer_capabilities=body.consumer_capabilities.model_dump() if body.consumer_capabilities else None`. It is currently NOT forwarded at all.
   c. services/chat-service/app/services/stream_service.py:3257 — add the `consumer_capabilities: dict | None = None` param and thread it to the three advertise call sites (~:4170, :4188, :4213) that already pass `studio=bool(studio_context)`.
   d. services/chat-service/app/services/frontend_tools.py — in the builder that does `defs.extend(_STUDIO_UI_TOOLS)` (:689, gated by the studio surface at :384/:677), after assembling the frontend-tool defs, intersect them with `consumer_capabilities["frontend_tools"]` when it is non-None. Keep the existing studio_context-presence gate — it stays the coarse gate; this is the per-tool refinement (spec 09 G6 / H12).
   e. TEST (pytest, chat-service): a request carrying studio_context + `consumer_capabilities={"frontend_tools":["ui_focus_manuscript_unit"]}` must advertise `ui_focus_manuscript_unit` and must NOT advertise `ui_open_studio_panel`; omitting consumer_capabilities advertises both (no regression).

2. FE — CALL contributeContext() and POPULATE consumer_capabilities from the mounted registry.
   a. frontend/src/features/studio/host/types.ts:29,31 — `frontendTools?: string[]` and `contributeContext?: () => StudioContextSlice | null` are declared and consumed by NOTHING. In the StudioHost registry, add a selector that (i) unions `frontendTools` across all MOUNTED registrations plus the always-on host tools, and (ii) calls every mounted `contributeContext()` and merges the returned StudioContextSlice keys (activeChapterId / activeSceneId / selectionRange / qualityIssueRef), last-focused wins on conflict.
   b. frontend/src/features/chat/hooks/runChatStream.ts:53,137 — extend the studioContext arg type and the body build to also emit `consumer_capabilities: { frontend_tools: [...] }` from (a)(i); feed the merged slice from (a)(ii) into the studio_context the studio chat senders already build (ComposePanel.tsx:31, StudioPopoutHost.tsx). Mirror the type through Chat.tsx:20, useChatMessages.ts:94, ChatStreamContext.tsx:58.
   c. TEST (vitest): mount two panels, one registering `frontendTools:["ui_open_studio_panel"]` + a contributeContext returning `{activeChapterId}`, the other contributing a selection; assert the outgoing request body carries the merged slice AND `consumer_capabilities.frontend_tools` = the union. Unmount one → its tool disappears from the body.

3. SAME SLICE, free: `StudioContext.active_panel_ids` (models.py:470) is SENT by the FE and read by NOTHING in chat-service — the genuine sent-but-unread instance of this bug class. Either read it (it is the natural source for (2)(a)(i)'s tool union — panel id -> registration -> frontendTools) or delete it from the model + the four FE type mirrors. Do not leave it declared-and-unread.

4. DOC — amend plan 30 §8.2 X-13 bullet (line ~662): replace "→ Wave 0 stretch, or Wave 7 at the latest" with "→ Wave 0, folded into the X-5/X-12 contract slice (same file, same contract regen, same two resolvers). NOT Wave 7 — spec 37 adds zero frontend tools / panel ids / contributeContext consumers." Mark spec 37 §11 OQ-5 CLOSED with a pointer to that bullet, and update 00_OVERVIEW.md:93/:99's 🔴 dead-field notes to point at the Wave-0 slice.

FALLBACK THE PO MAY VETO: if Wave 0 slips X-13 for scope, the ONLY acceptable alternative is to DELETE the four dead symbols (ConsumerCapabilities + its SendMessageRequest field, active_panel_ids, StudioToolRegistration.frontendTools, contributeContext) rather than carry them further — a declared-and-unread field is the class CLAUDE.md bans. Do not defer them a third time.

NOTE FOR THE RECORD: the spec's premise is understated. consumer_capabilities is not merely "unread" — it is an EMPTY model (`pass`, no fields) that messages.py never forwards, so it could not carry a value even if the FE sent one. It has no consumer AND no producer. Nothing depends on it today, which is exactly why moving it costs nothing.

*Evidence:* services/chat-service/app/models.py:474-476 — `class ConsumerCapabilities(BaseModel): """Studio consumer capabilities stub — reconciler track #09.""" pass` (ZERO fields); declared at models.py:502 and NOT forwarded in services/chat-service/app/routers/messages.py:530-548 (studio_context/editor_context/book_context/admin_context are; consumer_capabilities is not) and zero hits in frontend/src. The gate it duplicates already exists: services/chat-service/app/services/frontend_tools.py:384 ("Advertised ONLY when the request carries studio_context") + :677-689 (`defs.extend(_STUDIO_UI_TOOLS)`). Its FE siblings are equally dead: frontend/src/features/studio/host/types.ts:29 (`frontendTools?: string[]`) and :31 (`contributeContext?: () => StudioContextSlice | null`) — zero call sites. Bonus dead field the spec missed: services/chat-service/app/models.py:470 `active_panel_ids` IS sent (frontend/src/features/chat/hooks/runChatStream.ts:53,137) and read by nothing in chat-service. Wave-0 landing site is open: docs/specs/2026-07-01-writing-studio/30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md:338 (X-5 in the Wave 0 table), :655 (X-12 "Decide this in Wave 0, alongside X-5 — it is the same decision surface"), and :576 ("hiddenFromPalette / X-12: ZERO panels need it … X-12 does not bite this batch") confirms Wave 7 has no consumer for X-13.

### Q-37-OQ1-AGENT-OPENS-ISSUES
DO NOT build `ui_toggle_bottom_panel`. Add ZERO frontend tools, ZERO panel ids in Wave 7. OQ-1 CLOSES as a conscious won't-fix (defer gate #5) — NOT a defer row to Wave 0. Rationale from code: (a) the agent already has `composition_diagnostics` (server.py:3934), and (b) it already has a deterministic "show me" — every Issues row's owning panel (`quality-canon`, `quality-promises`, `quality-coverage`, `quality-critic`, `plan-hub`) is ALREADY in the `ui_open_studio_panel` enum (catalog.ts:266-270 == frontend_tools.py:476-482). Adding a 13th, overlapping nav tool would (c) red spec 37's own DoD-5 (contract file must stay BYTE-IDENTICAL) and (d) contradict sealed PO-3, which retires `ui_show_panel` precisely because two overlapping nav tools make the model pick the wrong one ("one name for one concept"). Building the thing we are simultaneously retiring is wrong by construction.

The wave must instead make that existing path REAL, in two concrete edits (both outside the frontend-tools contract, so DoD-5 stays green):

EDIT A — `services/composition-service/app/mcp/server.py`, the `composition_diagnostics` description (currently lines 3936-3941). Append verbatim: "Each row carries `panel_id` — the Studio panel that owns that finding. To SHOW the user a finding, call `ui_open_studio_panel` with that `panel_id`. A row with `panel_id: null` has no owning panel — state it, do NOT try to open one. The same ranked list is in the Studio bottom panel -> Issues tab." This is a composition-service MCP description; it does NOT touch `contracts/frontend-tools.contract.json`.

EDIT B — the sentence above must not be a lie, so the payload must carry the routing. In `services/composition-service/app/services/agent_native.py`, add a nullable `panel_id: str | None` field to the `Diagnostic` dataclass and populate it from the kind->panel map. That map lives in ONE place (the BE row), and the FE Issues tab READS it off the row — do not duplicate a second kind->panel map in `IssuesTab.tsx` (repo lesson: `css-var-duplicated-across-two-consumers-drifts`). `panel_id` MUST be `null` for the 3 FE-1 inert rows (the `plan-hub` focus rows — OQ-2 proved `focusNodeId`/`focusArcId` are read by nothing) and for `index_stale` (OQ-4, no owning panel). Those are the same rows the FE ships INERT — one inert contract, both surfaces.

TEST (the machine-check that keeps Edit A honest) — `services/composition-service/tests/test_agent_native_diagnostics.py`: for every `Diagnostic` kind the engine can emit, assert `panel_id` is EITHER a member of the `panel_id` enum loaded from `contracts/frontend-tools.contract.json` OR explicitly `None` and in the declared inert set. A kind with a `panel_id` the agent cannot open is the `silent-success-is-a-bug` class shipped again. Plus DoD-5: assert `contracts/frontend-tools.contract.json` is unchanged by this wave.

PO VETO NOTE (default I picked, so you can overrule cheaply): if you later want a literal "open the Issues tab for me" affordance, it is ONE tool added inside Wave 0's already-happening contract regen (schema + `CLOSED_SET_ARGS` + regen + interceptor branch + lift `StudioBottomPanel`'s local `useState` tab into the chrome store) — not a new mechanism, and not a reason to hold Wave 7.

*Evidence:* services/composition-service/app/mcp/server.py:3934-3947 (`composition_diagnostics` exists; synonyms include "issues"/"problems panel" — the agent is NOT blind to this data) · frontend/src/features/studio/panels/catalog.ts:266-270 (`quality`, `quality-promises`, `quality-critic`, `quality-coverage`, `quality-canon` are real openable dock panels) · services/chat-service/app/services/frontend_tools.py:476-482 + :511 (those same 5 ids are already in the `ui_open_studio_panel` `panel_id` enum / `_STUDIO_UI_TOOLS`) · frontend/src/features/studio/components/StudioBottomPanel.tsx:8,13 (`type BottomTab`, `useState<BottomTab>('jobs')` — the tab is component-local, no store for a tool to drive) · frontend/src/features/studio/components/StudioFrame.tsx:160 (`chrome.bottomOpen && <StudioBottomPanel/>` — not a dockview panel, confirming `ui_open_studio_panel` structurally cannot mount it) · docs/specs/2026-07-01-writing-studio/37_issues_feed.md:518 (§6 step 6: contract must be BYTE-IDENTICAL = DoD-5) · docs/specs/2026-07-01-writing-studio/30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md:21 (sealed PO-3: retire the overlapping nav tool, "one name for one concept")

### Q-37-BE1-DIAGNOSTICS-ROUTE
BUILD IT — it is unbuilt work, not a blocker (no `/diagnostics` route exists in `services/composition-service/app/routers/`; grep confirms zero hits). Spec 37 §5.1 already fixes the shape; the only genuinely open sub-decisions are settled below. Builder recipe, in order:

**1. EXTRACT (do not fork) — `services/composition-service/app/services/agent_native.py`.** Add:
```python
async def build_diagnostics(*, pool, book_client, outline: OutlineRepo, book_id: UUID,
                            project_id: UUID | None, bearer: str, cap: int) -> Diagnostics
```
Move `server.py:3968-4130` into it VERBATIM — all six source blocks (conformance+index staleness, `OutlineRepo.canon_issues`, `OutlineRepo.rule_violations`, `NarrativeThreadRepo.list_open`, `compute_prose_deleted`, `compute_coverage`), each still wrapped in its `try/except Exception → diag.warnings.append(...)`. That try-wrapping IS the "NEVER 500 on a degraded source" requirement — satisfied by construction, nothing new to write. Keep the imports LAZY (inside the function, as server.py does) to avoid an import cycle back into engine/clients. Replace the two `mint_service_bearer(tc.user_id, …)` call sites with the injected `bearer` param. Keep the `pid is None` warning ("absent, not zero") verbatim.

**2. MCP tool becomes a caller.** `server.py:3950-4132` reduces to: `_gate(VIEW)` → `resolve_scope` → `cap = max(1, min(int(limit or 25), 100))` (keep — MCP has no validation layer) → `diag = await build_diagnostics(pool=pool, book_client=get_book_client(), outline=OutlineRepo(pool), book_id=bid, project_id=pid, bearer=mint_service_bearer(tc.user_id, settings.jwt_secret), cap=cap)` → `return {"book_id": str(bid), **diag.ranked(cap=cap)}`. Payload must stay byte-identical (test below).

**3. FILTERS live in `Diagnostics.ranked()` (agent_native.py:128), not in the route.** New signature: `def ranked(self, cap=_DIAG_CAP, *, severity: str | None = None, kind: str | None = None)`. Order is **sort → filter → cap** (this is the one thing §5.1 and D-2 state in two different words; I am sealing it): filter the `ordered` list after the severity/recency sort, then slice `[:cap]`. `counts` and `total` stay **UNFILTERED and exact** (they come from `self.counts` / `len(self.items)`); `refs_capped` is computed over the **filtered** set (`len(filtered) > cap`). Defaults `None/None` ⇒ today's behaviour unchanged ⇒ MCP payload byte-identical.

**4. NEW FILE `app/routers/diagnostics.py`** — `router = APIRouter(prefix="/v1/composition")`, mirroring `conformance.py:424-454`:
```python
@router.get("/books/{book_id}/diagnostics")
async def read_diagnostics(
    book_id: UUID,
    limit: int = Query(25, ge=1, le=100),
    severity: Literal["error", "warn", "info"] | None = Query(None),
    kind: Literal["canon_contradiction", "broken_canon_rule", "prose_deleted_spec_node",
                  "conformance_never_run", "conformance_dirty", "index_stale",
                  "unplanned_chapter", "open_thread_debt"] | None = Query(None),
    user_id: UUID = Depends(get_current_user),
    bearer: str = Depends(get_bearer_token),
    grant: GrantClient = Depends(get_grant_client_dep),
    outline: OutlineRepo = Depends(get_outline_repo),
    book: BookClient = Depends(get_book_client_dep),
) -> dict[str, Any]:
```
Body: `authorize_book(grant, book_id, user_id, GrantLevel.VIEW)` in a try — `except OwnershipError: 404 "book not found"` / `except InsufficientGrant: 403 "insufficient access"` (copy conformance.py:446-451 exactly; H13 uniform, no enumeration oracle) → `_work, pid = await resolve_scope(WorksRepo(get_pool()), book_id)` → `diag = await build_diagnostics(..., bearer=bearer, cap=limit)` → `return {"book_id": str(book_id), **diag.ranked(cap=limit, severity=severity, kind=kind)}`.
- **CLAMPED ONCE:** `Query(ge=1, le=100)` IS the clamp — out-of-range ⇒ 422. Do **NOT** re-clamp with `max(1, min(...))` in the route, and pass that ONE `limit` value as BOTH the `build_diagnostics(cap=)` (which drives the per-source row slices) and the `ranked(cap=)`. Two different cap values is exactly the bug `server.py:3966` was written to kill.
- **BEARER: the user's own JWT** via `Depends(get_bearer_token)` (precedent: `plan_overlay.py:238` + `:255` passing it into `compute_coverage`). Do **NOT** mint a service bearer in a user-facing route — that re-opens the `internal-route-driven-by-a-session-must-grant-check` hole.
- Hard-code the `kind` Literal as a `Literal` built from the 8 SEVERITY keys (or `Literal[tuple(SEVERITY)]`-equivalent); a free string here is the closed-set-arg bug.
- The `kind` enum has EIGHT members (agent_native.py:60-73) — the spec text says "the SEVERITY keys"; that is 8, not 7.

**5. REGISTER:** `app.include_router(diagnostics.router)` in `main.py` right after line 244 (`conformance.router`). Zero gateway work — `gateway-setup.ts:354`'s composition `pathFilter` is prefix-generic.

**6. BE-1a widening goes INSIDE `build_diagnostics`** (one implementation ⇒ MCP + REST both get it): every `node_ref` gains `ref_kind` ∈ {`chapter`,`outline_node`,`structure_node`} — arcs ⇒ `structure_node` (`arc["structure_node_id"]`), scene rows (canon_contradiction, broken_canon_rule) ⇒ `outline_node`, prose_deleted ⇒ per `n["kind"]`, unplanned ⇒ `chapter` + `chapter_id`; `broken_canon_rule` also carries `rule_id`. Update `tests/unit/test_agent_native.py:254`'s SEVERITY-coverage loop to also assert `ref_kind` is in the closed set for every emitted node_ref.

**7. TESTS — `services/composition-service/tests/unit/test_diagnostics_route.py`:** (a) 404 on OwnershipError, 403 on InsufficientGrant; (b) **degraded-source test** — patch `compute_coverage` to raise ⇒ 200 with the warning string present and `counts` carrying NO `unplanned_chapter` key (omitted, not `0`) — never 500; (c) filter test — `?severity=error` ⇒ every item is error AND `counts` still contains the warn/info keys and `total` is unchanged; (d) `?limit=0` and `?limit=101` ⇒ 422; (e) **parity test** — the same `Diagnostics` object through the route and through the MCP tool yields identical `items/counts/total/refs_capped`.

If the PO disagrees with anything here, the one taste call to veto is #3's `refs_capped`-over-the-filtered-set (the alternative — refs_capped over the unfiltered set — would make a filtered view claim it truncated when it did not).

*Evidence:* services/composition-service/app/mcp/server.py:3950-4132 (the whole ~180-line source fanout to extract; :3966 = the single clamp `cap = max(1, min(int(limit or 25), 100))`; :4132 `return {"book_id": str(bid), **diag.ranked(cap=cap)}`) · services/composition-service/app/services/agent_native.py:60-73 (SEVERITY — 8 keys = the `kind` enum) and :128-153 (`Diagnostics.ranked()` — counts exact/uncapped, refs_capped, warnings-if-present) · services/composition-service/app/routers/conformance.py:424-454 (the mirror route: `APIRouter(prefix="/v1/composition")` at :63, authorize_book VIEW → OwnershipError⇒404 / InsufficientGrant⇒403 at :446-451) · services/composition-service/app/routers/plan_overlay.py:238 + :255 (`bearer: str = Depends(get_bearer_token)` → `compute_coverage(book_id, bearer, …)` — the user-JWT precedent) · services/composition-service/app/main.py:244 (register point) · grep: no `diagnostics` route exists under app/routers/ today.</evidence>
</invoke>


### Q-37-D2-SERVER-SIDE-FILTERS
SERVER-SIDE — confirmed by the code, do not simplify to the client. The ranking makes the bug reachable today: Diagnostics.ranked() sorts error→warn→info THEN caps, so with 30 errors and cap=25 every info row is already off the array before it reaches the client — a client-side Info-chip filter would render 0 rows while `counts` says 12.

BUILDER INSTRUCTION (BE-1, M1):
1. services/composition-service/app/services/agent_native.py:128 — widen to `def ranked(self, cap=_DIAG_CAP, severity: str | None = None, kind: str | None = None)`. Order inside MUST be: filter self.items by severity/kind → sort by (_RANK, _neg_ts) → shown = filtered[:cap]. (Filter BEFORE the cap.)
2. `counts` stays `dict(self.counts)` — accumulated in add() (agent_native.py:124-126) over ALL items, NEVER filtered. Set `refs_capped = len(filtered) > cap` (it must describe the view actually shown). Keep `total = len(self.items)` (unfiltered; the existing MCP consumer reads it) and add `filtered_total = len(filtered)`.
3. ADD `severity_counts` to the payload, derived from SEVERITY (agent_native.py:60-73) over ALL items: {"error": n, "warn": n, "info": n}. Reason: `counts` is KIND-keyed but the §8 toolbar chips ("Error 2 · Warn 5 · Info 1") are SEVERITY-keyed — without this the FE must re-implement the kind→severity map (the css-var-duplicated-across-two-consumers-drifts bug class). This is a sane default added on top of the sealed D-2; PO may veto it and instead ship the SEVERITY map to the FE.
4. Default args keep the sole existing caller `mcp/server.py:4132` (`diag.ranked(cap=cap)`) byte-identical — no back-compat break to the MCP tool.
5. Route `GET /v1/composition/books/{book_id}/diagnostics` passes `severity` (Literal["error","warn","info"]) and `kind` (validated against SEVERITY.keys() — closed set ⇒ enum, 422 on unknown, never a silent empty list) into ranked(). FE `IssuesFeed` REFETCHES on chip change and must NEVER `.filter()` the returned `items`; chips render from `severity_counts`, never from `items.length`.
6. GUARD TEST (services/composition-service/tests/unit/test_agent_native.py, beside the existing ranked tests at :210/:225): seed 30 `canon_contradiction` (error) + 12 `open_thread_debt` (info); assert ranked(cap=25, severity="info") returns 12 rows (NOT 0), counts["open_thread_debt"] == 12, counts["canon_contradiction"] == 30, severity_counts == {"error": 30, "info": 12}, refs_capped is False. Also assert ranked(cap=25) unfiltered gives 25 rows + refs_capped True. This test reds the instant a later agent moves the filter to the client or filters `counts`.

*Evidence:* services/composition-service/app/services/agent_native.py:128-152 — `ranked(cap)`: `ordered = sorted(items, key=(_RANK[severity], _neg_ts(at)))`; `shown = ordered[:cap]`; `"counts": dict(self.counts)` with the docstring "The counts are the EXACT totals; only the item rows are capped." · agent_native.py:124-126 — `add()` accumulates `self.counts[d.kind] += 1` over every item · agent_native.py:60-73 — `SEVERITY` (kind→severity closed set; counts are kind-keyed, chips are severity-keyed) · agent_native.py:74 — `_RANK = {"error":0,"warn":1,"info":2}` (the sort that makes client-side filtering lossy) · services/composition-service/app/mcp/server.py:4132 — `return {"book_id": str(bid), **diag.ranked(cap=cap)}` (sole existing caller; default args keep it unchanged) · spec docs/specs/2026-07-01-writing-studio/37_issues_feed.md:480-482 (§5.1 item 3) and :701 (§11 D-2 "DECIDED — do not simplify")

### Q-37-IF1-ENUM-MUST-STAY-3
CONFIRMED BY CODE — `ref_kind` is a 3-member closed set, exactly: `chapter | outline_node | structure_node`. Do NOT add `scene` or `canon_rule`. The concern is correct on both counts and the spec's §3 IF-1 text stands as written; the builder's job is the MAPPING, which is now fully specified below (no thought required at 3am).

BE-1a — in BOTH the new REST route and the back-ported MCP tool (`services/composition-service/app/mcp/server.py`, `composition_diagnostics`, lines 3950-4130), every `node_ref` gains `ref_kind` alongside the existing `kind` (`kind` = DISPLAY label, `ref_kind` = ROUTING key / id space). Map each emitter EXACTLY:

1. `conformance_dirty` + `conformance_never_run` (server.py:3995-4002) — id is `arc["structure_node_id"]` ⇒ `ref_kind: "structure_node"`, keep `kind: "arc"`.
2. `canon_contradiction` (server.py:4019-4026) — id is `issue["scene_id"]`, which `OutlineRepo.canon_issues` produces as `SELECT n.id AS scene_id … FROM outline_node n` ⇒ `ref_kind: "outline_node"`, keep `kind: "scene"`. ALSO add `chapter_id: issue["chapter_id"]` (IF-3 needs it; the repo already returns it — outline.py:1218/1248).
3. `broken_canon_rule` (server.py:4044-4051) — id is `item["scene_id"]`, same `outline_node n` select (outline.py:1341) ⇒ `ref_kind: "outline_node"`, keep `kind: "scene"`. `rule_id` and `chapter_id` are SIBLING fields on the Diagnostic (IF-2), NOT a node_ref — the repo already returns both (outline.py:1343). Never emit `ref_kind: "canon_rule"`.
4. `prose_deleted_spec_node` (server.py:4093-4095) — id is `n["id"]`, an `outline_node.id` ⇒ `ref_kind: "outline_node"` (a LITERAL, replacing today's free-string `n.get("kind") or "chapter"`, which is the exact IF-1 collision: an outline_node whose `kind` column is the string "chapter" currently emits `kind:"chapter"`, indistinguishable from a book-service chapter_id). Keep the row's own `kind` column as the display `kind`.
5. `unplanned_chapter` (server.py:4123-4127) — id is `ch["chapter_id"]`, a BOOK-service chapter id ⇒ `ref_kind: "chapter"`, keep `kind: "chapter"`.
6. `index_stale`, `open_thread_debt` — emit no `node_ref`; nothing to do.

DoD-1 test (per the spec, add to `services/composition-service/tests/unit/test_mcp_server.py` + the new route's test): assert the `ref_kind` enum literal is a 3-tuple/Literal of exactly `("chapter","outline_node","structure_node")`, and that a fixture exercising all 6 node_ref-bearing emitters produces only those 3 values — i.e. `assert set(r["node_ref"]["ref_kind"] for r in items) <= {"chapter","outline_node","structure_node"}` AND `"scene" not in …` / `"canon_rule" not in …`. Register `ref_kind` in `CLOSED_SET_ARGS` per the Frontend-Tool Contract if it becomes a tool ARG anywhere; as an OUTPUT field, pin it with a `Literal[...]` in the response model so a 4th member cannot be added silently.

Rationale (grounded, not taste): (a) `scene` is not an id space — it is the `kind` COLUMN VALUE of an `outline_node` row; carrying both names one id space twice, which is what IF-1 exists to kill and a breach of one-name-one-concept. (b) `canon_rule` is emitted by nothing — `rule_id` lives as a sibling column on the violation row, so the member would be dead enum surface (the over-advertising defect class). Three id spaces exist ⇒ three members.

*Evidence:* services/composition-service/app/db/repositories/outline.py:1218 (`SELECT n.id AS scene_id, n.title AS scene_title, n.chapter_id … FROM outline_node n` — canon_issues) and :1341-1343 (`n.id AS scene_id … v.violation ->> 'rule_id' AS rule_id` — rule_violations; rule_id is a SIBLING, never an identity) prove a "scene" IS an outline_node and no canon_rule id space exists. Emitters: services/composition-service/app/mcp/server.py:3998-4000 (structure_node_id → kind "arc"), :4023 (scene_id → kind "scene"), :4047 (scene_id → kind "scene", rule_id dropped), :4093-4095 (outline_node id → free-string kind, the collision), :4125-4126 (book-service chapter_id → kind "chapter"). Severity map / the 8 kinds: services/composition-service/app/services/agent_native.py:60-73; Diagnostic.node_ref is an untyped dict at agent_native.py:105-112 (why the enum must be pinned in the response model).

### Q-37-IF1-REFKIND-ID-SPACE-COLLISION
REAL BUG — build the `ref_kind` fix exactly as spec 37 §3 IF-1 states (3-member closed set), with two code-grounded refinements the spec leaves open. No sealed decision (§0 PO-1..4) is touched.

VERIFIED IN CODE — exactly three id spaces exist behind `node_ref.id`:
  1. book-service `chapter_id`  — `unplanned_chapter` (server.py:4125, id = `ch["chapter_id"]` from `compute_coverage`)
  2. composition `outline_node.id` — `prose_deleted_spec_node` (server.py:4099, id = `n["id"]` from `OutlineRepo.linked_chapter_nodes`, `SELECT id, title, kind, chapter_id … FROM outline_node`, outline.py:317) AND `canon_contradiction` (server.py:4025, `issue["scene_id"]` = `n.id AS scene_id … FROM outline_node n`, outline.py:1218) AND `broken_canon_rule` (server.py:4047, same `scene_id` source, outline.py:1338)
  3. composition `structure_node.id` — `conformance_dirty` / `conformance_never_run` (server.py:3998, `arc["structure_node_id"]`; arc_conformance_orchestrate.py:55 "arc IS a structure_node")
So `scene` is NOT a 4th space (it is an outline_node) and no diagnostic emits a `canon_rule` node_ref. The spec's 3-member set is correct — do not re-add `scene`/`canon_rule`.

BUILDER INSTRUCTIONS (concrete):

(1) `services/composition-service/app/services/agent_native.py` — add
    `REF_KINDS: Final[frozenset[str]] = frozenset({"chapter", "outline_node", "structure_node"})`
    and give `Diagnostic` (line 108-115) a `__post_init__` that raises `ValueError` if
    `node_ref` is set and `node_ref.get("ref_kind") not in REF_KINDS`. This makes a 4th id space
    IMPOSSIBLE to add silently — it is the guard, not the enum. `Diagnostics.ranked()` already
    passes `node_ref` through verbatim (agent_native.py:143), so no change there.
    `kind` REMAINS the DISPLAY label ("arc"/"scene"/"chapter"); `ref_kind` is the ROUTING key.

(2) `services/composition-service/app/mcp/server.py` — edit the 5 emitters (back-port to the MCP
    tool too, not just the REST mirror — one payload, one contract):
      · :3998 conformance → `{"kind":"arc","ref_kind":"structure_node","id":arc["structure_node_id"],"title":…}`
      · :4025 canon_contradiction → `{"kind":"scene","ref_kind":"outline_node","id":issue["scene_id"],"title":…}` + `chapter_id` (source HAS it: `n.chapter_id`, outline.py:1218) — omit the key when NULL, never emit `null`
      · :4047 broken_canon_rule → same as :4025 (+ the IF-2 `rule_id` sibling, adjudicated separately)
      · :4099 prose_deleted_spec_node → `{"kind": n.get("kind") or "chapter", "ref_kind":"outline_node", "id": n["id"], …}`
      · :4125 unplanned_chapter → `{"kind":"chapter","ref_kind":"chapter","id":str(ch["chapter_id"]), …}`

(3) REFINEMENT A (overrides a literal reading of BE-1a's "plus chapter_id where the source has it"):
    `prose_deleted_spec_node` MUST NOT emit `chapter_id`, even though the row carries one.
    By construction that chapter is GONE — coverage.py:212 computes `dangling = [n for n in linked
    if str(n["chapter_id"]) not in active]`. Emitting it hands the FE a guaranteed-404 deep-link
    target, i.e. re-creates IF-1's exact failure through the sibling field. If a future consumer
    needs it, name it `deleted_chapter_id` — never `chapter_id`. Add that as a code comment.

(4) REFINEMENT B: FE routes on `ref_kind` ONLY. Type it `type RefKind = 'chapter'|'outline_node'|'structure_node'`
    in the studio Issues-feed types; the routing table's key is `ref_kind` (never `kind`), and an
    unmapped `ref_kind` returns null ⇒ the row renders INERT (no chevron, not clickable) per spec
    §4.1.1. A FE that switches on `kind` is a review finding.

(5) TESTS (`services/composition-service/tests/unit/test_agent_native.py`, which today asserts
    nothing about node_ref): (a) every emitted `node_ref` carries a `ref_kind` in the 3-set;
    (b) `unplanned_chapter.ref_kind == "chapter"` and its `id` == the book-service chapter_id,
    while `prose_deleted_spec_node.ref_kind == "outline_node"` and its `id` == the outline_node.id
    (NOT its chapter_id) — the two rows in one payload, asserting disjointness explicitly;
    (c) `prose_deleted_spec_node` has NO `chapter_id` key; (d) constructing a `Diagnostic` with
    `ref_kind:"scene"` raises ValueError.

Cost of doing it now = ~30 lines across 3 files. The payload has zero consumers today (M1 is the
first), so this is a free fix now and a cross-service-normalization bug forever after.

*Evidence:* services/composition-service/app/mcp/server.py:4125 (`node_ref={"kind":"chapter","id":str(ch.get("chapter_id"))}` — book-service id) vs :4099 (`node_ref={"kind": n.get("kind") or "chapter", "id": n["id"]}` — composition outline_node id, from OutlineRepo.linked_chapter_nodes, services/composition-service/app/db/repositories/outline.py:316-321 `SELECT id, title, kind, chapter_id, story_order FROM outline_node`). Third space: server.py:3998 `arc["structure_node_id"]` (app/engine/arc_conformance_orchestrate.py:55 "arc is a structure_node"). `scene` is not a 4th space: outline.py:1218 `SELECT n.id AS scene_id … FROM outline_node n`. Dangling-chapter proof for refinement A: app/services/coverage.py:210-213.

### Q-37-IF2-RULEID-DROPPED
CONFIRMED — build BE-1a exactly as the spec states it (`broken_canon_rule` gains `rule_id` + `chapter_id` as SIBLING fields, not a node_ref). The concern is accurate: the repo already returns both keys and the handler discards them because the `Diagnostic` carrier has no field for them. Three edits, all additive:

(1) `services/composition-service/app/services/agent_native.py:107-114` — add two optional fields to the `Diagnostic` dataclass:
    `rule_id: str | None = None`
    `chapter_id: str | None = None`

(2) `services/composition-service/app/services/agent_native.py:139-147` — emit them in `Diagnostics.ranked()`'s item dict using the SAME conditional-spread pattern already used for `detail`/`node_ref`/`at`:
    `**({"rule_id": d.rule_id} if d.rule_id else {}),`
    `**({"chapter_id": d.chapter_id} if d.chapter_id else {}),`
    This is load-bearing: absent MUST stay absent. A violation whose judge JSON carried no `rule_id` (the `LEFT JOIN canon_rule` miss — the row whose title already reads "a rule that no longer exists") must OMIT the key, never send `null`/`""`. A `focusRuleId: null` in the FE would match `r.rule_id === focusRuleId` against other unattributed rows and hoist the wrong ones.

(3) `services/composition-service/app/mcp/server.py:4043-4050` — pass them through in source (2b):
    `rule_id=item.get("rule_id"), chapter_id=item.get("chapter_id"),`
    Keep `rule_text` in the `title` string as-is (the agent reads it) and keep `node_ref={"kind":"scene","id":item["scene_id"]}` pointing at the outline node. Per spec 37 §3 IF-1's explicit ruling, `canon_rule` is NOT a `ref_kind` member — `rule_id` rides as a sibling field. Do NOT drop rows whose `rule_id` is None; the violation is still real, it just isn't deep-linkable.

SCOPE EXTENSION (do it in the same edit, PO may veto): while `Diagnostic` is open, also pass `chapter_id=issue.get("chapter_id")` on the `canon_contradiction` row at `server.py:4025`. `OutlineRepo.canon_issues` already returns it (`outline.py:1214`) and IF-3 needs it for the `publish({type:'scene', sceneId, chapterId})` bus event, whose `chapterId` is REQUIRED by `host/types.ts`. Splitting this across waves means widening the `Diagnostic` dataclass twice for one bug class. Default = do both now.

FREE CONSEQUENCE: the BE-1 REST route returns `Diagnostics.ranked()` byte-identical, so it inherits the widening with zero extra work. The `composition_diagnostics` MCP tool declares no output schema (`server.py:3934-3949`), so the back-port is additive and cannot break an existing consumer.

TESTS (name them in the slice; `services/composition-service/tests/unit/test_agent_native.py` has ZERO `rule_id` coverage today — verified by grep):
  a. a `broken_canon_rule` item carries `rule_id` == the seeded violation's rule id and `chapter_id` == the scene's chapter;
  b. a violation with no `rule_id` in its judge JSON produces an item where the `rule_id` KEY IS ABSENT (`"rule_id" not in item`) — not `None`;
  c. DoD-6 live smoke stays as specced: the Issues row click → `openPanel('quality-canon', {params:{focusRuleId}})` → `FocusBanner` renders `ruleFocusHits > 0` (`QualityCanonPanel.tsx:137-145`). The unit test cannot prove IF-2 is fixed — it does not know the payload ever dropped the key — so the smoke is the real gate.

*Evidence:* services/composition-service/app/db/repositories/outline.py:1358-1367 (repo emits rule_id + chapter_id) → services/composition-service/app/mcp/server.py:4043-4050 (handler keeps only rule_text, in a string title) → services/composition-service/app/services/agent_native.py:107-114 + :139-147 (Diagnostic dataclass has no field for them; ranked() serializes only kind/severity/title/detail/node_ref/at — the drop is structural). Consumer that needs the key: frontend/src/features/studio/panels/useQualityCanon.ts:107 `hoist(allRules, (r) => r.rule_id === focusRuleId)`. Sealed-decision check: plan 30 line 443 already lists BE-1a as MUST-BUILD ("broken_canon_rule gains rule_id"); §0 PO-1..4 do not conflict.

### Q-37-BE1A-PAYLOAD-WIDENING
BUILD IT AS SPECCED, in ONE shared builder, with the two under-specified edges resolved below.

STEP 1 — extract the builder (this is what makes BE-1a a single fix instead of two drifting ones). Move the body of `composition_diagnostics` (server.py:3954-4130) verbatim into a new `services/composition-service/app/services/diagnostics.py`:
    async def build_diagnostics(*, pool, tc, book_id: UUID, cap: int) -> Diagnostics
The MCP tool becomes `return {"book_id": str(bid), **(await build_diagnostics(...)).ranked(cap=cap)}`. The BE-1 REST route (`GET /v1/composition/books/{book_id}/diagnostics`) calls the SAME function. Do not copy the handler into the router — a duplicated builder is how IF-1 gets fixed on one side only.

STEP 2 — widen the carrier. In `app/services/agent_native.py`:
  - `Diagnostic` (line 107): add `chapter_id: str | None = None` and `rule_id: str | None = None`.
  - `Diagnostics.ranked()` (line 137-146): emit them CONDITIONALLY, same style as the existing `detail`/`node_ref`/`at` keys:
        **({"chapter_id": d.chapter_id} if d.chapter_id else {}),
        **({"rule_id": d.rule_id} if d.rule_id else {}),
    NEVER emit `None`. Omission is the signal (it mirrors `_Absent.attach`, agent_native.py:95-105): a row whose routing key is missing is a row the FE must render inert. A `chapter_id: null` would read as "routable" and produce the silent-wrong-target this spec exists to kill.

STEP 3 — set `ref_kind` at all 5 emit sites. `kind` stays untouched (display label); `ref_kind` is the routing key. Exact per-site mapping, verified against the sources:
  1. conformance_dirty / conformance_never_run (server.py:3998) — node_ref={"kind":"arc", "ref_kind":"structure_node", "id": arc["structure_node_id"], "title":…}. No chapter_id (source has none).
  2. canon_contradiction (server.py:4025) — node_ref={"kind":"scene", "ref_kind":"outline_node", "id": issue["scene_id"], …}; chapter_id=issue.get("chapter_id") (outline.py:1247 — nullable, so omit-when-null applies).
  3. broken_canon_rule (server.py:4047) — node_ref={"kind":"scene", "ref_kind":"outline_node", "id": item["scene_id"], …}; chapter_id=item.get("chapter_id"); rule_id=item.get("rule_id") (both present at outline.py:1360-1367 and thrown away today).
  4. prose_deleted_spec_node (server.py:4099) — node_ref={"kind": n.get("kind") or "chapter", "ref_kind":"outline_node", "id": n["id"], …}. ⚠ DECISION (PO may veto): do NOT emit chapter_id here, even though the source row has one. `compute_prose_deleted` (coverage.py:210-213) selects precisely the nodes whose chapter is GONE — that id is a tombstone. Emitting it under the same field name that every other row uses to mean "a live chapter to focus" re-arms the exact mis-route IF-1 exists to kill; a consumer would publish a dead chapterId onto the bus. The row's own title already states the chapter is gone, and FE-1 routes this row via focusNodeId, never via chapter. "chapter_id wherever the source has it" = wherever the source has a LIVE one.
  5. unplanned_chapter (server.py:4125) — node_ref={"kind":"chapter", "ref_kind":"chapter", "id": str(ch["chapter_id"]), …}; chapter_id=str(ch["chapter_id"]) (same id, emitted as a sibling so every routable row exposes chapter_id UNIFORMLY — the FE reads one field, not a per-kind special case).
  index_stale and open_thread_debt are rollups: no node_ref, no chapter_id. Unchanged.

STEP 4 — DoD-1's test (tests/unit/test_agent_native.py + tests/unit/test_mcp_server.py):
  a) `test_ref_kind_is_the_three_member_closed_set` — drive build_diagnostics over fixtures that fire ALL 5 node_ref sites, assert `{i["node_ref"]["ref_kind"] for i in items} <= {"chapter","outline_node","structure_node"}` AND that every item carrying a node_ref HAS a ref_kind (a missing key must red, not pass). Explicitly assert `"scene" not in` and `"canon_rule" not in` the observed set — those two are the wrong answer a future edit will reach for.
  b) `test_broken_canon_rule_carries_rule_id_and_chapter_id` — the IF-2 regression.
  c) `test_canon_contradiction_omits_chapter_id_when_null` — assert the KEY IS ABSENT, not that it is None.
  d) `test_prose_deleted_never_emits_chapter_id` — locks decision 4 above so it is not "fixed" back.
  e) the degraded-source test already required by M1 (key OMITTED, not 0).

DO NOT touch `entity_references.py:138-222`. It builds a different `node_ref` (kinds motif_application / canon_rule / narrative_thread) for BE-1d find_references — a different id-space set. The 3-member closed set is the DIAGNOSTICS contract only. Unifying them would be wrong and would drag `canon_rule` back into the set §3 IF-1 deliberately excludes.

No CLOSED_SET_ARGS entry is needed: `ref_kind` is an OUTPUT field, not a tool input; the enum is enforced by test (a), not by the input registry.

Consistent with sealed §0: PO-1 (Wave 7 wires the existing Issues tab, no new panel) and PO-4 are untouched; this is BE payload work only.

*Evidence:* services/composition-service/app/mcp/server.py:3998 (arc→structure_node), :4025 (canon_contradiction, scene_id), :4047 (broken_canon_rule — drops rule_id/chapter_id), :4099 (prose_deleted, outline_node id under kind "chapter"), :4125 (unplanned_chapter, book-service chapter_id under the SAME kind string — the IF-1 collision) · services/composition-service/app/services/agent_native.py:107-113 (Diagnostic has no chapter_id/rule_id) and :137-146 (ranked() serializes a fixed key list; conditional-key pattern to mirror) and :95-105 (omit-when-degraded discipline) · services/composition-service/app/db/repositories/outline.py:1244-1252 (canon_issues returns nullable chapter_id) and :1360-1367 (rule_violations returns rule_id + chapter_id) · services/composition-service/app/services/coverage.py:210-213 (compute_prose_deleted returns exactly the nodes whose chapter_id is NOT active ⇒ tombstone id) and :105-108 (unplanned rows carry chapter_id) · services/composition-service/app/db/repositories/entity_references.py:138-222 (the OTHER node_ref — do not unify)

### Q-37-D3-WAVE3-404S
CONFIRMED by code — the spec's own answer ("use the GENERIC actions spine here; do NOT align with the broken per-action paths") is right, and §8.4 lines 618-620 already state it correctly. Do not change spec 37. Binding instruction for the M1 §8.4 Run-conformance button, plus one correction the spec does NOT have:

(1) THE ONLY PATH THE BUTTON MAY USE — three calls, no others:
  a. PROPOSE via the FE→MCP bridge: `mcpExecute('composition_conformance_run', { args: {...} }, token)`. The tool is on the bridge allowlist (services/api-gateway-bff/src/tools/tools.controller.ts:24-30). Returns `{confirm_token, descriptor, estimate:{estimated_usd,currency,basis}}`.
  b. CONFIRM: `POST /v1/composition/actions/confirm?token=<confirm_token>` — the token rides the QUERY string, identity is the Bearer JWT, body empty. (routers/actions.py:213.) Returns 202 `{job_id, status}`.
  c. POLL to terminal with the existing `compositionApi.getJob(job_id, token)` loop.
  Copy the shape verbatim from the already-working `arcConformanceRunConfirm` at frontend/src/features/composition/motif/api.ts:277-297 — do NOT copy `arcConformanceRunPropose` (see 3).

(2) NEVER call `/actions/conformance_run/estimate` or `/actions/conformance_run/confirm`. routers/actions.py mounts exactly two routes — `/preview` (:183) and `/confirm` (:213) — so those two paths 404 by construction. Do not "align" the feed with `motifApi.conformanceRunEstimate/Confirm` (api.ts:223-235); do not import them; do not reuse `useConformanceTrace` (hooks/useConformanceTrace.ts:31-38) for the feed's button — write the feed's own propose→confirm→poll.

(3) NEW — CORRECTION THE SPEC LACKS, and it is load-bearing for M1: the propose args model `_ConformanceRunArgs` (services/composition-service/app/mcp/server.py:3104-3118) extends `ForbidExtra` (`extra="forbid"`, server.py:13) and for arc scope takes **`arc_id`** — a composition `structure_node.id` — with the in-code comment "pass `arc_id` (a structure_node id), NOT a template id". The existing FE helper `arcConformanceRunPropose` sends **`arc_template_id`** (api.ts:255) → pydantic extra=forbid → 422 on EVERY call. That is a fourth live break in motif/api.ts, undocumented in plan 30 §3.3. The feed's button MUST send exactly: `{ args: { project_id, scope: 'arc', arc_id: <the structure_node id the feed row already carries — spec 37 §5 keys these rows on `structure_node`>, model_ref: <BYOK>, model_source: 'user_model' } }`. Since the feed row's subject id IS a `structure_node.id` (spec 37 line 154), no lookup is needed — pass it straight through as `arc_id`. If the builder chooses to also fix `arcConformanceRunPropose` (one-word field rename, arc_template_id → arc_id), that is a fix-now, not a defer — but it is NOT required for M1 and it touches Wave 3's file, so prefer leaving it alone to avoid a merge collision with Wave 3.

(4) D-3's defer row STAYS, targeting Wave 3 (G-CONFORMANCE-TRACE), but re-word it so it is not read as "blocked": all four breaks are UNBUILT WORK, not external blockers. Updated row text — `D-3 | origin: spec 37 §11 (constraint only; spec 37 itself is unaffected) | Wave-3 fix in frontend/src/features/composition/motif/api.ts: (a) DELETE conformanceRunEstimate (:223) + conformanceRunConfirm (:228) and repoint useConformanceTrace.ts:31-38 at the generic spine (mcpExecute composition_conformance_run scope='chapter' + chapter_id → POST /actions/confirm?token= → poll) — the BE for chapter scope is ALREADY live (server.py:3136-3151 accepts scope='chapter'; actions.py:343→714 enqueues; job_consumer.py:383 runs it), so this is a pure FE repoint, ~15 lines; (b) fix arc_template_id → arc_id at api.ts:255; (c) `POST /works/{pid}/scenes/{nodeId}/regenerate-to-beat` (api.ts:301, useMotifBinding.ts:66) has ZERO backend implementation — `grep -rn "regenerate.to.beat" services/` returns nothing — so Wave 3 must WRITE that route + engine (gate 3: naturally-next-phase; NOT gate 4/blocked — CLAUDE.md's anti-laziness rule applies). | gate: 1 (out of scope of the issues-feed spec) + 3 (naturally-next-phase) | target: Wave 3 G-CONFORMANCE-TRACE`.

(5) Definition of Done for the M1 button slice: a vitest in frontend/src/features/<feed>/__tests__/ that mocks fetch and ASSERTS the button issues (i) one bridge call to `composition_conformance_run` whose args contain `arc_id` and contain NO `arc_template_id` key, and (ii) a POST whose URL matches /\/v1\/composition\/actions\/confirm\?token=/ — and asserts that NO request URL ever matches /conformance_run\/(estimate|confirm)/. That last negative assertion is the mechanical guard that stops a future builder from "aligning" with the broken helper.

Sane default I am picking (veto-able): the feed does NOT fix motif/api.ts's four breaks — it routes around them. Rationale: spec 37 never touches that file, and editing it invites a Wave-3 merge collision. If you'd rather kill the 404s now (they are cheap), say so and the builder folds (4a)+(4b) into M1.

*Evidence:* services/composition-service/app/routers/actions.py:183 (`@router.get("/preview")`) + :213 (`@router.post("/confirm")`) — the ONLY two routes on `APIRouter(prefix="/v1/composition/actions")` (actions.py:57), so `/actions/conformance_run/estimate|confirm` 404 by construction. Descriptor live: actions.py:75 `_CONFORMANCE_RUN_DESCRIPTOR = "composition.conformance_run"` → :343 → `_execute_conformance_run` :714 → op enqueued (services/composition-service/app/worker/constants.py:38) → services/composition-service/app/worker/job_consumer.py:383-385 → `engine/motif_conformance_run.run_conformance_run`. Propose tool: services/composition-service/app/mcp/server.py:3121 `@mcp_server.tool(name="composition_conformance_run")`, args model :3104-3118 `_ConformanceRunArgs(ForbidExtra)` with `arc_id` (NOT `arc_template_id`) and `extra="forbid"` (server.py:13); chapter scope explicitly supported at :3139-3149. Bridge allowlist: services/api-gateway-bff/src/tools/tools.controller.ts:24-30. Working FE reference: frontend/src/features/composition/motif/api.ts:277-297 (`arcConformanceRunConfirm` → `${BASE}/actions/confirm?token=` + poll). The four breaks: api.ts:224 + :230 (404 — routes absent), api.ts:255 (`arc_template_id` → 422 under extra=forbid), api.ts:301 + hooks/useMotifBinding.ts:66 (`regenerate-to-beat` — `grep -rn "regenerate.to.beat" services/` = 0 hits, no BE route exists at all). Spec already says this: docs/specs/2026-07-01-writing-studio/37_issues_feed*.md:618-620.

### Q-37-USESTUDIOPANEL-DOES-NOT-EXPOSE-PARAMS
CLAIM CONFIRMED TRUE — and the spec's candidate answer ("props.params, full stop") is CORRECT but INCOMPLETE for FE-1. Keep §4.1.1's ⚠ note verbatim; ADD the sufficiency rule below, because "full stop" as written will produce the very bug FE-1 exists to kill.

(1) CONFIRMED: `useStudioPanel(panelId, api, extras?) -> string` returns the localized LABEL only (useStudioPanel.ts:11-15 signature, :34 `return label`, :31 `api.setTitle(label)`). It neither accepts nor returns params. Params arrive ONLY as the dockview prop `props.params`. Do not re-introduce the false claim.

(2) THE SUFFICIENCY RULE (the part "full stop" misses). The host's already-open re-open path is `StudioHostProvider.tsx:83` — `existing.api.updateParameters(opts.params)`; only a CLOSED panel receives params via `addPanel` (:92). So:
  - DERIVE-ONLY focus (useMemo/hoist computed straight off the prop) ⇒ `props.params` alone IS sufficient. Precedent: QualityPromisesPanel.tsx:23, KgEntitiesPanel.tsx:18, useQualityCanon's `hoist()`.
  - focus HELD IN useState ⇒ `props.params` alone is NOT sufficient. useState ignores a changed prop on re-render, so the SECOND issue-row click into an already-open singleton focuses nothing. You MUST also subscribe `props.api.onDidParametersChange`. Precedent: JobDetailPanel.tsx:28-34 ("the event fires on every call, so clicking a different job row while job-detail is already open still lands") and AgentModePanel.tsx:42-47.

(3) BUILDER INSTRUCTION FOR FE-1 (M1b) — exactly two files, both wiring-only; nothing is missing infrastructure:

  A. frontend/src/features/studio/panels/PlanHubPanel.tsx — this is the useState kind (focusTarget at :102, seq bumped at :110), so it needs BOTH legs. It ALREADY has the imperative: `focusNode(nodeId)` at :104-114 expands ancestors, bumps seq, selects. Do NOT write a new focus path — call the existing one. Add after the `focusNode` useCallback:
     - read `const p = (props.params ?? {}) as { focusNodeId?: unknown; focusArcId?: unknown }`
     - on mount: if `focusNodeId` (or `focusArcId`) is a non-empty string, call `focusNode(id)` — a Plan Hub node id and arc id are both node ids in the tree, so ONE handler serves both params; prefer `focusNodeId` when both are present.
     - subscribe: `useEffect(() => { const d = props.api.onDidParametersChange?.((next) => { const id = str(next?.focusNodeId) ?? str(next?.focusArcId); if (id) focusNode(id); }); return () => d?.dispose?.(); }, [props.api, focusNode]);` — mirror JobDetailPanel.tsx:28-34's dispose shape and its `str()` guard (JobDetailPanel.tsx:16).

  B. frontend/src/features/studio/panels/ChapterBrowserPanel.tsx — a hoist+highlight, i.e. derive-only, so `props.params.focusChapterId` ALONE is sufficient; do NOT add an onDidParametersChange subscription here. Mirror useQualityCanon's `hoist()` contract exactly (a focus HOISTS and HIGHLIGHTS, stable sort, NEVER filters/hides — useQualityCanon.ts:15-16 and its `hoist<T>()` helper). Do not invent a second focus contract.

  TESTS (both required, or the wiring is unproven): (i) PlanHubPanel — render with `params:{focusNodeId}`, assert `select`/camera fired; then fire `onDidParametersChange` with a DIFFERENT focusNodeId and assert it re-focused. That second assertion is the whole point — it is the one a props.params-only impl fails. (ii) ChapterBrowserPanel — render with `params:{focusChapterId}` and assert the row is hoisted to index 0 AND the non-matching rows are still present (proves hoist, not filter).

(4) DEFAULT I AM PICKING (veto-able): `focusArcId` and `focusNodeId` are handled by the SAME PlanHub code path rather than adding a second distinct mechanism, since both resolve to a node in the plan tree. If the PO wants an arc-specific camera framing (e.g. fit-to-arc-bounds rather than pan-to-node), that is a separate, later polish item — it does not block FE-1.

(5) COORDINATION (from spec 37 §4.1.1): both files are owned by the Book-Package track (plan 30 §9) — coordinate before editing. This does not change the decision, only the sequencing.

Consistent with §0 sealed PO decisions — PO-1 amends AN-12's "no new GUI surface" clause; FE-1 adds ZERO new panel ids and touches only two existing panels.

*Evidence:* frontend/src/features/studio/panels/useStudioPanel.ts:11-15 (signature `(panelId, api, extras?)`) + :34 (`return label`) — hook exposes NO params, returns the localized label. || frontend/src/features/studio/host/StudioHostProvider.tsx:83 (`existing.api.updateParameters(opts.params)` — the already-open re-open path) + :92 (`api.addPanel({... params})` — the closed-panel path); :47-48 comment states the contract: "Panels read props.params / api.onDidParametersChange". || Derive-only precedent: QualityPromisesPanel.tsx:23, KgEntitiesPanel.tsx:18. || useState precedent requiring BOTH legs: JobDetailPanel.tsx:24 + :28-34, AgentModePanel.tsx:42-47 (:15-16 comment names the pattern "props.params at mount + onDidParametersChange for an already-open singleton, DOCK-6"). || PlanHubPanel.tsx:39 (`useStudioPanel('plan-hub', props.api)` — return value discarded, props.params never read = param-blind, confirms FE-1), :102 (`useState<CameraFocusTarget|null>`), :104-114 (`focusNode()` already exists: expandAncestorsOf + seq bump + select). || Hoist contract to mirror: useQualityCanon.ts:15-16 ("A focus HOISTS and HIGHLIGHTS — it never hides") + its `hoist<T>()` stable-sort helper.

### Q-37-NO-WORK-SCOPE-STATE
CONFIRMED — and it must stay that way through the extraction. The no-Work path already degrades (never raises) in the MCP handler; `build_diagnostics` does not exist yet, so the builder's job is to carry the behavior across, fix one honesty defect it has today, and give the FE a machine-readable flag instead of a string it must pattern-match.

BUILDER INSTRUCTION (M1 / BE-1, exactly this):

1) EXTRACT (do not fork — spec 37 §5.1 rule 2). Move the ~180-line source fanout from `services/composition-service/app/mcp/server.py:3960-4132` into `services/composition-service/app/services/agent_native.py` as:
   `async def build_diagnostics(pool, book_client, book_id: UUID, bearer: str, cap: int = _DIAG_CAP) -> Diagnostics`
   It calls `resolve_scope(WorksRepo(pool), book_id)` itself. It NEVER raises on `(None, None)` and never 404s — `resolve_scope`'s own docstring (agent_native.py:205-215) already seals this: "Returns (None, None) only when the book genuinely has no composition Work at all — which is not an error either: it is a book nobody has planned yet, and saying so is the useful answer." `composition_diagnostics` (MCP) and the new REST route both call it and do nothing else but gate + serialize. Keep the bearer as a PARAM (route passes the user's JWT, MCP passes `mint_service_bearer(...)` — §5.1 rule 1).

2) BOOK-KEYED SOURCES STILL RUN when `pid is None`: (1) conformance + index staleness, (4) prose_deleted, (5) coverage/unplanned. They take `book_id`, not `project_id`. Do not gate them on the Work row.

3) FIX THE DEGRADE, DO NOT COPY IT VERBATIM. Today the three PROJECT-keyed sources are skipped via `if pid is None: raise LookupError("no project")` inside their `try` (server.py:4015-4016, 4038-4039, 4062-4063), so `except Exception` appends three MISLEADING warnings — "canon contradictions could not be read" / "broken canon rules could not be read" / "open thread debt could not be read" — indistinguishable from a real DB failure. In `build_diagnostics`, replace each with a plain guard OUTSIDE the try (`if pid is not None:` wrapping the block), so a no-Work book emits EXACTLY ONE warning: the existing string at server.py:3973-3976, "this book has no composition work — canon issues, thread debt and motif applications were NOT checked (absent, not zero)". Otherwise §4.1.3's strip renders "4 sources could not be read" on a perfectly healthy unplanned book and the user reads it as breakage.

4) ADD THE FLAG (this is the one net-new field). `Diagnostics` gains `has_work: bool = True`; `ranked()` emits `"has_work": <bool>` at top level next to `counts`/`total`. The REST route returns 200 with `{book_id, has_work: false, items:[...from the book-keyed sources...], counts:{...}, total, warnings:[the one string]}`. Rationale: §4.1.2 says the FE "renders whatever answered plus the warning" — the FE must NOT substring-match an English warning to decide that (i18n-fragile, and it is a closed-set state, not prose). `useDiagnostics.ts` branches on `has_work === false` → render the No-Work banner (i18n key `studio.issues.noWork`) ABOVE the normal body; the raw warning still ships for the agent/MCP reader. `IssuesTab` renders rows as normal — No Work is a BANNER, not an empty state.

5) TESTS (all three, or the slice is not done):
   - `services/composition-service/tests/unit/test_agent_native.py::test_a_book_with_NO_composition_work_DEGRADES_not_RAISES` — stub `works.resolve_by_book -> []` and `works.get_pending_for_book -> None`; assert `build_diagnostics(...)` RETURNS (no exception), `.has_work is False`, `warnings == [the single no-work string]` (assert LEN 1 — this is the guard against the 3-bogus-warnings regression), `"canon_contradiction" not in counts and "open_thread_debt" not in counts` (ABSENT, not `0` — the module's absent≠zero law), and that a seeded unplanned chapter STILL appears (proves book-keyed sources ran).
   - route test: `GET /v1/composition/books/{bid}/diagnostics` on a Work-less book → **200** (never 404/500) with `has_work: false`.
   - vitest: `IssuesTab` with `has_work:false` renders the no-work banner + still renders the book-keyed rows.

Default I am picking (veto-able): the flag is named `has_work` (boolean, always present). I did NOT reuse `warnings` as the signal, and I did NOT add a `scope` object — one name, one concept, one field.

*Evidence:* services/composition-service/app/services/agent_native.py:190-215 (`resolve_scope` — docstring: "(None, None)… is not an error either"; the live-smoke 404 it already cost once) · services/composition-service/app/mcp/server.py:3962 (`_work, pid = await resolve_scope(...)`), :3969-3976 (the `if pid is None:` warning — degrade, no raise), :4015-4016 / :4038-4039 / :4062-4063 (`raise LookupError("no project")` inside the try → 3 misleading "could not be read" warnings — the defect to fix in the extraction), :4132 (`return {"book_id": str(bid), **diag.ranked(cap=cap)}` — the payload `has_work` joins) · agent_native.py:78-105 (`Block` / absent≠zero) · spec 37 §5.1 rules 1-2 (bearer + "extract the body, do not fork it") · no existing test covers the no-Work path (`grep -n "def test" tests/unit/test_agent_native.py` — 22 tests, none for it)

### Q-37-BUS-PUBLISH-SIDE-EFFECT
Answer (a) — INTENDED. Keep the publish. The whole-studio retarget IS the studio's focus model, not an accidental side effect, and it is not lossy. Builder instructions:

1. KEEP `publish({type:'scene', sceneId, chapterId})` in the canon_contradiction row's click handler, then `openPanel('quality-canon', {focus:true, params:{bookId, focusChapterId}})`. Spec §4.1.1 row 1 is CORRECT as written. Rationale to record in the spec: publishing `scene` sets BOTH `activeSceneId` and `activeChapterId` (types.ts:97-98), which retargets the editor (ManuscriptUnitProvider.tsx:321-326 → openUnit), the SceneRail (SceneRail.tsx:197-200 → jumpToScene) and the scene-inspector (useSceneInspector.ts:49-53). That is exactly what the user wants when they click "this scene contradicts canon": the canon panel comes forward AND the editor behind it is now sitting on the offending scene, ready to fix. It is dirty-SAFE — openUnit dirty-flushes (saves) before switching (ManuscriptUnitProvider.tsx:184-190: "a pending edit is SAVED before switching so navigation never loses work"), so no unsaved work is ever destroyed. And it is the established precedent: the only three existing scene publishers (StudioFrame.tsx:115 Quick Open, StudioFrame.tsx:125 navigator select, SceneBrowserPanel.tsx:229 Scene Browser row) all do this same whole-studio retarget.

2. DO NOT call `host.focusManuscriptUnit()` here (unlike StudioFrame.tsx:115/125). It calls `openPanel('editor')`, which would open/raise the editor and steal dock focus back from quality-canon. Use the BARE `host.publish(...)` — it touches the context snapshot only, never dock focus. This is the one distinction the spec must state explicitly: the publish moves the CONTEXT, `openPanel` moves the FOCUS.

3. BLOCKING PREREQ (a real defect this adjudication uncovered): the row cannot build the event today. `services/composition-service/app/mcp/server.py:4020-4022` emits `node_ref={"kind":"scene","id":issue["scene_id"],"title":…}` and DROPS chapter_id — even though the repo already SELECTs it (`services/composition-service/app/db/repositories/outline.py:1218`: `n.id AS scene_id, n.title AS scene_title, n.chapter_id`). Fix: add `"chapter_id": issue["chapter_id"]` to that node_ref dict (and mirror it in the REST diagnostics mirror + the `ref_kind` work in §4.1.1). Without it there is no `chapterId` to publish and no `focusChapterId` to pass — useQualityCanon.ts:111 hoists on `i.chapter_id === focusChapterId`, so the deep-link silently does nothing.

4. Guard the publish: `if (!row.node_ref?.chapter_id) { openPanel only, skip the publish; }` — never publish a scene event with an empty chapterId (SceneBrowserPanel.tsx:229 today passes `chapterId ?? ''`, which would blank the editor's active chapter). canon_contradiction is SAFE to publish as a scene because the repo hard-filters `n2.kind = 'scene'` (outline.py:1229); `prose_deleted_spec_node` is NOT (its node_ref may be a chapter-kind outline node) and must keep the spec's existing plan-hub-only routing.

5. TEST (Wave 7, `frontend/src/features/studio/panels/__tests__/`): assert that clicking a canon_contradiction row (a) fires exactly ONE bus event, `{type:'scene', sceneId, chapterId}`, (b) leaves `quality-canon` as the ACTIVE dock panel (i.e. `focusManuscriptUnit`/`openPanel('editor')` was NOT called), and (c) with a row whose node_ref has no chapter_id, publishes NOTHING and still opens quality-canon.

PO veto note: if the PO prefers (b) "panel-only, never move the editor", the only change is to delete the publish in step 1 and drop step 4 — steps 3 and 5 stand either way, since focusChapterId is needed for the hoist regardless. I am defaulting to (a) because it matches every existing scene-navigation call site in the codebase and loses no work.

*Evidence:* frontend/src/features/studio/host/types.ts:97-98 (scene event sets activeSceneId AND activeChapterId — the global retarget); frontend/src/features/studio/manuscript/unit/ManuscriptUnitProvider.tsx:321-326 (activeChapterId → openUnit → editor loads that chapter) + :184-190 (openUnit dirty-FLUSHES/saves before switching → no work lost); frontend/src/features/studio/manuscript/SceneRail.tsx:197-200 + frontend/src/features/studio/panels/useSceneInspector.ts:49-53 (the other two consumers); precedent: frontend/src/features/studio/components/StudioFrame.tsx:115,125 + frontend/src/features/studio/panels/SceneBrowserPanel.tsx:229 (all three existing scene publishers do the same whole-studio retarget); DEFECT: services/composition-service/app/mcp/server.py:4020-4022 drops chapter_id from node_ref though services/composition-service/app/db/repositories/outline.py:1218 selects it, and :1229 (`n2.kind = 'scene'`) proves canon_contradiction is always a scene; consumer: frontend/src/features/studio/panels/useQualityCanon.ts:111 (hoists on i.chapter_id === focusChapterId)

### Q-37-COUNTS-MUST-STAY-UNFILTERED
UPHELD — implement the constraint inside the ENGINE, not the route, and add the one number the constraint forgets (`matched`).

1) BE-1 (composition-service). Change the signature in `app/services/agent_native.py` to:
   `def ranked(self, cap: int = _DIAG_CAP, *, severity: str | None = None, kind: str | None = None) -> dict[str, Any]:`
   Body, in this exact order:
   - sort as today (`_RANK`, `_neg_ts`) → `ordered`;
   - THEN filter: `matched = [d for d in ordered if (severity is None or d.severity == severity) and (kind is None or d.kind == kind)]`;
   - THEN cap: `shown = matched[:cap]`;
   - return `"counts": dict(self.counts)` — built from `self.items`, i.e. the FULL unfiltered set — UNCHANGED from today (agent_native.py:152);
   - `"total": len(self.items)` — UNCHANGED, the honest book-wide total, never narrowed by a filter;
   - NEW key `"matched": len(matched)` — how many rows the filter selected before the cap;
   - `"refs_capped": len(matched) > cap` (was `len(ordered) > cap`) — the cap is now relative to the FILTERED set, per D-2.
   With no filter args `matched == total` and the payload is a strict superset of today's, so `server.py:4132` (`diag.ranked(cap=cap)`) needs NO change and the MCP contract does not break.
   Do NOT put the filter in the router — a route-side `[i for i in payload["items"] if …]` re-derives severity from the item rows and forks the SEVERITY map (the `css-var-duplicated-across-two-consumers-drifts` bug the module's own docstring forbids).
   The router `read_diagnostics` validates `kind` against `SEVERITY.keys()` (422 on unknown — never silently return an empty list) and calls `build_diagnostics(...).ranked(cap=cap, severity=severity, kind=kind)`.

2) FE (IssuesTab, inside the existing `frontend/src/features/studio/components/StudioBottomPanel.tsx` Issues tab — no new panel id). The severity chips and the kind select render their numbers from `data.counts` ONLY: `Error = sum(counts[k] for k where SEVERITY[k]==='error')`, etc. They must NEVER read `data.items.length` or a filtered row array. Export the severity map ONCE (`frontend/src/features/studio/issues/severity.ts`, mirroring `agent_native.SEVERITY`'s 8 keys) — do not inline it twice. Chips stay lit and keep their real numbers while a filter is active; the active chip gets `aria-pressed`, not a zeroed label.
   Footer: `Showing {items.length} of {matched} · {total} findings in this book` — so a filtered view can never read as "my errors went away", and `refs_capped` still means "there are more MATCHING rows than shown".

3) Tests (both are Definition-of-Done for M1, and `/review-impl` runs at wave close):
   - `services/composition-service/tests/unit/test_agent_native.py` (extend near the existing `ranked` tests at :210/:225): build a `Diagnostics` with 2 `canon_contradiction` (error) + 1 `open_thread_debt` (info); assert `ranked(severity="info")` → `len(items)==1`, `counts == {"canon_contradiction": 2, "open_thread_debt": 1}` (error kind STILL PRESENT AND NONZERO), `total == 3`, `matched == 1`, `refs_capped is False`. This is the regression that makes "Error 2 → Error 0" impossible.
   - a router test: `GET /v1/composition/books/{id}/diagnostics?severity=info` → response `counts` still carries the error kinds.
   - a Vitest on the Issues toolbar: render with `counts={canon_contradiction:2}`, active filter `info`, `items=[]` → the Error chip renders "2", not "0", and not hidden.

*Evidence:* services/composition-service/app/services/agent_native.py:139-159 — `Diagnostics.ranked()`: `shown = ordered[:cap]`; `"counts": dict(self.counts)` with the comment "# EXACT, never capped — this is what the agent reasons about."; `"total": len(self.items)`; `"refs_capped": len(ordered) > cap`. Sole caller: services/composition-service/app/mcp/server.py:4132 `return {"book_id": str(bid), **diag.ranked(cap=cap)}` (no filter args today). Severity map: agent_native.py:60-73 (8 kinds). Spec constraint: docs/specs/2026-07-01-writing-studio/37_issues_feed.md:480-482 (§5.1(3)) + :238-243 (toolbar chips read the exact counts map) + :701 (D-2: cap applies AFTER the filter, server-side, "do not simplify"). FE stub to replace: frontend/src/features/studio/components/StudioBottomPanel.tsx:43-45.

### Q-37-FE1-PARAM-BLIND-TARGETS
BUILD IT in M1b as specced (hoist+highlight, never filter/hide) — but the "mirror focusNode / mirror hoist()" instruction as written ships TWO silent no-ops. The build is 3 slices:

SLICE 1 — PlanCanvas camera (do this FIRST; plan-hub's deep-link is inert without it).
`frontend/src/features/plan-hub/components/PlanCanvas.tsx:69-91` — CameraController resolves `nodes.find(p => p.id === focusTarget.nodeId)` and returns silently when absent (`:86`). An EXPANDED arc is a `LaneBand` (laneLayout.ts:105-119), NOT a member of `layout.nodes` — only a COLLAPSED arc is a rollup node (laneLayout.ts:139). And `focusNode` calls `expandAncestorsOf` (ancestors only), so an expanded arc NEVER becomes a rollup ⇒ a `focusArcId` pan never fires. Fix: pass `lanes: LaneBand[]` into PlanCanvas → CameraController; resolve the target as `nodes.find(n => n.id === id)` ?? the first node drawn inside that band, where the band's descendants are the lanes with `l.y >= band.y && l.y < band.y + band.height` (LaneBand has no parent_id; nesting is geometric) and the node is `nodes.find(n => n.laneId && bandLaneIds.has(n.laneId))` (`NodePosition.laneId`, laneLayout.ts:128). Add `lanes` to the effect deps — the existing per-`seq` `pannedFor` latch (`:82-87`) then makes this WAIT FOR LAYOUT, which is what makes a COLD-OPEN deep-link work (params land on the first render, when `layout.nodes` is still empty — resolving the pan target eagerly in the panel would return null forever and re-ship IF-4). This one change also fixes the identical latent no-op on the PH25 rail path.
TEST: `PlanCanvas.test.tsx` — focus an expanded arc's id ⇒ `setCenter` called with the coords of the first node in its band; focus a collapsed arc's id ⇒ centers the rollup; focus an id absent at mount, then land the layout ⇒ centers exactly ONCE.

SLICE 2 — PlanHubPanel consumes params.
`frontend/src/features/studio/panels/PlanHubPanel.tsx` — add `const p = props.params as { focusNodeId?: string | null; focusArcId?: string | null } | undefined`. `focusNodeId` and `focusArcId` are the SAME id space (rollup node id === structure_node id — see the file's own header + laneLayout.ts:106), so ONE handler: `const target = p?.focusNodeId ?? p?.focusArcId ?? null` (focusNodeId wins) → call the EXISTING `focusNode(target)` (`:105-116`) — do not write a second focus path. Apply it in an effect that mirrors the existing planFocus bus effect (`:118-126`) but guards on the `props.params` OBJECT IDENTITY via a `useRef` (dockview only swaps that object on `addPanel`/`updateParameters` — StudioHostProvider.tsx:83/92 — so identity-guarding re-pans on a REPEAT deep-link to the same node, which a value-guard would swallow, while unrelated re-renders are inert). `focusNode` already does expandAncestorsOf + select + seq-bump, and `select(arcId)` is safe for an arc at ANY expand state because `usePlanHub.ts:107-114` keys `nodeContent` by every shell arc ⇒ the drawer resolves. NEVER filter the canvas — PH14 forbids re-laying out under the user; focus = expand + select + pan (+ the existing ring), exactly like useQualityCanon's hoist contract.
TEST: `planHubDeepLink.test.tsx` (extend the existing file) — mount PlanHubPanel with `params={{focusArcId:'a1'}}` ⇒ a1 selected + drawer open + camera target resolves; `params={{focusNodeId:'c3'}}` inside a COLLAPSED arc ⇒ ancestors expanded, c3 selected; params absent ⇒ zero focus calls (no phantom select).

SLICE 3 — ChapterBrowser consumes focusChapterId, ACROSS PAGES.
`ChapterBrowserPanel.tsx:23` — read `props.params.focusChapterId` and pass it into `ChapterBrowserTitleView` (also force `mode='title'` on a focus, since content-mode cannot show it). DO NOT just hoist the loaded rows: the list is SERVER-PAGED (`ChapterBrowserTitleView.tsx:9-13`, `useServerPagedList`), so a focused chapter on page 3 would be silently absent — the exact false-"absent" bug class this repo already has a lesson for. Instead: fetch the target directly with the EXISTING `booksApi.getChapter(token, bookId, chapterId)` (`frontend/src/features/books/api.ts:345`) via a `useQuery` keyed on it, and render it as a PINNED, highlighted focus row ABOVE the list (reuse the existing row component + the `HIT` ring styling from QualityCanonPanel.tsx:26), de-duped against the in-page rows (if it IS on the current page, highlight it in place AND keep the pin — never hide either). Mirror useQualityCanon's honesty clause (useQualityCanon.ts:15-18): if getChapter 404s, render an explicit banner ("that chapter no longer exists") — never an unchanged list that pretends the link did something. Do not touch the filters/pagination — focus HOISTS, never filters.
TEST: `ChapterBrowserPanel.test.tsx` / `ChapterBrowserTitleView.test.tsx` — focusChapterId NOT in the loaded page ⇒ pinned row rendered from getChapter, page rows unchanged, total unchanged; focusChapterId IS on the page ⇒ highlighted in place, no duplicate row; getChapter 404 ⇒ explicit banner; no params ⇒ no getChapter call at all.

DEFAULT I am picking (veto-able): `focusArcId` on an expanded arc pans to its first drawn child rather than auto-collapsing the arc into its rollup — collapsing would hide content the user was sent to look at, which violates "focus never hides".

*Evidence:* PARAM-BLIND CONFIRMED: frontend/src/features/studio/panels/PlanHubPanel.tsx:39 + ChapterBrowserPanel.tsx:23-27 call useStudioPanel(id, props.api) and never read props.params (PlanHubPanel only EMITS them, :74). SEAM EXISTS: StudioHostProvider.tsx:83 (updateParameters) / :92 (addPanel params); read pattern QualityCanonPanel.tsx:33. TRAP 1: PlanCanvas.tsx:85-86 CameraController nodes.find(...) → `if (!n) return;` silent no-op; an expanded arc is a LaneBand (laneLayout.ts:105-119) not a node (laneLayout.ts:139 "nodes = lane chapters + scenes + arc rollups"); NodePosition.laneId at laneLayout.ts:128 is the seam for the band fallback; usePlanHub.ts:107-114 keys nodeContent by every shell arc so select(arcId) always resolves the drawer. TRAP 2: ChapterBrowserTitleView.tsx:9-13 is server-paged via useServerPagedList; booksApi.getChapter exists at frontend/src/features/books/api.ts:345. Reference contract: useQualityCanon.ts:15-18 (focus HOISTS, never hides; say so when the link found nothing) + hoist() at :62-66.

### Q-37-LIMIT-CLAMP-ONCE
Build it as follows — the clamp arithmetic lives in EXACTLY ONE function; the route validates, the MCP tool coerces.

1) CLAMP SITE (the only one). During the BE-1 extraction (spec §5.1 point 2 — move the ~180-line fanout out of `composition_diagnostics` into `agent_native.build_diagnostics`), MOVE the clamp line with it. New signature in `services/composition-service/app/services/agent_native.py`:
   `async def build_diagnostics(pool, book_client, book_id: UUID, bearer: str, limit: int | None = None) -> Diagnostics:`
   First statement in the body, verbatim from server.py:3966 including its comment:
   `cap = max(1, min(int(limit or _DIAG_CAP), 100))`   # _DIAG_CAP = 25, agent_native.py:38 — one home for the default
   After that line the RAW `limit` is never referenced again. `cap` feeds every slice: `pd.nodes[:cap]` (today server.py:4091), `cov.unplanned[:cap]` (server.py:4121), and the terminal `Diagnostics.ranked(cap)`. Do NOT add a second `max/min` in the router, in `ranked()`, or in the MCP tool.

2) MCP TOOL (`app/mcp/server.py` `composition_diagnostics`, sig at :3952). Keep `limit: Annotated[int, ...] = 25`. DELETE its local `cap = max(1, min(...))` at :3966 and pass the raw `limit` straight to `build_diagnostics(...)`. An LLM sending `limit=0`/`-5`/`500` must be coerced, never error — that is why the clamp is the shared function's job.

3) REST ROUTE (new `GET /v1/composition/books/{book_id}/diagnostics`, mirror `routers/conformance.py:424`). Keep `limit: int = Query(25, ge=1, le=100)`. FastAPI REJECTS out-of-range with 422 — it does NOT clamp, and that is CORRECT and intentional: an HTTP client that sends `limit=500` gets told, it does not get silently given 100. This is the exact divergence the spec's "mirror server.py:3966" phrasing papered over; recorded here so it is not re-litigated. The route then calls `build_diagnostics(..., limit=limit)`, whose clamp is a proven no-op for any value FastAPI let through (idempotent, so no drift possible). The route must NOT re-implement the clamp.
   Note the repo bug class this defends against (`chapter-list-limit100-fallback-20-bug`): the failure mode is a helper that SILENTLY substitutes a different default on out-of-range input. FastAPI's `ge/le` cannot do that. Do not hand-roll a `parse_limit()` helper here.

4) TESTS (all MUST-BUILD in the BE-1 slice; the clamp is asserted, not assumed):
   a. `test_diagnostics_route_rejects_out_of_range` — `limit=0` → 422, `limit=-1` → 422, `limit=101` → 422. Explicitly assert `resp.status_code == 422` and NOT `200` — a 200 carrying a silently-substituted default is the shipped bug class.
   b. `test_diagnostics_route_default_is_25` — omit `limit`, seed >25 diagnostics, assert `len(body["items"]) == 25`, `body["refs_capped"] is True`, and `body["total"]` == the true count (counts/total are NEVER capped — agent_native.py:151).
   c. `test_build_diagnostics_clamps_once` (unit, on `agent_native.build_diagnostics`, the MCP path): `limit=-5` → returns 1 item and it is the HIGHEST-severity row (proves the negative sliced from the FRONT via `cap>=1`, not from the end via a raw `[:-5]` — the exact bug the server.py:3966 comment records); `limit=0` → 1 item (NOT an empty list); `limit=1000` → ≤100 items; `limit=None` → 25.
   d. `test_mcp_diagnostics_still_clamps` — call the MCP tool with `limit=500` → ≤100 items, and with `limit=0` → 1 item. Guards that step (2)'s deletion did not drop the coercion an LLM depends on.
   e. Parity: assert route(limit=25) items == mcp(limit=25) items byte-identical (spec §5.1: "byte-identical to Diagnostics.ranked()"), so the shared body can never fork (`css-var-duplicated-across-two-consumers-drifts`).

If the PO disagrees with 422-on-out-of-range for the REST route, the only alternative is to clamp there too — but that hides client bugs and no sibling composition route does it, so 422 is the default I'm picking.

*Evidence:* services/composition-service/app/mcp/server.py:3964-3966 — `# Clamp ONCE. The row slices below used the RAW arg while the ranked cap clamped it — a negative \`limit\` would have sliced from the end.` / `cap = max(1, min(int(limit or 25), 100))`; consumed at server.py:4091 (`pd.nodes[:cap]`) and server.py:4121 (`cov.unplanned[:cap]`). services/composition-service/app/services/agent_native.py:38 `_DIAG_CAP = 25`; :128 `def ranked(self, cap: int = _DIAG_CAP)`; :137 `shown = ordered[:cap]`; :151 `"refs_capped": len(ordered) > cap`. Route precedent: services/composition-service/app/routers/conformance.py:424-454 (`read_conformance_status` — book-scoped, VIEW-gated via authorize_book, OwnershipError⇒404 / InsufficientGrant⇒403). Spec BE-1: docs/specs/2026-07-01-writing-studio/37_issues_feed.md:442 and the §5.1 sketch at :459 (`limit: int = Query(25, ge=1, le=100)`) — which VALIDATES rather than clamps, the ambiguity this decision resolves.

### Q-37-IF3-SCENE-INSPECTOR-BUS-NOT-PARAMS
ADOPT publish-then-open; do NOT make `scene-inspector` param-aware. The spec's candidate answer is correct and is already the shipped contract — `SceneBrowserPanel.tsx:229-230` does `host.publish({type:'scene', sceneId, chapterId})` then `host.openPanel('scene-inspector', {focus:true})`, and `useSceneInspector.ts:1-2` documents bus-selection as deliberate ("a detail-over-selection pane (SC10)"). Adding a `params.nodeId` read would give one concept two selection sources (one-name-one-concept breach) and fork the OCC/load path. BUILD EXACTLY THIS:

(A) BE-1a — `services/composition-service/app/services/agent_native.py:107-114`: add `chapter_id: str | None = None` and `rule_id: str | None = None` to the `Diagnostic` dataclass, and emit both from `Diagnostics.ranked()` OMITTING the key when None (mirror `Block.into()`'s absent-vs-zero discipline at agent_native.py:94-99 — never emit `null`/`""`).

(B) BE-1a — `services/composition-service/app/mcp/server.py:4019-4028` (`canon_contradiction`): set `chapter_id=str(issue["chapter_id"])` and change `node_ref={"kind": "scene", ...}` → `{"kind": "outline_node", ...}` (IF-1: a scene IS an outline_node; the closed set is chapter|outline_node|structure_node). Same at `server.py:4043-4050` (`broken_canon_rule`): add `chapter_id=str(item["chapter_id"])`, `rule_id=str(item["rule_id"])`, and the same `node_ref.kind` fix. NO null branch is needed: `migrate.py:212` `CONSTRAINT outline_chapter_required CHECK (kind NOT IN ('chapter','scene') OR chapter_id IS NOT NULL)` + `canon_issues`'s `n2.kind = 'scene'` filter make `chapter_id` NOT NULL on every canon row, by construction.

(C) FE — the M1 Lane-B row handler in the new `IssuesTab.tsx`, for `canon_contradiction`:
    if (row.chapter_id) host.publish({ type: 'scene', sceneId: row.node_ref.id, chapterId: row.chapter_id });
    host.openPanel('quality-canon', { focus: true, params: { bookId, focusChapterId: row.chapter_id } });
The `if (row.chapter_id)` guard is MANDATORY and is a hazard the spec did not name: `host/types.ts:97` reduces `case 'scene'` as `activeChapterId: e.chapterId` UNCONDITIONALLY, so publishing `chapterId: ''` silently clobbers the editor's active chapter. `SceneBrowserPanel.tsx:229` has that latent hole (`r.chapterId ?? ''`) — DO NOT copy it. (Fixing SceneBrowserPanel's `?? ''` is a separate one-liner; fix-now if the wave touches that file, else leave it.)

(D) Scope note the builder must not miss: per the routing table (spec 37 §4.1.1 line 249) the `canon_contradiction` row opens **quality-canon**, NOT scene-inspector. The `publish` is there so an ALREADY-OPEN scene-inspector re-targets to the right scene; it is not a scene-inspector deep-link. So no scene-inspector code changes in M1 at all — the whole of IF-3 reduces to (A)+(B)+(C).

(E) TESTS (both required, both name the effect): pytest — assert the `canon_contradiction` and `broken_canon_rule` dicts from `Diagnostics.ranked()` carry `chapter_id` (and `rule_id` for the rule row) and `node_ref["kind"] == "outline_node"`. vitest — a handler test asserting `publish` was called with `{type:'scene', sceneId, chapterId}` BEFORE `openPanel`, plus a test that a row with NO `chapter_id` does NOT publish (guards the activeChapterId-clobber).

*Evidence:* frontend/src/features/studio/panels/SceneBrowserPanel.tsx:229-230 (shipped publish-then-open precedent) · frontend/src/features/studio/panels/useSceneInspector.ts:1-2,25 (bus-selection is by design, `useStudioBusSelector((s) => s.activeSceneId)`) · frontend/src/features/studio/host/types.ts:45 (`{type:'scene'; sceneId; chapterId}` — chapterId required), :97 (`activeChapterId: e.chapterId` set unconditionally → the empty-string clobber) · services/composition-service/app/mcp/server.py:4025 + :4047 (`node_ref={"kind":"scene"...}`, chapter_id/rule_id dropped) · services/composition-service/app/services/agent_native.py:107-114 (Diagnostic dataclass — no chapter_id/rule_id field) · services/composition-service/app/db/migrate.py:212 (`CHECK (kind NOT IN ('chapter','scene') OR chapter_id IS NOT NULL)` → chapter_id guaranteed on every canon row) · docs/specs/2026-07-01-writing-studio/37_issues_feed.md:249 (canon_contradiction routes to quality-canon, not scene-inspector)

### Q-37-WARNINGS-STRIP-MANDATORY
MANDATORY — build the strip, exactly as §4.1.3 says. But the naive implementation of §4.1.2's copy ships TWO NEW LIES, both provable from the code. Seal this contract:

**A. `warnings` is ABSENT when clean, not `[]`.** `agent_native.py:152` emits `**({"warnings": self.warnings} if self.warnings else {})`. So `data.warnings.length` throws on a clean book. TS type in `useDiagnostics.ts`: `warnings?: string[]; degraded_sources?: number`. FE: `const warnings = data?.warnings ?? []`.

**B. "7 sources" is FALSE — there are SIX.** `composition_diagnostics` (`server.py:3960-4132`) has exactly 6 source blocks: (1) conformance+index, (2) canon contradictions, (2b) broken canon rules, (3) open thread debt, (4) prose-deleted spec nodes, (5) coverage/unplanned. Eight *kinds* (`SEVERITY`, `agent_native.py:60-73`), six *sources*. Spec 37 drifts three ways ("seven sources" §1, "~2.5 of 5" §1.1, "across 7 sources" §4.1.2). **All FE copy and the enumerated source list say 6.**

**C. `warnings.length` is NOT the count of unread sources — deriving N from it re-commits the exact dishonesty the strip exists to kill.** Two payload warnings are not source failures: the OUT-5 truncation notice `"showing X of Y broken canon rules"` (`server.py:4053`), and the no-project umbrella (`server.py:3973`) which DOUBLE-COUNTS — when `pid is None`, sources (2)/(2b)/(3) each `raise LookupError("no project")` (`:4016,:4039,:4063`) and each appends its own "could not be read" warning too ⇒ **4 warnings for 3 unread sources** on the most common degraded book (no composition Work). The count must come from the backend.

**BUILD — BE (lands inside the `build_diagnostics()` extraction M1/DoD-1 already mandates, so MCP + REST share it):**
1. `agent_native.py` — `Diagnostics` gains `degraded_sources: int = 0` and a method `source_failed(self, warning: str) -> None` that appends to `warnings` AND increments the counter. `ranked()` emits `**({"degraded_sources": self.degraded_sources} if self.degraded_sources else {})` — omitted when 0, so BE-1's "byte-identical to `Diagnostics.ranked()`" clause still holds for the clean payload.
2. `build_diagnostics()` — every one of the 6 sources' `except` blocks (`server.py:4011,4031,4058,4073,4104,4130`) and the two explicit degrade branches (`pd.degraded` :4089, `cov.degraded` :4117) call `diag.source_failed(...)`. The cap notice (:4053) keeps plain `warnings.append` — it is a truncation, not a failure.
3. Delete the umbrella append (`:3973-3976`) and the three `raise LookupError("no project")` lines; instead guard sources (2)/(2b)/(3) with `if pid is None: diag.source_failed("<source> could not be read — this book has no composition work"); else: <try block>`. Result: no-Work book ⇒ exactly 3 warnings, `degraded_sources: 3`. (Motif applications are not a source here; drop them from the copy.)

**BUILD — FE (`IssuesTab.tsx`, `useDiagnostics.ts`, `en/studio.json`):**
- Strip renders iff `warnings.length > 0` — **above the rows, in both the empty AND the populated state**. `data-testid="issues-warnings-strip"`, `role="status"`, amber (`border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-400`), an i18n heading + a `<ul>` with ONE `<li>` per warning rendering the BE string **verbatim** (no truncation, no re-wording, no i18n of the body — the string IS the message).
- Empty body (`items.length === 0`): `warnings.length === 0` ⇒ `issues.emptyClean` = "No issues found across 6 sources." + the 6-source list. `warnings.length > 0` ⇒ `issues.emptyDegraded` = "No issues found in the sources that answered — {{count}} of 6 sources could not be read." with `count = data.degraded_sources ?? 0`, `data-testid="issues-empty-degraded"`. **`emptyClean` is unreachable whenever `warnings` is non-empty** — assert that, don't just intend it.

**TESTS (this is DoD-3, literal):**
- `IssuesTab.test.tsx`: (a) `{items: [], warnings: ['a','b'], degraded_sources: 2}` ⇒ strip present, both strings verbatim, `issues-empty-degraded` matches /2 of 6 sources could not be read/, `queryByText(/No issues found across 6 sources/) === null`. (b) clean = `{items: [], counts: {}, total: 0, refs_capped: false}` with **NO `warnings` key at all** (the real wire shape) ⇒ no strip, clean copy, no crash. (c) `{items: [row], warnings: ['showing 25 of 38 broken canon rules']}` ⇒ strip renders and PRECEDES `issues-row-0` in DOM order.
- `tests/test_diagnostics_route.py`: (a) make `book_client.list_chapters` raise ⇒ `"unplanned_chapter" not in body["counts"]`, `body["warnings"]` non-empty, `body["degraded_sources"] >= 1` — **never `unplanned: 0`**. (b) clean book ⇒ `"warnings" not in body and "degraded_sources" not in body`. (c) no-Work book ⇒ `body["degraded_sources"] == 3` and `len(body["warnings"]) == 3` (the anti-double-count regression guard).

Default I am picking (veto-able): the extra `degraded_sources` int rather than making the FE count strings. Counting free-text warnings to produce "N sources" is guessing, and this is the one screen that must not guess.

*Evidence:* services/composition-service/app/services/agent_native.py:152 (`warnings` key OMITTED when empty ⇒ FE must default `?? []`); :94-103 (`Block.into` — absent≠zero); :60-73 (SEVERITY = 8 kinds, not 7 sources). services/composition-service/app/mcp/server.py:3960-4132 (SIX source blocks, not seven); :3973-3976 + :4016/:4039/:4063 (no-project umbrella warning double-counts with the three per-source warnings ⇒ 4 warnings / 3 unread sources); :4053 (`"showing X of Y broken canon rules"` is a cap notice, not a source failure) ⇒ `warnings.length` ≠ "N sources could not be read". frontend/src/features/studio/components/StudioBottomPanel.tsx:43-45 (the shared stub being replaced).

### Q-37-REFS-CAPPED-FIELD-SHAPE
VERIFIED — the spec is correct and `refs_capped` is NOT a copy-paste. `Diagnostics.ranked()` returns exactly `{items, counts, total, refs_capped, warnings?}`; counts are exact, only rows are capped. "refs" = the diagnostic item ROWS (the module's own term, agent_native.py:35-37: "exact COUNTS, capped REFS (OUT-5 verbatim)"), not entity-references. KEEP THE NAME — it is load-bearing across the already-shipped MCP tool (server.py:4132), its test (test_agent_native.py:210-213), and the single shared `build_diagnostics()` that spec 37 DoD #1 requires both surfaces to call. A rename buys nothing and breaks three call sites.

BUILDER INSTRUCTION — mirror byte-for-byte:

useDiagnostics.ts types:
  type Severity = 'error' | 'warn' | 'info';
  type DiagKind = 'canon_contradiction' | 'broken_canon_rule' | 'prose_deleted_spec_node'
    | 'conformance_never_run' | 'conformance_dirty' | 'index_stale'
    | 'unplanned_chapter' | 'open_thread_debt';   // the 8 SEVERITY keys, agent_native.py:60-73
  interface DiagnosticItem { kind: DiagKind; severity: Severity; title: string;
    detail?: string; node_ref?: {kind: string; id: string; title?: string}; at?: string; }
  interface DiagnosticsResponse { book_id: string; items: DiagnosticItem[];
    counts: Partial<Record<DiagKind, number>>; total: number; refs_capped: boolean;
    warnings?: string[]; computed_at: string; }

BE-1 response model = `{book_id, **ranked()}` + `computed_at`, exactly as server.py:4132 does.
Footer: `Showing {items.length} of {total} findings` — refs_capped === (total > items.length).

THREE SPEC ERRORS FOUND — fix these while building, they are not optional:

(1) `counts` is KIND-keyed, NOT severity-keyed (agent_native.py:126: `self.counts[d.kind] = ...`). Spec 37 §4.1 says the toolbar renders "severity filter chips (All · Error 2 · Warn 5 · Info 1 — counts from the exact `counts` map)". That is IMPOSSIBLE as written: `counts["error"]` is `undefined`. The FE MUST fold kind→severity through the SEVERITY map (agent_native.py:60-73) to compute the severity chip counts. A builder following §4.1 literally renders "Error 0" on a book with 2 canon contradictions — the exact false-clean lie the module exists to prevent. Export the kind→severity map to FE (or have BE-1 additionally emit `counts_by_severity`); pick ONE and test it.

(2) `warnings` is OMITTED when empty, not `[]` (conditional spread, agent_native.py:152). Same for per-item `detail`/`node_ref`/`at` (lines 142-144). All optional in TS; `res.warnings.length` crashes on a clean book. Read as `(res.warnings ?? [])`.

(3) `computed_at` does NOT exist in ranked() — the BE-1 route must add it. Spec §4.1/§4.1.2 footer ("computed just now" / the Stale row) assumes it.

CAVEAT (note, do not "fix" mid-wave): `total` is findings COLLECTED. Two sources pre-cap at the source (server.py:4091 `pd.nodes[:cap]`, server.py:4121 `cov.unplanned[:cap]`), so a book with 40 unplanned chapters at limit=25 reports total=25, refs_capped=false. Existing engine behavior, out of scope for a field-shape question; the footer stays honest about what was collected.

BE-1 is unbuilt work to WRITE: no diagnostics route exists in composition-service/app/routers/ today (grep: zero hits). Gateway auto-proxies it (gateway-setup.ts:354).

*Evidence:* services/composition-service/app/services/agent_native.py:128-153 (`Diagnostics.ranked()` returns items/counts/total/refs_capped/warnings; line 151 `"refs_capped": len(ordered) > cap`; line 152 conditional-spread omits `warnings` when empty; lines 142-144 omit detail/node_ref/at). agent_native.py:35-37 (docstring defines "refs" = capped item ROWS, OUT-5). agent_native.py:126 (`self.counts[d.kind]` — KIND-keyed, the §4.1 severity-chip bug). agent_native.py:60-73 (SEVERITY = the 8-kind closed set) + :74 (_RANK). services/composition-service/app/mcp/server.py:4132 (`return {"book_id": str(bid), **diag.ranked(cap=cap)}`) + :3966 (limit clamp `max(1, min(int(limit or 25), 100))`). tests/unit/test_agent_native.py:201-227 (locks exact-counts/capped-rows + the degraded warnings path). grep of composition-service/app/routers/ for "diagnostics" = 0 hits ⇒ BE-1 is unbuilt work to write.

### Q-37-DEGRADED-SOURCE-BE-TEST
BUILD IT — and build it against the payload that actually exists, not the one DoD-2's wording implies. There is NO `coverage` key in the diagnostics payload: `Diagnostics.ranked()` (agent_native.py:128-153) emits `{items, counts, total, refs_capped, warnings?}` and `counts` is SPARSE (a kind appears only when `add()` fired). So the DoD-2 assertion set, restated concretely:

FILE: services/composition-service/tests/unit/test_diagnostics_route.py (new; mirror the bare-app + dep-override harness of tests/unit/test_plan_overlay.py:260-340, and the naming of its precedent test at line 227 `test_degraded_coverage_OMITS_the_key_and_warns`).

TEST 1 — `test_degraded_spine_OMITS_the_coverage_kinds_and_warns` (the DoD-2 test):
  Fake BookClient whose `list_chapters(...)` raises `BookClientError(503, "book-service unreachable")` on EVERY call. Override the route's book-client + outline-repo + grant deps; GET /v1/composition/books/{bid}/diagnostics. Assert:
    a. `resp.status_code == 200`  (never 500 on a degraded source)
    b. `"unplanned_chapter" not in body["counts"]`  — NOT `== 0`. This is the real form of "no coverage key": counts must stay sparse. (Also add: `assert set(body["counts"]) <= set(SEVERITY)` and that no one seeds zeros for the 8 SEVERITY keys — a zero-seeded counts map is the exact regression this test exists to kill.)
    c. `"prose_deleted_spec_node" not in body["counts"]` — 🔴 THE TRAP: `list_chapters` feeds TWO sources, not one. `compute_prose_deleted` (server.py:4085 → coverage.py:188) AND `compute_coverage` (server.py:4115 → coverage.py:135) each read the spine. One raising fake degrades BOTH.
    d. no item in `body["items"]` has `kind` in {"unplanned_chapter","prose_deleted_spec_node"}
    e. `len(body["warnings"]) == 2` and both substrings present: "unplanned chapters are unknown for this book (not zero)" (coverage.py:143) and "prose-deleted spec nodes are unknown for this book (not zero)" (coverage.py:197). A test asserting ONE warning will red — that is by design.
    f. the OTHER sources still populate: seed one open thread (or one canon issue) via the fake outline repo and assert its kind IS in `counts` — proving degrade is per-source, not a whole-payload wipe.

TEST 2 — `test_raw_transport_error_does_not_500` (one extra fake, ~10 lines): same but the fake raises a bare `RuntimeError("connect timeout")` (NOT a BookClientError). `compute_coverage`/`compute_prose_deleted` catch ONLY `BookClientError` (coverage.py:138, 190), so the sole thing between an unwrapped transport error and a 500 is the outer `except Exception` in the fanout (server.py:4132, 4092). BE-1a moves that fanout into `agent_native.build_diagnostics()` — this test is what proves the try/except survived the lift. Assert `status_code == 200` and `body["warnings"]` contains "the planned-vs-written diff could not be computed" + "prose-deleted spec nodes could not be checked".

TEST 3 (cheap, same file) — parity: call `build_diagnostics()` directly with the same raising fake and assert `.ranked()` equals the route body minus `book_id`. This is DoD-1's "one fanout, no fork" guard at test level.

WIRING THE BUILDER MUST NOT GET WRONG (BE-1a): extract server.py:3970-4132 verbatim into `async def build_diagnostics(*, pool, book_client, book_id, bearer, cap) -> Diagnostics` in app/services/agent_native.py (it resolves its own `pid` via `resolve_scope(WorksRepo(pool), book_id)` so both callers pass the same 5 args). KEEP every per-source `try/except Exception: diag.warnings.append(...)` — those ARE the "never 500 on a degraded source" contract; deleting one to "clean up" is the bug. The MCP tool passes `mint_service_bearer(tc.user_id, …)`; the NEW route passes the USER's own JWT via `bearer: str = Depends(get_bearer_token)` (precedent: routers/plan_overlay.py:255 calls `compute_coverage(book_id, bearer, …)` with exactly that) — minting a service bearer inside a user-facing route re-opens the internal-route-must-grant-check hole. Route lives in a new app/routers/diagnostics.py with `APIRouter(prefix="/v1/composition")`, `GET /books/{book_id}/diagnostics`, E0 VIEW gate FIRST via `authorize_book` with the H13 uniform mapping (OwnershipError⇒404, InsufficientGrant⇒403) — copy routers/conformance.py:423-454 wholesale; register in main.py next to `app.include_router(conformance.router)` (main.py:244).

Default I am choosing (veto-able): the route does NOT dedupe the two spine reads — it fans out to book-service twice, exactly as the MCP tool does today. Deduping is a correctness-neutral optimization that would change `build_diagnostics`'s shape and give the two sources a shared failure mode; not worth it on a cheap read.

*Evidence:* services/composition-service/app/services/agent_native.py:128-153 (`ranked()` → {items,counts,total,refs_capped,warnings?} — NO `coverage` key; counts sparse via `add()` at :124-126) · services/composition-service/app/services/coverage.py:135-145 + :188-199 (BOTH `compute_coverage` and `compute_prose_deleted` call `list_chapters(..., raise_on_404=True)` and degrade to `degraded=True` + warning; they catch ONLY BookClientError at :138/:190) · services/composition-service/app/mcp/server.py:4085-4132 (sources (4)+(5): `if degraded: diag.warnings.append(...)`, each wrapped in `except Exception` → never raises) · services/composition-service/tests/unit/test_plan_overlay.py:227 (`test_degraded_coverage_OMITS_the_key_and_warns` — the precedent harness to mirror) · services/composition-service/app/routers/plan_overlay.py:255 (user-bearer precedent for calling `compute_coverage` from a REST route) · services/composition-service/app/routers/conformance.py:423-454 (the route shape + H13 404/403 mapping to copy) · No existing test covers the diagnostics fanout's degraded path — grep of tests/unit/test_agent_native.py shows only `Block.into()` unit coverage (:42-53).

### Q-37-PLANHUB-CAN-IT-REVEAL-AN-OUTLINE-NODE
ANSWER = (a), with a correction the spec missed. The Plan Hub canvas holds BOTH id spaces in ONE keyspace — `focusNodeId` HAS something to reveal, and option (b) ("needs a different target panel") is wrong by code.

PROOF (the two collections are already merged):
- structure nodes (saga/arc): `usePlanHub.ts:66` `shell = getArcs(...).arcs` → `nodeContent[a.id]` (`usePlanHub.ts:109-113`), drawn as ArcRollupNode.
- outline nodes (chapter/scene): `usePlanWindows` → `windowsResult.content` → `nodeContent[n.id]` (`usePlanHub.ts:115-123`), drawn as ChapterNode/SceneNode. The comment at `usePlanHub.ts:106` states it outright: *"the window content wins on id collision — it never collides, arcs vs outline nodes"*.
- `laneLayout(shell, windows, collapse)` (`usePlanHub.ts:91`) emits BOTH families into `layout.nodes`; `select(id)` is one id space (`usePlanHub.ts:145`); the camera keys on a plain node id (`PlanCanvas.tsx:85`). So an outline_node.id and a structure_node.id are interchangeable inputs to select+pan today.

THE REAL GAP (this, not the id space, is what FE-1 must build): outline nodes are LAZILY windowed — a chapter card only exists once its ARC is expanded, a scene card only once its parent CHAPTER is expanded (`usePlanHub.ts:71-72`; `usePlanWindows.ts` header). And `expandAncestorsOf` (`usePlanHub.ts:152-167`) builds `byId` from the ARC SHELL ONLY, so handing it an `outline_node.id` finds nothing → `ancestors=[]` → early return → nothing expands → the camera pans to nothing. `PlanHubPanel.focusNode()` (`PlanHubPanel.tsx:104-114`) therefore works for arcs and SILENTLY NO-OPS for outline nodes.

BUILDER INSTRUCTION (M1b / FE-1) — 4 concrete changes:

1. ONE PARAM NAME, not two. `grep -rn "focusNodeId|focusArcId" services/ frontend/` = ZERO hits (verified) — both names exist only in docs, so there is no compat cost. **Collapse to a single `focusNodeId`** that accepts ANY plan-hub node id (saga | arc | chapter | scene). Retroactively fix §4.1.1: the `conformance_never_run` / `conformance_dirty` rows send `focusNodeId: <structure_node.id>`; `prose_deleted_spec_node` sends `focusNodeId: <outline_node.id>`. Two names for one concept violates the Frontend-Tool-Contract "one name for one concept" rule. (Default I am picking — veto-able: if the PO wants `focusArcId` kept, PlanHubPanel just coalesces `focusArcId ?? focusNodeId`, since it is one keyspace anyway.)

2. `usePlanHub.ts` — add `revealNode(nodeId: string): Promise<void>` to `PlanHubView` (logic in the hook, not the panel — MVC rule):
   - if `shell.some(s => s.id === nodeId)` ⇒ arc/saga: `expandAncestorsOf(nodeId)`, done.
   - else it is an outline node ⇒ resolve its ancestors via `compositionApi.getNode(nodeId, token)` (queryClient.fetchQuery, key `['plan-hub','node',nodeId]` — the SAME key `usePlanNode.ts` already uses, so it is cache-shared, no extra request). `OutlineNode` carries `parent_id` (`composition/types.ts:189`) and `structure_node_id` ("the arc a CHAPTER node is bound to (null on scenes)", `composition/types.ts:216`).
     - kind `chapter` ⇒ `arcId = node.structure_node_id`.
     - kind `scene` ⇒ `chapterNodeId = node.parent_id`; second `getNode(chapterNodeId)` ⇒ `arcId = chapter.structure_node_id`.
   - then: if `arcId` → `expandAncestorsOf(arcId)` **and** add `arcId` itself to `expandedArcs` (expandAncestorsOf deliberately expands only ANCESTORS — the arc itself must also be open or its chapter window never loads); if `chapterNodeId` → add it to `expandedChapters`. Both setters idempotent (return `prev` when already present, keeping identity).
   - `arcId === null` ⇒ the chapter lives in the always-loaded UNASSIGNED window (`usePlanWindows.UNASSIGNED_KEY`, "loads on EVERY book open") ⇒ no expand needed, just select+pan.

3. `PlanHubPanel.tsx` — read the deep-link param and drive the existing camera. Mirror the bus effect at `PlanHubPanel.tsx:120-127`:
   `const focusNodeId = (props.params as {focusNodeId?: string} | undefined)?.focusNodeId ?? null;` then a `useEffect` on `[focusNodeId]` that does `await view.revealNode(focusNodeId); focusNode(focusNodeId);`. This is a legitimate useEffect (synchronising an external request stream onto an imperative camera — same justification as the planFocus effect). Params on an ALREADY-OPEN panel arrive via `updateParameters` (`StudioHostProvider.tsx:83`), so dockview re-renders with new `props.params` and the effect refires — no extra plumbing.
   The camera needs no change: `CameraController` (`PlanCanvas.tsx:83-89`) already re-runs on `nodes` and pans as soon as the target appears, once per `seq` — so the async window load resolving a render later is exactly the case it was built for.

4. NO SILENT NO-OP (the pagination edge the spec never saw). An arc's chapter window is keyset-paged at `CHILD_PAGE = 100` (`usePlanWindows.ts:14`); a chapter past page 1 will not be in `layout.nodes` even after its arc expands, so the camera would silently never pan. Required: after reveal, if the id is still absent from `view.nodeContent` and the slice `hasMore`, call `loadMoreArc` (and, for scenes, `loadMoreChapter` — usePlanWindows exports it but `usePlanHub` does NOT currently return it: add it to `PlanHubView`) up to a bound of 5 pages; if still not found, render a `data-testid="plan-hub-focus-missing"` HUD notice ("that plan node isn't on this canvas — it may have been archived"), mirroring `ThreadsPanel`'s `composition-threads-focus-missing` (asserted in `planHubDeepLink.test.tsx:76`).

TESTS (Definition of Done for the slice):
- `frontend/src/features/plan-hub/hooks/__tests__/usePlanHubReveal.test.tsx` — reveal a SCENE id under a collapsed arc: asserts `getNode` is called twice (scene→chapter), and that the arc + parent chapter end up expanded (the scene node appears in `layout.nodes`). Reveal a CHAPTER id with `structure_node_id: null`: asserts NO expand happens and the node is selectable (unassigned strip).
- extend `frontend/src/features/studio/panels/__tests__/planHubDeepLink.test.tsx` — render `PlanHubPanel` with `props.params.focusNodeId` = an outline_node id, assert `select` fired with THAT id and the camera `focusTarget.nodeId` equals it (per plan 30 M1b: *asserting the tab mounted is NOT the assertion; asserting the right row is focused IS*), plus an unresolvable id renders `plan-hub-focus-missing`.
- Playwright: click the `prose_deleted_spec_node` row → the plan-hub canvas is centred on the offending chapter/scene card, not merely mounted.

Ownership caveat from plan 30 §5/§9 stands: `PlanHubPanel.tsx` is co-owned with the Book-Package track — do FE-1 after that handoff, but the design above is now settled and does not depend on it.

*Evidence:* frontend/src/features/plan-hub/hooks/usePlanHub.ts:106-123 (nodeContent merges arc-shell ids AND outline-node ids — "it never collides, arcs vs outline nodes"); :91 laneLayout(shell, windows) emits both families; :145 select() is one keyspace; :152-167 expandAncestorsOf builds byId from the ARC SHELL ONLY ⇒ an outline_node.id early-returns and expands nothing (the actual FE-1 bug); :71-72 "Only an OPEN arc/chapter loads its window". frontend/src/features/studio/panels/PlanHubPanel.tsx:39 (never reads props.params), :104-114 focusNode, :120-127 the bus effect to mirror. frontend/src/features/plan-hub/components/PlanCanvas.tsx:83-89 (camera re-runs on `nodes`, pans when the target appears — no change needed). frontend/src/features/composition/types.ts:189,216 (OutlineNode.parent_id + structure_node_id = the ancestor path) with compositionApi.getNode at frontend/src/features/composition/api.ts:207. frontend/src/features/plan-hub/hooks/usePlanWindows.ts:14 (CHILD_PAGE=100 → the pagination silent-no-op edge) and UNASSIGNED_KEY ("loads on EVERY book open"). frontend/src/features/studio/host/StudioHostProvider.tsx:83 (updateParameters delivers params to an already-open panel). `grep -rn "focusNodeId|focusArcId" services/ frontend/` → ZERO hits ⇒ renaming to one param is free.

### Q-37-BEARER-USER-JWT-NOT-SERVICE
Answer (a) — the user's own JWT works and is the correct bearer. The spec's claim is VERIFIED; BE-1 can be written exactly as specced. Builder instructions:

1. In the new `read_diagnostics` route (`services/composition-service/app/routers/agent_native.py` or wherever BE-1 lands), add the dependency EXACTLY as `plan_overlay.py:238` does:
   `from app.middleware.jwt_auth import get_bearer_token, get_current_user`
   `bearer: str = Depends(get_bearer_token),`
   Do NOT import or call `mint_service_bearer` anywhere in the route module.

2. Order is load-bearing: run the E0 VIEW gate FIRST (`await _gate_book(grant, book_id, user_id, GrantLevel.VIEW)` — mirror `plan_overlay.py:249`, which yields the uniform 403/404 no-oracle behavior), THEN pass `bearer` down. book-service re-checks the grant anyway (`authBook(..., GrantView)`), so the two gates agree; the route's gate exists for the uniform error shape, not for safety.

3. The extracted `agent_native.build_diagnostics(pool, book_client, book_id, bearer, cap) -> Diagnostics` keeps `bearer: str` as a plain parameter (this is what `compute_coverage`/`compute_prose_deleted` already do at coverage.py:118 / coverage.py:175 — no engine change needed). The REST route passes `Depends(get_bearer_token)`; the MCP tool KEEPS `mint_service_bearer(tc.user_id, settings.jwt_secret)` because the MCP envelope genuinely carries no JWT (service_bearer.py:1-30 documents exactly this). Do not "clean up" the MCP path's minting — that is correct there and wrong in the route.

4. No new internal book-service route is required. Do not design a grant-checked internal call; candidate (b) is moot.

5. Test to write: a route test asserting that the `Authorization` header the composition route received is the SAME token forwarded to book-service's `GET /v1/books/{id}/chapters` (spy on `BookClient._request`), and that `mint_service_bearer` is NEVER called on the REST path (`patch.object(module, "mint_service_bearer", side_effect=AssertionError)` — it must not be reachable, which also guards against a later copy-paste from the MCP handler re-opening the internal-route-driven-by-a-session hole).

*Evidence:* book-service/internal/api/server.go:296 — `r.Get("/chapters", s.listChapters)` sits under `r.Route("/v1/books")` → `/{book_id}`, NOT under the `/internal` group (server.go:185-186 is the only place `requireInternalToken` is applied; the internal twin is a separate handler at server.go:204). server.go:1283 — `listChapters` gates with `s.authBook(w, r, bookID, GrantView)`, which at book-service/internal/api/collaborators.go:149 calls `s.requireUserID(r)` and resolves the E0 grant from the JWT `sub` — i.e. the route is JWT-only + grant-checked, and a service token is not accepted at all. composition-service/app/clients/book_client.py:356 — `list_chapters` calls exactly `GET /v1/books/{book_id}/chapters` with the forwarded bearer. composition-service/app/mcp/service_bearer.py:1-30 (docstring) — "Those routes are **public JWT-only** ... book-service enforces book ownership in SQL keyed on the JWT `sub` claim. The MCP envelope carries NO JWT" — the minting exists solely because the MCP envelope lacks a JWT, not because book-service demands a service token. Precedent CONFIRMED: composition-service/app/routers/plan_overlay.py:238 `bearer: str = Depends(get_bearer_token)` → :249 `_gate_book(..., GrantLevel.VIEW)` → :255 `compute_coverage(book_id, bearer, book=book, outline=outline)` (same pattern in engine.py:331/707/905, arc.py:587, approve.py:83, outline.py, grounding.py:67, authoring_runs.py:213). Engine signatures already bearer-agnostic: composition-service/app/services/coverage.py:118 `compute_coverage(book_id, bearer, *, book, outline)` and coverage.py:175 `compute_prose_deleted(book_id, bearer, *, book, outline)`.

### Q-37-IF4-INERT-ROW-RULE
AFFIRM IF-4 as written — its premise is verified in code (both target panels are param-blind receivers) — but ship it with three corrections, because the spec's own row-count is wrong and would leak the exact bug IF-4 exists to prevent.

(1) THE RULE STANDS. A row renders with NO chevron, is NOT clickable, and carries its reason in `title` when EITHER no panel owns the fix OR its target panel is param-blind. "The panel will actually focus what I clicked" is the test, not "the panel exists". Ship M1 inert; light up in M1b. No re-litigation.

(2) 🔴 FIX THE COUNT — IT IS 4 INERT FE-1 KINDS, NOT 3. `agent_native.py:60-72` defines 8 SEVERITY kinds; spec §4.1.1's routing table has 7 rows because `conformance_never_run` and `conformance_dirty` are TWO distinct kinds collapsed into ONE table row. The DoD test as specced ("the 3 FE-1 rows have no chevron") counts table rows — a builder implementing per-`kind` leaves the 4th kind CLICKABLE, opening `plan-hub` onto nothing. That is the silent-success-is-a-bug class IF-4 was written to kill, smuggled in through the test that was supposed to guard it. True M1 tally: 3 CLICKABLE (`canon_contradiction`, `broken_canon_rule` → quality-canon; `open_thread_debt` → quality-promises) and 5 INERT (`prose_deleted_spec_node`, `conformance_never_run`, `conformance_dirty`, `unplanned_chapter` = FE-1 case 2; `index_stale` = case 1, no panel). Correct spec 37's M1 line "4 live rows (quality-canon ×2, quality-promises, index_stale-inert)" — it double-counts `index_stale` as live while calling it inert.

(3) MAKE IT DATA-DRIVEN so M1b's flip is one line and the test cannot drift. In a new `frontend/src/features/studio/components/issueRoutes.ts`, export ONE table keyed by the 8 kinds — `ISSUE_ROUTES: Record<IssueKind, {panel: PanelId, params: (i: Diagnostic) => object} | null>` (null = case 1, no panel) — plus `const PARAM_BLIND_PANELS = new Set(['plan-hub', 'chapter-browser'])` (case 2). Export ONE predicate: `isClickable(kind) = ISSUE_ROUTES[kind] !== null && !PARAM_BLIND_PANELS.has(ISSUE_ROUTES[kind].panel)`. The `IssuesTab.tsx` row renderer emits a chevron + onClick IFF `isClickable(kind)`, else renders no chevron, no handler, and a `title` from `inertReason(kind)` — two distinct strings, because the two cases are not the same promise to the user: case 1 = "the sweeper heals this automatically — nothing to open", case 2 = "the Plan Hub can't focus this yet". Do NOT give an unfixable row a "coming soon" title.

M1b (FE-1) then = teach `PlanHubPanel` to read `props.params.{focusNodeId,focusArcId}` and `ChapterBrowserPanel` to read `props.params.focusChapterId`, both hoisting+revealing by mirroring `useQualityCanon.ts:64` `hoist()` (a focus HOISTS and HIGHLIGHTS, it never filters/hides), then DELETE the two entries from `PARAM_BLIND_PANELS`. That single deletion lights up all 4 rows with zero edits to the row renderer.

THE TEST (M1 DoD, replaces the specced "3 rows" assertion): drive it off the table, never off a hardcoded kind list — `for (const kind of ALL_8_KINDS)` render a row and assert `queryByTestId('issue-chevron')` is null and `click()` mounts NO dock tab exactly when `!isClickable(kind)`. Add ONE arithmetic guard: `expect(ALL_KINDS.filter(isClickable)).toHaveLength(3)` and `expect(inert).toHaveLength(5)`, with a comment naming the 4 FE-1 kinds. This test PASSES UNCHANGED through M1b's flip only if the counts are updated deliberately (3→7 clickable, 5→1 inert) — so M1b cannot silently leave a row dark, and M1 cannot silently let one through. That is the guard the spec wanted and mis-specified.

BUILDER NOTE (kills a 3am stall): spec 37 §4.1.1's warning "⚠ Both files are owned by the Book-Package track — coordinate before editing" is SOFT, not a lock. `docs/plans/2026-07-12-book-package-RUN-STATE.md` mentions `PlanHubPanel` in exactly two places — `:103` (A12, a test-COVERAGE debt row) and `:213` (DBT-03, a conscious won't-build) — neither is an in-flight edit of the file. M1b does NOT wait on a handoff nobody owes. Just check `git log --oneline -5 -- frontend/src/features/studio/panels/PlanHubPanel.tsx` before editing and proceed.

*Evidence:* PREMISE CONFIRMED: frontend/src/features/studio/panels/PlanHubPanel.tsx:39 (`useStudioPanel('plan-hub', props.api)` — return discarded, `props.params` never read; it only EMITS a deep-link at :74) · frontend/src/features/studio/panels/ChapterBrowserPanel.tsx:23 (same, reads no props.params) · `grep -rn "focusNodeId|focusArcId" frontend/src` → zero hits, confirming both params are unbuilt. RECEIVER PATTERN TO MIRROR: frontend/src/features/studio/panels/useQualityCanon.ts:64-75 (`hoist()`) and :111 (hoists on `i.chapter_id === focusChapterId`), contrasted with the working consumers QualityPromisesPanel.tsx:23 / JobDetailPanel.tsx:24. THE COUNTING BUG: services/composition-service/app/services/agent_native.py:60-72 — SEVERITY holds 8 kinds (canon_contradiction, broken_canon_rule, prose_deleted_spec_node, conformance_never_run, conformance_dirty, index_stale, unplanned_chapter, open_thread_debt) while spec 37 §4.1.1 (lines 248-255) has only 7 table rows — `conformance_never_run · conformance_dirty` share line 252 — so the FE-1 inert set is 4 KINDS, not the 3 the DoD (line 638, 679) asserts. OWNERSHIP CLAIM IS SOFT: docs/plans/2026-07-12-book-package-RUN-STATE.md:103 (A12 coverage debt) and :213 (DBT-03 won't-build) are the only PlanHubPanel mentions — no active edit. RENDER SITE: frontend/src/features/studio/components/StudioBottomPanel.tsx:8 (`type BottomTab = 'jobs' | 'generation' | 'issues'` — the Issues tab is still a stub).

### Q-37-SOURCE-COUNT-INCONSISTENT
**It is SIX sources / EIGHT kinds.** Not 7, not 5. (§5 BE-1's "8 SEVERITY keys" is CORRECT; §4.2's "EIGHT" refers to REFERENCE_SOURCES — a different closed set — and is also correct. Leave both.)

WHY: `SEVERITY` (agent_native.py:60-73) = 8 keys. The `composition_diagnostics` fanout = 6 independently-degradable producer blocks (server.py:3978 / 4013 / 4033 / 4060 / 4075 / 4106). `index_stale`, `conformance_dirty` and `conformance_never_run` all fall out of the ONE `compute_conformance_status` call — they cannot degrade independently, so they are one source, not three. Spec 37 §2 already enumerates exactly six engines while its own prose says "7"; the "7" was miscounted off §1.1's *kind* table. The "5" is a stale pre-PH18/pre-IX-13 count.

BUILDER INSTRUCTIONS (M1, in the BE-1 `build_diagnostics` extraction — spec 37 §5's "extract the body, do not fork it"):

1. `services/composition-service/app/services/agent_native.py` — after SEVERITY (line 73) add the two constants, so no number is ever hardcoded downstream:
```python
#: The diagnostics fanout's SOURCE set — one entry per independently-degradable producer block.
#: SIX, not seven: compute_conformance_status is ONE call that emits three kinds.
DIAGNOSTIC_SOURCES: tuple[str, ...] = (
    "conformance",          # compute_conformance_status → conformance_dirty|_never_run|index_stale
    "canon_contradiction",  # OutlineRepo.canon_issues
    "canon_rule",           # OutlineRepo.rule_violations
    "thread_debt",          # NarrativeThreadRepo.list_open
    "prose_deleted",        # compute_prose_deleted
    "coverage",             # compute_coverage
)
KIND_SOURCE: dict[str, str] = {
    "conformance_dirty": "conformance", "conformance_never_run": "conformance",
    "index_stale": "conformance", "canon_contradiction": "canon_contradiction",
    "broken_canon_rule": "canon_rule", "open_thread_debt": "thread_debt",
    "prose_deleted_spec_node": "prose_deleted", "unplanned_chapter": "coverage",
}
```
TEST (mirror the existing binding test at tests/unit/test_agent_native.py:239): assert `set(KIND_SOURCE) == set(SEVERITY)` and `set(KIND_SOURCE.values()) == set(DIAGNOSTIC_SOURCES)`. That makes a future 7th source impossible to add without updating both — the drift this question is about becomes unwritable.

2. `Diagnostics` gains `degraded_sources: list[str]`. Each of the 6 except-blocks (and the `cov.degraded` / `pd.degraded` branches) appends its source id alongside its warning string. Each emitted `Diagnostic` row gains `source: KIND_SOURCE[kind]` (ships with BE-1a's `ref_kind` widening). `ranked()` payload gains `sources: list(DIAGNOSTIC_SOURCES)` + `degraded_sources`. Back-port to the MCP tool (same body — it is extracted, not forked).

3. 🔴 FE MUST NOT compute "N sources could not be read" from `len(warnings)` — `warnings[]` also carries NON-source entries: the no-Work notice (server.py:3973) and the broken-canon-rule cap notice (server.py:4053). Counting warnings over-reports failed sources on a healthy book with no Work. Use `degraded_sources.length`.

4. i18n (en/studio.json): NO literal number. `issues.empty` = "No issues found across {{count}} sources." with `count = data.sources.length` (renders 6); `issues.emptyDegraded` = "No issues found in the sources that answered — {{count}} sources could not be read." with `count = data.degraded_sources.length`. Render the source list from `data.sources` (§4.1.2 wants "and the source list").

5. BE-1 route: `kind` enum = the 8 SEVERITY keys (UNCHANGED — spec is right). Optionally add a `source` filter enum = the 6 DIAGNOSTIC_SOURCES.

6. Spec-doc corrections in `37_issues_feed.md` (do this in M1, same commit): §1 "seven sources" → "six sources"; §1.1 prose "~2.5 of 5 sources have a human surface" → "2 of the 8 kinds (`index_stale`, `prose_deleted_spec_node`) have NO human surface at all, and none of the 6 sources is ranked" (keep the table; retitle its header "Diagnostic kind (8 of them, across 6 sources)"); §2 "Each of the 7 sources" → "Each of the 6 sources" (its engine list is already correct at six); §4.1.2 empty copy → the derived {{count}} string. ALSO fix the stale MCP tool description at server.py:3936-3941 — it names only 5 of the 8 kinds (omits `broken_canon_rule` and `prose_deleted_spec_node`, the two ERROR classes).

DO NOT edit plan 30 §0 PO-1's "~2.5 of 5" rationale — §0 is SEALED, and the corrected count does not disturb the decision (AN-12's premise "the human equivalents already exist" is false at 5, 6, or 8). Note the correction in spec 37 only.

*Evidence:* services/composition-service/app/services/agent_native.py:60-73 — SEVERITY has exactly 8 keys (canon_contradiction, broken_canon_rule, prose_deleted_spec_node, conformance_never_run, conformance_dirty, index_stale, unplanned_chapter, open_thread_debt). services/composition-service/app/mcp/server.py:3978, 4013, 4033, 4060, 4075, 4106 — exactly 6 producer try-blocks in composition_diagnostics ((1) compute_conformance_status, (2) OutlineRepo.canon_issues, (2b) OutlineRepo.rule_violations, (3) NarrativeThreadRepo.list_open, (4) compute_prose_deleted, (5) compute_coverage), each with exactly ONE degrade path; index_stale is read off status["index"] inside block (1) (server.py:4004), so it is not a separate source. Spec 37 §2 (37_issues_feed.md:95-98) itself lists exactly those SIX engines under the words "Each of the 7 sources". Non-source warnings that break a len(warnings) count: server.py:3973 (no-Work notice) and server.py:4053 (rule-violation cap notice). REFERENCE_SOURCES (agent_native.py:44-56) is a DIFFERENT closed set and genuinely has 8 members — §4.2's "EIGHT" is right.

### Q-37-BE1A-MCP-BACKPORT
**The MCP "back-port" is ZERO schema work. Composition's MCP server has exactly ONE schema source (the FastMCP function signature — inputs only) and ZERO output-schema sources, and no existing test asserts the node_ref shape. Do not go hunting for a 3-source update; the knowledge-service lesson does not apply here (it was about INPUT args; BE-1a widens the OUTPUT).**

EVIDENCE FOR THAT CLAIM (builder may trust it, it is verified):
1. `server.py:101` `mcp_server = make_stateless_fastmcp("composition")` (`mcp.server.fastmcp`, `sdks/python/loreweave_mcp/context.py:69-94`). Tools are registered ONLY via `@mcp_server.tool(name=…, description=…, meta=require_meta(…))` + `Annotated` params. Composition has **no** `app/tools/definitions.py`, no bespoke `TOOL_DEFINITIONS`, no pydantic arg-model layer, no `execute_tool` dispatcher (grep across `services/composition-service/app` = zero hits). knowledge-service's 3 sources are its own; composition has 1.
2. I probed the installed MCP SDK: a FastMCP tool annotated `-> dict` advertises `outputSchema: null`. `composition_diagnostics` is `-> dict` (`server.py:3954`). **Nothing advertises, validates, or strips its response fields.** Adding `ref_kind`/`chapter_id`/`rule_id` is purely additive to an untyped payload.
3. `contracts/mcp-response-shapes/composition.json` pins only the `_*_REF_FIELDS` constants consumed by `apply_response_contract`. `composition_diagnostics` never calls `apply_response_contract` (it returns raw at `server.py:4132`) ⇒ **no `WRITE_MCP_SHAPES=1` regen, no contract file to touch.** And `shape_snapshot._assert_no_inline_ref_literals` only inspects `apply_response_contract(...)` call nodes (`shape_snapshot.py:53`), so the `Diagnostic(node_ref={...})` dict literals are outside that guard.
4. Zero MCP tests assert the old `node_ref` shape (`grep node_ref services/composition-service/tests` → no hit in `test_agent_native.py` / `test_mcp_server.py`; `test_mcp_server.py:106` only asserts the tool NAME is registered). No gateway, ai-gateway, agent-registry or frontend-tool-contract artifact names this tool's payload.

SO BUILD IT AS A ONE-PRODUCER CHANGE — then the back-port is a no-op by construction:

**Step 1 — widen the producer type.** `services/composition-service/app/services/agent_native.py:107-114`: add module constant `REF_KINDS = ("chapter", "outline_node", "structure_node")` beside `SEVERITY` (`:60-73`); add `rule_id: str | None = None` to `Diagnostic`; add `__post_init__` asserting `node_ref["ref_kind"] in REF_KINDS` whenever `node_ref` is set (closed set, fail loud — this is the IN-2/enum discipline the mcp-tool-io standard demands). `Diagnostics.ranked()` (`:128-153`) passes `node_ref` through untouched and must also emit `**({"rule_id": d.rule_id} if d.rule_id else {})`.

**Step 2 — rewrite the 5 `node_ref` emitters** in `server.py` to the 3 real id spaces (today they emit `kind: "arc" | "scene" | "chapter"` — `arc`/`scene` are NOT id spaces; §3 IF-1 is right). REPLACE the `kind` key with `ref_kind` (do not dual-write — nothing reads `kind`, grep-verified):
- `server.py:3998` conformance → `{"ref_kind":"structure_node","id":arc["structure_node_id"],"title":…}`
- `server.py:4025` canon_contradiction → `{"ref_kind":"outline_node","id":issue["scene_id"],"title":…,"chapter_id":issue["chapter_id"]}` — `canon_issues` already SELECTs `n.chapter_id` (`outline.py:1218`, returned at `:1247`); the id is an `outline_node.id` with `kind='scene'` (`outline.py:1230`).
- `server.py:4047` broken_canon_rule → same `outline_node` ref + `chapter_id`, PLUS top-level `rule_id=item["rule_id"]` — `rule_violations` already SELECTs `v.violation ->> 'rule_id' AS rule_id` (`outline.py:~1343`).
- `server.py:4099` prose_deleted_spec_node → `{"ref_kind":"outline_node","id":n["id"],"title":…,"chapter_id":n["chapter_id"]}` (rows come from `OutlineRepo.linked_chapter_nodes`, `outline.py:305-317`, which SELECTs `id,title,kind,chapter_id`). Drop the `n.get("kind") or "chapter"` passthrough — it was leaking the outline `kind` into a ref_kind slot.
- `server.py:4125` unplanned_chapter → `{"ref_kind":"chapter","id":str(ch["chapter_id"]),"title":…,"chapter_id":str(ch["chapter_id"])}`

**Step 3 — extract, don't duplicate (this IS the back-port).** BE-1's REST route must return a byte-identical payload, but the 5-source collection currently lives INLINE in the MCP handler (`server.py:3968-4132`). Lift it to `collect_diagnostics(*, pool, book_id, project_id, bearer, cap) -> Diagnostics` in `app/services/agent_native.py`, parameterized by `bearer` (MCP passes `mint_service_bearer(tc.user_id, settings.jwt_secret)` as today; the REST route passes the caller's own JWT per spec §5.1). `composition_diagnostics` then becomes: `_gate(…VIEW)` → `resolve_scope` → `collect_diagnostics(…)` → `return {"book_id": str(bid), **diag.ranked(cap=cap)}`. The router calls the same function. ONE producer ⇒ MCP and REST cannot drift, and "back-port" costs nothing.

**Step 4 — THE ONE THING THAT WILL GO RED (fix it, do not loosen it).** `tests/unit/test_agent_native.py` guards the diagnostics logic by SOURCE TEXT via `inspect.getsource(server.composition_diagnostics)`: lines **171-175** (`compute_conformance_status(`, `canon_issues(`, `list_open(`, `compute_coverage(`), **253-260** (every `SEVERITY` key appears in the source), **272-275** (`# (1)`…`# (5)` markers + `rule_violations(`), **349-351** (`cap = max(1, min(int(limit or 25), 100))` and no `[:limit]`). Step 3 moves that text out of the tool fn ⇒ these 4 tests break. **Re-point them at `inspect.getsource(agent_native.collect_diagnostics)` with every assertion intact** (they encode the silent-hole bug from `/review-impl`, docstring `:239-250`). Keep `test_diagnostics_NEVER_SPENDS` (`:178-190`) pointed at `server.composition_diagnostics` — the `require_meta("R","book")` block still lives there; also keep its `"conformance_run(" not in src` assertion true for the extracted fn (add the same assertion there).

**Step 5 — new guards (both surfaces, one truth).** In `test_agent_native.py` add: (a) `test_every_node_ref_declares_a_ref_kind_from_the_CLOSED_SET` — assert `REF_KINDS == ("chapter","outline_node","structure_node")` and that `"scene"` / `"canon_rule"` are NOT in it, and that a `Diagnostic(node_ref={"ref_kind":"scene",...})` raises; (b) `test_the_MCP_tool_and_the_REST_route_share_ONE_diagnostics_producer` — assert `"collect_diagnostics(" in inspect.getsource(server.composition_diagnostics)` AND in the router handler's source (this is the anti-drift assertion the back-port actually needs, replacing the schema hunt).

**Not touched, confirmed:** `contracts/` (nothing to regen), gateway (`gateway-setup.ts:354` generic pathFilter), ai-gateway federation, agent-registry catalog, `contracts/frontend-tools.contract.json`. Verify with `python -m pytest tests -q -n auto --dist loadgroup` in `services/composition-service`.

*Evidence:* services/composition-service/app/mcp/server.py:101 (make_stateless_fastmcp), :3934-3954 (tool decorator — inputs only, `-> dict`), :3998/:4025/:4047/:4099/:4125 (the 5 node_ref emitters), :4132 (raw return, no apply_response_contract) · app/services/agent_native.py:60-73 (SEVERITY), :107-114 (Diagnostic dataclass, node_ref), :128-153 (ranked passthrough) · app/db/repositories/outline.py:1218+1247 (canon_issues carries chapter_id), :1257+~1343 (rule_violations carries rule_id), :305-317 (linked_chapter_nodes carries chapter_id) · sdks/python/loreweave_mcp/shape_snapshot.py:29-63 (inline-literal guard fires ONLY on apply_response_contract calls) · contracts/mcp-response-shapes/composition.json (only _*_REF_FIELDS; no diagnostics entry) · tests/unit/test_agent_native.py:171-175,178-190,253-260,272-275,344-351 (source-text guards that Step 3 breaks) · tests/unit/test_mcp_server.py:106 (name-only registration check) · grep node_ref over services/composition-service/tests = zero shape assertions · probe of installed mcp SDK: FastMCP tool `-> dict` ⇒ outputSchema null.

### Q-37-BOTTOM-PANEL-TEST-INVERSION
Rewrite `StudioBottomPanel.test.tsx` in the SAME M1 slice that does the always-mounted refactor (never separately — the refactor reds `:12` by construction), and hide the inactive bodies with the HTML `hidden` ATTRIBUTE, not Tailwind's `hidden` class.

WHY THE ATTRIBUTE (this is the part the spec's §6 note does not say, and getting it wrong makes the fix red): vitest runs `environment: 'jsdom'` (`frontend/vite.config.ts:66`) with NO CSS loaded, so `className="hidden"` computes to `display:block` in jsdom and jest-dom's `toBeVisible()` would call a hidden body VISIBLE — `not.toBeVisible()` would falsely red. jest-dom (`frontend/vitest.setup.ts:1`) explicitly treats `hasAttribute('hidden')` as not-visible, and jsdom's UA stylesheet applies `[hidden]{display:none}`. The repo's shipped precedent for keep-mounted tab bodies is `frontend/src/features/knowledge/components/EntityDetailPanel.tsx:332` — `<div hidden={panelTab !== 'current'} …>`. Mirror it.

1) COMPONENT (`frontend/src/features/studio/components/StudioBottomPanel.tsx`) — replace the single body div at :43-45 with three always-mounted siblings (CLAUDE.md: never conditionally unmount stateful components; the Jobs tab will own an SSE subscription):
```tsx
const BODIES: Record<BottomTab, React.ComponentType> = { jobs: JobsTab, generation: GenerationTab, issues: IssuesTab };
…
{TABS.map((tb) => {
  const Body = BODIES[tb];
  return (
    <div
      key={tb}
      role="tabpanel"
      data-testid={`bottom-body-${tb}`}
      hidden={tab !== tb}                                   // ← HTML attribute: jsdom + jest-dom honor it
      className={cn('flex-1 overflow-y-auto', tab !== tb && 'hidden')}  // class is for prod CSS only
    >
      <Body />
    </div>
  );
})}
```
(In M1 `JobsTab`/`GenerationTab` are still stub bodies, but they are REAL components rendering the honest §4.3 copy — not the `bottomStub.*` "once wired" lie. `IssuesTab` is live.)

2) TEST — delete both `textContent` assertions (`:9`, `:12`) and replace the whole first `it` with a table-driven guard + a visibility assertion. Keep the second `it` (onClose) unchanged:
```tsx
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { StudioBottomPanel } from '../StudioBottomPanel';

const TABS = ['jobs', 'generation', 'issues'] as const;   // must equal StudioBottomPanel's TABS

describe('StudioBottomPanel', () => {
  // DoD-4: every BottomTab id has a bottom.<id> label key AND a rendered body component.
  it.each(TABS)('tab %s has a label key and a mounted body', (tb) => {
    render(<StudioBottomPanel onClose={vi.fn()} />);
    expect(screen.getByText(`bottom.${tb}`)).toBeInTheDocument();       // i18n mock returns the KEY
    expect(screen.getByTestId(`bottom-body-${tb}`)).toBeInTheDocument(); // always MOUNTED, even when inactive
  });

  it('defaults to Jobs and switches tabs by VISIBILITY, not by mount/textContent', () => {
    render(<StudioBottomPanel onClose={vi.fn()} />);
    expect(screen.getByTestId('bottom-body-jobs')).toBeVisible();
    expect(screen.getByTestId('bottom-body-generation')).not.toBeVisible();

    fireEvent.click(screen.getByText('bottom.generation'));

    expect(screen.getByTestId('bottom-body-generation')).toBeVisible();
    expect(screen.getByTestId('bottom-body-jobs')).not.toBeVisible();   // still MOUNTED — hidden, not destroyed
    expect(screen.getByTestId('bottom-body-jobs')).toBeInTheDocument();  // the anti-unmount guard
  });
});
```
No assertion anywhere may reference `bottomStub.*` — that string is being deleted, and asserting on `textContent` after the refactor is precisely how a green test certifies the wrong thing (all three hidden bodies still contribute to `textContent`).

3) If any child body pulls context (React-Query, JobsStreamProvider), render through the existing `src/test/renderWithClient.tsx` helper rather than bare `render`.

Default I am picking (veto-able): the three bodies stay plain `hidden`-attribute divs rather than a `role="tablist"`/`aria-controls` ARIA tab widget — a full ARIA tab pattern is an a11y improvement worth doing, but it is not what this question asks and it would balloon M1's diff. If the PO wants the ARIA pattern, it is an additive follow-up on the same file.

*Evidence:* frontend/src/features/studio/components/__tests__/StudioBottomPanel.test.tsx:9 (`expect(panel.textContent).toContain('bottomStub.jobs')` — guards the stub) and :12 (`not.toContain('bottomStub.jobs')` — reds under always-mounted, since hidden elements still contribute textContent) · frontend/src/features/studio/components/StudioBottomPanel.tsx:43-45 (single active-tab body div = the thing being replaced) · frontend/vite.config.ts:66 (`environment: 'jsdom'`, no CSS ⇒ Tailwind `.hidden` class does NOT make jest-dom's toBeVisible() false) · frontend/vitest.setup.ts:1 (`@testing-library/jest-dom/vitest` ⇒ toBeVisible() available; it honors the `hidden` ATTRIBUTE) · frontend/vitest.setup.ts:24-40 (react-i18next mocked to return the KEY, ignoring defaultValue ⇒ assert on `bottom.<id>`) · frontend/src/features/knowledge/components/EntityDetailPanel.tsx:332 (`<div hidden={panelTab !== 'current'} …>` — the repo's shipped keep-mounted-tab-body precedent to mirror) · docs/specs/2026-07-01-writing-studio/37_issues_feed.md:526-536 (§6 guard) + :662-663 (DoD-4)

### Q-37-REACTQUERY-MANDATORY
CONFIRMED BY CODE — it is a hard constraint, and here is the exact contract the builder implements (no further thought required).

1) `frontend/src/features/studio/hooks/useDiagnostics.ts` (new) MUST own its rows with `useQuery` from `@tanstack/react-query`. NO `useState`+`useEffect` loader, NO manual `fetch` in the component. Exactly:
   - `useQuery({ queryKey: ['composition', 'diagnostics', bookId], queryFn: () => compositionApi.getDiagnostics(bookId, { cap }), staleTime: 60_000, enabled: !!bookId })`
   - The lens hook (`EntityReferencesLens`) uses `queryKey: ['composition', 'entity-references', bookId, entityId]` — note the bookId sits at index 2 so the handler's prefix-invalidate on `['composition','entity-references', bookId]` reaches every entity's cached lens for that book.
   - The `warnings[]` / omitted-source branch (§4.2 "absent ≠ zero") is derived from the query's `data`, not stored separately — a second useState mirror of query data reintroduces the same staleness bug at half scale.
   - Refresh button = `refetch()` from the same query. Tab-open = the query going active. Both fall out of React-Query for free; do not hand-roll either.

2) `frontend/src/features/studio/agent/handlers/diagnosticsEffects.ts` (new) registers the invalidation, per spec §7.1 — but EXTEND the spec's regex, because the code shows prose/chapter writes also stale this feed (`index_stale`, `prose_deleted_spec_node`, `unplanned_chapter`, `conformance_dirty` all move on a chapter write, and `bookEffects.ts:59-60` already treats those tool names as book/prose writes):
   ```ts
   let registered = false;
   const DIAGNOSTICS_STALING = /^composition_(canon_rule_|conformance_run|outline_node_|arc_|motif_(bind|unbind))/;
   const PROSE_STALING = /^(book_.*(draft|chapter)|composition_.*(prose|draft))/;
   export function diagnosticsEffect(ctx: EffectContext): void {
     ctx.queryClient.invalidateQueries({ queryKey: ['composition', 'diagnostics', ctx.bookId] });
     ctx.queryClient.invalidateQueries({ queryKey: ['composition', 'entity-references', ctx.bookId] });
   }
   export function registerDiagnosticsEffectHandlers(): void {
     if (registered) return; registered = true;
     registerEffectHandler(DIAGNOSTICS_STALING, diagnosticsEffect);
     registerEffectHandler(PROSE_STALING, diagnosticsEffect);
   }
   ```
   Wire it in `useStudioEffectReconciler.ts` alongside the 4 existing `register*EffectHandlers()` calls (lines 35-39 + the import block at 18-21), and delete the now-false comment at `useStudioEffectReconciler.ts:7-9`. Invalidation is cheap (React-Query only refetches ACTIVE observers), so the widened pattern costs nothing when the Issues tab is not mounted.

3) StudioBottomPanel's 3-body always-mounted refactor (M1) is what makes this actually fire: with Issues/Jobs/Generation all mounted and hidden via CSS (never ternary-unmounted — CLAUDE.md FE rule), the diagnostics query stays an ACTIVE observer even while another tab is showing, so the Lane-B invalidate refetches immediately instead of waiting for a remount.

4) THE TEST THAT MAKES THIS REAL (the constraint is worthless if only spy-asserted — a spy on `invalidateQueries` passes even if the tab uses `useState`). In `frontend/src/features/studio/agent/__tests__/diagnosticsEffects.test.tsx`: render `<IssuesTab bookId="b1"/>` inside a REAL `QueryClientProvider` with a stubbed `compositionApi.getDiagnostics`; await first render (fetch called once); then call `diagnosticsEffect({ tool: 'composition_canon_rule_update', bookId: 'b1', queryClient, ... })`; assert `getDiagnostics` was called a SECOND time and the new row text appears in the DOM. Prove refresh BY EFFECT, not by spy. Add the same shape for `book_save_chapter_draft` to lock the widened PROSE_STALING pattern.

Grounding: this is not a preference — `EffectContext` (effectRegistry.ts:9-24) exposes only `queryClient` as a generic refresh channel; its two other escape hatches (`reloadChapter`/`reloadScenes`) are hard-bound to the Tier-4 manuscript hoist and have no bottom-panel analogue. A useState-held Issues feed is therefore unreachable from Lane B by construction, and the panel would silently show a problem the agent already fixed.

*Evidence:* frontend/src/features/studio/agent/effectRegistry.ts:14 (`queryClient: QueryClient` is the only generic refresh channel in EffectContext; lines 20-23 `reloadChapter`/`reloadScenes` are Tier-4-hoist-only, no bottom-panel analogue) · frontend/src/features/studio/agent/handlers/bookEffects.ts:37,49 + glossaryEffects.ts:43-49 + knowledgeEffects.ts:24-44 + translationEffects.ts:16-17 (EVERY existing Lane-B handler refreshes solely via `queryClient.invalidateQueries({queryKey})` — a hand-rolled useState consumer is unreachable from all of them) · frontend/src/features/studio/agent/useStudioEffectReconciler.ts:52-63 (ctx construction — no panel-local-state hook exists) and :7-9 (the stale comment to delete) · frontend/src/features/studio/panels/useQualityCanon.ts:20 (`import { useQuery } from '@tanstack/react-query'` — the sibling quality panel already owns its data this way) · spec 37_issues_feed.md:553-562 (§7.1) and :326-327 (staleTime 60_000)

### Q-37-ALWAYS-MOUNTED-3-BODIES
CONFIRMED as M1's first work item, but the spec's framing is INSUFFICIENT — implement it in THREE parts, or the fix is a no-op. The SSE is not owned by the tab, so three always-mounted bodies alone do not save it.

**Part 1 — StudioBottomPanel.tsx: three always-mounted bodies.** Replace the single body div (lines 43-45, `t(`bottomStub.${tab}`)`) with three sibling bodies, all rendered on every render, each: `<div role="tabpanel" data-testid={`studio-bottom-body-${tb}`} className={cn('flex-1 overflow-y-auto p-4', tab === tb ? 'block' : 'hidden')}>`. Keep the `tab` useState. Bodies = `<JobsTabBody/>`, `<GenerationTabBody/>`, `<IssuesTabBody/>` (Issues stays a stub until Wave 7 per PO-1; Generation until its wave). ⚠ Do NOT write `className={cn('flex ...', tab !== tb && 'hidden')}` — `flex` and `hidden` are both `display` utilities and precedence is decided by Tailwind's CSS source order, not class order. Apply `block`/`flex` OR `hidden`, never both.

**Part 2 (the one the spec misses) — StudioFrame.tsx:160.** Today: `{chrome.bottomOpen && <StudioBottomPanel onClose={chrome.toggleBottom} />}`. This unmounts ALL THREE bodies whenever the user collapses the panel, so Part 1 buys nothing. Change to unconditional `<StudioBottomPanel open={chrome.bottomOpen} onClose={chrome.toggleBottom} />`, and collapse via CSS inside the panel: root `className={cn('flex-shrink-0 flex-col border-t bg-card', open ? 'flex h-[168px]' : 'hidden')}`. This is the file's own established precedent — ManuscriptUnitProvider is hoisted "above every chrome conditional, so a sidebar/bottom toggle never remounts it" (StudioFrame.tsx:133-137) and the palettes are "always mounted … visibility via `open`" (line 173).

**Part 3 — hoist ONE JobsStreamProvider; make it re-entrant.** The Jobs subscription lives in `JobsStreamProvider` (JobsStreamProvider.tsx:38) → `useJobsStream` (useJobsStream.ts:20), which opens one long-lived `fetch()` stream per mount and aborts it on unmount (useJobsStream.ts:111-116). `JobsListPanel.tsx:26` and `JobDetailPanel.tsx:46` ALREADY each mount their own; a third inside the Jobs tab = three concurrent `/v1/jobs/stream` connections per user. So: (a) mount exactly one `<JobsStreamProvider>` in StudioFrame directly inside `<ManuscriptUnitProvider>` (StudioFrame.tsx:137) so it sits above every chrome conditional; (b) `JobsTabBody` consumes `useJobLive`/`useJobsConnection` from context and mounts NO provider; (c) make JobsStreamProvider re-entrant so the dock panels inherit instead of opening a second stream — split it: `export function JobsStreamProvider({children}) { const existing = useContext(StoreCtx); if (existing) return <>{children}</>; return <JobsStreamRoot>{children}</JobsStreamRoot>; }` with the current body moved verbatim into `JobsStreamRoot`. (Two components keeps hook counts stable — do not early-return inside the existing body.) Standalone `/jobs` + `/jobs/:id` pages have no ancestor provider, so they keep working unchanged.

**Tests (rewrite, don't preserve).** `StudioBottomPanel.test.tsx:12` asserts `expect(panel.textContent).not.toContain('bottomStub.jobs')` after switching tabs — that assertion is FALSE BY DESIGN once bodies are always mounted (jsdom `textContent` includes `display:none` nodes). The builder MUST delete it, NOT "fix" the component to satisfy it. Replace with: (1) all three `studio-bottom-body-*` testids present in the DOM at all times; (2) exactly one lacks `hidden`; (3) after clicking Generation, the jobs body is STILL in the DOM and now carries `hidden`. Then add the two tests that actually pin the invariant: (4) a mount-counter body (increments a ref in `useEffect(…, [])`) mounted once across 3 tab switches; (5) **a StudioFrame test that toggles the bottom panel closed→open and asserts the jobs stream `fetch` was called exactly ONCE** (spy `global.fetch` / mock `jobsApi.streamUrl`). Test 5 is the regression gate for Part 2 — without it, a future `&&` creeps back in silently.

**Default I am picking (PO may veto):** the Jobs SSE stays connected for the whole studio session, including while the bottom panel is collapsed. It is one fetch stream, it is what `/jobs` already does, and disconnect-on-collapse would re-introduce the reconnect-backoff storm useJobsStream.ts:43-48 exists to survive. If the PO wants the stream to drop on collapse, that is a JobsStreamProvider prop (`enabled`), not a remount — never re-introduce the conditional mount.

*Evidence:* frontend/src/features/studio/components/StudioFrame.tsx:160 — `{chrome.bottomOpen && <StudioBottomPanel onClose={chrome.toggleBottom} />}` (the parent-level conditional unmount the spec misses; contradicts the same file's own D4 no-remount comment at :157-158 and the hoisted ManuscriptUnitProvider at :133-137). frontend/src/features/studio/components/StudioBottomPanel.tsx:43-45 — single body div interpolating t(`bottomStub.${tab}`). frontend/src/features/jobs/hooks/useJobsStream.ts:20,55,111-116 — one long-lived fetch() stream per mount, `controller?.abort()` in cleanup ⇒ any unmount kills it. frontend/src/features/jobs/context/JobsStreamProvider.tsx:38,91 — the provider (not the tab) owns the stream. frontend/src/features/studio/panels/JobsListPanel.tsx:26 + JobDetailPanel.tsx:46 — two providers already mounted in-dock ⇒ a third in the bottom panel = 3 concurrent /v1/jobs/stream connections. frontend/src/features/studio/components/__tests__/StudioBottomPanel.test.tsx:12 — `not.toContain('bottomStub.jobs')` is the assertion that must be deleted.

### Q-37-X1-DOCK7-HARD-PREREQ
SHIP THE RUN-CONFORMANCE BUTTON in M1 (spec 37 §8.4). X-1 has NOT landed today, but it is a Wave-0 hard gate that lands BEFORE M1, and the fix is ~15 lines. Do NOT ship the degraded no-Run-button variant, and do NOT defer.

X-1 (do it in Wave 0; if M1 starts and it is still unlanded, do it as M1's slice 0 — it is fix-now, not a defer):

FILE frontend/src/components/shared/AddModelCta.tsx — fix at the SHARED component, never at the ~8 call sites.
1. `import { useOptionalStudioHost } from '@/features/studio/host/StudioHostProvider';`
2. In `AddModelCta({ returnTo, capability, label, variant, className })` add `const studioHost = useOptionalStudioHost();`.
3. Hoist the inner markup once: `const inner = (<><Plus className={variant === 'link' ? 'h-3 w-3' : 'h-3.5 w-3.5'} />{text}</>)` and hoist the two existing className strings into `const cls = variant === 'link' ? '<the link classes at :47>' : '<the button classes at :61>'`.
4. Branch BEFORE the `<Link>`: if `studioHost` is non-null, return `<button type="button" className={cn(cls, className)} onClick={() => studioHost.openPanel('settings', { focus: true, params: { tab: 'providers' } })}>{inner}</button>`. Otherwise return the EXISTING `<Link to={to}>` unchanged (the `?return=` round-trip is the correct non-studio behavior and must be preserved verbatim).
   Seams already exist and are verified: StudioHostProvider.tsx:52 `openPanel(panelId, {focus?, title?, params?, component?})`; catalog.ts:120 registers panel id `settings`; SettingsPanel.tsx seeds+follows `params.tab`. `returnTo` is inert inside the studio (no navigation happens) — leave the prop alone.

TESTS frontend/src/components/shared/__tests__/AddModelCta.test.tsx — keep all 3 existing cases (they now assert the OUTSIDE-studio branch). Add two:
 - "inside the studio it does not render a link": render inside a StudioHostProvider (or vi.mock '@/features/studio/host/StudioHostProvider' so `useOptionalStudioHost` returns `{ openPanel: vi.fn(), ... }`), assert `screen.queryByRole('link')` is null and `getByRole('button')` exists.
 - "inside the studio it opens the settings panel on the providers tab": click the button, assert `openPanel` called with `('settings', expect.objectContaining({ params: { tab: 'providers' } }))`. This is a DOCK-7 effect test — assert the dock is NOT torn down (no navigation), not just that a handler fired.

THEN in M1: the `conformance_never_run` / `conformance_dirty` row keeps BOTH affordances — the deep-link to `plan-hub` (`openPanel('plan-hub', {params:{bookId, focusArcId}})`, spec 37:252) AND the Run-conformance button on the GENERIC propose→confirm spine (`POST /v1/composition/actions/propose` + `/confirm`, descriptor `composition.conformance_run`, spec 37:618) with a `ModelPicker` for the BYOK `model_ref`. Never the two invented per-action 404 paths (spec 37:620, D-3).

Default I am picking, so the PO can veto: X-1 is a prerequisite to BUILD, not a reason to CUT scope.

*Evidence:* frontend/src/components/shared/AddModelCta.tsx:33-68 (unconditional <Link>, no useOptionalStudioHost — X-1 unlanded) · frontend/src/components/model-picker/ModelPicker.tsx:388 (empty state renders AddModelCta) · grep useOptionalStudioHost: 6 call sites, none in AddModelCta.tsx; precedent frontend/src/features/glossary-translate/StepConfig.tsx:44 · frontend/src/features/studio/host/StudioHostProvider.tsx:52 (openPanel signature) + :143 (useOptionalStudioHost) · frontend/src/features/studio/panels/catalog.ts:120 (panel id 'settings') · frontend/src/features/studio/panels/SettingsPanel.tsx:31 (params.tab deep-link) · docs/specs/2026-07-01-writing-studio/30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md:334,345 (X-1 = Wave-0 gate, sized S) · docs/specs/2026-07-01-writing-studio/37_issues_feed.md:614-623

### Q-37-LANEB-HANDLER
BUILD IT as specced, with ONE correction to the regex (it over-matches READ tools) and one addition. This is a work item, not an open question — but the spec's literal regex ships a refetch-storm bug, so the builder needs the corrected version.

**1. New file `frontend/src/features/studio/agent/handlers/diagnosticsEffects.ts`** — mirror the exact shape of `knowledgeEffects.ts` (module-level `registered` flag, exported pattern const, exported `_resetDiagnosticsEffectHandlers()` test hook):

```ts
// Writes ONLY. Reads are excluded so a chatty agent read-loop doesn't thrash the query
// cache (same rule as KNOWLEDGE_WRITE_PATTERN, knowledgeEffects.ts:19-20). Critically,
// the Issues panel's OWN read tools (composition_diagnostics, composition_find_references)
// must never match — that would be a self-invalidating refetch storm.
export const DIAGNOSTICS_STALING_PATTERN =
  /^composition_(canon_rule_(create|update|delete)|conformance_run|outline_node_|arc_(create|update|delete|move|apply|assign_chapters|restore)|motif_(bind|unbind)|authoring_run_(accept_unit|revert_all))/;

export function diagnosticsEffect(ctx: EffectContext): void {
  ctx.queryClient.invalidateQueries({ queryKey: ['composition', 'diagnostics', ctx.bookId] });
  ctx.queryClient.invalidateQueries({ queryKey: ['composition', 'entity-references', ctx.bookId] });
}

let registered = false;
export function registerDiagnosticsEffectHandlers(): void {
  if (registered) return;
  registered = true;
  registerEffectHandler(DIAGNOSTICS_STALING_PATTERN, diagnosticsEffect);
}
export function _resetDiagnosticsEffectHandlers(): void { registered = false; }
```

WHY the regex changed from the spec's `/^composition_(canon_rule_|conformance_run|outline_node_|arc_|motif_(bind|unbind))/`:
- **`arc_` is a bare prefix** and matches five READ tools that exist today — `composition_arc_list`, `_get`, `_suggest`, `_template_drift`, `_import_analyze`. Every agent read of the arc roster would invalidate diagnostics → refetch → invalidate. Use the write-verb allowlist above instead. Allowlist (not negative-lookahead) is deliberate: a read tool added later then fails CLOSED (stale panel = status quo) rather than joining a refetch storm.
- **`authoring_run_(accept_unit|revert_all)` ADDED.** These write/revert manuscript prose, so they stale conformance diagnostics — and they match NO existing handler (`/^composition_.*(prose|draft)/` at bookEffects.ts:60 does not match `authoring_run_accept_unit`). Deleting the false comment is what surfaces this; a spurious invalidate costs one refetch, a missed one is exactly the bug X-4 exists to kill — asymmetric, so include them.
- `conformance_run` stays a literal (correctly does NOT match the `composition_conformance_status` read). Note for the builder: this fires at *dispatch*, not run *completion* — the panel's own polling covers completion. Do not add `conformance_status` to the pattern.

**2. `outline_node_` double-matching is CORRECT — do not "fix" it.** `bookEffects.ts:62` already registers `/^composition_(outline_node|scene_link)_/` → `outlineEffect`. `effectRegistry.ts:46-51` runs ALL matching handlers, and the reconciler dedupes per tool-CALL, not per handler. So an outline write correctly runs both (outline invalidation + diagnostics invalidation). Leave both registered.

**3. Register it** in `useStudioEffectReconciler.ts`: add the import beside line 21 and `registerDiagnosticsEffectHandlers();` inside the register-once `useEffect` at lines 34-39.

**4. Delete the false comment, lines 7-9** of `useStudioEffectReconciler.ts`. It asserts "authoring_run has no MCP tools at all, REST-only, no Studio consumer to go stale" — provably false. Replace with a one-liner naming the five registered handler families (book/glossary/knowledge/translation/diagnostics).

**5. Hard design constraint (spec §7.1, and it is load-bearing):** the Issues tab MUST own its data via React-Query (`useDiagnostics.ts`, keyed `['composition','diagnostics',bookId]`) — `invalidateQueries` cannot reach hand-rolled `useState` loader state. If the panel hand-rolls its fetch, this entire handler is a silent no-op and the wave ships the exact staleness it was built to kill.

**6. Test — `frontend/src/features/studio/agent/handlers/__tests__/diagnosticsEffects.test.ts`** (this dir currently holds only `resultEnvelope.test.ts`; no handler test exists to copy, so write it fresh). Use `clearEffectHandlers()` + `_resetDiagnosticsEffectHandlers()` in `beforeEach`, spy on `queryClient.invalidateQueries`, drive through `runEffectHandlers`. Assert:
  a. `composition_canon_rule_update` → BOTH keys invalidated;
  b. `composition_motif_bind`, `composition_conformance_run`, `composition_authoring_run_accept_unit` → invalidated;
  c. 🔴 the anti-thrash guard — `composition_arc_list`, `composition_arc_get`, `composition_diagnostics`, `composition_find_references`, `composition_conformance_status` each invalidate NOTHING. This assertion is the point of the corrected regex; without it the spec's literal pattern regresses silently.
  ⚠ Do not return a mock from `beforeEach` (Vitest treats a returned fn as teardown).

*Evidence:* frontend/src/features/studio/agent/handlers/bookEffects.ts:59-62 + glossaryEffects.ts:59 + knowledgeEffects.ts:51 + translationEffects.ts:28 = the COMPLETE registered handler set; `grep -rn "queryKey: \['composition'" frontend/src` returns zero hits for 'diagnostics'/'entity-references' → nothing invalidates the Issues feed (spec premise CONFIRMED). False comment: frontend/src/features/studio/agent/useStudioEffectReconciler.ts:7-9 claims "authoring_run has no MCP tools at all, REST-only", refuted by services/composition-service/app/mcp/server.py:1616 (`composition_authoring_run_create`) and :1723 (`_start`). Regex over-match: composition_arc_list/_get/_suggest/_template_drift/_import_analyze are READ tools in server.py that the spec's bare `arc_` prefix matches; the anti-thrash precedent is knowledgeEffects.ts:19-20 (KNOWLEDGE_WRITE_PATTERN's read exclusions). Multi-handler dispatch (why outline_node_ double-match is safe): effectRegistry.ts:46-51. Panel read tools that must never match: server.py:3867 (`composition_find_references`), :3935 (`composition_diagnostics`). Registration site: useStudioEffectReconciler.ts:34-39.

### Q-37-BE1D-REST-VS-BRIDGE
BUILD IT AS A REST ROUTE. Do NOT touch FE_BRIDGE_TOOL_ALLOWLIST. Concrete build instruction for BE-1d:

1. NEW FILE `services/composition-service/app/routers/diagnostics.py` — host BOTH BE-1 (`GET /books/{book_id}/diagnostics`) and BE-1d here; `router = APIRouter(prefix="/v1/composition")`, copying the imports/deps of `routers/conformance.py:1-63`.

2. Route signature (mirror `conformance.py:424-454` exactly):
```python
@router.get("/books/{book_id}/entity-references")
async def read_entity_references(
    book_id: UUID,
    entity_id: UUID = Query(...),
    sources: list[ReferenceSource] | None = Query(None),   # FastAPI enum-validates -> 422 on typo
    limit: int = Query(20, ge=1, le=100),
    user_id: UUID = Depends(get_current_user),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
```
- Import `ReferenceSource` + `REFERENCE_SOURCES` from `app.services.agent_native` (agent_native.py:43-56) — do NOT re-declare the 8-set (one name, one concept).
- E0 gate FIRST: `await authorize_book(grant, book_id, user_id, GrantLevel.VIEW)`; `except OwnershipError -> 404 "book not found"`, `except InsufficientGrant -> 403 "insufficient access"` (H13 uniform, no enumeration oracle).
- Body: `want = tuple(sources) if sources else REFERENCE_SOURCES`; `cap = max(1, min(limit, 100))`; loop `EntityReferencesRepo(get_pool()).find(src, book_id=..., entity_id=..., limit=cap)` and emit the SAME shape the MCP tool returns (mcp/server.py:3901-3931): `{book_id, entity_id, sources: {<src>: {count, refs, has_more}}, ...}`, per-source degrade to `{"error": "this source could not be read"}` — never 500 the whole route on one bad source.
- Do NOT catch `ValueError("unknown reference source")` into a zero-count (entity_references.py:80 raises ON PURPOSE) — the enum on the route makes it unreachable; a bad `sources` value must surface as 422, never as `(0, [])`.

3. `services/composition-service/app/main.py` — add `diagnostics` to the router import list (line ~39) and `app.include_router(diagnostics.router)` next to the conformance line (~244).

4. GATEWAY: zero work. `gateway-setup.ts:354` proxies any `/v1/composition*` path with no rewrite.

5. NAME: the route is `entity-references` and is BOOK-scoped — `/works/{pid}/references` is TAKEN by the research reference shelf (`routers/references.py`, flagged at entity_references.py:8-15).

6. TESTS (composition unit suite): (a) 403 without VIEW, 404 on foreign/missing book; (b) `?sources=bogus` -> 422 (NOT a 200 with zero counts); (c) omitted `sources` -> all 8 keys present; (d) one source raising -> that key carries `error` and the other 7 still answer; (e) response shape byte-matches `composition_find_references`.

Rejected: adding `composition_find_references` to FE_BRIDGE_TOOL_ALLOWLIST. Verified in code — the allowlist is exactly 5 spend-adjacent names (4 cost-gated PROPOSE + 1 POLL) and the file's own header states the bridge exists to mint a cost-gated confirm token without a chat agent in the loop. A free VIEW read has no propose->confirm to justify it, and widening the privileged bridge surface for a read buys nothing. Every sibling studio panel already reaches composition over REST.

*Evidence:* services/api-gateway-bff/src/tools/tools.controller.ts:24-30 (FE_BRIDGE_TOOL_ALLOWLIST = 5 spend-adjacent names: composition_conformance_run/motif_mine/motif_adopt/arc_import_analyze + composition_get_mine_job; header comment: bridge = FE-drives-a-Tier-W-PROPOSE) · services/composition-service/app/mcp/server.py:3867-3931 (composition_find_references = pure VIEW-gated read over EntityReferencesRepo, no spend) · services/composition-service/app/db/repositories/entity_references.py:60-82 (find() -> (exact_count, capped_refs); RAISES on unknown source) · services/composition-service/app/services/agent_native.py:43-56 (ReferenceSource Literal + REFERENCE_SOURCES 8-tuple) · services/composition-service/app/routers/conformance.py:63,424-454 (prefix /v1/composition; the book-scoped VIEW-gated 404/403 mirror pattern) · services/composition-service/app/main.py:39,244 (router registration site) · services/api-gateway-bff/src/gateway-setup.ts:354 (pathFilter startsWith('/v1/composition'), no rewrite -> new route auto-proxied)

### Q-37-LENS-EIGHT-ROWS
EIGHT rows. The code is unambiguous and the six-row cut is a bug — do not re-collapse. Concrete instruction for M2:

1. **Never hand-write the source list on the FE.** Add `frontend/src/features/studio/lens/referenceSources.ts` exporting `REFERENCE_SOURCES` as an 8-tuple in the exact order of `agent_native.py:53-56` (`outline_pov, outline_present, scene_pov, scene_present, structure_roster, motif_application, canon_rule, narrative_thread`) plus a `LABEL: Record<ReferenceSource, string>` map (`POV · chapters`, `Present · chapters`, `POV · scenes`, `Present · scenes`, `Arc roster`, `Motifs`, `Canon rules`, `Threads opened`). `EntityReferencesLens.tsx` renders `REFERENCE_SOURCES.map(...)` — one `<li data-testid={`lens-row-${src}`}>` per member, unconditionally, **before** the response is consulted. A row exists even when the key is absent from the payload; you cannot draw six because you cannot skip a `.map` member.

2. **Row state is a 3-way branch, never a number-with-default.** For each `src`: (a) `payload.sources[src]?.error` ⇒ render "could not be read" + a retry affordance (this is `server.py:3909-3913`'s `{"error": "this source could not be read"}` — a source that never renders a row can never render its own degrade, which is the §4.1.3 absent≠zero violation); (b) key present ⇒ render the exact `count` + `has_more` chevron; (c) key missing entirely ⇒ treat as (a) with "not returned". Forbidden: `count ?? 0`, `count || 0`, `Number(count)` — a lint-visible `?? 0` on a count is the exact defect. Because `Block.into` (agent_native.py) OMITS a degraded key by design, any `?? 0` converts an unknown into a confident "0 references", and the agent/author's next move on "0" is to delete the entity.

3. **BE-1d (the read-only REST mirror, unbuilt — write it, it is not a blocker):** `GET /internal/books/{book_id}/entities/{entity_id}/references?limit=` in composition-service returns `{sources: {<all 8 keys>}}` by iterating `REFERENCE_SOURCES` and reusing `EntityReferencesRepo.find` (entity_references.py:69-83) with the same per-source try/except → `{"error": ...}` envelope as `server.py:3903-3915`. Do NOT re-declare the list; import it. E0 VIEW gate on `book_id`, same as the tool.

4. **M2 DoD tests (both required to close the wave):**
   - FE (vitest/RTL): mock the route with a payload containing only 3 of the 8 keys, one of them `{error: "..."}` ⇒ assert `getAllByTestId(/^lens-row-/)` has length **8**, assert the errored row shows "could not be read", assert the 5 missing keys do **not** render "0".
   - BE (pytest): `set(response["sources"].keys()) == set(REFERENCE_SOURCES)` and, with one source patched to raise, the other 7 still carry counts while the failed one carries `error` (mirrors the tool's existing `test_the_reference_sources_are_a_CLOSED_SET_of_eight`, tests/unit/test_agent_native.py:106-114).

The pov/present × chapter/scene split is the repo's own physical model, not a spec flourish: there is no `scenes` table; `outline_node` holds both and `_NODE_KIND` (entity_references.py:50-53) maps `outline_*`→`kind='chapter'`, `scene_*`→`kind='scene'`. Four genuinely different WHERE clauses. Collapsing to six drops `outline_present` and `scene_pov` outright — a character present on 7 chapter nodes and 0 scene nodes would read "Present — 0".

Default I am setting (veto-able): the merged-row alternative is REJECTED for v1. It is strictly more code (sum both counts AND degrade if either errored) for strictly less information. If a future PO wants merged display, do it as a pure FE fold over the 8 rows the API already returns — never by shrinking the source list.

*Evidence:* services/composition-service/app/services/agent_native.py:43-56 (ReferenceSource Literal + REFERENCE_SOURCES 8-tuple, with the comment "EIGHT sources over the seven F-A4 shapes (the outline pov/present pair splits)") · services/composition-service/app/mcp/server.py:3903-3915 (`want = tuple(sources) if sources else REFERENCE_SOURCES`; per-source `except` ⇒ `out_sources[src] = {"error": "this source could not be read"}` — the degrade is PER SOURCE, so a source with no row cannot render it) · services/composition-service/app/db/repositories/entity_references.py:50-53 (`_NODE_KIND`: outline_*→chapter, scene_*→scene) and :69-83 (8-entry dispatch; unknown source RAISES rather than returning (0,[])) · services/composition-service/tests/unit/test_agent_native.py:106-114 (`assert len(REFERENCE_SOURCES) == 8` already guards the BE side; M2 adds the FE-side equivalent) · frontend/src/features/plan-hub/components/PlanDrawer.tsx:287 confirms the lens/route is genuinely unbuilt ("spec 28 AN-3, not built yet") — buildable work, not a blocker.

### Q-37-COSTGATE-GENERIC-SPINE
CONSTRAINT CONFIRMED, and it is already satisfiable with zero new code — the builder must REUSE the working sibling, not write a new client.

Builder instruction (Issues-feed "Run conformance" row, spec 37 §8.4):
1. Call `motifApi.arcConformanceRunPropose({ projectId, arcTemplateId: <arcId>, modelRef, modelSource: 'user_model' }, token)` — frontend/src/features/composition/motif/api.ts:245. It executes the MCP tool `composition_conformance_run` via `mcpExecute` (MCP-first mint) and returns `{confirm_token, descriptor:'composition.conformance_run', est_usd}`. Render that in the existing CostConfirmCard.
2. On human confirm call `motifApi.arcConformanceRunConfirm(confirm_token, token)` — api.ts:277. It POSTs `/v1/composition/actions/confirm?token=<ct>` (token in the QUERY, identity = Bearer JWT), gets `{job_id}` (202), and polls `compositionApi.getJob` to terminal. That is exactly the generic spine the spec demands (dispatch: actions.py:343 → _execute_conformance_run:714).
3. NEVER call `motifApi.conformanceRunEstimate` (api.ts:223) or `motifApi.conformanceRunConfirm` (api.ts:228). Grep confirms NO backend route `/actions/conformance_run/{estimate,confirm}` exists in composition-service — they 404. They are the broken chapter-scope sibling still wired at useConformanceTrace.ts:32,36; Wave 3 / plan 30 §3.3 owns deleting them. Do not import them, do not copy their shape.
4. HARD ADDITIONAL CONSTRAINT the spec does not state (found in code, and it is the same paid-spinner class): the run MUST be `scope:'arc'` with `arc_id` = a **structure_node id** (NOT an arc_template_id) plus a BYOK `model_ref`. `app/engine/motif_conformance_run.py:74-79` raises a terminal ValueError for `scope != 'arc'` — so a chapter-scope run through the CORRECT spine still mints a token, runs the usage-billing precheck (actions.py:721), enqueues, and the job fails. Chapter conformance is served by the free synchronous GET `/v1/composition/works/{pid}/conformance?scope=chapter&chapter_id=` (motifApi.conformance, api.ts:204) — if a chapter row ever needs a "refresh", refetch that GET; it is not a paid action.
5. Optional (not required): `GET /v1/composition/actions/preview?token=` (actions.py:183) can be used to render current-state before confirm, but no shipped composition caller uses it — the propose envelope's `estimate` is sufficient. Default: skip preview, mirror the arc sibling exactly.
6. Spec 37 §8.4's X-1 gate stands unchanged: the ModelPicker/AddModelCta prerequisite means if X-1 (DOCK-7 teardown) has not landed, ship M1 WITHOUT the Run button rather than shipping the dock-destroying landmine.

*Evidence:* services/composition-service/app/routers/actions.py:75 (_CONFORMANCE_RUN_DESCRIPTOR), :183 (GET /preview), :343 (confirm dispatch → _execute_conformance_run), :714-753 (claim→precheck→enqueue, poll=composition_get_mine_job) · services/composition-service/app/mcp/server.py:3105-3186 (composition_conformance_run mints the token; arc scope requires arc_id [structure_node] + model_ref) · services/composition-service/app/engine/motif_conformance_run.py:74-79 (worker raises terminal ValueError for scope != 'arc') · frontend/src/features/composition/motif/api.ts:245-297 (arcConformanceRunPropose/arcConformanceRunConfirm = the correct generic-spine pair) · frontend/src/features/composition/motif/api.ts:223-235 + hooks/useConformanceTrace.ts:32,36 (the two 404 per-action paths — `grep -rn "conformance_run/estimate" --include=*.py` returns ZERO backend routes)

### Q-37-BE1D-SOURCES-ENUM-NO-ZERO
CONSTRAINT ACCEPTED AS WRITTEN — it is buildable today; here is the exact instruction, no further thought required.

(1) ENUM-VALIDATE AT THE ROUTE BOUNDARY (new file `services/composition-service/app/routers/entity_references.py`, mounted on the existing composition router; path `GET /v1/composition/books/{book_id}/entity-references` — NOT `/works/{pid}/references`, which `routers/references.py` already owns for the research reference shelf):

    from app.services.agent_native import REFERENCE_SOURCES, ReferenceSource
    @router.get("/books/{book_id}/entity-references")
    async def read_entity_references(
        book_id: UUID,
        entity_id: UUID = Query(...),
        sources: list[ReferenceSource] | None = Query(None),   # <-- the enum. Literal ⇒ FastAPI/Pydantic 422s an unknown value BEFORE the repo is ever called.
        limit: int = Query(20, ge=1, le=100),
        user_id: UUID = Depends(get_current_user),
        grant: GrantClient = Depends(get_grant_client_dep),
    ) -> dict[str, Any]:

Do NOT declare `sources: list[str]` and hand-check it; do NOT normalize/drop unknown members. `ReferenceSource` (agent_native.py:43-52) IS the closed set — reuse it, one name one concept. `want = tuple(sources) if sources else REFERENCE_SOURCES` (mirror server.py:3903). E0 VIEW gate runs FIRST (`authorize_book` → OwnershipError⇒404, InsufficientGrant⇒403), before any arg-shaped work.

(2) THE PER-SOURCE DEGRADE CATCH MUST NOT SWALLOW `ValueError`. Copy the MCP loop's degrade shape (server.py:3908-3918) but narrow the catch — in the route:

    for src in want:
        try:
            count, refs = await repo.find(src, book_id=bid, entity_id=eid, limit=cap)
        except ValueError:
            raise                                  # closed-set violation = a BUG, not a degraded source. Let it 500 loudly.
        except Exception:                          # noqa: BLE001 — a real read failure degrades ONE source
            logger.warning("entity_references: source %s failed", src, exc_info=True)
            out[src] = {"error": "this source could not be read"}
            continue
        out[src] = {"count": count, "refs": refs, "has_more": count > len(refs)}

A failed source is OMITTED-as-error, NEVER `{"count": 0, "refs": []}`. Absent ≠ zero (agent_native.Block's own law). Counts stay EXACT; only `refs` is capped.

(3) FIX-NOW BUG IN THE EXISTING MCP CONSUMER (this is the live half of the concern — the repo already raises correctly, but its only caller launders the raise). `services/composition-service/app/mcp/server.py:3911` catches bare `Exception`, so an unknown source becomes `{"error": "this source could not be read"}` — a *transient-looking* failure. It is not a zero, so it doesn't break the letter of the rule, but it hides a closed-set typo as a retryable read error, and the M2 lens renders both identically. Add the same `except ValueError: raise` line above it. One line, same wave (Wave 7 / M2), covered by the tests below.

(4) TESTS (name them in the slice's DoD):
  - `tests/unit/test_entity_references_route.py::test_unknown_source_is_422` — `?sources=outline` (the classic typo the docstring names) ⇒ **422**, and assert the repo was NEVER called (spy/mock on `EntityReferencesRepo.find`). It must not be a 200 with a zero.
  - `::test_all_eight_sources_default` — omit `sources` ⇒ all 8 `REFERENCE_SOURCES` keys present in the response body (guards re-collapsing the pov/present split).
  - `::test_one_source_db_error_degrades_not_zeroes` — make one source raise `asyncpg.PostgresError` ⇒ that key is `{"error": ...}` and the other 7 answer; assert the degraded key has NO `count` field.
  - `tests/unit/test_mcp_server.py` — `composition_find_references` with a bad source propagates (does not return `{"error": "could not be read"}`).

DEFAULT I AM PICKING (veto-able): `sources` is repeatable-query-param style (`?sources=outline_pov&sources=canon_rule`), not a comma-joined string — it is what FastAPI gives you for free with a `list[Literal]` and it is what makes the 422 automatic. If the PO wants CSV, that is a hand-parser and it re-opens exactly this bug class.

NOT AN ESCALATION and NOT A DEFER: the route does not exist, which per CLAUDE.md's anti-laziness rule is unbuilt work, not a blocker. §5.2 already sealed REST-over-mcpBridge; nothing here contradicts §0 PO-1..4 of plan 30.

*Evidence:* services/composition-service/app/db/repositories/entity_references.py:60-83 — `find()` dict-dispatch; line 79-80 `if fn is None: raise ValueError(f"unknown reference source: {source}")`, docstring 63-68 states the "(0, []) would read as 'used nowhere' … the agent's next move on that answer is to delete something" rationale verbatim. · Closed set: services/composition-service/app/services/agent_native.py:43-56 (`ReferenceSource` Literal of 8 + `REFERENCE_SOURCES` tuple); pinned by services/composition-service/tests/unit/test_agent_native.py:109-110 (`len == 8`). · THE LIVE BUG: services/composition-service/app/mcp/server.py:3908-3913 — `try: count, refs = await repo.find(...)` / `except Exception:  # noqa: BLE001 — one source degrades` / `out_sources[src] = {"error": "this source could not be read"}` — the broad catch swallows the unknown-source ValueError into the degrade shape. · Route precedent (VIEW-gated, Query-validated, engine-composing): services/composition-service/app/routers/conformance.py:424-454. · Name-collision guard: services/composition-service/app/routers/references.py (research shelf) vs entity_references.py:8-15 (the deliberate rename note). · Spec §5.2, docs/specs/2026-07-01-writing-studio/37_issues_feed.md:484-501 (REST chosen; `/works/{pid}/references` is TAKEN).

### Q-37-LENS-PER-SOURCE-DEGRADE
CONFIRMED as a binding M2 constraint — the code degrades per-source exactly as §4.2 claims, so the lens MUST render 8 rows with per-source degrade. Build it this way (no further design input needed):

(1) FE source-of-order constant. In `frontend/src/features/studio/panels/EntityReferencesLens.tsx` (new file; sibling of the existing `frontend/src/features/studio/panels/EntityRefField.tsx`) export
`const REFERENCE_SOURCES = ['outline_pov','outline_present','scene_pov','scene_present','structure_roster','motif_application','canon_rule','narrative_thread'] as const;`
mirroring `services/composition-service/app/services/agent_native.py:53-56`.

(2) RENDER THE CONSTANT, NEVER THE RESPONSE KEYS. The row list is `REFERENCE_SOURCES.map(...)` — do NOT `Object.keys(payload.sources)`. Iterating the payload is the same bug class as the 6-row collapse: a source the server omitted would silently not draw, and its failure would be invisible.

(3) Three-way per-row branch, in this order:
  - `payload.sources[src] === undefined` (key absent) → render **"could not be read"** (treat a missing key as an error, NOT as zero).
  - `'error' in payload.sources[src]` → render **"could not be read"** (muted/warn styling, NO count glyph, row not expandable, not clickable). Grounded in `server.py:3909-3913`, which sets `{"error": "this source could not be read"}` per source and `continue`s so the other seven still answer.
  - else → exact `count` (`server.py:3915-3919`) + expand to `refs` with a "+N more" affordance when `has_more`.

(4) Loading = exactly 8 skeleton rows, keyed by `REFERENCE_SOURCES` (not a magic `[...Array(6)]`).

(5) All-zero copy — "Not referenced anywhere in the spec layer — all 8 sources answered, all 8 returned 0." — is gated on a predicate, not on emptiness: `REFERENCE_SOURCES.every(s => payload.sources[s] && !('error' in payload.sources[s]) && payload.sources[s].count === 0)`. If ANY source is absent or errored, that copy is forbidden; render the rows with their degrade markers instead.

(6) THE FOOTNOTE — correcting the spec, which says "render the tool's own `_meta.note`". DO NOT echo `_meta.note` verbatim. The actual string at `server.py:3926-3930` is agent-facing and names MCP tools: "Composition scope only. The prose side is glossary_list_chapter_links + glossary_get_entity_evidence; the graph side is kg_entity_edge_timeline." Putting that in an author's popover is a defect. Instead: BE-1d keeps returning `_meta.note` unchanged (the agent path needs it), and the FE renders an i18n string `refs.scopeNote` = "Composition scope only — prose mentions live in the glossary; graph edges in the KG." (generated across 18 locales via `python scripts/i18n_translate.py`, per §6 — never hand-written). Render it UNCONDITIONALLY in all three states (loaded / all-zero / degraded) — it is the guard against reading "23 scenes" as "23 prose mentions".

(7) BE-1d route (§5.2, already sealed as REST): `GET /v1/composition/books/{bid}/entity-references` must enum-validate `sources` as a FastAPI `Literal`/enum over the 8 members and let `EntityReferencesRepo.find`'s raise-on-unknown surface as 422. NEVER catch an unknown source into `(0, [])` — that renders as "used nowhere".

M2 Definition-of-Done tests (all must exist, all must be new):
  - `entityReferencesLens.test.tsx` T1 — payload with all 8 sources at count 0 → assert 8 rows render (assert on the 8 row testids) AND the all-zero copy shows.
  - T2 (degrade) — payload where `scene_pov: {error: "this source could not be read"}` and the other 7 have counts → assert the scene_pov row's text is "could not be read", assert the string "0" does NOT appear in that row, assert the other 7 counts render.
  - T3 (omitted key) — payload that omits `outline_present` entirely → its row still renders and reads "could not be read".
  - T4 (footnote) — assert `refs.scopeNote` copy is in the DOM in loaded, all-zero, AND degraded states; assert the raw substring "glossary_list_chapter_links" is NOT in the DOM.
  - T5 (loading) — 8 skeleton rows.
  - BE: a pytest that makes one source's repo call raise and asserts the route still returns the other 7 with counts plus `{"error": ...}` for the failed one (mirror the existing MCP-level shape).
  - Plus the M2 live browser smoke already required by the spec.

Note the one place I overrode the spec (item 6 — footnote copy comes from i18n, not from `_meta.note`); PO may veto, but rendering the raw note ships MCP tool names into the author UI.

*Evidence:* services/composition-service/app/mcp/server.py:3908-3919 — `for src in want: try: ... except Exception: out_sources[src] = {"error": "this source could not be read"}; continue` (per-source degrade, the rest still answer; success branch emits exact `count` + `refs` + `has_more`). services/composition-service/app/services/agent_native.py:53-56 — `REFERENCE_SOURCES` is exactly eight: outline_pov, outline_present, scene_pov, scene_present, structure_roster, motif_application, canon_rule, narrative_thread. services/composition-service/app/mcp/server.py:3925-3930 — `_meta.note` = "Composition scope only. The prose side is glossary_list_chapter_links + glossary_get_entity_evidence; the graph side is kg_entity_edge_timeline." (agent-facing tool names — NOT the human copy §4.2 quotes; hence the i18n `refs.scopeNote` override). docs/specs/2026-07-01-writing-studio/37_issues_feed.md:372, 389-396, 640 (the constraint + M2 DoD row); :484-508 (§5.2 REST sealed, `entity-references` name, enum-validate `sources`, "do not catch that into a zero").

### Q-37-PANEL-ENUM-57-CLAIM
CLAIM VERIFIED AT HEAD (b2a119460, feat/context-budget-law): py enum 57 == contract enum 57 == openable 57, zero drift. Set-diff py↔contract is empty both ways; panelCatalogContract.test.ts runs 4/4 green. The spec's §6 statement is TRUE as of the build HEAD, and the "adds NO panel" design is sound.

BUILDER INSTRUCTION (do this, nothing more):

1. DO NOT hardcode 57 anywhere in code, test, or evidence string. The invariant is EQUALITY, not the literal. Both existing guards are already literal-free — do not "improve" them by adding a count assertion.

2. Restate DoD-5 in docs/specs/2026-07-01-writing-studio/37_issues_feed.md. Two edits, both mechanical:
   - Line 509: replace "Current state, verified: **py enum 57 == contract enum 57 == openable 57, zero drift.**" with: "Verified at HEAD b2a119460: **py enum == contract enum == openable, zero drift (N=57 at time of writing — N is NOT load-bearing; concurrent tracks may move it and that is correct, not drift)."
   - Line 666: replace "`panelCatalogContract.test.ts` still reports **57 == 57 == 57**" with "`panelCatalogContract.test.ts` is GREEN (it asserts sorted-set equality; the count is whatever the catalog says)."

3. DoD-5's evidence gate becomes exactly these three commands, with pasted output:
   a. `cd frontend && npx vitest run src/features/studio/panels/__tests__/panelCatalogContract.test.ts`  -> must be 4 passed.
   b. `cd services/chat-service && python -m pytest tests/test_frontend_tools_contract.py -q`  -> must be green (this is the py->contract leg; the FE test alone does NOT cover it).
   c. SCOPED contract diff — NOT a bare `git diff`. Use `git diff --exit-code <wave-base-sha>..HEAD -- contracts/frontend-tools.contract.json` where <wave-base-sha> is the commit the wave branched from. Rationale: a bare/unscoped diff against a stale spec-time snapshot will false-red if a concurrent track (Book-Package, Track C) legitimately lands a panel and regenerates the contract. The assertion this wave owes is "THIS WAVE did not touch the contract file", not "the file never changed since the spec was written."

4. Keep the spec's 🔴 rule intact and unweakened: DO NOT add "issues" to the frontend_tools.py panel_id enum. The bottom-panel Issues tab is not a dockview panel; a pseudo-id with no catalog row reds panelCatalogContract.test.ts immediately, and correctly (ui_open_studio_panel resolves through dockview, which cannot mount it). This is the guard doing its job, not an obstacle to route around.

5. If the wave-scoped diff in 3c is non-empty, that is a REAL failure — it means the wave added a panel it was not supposed to add. Stop and fix the wave, do not regenerate the contract to make it green.

DEFAULT THE PO CAN VETO: I am treating the count (57) as incidental and the equality as the invariant. If the PO actually wants a pinned panel count as a change-control tripwire (i.e. any new panel from ANY track must be consciously acknowledged), that is a different feature and belongs in its own slice — not smuggled into spec 37's DoD.

*Evidence:* frontend/src/features/studio/panels/__tests__/panelCatalogContract.test.ts:32-35 — asserts sorted(contract panel_id enum) === sorted(OPENABLE_STUDIO_PANELS.map(p=>p.id)); no literal count. Passes 4/4 at HEAD.
services/chat-service/app/services/frontend_tools.py:402 — panel_id enum, 57 ids, 0 dupes.
contracts/frontend-tools.contract.json → ui_open_studio_panel.args.panel_id.enum — 57 ids; set-diff vs py enum empty both directions (py-only: {}, contract-only: {}).
frontend/src/features/studio/panels/catalog.ts:279 — `export const OPENABLE_STUDIO_PANELS = STUDIO_PANELS.filter((p) => !p.hiddenFromPalette);` (15 hiddenFromPalette flags in catalog).
services/chat-service/tests/test_frontend_tools_contract.py:130-147 — test_contract_json_matches_the_live_schemas: the py→contract leg, asserts on-disk JSON == live schemas, regen via WRITE_FRONTEND_CONTRACT=1.
git log -1: b2a119460 (branch feat/context-budget-law). Concurrent panel landing a800f0b94 (book-package 22-C2 scene-browser) already moved the catalog and kept all three legs equal — the lock works.
docs/specs/2026-07-01-writing-studio/37_issues_feed.md:509 and :666 — the two lines carrying the stale `57` literal that must be de-hardcoded.

### Q-37-PAID-ACTION-IN-FLIGHT
UPHOLD the constraint, REPLACE the mechanism. The "no optimistic mutation of a diagnostics row, ever — it is a derived read" half of §8.4 STANDS verbatim. The "the finished job lands via the Lane-B handler (§7.1)" half is FALSE against the code and must be rewritten before M1 is built, or the builder ships a spinner that never resolves (the exact paid-action defect the PO named as a CRITICAL blocker).

WHY IT IS FALSE: `useStudioEffectReconciler.ts:38-63` only runs handlers for tool-call records inside `useChatStream().messages`. The human's Run-conformance click is `mcpExecute(propose)` -> `POST /v1/composition/actions/confirm` -> 202 `{job_id, poll:"composition_get_mine_job"}` (`services/composition-service/app/routers/actions.py:714-745`). None of that is a chat tool_call, so Lane-B can never fire for it. Worse, on the AGENT path `composition_conformance_run` is a PROPOSE (mints a token, writes nothing) — §7.1's regex would invalidate the feed BEFORE any work happened and still miss the completion.

BUILDER INSTRUCTION (M1):

1. `frontend/src/features/studio/components/bottom/IssuesTab.tsx` — in-flight state is EPHEMERAL COMPONENT STATE, never spliced into the React-Query diagnostics data: `const [runs, setRuns] = useState<Map<string, {jobId: string; error?: string}>>()` keyed by the row's stable key. Render spinner + `jobId` + disabled button by looking the row key up in `runs`. The diagnostics query object is read-only; never `setQueryData` on it.

2. COMPLETION = POLL, NOT LANE-B. New `frontend/src/features/studio/hooks/useConformanceRun.ts`: after `POST /actions/confirm` returns `job_id`, drive a React-Query query `['composition','job',jobId]` calling the SHIPPED `compositionApi.getJob(jobId, token)` (`frontend/src/features/composition/api.ts:420` -> `GET /v1/composition/jobs/{job_id}`, `services/composition-service/app/routers/engine.py:1415`, VIEW-gated on the job's project->book) with `enabled: !!jobId` and `refetchInterval: (q) => ['pending','running'].includes(q.state.data?.status) ? 2000 : false`. Mirror the shipped budget (`JOB_POLL_INTERVAL_MS=2000`, `JOB_POLL_MAX=300` ~= 10 min, `composition/api.ts:47-51`). Do NOT hand-roll a `while` loop in the component (leaks past unmount); React-Query's refetchInterval stops on unmount. Precedent to copy: `frontend/src/features/composition/motif/api.ts:274-296` (`arcConformanceRunConfirm`) already polls getJob for THIS EXACT descriptor.

3. TERMINAL HANDLING — three branches, all mandatory:
   - `completed` -> `queryClient.invalidateQueries({queryKey:['composition','diagnostics',bookId]})`, delete the `runs` entry, toast success. The row DISAPPEARS because the source re-ranks. That is correct and is the whole point of the derived-read rule.
   - `failed` -> DO NOT clear silently and DO NOT let the row revert to its un-run state. The user PAID. Pin the row's action area to an inline error (`job.result.error`) + Retry until the user dismisses it. A silent revert here is the repo's `silent-success-is-a-bug` class on a spend path.
   - poll budget exhausted while still `running` -> keep "running" + the job id + a link `openPanel('job-detail', {params:{service:'composition', jobId}})`. NEVER claim done.

4. `frontend/src/features/studio/agent/handlers/diagnosticsEffects.ts` — §7.1's `DIAGNOSTICS_STALING` regex must DROP `conformance_run` (it is a propose; matching it is a false refresh that fires before any work). Ship it as `/^composition_(canon_rule_|outline_node_|arc_|motif_(bind|unbind))/` with a comment naming why. Then ADD a SECOND, separate handler for the agent-driven completion — the only place a completion ever surfaces as a chat tool_call: `registerEffectHandler('composition_get_mine_job', (ctx) => { if ((ctx.result as any)?.status === 'completed') ctx.queryClient.invalidateQueries({queryKey:['composition','diagnostics',ctx.bookId]}); })` (tool verified at `services/composition-service/app/mcp/server.py:3193`).

5. RELOAD DEFAULT (note it so the PO can veto): a full page reload loses `jobId` and the spinner. ACCEPT that in M1 — the job still runs and the row re-ranks away on the next fetch. Do NOT persist jobId to localStorage (it is per-book server state, not a per-device UI preference). Rehydrating the in-flight chip from the jobs list is an M3 follow-up (it needs BE-1b/BE-1c's `book_id` stamp), not M1 work.

6. SPEC EDIT (do it in the same wave): rewrite §8.4's last bullet and §7.1's regex in `docs/specs/2026-07-01-writing-studio/37_issues_feed.md` to match the above. Leaving the false Lane-B sentence on disk is how the next agent rebuilds the bug.

TESTS (DoD): (a) vitest — confirm returns a job_id, the row renders spinner+jobId+disabled button, and `queryClient.getQueryData(['composition','diagnostics',bookId])` is BYTE-IDENTICAL to the pre-click value (the no-optimistic-mutation guard, asserted, not assumed); (b) vitest — poll returns `completed` -> `invalidateQueries` was called with the diagnostics key; (c) vitest — poll returns `failed` -> the row still renders and shows the error string (the paid-for-nothing guard); (d) vitest — `diagnosticsEffects` does NOT invalidate on `composition_conformance_run` but DOES on `composition_get_mine_job` with `status:'completed'`.

PREREQUISITE UNCHANGED: X-1 (DOCK-7 teardown) is still a hard gate on the Run button per §8.4; if X-1 has not landed, ship M1 with no Run button and none of the above in-flight machinery is reachable.

*Evidence:* frontend/src/features/studio/agent/useStudioEffectReconciler.ts:38-63 (Lane-B fires ONLY on chat-stream tool_calls with ok===true — a REST /actions/confirm 202 is not one) · services/composition-service/app/routers/actions.py:714-745 (_execute_conformance_run returns {"outcome":"action_accepted","job_id":…,"poll":"composition_get_mine_job"}) · services/composition-service/app/routers/engine.py:1415 (GET /v1/composition/jobs/{job_id}, VIEW-gated) · frontend/src/features/composition/api.ts:420 + :47-72 (getJob + _pollJob budget 2000ms x 300) · frontend/src/features/composition/motif/api.ts:274-296 (shipped propose->confirm->poll precedent for descriptor composition.conformance_run) · services/composition-service/app/mcp/server.py:3193 (composition_get_mine_job) · docs/specs/2026-07-01-writing-studio/37_issues_feed.md:628-630 (the false sentence) and :542-556 (the regex to fix)

### Q-37-M3-JOBS-BOOKID-BLOCKER
NOT a blocker — it is unbuilt work, and both halves are XS. BUILD BOTH (they land in M3's first slice; M1/M2 unaffected). Confirmed against code: `GET /v1/jobs` has no `book_id` param (jobs-service/app/routers/jobs.py:42-51), `store._build_filters` has no book_id clause (projection/store.py:243-286), and composition's `_job_params` (generation_jobs.py:127-145) omits it. But the data is already at hand — no schema change, no new plumbing.

**BE-1b — stamp `book_id` at the composition producer (XS, ~2 lines + 1 test).**
File: `services/composition-service/app/db/repositories/generation_jobs.py`.
At the create emit (line 180-184) the row has already been INSERTed and `job = _row_to_job(row)` is in hand; `GenerationJob.book_id` is a NON-NULL `UUID` (db/models.py:365 — it is derived in-SQL from `composition_work` by the INSERT…SELECT at generation_jobs.py:160-168, so it can never be NULL). So change ONLY the emit call:
  `params=_job_params` → `params={**_job_params, "book_id": str(job.book_id)}`
Do NOT touch `_job_params`'s construction (it is built pre-INSERT, before book_id is resolved). Do NOT add book_id to the later status-transition emits — they pass `params=None`, and the projection's jsonb `||` merge (store.py:61) keeps the create-time keys forever, which is exactly why this is additive and safe.
Test: `services/composition-service/tests/` — extend the existing emit-spy test for `create` (the one that asserts `params["retryable"]`) with `assert params["book_id"] == str(work.book_id)`.

**BE-1c — `book_id` filter on the jobs read side (XS, ~8 lines + 1 test + 1 index).**
1. `services/jobs-service/app/projection/store.py`: add `book_id: Optional[str] = None` kwarg to `_build_filters`, `list_jobs`, and `list_jobs_paged`; in `_build_filters` append:
   `args.append(book_id); where.append(f"j.params->>'book_id' = ${len(args)}")`
   (text compare — `params` is jsonb, the producer stamps a string; no `::uuid` cast, which would blow up on a legacy row with a junk value).
2. `services/jobs-service/app/routers/jobs.py:42-51`: add `book_id: Optional[str] = Query(default=None, description="filter to one book (matches params->>'book_id')")`, validate it parses as a UUID (`uuid.UUID(book_id)` → `HTTPException(400)` on failure) and pass it to BOTH store calls. Owner scoping is unchanged — `j.owner_user_id = $1` stays the first predicate, so this is a narrowing filter, never an auth key.
3. `services/jobs-service/app/migrate.py` (idempotent DDL, alongside idx_job_projection_owner_updated at line 64): add
   `CREATE INDEX IF NOT EXISTS idx_job_projection_owner_book ON job_projection (owner_user_id, ((params->>'book_id')), job_updated_at DESC);`
4. Parity: `services/jobs-service/app/mcp/server.py` — add the same optional `book_id` arg to the `jobs_list` tool and pass it through, and FIX the now-false docstring at line 12 ("a job is owned by exactly one user (owner_user_id) with no book_id") → "…with an optional params.book_id scope stamp (filter only — never an auth key)".
Tests: `services/jobs-service/tests/` — one store test seeding two projected jobs with different `params.book_id` + one with none, asserting the filter returns exactly the matching one in both keyset and offset modes.

**Feed semantics the builder should assume (my default; PO may veto):** the M3 book-scoped Jobs feed shows only jobs whose producer stamps `book_id`. As of this build that is composition only — knowledge's `_job_params` (extraction_jobs.py:415) and translation's emits stamp none. That is FINE and intended: the Studio Jobs feed is about *this book's writing work*. Do NOT widen the stamp to knowledge/translation/lore-enrichment in this slice; if the feed later needs them, it is the same 1-line change per producer against the same generic filter. Unstamped rows are simply invisible under `?book_id=` (never mislabelled), so nothing regresses.

*Evidence:* services/jobs-service/app/routers/jobs.py:42-51 (no book_id param) · services/jobs-service/app/projection/store.py:243-286 (_build_filters has no book_id clause) + store.py:61 (`params = COALESCE(job_projection.params,'{}') || COALESCE(EXCLUDED.params,'{}')` — the additive merge that makes a create-time stamp durable) · services/composition-service/app/db/repositories/generation_jobs.py:127-145 (_job_params omits book_id) and :175-184 (emit site — `job` already carries book_id) · services/composition-service/app/db/models.py:365 (`book_id: UUID` — non-null, "tenancy scope key") · services/jobs-service/app/mcp/server.py:12 (stale "with no book_id" comment) · services/jobs-service/app/migrate.py:64-75 (idempotent index DDL home)

### Q-37-LANEB-REGEX-COVERAGE
TWO findings, both settled from code.

(1) ctx IS fine — no change needed. `EffectContext` already exposes `bookId: string` (effectRegistry.ts:12) and `queryClient: QueryClient` (:14). The §7.1 snippet's assumption holds verbatim; do NOT widen EffectContext.

(2) The §7.1 regex is UNDER-inclusive (it misses 4 whole writer families, not just `book_chapter_*`) and simultaneously OVER-inclusive on `arc_` (it matches the READ tools `composition_arc_get|arc_list|arc_suggest|arc_template_drift|arc_import_analyze`). REPLACE it.

BUILDER INSTRUCTION — `frontend/src/features/studio/agent/handlers/diagnosticsEffects.ts` (new file, M1):

```ts
// Derived from the EMITTED tool names, not asserted. Sources:
//   book-service   mcp_server.go / mcp_actions.go  (addTool "book_chapter_*", "book_index_chapter")
//   composition    mcp/server.py                   (composition_*)
// Each branch below stales at least one of the 8 SEVERITY kinds (agent_native.py:60-72)
// or one of the 8 REFERENCE_SOURCES (agent_native.py:53).
const DIAGNOSTICS_STALING =
  /^(book_(chapter_|index_chapter)|composition_(canon_rule_|conformance_run|outline_node_|scene_link_|write_prose|publish|generate|arc_(create|update|delete|move|apply|assign_chapters|restore)|motif_(bind|unbind|adopt|archive|mine|link_create|link_delete)|authoring_run_(start|resume|close|gate|accept_unit|reject_unit|revert_all)))/;

export function diagnosticsEffect(ctx: EffectContext): void {
  ctx.queryClient.invalidateQueries({ queryKey: ['composition', 'diagnostics', ctx.bookId] });
  ctx.queryClient.invalidateQueries({ queryKey: ['composition', 'entity-references', ctx.bookId] });
}
let registered = false;
export function registerDiagnosticsEffectHandlers(): void {
  if (registered) return; registered = true;
  registerEffectHandler(DIAGNOSTICS_STALING, diagnosticsEffect);
}
```
Call `registerDiagnosticsEffectHandlers()` alongside the existing `registerDefaultEffectHandlers()` in `useStudioEffectReconciler.ts`, and delete the now-false comment at its lines 7-9 (X-4 names it).

WHY EACH ADDED BRANCH (this is the derivation the spec owed):
- `book_chapter_*` + `book_index_chapter` — `unplanned_chapter` is a set-difference over the BOOK chapter spine (services/composition-service/app/services/coverage.py, `compute_coverage`), and `prose_deleted_spec_node` is its inverse (`compute_prose_deleted`). Both change on chapter create/bulk_create/delete/purge/restore_revision; `index_stale` changes on save_draft/publish/index_chapter. A `^composition_`-only regex can NEVER see these — the exact miss the question flags.
- `composition_write_prose|publish|generate` + `authoring_run_*` — `DIRTY_REASONS = ("never_run","prose_drift","spec_drift","index_stale")` (arc_conformance_orchestrate.py:304): prose writes dirty every arc. These same paths are the ONLY writers of `narrative_thread` (there is no `composition_thread_*` MCP tool — NarrativeThreadRepo's writers live in engine/narrative_thread.py, routers/actions.py, authoring_run_service.py), so `open_thread_debt` + the `narrative_thread` lens source stale here or nowhere. They also produce `canon_contradiction` (the critic lane).
- `composition_scene_link_*` — scenes ARE `outline_node` rows (entity_references.py:19-21, `_NODE_KIND`), and scene links move the chapter↔spec linkage that coverage/prose-deleted read.
- motif `adopt|archive|mine|link_create|link_delete` — `motif_application` (a lens source, entity_references.py:144) is FK-SET-NULLed by archive (motif_repo.py:444) and written by adopt/mine, not only by bind/unbind.
- `arc_` narrowed to the 7 write verbs — the old open-ended `arc_` fired a diagnostics + entity-references refetch on every `composition_arc_get`/`arc_list` (i.e. on every Arc Inspector open). Harmless but wasteful; the closed verb list kills it.

TEST (M1 DoD, `frontend/src/features/studio/agent/handlers/__tests__/diagnosticsEffects.test.ts`): table-driven — assert the regex MATCHES all of `book_chapter_create, book_chapter_bulk_create, book_chapter_delete, book_chapter_purge, book_chapter_save_draft, book_chapter_publish, book_chapter_unpublish, book_chapter_update_meta, book_chapter_restore_revision, book_index_chapter, composition_canon_rule_create/update/delete, composition_conformance_run, composition_outline_node_create/update/delete/move/restore, composition_scene_link_create/delete, composition_write_prose, composition_publish, composition_generate, composition_arc_create/update/delete/move/apply/assign_chapters/restore, composition_motif_bind/unbind/adopt/archive/mine/link_create/link_delete, composition_authoring_run_accept_unit/close/start/revert_all` and does NOT match the reads `composition_diagnostics, composition_get_prose, composition_arc_get, composition_arc_list, composition_find_references, book_get_chapter, book_list_chapters`. Plus one behavioral test: a matching tool invalidates BOTH query keys with ctx.bookId.

CONSTRAINT (already in §7.1, restate in the slice): the Issues tab and the lens must hold their data in React-Query, or these invalidations reach nothing (`invalidatequeries-cannot-reach-hand-rolled-state`).

*Evidence:* frontend/src/features/studio/agent/effectRegistry.ts:9-24 (EffectContext already has `bookId` :12 and `queryClient` :14 — ctx assumption CONFIRMED); frontend/src/features/studio/agent/handlers/bookEffects.ts:59-62 (existing `^composition_...` patterns — all composition-prefixed, zero `book_chapter_*` diagnostics coverage); services/book-service/internal/api/mcp_server.go:148 + mcp_actions.go:105 (`book_chapter_create` / `book_chapter_delete` are real emitted MCP tool names; full addTool list also has bulk_create/purge/save_draft/publish/unpublish/update_meta/restore_revision/book_index_chapter); services/composition-service/app/services/coverage.py (unplanned_chapter = set-difference over the BOOK chapter spine ⇒ staled by book_chapter_*); services/composition-service/app/mcp/server.py:4085-4130 (compute_prose_deleted + compute_coverage sources); services/composition-service/app/engine/arc_conformance_orchestrate.py:304 (`DIRTY_REASONS = ("never_run","prose_drift","spec_drift","index_stale")` ⇒ prose writes dirty conformance); services/composition-service/app/mcp/server.py:4064 (open_thread_debt reads NarrativeThreadRepo; no `composition_thread_*` tool exists — engine-written only); services/composition-service/app/services/agent_native.py:53 + :60-72 (the 8 REFERENCE_SOURCES and the 8 SEVERITY kinds); services/composition-service/app/db/repositories/entity_references.py:19-21,144-165 (scenes are outline_node rows; motif_application is a lens source) + db/repositories/motif_repo.py:444 (archive SET-NULLs motif_application).

### Q-37-HONEST-STUB-COPY
CONFIRMED — this is a work item, and the answer is YES: M1 rewrites the `bottomStub.*` copy even though M3 (Jobs/Generation wiring) is deferred. It is ~6 lines of copy + one i18n regen; deferring it would be deferring a one-line fix (CLAUDE.md: fixing is cheaper than carrying the row). Do exactly this, in M1:

(1) `frontend/src/i18n/locales/en/studio.json` (block at :721) — replace the `bottomStub` object with TWO keys (drop `issues`, whose body becomes the real `IssuesTab` in M1; its empty/warnings copy lives under the new `issues.*` keys):
  "bottomStub": {
    "jobs": "Book-scoped job feed — pending `book_id` on the jobs projection (BE-1b).",
    "generation": "Book-scoped generation feed — pending `book_id` on the jobs projection (BE-1b)."
  }
(Default: keep the literal ticket id `BE-1b` in the visible string, per spec §4.3 — it is what makes the stub greppable and un-rottable. PO may veto the id and keep only the capability clause; nothing else changes if so.)

(2) 18 locales — do NOT hand-edit. Run `python scripts/i18n_translate.py --ns studio --force` (spec §6 row 3-4: the `bottomStub.*` keys change meaning and `bottom.*`/`issues.*`/`refs.*` keys are added → generated, never hand-written). Commit the regenerated locale JSON with the wave.

(3) `frontend/src/features/studio/components/StudioBottomPanel.tsx:44` — the single templated stub body disappears in the §4.0 always-mounted refactor. The honest copy is rendered by the two stub tabs: `components/bottom/JobsTab.tsx` and `components/bottom/GenerationTab.tsx` each render `t('bottomStub.jobs' | 'bottomStub.generation')` with the en string above as `defaultValue` (i.e. the defaultValue must match the en locale — never leave 'Feed appears here once wired.' anywhere). `IssuesTab.tsx` renders the real feed and reads NO `bottomStub.*` key.

(4) Test guards (M1, in `__tests__/StudioBottomPanel.test.tsx`, replacing :9/:11/:12 which today assert the lie and which the always-mounted refactor reds anyway — hidden bodies still contribute to `textContent`, so assert VISIBILITY): 
  a. every `BottomTab` id has a `bottom.<id>` label key AND a mounted body component (`expect(screen.getByTestId('bottom-body-jobs')).not.toBeVisible()` after switching away, etc.);
  b. an anti-rot assertion over the en locale: `import en from '@/i18n/locales/en/studio.json'` → `expect(Object.keys(en.bottomStub).sort()).toEqual(['generation','jobs'])` and `expect(en.bottomStub.jobs + en.bottomStub.generation).not.toMatch(/once wired|soon/i)`. This is what stops the copy silently regressing to "soon" while M3 sits deferred.

(5) When M3 lands, DELETE both `bottomStub.*` keys + guard (b) in the same commit as BE-1b/BE-1c. For the record, BE-1b is NOT plumbing: `book_id` is already derived in-SQL at `generation_jobs.py:164` and `job = _row_to_job(row)` runs before the emit, so BE-1b == `params={**_job_params, "book_id": str(job.book_id)}` at `generation_jobs.py:180-184` and at the twin insert site `:543-558`. BE-1c == one `book_id` Query param on `jobs.py:42-51` + a `params->>'book_id'` predicate.

*Evidence:* frontend/src/features/studio/components/StudioBottomPanel.tsx:44 (`t(`bottomStub.${tab}`, { defaultValue: 'Feed appears here once wired.' })`) · frontend/src/i18n/locales/en/studio.json:721-725 (all three stubs say "…once wired", same block at :721 in all 18 locales) · frontend/src/features/studio/components/__tests__/StudioBottomPanel.test.tsx:9,11,12 (currently GUARDS the lie) · blocker is real: services/jobs-service/app/routers/jobs.py:42-51 has no `book_id` query param, and services/composition-service/app/db/repositories/generation_jobs.py:127-143 `_job_params` omits `book_id` — while :164 already derives `w.book_id` in-SQL and :180-184 emits after `_row_to_job(row)`, so BE-1b is one line. Sealed by spec 37 §9: "M3 is independently deferrable — and if it is deferred, the stub copy still changes (M1 ships the honest string)."

### Q-37-LENS-A11Y-AFFORDANCE
CONFIRMED as a real defect, and the fix is NOT a separate `⋯` glyph on the plan-hub chip — MAKE THE CAST CHIP ITSELF THE BUTTON, mirroring CanonBadge in the same file. `⋯` appears in exactly ONE place (EntityRefField single-mode), where a `<select>` cannot host the trigger. Default I am picking (PO may veto): no `⋯` on the Plan Hub cast chip — it is `max-w-[5rem] truncate` inside a dense ReactFlow node; a second glyph doubles chip width and steals truncation budget from the entity name. Right-click stays as a power-user shortcut; the button is the accessible path.

SLICE A — plan-hub (additive + degrade-safe ⇒ NO Book-Package handoff needed, only a heads-up; when the new prop is absent the chip renders byte-identical to today):
1. `frontend/src/features/plan-hub/components/nodePresentation.ts:45` — next to `onOpenRef`, add to `PlanNodeData`: `onOpenEntityLens?: (entityId: string, nodeId: string) => void;`
2. `PlanCanvas.tsx:148, 201, 223` — accept the prop, spread it onto every node's `data`, add it to the useMemo dep array. Mirror `onOpenRef` at all three sites exactly.
3. Forward it in `ChapterNode.tsx:13/63`, `SceneNode.tsx:14/41`, `ArcRollupNode.tsx:15/69` → `<NodeBadges onOpenEntityLens={…}>`.
4. `NodeBadges.tsx` — extract `case 'cast'` into a `CastBadge` component built like `CanonBadge` (lines 26-57). If `onOpenEntityLens` is wired AND `r.state !== 'unknown'` (unknown = not-paged-in, nothing to look up): render `<button type="button">` KEEPING the existing `data-testid={`plan-badge-cast-${nodeId}-${entityId}`}` and `data-cast-state` attrs (tests depend on them), plus `aria-label={`Find references to ${label}`}`, `onClick={e => { e.stopPropagation(); onOpenEntityLens(b.entityId, nodeId); }}`, `onContextMenu={e => { e.preventDefault(); e.stopPropagation(); onOpenEntityLens(b.entityId, nodeId); }}`, `className={cn(cls,'pointer-events-auto')}`. `state === 'missing'` GETS the button too (a broken ref is exactly what you want to find references for). Not wired ⇒ today's exact `<span>`. Enter/Space come free with `<button>` — write no key handler.
5. `PlanHubPanel.tsx:228 and :288` — pass `onOpenEntityLens={openEntityLens}` right beside the existing `onOpenRef={openRef}`.

SLICE B — studio `EntityRefField.tsx` (studio-owned, no coordination):
6. Add `onOpenLens?: (entityId: string) => void` to `BaseProps` (lines 12-17). In `MultiRef` (line 55+) the chip renders `{labelFor(id)}` as bare text beside the × button: when `onOpenLens` is wired, wrap that label in `<button type="button" data-testid={`${testid}-lens-${id}`} aria-label={t('panels.scene-inspector.ref.find', { name, defaultValue: `Find references to ${name}` })} onClick={() => onOpenLens(id)}>`, and put `onContextMenu` (preventDefault → onOpenLens) on the wrapping `<span>`. Not wired ⇒ plain text, never a dead button.
7. SINGLE mode has no chip — the value lives in the `<select>` (lines 36-51). Render, immediately AFTER the select, `<button type="button" data-testid={`${testid}-lens`} aria-label={same string}>⋯</button>`, mounted only when `props.value && onOpenLens`. This is the one legitimate `⋯`.
8. Wire `onOpenLens` at the SceneInspector call sites of `EntityRefField`.

SLICE C — the popover (`panels/EntityReferencesLens.tsx`):
9. Do NOT add a radix dep — there is no Popover/DropdownMenu primitive here. Mirror `features/composition/motif/components/SwapMotifPopover.tsx:16-30`: `role="dialog" aria-modal="true" aria-label={entityName} tabIndex={-1}`, `useEffect(() => { if (open) ref.current?.focus(); }, [open])`, `onKeyDown` Escape → `onClose`.
10. ADD the one thing SwapMotifPopover lacks: RETURN FOCUS TO THE TRIGGER on close (capture `document.activeElement` as the trigger at open; `.focus()` it in every close path). Mandatory now that the trigger is keyboard-reachable — without it, Escape strands focus on `<body>`.

TESTS (M2 DoD gains these literal items):
- `NodeBadges.test.tsx`: (a) with `onOpenEntityLens`, `getByTestId('plan-badge-cast-…').tagName === 'BUTTON'` with a non-empty `aria-label`, and `userEvent.tab()` reaches it; (b) `fireEvent.contextMenu` fires the handler AND `defaultPrevented === true` (no native browser menu over the canvas); (c) WITHOUT the prop it is still a `<span>` and clicking calls nothing — the never-a-dead-button guard.
- `EntityRefField.test.tsx` (exists): the multi-chip lens button is keyboard-reachable; the single-mode `⋯` button mounts only when a value is set.
- `EntityReferencesLens.test.tsx`: Escape closes AND focus returns to the trigger element.
- M2 live browser smoke (§10) adds one line: open the lens KEYBOARD-ONLY (Tab to the cast chip → Enter), no mouse. A mouse-only smoke does not prove this fix.

*Evidence:* frontend/src/features/plan-hub/components/NodeBadges.tsx:26-57 (CanonBadge — the exact wired-⇒-button / unwired-⇒-span precedent to mirror) vs NodeBadges.tsx:88-121 (`case 'cast'` — a bare non-focusable `<span>`, no tabIndex/handler ⇒ right-click-only would be keyboard-unreachable; defect confirmed). Plumbing chain for the new callback: nodePresentation.ts:45 (`onOpenRef` on PlanNodeData) → PlanCanvas.tsx:148,201,223 → ChapterNode.tsx:13,63 / SceneNode.tsx:14,41 / ArcRollupNode.tsx:15,69 → NodeBadges.tsx:17,68 → PlanHubPanel.tsx:228,288. Studio side: EntityRefField.tsx:12-17 (BaseProps), :36-51 (single = `<select>`, no chip to hang a trigger on ⇒ the one place `⋯` is right), :66-82 (MultiRef chip = `<span>` + a `×` `<button>` that already proves the aria-label pattern). Popover: no `components/ui/` dir and frontend/package.json:26-27 has only @radix-ui/react-dialog + react-slot ⇒ hand-roll from SwapMotifPopover.tsx:16-30 (role=dialog/aria-modal/tabIndex=-1/autofocus/Escape), adding the focus-return it lacks.

### Q-37-I18N-KEYS-18-LOCALES
RULE (bake into every wave's DoD): **never change the meaning of an existing i18n key — a changed meaning is a NEW key + DELETE of the old one.** Grounding: the generator's resume path carries an existing translation forward on key-presence/placeholder-parity alone and NEVER compares the English source VALUE (scripts/i18n_translate.py:339-357). So "repurpose bottomStub.*" ⇒ all 17 target locales keep the OLD sentence forever AND `--check` reports 0 hard / 0 soft (green). Silent-stale, no signal.

BUILDER STEPS (i18n slice, run ONCE at the END of each wave, after that wave's `en` keys are final):

1. Hand-edit ONLY `frontend/src/i18n/locales/en/studio.json`. Never hand-edit the other 17.
   - DELETE the whole `"bottomStub"` object (en/studio.json:721-725). Do NOT repurpose it.
   - ADD the wave's new keys under `bottom.*` (M1/M3), `issues.*` (M1), `refs.*` (M2).
   - M3's honest stub text (spec §4.3) gets NEW key names — e.g. `bottom.pending.jobs` = "Book-scoped job feed — pending book_id on the jobs projection (BE-1b)." and `bottom.pending.generation` = same shape. NOT `bottomStub.*`.
2. `StudioBottomPanel.tsx:44` (`t(\`bottomStub.${tab}\`, …)`) disappears with the §4.0 always-mounted refactor; each of the three body components owns its own keys.
3. Do NOT hand-delete `bottomStub` from the 17 target files. Because the wave adds new `en` keys, `plan_namespace` returns `status:"work"` for studio.json in every language, and `assemble_and_write` (scripts/i18n_translate.py:366-380) rebuilds each file from `passthrough + carry + chunks` — all keyed off the EN key set — so orphan keys are pruned automatically.
4. GENERATE (never hand-write): bring LM Studio up on :1234 with `google/gemma-4-26b-a4b-qat`, then from repo root: `python scripts/i18n_translate.py --ns studio`. Plain resume = gap-fill: it translates ONLY the new keys and carries the ~700 existing ones. **Do NOT pass `--force`** (re-translates the whole namespace × 17 langs for nothing). Escape hatch if LM Studio can't run: `ENDPOINT`/`MODEL` are module constants at scripts/i18n_translate.py:50-51 (plain OpenAI-compatible chat) — temporarily repoint them; do NOT commit that edit. This is NOT a defer.
5. VERIFY (paste the output into the VERIFY evidence string):
   - `for l in vi ja ko zh-CN zh-TW es pt-BR fr de ru id ms tr ar hi bn th; do python scripts/i18n_translate.py --check $l/studio.json; done` → every line must read `0 hard`.
   - `ls frontend/src/i18n/locales/*/_FAILED.json` → must be empty (the tool writes it on heal-exhaustion, deletes it when clean: scripts/i18n_translate.py:470-480).
   - `grep -rl bottomStub frontend/src/` → returns nothing (incl. StudioBottomPanel.test.tsx).
   - Eyeball the 8 Latin-script targets' new keys (vi/es/pt-BR/fr/de/id/ms/tr): `isolate_retry_soft` (scripts/i18n_translate.py:270-308) early-returns when `script_re is None`, so an English echo in those 8 has NO detector. ~10 keys × 8 files — cheap.
6. ADD THE MECHANICAL GUARD (checklist⇒test-the-effect): new file `frontend/src/i18n/__tests__/studioBottomParity.test.ts`, modeled on the existing `frontend/src/i18n/__tests__/onboardingParity.test.ts` (same flatten() + key-set-equality shape), importing all 17 target `studio.json` files. Per locale assert: (a) key set === en key set; (b) no empty values; (c) the `{{placeholder}}` set per key === en's; (d) NO key begins with `bottomStub.`; (e) every `BottomTab` id has a `bottom.<id>` key. This test is the wave's i18n gate — it reds if the generator was skipped, which is exactly the desired signal.
7. `/review-impl` at wave close, per PO policy #2.

No PO call is needed: nothing here is a product/taste choice, and this contradicts no §0 sealed decision (it adds zero panel ids, zero catalog rows, zero `panel_id` enum members — consistent with plan 30 §0 / spec 37 §6).

*Evidence:* scripts/i18n_translate.py:339-357 — plan_namespace() gap-fill: `if (k not in retry_keys and isinstance(ev, str) and ev and placeholders(ev) == placeholders(srcv)): carry[k] = ev` — carries the existing translation on key-presence + placeholder-parity, NEVER compares the en source VALUE ⇒ a changed-meaning key ships the stale translation in all 17 locales with a green `--check`. Corroborating: frontend/src/i18n/locales/en/studio.json:721-725 (the `bottomStub` object to delete) vs frontend/src/i18n/locales/fr/studio.json:721-725 (the translation that would be silently carried); frontend/src/features/studio/components/StudioBottomPanel.tsx:44 (the `t('bottomStub.${tab}')` call site); scripts/i18n_translate.py:270-308 (isolate_retry_soft — fixes the SOFT-untranslated lesson, but early-returns for the 8 Latin-script targets); frontend/src/i18n/__tests__/onboardingParity.test.ts:1-49 (the parity-test pattern to copy).

### Q-37-RESIZE-GRIP-UNASSIGNED
Candidate (a): FOLD INTO M1 as a named Contents line item + a DoD item. The question's premise is false — it is NOT a frame change. The 168px literal lives in StudioBottomPanel.tsx:16 (`h-[168px]`), not StudioFrame.tsx:160 (which is only the mount site), and StudioDock.tsx:32 is already `min-h-0 flex-1`, so a `flex-shrink-0` sibling of ANY height needs zero layout change to the frame — only 2 props passed. Persistence already has a home: useStudioChrome.ts:11 key `lw_studio_chrome_${bookId}` with write-through at :43/:51/:59 and a defensive load() at :16-31 — so NO new localStorage key, no new setting, no env flag (consistent with spec 37 §8.2 + CLAUDE.md's per-device-UI carve-out). Total: ~30 lines across 3 files + 2 EXISTING test files. Under CLAUDE.md's fix-now rule the defer row would cost more than the fix; and M1's own DoD is a *usable* feed — §4.1 spends two toolbar rows (filter chips + warnings strip) of the 168px, leaving ~2 visible rows, so a fixed-height M1 ships an unusable feed. Does not contradict §0: PO-1 sanctions wiring the EXISTING StudioBottomPanel; a grip adds no dock panel and no panel_id enum member, so AN-12's fork risk still cannot apply.

BOUNDS: min 120px · max 60vh · default 168px. Clamp on load AND on drag. (Default I chose, PO may veto: 60vh max rather than 80vh/unbounded — the editor is the primary surface and a bottom panel that can eat the dock is a footgun; 60vh already covers "I want to read 20 issues".)

BUILDER STEPS:
1. frontend/src/features/studio/types.ts:13-23 — add `bottomHeight: number` to StudioChromeState; DEFAULT_CHROME.bottomHeight = 168. Export BOTTOM_MIN_PX = 120, BOTTOM_MAX_VH = 0.6.
2. frontend/src/features/studio/hooks/useStudioChrome.ts — add `clampBottomHeight(px) => Math.min(Math.max(px, 120), Math.round(window.innerHeight * 0.6))`. In load() (mirroring the existing defensive ACTIVITY_VIEWS.includes guard at :22): `bottomHeight: Number.isFinite(parsed.bottomHeight) ? clampBottomHeight(parsed.bottomHeight!) : 168`. Add `setBottomHeight(px)` that clamps + write-throughs to the SAME key (copy the toggleBottom body at :56-62); export it.
3. frontend/src/features/studio/components/StudioBottomPanel.tsx:16 — props become { height, onHeightChange, onClose }; replace `h-[168px]` with `style={{ height }}`, keep flex-shrink-0. Add as the FIRST child (above the tab strip): `<div data-testid="studio-bottom-grip" role="separator" aria-orientation="horizontal" tabIndex={0} className="h-1 flex-shrink-0 cursor-row-resize hover:bg-primary/40" …>`. onMouseDown: capture startY/startH, attach mousemove/mouseup to `window` INSIDE the handler, call `onHeightChange(startH - (e.clientY - startY))` (drag up grows), detach on mouseup. NO useEffect (CLAUDE.md: no useEffect for event handling). Keyboard: ArrowUp/ArrowDown on the focused separator = ±16px (the grip must not be mouse-only).
4. frontend/src/features/studio/components/StudioFrame.tsx:160 — `<StudioBottomPanel height={chrome.bottomHeight} onHeightChange={chrome.setBottomHeight} onClose={chrome.toggleBottom} />`. That is the entire frame diff.
5. TESTS (extend the two files that already exist): hooks/__tests__/useStudioChrome.test.ts — setBottomHeight(9999) persists the 60vh clamp; setBottomHeight(10) persists 120; a corrupt/absent stored bottomHeight loads 168. components/__tests__/StudioBottomPanel.test.tsx — the grip renders; mouseDown(grip,{clientY:500}) → mouseMove(window,{clientY:400}) → mouseUp calls onHeightChange(268).
6. SPEC EDITS to 37_issues_feed.md: (i) §9 M1 Contents — append "the resize grip (StudioBottomPanel + useStudioChrome.bottomHeight, 120px–60vh)"; (ii) §10 DoD — add "the panel is drag-resizable and the height survives reload, persisted in the EXISTING lw_studio_chrome_${bookId} key — asserted by a clamp vitest + a drag vitest and exercised in the §10 live smoke"; (iii) CORRECT §4.0's prose, which wrongly says the height is fixed at StudioFrame.tsx:160 — it is StudioBottomPanel.tsx:16, and the frame needs no layout change.

*Evidence:* frontend/src/features/studio/components/StudioBottomPanel.tsx:16 — `<div data-testid="studio-bottom" className="flex h-[168px] flex-shrink-0 flex-col border-t bg-card">` (the 168px literal is HERE, not in the frame). frontend/src/features/studio/components/StudioFrame.tsx:160 — `{chrome.bottomOpen && <StudioBottomPanel onClose={chrome.toggleBottom} />}` (mount site only). frontend/src/features/studio/components/StudioDock.tsx:32 — `<div data-testid="studio-dock" className="relative min-h-0 flex-1">` (the dock already absorbs any sibling height ⇒ no frame layout change). frontend/src/features/studio/hooks/useStudioChrome.ts:11 `const chromeKey = (bookId) => \`lw_studio_chrome_${bookId}\`` + :16-31 load() + :56-62 toggleBottom write-through (the persistence home already exists — no new key). frontend/src/features/studio/types.ts:13-23 StudioChromeState/DEFAULT_CHROME (where bottomHeight is added). Existing tests to extend: frontend/src/features/studio/hooks/__tests__/useStudioChrome.test.ts, frontend/src/features/studio/components/__tests__/StudioBottomPanel.test.tsx. Sealed-decision check: docs/specs/2026-07-01-writing-studio/30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md §0 PO-1 ("wire the EXISTING StudioBottomPanel … no new dock panel") — a grip adds no panel_id, so PO-1 is honoured.

### Q-37-LENS-EXPANDED-ROWS-INERT
AFFIRM the constraint — but its SCOPE as written in §4.2 is wrong by 5x, and applying it literally ships the very bug it forbids. Three instructions:

(1) CORRECT THE SCOPE. §4.2 says only "an expanded `structure_roster` row targets plan-hub". The code says FIVE of the eight REFERENCE_SOURCES emit refs into plan-hub's node id-space: `outline_pov`, `outline_present`, `scene_pov`, `scene_present` (all → `node_ref={kind:"chapter"|"scene", id: outline_node.id}`, via `_ref()` at entity_references.py:207-213) plus `structure_roster` (→ `{kind: structure_node.kind, id: structure_node.id}`, :135-141). Only TWO sources have a target that provably focuses today: `canon_rule` → quality-canon `focusRuleId` (useQualityCanon.ts:74,107) and `narrative_thread` → quality-promises `focusThreadId` (QualityPromisesPanel.tsx:23). `motif_application` has NO consuming panel at all. ⇒ In M2, SIX of eight expanded-row kinds are inert, not one. Rewrite the §4.2 sentence to say so.

(2) ⚠ ID-SPACE TRAP — do NOT route the `chapter`-kind rows to `chapter-browser`. `node_ref.kind=="chapter"` is an `outline_node` of kind chapter, NOT a book-service `chapter_id`. Passing `focusChapterId = node_ref.id` puts an outline_node id in a chapter_id slot: it focuses nothing FOREVER, even after FE-1 lands (repo's cross-service-normalization bug class). All 5 go to `plan-hub` as `focusNodeId`. Never chapter-browser.

(3) BUILD ONE RESOLVER, NOT TWO INERT LISTS — this is what structurally answers the concern. New file `frontend/src/features/studio/panels/issues/deepLinkRef.ts`:
    export type DeepLink = {panel: string; params: Record<string,unknown>} | {inert: true; reason: string};
    export function resolveRefDeepLink(ref: {kind: string; id: string; chapterId?: string|null}, bookId: string): DeepLink
keyed on the `ref_kind` / `node_ref.kind` closed set, returning `{inert, reason}` for every kind whose target panel does not provably read its focus param. BOTH `IssuesTab` (M1) and `EntityReferencesLens` (M2) MUST call it — no surface hand-rolls its own routing. Then the lens CANNOT do what the feed was forbidden to do: it is the same function. And when FE-1 lands (M1b), you flip the plan-hub branches in ONE file and BOTH surfaces light up together, regardless of whether M2 shipped before M1b. That removes the M2-before-M1b ordering hazard entirely rather than relying on a builder remembering a rule.

TEST (the DoD step, per "checklist⇒test the effect"): `deepLinkRef.test.ts` — table-driven over all 8 REFERENCE_SOURCES asserting each kind's resolution, plus a guard asserting every NON-inert branch names a panel in a `PARAM_CONSUMING_PANELS` allowlist, where membership requires an existing test proving that panel reads that param. A new live branch with no proof test reds the suite.

NOTE FOR THE FE-1 IMPLEMENTER (M1b): FE-1 is ~3 lines, not a new capability. `PlanHubPanel.tsx:104-114` ALREADY has `focusNode(nodeId)` = expandAncestorsOf + camera pan + select, already consumed from the `planFocusNode` bus slice at :121-127 (published today by StudioSideBar.tsx:52-54). FE-1 = read `props.params.focusNodeId ?? props.params.focusArcId` and call the EXISTING `focusNode()`. Do NOT invent a second focus mechanism, and do NOT route the lens through the bus as a special case to dodge the Book-Package-track handoff — a second mechanism for one concept is a one-name-one-concept violation and is exactly "the lens doing what the feed was forbidden to do".

DEFAULT THE PO CAN VETO: M2 ships the 6 non-focusable row kinds inert (chevron-less, reason in `title`) via the shared resolver; if M1b has already landed, the 5 plan-hub rows are live automatically with zero extra work. `motif_application` stays inert until spec 33's motif panel lands with a focus param.

*Evidence:* services/composition-service/app/db/repositories/entity_references.py:207-213 (`_ref()` → node_ref {kind: "chapter"|"scene", id: outline_node.id} for outline_pov/outline_present/scene_pov/scene_present) · :135-141 (`_structure_roster` → node_ref {kind: structure_node.kind, id: structure_node.id}) · :143-165 (`_motif_application` → kind "motif_application") · app/services/agent_native.py:53-56 (REFERENCE_SOURCES = the 8). Targets that DO focus today: frontend/src/features/studio/panels/useQualityCanon.ts:74,107 (focusRuleId hoist) and QualityPromisesPanel.tsx:23 (focusThreadId). Param-blind: PlanHubPanel.tsx:39 (`useStudioPanel('plan-hub', props.api)` — props.params never read) and ChapterBrowserPanel.tsx:23 (same); `grep -rn "focusNodeId\|focusArcId" frontend/src` → 0 hits. Live focus machinery that FE-1 should reuse: PlanHubPanel.tsx:104-114 (`focusNode` = expandAncestorsOf + camera + select) wired from the bus at :121-127; publisher pattern at StudioSideBar.tsx:52-54; bus slice at studio/host/types.ts:66,87,109-110.

### Q-37-FRESHNESS-PULL-ONLY
KEEP pull-only — and stop *tolerating* the double fan-out: DELETE it. Three concrete changes, all in M1, all fix-now (none clears a defer gate).

(1) READ THE SPINE ONCE PER REQUEST (backend, `services/composition-service/app/services/coverage.py`). Today `compute_coverage` (:135) and `compute_prose_deleted` (:188) each issue their own exhaustive `book.list_chapters(book_id, bearer, limit=_SPINE_LIMIT, raise_on_404=True)`, and `book_client.py:328-340` paginates at 100 rows/page — so a 400-chapter book costs 4+4 = 8 book-service round-trips per diagnostics call. Add:
    @dataclass(frozen=True)
    class Spine:
        chapters: list[dict[str, Any]] = field(default_factory=list)
        unreadable: bool = False      # BookClientError / 404 — the current `degraded` cause
        truncated: bool = False       # len(chapters) >= _SPINE_LIMIT
    async def read_spine(book_id: UUID, bearer: str, *, book: BookClient) -> Spine
(the single try/except + ceiling check now duplicated at :134-151 and :187-208). Then give BOTH compute fns an optional `spine: Spine | None = None` param: when None they call `read_spine` themselves (so `plan_overlay.py:255` and `mcp/server.py:3811` keep working byte-identically — zero behavior change), when passed they use it. Their DIVERGENT degradation semantics stay exactly as written and must not be unified: coverage treats `truncated` as `spine_truncated` (a FLOOR, still renders — :149-153) while prose_deleted treats it as `degraded=True` with its own warning (:200-208). In `build_diagnostics` (the extraction BE-1a already mandates) call `read_spine` ONCE and hand the same `Spine` to source (4) and source (5). Net: book-service fan-out halves; the "cheap but not free" premise of the concern is retired, not managed.
TEST (`tests/unit/test_coverage.py`): a spy BookClient whose `list_chapters` increments a counter — assert it is called EXACTLY ONCE across a full `build_diagnostics` run (this is the regression guard; today it would read 2). Plus: an unreadable `Spine` ⇒ coverage omits the key + warns AND prose_deleted omits + warns; a truncated `Spine` ⇒ coverage still renders with `spine_truncated=True` while prose_deleted goes `degraded=True`.

(2) THE FOOTER'S `computed_at` DOES NOT EXIST — ADD IT. `Diagnostics.ranked()` (`agent_native.py:138-153`) returns only `items/counts/total/refs_capped/warnings`; §4.1.2's "Stale ⇒ a `computed_at` relative time in the footer" has no field to bind to. Stamp it additively IN `ranked()`: `"computed_at": datetime.now(timezone.utc).isoformat()`. Do it in `ranked()` (not in the router) so the MCP tool gets freshness too — BE-1's "byte-identical to ranked()" contract then holds for free, and no test breaks (`test_agent_native.py:210-225` asserts keys, never strict dict equality). The FE footer renders `formatRelative(data.computed_at)` — the SERVER's compute time, NOT React-Query's `dataUpdatedAt`.

(3) THE 4th TRIGGER YOU DIDN'T SANCTION — CLOSE IT. `frontend/src/App.tsx:11` sets the global QueryClient default `refetchOnWindowFocus: true`. An Issues tab that inherits it refetches (and re-fans-out to book-service) on every alt-tab return — a trigger outside the spec's enumerated (a)/(b)/(c). `useDiagnostics.ts` MUST override explicitly:
    useQuery({ queryKey: ['composition','diagnostics',bookId,{severity,kind,limit}],
               staleTime: 60_000, refetchInterval: false, refetchOnWindowFocus: false, ... })
and the three sanctioned triggers are exactly: query mount (tab open), the Refresh button (`refetch()`), and `diagnosticsEffects.ts`'s `invalidateQueries({queryKey:['composition','diagnostics',bookId]})` (§7.1). NO polling, NO SSE, NO websocket — confirmed as the design, not a placeholder. The Issues tab must hold its data in React-Query (hand-rolled state is unreachable by the Lane-B handler — `invalidatequeries-cannot-reach-hand-rolled-state`); that stays a hard constraint.
TEST (vitest): assert the `useQuery` options object carries `staleTime: 60_000`, `refetchInterval: false`, `refetchOnWindowFocus: false` — a checklist item is DONE only when a test asserts its effect.

Default I'm picking that the PO may veto: `computed_at` is server-stamped rather than client-derived, and it lands on the shared `ranked()` payload (so the agent sees it too). If the PO would rather keep the MCP payload frozen, move the stamp into the BE-1 router only — everything else above is unchanged.

*Evidence:* services/composition-service/app/services/coverage.py:135-137 + :188-190 (two independent exhaustive `list_chapters` calls) · app/clients/book_client.py:328-340 (`_CHAPTERS_PAGE_LIMIT = 100` ⇒ each spine read = ceil(N/100) HTTP calls) · app/mcp/server.py:4084 + :4111 (diagnostics invokes both) · app/services/agent_native.py:138-153 (`ranked()` has NO `computed_at`) · frontend/src/App.tsx:11 (`refetchOnWindowFocus: true` global default) · services/composition-service/tests/unit/test_agent_native.py:210-225 (key-wise asserts, no strict dict equality ⇒ additive field is safe)

### Q-37-M3-CROSS-SERVICE-SMOKE
CONFIRMED — live-smoke is a HARD GATE on M3, not advisory. The concern is correct and the code makes it sharper. Write it into 37 §9 M3 DoD as a literal step, plus these three code facts the spec got only half-right:

(1) BE-1b — stamp book_id at BOTH composition create-emits, not one.
- `services/composition-service/app/db/repositories/generation_jobs.py:127` `_job_params`: add `"book_id": None` placeholder is WRONG — instead, after `job = _row_to_job(row)` (line ~179) do `_job_params["book_id"] = str(job.book_id)` before the `emit_job_event(..., params=_job_params)` at line 180. book_id is derived IN THE SQL (`SELECT $1, $2, w.book_id, …`, line 164) and is already on the returned row — do NOT re-query and do NOT read it off the caller.
- 🔴 `generation_jobs.py:563` is a SECOND create-emit (promoted-scene-prose) that today passes NO `params` at all. Add `params={"book_id": str(job.book_id)}` there. The projection's merge (`jobs-service/app/projection/store.py:61`, `params = COALESCE(old,'{}') || COALESCE(new,'{}')`) only PRESERVES keys — it never invents one, so a job minted on this path would be invisible to the book filter forever. The spec named only line 127; a builder following the spec literally ships a silent omission.
- Same one-liner at `services/translation-service/app/routers/jobs.py:229` `_job_params`: add `"book_id": str(book_id)` — `book_id` is already a parameter of the enclosing `_resolve_and_create_job(db, book_id, …)` (line 106). Without it the tab labelled "Jobs" shows composition jobs only while the book's translation jobs run invisibly — this repo's own silent-omission class. (If the builder judges translation out of scope, that is the ONE thing here that may become a defer row + an honest tab label; the composition half may not.)

(2) BE-1c — one filter, one place. Add `book_id: Optional[str] = Query(default=None)` to `list_jobs` (`services/jobs-service/app/routers/jobs.py:42-51`), thread it into BOTH `store.list_jobs` and `store.list_jobs_paged`, and implement it ONCE in the shared `_build_filters` (`store.py:243`) as `where.append(f"j.params->>'book_id' = ${len(args)}")` — after the owner-scope clause, never replacing it. Note `_build_filters` already forces `j.parent_job_id IS NULL` on the default view; composition jobs are top-level so the smoke is unaffected, but do not remove that clause.

(3) THE SMOKE (the gate itself). New `scripts/smoke_jobs_book_scope_live.py`, modelled on the existing `scripts/smoke_compose_generate_live.py` (same test account 019d5e3c-…, same Dracula BOOK/Work constants, same JWT minting helper). On a stack-up it MUST, in one run:
  a. mint a real composition generation job through the real producer (reuse smoke_compose_generate_live's propose→confirm path — do not INSERT a row by hand; the point is to exercise the producer→outbox→projection path);
  b. poll `GET /v1/jobs?book_id=<BOOK>` through the gateway (:3123) with the user bearer until the new job_id appears — ASSERT it appears, and ASSERT the returned row's `params.book_id == BOOK`;
  c. 🔴 the NEGATIVE half, without which the smoke proves nothing: `GET /v1/jobs?book_id=<a different/random book uuid>` must NOT contain that job_id. A filter that is a silent no-op passes (b) and fails (c) — this is exactly the bug class the concern is raising.
  d. paste the actual pasted output into the VERIFY evidence string as `live smoke: <job_id> visible under ?book_id=<BOOK>, absent under ?book_id=<other>`.

ESCAPE HATCH (the only one): if the full stack genuinely cannot boot at build time, M3 DOES NOT SHIP. Unit-green alone may never close M3. In that case the honest stub copy shipped by M1 stays, and a defer row `D-37-M3-JOBS-LIVE-SMOKE` (gate 4, target: next stack-up) is written. Shipping the Jobs/Generation tabs on mock-green is forbidden.

*Evidence:* services/composition-service/app/db/repositories/generation_jobs.py:127-141 (_job_params, no book_id) · :164 (`SELECT $1, $2, w.book_id, …` — book_id already derived) · :180 (emit with params) · :563 (SECOND create-emit, params omitted entirely — spec 37 §5 BE-1b names only :127) · services/jobs-service/app/routers/jobs.py:42-51 (list_jobs query params, no book_id) · services/jobs-service/app/projection/store.py:243-282 (_build_filters, the single shared WHERE builder) · store.py:57-61 (params jsonb COALESCE merge — preserves, never invents) · services/translation-service/app/routers/jobs.py:229-237 (_job_params, no book_id) + :106 (book_id already in scope) · scripts/smoke_compose_generate_live.py:1-30 (existing live-smoke to model on) · docs/specs/2026-07-01-writing-studio/37_issues_feed.md:641 (M3 DoD already says live-smoke MANDATORY)

### Q-37-X10-DO-NOT-TOUCH-STREAM-SERVICE
THE NO-GO ZONE IS LIFTED — the constraint's premise is false as of HEAD. `git status --porcelain services/chat-service/ frontend/src/features/chat/` is EMPTY: Track C's D8 files (stream_service.py, tool_permissions.py, ToolApprovalCard.tsx, useChatMessages.ts) are committed and clean (stream_service.py last touched by a23c3f15e). Plan 30 §9's "uncommitted, mid-edit RIGHT NOW" row (line 715) is stale. Spec 37 §7.3 is therefore superseded: strike "out of scope / do not touch it" and REPLACE it with "Track C has landed; X-10 runs as the LAST slice of this wave."

BUILDER INSTRUCTION (do this as the final slice of the Issues-feed wave, after the diagnostics + find_references human surfaces land, so the scent sentence is written ONCE and correctly):

1. FILE: services/chat-service/app/services/stream_service.py. Replace the inline block at lines 3751-3765 with a call to a new module-level pure helper (put it next to `_inject_context_ids`, which is already unit-tested in tests/test_context_id_injection.py):

   def _build_book_context_note(book_id, chapter_id, project_id, tools_enabled: bool) -> str | None:
       if not book_id: return None
       note = f"You are working inside book_id={book_id}."
       if chapter_id: note += f" The active chapter is chapter_id={chapter_id}."
       if project_id: note += (f" This book's composition/knowledge project is project_id={project_id}"
                               " — pass it verbatim to any tool that requires a project_id"
                               " (a book_id is NOT a project_id).")
       note += (" Use these exact ids for any tool that requires a book_id or chapter_id."
                " Never ask the user for the book_id and never pass a placeholder.")
       if tools_enabled:   # ← the X-10 / AN-C2 discovery scent — ONE sentence, ~45 tokens
           note += (" To see what is wrong with this book call composition_diagnostics;"
                    " to see everything that references an entity call composition_find_references;"
                    " for the book's structure at a glance call composition_package_tree.")
       return note

   Call site: `book_context_note = _build_book_context_note(_ctx_book_id, _ctx_chapter_id, _ctx_project_id, tools_enabled=(stream_format == "agui" and not disable_tools and kctx.tool_calling_enabled))` — reuse the exact same guard expression already used at line 3635 for the workflows fetch. The scent is gated on tools_enabled so a no-tools turn never names tools it cannot call (no-silent-no-op discipline).

2. TEST (new): services/chat-service/tests/test_stream_service_book_context_note.py — 4 cases: (a) book_id=None ⇒ note is None; (b) tools_enabled=True ⇒ all three literals "composition_diagnostics", "composition_find_references", "composition_package_tree" appear; (c) tools_enabled=False ⇒ none of the three appear; (d) project_id present ⇒ the "a book_id is NOT a project_id" clause survives (regression guard on CTX-1).

3. Use the EXACT tool names as registered — composition_package_tree (mcp/server.py:3712), composition_find_references (:3867), composition_diagnostics (:3935). Do NOT invent a namespaced/prefixed variant.

4. This does NOT contradict IF-5 (§7.2): naming composition_package_tree in the AGENT's scent is not a human GUI surface, so AN-12 still stands for it.

Cost note (Context Budget Law): +1 sentence (~45 tokens) on book-scoped tool-enabled turns only. If a budget test reds on the constant, update the baseline — do not drop the scent.

PO veto point (my chosen default, flag if you disagree): I named all THREE tools rather than only the two getting human surfaces, because AN-11's own risk row calls "shipped but never called" a FAIL and package_tree is precisely the tool with no human path to it.

*Evidence:* services/chat-service/app/services/stream_service.py:3751-3765 (book_context_note, ids only — 0 tool names); `git status --porcelain services/chat-service/ frontend/src/features/chat/` → empty (Track C landed; last commit a23c3f15e); `grep -rn "composition_package_tree|composition_diagnostics" services/chat-service/app/` → 0 hits; tools registered at services/composition-service/app/mcp/server.py:3712 (package_tree), :3867 (find_references), :3935 (diagnostics); stale no-go row at docs/specs/2026-07-01-writing-studio/30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md:715 and X-10 row at :343.

### Q-37-OQ2-CLOSED-DO-NOT-RELITIGATE
CONFIRMED CLOSED — the answer is still NO at the CURRENT HEAD b2a119460 (I re-grepped as instructed; HEAD has moved past 9262ed53e but no track added these params). `focusNodeId`/`focusArcId` = ZERO hits anywhere in frontend/src. `PlanHubPanel.tsx:39` and `ChapterBrowserPanel.tsx:23` call `useStudioPanel(id, props.api)` and never reference `props.params` at all. `useStudioPanel` returns a localized label STRING (useStudioPanel.ts:11-17) — it has no params channel; params arrive ONLY as the dockview prop `props.params`. The M1 inert-row decision stands: the 3 rows targeting plan-hub ship INERT (IF-4 case 2) and light up in M1b via FE-1. Do not re-open.

BUILDER INSTRUCTION for FE-1 (M1b) — it is SMALLER than the spec assumes; do NOT build a focus mechanism, plan-hub already has one:

1) `PlanHubPanel.tsx` ALREADY has the complete focus primitive: `focusNode(nodeId)` at line 104 does expandAncestorsOf -> camera pan (bump `focusTarget.seq`) -> `select(nodeId)`. It is currently fed ONLY by the studio bus (`planFocusSeq`/`planFocusNodeId`, the PH25 Activity-Bar rail). FE-1 = feed that SAME `focusNode` from `props.params`. Do not add a second focus path.

2) In `PlanHubPanel.tsx`, read `const p = props.params as { focusNodeId?: string; focusArcId?: string } | undefined` and resolve `const target = p?.focusNodeId ?? p?.focusArcId ?? null`. A single target is correct for BOTH: the file's own header comment states "rollup node id === structure_node id" — an arc's rollup node IS a node in `view.layout`, so `focusNode(arcId)` works unchanged. No separate arc code path.

3) CRITICAL TRAP — do NOT fire this on a bare mount effect. `expandAncestorsOf` (usePlanHub.ts:152-167) closes over `shell`, which is EMPTY at mount, so it early-returns at line 160, and `select()` then selects a node that is not drawn. That silently reproduces the exact "opens the panel onto nothing" bug FE-1 exists to kill — and a unit test over a mocked usePlanHub would still pass. Gate the effect on the shell having LANDED and latch it once: `const fired = useRef(false); useEffect(() => { if (fired.current || !target) return; if (!view.layout.nodes.some(n => n.id === target)) return; fired.current = true; focusNode(target); }, [target, view.layout.nodes, focusNode]);` Mirror the existing bus-effect's seq/ref discipline (PlanHubPanel.tsx ~118-126) so a re-mount never replays a stale focus. This is a legitimate useEffect (synchronising an external request stream onto an imperative camera), consistent with the comment already in that file.

4) Sibling, same wave: `ChapterBrowserPanel.tsx` reads `props.params.focusChapterId` and hoists+reveals that row. Mirror `useQualityCanon`'s `hoist()` (useQualityCanon.ts:64 — stable sort, hoists the match to the top, NEVER hides non-matches; params typed as a `CanonFocusParams`-style interface, useQualityCanon.ts:27-31).

5) TEST (this is the assertion that matters): a Playwright click on the issue row must land ON THE FOCUSED NODE — assert `plan-hub` shows the target node SELECTED (and its collapsed ancestor arcs expanded), NOT merely that the tab mounted. Asserting the panel mounted is the false-green this whole item exists to prevent. Add a vitest that renders PlanHubPanel with `props.params={{focusNodeId}}` against a usePlanHub whose `shell` arrives ASYNC (empty on first render, populated on the second) — that test reds against the naive mount-effect and greens only with the shell-gated latch.

DEFAULT I PICKED (veto-able): the spec's §9 note says the Book-Package track "owns both files", implying FE-1 must wait for a handoff. I checked — there are NO uncommitted changes to `frontend/src/features/studio/panels/` and the last commit touching either file is d662bd97d (the D-04 canon deep-link, already landed). The files are FREE. Build FE-1 in M1b without waiting for a handoff; just re-run `git status --porcelain -- frontend/src/features/studio/panels/` at build time and rebase if that has changed.

*Evidence:* RE-VERIFIED AT HEAD b2a119460 (moved past the 9262ed53e cited in the question; answer unchanged).
· `grep -rn "focusNodeId|focusArcId" frontend/src` -> ZERO hits (matches exist only in docs/specs/2026-07-01-writing-studio/*.md).
· `grep -rn "props.params" PlanHubPanel.tsx ChapterBrowserPanel.tsx` -> ZERO hits. Confirms neither panel reads params.
· frontend/src/features/studio/panels/PlanHubPanel.tsx:39 — `useStudioPanel('plan-hub', props.api);` (params never consumed)
· frontend/src/features/studio/panels/ChapterBrowserPanel.tsx:23 — `useStudioPanel('chapter-browser', props.api);` (params never consumed)
· frontend/src/features/studio/panels/useStudioPanel.ts:11-17 — signature `(panelId, api, extras?) -> string`, returns the i18n label; NO params return. The old "useStudioPanel exposes params" claim is FALSE, as recorded.
· THE EXISTING SEAM (makes FE-1 small): PlanHubPanel.tsx:102-113 — `const [focusTarget, setFocusTarget] = useState<CameraFocusTarget|null>(null)` + `const focusNode = useCallback((nodeId) => { expandAncestorsOf(nodeId); setFocusTarget(prev => ({nodeId, seq:(prev?.seq??0)+1})); select(nodeId); })`. Fed only by the bus at PlanHubPanel.tsx:118-126.
· THE TRAP: frontend/src/features/plan-hub/hooks/usePlanHub.ts:152-167 — `expandAncestorsOf` builds `new Map(shell.map(...))` and `if (!ancestors.length) return;` (line 160). `shell` is empty at mount => a mount-time param focus is a silent no-op.
· ARC==NODE: PlanHubPanel.tsx header comment (lines 13-16) — "rollup node id === structure_node id, laneLayout" => focusArcId routes through the same focusNode().
· HOIST REFERENCE: frontend/src/features/studio/panels/useQualityCanon.ts:64 `function hoist<T>(rows, matches, active)` + :27-31 `CanonFocusParams {focusRuleId?, focusChapterId?}` + :74 `params?.focusRuleId ?? null`; consumed at QualityCanonPanel.tsx:33.
· PRECEDENT (14 panels already do this): JobDetailPanel.tsx:24, SettingsPanel.tsx:35, KgEvidencePanel.tsx:14, QualityPromisesPanel.tsx:23, WikiEditorPanel.tsx:50, BookReaderPanel.tsx:52, ChapterRevisionComparePanel.tsx:44.
· FILE OWNERSHIP: `git status --porcelain -- frontend/src/features/studio/panels/` -> empty; last commit touching either target file = d662bd97d (landed). No in-flight Book-Package-track edits to block on.

### Q-37-M1B-DOD-FOCUS-NOT-MOUNT
The concern is valid and the fix is mechanical: today "focused" is NOT OBSERVABLE on either FE-1 target, so any M1b test would be forced to assert on mounting. Replace 37 §9's M1b DoD prose with this literal 5-part contract. It mirrors the shipped `quality-canon` precedent exactly — do not invent a second focus idiom.

(1) MAKE FOCUS ASSERTABLE (the missing surface — this is why the "obvious test" is a mount test).
- `frontend/src/features/plan-hub/components/ChapterNode.tsx:21`, `ArcRollupNode.tsx:23`, `SceneNode.tsx:23`: add `data-selected={selected ? 'true' : undefined}` beside the existing `data-testid={`plan-node-*-${node.id}`}`. Today `selected` renders ONLY as the class `ring-2 ring-primary` (ChapterNode.tsx:27) — unassertable.
- `frontend/src/features/studio/panels/ChapterBrowserTitleView.tsx:463` (row div): add `data-chapter-id={c.chapter_id}` and `data-focused={c.chapter_id === focusChapterId ? 'true' : undefined}`.
Both mirror `QualityCanonPanel.tsx:168` (`data-focused={focused ? 'true' : undefined}`) — one idiom, one name.

(2) WIRE THE PARAMS TO THE EXISTING REVEAL PATH.
- `PlanHubPanel.tsx:38-42` currently discards `props.params`. Read `{focusNodeId, focusArcId}` from `props.params` and call the EXISTING `focusNode(nodeId)` (`PlanHubPanel.tsx:104-114` = expandAncestorsOf + camera seq bump + select). `focusArcId` resolves to the arc rollup node (rollup node id === structure_node id — PlanHubPanel.tsx:13-16). Guard the mount effect with a seq/ref diff exactly like the bus effect at `:120-127`.
- `ChapterBrowserPanel.tsx:23` reads `props.params.focusChapterId` and passes it to `ChapterBrowserTitleView` (and forces `mode='title'`). Because the list is SERVER-PAGED (`ChapterBrowserTitleView.tsx:93,125`), the focused chapter may not be on the loaded page: fetch it with `booksApi.getChapter(token, bookId, focusChapterId)` (`frontend/src/features/books/api.ts:345` — NO new route needed) and PIN it as a row at the top of the list with `data-focused="true"`. A focus HOISTS, never filters (`useQualityCanon.ts:15-16,64-67`).

(3) A FOCUS THAT MATCHES NOTHING MUST SAY SO (the anti-silent-success half — mirror `FocusBanner`, QualityCanonPanel.tsx:136-160).
- PlanHub: focus id absent from `view.nodeContent` after expand ⇒ render `data-testid="plan-hub-focus-miss"` ("the node you came from is not in this plan"). NEVER a plain unfocused canvas.
- ChapterBrowser: `getChapter` 404 ⇒ `data-testid="chapter-browser-focus-miss"`.

(4) THE TESTS — M1b does not close without all four. DoD-0 ("provably reads the focus param") is satisfied by T1, never by inspection.
- T1 (THE guard) `frontend/src/features/studio/panels/__tests__/issuesFeedFocusContract.test.tsx`: for each of the 3 FE-1 kinds (`prose_deleted_spec_node`, `conformance_never_run|dirty`, `unplanned_chapter`), IMPORT the Issues routing table and use the openPanel args it ACTUALLY emits (never a hand-written params object — a hand-written one only encodes the author's assumption and cannot catch a `focusNodeId` vs `nodeId` key drift), render the target panel with `props.params = args.params`, and assert exactly ONE `[data-focused="true"]`/`[data-selected="true"]` element AND that its `data-testid`/`data-chapter-id` carries the id the ROW sent. This is the emitter→consumer join.
- T2 miss path: unknown id ⇒ the miss banner renders and ZERO elements carry `data-focused`/`data-selected`.
- T3 negative control (proves the assertion can fail): panel rendered with NO params ⇒ zero `[data-focused]`/`[data-selected]`.
- T4 Playwright (folds into DoD-6): the assertion is written against the SEEDED id — the id comes from the test's own fixture/row payload and is NEVER read back out of the panel (reading it back lets a panel that focuses anything at all pass). Literally:
    // BANNED — certifies nothing: expect(page.getByTestId('studio-plan-hub-panel')).toBeVisible()
    await clickIssuesRow('unplanned_chapter');
    const f = page.locator('[data-testid="studio-chapter-browser-panel"] [data-focused="true"]');
    await expect(f).toHaveCount(1);
    await expect(f).toHaveAttribute('data-chapter-id', seededChapterId);
  and for plan-hub: await expect(page.locator('[data-testid="studio-plan-hub-panel"] [data-selected="true"]')).toHaveAttribute('data-testid', `plan-node-chapter-${seededNodeId}`);
  Drive dockview via evaluate + data-testid (refs go stale).

(5) WRITE THE BAN INTO THE DoD, not just the requirement: "asserting a panel/tab MOUNTED, or asserting any `studio-*-panel` testid is visible, is NOT an M1b assertion and does not close the slice. The assertion must name the entity id the clicked row sent." Also note the ownership constraint already in the spec: ChapterNode/ArcRollupNode/PlanHubPanel/ChapterBrowserTitleView are Book-Package-track-owned (plan 30 §9) — coordinate before editing; the changes above are additive attributes + a params read, chosen to minimise conflict surface.

Default I am picking (PO may veto): the paged-miss case PINS the focused chapter row rather than auto-paging to it — pinning is O(1), works on any page, and preserves "focus hoists, never filters".

*Evidence:* frontend/src/features/studio/panels/QualityCanonPanel.tsx:168 (`data-focused` — the shipped assertable-focus precedent) + :136-160 (FocusBanner admits a zero-hit focus); frontend/src/features/studio/panels/useQualityCanon.ts:64-67,107 (hoist contract, "a focus HOISTS and HIGHLIGHTS — it never hides"); frontend/src/features/plan-hub/components/ChapterNode.tsx:21,27 (selected is a Tailwind class ONLY — nothing to assert on; same ArcRollupNode.tsx:23,27, SceneNode.tsx:23); frontend/src/features/studio/panels/ChapterBrowserTitleView.tsx:463 (row has no chapter id attr) + :93,125 (server-paged 50/page ⇒ focused chapter may be off-page); frontend/src/features/studio/panels/PlanHubPanel.tsx:39 (props.params discarded), :104-114 (focusNode = expandAncestorsOf + camera + select — the reveal path to reuse), :120-127 (seq-diff effect pattern to mirror); frontend/src/features/studio/panels/ChapterBrowserPanel.tsx:23 (never reads props.params); frontend/src/features/books/api.ts:345 (getChapter — the off-page fetch needs no new route)

### Q-37-DOD6-LIVE-BROWSER-SMOKE
DoD-6 STANDS AS WRITTEN — it is buildable today at $0, needs no LLM, and every piece it requires already exists. Do NOT weaken it, do NOT accept `live infra unavailable`. Build it as TWO committed specs on the M1/M2 slice boundary (§9 says M1/M2 are independently shippable; one lumped smoke would block M1 on M2's lens).

**A · The seed is SQL, not a generation run ($0, deterministic).** `OutlineRepo.rule_violations` (services/composition-service/app/db/repositories/outline.py:1257-1372) reads ONLY: the latest `status='completed'` `generation_job` per scene `outline_node`, `operation <> 'promoted_scene_prose'` (outline.py:1324), unnesting `critic->'violations'` where `violated IS DISTINCT FROM false` and `dismissed IS DISTINCT FROM true`, LEFT JOINing `canon_rule` on `cr.id::text = violation->>'rule_id'`. So add to `frontend/tests/e2e/helpers/db.ts` (it already has `queryComposition()` + `dbAvailable()` at :19,:45):
`seedCanonRuleViolation(projectId, bookId, sceneNodeId, userId) -> ruleId` = INSERT one `canon_rule` (project_id, text, active=true, is_archived=false) + one `generation_job` (`generation_job` DDL: migrate.py:265-285) with `status='completed'`, `operation='draft_scene'`, `outline_node_id=<scene>`, `critic='{"violations":[{"rule_id":"<ruleId>","why":"...","span":"..."}]}'::jsonb`. Book/work/scene come from the EXISTING helpers `createBook` / `createCompositionWork` / `createCompositionScene` / `createOutlineNode` (frontend/tests/e2e/helpers/api.ts:46,305,312,325). Zero LLM spend.

**B · The hoist assertion needs NO new testid.** `QualityCanonPanel.tsx:168` already renders `<li data-testid="quality-canon-rule-item" data-focused={focused?'true':undefined}>`, and `useQualityCanon.ts:107` does the sort. The IF-2 proof is one line:
`await expect(page.getByTestId('quality-canon-rule-item').first()).toHaveAttribute('data-focused','true')`
plus `await expect(page.getByTestId('studio-quality-canon-panel')).toBeVisible()` (:48). If `rule_id` is still dropped from the payload, `focusRuleId` is null, `hoist()` is inert, and `.first()` has no `data-focused` → RED. That is exactly the assertion the unit test cannot make.

**C · The INERT proof must diff the DOCK-TAB SET, not just look for one tab.** For each of the 3 FE-1 rows (`prose_deleted_spec_node`, `conformance_never_run|_dirty`, `unplanned_chapter`): assert `getByTestId('issues-row-chevron-<idx>')` has count 0; snapshot `page.locator('.dv-default-tab').allTextContents()` BEFORE, `.click()` the row, assert the array is UNCHANGED after. (StudioPage.closePanel already uses `.dv-default-tab` — pages/StudioPage.ts:64.) Asserting merely "no plan-hub tab" would pass if the row opened some other panel.

**D · New testids the M1 build must ADD.** `StudioBottomPanel.tsx` today carries only `data-testid="studio-bottom"` (:16). Add `bottom-tab-<id>` and `bottom-body-<id>` (§6 already names `bottom-body-jobs`), plus per-row `issues-row-<kind>-<idx>` carrying `data-severity="error|warn|info"`, and `issues-row-chevron-<idx>` rendered ONLY when the row is live — the chevron's ABSENCE is the machine-readable inert contract. `StudioPage` already exposes `bottom` + `toggleBottom` (pages/StudioPage.ts:23-24) — reuse, don't re-add.

**E · M2 lens spec.** Right-click `plan-badge-cast-<nodeId>` (NodeBadges.tsx follows `plan-badge-<x>-${nodeId}`, :38,73,82) → assert `getByTestId(/^refs-lens-source-/)` `.toHaveCount(8)` — one per `REFERENCE_SOURCES` (agent_native.py:53-56: outline_pov, outline_present, scene_pov, scene_present, structure_roster, motif_application, canon_rule, narrative_thread) — and ≥1 count cell non-zero. Add `refs-lens-source-<source>` + `refs-lens-count-<source>` testids.

**F · The run recipe — use :5199, not :5174.** :5174 is the BAKED nginx image; FE changes require an image rebuild and a host vite would SHADOW it. So: `cd frontend && npx vite --port 5199` (proxies /v1 → gateway :3123), then `PLAYWRIGHT_BASE_URL=http://localhost:5199 npx playwright test tests/e2e/specs/issues-feed.spec.ts --project=chromium` — `playwright.config.ts:3` already reads `PLAYWRIGHT_BASE_URL` (defaulting to 5174). Docker stack must be up (gateway + composition + book + postgres). Screenshots: write to `docs/specs/2026-07-01-writing-studio/evidence/37-issues-feed.png` and `-lens.png` and COMMIT them (the playwright `outputDir` tests/e2e/test-results is throwaway).

**G · Skip-gate policy (my default, veto-able).** Guard both specs with `test.skip(!dbAvailable())` (helpers/db.ts:45) so a stack-less CI SKIPS rather than REDS — BUT a SKIP does not satisfy DoD-6. The wave closes only when the transcript contains the pasted runner output showing the specs PASSED (`N passed`, not `N skipped`) + the two committed screenshots. This is the `env-gated-integration-tests-skip-and-the-green-suite-lies` trap; a skipped smoke is an unmet DoD, not a green one.

New files: `frontend/tests/e2e/specs/issues-feed.spec.ts` (M1, DoD-6 bullets 1-4) and `frontend/tests/e2e/specs/entity-references-lens.spec.ts` (M2, DoD-6 bullet 5).

*Evidence:* Seedability (no LLM): services/composition-service/app/db/repositories/outline.py:1257-1372 (`rule_violations` reads latest completed generation_job's `critic->'violations'`, excludes `operation='promoted_scene_prose'` at :1324) + generation_job DDL services/composition-service/app/db/migrate.py:265-285 (`critic JSONB`, `status`, `outline_node_id`). Hoist assertion already has its hook: frontend/src/features/studio/panels/QualityCanonPanel.tsx:168 (`data-testid="quality-canon-rule-item" data-focused=…`) driven by frontend/src/features/studio/panels/useQualityCanon.ts:106-109 (`hoist(allRules, r => r.rule_id === focusRuleId)`). Harness exists: frontend/playwright.config.ts:3 (`PLAYWRIGHT_BASE_URL` env override), frontend/tests/e2e/pages/StudioPage.ts:23-24,35,64 (`studio-bottom`, `studio-toggle-bottom`, `goto`, `.dv-default-tab`), frontend/tests/e2e/helpers/db.ts:19,45 (`queryComposition`, `dbAvailable`), frontend/tests/e2e/helpers/api.ts:46,305,312,325 (`createBook`, `createCompositionWork`, `createCompositionScene`, `createOutlineNode`). Missing testids: frontend/src/features/studio/components/StudioBottomPanel.tsx:16 (only `studio-bottom`). 8 sources: services/composition-service/app/services/agent_native.py:53-56. Cast badge naming: frontend/src/features/plan-hub/components/NodeBadges.tsx:38,73,82 (`plan-badge-<x>-${nodeId}`).

### Q-37-GATEWAY-ZERO-WORK
CLAIM CONFIRMED — ZERO gateway work, for BOTH composition AND jobs. Do not write any gateway code for M1/M2/M3.

(1) COMPOSITION (BE-1, BE-1d): gateway-setup.ts:350-354 `pathFilter: (pathname) => pathname.startsWith('/v1/composition')` with NO `pathRewrite`, dispatched at :657-658 from a root-mounted `instance.use()` (no mount-path prefix stripping). Any new `/v1/composition/**` route auto-proxies. Reachable from the FE with zero gateway change.

(2) JOBS `book_id` PARAM (BE-1c): also zero gateway work — the param is NOT stripped. gateway-setup.ts:273-277 is the identical shape (pathFilter startsWith '/v1/jobs', no pathRewrite), dispatched at :663-664. Two independent reasons a query param cannot break it: (a) the dispatcher branches on Express `req.path`, which EXCLUDES the query string, so `?book_id=` can never break the startsWith match; (b) `createProxyMiddleware` with no `pathRewrite` forwards `req.url` verbatim (path + query). The gateway never enumerates, validates, or whitelists query params anywhere in the 673-line file. PROOF BY SHIPPED PRECEDENT, not reasoning: the FE already pushes 8 query params through this exact proxy (frontend/src/features/jobs/api.ts:18-28 — status, kind, parent, q, bucket, cursor, offset, limit) and jobs-service reads exactly those as FastAPI Query() params (jobs-service/app/routers/jobs.py:44-51). `book_id` is the 9th and is indistinguishable from the other 8 at the proxy.

THE REAL RISK THE SPEC MISSED (fix it in BE-1c, it is buildable not blocked): `job_projection` has NO `book_id` column (jobs-service/app/migrate.py:29-53). So BE-1c is not merely "add a Query param" — with no carrier the param parses fine, filters nothing, and returns EVERY job while the test looks green (the repo's "silent success is a bug" class). BUILD IT VIA `params` JSONB — do NOT add a column. The table's own comment (migrate.py:43-46) declares `params JSONB` to be exactly this extension point ("whitelisted dynamic key-value — model now, effort later — no schema change"); the consumer additive-COALESCE-merges it so a later event never wipes it (projection/store.py:61); and `params.retryable` (jobs-service/app/contract.py:53-55) is the shipped precedent of a producer-set params key read as a first-class signal. `params.book_id` is the identical shape.

BUILDER STEPS — 3 edits, all in-repo:
1. PRODUCER — services/composition-service/app/db/repositories/generation_jobs.py:183: change `params=_job_params` to `params={**_job_params, "book_id": str(job.book_id)}`. `book_id` is already on the row (the INSERT…SELECT derives it from `composition_work w.book_id`, lines 163-164) and `job` is in scope from line 176. One line.
2. READER — services/jobs-service/app/routers/jobs.py:43-51: add `book_id: Optional[str] = Query(default=None)` and thread it into `store.list_jobs`; in projection/store.py add `AND params->>'book_id' = $n` to the list WHERE. Add the expression index in migrate.py beside the others (~line 64): `CREATE INDEX IF NOT EXISTS idx_job_projection_owner_book ON job_projection (owner_user_id, (params->>'book_id'), job_updated_at DESC);`
3. FE — frontend/src/features/jobs/api.ts:18-28: `if (params.bookId) q.set('book_id', params.bookId);` + the field on `JobListParams` in types.ts.

TEST (the one that matters): a jobs-service test asserting `GET /v1/jobs?book_id=X` returns only rows whose `params->>'book_id' = X` AND EXCLUDES a same-owner job belonging to another book. The exclusion assertion is the one that catches the silent-no-op — a param the query ignores returns everything and still passes a presence-only test.

SCOPE NOTE (default I am picking; PO may veto): jobs from producers that do not set `params.book_id` (translation, extraction, …) will be invisible under a `book_id` filter. That is CORRECT for M3's "this book's issues feed". If a later wave wants a cross-kind book filter, each producer adds the same one-liner — same shape, still no schema change. Worth a comment in the code, not a defer row.

*Evidence:* services/api-gateway-bff/src/gateway-setup.ts:350-354 (compositionProxy: pathFilter startsWith '/v1/composition', no pathRewrite) + :657-658 (dispatch); gateway-setup.ts:273-277 (jobsProxy: pathFilter startsWith '/v1/jobs', no pathRewrite) + :663-664 (dispatch); dispatcher is a root-mounted `instance.use()` branching on Express `req.path` (query-string-excluded) — gateway-setup.ts:570-667, no query-param handling anywhere in the file. Passthrough proven by shipped precedent: frontend/src/features/jobs/api.ts:18-28 (8 query params sent) ↔ services/jobs-service/app/routers/jobs.py:44-51 (same 8 read as FastAPI Query()). Missing carrier: services/jobs-service/app/migrate.py:29-53 (job_projection has no book_id column) + :43-46 (params JSONB declared as the no-schema-change extension point); services/jobs-service/app/projection/store.py:61 (params additive-COALESCE merge); services/jobs-service/app/contract.py:53-55 (params.retryable = shipped producer-set-key precedent); services/composition-service/app/db/repositories/generation_jobs.py:127-133 (_job_params), :163-164 (book_id derived from composition_work), :176-183 (job in scope; emit_job_event(params=_job_params)).

### Q-37-M1-M2-DISJOINT-CLAIM
The §9 claim is FALSE as written — CORRECT THE SPEC and BUILD THE SHARED ROUTER IN M1. M1 and M2 are *sequentially* shippable (M2 after M1), NOT parallelizable, and they do NOT touch disjoint files: they share (a) the row→panel router, (b) the `studio.json` locale family, (c) the BE payload conventions.

**M1 MUST create `frontend/src/features/studio/host/issueRouting.ts`** — one pure module, mirroring the shipped `host/studioLinks.ts` pattern exactly (no React, no hooks, host injected by the caller, returns an `effect` closure). NOT `studio/lib/issueRouting.ts` as §9 suggests — there is no `lib/` dir, and `host/` is already the home of pure host-effect resolvers (`studioLinks.ts`), with its test dir `host/__tests__/`.

EXACT CONTENTS (build this, don't redesign it):

```ts
// frontend/src/features/studio/host/issueRouting.ts
import type { StudioHost } from './StudioHostProvider';

/** Spec 37 §3 IF-1 — the 3-member closed set. Do not add canon_rule/scene. */
export type IssueRefKind = 'chapter' | 'outline_node' | 'structure_node';

/** The normalized target BOTH surfaces produce. Issues rows normalize from the diagnostic
 *  `kind` + `node_ref` + IF-2 siblings; lens rows normalize from a REFERENCE_SOURCES member. */
export interface IssueTarget {
  refKind?: IssueRefKind | null;
  refId?: string | null;      // id in refKind's space — NEVER cross-assigned (IF-1)
  chapterId?: string | null;  // book-service chapter_id ONLY
  sceneId?: string | null;
  ruleId?: string | null;     // IF-2 sibling
  threadId?: string | null;
  arcId?: string | null;
}

export type IssueRoute =
  | { kind: 'inert'; reason: 'no-owner' | 'param-blind'; panelId?: string }
  | { kind: 'open'; panelId: string; params: Record<string, unknown>;
      effect: (host: StudioHost) => void };

/** FE-1 (§4.1.1): panels that do NOT yet read their focus param. THE SINGLE KILL-SWITCH —
 *  M1b deletes entries here and every row in BOTH surfaces lights up. Never inline this test. */
export const PARAM_BLIND_PANELS: ReadonlySet<string> = new Set(['plan-hub', 'chapter-browser']);

export function routeDiagnostic(item: DiagnosticItem, bookId: string): IssueRoute;
export function routeReference(source: ReferenceSource, t: IssueTarget, bookId: string): IssueRoute;
```

Both public fns normalize to `IssueTarget` and delegate to ONE private `route(panelId, params, effect)` that applies, in order: (1) no panel owns it (`index_stale`) → `{kind:'inert', reason:'no-owner'}`; (2) `PARAM_BLIND_PANELS.has(panelId)` → `{kind:'inert', reason:'param-blind', panelId}`; (3) otherwise `{kind:'open', ..., effect: (host) => { host.publish?…; host.openPanel(panelId, {focus:true, params}) }}`. The `canon_contradiction` row's `publish({type:'scene', sceneId, chapterId})` + `openPanel` pair lives INSIDE that effect — `StudioHost` (StudioHostProvider.tsx:32-59) exposes both `publish` and `openPanel`, so one closure covers every row in §4.1.1.

CONSUMER RULE (enforced): `IssuesTab.tsx` (M1) and `EntityReferencesLens.tsx` (M2) call `routeDiagnostic`/`routeReference` and render `route.kind === 'inert'` as chevron-less + not-clickable + `title=reason` (IF-4). NEITHER file may contain a literal panel id string ('quality-canon', 'plan-hub', 'quality-promises', 'chapter-browser', 'editor', 'job-detail'). Add this to each wave's DoD as a grep: `grep -nE "openPanel\(['\"](quality-canon|quality-promises|plan-hub|chapter-browser)" frontend/src/features/studio/components/bottom/ frontend/src/features/studio/panels/EntityReferencesLens.tsx` must return ZERO hits.

TESTS (M1, `host/__tests__/issueRouting.test.ts` — mirror `studioLinks.test.ts`):
- all 7 §4.1.1 kinds → the exact expected `{panelId, params}` (table-driven);
- `index_stale` → `inert/no-owner`;
- `prose_deleted_spec_node` + both `conformance_*` + `unplanned_chapter` → `inert/param-blind` (this is DoD-0's guard, and it lives HERE, in the router — not duplicated into two component tests);
- IF-1: a `prose_deleted_spec_node`'s `outline_node` id is NEVER emitted as `focusChapterId`;
- M1b flips `PARAM_BLIND_PANELS` to empty and the SAME table asserts those 4 rows become `open`.

BOOKKEEPING (do in M1, one edit each):
1. `37_issues_feed.md` §9 — replace *"M1 and M2 are independently shippable and touch disjoint files"* with: *"M2 depends on M1: it consumes `host/issueRouting.ts` (the §4.1.1 router incl. the FE-1 inert rule, per §4.2) and the same `studio.json` locale family. Ship M1 → M2 → (M1b | M3). Do not parallelize M1 and M2."*
2. `37_issues_feed.md` §9 M1 row — add `host/issueRouting.ts` + its test to M1's Contents, and add the zero-literal-panel-id grep to M1's DoD.
3. i18n: M1 owns namespace `issues.*`, M2 owns `entityRefs.*` in `frontend/src/i18n/locales/<lang>/studio.json` (18 locales). Disjoint key namespaces make the shared file additively mergeable — state that in §9 rather than claiming the file isn't shared.

DEFAULT I AM PICKING (veto-able): the module goes in `host/`, not a new `lib/` dir, because `host/studioLinks.ts` is the exact same shape (pure resolver → `effect: (host) => void`) and splitting the two across two dirs is how the second router gets written.

*Evidence:* FORK CONFIRMED — the spec contradicts its own §9: `docs/specs/2026-07-01-writing-studio/37_issues_feed.md:385` — "Each expanded row deep-links exactly like an Issues row (§4.1.1 routing) — **including the FE-1 inert rule**" (M2 consumes M1's table verbatim). NO shared router exists today: the sole deep-link emitter is inlined at `frontend/src/features/studio/panels/PlanHubPanel.tsx:65-78` (`openRef` hand-rolls `openPanel('quality-canon', {focus:true, params:{bookId, focusRuleId, focusChapterId}})`) — copy it twice more and there are 3 forks. PATTERN TO MIRROR: `frontend/src/features/studio/host/studioLinks.ts:1-12,64-115` (pure, React-free, `{kind, effect:(host:StudioHost)=>void}`, host injected, tested standalone at `host/__tests__/studioLinks.test.ts`). `StudioHost` exposes BOTH `publish` and `openPanel` — `frontend/src/features/studio/host/StudioHostProvider.tsx:43,52` — so one `effect` closure covers the `publish({type:'scene'})`+`openPanel` row. FE-1 grounding (the inert predicate that MUST be single-sourced): `grep -rn "focusNodeId|focusArcId" frontend/src` = 0 hits; `PlanHubPanel.tsx:39` and `ChapterBrowserPanel.tsx:23` never read `props.params` — while `useQualityCanon.ts:74-75,107-112` DOES (`hoist()` on focusRuleId/focusChapterId). i18n IS shared: `frontend/src/i18n/locales/{ar,bn,de,en,es,fr,hi,id,ja,ko,ms,pt-BR,ru,th,tr,vi,zh-CN,zh-TW}/studio.json` — one file family, 18 locales, both milestones write it. No `frontend/src/features/studio/lib/` dir exists (dirs: agent, components, documents, hooks, host, manuscript, onboarding, palette, panels, popout, statusbar).

### Q-37-SEED-CANON-VIOLATION-FIXTURE
ANSWER = (b), and it is not close: NO book qualifies today, and none can. Live query against loreweave_composition on infra-postgres-1: the full rule_violations predicate returns 0 rows; canon_rule holds 0 active rules across 0 projects; generation_job holds 0 rows with a non-null critic; outline_node holds 0 rows of kind='scene' (7 nodes, none a scene). There is no scene to hang a violation on and no canon rule in the entire DB. Do not spend time hunting for a fixture book — there isn't one.

THE UNLOCK (read this before building): a broken_canon_rule row is NOT computed by an engine at read time. It is read straight out of the generation_job.critic JSONB column (outline.py:1257), joined to the rule by plain text: `LEFT JOIN canon_rule cr ON cr.id::text = v.violation ->> 'rule_id'` (outline.py:1350). So the fixture is PURE SQL — deterministic, $0, and NO judge_prose/LLM run. Seeding the violation by actually running the critic would be both non-deterministic and paid; that flakiness is exactly what DoD-6's word "KNOWN-SEEDED" exists to exclude. Do not run the critic.

BUILDER INSTRUCTION — add `seedCanonViolation()` to frontend/tests/e2e/helpers/db.ts, directly beside the existing `seedPriorExtractionJob()` (db.ts:30), which is the identical precedent (shells `docker exec <PG_CONTAINER> psql` into the dev stack to seed rows the UI cannot create). Gate the spec on the existing `dbAvailable()` (db.ts:45) so it SKIPS, not fails, when the stack is down.

Seed a FRESH book per run (title e.g. "LW-E2E-ISSUES-FEED"), NOT a named permanent fixture. Rationale, and it is the repo's own lesson (`shared-dev-db-not-clean-fixture-e2e`): a shared book accumulates unrelated rows, and DoD-6 requires CLICKING the broken_canon_rule row specifically. A fresh book yields exactly one error row => the click target is unambiguous. A reused book makes that assertion race pre-existing data.

The rows, in order:
1. Book + project via the existing tests/e2e/helpers/api.ts (owned by claude-test@loreweave.dev).
2. Cast entity via the existing tests/e2e/helpers/glossary.ts — MINT IT, do not invent a UUID. entity_id is a glossary entity id; a fabricated UUID renders a nameless cast chip that the right-click lens smoke cannot target.
3. outline_node chapter: kind='chapter', book_id, project_id, NOT is_archived.
4. outline_node scene: kind='scene', chapter_id -> the chapter, NOT is_archived, AND pov_entity_id = <entityId>, present_entity_ids = ARRAY[<entityId>::uuid].
5. canon_rule: id = a FIXED uuid, project_id, book_id, created_by = test user, text = a real sentence, active = true, is_archived = false, entity_id = <entityId>.
6. generation_job: project_id, book_id, created_by, outline_node_id = <the scene id>, status='completed', operation='scene_prose' (ANY value except 'promoted_scene_prose' — that value is explicitly excluded by the query and would silently yield zero rows), critic = '{"violations":[{"rule_id":"<canon_rule uuid AS TEXT>","violated":true,"why":"...","span":"..."}]}'.

CRITICAL DETAIL: rule_id must be the canon_rule UUID rendered as a STRING (the join is `cr.id::text = ...`). Get it wrong and rule_text comes back NULL — the row still appears (the repo never drops unattributable findings, by design), so the smoke goes GREEN while the "focused rule is hoisted" assertion is vacuous. Assert rule_text is non-null in the seed helper itself.

SECOND HALF OF THE QUESTION — the cast entity with non-zero references is NOT a separate fixture. It falls out of the above for free: step 4 makes outline_present/scene_pov/scene_present non-zero and step 5 makes canon_rule non-zero => 3 of the 8 REFERENCE_SOURCES carry a non-zero exact count, which is precisely what DoD-6 asks ("all 8 source rows present and a non-zero exact count" — presence is a rendering guarantee, non-zero need only hold for one). The other 5 sources correctly render 0, and 0 != absent is the very distinction §4.2 protects. Optionally enrich structure_node.roster_bindings / motif_application / narrative_thread(opened_at_node) to light more sources, but it is NOT required to pass DoD-6.

Make the helper idempotent (fixed UUIDs + ON CONFLICT DO NOTHING, or delete-then-insert scoped to the seeded book) so a re-run does not double the rows and flip a count assertion.

PO VETO POINT (default I chose, so it can be overridden cheaply): fresh-book-per-run over a named permanent fixture book. If the PO would rather have one durable seeded demo book on the test account, the same helper serves — call it once from a seed script instead of from beforeAll — but then the "exactly one error row" assertion must relax to ">= 1 row whose kind is broken_canon_rule and whose rule_id equals the seeded uuid".

*Evidence:* services/composition-service/app/db/repositories/outline.py:1257 (rule_violations reads generation_job.critic JSONB — no engine at read time) and :1350 (`LEFT JOIN canon_rule cr ON cr.id::text = v.violation ->> 'rule_id'` — the rule_id must be UUID-as-text); services/composition-service/app/mcp/server.py:4044 (broken_canon_rule Diagnostic emission, severity from agent_native.py:66); services/composition-service/app/db/repositories/entity_references.py:60-118 (the 8 REFERENCE_SOURCES; _pov/_present key on outline_node.pov_entity_id / present_entity_ids); frontend/tests/e2e/helpers/db.ts:30 (seedPriorExtractionJob — the exact docker-exec-psql seeding precedent to copy) and :45 (dbAvailable gate). LIVE DB (docker exec infra-postgres-1 psql -U loreweave -d loreweave_composition): rule_violations predicate run book-wide => 0 rows; `SELECT count(*) FROM canon_rule WHERE active AND NOT is_archived` => 0 rules / 0 projects; `SELECT count(*) FROM generation_job WHERE critic IS NOT NULL AND critic <> 'null'::jsonb` => 0; `SELECT count(*) FILTER (WHERE kind='scene') FROM outline_node` => 0 of 7; generation_job by operation => plan_forge_propose(11), plan_pass(4) only.

## Not a question (already answered by code / a sealed decision)
- **Q-37-BE1-EXTRACT-NOT-FORK** — Not a question — it is a work item, and the code confirms the spec's instruction is correct as written and mechanically executable. Build it exactly as follows.

(1) `agent_native.py` ALREADY exists (215 lines) and already owns every type the fanout accumulates into — `Diagnostic`, `Diagnostics`, `SEVERITY`, `Block`, `resolve_scope`. Only `build_diagnostics` is missing. Add to `services/composition-service/app/services/agent_native.py`:

    async def build_diagnostics(pool, book_client, book_id: UUID, bearer: str, cap: int = 25) -> Diagnostics

(2) MOVE `services/composition-service/app/mcp/server.py:3961-4131` (from `pool = get_pool()` through the end of source-(5) coverage, i.e. everything above the `return` at :4132) into that function body VERBATIM, with exactly four substitutions:
    - `pool = get_pool()` → deleted (pool is now a param)
    - `_work, pid = await resolve_scope(WorksRepo(pool), bid)` → keep as-is; `resolve_scope` is already in this module (agent_native.py:190). Import `WorksRepo` function-locally.
    - `get_book_client()` (3 occurrences: sources 1, 4, 5) → the `book_client` param
    - `mint_service_bearer(tc.user_id, settings.jwt_secret)` (2 occurrences: source (4) prose-deleted at ~:4082 and source (5) coverage at ~:4108) → the `bearer` param
    - `bid` → `book_id`
  Return `diag` (the Diagnostics accumulator), NOT the dict. Ranking/capping stays the caller's job so BE-1a can widen the route payload without touching the tool.

(3) PRESERVE THE FUNCTION-LOCAL IMPORTS. server.py deliberately imports `get_book_client`, `compute_conformance_status`, `compute_coverage`, `compute_prose_deleted` INSIDE the function body, not at module scope; agent_native.py currently imports nothing from app.clients/app.engine/app.db. Keep them function-local inside `build_diagnostics`. Do NOT hoist them to module scope as a tidy-up — that is an import-cycle risk for a purely cosmetic gain.

(4) DEFENSIVE RE-CLAMP (my call — deviates slightly from the spec signature, veto if you disagree). The spec passes `cap` IN, which puts the clamp `max(1, min(int(limit or 25), 100))` (currently server.py:3966) in TWO callers — two clamps that drift is the identical bug class this item exists to kill. So make the FIRST line of `build_diagnostics` re-clamp: `cap = max(1, min(int(cap or 25), 100))`. Callers may still clamp; no caller can pass a bad cap.

(5) REWIRE BOTH CALLERS:
    - MCP tool `composition_diagnostics` (server.py:3950) becomes ~8 lines: `_ctx` → `_gate(tc, bid, GrantLevel.VIEW)` → `pool = get_pool()` → `diag = await build_diagnostics(pool, get_book_client(), bid, mint_service_bearer(tc.user_id, settings.jwt_secret), limit)` → `return {"book_id": str(bid), **diag.ranked(cap=cap)}`. Behaviour must be byte-identical.
    - The new BE-1 route calls the SAME `build_diagnostics` and does its own `.ranked()` + BE-1a payload widening.

(6) NO SECOND FANOUT EXISTS TODAY — verified. `grep -rn "canon_issues|rule_violations|compute_prose_deleted|compute_conformance_status" services/composition-service/app/routers/ app/services/` returns only single-source owners (routers/outline.py:522,546; routers/conformance.py:453), never the composed 5-source rollup. So this is extract-BEFORE-adding-the-route: the css-var duplication is PREVENTABLE, not yet present. Do the extraction in the same slice that adds the route, never after.

DoD-1 grep (run at wave close, paste output into the transcript): `grep -rn "SEVERITY\[" services/composition-service/app/ --include=*.py` must return hits ONLY in `services/agent_native.py`. Zero hits in `mcp/server.py` and zero in `routers/` proves the fanout has exactly one home. Plus: `tests/unit/test_agent_native.py` already exists — add a test that calls `build_diagnostics` directly with a stub book_client and asserts a degraded source yields a `warnings` entry and OMITS the key rather than emitting `0` (absent != zero, the module's stated second law).
- **Q-37-403-404-UNIFORM** — This is a work item whose contract is ALREADY fully determined by shipped code — there is nothing to decide, only to copy. `authorize_book()` (services/composition-service/app/grant_deps.py:42-57) already raises `OwnershipError` on `GrantLevel.NONE` (line 50) and `InsufficientGrant` when `not lvl.at_least(need)` (line 52), and every composition router already maps them 404 / 403. The SDK is fail-closed: `GrantClient.resolve_access` returns `(NONE, "")` on a book-service outage (sdks/python/loreweave_grants/__init__.py:117-130), so an outage degrades to 404, not a leak — no extra BookClientError branch is needed at the gate. A collaborator with VIEW passes because `VIEW.at_least(VIEW)` is true; VIEW is the floor.

BUILDER INSTRUCTION (BE-1, M1) — do exactly this, no invention:
1. New file `services/composition-service/app/routers/diagnostics.py`, `router = APIRouter(prefix="/v1/composition")`, route `@router.get("/books/{book_id}/diagnostics")`. Params: `book_id: UUID` (path), `limit: Annotated[int, Query(ge=1, le=100)] = 25`, `severity: Literal["error","warn","info"] | None = None`, `kind: Literal[<the 8 SEVERITY keys>] | None = None`, `user_id: UUID = Depends(get_current_user)`, `grant: GrantClient = Depends(get_grant_client_dep)`.
2. FIRST statement of the handler body — before ANY repo/pool call — copy the `_gate_book` helper verbatim from `services/composition-service/app/routers/canon.py:70-78`:
   `try: await authorize_book(grant, book_id, user_id, GrantLevel.VIEW)` / `except OwnershipError: raise HTTPException(status_code=404, detail="book not found")` / `except InsufficientGrant: raise HTTPException(status_code=403, detail="insufficient access")`.
   Use detail `"book not found"` (the book-scoped wording used at grounding.py:115), NOT `"work not found"` (that string is for project-scoped routes). Gate on the PATH `book_id` — never on a book_id derived from a repo row, and never call `resolve_scope`/`WorksRepo` before the gate (that would make a bookless/absent book distinguishable = the enumeration oracle H13 forbids).
3. AFTER the gate, call the extracted `build_diagnostics(...)` (the BE-1a extraction of mcp/server.py:3950-4132). Keep its per-source `try/except → diag.warnings.append(...)` behavior intact: a degraded source is a `warnings[]` entry + an OMITTED count key, never a 500 and never `0`. Clamp `limit` ONCE (mirror server.py:3966 `cap = max(1, min(int(limit or 25), 100))`) — but since FastAPI already validates `ge=1, le=100`, an out-of-range value is a 422 at the boundary; keep the clamp anyway as defense-in-depth.
4. Mount it in `services/composition-service/app/main.py` next to the other read routers (after line 244, e.g. `app.include_router(diagnostics.router)  # 37 BE-1 — issues feed`). A router that is written but not included is the "built but unreachable" bug class this repo has already shipped once.
5. Tests (add to `services/composition-service/tests/unit/`, mirroring `tests/unit/test_grant_gate.py`): (a) no grant ⇒ 404 with body `{"detail":"book not found"}`; (b) grant below VIEW ⇒ 403 `insufficient access`; (c) collaborator with VIEW ⇒ 200 and sees the owner's issues; (d) book-service down (GrantClient raising/timing out) ⇒ 404, asserting the 404 body is BYTE-IDENTICAL to the no-such-book 404 (that identity IS the anti-oracle assertion — assert it, don't just assume it); (e) the gate is called BEFORE the repo: assert the works/pool repo mock recorded ZERO calls on the 404 and 403 paths.
Do not add a 401/500 branch of your own — `get_current_user` already yields 401, and a source failure is a warning, not a 500.

Default noted for PO veto: an unreachable book-service surfaces as 404 (fail-closed), matching every existing composition router, rather than 502. If the PO prefers a 502 there it is a one-line change — but it re-opens the oracle question, so the sane default is uniformity with the rest of the service.
- **Q-37-NO-PANEL-ID-ISSUES** — The constraint is already true and already machine-enforced — there is nothing to decide, only a null action to obey and a proof to run. BUILDER INSTRUCTION (M1/M2 of spec 37): (1) Do NOT touch services/chat-service/app/services/frontend_tools.py at all in this wave — no new panel_id enum member, no "issues" pseudo-id, no CLOSED_SET_ARGS entry. (2) Do NOT add a row to frontend/src/features/studio/panels/catalog.ts's STUDIO_PANELS. The Issues feed ships as a TAB inside the existing non-dockview StudioBottomPanel (new files: components/bottom/IssuesTab.tsx, JobsTab.tsx, GenerationTab.tsx, hooks/useDiagnostics.ts) — it is not a dock panel and must never be advertised as one. (3) Do NOT regenerate the contract: do NOT run `WRITE_FRONTEND_CONTRACT=1 pytest` in this wave; contracts/frontend-tools.contract.json must not be written at all. (4) DoD-5 proof, run literally at wave close and paste the output: `git diff --exit-code -- contracts/frontend-tools.contract.json` (must exit 0) AND `cd frontend && npx vitest run src/features/studio/panels/__tests__/panelCatalogContract.test.ts` (4 tests green — its "advertised set == palette-openable set" assertion IS the 57==57==57 check). If the agent needs to surface the feed to a human, it uses the existing composition_diagnostics tool and STATES the findings — a `ui_toggle_bottom_panel {tab: enum}` affordance is a separate frontend-tool-contract change already deferred to X-5/X-12 (spec 37 OQ-1, gate #1), and must not be smuggled into this wave. Rationale grounded in code: ui_open_studio_panel resolves through dockview via STUDIO_PANEL_COMPONENTS, which physically cannot mount the bottom panel, so an "issues" enum member would be exactly the silent-no-op class the Frontend-Tool Contract exists to kill.
- **Q-37-BE1D-ENTITY-REFS-ROUTE** — NOT A QUESTION — spec 37 §5.2 already SEALED the only real choice ("REST, not mcpBridge — recorded so it is not re-litigated", 37_issues_feed.md:486), nothing in plan 30 §0 PO-1..4 disturbs it, and the engine (EntityReferencesRepo) is already on disk. BE-1d is a WORK ITEM, size S. Build it in M2 exactly as follows.

(1) EXTRACT the fan-out — do NOT write a second copy. The loop the route needs already lives inside the MCP tool at mcp/server.py:3892-3931. Move it into services/agent_native.py (where REFERENCE_SOURCES already lives) as:
    async def find_entity_references(pool, *, book_id: UUID, entity_id: UUID, sources: tuple[str, ...] | None, limit: int) -> dict
  Body = the current tool body from `want = tuple(sources) if sources else REFERENCE_SOURCES` through the final return: cap = max(1, min(int(limit or 20), 100)); per-source try/except that on failure emits {"error": "this source could not be read"} and CONTINUES (never {"count": 0}); on success {"count": <exact>, "refs": [...], "has_more": count > len(refs)}; return {"book_id","entity_id","sources",_meta}. Then rewrite mcp/server.py:3892-3931 to call it, so tool and route return ONE byte-identical shape (one name, one concept — no drift lock needed because there is only one producer).

(2) NEW FILE services/composition-service/app/routers/entity_references.py. Do NOT touch routers/references.py — it is the author's research reference shelf (LOOM T3.6) and it mounts on the SAME prefix (references.py:46), which is exactly why the new route is book-scoped and named entity-references. Copy the read pattern verbatim from routers/conformance.py:424-455:
    router = APIRouter(prefix="/v1/composition")
    @router.get("/books/{book_id}/entity-references")
    async def read_entity_references(
        book_id: UUID,
        entity_id: UUID = Query(...),
        sources: list[ReferenceSource] | None = Query(None),   # Literal from agent_native.py:43 → FastAPI 422s a typo. THIS is §5.2's "validated as an enum on the route".
        limit: int = Query(20, ge=1, le=100),
        user_id: UUID = Depends(get_current_user),
        grant: GrantClient = Depends(get_grant_client_dep),
    ) -> dict[str, Any]:
        try: await authorize_book(grant, book_id, user_id, GrantLevel.VIEW)
        except OwnershipError: raise HTTPException(404, "book not found")
        except InsufficientGrant: raise HTTPException(403, "insufficient access")
        return await find_entity_references(get_pool(), book_id=book_id, entity_id=entity_id, sources=tuple(sources) if sources else None, limit=limit)
  VIEW gate only (it is a free read — no spend, no propose→confirm). H13-uniform 404/403. NO project_id anywhere: all 8 sources are book-scoped (entity_references.py:41-48 explains why threading one through was an active bug).

(3) REGISTER in app/main.py next to line 225: `app.include_router(entity_references.router)  # 37 BE-1d — entity backlinks lens`. Gateway needs ZERO work — gateway-setup.ts:354 pathFilter is a generic /v1/composition prefix match.

(4) NEVER swallow the ValueError into a zero. EntityReferencesRepo.find raises on an unknown source ON PURPOSE (entity_references.py:64-69): a silent (0, []) reads as "this entity is used nowhere", and the agent's next move on that answer is to delete something. The Literal enum makes a bad `sources` a 422 before the repo is ever reached; the per-source except in the shared helper is for a DB/source failure and must render "could not be read", never 0.

(5) TEST — tests/unit/test_entity_references_route.py, all five asserted:
  a. sources omitted ⇒ response["sources"] has all 8 REFERENCE_SOURCES keys (the guard against re-collapsing the pov/present pair — same assertion §5 M2 demands of the lens);
  b. sources=["outline"] (a plausible typo) ⇒ 422, NOT 200-with-zeros;
  c. one source's repo call raising ⇒ that key is {"error": ...} and the other seven still answer;
  d. count stays EXACT while refs are capped at limit, and has_more is True;
  e. foreign book ⇒ 404, VIEW-less viewer ⇒ 403.
  Plus one test asserting the MCP tool and the route return the identical dict for the same args (proves the extraction in step 1 did not fork).

Default I am picking on the PO's behalf (veto-able): the route returns the tool's dict verbatim, `_meta` note included. FE ignores it; keeping the shapes byte-identical is worth more than a two-key diet.
- **Q-37-AN12-AMENDMENT-LOCATION** — VERIFIED — candidate (a): the amendment ALREADY EXISTS in spec 28 and is already committed. Spec 37's status block is telling the truth; DoD-7 is satisfied at build time. NOTHING TO AUTHOR.

Evidence: `docs/specs/2026-07-01-writing-studio/28_agent_native_studio.md:217` opens `## AN-12 AMENDED (PO-1, 2026-07-12)`, running :217-283. It is substantive, not a stub: it states what changed (the "No new GUI surface" clause LIFTED for `composition_diagnostics` + `composition_find_references` only), cites its authority (plan 30 §0 PO-1, sealed 2026-07-12), proves AN-12's premise false with a per-kind human-surface table at HEAD 9262ed53e, enumerates the 5 clauses that STILL BIND (no new dock panel / zero catalog rows / zero panel_id enum change; ships into the EXISTING StudioBottomPanel Issues tab; find_references is a LENS not a panel; the feed ROUTES, never EDITS; `composition_package_tree` gets NO human surface — conscious won't-fix), and restates the lifted clause verbatim as strikethrough → amended text.

It is COMMITTED: `git show HEAD:...28_agent_native_studio.md | grep "AN-12 AMENDED"` → hit at line 217 (commit d0f17555e, "docs(studio): tool<->GUI gap audit + master plan (30) + wave specs 31-38"). `git status --short` on specs 28/30/37 → clean. So DoD-7's "the AN-12 amendment is committed IN SPEC 28, not here" is met by an already-landed commit, and spec 37 does NOT rest on an unwritten PO-1.

BUILDER INSTRUCTION (2 steps, both cheap):

1. At Wave 7 close-out, tick DoD-7 with this one-command proof (do not re-author anything):
   `git show HEAD:docs/specs/2026-07-01-writing-studio/28_agent_native_studio.md | grep -n "AN-12 AMENDED"`
   Expect: `217:## AN-12 AMENDED (PO-1, 2026-07-12)`. Paste that output as the DoD-7 evidence string.

2. FIX-NOW (a real trap, ~4 lines of doc edit, do it in the Wave-7 docs commit): the label "AN-12" now names TWO different artifacts, and a close-out grep for "AN-12" surfaces both — which will make a builder conclude DoD-7 is unmet when it is met.
   - (i) the AMENDMENT — exists, 28:217. This is what DoD-7 means.
   - (ii) an UNWRITTEN "AN-12 section defining `resource_ref`" promised by 28 OQ-8 (`28_agent_native_studio.md:615`), demanded by plan 30 X-6 (`30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md:339` and `:346` — "an AN-12 section INSIDE 28"), and queued at `00C_POST_ARCHITECTURE_QUEUE.md:46`. That one is gated on spec 24 Phase 4, is required by nothing in v1 (P-13 made "Ask AI" = Compose chat with a selection ref), and is NOT part of spec 37's DoD-7.
   Rename (ii) to a free row id — **AN-14** — in exactly these 4 places, changing only the row label, not the content:
     - `28_agent_native_studio.md:615` — "this spec gains an AN-12 section defining `resource_ref`" → "gains an **AN-14** section…"
     - `30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md:339` (X-6 row) and `:346` ("Specs to write: an AN-12 section inside 28") → AN-14
     - `30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md:337`-ish X-6 title line "Write spec 28's AN-12 `resource_ref` section" → AN-14
     - `00C_POST_ARCHITECTURE_QUEUE.md:46` — "AN-12 `resource_ref`" → "AN-14 `resource_ref`"
     - `32_arc_inspector.md:405` — "X-6 / spec 28 AN-12 / OQ-8" → "X-6 / spec 28 AN-14 / OQ-8"
   AN-13 is taken (28:197, cascade-rename won't-fix); AN-14 is free. Do NOT touch the AN-12 AMENDED section itself, and do NOT delete AN-12's original row at 28:196 — the amendment explicitly says "read them together; do not reconcile one against the other by deleting either."

Scope note for the builder: X-6 / `resource_ref` (soon AN-14) remains OUT of Wave 7. It is Wave-0-gate work for spec 24 Phase 4 and gates nothing in spec 37. Do not pull it in.

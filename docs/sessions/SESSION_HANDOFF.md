# ▶▶ NEXT SESSION STARTS HERE

## 🔁 S-12 WORKFLOWS + WORKFLOW-PROPOSALS GUI (G-WORKFLOWS) — **SHIPPED (2026-07-18)**
> Spec: [`docs/specs/2026-07-17-studio-completeness-build/S-12_workflows.md`](../specs/2026-07-17-studio-completeness-build/S-12_workflows.md) ·
> RUN-STATE: [`docs/plans/2026-07-18-S12-workflows-gui-RUN-STATE.md`](../plans/2026-07-18-S12-workflows-gui-RUN-STATE.md).
> Closed the "an agent proposes a workflow (registry_propose_workflow) that no human can approve — there's no UI"
> hole. **Investigation corrected 2 stale spec claims:** (a) the spec's "zero FE" was wrong — a read-only
> `WorkflowRack` + a working `modeBindings` UI already existed, but ONLY on the `/extensions` route (not the
> studio dock / panel enum); (b) mirroring `setSkillEnabled` REQUIRED a **new `workflow_enablement` table** the
> spec didn't spell out. **Built (4 slices, each review-impl + QC):**
> - **BE (4ca23a644):** `workflow_enablement` migration + `GET/DELETE /v1/agent-registry/workflows/{id}` +
>   `PUT .../{id}/enablement` (mirror skills); list exposes workflow_id + effective enabled. 8 pgxmock tests.
>   **SD-1:** enablement is a PER-USER override (safe for System too — a preference, not a shared-row write; the
>   System guard is on DELETE). review-impl fixed getWorkflow book READ requiring ≥edit → ≥view.
> - **FE panels (821fbe99f):** `workflows` (manage: per-user toggle + delete-own; System read-only) +
>   `workflow-proposals` (approve mints the workflow / reject) studio panels — GG-8 (catalog + chat-service
>   panel_id enum +2 + contract regen + i18n×17). 8 view tests + panelCatalogContract 9/9.
> - **FE setting (9e3d5c050):** `workflow-bindings` settings tab (mode→workflow auto-inject) — lands on both
>   /settings + studio dock via the one registry; settingsTabParity 9/9.
> **Debt:** D-S12-LIVE-SMOKE (agent-loop E2E needs live stack+browser — each link proven in isolation);
> D-S12-BINDINGS-I18N (BindingSettings hardcodes English, pre-existing). MCP delete/enablement tools = conscious
> defer (agents propose, humans dispose).

## 📜 GLOSSARY CONTRACT-FIRST — P1–P4 COMPLETE, contract now 100% + CI-enforced **SHIPPED (2026-07-18)**
> Spec: [`docs/specs/2026-07-18-glossary-contract-first-restoration.md`](../specs/2026-07-18-glossary-contract-first-restoration.md) ·
> RUN-STATE: [`docs/plans/2026-07-18-glossary-contract-first-RUN-STATE.md`](../plans/2026-07-18-glossary-contract-first-RUN-STATE.md).
> The glossary OpenAPI contract was ~20% documented (149 public /v1 routes / ~30 documented), stale, unenforced.
> **All 4 slices shipped:**
> - **P1 (35aea0555)** — `TestOpenAPIRouteConformance`: `chi.Walk`s the real router (no-DB `NewServer(nil,cfg)`),
>   line-scans the contract YAMLs' `paths:` block (a strict parse chokes on unquoted colons in prose), reds on
>   undocumented `/v1` route OR phantom documented-but-unrouted path. `/v1`-prefix scope, param-name-agnostic
>   normalize, honest regen'd allowlist. **SD-8 earned its keep day one:** 6 `/v1/canon/*` phantoms (L5.F canon
>   RPC — unbuilt sub-program) → named honest exemption. review-impl fixed a silent-revert (`# permanent:` clobber).
> - **P2 (6ab344a6d)** — `entities.yaml`: 30 entity-family routes (CRUD, attr-value add/PATCH/delete, translations/
>   evidences/items, chapter-links, revisions, merge/reassign/pin, bulk). review-impl fixed a fabricated `relevance` enum.
> - **P3 (a few commits)** — 5 YAMLs (actions, system-admin, user-kinds, wiki×25, book-ops×26) = 83 routes.
>   **Allowlist drained 113→0 — every public /v1 route documented (~20%→100% path+method).** review-impl fixed
>   a 2nd fabricated enum (wiki review body). 0 phantoms across all 113 (no typos).
> - **P4** — allowlist 0 ⇒ gate strict; dedicated `-count=1` step in `foundation-ci.yml` (cache-proof); named in
>   `CLAUDE.md`'s contract-first rule. **Contract-first is now LIVED for glossary.**
> Scope was path+method (SD-7); full request/response **schema** conformance = optional P5. Follow-ups (RUN-STATE):
> canon RPC YAML relocation + its one-char parse fix (L5.F track owns).

## ♻️ S-08 SOFT-ARCHIVE RESTORE (motif + arc-template) — **SHIPPED (2026-07-18)**
> Spec: [`docs/specs/2026-07-17-studio-completeness-build/S-08_soft-archive-restore.md`](../specs/2026-07-17-studio-completeness-build/S-08_soft-archive-restore.md) §8–9.
> **Investigation correction (verified vs code):** the spec's "dead-end soft-delete, no transport to
> un-archive" was FALSE at the API layer — `patch(status='active')` already un-archives (both patch-args
> carry `status`, no `status<>'archived'` guard). The real gap: no dedicated idempotent restore verb, no FE
> affordance, and archive's MCP `undo_hint` was `None`. **Built:** `MotifRepo.restore`/`restore_shared` +
> `ArcTemplateRepo.restore(book_id)`; routes `POST …/{id}/restore[?book_id=]`; MCP
> `composition_motif_restore` + `composition_arc_template_restore`; archive tools' undo_hint now points at
> restore. FE: arc-templates **Archived tab + Restore** (`useArcTemplates` archived tier + `arcApi.restore`/
> `motifApi.restore`). Commits `fa79e0963` (BE), `005cf6545` (FE), `cf46d4a0f` (spec). **VERIFY:** repo DB
> round-trip on real PG (id+version preserved, foreign/wrong-book/not-archived→None, shared tier) + router
> 404/owner/shared + MCP tool-list parity/tier-gate/functional = **220 passed**; FE panel 10/10, tsc 0;
> provider-gate clean. Container rebuild-smoke skipped (shared stack in active concurrent use; single-service
> change → real-PG + real-MCP-loopback + TestClient cover the path).
> **`/review-impl` + completeness pass (2026-07-18):** standards COMPLIANT (tenancy scope keys + EDIT-gate,
> 404 anti-oracle, MCP-first), no HIGH. Fixed MED-1 (restore shared-tier EDIT-gate DENY tests — route 403 +
> MCP H13, commit `51f742a70`) + MED-2 (`composition_arc_template_restore` functional test). **Recently
> cleared: `D-S08-FE-MOTIF-ARCHIVED-VIEW`** (commit `6e60be1b0`) — the motif library gained an **Archived
> scope tab** + **Restore** on archived cards (mirrors the `drafts` scope; `useMotifDraftActions.restore`).
> 200 composition-FE tests green, tsc 0. **No open S-08 defers.** (LOW-2 accepted: the FE archived views are
> owner-only; book-shared restore is REST/MCP-only, a conscious follow-up.)

## 🪟 STUDIO DOCK UX — resizable side bar + panel-layout presets — **SHIPPED (2026-07-18)**
> Plan: [`docs/plans/2026-07-18-studio-dock-resizable-sidebar-and-layout-presets.md`](../plans/2026-07-18-studio-dock-resizable-sidebar-and-layout-presets.md). FE-only (no backend).
> The manuscript side bar is now width-resizable like a dock panel (drag sash, dbl-click reset, per-book
> localStorage), and a `LayoutGrid` top-bar icon opens a VS Code-style preset menu (1/2/3/4/6/8 columns +
> 2×2/3×2/4×2 grids) that reflows the open dock panels via `host.applyDockLayout` — the missing UI for
> ultrawide screens (dockview always supported unlimited splits). Commits: `bd6d2a02b` (resize), `18daacf26`
> (reflow util), S3 (picker+icon+seam), `0fcb4e5e0` (live-smoke bug fix: reflow self-moved a sole-occupant
> panel into its own group → dockview emptied the dock; fixed by skipping already-placed panels). Live-smoked
> on :5199 (resize persist, cols2 split, single merge-back, cols8 too-narrow gating). 51 unit tests + full
> studio vitest 1389 green; tsc 0.
> **Deferred (1, tracked): `D-STUDIO-DOCK-I18N-CONVERGE`** — the 15 new `manuscript`/`layout`/`sidebar.resize`
> studio keys are seeded in en + translated in the working tree (17 locales, gemma-4-26b) but the COMMIT is
> deferred: en/studio.json was under LIVE concurrent edit by a plan-hub session (adding reference-shelf/adv
> keys), and the i18n parity gate (working-tree-en as source) would force co-carrying their moving,
> half-finished keys or risk clobbering their edits. Keys render via English `defaultValue` meanwhile; land at
> convergence (S-02 i18n precedent). Trigger: when en/studio.json churn settles, commit the 18 studio.json.

## 🏗️ STUDIO COMPLETENESS — audited, specced, SEALED → **BUILD NEXT** (2026-07-17)
> **Read first:** [`docs/specs/2026-07-17-studio-completeness-build/00_ROADMAP.md`](../specs/2026-07-17-studio-completeness-build/00_ROADMAP.md)
> + [`01_DECISIONS.md`](../specs/2026-07-17-studio-completeness-build/01_DECISIONS.md) (sealed) ·
> **Audit:** [`docs/plans/2026-07-17-studio-completeness-AUDIT.md`](../plans/2026-07-17-studio-completeness-AUDIT.md).
>
> A 6-round audit (parity + **CRUD-completeness**) found the real work is **not porting legacy** — the legacy
> is itself incomplete, so several domains are missing a verb **at the data layer**. **12 detail specs
> (S-01..S-12) written + CLARIFY-sealed**, 3 HTML drafts for the net-new surfaces. All decisions in
> `01_DECISIONS.md`; **nothing parked** (G-WORKFLOWS sealed to this track = S-12).
>
> **BUILD ORDER (PO: fanout, Tier-A parallel):** the four Tier-A DATA-layer specs go first, in parallel
> (disjoint services):
> - **S-01** structure-template authoring — composition
> - **S-02** manuscript parts (acts/volumes) — book-service (Go)
> - **S-03** references UPDATE — composition
> - **S-04** derivative delta editing — composition
>
> Then Tier-B (S-05 fact+triage · S-06 attr-value · S-07 world OCC · S-08 restores · S-09 wire-ups · S-11
> search · S-12 workflows) and Tier-C (S-10 FE orphans + `[[`-create). Each build: full workflow, VERIFY
> evidence, 2-stage review, `/review-impl` for the tenancy/data specs, live-smoke where it crosses services.
> **Same-folder multi-session rules apply** (never `git add -A`; commit only your own files; scoped tests
> during BUILD; the studio registry — catalog.ts/enum/contract — is convergence-node work).

## 🔧 BUILD FIXED + repo-wide TEST SWEEP — **DONE, 2026-07-17** (HEAD `4ea141e9e`)
>
> ### `docker compose build` was BROKEN — fixed at root cause (`b74a48793`)
> Reproduced first: `docker compose build` → **EXIT 1**, `target learning-service: failed to solve`.
> **Root cause (a single-service build HIDES it):** compose builds ~33 images **concurrently** ⇒ ~33 pip
> processes hit PyPI at once ⇒ the CDN returns **truncated bodies**. Building one service alone succeeds
> every time. The network is **FLAKY UNDER CONCURRENCY, not blocked** (an early read of mine said
> "blocked" — wrong; and there is no IPv6 route here at all, so that theory was wrong too).
> **Why pip's own `--retries` can't save it:** pip retries a *failed connection* (the log shows
> `Retrying (Retry(total=4…))` recovering fine), but a **truncated body under HTTP 200** is not a failure
> to pip — it parses the short JSON index and dies with `JSONDecodeError`, instantly, no retry. **Fix:** an
> outer retry loop around all 24 pip RUNs in 11 Dockerfiles (any non-zero exit is retryable; still fails
> hard after 5 so it never masks a real error). **Proof — same network, same 33-way storm:** network errors
> still occurred **25×**, the retry fired **12×**, `failed to solve` **0**, **33/33 images Built, EXIT 0**,
> on the **default PyPI**. `345055b4b` also adds an opt-in `ARG PIP_INDEX_URL` (defaults to PyPI — CI/prod
> byte-identical) as an escape hatch for an unusable index; it is **not** the flaky-network fix.
> **PO question settled with evidence:** there is **no library to remove or rewrite** — zero CN packages in
> any requirements; the same `/sdk` installs cleanly (50+ deps) with only the index host changed; and a
> mirror wheel hashed **byte-identical** to PyPI's own published sha256.
>
> ### Repo-wide sweep — EVERY suite green, 15 reds cleared (`bf29e70b5`, `4ea141e9e`)
> | | result |
> |---|---|
> | **Python** 14 svcs | **12 reds → fixed.** chat 1708 · composition 2289 · knowledge 4009 · worker-ai 474 · translation 1053 · lore-enrichment 965 · campaign 183 · learning 195 · jobs 97 · video-gen 58 |
> | **Go** 28 svcs | 28/28 ok, no reds |
> | **Rust** | tilemap 518 · world 134 · roleplay 9 · travel 0 (genuinely has no tests) |
> | **Node** | api-gateway-bff **201** (was 188 + 2 dead suites) · ai-gateway 206 · mcp-public-gateway 264 · game-server 40 · knowledge-gateway 19 |
> | **Frontends** | frontend 5739 · frontend-game 155 · cms-frontend 41 |
>
> **Two finds worth carrying forward:**
> - **A REAL bug:** `kg_create_node.kind` advertised **no enum** — S7's 5-kind closed set lived only in the
>   bespoke schema, while the **FastMCP signature** (the one actually advertised as `inputSchema`) typed it
>   `str` with the set in *prose*. The `panel_id:"editor"` silent-no-op class. Fixed at the SSOT:
>   `AUTHORABLE_KINDS` now derives from an `AuthorableKind` Literal that the signature reuses.
> - **api-gateway-bff's green was LYING:** "188 passed" while health.spec + proxy-routing.spec **never ran**
>   (a required `agentRegistryUrl` was added; the fixtures weren't → TS2345 killed both suites before their
>   first test). 13 tests had silently stopped executing.
>
> **Gotchas for the next sweeper** (both bit me):
> - `cargo` prints one `test result:` line **per target** — reading only the last reports an empty doc-test
>   as the total (my first pass claimed world-service had 0 tests; it has 134). **Aggregate them.**
> - **Never run a whole suite while other suites/builds run** — CPU contention false-REDs any wall-clock
>   assertion (it red `test_intent_classifier` once; `874713245` converted that one to a scaling ratio).
> - `frontend-game` + `packages/*` are **pnpm** (`pnpm-workspace.yaml`); `frontend/` is **intentionally npm**.
>   `npm install` in frontend-game breaks node_modules — use `pnpm install --filter frontend-game...`.
> - `cms-frontend` + `knowledge-gateway` ship **no node_modules** — their suites (41 / 19) run only after an
>   install, so nobody had been running them.

## 🧹 RECONCILE of the 8-session fan-out — **DONE, 2026-07-17** (HEAD `e72d712c1`)
> The shared checkout is **reconciled: `git ls-files --others` empty, and the only file left dirty is
> `docs/ARCHITECTURE.md`** — it was still being written *while this reconcile ran* (mtime landed mid-commit;
> confirmed settled, not abandoned), so by PO decision it stays with its owning session to commit. Its numbers
> were spot-checked as correct in passing (52 language-rule rows = 47 mapped + 5 `missing`; 47 service dirs on
> disk; 3 SPAs). **Do not treat it as junk.** 75 modified + 12 untracked files triaged into 5 commits. **The tree is green: frontend 785 files / 5739 tests · knowledge
> tests/unit 3891 (`-n auto --dist loadgroup`) · tsc EXIT 0 · i18n-completeness / ai-provider / knowledge-access
> gates all OK.**
>
> **⚠️ The headline finding: HEAD itself was RED in 3 places.** Three sessions committed production code and
> left the test asserting it dirty in the worktree — the exact shared-index hazard S8's caveat flags below.
> Each was proven by checking the HEAD test out against the committed source before repairing (`669e989df`):
> - `test_migrate_ddl` — WS-5.7's `'commitment'` fact_type shipped in migrate.py/models.py, the 6-value CHECK
>   assertion did not. · `SceneInspectorPanel` — 7/8 red; the inspector gained `SceneMotifsSection` (query hooks).
> - `PolishPanel` — the M3 apply-seam added the OCC `draftVersion` to the hook's return; the test's fake hook
>   state never grew it. Now asserts BOTH args, so **the OCC version threading is genuinely tested**, not just
>   un-red. The component was right all along — the mock had drifted from the hook it stands in for.
>
> **Other work:** `874713245` intent-classifier's absolute `<15ms` wall-clock budget → a **scaling-ratio**
> assertion (it false-red only because this session ran vitest+tsc concurrently; measured real 1.97x vs a
> quadratic stand-in 3.85x, so the new gate has teeth) · `807593510` **the convergence i18n translate-pass —
> 17 locales × 33 namespaces at full `en` parity** (this clears every session's deferred i18n row, incl. S7's)
> · `14bdaa1c1` plan links broken by the W0-S10 spec renumber (14→14a/14b, 15→15a/15b) · `e72d712c1` gitignore:
> `frontend/s8-journey/` never matched (nested patterns are relative to their own dir) + root `/*.png` +
> `test-results/`. Smoke screenshots are **ignored, not deleted** — the RUN-STATE docs cite them and every one
> is reproducible by re-running its spec.
>
> **▶ STILL OPEN — convergence node §6** (needs all 8 tracks, not any one session): loop-③ Studio-only smoke ·
> GG-4 retire `ChapterEditorPage` · rebuild+redeploy the baked images (dev is verified; **prod is not**, and
> stale images give false-greens — see the `live-smoke-rebuild-stale-images-first` lesson).

## ⭐ Track: STUDIO-S8 TRANSLATION (spec 29) — **CLOSED, 2026-07-17**
> **RUN-STATE (authoritative):** [`docs/plans/2026-07-16-studio-session-S8-RUN-STATE.md`](../plans/2026-07-16-studio-session-S8-RUN-STATE.md)
> **Spec:** [`docs/specs/2026-07-01-writing-studio/29_translation_repair.md`](../specs/2026-07-01-writing-studio/29_translation_repair.md)
>
> Full spec-29 repair shipped (T1–T10, S1–S12, D1–D13): matrix operable (header CTA, one-row-per-chapter,
> pagination, orphan footnote), no-silent-fail typed errors + Retry everywhere, the **content-language SSOT**
> (`contracts/languages.contract.json` + Python mirror + parity tests + write-validation at every writer +
> MCP enum), and the grant-gate. **D-TRANSL-LANG-BACKFILL EXECUTED** (Vietnamese→vi merged, 0 remaining).
> Cold-start audit → 5 fixes. **Closure gates green: FE 150 vitest · BE 1053 pytest.** Live-smoke both
> states + 5 Playwright e2e + a blackbox author journey (verdict: usable). All DEBT/PARKED cleared.
> **Caveat:** several S8 commits were absorbed into a concurrent session's commit via the shared index
> (code verified in HEAD, just misattributed — see RUN-STATE DRIFT). Nothing open for S8.
> **NOT S8's — convergence node §6 (after all 8 sessions close):** loop-③ Studio-only smoke + GG-4 retire `ChapterEditorPage`.

## ⭐ Track: AGENT-TASK-GOVERNANCE + close-21-28 — **CLOSED TO EVIDENCE, 2026-07-16** (HEAD `7e44b296e`)
> **Spec (SEALED):** [`docs/specs/2026-07-15-agent-task-governance.md`](../specs/2026-07-15-agent-task-governance.md) ·
> **Plan + RUN-STATE:** [`docs/plans/2026-07-13-close-21-28-plan.md`](../plans/2026-07-13-close-21-28-plan.md) (§9 = the live registers).
> Governance was folded into the close-21-28 plan as **Phase G** (Governance-P5 = Phase 4's S06 replay).
>
> **DONE + committed:** G0 `d27962e0e` (trustworthy `structure`/`structure_fresh` effect + `book-state-keys.contract.json`) ·
> G1 `3237e2b79` (DRIVE the rail: `compile-plan` step + enforce/hold/honest-giveup/escape-hatch) ·
> G2 `fe4af551b` (enforcement strength+N as deploy config; per-user SET-1 deferred D-G2-SETUSER) ·
> **G5 `f1bb78308` — S06 FLAGSHIP GREEN in-container on local gemma-4** (`structure_node=1`, compile-attributed,
> `plan_compile ok=true`; the rail DROVE propose→compile). **B4 resolved** (generate is gated, not a bug).
> **Key finding:** the governance drives correctly; the last blocker was PlanForge rules-mode needing a
> NUMBERED `# 1. Arc Overview` header (see the memory + plan §9.1 D-G5-NUMBERED-HEADER).
>
> **▶ STATUS: CLOSED TO EVIDENCE (2026-07-16).** Every DoD slice marked [x] with pasted evidence.
> Committed: **Phase G COMPLETE (G0–G5)** · **B4** (generate gated) · **Phase 2 T5/T6** · **Phase 5
> D3/D4/D5/F3** · **Phase 2b O-1/O-2/O-3** · **G3/G4** · **Phase 6 C0–C5** · **O-11** `e3023c775` (what-if
> branch producer → thin studio panel + LIVE browser smoke of the port: palette-discoverable, opens, mounts,
> renders) · **Phase 3 H8.1** `7b52ebc24` (10k fixture + EXPLAIN keyset — **caught+fixed an O(offset)
> deep-page bug**: OR-form keyset was a Filter; row-constructor `(rank,id)>(x,y)` pushes into the Index Cond →
> page-50 179 buf→6 buf) · **Phase 3 H8.2** `7e44b296e` (FULL live trusted-CDP-mouse drag: staged plan-hub
> graph on real book 019f6571, dragged Chapter 1 across lanes, DB `structure_node_id` …a1→…a2 before/after,
> badge source 4/0→3/1) · **F2 ◐** (prose_drift flip mechanism test-proven ×14 + `/conformance/status`
> overlay proven live-reachable). **All throwaway fixtures cleaned — 0 leak (pasted count queries).**
>
> **▶ S06=G5 RE-PROVEN FRESH (2026-07-16, `c40f7ddd0`).** After the Stop-hook asked for a live S06 run in
> the session transcript, 6 live gemma-4 rolls surfaced a real gap: the weak agent PROPOSES a valid rules
> spec but drops the follow-up `plan_compile` (the drive holds+re-prompts but by G1 design doesn't execute).
> **Fix shipped:** `planforge_rules_autocompile` (deploy ceiling, default OFF) — a rules propose that parses
> ≥1 arc auto-compiles inline ($0/deterministic). Fresh green: `structure_node=4` (all `plan_run_id`-attributed)
> + `outline_node=4` linked, on local gemma-4, no paid model; unit-pinned both flag sides. Also fixed my own
> harness bug (S06 needs `SKILL_BOOK_ID`). Residual PO-DECIDE: flip the deploy default ON / generalize
> drive-executes-deterministic-steps (`D-G5-DRIVE-EXEC`; neither blocks — S06 is green with the flag).
> **Note:** the dev composition-service container currently runs with `PLANFORGE_RULES_AUTOCOMPILE=true`.
>
> **▶ FULLY CLOSED (2026-07-16) — the two remaining deep-flow live-smokes are now BOTH proven live, harness-
> first, on the local model (no paid spend):**
> - **F2 ✅** (`c070f1d5f`) — `D-F2-CONFORMANCE-PIPELINE-SMOKE` cleared: staged chapters+revisions+snapshot,
>   bumped `kg_indexed_revision_id` → `prose_drift` appeared through the REAL `/conformance/status` route and
>   cleared on re-conform; the Plan-Hub **"conformance drift" badge flips both ways** in the browser.
> - **O-11 ✅** (`511e0ec60`, crash fix `e3c5bb4dd`) — `D-O11-PROMOTE-FLOW-SMOKE` cleared: the deep flow
>   branch-previews → **generates an alt-take** (2090 chars ghost prose on local gemma-4) → **promotes** into a
>   derivative Work (persisted:true). **It caught a real white-screen crash** (the panel passed the Work
>   envelope, not the inner Work; the unit test mocked a bare work and hid it) — FIXED + regression-tested.
>
> **Only 1 non-blocking item left: `D-G5-DRIVE-EXEC`** (PO-DECIDE) — flip `planforge_rules_autocompile`'s
> deploy default ON platform-wide / generalize drive-executes-deterministic-steps. S06 is green with the flag
> as-is; this is a product choice, not a gap. Also still tracked (unchanged): P-O1a, P-O2a, D-G2-SETUSER.
> Superseded: D-O11-ATTENDED, D-PHASE3-ATTENDED.

## ⭐ Track: MOBILE — shell + super-app home + PWA + push — **SHIPPED (M0–M5, 2026-07-15)**

> **Spec (SEALED):** [`docs/specs/2026-07-15-mobile-shell-and-home.md`](../specs/2026-07-15-mobile-shell-and-home.md) ·
> **Plan + RUN-STATE:** [`docs/plans/2026-07-15-mobile-shell-and-home-plan.md`](../plans/2026-07-15-mobile-shell-and-home-plan.md), [`…-RUN-STATE.md`](../plans/2026-07-15-mobile-shell-and-home-RUN-STATE.md)
> `7f09561be` M0 · `b165c10b4` M1 · `e42253548` M2 · `cb9ee0bd4` M3 · `db2bba64e` M4 · `9e9809384` M5

LoreWeave is now **mobile-first**. Each slice: pasted green tests + a cross-service live-smoke + a cold
`/review-impl` (the risky ones got cold-start subagents — they found + fixed real bugs: a shipped-raw-i18n-key,
a rotate-mid-distill duplicate-spend, an unbounded BFF cache, a feed-truncation, **an SSRF in the push register**).

- **M0** `AppShell` — one persistent `<Outlet/>`, chrome-only swap at 767px (no remount → chat SSE/voice survive);
  bottom tabs (centre = Assistant); addressable `Sheet` (`?sheet=`).
- **M1** the assistant on mobile — `<Chat>` + a dock/sheets bound to the SAME hooks (reuse thesis proven).
- **M2** platform home + activity feed — 2 BFF read routes (`/v1/home` degrade contract; `/v1/activity` keyset).
- **M3** You screen + all-apps drawer; existing workshops render in the mobile chrome.
- **M4** PWA (manifest+SW, `/v1` network-only, no silent update) + **global always-visible bottom nav** (user
  feedback: it was getting lost on full-screen routes) + deep-link-survives-login + resume-token-refresh + a11y.
- **M5** content-free Web Push — `push_subscriptions`/`push_preferences`, VAPID sender (exactly-once, 410-prune,
  fail-closed gate, SSRF-guarded), FE SW handler + capability-gated toggle + sign-out teardown.

### ▶ NEXT for this track (all tracked in the RUN-STATE §5)
1. **D-PUSH-LIVE-SMOKE** — the closed-tab VAPID push was WAIVED (dev has no VAPID keypair / HTTPS / browser push
   service). All mechanics are unit-proven + the routes live-smoked. Do the real closed-tab content-free E2E on a
   deploy that has VAPID + HTTPS.
2. **D-PUSH-ACCOUNT-TEARDOWN** — `DeleteAllForOwner` is built but unwired (account erasure is admin-cli-driven, no
   event to bind). Wire it to an erasure event, or add `push_subscriptions` to the admin erasure purge.
3. Native (Capacitor) is a documented fallback, NOT built — only if an iOS-push-unreliable / store-required /
   background-voice trigger fires.

---

## ⭐ Track: SC11 AMENDMENT — the written-verdict is MAINTAINED, not derived — **SHIPPED** (2026-07-13)

> **Spec + full build audit:** [`docs/specs/2026-07-13-sc11-amendment-written-verdict.md`](../specs/2026-07-13-sc11-amendment-written-verdict.md)
> `3e0dbca3b` P0 · `7f6c921ce` P1 · `515b3676b` P2 · `12ee4d1f2` P3 · `4bffd2cbe` P4

**"Is there prose behind this spec node?" is now a COLUMN, maintained on write.** It used to be
derived on the client — **twice**, in two features, with two different partial-read guards — and it
was invisible to agents (it lived in a `useState` and died with the panel).

The chain is live across four services: `PATCH /draft` → `POST /publish` → book-service writes
`scenes.source_scene_id` + emits `chapter.scenes_linked` → worker-infra relays it → **composition's
first domain-event consumer** re-reads that chapter → `outline_node.written_scene_id` **stamps
itself** → the canvas payload carries `written`. Delete the chapter → **it clears itself.**

**`useActualState` is deleted** (130 lines of generation guards, dedupe sets, completeness tracking
and page-walk bounds). The cold-open budget test now **forbids** `listScenes` outright.

### ⚠ The two things worth reading before touching this

**1 · The writer census was wrong TWICE.** The spec said `scenes.source_scene_id` is written in
**three** places. It is written in **seven**. The DB test found PUBLISH and the IX-3 sweeper (which
re-links a book *in the background*); `/review-impl` found the two worker-infra import INSERTs — and
those are the nasty ones, because the IX-12 write-back **only fills NULLs**, so a re-imported book
arrives already-anchored, nothing announces it, and **the whole book renders unwritten**. Two
source-level drift-locks now pin the census. **An eighth writer without its event turns them red.**

**2 · `written_scene_id` is a REGENERABLE CACHE, not a second anchor.** DA-3 says *"the index points
at the spec, never the reverse"* — so a back-pointer on `outline_node` **looks** like a violation and
the next agent will be tempted to delete it. It is not: book-service always wins, and the sweeper
rebuilds it from `scenes.source_scene_id`. The DDL comment and a test both say so. **Deleting it would
silently restore the client-side derivation.**

### ▶ NEXT for this track

1. **Debt — the event dispatcher is duplicated.** knowledge-service has an `EventDispatcher` class;
   composition now has its own; campaign-service uses an `if`-chain. `BaseProjectionConsumer` already
   lives in the `loreweave_jobs` SDK and the dispatcher should follow it (**SDK-First: ≥2 users ⇒
   SDK**). Not done here: knowledge-service is under active concurrent development.
2. **The backfill has not been RUN on existing books.** `written_verdict_service.backfill_all` is
   built, tested (idempotent + keyset-resumable + never-clears-on-a-degraded-read) and ready, but no
   production run has happened. New/edited chapters self-heal via the event; **old untouched books
   will render unwritten until it runs.**
3. **`P-08`** (from the book-package cluster) is still open — the planning tools are federated but not
   in `ALWAYS_ON_CORE`, so the agent never discovers them (`discovery_calls_total: 0`).


## ⭐ Track: WRITING STUDIO — TOOL↔GUI GAP (specs 30–38) — **AUDIT + SPECS DONE, BUILD NOT PLANNED** (2026-07-12, branch `feat/context-budget-law`, HEAD `9262ed53e`)

> **Anchor:** [`docs/specs/2026-07-01-writing-studio/30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md`](../specs/2026-07-01-writing-studio/30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md)
> — **§0 = the 4 SEALED PO decisions (do not re-litigate from memory) · §4 = the authoritative per-spec
> status of 00–29 · §5 = the gap register · §7 = the waves.**
> *(The three track blocks below are DIFFERENT, concurrent tracks — left intact.)*

**The law it enforces (GG-1):** *every backend capability a user owns must have a human surface. The
agent is an accelerant on the user's own capabilities — never the only door to them.*

**What landed (docs only — zero code):**
- **The audit.** 37 agents across inventory → join → adversarial-refute → completeness-critic. **22
  verified gaps: 18 CONFIRMED · 4 PARTIAL · 0 refuted** (every refuted sub-claim is parked in §10 so it
  is never re-raised). Also found **3 FE calls that 404 in production today** (§3.3) and 10 of
  composition's 31 tables reachable **only** from the legacy page spec 16 is slated to delete — so
  **GG-4: retiring `ChapterEditorPage` before the ports land DELETES shipped features.**
- **The master plan (30)** — waves 0–8 + the spec-29 parallel lane, 19 backend prereqs, and **4 SEALED
  PO decisions**: PO-1 amend spec 28's AN-12 (its *architecture* stands: no new panel) · **PO-2
  G-WORKFLOWS → Track C** · PO-3 retire `ui_show_panel` into `ui_open_studio_panel` · PO-4 **all specs +
  drafts before any implementation plan**.
- **Specs 31–38 + 11 HTML drafts** (`design-drafts/screens/studio/`) — PO-4 is now satisfied.
- `00_OVERVIEW`'s index + Debt stack and `00C`'s queue refreshed against §4 (they were actively
  misleading: 00C's Q-2 *"Agent Mode 0% frontend"* was **flatly false** — the panel is in the catalog
  **and** the agent enum; **cleared**).

### ▶ NEXT for this track

**The implementation plan is NOT written** (PO-4 held it until the specs+drafts existed — they now do).
**The next step is to PLAN the build**, starting with **Wave 0 — FOUNDATIONS** (30 §7; no panels, all
landmines under every other wave):

1. **X-1** — `AddModelCta` DOCK-7 teardown, fixed at the **shared component** (not the ~8 call sites).
2. **X-2** — `CATEGORY_ORDER` is missing `'quality'` (`indexOf` → -1 ⇒ it sorts **first**, not last).
3. **X-4** — the **Lane-B effect registry covers none of the new domains** (~15 handlers: canon_rule,
   motif, arc, plan_*, authoring_run, world_map, kg_create_node…) — without it every agent write leaves
   the new panel stale.
4. **X-5** — retire `ui_show_panel` (PO-3) + intercept `ui_watch_job` (it tears the dock down today).
5. **X-7** — the **`gather_motifs` packer lens** (21-G1): `pack()` reads **zero** motif data. Wave 3 is
   HARD-GATED on it, or it ships a beautiful editor for a field nothing consumes.
6. **The 3 live 404s** (§3.3) + the 4th the 34 review found (`_execute_arc_import`'s unreadable job).

Then Wave 1 (spec 31, cheapest+highest value) — or the **spec-29 translation lane**, which collides with
nothing. **G-WORKFLOWS was handed to Track C (PO-2)** — its P-5 claims the workflow rack/binding UI. ⚠
Hand Track C this fact: `registry_propose_workflow`'s own description says the user approves *"in the
UI"* and **there is no UI**, so an agent calling it today writes a row **no human can ever approve**.

### Deferred (from plan 30 — consciously parked, each with its gate reason)

| ID | What | Gate |
|---|---|---|
| **D-PUSH-LIVE-SMOKE** | The M5 closed-tab VAPID push not proven live (mechanics unit-proven; routes live-smoked; SSRF guard live-verified). | #4 blocked-on-external: needs a deploy with a VAPID keypair + HTTPS + a browser push service (FCM/autopush) — none bootable at dev. Do the closed-tab content-free E2E there. |
| **D-PUSH-ACCOUNT-TEARDOWN** | M5 push subs not auto-deleted on ACCOUNT deletion (sign-out DELETE IS wired). `DeleteAllForOwner` primitive is built. | #2/#4: account erasure is admin-cli-driven, no AMQP event to bind. Wire to an erasure event OR add `push_subscriptions` to the admin erasure purge. |
| **D-STUDIO-07S-COMPACTION-BREAKER** | 🔴 **P1 — a real defect, not a gap.** 07S has **no microcompact tier, no `hard_truncate`, and no `compaction_failed` breaker** (0 grep hits) — while **Agent Mode's L3/L4 autonomous runs are SHIPPED and running**, and 07S §3/§10 make that breaker **MANDATORY for headless runs**. An unattended run can therefore fail compaction with nothing to stop it. **Raise it, scope it, build it.** | #2 large/structural (needs its own slice + design), **not** "later" |
| **D-STUDIO-HOOKS-10** | Spec **10 · agent lifecycle hooks — 0% built** (a service, a table, an orchestrator, a sandbox, a manifest format, a settings UI; zero grep hits). **XL.** The single biggest unbuilt block in 00–11. | #2 large/structural — needs its own track, not a wave |
| **D-ARC-DECOMPILER** | Spec **26-D3** — the arc decompiler: the only path to a spec tree for an **imported** book with no plan. | #2 large/structural |
| **D-PLANFORGE-PROPOSE-BLIND** | Spec **21-G2** — PlanForge `propose.py` takes no `existing_state`: proposing a plan for a book with 200 chapters **ignores all of them**. | #2 — a real engine change; not in any wave |
| **D-WIKI-INVERSE-GAP** | **GG-2 (the inverse law):** `wiki` + `wiki-editor` panels exist and glossary-service registers **zero `wiki_*` MCP tools** — the agent cannot help with the wiki at all. | #3 naturally-next-phase — no wave owns it yet |
| **D-G2-SETUSER** | **Per-USER tuning of the governance enforcement strength** (`enforce`/`nudge`/`off` + N), beyond the platform deploy config that shipped (close-21-28 G2). **PO wants per-user** (2026-07-16) — promoted here from the now-closed 21-28 §9.2 so it isn't orphaned. | #2 large/structural — needs the full ai-prefs pipeline (enum + write-door + tier cascade + deep stream threading) **and an FE settings surface** in the studio to trigger it. Build when the studio settings surface lands. |

<details><summary>Numbers, and where the audit says it is uncertain</summary>

75 composition MCP tools (17 AGENT-ONLY) · 155 REST routes (~22 with no FE consumer) · 31 tables (10
LEGACY-ONLY, 2 WRITE-ONLY) · 68 catalog panels (agent enum **57 == 57** openable — **zero drift**) · 12
frontend tools (2 defective). ⚠ **The "173 tools / 23 no-GUI" scoreboard is a FLOOR, not a total**:
provider-registry's 14 MCP tools and catalog-service's 2 were **never swept** (§3.4 — closing them is
Wave 0's X-9), and provider-registry registers `web_search` **unprefixed**, which the repo's own
namespacing law says **shadows**.

</details>

## ⭐ Track: ALL-TRACKS-CLEAR (Agent Discoverability & Workflow, A/B/C/D) — **COMPLETE** (2026-07-15, branch `feat/context-budget-law`)

> **Anchor:** [`docs/plans/2026-07-13-all-tracks-clear-RUN-STATE.md`](../plans/2026-07-13-all-tracks-clear-RUN-STATE.md) (§1b scenario tally · §8 drift) · report [`docs/eval/discoverability/2026-07-15-M2-all-scenarios-clear.md`](../eval/discoverability/2026-07-15-M2-all-scenarios-clear.md).

All six DoD criteria met + proven in-transcript (spec `docs/specs/2026-07-13-all-tracks-clear.md`):
1. **18/18 scenarios ≥2/3** — DB ground-truth + judge, assembled across small batches (a concurrent
   session recreated chat-service ~every 1.5 h; each scenario has a clean 3-run block). S06 flagship
   **3/3 fresh** (`chapters_with_prose=1`). The "18/18 already-proven" inherited claim was an overclaim
   (cherry-picked runs); real blocker was the test account's **200-book quota** — fixed self-healing.
2. **4 FE surfaces browser-proven by effect** — workflow rack (15 cards), binding UI (vision-to-book
   bound), W10 maps canvas (3 maps + Ironhold marker) + `/v1/worlds/{id}/maps` REST 200s, W11
   lore-seeker (FE now sends `before_chapter_id`; BE window discriminates ch1-vs-ch3 live).
3. **Track A/B gaps** — tier-tag CI gate (central `scripts/tier-tag-gate.py`, wired `lint-foundation.yml`
   p1-lints + pre-commit; Python `_meta` byte-compile-only replaced by the real scan) · #6 gated-reason
   (BUILT, `scope_note`) · F3 floor (`effective_limit`) · `story_search before_chapter_id` cutoff.
4. **5 bugs** — ONTOLOGY-BLOAT (8859B<32KB) · CHAPTER-PAGINATION (2 DB tests) · PROSE-BLOCKS-BACKFILL
   (0 manuscript gaps) · EVAL-SPEND-FIXTURE (grants seeded) · **P-2** (147 tests — ⚠ knowingly touched
   the concurrent session's 4 stale tool-count tests).
5. **Docs reconciled** — BOARD.md, TRACK-C-AUDIT.md, W10/W11 spec (BUILT), TRACK-D-COMPLETION.md
   (SUBSTANTIALLY MET, 211/224, web_search keyless relay), RUN-STATE §1b + DR14/DR15, this file.
6. **S06 regression gate green** (3/3 fresh).

Mandatory adversarial review (W11 reader/consent) found + FIXED 2 real fail-opens: entity-LIST spoiler
window (names leaked past the facts window) + consent read-tool fail-open on a DB blip. Commits
`e1891749c` · `876a3d6a8` · `5c10e259b`.

**Post-clear audit + remediation + QC (2026-07-15, same session):**
- **4-track cold-start completeness audit** (1 agent/track, disjoint, "assume inflated"): A/B/C
  **SUBSTANTIALLY COMPLETE** (no false shells; B's 2 findings = the ones fixed above, confirmed closed);
  **D OVERSTATED** — infra MET but the WS-D4 `waived`-in-manifest exit mechanism was never built (13
  waives were prose-only), `save_draft` was a rationalized waive (M0a-fixed), 2–3 buildable-at-$0 waives
  mislabeled "paid". Commit `319581f72`.
- **D-TRACKD-REACCOUNT — CLEARED** (spec `docs/specs/2026-07-15-track-d-reaccount.md`; M1 `6e1e05966`,
  M2/M3 `47ae92c0b`, M4 `56e6103b9`, M5 `bfd8e4f91`): built the `waived:{reason,gate}` mechanism (schema
  v2, generation fails-closed on a null-without-a-waiver); post-M0a re-sweep flipped **0/13** + **0 broken**
  → VALIDATED the waives (evidence-sharpened gates: deferred-build×9, needs-resweep×2, external×1,
  upstream-drift×1). **211 executes:true + 13 machine-waived = 224 accounted, executes NOT faked;** WS-D4's
  OR-WAIVED clause finally machine-backed. Track D → **MET**. Cold-start `/review-impl` clean (1 finding,
  fixed in-phase).
- **QC close:** rebuilt+redeployed chat-service (consent Fix-2, verified live) + knowledge-service
  (entity-list window + story_search schema). Full suites: knowledge **3985 pass**, chat **1665 pass**.
  **1 real regression caught + fixed** (`f80c875ca`): story_search's `before_chapter_id` was in the arg
  model/executor/FastMCP sig but MISSING from the hand-written JSON schema (3-schema-sources trap) — the
  LLM couldn't discover the spoiler cutoff; S11 masked it (harness-injected). ⚠ **9 remaining suite fails
  are NOT this session's** (git-verified: 2 knowledge `fact_type` = P5 commitment track `3b45ad4d3`; 2
  chat `voice_billing` = voice track `e0e64f9fd`; 5 = the documented D-SUITE-RED-5) — flagged for their
  owning sessions per shared-checkout invariant #9, not touched.

## ⭐ Track: BOOK-PACKAGE CLUSTER (specs 22–28) — **COMPLETE** (2026-07-12, branch `feat/context-budget-law`)

> **Anchor:** [`docs/plans/2026-07-12-book-package-RUN-STATE.md`](../plans/2026-07-12-book-package-RUN-STATE.md) —
> §5 slice board · §6 decisions · §7 parked · §8 debt · §9 drift · §10 completeness ledger · §11 final audit.
> *(The Work-Assistant and Track-C blocks below are DIFFERENT, concurrent tracks — left intact.)*

**All of 00B is built and live-proven, except one externally-blocked eval.** A book now goes from a
braindump to a linked, cast-populated, scene-level plan with a manuscript under it — and an agent can
orient in it, search it, and be told what is wrong with it.

- **Stage 7 · `24` Plan Hub** — the ACTION half (`b904b3a74`, `09f2d29b1`).
- **Stage 6 · `27` PlanForge v2** — the seven-pass compiler. **LIVE: `pass_cursor 7/7`**, both human
  checkpoints honoured, the glossary seeded through the bootstrap quarantine (PF-7), the roster bound
  onto the spec (PF-13), 6 scenes linked with tension **and** resolved cast, bootstrap stamping 2/2
  planned nodes (E3). Re-running a pass stales everything downstream with **zero invalidation writes**.
- **Stage 8 · `28` agent-native** — `composition_package_tree` (the agent's `ls -R`, **~138 tokens** on a
  real book), `composition_find_references` (the inverse query composition never had), and
  `composition_diagnostics` (the problems panel). All three live over the real MCP transport.

**2067 tests pass.** Four `/review-impl` passes found **9 HIGH — every one mine**; all fixed in-phase.

### ⚠ The one thing to read before touching the compiler

`propose.py` (rules mode) spent its entire life returning **one specific Vietnamese novel's**
characters, planner-variables, forbids and arc titles for *every* book anyone planned — and it never
failed, never returned empty, and never looked wrong. It is fixed (`2c0a44a30`), and the lesson is
the point: **a confident wrong answer is the worst failure mode there is.** It only surfaced because
the linker finally tried to write the compiler's output somewhere real (BPS-18: *an emitted artifact
with no linker is a bug*).

### D-04 RESOLVED (2026-07-12) — PH18's rule deep-link was never impossible

The PO asked to see the canon data model, and the model said I was wrong. A generation job carries
**two** verdicts, written by two engines into two columns:

| | `result.canon.violations[]` | `critic.violations[]` |
|---|---|---|
| asks | "is a character marked **gone** still acting?" | "which author-declared **rule** does this contradict?" |
| keyed by | `entity_id` — `canon_check` never loads `canon_rule` at all | **`rule_id`** — `judge_prose` is handed the active rules; `_filter_violations` DROPS any item lacking one |
| surfaced as | `CanonIssue` → what the panel listed | **nothing, until now** |

The rule→violation link **already existed** — the panel just surfaced the wrong lane, and there was
already a `POST /jobs/{id}/dismiss-violation` addressing violations BY RULE. Shipped option B: a new
`GET /works/{pid}/rule-violations` + a third lane in `QualityCanonPanel` + `PlanHubPanel` forwarding
`focusRuleId` instead of discarding it. **PH18 was never a spec amendment. It was a small build I
mis-scoped by reading one object and generalising to the system** (RUN-STATE DR-26).

### ⚠ And the review found a worse one — a panel that lied

`QualityCanonPanel` rendered **"No canon issues found."** whenever the composition Work did not
resolve — pending backfill, absent, **or composition-service simply DOWN**. Both its queries are
`enabled: !!projectId`, so they never ran, resolved to `[]` with no error, and `empty` computed true.
Its 3 sibling quality panels already guard this (`QualityNoWorkState`); canon never adopted it. **Not
hypothetical: all 8 Works in the dev DB are `pending_project_backfill`, so it was lying about every
book.** One test had even pinned the false-clean as correct. Fixed + 5 regression tests (DR-27).

**Also fixed in-phase:** `rule_violations` was unbounded (now capped 200 + exact count + `capped`
flag — `pagination-cap-lint` misses a route with no `limit` param to clamp); `composition_diagnostics`
gained source **(2b)**, so the agent can see a broken canon rule too.

### ★ The flagship gate is RED — and it is the most useful thing this run produced

`P-07` was **never blocked** (that park note was a correlation shipped as causation — see DR-31/32).
Run correctly, S06 completes and the agent-native surface **works**: 17/17 turns, 28 tool calls,
0 empty-intent, **9 effectful**, 0 commit-failed, 0 false-success claims, 4 glossary entities created.

**But the gate fails:** `structure_node=0 · outline_node=0 · plan_run=0 · chapters=0`. The agent
called **only** `glossary_*` and `kg_*` — **not one `composition_*` or `plan_*` tool in 17 turns**.

**Root cause (evidenced):** the planning tools ARE federated (ai-gateway catalog `245 tools / 10
providers`) but are NOT in `ALWAYS_ON_CORE` (≤10 tools). Everything else is reachable **only via
discovery** — and the run recorded **`discovery_calls_total: 0`**. The agent never once looked for a
tool, so it never found the ones built for it.

**We built the tools. The agent cannot see them.** Tracked as **P-08**; the fix is in chat-service's
`tool_discovery.ALWAYS_ON_CORE` / Track-C mode bindings / Track-D tool-liveness — **not** in this
cluster, whose tools are built, advertised and effectful.

### ▶ NEXT for this track

0. **⚠ PO-DECIDE — SC11/PH12 → the amendment is WRITTEN and awaiting sign-off:**
   [`docs/specs/2026-07-13-sc11-amendment-written-verdict.md`](../specs/2026-07-13-sc11-amendment-written-verdict.md).
   *Maintain the written-verdict on write (a column), don't derive it on read — by either side.* It does
   **not** overturn BPS-11 (which asked only about `status`/`pov` FILTERS). It also surfaces a **live
   latent bug** worth fixing on its own: the IX-12 decompile write-back sets `scenes.source_scene_id` and
   **emits no event** (§5.2 / Phase 0).
   *(original note below)*
0b. **⚠ PO-DECIDE — SC11/PH12 vs "the FE is a projection of data state".** The PO's rule and SC11 point
   opposite ways. `useActualState` derives *"has this scene been drafted?"* — **a fact an agent would
   obviously ask** — client-side, and it costs ~130 lines of generation-guards, per-chapter completeness
   tracking and page-walk bounds to stay correct. The same relation (spec↔manuscript) is already
   computed **server-side** in two other places (`compute_coverage`, `compute_prose_deleted`), both
   agent-reachable. Proposed test: **fact vs view** — *"would an agent ever ask this?"* yes ⇒ BE.
   Proposed resolution: **amend SC11, don't overturn it** — keep "no per-node server join at render
   time", add "a derived FACT about the relation is one bulk anti-join, server-side" (the shape
   `compute_coverage` already ships). **Not actioned — SC11 is LOCKED; this is the PO's call.**
1. **`P-08` — make the planning tools reachable** (see above; the old `P-07` "blocked" note is void) (the pillar's ship signal, 27 H4 / 28 AN-D3). **Blocked
   externally, not by code:** a concurrent session was redeploying `chat-service` and every redeploy
   401'd the 17-turn eval mid-run (reached turn 8/17, 4 tool calls, 0 empty-intent — the harness and
   the new tools work). Re-run when the stack is quiet:
   ```
   JWT_SECRET=<chat-service env> QG_BASE=http://localhost:8212    QG_MODEL_REF=019ebb72-27a2-72f3-a42d-d2d0e0ded179    QG_SCENARIOS=scripts/eval/discoverability_scenarios/S06-flagship.json    QG_OUT=docs/eval/discoverability/runs/2026-07-12-S06-v2-gate    python scripts/eval/run_discoverability_scenario.py
   ```
   The *structural* property its gate names ("the plan movement ends with linked structure") is
   already live-proven; what stays unproven is whether the AGENT discovers and drives the new tools.
2. **`⚠ PO-DECIDE` (D-04)** — 24 PH18 asks for a canon deep-link "filtered to the rule". That is
   **impossible against the data model** (`CanonIssue` rows carry no rule id). I deep-linked by the
   node's CHAPTER and flagged it. Rule-level filtering needs a `rule_id` on `CanonIssue` — a `26`
   change, and PH18 becomes a spec amendment.
3. **New debt:** `DBT-10` (request bodies are unbounded — a body cap belongs at the router layer for
   every large-text field), `DBT-11` (a service-wide `paid` audit — Track D's), `DBT-09` (book delete
   does not cascade to composition's spec rows — cross-service, real, outside this cluster).


## ⭐ Track: WORK ASSISTANT — Phase 0 COMPLETE · Phase 1 ~40% (2026-07-12, branch `feat/context-budget-law`)

> **Anchor:** [`docs/plans/2026-07-11-work-assistant-RUN-STATE.md`](../plans/2026-07-11-work-assistant-RUN-STATE.md) —
> **read it FIRST**, then `git log --oneline -15`. It holds the slice board (§5), the decision/parked/debt/drift
> registers (§6–§9) and the final audit (§10). *(The Track-C block below is a DIFFERENT, concurrent track — left intact.)*

**PHASE 0 — publish-independent KG indexing: DONE, live-smoked, `/review-impl`-clean.**
Publishing no longer gates the knowledge graph. `chapters.kg_indexed_revision_id` + `kg_exclude`; an explicit
"add to knowledge" action (`chapter.kg_indexed`); the reparse sweeper, the whole-book rebuild, the passage
backfill/ingester, the cost estimate, composition's `index_stale` and glossary's wiki-staleness all re-keyed.
FE control + indexed-state badge. **A 6-modality sweep found 29 duplicated read-gates across 6 services where
the spec named ~5** — including campaign-service and glossary-service, which nobody had looked at.

**`/review-impl` confirmed 28 findings (2 P0) — all fixed. Three sat under GREEN TESTS I wrote myself:**
publishing a `kg_exclude`'d chapter still indexed it (the pointer is not what puts a chapter in the graph — the
EVENT is); both passage backfills stamped unreviewed **draft prose as canon** and one embedded the *live draft*;
worker-ai silently rebuilt only the **first 100 chapters** of any book and reported success.

**PHASE 1 — WS-1.0…1.3 shipped:**
- **WS-1.0** envelope encryption (PO-2): per-user DEK wrapped by a deployment KEK, AES-GCM, retired-keyring so a
  rotation cannot orphan a diary; **blind index** (HMAC tokens; 2- **and** 3-grams, or CJK search returns nothing);
  **encrypted embeddings** + in-memory cosine (plaintext embeddings ≈ plaintext diary). Cross-language golden
  vector: Python unwraps a DEK **Go** wrapped. DEK cascade-deletes with the user = the D18 crypto-shred.
- **WS-1.1** `books.kind` — the **privacy lock**, immutability enforced by a **DB trigger** (not a convention).
- **WS-1.2** core egress locks: a diary **cannot be shared** (DB trigger), **has no wiki** (the widest hole — it
  would have served AI biographies of real colleagues to the internet), is **hidden from the library LIST**; and
  `kind` now rides `getBookProjection`/`getBookAccess` so consumers *can* guard (gated behind a grant, else it is
  an oracle).
- **WS-1.3** diary schema + the **D6 gate**, which exposed that the existing chat-turn gate was **decorative**
  (its answer was computed, logged, then ignored while the enqueue ran anyway).

**▶ NEXT: WS-1.4 provisioning** (makes the assistant exist end-to-end; immediately demoable). Then 1.7 session →
1.8 distiller → 1.9 recall → 1.10 FE. **All foundations are in and tested; what remains is build volume.**

**⚠️ NEEDS A HUMAN DECISION (RUN-STATE §7):** **P-1** campaign-service (should a campaign be buildable from
indexed *drafts*? — I refused to change another feature's semantics silently) · **P-3** publish@A + index-draft@B
demotes a chapter out of canon search · **P-4** the remaining egress paths (`memory_*` leak, content-free
notifications, public-MCP scoping) — a **Phase-1 EXIT requirement, before any real diary content exists**.

---

**Track C — LONG AUTONOMOUS RUN 2026-07-12: Phase 1 (consent defect) + Phase 2 (rail-driver mechanism) DONE + review-clean; catalog 3→5.** Full record + PO decision packet: [`docs/plans/2026-07-12-track-c-completion-RUN-STATE.md`](../plans/2026-07-12-track-c-completion-RUN-STATE.md) (§10 ledger, §11 packet). Highlights: the **consent defect `D-C-ALLOWLIST-WRITE-ONLY` is CLOSED** (view/revoke/deny + the backend that never existed); the **flagship's real blocker was a 44KB tool payload** the model called 24× and built nothing from — fixed, plus a **result-size ceiling in both MCP SDKs**; S06 categories **0→reliably 13** (still 1/5, model adopts-and-stops → parked P-1 = server-side step-runner). Two adversarial reviews (49 confirmed findings, incl. 3 HIGHs where my own code broke the platform) all fixed in-phase. **Superseded — WS-3 SHIPPED 2026-07-11:** [`2026-07-11-ws3-mode-capability-binding.md`](../eval/discoverability/2026-07-11-ws3-mode-capability-binding.md).

- **The measured bug WS-3 kills:** advertising a workflow does NOT work. S06 had the right workflow advertised **plus** a steering directive telling the agent to load one, and it still improvised — because a user co-writing a novel never *asks* ("set up my world"); they only **assent** to the agent's own offer (*"yeah do it"*). Recognising a workflow from an assent is a step a mid-tier model does not reliably take. **A PIN removes the step:** the rail is rendered into context from turn 1. Live proof, same turn, same model: baseline `find_tools → plan_propose_spec` (improvised) ⇒ WS-3 **`glossary_adopt_standards`** (runs the rail).
- **Shipped:** `mode_bindings` (agent-registry, 3-tier System/user/book, scope-key CHECK + per-tier partial UNIQUEs) · effective = **union of tiers MINUS `disable_workflows`** (a **C6 extension** — a pure union leaves a user unable to turn OFF a System pin, i.e. a global flag wearing a setting's clothes; a translator must be able to drop the co-writer rail) · read folded into the existing per-turn `/internal/workflows?mode=` call (one hop, one degrade path) · `GET/PUT /v1/agent-registry/mode-bindings/{mode}[?book_id=]` (System never writable; a pin naming an invisible workflow is **rejected at the write**) · consumption: `inject_skills` (additive, surface-filtered) + `seed_tool_categories` (same single budget ceiling) + **`inject_workflows` = PIN** (rail rendered by `workflow_load_result()` itself — one rail format, cannot drift; step tools pre-activated) · **`budget_rail_tools()`** budgets a rail in **declared step order** (the existing read-first budget would drop exactly the *write* steps that persist anything) · **the flagship `vision-to-book` rail** System workflow (12 steps, surfaces `{book,editor}`). The hardcoded `plan→plan_forge` **stays** as the degrade-safe fallback.
- **S06: 1/5 → 2/5.** World structure now gets BUILT (**0 → 12 kinds**), plan retained, **jargon PlanForge 27→4**, slug leak 6→1, **discovery calls 0**. Pin cost is bounded + measured: **+3.0K tok/pass** (rail 1246 + 11 step schemas 1740).
- **Three real bugs the run caught:** (1) **a stale image made the first run a lie** — `docker compose build` had failed on a transient PyPI SSL error, `up -d` saw no new image, and the "WS-3" run measured pre-WS-3 code (caught because `plan_nudge` moved only +51 tok and `mcp_tool_schemas` was byte-identical; **always grep the running container**); (2) **the rail leaked its own name** to the novelist ("we can use the *vision-to-book* workflow" ×6) — the rail is the agent's PRIVATE recipe, now stated as such + test-locked; (3) **a bare apostrophe inside a Postgres `E'…'` literal killed the ENTIRE migration at boot** while every Go unit test stayed green — this class has now bitten twice (a backtick killed the Go raw string in WS-5), so it is **statically linted** (`migrate_lint_test.go`). Same file: System workflow seeds now **`DO UPDATE`**, not `DO NOTHING` (a code-owned row that a deploy can never correct is the "migration never revisits its default" trap — which already bit this effort once).
- **Verify:** chat-service **1406** green (+19 new) · agent-registry api + migrate green (+6 binding tests incl. *user vetoes a System pin*, + the lint). live smoke: S06 on a fresh, provably-empty book.
- **`/review-impl` (33-agent adversarial, 27 raised → 17 confirmed / 10 refuted) — ALL 17 FIXED + verified.** Write-up: [`2026-07-11-review-impl-ws3.md`](../eval/discoverability/2026-07-11-review-impl-ws3.md). **It found the S06 rail-stall root cause I was about to hunt by hand:** (1) **HIGH** — a confirm-gate **resume keeps the rail's TEXT but drops its TOOLS** (the rail rides the system message inside `working`; the resume re-derives the surface with no `book_id` to re-fetch the binding), and the flagship rail's first confirm gate is **step 3 of 12**, so the flagship rail broke at its very first gate → `pinned_step_tools` now rides the `SuspendedRun` (new `chat_suspended_runs.pinned_step_tools` column); (2) **the flagship rail's `capture-cast` was mislabelled ASYNC** — `glossary_extract_entities_from_doc` matches the name heuristic (`extract_entities`), so the rail told the agent to *watch a background job* for a SYNCHRONOUS tool and it stalled forever → authored `async_job:false`. Also: `/internal/workflows` **never grant-checked its client-supplied `book_id`** (any user could read any book's book-tier workflows + binding by knowing the UUID → `bookGrantOK(GrantView)`, fail-soft); the **book-tier pin was validated against the WRITER's private visibility** (A could pin a private workflow into a SHARED book — invisible to every grantee, whose turns silently ran unpinned while GET reported it as effective — and the book's OWN workflows were unpinnable); the System **`mode_bindings` seed still used `DO NOTHING`**; `inject_skills`/`seed_tool_categories` were **stored unvalidated and silently no-op'd** (write-only behavior); the pinned block had **no aggregate ceiling**; the pin lost the catalog's `_meta.async` (pin/load drift); and the **migration lint was tautologically green** — the scanner stops AT the first bare quote, so the body it checked could never contain one → rewritten to detect MIS-TERMINATION, with a negative control.
- **Two more bugs found by running the fixed code.** (a) **A cap silently ate the rail's most important rules** — the flagship rail's notes were 3218 chars against my own 3000-char cap, so the tail was dropped, and the tail was the SPEAK-PLAINLY block: **the jargon leak survived its own fix and the truncation said nothing.** Cap raised + truncation now WARNS + the registry lints that a seeded rail fits the consumer's ceiling. (b) **A mid-tier model cannot transcribe a UUID** — gemma passed the real `book_id` **plus one extra character** → `400 book_id must be a UUID`, twice (same failure mode as its 519-char confirm_token mangling). Arg-injection only filled a MISSING id (to respect a cross-book call); a **malformed** value cannot be a deliberate cross-book call, so the server's known id now wins — a valid-but-different UUID is still honored (negative control). **General fix: helps every weak model.**
- **Live re-run:** the honest error from the silent-success fix **drove self-correction** (proposed entities before any category existed → *"unknown kind: character… create the categories first"* → the agent immediately called `glossary_adopt_standards`). **But S06 still does not ship, and VARIANCE is now the story:** four runs, identical stack/model/scenario → kinds **5 / 12 / 0 / 5** · entities **0 / 0 / 0 / 0** · plan **0 / 1 / 0 / 0**. The rail reliably STARTS (assent gap stays closed); the cast NEVER lands in any run.
- **Verify (post-review):** chat-service **1418** green (+31) · agent-registry api + migrate green (incl. the lint's negative control) · both migrations applied on a real stack.
- **Deferred (tracked) — RE-VERIFIED against code 2026-07-11:** (a) ~~`D-WS3-RESUME-PIN`~~ **CLEARED** — fixed by /review-impl (it was a HIGH, not a defer: the rail's TEXT survived the suspend while its TOOLS did not). (b) ~~`D-WS3-BOOK-TIER-PIN`~~ **CLEARED** — fixed by /review-impl (`workflowVisibleInBook`; the reviewers showed it was worse than I logged: it ALSO let a private workflow be pinned into a shared book). (c) `D-WS3-BINDING-GUI` — **still open**: the binding is API-addressable (`GET/PUT /v1/agent-registry/mode-bindings/{mode}`) but has no settings panel, so a user cannot turn the co-writer rail off without an API call (gate #2: a settings surface, not a knob).

**▶ NEXT (Track C) — 2026-07-13: S06 PASSES the FULL §4 DoD — 5/5 with ALL FOUR gates clean in 3/3 consecutive fresh-empty-book runs.** Three root causes, all fixed: connect-project = **eval-HARNESS run_id bug (DR21)** (harness resumed with stale `RUN_STARTED.runId` not each suspend's `pendingToolCall.runId` → consent resume "expired" → `kg_project_create` never ran); missing 5th artifact + async-poll = flagship arc-plan being an **async llm job a mid-tier model can't watch** → made SYNCHRONOUS (mode=rules; driver chains arc-plan→draft→write, DR23); vocab = a mid-tier model won't self-censor → a **deterministic `scrub_jargon` guard** at the emitter rewrites §4 system-jargon in the user-facing stream (DR26). Also hardened gemma's `project_id=[uuid]` list-wrap (DR22). **Pasted SQL + gate eval, 3 runs: `VOCAB-1/2/3 all 5/5 · persist=[] · async=0 · jargon=0 · CLEAN`.** Commits: `55e537e0d` (connect-project), `7d2e945ef`+`bac8802c2` (sync plan/async), `af336c338` (vocab guard); earlier `3ad8f9898` (step-runner review), `c59d9ccf9` (WS-5 catalog 10/10), `72b5fc895` (D3/D7 sign-off). **Still parked with next-steps (RUN-STATE §7):** P-4 (scenarios — prioritise S00e), P-5 (FE surfaces). Full record + PO packet: RUN-STATE §7/§10/§11. Everything below is the SUPERSEDED pre-run diagnosis, kept for the record.

<details><summary>Superseded pre-run diagnosis (2026-07-11)</summary>

**The remaining blocker is that NOTHING DRIVES THE RAIL FORWARD.** Post-review, the mechanism is no longer the problem: discovery is dead (0 `find_tools` calls), the assent lands on the rail, the step tools are advertised (including across a confirm gate now), and the tool errors are honest and actionable enough to drive self-correction. What is left is that the model must HOLD a 12-step recipe across a 17-turn conversation while also doing the emotional work of the scene — and it drops it; each user turn gets answered on its own terms. **That points at a server-side STEP-RUNNER that advances the rail** ("you are at step N; N-1 succeeded; the next call is X") rather than a rail the model must remember to follow, plus **book-state grounding** so "what is already done" is answerable from the SSOT instead of from memory. A real design, not a prompt tweak — and the honest next milestone. (Superseded diagnosis, kept for the record: **S06 was 2/5 — the remaining blocker is RAIL CONTINUATION, not discovery.**) The agent now *starts* the rail (assent → adopt categories) but does **not continue it**: across movements D/E it calls nothing, so the **cast** (`glossary_extract_entities_from_doc` → `propose_entities`), the **connections**, and the **draft** never run even though their tools are advertised and their steps are in context. Two candidate causes, not yet separated: (a) **no progress state** — the rail says "continue from the first step still outstanding" but the agent cannot know what is done (pre-fix run re-read step 1 three times); telling it the **book's actual state** ("12 categories exist; cast: 0") would make that answerable from the SSOT; (b) **one-tool-per-turn habit** — it treats each user message as a conversational turn despite an explicit "chain the steps" instruction, which may mean the rail must be **driven** by a step-runner rather than described. Also open: `PlanForge`×4 / `NovelSystemSpec`×3 still reach the user from the **plan_forge skill prose / tool descriptions** (a separate vocabulary owner needing the same treatment); S04/S05 fixtures; a settings GUI for the binding (the record is API-addressable today).

</details>

**PLAN HUB v2 (spec 24, Stage 7) — Phases H1 (read surfaces) + H2 (canvas core) + H3 (drawer) / H4 (decorations) / H6 (rail) SHIPPED, 2026-07-11** (branch `feat/context-budget-law`; each built via a parallel fan-out + serial integrate/verify). The Hub is a real, openable, 3-region panel — left navigator rail · center React Flow canvas · right detail drawer — over the package structure; H5 (drag mutations) + H2.6 bus + H8 are next.
- **What shipped (all book-keyed, VIEW-gated per BPS-8):** (1) `GET /v1/composition/books/{book_id}/outline/children` — re-keyed to book_id with the `structure_node_id` ARC axis + `parent_id` SCENE axis (mutually-exclusive, **exactly one required — the OQ-4 omitted-parent flip**: no "omitted → all chapters" path, 400 otherwise), `detail=summary` PH10 projection (prose OFF the canvas; present_entity_ids ≤3 + exact `present_entity_count`), keyset `(rank,id)`; (2) `idx_outline_node_structure_keyset` partial index (the structure-axis query repeats `AND kind='chapter' AND NOT is_archived` VERBATIM so the planner uses it — H8.1 will EXPLAIN-assert); (3) `GET .../scene-links` book-keyed edge list; (4) new `GET .../plan-overlay` aggregate (problems=canon+open-threads by node with a global ~50 refs cap + `refs_capped` while counts stay EXACT; tension_rollup; motif_chips pinned-vs-live; `unplanned_chapters=[]` — FE derives it, SC11 forbids the cross-service join); (5) glossary `entity-names` widened — keyset pagination + `truncated`/`next_cursor` + all-non-deleted status (FE client accumulates pages, same flat array to callers).
- **Ratified design decision:** canon_rule has NO node FK, so the overlay anchors a rule to the chapter whose `story_order` == its `from_order`/`until_order` boundary (sparse, matches the spec's own "ch 40" example).
- **Verify:** composition **1755 unit + 242 DB-integration** + a **live-SQL by-effect test** I added (the fan-out wrote MOCKED unit tests only — this proves every new query executes against the real lifted schema, incl. the tenancy double-filter), full **glossary Go** package, **FE tsc** clean. Adversarial 3-concern workflow review (plan-overlay correctness / tenancy sweep / glossary contract) → **0 confirmed, 2 LOW refuted**.
- **Phase H2 (canvas core) SHIPPED — the `plan-hub` panel renders the whole package on a React Flow canvas.** Added `reactflow@11` (RF is the pan/zoom/edge SHELL; nodes sit at the FIXED positions `laneLayout` computes — never RF auto-layout). Structure: `features/plan-hub/{types.ts (the PlanHubView/PlanCanvasProps contract), api.ts, hooks/ (usePlanWindows keyset loader, useActualState two-truths join reusing booksApi.listScenes, usePlanHub controller — 4 parallel cold-open reads, conformance-404→null), components/ (PlanCanvas + ChapterNode/SceneNode/ArcRollupNode/LaneBandLayer)}` + `studio/panels/PlanHubPanel.tsx`. Registered: catalog row + `panel_id` enum add (`frontend_tools.py`) + `WRITE_FRONTEND_CONTRACT=1` regen + en i18n. Default view = all arcs collapsed to rollup cards on arc-titled lanes; expand an arc → keyset-loads its chapters, expand a chapter → its scenes. **Verify:** FE tsc clean, vitest 32 (plan-hub 28 + panelCatalogContract 4) + dockablePanelHygiene 165, chat-service frontend_tools 42, contract regen consistent.
- **H2 carry-forwards:** (1) **node-content titles — DONE** (folded in right after H2): a `nodeContent: Record<id,{title,status,tension,kind,chapterId}>` now threads PlanHubView→PlanCanvasProps→RF node data (usePlanWindows keeps the raw `SummaryNode` + exposes a `content` map; usePlanHub merges it with arc titles). Chapter/scene cards render real titles (story-order fallback), arc-rollups show the arc title + chapter count; `chapterId` is now on the canvas, which unblocks (2). (2) **H2.6 bus** (selection publish + editor active-chapter subscribe) + **camera focus (OQ-5)** — still open, now unblocked by (1)'s `chapterId`. (3) **multi-locale i18n** — only `en` added; other locales fall back until `scripts/i18n_translate.py` runs.
- **Phase H3/H4/H6 SHIPPED — the drawer, node decorations, and navigator rail (fan-out ∥ then serial integrate/verify/review).** **H3 drawer:** `PlanDrawer` (280px `absolute` overlay, self-hides on null selection) + `usePlanNode` controller (chapter/scene → `compositionApi.getNode`; arc/saga → the SAME `getArcs` shell cache, react-query dedupes; cast ids → names via `useGlossaryRoster` — all DOCK-2 reuse, no forks; arc-inspector 23-C3 not built → honest minimal summary + visible gap note). **H4 decorations:** `orderNodeBadges` = the ONE PH23 precedence home (canon>drift>threads>pacing>motif≤2>+N), `NodeBadges` row + `PacingSparkline`, wired onto Chapter/Scene/ArcRollup; canon deep-link is a graceful callback seam (`onOpenRef` unwired ⇒ plain chip, never a dead button). **H6 rail:** `PlanNavigatorRail` + `usePlanNavigator` (flatten arc shell, depth from the parent_id TREE not the trusted field, rank-ordered; row click = hub-focus, not editor-open). **Integrate:** `PlanHubPanel` now renders all three regions sharing ONE `view.selectedId` (rail `onFocusNode`→select, canvas click→select, drawer reads it; rollup node id === structure_node id so an arc selection resolves against the shell). **Verify:** FE tsc 0, vitest plan-hub+panels **606** + dockablePanelHygiene 165; go build/vet/unit green.
- **Adversarial `/review-impl` (5-concern fan-out → 2-skeptic refute-verify): 1 MED confirmed + fixed, 5 refuted 2/2.** **Fixed (MED, my H1 code):** glossary `entity-names` resolved display_name from `'name'` ONLY → every **`term`-keyed** entity (terminology/concept kinds) dropped from the badge name map; now mirrors `loadEntityDetail`'s `code IN ('name','term')` (prefer `name`), locked by a term-keyed row in the DB regression test (`entity_names_test.go`; env-gated — skips without `GLOSSARY_TEST_DB_URL`). **Refuted:** 2× "drawer/rail unreachable" (stale — skeptics read the now-integrated panel); canon NULL-`story_order` omission (from_order IS a timeline position — an unplaced chapter has no correct anchor, documented sparse design); canon deep-link inert (graceful `<span>` fallback, future-phase wiring); status-widening (intentional + already tested — a name map resolves all non-deleted).
- **Phase H2.6 bus + camera (OQ-5) SHIPPED.** **You-are-here:** `PlanHubPanel` subscribes the editor's active-chapter off the bus (`useStudioBusSelector(s=>s.activeChapterId)` — `focusManuscriptUnit` already publishes it, verified; no editor change), maps it to the CHAPTER node whose `chapterId` matches (kind-guarded so a scene can't shadow its chapter), and the card renders a distinct sky outline that composes with the selection ring (`data-here`). **Camera:** a rail row focus now pans the canvas — `focusNode` = select + bump a focus `seq`; `PlanCanvas`'s `CameraController` (inside `ReactFlowProvider`) calls `setCenter(node centre, {zoom})` on `seq` change (a legitimate sync-with-imperative-API effect; a missing node is a best-effort no-op). **Verify:** plan-hub vitest 54 (+ a mocked-RF camera by-effect test proving `setCenter` fires + the you-are-here data-here test) + studio panels 556 + hygiene 165, tsc + eslint 0. **Deferred (tracked):** (a) **publish `planHub.selection`** to the bus — no consumer reads a Hub-selection slice yet (chat/agent context reads only `activeChapterId`); building it now = a write-only value (gate #1: needs the chat-context seam). (b) **OQ-5 auto-expand-on-focus** — the camera pan is best-effort: it no-ops when the target isn't a rendered content node. In the DEFAULT all-collapsed view only the outermost (saga) rollup is a content node, so a **rail-row click on any descendant arc/sub-arc highlights the row + opens the drawer but does NOT pan** (the review round-2 flagged this — refuted as a shipping defect since the click still gives visible feedback, but it IS the OQ-5 gap). The fix is the same auto-expand-ancestors work as cold-open: focusing a node should expand its ancestor arcs so it renders, then pan. Needs the chapter_id→arc / ancestor-expand resolution (the shell is arcs-only; a chapter's `structure_node_id` isn't known until its window loads). The interactive pan for already-rendered nodes (this milestone) is the buildable slice.
- **Phase H5 Row-5 (scene-link closed-set) + H8.1 (perf EXPLAIN) SHIPPED.** **Row 5 (IN-2):** `composition_scene_link_create.kind` was a free `str` guarded only by the DB CHECK → now `LinkKind` Literal (the REST mirror already had it), a clean 422 instead of a 500 for a bad value from a weak model; new rejection test. **H8.1 (perf DoD, live-proven):** a DB-integration EXPLAIN test seeds 7.4k chapters (4k live under the target arc + 3k sibling-arc noise + 400 archived) and asserts `list_children_by_structure` rides `idx_outline_node_structure_keyset` (Index Scan, **no Seq Scan, no Sort**) — the by-effect proof that repeating `AND kind='chapter' AND NOT is_archived` VERBATIM matches the partial index. Ran green on a throwaway DB (`TEST_COMPOSITION_DB_URL`, dropped after); env-gated so it skips where that DB isn't set.
- **🔴 HIGH bug caught by the H1 route LIVE SMOKE + fixed (`composition-service` rebuilt on the dev stack):** the Hub's **read surface #1 (arc shell) returned the wrong shape** — `GET /books/{book_id}/arcs` (`list_arcs`, the shared BA11 Chapter-Browser route) served `{nodes: [raw structure_node]}` with **no derived block**, but the FE `getArcs` expects `{arcs: [ArcListNode]}` with `span`/`is_contiguous`/`chapter_count`. Against the real backend `data.arcs` was `undefined` → **the Hub canvas rendered NO lanes** even when arcs exist (unit tests missed it — FE mocks return `{arcs}`; the exact `new-cross-service-contract-needs-consumer-live-smoke` class). **Fix:** `StructureRepo.derived_blocks(book_id)` computes the span/count/contiguity for EVERY node in ONE recursive-CTE aggregate (no N+1, PH9); `list_arcs` attaches it additively (Chapter Browser ignores the extra fields); `getArcs` normalises `{nodes}`→`{arcs}`. **Live-proven through the gateway** with a seeded book (Saga=5 rolls up Arc-One=3 + Arc-Two=2; spans 1-5/1-3/4-5; the OQ-4 400 guard + plan-overlay/scene-links/children-summary all correct), then the seed was cleaned up. Locked by a `derived_blocks` integration test (incl. a non-contiguous arc). **This means the H2 canvas now actually renders its lanes against real data.**
- **Adversarial `/review-impl` round 2 (derived_blocks / H2.6 camera-bus / Row5 / H8.1; 3-finder fan-out → 2-skeptic verify): 0 confirmed, 3 refuted 2/2 + cheap hardening applied.** The `derived_blocks` recursive CTE is correct (each chapter binds to one leaf that appears once per root ⇒ no double-count, verified live saga=5=3+2; `is_contiguous` MEASURES `count(DISTINCT story_order)`, doesn't assume uniqueness; UNION-recursion terminates on any cycle); `getArcs`'s `?? []` can't mask errors (`apiJson` throws on non-2xx). Refuted findings, hardened anyway: (1) H8.1 EXPLAIN test now ALSO exercises the real `list_children_by_structure` (was a hand-copy → predicate drift could hide); (2) `derived_blocks` documented as deliberately live-only (archived nodes get the empty block in an `include_archived` view — intended); (3) rail-focus-can't-pan-collapsed-node folded into the OQ-5 deferral above.
- **Write-mirror audit for H5 (all REST routes EXIST — H5 is FE-heavy, not backend-blocked):** row 1 chapter→lane `POST /books/{book_id}/arcs/assign-chapters` (sets `structure_node_id`); row 2 arc move `POST /arcs/{id}/move`; rows 3-4 outline reorder/reparent `POST /outline/nodes/{id}/reorder` (fractional rank + OCC If-Match + scene story_order renumber). All OCC'd (If-Match → 412). NB: `reorder` groups siblings by `parent_id`, so it serves scene-within-chapter + scene-reparent; **chapter↔arc rebind is `assign-chapters` (structure_node_id), a separate route** — the FE drag must dispatch by node kind.
- **Phase H8.2 live browser smoke — PASSED ✅ (Playwright on `vite dev :5210` → gateway `:3123`, composition-service rebuilt, a SQL-seeded book, cleaned up after).** Opened `plan-hub` via the **command palette** ("Studio: Open Plan Hub" — the `ui_open_studio_panel` resolver + catalog row work live). The canvas rendered the seeded structure: **3 arc lanes** (Saga One / Arc One / Arc Two), the rollup card **"Saga One · 5 chapters"** and the **navigator rail** rows "Saga One 5 / Arc One 3 / Arc Two 2" — the exact derived `chapter_count`s, i.e. the read-surface-#1 fix confirmed **in the real UI** (0 console errors on load). Expanding Arc One **lazy-loaded its chapters via the children route** ("The Summons / The Road / The Gate", story order, real titles). Selecting a chapter **opened the H3 drawer**, which **degraded gracefully** to an honest "not found or not accessible" (the per-node `getNode` derives scope from the row's `project_id`→Work→grant — correct product behaviour; the SQL seed's fake `project_id` had no Work, so 404 — a seed artifact, not a bug; **no crash, panel stayed mounted**). The OQ-4 400 guard + plan-overlay/scene-links/children envelopes were all confirmed correct through the gateway earlier in the same session.
- **Phase H5 Row-1 (drag chapter → another lane = arc rebind) SHIPPED (FE).** `leafLaneAtY(lanes, y)` pure drop-target helper (the LEAF lane whose band contains the drop-y; non-leaf/gap → null); `api.assignChapters` (the `/arcs/assign-chapters` mirror — idempotent bulk set of `structure_node_id`, no OCC); `usePlanHub.moveChapterToArc` mutation (on success invalidates all `['plan-hub']` reads → shell/windows/overlay refetch → laneLayout re-places the card); `PlanCanvas` makes CHAPTER nodes draggable + `onNodeDragStop` resolves the target lane and fires `onMoveChapter` iff it's a DIFFERENT leaf arc. **RF v11 gotcha fixed (live-caught): a per-node `draggable:true` does NOT override a global `nodesDraggable={false}` — must set `nodesDraggable={canDrag}` and let the per-node flag select WHAT drags.** **Verify:** `leafLaneAtY` 4 unit + drag-handler 5 unit (mocked-RF: drop→target→onMoveChapter; same-lane/gap/non-chapter no-op) + plan-hub vitest 63, tsc/eslint 0. **`assign-chapters` mutation LIVE-PROVEN** through the gateway (moved a seeded chapter Arc-Two→Arc-One; DB `structure_node_id` + arc counts 3/2→4/1 changed, then reset). The node accepts a real drag-start (Playwright mousedown began an RF drag). **⚠ NOT yet live-verified: the end-to-end drag GESTURE → DB in an automated smoke** — d3-drag needs trusted pointer events the Playwright-MCP harness can't reliably deliver, and the lane bands are `pointer-events-none` (browser_drag can't drop onto them; synthetic PointerEvents don't drive d3-drag). Every LINK is proven independently; the composed gesture needs a **human/manual live-confirm** or a better drag harness. `node.position` (RF) and `layout.lanes.y` share the flow coordinate space, so the hit-test is coordinate-correct by construction.
- **Phase H5 Row-4 (drag a scene onto another chapter = re-parent) SHIPPED (FE) — the OCC path.** `chapterAtPoint(nodes, x, y)` pure drop-target (the CHAPTER card whose box contains the point; the box spans the chapter-ROW strip so a drop low on the card still lands; gutters/scene-row → null); `api.reorderNode` (the `/outline/nodes/{id}/reorder` mirror — server computes the fractional rank, **inherits the new chapter's `chapter_id`**, renumbers scene `story_order`, all in ONE txn) carrying **OCC via the `If-Match: <version>` header** (PH20/F-H3); `usePlanHub.moveSceneToChapter` picks `after_id` = the target chapter's LAST loaded scene (byte-order rank compare, matching the server's `rank COLLATE "C"`), sends the scene's `version`, and invalidates on **SETTLED** (success OR error) so a 412 **reloads the true state** — the SceneRail "changed elsewhere — reloaded" recovery, never a silent overwrite. `moveError` is surfaced in the panel (never swallowed). Division of labour: the CANVAS resolves only the target chapter; the CONTROLLER decides whether it's a real move (it owns the scene's parent + version), so a drop back on its own chapter is a no-op. **Verify:** `chapterAtPoint` 5 unit + scene-drag handler 5 unit (target resolve · own-chapter still reports · gutter no-op · kind routing · read-only) + plan-hub vitest **73**, studio panels 556, tsc/eslint 0. **Both mutation paths LIVE-PROVEN** through the gateway on a seeded book **with a real `composition_work` row**: reorder with `If-Match: 1` → 200, `parent_id`→c2, `chapter_id` **inherited** (c2's), version 1→2; replaying the **stale `If-Match: 1` → 412 `NODE_VERSION_CONFLICT`** with the `current` row in the body — exactly what `moveError` recovers from. Seed cleaned up.
- **Phase H5 Row-2 (drag an arc BAND = move it in the structure tree) SHIPPED (FE).** `bandAtY(lanes, y)` pure drop-target (the INNERMOST band containing y — bands NEST, so a drop over a nested arc targets that arc, not its wrapping saga; the saga still wins in its header strip / the inter-arc gap). The band body stays `pointer-events-none` (the pane must still pan through it), so React Flow starts the drag ONLY from the header via `node.dragHandle` (`.plan-lane-handle`, `cursor-grab`). **Only ARC bands drag — a saga is never draggable** (the server rejects a parented saga, so the affordance would only ever fail). `api.moveArc` → `/arcs/{id}/move`; **no OCC** — a structural move is guarded by the DB's constraints, not a row version. **The nest-vs-sibling DECISION lives in the controller** (it holds the shell's `parent_id`/`rank`): a drop on a saga or a parent arc **NESTS** under it (appended as its last child, byte-order rank); a drop on a **LEAF** arc makes the dragged arc that leaf's **next SIBLING**. A client cycle guard skips the pointless call when dropping an arc into its own subtree. **Verify:** `bandAtY` 3 unit + arc-band drag 5 unit (target report · self no-op · off-band no-op · prefix routing · read-only) + plan-hub vitest **81**, studio panels 556, tsc/eslint 0. **LIVE-PROVEN** through the gateway: nesting Arc Two under Arc One → 200 with **`depth` recomputed to 2**; the cycle (Arc One under its own now-descendant) → clean **400 `STRUCTURE_CONSTRAINT`** (never a 500) → `moveError`. Seed cleaned up.
- **`/review-impl` on the three H5 rows — 2 HIGH + 5 MED/LOW fixed; the drag DID NOT WORK end-to-end (`24eae5934`).** Unit tests passed straight through both HIGHs, and the live smoke had hidden them by hand-seeding. **HIGH-1 — the moved card never left its old lane:** the moves invalidated the react-query reads, but the chapter/scene WINDOWS are hand-rolled state (`usePlanWindows`), so `invalidateQueries` could not reach them — and they hold exactly the rows a move mutates (`structure_node_id`/`parent_id`/**`version`**). The card kept its pre-move lane forever (the write looked silently ignored while the rollup count moved), and the scene's stale version 412'd the very next move of the same node. Fixed by `usePlanWindows.reload()`, called with the invalidate on every settle. **HIGH-2 — the card never moved under the cursor:** a controlled React Flow (`nodes` prop) with **no `onNodesChange`** never applies a drag to its store, so the user dragged, saw nothing, released, and a write fired. Fixed with `useNodesState` + reset from `laneLayout` on layout change and at drag stop (which IS the snap-back the old comments claimed). **HIGH-3 — hit-tests probed the dragged node's TOP-LEFT with RF's default `nodeDragThreshold: 0`:** a 13px nudge up rebound a chapter to the lane above while the card still looked inside its own; a **1px twitch on a scene card re-parented it under the neighbour AND renumbered two chapters**. Fixed: the drop target is now resolved from the **CURSOR** (`screenToFlowPosition`) + a 5px threshold — cursor targeting is also inherently no-op-safe (the cursor starts inside the dragged element's own region). **MED/LOW:** arc move sent `after_id === itself` when dropping an arc on its own parent (⇒ a 400 explaining the wrong rule); the scene append position was read from a window that is EMPTY in the common case (the target chapter is collapsed) so `after_id=null` made the server **PREPEND** the scene and renumber the chapter — it now asks the server for the true last sibling; the error banner never cleared; a 0-row assign reported success; a second drag is now blocked while a move is in flight. Mutations extracted to `hooks/usePlanMoves.ts` (there were **no controller tests at all** — now 14). Standards gate: the new write routes DO grant-check, but nothing would have gone red if the gate were deleted → `tests/unit/test_arc_hub_routes.py` (VIEW→403 / NONE→404 / missing→404, repo never called) + the derived-block attach.
- **The drag GESTURE is now LIVE-PROVEN ✅ (the automation gap is CLOSED).** Playwright's **CDP mouse events are trusted**, which is what d3-drag requires — `page.mouse.down/move(steps)/up` drives a real React Flow drag (the earlier `browser_drag`/synthetic-PointerEvent attempts were the wrong tool, not a real limitation). Full loop on a seeded 2-arc book: card transform `24,16 → 26,20 → -27,199.5` (**it drags**) → `POST assign-chapters` → **Arc Beta rollup 1→2 chapters, Ch One gone from Arc Alpha**, ⚠ non-contiguity chip appears, DB confirms the rebind. A **2px twitch fires ZERO writes** and snaps back exactly. 0 console errors. Seeds cleaned up.
- **The chapter READING AXIS was never written — the Hub's x-order was UUID order (`7c8a8a487`).** Found while scoping Row-3. `_insert_decomposed_tree` passes `story_order` for the scenes but **not for their chapter**, and it is the only chapter-creation path in the service ⇒ **every chapter node ever persisted has `story_order` NULL**. Three live consequences, none caught by a test (the fixtures hand-seeded the field production never writes): the plan-overlay **canon anchor join** (`chapter.story_order = canon_rule.from_order`) could never match ⇒ a chapter could not carry a canon badge at all; the arc's derived **span/BA6 contiguity** was unresolvable; and the FE coerced NULL→0, tying **every** chapter at order 0 so laneLayout's x-sort fell through to the id tiebreak. Fixed: write the chapter at its own slot on the axis it already shares with its scenes and the canon-rule windows (`chapter_sort * STRIDE` = exactly its scene 0) + a **boot backfill** recovering existing rows' positions from their scenes (a scene-less chapter stays NULL — unknown, never guessed as 0). That exposed an older bug: the axis is **STRIDED**, so adjacent chapters differ by 1000 and both contiguity checks did `+1`/`max-min+1` arithmetic on it ⇒ with real data **every arc reads non-contiguous and every lane renders segmented**. BA6 non-contiguity actually means *another arc's chapters interleave* — a hole in the lane — so both sides now decide it **positionally** (`dense_rank` server-side; slot adjacency in laneLayout), which is **stride-agnostic**. A live browser check then caught a bug the fix introduced: `span` was BOTH displayed in the drawer ("chapters 1–3" — wants the ordinal) AND used as the rollup's sort key (must be on the cards' RAW axis) ⇒ the rollup sorted at position 4 against chapters at 1000 and landed at slot 0. Split into **`span`** (display ordinal) + **`first_story_order`** (raw sort key) — one field, one job. **LIVE A/B on identical data:** old code `span=1000..3000 contiguous=False` → new `span=1–3 contiguous=True`; canvas order Ch One(24)→Ch Two(168)→Ch Three(312)→Arc Beta rollup(456, correctly last).
- **H5 Row-3 SHIPPED — the deferred "infrastructure" was BUILT, not carried (`27fd52641`).** The last PH20 row, and the only one that crosses a service seam: the Hub's x-axis IS the book's reading order, which **book-service owns**. **book-service `POST /v1/books/{id}/chapters/reorder` (NEW):** a reorder was *impossible* through the existing PATCH — `idx_chapters_unique_slot_lang_active` is a partial UNIQUE on `(book_id, sort_order, original_language)`, so moving chapter 5 into slot 2 collides with whoever holds slot 2 → 409. A permutation cannot be written row-by-row against a non-deferrable unique index, so it goes in **TWO statements whose target sets are disjoint from their sources**: negate every slot, then write the dense 1..N. `FOR UPDATE` on the language track serializes concurrent reorders — which is why **no `version` column is needed** (this is a whole-sequence rewrite, not a field edit). **composition `POST /books/{id}/chapters/reorder` (the single entry point):** calls book-service, then rebuilds the mirror — chapter slots, their scenes, **and the `canon_rule` anchors** (`from_order`/`until_order` are positions on this very axis with **no node FK** — the story timeline IS their only anchor — so a renumber that ignored them would silently re-point a rule at whatever chapter now sits in the old slot). Both halves idempotent ⇒ the retry a `502 MIRROR_RESYNC_FAILED` asks for converges. **Also fixed on the way:** `_renumber_scene_story_order` renumbered a chapter's scenes to a chapter-LOCAL `0..n-1` while `plan.py` writes them as `chapter_sort*1000 + i` — **two conventions on one column**, and the Row-4 scene drag fired the wrong one, collapsing scenes onto the same low integers as every other chapter's. **FE:** a chapter dragged WITHIN its lane is a reading-order move (a DIFFERENT lane stays Row-1); the controller **REFUSES** to move a chapter past a collapsed arc (its hidden chapters cannot be named to the server, and falling back to the last loaded chapter would place it BEFORE them — a silent wrong move on the real manuscript). **LIVE-PROVEN:** Ch One dragged past Ch Three → manuscript `1 Ch Two / 2 Ch Three / 3 Ch One`, mirror `1000/2000/3000` matching, and the **canon anchor moved 1000 → 3000 — it followed its chapter.**
- **Optimistic re-place + one-level UNDO (`23bf01642`) and OQ-5 auto-expand (`29004dffd`) — the last two polish defers, CLEARED.** Optimistic: `usePlanWindows.patch()` re-places the card the instant the drag ends (display-only; the settle reload overwrites it, so a FAILED move rolls itself back for free). Undo: the inverse is captured BEFORE the write from state we already hold — the server's answer no longer knows where the node came from. One level, not a stack (a deep stack would let a user walk back through writes later work already built on). **Found while testing:** the Row-3 no-op guard compared against the LOADED chapters, so a chapter whose predecessor sits in a collapsed arc looked "already first" and the drag was **silently swallowed** — a false no-op, strictly worse than the redundant idempotent write it was avoiding; the check now runs against the book's own order. OQ-5: an arc under a collapsed ancestor isn't drawn at all, so a rail click had **nothing to pan to** — focusing now opens the ancestors first, and the camera waits for the node to appear (latched once per request). **LIVE:** drag → Undo → both the manuscript and the mirror reverted, 0 console errors.
- **~~▶ NEXT: H5 Row-3 is DEFERRED~~ — SUPERSEDED, see above. The original deferral reasoning is kept for the record:** Rows 1/2/4/5 ship and are live-proven; Row-3 (reorder a chapter *within* its lane) is **not a drag handler** and must not be built as one — it is a **manuscript reorder**, and three gaps stack: (a) **book-service has no transactional chapter reorder** — `sort_order` is writable only via the generic `PATCH /v1/books/{id}/chapters/{id}` (single-row, no OCC), and the partial `UNIQUE(book_id, sort_order, original_language) WHERE active` index makes a swap/shift **structurally impossible** through it (a same-language book 409s), so it needs a NEW `POST /chapters/reorder` (one txn, renumber the run, dodge the unique index) plus a `version` column chapters don't have; (b) **no book→composition sync seam exists** (composition consumes only its own job queue — zero book/chapter event consumers), so a book-side reorder would not re-derive the composition `story_order` mirror; (c) **`canon_rule` is anchored on `story_order` with no node FK**, so any renumber silently re-anchors or orphans canon rules — a correctness decision, not a polish item. That is a spec, not an edit. **The prerequisite (Gap A: chapter `story_order` was never populated) is now FIXED and shipped** — see above. Remaining polish: **optimistic re-place** (avoid the brief refetch snap) + **undo** via `_meta.undo_hint`. **Live-smoke recipes (both proven):** insert a `composition_work` row (project_id→book_id, created_by=test user) FIRST or every by-id route 404s on the grant resolve; and the book must exist in **book-service** (the grant resolves through it) — a fabricated `book_id` 404s. **Drive drags with `page.mouse` (CDP/trusted), never `browser_drag` or synthetic PointerEvents.** H7 view-modes deferred (P-10). Remaining i18n: only `en` for `plan-hub` + `planNav`; run `scripts/i18n_translate.py`.
- **▶ NEXT: PLAN HUB v2 (spec 24) — the H5 interaction surface is COMPLETE and every Plan-Hub deferral is CLEARED.** All five PH20 rows ship and are live-proven with a real trusted-event drag; optimistic re-place, one-level undo, and the OQ-5 camera are in. **Recently cleared:** `D-PLANHUB-ROW3-CHAPTER-REORDER` (built the book-service reorder + the mirror/canon resync rather than carrying it); `D-PLANHUB-SCENELESS-CHAPTER-POSITION` (the resync pulls positions from book-service directly, so a scene-less chapter now gets its slot — any reorder repairs the whole book, and new chapters always get one at commit); `D-PLANHUB-OPTIMISTIC-REPLACE`; `OQ-5 auto-expand-on-focus`; the drag-gesture "needs a human confirm" caveat (**`page.mouse` = CDP = trusted events**, which is exactly what d3-drag wants — `browser_drag`/synthetic PointerEvents were the wrong tool, not a real limit); and plan-hub i18n (all 17 locales). **Still open, deliberately:** (a) **publish `planHub.selection` to the bus** — a **won't-build until a consumer exists**: nothing reads a Hub-selection slice today (chat/agent context reads only `activeChapterId`), so building it now is a write-only value, which is itself the bug class this repo bans. (b) **H7 view-modes** (P-10, its own phase). (c) A **React Flow mount-frame warning** ("parent container needs a width and a height") — cosmetic and pre-existing: dockview sizes the panel a frame after mount, and the container then measures ~2920×666 and renders correctly; a fix would mean gating the canvas mount on a ResizeObserver, which is real risk for a benign warning. **Next phase: 26/28, or H7.** **Live-smoke recipes (all proven):** seed a `composition_work` row FIRST (else by-id routes 404 on the grant resolve); the book must exist in **book-service** (the grant resolves through it); drive drags with `page.mouse`, never `browser_drag`; and **rebuild + `--force-recreate`** before believing a live result (a stale image read as a false green once this session).

**BOOK-PACKAGE — the two "clear legacy" carry-forwards from Deploy 2 are CLOSED, 2026-07-11** (spec 25 M4/M5; branch `feat/context-budget-law`; composition-service only, one atomic commit).
- **Legacy decompose window (the live 500) — FIXED.** The A3 decompose-commit + arc-materialize paths minted a `kind='arc'` OUTLINE_NODE as the arc container, which the post-lift `outline_node` kind CHECK REJECTS on a lifted DB → both routes 500'd on the one live DB. Now `_insert_decomposed_tree` creates a `structure_node` arc (kind='arc') and links chapters via `outline_node.structure_node_id` (parent_id NULL) — the M4 shape + spec-27 link step; this also ACTIVATES the arc lens for decompose content. `book_id` threaded through `commit/create_decomposed_tree` from `work.book_id`; the replace-sweep now archives the emptied `structure_node` arc (scoped via the structure_node_id link, book-scoped). Base `outline_node` CHECK deliberately KEPT allowing 'arc' so the arc-lift TEST can still seed legacy arcs (M5 tightens it on real lifted DBs). **Verify:** 1727 unit + 241 DB-integration + 95 repo green + a new regression test (zero arc outline_nodes minted; arc lives in structure_node); adversarial 6-concern workflow review → **0 confirmed, 2 refuted**.
- **BA10 vocab rename — the RISK closed, the cosmetic rename DEFERRED (gate #2/#5).** `arc_template` DB columns are renamed tracks/roster; every reader ALIASES them back to the API field names threads/arc_roster (a deliberate, documented bridge — contract stable). Audited: ALL `FROM arc_template` readers alias consistently → **no residual bug**. The full vocab rename across Pydantic/MCP/contract/FE (~95 occ / 32 files) is breaking, zero-functional-benefit, and touches the exact FE surface (ArcApplyPreview/ArcTimeline/ArcTemplateLibrary) spec 24 reworks → deferred to **24/28** (the prior recommendation). What WAS closed now: `retrieve_arcs` — the one reader that lacked a DB test, the path this session's motif_retrieve 500 hit — gains a DB integration guard-by-EFFECT (`test_arc_template_repo.py`), red-first proven (`UndefinedColumnError` when the alias is dropped).

**TRACK D COMPLETION — the two liveness proofs the track exists for are now TAKEN, 2026-07-11** (branch `feat/context-budget-law`). A completeness audit found Track D's *metadata+gate+sweep* half was solid (0 broken) but the two actual proofs were never done — and the reused "WS-D5" number hid the frontend-tools deliverable. Spec: [`docs/specs/2026-07-09-mcp-tool-liveness-eval/TRACK-D-COMPLETION.md`](../specs/2026-07-09-mcp-tool-liveness-eval/TRACK-D-COMPLETION.md). All four phases done this session:
- **WS-D6 · flagship S06 — PROVEN.** Stack rebuilt to HEAD; S06 re-run on local gemma: **`effectful_tool_calls>0` in 4/5 warm trials + `persist_claims_without_write==[]` in 6/6**, DB-verified as real `plan_run` rows (model-synthesized premises). The baseline's founding failure (0 tools + "I locked it into the core" lie) is reversed. Report: [`2026-07-11-S06-flagship-rerun.md`](../eval/discoverability/2026-07-11-S06-flagship-rerun.md). DoD #5 met (D-side of N3; full go/no-go still needs Track C).
- **WS-D5 · frontend tools (the REAL one) — DONE.** G3 all-12 (BE 21 + FE pure-resolver). G4 live-browser: new `frontend/tests/e2e/specs/frontend-tools-liveness.spec.ts` + `helpers/frontendToolInject.ts` — **4 passed**, injecting a suspended frontend-tool call via canned AG-UI SSE so the REAL FE executor/resolver/card + `/tool-results` resume run deterministically (both executor paths; the other 8 share them). The FE-tools proof needed the 0-message-session NULLS-LAST fix to activate the chat.
- **WS-D4 · capability sweep 62 → 13 null, 0 broken.** Reached **$0** via authored args + creator chains + $0 DB seeds + a pre-sweep `seed_chain_extras` (2 KG nodes + a 2nd composition project with 2 nodes/archived-node/motif + a user-tier motif pair): arc family (8), authoring-run (6), plan_* (4), glossary book-standard (4), book steering, jobs (3), the **kg build chain** + **kg node-chain** (propose_edge/triage/entity_edge_timeline/adopt_template) + kg_create_node, scene/outline chains, motif bind/unbind + link pair, kg_world_query + book_scene_get + 5 translation-version tools — all leak-verified in teardown (`world/translation/motif: ok`). Manifest regenerated (`211 executes:true · 0 false · 13 null`, 224 catalog, 2 service copies byte-identical). **The 13 residue are ALL genuine WAIVES** (browser-JWT ontology graph_schemas ×3 / real async job ×2 / bespoke multi-FK seed ×4 / pre-existing draft ×1 / paid+cross-service ×3). CD4 stays reject-on-`executes:false`. **Both prior caveats CLEARED** (needed `kg_create_node` deployed — rebuilt knowledge-service + ai-gateway).
- **Bookkeeping:** WS-D5 number-collision resolved (WS-D5a=description follow-up; WS-D5=frontend tools) in TRACK-D.md; BOARD ND3 → ✅(redefined per WS-D5c), N3 → 🔄(D-side ✅, blocked on C). **`/review-impl` found + fixed 3 bugs:** dead world-seed (`worlds` PK is `id` not `world_id`), a FE-spec session leak, a redundant teardown ternary. **Gateway prefix-drop test BUILT** (`scripts/eval/tool_liveness/tests/test_federation_prefix.py`) — the general Track-A catch (each provider's own tools/list vs the federated catalog; passes live across all 5 providers), closing the gap the concurrent book-service-scoped test left.

**TRACK B COMPLETENESS AUDIT + REMEDIATION — the "CLOSED / all defers cleared / W10 backend COMPLETE" claims were overstated; audited and fixed, 2026-07-11** (branch `feat/context-budget-law`). A 6-dimension adversarial audit (grounded in code, refute-verified — 13 agents) confirmed the Track-B MCP-tool spine genuinely shipped and is correctly wired, but graded the backend **~85% against its OWN sign-off**: 4 real open items + 1 unproven surface, NOT "all defers cleared." **Zero HIGH findings** (nothing broken); everything was short-of-signoff, latent, or unproven. All four addressed this session:
- **R1 discoverability (`695aa5f64`).** `world_*`/`world_map_*` reached the federated catalog but were NOT group-enumerable — no `world` key in `GROUP_DIRECTORY` on EITHER surface, so `find_tools(group=…)`/`tool_list(category=…)` excluded all 9 and they fell out of the `book` category (discoverability is Track B's core concern). Added the `world` group (ai-gateway `find-tools.ts` + chat-service `tool_discovery.py`, lockstep) + a book-service `tools/list` prefix-enforcement test that drives the REAL in-process catalog and asserts every tool matches a book-provider prefix — closes the C-GW drop class that silently ate `story_search`/`world_*`/`lore_*` three times (specs only guarded the map, not the tools).
- **R2 maps finished (`54cf2e435`).** The maps deliverable fell short of its §7.1 "full: image+pins+regions" sign-off (no image write path, no delete/undo). Added `POST /internal/worlds/maps/{map_id}/image` (server-side MinIO upload, owner-scoped by `?user_id`, records `image_object_key` + dims), optional `image_ref` on create, resolved `image_url` on get/list, and `world_map_delete`/`world_map_remove_marker`/`world_map_remove_region` (Tier-A, owner-scoped, CASCADE + best-effort blob cleanup). Restored the accurate "reversible" wording. Live-proven round-trip (image_ref storage + URL, owner-scoped removes, CASCADE-on-delete, re-delete-not-found).
- **R3 verification (`d91ae13a0`).** ~384 glossary + ~66 book DB round-trips SKIPed for lack of `*_TEST_DATABASE_URL` and NO CI set them → green-by-skip, not green-by-proof. New `.github/workflows/domain-db-smoke.yml` spins an ephemeral `postgres:18-alpine` (schemas need PG18 `uuidv7()`) + runs both api suites with the env set (locally proven green first: book 5.3s, glossary 115s/652 tests/0 skip).
- **R0 truth-drifts (folded into `695aa5f64`).** `anchor_loader.py` WARNING/comments named the DROPPED `entity_glossary_id_unique` + asserted it was GLOBAL (corrected to `entity_glossary_fk_unique`, project-scoped); the `mcp_maps.go` header promised a delete tool that didn't exist yet.

**Residuals — the two optional polish items are now CLOSED (R5); the remaining two are not Track-B defects:** ✅ **(1) DONE (R5):** `proposeNewEntity` now returns the caller's supplied attribute codes on `skipped_exists`/`skipped_tombstoned` (was `nil`), so `attributes_skipped` surfaces what didn't land instead of silently dropping it — the weak-model signal to reapply via `glossary_entity_set_attributes`. ✅ **(3) DONE (R5):** the map image-upload handler now sweeps the orphaned prior object best-effort when a format-changing re-upload changes the deterministic key. **Not Track-B defects (left as-is):** (2) `glossary_confirm_action` doc-drift belongs to **Track A** (a chat-service FRONTEND tool, not a Track-B file) — action it under A or record an explicit won't-fix so it stops re-surfacing; (4) `world_map_delete` is Tier-A (no confirm) — a deliberate design choice, consistent with the owner-only/no-sharing world+map surface (blast radius = one re-creatable map).

**W11-M1 SHIPPED — reader spoiler-cutoff wiring (reading-position resolver + RAG cutoff), 2026-07-11** (branch `feat/context-budget-law`). Spec: [`docs/specs/2026-07-11-w10-w11-world-container-and-reader-backends.md`](../specs/2026-07-11-w10-w11-world-container-and-reader-backends.md) §4.1/§4.3. First milestone of the W10/W11 autonomous build (order: W11-M1→M2→M3, then W10-M1→M2).
- **book-service** — `GET /internal/books/{book_id}/reading-position?user_id=` → `{furthest_chapter_id, furthest_sort_order}` = furthest **active** read chapter (`analytics.go`). Internal-token; the reader's own row (no grant needed).
- **knowledge-service** — `raw_search` gains `before_chapter_id`; `spoiler_window.resolve_before_sort_order` (fail-closed -1); `run_hybrid_search` windows each leg **before fusion** on its None-preserving chapter source.
- **Adversarial review (5-dim workflow → refute-verify) caught 1 HIGH + 4 MED/LOW, all fixed:** (1) **HIGH fail-OPEN** — `passage_to_hit` coerces an unknown `chapter_index` (None) to `sortOrder 0`; a canon passage that was un-ordered at publish (book-service returned `{}` for sort_orders — a documented state) would surface for every reader as "chapter 0". Fixed by windowing raw passages on the None-preserving `chapter_index` per-leg (drop unknown + future). (2) **MED correctness** — the reading-position JOIN missed `lifecycle_state='active'`; chapters are SOFT-deleted, so a soft-deleted chapter could be returned as the cutoff. Fixed + live-verified against real PG. (3) MED/coverage — added book-service DB tests (`analytics_db_test.go`, live-verified) + the raw_search endpoint-seam tests. (4) LOW — the resolver now distinguishes `pgx.ErrNoRows` (silent null) from a real DB error (logged, still fail-closed null).
- **Verify:** book-service API suite green + 4 reading-position DB tests PASS live (`BOOK_TEST_DATABASE_URL`→:5555); knowledge **3750 passed** (+5).

**W11-M2 SHIPPED — reader ask-the-lore facade, 2026-07-11.** Four Tier-R MCP tools (`lore_ask`/`lore_browse_entities`/`lore_entity`/`lore_timeline`) in `app/tools/reader_tools.py`, wired across all three schema sources (shim + ARG_MODELS + TOOL_DEFINITIONS; drift test 32→36). The spoiler cutoff is SERVER-enforced from the reader's OWN furthest-read chapter (there is no `before_chapter` arg), all reads resolve-to-owner after a `book_id≥VIEW` grant, fail-closed everywhere. **Adversarial 5-dim facade review (refute-verified) → 4 CONFIRMED (2 HIGH, 1 MED, 1 LOW), all fixed:** (1) **HIGH** glossary-id vs KG-id mismatch made `lore_entity` return empty for EVERY entity (browse→inspect silently dead) → `resolve_kg_entity_id_by_glossary_id`, project-scoped; (2) **HIGH** `kind` filter read `kind`/`entity_kind` but the glossary row serializes `kind_code` → fixed; (3) **MED** glossary default `recency_window=100` dropped long-absent entities from the "whole cast" → `recency_window=0` (spoiler cutoff only); (4) **LOW** `list_facts_for_entity` wasn't project-scoped (cross-book fact exposure to a VIEW-grantee via an out-of-band id) → added `project_id`; plus a `book_client`-None guard mirroring `story_search`. **Verify:** knowledge **3772 passed** (9 reader tests: fail-closed null→empty · anti-oracle · resolve-to-owner · glossary `+1` inclusion · `kind_code` · `recency_window=0` · project-scoped facts · no-KG-anchor honest empty).

**W11-M3 SHIPPED — public/anonymous canon-only lore route, 2026-07-11.** `GET /v1/sharing/unlisted/{access_token}/lore` (sharing-service, no auth — anonymous, gated only by the secret unlisted token). Resolves token→book_id (bad/non-unlisted → 404 anti-oracle) + lifecycle guard, then calls glossary internal `known-entities` with an **EXPLICIT `status='active'`** (canon-only, NOT the implicit link-absence) + `alive=true&min_frequency=1`. Self-declared `?before_chapter=N` cutoff (glossary exclusive `<` → N+1). **Adversarial 4-dim review (refute-verified) → 5 CONFIRMED, all fixed:** (1) **HIGH** the feature was DEAD + the test LIED — glossary `known-entities` returns a BARE JSON ARRAY but the consumer decoded an object → always empty; the canon-only test mocked a fictional `{entities,count}` object (mocked-client-hides-shape) so it passed against a shape production never emits. Fixed: decode `[]`; test mocks the real bare array. (2) **MED** `getKnownEntities` omitted `deleted_at IS NULL` — soft-delete is a pure `SET deleted_at` (keeps status/alive/links), so an author-DELETED `active` entity would leak publicly. Fixed for ALL callers + live DB test. (3) **LOW** malformed/negative `before_chapter` → now **400** (never dump full canon on a typo). (4) **LOW** dead 503 branch removed. (5) **MED** default (no cutoff) serves whole published canon — accept-and-documented (the unlisted link already exposes full book TEXT; `windowed:false` signals the UI). **Verify:** sharing-service suite green; glossary api suite green incl. 2 live DB tests (happy-path + soft-delete-excluded).

**W10-M1 SHIPPED — world write surface + kg_create_node, 2026-07-11** (`b07fcb85b` + `7db8c1f7d`). book-service world MCP tools `world_create`/`world_get`/`world_list`/`world_move_book` (owner-scoped, no E0 sharing; create/move Tier-A DIRECT — the kg_project_create analog, NOT the Tier-W confirm spine; shared `createWorldCore` provisions world + hidden bible book + chapter, HTTP `createWorld` now reuses it) + internal `GET /internal/worlds/{id}/bible` (world→bible resolution for world-native lore authoring). knowledge `kg_create_node` (Tier-A, manual single-node create — the W4 "no manual node" blocker; unblocks `kg_propose_edge`; runs as owner, EDIT grant). **Adversarial 3-dim review → 1 HIGH + 1 LOW + 1 COSMETIC, all fixed. The HIGH is important:** ai-gateway federation DROPS any tool not matching its provider's prefix (C-GW gate); `book` allowed only `book_`, so ALL `world_*` were silently dropped — AND the SAME gate had silently dropped the already-shipped W11-M2 `lore_*` tools (knowledge allowed only `memory_`/`kg_`/`story_`). Fixed BOTH in `EXTRA_PREFIX_MAP` (`book:['world_']`, `knowledge += 'lore_'`) + `providers.spec` assertions. LOW: `world_move_book` swallowed the ownership-check DB error → now distinguished. **Verify:** book-service api suite green (world DB tests live); ai-gateway providers.spec 14 + tsc clean; knowledge 3778 (kg_create_node: create/anti-oracle/resolve-to-owner). **⚠ Enforcement gap (follow-up):** nothing auto-catches a future MCP tool registered with a prefix its provider doesn't allow (the class that dropped `world_*`/`lore_*`/`story_search`) — providers.spec only guards the map, not the tools. A `tools/list` integration test asserting every tool matches its provider prefix would close it.

**W10-M2 SHIPPED — maps primitive, 2026-07-11** (`f1871835c`). **▶▶ ALL 6 W10/W11 MILESTONES SHIPPED** (W11-M1/M2/M3 reader journey + W10-M1/M2 world container, each with a mandatory adversarial review). ⚠ **A later completeness audit (see the TRACK B block at the top) found the "backend COMPLETE" framing overstated** — the maps image UPLOAD path + delete/undo tools were NOT actually shipped here; they were finished 2026-07-11 in R2 (`54cf2e435`). book-service `world_maps`/`map_markers`/`map_regions` tables (world_id-scoped; `x/y DOUBLE PRECISION [0,1]`; polygon JSONB; CASCADE world→maps→markers/regions; the G1-lock test scoped to `books` so `world_maps.world_id NOT NULL` doesn't false-match) + 5 `world_map_*` MCP tools (create/add_marker/add_region/get/list; owner-scoped; `world_` prefix federated). **Adversarial 3-dim review → 1 MED + 2 COSMETIC:** MED (fixed) — `world_map_get` swallowed marker/region sub-query + row errors (silent-success: a transient DB error dropped a map's pins as an authoritative empty result); COSMETIC (fixed) — removed the "Reversible" over-promise (no delete tool yet); COSMETIC (accepted) — a degenerate polygon stores faithfully (spec-faithful GIGO). **Verify:** book-service api + migrate suites green; map DB round-trip live (create→marker→region→get + owner-scoping). **▶ FOLLOW-ONS:** (1) the MinIO image UPLOAD REST + `world_map_delete`/`remove_marker`/`remove_region` tools → **DONE 2026-07-11 (R2 `54cf2e435`)**; (2) the enforcement-gap `tools/list` prefix test → **DONE (R1 `695aa5f64`)**; (3) `D-WS4C-EFFECTIVE-VALUE` remains cleared. **Track C** owns all W8/W10/W11 SURFACES (onboarding fork, world-container UI, reader UI, map canvas) + the W1–W12 workflow objects — the backends they consume are now shipped.

**Chat & AI settings — the SESSION half of G1 shipped (the chat GUI is unified), 2026-07-10** (branch `feat/context-budget-law`). Spec: [`docs/specs/2026-07-05-chat-ai-settings.md`](../specs/2026-07-05-chat-ai-settings.md). Four milestones, two commits.

- **The foundation was broken, and that's why the UI never existed.** `chat_sessions` had `grounding_enabled` / `voice_overrides` / `context_overrides`; the effective-settings resolver READ all three and the turn consumed `grounding_enabled` — but **nothing could write them**. `PatchSessionRequest` never declared the fields, so Pydantic's `extra="ignore"` accepted the keys, dropped them, and returned **200**. The Session tier of `System → Account → Book → Session` was permanently NULL. Fixed (`d524e1e60`) with the 3-state contract (omit / explicit `null` = clear-to-inherit / value, read from `model_fields_set` — an `is not None` write path can turn an override ON but never back to inherit), one shared `apply_patch` deep-merge for both write doors, and the closed-set enum registry moved out of the account router into `settings_resolution` (the session row is a **second write door** onto settings the turn consumes; a bad `context.mode` would have stored fine and been read as `auto` by every consumer).
- **The chat panel predated the cascade.** `SessionSettingsPanel` never called the resolver and seeded itself from **client-side literals** — `temperature ?? 0.7`, `top_p ?? 0.9`. Those are not the system defaults (the backend's `_SYSTEM_BEHAVIOR` holds only `reasoning_effort` + `permission_mode`); the request went out with the field UNSET and the provider picked its own. Two different numbers, one of them on screen. It now reads the cascade, shows a `TierChip` per row, and offers **"clear · inherit *X*"** keyed on `source_tier`, **never on value-equality** (setting temperature to exactly your account default is still "set here", and must stay clearable). An unset sampling param renders *"Not set — the provider's own default applies"*.
- **Voice had two account stores that never spoke.** Settings → Chat & AI → Voice wrote `user_chat_ai_prefs.voice`; the chat `VoiceSettingsPanel` wrote `lw_voice_prefs`/`voice_prefs`, and **the voice runtime reads the second one** — so picking a TTS voice in the unified panel changed nothing you could hear. `voiceBridge.ts` reconciles them (spec §7.1 MIG-4 dual-write, both directions, shared leaves only) and normalizes a vocabulary split: the account panel wrote `tts_source: 'user_model'` (the *model-source* axis) for what the voice store calls `'ai_model'` (the *audio-source* axis).
- **Also:** `VoiceSettingsPanel` folded in as the panel's Voice **section** (`embedded` prop — two stacked `fixed` slide-overs would fight for the right edge and steal the click-outside handler); the mic button deep-links to it. The "6-vs-4 preset lists" became one `PROMPT_PRESETS` — they had diverged in keys, capitalisation *and* prompt text, so the prompt a new chat was seeded with was not the prompt the settings panel showed under that name.
- **Found by the live smoke, fixed:** `MultiProjectPicker` defaulted to `limit=200` against a route that caps at `le=100` → a silent **422**, so the knowledge-graph picker had been listing **nothing**.
- **Verify:** chat-service **1377 passed**; FE **117 files / 902 tests**, `tsc --noEmit` + eslint clean. **Live smoke (BE)**: baseline `grounding=True/system`, `context.mode=auto/account` → PATCH → both `source_tier=session` → deep-merge keeps siblings → bad enum 422 and does not leak into storage → explicit null clears back to exactly the baseline tiers. **Live smoke (browser, real gateway)**: temperature shows "Not set" with no slider; grounding chip `system` → toggle → `session` + "clear · inherit on" → full reload → **still** `session` → clear → back to `system`. Zero console errors.
- **`/review-impl` (`8d19aaa73`) — 2 HIGH + 3 MED/LOW, all introduced by the work above, all red-first then fixed:**
  - **HIGH-1, cross-session write.** `useSessionSettingsEditor.send()` PATCHed `latest.current.session_id`, and `latest.current` is reassigned *during render*. The panel stays mounted across a session switch, and the switch itself invalidates `send`'s identity → fires the cleanup that flushes the debounce. A half-typed prompt for chat **A** was written to chat **B**. Fixed: bind the pending body to the session it was *authored* on (`pendingFor`), flush the old body first, and only hand the resulting row back to the provider if it is still the session on screen. Test: `expected 'B' to be 'A'`.
  - **HIGH-2, full subtree remount.** `VoiceShell` was a component declared *inside* `VoiceSettingsPanel`'s render body → new component TYPE every render → React unmounts+remounts everything (focus lost mid-typing, slider drag drops pointer capture, voice list re-fetched per keystroke). Hoisted to module scope. Test counts **mounts**, not renders: 4 → 8 before the fix.
  - **MED** — `accountVoiceDiffers` was exported, tested and **never called** while the mirror's comment claimed it only wrote on real changes. Given its job (each mirror is an auth-service POST); the voice panel now also guards on `prev[key] !== value`.
  - **MED** — the 6-vs-4 preset split was **mirrored in i18n** and survived the code fix (`new.preset.*` 4 keys vs `settings.preset.*` 6 keys). One `presets.<key>` block now across **19 locales**, reusing existing translations (vi keeps *Tiểu thuyết gia*). Verified mechanically: the only key changes anywhere are the two retired blocks + the one added block; every other value byte-identical.
  - **LOW** — `BehaviorSection`'s system-prompt chip was hand-rolled instead of using the shared `isOverridden` predicate (the exact drift it exists to prevent), and had no clear affordance.
  - Re-verified live after the fixes: chip `system → session → system`, voice embedded with 0 rival overlays, one unified preset list, 0 console errors. FE **122 files / 951 tests**.
- **Deferred:** `D-CHATAI-VOICE-TWO-STORES-ENUM` (LOW) — `tts_source`/`stt_source` are deliberately left OUT of `SETTING_ENUMS`: validating either vocabulary today would 422 a live client that still sends the old word. A tripwire test asserts their absence, so whoever finishes the voice migration must reconcile the vocabulary rather than silently delete the assertion.

**▶ TRACK B — CLOSED (this session).** Everything in [`tracks/TRACK-B.md`](../specs/2026-07-09-agent-discoverability-and-workflow/tracks/TRACK-B.md) is delivered **except one item, deliberately not started**:

| Deliverable | State |
|---|---|
| WS-4A `glossary_extract_entities_from_doc` | ✅ live-smoked (real BYOK gemma) |
| WS-4B `kg_project_entities_to_nodes` + `KG_ENDPOINT_NOT_NODE` fail-fast | ✅ live-smoked (real Neo4j) |
| WS-4C Half B (`llm_tool_call` facts → L2) | ✅ |
| WS-4C Half A (canon auto-capture → `ai-suggested` inbox) | ✅ live-smoked (3 services); **opt-in** after `/review-impl` |
| Entity identity: `scope_label`, `glossary_entity_rename`, reachable `glossary_entity_delete` | ✅ (`mcp_server.go:89`) |
| Domain feedback: NFC/NFD+CJK dedup · read-your-writes · upsert-on-create | ✅ (verified against code, not self-reported) |
| Domain feedback: `propose_*`-writes-immediately naming | → **Track D's D1**, not Track B |
| Domain feedback: `glossary_confirm_action` doc-drift | ⬜ cannot confirm without its original feedback item |
| **W8/W10/W11 product-journey backends** (world-container graph/map authoring; reader spoiler-cutoff) | ⬜ **NOT STARTED** — P2, structurally large, needs its own design pass (defer gate #2) |

**Track-B defers still open:** ⚠ this "none" was later shown overstated — the 2026-07-11 completeness audit (see the TRACK B AUDIT block at the very top) found 4 real open items + 1 unproven surface, all since addressed (R0–R3), plus 4 LOW residuals tracked there. `D-WS4C-EFFECTIVE-VALUE` was CLEARED this session (see the CLEARED row below).
**Bugs found and fixed while closing Track B** (each with a spec + live proof): `D-KG-GLOSSARY-FK-GLOBAL-UNIQUE` (Neo4j FK was globally unique; a 2nd project could anchor nothing) · `D-GLOSSARY-KNOWN-ENTITIES-STATUS-PARAM` · `D-ANCHOR-PRELOAD-50-CAP` · `D-KNOWLEDGE-TOOL-ERRORS-NOT-ISERROR` · capture defaulting to ON (spent users' BYOK tokens) · `ADD COLUMN IF NOT EXISTS` never revisiting a bad default (21/21 dev projects opted in).

**▶ NEXT (whoever picks this up):** Track B's only remaining scope is the **W10 + W11 backends**. **Design pass DONE 2026-07-11** — [`docs/specs/2026-07-11-w10-w11-world-container-and-reader-backends.md`](../specs/2026-07-11-w10-w11-world-container-and-reader-backends.md), grounded in 3 parallel research sweeps. **The scope collapsed:** both are mostly *wiring over substrates that already exist* (W10 world container = `creation-unblock` C20/C21/C22/C28 substrate + read `kg_world_query`; W11 spoiler engine = `spoiler_window.py` + `reading_progress` + windowed reads already shipped). Only two pieces are genuinely greenfield: **W10 maps** (a new spatial primitive) and **W11 public/anonymous lore access** (a new public data surface — consciously overrides the earlier "reader product / world-sharing" non-goal, per the user's 2026-07-11 decision). **SIGNED OFF 2026-07-11** (spec §7): maps = full (image+pins+regions); `lore_ask` = evidence-bundle default, optional server-compose only on a BYOK model via provider-registry (public/anonymous = evidence-bundle-only); public reader = unlisted-token gated, canon-only; **build order = W11 first**. **▶ BUILD NOT STARTED — begin at W11-M1** (reading-position resolver in book-service + RAG `before_chapter_id` cutoff on `raw_search` + KG fact/status auth unified onto grants ≥VIEW). The three seams are already grounded: book-service `reading_progress` (`analytics.go`), knowledge `raw_search.py:117` resolve-grant/resolve-to-owner pattern to mirror, and `entities.py` owner-`user_id` reads to move onto `resolve_grant`. Then W11-M2 (reader ask-the-lore facade, cutoff server-enforced) → W11-M3 (public route, mandatory `/review-impl`) → W10-M1 (world write surface) → W10-M2 (maps).

Ownership, since this is easy to get wrong: **W8/W10/W11 are product *journeys*, not tracks.** They are split — **Track B** owns the W10/W11 *backends*; **Track C** owns all three *surfaces* + the W1–W12 workflow objects (WS-5). Track C's W10/W11 surfaces are **blocked on Track B's backends** (TRACK-C.md "Consumes: B's backing tools for W2/W4/W10/W11"). **W8 needs no Track-B backend** — it is an onboarding routing fork, a Track-C surface change; B's brief names it in a heading but scopes only W10/W11 work, and C's consumes-line omits it. Track D is unrelated (tool liveness + `_meta`).

**Track D — WS-D3 capability sweep reachability + CD4 warning conformance, 2026-07-11** (branch `feat/context-budget-law`, `e2fc2941a` · `387278580` · `05a95336b`). Evidence: [`docs/eval/tool-liveness/2026-07-10-capability-sweep.md`](../eval/tool-liveness/2026-07-10-capability-sweep.md).

- **Deterministic sweep 93 → 126 execute, 0 broken** ($0, no LLM). Three passes: (1) `$ref`/`$defs` resolution in `fill_args` — 28 composition tools wrap args in `{"args": {"$ref": …}}`, fully described therefore buildable (cycle-safe); (2) a **seeded keyless throwaway credential + model** reaches the 6 credential-gated tools (`settings_provider_inventory` + five `settings_model_*`) — a model can't mint a credential (OD-S1), so that's missing *fixture* state, not "unreachable by design"; the earlier plan to WAIVE them was wrong (seed disproves "never executes"); (3) **chained creators** (`project_chain.py`): `composition_create_work` mints the composition `project_id` (≠ kg project), `plan_propose_spec` in `rules` mode is synchronous → real `run_id`, `outline_node_create`(kind `beat`)/`canon_rule_create` return `{id,version}`, `composition_motif_create` → `motif_id`. Manifest 199 tools · 5 proven · **0 BLOCKED** · 73 unchecked; 3 service copies byte-identical.
- **`/review-impl` caught a real leak:** `teardown_composition` hardcoded 5 tables and leaked a `generation_job` row per sweep. Rewritten to discover book-scoped tables at runtime + retry-delete + **verify zero survive** (`{tables:20, clean:True}`). Plus a manifest-merge guard (conclusive never clobbered by a later `null`) and manifest.build's first unit tests.
- **CD4 warning conformance (bug, not amendment):** `livenessWarnings` warned on `!proven`, contradicting CD4's own table (`executes:true`/RED-SELECT → **no warning**; only `executes:null` warns). `proven` includes G1 (selection), irrelevant to a workflow step that names its tool. Fixed Go predicate → `toolUnchecked`; chat-service was already correct (acts only on `executes:false`). Hard REJECT gate unchanged.

**Track D — WS-D1 SHIPPED + F6 root-caused and fixed, 2026-07-10** (branch `feat/context-budget-law`, `713e6ba65` · `a1fa023a5`). Evidence: [`docs/eval/tool-liveness/2026-07-10-f6-kg-build-graph-unreachable-by-agent.md`](../eval/tool-liveness/2026-07-10-f6-kg-build-graph-unreachable-by-agent.md).

- **WS-D1 (CD2 `propose_*` law).** Wire lints on **three** services (glossary Go · knowledge Py · composition Py) covering **19** `propose_*` tools — 15 federated + **4 `glossary_admin_propose_*`** that never reach the gateway catalog (the admin server isn't federated) and so were invisible to the tool audit. Rule 1 (`tier ∈ {A,W}`) already held (Wave 1 tiered them); the lint is now the regression gate. Rule 4 had **one** real violation: `plan_propose_spec` declared neither pattern — fixed. The checks are **tier-directed**, which is load-bearing: `glossary_propose_status_change` is Tier W yet contains the word "draft" *as a status value*, so a naive scan false-positives. The A-branch's no-`confirm_token` rule **caught its own author** (my first fix wrote "…no `confirm_token`") — correct behavior, because models handle negation poorly. Every lint ships a **negative control**. Audit: `glossary_propose_aliases` is draft-only, proven at the SQL (an empty `'[]'` scaffold under a self-assignment `ON CONFLICT` no-op; `confidence='draft'` guarded by `WHERE confidence <> 'verified'`, so it can never overwrite a verified rendering). Also corrected TRACK-D's DoD, which still read "money-spenders … are never tier `R`" — contradicting CD1's `paid ⊥ tier` and the `web_search` shipped in Wave 2.
- **F6 — `kg_build_graph` was UNREACHABLE by an agent.** The harness reported *"unhandled errors in a TaskGroup (1 sub-exception)"*. That was never the server's message: `mcp_direct.call()` raised **inside** two nested anyio task groups, so anyio re-wrapped it and destroyed the text. The real error told a **tool-calling model to open a GUI dialog**, named no tool — and there *was* no tool to name. The agent's chain had a hole in the middle: `kg_project_create` ✅ → **configure embedding model ❌ (REST route + dialog only)** → `kg_run_benchmark` ✅ → `kg_build_graph` ✅. So every agent-created project dead-ended, and the async class's only probe could never run. An **MCP-first invariant** violation. Fixed: new Tier-A `kg_project_set_embedding_model` (probes the vector dimension — an LLM cannot know it; **set-on-unset only**, because changing it on a built graph orphans passages into silent zero-recall, which stays a confirm-gated REST op); agent-native error prose at all 3 sites; harness `MCPToolError` + `ExceptionGroup` flattening. **Live-proven** (rebuilt images, real bge-m3, $0): build blocked → set model (dimension **1024** probed live) → build retry mints `proposed:true` + `confirm_token`. The token was deliberately **not** redeemed (confirming starts a real paid extraction job); the fixture project was restored to NULL.
- **Carry into WS-D3:** `kg_build_graph`'s matrix cell read `G1 RED — "model did not call it"` (F5, under-selection). True — but it **masked** the fact the tool could not have succeeded even if selected. A RED-G1 must be re-run **deterministically (MCP-direct)** to separate a *selection* failure from a *capability* failure, or the ship gate will keep mistaking one for the other.

**Verify:** knowledge **3842 passed**, 530 skipped · composition **1693** · glossary Go green · harness pure 7.

**▶ NEXT (Track D):** WS-D3 **DONE**; **WS-D4 partial DONE** + registry-slug residue cleared (commits `f9f841797` · `301f27bc6`). WS-D4 shipped `executes ∧ effect` for the workflow-critical set (derived live from `agent_registry.workflows` = `glossary-bootstrap`'s 4 steps): independent read-back (CD3), a silent success folds to `executes:false`. 3/4 critical tools effect-verified; `glossary_extract_entities_from_doc` is **paid** → an honest $0 gap in the sole curated workflow. Manifest gains informational `effect_verified` (`proven ⊆ effect_verified`). Sweep now **130 execute · 0 broken · 84 unchecked** (catalog grew to 216 under concurrent work). **Step 5 DONE** (`c71ece01c`): the F5 description-quality signal ships as a $0 classification proxy (`selection.py`) — model out of the agent loop, whole catalog as distractors, routed via `loreweave_llm` SDK → provider-registry → local gemma. **110/146 discoverable (75%), 36 miss, 0 error.** The 36 misses are a description-quality backlog, kept OUT of the gate manifest (chat-surface concern ≠ `executes` gate). Report: [`2026-07-11-selection-quality.md`](../eval/tool-liveness/2026-07-11-selection-quality.md). **WS-D5 specced + fixable subset cleared** (`8eb808b42`; spec [`WS-D5-followups.md`](../specs/2026-07-09-mcp-tool-liveness-eval/WS-D5-followups.md)) — the three follow-ups triaged do-now / tracked-defer / won't-do: **(a)** the 36 selection misses split into synonym bugs + buried-surface + inherent ambiguity — cleared the synonyms (`book_steering_set`, `registry_propose_skill`, `book_search`) and added `[Authoring workspace]`/`[Saved book]` surface tags to the `composition_*`/`book_*` chapter tools; verified in-memory (synonym fixes hit; the `book⇄composition` two-home ambiguity confirmed **inherent** = the accepted floor). **(b)** the 84-`null` residue is tracked-deferred (authoring-run/`job_id` need SPEND, kg-graph needs an ontology fixture; the cheaply-seedable credential + registry-slug clusters are done). **(c)** hard-reject→`proven` is a recorded **won't-do** (`proven`/G1 is a chat-surface signal, not the workflow gate). **Deploy DONE + live-verified** (`78ead137d`): rebuilt the 3 MCP-server containers **and** restarted `ai-gateway` (it caches the federated `tools/list` — edits aren't live until the gateway cache clears; recorded in the spec). Live re-run: **112/146 (76%), 34 miss** — `book_steering_set` + `registry_propose_skill` dropped out (synonym fixes work live); net moved only 2 because ~76% is the **floor** set by inherent `book⇄composition` surface overlap, not prose. **WS-D5a dedup + synonym pass DONE + live** (`6a500e0ed` · `7e9305bd9` · `bd079a00e` · `3db456717` · `4fa6a1167`). Verified in code (2 traces): `composition_{get_prose,write_prose,publish}` are TRUE duplicates of `book_*` (same `chapter_drafts` row — the "two-layer" guess was wrong) → **deprecated** the 3 proxies (`visibility:legacy`+`superseded_by`; added those params to Python `require_meta`); `glossary_book_delete` was already legacy; `ontology_upsert` vs `propose_new_attribute` are NOT dups (direct-write vs confirm-token — descriptions now say so). **Harness fix:** `selection.py` now excludes `visibility:legacy` from the distractor pool (production hides them). Then a **7-synonym batch** (composition/translation/provider-registry) cleared the last clearly-fixable misses incl. 2 spend-routing safety fixes. **Selection trajectory: 75% → 76% → 78% → 82% (25 miss).** The 25 remaining are the floor — inherent two-home ambiguity + get/list/create family adjacency, not description bugs. **#1 residue build DONE** (`29cb28bef` · `c996889f0` · `ec47e56e4`) + **#3 routing fix** (`3c2ad45de`). Re-examined the "needs SPEND" residue per the anti-laziness rule — most was fixture-buildable: reached **12** tools (glossary direct `propose_new_kind`/`_attribute`; glossary array-payload `ontology_upsert`/`_delete`/`propose_aliases`/`_translation`/`_kinds`/`_batch` — item shapes traced from the Go structs; `book_chapter_restore_revision`; the authoring-run family via `seed_authoring_run` = a plan_run_id + a seeded `authoring_runs` row, $0, no paid confirm). Plus fixed concurrent-churn (`outline_node` kind `beat`→`chapter`) restoring the node chain. Then a **lower-yield handful** (`bdc993b54`, +8): `book_chapter_bulk_create`, `glossary_book_set_kind_genres`/`_propose_reassign_kind`/`_propose_merge` (2 fixture entities), `composition_authoring_run_revert_all`, `memory_remember`→`memory_forget`, `registry_update_workflow`. **Two harness bugs found + fixed:** the classifier scored an INPUT-arg validation error as `executes:false` (a false-block — narrowed `_INTERNAL_FAULT` to "validating tool **output**" only); and the fixed `X-Session-Id` accumulated state and tripped `memory_remember`'s 10/session cap (now unique per run). **Capability sweep 135 → 159 execute · 0 broken · nulls 86 → 62.** **#3:** verified `jobs_cancel` can't touch an authoring run (it queries `job_projection`; runs are never emitted as jobs) — "cancel autonomous run" → `jobs_cancel` was a silent no-op; fixed `authoring_run_close` to win that intent (live-verified HIT). **Genuine residue (62 nulls, none blocking):** ~4 correctly-null (paid/legacy); ~20 genuinely-blocked (kg-graph needs a built graph, `job_id`/`jobs_*` need a real async job = SPEND, `glossary_book_sync_apply` needs a divergent upstream); the rest need deeper fixtures (2-of link creators = seed 2 motifs/nodes; translation-version tools need a real translation). **0 tools are executes:false — nothing is broken;** further null reduction is completeness-polish (executes:null blocks nothing). Selection floor 82%; further miss reduction is a **product decision** on the parallel book/composition surfaces.

---

**Book-Package architecture — the full 5-pillar spec cluster SHIPPED + one live bug fixed, 2026-07-10** (branch `feat/context-budget-law`, studio track).

- **The governing model is law now:** a book is a **package** — manifest (`composition_work`) · registry `deps/` · lockfile (`motif_application`) · **spec/** (`structure_node` saga→arc→sub-arc + `outline_node`) · tests/ (canon+threads) · manuscript/ (prose SSOT, never regenerated) · `.index/` (`scenes` = source map, anchor INVERTED to `scenes.source_scene_id`) · `.runs/` (PlanForge = **the compiler**). Plan↔prose is desired↔actual state (the terraform relation), reconciled by conformance — never source→binary. [`00A_BOOK_PACKAGE_STRUCTURE.md`](../specs/2026-07-01-writing-studio/00A_BOOK_PACKAGE_STRUCTURE.md): DA-1..14 invariants + the BPS-1..21 register, **every open question closed**.
- **Specs 22–28 + 00B written/amended** (multi-agent: 6 recon → 5 authors → adversarial verify → fix → 2 integration rounds): `22` (scene seam, amended to the index model — read-only `/v1`, publish-only cadence), `23` (`structure_node`; its **E5/E3 built+verified**: the BPS-20 fixture-constant bug — every PlanForge book compiled as xianxia with "dry humor", reaching `propose_cast` — fixed in `compile.py`, 7 red→green guard tests, composition 1690 green), `24` (Plan Hub v2, ≤5-request canvas contract), `25` (migration master: 12-table re-key; **C23 derivative-Work refinements PM-3/PM-4/PM-10 forced by shipped code** — `project_id` survives as the Work partition key, partial manifest unique; KG-side verdict: safe now), `26` (index lifecycle state machine; ONE staleness computation, IX-14), `27` (multi-pass compiler: 7 pass contracts + the link step, run-scoped idempotency PF-10), `28` (agent-native: Cursor-parity matrix, `package_tree`/`find_references`/`diagnostics`/steering-as-`.cursorrules`). All 15 integration conflicts + 4 residuals **adjudicated ✅** ([`00B`](../specs/2026-07-01-writing-studio/00B_EXECUTION_ROADMAP.md) §5 ledger; NC-1 resolved direct-consume ≤5). `29_translation_repair.md` = renumbered out of the `24_` collision.
- **✅ ALL PRODUCT DECISIONS RATIFIED (PO, 2026-07-10):** the 15 P-rows of [`00B`](../specs/2026-07-01-writing-studio/00B_EXECUTION_ROADMAP.md) §6 — recommended defaults approved verbatim ("seal layer 1") — plus BPS-9 (parts/saga → **explicit proposal**: the decompiler proposes volume-aligned arcs through the existing Tier-W confirm gate, `26` IX-17; DA-12 refined to forbid only the *silent* path). All five pillar specs flipped **📐 SEALED**. **Zero open questions remain in the 22–28 cluster.**
- **✅ Stage 1 (00B) / `25` Deploy 1 SHIPPED + APPLIED TO THE DEV DB, 2026-07-10.** RB-1 reached. Marker `pkg_rekey_v1` stamped; composition-service healthy. Built by 8 fan-out agents → 6 repair agents → `/review-impl` (7 dimensions, 3-lens refute-verify) → 4 DB-heal agents.
  - **Live proof (T6 + T3 + T5, through the gateway).** A non-grantee gets the uniform `404 "not found or not accessible"`. After an EDIT grant, collaborator B **reads the owner's outline (49 nodes) and writes into THE canonical Work** — `created_by=B`, `book_id` derived in-SQL, **1 canonical Work / 0 pending forks** (F5's per-user fork bug is structurally dead). B drove a **$0 local gemma-26b** generation whose `generation_job.created_by = B` (T5 spend attribution), while provider-registry **refused A's BYOK credential to B** — OQ-9's fail-actionably, not a silent cross-tenant spend.
  - **Live schema:** `created_by` 15/15 tables · `user_id` survivors **0** · `book_id NOT NULL` 13/13 · `.runs/` 4/4 renamed · deps registry untouched (PM-16) · `style_profile_pkey = (project_id, scope_id, scope_type)` (actor demoted) · `structure_node` + trigger present. Rows: works 204, outline 1511, jobs 772, **derivatives 5 intact**. Exactly the 9 quarantined rows removed, nothing else.
  - **Operator pass (done).** `_pkg_rekey_quarantine` holds 9 rows: 4 `kind='beat'` (M0.3), 1 empty F5-fork Work (M0.1), 4 orphan `generation_job` (M0.4). Pre-migration snapshot: `/tmp/comp_predeploy1.sql` inside `infra-postgres-1`.
  - **Five real bugs the process caught** (none by the mock suite):
    1. **HIGH cross-book IDOR** (Wave-1 regression). `actions.py` confirm-dispatch gated EDIT on the *request-body* `book_id`, then mutated a run loaded bare-id. An EDIT grant on ANY book let a caller `start`/`resume`/`gate` another user's authoring run (spending their BYOK) or `revert_all` it (destroying their drafts). HEAD had `svc.start(envelope_user, run_id)`; de-scoping deleted that fence. Fixed by `_authoring_run_in_book` (confirm) + `_require_own_run` (4 MCP propose tools). 38 effect tests spy the mutator to prove it is never awaited on refusal.
    2. **HIGH `jobs.get(project_id, job_id)`** in `EngineDraftingSeam` after the repo went bare-id → `TypeError` on every real draft. Invisible because every test injects `FakeSeam`.
    3. **MED missing creator check** on MCP `accept_unit`/`reject_unit` (REST is creator-only; the tools' docstrings promised owner-only).
    4. **HIGH C16 regression** (found only by real SQL): every re-keyed write derived `book_id` via `WHERE w.project_id = $n`, which can never match a **lazy Work** (`project_id NULL`, addressed by surrogate `id`). PlanForge on a greenfield book during a knowledge-service outage hard-failed instead of degrading. 15 join sites now resolve the Work by `project_id OR (project_id IS NULL AND id = $n)`. `tests/integration/db/test_c16_pending_work.py` pins it — including that a *genuinely* dangling project still raises (the orphan guard was not weakened).
    5. **Two bugs of my own, caught by the live boot** (no test could): M0.4's anti-join sentinel must be `w.id`, not `w.project_id` (a matched pending Work has `project_id NULL` by definition → every lazy-Work row read as an unrecoverable orphan); and the M2 **batched** backfill kept the old predicate while the single-statement one got the fix. `test_m0_4_and_m2_agree_on_lazy_work_rows` is red-first against either.
  - **Also landed:** **M0.7** pre-flight (the `decompose_commit` narrowing had no guard symmetric to M0.6 — an opaque `UniqueViolation` would have crash-looped a boot with no operator protocol) · **PM-13 rollback is now an artifact, not a claim**: `revert_package_rekey()` + a `up→down→up` test asserting byte-identical schema · invariant lint (zero `created_by = $n` access filters) · PM-15 allowlist widened to the 8 real Book-tier keys after M0.5's **live** inventory contradicted the code scan · anti-oracle 404s unified in `outline.py` + `works.py` · `idx_reference_source_project_read` (the M3.3 rename cascade had left `pack()`'s hot-path search seq-scanning).
  - **Verify:** composition unit **1740 passed / 0 failed**; composition DB-integration **192 passed** (was 106 failing — those tests had been *skipping* for want of `TEST_COMPOSITION_DB_URL`, so no re-keyed SQL had ever executed); `25`-T1/T2 + PM-13 round-trip **12/12** against a legacy schema loaded verbatim from **git HEAD's `migrate.py`**; book-service migrate green incl. a **live** backfill test (1201 rows across batch boundaries, crash-retry, marker gating).
- **✅ Stage 2 (00B) / `23` structure layer SHIPPED + live-proven on dev, 2026-07-11.** RB-2 reached. 7 fan-out agents → 6 repair/reconcile/coverage agents → `/review-impl` (5 dims, 3-lens refute-verify).
  - **Shipped:** `structure_node` `StructureRepo` (tree CRUD, move-with-subtree-depth-recompute, BA7 cascade resolvers, BA6/BA15 derived rollups); arc conformance retargeted to the durable spec (BA4, reads the first-class `motif_application.structure_node_id`); `arc_apply`/`arc_extract_template` (template↔spec, pacing→scene tension per BA3); **the packer injects the resolved arc chain (BA12)**; the full `composition_arc_*` MCP surface + REST write mirrors; book-service scene read routes + MCP + parse writers + the **v2 backfill that closes the Stage-1 `scenes.book_id` window**; the tiptap `source_scene_id` anchor walker (26-A). Idempotent migration adds `structure_node.created_by` + `outline_node.structure_node_id` (both live on dev).
  - **THE bug the review caught:** BA12 — the whole reason pillar 23 exists — was **dormant in production**. The build's D2 "ship gate" passed only because it injected a `FakeStructureRepo` and hand-set `structure_node_id`; **no real `pack()` caller wired `structure_repo` and `OutlineNode` had no `structure_node_id` field**, so the arc never reached the prompt. Fixed: field on `OutlineNode` + `OutlineRepo._SELECT` + a `chapter_structure_node_id` resolver (a scene can't carry the arc id — the CHECK forbids it — so the packer resolves scene→chapter→arc); `structure_repo` wired at all 4 pack call sites via a **tolerant dep** (None on an uninitialised pool → arc lens dormant → the ~30 existing handler tests need no change); a **wired** effect test 3/3; and a **live gateway smoke** — created an arc, assigned a chapter, ran the grounding preview, and the `<arc>` block reached the prompt with the arc's track. Lesson: [[test-injecting-a-fake-at-the-chokepoint-cannot-prove-the-chokepoint-is-wired]].
  - **Other seam fixes:** A5↔A4 (`arc_apply` wrote the arc link to `annotations`; conformance read the *column* — made first-class end-to-end, proven via real `arc_apply`); the async conformance worker retargeted `arc_template_id`→`arc_id`; the Go nullable-title scan was **5 sites** (two REST 500s). Plus a **latent Stage-1 defect**: `test_package_rekey.py` built its "legacy" schema from `git HEAD`, which inverts the moment the migration commits — rewrote it to migrate-then-revert. [[migration-test-legacy-from-git-head-inverts-on-commit]]
  - **Verify:** composition unit **1776**, DB-integration **218** (real Postgres), book-service `go test ./internal/...` green (incl. live scenes backfill), go build clean.
  - **Stage-2 deferred (honest fail-closed, tracked):**
    - **`D-ARC-APPLY-MCP-WRAPPER`** (MED, gate #2 — large/structural). `composition_arc_apply` + `composition_arc_template_drift` MCP tools return an honest `{success:false, error:"arc engine not yet integrated…"}` (their `getattr` finds no symbol). The engine `arc_apply` exists + is tested, and `composition_arc_extract_template` **is now wired** (`extract_template_from_arc`). Missing: the *apply* wrapper's motif-resolver + cast-index orchestration (the `POST /arc/materialize` route, plan.py ~1300, is the assembly template) and a `build_template_drift` engine fn. Not silent, fails closed. Trigger: a focused B2-tail build.
    - **`D-ENGINE-UNUSED-STRUCTURE-DEP`** (COSMETIC). 3 non-pack engine handlers carry an unused `structures` dep from the wiring sweep; harmless with the tolerant dep. Trigger: next engine.py touch.
- **✅ Stage 4 BACKEND SHIPPED + D3 live-proven on dev, 2026-07-11 (RB-4-BE).** FE half (22-C + 24-H2.2) is the follow-on. 3 build agents → parent SC4 read-path fix → `/review-impl` (4 dims, 3-lens refute-verify).
  - **Shipped:** `22`-B2 (8 SC4 fields updatable, incl. `exit_state` `::jsonb`) · B3 (MCP create/update args gain the 8 fields, schema enums/ranges — bad `value_shift` 422s pre-DB) · **B4 the SC6 scene DECOMPILER** (`/internal/books/{id}/materialize-scenes` for the import tail + EDIT-gated `/v1` mirror; reads book-service scenes, upserts one `outline_node` per parse leaf, idempotent, book-scoped) · `28`-AN-B (`book_steering_list/set/delete` + `book_search` MCP tools over shipped REST engines).
  - **Parent fix — SC4 write-only gap:** B2/B3 wrote the 8 fields but `OutlineNode`/`_SELECT_COLS` didn't READ them (create/get echoed a node without them; the inspector couldn't render intent). Added them to the model + `_SELECT_COLS` + `json.loads(exit_state)` on read (no jsonb codec on the pool).
  - **`/review-impl` — 2 CONFIRMED MED, both fixed with red-first tests:**
    - **DECOMP-2**: the decompiler minted onto a *pending* Work's surrogate-id partition, which `backfill_project` re-keys on `composition_work` but NOT `outline_node` → stranded nodes after backfill (empty rail + orphans + re-mint). Fixed: refuse to mint onto a pending Work (`work_resolved:false` + reason); the import tail re-runs after backfill.
    - **SC4-UNDO**: the update tool emitted a `field:null` undo for a nullable field set from NULL — the sparse patch drops it (silently-lying undo). Fixed: emit `undo_hint=None` when a changed field's prior was None.
    - **DECOMP-1 REFUTED**: `scenes` is insert-once, no renumber path — the positional idempotency key is a spec'd interim pending 26-D1.
  - **Verify:** composition unit **1783**, DB-integration **231**, book-service go build/vet/MCP tests green. **D3 live smoke through the gateway:** Work for a 3-scene book → decompile via `/v1` (`created:3`) → re-run (`created:0, matched:3` — idempotent, no duplication) → cleaned up. Tenancy: the internal route grant-checks the asserted owner; `/v1` gates the caller.
  - **✅ 22-C1..C5 shipped** (`scene-browser` + `scene-inspector` panels, `SceneRail` inline title, i18n; 3 live browser smokes caught 2 real cross-service bugs — `scene_id` not `id`, bare `/outline/nodes/{id}` path — that all 498 vitest missed). **✅ 26-F state chips shipped** (`51a4def37`, IX-14 consumer). **✅ 24-H2.2 shipped** (`402d36fc2`) — the deterministic lane-layout engine as ONE pure headless function `(shell, windows, collapse) → positions` (PH14: rank-ordered depth-nested bands, global-story-order x with collapsed-run compression, BA6 contiguous-run segmentation, insert-shifts-never-reshuffles, PH21 unplanned tray, minimap-safe extent); zero backend dep, `features/plan-hub/layout/laneLayout.ts`, vitest 12/12, tsc+eslint clean.
  - **✅ 22-C3b entity-ref pickers shipped** (`75919d061`) — the last F2 fields (`pov_entity_id`/`present_entity_ids`/`location_entity_id`) become editable glossary refs in a new **Cast & Setting** section. `EntityRefField` (single+multi) resolves ids→names via `useGlossaryRoster` (DOCK-2 no fork; the planner+canon picker's source); a ref missing from the roster shows a short-id, never blanked; each field patches only its own key. **✅ 22-C3 Links section shipped** (`616c24036`) — the scene's `scene_link` edges read/add/removed inline, reusing `useSceneLinks`/`useOutline`/`useOutlineMutations` (DOCK-2 no fork); picker excludes self+already-outgoing; `LinkRow` hoisted out of render body (the remount lesson). **The scene-inspector is now feature-complete** (Identity · Intent · Cast&Setting · Craft · Links · Grounding + the 26-F dirty banner). vitest studio panels **537** green; tsc+eslint clean. Gateway smoke: glossary roster call 200 `{items:[]}` for real books (mapping already proven by shipped roster consumers); Links reuses hooks already live-exercised by SceneGraphCanvas — both single-service.
  - **✅ Adversarial review + fixes** (`619e35aca`) — a 13-agent multi-agent review (finder-per-file → 2-lens refute-verify) over 24-H2.2 / 22-C3b / Links found **5 real defects unit tests missed**, all confirmed by both skeptics, all fixed with red-first tests: (MED) `laneLayout` non-leaf-band-with-direct-chapters overlap (chapter+scenes collided + overflowed child bands — reachable, no leaf guard on `assign_chapters`); (MED) `useSceneInspector` OCC **single-flight race** — `EntityRefField` commits on every change so two rapid Cast&Setting edits both sent `If-Match v1` → 2nd silently dropped + false "changed elsewhere"; `patch()` now chains + reads a live version mirror; (LOW×3) Links empty-state gated on project-wide count, `titleOf` `??`→`||` for empty-title scenes, target picker over-excluded across kinds (BE uniqueness is `(from,to,kind)`). vitest studio panels+plan-hub **554** green.
  - **✅ 22-C2b bulk triage shipped** (`79916cc33`) — the browse-only scene-browser gains bulk-select (checkbox column on spec-backed rows only, select-all) + a bulk bar (set-status, trash) via `useSceneBulk`, which fans OCC writes across DISTINCT nodes in parallel (each its own version → no single-flight race) with an honest partial-failure tally (412=conflict, else=failure), targeting the spec via the shipped `composition_outline_node_update`/archive path (no `structure_node`). The bar counts only ACTIONABLE (visible+selected) targets. vitest: useSceneBulk 5 + SceneBrowserPanel 13; studio panels **550** green; tsc+eslint clean.
  - **✅ C2b adversarial review + fixes** (`94727db55`, `020abe2f5`) — a cold-start 2-finder × 2-lens review surfaced, inside a *refuted* finding, a **HIGH silent-no-op**: the REST `NodePatch`/`NodeCreate` models never declared the `22` SC4 fields (`target_words`/`location_entity_id`/`conflict`/`outcome`/`stakes`/`story_time`/`value_shift`), so Pydantic's `extra='ignore'` **silently dropped** them — **the scene-inspector's whole Craft section + location picker + bulk-words no-op'd through the GUI** while the MCP tool (which has them) worked (the CF-9 "one repo method, two front doors" divergence; repo `_UPDATABLE_COLUMNS` already writes them). **This also silently broke the already-"shipped" C3 Craft edits — now repaired.** Fixed both REST models + wired the create handler (`exit_state` stays MCP-only per SC12); guarded by a drift test (`NodePatch ⊇ _UPDATABLE_COLUMNS − exit_state`) + a **TestClient HTTP round-trip** proving the body reaches `update_node`. Swept the sibling `ArcPatch` mirror — already correct, now guarded. Plus 3 FE fixes: the bulk partial-failure tally was **structurally invisible** (rendered inside the selection-gated bar that `runBulk` unmounts on completion) → standalone `BulkResult` banner; per-row checkbox aria-label now carries the scene title; fractional `target_words` (0<n<0.5) rounded-to-0 *after* the guard → round before. composition contract 6 + FE panels 554 green. **⚠ Deferred `D-NODEPATCH-SC4-LIVE-SMOKE`** (gate #4 — no live fixture): the dev test account has no book with chapters + a Work + a scene node, so a full-stack GUI-edit→persist smoke needs a decompiled-book fixture that doesn't exist; the fix is proven by the red-first HTTP round-trip + drift-guard + pre-tested repo write. Bank: [[rest-write-mirror-drops-fields-the-mcp-tool-accepts]].
  - **▶ The unblocked Stage-4 FE wave is COMPLETE.** `22`-D2 satisfied (frontend-tools contract already lists both scene panels; no new enum added). `22`-D1 (OpenAPI for the book-service `/v1` scene routes) is a **book-service Go task**, owned by the scene-route wave, and needs a drift-test to be worth writing — out of the FE wave's scope. **Note (2026-07-11): the structure-layer backend — `structure_node` table + `StructureRepo` + arc engines + Deploy-1 `book_id` columns — now EXISTS in composition code** (a concurrent session built it since the roadmap's 2026-07-10 snapshot), but `structure_node` holds no arc rows until Deploy 2 lifts them, so building its consumers now renders empty. **Remaining, genuinely Deploy-2-gated (needs `structure_node` DATA):** C2b **group-by-Arc**, C4b SceneRail identity-union, the Hub canvas (24-H2 consuming `laneLayout`). Follow-ons buildable anytime (not gated, not urgent): windowed spec-paging, row virtualization (V2-11: profiling-gated), bulk set-POV/words. Do NOT build the Deploy-2 consumers blind. FE verify = `tsc --noEmit` + vitest + a **built-image** browser smoke (`frontend-5174-is-baked-prod-nginx-not-vite`).
  - **✅ Stage 3 / Deploy 2 (M4/M5) BUILT + REHEARSED + RUN LIVE, 2026-07-11 (human green-lit P-4).** `app/db/arc_lift.py` (`run_arc_lift`, marker `pkg_lift_v1`, NOT boot-wired — operator/`python -m app.db.arc_lift`): M4 lift (arc `outline_node`→`structure_node`, `_arc_lift_map`, chapter re-point, provenance, PM-10 `decompose_commit.arc_id`→`structure_node_id`), M5 contract (DELETE arcs + `kind` CHECK→`('chapter','scene')`, `arc_template` threads→tracks/arc_roster→roster, drop map). **Two cascade fixes the rehearsal caught:** `motif_application.outline_node_id` is ON DELETE CASCADE (M4.3 nulls it after re-anchoring to `structure_node`); the M5 orphan guard excludes sub-arcs. **T7 rehearsed GREEN two ways** (synthetic 2-arc+nesting+motif+decompose; real pg_dump of the live composition DB). **23-A7 reader code** (`e5bf8a9d9`): base CREATE + `arc_template_repo` now use `tracks`/`roster`/`structure_node_id` (SELECT aliases `tracks AS threads` so the Pydantic/MCP field names stay — full BA10 API rename deferred). **LIVE RUN on the dev DB:** Deploy 1 was applied + **0 arc rows** (was 81 on 2026-07-10; since emptied), so the lift moved no data — M5 was a schema-only change. Rebuilt composition-service+worker images → ran M5 → recreated containers. **Verified live:** `pkg_lift_v1` stamped, `kind` CHECK swapped, columns renamed, **9 arc_templates + 28 motif_applications preserved**, service healthy, `GET /v1/composition/arc-templates/catalog` → 200 (aliased reader code executes clean). Commits `d5512dac9`, `e5bf8a9d9`. **✅ Adversarial review (25 agents) → HIGH live bug + 2 guards fixed** (`93e57708c`): `motif_retrieve._ARC_RETRIEVE_COLS` (a SECOND arc_template projection, the `retrieve_arcs` path) was NOT aliased for the rename → 500'd on every call against the renamed live DB; fixed + redeployed + verified (test_motif_retrieve_db 5 green). Plus 2 migration-robustness guards the 0-arc live run couldn't exercise: an M4 pre-flight refusing arcs nested >2 deep (would crash the depth trigger mid-lift) and an M5 guard for `scene_link`/`scene_grounding_pins` ON DELETE CASCADE refs to arcs (silent loss) — both with red-first tests. **Known window (roadmap-planned):** the legacy `outline.py` decompose creates `kind='arc'` outline_nodes → now CHECK-rejected until Stage 6 (27) migrates it to `structure_node` (dormant on dev: 0 decomposes; the modern arc CRUD already uses `StructureRepo`).

- **✅ Stage 5 CORE SHIPPED + RB-5 live-proven cross-service, 2026-07-11 (RB-5).** The `26` indexing/staleness spine. 3 build agents (one per service) → parent contract reconcile → `/review-impl` (3 dims, 3-lens refute-verify). 26-D provenance + 26-F FE chips are follow-ons.
  - **Shipped:** (book-service) `chapters.last_parsed_revision_id` + a hash-preserving `reparse.go` (unchanged leaves keep their row + `source_scene_id` back-link — the invariant the whole system rests on) that upserts scenes and emits `chapter.scenes_reparsed` IN the publish Tx + a sweeper on the staleness predicate (= the producer's, reconcile-by-truth-mirror) + a `canon-markers` batch route; import writers auto-publish (IX-1 corollary). (composition) `arc_conformance_state` (durable, input-pinned snapshots) + `persist_conformance_state` at the one `compute_arc_report` seam + the **IX-14 `conformance/status` read contract** (route + `composition_conformance_status` MCP tool — the ONE staleness computation the Hub/inspector/agents all consume). (knowledge) the `chapter.scenes_reparsed` K14 consumer → book-scoped extraction-cache invalidation.
  - **Frozen event** (spec IX-10, reconciled — I'd let a spurious `scene_count` into the prompt; producer & consumer agree on the 4-field shape): `chapter.scenes_reparsed {book_id, chapter_id, published_revision_id, parse_version}`, aggregate_type `chapter`, Redis stream `loreweave:events:chapter`.
  - **`/review-impl` — 1 HIGH + 3 MED, all fixed with regression tests:**
    - **COMP-STALE-1 (HIGH)**: `stale_chapters` carried only the index-stale set, so on the NORMAL publish path (IX-2 re-parses in-Tx → index fresh immediately, `prose_drift` the only signal) a chapter whose canon just moved rendered **false-fresh** in the scene-inspector (chip = `arc.dirty AND chapter IN stale_chapters`). Fixed: collect the prose-drifted chapters into `stale_chapters`; the book-level `stale_chapter_count` rollup stays index-stale-only (distinct concepts).
    - **RB-2 (MED)**: publish (chapters→scenes) and the sweeper (scenes→chapters) took opposite lock order → AB-BA deadlock. Sweeper now locks the chapters row FIRST (`SELECT … FOR UPDATE`, which also folds in the concurrent-republish guard).
    - **RB-3 (MED)**: the `parse_version` chapter-scalar was `bump`, overstated on a delete-only reparse (no surviving row carries it) → disagreed with canon-markers' `MAX`-over-active. Fixed: compute the true `MAX` (one computation, reconcile-by-truth).
    - **RB5-1 (MED)**: a no-op re-parse still emitted `chapter.scenes_reparsed` → the consumer wiped the WHOLE book's extraction cache (a costly re-extract for zero change). Fixed: emit only when `counts.changed()`.
  - **Verify:** composition unit **1783** + DB-integration **233**; knowledge **34**; book-service go build/vet + full suite (serial). **RB-5 live smoke through the gateway:** published a draft chapter → book-service re-parsed (1 scene) → `chapter.scenes_reparsed` in-Tx → outbox relay → the knowledge K14 consumer logged `IX-10: chapter.scenes_reparsed invalidated extraction cache book=… chapter=… parse_version=1`. The frozen contract is proven THROUGH its consumer (the RB-5 mandate), not just asserted.
  - **✅ 26-D1 SHIPPED (`141641a73`):** `outline_node.source`/`decompile_key` + `structure_node.source` (IX-11); the decompiler stamps `source='decompiled'` + the key on mint and **never overwrites an authored node** (reports `skipped_authored`); `source` is readable for the "mined" badge. 7 decompiler DB tests; migration applied to dev.
  - **✅ 26-D2 SHIPPED (IX-12 import-tail write-back).** Composition `materialize_scenes` returns `mappings[{chapter_id, sort_order, outline_node_id}]` — one per leaf that resolves to a decompiler-OWNED node (fresh mint OR re-matched decompiled; a `source_scene_id`-preset leaf and a human-authored node are NOT mapped, so a retry after a failed write-back returns the same map). The worker-infra import tail ([import_processor.go](../../services/worker-infra/internal/tasks/import_processor.go) `writeBackSceneLinks`, from both the pandoc + PDF paths) calls composition's `/internal/books/{id}/materialize-scenes` and writes `scenes.source_scene_id` from the map — **only where NULL** (IX-5 r1 anchor wins), BEST-EFFORT (a failure never fails the already-committed import; a Work-less book is a graceful no-op). New `MaterializeClient` + `CompositionServiceURL` config + compose env. Tests: composition `test_mappings_returned_…` (9 decompiler DB tests); Go `TestMaterializeClient_*` (token/path/decode/no-op/non-200). String→uuid bind verified safe against the existing import-INSERT precedent. **`LIVE-SMOKE deferred to D-IX12-IMPORT-E2E`** — full upload→parse→decompile→write-back E2E needs the whole ingest pipeline (MinIO + RabbitMQ + worker + a Work-backed book); recipe: import a book that already has a canonical Work, assert `scenes.source_scene_id` fills for anchor-less leaves.
  - **D3 RECLASSIFIED → `D-ARC-DECOMPILER-STRUCTURE-NODE` (gate #2, real feature gap).** Spec 26 D3 says `arc_import_analyze` stamps `source='decompiled'` on minted `structure_node`s — but that flow (`motif_deconstruct.py`) mints a reusable **`arc_template`** (`source='imported'`), NOT a `structure_node`. The arc DECOMPILER the spec envisions (mine a book's own prose → template-less `structure_node`s, `source='decompiled'`, `arc_template_id` NULL, Tier-W propose→confirm, IX-17 volume-aligned) **does not exist** — a distinct feature from template-import. The `structure_node.source` column is ready (D1); minting decompiled arcs needs a design decision + a real build. NOT force-built — a write-only `source` param with no consumer is the write-only-blob anti-pattern IX-11 warns against.
  - **✅ 26-D1 `/review-impl` fix SHIPPED (`ecd972a25`) — 1 HIGH, reachable, unit-green-missed.** The D1 partial unique index `uq_outline_node_decompile_key` filtered only `WHERE decompile_key IS NOT NULL`, but the decompiler's idempotency probe filters `AND NOT is_archived`. So: mint a scene → user deletes it via `composition_node_archive` (`is_archived=true`, key retained) → re-import → the probe skips the tombstone → INSERTs the same `(book_id, key)` → **UniqueViolation aborts the whole book's decompile** (pre-D1 this re-minted cleanly — D1's constraint introduced the crash). Fix: index predicate now mirrors the producer — `… WHERE decompile_key IS NOT NULL AND NOT is_archived` (one LIVE decompiled node per (book,key); tombstones exempt), with a **self-healing DO-block** that drops a stale index built without the exemption (IF-NOT-EXISTS can't replace a differing predicate — `add-column-if-not-exists-never-revisits-a-bad-default`). Proven by real SQL: the new `test_archived_decompiled_node_rerun_does_not_collide` REDS against the stale predicate with the exact `UniqueViolationError` and GREENS against the fix (8/8 decompiler DB tests); dev schema rebuilt from the fixed migration. Lesson: `reconcile-by-truth-mirror-producer-predicate` — a uniqueness constraint must share the WHERE of the producer that probes for the row it guards.
  - **26-D1 review — 1 resolved, 1 genuinely gate-#3-held:**
    - **✅ `D-DECOMP-REIMPORT-RESURRECTS-DELETED-SCENE` RESOLVED (conscious won't-fix, documented).** Because the probe skips archived rows, a re-import re-mints a scene the user soft-DELETED. Both defaults have a real failure mode: *resurrect* (keep current) re-adds a deleted scene on the next reparse (annoying, but **non-destructive** — the user re-deletes); *respect-the-delete* (suppress on a matching `decompile_key` tombstone) would **suppress a legitimately-changed scene** at the same `chapter:sort_order` after a source edit (silent data omission). Decision: **keep resurrect** — the non-destructive default is safer than silent omission, and the model "the decompiled spec mirrors current source" is coherent (to remove a scene permanently, remove it from source). Re-open only if authoring feedback shows the re-add is worse than the omission risk.
    - **`D-DECOMP-KEY-COLLIDES-ON-SPEC-BRANCH`** (LOW, gate #3 — genuinely held: no branch-copy code exists to fix). `decompile_key` is unique per `(book_id, …)` but scenes only ever mint into the book's **canonical** partition today, so it cannot collide across Works. When 23 BA8 spec-**branching** (derivative Works sharing a `book_id`) is built, the branch/copy of `outline_node` rows MUST null `decompile_key` on the copy (or scope the key by `project_id`), else the copy collides on `uq_outline_node_decompile_key`. This is a **tripwire for the future branch-builder**, not buildable now (there is no derivative-Work copy path to modify). Trigger: implementing derivative-Work branch/copy.
  - **✅ 22-C1 SHIPPED (`7497904b8`) — FE scene foundation.** `OutlineNode` (`composition/types.ts`) widened with the intent/craft fields the inspector/browser render (goal, pov_entity_id, present_entity_ids, tension, structure_node_id, the 8 SC4 fields, 26 `source`) — all OPTIONAL so the summary projection still type-checks. `booksApi` gained the `Scene` identity type + `listScenes(bookId, {chapter_id, source_scene_id, q, cursor, limit})` over the VIEW-gated `/v1/books/{id}/scenes`. vitest (4) + tsc + eslint clean.
  - **✅ 22-C2 SHIPPED (`a800f0b94`) — the `scene-browser` dock panel, end-to-end.** Renders the 3-shape UNION (linked / spec_only "not yet written" / index_only "written-not-decompiled|anchor-lost") so an imported book's scenes show BEFORE any Work exists (empty-rail bug fixed at root); Work-less is a first-class greyed-intent state. MVC: `sceneUnion.ts` (pure join, 11 tests) · `useSceneBrowser.ts` (controller) · `SceneBrowserPanel.tsx` (view, 4 component tests). Registered across ALL THREE nav lists in lockstep (catalog.ts + chat-service `panel_id` enum + regenerated `contracts/frontend-tools.contract.json`) + en/studio.json; panel-hygiene(157)+catalog-contract(4)+registry(4)+contract(21) guards green; tsc+eslint clean. **`LIVE-SMOKE deferred to D-SCENE-BROWSER-AGENT-OPEN`** (agent→GUI open needs live browser+chat).
  - **✅ `/review-impl` on the wave SHIPPED (`d8173ce51`) — 6 confirmed fixed (1 HIGH, 4 MED, 1 LOW).** A 5-dimension adversarial review (refute-verified by 2 skeptics each; 9 raw → 7 survived) of the defer-batch + 26-D2 + C1 + C2. Fixed: **HIGH** scene-browser mislabelled most written scenes "not yet written" on any >100-scene book (spec side loaded whole, index side paged) → `joinSceneRows(…, specComplete)` suppresses spec_only until the index is fully paged. **MED** duplicate React key when two scenes anchor one node → 2nd demoted to anchor-lost index_only. **MED** getOutline failure blanked identity rows → `Promise.allSettled` decouple + soft "intent unavailable". **MED** empty-state flash during Work resolve → `ready` gate + Loading state. **MED** partial-content-then-error rendered clean → all 3 stream consumers OR the error into `truncated` + carry `error`. **LOW** Work `unavailable` shown as "no plan" CTA → gated on status. `useSceneBrowser` went from 0 → 5 hook tests; FE 498 panel tests + composition engine/worker 30 green. **Refuted (recorded):** decompiler fast-path dangling anchor (read-side re-derives), package_rekey `to_regclass`/`current_schema` divergence (public-schema-only + test-enforced). **✅ `D-IX12-WRITEBACK-DB-TEST` CLEARED (`c2d06d827`)** — a real-PG test (`BOOK_TEST_DATABASE_URL`-gated, `writeback_db_test.go`) seeds a book+chapter+2 scenes (one anchored, one NULL), feeds a decompile map targeting both, and proves the IX-5 r1 `AND source_scene_id IS NULL` guard: recovered anchor untouched, only the NULL leaf written, idempotent (`linked=1` then `linked=0` live); also confirms the Go string→uuid bind.
  - **✅ `D-SCENE-BROWSER-AGENT-OPEN` CLEARED — live browser smoke + a real bug caught (`dea6e39a0`).** Smoke on a **private** vite dev (`:5200`, my working tree — NOT the concurrent session's `:5199`): logged in, opened Scene Browser via the command palette on a PDF-imported book (registered + i18n-discoverable), rendered **3 `index_only` rows** — imported scenes showing before any plan, empty-rail bug fixed at root, proven LIVE. The smoke **caught a cross-service bug all 498 vitest tests missed**: book-service returns the scene PK as **`scene_id`**, not `id` (`scenes.go:238`), so `sceneUnion` keyed every row `idx:undefined` → React duplicate-key. Fixed (`Scene.id`→`scene_id`) + regression test + re-smoked clean (unique UUID keys, 0 console errors). Exactly why the browser smoke is the C-wave DoD (`agent-gui-loop-needs-live-browser-smoke-not-raw-stream`).
  - **✅ 22-C4 (part) SHIPPED (`8fd0eadf7`) — inline scene-title edit in the SceneRail** (fixes the F2 create-only pathology): the ✎ affordance opens an inline input writing `outline_node.title` (the spec, never `scenes.title`) via the OCC patchNode path; single-click still jumps (M-F). SceneRail 18 tests.
  - **✅ 22-C3 SHIPPED — the `scene-inspector` detail pane (full-stack), + a live browser smoke that caught 2 real bugs.** ⚠ **Commit-attribution artifact:** a concurrent track-d/track-b session's `commit -a` **swept my staged/new C3 files into ITS commits** (mainly `c996889f0`) — the code is FULLY INTACT in HEAD (verified: inspector 159 lines, inline-reload, bare `getNode`, `get_node` route; working tree clean; 513 panel tests + tsc + eslint + live smoke all green), only my commit message was lost. Fixes the F2 pathology (goal/pov/tension/craft were human-invisible or read-only-to-everyone): the inspector reads AND edits them, OCC-guarded, sectioned Identity·Intent·Craft·Grounding (GroundingPanel reused). New VIEW-gated `GET /outline/nodes/{node_id}` (bare, gate-from-row). Clicking a spec-backed scene-browser row selects (bus) + opens it. **The live smoke (vite :5200, my tree — NOT the concurrent `:5199`) caught 2 bugs the mocks hid:** getNode wrongly prefixed `/works/{projectId}/` (bare route → 404 live) → fixed; and confirmed the get_node response shape matches FE `OutlineNode` (seeded a node, 200 with all fields). **LESSON (banked):** in a shared checkout with a live concurrent committer, `git add` then `git commit` races — use **`git commit -- <paths>`** (atomic pathspec, no staging gap).
  - **✅ 26-F SHIPPED (`51a4def37`) — state chips (the conformance-staleness signal made visible).** FE consumer of IX-14 (`GET /books/{id}/conformance/status`, shipped Stage-5): `useConformanceStatus` derives the dirty-chapter set = union of `stale_chapters` over DIRTY arcs (a scene's dirty chip = its arc's `dirty ∧ chapter ∈ stale_chapters`); advisory — a fetch failure just drops the chips. Wired: amber "canon moved" column chip on scene-browser rows whose chapter drifted + a banner on the scene-inspector. New `ConformanceStatus` types + `getConformanceStatus`. FE 519 panel tests + tsc + eslint; live smoke (`:5200`): `/conformance/status` 200 with the exact shape, both panels consume it 0-console-error (3rd smoke — type matched, no bug this time). Committed via `git add … && git commit -- <paths>` (new files can't be pathspec-committed alone).
  - **▶ NEXT FE (remaining C-wave):** **C3b** — pov/present/location entity-picker (glossary lookup) + inspector Links section (SceneGraphCanvas) · **C4b** — SceneRail renders the book-service IDENTITY union (entangles `ManuscriptUnitProvider`) · **C2b** (group-by · bulk spec writes · virtualization · windowed spec paging) · **22-D1/D2** OpenAPI + contract regen. **24-H2.2 lane-layout is Stage-7 Hub** (gated on Deploy 2). Browser-smoke recipe proven on `:5200` (own vite; leave the concurrent `:5199` alone).
  - **▶ AND: Stage 3 / Deploy 2** — build M4/M5 + the T7 rehearsal on a restored snapshot; the destructive run on dev waits for P-4 (a real authoring session, human-gated).
  - **⚠ Deploy 2 (Stage 3, M4/M5) is GATED by P-4** — it deletes the arc rows with no rollback and must wait until Deploy 1 has survived a real authoring session. Do not run it unattended.
  - **Stage-1 deferred — both CLEARED 2026-07-11 (autonomous defer-clearing pass):**
    - **✅ `D-ENGINE-ERRORED-JOB-MARKED-COMPLETED` CLEARED** — the buildable zero-content slice is fixed. `stream_draft` ALWAYS yields a terminal usage frame even after an `LLMError`, so an unresolved-model draft landed `completed` with 0 tokens. `error` now rides that terminal frame ([cowrite.py](../../services/composition-service/app/engine/cowrite.py)); all three consumers — the two inline `event_gen` handlers ([engine.py](../../services/composition-service/app/routers/engine.py)) and the worker's `run_selection_edit` ([operations.py](../../services/composition-service/app/worker/operations.py)) — mark **failed** when an error occurred with NO content, and surface the reason. The taxonomy tail (partial-content-then-error = `completed`+`truncated`) is intentionally kept. Tests: router `test_generate_errored_no_content_marks_failed_not_completed` (+ the after-content control); worker `test_run_selection_edit_errored_no_content_raises` (+ control); cowrite `test_stream_draft_error_no_content_flags_error_on_terminal_frame`.
    - **✅ `D-PKGREKEY-DDL-SCHEMA-QUALIFIER` CLEARED** — all 8 `information_schema` existence guards in [package_rekey.py](../../services/composition-service/app/db/package_rekey.py) now filter `AND table_schema = current_schema()` (search-path-correct), so a same-named table in another schema can't mis-fire the conditional DDL. Guarded by a source-lint `test_package_rekey_information_schema_guards_are_schema_qualified` + its negative control (≥8 guards asserted).

---

**Track D — WS-D0 Wave 2 SHIPPED: `web_search` universalized + the spend gate PROVEN LIVE, 2026-07-10** (branch `feat/context-budget-law`). Evidence: [`docs/eval/tool-liveness/2026-07-10-wave2-web-search-spend-live-smoke.md`](../eval/tool-liveness/2026-07-10-wave2-web-search-spend-live-smoke.md). **WS-D0 is now COMPLETE** (Waves 0/1/2 = `97e1b6ea9`, `bbe18e73b`, this commit).

- **`web_search` is now a first-class universal tool** on **provider-registry** (the only service permitted the outward call). Both transports — the `/internal/web-search` HTTP route and the new MCP tool — go through ONE `runWebSearch` core (`web_search_core.go`): resolve BYOK model → decrypt (keyless OK) → `provider.WebSearch` (already INV-6 neutralized) → `recordSyncUsage`. A third consumer MUST call it, never re-derive it — re-deriving is what produced the three drifted neutralizers Wave 1 deleted.
- **`glossary_web_search` is demoted IN PLACE**, never renamed or deleted: `visibility: legacy` + `superseded_by: web_search` (the field's **first production producer**). It cannot move — the C-GW prefix gate binds a name to its provider — and its `tool-policy.ts` row must stay or every public key scoped to `domain:glossary` 403s. The rename is deliberately **not** transparent at the public edge: `web_search` needs `domain:research`.
- **Hot path 9→10.** `web_search` joins `ALWAYS_ON_CORE_NAMES` — the only *federated* core tool, so it resolves from the catalog, and a degraded gateway omits it rather than advertising a fabricated schema (`_add(None)`; pinned by a new test).
- **The compaction bug is fixed and can't rot again.** `DEFAULT_EXCLUDE_TOOLS = {"web_search"}` had matched **nothing** since it was written (the wire name was only ever `glossary_web_search`), so every web-search result was silently evictable. `test_never_evicts_excluded_tool` passed the whole time — it fed the compactor the same fictional name. New tests pin the set against names the platform *actually registers*.
- **LIVE SMOKE, all gates green** (images rebuilt first — stale images are the false-green trap): `web_search` in `advertised.core` with **0** discovery round-trips · turn suspends with `tier:"R", spend:true, approval_kinds:["spend"]` in **write** mode (⇒ the suspend can only be the spend gate; a Tier-A mutation gate cannot fire for a Tier-R tool — the **tier-orthogonality proof**) · **NO SPEND BEFORE CONSENT**: billing ledger `10 → 10` across a suspended-unapproved turn, `→ 11` after approval · tool returns 5 real sources · `approved_once` persists no allowlist row · `glossary_web_search` still resolves, labeled.
- **Three machine contracts fired and were right** (all fixed, none suppressed): the skill-claims lint (a prompt naming a tool it can't reach — `web_search` is core, so the exemption is now explicit rather than an accident of prefix), the legacy-tool lint (a skill must never name a superseded tool — the deprecation note was removed from the prompt entirely), and the public-gateway domain drift-lock (a new `Domain` is a public **entitlement** decision, not a typing detail).

**Verify:** chat **1326 passed**; composition **1690 passed** (kernel `DEFAULT_EXCLUDE_TOOLS` consumer); mcp-public-gateway **264**; ai-gateway **202**; glossary + provider-registry Go green (incl. a new wire gate pinning `web_search` = Tier-R **and** `paid`, and the `settings_`/`web_` two-namespace prefix mirror of ai-gateway's `EXTRA_PREFIX_MAP`).

**Wave 2 deferred:** none new. Layer-2 spend (a `per_call` pricing dimension + `Reserve`/`Reconcile` on the sync path, deriving `paid_read` from `_meta.paid`) remains out of WS-D0 by design — this wave shipped **consent**, not accounting.

**▶ NEXT:** WS-D1 (`propose_*` lint) · WS-D2+ (TLE harness beyond P0 — its async poller is the one component never live-proven; `kg_build_graph` errors on a fresh project, F6). S-HARNESS's F5 (a mid-tier model under-selects Tier-W/async tools) is the finding CD4's ship gate should block on.

---

**Track D — WS-D0 Wave 1 SHIPPED (5-slice fan-out), 2026-07-10** (branch `feat/context-budget-law`). Spec: [`docs/specs/2026-07-09-mcp-tool-liveness-eval/`](../specs/2026-07-09-mcp-tool-liveness-eval/README.md) · plan [`docs/plans/2026-07-09-track-d-ws-d0-fanout.md`](../plans/2026-07-09-track-d-ws-d0-fanout.md). Wave 0 = `97e1b6ea9`.

- **S-GLOSSARY** — 33 untiered MCP tools got `_meta` (tier+scope, `paid` on `glossary_web_search`/`glossary_deep_research`/`glossary_plan`/`glossary_extract_entities_from_doc`) + a `tools/list` wire gate. Closes the "untiered ⇒ silent-R ⇒ a WRITE runs in ask-mode" hole (`RegisterTool` never validated `_meta`). Caught a naming trap: the codebase's "class W" = direct Edit-gated write = lwmcp **Tier A**; "class C" (confirm-token) = lwmcp **Tier W** — so `glossary_propose_translation`/`_aliases` are A (draft, no token), not W.
- **S-SPEND** — spend-approval gate on the **sync** MCP tool path (`stream_service.py` — NOTE: this file was swept into commit `8bad373b4` by a concurrent broad-add; its dependency `tool_approvals.py` lands in THIS commit, healing the split). Gate is tier-**orthogonal** (fires for a Tier-R paid tool) and mode-**independent** (fires in `ask`). Separate consent kinds via namespaced key `spend::<tool>` (no migration); spend fails **closed**, mutation fails **open**; one card lists both `approval_kinds` (the resume path executes directly, so two gates would bypass the second consent).
- **S-COMPOSITION** — 8 async omissions marked `async_job=True` (5 Tier-W confirm-then-job + 3 `plan_*` enqueue) + wire gates. **`lore_enrichment_auto_enrich` stays Tier A** (spec's "A→W" was wrong — no `confirm_token`; quarantined+cost-bounded by design; spec corrected).
- **S-PRODUCER** — INV-6 web-search neutralization moved to the producer (provider-registry `web_search.go`); the 3 drifted consumer copies each had a *different* hole and **none blocked SSRF**. Producer now folds all Unicode control+space and blocks SSRF (loopback/link-local/private/`169.254.169.254`/`localhost`/`.internal`). **Integration-review add:** `isInternalHost` also blocks obfuscated numeric IPs (`http://2130706433/`, hex/octal/short) that `net.ParseIP` misses but curl/browsers resolve.
- **S-HARNESS** — Tool Liveness Eval P0 (`scripts/eval/tool_liveness/`): SSE driver, **confirm resolver** (no NL harness posted to `/actions/confirm` before), **fixture factory**, **effect oracle** (proven discriminating — phantom rows read back absent). Ran LIVE on gemma ($0); its F1/F3 (untiered glossary tools, `adopt_standards` mints-a-token-but-advertises-read) independently reproduced the exact gaps this wave fixes — because the running containers are **stale images** (⇒ Wave 2 live-smoke MUST rebuild first).

**Verify:** glossary Go + provider-registry Go `go test` green; composition wire+client 10 · lore-enrichment wire 3 · chat spend-gate 11 + regression subset 71 green.

**New deferred (Wave 1):**
- **`D-LORE-ENRICH-MCP-TEST-XDIST-FLAKE`** (LOW, pre-existing, gate #1) — `services/lore-enrichment-service/tests/test_mcp_server.py`'s module-scoped loopback-server fixture is re-instantiated under xdist load-scheduling → intermittent `RuntimeError: StreamableHTTPSessionManager.run() can only be called once per instance`. Proven independent of Wave-1 changes (reproduces with the new file `--ignore`d). Fix: pin that module with `pytest.mark.xdist_group(...)`.
- **Wave 2 (next, SERIAL)** — S-WEB universalize `web_search` on provider-registry (rename/demote `glossary_web_search` in place → `VisibilityLegacy` + `superseded_by`; `tool-policy.ts` `research` domain; fix the `DEFAULT_EXCLUDE_TOOLS` compaction bug that never matched the wire name) → hot-path into `ALWAYS_ON_CORE_NAMES` → **ONE live smoke (rebuild images first): NL research ask → spend card appears → approve → runs**.


**Track B — `D-WS4C-HALFA` SHIPPED. Track B is complete except the W8/W10/W11 product-journey backends (P2, needs its own design pass), 2026-07-10** (branch `feat/context-budget-law`, HEAD `pending`). Spec: [`docs/specs/2026-07-10-ws4c-half-a-canon-auto-capture.md`](../specs/2026-07-10-ws4c-half-a-canon-auto-capture.md).

- **What it closes (F4 write-side).** The durable, always-auto-recalled store is the **glossary** (re-read into the context block every turn) — not `memory_remember` (0.7-confidence, rate-limited, confirm-gated, excluded from L2). Before this, a name coined at turn 3 survived to turn 40 only if the model *chose* to call a write tool. Now, every 4th assistant turn, the exchange's newly-**named** entities land in the book's existing review inbox as `draft` + `ai-suggested` — **human-gated, never canon**; a rejected name carries the `ai-rejected` tombstone and is never re-proposed. (Half B — admitting `llm_tool_call` facts to L2 — shipped in `0742d8373`.)
- **New route: `POST /internal/books/{book_id}/capture-canon`** (glossary). Reuses BOTH existing cores rather than adding a write path: WS-4A's `extractEntityCandidates` (ontology-grounded, injection-framed) + `proposeNewEntity` (per-book advisory lock, `(kind, name-or-alias, scope)` dedup, tombstone gate, `[ai-suggested, assistant]` tags). Capture therefore **cannot mutate an entity that already exists**.
- **The tenancy decision (load-bearing).** Unlike its `/internal` siblings — called by the extraction worker for a job it already owns — this route is driven by a *chat session*, whose `book_id` traces back to user-supplied data. So it **grant-checks `owner_user_id` at `GrantEdit` before the extractor runs**: an internal token is not authorization to write into an arbitrary book, and naming someone else's book cannot spend their tokens. Chat passes the **server-resolved** `book_id` (knowledge's `resolve_book_id(project)`), never the FE-supplied `editor_context.book_id`.
- **Two prompt flavours, one extractor.** The seed-doc prompt's "extract EVERY distinct entity" is right for notes and catastrophic for chat prose (it harvests every common noun into the human's review queue). `flavorChatCapture` instead demands only names the exchange **introduces or defines**, and explicitly blesses the empty result. Shared: shape, grounding, `safePromptField` neutralization, the repair round, the candidate cap.
- **The toggle is a USER setting, not an env flag** (Settings & Config Boundary — capture spends the user's BYOK tokens). `knowledge_projects.canon_capture_enabled` (NOT NULL DEFAULT true, mirroring `tool_calling_enabled`) rides the existing `kctx` wire. `CHAT_CANON_CAPTURE_ENABLED` is a deploy **ceiling**: `effective = AND(deploy, project)`. Every turn logs `fire=… reason=…` — no silent hidden default. Capture **fails CLOSED** everywhere `tool_calling_enabled` fails open (no-project mode, multi-project mode, degraded kctx, an older knowledge-service that omits the field, the resume path): a spend-causing behaviour must never be enabled by an unset value.
- **Live smoke (3 services, real BYOK gemma-26b, $0).** Chat's **real** `CanonCaptureClient` → glossary `:8211` → provider-registry `:8208` → LM Studio. On a clean test-account book: stranger denied with **0 rows written**; owner captured `Ilyana Vosk` + `Marek Tallow` as `draft`+`ai-suggested`; re-capture `created=[] skipped=2` with **0 duplicate names**; a rejected name was not re-proposed. The model also declined to invent a `place` kind for "Grendlehaven", reporting it in `notes` — grounding + selection rule both held on a real 26B local model.
- **Three bugs found in my own REVIEW, fixed:** (1) `NameError` — `_build_project_id` / `_resolved_book_id` live in `stream_response`, but the post-turn block lives in `_emit_chat_turn`; the existing chat suite caught it (96 reds). Fixed by threading a typed `CaptureContext` (`ctx=None` ⇒ fail closed). (2) a bare `asyncio.create_task` on a 90s task is GC-eligible mid-flight — asyncio holds only a weak ref; added a `_pending` strong-ref set + done-callback discard + a test. (3) byte-slicing the source cap would split a CJK rune → rune-safe truncation, and the truncation is **reported**, never a silent partial.
- **Verify:** glossary `go build`/`go vet` clean + `internal/api` suite green (+9 tests); chat **1337 passed** (+31); knowledge **3757 passed, 7 skipped** (+4); `ai-provider-gate` OK; ruff clean.
- **Deliberately NOT captured on the tool-confirm RESUME path** (`resume_stream_response` rebuilds no knowledge context → `ctx=None` → `no_capture_context`). Capture is cadence-based, so a resumed turn defers to the next tick; resolving a book id there would add a knowledge round-trip for no continuity gain.

**`/review-impl` on WS-4C Half A — 2 HIGH + 2 MED found; all fixed, 2026-07-10.**

- **HIGH-1 (money) — capture spent the user's tokens by default.** The project toggle shipped `DEFAULT true` with no settings UI, so every existing and new project began doing an LLM call every 4th turn on the user's own paid model, with no way for its owner to see or stop it. **Flipped to opt-in** (`DEFAULT false` + an idempotent `ALTER COLUMN … SET DEFAULT false` correcting any dev DB that ran the earlier revision of this branch) **and shipped the FE toggle** in `ProjectFormModal` beside `tool_calling_enabled`/`memory_remember_confirm` (disabled without a linked book, mirroring the backend's `no_book` gate). Capture is *ambient* spend — it fires on ordinary chatting for a turn the user never asked for — so **the toggle IS the consent and must start un-granted**, the same boundary Track D's spend gate draws. The DDL test now asserts the `DEFAULT true` string is **absent**.
- **HIGH-2 (process) — `8bad373b4` left HEAD broken for two commits.** `git add stream_service.py` stages the *whole file*; it then carried a concurrent session's uncommitted Track-D spend-gate hunks, whose other half (`tool_approvals.py`) stayed behind. HEAD called `is_tool_approved(...)` with 4 args against a 3-arg def → `TypeError` on every Tier-A tool call in write mode. **It went unseen because pytest runs against the WORKING TREE, not HEAD** — a green 1337-test suite proved nothing about the commit. Repaired by Track D's `bbe18e73b`; re-verified with an AST arity check over every call site at HEAD. **In a shared checkout, `git diff --cached <file>` before committing any co-edited file, and treat a green suite as evidence about the working tree only.**
- **MED-1 — a 409 was diagnosed by status, not by code.** glossary returns 409 for *both* `GLOSS_NO_KINDS` and `GLOSS_BOOK_INVALID_LIFECYCLE` (a trashed book); the client blamed "no entity kinds" for both, sending the reader to fix the wrong thing. Now branches on the envelope's `code`.
- **MED-2 — nothing guarded the `kctx` wire.** The toggle crosses two services on `model_validate(from_attributes)`; a rename on either side silently falls back to the default → capture goes permanently, silently off with nothing red. The live smoke called glossary *directly* and never touched this path. Now pinned on both sides, including the fail-closed default.
- **LOW — the board row overclaimed "domain fixes ✅"**; corrected. Verified since: `glossary_entity_delete` is registered/reachable (`mcp_server.go:89`); NFC/NFD+CJK dedup folding is done (`textnorm` → NFKC + casefold + trad→simp); read-your-writes holds (`select_for_context` applies no status filter, so a fresh draft is searchable); upsert-on-create was resolved *by design* (create-only + `set_attributes`/`rename`). `propose_*`-writes-immediately naming is **Track D's D1**; `glossary_confirm_action` doc-drift can't be confirmed without its original feedback item.
- **Verify:** knowledge targeted **125 passed**; chat `test_canon_capture` **37 passed**; FE `ProjectFormModal.toggles` **10 passed**; `tsc --noEmit` clean.

**`D-WS4C-EFFECTIVE-VALUE` — CLEARED, 2026-07-10** (branch `feat/context-budget-law`). The deploy ceiling is no longer invisible to the FE. Chose option (b): a small **`GET /v1/chat/capabilities`** publishes the deploy-tier ceiling (`{canon_capture: {deploy_allows, source_tier:"system"}}`) rather than folding it into the per-context cascade of `effective-settings` — a deploy kill-switch is process-global, not per-user/per-book, so it does not belong in the shadowing resolver. The **join stays where both halves are known**: the knowledge project-settings modal already holds the user knob (`project.canon_capture_enabled`), so it ANDs the ceiling in (`useChatCapabilities` hook) and, when a deployment has capture off, surfaces "Turned off for this deployment — your choice is saved, but capture won't run" instead of a toggle that silently does nothing (the SET-4 "silently-off" bug). Unknown ceiling (fetch pending/failed) ⇒ assume allowed, so a transient outage never fabricates the warning. Proven by effect: FE test asserts the warning appears iff `deploy_allows === false`; a hook test pins the request path + the degrade-to-null path; BE tests pin the ceiling on/off + auth. **Verify:** chat-service **1380 passed**; FE knowledge components **450** + chat-ai-settings **38**; `tsc --noEmit` clean; provider-gate OK.

**`D-KG-GLOSSARY-FK-GLOBAL-UNIQUE` — CLEARED (schema + event path), 2026-07-10** (branch `feat/context-budget-law`, HEAD `pending`). Spec: [`docs/specs/2026-07-10-kg-glossary-fk-project-scoped.md`](../specs/2026-07-10-kg-glossary-fk-project-scoped.md). Track B's deferred list is now **empty**.

- **Root cause: two anchor-writers with contradictory identity models.** `upsert_glossary_anchor` MERGEs on `Entity.id = hash(user, project, name, kind)` (per-project), while `sync_glossary_entity_to_neo4j` MERGEd on `(user_id, glossary_entity_id)` (shared across projects) — and the Neo4j constraint `entity_glossary_id_unique` silently enforced the *shared* model **globally, across every tenant and project**. `glossary_sync`'s own header admitted the fallout: it had to overwrite `project_id` on ON MATCH ("latest-sync wins"), making the field meaningless while every read (salience, coref, graph views) filters on it. Consequence: a second knowledge project over a book could not anchor anything the first had anchored — breaking `kg_project_entities_to_nodes` **and the shipped extraction Pass-0 pre-loader**.
- **Fix (per-project identity, matching `Entity.id`):** constraint → composite `(user_id, project_id, glossary_entity_id)`; `get_entity_by_glossary_id` takes a **required** `project_id`; `get_neighborhood_by_glossary_id` takes an **optional** one (its only caller is glossary's wiki renderer, which knows a book not a project — deterministic first-node + warn, no cross-service contract change); `glossary_sync`'s MERGE key gains `project_id` and no longer stomps it; `glossary.entity_merged` now consolidates in **every** project of the book (this also fixes the arbitrary `LIMIT 1` drift its own comment flagged).
- **No backfill.** Existing data satisfies the strictly-stronger global constraint, so the composite creates cleanly — confirmed by swapping it on the **real dev graph (5023 anchored nodes)**. Composite uniqueness is Community-supported (only NODE KEY is Enterprise); NULL-bearing rows stay exempt, so discovered entities (FK NULL) are unaffected exactly as before.
- **Live proof (the bug was only ever visible live).** Re-ran the WS-4B projection on the *exact* book that previously conflicted (100 entities, 80 owned by that book's other project): **`nodes_created` 20 → 100, `nodes_conflicted` 80 → 0**, idempotent on re-run, the other project's nodes untouched, test tenant cleaned up.
- **Verify:** knowledge unit suite **3753 passed**; Neo4j integration `test_entities_repo_k11_5b.py` + `test_neo4j_schema.py` **34 passed** against the live graph (incl. the new `test_fk_unique_is_per_project_not_global` and the schema drift-lock, which correctly caught the constraint rename); `ai-provider-gate` OK. Two integration failures seen while running the broader suite are **pre-existing and unrelated** — `test_entities_browse_repo.py` omits a now-required `expected_version` kwarg (API drift from another branch) and `test_passages_repo.py` trips on leftover `:Passage` nodes in the shared dev graph.
- **Kept deliberately:** `kg_project_entities_to_nodes`'s `nodes_conflicted` counter. It should now always be 0; it stays as a self-explaining guard so a future constraint regression can never present a partial projection as a success.
- **Ops note:** the schema runner applies `neo4j_schema.cypher` on startup, so the constraint swap lands automatically on deploy. It was applied to the dev graph by hand during this work.

**Track B — ALL deferred items cleared + both live-smokes run; 1 new schema bug found, 2026-07-10** (branch `feat/context-budget-law`, HEAD `pending`). Cleared every Track-B defer before resuming. The live smokes were worth it: they found a real bug the mocks could never have.

- **`D-GLOSSARY-KNOWN-ENTITIES-STATUS-PARAM` — CLEARED.** `getKnownEntities` now reads `status` (closed set `active|inactive|draft|rejected`, invalid ⇒ 400); absent ⇒ **no filter**, which is the behavior every caller has always actually had. Client default changed `"active"` → **None**, and `load_glossary_anchors` / `build_wiki_effect` updated to send none. **This mattered: both entity-creation paths insert `status='draft'`**, so had the param ever been honored, the wiki and the extraction anchors would have gotten ~nothing. Live-proved: `status=active` on a real 100-entity book returns **0**; `status=draft` returns **100**.
- **`D-ANCHOR-PRELOAD-50-CAP` — CLEARED.** Handler gained `offset` + a deterministic `ORDER BY … , e.entity_id ASC` tiebreak; new `GlossaryClient.list_all_entities()` pages to exhaustion with a `max_pages` runaway guard and an honest `truncated` flag (a mid-walk page failure returns the partial + `truncated=True`, never a silent short read). **Extraction Pass-0 silently anchored only 50** entities of any book — a 300-entity book let the extractor mint duplicate nodes for 250. Now pages. `build_wiki_effect` had the same 50-cap; fixed.
- **`D-KNOWLEDGE-TOOL-ERRORS-NOT-ISERROR` — CLEARED.** `_dispatch` now **raises `ToolError`** on a tool failure, so the MCP result carries `isError:true` and ai-gateway's C4 normalizer sees it (it previously returned `{"success": false}` on an otherwise *successful* result — a consumer branching on `isError` read a failure as success). The error body is the C4-shaped JSON `{code?, message, detail?}` — the same shape ai-gateway writes — and chat's `knowledge_client._error_envelope()` decodes it, so `KG_ENDPOINT_NOT_NODE` + `detail.missing` now genuinely reach a workflow. **Found doing this: C5 was NOT satisfied end-to-end** — chat's consumer had been dropping `code`/`detail`.
- **`D-WS4A-LIVE-SMOKE` — CLEARED.** `glossary_extract_entities_from_doc` driven through the real `/mcp` endpoint with a real BYOK model (lm_studio `google/gemma-4-26b-a4b-qat` via provider-registry) on a 31-kind book: 5 candidates, all with real kind + attribute codes, all 4 seeded proper nouns found, the 2 unmappable items honestly reported in `notes`, and **no `name` attribute** (the /review-impl LOW-3 fix holds live).
- **`D-WS4B-LIVE-SMOKE` — CLEARED.** `project_glossary_entities_to_nodes` driven against the real glossary HTTP route + real dev Neo4j on a fresh tenant: the **old default read 9 of 35 entities** (the HIGH-1 bug, reproduced on production data); paged read gets all 35; projection creates 35 anchored nodes, is idempotent on re-run (0 created / 35 existing), tenant-scoped, subset-by-`entity_ids` works; test nodes cleaned up.

**NEW finding (from the live smoke) — `D-KG-GLOSSARY-FK-GLOBAL-UNIQUE` (HIGH, pre-existing, structural).** The Neo4j constraint `entity_glossary_id_unique` makes `Entity.glossary_entity_id` **globally unique across every tenant and project**, yet `Entity.id` is `hash(user_id, project_id, name, kind)` — so the same glossary entity legitimately maps to a *different node per project*. Consequence: **a second knowledge project over the same book cannot anchor any entity the first one anchored** (`ConstraintValidationFailed`); this hits `kg_project_entities_to_nodes` AND the shipped extraction Pass-0 anchor pre-load. Reproduced live: projecting a book into a new project anchored only 20 of 100 entities, the other 80 already owned by that book's existing project.
- **Mitigated now (honesty):** the projection catches `ConstraintError`, counts it as `conflicted` (separate from `skipped`), and the tool returns `nodes_conflicted` + a plain-language `note` — instead of silently reporting a smaller `nodes_created` that reads like success.
- **Proper fix (needs its own plan — deferred, gate #2 structural):** replace the global constraint with a composite `(user_id, project_id, glossary_entity_id)` uniqueness (Community supports composite uniqueness; NULL-bearing rows are exempt, so discovered entities are unaffected), then **project-scope `get_entity_by_glossary_id`** (today only `user_id`-scoped, and its multi-row safety net would silently return an arbitrary project's node) and update its one real caller, the shipped `glossary.entity_merged` event handler, to consolidate per-project. Touches a live event path → own VERIFY.

**Verify:** glossary-service `go build`/`go vet` clean + **full `internal/api` suite green against a real Postgres (96s)**, incl. a new DB regression test proving the prose-less/status/offset semantics. knowledge-service **3751 passed**; chat-service **1291 passed**. `ai-provider-gate.py` OK.

**`/review-impl` on Track B — 2 HIGH + 1 LOW found and fixed; 3 deferred, 2026-07-09** (branch `feat/context-budget-law`, HEAD `pending`). Adversarial review of the 4 Track-B commits. The two HIGHs were both hidden by **mocked clients in my own unit tests** — the classic "the mock encoded my assumption, not reality" gap.

- **HIGH-1 — WS-4B's headline path was broken for its ONLY scenario.** `project_glossary_entities_to_nodes` called `list_entities(book_id, status_filter="active")`, inheriting three `known-entities` handler defaults: `min_frequency=2` (→ `HAVING COUNT(cl.link_id) >= 2` over a **LEFT JOIN** of chapter links), `limit=50`, `alive=true`. So on a **prose-less book — exactly scenario S04's premise ("my chapters are still empty")** — it returned **zero** entities and projected **zero** nodes. It also silently truncated any glossary >50 and silently dropped narratively-**dead** characters (`alive` is a story flag, not a review status). Fixed: pass `min_frequency=0` (even `1` excludes an unlinked entity), `include_dead=True`, `limit=500` (the handler's cap); `ProjectionResult.truncated` + a `note` now surface a partial projection instead of reporting it as complete. Also discovered: the handler **never reads the `status` query param at all**, so `status_filter` was always a no-op (see deferred).
- **HIGH-2 — WS-4C's additive tool-fact branch could silently zero the ENTIRE L2 memory layer.** `_select_tool_facts` ran FIRST in `select_l2_facts` and was unguarded; any failure propagated out, was swallowed by Mode 3's `_safe_l2_facts`, and returned an empty `L2FactResult` — discarding the relations/negations that would have succeeded. Worse, `list_facts_by_type` raises on `limit<=0`, so an operator setting `CONTEXT_L2_TOOL_FACTS_LIMIT=0` to "disable" the feature would have **killed all L2 recall**. Fixed: own try/except (mirroring the codebase's own documented 2-hop discipline) + skip on non-positive limit.
- **LOW-3 — WS-4A advertised `name` as a settable attribute.** Every kind carries a required `name` attr_def (`kinds_crud.go:125` force-adds it), so the grounding prompt listed it and `parseDocExtraction` accepted `attributes:{"name":…}` — a second name conflicting with the candidate's top-level one. Inert at create (`ON CONFLICT DO NOTHING`) but a silent **rename** if a workflow fed those attributes to `glossary_entity_set_attributes`. Fixed: excluded from both the prompt and the candidate filter.
- **Verified clean (not rubber-stamped):** `kg_project_entities_to_nodes` is correctly tiered `("A","project")` by Track A's `_meta` adoption (a silent-R default would have made it runnable in read-only *ask* mode); `ai-provider-gate.py` passes (no direct SDK / hardcoded model — WS-4A resolves BYOK via provider-registry); glossary `by-ids` is book-scoped (`WHERE e.book_id=$1`) and `book_id` comes from `project_meta`, not the caller, so the subset projection can't read another book; `existing_entity_node_ids` filters `user_id` and matches `Entity.id` — the same id-space confirm-time `create_relation` uses — so the fail-fast can't leak another tenant's node existence; the `__was_created` marker is REMOVEd before the `user_id` filter so it can never persist (live-verified earlier); rename's grant-check-then-lookup ordering preserves the anti-oracle; `current` survives budget trimming ("keep current/recent/negative").
- **Verify:** knowledge-service unit suite **3707 passed** (4 new regression tests pinning the exact glossary-read params, truncation reporting, tool-fact degrade-safety, and the zero-limit guard); glossary-service `go build`/`go vet` clean, `internal/api` green (2 new tests). **`D-WS4B-LIVE-SMOKE` is now HIGHER priority** — the HIGH-1 bug lived precisely in the mocked glossary HTTP read; glossary-service/Postgres are down locally so the real round-trip is still unverified.

**New deferred items:**
- **`D-GLOSSARY-KNOWN-ENTITIES-STATUS-PARAM`** (MED) — `getKnownEntities` never reads the `status` query param; every caller's `status_filter="active"` is silently ignored (a write-only parameter). Fixing it server-side would change shipped extraction behavior → needs its own verify.
- **`D-ANCHOR-PRELOAD-50-CAP`** (MED, latent, pre-existing) — extraction Pass-0's `load_glossary_anchors` also passes no `limit`, so it silently pre-loads at most **50** anchors; a book with 300 curated entities anchors 50 and lets extraction mint duplicate nodes for the rest. Deliberately NOT changed here (alters shipped extraction resolution; own verify needed).
- **`D-KNOWLEDGE-TOOL-ERRORS-NOT-ISERROR`** (LOW) — knowledge-service `_dispatch` returns tool failures as `{"success": false, …}` on a *successful* MCP result, never `isError`, so ai-gateway's C4 normalizer never sees them. My `code`/`detail` therefore survive verbatim (C5 satisfied), but a C4-aware consumer branching on `isError` won't detect the failure. Pre-existing across all knowledge tools.


**`D-PRICING-REFRESH` — BYOK model pricing is now editable + OpenRouter live-check, 2026-07-09** (branch `feat/context-budget-law`, HEAD `pending`, commit `6f06b3810`). User-reported bug: registering a paid model (e.g. OpenAI gpt-4o) pre-filled a price with NO way to correct or refresh it afterward — `patchUserModel` never had a `pricing` field (`createUserModel` was the only write path, ever built), and no UI showed the numeric rate anywhere.

- **Root constraint (shaped the fix):** neither OpenAI, Anthropic, nor Google publish a machine-readable pricing API — a genuine "auto re-fetch from the provider" isn't possible. OpenRouter (third-party model-routing aggregator) does expose a public, unauthenticated live catalog it keeps in sync (they resell those models) — the closest available public source, used as a best-effort SUGGESTION only, never auto-applied.
- **Backend**: `parsePricingInput` extracted as the one validator shared by create+patch (patch never had pricing validation before — it never had the field). New `GET .../user-models/{id}/pricing/suggest` (`billing.FetchOpenRouterPricing`) maps `provider_kind` → OpenRouter's namespace (`gemini`→`google`), converts USD/token → USD/Mtok (verified live: gpt-4o's real OpenRouter entry converts to exactly this service's own hand-curated default, 2.50/10.00). Every failure mode (unmapped kind, no catalog match, network error) → `{found:false}`, never an error.
- **Frontend**: `EditModelModal` gains a "Pricing (USD per 1M tokens)" section — the numeric rate was never shown anywhere before this. Editable, with a "Check OpenRouter" button + Apply (never auto-write). Local BYOK kinds show a free note instead. Save spreads the model's existing pricing dims first (media-model fields like `per_image` aren't UI-exposed here) so editing input/output can't clobber them under the full-replace PATCH.
- **Verify**: full backend suite green (`internal/api` + new `internal/billing/openrouter_pricing_test.go`). 7 new frontend tests. **Live-verified end-to-end**: real `GET .../pricing/suggest` against the real OpenRouter API for the test account's real gpt-4o row; PATCH pricing write + negative-rejection + restore via curl; then a full Playwright browser round-trip against a real Vite dev server + real login — edited price, checked OpenRouter, saw the live suggestion, applied it, rejected a negative value client-side, saved a valid value, confirmed persisted in Postgres, zero console errors.
- i18n: new keys authored in `en`, scaffolded to all 16 other locales via `scripts/i18n_translate.py` (0 failed keys).
- **`/review-impl` on this feature (commit `cd099fdf8`) — 3 findings, all fixed:** **MED** every "Check OpenRouter" click re-downloaded the entire catalog uncached (repeated third-party load, risked a rate-limit/block silently degrading the feature for everyone) → added a 10-min in-memory TTL cache that serves stale-but-present data through a later fetch error (live-verified: 2nd call 668ms→4.9ms). **MED** every failure path logged nothing (no way to tell "not on OpenRouter" from "OpenRouter's blocking us") → added `slog.Warn` on every degrade branch, caller still only ever sees `{found:false}`. **LOW** `openRouterNamespace`/`defaultPriceTable` are two hand-maintained provider_kind lists with nothing enforcing they stay in sync → added a drift test. New tests for all three; full backend suite green; rebuilt + re-verified live.

---

**Track B — domain-feedback backlog verified mostly-stale; 1 discoverability nit fixed, 2026-07-09** (branch `feat/context-budget-law`, HEAD `pending`). Verified the Track-B "domain feedback fixes" checklist against code before building (the "debt lists overstate real debt" lesson held):
- **dedup NFC/NFD + read-your-writes → ALREADY DONE.** `textnorm.Normalize` is NFKC (+ casefold + CJK trad→simp); "NFKC subsumes NFC", so NFC/NFD inputs dedup to the same `normalized_name`. Read-your-writes closed by `D-GLOSSARY-PROPOSE-LOCK` (dedup+create under one tx + per-book advisory lock).
- **propose_* naming → NON-ISSUE.** `glossary_propose_entities` already says "created as a DRAFT suggestion in the review inbox — NOT canon"; the propose→confirm tools (`propose_new_kind`/`_kinds`/`plan`) correctly mint a confirm-token. Naming is consistent.
- **upsert/merge-on-create → conscious won't-fix.** The create-vs-edit split is already clean: `glossary_propose_entities` CREATES (skip-on-exists), `glossary_entity_set_attributes` (Tier-A) is the dedicated merge-onto-existing path. Making propose also merge would risk silently clobbering human edits.
- **`glossary_confirm_action` doc-drift → not a Track-B file.** It's a FRONTEND tool (chat-service `frontend_tools.py`/`agent_surface.py`), outside Track B's chat-service partition (B owns only the auto-capture context/persist files). Flag for Track A / a coordinated pass.
- **FIXED (the one real, cheap item):** `glossary_propose_entities`' skip-exists description now points the agent at `glossary_entity_set_attributes`/`glossary_entity_rename` to edit an existing entity (discoverability — an agent that hits `skipped_exists` now knows the next move). Build + `internal/api` tests green.

**Track B remaining:** WS-4C Half A (deferred `D-WS4C-HALFA`, below) + the **W8/W10/W11 product-journey backends** (onboarding-fork, world-container graph/map authoring, reader spoiler-cutoff) — these are **large P2 features** that each warrant their own CLARIFY/design pass, not blind building; recommend prioritizing with the human before starting.

---

**Track B — WS-4C Half B (memory facts → L2 auto-recall) shipped; Half A deferred, 2026-07-09** (branch `feat/context-budget-law`, HEAD `pending`). User chose the human-gated design ("inbox entities + L2 facts") for WS-4C auto-capture. All in knowledge-service (independent).

- **Half B (SHIPPED) — admit `memory_remember`/`llm_tool_call` facts into per-turn L2 auto-recall.** Root-cause correction to the spec's premise: these facts weren't merely confidence-gated out — `select_l2_facts` **never queried decision/preference/milestone facts at all** (only relations + negations), and memory facts are also unanchored (no `:ABOUT` edge, `from_order=NULL`) + written at 0.7. So the real fix is a **new project-level selection branch**, not lowering a threshold. Added `_select_tool_facts` to `select_l2_facts` (runs even with no entity named — these are project-level "we decided X"/"user prefers Y" canon), backed by a new `source_type` filter on `list_facts_by_type`, gated by `context_l2_tool_facts` (default on) at `context_l2_tool_fact_min_confidence=0.7`, capped at 20/turn. Facts land in `current` (each sentence carries its own polarity), keeping `negative` purely entity-anchored so the widened-retry miss-detection isn't perturbed (guard changed from `total()==0` → `not background and not negative`).
- **Verify:** knowledge-service unit suite **3703 passed** (3 new selector/mode tests incl. "tool facts don't mask the relation-retry"). **Source_type filter Cypher LIVE-VERIFIED against dev Neo4j** (`:7688`): llm_tool_call@0.7 selected, correctly excluded@0.8 without the filter, tenant-isolated.
- **Half A (DEFERRED — `D-WS4C-HALFA`): auto-capture user-stated new proper-nouns as `ai-suggested` glossary entities (review inbox).** Blocked on a coordinated touch-point: the per-turn trigger fits ONLY in `stream_service.py`'s post-turn best-effort block (spawn a task, like `_fire_executive_tick`), and that file currently carries **Track A's uncommitted WS-1a changes** — editing/committing it would entangle their work. Once Track A commits `stream_service.py`, Half A is a clean self-contained build: a new Track-B `canon_capture.py` module + a chat-side glossary write-client (chat has only a read client today) pointing at glossary `POST /internal/books/{id}/extract-entities` with `default_tags=["ai-suggested","chat-captured"]` + one spawn line + tests. Gate reason #4 (blocked on concurrent external work in the exact shared file). **Design note:** captured entities land in the review inbox (not silent canon), so they're auto-injected only after the user approves — Half B covers the immediate within-session recall.

---

**Track B — WS-4B glossary→KG projection + kg_propose_edge fail-fast shipped, 2026-07-09** (branch `feat/context-budget-law`, HEAD `pending`). Second Track B milestone; all in knowledge-service (disjoint from Track A/glossary). Unblocks scenario S04 ("map how everything connects" from recorded lore, no chapter prose).

- **`kg_project_entities_to_nodes(project_id, entity_ids?)` → `{nodes_created, nodes_existing, entities_seen, skipped}` (Tier-A).** Deterministic, idempotent projection of a book's glossary entities into the KG as canonical `:Entity` nodes — the structured, prose-less way to seed the graph. Orchestrator `project_glossary_entities_to_nodes` in `anchor_loader.py` (sibling of the extraction Pass-0 `load_glossary_anchors`); reuses `upsert_glossary_anchor`. `entity_ids` given → project that subset (`fetch_entities_by_ids`); omit → whole active glossary (`list_entities`). Book-less project → clear error.
- **Created-vs-existing accounting** via a transient `__was_created` marker in `_UPSERT_ANCHOR_CYPHER` (read into a return column, then `REMOVE`d — never persists). New `upsert_glossary_anchor_counted`; base `upsert_glossary_anchor` now delegates to it (extraction path unchanged).
- **`kg_propose_edge` fail-fast (contract C5):** a read-only endpoint-existence precheck (`existing_entity_node_ids`, matching `Entity.id` exactly as confirm-time `create_relation` does) rejects an edge whose endpoints aren't nodes yet with `{code:"KG_ENDPOINT_NOT_NODE", detail:{missing:[...]}}` — instead of parking then failing at confirm. Runs as the LAST gate (after the cheap schema/temporal checks). This READS Neo4j but never writes it (INV-K1's human-gated-write intact).
- **Structured tool errors:** `ToolExecutionError`/`ToolResult`/`_dispatch` now carry optional `code`/`detail` (backward-compatible; contract C4/C5) so a workflow can branch on `KG_ENDPOINT_NOT_NODE`.
- **4 MCP registration sites** updated (arg model · OpenAI def · FastMCP signature · handler map); drift-lock count 30→31.
- **Verify:** knowledge-service unit suite **3700 passed**; drift-lock + new handler/projection/fail-fast tests green. **Cypher LIVE-VERIFIED against the running dev Neo4j** (`:7688`) via a safe unique-test-id script: create→was_created=True, re-run→False, transient marker doesn't persist, base upsert intact, tenant-isolated existence check. **Live-smoke deferred — `D-WS4B-LIVE-SMOKE`**: the full MCP round-trip (knowledge→glossary HTTP read + Neo4j write through the gateway) needs a real book+glossary+project — smoke at N3 (flagship S04/S06); glossary read reuses the shipped extraction Pass-0 client methods, so risk is low.
- **Next in Track B:** WS-4C auto-capture (chat canon → glossary entities + admit `llm_tool_call` facts to L2).

---

**`/review-impl` on the chat context-meter fix — 2 findings, both fixed, 2026-07-09** (branch `feat/context-budget-law`, HEAD `pending`, commit `0ec923018`). Adversarial review of the entry below (`D-CHAT-CONTEXT-METER-OVERCOUNT` + compact fix).

- **MED — `apiJson`'s `detail` fallback only handled string/422-array shapes**, missing the plain-object `{code, message}` / `{code}` shape `composition-service` (`actions.py`'s `{"code":"action_error"}`) and `campaign-service` (`grant_deps.py`'s `{code, message}`) actually raise — those errors still fell back to the meaningless `statusText`, the exact bug class the fix was meant to close. Fixed: read `detail.message ?? detail.code` when `detail` is a non-array object.
- **LOW — the new regression test didn't assert `raw_tokens`** (the Inspector's `reduction_pct` baseline) also uses the true-occupancy value, only `used_tokens`/persisted `caching.context_size`/the billed column. Added the missing assertion.
- **Verified clean, no other finding**: traced every `compute_budget`/`used_tokens` consumer (mid-turn compaction trigger uses a fresh assembly-time estimate, unaffected; the stateful-chain guard already used `context_size`; `voice_stream_service.py` doesn't use this meter; the FE History chart plots per-category `breakdown`, never `used_tokens`, so it was never affected by the sum bug); confirmed the `_ctx_size==0` fallback edge case is safe; confirmed `raw_tokens >= used_tokens` always holds. No ENFORCED/LOCKED standard touched (checked the Context Budget Law quick-nav entry — `used_tokens` isn't a frozen spec field).
- **Verify**: frontend full suite green (4522/4522). Backend: chat-service full suite 1254 passed / 1 failed — the failure (`test_tool_discovery.py::TestGenericFrontendTools::test_universal_core_advertises_generic_frontend_tools`) is from a **concurrent session's uncommitted WS-1a work** (`tool_list`/`tool_load`, 214 uncommitted lines in `tool_discovery.py`/`stream_service.py` at review time) sharing this checkout — confirmed unrelated via `git diff --stat`, untouched by this commit.

---

**Track B (agent-discoverability effort) — WS-4A seed-doc→entities + entity rename shipped, 2026-07-09** (branch `feat/context-budget-law`, HEAD `pending`). First milestone of Track B ([`docs/specs/2026-07-09-agent-discoverability-and-workflow/tracks/TRACK-B.md`](../specs/2026-07-09-agent-discoverability-and-workflow/tracks/TRACK-B.md)). Both new tools in glossary-service, disjoint from Track A's files (A is concurrently on the discovery spine).

- **WS-4A · `glossary_extract_entities_from_doc(book_id, source_markdown, kinds_hint?)` → `{candidates:[{kind,name,attributes}], notes?}` (Tier-R, no writes).** The seed-doc→entity-candidates bridge (workflow W2 / scenario S02 Path B — "add everyone in these notes"). Grounds a user-BYOK model in the book's EXISTING ontology (kinds + attribute codes/descriptions), returns candidates using only real codes, feeds `glossary_propose_entities`. Reuses the shipped `glossary_plan` LLM pattern (llmClient→provider-registry, loose-emit→validate→1-repair; doc framed as untrusted DATA, ontology descriptions neutralized). New files `entity_doc_extract_tools.go` (+`_test.go`). The parse/validate/filter/dedup core is a pure function with full unit coverage.
- **Entity identity · `glossary_entity_rename(book_id, entity_id, name)` (Tier-A).** First-class discoverable rename delegating to the exact `setEntityAttributes` core (`{"name": …}`), so it can't drift from the general editor. Added to `entity_attribute_edit_tools.go`. `glossary_entity_delete` already existed/reachable (Tier-W) — nothing to build there.
- **Contract note:** refined C5 for rename — signature takes `book_id` (anti-oracle: grant-check the named book first) and tier is **A not W** (rename is reversible; set_attributes already renames at Tier-A). Recorded in the umbrella `contracts.md` + `tracks/BOARD.md` change logs; **Track C**: rename workflow steps use `gate: none`.
- **Verify:** glossary-service `go build`/`go vet` clean; full `internal/api` package green (new unit tests + no regressions). **Live-smoke deferred — `D-WS4A-LIVE-SMOKE`**: WS-4A's LLM round-trip (glossary→provider-registry) wasn't live-smoked (needs the stack up + a BYOK chat model); plumbing is identical to the shipped `glossary_plan`, so risk is low — smoke it at N3 (flagship S06) or next stack-up.
- **Next in Track B:** WS-4B (`kg_project_entities_to_nodes` + `kg_propose_edge` fail-fast `KG_ENDPOINT_NOT_NODE`) in knowledge-service — code already mapped (`upsert_glossary_anchor` is the projection primitive; needs `{nodes_created,nodes_existing}` accounting + a GlossaryClient on ToolContext).

---

**`D-CHAT-CONTEXT-METER-OVERCOUNT` + compact error-swallowing fixed, 2026-07-09** (branch `feat/context-budget-law`, HEAD `pending`, commit `a7952c57b`). User-reported bug: a 200K-model chat session (`019f42c2-9b20-7449-9245-7856aa5e22b5`) with 54 tool calls across 30 completions in ONE turn showed **935,676/200,000 tokens (469%)** in the GUI meter, and clicking "Compact" surfaced a confusing "Conflict" error instead of the real reason.

- **Root cause (meter)**: `used_tokens` was fed `input_tok` — the SUM of provider input tokens across every completion in the turn's tool-loop (each iteration re-sends the full prompt). That sum IS the real provider billing (correctly untouched for `chat_messages.input_tokens`/`billing.log_usage`/cache hit-rate math) but is NOT context occupancy — the real single-call size was only 34K (17% of the window), a 27x inflation that scales with `llm_call_count`. Fixed: `used_tokens`/`raw_tokens` now use `_ctx_size` (the true last-completion input size, already tracked for the stateful chain's window-boundary guard), falling back to the sum only when unavailable. **This is a known bug class resurfacing** — a 2026-07-06 investigation of the identical symptom fixed the stateful-chain consumer the same way but never migrated the GUI meter path; this closes that gap too.
- **Root cause (compact)**: not actually a crash — a correct 409 "nothing to compact" guard (2 message rows ≤ default `keep_recent=8`, since all 54 tool calls live inside ONE assistant row's JSONB). But FastAPI's `{"detail": ...}` error shape (used by every Python service — chat/knowledge/composition/lore-enrichment) doesn't match `apiJson`'s `ApiError{code,message}` expectation, so the real detail was silently dropped in favor of `res.statusText` ("Conflict"). Fixed `apiJson` to fall back to `detail` (string or joined 422-validation-array) before `statusText` — repo-wide fix, not compact-specific.
- Also clamped `ContextMeter.tsx`'s displayed pct (real overflow still shows, e.g. "142%"; a runaway value like the historical 469% now shows ">299%") as an independent defense-in-depth backstop.
- **Verify**: new regression test reproduces the exact bug shape (sum=3000 across 3 fake completions, true size=1000) and asserts `used_tokens==1000` while the billed `input_tokens` column still carries 3000. Backend full suite green (1243 passed), frontend full suite green (629 files/4520 tests). Rebuilt `chat-service` Docker image; live-verified the compact fix end-to-end against the real gateway (seeded a scratch session with the exact 2-message shape, got the real `409 {"detail":"nothing to compact"}`, confirmed the fixed FE parsing now surfaces it instead of "Conflict").
- **Caveat**: the meter fix is write-path only — the original session's already-persisted `935,676` row is historical data and won't retroactively correct; only new turns going forward compute the true occupancy.

---

**`D-GLOSSARY-PROPOSE-LOCK` cleared — propose-entity dedup TOCTOU race closed, 2026-07-09** (branch `feat/context-budget-law`, HEAD `pending`, commit `a21483b91`). The deferred item from the entry below is resolved, not just re-attempted: `proposeNewEntity`'s dedup check, tombstone check, attr-def load, create, and scope_label set now all run on ONE tx held under the SAME per-book advisory lock the bulk extraction pipeline uses (`extractionWritebackLockNS`, INV-C1). Live-verified against the rebuilt stack: 8 truly concurrent identical MCP `glossary_propose_entities` calls now yield exactly 1 `created` + 7 `skipped_exists`, and exactly 1 DB row (previously 8 duplicates).

**Root cause of the two prior deadlock attempts** (which is why this needed its own session, per the earlier "needs its own connection-budget-aware design" note): `loadAttrDefMap` hardcoded `s.pool` internally with no querier param at all, unlike its sibling helpers (`findEntityByNameOrAlias`, `entityHasTag`, `createExtractedEntity`), all of which already accept a `pgxRWQuerier`. Any caller holding a tx (to take the lock) that then called `loadAttrDefMap` needed a SECOND pool connection while the first stayed open — self-starving under a small pool + concurrent load, not a lock-ordering bug. Fixed generally by giving `loadAttrDefMap` the same `q pgxRWQuerier` param, so `proposeNewEntity` now runs start-to-finish on exactly one connection. **Bonus find:** this also silently affected two production call sites already shipped — `facts_handler.go`'s `internalResolveOrCreateEntity` and `internalSplitEntity` both already open a tx + take the book lock, then called `loadAttrDefMap` (hitting `s.pool` for a 2nd connection) — same latent bug, just never triggered at production concurrency. Both now pass `tx`.

- **Verify**: full glossary-service suite green (`internal/api` 473.021s). Test renamed `TestProposeNewEntity_ConcurrentRaceSerializedByBookLock`, now asserts exactly 1 surviving row (was: any count, just not wrongly-scoped) — 8/8 isolated passes + 4x of the previously-hang-prone combined set, no hangs, ~1.4s each. Rebuilt `glossary-service` Docker image; live re-verified via 8 concurrent MCP calls through the real gateway.

---

**`/review-impl` on the scope_label feature — 5 findings, all fixed, 2026-07-09** (branch `feat/context-budget-law`, HEAD `pending`, commit `23b6007d7`). Adversarial review of the previous entry's scope_label work (backend + frontend). All fixed, verified live.

- **HIGH — `proposeNewEntity` could orphan a wrongly-scoped entity.** The scope_label UPDATE ran as a separate, later `s.pool.Exec` AFTER `createExtractedEntity` had already committed — a failure on that UPDATE (a `uq_entity_dedup` collision) left a real entity committed with `scope_label=''` while reporting "error" and discarding its id (`uuid.Nil`), an unrecoverable orphan. Fixed: one transaction opened right before the writes (after the dedup check + attr-def load, which stay on `s.pool`) so a scope_label failure rolls back the whole creation. **Fixing this surfaced a real connection-pool self-deadlock** (opening the tx too early, before other `s.pool`-only calls, made each concurrent "winner" wait on a second connection while holding its first — reproduced twice, hung the full 10-minute test timeout) — root-caused and corrected by narrowing the transaction's scope. New test (8 concurrent identical proposals) proved the atomicity fix and surfaced a separate, deliberately out-of-scope, pre-existing gap: the dedup check itself had no per-book advisory lock (a genuine TOCTOU race predating scope_label entirely). Tracked as `D-GLOSSARY-PROPOSE-LOCK` — **cleared same day**, see the entry above.
- **MED — scope_label trimmed on 3 of 4 write paths, not the MCP edit tool** (`glossary_entity_set_attributes`) — risking `" World A"` vs `"World A"` being treated as different scopes.
- **MED — no length validation anywhere** (unlike `short_description`'s 500-char cap). Added shared `validateScopeLabel` (trim + 200-char bound) used by all 4 write paths, each returning a clean rejection instead of risking a raw Postgres "index row size exceeds maximum" error.
- **MED — `EntityEditorModal`'s scope_label input was uncontrolled**; after a rejected edit it kept showing the failed value as if it had stuck. Now controlled, synced via `useEffect`, explicitly reverted on error.
- **LOW — the MCP-core collision test only asserted "some error"**, not the specific message; a regression in `isUniqueViolation` detection would have silently degraded without a red test. Now asserts the exact message.
- **Verify**: full glossary-service suite green (509.503s), full frontend suite green (629 files/4515 tests), new concurrency test reliable 8/8 combined + isolated, live end-to-end re-verification against the rebuilt stack (oversized value rejected at create+edit time, whitespace trimmed, DB state unchanged after a rejected edit).

---

**MCP feedback follow-up — 2 discoverability bugs fixed + new entity-attribute-editor tool + entity scope_label feature, 2026-07-08** (branch `feat/context-budget-law`, HEAD `pending`, commits `b7742a600`/`b76c06b1b`/`5f5fc61ca`, source `D:\Works\novels\mi_de\loreweave-mcp-feedback.md`'s newest entries). All 4 items live-verified against the real rebuilt stack (not just unit tests), each via a direct MCP call + Postgres state check.

- **#1 — `find_tools` couldn't surface the only live entity-creation tool for a natural query.** `glossary_propose_entities`'s Meta synonyms/description were all batch-phrased ("bulk", "several") with plural "entities" only — the token-overlap scorer (no stemming) lost the ranking race to `glossary_propose_new_kind`/`_reassign_kind`/`_new_attribute` for a plain "create a new entity" intent (returned 0/8 relevant results). Added singular-entity + create/add/author synonyms. Live-verified: the exact repro intent now returns it FIRST.
- **#2 — `confirm_action({domain:"knowledge"})` 422'd a valid token.** The `find_tools` GROUP name for `kg_*`/`memory_*` tools is `"knowledge"` (chat-service already aliases this internally), but the real confirm route/`DomainConfirmServiceURLs` key is `"kg"` — an agent naturally reused the group name it just discovered the tool under. Added the same alias normalization on auth-service's side (`mcp_approvals.go`, both the self-confirm and human-approval-queue entry points). Live-verified via the internal endpoint: `domain="knowledge"` and `domain="kg"` now behave identically; an unknown domain still correctly 422s.
- **#3 — new tool `glossary_entity_set_attributes` (Tier-A).** Entities were write-once for attribute values via MCP — creation tools only set values at CREATE time and are idempotent-skip on re-call (no merge). No MCP-reachable editor existed even though the REST/UI path (`applyEntityEdit`, `patchAttributeValue`) always supported edit/clear. New tool takes `attr_code -> value` (empty clears, missing code is added via UPSERT since an MCP-created entity doesn't pre-seed every kind attribute), and — since "name" is just another attr_code — this also closes the feedback's separate "no rename" gap for free.
- **#4 — entity `scope_label` (D-GLOSSARY-ENTITY-SCOPE), the "qualifier" design ask.** Author's real problem: a multi-world/reincarnation story has names that legitimately recur (e.g. two unrelated "Lam gia" in different worlds) — the dedup key was `(book_id, kind_id, normalized_name)` only, so these silently collided. CLARIFY'd scope with the author before building: a plain author-set TEXT label (NOT a structured FK to a world_realm entity — no entity-to-entity reference primitive exists anywhere in this schema today, attribute field_types are all scalar), optional for every kind (no kind requires it). Migration 0051 adds `scope_label TEXT NOT NULL DEFAULT ''` + widens `uq_entity_dedup` to `(book_id, kind_id, normalized_name, scope_label)` — additive/non-destructive by construction (every existing row defaults to `''`, a strict superset of the old key). `findEntityByNameOrAlias` takes an added scope param (bulk extraction pipeline + facts_handler pass `""`, unchanged behavior, deliberately out of scope — no scope concept there yet); `glossary_propose_entities` accepts an optional `scope_label` per item; `glossary_entity_set_attributes` can set/clear it on an existing entity (with the same duplicate-collision rejection a name change gets); `glossary_get_entity` surfaces it.
- **Verify (all 4)**: full glossary-service suite green each time (`go build`/`go vet` clean, targeted + full-suite `go test`, up to 511s for the final scope_label pass). Every fix rebuilt into the real `glossary-service`/`auth-service` Docker images and re-verified live: migration 0051 confirmed applied cleanly to the shared dev Postgres (ledger row + reshaped index checked directly), and a full live MCP round-trip (create two same-name-same-kind entities with different `scope_label` → genuinely distinct; a third with a matching scope → correctly deduped; edit-time scope collision → correctly rejected).
- **Follow-up, same day — both deferred items closed + full UI (commits `ba4b40cb2`/`111826050`).** User asked to "do this too" (the two items above) plus update the frontend:
  - `findEntityCrossKind` (bulk extraction pipeline) now takes a scope param (both callers pass `""` — the pipeline still has no scope concept — but this stops an unscoped extraction from silently merging onto a human-disambiguated scoped entity regardless of which world the chapter belongs to). New test: `TestCrossKindDedup_ScopedEntityNotReusedByUnscopedExtraction`.
  - `scope_label` now surfaces on `glossary_list_unknown_entities`/`glossary_list_ai_suggestions` (the actual triage-decision surfaces) and the general `listEntities` REST query.
  - **REST PATCH support added** (`entity_handler.go`) — the manual-edit UI (`EntityEditorModal`) writes via REST `patchEntity`, not the MCP tool, so this was needed for the UI to work at all; a colliding value returns 409 `GLOSS_DUPLICATE_NAME`. New test: `TestPatchEntity_ScopeLabel`.
  - **Full frontend UI**: `EntityEditorModal` gained a scope_label input (commits on blur); `GlossaryEntityList`/`UnknownEntitiesPanel`/`AiSuggestionsPanel` show a violet scope badge; the KG `EntityDetailPanel` surfaces the anchored glossary entity's scope_label read-only. New/updated tests across all touched files; full frontend suite green (629 files / 4514 tests).
  - **Live smoke caught a real bug**: the first Playwright pass against the rebuilt stack showed the PATCH returning 200 but the value never persisting — the running `glossary-service` container was stale (never rebuilt after the `findEntityCrossKind`/PATCH commits), so the old binary silently ignored the unrecognized `scope_label` JSON key (a real instance of the `silent-success-is-a-bug` class). Rebuilding+restarting fixed it; re-verified end to end (create → edit scope_label → persisted in real Postgres → badge renders in the list).

---

**glossary-service test-suite speedup attempt — pre-existing bug fixed, parallelization REVERTED after real deadlock, 2026-07-08** (branch `feat/context-budget-law`, HEAD `pending`, `services/glossary-service/internal/api/export_handler_test.go` only). User asked to (a) fix the known pre-existing `TestExportQueryChapterFilter` flake and (b) investigate parallelizing the Go test suite to use the machine's 32 logical threads (i9-13900K). (a) is done and kept; (b) was attempted at scale, found genuinely unsafe, and reverted — full honesty over a shaky partial win.

- **Kept — `TestExportQueryChapterFilter` row-accumulation bug (the original ask), root-caused + fixed.** `t.Cleanup` was registered AFTER a `t.Fatalf` assertion; `Fatalf` calls `runtime.Goexit()` immediately, so on any failure the cleanup was never reached — against the shared, never-reset dev Postgres this was self-perpetuating (rows observed growing 3→4→5 across repeated runs under a hardcoded `book_id`/`chapter_id`). Fixed: `t.Cleanup` now registered immediately after the inserts (before any assertion that could fail-fast), plus fresh `uuid.New()` ids per run (defense in depth). Verified via repeated fresh (`-count=1`) runs, all green.
- **Kept — per-test pgxpool connection cap.** `openTestDB`'s pool now sets `MaxConns=3` explicitly (`pgxpool.ParseConfig`+`NewWithConfig`) instead of the library default `max(4, NumCPU())` — on this 32-thread machine an uncapped pool could open up to 32 connections each; harmless on its own, protects the shared dev Postgres's `max_connections=100` (already ~68-79 consumed by other locally-running services) regardless of how tests are invoked.
- **Attempted, then REVERTED — broad `t.Parallel()` sweep across ~86 files + a migration-ledger dedup mechanism (`applyOnceOrFatal`, ledger-routing every `runXXXMigrations` helper through `migrate.EnsureLedger`/`migrate.ApplyOnce` to stop each DB test re-running ~24 raw DDL steps unconditionally).** Real ~14x speedup WAS demonstrated when a run happened to succeed (34s vs the ~450-500s baseline) — but after 2 agent sessions + this session's own independent re-verification (~9 full-suite attempts total), **zero fully-green runs were ever achieved**. Two concrete failure modes persisted even after a dedicated fix attempt: (1) `TestK3_AutoRegenOnDescriptionUpdate` failed identically even in near-isolation despite a targeted 50ms-sleep fix already in the code (the fix didn't address the real cause — once migrations stopped re-running, two `now()` calls could land on the same Postgres transaction-timestamp tick; the sleep didn't reliably prevent this); (2) `TestProposeNewEntity_CreatesDraftThenDedups` hit a genuine, live-confirmed Postgres deadlock (`SQLSTATE 40P01`, `adoptTestBook kinds`) — a REAL engine-level deadlock (confirmed via a live `pg_locks` capture), meaning the ledger dedup mechanism, despite its design intent, was not actually eliminating migration/DML lock contention under `t.Parallel()`. Separately, the agent doing this work also found (twice) that 2 shared Postgres functions (`recalculate_entity_snapshot`, `trig_fn_entity_self_snapshot`) had reverted to stale pre-G4 definitions from an unidentified external source during its work window — repaired reactively but never root-caused, a real open risk on this shared, multi-consumer dev database. Given the CLAUDE.md Debugging Protocol hard-stop ("3+ fix attempts fail → stop, question architecture"), zero clean runs, a "fixed" test still failing, and an unexplained external DB mutation — the whole sweep was reverted rather than pushed further or shipped shaky. Reverted 87 of 88 touched files back to HEAD; kept only the two independently-verified fixes above in `export_handler_test.go` (also dropped `t.Parallel()` from that file's own 2 DB-touching tests, `TestUpSnapshotColumnExists`/`TestExportQueryChapterFilter`, for consistency — the migration-dedup mechanism they'd need to be safely parallel no longer exists in the codebase).
- **Verify**: `go build ./...` clean; targeted tests (`TestExportQueryChapterFilter`, `TestUpSnapshotColumnExists`, `TestSnapshotToRAGEntity*`) all green; full `internal/api` suite green, `485.877s` (matches the pre-existing ~450-500s baseline — confirms the speedup is what's being given up, not stability).
- **Answer to the CPU-utilization question**: no, the i9-13900K's 32 threads are NOT being exploited by this suite today (sequential `go test`, single core doing DB round-trips). A real speedup is achievable in principle (~14x demonstrated) but requires migration-DDL/DML lock contention to be solved correctly first — this session's attempt was not sufficient. Left as a genuine, well-scoped follow-on rather than a Deferred row with a quick label, since a next attempt needs a different approach (e.g., run migrations ONCE per test binary in `TestMain` rather than per-helper-on-first-call, or shard DB-touching tests onto their own serialized sub-group while parallelizing only pure-unit tests) — not just a retry of the same ledger idea.

---

**Glossary entity-triage UX — 3 findings shipped, 2026-07-08** (branch `feat/context-budget-law`, HEAD `pending`, commit `698ee6cf5`, source `D:\Works\novels\mi_de\loreweave-mcp-feedback.md`'s "new friction found during real entity-triage work" section). Built via fan-out (2 background agents for A/B, C done directly), all contained to glossary-service, no migration.

- **A — `glossary_entity_delete` (Tier-W propose+confirm) + `glossary_entity_restore` (Tier-A direct)**: no MCP way existed to remove a genuinely empty AI-extraction draft (no name/attributes/evidence — `glossary_propose_reassign_kind` is the wrong tool, nothing to classify). Wraps EXISTING soft-delete/restore core logic (`entity_handler.go`'s `deleteEntity`, `recycle_bin_handler.go`'s `restoreEntity` — previously REST-only), now extracted into `softDeleteEntityCore`/`restoreEntityCore` shared by both surfaces. The frontend's Undo allowlist (`useActivityUndo.ts`) already carried these exact tool names, waiting for a backend that was never built.
- **B — added `"rejected"` as a 4th entity status**: no DB CHECK constraint existed (no migration needed) — consolidated 2 independent literal enum checks in `entity_handler.go` onto the single `validEntityStatus` source of truth, then added the value there once. Frontend: `EntityStatus` type, filter-tab, reject bulk-action button, i18n key (`en` only).
- **C — `glossary_list_unknown_entities`/`glossary_list_ai_suggestions` now default to `status="draft"`** (mirrors the existing `glossary_list_merge_candidates` default-with-override pattern already in the same file; `status="all"` restores the old status-blind behavior) — previously neither filtered by status at all, so triaging an entity never removed it from the next call's results (the inboxes never drained).
- **Verify**: glossary-service full suite green (only the known pre-existing `TestExportQueryChapterFilter` flake, re-confirmed unrelated via `git stash` again today). Frontend: `tsc` clean, 159/159 vitest. **Live-verified end-to-end** against the rebuilt real stack: real `ai-gateway` MCP calls + the real REST `/v1/glossary/actions/confirm` endpoint + real Postgres checks — propose-delete → confirm → soft-deleted in DB → restore → live again; propose-status-change to `'rejected'` → confirm → DB `status='rejected'` → entity drains from the default ai-suggestions view but still shows under `status=all`/`status=rejected`.

---

**#9 follow-up — spec-compliance fix for external clients, 2026-07-08** (branch `feat/context-budget-law`, HEAD `pending`, commit `bed6f522e`). External spec review of the same-day #9 fix (see the entry below) caught a real, verified issue: MCP spec 2025-06-18 "Tools > Structured Content" says a tool returning `structuredContent` **SHOULD** also return the serialized JSON in `content` for backward compat — confirmed by fetching the live spec text directly, not just trusting the claim. `structuredContent` was introduced in that same revision, so a client on an older negotiated protocol version has no way to read it — our compact placeholder would have silently destroyed data for such a client, not just cost it tokens.

- **Root cause of why this wasn't already handled**: our internal traffic (chat-service → ai-gateway → domain services) is fully controlled by us and always reads `structuredContent` — safe as shipped. `mcp-public-gateway` is the ONLY layer that terminates the MCP handshake with an external, third-party client we don't control — investigated and confirmed `ai-gateway` builds a fresh, stateless SDK `Server` per HTTP request with no negotiated-protocol-version getter exposed, so the client's own `mcp-protocol-version` HTTP header (already read per-request by the edge, previously only to forward it) is the only usable signal — no new session state needed.
- **Fix**: new `rehydrateContentForLegacyClients` (`services/mcp-public-gateway/src/scope/structured-content-rehydration.ts`) — when the negotiated version can't be confirmed `>= 2025-06-18` (including an ABSENT header — deliberately conservative default, since wrongly assuming support silently destroys data for a client we'd never hear the complaint from, while wrongly assuming legacy only costs that one response some tokens), rehydrates `content[0].text` from `structuredContent`, but ONLY when it's an exact match for our own SDKs' known placeholder text — never touches a handler's genuinely custom content or an already-always-duplicating tool (e.g. `find_tools`'s own synthetic response). Wired into `public-mcp.controller.ts`'s one generic response-relay chokepoint.
- **Verify**: 12 new tests (version boundary at exactly 2025-06-18, absent-header default, exact-placeholder-only match, batch responses, SSE/non-JSON passthrough, error responses) — mcp-public-gateway 256/256, `tsc --noEmit` clean. **Live-verified end-to-end** through the real rebuilt stack via a freshly minted (then revoked) real `mcp-public-gateway` API key: `mcp-protocol-version: 2025-06-18` → 46-byte placeholder; `2024-11-05` → full 7265-byte rehydrated JSON (structuredContent still present too, additive not destructive); no version header at all → also rehydrates (conservative default confirmed live, not just unit-tested).

---

**External MCP-discoverability audit #9 (payload duplication) — resolved, 2026-07-08** (branch `feat/context-budget-law`, HEAD `pending`, commit `7d7b77639`). Supersedes the "large/structural, deferred" call in the entry below it — root-caused precisely by reading both SDKs' actual source, turning it into a small, well-contained fix instead of a 150+-handler sweep.

- **Root cause, Go** (`github.com/modelcontextprotocol/go-sdk` v1.6.1): `mcp.AddTool`'s own dispatch wrapper auto-fills `res.Content` from the marshaled `Out` struct ONLY when a handler leaves `res.Content` nil — every handler in this codebase does exactly that, so the SDK's "helpful fallback" fires on literally every call. New `sdks/go/loreweave_mcp.RegisterTool[In,Out]` — a DROP-IN replacement for `mcp.AddTool` (identical signature) — wraps the handler to pre-fill a short constant placeholder into `Content` whenever it's nil, making the SDK's own `Content == nil` auto-duplication check false. `StructuredContent` (the only field a real client reads) and any handler-built custom `Content` are both untouched.
- **Wiring, Go**: `book-service`/`catalog-service`/`agent-registry-service`/`provider-registry-service` each ALREADY had their own local generic wrapper around `mcp.AddTool` (found during investigation — turned this into a 1-line delegation per service). `glossary-service` calls `mcp.AddTool` directly ~50 times across 13 files — a mechanical sweep (same call signature, `mcp.AddTool(` → `lwmcp.RegisterTool(`, zero logic change beyond the fix itself), done via a background agent.
- **Root cause, Python** (FastMCP / `mcp` 1.28.1): `FuncMetadata.convert_result` unconditionally builds a full duplicate JSON-text content block alongside `structured_content` whenever a tool has an output schema — no per-handler escape hatch exists (unlike Go). New `sdks/python/loreweave_mcp.patch_convert_result()` monkeypatches this ONCE, defensively (never raises — degrades to the SDK's default behavior if a future `mcp` release changes the target shape). Wired into `make_stateless_fastmcp` (the existing shared chokepoint `composition`/`jobs`/`translation`/`lore-enrichment-service` already build their FastMCP server through — free for all 4) + an explicit call in `knowledge-service` (builds FastMCP directly, but already ships `loreweave_mcp` as a dependency via its Dockerfile's `pip install /sdk` — zero new dependency).
- **Verify (all green except pre-existing, confirmed-unrelated flakes)**: `sdks/go/loreweave_mcp` +3 tests (real in-process client-server round trip via `mcp.NewInMemoryTransports()`), `sdks/python/loreweave_mcp` +4 tests (real FastMCP round trip). book-service 193/194, catalog-service 11/11, agent-registry-service 56/56, provider-registry-service 662/663, glossary-service 582/583 — every one of the 3 non-green results independently re-confirmed via `git stash` to fail IDENTICALLY without this change (book/provider-registry: previously-known `TestMCP_GetChapter_IncludeBody_DB` NULL-title bug + `TestLive_WebSearch_RealProvider`'s external network dependency; glossary: `TestExportQueryChapterFilter` accumulates rows against a HARDCODED book/chapter id every run against the shared, never-reset dev Postgres — a genuine pre-existing test-hygiene bug, unrelated to MCP tool registration, flagged but NOT fixed this pass, out of scope). composition-service 1680/1680, jobs-service 97/97, translation-service 1042/1042, knowledge-service 3690+33/3690+33, lore-enrichment-service 957/957 (+5 pre-existing xdist-parallel-only flakes in `test_mcp_server.py`, also confirmed via `git stash` to reproduce identically unpatched).
- **Live-verified against the rebuilt real stack** through ai-gateway's actual MCP endpoint: `glossary_book_ontology_read` (the audit's own headline "single largest payload" example) now returns a 46-char `content[0].text` placeholder instead of a ~7.7KB duplicate, with `structuredContent` unchanged at 7706 chars. Honest finding, not glossed over: the 3 Python tools sampled live (`jobs_list`, `jobs_summary`, `kg_project_list`) all use a plain `-> dict` return annotation, which FastMCP's own auto-detection never treats as "structured output" — so no duplication existed for THEM to begin with (nothing to fix there today); the Python-side fix is verified correct via its own unit tests and stands ready for whenever a Python tool adopts a real Pydantic/typed output model.
- **Found, NOT fixed (out of scope, flagged for a future session, not a new Deferred row since it's unrelated to any tracked item)**: `TestExportQueryChapterFilter` (`services/glossary-service/internal/api/export_handler_test.go`) uses a hardcoded `book_id`/`chapter_id` and never cleans up its own inserted rows — every run against the shared dev Postgres adds one more row, so the assertion count grows monotonically across repeated runs (observed 3 → 4 → 5 across this session's repeated suite runs). Same root-cause CLASS as the `shared-dev-db-not-clean-fixture-e2e` lesson. Cheap fix (unique per-run UUIDs or a cleanup at test start), just genuinely unrelated to this session's actual task — flagging rather than silently fixing scope-outside-the-ask.

---

**External MCP-discoverability audit — re-verification pass A-E shipped, 2026-07-08** (branch `feat/context-budget-law`, HEAD `pending`, commit `53edfd411`, source `D:\Works\novels\mi_de\loreweave-mcp-feedback.md`). The external cold-start audit re-ran its own repros and confirmed #8 (`confirm_action`)/#2 (`knowledge` domain)/#4 (`invoke_tool` gate)/#7 (`composition_create_work` project_id) all genuinely fixed already. This pass closes the remaining actionable items via fan-out (chat-service+ai-gateway done directly; mcp-public-gateway and glossary-service each via one background agent, disjoint files).

- **A (#1/#5, highest value) — `find_tools` still under-returned on generic queries.** Root cause: the 2026-07-07 enumeration-mode fix only fires on a LITERALLY blank `intent`; a real exploratory query ("list everything you can do in this domain") is non-blank but low-signal, so it never hit that path — measured live: `book` group → 1/~15 tools, 7% recall. Fix: `group` set + a non-blank intent scoring below `CONFIDENCE_THRESHOLD` now ALSO falls back to full enumeration; no `group` + blank intent now returns the `GROUP_DIRECTORY` listing (11 domains) instead of a bare "intent required" scold. Mirrored in `chat-service/tool_discovery.py` + `ai-gateway/find-tools.ts` (kept in lockstep, same discipline as `GROUP_DIRECTORY`/`domainOf`). **Live-verified against the rebuilt real stack** (not just unit tests): `book` group now returns 21 tools (enumerated) instead of 1; a confident query ("create a book") still correctly uses ranked search, not forced enumeration (no regression). Interesting live finding: the SAME weak query against `glossary` today scores CONFIDENT (not a bug — glossary tool descriptions have grown much more verbose since the 2026-07-07 audit snapshot, incidentally token-overlapping generic words; the fix correctly defers to ranked search whenever the existing confidence scorer says confident, unchanged).
- **B (#6) — `registry`/`story` entitlement opacity.** `mcp-public-gateway`'s `filterOneFindToolsResult` (+ batch sibling) now sets `scope_note` when ITS OWN scope-filter strips a previously non-empty match set to zero — distinguishes "not entitled" from ai-gateway's own "domain genuinely has no tools" note (untouched, still correct for the genuinely-empty case).
- **C (#10, narrow scope only)** — `invoke_tool`'s `malformedResult`/`notActivatedError` + `confirm_action`'s business-error path now share one `buildErrorEnvelope` helper (new `mcp-error-envelope.ts`) instead of 3 hand-rolled shapes. Shape #1 (raw JSON-RPC transport error, intentional anti-oracle fusion) and shape #3 (Pydantic validation, cross-service, already-started-but-not-centralized in 3+ services) deliberately NOT touched — see Deferred.
- **D (#11 completeness)** — the no-op `Warning` field (shipped 2026-07-07 for `glossary_adopt_standards` only) extended to 5 more propose handlers with a clean, mechanically-checkable zero-effect condition: `glossary_book_sync_apply` (all-retired sources), `glossary_propose_status_change` (already-at-target), `glossary_propose_reassign_kind` (already-that-kind), `glossary_admin_propose_patch` (no fields given), `glossary_ontology_delete` batch (all already-gone). Deliberately skipped (documented why, not silently dropped): `glossary_propose_merge` (no zero-effect path — always soft-deletes losers), `glossary_propose_restore_revision`/`glossary_book_revert` (would need a full JSON-snapshot diff, too deep to do safely), `glossary_plan`/`glossary_propose_batch` (zero-op already hard-rejected pre-mint, a *non-empty*-but-all-skip plan needs replaying the executor's per-op logic — out of scope), `glossary_propose_new_kind/_kinds/_new_attribute`/`glossary_book_delete` (no clean signal for partial-batch conflicts).
- **E (bonus nit)** — public-gateway now rewrites any federated tool description's stale `glossary_confirm_action` mention to `confirm_action` at the existing `augmentOneListMessage` chokepoint (generic string-replace, not a hardcoded 9-name list) — glossary-service's own Go source is UNTOUCHED since that name is correct on the separate chat-service surface (`frontend_tools.py`).
- **Verify (all green):** chat-service 1242/1242, ai-gateway 175/175 + `tsc --noEmit` clean, mcp-public-gateway 244/244 + `tsc --noEmit` clean, glossary-service `internal/api` full suite green (DB-integration, real Postgres, 457s). Rebuilt all 4 touched service images (none had source volume mounts) and live-verified A end-to-end through the real running `ai-gateway` MCP endpoint.
- **Deferred:** ~~`D-MCP-PAYLOAD-DUPLICATION` (#9)~~ — **RESOLVED same day**, see the entry above this one (turned out to have a single chokepoint per language after all — a shared `RegisterTool`/`patch_convert_result` helper, not a 150+-handler sweep). `D-MCP-ERROR-SHAPE-UNIFICATION-FULL` (#10 remainder, gate #2, still open) — shape #1 (transport-level, intentionally different) and shape #3 (Pydantic, already independently started in knowledge/jobs/translation-service, absent in composition-service + 6 more Python MCP services) need cross-service surgery, not built this pass.

---

**`D-BLANK-TOOL-ARGS-LOOP` — real production bug found + fixed + live-verified against a real end-user's actual failing session, 2026-07-08** (branch `feat/context-budget-law`, HEAD `pending`, `services/chat-service/app/services/stream_service.py` + `tests/test_stream_service.py`). Supersedes the "no action needed in this repo" conclusion in the entry below it — that conclusion was about the upstream LM Studio bug (still true, still unfixable here), but a SEPARATE, genuinely-ours circuit-breaker gap was found and fixed this pass.

- **Trigger**: user asked to inspect a real production chat session (`019f4000-43ee-7201-9d45-e2fafc83696d`, a genuine other end-user, NOT the dev test account) reporting a general web-search query. Confirmed: `find_tools` called with blank `args:{}` 7 then 6 times across two turns (gemma-4-26b-a4b-qat), `glossary_web_search` called blank-args twice (validation error `missing properties: ["query"]`) — all bounded only by the pre-existing `max_total_passes=15` safety net, not by anything targeted.
- **Root cause (ours, fixable)**: `FindToolsAttemptTracker.record()` (`tool_discovery.py`) deliberately never tracks a blank-intent call ("no wording to detect a near-duplicate of") — but a blank-intent call is EXACTLY the shape the known upstream LM Studio blank-args bug produces, so the one loop-prevention mechanism built for this class of bug structurally never engages for its dominant real-world trigger.
- **Fix**: a NEW per-turn (in-memory, not session-keyed) circuit breaker in `stream_service.py` — `BLANK_TOOL_ARGS_CAP=2`, one SHARED streak counter across both observed shapes: (1) `find_tools` called with no `group` + blank `intent`, short-circuited before `find_tools_result_async` runs; (2) ANY generic backend tool whose args fail the domain service's own `"required: missing properties"` validation, short-circuited before the `mcp_execute_tool` MCP round-trip. Shared (not two independent counters) because the real session mixed both shapes in one turn. First `BLANK_TOOL_ARGS_CAP` blank/invalid attempts still behave exactly as before (a call or two probing the surface is normal); the next one returns a hard "STOP retrying, tell the user" directive instead of the same unhelpful note/error repeated. A genuine non-blank call resets the streak (no false-positive capping of legitimate multi-tool turns). Also: a `TraceAccumulator` span (`trace.add(..., is_error=True)`) at each trip, reusing the EXISTING Context-Budget-Law Inspector plumbing (not a new metrics pipeline) so a capped turn is visible in the Inspector GUI, plus a `logger.warning("D-BLANK-TOOL-ARGS-LOOP: ...")` line, greppable for ops monitoring.
- **VERIFY — genuinely live, not just unit**: rebuilt the `chat-service` Docker image (host edits don't hot-reload; the container has no source volume mount), sent the EXACT reproducing query ("Giúp tôi tìm kiếm trên internet về tình hình chiến tranh của Mỹ và Iran hiện nay") through the real gateway→chat-service→LM Studio pipeline against the SAME model (gemma-4-26b-a4b-qat, dev test account's own instance, `019ebb72-27a2-72f3-a42d-d2d0e0ded179`) 3 separate times (including once after the rebuild that added the Inspector trace span). Every run: the model called `glossary_web_search` blank-args, 3rd attempt capped exactly as designed (`chat_messages.tool_calls[2].error` = the new directive message), `docker logs` shows the `D-BLANK-TOOL-ARGS-LOOP` warning firing, and the model's final answer to the user was a coherent, honest degrade (told the user tool-calling is down, gave real alternative news sources) instead of looping for 13+ turns. chat-service full suite: 1238/1238 (4 new tests: blank-intent find_tools capping, streak-reset-on-real-call, generic-tool capping, shared-streak-across-both-shapes reproducing the exact real session's tool sequence).
- **Also resolved, incidentally, while investigating**: user's second hypothesis ("web search chưa bao giờ test, hoàn toàn vô dụng") was only partially right — the buggy session never actually reached provider-registry-service (blank args failed validation before the MCP call), and a DIFFERENT same-day session with well-formed args got REAL SearXNG results (Vietnamese news, real URLs) — so the backend itself works; the gap is that `TestLive_WebSearch_RealProvider` (a real live-smoke test that already exists in provider-registry-service) is opt-in-only, not wired into any continuous/production monitoring, so a SearXNG per-engine degradation (the pasted DuckDuckGo/Startpage CAPTCHA log) would go undetected — not fixed this pass (see Deferred). Also confirmed `lore-enrichment-service` has NO web-search implementation of its own (the user's third hypothesis) — its one `searx`/`tavily`/`ddgs` reference is a NEGATIVE test asserting it must never import one; the ONLY real web-search implementation in the repo is provider-registry-service's Tavily-compatible adapter.
- **Deferred**: `D-WEBSEARCH-PROD-MONITORING` (gate #2, large/structural) — no continuous health-check/alerting on the real web-search provider's engine success rate; would need either a scheduled job hitting `TestLive_WebSearch_RealProvider`'s same path or a metrics pipeline (chat-service/provider-registry-service currently have neither Prometheus counters nor a cron runner wired for this) — not built this pass, needs its own small design (which job-runner, what alert threshold).

---

**MCP discovery-and-reliability hardening + Intent→Skill Router (Part F: F0/F2) + confirm_action cross-service auth fix — ALL SHIPPED, 6 parallel `/review-impl` rounds fixed, live-verified, 2026-07-08** (branch `feat/context-budget-law`, HEAD `pending`, specs [`docs/specs/2026-07-07-mcp-discovery-and-reliability-hardening.md`](../specs/2026-07-07-mcp-discovery-and-reliability-hardening.md) + [`docs/specs/2026-07-07-skill-authoring-and-mcp-exposure-standard.md`](../specs/2026-07-07-skill-authoring-and-mcp-exposure-standard.md) Part F, plans [`docs/plans/2026-07-07-mcp-discovery-and-reliability-hardening.md`](../plans/2026-07-07-mcp-discovery-and-reliability-hardening.md) + [`docs/plans/2026-07-07-intent-skill-router.md`](../plans/2026-07-07-intent-skill-router.md)). Origin: 4 real production chat sessions failed on an identical general web-search query (unbounded find_tools loop — one hit 40 iterations/53.8s, duplicate tool-calls, hallucinated non-web answers) + an external cold-start MCP discoverability audit (`docs/bugs/2026-07-07-mcp-discoverability-external-audit.md`). Built via fan-out (11 disjoint slices across chat-service/ai-gateway/mcp-public-gateway/glossary/book/provider-registry/composition), then 6 parallel `/review-impl` adversarial reviews found 5 HIGH + ~7 MED real bugs, all fixed and re-verified — not rubber-stamped.

- **Layer A (`find_tools` hardening)**: true per-domain enumeration (mirrors `GROUP_DIRECTORY` one level down — a `group`+blank-`intent` call now returns every non-legacy tool unranked instead of nothing), retry-cap (`FindToolsAttemptTracker`, session-keyed + TTL + token-set near-duplicate detection, TS+Python mirrors), embeddings-backed `search_catalog` blended with token-overlap via `max()` (chat-service's first embedding-provider call site, `app/client/embedding_client.py`), tool-call-duplication fix (`_drop_duplicate_empty_tool_calls`, tracks last well-formed call per tool name).
- **Part F (Intent→Skill Router)**: F0 (general web-research taught directly in `universal_skill.py`, closing the traced orphaned-capability gap — `glossary_web_search` was only ever taught by `glossary_skill`, invisible on the `chat` surface) + F2 (`skill_router.py`, embedding-similarity router, additive-only to `resolve_skills_to_inject_async`, fallback-safe to the static/structural result on any embed failure).
- **`confirm_action` cross-service auth bug (found DURING `/review-impl`, not part of the original plan)**: `auth-service`'s `replayConfirm` (self-confirm + human-approval replay) sends a query-param token + `X-Internal-Token`/`X-User-Id` envelope with **no Bearer JWT** — but glossary-service/book-service/provider-registry-service's confirm routes required Bearer-only + JSON-body token, so **every** confirm-replay 401'd unconditionally for these 3 domains (composition/translation/knowledge-service already had the correct dual-auth pattern, `D-PMCP-WORKER-CARRIER`). Fixed via a new shared `loreweave_mcp.ResolveEnvelopeOrBearerCaller` helper (SDK-First consolidation, replacing 3 independent copies).
- **`/review-impl` (6 parallel shards) — 5 HIGH + ~7 MED, all fixed, none deferred**: cross-model tool-vector cache poisoning (cache key now includes `model_source`/`model_ref`), embeddings calling the turn's CHAT model instead of a resolved embedding-capable model (now resolves via `get_default_model("embedding", user_id)`, skips the network call entirely when unset), enumeration bypassing all in-turn token budgeting (reopened the 2026-07-06 context-explosion class — now trimmed via `budget_names_by_tokens` before entering `active_tool_names`), `FindToolsAttemptTracker`'s top-level session map never shrinking (unbounded leak, fixed in both TS and Python), `registry` domain totally missing from `mcp-public-gateway`'s `TOOL_POLICY` (same bug class as `story`, found unaudited), `composition_create_work`'s auto-create path never backfilling a pending Work after a knowledge-service outage recovers (orphaned row + duplicate project), 2 more untracked duplicate `_cosine` implementations (1 migrated, 1 correctly left alone with a documented reason).
- **VERIFY — live, not just unit**: re-ran the EXACT original 4-session repro live against the rebuilt stack — Qwen2.5 7B makes one clean `glossary_web_search` call with real cited results; gemma-4-26b-a4b-qat now bounded to 11-16 iterations with honest disclosure (down from 40 iterations/53.8s + a hallucinated non-web answer). External audit's #2/#3 (`knowledge` domain unreachable via `find_tools`→`invoke_tool`) confirmed live-fixed, closing `D-INVOKE-TOOL-LIVE-SMOKE`. Full Part E eval re-run (37 scenarios, gemma-4-26b-a4b-qat, ALL fixes live) — **zero hallucinated tool names, 4th consecutive round** — see [`docs/eval/skill-authoring/2026-07-08-gemma-post-allfixes-rerun.md`](../eval/skill-authoring/2026-07-08-gemma-post-allfixes-rerun.md).
- **New finding, NOT fixed this pass (tracked below)**: gemma-4-26b-a4b-qat sends **blank arguments to virtually every tool call** (100% of 344 calls across all 37 sessions in the round-5 re-run) — broader than the previously-known blank-`find_tools`-intent case, and bypasses both the retry-cap and the dedup fix (neither's trigger condition is ever met when args are blank from the very first call). What actually bounds every scenario today is a pre-existing, untouched `max_total_passes=15` safety net, not this session's targeted fixes. User's hypothesis (2026-07-08, next session should investigate): this may be a wrong tool-calling REQUEST FORMAT on our side for LM Studio, not purely a gemma model defect — LM Studio's own console reportedly shows a warning. See Deferred.
- Test suites: chat-service, ai-gateway, mcp-public-gateway, glossary-service, book-service, provider-registry-service, composition-service, knowledge-service, lore-enrichment-service, sdks/python — all green (2 pre-existing, unrelated failures identified and ruled out: `TestMCP_GetChapter_IncludeBody_DB` NULL-title Scan bug from commit `cbb3f1d49`, and a live SearXNG-dependent web-search test transiently 502'ing).
- **2 follow-on fixes from the LM Studio investigation below** (both real, both kept, neither is THE fix for the blank-args cascade — see Deferred): (1) `stream_service.py` no longer persists a tool call's raw `arguments` string verbatim into `working` (the conversation-history list re-sent to the provider every pass) — it can be `""` when a model streams nothing, which violates the OpenAI tool-calling wire contract (`function.arguments` must always be valid JSON) and made LM Studio's own history-reconstruction throw (`JSON.parse('')`). Always re-serializes through `_parse_tool_args` now (min `"{}"`). Live A/B tested against `qwen/qwen3.6-35b-a3b` — confirmed this does NOT change the observed cascade (byte-identical before/after), but is kept as a genuine, independently-worthwhile spec-compliance fix. (2) `loreweave_llm.Client._dispatch_event`'s `error`-event branch no longer crashes with an opaque `pydantic.ValidationError` when a producer omits the required `message` field — degrades to a best-effort `ErrorEvent` instead, so a future upstream failure is diagnosable from application logs, not just LM Studio's own server log (which is how this session's crash cause was actually found).

**Deferred:**
- ~~`D-LMSTUDIO-TOOLCALL-FORMAT`~~ — **ROOT-CAUSED 2026-07-08 (revised), NOT a LoreWeave bug.** User correctly suspected the pattern was too uniform to be pure model noise, and correctly pushed back when a first-pass conclusion ("gemma-template-specific") turned out to be premature — a live test proved `qwen/qwen3.6-35b-a3b` (a different model, different author, different chat template) shows the IDENTICAL 100%-blank-args symptom, ruling that narrower theory out. Root cause, confirmed via LM Studio's own server logs lining up to the second across 4 separate live runs: LM Studio's tool-call PARSER for both `gemma-4-26b-a4b-qat` AND `qwen/qwen3.6-35b-a3b` has known, model-exact-matched upstream bugs — gemma: `chat_template.jinja` missing a `format_type_argument` macro (lmstudio-bug-tracker [#2012](https://github.com/lmstudio-ai/lmstudio-bug-tracker/issues/2012)/[#1927](https://github.com/lmstudio-ai/lmstudio-bug-tracker/issues/1927), exact model match; mlx-swift-lm [#259](https://github.com/ml-explore/mlx-swift-lm/issues/259): `GemmaFunctionParser uses outdated tags`); qwen: the parser scans INSIDE `<think>` reasoning blocks and misfires on tool-call-shaped text inside them, crashing with `Failed to parse tool call: Expected "<parameter=", but got "<parameter>"` (lmstudio-bug-tracker [#1999](https://github.com/lmstudio-ai/lmstudio-bug-tracker/issues/1999), literally titled with our exact model string; [#1592](https://github.com/lmstudio-ai/lmstudio-bug-tracker/issues/1592)/[#827](https://github.com/lmstudio-ai/lmstudio-bug-tracker/issues/827) describe the same `<think>`-block misfire class) — confirmed reproducing even though our own request explicitly sends `enable_thinking: false` (verified in code), so either Qwen3.6's template doesn't fully honor that flag (a known family quirk) or the tag-format bug is independent of thinking mode entirely. Verified our own `lmStudioAdapter` (`provider-registry-service/internal/provider/adapters.go:1546-1596`) sends a standard OpenAI-compat `tools`/`tool_choice` payload in both cases — no request-format bug on our side; the 2 real bugs this investigation DID find on our side (arguments-JSON-coercion, ErrorEvent-masking, both above) are independently-worthwhile fixes, confirmed via live A/B test to NOT be the cascade's actual driver. **Fix is local/infra, not code**: for gemma, re-download from `lmstudio-community` HF namespace or patch the Jinja template per [this HF discussion](https://huggingface.co/google/gemma-4-26B-A4B-it/discussions/20); for qwen, the community-reported workaround is disabling "thinking" at the template level (`{%- set enable_thinking = false %}`, distinct from our request-level flag) or watching lmstudio-bug-tracker #1999 for an upstream parser fix. No action needed in this repo. Until resolved locally, treat local LM Studio models as diagnostic-for-platform-loop-safety only, not reliable for tool-calling-dependent content evals (Qwen2.5 7B Instruct remains the more diagnostic model for skill-content signal, per round 3/4).
- `D-CHATMESSAGES-PERSISTENCE-GAP` (gate #4) — 4 of 37 sessions in the gemma round-5 re-run had NO persisted `assistant`+`tool_calls` row in `chat_messages` at all (only the `user` turn), found incidentally while pulling eval evidence via direct Postgres query — not chased down this pass.
- Error-envelope normalization (external audit #10) — split into its own follow-on plan per this effort's OQ3, not built this pass.
- Embeddings-based routing/search not yet live-confirmed working for gemma specifically (the code path structurally never fires — gemma never sends a non-blank intent); confirmed working for Qwen (round 4's Task 4).

---

**Skill-authoring + MCP exposure standard — ALL PARTS (A–E) SHIPPED + Part E root-cause/re-run, 2026-07-07/08** (branch `feat/context-budget-law`, HEAD `pending`, spec [`docs/specs/2026-07-07-skill-authoring-and-mcp-exposure-standard.md`](../specs/2026-07-07-skill-authoring-and-mcp-exposure-standard.md)). Direct follow-on to the MCP tool-calling fix below — user's framing: tool count will keep growing, and skills need to be genuine "workflow definitions + tool-use guides," not bare "here's MCP, go find_tools yourself." This entry supersedes the prior Part A+B entry — same effort, closed out via fan-out (Part B Phase 2, then Parts C+D+E, then a 2026-07-08 investigation that found + fixed 2 real bugs behind Part E's initial noisy results).

- **Part A — the skill-authoring contract.** `SkillDef` gained `hot_domains`; a permanent lint (`TestSkillClaimsLint`) scans every skill's prose for real catalog tool names and fails if the tool's domain isn't declared hot. Found 3 pre-existing bugs on first build (knowledge_skill's undeclared claim, 7 stale glossary tool refs, the `kg_*`/`memory_*`→`"knowledge"` alias gap).
- **Part B Phase 1+2 — all 5 domain skills.** `composition_skill.py` (~56 tools), `translation_skill.py` (12), `book_skill.py` (21), `settings_skill.py` (12), `jobs_skill.py` (5). All curated-pin-only except composition (auto-injects on studio). `/review-impl`-equivalent fact-check across all 5: **8 Phase-1 findings + 3 Phase-2 findings, all fixed** (full detail in the spec's build notes) — headline: `jobs`/`settings` came back clean; `book_skill` had a real WRONG claim (said `book_get_chapter` exposes `draft_version` for `base_version` — it doesn't, no MCP read tool does; fixed with the one safe deterministic case + an explicit "open the editor" fallback for everything else).
- **Part C — `mcp-public-gateway` scope-size-adaptive exposure, threshold=20.** A key resolving to <20 tools skips the lazy find_tools→invoke_tool collapse and gets the flat scope-filtered list directly (like `ai-gateway`'s internal `/mcp` already does); ≥20 unchanged. Real data: 5 active keys, bimodal (3→5 tools, 2→161 tools — the second cluster almost certainly the external-agent keys from the original bug report). `scopeToolCount()` + `DIRECT_LIST_TOOL_THRESHOLD` in `tool-policy.ts`; wired as `directList` branch in `public-mcp.controller.ts`. mcp-public-gateway 230/230, `tsc --noEmit` clean.
- **Part D — hot-domain generic derivation, closes `D-SKILL-HOTDOMAIN-RUNTIME-WIRING`.** `surface_hot_domains()` now derives from `resolve_skills_to_inject`'s default codes' own `hot_domains` (+ `story`, the one surface-level exception) instead of 3 hand-authored constants (`_BOOK_SCOPED_HOT_DOMAINS`/`_STUDIO_HOT_DOMAINS`/`PLAN_HOT_DOMAINS`, now deleted). **Sign-off'd behavior change**: `knowledge_skill`'s already-honest `hot_domains={"knowledge"}` declaration is now HONORED everywhere it auto-injects, including universal/chat (previously hot-seeded nothing) — a real, deliberate, token-budget-verified widening, not silent. Full regression: 5 tests updated (all the same expected flip, documented inline), every other domain byte-for-byte unchanged. chat-service 1152/1152.
- **Part E — live judge-gate eval, first pass + root-cause follow-up (2026-07-08).** New harness `scripts/eval/run_skill_gate.py` (sibling of `run_quality_gate.py`, adds per-turn `book_context`/`editor_context`/`studio_context`/`enabled_skills` so a scenario can force the right surface+pin). 37 scenarios across 5 files (`scripts/eval/skill_scenarios/*.json`). First pass (`gemma-4-26b-a4b-qat`) found a dominant `find_tools`-loop-then-give-up pattern; **root-caused as TWO real, fixed bugs, not model noise** — see [`docs/eval/skill-authoring/2026-07-08-loop-flake-rootcause-and-rerun.md`](../eval/skill-authoring/2026-07-08-loop-flake-rootcause-and-rerun.md):
  1. `find_tools_result()` silently degraded a missing/blank `intent` into a genuine zero-token search instead of a directive error (`tool_discovery.py`).
  2. **The real dominant cause**: `is_curated()` derived curated-mode ONLY from `enabled_tools` — the REAL frontend's skill-pin UI (`useContextRack.ts`) pins via `enabled_skills` alone, `enabled_tools` always `[]`, so a pinned skill's TOOLS never got hot-seeded even though its PROMPT confidently told the model to call them directly. Live-observed causing false "this tool doesn't exist" claims across all 5 skill files. **Part B's own tests never caught this** — every `TestCuratedSkillHotDomainUnion` test co-pinned a dummy `enabled_tools` entry alongside the skill under test, accidentally masking the exact path production uses. Fixed: `is_curated()` now OR's `enabled_skills`; an identical dead short-circuit in `effective_enabled_tools()` removed too (`tool_surface.py`). 3 new regression tests, including the exact real-world "skill pinned alone" case.
  Clean re-run (`Qwen2.5 7B Instruct`, both fixes live): **zero hallucinated tool names** (even stronger than pass 1), dominant false-tool-denial gone for 3/5 skills + reduced for the other 2 (residual: composition's ~56-tool domain genuinely exceeds the hot-seed budget by design — `find_tools` search itself verified correct, gap is model discipline). Two NEW patterns surfaced that are model-capability, not skill/platform bugs — "real tool call, 0 chars to user" (matches this repo's pre-existing `reasoning-model-burns-max-tokens-before-real-answer` lesson) and non-convergent retry loops — neither tracked as a new defer row.
- **VERIFY (final, whole spec closure):** chat-service 1158/1158, mcp-public-gateway 230/230 (`tsc --noEmit` clean), live judge-gate run completed twice (first pass + post-fix re-run, 37 scenarios × 5 skills each). ai-gateway untouched throughout.
- **Deferred:**
  - `D-SKILL-LINT-LIVE-CATALOG` (gate #4→buildable, spec §8b.2) — the lint can't catch a stale/typo'd tool-name-shaped token matching NO real catalog entry. Buildable via a snapshot-harness mirroring `contracts/mcp-response-shapes/*.json`'s pattern — not yet built.
  - **Cleared this pass**: `D-SKILL-EVAL-DISCOVERY-LOOP-FLAKE` and `D-SKILL-EVAL-RERUN-AFTER-LOOP-FIX` — both RESOLVED, see Part E note above.
  - **Note (not a defer row, out of scope)**: `motif_not_connected_to_planforge` (composition) still FAILed on the clean re-run — a genuine conceptual miss (the skill's existing wording is fairly explicit) surviving a properly-functioning platform, but n=1 from a 7B model isn't enough to justify rewriting the skill off one data point; left as-is.
  - **In-flight, another concurrent session, NOT this session's work**: `docs/specs/2026-07-07-mcp-discovery-and-reliability-hardening.md` + a "Part F: Intent→Skill Router" addendum to the skill-authoring spec are mid-CLARIFY in a parallel session sharing this checkout — cross-references this session's Part E report as corroborating evidence. Left entirely untouched beyond two small additive clarifying notes (marking the loop-flake root-cause as now understood) — do not commit that spec file's Part F content as this session's work.
  - **Recently cleared this pass:** Part B Phase 2 (book/settings/jobs), Part C, Part D, Part E first pass — the ENTIRE spec's originally-scoped work is now shipped. Only the two loop-flake-investigation items above remain open.

---

**MCP tool-calling: Plan/Ask-mode seeding gaps (internal) + `invoke_tool` facade (external) — SHIPPED + `/review-impl` clean, 2026-07-07** (branch `feat/context-budget-law`, HEAD `pending`). Triggered by an external bug report (an outside agent testing the public MCP edge found it could never call any tool beyond `find_tools`) plus the user separately noticing the internal Studio chat also mis-called Plan-mode tools. Root causes turned out to be TWO unrelated bugs in the same tool-discovery subsystem:

- **Milestone 1 (chat-service, internal, higher user impact):** `plan_forge_skill.py`'s system prompt told the model to call `plan_propose_spec` etc. immediately, but `tool_discovery.py`'s hot-domain sets never included a `"plan"` domain (PlanForge tools federate under their own `plan_` prefix, not `composition_`) — so Plan-mode turn 1 never advertised the tools the skill told the model to call. Fixed: `surface_hot_domains()`/`discovery_seed_for_surface()` now take `permission_mode` and hot-seed `plan_*` when `permission_mode=="plan"`, on BOTH the auto and curated-pins paths (the curated-mode fix needed a `/review-impl`-caught correction — see below). Also fixed: `GROUP_DIRECTORY` (`tool_discovery.py` + its TS mirror `find-tools.ts`) had two entries overclaiming tools outside their own name-prefix (`"story"` claimed `book_get_chapter`, `"composition"` claimed `plan_*`) — `find_tools(group=...)` could never actually surface them since the filter is prefix-based; corrected the text + added the missing `"plan"` group. Also added `ASK_MODE_NUDGE` — Ask mode previously had ZERO system-prompt explanation (only Plan mode had one), so a model only learned "read-only" reactively from a rejected tool call.
- **Milestone 2 (mcp-public-gateway + ai-gateway, external, architectural):** the public MCP edge's lazy-tool-loading design (`find_tools` "activates" a tool server-side) assumed a client would re-fetch `tools/list` after activation — but a standard MCP client (Claude Code confirmed) caches `tools/list` ONCE at connect and never re-polls, so an "activated" tool could never actually be CALLED (the client refuses to send a name it never saw listed). The originally-planned fix (`notifications/tools/list_changed`, see `docs/plans/2026-06-29-public-mcp-lazy-tool-loading.md`) was never even implemented and wouldn't have worked anyway. Fixed with a new always-present `invoke_tool(name, arguments)` facade (`services/mcp-public-gateway/src/scope/invoke-tool.ts`, NEW file) that the client CAN call; the edge unwraps it into a normal `tools/call` for the real target at the very top of the request pipeline (`public-mcp.controller.ts`) so every existing gate (scope, rate-limit, idempotency, confirm-divert, audit) applies unmodified to the genuine tool name. Also added an MCP `instructions` field to `ai-gateway`'s `proxy-server.factory.ts` (previously ZERO onboarding text for a fresh client).
- **`/review-impl` (1 HIGH + 2 MED fixed, all re-verified):** (1) HIGH — the curated-mode Plan fix double-budgeted the hot tool-set (the shared glossary/story/plan union PLUS an unconditional second plan-only union), risking ~2× `HOT_SEED_TOKEN_BUDGET` per turn — the exact context-explosion pattern this budget system exists to prevent; fixed by only reaching for the separate carve-out when the shared union's gate (`glossary_in_skills`) actually skipped (i.e., never double-count). (2) MED — a malformed `invoke_tool` call short-circuited BEFORE rate-limiting (unlike every sibling denial path) — an authenticated key could flood malformed calls untouched; fixed by deferring the response until after the rate-limit check. (3) MED — the invoke_tool "not yet activated" denial was audited as `denied_scope`, conflating a normal first-call-flow miss with a genuine scope violation in the owner-facing audit trail; changed to `tool_error` (a valid existing enum value, matches the response's MCP-`isError` shape rather than a JSON-RPC anti-oracle deny). Also fixed a stale/misleading code comment and added a `docs/standards/mcp-tool-io.md` Known-gaps entry documenting `invoke_tool`'s generic-`arguments` schema as a deliberate, protocol-necessitated IN-3/IN-4 deviation (not a gap to close).
- **VERIFY (final, all green):** chat-service 1127/1127, mcp-public-gateway 223/223 (+`tsc --noEmit` clean), ai-gateway 139/139 (+`tsc --noEmit` clean).
- **Deferred:**
  - `D-INVOKE-TOOL-LIVE-SMOKE` (gate #4, needs infra) — no real external MCP client re-test against a running stack yet; this is literally how the original bug was found, so the unit/integration-only suite has a known blind spot. Re-test with a real external agent (or Claude Code pointed at a live `mcp-public-gateway`) once the stack is up.
  - `D-I18N-MODE-NUDGE-RELABEL` (gate #3, naturally-next-phase) — `frontend/src/i18n/locales/en/chat.json`'s `plan_nudge` category label was relabeled "Plan nudge"→"Mode nudge" (it now also carries the Ask-mode nudge) but the other 18 locale files are UNCHANGED (still say the old Plan-specific translation) — running `scripts/i18n_translate.py --ns chat --force` mid-session retranslated the ENTIRE `vi/chat.json` namespace (172 lines) instead of just the one key, which was reverted rather than land an unreviewed bulk-retranslation diff. Needs a proper run (ideally a single-key-scoped mode, or a reviewed full retranslation) in a dedicated i18n pass.
  - `D-PLAN-CURATED-SKILL-FLAG-NAMING` (gate #1, out of scope, found not fixed) — `tool_surface.py`'s `effective_enabled_tools` hot-domain auto-union gate is literally named/keyed on `"glossary"` (`glossary_in_skills`) even though it now also governs whether `plan_*`/composition domains ride along; works correctly today (Milestone 1 handles the plan-mode case with an explicit carve-out) but the naming is misleading and worth generalizing if a THIRD mode-specific skill needs the same treatment later.
- **NEXT:** the user wants to follow up with a broader discussion — web-research how the MCP ecosystem (Anthropic's own guidance, other production MCP servers) designs lazy/progressive tool-disclosure, compare against what just got fixed here, and reconsider whether `docs/standards/mcp-tool-io.md` / the skill-injection design needs a deeper rewrite (the user's hypothesis: the original Context Budget Law tool-discovery cutover was too aggressive and degraded quality, of which this session's bugs are a symptom, not the root fix).

---

**Hardcoded context-window audit — Tier 0/1/2 shipped + `/review-impl` + Tier 3 closed,
2026-07-08.** Full detail in
[`docs/plans/2026-07-07-hardcoded-context-window-constants-audit.md`](../plans/2026-07-07-hardcoded-context-window-constants-audit.md)'s
`/review-impl` findings section + Tier 3 correction. Summary of this pass:

- **HIGH fixed:** a negative/zero `context_length` was treated as "resolved" through the
  whole chain, producing a negative `max_tokens` sent to a provider. Root cause:
  `patchUserModel` (provider-registry-service) had zero validation (unlike `createUserModel`),
  and 3 resolver call sites used a falsy-only check (`if cw else None` / `cw or FALLBACK`)
  that a negative number sails through (negative ints are truthy in Python/Go isn't the
  issue — the check itself just didn't test the sign). Fixed at the DB-write boundary
  (both Go handlers now reject `context_length <= 0`) + defense-in-depth at every downstream
  falsy check (`_context_length.py`, composition-service's `llm_client.py`,
  translation-service's `extraction_model.py`, `entity_recovery.py`/`pass2_filter.py`,
  `knowledge_client.py`) + the FE `EditModelModal.tsx` input gained `min={1}`.
- **MED fixed:** subagent's nested `_stream_with_tools` call (chat-service
  `stream_service.py`) dropped `context_length` — forwarded now, but only when the subagent
  runs the SAME model as the caller (a different `sub_model_ref` correctly keeps the flat
  default rather than misapplying the parent's window).
- **MED fixed:** composition-service's null-project `pack()` branch never scaled its budget
  — `_pack_null_project` read the flat `settings.pack_token_budget` directly instead of the
  caller's already-scaled `budget_tokens`. Fixed.
- **LOW, all closed:** corrected an overclaiming test comment in
  `context_window_test.go` (no docker-compose integration suite actually exists for this
  service yet); strengthened a weak assertion in `test_context_length_scales_the_distill_cap`;
  added the missing SDK-level scaling test for `summarize_level`; added the missing
  effect-proving test for `build_multi_project_mode`'s shared-budget scaling; resolved the
  plan's own flagged-open question — ai-gateway's `grounding.controller.ts` is a pure
  JSON-body pass-through (not the MCP federation path), so `context_length` DOES survive
  the chat→knowledge hop unmodified.
- **Tier 3 verified + closed (not a live bug):** the plan's original claim that
  `ModelCaps`/`planner.plan()` have "zero production instantiations" was WRONG — verified
  they ARE used by translation-service's `estimate_extraction_cost()` (real callers:
  `mcp/server.py`, `routers/extraction.py`). Corrected the doc. Still not an active bug: the
  reachable fallback path is a cost-**estimate** (pre-job quote), never drives a real LLM
  call's chunk sizing (that's `chapter_worker.py`, a separate already-fixed mechanism) — so
  it matches the doc's own "Ruled out" cost-estimate-heuristic category, not a Tier-1/2 bug.
  `_build_budget_for_model()` specifically still has zero callers, confirmed.
- **New, OUT-OF-SCOPE finding flagged for the user (not fixed — needs a product decision,
  not a mechanical patch):** while verifying Tier 3, found `estimate_extraction_cost()`
  (`extraction_prompt.py:520-539`) appears to double-apply the reasoning-effort output
  multiplier on the planner path — its own local table scales `output_per_call` once, then
  `planner.py`'s separate multiplier table scales the ALREADY-scaled value again (for
  `effort="high"`: 2000 × 4.0 × 2.5 = 20,000, not the intended single scaling). The existing
  test only asserts monotonic growth, not an exact value, so it doesn't catch this. Root
  cause is clear but which of the two multiplier tables should govern is a product call, not
  something to guess-fix — flagged in the plan doc, not touched.
- All 7 touched services re-verified green after the `/review-impl` fixes: provider-registry
  Go (`go build` + `go test`, all pass), sdks/python (785 passed, same 6 pre-existing
  unrelated failures), chat-service (1118), composition-service (1674, up from 1670),
  knowledge-service (3796, up from 3795), translation-service (1041), worker-ai (308, same 1
  pre-existing unrelated failure). Frontend `tsc --noEmit` clean.

---

**Hardcoded context-window audit — Tier 0 + Tier 1 + Tier 2 ALL SHIPPED, 2026-07-08.** Full
detail in
[`docs/plans/2026-07-07-hardcoded-context-window-constants-audit.md`](../plans/2026-07-07-hardcoded-context-window-constants-audit.md)'s
completion logs. Summary: fixed `provider-registry-service`'s `getModelContextWindow`
fabricating `8192` on every failure path (now returns `resolved:false`, never guesses) +
merged preconfig `context_length` into live OpenAI discovery; deduped `chapter_worker.py`'s
fallback with the shared helper. Unlocked model-context-aware chunk sizing for all 4 KG
extractors (entity/relation/event/fact) AND the sync `extract_pass2` path — the bug wasn't
scoped to the decoupled path alone as first thought. Added a new shared kernel helper
`loreweave_context.budget.scale_by_window`, wired through chat-service (tool-surface
budgets, steering cap, D7 tool-result cap, story_state cap, subagent result cap),
composition-service (pack/compress/stitch/coverage/motif-chunk budgets — needed a new
`LLMClient.resolve_context_length`), translation-service's glossary-translate worker (a
*clamp-down* for small windows, not scale-up), and knowledge-service's Mode-3 budget (the
one genuine **cross-service contract change**: chat-service now sends `context_length` as
a new additive field on `POST /context/build`, matching this endpoint's own established
optional-field pattern). `sdks/python`'s `entity_recovery.py`/`pass2_filter.py` needed the
same clamp-down shape as translation's fix (output scales by item count, not window — the
bug was no ceiling at all, not a wrong ceiling), threaded through both the sync `pass2.py`
path and the decoupled `worker-ai` path. Reviewed and explicitly excluded 2 items that
aren't the same bug class (`SELECTION_MAX_CHARS` is a Pydantic request-validation
constraint + deliberate UX backstop; `grounding.py`'s preview endpoint has no model
reference to scale against). All touched services' full suites green (provider-registry Go,
sdks/python, worker-ai, translation-service, chat-service, composition-service,
knowledge-service — new tests added in every one, including the two-services-apart
context_length threading). **Only Tier 3 left, genuinely low-priority:** latent dead-code
defaults in `loreweave_extraction.context_budget` (`DEFAULT_MODEL_CONTEXT`/
`DEFAULT_MAX_OUTPUT_TOKENS`) — zero production callers today, fix only if/when
`loreweave_extraction.planner`/`ModelCaps` gets wired up. **One thing NOT independently
verified:** whether ai-gateway's MCP federation hop preserves the new `context_length`
field on the chat→knowledge `/context/build` call (there's a prior precedent of a
federation hop silently dropping a field — `[[gateway-drops-xprojectid-envelope]]`) — worth
checking if Mode-3 budget scaling doesn't seem to take effect live.

The web/deep search scoping issue flagged earlier in this conversation (session
`chat/019f38aa-c817-78b6-a686-dc9fe13cff6f`) — user confirmed a separate agent/session
already fixed it (2026-07-08). Not independently re-verified in THIS session; if it
resurfaces, re-root-cause rather than assuming stale context.

---

**Context budget hardcoded-cap bug fixed + repo-wide audit, 2026-07-07.** User hit
`sdks/python/loreweave_context/budget.py`'s absolute cap (`_TARGET_MAX_CAP=200_000`) clamping
the Context Inspector's soft target for a 1M-context model to the same number a 200K model
got. Fixed: both `floor`/`surface_max` are now pure fractions of the model's resolved
`context_length` (`0.1×`/`0.75×window`), no absolute ceiling at all — tests updated + a new
1M-window regression test added (both `sdks/python/tests/test_context_plan.py` and
`services/chat-service/tests/test_token_budget.py`). User then asked for a full audit of the
same bug class elsewhere — see
[`docs/plans/2026-07-07-hardcoded-context-window-constants-audit.md`](../plans/2026-07-07-hardcoded-context-window-constants-audit.md):
**12 more hits found** across chat-service, composition-service, translation-service,
knowledge-service, and `sdks/python` extraction — ranked Tier 0 (provider-registry-service's
`getModelContextWindow` silently fabricates an `8192` fallback on 5 failure paths, poisoning
translation-service's chunk sizing — fix this FIRST) → Tier 1 (cheap, `context_length`
already resolvable at the call site — includes a one-line-fix root cause in
`services/worker-ai/app/decoupled_extract.py` that unlocks 4 extractors at once) → Tier 2
(needs new parameter plumbing) → Tier 3 (latent/unreachable, fix before ever wired up). Audit
only — **no fixes applied yet beyond the original `budget.py` bug**; this is next-session
work. Also open from the same conversation: web/deep search tool is entity/glossary-scoped
and errors when asked to search general topics outside a book (session
`chat/019f38aa-c817-78b6-a686-dc9fe13cff6f` — exception, agent output not tracked); nav-scroll
CSS fix (`Sidebar.tsx:129` missing `min-h-0 overflow-y-auto`); Context Inspector page layout
(`ContextInspectorPage.tsx:14` hardcoded `h-[calc(100vh-4rem)]` wrong for its `DashboardLayout`
ancestor); notification mark-read race (`NotificationBell.tsx:58-66` fires PATCH without
awaiting, a concurrent GET clobbers the optimistic state); Inspector missing prompt-caching
surfacing (data already flows to the API, FE `ContextTraceFrame` type just never declares
it); glossary `/genres` 404 (`SettingsTab.tsx` still calls a route retired in the G4e
migration, needs to move to `/ontology/genres`) — **none of these 6 have been fixed yet**,
all root-caused only.

---

**Studio v2 Quality tab — hub + 4 sibling panels shipped, /review-impl'd, 2026-07-06.**
Plan [`docs/plans/2026-07-06-studio-quality-tab.md`](../plans/2026-07-06-studio-quality-tab.md). Filled the
`ActivityView='quality'` stub (previously just "Coming soon" text) with real capabilities, full-scope per PO
decision (including new canon-issues backend, not deferred). Backend (commit `128e82318`): NEW read-only
endpoints — composition-service `GET /works/{id}/canon-issues` (itemized version of `chapter_scene_gate`'s
canon join, book-wide instead of per-chapter) and knowledge-service `GET /extraction/projects/{id}/canon-flags`
(closes the previously-deferred `D-KG-CANON-FLAG-REVIEW-UI`) — both pure new queries over existing data, no
migrations. Frontend (commit `75360bbd7`): DOCK-8 hub (`quality`) + 4 sibling panels
(`quality-promises`/`quality-critic`/`quality-coverage` reuse composition's `ThreadsPanel`/`QualityReportSection`/
`BookPromiseCoverageSection` AS-IS via DOCK-2; `quality-canon` is new, merging both backend sources with
jump-to-chapter via the existing `focusManuscriptUnit` host action). Added 5 panel_ids to
`ui_open_studio_panel` + regenerated `contracts/frontend-tools.contract.json`. **`/review-impl` same session**
found + fixed 2: a canon-source fetch error silently rendered as "no issues" (false-negative, now a visible
error banner) and the critic panel's 500-chapter picker cap was silent (now shows "showing first N of M").
9+7 new backend tests, 31 new frontend tests, full backend+frontend suites green (composition 1839/1839
sequential — the earlier `-n auto` xdist run's 156 errors were confirmed pre-existing environmental flakiness
via A/B, not a regression), FE 2403/2403 no regressions. Live-verified against the real dev stack with a real
JWT: `canon-flags` surfaced an actual pre-existing "Alice marked gone but referenced active" contradiction; a
live browser session (Playwright, logged in as the test account) confirmed the Quality hub opens from the
sidebar and renders real data (correct "no co-writer session" hint for a book with no composition Work).
**Deferred (documented, not silently dropped):** `canon-issues` has no pagination — accepted as-is (an advisory
list of *currently unresolved* contradictions should stay small in practice; revisit only if a real book proves
otherwise).

---

**PDF book import (text + image/chart, page-chunking) — shipped, live-verified end-to-end, 2026-07-06.**
Spec [`docs/specs/2026-07-06-pdf-book-import.md`](../specs/2026-07-06-pdf-book-import.md). Motivated by an audit
finding PDF was rejected outright at book import and the platform was architecturally novel-only (see memory
`pdf-ingestion-novel-only-gap`); user wants lore/technical-reference books importable too. CLARIFY locked L1-L9
(knowledge-service owns extraction; images captioned via a NEW vision LLM op, not asset-only; chunk boundary =
chapter boundary always, no heading-regex dependency; async per-chunk worker calls — not one whole-book call, which
an adversarial spec review found would blow the worker's 5-min HTTP timeout on any book needing >~5 captioned
images; idempotency via `chapters.import_job_id` + `ON CONFLICT`). Shipped across 6 services, all phases
live-verified, not just unit-tested:
1. **provider-registry-service** — new first-class `"vision"` job operation (`CaptionImage` adapter method,
   OpenAI multimodal `/v1/chat/completions` implementation, stubs for anthropic/ollama/lm_studio, cost estimator
   that deliberately does NOT walk the base64 image bytes as text — a flat per-image token ceiling instead, to
   avoid wildly over-pricing a call). Live-proven with a real gpt-4o call captioning a generated test chart before
   anything else was built on top of it.
2. **`sdks/python/loreweave_parse/pdf_walker.py`** (new SDK module) — PyMuPDF per-page text + embedded-image
   extraction, OCR fallback ported from lore-enrichment-service's `extract.py` (incl. `tesseract_lang_for`), image
   dedup-by-hash + min-dimension filter + downscale-for-vision. 21 tests against real fitz-generated PDF fixtures.
3. **knowledge-service** — `/internal/parse/pdf-chunk` (one chunk in → one Chapter + its images out, per-image
   caption failure degrades to `caption=None` and never fails the chunk) + `/internal/parse/pdf-peek` (page count,
   rejects encrypted/corrupted PDFs early). 13 tests incl. a mocked-LLM captioning path + dedup-within-chunk.
4. **book-service** — `.pdf` added to `allowedImportFormats`, routed through the existing async `import_jobs`
   pipeline (not sync like `.txt`); new `POST .../import/pdf-peek`; migrations: `chapter_page_images` table,
   `import_jobs.{pages_per_chunk,caption_images,vision_model_source,vision_model_ref}`,
   `chapters.import_job_id` + partial unique index for the idempotency guard.
5. **worker-infra** — new `processPdfImport` per-chunk loop (skips pandoc; one `/internal/parse/pdf-chunk` call
   per N-page window; final chapter count re-queried from DB, not accumulated, since `ON CONFLICT DO NOTHING` can
   skip chunks on redelivery). **Live smoke caught a real bug**: the partial unique index
   `idx_chapters_unique_import_job_path` requires the `ON CONFLICT` clause's `WHERE` predicate to match exactly —
   the first live run failed 100% with `SQLSTATE 42P10` until `WHERE import_job_id IS NOT NULL` was added to the
   `ON CONFLICT` target itself, not just the index. Fixed, rebuilt, re-ran clean.
6. **Frontend** — new `features/pdf-import/` wizard mirroring `features/extraction/`'s hook/component split
   (`usePdfImportState`/`usePdfImportPolling`, NOT `components/import/ImportDialog.tsx`'s monolithic anti-pattern),
   wired into `ChaptersTab.tsx`. `tsc --noEmit` clean, 8 new tests. **Not yet i18n'd** (hardcoded English strings) —
   flagged, not silently skipped; this repo's 18-locale standard is a real follow-up debt for this feature.

**Live E2E proof** (not just unit tests): built a 5-page test PDF (prose + one real embedded bar-chart PNG) via
PyMuPDF, rebuilt+restarted provider-registry-service/knowledge-service/book-service/worker-infra with all changes,
created a real book via the API, ran `pdf-peek` (correct page_count=5) then a real import
(`pages_per_chunk=2, caption_images=true`, real gpt-4o BYOK model) through the gateway. Result: 3 chapters created
exactly as expected (`ceil(5/2)`), titled `"Pages N-M: <best-effort heading>"`, the chart image captured on the
right chapter/page with a REAL gpt-4o caption ("The bar chart compares three engines (A, B, and C)...") both
stored in `chapter_page_images` AND correctly inlined into the chapter's scene text as
`[Image (page 3): ...]` — the exact mechanism meant to make chart content visible to glossary/KG extraction.

**`/review-impl` same session — 3 HIGH findings, all fixed + live-reverified, user-directed.**
User named the concrete gap: Ollama/LM-Studio/Anthropic genuinely have vision-capable models (e.g.
`google/gemma-4-26b-a4b-qat` in LM Studio) and the original stub (`ErrOperationNotSupported`) was wrong, not a
deliberate scope cut. **HIGH#1 — the stub was a real gap, not a safe default**: LM Studio's OWN model-inventory
parsing (`parseLMStudioNativeModels`, `adapters.go`) already detects+flags `capability_flags.vision`, and
Ollama/LM-Studio already serve chat over the identical OpenAI-compatible `/v1/chat/completions` endpoint OpenAI
itself uses — the capability was already discoverable in this codebase, captioning just wasn't wired to it. Fixed:
real `CaptionImage` for all 3 (`local_vision.go` shares OpenAI's wire-shape builder via new
`openai_compat_vision.go`; `anthropic_vision.go` uses Anthropic's structurally different Messages-API image-block
shape), `adapters_vision.go`'s stubs deleted, 17 adapter tests (was 9). **HIGH#2 — self-inflicted migration
crash-loop**: adding `'vision'` to only the FINAL `llm_jobs_operation_check` constraint block (not backfilling it
into the 4 earlier historical DROP+ADD blocks) violated a rule the migration file's OWN comment (line 164) already
documented from a prior incident — Postgres validates each ADD CONSTRAINT against existing rows as the whole
schemaSQL replays every startup (no version tracking), so an earlier block missing `'vision'` fails outright once
a `'vision'`-tagged row exists. Caught the instant provider-registry-service was rebuilt after live-testing created
such a row — service refused to start. Fixed by adding `'vision'` to all 5 blocks. **HIGH#3 — reasoning-model
token starvation**: live-testing against LM Studio's `google/gemma-4-26b-a4b-qat` (a reasoning-capable local vision
model) returned `LLM_VISION_CAPTION_FAILED: upstream returned no caption` at the original `max_tokens=150` — the
model correctly identified the test chart in its `reasoning_content` scratchpad (147 tokens) but got cut off
(`finish_reason="length"`) before ever writing the real answer into `content`. Confirmed live at `max_tokens=600`
the same model completes reasoning (~440 tokens) and emits a correct caption. Fixed: `_CAPTION_MAX_TOKENS` raised
150→700 (`internal_parse_pdf.py`). **Live-reverified end-to-end after all 3 fixes**: real book import via LM
Studio's local model ($0 cost) — "This bar chart displays three blue bars labeled 'Engine A,' 'Engine B,' and
'Engine C.' The bars show an increasing trend..." — correctly captioned, stored, and inlined, through the full
book-service→worker-infra→knowledge-service→provider-registry→LM-Studio chain. Two test books now exist in dev DB:
`019f3804-...` (gpt-4o captions) and `019f381e-...` (LM Studio captions) — both available for the still-open
glossary/KG extraction test noted above.

**Deferred / not done this session:**
- **Glossary/KG extraction was NOT run against the new PDF-imported book** — the original motivating question
  ("does glossary/KG work on a technical book") is still open; this session built+proved the IMPORT pipeline only.
  The test book (`019f3804-7eb7-7958-8e71-f7c6c837f945`, "PDF Import Smoke Test") still exists in the dev DB with
  its 3 real chapters — next session can run extraction against it directly (note: its `extraction-profile` came
  back empty `kinds:[]` since it has no `genre_tags` — a manual kind list will need to be passed to the extraction
  job request rather than relying on profile auto-resolution, consistent with the original audit's finding that
  extraction profiles are genre-driven and technical books get nothing suggested by default).
- **Orphaned-MinIO-blob cleanup on a failed PDF import** — consciously deferred (pre-existing gap shared by
  docx/epub too, not introduced by this feature; gate reason: out-of-scope/pre-existing).
- ~~i18n for the new wizard strings~~ → **RESOLVED same day, follow-up.** Authored `en/pdf-import.json` (52
  keys), wired all 6 step components + the ChaptersTab "Import PDF" button through `useTranslation`, ran
  `scripts/i18n_translate.py` to generate all 16 other locales — 0 hard/soft verify failures across all 17
  after fixing one flaky `zh-TW` key by hand (the model echoed English back inside a crowded batch; isolated
  single-key retry succeeded instantly). That flakiness surfaced a real gap in the translation tool itself
  (self-heal only retried HARD failures, never SOFT ones) — fixed by adding an `isolate_retry_soft()` pass to
  `scripts/i18n_translate.py`, verified live against the same key.
- ~~Anthropic/Ollama/LM-Studio vision support~~ → **RESOLVED at `/review-impl` same session** — real
  implementations for all 3, live-verified against LM Studio's local `google/gemma-4-26b-a4b-qat` model.

---

**Glossary unmatched-attribute fallback (D-GLOSSARY-UNMATCHED-ATTR-FALLBACK) — shipped, live-verified, 2026-07-06.**
Design question raised during the PlanForge auto-bootstrap follow-up: an AI proposal (bootstrap gate, extraction,
future callers) can send a glossary attribute code a kind hasn't registered (e.g. guessing a field name). PO framed
the philosophy explicitly: glossary/wiki content is authored prose, not a rigid code schema — losing an
AI-observed detail entirely (the prior behavior: silent no-op, `services/glossary-service/internal/api/
extraction_handler.go`'s `createExtractedEntity`/`mergeExtractedEntity`, `if !ok { continue }`) is worse than
filing it under a generic heading. Considered and rejected: (a) strict validation/reject — fights the intentional
EAV-not-JSON-schema design (`docs/standards/scope-separation.md` SCOPE-3); (b) a new `entity_facts` `fact_kind='note'`
extension — architecturally cleaner (reuses the bi-temporal SSOT) but L-sized; PO chose the simplest option that
still avoids a 4th parallel storage location — **route into the kind's EXISTING "description" textarea** (every
system-seeded kind already ships one, `internal/domain/kinds.go`), not a new column/table. **Fix (S-sized, one
shared write path — both callers of `/internal/books/{id}/extract-entities` benefit, not just PlanForge):**
new `appendUnmatchedAttrsToFallback` helper — appends (never overwrites) unmatched `code: value` lines into the
kind's `description` attr, honors the INV-8 verified-clobber guard (a human-verified description is never
machine-appended to; those codes report skip-reason `verified` instead), degrades to the old silent-skip when the
kind has no `description` attr_def at all (skip-reason `unmapped`). 7 new tests (1 pure-unit no-DB early-return
proof + 3 DB-integration: create/merge-append/verified-guard) all pass; full glossary-service suite green
(`-p 1`, sequential — the one flake seen under default parallel `go test ./...`, `internal/migrate`'s
`TestSeed_Reconciles…`, reproduced IDENTICALLY with the change reverted and is a pre-existing shared-test-DB
cross-package race unrelated to this change, per [[shared-db-parallel-test-migration-deadlock]] class). **Live-
verified** against the real dev stack: rebuilt+restarted glossary-service, POSTed an unmatched attribute
(`signature_scent`) to a real adopted book via `extract-entities`, confirmed by direct SQL it landed as
`- signature_scent: sandalwood` inside `description` (not dropped), cleaned up the test entity.

**Same feature — `/review-impl` run immediately after, 1 HIGH + 3 related findings, all fixed same session.**
HIGH: the fallback reported the ORIGINAL unmatched code (not "description") as "written", which feeds
`emitChapterFacts` (Path A) — minting a **phantom `entity_facts` row** for an attribute with no `attr_def`/no EAV
cell at all, a direct **INV-FACTS** violation (`entity_facts` is the SSOT; the EAV projection is a regenerable
cache that must agree with it). Worse: this exposed a **pre-existing, independent variant of the same bug on
CREATE** (`createExtractedEntity`'s caller blindly listed every raw attribute key as "written", matched or not) —
live in the codebase before this session, only surfaced because **3 existing tests
(`TestBulkExtract_EmitsTemporalFacts`, `TestFactsHTTP`, `TestProposeNewEntity_CreatesDraftThenDedups`) were
unknowingly asserting on the phantom fact** as if it were correct behavior (all three used an unregistered
Chinese attribute code `境界`, coincidentally proving the bug rather than real EAV-backed emission). Also found:
the `glossary_propose_new_entity` MCP tool's `proposeNewEntity` had its own pre-check duplicating (now-stale)
"this code will be dropped" logic, telling the calling LLM an attribute "didn't land" when it actually landed in
`description` — self-correcting-error accuracy defect. **Fix:** `createExtractedEntity` now returns real
`(written, skipped)` (was `(uuid.UUID, error)` only) computed from actual attr_def matches, not raw keys; a new
`markDescriptionWritten` helper reports "description" (a real attr_def, fact-emission-safe) instead of the
phantom code; all 3 callers (`bulkExtractEntities` create branch, `mcp_server.go` `proposeNewEntity`, 2
`facts_handler.go` call sites) updated for the new signature; `proposeNewEntity`'s stale duplicate pre-check
removed in favor of the real returned skip list. 3 pre-existing tests fixed to seed with a REAL attr code
(`occupation`) instead of the phantom `境界`; 1 new regression test
(`TestBulkExtract_UnmatchedAttrFallbackDoesNotMintPhantomFact`) proves zero phantom fact rows on both create AND
merge while the real EAV capture still lands. Full suite green (`-p 1`); live-verified against the real dev
stack — a Path-A extraction with an unmatched code now shows ONLY `name`/`appearance` in `entity_facts` (no
phantom row) while `description` correctly carries the note, cleaned up after.

---

**Context-retrieval M4 — M1a passage→graph bridge RE-MEASURED on a 2nd, independent, MULTILINGUAL corpus + a fix it surfaced, 2026-07-06.**
Plan [`2026-07-06-context-retrieval-improvements.md`](../plans/2026-07-06-context-retrieval-improvements.md);
eval [`docs/eval/context-budget/M4-multilingual-bridge-remeasure-2026-07-06.md`](../eval/context-budget/M4-multilingual-bridge-remeasure-2026-07-06.md).
The first M4 A/B was English/Dracula only; the platform is Vietnamese/Chinese. A live Neo4j survey found a
**2nd usable corpus** the first M4 said didn't exist — Vietnamese xianxia `019f1783` (30 ent / 95 rel / 181 pass,
denser than Dracula). **Result:** the bridge is **cross-lingually safe** (no genuine answer regression — the one
apparent A/B "worse" is a judge-truncation artifact on a byte-identical answer) and the Dracula "weak-but-positive"
GO replicates — BUT shipped M1a was **materially degraded on Vietnamese**: it reuses `extract_candidates` (a
user-MESSAGE extractor) over passage PROSE, where quoted dialogue sentences + sentence-initial common words
(`Một`/`Sự`/`Không`) starved the anchor cap → **1/6 slots resolved to a real entity**. **FIX SHIPPED** (bridge-local,
shared extractor untouched): `_looks_like_sentence` junk-filter + **resolve-THEN-cap** over a bounded pool in
`facts.py` → mechanism yield **2×** (3.42→6.92 facts/query, 8→11 of 12 queries), 3 new unit tests, `test_facts_selector`
21/21 (the 3 `test_mode_full` budget reds are PRE-EXISTING — fail identically without this change). Harness gotcha
recorded: the Vietnamese passages index under a *different* bge-m3 `user_model` id (`019eeb08-8bff…`) than Dracula's —
an eval must embed the query with the corpus's OWN index model or `find_passages_by_vector` returns 0 (cross-service
model-ref bug class). **NEXT:** M1b/M3 stay gated on measurement (don't build speculatively). Two tracked rows below.
- **D-BRIDGE-NAME-FRAGMENT ✅ CLEARED (same session):** the shared `LATIN_NAME_RE` split multi-token
  Sino-Vietnamese names (`Cửu U Ma Cơ`→`Cửu`/`Ma Cơ`; `Hắc Sát Lão Nhân` truncated to 3 words). Fixed in
  `scripts.py`: subsequent word may be a single-uppercase INTERIOR connector (lookahead requires a real word to
  follow, so a trailing stray capital like `Paris U` isn't glued on) + word cap 3→5. Shared-regex regression pass:
  knowledge unit **3606 passed** (4 reds pre-existing — fail identically on a stash baseline); 4 new `test_scripts`
  cases. **Live-verified**: `Cửu U Ma Cơ` now resolves whole; with both bridge fixes the Vietnamese A/B is a CLEAN
  **+36% overall / +67% bridge-class, 3 wins / 0 regressions** (bridge yield 3.42→10.83 facts/query).
- **D-EVAL-BOOK ✅ CLOSED (same session):** built a larger **Chinese** corpus (万古神帝 `019f37f0`, 158 ent /
  402 rel / 58 pass, extracted this session ch 1-20) and re-ran the A/B — eval
  [`M4-wangu-largecorpus-2026-07-06.md`](../eval/context-budget/M4-wangu-largecorpus-2026-07-06.md): **+19% overall /
  +17% bridge-class (→2.0) / 0 regressions**. M1a is now sized across **3 corpora / 3 languages** (EN +14%, VI +36%,
  ZH +19% overall; bridge-class +50/67/17%; **0 of 31 questions regressed anywhere**) — a **safe, reliably-positive**
  recall aid (modest magnitude, decisive safety + cross-lingual consistency). Keep ON.
- **D-BACKFILL-NO-SCOPE-LIMIT ✅ CLEARED (found building the corpus, commit `5205e5c8c`):** setting a project's
  embedding model (`PUT /embedding-model`) fired a SYNCHRONOUS whole-published-book passage backfill (no scope limit) —
  on 万古神帝 (4232 ch) it ran away embedding ~11.6K passages before a restart stopped it. Fix: `chapter_range` scope on
  both backfills + threading the extraction job's scope_range + an inline cap (`kg_backfill_max_inline_chapters`=200)
  that skips the synchronous whole-book backfill on large books. 3 new tests; live-verified (scoped run ingested only
  the 20-ch slice). Also diagnosed an extraction "stall" (user-caught): NOT a systemic bug — a **transient LM Studio
  mid-stream drop** (ruled out governor/breaker/idle-timeout with evidence; a 2-ch reproduction completed cleanly).
- **Extraction over-extraction — analysis + plan (`340de487e`):**
  [`2026-07-06-extraction-cost-and-tiering.md`](../plans/2026-07-06-extraction-cost-and-tiering.md). Per user question
  "are we over-extracting?": the pipeline runs **4 LLM passes over the same chunks** (entity/event/fact/relation) →
  ~28 calls/chapter ≈ 84K tok/chapter (text paid 4×). Extract-vs-load break-even ≈ 19 uses/chapter → eager whole-book
  extraction of a 4232-ch novel (~355M tok) is a net loss on the long tail. Plan: P1 unified prompt (4×→1×), P2
  fewer/larger chunks, P3 lazy/selective extraction (also fixes the never-gated Knowledge-extraction defect), P4 hybrid
  raw-in-context + KG tiering, P5 local token estimation (cost is invisible — `tokens_used=0` on local). Extends
  `D-EXTRACTION-PROMPT-FANOUT` + new `D-EXTRACTION-EAGER-WHOLE-BOOK`. **NEXT (retrieval track): M1b/M3 still gated on
  measurement; the extraction cost work (P1 first) is the higher-value follow-on the user surfaced.**

---

**Tool-catalog-simplification — live-verified against the real stack, spec fully CLOSED (all §10 items), 2026-07-06.**
[`docs/specs/2026-07-06-tool-catalog-simplification.md`](../specs/2026-07-06-tool-catalog-simplification.md) §10
item 5 (never done before — everything prior was unit/integration tests against mocks or a small offline eval
catalog). Rebuilt + restarted chat-service/ai-gateway/glossary-service and verified live: metadata passthrough
(`_meta.visibility` on the real MCP wire), CAT-4 exclusion, and the token measurement (**~4,118 tokens vs the
original ~24,000-token baseline, an 83% reduction**, live-confirmed on the real 190-tool federated catalog).
**Found a real bug live verification alone could catch**: `search_catalog`'s fuzzy-rescue branch never actually
enforced its own documented precondition ("rescues a tool with NO token overlap") — an exact single-shared-word
overlap (e.g. an unrelated tool's synonym containing "book") auto-qualified as a "strong fuzzy hit," overriding the
whole score to 1.0. Invisible on eval-doc's small 4-tool test catalog; real at the actual 190-tool scale, where
`glossary_ontology_upsert` didn't even place top-5 for the eval's own query ("add a new kind to the book"). Fixed
in both `tool_discovery.py` and `find-tools.ts` (gate on `overlap == 0`), 4 new regression tests, re-verified live
post-fix (now ranks 1st for all 3 original eval queries). Also live-smoked `glossary_propose_entities` against the
real POC book (`019f1783-ebb4-…`) — 2 draft entities created, verified by DB effect, cleaned up after. Commit
`e12bf4056`. **Lesson for future specs: an offline eval catalog this small can hide ranking bugs that only show up
at real tool-count scale — a live cross-service smoke against the REAL federated catalog is not optional polish,
it's where this exact bug was found.**

---

**Tool-catalog-simplification — all 6 open questions resolved, spec CLOSED, 2026-07-06.**
[`docs/specs/2026-07-06-tool-catalog-simplification.md`](../specs/2026-07-06-tool-catalog-simplification.md)
§11 fully resolved: 5 items confirmed-as-shipped (memory_search stays owned by the
2026-07-05 plan, `story` stays hot, per-session-only legacy pinning, `maxItems:50`
accepted as-is), 1 required new BUILD — PO confirmed bulk entity creation is a real
near-term need, so `glossary_propose_entities` shipped (batch sibling of
`glossary_propose_new_entity`, now legacy-tagged; same CAT-1/3/4 playbook as the
ontology tools; reuses `proposeNewEntity` per item). `entity_set_genres`/
`chapter_link`/`evidence` batching stays unconfirmed, deferred until a real caller
appears. Commit `ae6358071`.

**Same commit — 3 recurring test failures fixed (user: "quá phiền", just fix them):**
- chat-service `_emit_chat_turn`: `_chain_reason`/`_stateful`/`_prev_rid`/
  `_delta_msgs` were only initialized inside the tool-calling branch but read
  unconditionally later — `UnboundLocalError` on every plain-gateway (non-tool)
  turn. Hoisted the init above the if/else. Fixed 10/14 `test_stream_service.py`
  failures; the other 4 were a stale test assumption (a positional INSERT-arg
  index that shifted when `response_id` was appended as a new trailing param by
  an earlier unrelated change) — updated the indices.
- glossary-service `TestFK_WikiArticle_RestrictsEntityDelete`: root-caused to the
  migration's idempotency guard checking a constraint's NAME instead of its
  actual delete-action — the pre-existing CASCADE constraint already carried the
  name the guard was checking for ("already applied"), so the CASCADE→RESTRICT
  swap had never actually run against a real (non-fresh) `wiki_articles` table.
  Verified live via `pg_constraint`/`pg_get_constraintdef` before (CASCADE) and
  after (RESTRICT) the fix.
- Full glossary-service suite: green (all packages). Full chat-service suite:
  1084/1084 passed (was 14 failing).

---

**PlanForge auto-bootstrap Phase 2 M1 (hardening) — done + live-verified, 2026-07-06.**
User's POST-REVIEW verdict on the POC: complete [B]/[C]/[D] + a real UI
before production (not ship the POC as-is) — see
[`docs/specs/2026-07-06-planforge-auto-bootstrap.md`](../specs/2026-07-06-planforge-auto-bootstrap.md)
§6 for the M1-M4 milestone breakdown. **M1 done**: found+fixed a real
double-propose race the POC's own tests missed — dedup was scoped to only
`status='applied'` proposals, so calling `propose()` twice before applying
the first would silently re-offer (and, if both got approved+applied,
double-create) the same chapters. Fixed: `list_active_for_book` now covers
every non-rejected status; dedup reads each active record's `diff` directly.
Also added: negative-path router tests (403 insufficient-grant, 404
no-grant, mirroring `test_grant_gate.py`), info/warning logging through
propose/approve/reject/apply. 6 new tests, full suite green (1595 unit + 162
integration). Live-verified post-rebuild: propose against the same real
run now correctly logs "already-claimed by another proposal" and returns
an empty diff (both target chapters already real from the POC's earlier
live-verify). Commit `c5a9caf2d`.
**M2 (real [B] glossary wiring) — done + live-verified, same day.** Wired
compile()'s already-correct `glossary_seeds` (previously dead code) into the
gate as a second diff-item type (`new_glossary_entities`), calling a NEW
`glossary_client.seed_entities_or_raise()` at apply time (distinct from the
existing degrade-safe `seed_entities` used by read-time context assembly —
this gate needs failures to surface, not silently degrade). **Discovered
mid-build**: glossary-service requires a book's ontology to be "adopted"
first (`GLOSS_BOOK_NOT_SCAFFOLDED`, 422) — a real, separate, user-driven
action (picking genres/kinds via the Graph Schema tab), correctly scoped
OUT of this gate rather than auto-triggered. Surfaced as an actionable 422
with a clear message; the proposal is marked `failed` (resumable — retry
after adopting succeeds). 5 new tests, full suite green (1595 unit + 166
integration). Live-verified: seeded a real glossary entity ("Nữ chính")
through the gate against the real dev stack, confirmed present in
glossary-service's own DB with correct attributes/tags. Commit `b606a70a3`.
**M3 (scene/beat drafting context) — done + live-verified, same day.**
Escalated twice mid-build (both reported to the user before proceeding,
per "task is larger than classified — announce"): first found the Stage
0-5 pipeline is a full 5-6-LLM-call orchestration (cast/motifs/beats/
arcs/decompose/heal), not a single call; second found its own Stage 0
`propose_cast`+`seed_entities` would double-seed glossary against M2's
fix if invoked from inside the gate. User chose full completion both
times. **Resolution: the gate never triggers the pipeline itself** — it
only reads an ALREADY-COMPLETED `plan_pipeline` job's result if a
separate, explicit `compile(run_pipeline=true)` call already produced
one, so propose() stays zero-LLM-call regardless. Along the way, fixed a
REAL pre-existing bug: that pipeline path had NEVER worked in production —
`ChapterPlan(**c)` TypeError on every invocation (wrong field names +
missing required keys). Fixed the mapping (`chapter_id=event_id` for
correlation) + filled in missing keys; `pipeline_job_id` now persists
onto `plan_run.checkpoint_state` (previously returned once, never
queryable again). 9 new tests, full suite green (1595 unit + 170
integration). **Live-verified end-to-end with a real local model**: ran
the actual 6-stage pipeline for real, confirmed completion (previously
guaranteed to crash) with the correct `chapter_id: "arc_2_event_1"`
correlation, and confirmed bootstrap's `propose()` reads the completed
job without error. Commit `8df1be958`.
**M4 (real plain-language UI) — done + live-verified, same day. All 4
milestones of Phase 2 now complete.** New `BootstrapPanel` + `useBootstrap`
replace raw JSON as the review surface for propose/approve/reject/apply
(diff items as plain-language cards, every failure state incl. M2's
"book not adopted" 422 shows the actionable message + Retry, never a dead
end — the LOCKED DESIGN PRINCIPLE from the earlier redesign mockup).
**User caught a real adjacent gap mid-verify**: Compile's `arc_id` was
STILL a bare text input (D-PLANFORGE-GUI-AUDIT gap #1 — designed in the
mockup, never built) — my new bootstrap panel was unreachable behind it
for a real user. Fixed: `get_run_detail` now surfaces the spec's own
`arcs` as `{id, title}` (previously only artifact refs, never content,
were ever returned); `PlanRunView` renders a real picker by title. 13
new/changed tests, full suite green (1595 backend unit + 171 integration,
4482 frontend). Live-verified through the actual browser (real login,
real Studio, real Planner panel): arc picker shows real titles sourced
from the real spec; bootstrap propose() against a real compiled run
renders the correct plain-language state. Commit `9c685c28a`.
**PlanForge auto-bootstrap Phase 2 (M1-M4) is now complete** — the POC's
POST-REVIEW gaps are all closed. Not yet done (explicitly out of this
effort's scope, per the design doc's non-goals): bulk auto-draft,
line-by-line approve/reject, and re-visiting whether the arc-picker fix
should extend further (e.g. an empty-arcs self-check hint).
**`/review-impl` on the whole M1-M4 effort — 1 HIGH + 3 MED + 1 LOW found,
all fixed same day.** HIGH: `apply()` called `get_book()` OUTSIDE its
try/except and only caught 2 known error types inside it — ANY other
failure (a transient book-service blip, a DB hiccup) left the proposal
stuck at `status='applying'` FOREVER, un-retriable (`claim_for_apply`
only re-claims from `approved`/`failed`). Fixed: the whole post-claim
body now sits inside one `try` with a broadened `except Exception`
(doesn't swallow `CancelledError`). MED: recompiling the same run with a
different arc left the PREVIOUS arc's stale bootstrap proposal on
screen — `onCompile` never called `bootstrap.reset()`. MED: 2 REAL
`plan_bootstrap_proposal` rows already in the live DB predate the
`new_glossary_entities` key (pre-M2) — backend already defends with
`.get(key, [])`, `BootstrapPanel` didn't (not reachable today, but
`api.bootstrapGet` sits unused, inviting the crash the moment a "reload
proposal" feature calls it). LOW: a malformed `checkpoint_state`
pipeline_job_id could crash the whole (required) `propose()` call over
an optional M3 enhancement. 6 new tests (2 against a real Postgres
proving the stuck-state fix + resumable retry), full suite green (1595
unit + 173 integration + 4488 frontend), live-verified no regression on
the real dev stack. Documented-not-fixed: `_serialize_run`'s new `arcs`
field adds a per-row query to the Runs LIST endpoint though only the
single-run Compile picker needs it — bounded, low-impact today. Commit
`6afae09e5`.

---

**Tool-catalog-simplification — Part D (pinned_legacy_tools) + Part A prompt wiring shipped, 2026-07-06.**
[`docs/specs/2026-07-06-tool-catalog-simplification.md`](../specs/2026-07-06-tool-catalog-simplification.md).
Completes the spec's rollout (§10 items 1-3 all DONE): CAT-4 legacy-visibility filter +
group directory (commit `8927713c7`), `glossary_ontology_upsert`/`delete` Go handlers
(commit `0d4ec73cd`), and this pass's two remaining pieces (commit `dee43f8de`):
`group_directory_text()` now actually rides the live system prompt (was schema-only
before), and a new `pinned_legacy_tools` per-session setting lets a user manually
re-pin a superseded (find_tools-invisible) tool for one session only — closed-set
validated against the live catalog (422 on an unknown name), kept as its OWN session
column rather than folded into `enabled_tools` (folding in would've silently flipped
the whole session into curated mode from pinning one legacy tool). FE: a collapsed
"Advanced tools" section in the tool-add modal + a distinct amber chip in the context
rack. 24 new tests (12 backend + 12 FE), full chat-service + FE chat suites green,
`tsc --noEmit` clean. Remaining (deferred, tracked in the spec §10 item 4-5): audit any
FE surface still naming the 6 old glossary tools directly; cross-service live-smoke of
the new ontology tools through the real chat agent + a before/after token measurement;
composition/knowledge/translation tool unification as separate follow-on specs.

**Found but NOT fixed (flag for the owning session/track):** a full chat-service suite
run surfaced `UnboundLocalError: cannot access local variable '_chain_reason'` in
`stream_service.py`'s `_emit_chat_turn`, in the plain-gateway (non-tool-calling) branch —
`_chain_reason` is only initialized inside the `if use_tools or _subagent_tool is not None:`
branch (~line 2810) but read unconditionally later (~line 3143). Traced to commit
`dbc5c0b31` ("feat(caching): P3 stateful chain-management"), NOT this session's work —
verified via `git diff --stat HEAD` showing zero further diff on that file before this
session's edits landed. Breaks basic non-tool-calling turns (`test_emits_text_deltas`,
`test_persists_assistant_message`, etc. — 14 failures). Left untouched since it's a
different feature's actively-changing file in a shared checkout; whoever owns the
stateful-chain track should add the missing `_chain_reason`/`_stateful`/`_prev_rid`/
`_delta_msgs` initialization to the `else:` branch at ~line 2883.

---

**PlanForge auto-bootstrap POC — BUILT + live-verified end-to-end, 2026-07-06.**
The gate (propose→record→approve→apply) + [A] chapter-shell creation, per
[`docs/plans/2026-07-06-planforge-auto-bootstrap-poc.md`](../plans/2026-07-06-planforge-auto-bootstrap-poc.md).
New: `plan_bootstrap_proposal` table (composition-service migrate.py), repo
`app/db/repositories/plan_bootstrap_proposals.py` (atomic claim via
conditional UPDATE, resumable-after-failure), `app/services/bootstrap_service.py`
(propose is pure deterministic diffing — zero LLM calls for this scope — via
the already-existing `book_client.list_chapters()` + prior applied records,
dedup by title per the accepted POC approximation), `app/routers/plan_bootstrap.py`
(propose/approve/reject/apply/get), `book_client.create_chapter()` (never
sends `sort_order` — book-service auto-appends). 17 new tests (5 repo + 6
service + 6 router), all green; full composition-service suite (1589 unit +
161 integration) still green. **Live-verified against the real dev stack**
(rebuilt+restarted composition-service, real JWT via gateway login): proposed
against book `Ma Nữ Nghịch Thiên (POC)` (019f1783-ebb4…) + its real compiled
run, approved, applied — 2 real chapters ("Event 1 — Nhập Môn", "Event 2 —
Biến Hóa Đầu Tiên") created via book-service, appended at sort_order 13/14
after the book's existing 12 chapters (no collision — confirmed book-service's
auto-append), visible in the real Studio Chapter Browser (screenshot taken,
not committed). Re-applying the same record was confirmed a safe no-op (no
duplicate chapters). **These 2 chapters are now real, intentional data in the
test account's own POC book** (same account this repo's Test Account section
designates for browser smokes) — left in place as live evidence, not rolled
back.
Explicitly out of POC scope (unchanged from the design): real [B] glossary
POST wiring, [C]/[D] (drafting context + reachability), bulk auto-draft,
line-by-line approve/reject, polished plain-language review UI (raw JSON
from `GET .../bootstrap/{id}` is the POC's review surface). These are their
own future scoped PLAN/BUILD passes.

---

**PlanForge auto-bootstrap — CLARIFY+DESIGN done, POC scoped, NO BUILD yet, 2026-07-06 (superseded by the BUILD above).**
[`docs/specs/2026-07-06-planforge-auto-bootstrap.md`](../specs/2026-07-06-planforge-auto-bootstrap.md).
User asked: does planning from a completely empty book auto-create the ontology/KG/arc/chapter/
scene/beat? **Traced the real code (2 research passes) — answer is no, and worse than assumed.**
`compile()` only ever produces a JSON `PlanningPackage`; `run_pipeline=true` additionally seeds
Glossary **character** entities but via an INDEPENDENT `propose_cast` LLM call that ignores the
spec's own already-parsed character/mechanic data (`compile_artifacts`'s own `glossary_seeds` is
dead code, computed but never POSTed anywhere); Neo4j KG sync then chains off that (silent no-op
if Neo4j isn't configured). **No planning code path, in any mode, ever creates a real book-service
`Chapter` row** — `book_client.py` doesn't even have a `create_chapter` method. "Scene" IS a real
DB table (`book-service.scenes`) but only populated by the document-IMPORT parser, then
immediately flattened back into one chapter body — a read-only KG-extraction index, not an
editable unit. "Beat" has NO persisted representation anywhere — pure in-memory JSON inside the
Stage 0-5 pipeline, discarded after the job response. **The smallest real editable unit in the
whole architecture is the entire Chapter's Tiptap body** — this is a design constraint to respect,
not a gap to invent around.
User's direction: build a multi-step auto-bootstrap workflow, but **POC first, done rigorously**
(their words: "cân poc và làm nghiêm ngặt vì nó có rất nhiều bước, khá là lớn"). Proposed 5-step
workflow in the spec: [A] create real chapter shells from `package.chapters[]` (NEW — zero prior
art, the foundational unknown) → [B] fix glossary seeding to use the spec's own data (bug fix) →
[C] wire Stage 0-5 scene/beat plans as per-chapter drafting CONTEXT, not new DB rows → [D] reach
the already-working `run_chapter_generate` per real chapter_id → [E] KG sync falls out for free
once [B] is correct. **Recommended POC scope: [A] ALONE** — chapter-shell creation +
`event_id↔chapter_id` mapping, live-verified in the Studio's Manuscript Navigator, nothing else.
3 open questions logged in the spec (mapping storage, ordinal collision on non-empty books,
idempotency on re-compile) for the next CLARIFY checkpoint before even the POC's own BUILD.
**Correctly classified XL — this doc is CLARIFY+DESIGN only, no code changes.**
**Revision same day — added a propose→record→approve→apply gate** (user: LLM plans ONCE, saves a
reviewable record, applies only after human approval, never re-runs the LLM per apply/retry).
Mirrors Enrichment's H0 quarantine+promote shape + PlanForge's own `plan_apply_revision` honesty
contract. [A]/[B]/ontology-kind-gaps now sit behind this gate: one propose pass → `plan_artifact`
kind `"bootstrap_proposal"` (status pending) → human approve → deterministic apply with per-item
status (partial-failure visible, not a bare retry). POC scope revised to prove the gate + [A]
together, not [A] in isolation. 4 open questions now (added: record storage shape — dedicated
table leaning, given it's a real state machine not a static blob; reject semantics — kept for
audit like Enrichment's retract, not deleted). Commit `a2d9d6a83`.
**CLARIFY closed same day — all 4 open questions resolved with fresh code evidence** (book-service's
`createChapter` Go handler + OpenAPI contract, Enrichment's `enrichment_proposal` schema,
`plan_artifact`'s own schema). Record lives in a NEW dedicated table `plan_bootstrap_proposal`
(confirmed `plan_artifact` is write-once with no status/UPDATE path — wrong fit), scoped by
`book_id`+`owner_user_id`+`run_id` per tenancy rules, modeled on `enrichment_proposal`'s
status-enum + transition-guard-trigger shape. Ordinal collisions are a non-issue — book-service
already auto-appends when `sort_order` is omitted. Idempotency dedups against
`book_client.list_chapters()` (existing method, no new code) + prior applied records' `applied_results`.
Reject keeps `status='rejected'` for audit. Bonus: POC's propose step needs **zero LLM calls** —
pure deterministic diffing. Moving to PLAN+BUILD on the POC next. Commit `0f5eeb669`.

---

**`D-PLANFORGE-GUI-AUDIT` follow-up — draft HTML mockup for a Planner panel redesign, 2026-07-06.**
User confirmed the root diagnosis: the shipped Planner panel (see this file's earlier
`D-PLANFORGE-GUI-AUDIT` entry — P0 crash fixed same day + 4 UX gaps found) is a **leaky
abstraction**, not just missing buttons — it renders raw backend vocabulary (`arc_id` strings, rule
names like `pa_not_realm`/`sg_value_shift_per_scene`, raw `var_delta` shapes) at a novel-WRITER
audience with no reason to know any of it. Backend pipeline (propose→self-check→interpret→apply→
autofix→checkpoint→validate→compile, 8 rules) stays as-is — only the frontend translation layer
needs a redesign. Draft HTML mockup (same process as Agent Mode/Cursor-for-novels — CLARIFY→DESIGN
→draft-HTML→spec→build):
[`design-drafts/planforge/2026-07-06-planner-panel-redesign-mockup.html`](../../design-drafts/planforge/2026-07-06-planner-panel-redesign-mockup.html).
5-step flow (Start → Understood → Check & Fix → Ready to Draft → Done), dark theme tokens copied
verbatim from `frontend/src/index.css`'s real `:root` HSL values (shows "inside the real Studio,"
not a generic doc). Key translations: spec.arcs/characters/variables rendered as plain-language
cards instead of a raw artifact-ID list; validation findings split into hard-fail vs advisory tiers
(mirroring the `tier` field shipped in `validate.py` 2026-07-06) with "Fix this for me" buttons
wired conceptually to the existing (chat-only) `plan_apply_revision`/`plan_handoff_autofix` tools;
the blind `arc_id` text input replaced with a card-picker sourced from the spec's own `arcs[]`.
Live-verified rendering (local static server + Playwright screenshots, 3 states checked) before
sharing — not wired to any real API, review artifact only. **Not yet a written spec or BUILD** —
next step if picked up: gather any feedback on the mockup, then write the accompanying spec doc
(`docs/specs/YYYY-MM-DD-planforge-planner-redesign.md`) before implementation.
**v2 same day — edge-case pass** (user: "chức năng này phải đủ dễ sử dụng, tránh tình huống check
lỗi, người dùng phải mò và sửa raw plan, họ không làm được đâu" — never let a failure path force
the writer to touch the raw plan themselves). v1 had 5 gaps that would have done exactly that:
"Quick check" (the fragile regex parser) was the DEFAULT mode — swapped default to AI-assisted;
no state existed for "we couldn't understand your document" (0 arcs/0 characters) — added a
dedicated low-extraction branch with concrete next steps; "Continue anyway" let you skip past a
hard finding even though the REAL backend hard-blocks `compile()` on any hard-tier failure (the
mockup was lying about what happens next) — Continue is now disabled+explained until every hard
finding resolves, advisory findings never block; "Fix this for me" had no failure path — added a
working state + an autofix-failed fallback that suggests a concrete plain-language edit to the
ORIGINAL text or hands off to chat, never raw JSON; the arc picker let you select an admittedly
incomplete arc with no guidance — made incomplete arcs genuinely non-selectable with an "Ask AI to
help complete this arc" escape hatch. **Locked design principle added to the file: this panel
never exposes a raw spec/JSON editor as a fallback, at any failure point.** Live-verified all new
states (idle/fixing/resolved/failed/low-extraction/disabled-arc) via local server + Playwright
before redeploying. Commit `e19a9d863`.

---

**SPEC: Provider Context Strategy (capability-gated stateful caching) — 2026-07-06, DESIGN done, build
pending.** [`docs/specs/2026-07-06-provider-context-strategy.md`](../specs/2026-07-06-provider-context-strategy.md).
Live-verified the crux: on the exact A4B model (LM Studio bug #1563 = no chat/completions prefix-cache),
**`/v1/responses` + `previous_response_id` caches 1711/1727 tok = 99%** where `/v1/chat/completions`
caches 0. So the fix for local context-explosion is the **stateful Responses API**, as a capability-gated
OPTION (not replacing the unified path). Architecture resolved with the user: 2-layer **ProviderContextStrategy**
(chat-service = context POLICY, provider-registry = TRANSPORT — extends the existing `use_anthropic_cache`
2-layer pattern); capability-keyed (not provider-name); DB-authoritative + `previous_response_id` as an
ephemeral degrade-safe hint; **Planner owns strategy + cache-aware budget**. Spec covers 12 edge-case
resolutions + **caching cost-monitoring/thrashing guardrail** (caching isn't free — Anthropic write=1.25×;
prove-by-effect) + **Inspector `caching` section** (extends fix-#5 `llm_call_count`) + **cache-aware
context-management** (server-side budget for stateful, compaction=cache-write-penalty, re-chain-at-boundary
= E5 resolves cost↔accuracy). Also found: shipped `applyAnthropicPromptCache` double-marks system (chat-service
already does) → reconcile to **tools-only** (Phase 1). Build phases: **P1** capability+monitoring+Inspector+§10
reconcile (no new transport, safe) · **P2** responsesAdapter+SDK+DB+stateful (behind `LLM_STATEFUL_CACHE`) ·
**P3** cache-aware Planner.

**▶ P1 BUILT & COMMITTED 2026-07-06** (4 risk-boundary commits): **P1.a** `594fbdf77` §10 tools-only
reconcile (`applyAnthropicPromptCache` marks tools-only; chat-service already marks system, forwarded
verbatim at adapters.go:1137 — freed a redundant Anthropic breakpoint). **P1.b+P1.c** `51dd5cccf`
capability model (`provider/capabilities.go` `CapabilitiesFor(kind)` → prompt_cache_control /
responses_api / auto_prefix_cache, surfaced on the credential-resolve response + chat-service
`ProviderCredentials.capabilities`) + cache-token split wired end-to-end (StreamChunk
`CacheCreationTokens`/`CacheReadTokens`, both Go streamers, openapi + SDK `UsageEvent` — provider-
normalized: creation=written, read=served-from-cache; InputTokens keeps the billing fold). **P1.d**
`e3847075c` `caching_monitor.py` (per-turn strategy label FROM capability, hit_rate, token-relative
cost_delta_ratio + write_premium via standard cache multipliers, net_negative; rolling `detect_thrashing`
§7 guardrail — only explicit-cache can thrash, ≥3-turn verdict so priming isn't flagged) → contextBudget
`caching` section (additive) + §11a gate row (85 items, 0 problems). Tests: caching_monitor 12,
token_budget 31, provider Go suite green, SDK stream green.
**✅ LIVE-SMOKE CLEARED 2026-07-06** (`D-CACHING-MONITOR-LIVE-SMOKE` closed — the "crash-loop" blocker
was STALE: both services rebuilt + came up `healthy` immediately). Evidence on the real stack:
(1) rebuilt provider-registry + chat-service images, both healthy. (2) `/internal/credentials/user_model/…`
returns `capabilities:{auto_prefix_cache:true, prompt_cache_control:false, responses_api:true}` for the
lm_studio Gemma model — P1.b wire proven. (3) real gateway turn (login→session→message→SSE) persisted a
contextBudget `caching` section: `strategy:stateless, auto_prefix:true, thrashing:null, uncached_tok:30925,
create/read 0` — P1.b→P1.d frame wiring proven cross-service. **Nonzero cache_read live proof is
transport-gated to P2:** LM Studio chat/completions reports NO `cached_tokens` at all (verified: dense
Qwen2.5-7B, KV-cached prefix, field absent) — the split only surfaces on `/v1/responses` (the P2 adapter,
= the 99% measurement). That path is unit-bound both sides now (Go streamer cached_tokens→CacheReadTokens,
SDK round-trip, monitor math) and will be the FIRST live-smoke of P2.

**▶ P2 BUILT & LIVE-VERIFIED 2026-07-06** (3 commits, `LLM_STATEFUL_CACHE` default-OFF so nothing changes
until flipped). Design doc: [`docs/specs/2026-07-06-provider-context-strategy-p2-transport.md`](../specs/2026-07-06-provider-context-strategy-p2-transport.md)
(resolved the "special route?" question → NO, shared `/internal/llm/stream` + capability-gated flag,
consistent with how the gateway already abstracts per-provider wire; + 7 adversarially-found edge cases,
esp. the §5a 4-part head-validity predicate + system→`instructions`). **P2.a** `d1f967ab2` transport:
`responses_streamer.go`/`responses_adapter.go` (`/v1/responses` SSE parse, tool reassembly, `ResponseID`
return, capability+flag gate); SDK `StreamRequest.stateful/previous_response_id` + `DoneEvent.response_id`.
**P2.b+P2.c** `f5c9a874d`: DB `chat_messages.response_id` chain head (+ partial index; head = latest
assistant row, so E7/E5 need no table); `stateful_chain.decide_chain` (§5a predicate); `_stream_with_tools`
delta-send + tool-loop id threading (E2) + E1 re-establish; system→`instructions` (Responses doesn't
inherit them → mid-session system change applies with no re-chain); `LLM_RESPONSE_CHAIN_NOT_FOUND`
classifier (400 body live-probed). Also fixed a **latent P1.d bug**: the no-tools terminal yield dropped
the summed cache split + response_id (a deeper-nested `_Usage` the P1.d replace_all missed).
**LIVE-SMOKE (LM Studio gemma-4-26b, flag on):** 2-turn chat → turn 2 `read_tok 30921, hit_rate 99.9%,
uncached 434` (the 99% cache_read P1 couldn't reach, now on the frame + persisted head); E2 tool-loop
chains within a turn (4 passes ~99% cached each); E1 corrupt-head → transparent re-establish, still
recalled the codeword. All isolated via a temp compose override (deleted); stack reverted to default-off.

**P2 EVAL DONE** (`10c33e523`, [`docs/eval/context-budget/stateful-vs-stateless-2026-07-06.md`](../eval/context-budget/stateful-vs-stateless-2026-07-06.md)):
12-turn A/B on local gemma-4-26b — stateful cut **Σ uncached tokens 355K→29.7K (−91.6%)** with
**IDENTICAL 4/4 fact-recall** (no quality loss). Each continue turn sends a ~27-tok delta vs a 29.5K
full re-send; ~100% cached after establish. The tool-schema-dominated base = the original explosion case.

**▶ P3 BUILT 2026-07-06** (`dbc5c0b31`) — the long-session (window-boundary) case the user flagged
("not facing the problem doesn't mean it won't happen; long context hits 1M-3M"). A **22-turn
growing-context probe** exercised the boundary:
- **Correct across a long session:** recall of a turn-1 fact passed after 21 filler turns; continues
  ~95% cached; no overflow. But the accumulated server-side chain GROWS (32K→73K) — stateful holds the
  full chain (unlike stateless's ~32K-compacted), so it MUST be bounded.
- **R1 real bug fixed:** rule-4's window guard read the persisted `input_tokens`, which SUMS the tool-loop
  (N-iteration turn ≈ N× the real context) → fired ~N× too early. Now reads the TRUE single-call
  `context_size` (tracked in _stream_with_tools, on all 3 terminal yields, persisted on the caching frame).
- **Observability:** `decide_chain` returns a `reason`; frame carries `chain_action` (continue /
  establish_first / reestablish_{stateless_prev,model_switch,compaction,window}) + `context_size`.
- **Bounded re-chain verified** (artificial `LLM_STATEFUL_MAX_CHAIN_TOKENS=45000` forced boundary at
  turn 9): re-establish RESETS ctx_size (sends compacted context), cycles 39K↔47K, no overflow/thrash.
- **KEY FINDING:** keep the threshold NEAR the window. A 45K cap (22% of 200K) forced compaction so early
  it summarized away the turn-1 fact (recall FAIL); the default `0.75×effective_limit` (~143K for 200K)
  held it. **The real long-session lever is the T6 fact-preserving summarizer's QUALITY at the boundary**
  — a separate, existing Context-Budget-Law concern, NOT the chain logic. Optional cap only for a provider
  loading a smaller n_ctx; set near that real window, never low.

**▶ THREE FIXES from the long-session investigation (user-flagged: reasoning loop + fact loss), 2026-07-06:**
- **Reasoning ⨯ caching NO tradeoff** (`84ada383d`) — user was right they coexist. `/v1/responses` IGNORES
  the FLAT `reasoning_effort` (/chat-completions field) → thinking-off was a silent no-op in stateful mode
  → an always-reasoning gemma-a4b could spiral. Web-researched + live-verified: the Responses API uses the
  NESTED `reasoning:{effort:…}` (none|minimal|low|medium|high). `mapResponsesEffort` maps off→none (DISABLES:
  reasoning_tokens 0 live) / high→on. Reasoning items are DROPPED between turns (not accumulated) — earlier
  "poisons the chain" worry was wrong.
- **Output ceiling** (same commit) — an uncapped /v1/responses turn + always-reasoning model looped to 60K+
  (observed). `buildResponsesBody` enforces a bounded `max_output_tokens` default (16384, tunable via
  `LLM_RESPONSES_MAX_OUTPUT_TOKENS`; caller max_tokens wins). A stateful turn can never run away.
- **T6 breadcrumb single-word coined names** (`2412716f5`) — the compaction fact-preservation breadcrumb
  dropped 7/9 single-word novel names (VORTHANE/Kael/Emberfall…) because `_PROPER` needs 2+ words. Fixed with
  `_proper_singletons` (ALL-CAPS + non-common-opener capitals, precise stoplist). Live: a 22-turn session
  through forced compaction cycles recalled a turn-1 secret ("VORTHANE") — was FAIL→now PASS. Benefits BOTH
  stateless + stateful compaction. This IS the "T6 quality" lever the P3 finding pointed at.

**▶ REVIEW-IMPL + STATEFUL TURNED ON BY DEFAULT 2026-07-06** (user: "review-impl, fix bugs, clear debts,
then turn on stateful — industry standard"). A 3-agent adversarial review found **7 real bugs**, all fixed:
- chat-service hot-path (`4fa6f7979`): **H1** stateful+frontend-tool suspend/resume dropped the tool
  result (resume rebuilt a delta missing the assistant tool_call + result) → fix: suspend persists the
  reconstructed FULL context, resume runs stateless (`is_resume` guard); **H2** in-loop compaction
  corrupted the delta indices (`working[_stateful_sent:]` went empty) → skip in-loop compaction when
  stateful (history is server-side; rule-4 bounds it); **M4** system/grounding dropped on tool-loop
  passes ≥1 → re-prepend system each stateful pass.
- transport (`9974ae54e`): **H** finish_reason hardcoded "stop" (truncation/tool-stops mislabeled) →
  capture response.status/incomplete_details + tool_calls; **H** assistant tool_calls not representable →
  E1 replay orphaned a function_call_output (400) → map assistant tool_calls → function_call items;
  **M** isChainNotFound only matched LM Studio → broadened for OpenAI prose.
- breadcrumb multilingual (`b45269843`, HIGH for this platform): Vietnamese names shredded at diacritics
  + protagonist dropped; Chinese ZERO extraction → Unicode `_WORD`, CJK sentence-split + numerals,
  `_QUOTED_CJK`; English adverb-openers glued onto names → dropped `_PROPER`, stoplist on ALL-CAPS +
  adverbs/scaffold. (Follow-up: non-quoted CJK NER via the multilingual NLP slice.)
- **STATEFUL ON BY DEFAULT** (`…flip…`): both `stateful_enabled()` (chat) + `StatefulCacheEnabled()`
  (gateway) default ON, read identically (flag-consistency), disable via `LLM_STATEFUL_CACHE=0`.
  **Live-verified default-on**: 2-turn smoke 99.94% cache with NO override + 22-turn recall PASS.
  Standards gate clean (transport in provider-registry; env vars are deploy ceilings; response_id
  session-owner-scoped; no model literals).

**NEXT:** return to [`docs/plans/2026-07-06-context-retrieval-improvements.md`](../plans/2026-07-06-context-retrieval-improvements.md)
(the retrieval-quality track — M1a passage→graph bridge shipped; remaining milestones). Deferred: the
no-tools `_stream_via_gateway` path is stateless-only (safe, self-heals via §5a rule-1); non-quoted CJK
name extraction in the breadcrumb (needs NER). Both low-priority.

---

**`D-PLANFORGE-GUI-AUDIT` — P0 crash FIXED, 4 real UX gaps found + scoped, 2026-07-06** (user: "planner
GUI thật sự là không thể sử dụng được... đứng ở vai trò người dùng và xem lại UI/UX" — go use it as
a real user, don't guess from code). Live-drove the Planner panel via Playwright as a real user
would (login → open book → Planner tab → paste markdown → Propose → Validate → Compile), on an
EXISTING book with prior runs, not a synthetic fixture.
**P0 FOUND + FIXED: Compile white-screens the entire Studio on SUCCESS.** `compile()` legitimately
returns `pipeline_job_id: null` when `run_pipeline` wasn't requested (the ONLY path this compact
form offers — there's no checkbox for it) — confirmed via the real `POST .../compile` response
body (200 OK, `pipeline_job_id: null`). `PlanRunView.tsx:121` called
`compileResult.pipeline_job_id.slice(0, 8)` unguarded, crashing with no error boundary → full blank
page. This is the SECOND instance of this exact bug class in this same component (a prior
`fidelity_score` null-crash already has a regression test with a comment noting "only the live
render caught it" — the lesson didn't generalize to the next null field). Fixed: guarded render +
`pipeline_job_id: string | null` in `types.ts` (was lying `: string`) + 2 new regression tests.
Frontend suite 22/22 plan-forge tests pass, tsc clean. Live-reverified on a vite :5199 dev server
against the real gateway: compile no longer crashes, other Planner functions unaffected.
**4 real, NOT-yet-fixed UX gaps found + confirmed live** (not guessed from reading code):
1. **Compile's `arc_id` is a bare text input with ZERO guidance** — no dropdown/autocomplete from
   the already-proposed spec's `arcs[]` list, no placeholder example, no default. A user has no
   way to know what to type (confirmed: I only unblocked it because I authored the test fixture and
   knew "arc_2" — a real user pasting their own doc has no such knowledge). Button is silently
   disabled with zero indication WHY (looks broken, not "waiting for input").
2. **No spec/document viewer** — after Propose, the UI shows only 3-5 unclickable "artifact" rows
   (kind + truncated UUID). No readable rendering of what got extracted (characters, arcs, events,
   variables) for the user to sanity-check the AI's understanding of their document.
3. **Source markdown doesn't resume when reopening an existing run** — the textarea is empty even
   though a `document` artifact with the original text exists server-side; a returning user can't
   tell if that's expected or broken.
4. **No error-recovery / fix-it affordance in the GUI** — the MCP-only tools `plan_interpret_feedback`
   / `plan_apply_revision` / `plan_handoff_autofix` exist specifically for "gaps found → fix them"
   but are wired to the chat agent only, not exposed as GUI buttons — a GUI-only user hitting a
   failed validation has no in-panel path forward besides re-pasting different markdown from scratch.
**Not fixed this pass** — these 4 are a real UX redesign (new dropdown backed by spec data, a spec
summary view, resume-on-load wiring, surfacing existing self-check/interpret/apply tools as GUI
affordances), correctly Large per the Task Size table, needs its own CLARIFY before BUILD. Full
audit trail (exact clicks, exact API responses, exact error text) is in this session's transcript;
not yet written to a standalone doc — do that first if picking this up next.

---

**Context-explosion fix — 4 of 5 SHIPPED 2026-07-06** (chat-service; user report: 20-turn / 8K-content
chat burned ~1.4M input tokens on Gemma-26B-A4B local, continuous compaction). **Investigation +
web-research** (`docs/eval/context-budget/context-explosion-investigation-2026-07-06.md`): NOT a
cross-turn history bug (history stays 14–1315 tok). Two causes: **(A) the book-scoped hot-seed
advertised ENTIRE glossary+story domains (~64 tools / 24,388 tok) on EVERY LLM call** —
`context_breakdown.mcp_tool_schemas` flat 24388 across all 20 turns, `enabled/activated_tools` empty →
it's the surface hot-seed, `_BOOK_SCOPED_HOT_DOMAINS={glossary,story}`; **(B) the tool-loop re-sends
it every iteration and `total_input` SUMS it** (`(N+1)×~30K`; seq-22/6-calls=148K). Industry-confirmed
("bloat tax" / RAG-MCP: bloated tools also crash tool-selection accuracy 43%→14%; Anthropic shipped
Tool Search to GA). Local-vs-Sonnet: LM Studio bug #1563 — **KV-cache reuse unsupported for A3B/A4B
(MoE)** → full recompute every call. **Fixes shipped:** #1 `tool_surface.budget_names_by_tokens` —
token-budget the hot-seed (24K→≤4K, read-tools-first, find_tools backstops); #2 `merge_activated_tools`
catalog-aware TOKEN cap (was count-64); #4 verified reasoning_content already stripped (loop append
omits it, not persisted); #5 `llm_call_count` threaded into the `contextBudget` frame so the summed
input is legible. **VERIFY:** 241 chat-service tests green (8 new budget tests); hot-seed drop
24,388→≤4,000 (prod-measured old + budget-bounded new). Live re-measure blocked — chat-service
container crash-looping (env). **Fix #3 `D-PROMPT-CACHING` — SHIPPED** (provider-registry, per-provider
after web-research): Anthropic needs EXPLICIT `cache_control` (added on last tool + system, default-on
kill-switch `LLM_PROMPT_CACHE`), while OpenAI/Gemini/DeepSeek/vLLM cache AUTOMATICALLY (nothing to
send — already on by default). `/review-impl` then corrected the local wiring: LM Studio has its OWN
adapter (`lmStudioAdapter`, distinct from the openai/vLLM one), so `cache_prompt` lives there
**default-ON** (kill-switch only) — the provider IDENTITY is the gate, no base_url guess, no vLLM on
that path to 400. Also fixed by the review: **usage under-count** (Anthropic reports input_tokens
EXCLUDING cached; now folds cache_creation/cache_read into InputTokens so spend/caps stay accurate),
a **cache-minimum size guard** (skip marking below ~4KB so no wasted breakpoint on tiny tool sets),
and **adapter-wiring tests** (httptest proves Stream actually applies cache_control / cache_prompt /
never-to-openai). `provider/prompt_cache.go` + 12 Go tests; full provider suite green. Note: the
reported A4B model still can't KV-reuse (bug #1563) — this benefits Anthropic/OpenAI/dense-local
configs. **Container note:** rebuild chat-service + provider-registry images to run the fixes live.

---

**M1a passage→graph anchor bridge SHIPPED 2026-07-06** (context-retrieval track,
`docs/plans/2026-07-06-context-retrieval-improvements.md`). **Root finding that reframed the work:**
the plan's "retrieval never traverses the graph" was FALSE — `select_l2_facts` already does 1-hop +
2-hop + widened-retry; the *real* gap is that graph expansion anchors ONLY on `intent.entities` (what
the classifier pulls from the message), so natural queries naming no entity get ZERO graph facts (M4:
6/6 such queries). M1a expands 1-hop from entities the retrieved PASSAGES surfaced that the message
didn't anchor, injecting the relations into the L2 facts block. New `facts.py`
`select_bridge_anchor_names` (pure, deterministic rank-order cap — reuses `extract_candidates`) +
`expand_facts_from_passages` (reuses `find_entities_by_name`/`find_relations_for_entity`); `full.py`
`_safe_expand_from_passages` wrapper (degrade-safe, mirrors `_safe_l2_facts`) wired after the widened
retry, before L1-dedup; kill-switch `context_passage_graph_expansion_enabled` (default ON, deploy
ceiling per SET). **Evidence (`docs/eval/context-budget/M4-graph-anchor-bridge-2026-07-06.md`):** 100%
coverage gap + 6/6 empty-anchor rescue (STRONG); answer-quality A/B **weak-but-positive, 0 regressions
across every fair run** (+14% overall on the most-rigorous config). **A `/review-impl` caught a HIGH
methodology flaw** — the first A/B starved the baseline of the passages production actually serves;
fixing it (passages in both arms + truncation-exclusion + single-model, since lm_studio thrashes on
2-model configs) DEFLATED the inflated "+28%/2×" headline but the bridge still never regressed. GO
justified by empty-anchor rescue + zero-regression safety, not a large lift. **VERIFY:** 20 M1a unit
tests green; full knowledge unit suite **3599 passed** (0 new failures — 4 pre-existing reds confirmed
via stash-baseline: `test_mode_full` 3× budget/summary + `test_internal_dispatch` 1×, all unrelated);
**live-smoke** on real Dracula (embed→passages→bridge): natural "who did he meet at the inn?" → 0→**7
real graph facts** (Count Dracula hosts/imprisoned_by Harker). **NEXT on this track:** M2 R3-residual
(point checklist-gate at `context-budget-law.md §11a`); a larger multilingual eval corpus (real
`D-EVAL-BOOK` — only Dracula is a wired test-account project today) for a robustness A/B; M3 pull-mode
pilot. **Container note:** infra-knowledge-service-1 has the new `facts.py` copied in for the smoke but
OLD `full.py`/`config.py` — rebuild the image for M1a to run in live grounding.

---

**`sg_value_shift_per_scene` ADOPTED as PlanForge's 8th rule, ADVISORY tier, 2026-07-06** (user
picked "Adopt Story Grid rule vào validator thật" — closing out
`docs/specs/2026-07-05-narrative-forge/00_METHODOLOGY.md` §5 decision 3). `run_rules()` now
returns this rule tagged `"tier": "advisory"`; every pre-existing rule defaults to `tier="hard"`
(zero changes needed to them). **The real problem this surfaced**: `plan_forge_service.py`'s
`validate()` and `compile()` both treated `run_rules()`'s WHOLE output as hard-blocking
(`compile()` literally raises `ValueError` on any failure) — naively appending the new rule would
have hard-blocked the golden fixture itself (it genuinely fails this rule), the opposite of the
"advisory, never hard-block" conclusion already reached twice in the eval doc. Fixed via new
`plan_forge_service._hard_rules_pass(rules_out)` (filters to `tier=="hard"`) replacing both raw
`all(r["pass"]...)` call sites. `validate_golden`'s S1-S8 criteria and `refine.py`'s
`linter_no_regress` (a fixed `CORE_RULES` allowlist) both needed ZERO changes — they already only
reference specific rule names, so the new rule is simply never added to either. **Live-verified
end-to-end against a real LLM-produced spec** (not just unit tests): rule correctly failed on 4
events, tagged advisory, and `_hard_rules_pass` correctly returned `True` (no incorrect block).
4 new tests, full suite **1647 passed/150 skipped** (was 1643, 0 regressions).
`docs/specs/.../00_METHODOLOGY.md` §5 decision 3 is now **CLOSED**. Full detail:
[`docs/eval/plan-forge-story-grid-poc-2026-07-06.md`](../eval/plan-forge-story-grid-poc-2026-07-06.md)
("Third addendum" section).

---

**`D-PLANFORGE-STORY-GRID-POC` DONE 2026-07-06** (user: "POC Story Grid", per
`docs/specs/2026-07-05-narrative-forge/00_METHODOLOGY.md` decision #3 — Story Grid is NOT a
swap-in for PlanForge's 7-rule validator, needs its OWN POC scored side-by-side against the same
fixtures first). New `services/composition-service/app/engine/plan_forge/validate_story_grid.py`
(deliberately NOT wired into `validate.run_rules`/`validate_golden`) operationalizes 2 mechanically
-checkable Story Grid principles against the CURRENT spec schema, no new fields: `sg_value_shift_
per_scene` (every event must carry ≥1 var_delta — Story Grid's "a scene must turn a value") and
`sg_negative_turn_exists` (the arc's deltas must include a cost, not just gains). Run against the
SAME `story-plan-v1.md` fixture the 7 core rules already pass: **all 7 core rules still PASS;
`sg_value_shift_per_scene` FAILS, finding a real gap none of the 7 rules check** — `arc_2_event_3`
and `arc_2_event_7` parse with zero var_deltas. Five Commandments beat-sequencing and genre
obligatory-scenes were explicitly NOT operationalized (need a `beat_type` field the spec doesn't
have — out of scope, named not silently dropped). **Found + fixed a real pre-existing bug while
building this** (not a Story Grid defect): `propose.py::_parse_events_in_block` let the LAST event
in an arc block bleed into the arc's trailing closing-summary text (no next `### ` to stop at),
spuriously matching `arc_2_event_7`'s var_delta regex against the summary's "THR: rò rỉ đầu tiên"
line. Fixed via truncating each event body at the first `\n---` marker. 8 new unit tests
(`test_plan_forge_story_grid.py`) + full `plan_forge` suite re-run clean (40/40); full composition
suite **1636 passed/150 skipped** (was 1628, +8, 0 regressions). Full report:
[`docs/eval/plan-forge-story-grid-poc-2026-07-06.md`](../eval/plan-forge-story-grid-poc-2026-07-06.md).
**Not adopted into the real gate** — adoption is a follow-up decision for whoever next revisits
PlanForge's validator, per the locked decision.
**Addendum same day (user: "do more evaluate before we consider to update current validator"):**
ran the REAL production async LLM propose path (`propose_spec_llm_async`/`ProviderPlanForgeLLM`,
NOT the regex-only fixture-quality `propose_spec`) against the real fixture — real
provider-registry route, real BYOK local model (Gemma-4 26B-A4B QAT 200K, $0), zero mocking.
**`sg_value_shift_per_scene`'s signal splits into robust vs noisy:** `arc_2_event_3`/`_7` have NO
var_delta under BOTH the regex parser AND the LLM (a stable, cross-method-validated gap);
`arc_2_event_1`/`_4` only fail under ONE method each (generation-method noise, not a real gap) —
revised recommendation: trust only the cross-method intersection, and if ever adopted this MUST
be `quarantine`/`advisory` tier, never `hard-block`, same lesson as the canon-check judge-eval
(one run overstates signal). **Bigger discovery: a real false-positive in an EXISTING core rule**
(`pa_not_realm`, not Story Grid) — it fires on the LLM spec because its `reason`-text keyword
check ("cảnh giới") can't distinguish "PA rises because of a realm-breakthrough EXPERIENCE"
(legitimate, this story's own design) from "PA is coupled to realm" (the actually-forbidden
case); every prior test of `pa_not_realm` only ever used the regex spec or a synthetic patch —
this is the first time it was checked against real LLM output. **Tracked, not fixed
(`D-PLANFORGE-PA-REALM-FALSE-POSITIVE`, see Deferred Items)** — different rule, needs a
considered fix not a same-session regex tweak. 1 new regression test
(`test_sg_value_shift_blind_to_untracked_narrative_value`) encodes the "rule can't see
untracked-variable value shifts" caveat. Full addendum:
[`docs/eval/plan-forge-story-grid-poc-2026-07-06.md`](../eval/plan-forge-story-grid-poc-2026-07-06.md)
(same file, "Addendum" section).
**`D-PLANFORGE-PA-REALM-FALSE-POSITIVE` FIXED same day** (user: "đi test thật rồi đánh giá để
fix bug hoặc improve" — go test for real, evaluate, then fix or improve). Built a committed,
reusable harness (`services/composition-service/scripts/live_validate_planforge_llm.py`) that
runs the REAL async LLM propose path N times against the real fixture and scores all 8 core
rules each run. **Round 1 (5 runs) found a SECOND real bug immediately**: the harness crashed on
run 1 (`AttributeError: 'list' object has no attribute 'lower'`) because the model sometimes
emits `synopsis` as a bullet array, not a string — fixed at the actual normalization boundary
(`propose_llm.py::normalize_spec`, new `_normalize_synopsis` helper, same pattern as the existing
`normalize_planner_notes`). **Round 2 (5 runs) confirmed `pa_not_realm` fails 5/5 — a 100%
reproduction rate**: Event 5 (the story's own "first realm entry" scene) always produces a
PA-delta reason naming the realm breakthrough itself, and NONE of the 5 runs ever produced
proportional/scaling language (the actually-forbidden case). **Fixed** by replacing the bare
`"cảnh giới" in reason` substring check with a pattern matching only proportional-coupling
phrasing (`theo|tỷ lệ|dựa trên/vào|gắn với|mỗi` + `cảnh giới`) — reusing the exact phrase the
source doc itself uses for the forbidden case. The pre-existing `coupled_to_realm: true` golden
negative test is untouched (that boolean check is the primary signal; the keyword match is now a
narrower defense-in-depth layer). **Round 3 (5 fresh runs, post-fix): all 8 core rules 5/5 PASS**,
including 3 newly-observed PA phrasings not seen in round 2 — the fix generalizes, not just
pattern-matches one anecdote. 3 new regression tests
(`test_normalize_spec_coerces_list_synopsis_to_string`,
`test_pa_not_realm_tolerates_realm_breakthrough_as_pa_trigger`,
`test_pa_not_realm_still_catches_proportional_coupling_language`). Full composition suite
**1643 passed/150 skipped** (was 1640, 0 regressions). 3 rounds / 15 real LLM propose calls
total, $0 local model, zero mocking. `D-PLANFORGE-PA-REALM-FALSE-POSITIVE` **CLOSED**. Full
detail: `docs/eval/plan-forge-story-grid-poc-2026-07-06.md` ("Second addendum" section).

---

**`D-KG-EXTRACTION-CANON-WIRE` + `D-CANON-CHECK-SDK-UNIFY` SHIPPED 2026-07-06 (both follow-ups
from the 2026-07-05 POC + 2026-07-06 judge-eval, user: "làm D-KG-EXTRACTION-CANON-WIRE vaf
D-CANON-CHECK-SDK-UNIFY"; plan [`docs/plans/2026-07-06-canon-check-wire-and-unify.md`](../plans/2026-07-06-canon-check-wire-and-unify.md)).**
**Part A — WIRE.** Researched the write path (`pass2_orchestrator.py::_run_pipeline`, right
before `write_pass2_extraction`) and REJECTED reusing `kg_triage_items` (structurally similar
"park for review" but semantically wrong — its own docstring says items are parked
**NOT written to Neo4j**, a withhold-until-resolved lifecycle for SCHEMA-mismatch failures;
reusing it for a narrative-continuity flag whose judge is only 85.7%-precise would silently drop
~1-in-7 legitimate revivals/dialogue turns pending a review nobody may perform). **Chosen
mechanism: `job_logs`** (already wired to the Studio's JobLogsPanel) — the write proceeds
UNCONDITIONALLY; a confirmed contradiction is just logged (`event: pass2_canon_flag`) for human
review. New `list_gone_entities()` in `entity_status.py` (no prior "all currently-gone entities
for a project" query existed — `status_at_order`/`statuses_detail_at_order` both need a
caller-supplied id list). New `_maybe_run_canon_check_gate` in `pass2_orchestrator.py`, called
before Step 5, reusing the SAME model already resolved for the extraction job (no new setting).
6 new Neo4j-integration tests (`list_gone_entities`) + 4 new mocked-gate tests (noop-when-no-gone,
logs-on-confirmed-write-still-proceeds, skips-log-when-not-confirmed, degrades-safely-on-exception)
— all green. **Live-smoked end-to-end through the REAL pipeline** (real Neo4j, real LLM via
`extract_pass2_chapter`, not a mocked call) — confirmed the `pass2_canon_flag` job_logs row fires
correctly when the judge confirms a contradiction.
**Part B — SDK-UNIFY.** Diffed both services' `canon_check.py` files function-by-function:
`_find_span`/`_parse_verdicts`/the judge request shape/the verdict-apply loop/the symbolic-filter
body/the compose control-flow were byte-identical or near-identical; prompt wording, the
per-service extra candidate field (`glossary_entity_id` vs `gone_from_order`), and composition's
entire `reflect_revise` check→revise loop are genuinely divergent and stayed per-service. New
package **`sdks/python/loreweave_canon_check`** (flat submodule, added to the shared root
`pyproject.toml` include list per convention) hoists `find_span`, `parse_judge_verdicts`,
`extract_judge_text`, `build_judge_request`, `apply_verdicts`, `gone_entities_referenced`,
`CanonCandidateBase`. Both services' `canon_check.py` are now thin wrappers. **Fixed a real gap
in the same pass:** knowledge's judge caught bare `Exception` + manually indexed
`job.result["messages"][0]["content"]`; now uses the same `LLMError` + `extract_judge_text`
precision composition's already had. 33 new SDK unit tests; composition full suite re-run
**1628 passed/150 skipped, 0 regressions**; knowledge full suite **3590 passed** (same 4
pre-existing unrelated failures as before, confirmed via earlier `git stash`).
**A genuine parsing bug found DURING regression verification (pre-existing in BOTH services'
ORIGINAL code, not introduced by the refactor) — fixed as part of the unification:** the verdict
parser used a naive `text.find("{")..text.rfind("}")` span; captured live, this $0 local model
sometimes emits a first (wrong) JSON verdict, a `*(Self-correction: ...)*` prose aside, then a
corrected second JSON block — the naive span swallowed the prose between them and silently failed
to parse, discarding the model's own corrected answer as a false "inconclusive". Fixed via a
string-aware brace-balanced scanner that takes the LAST parseable `{"verdicts":...}` block
(honoring self-correction as final intent); 4 new regression tests.
**Sobering re-measurement, honestly documented (addendum in [`docs/eval/canon-check-judge-2026-07-06.md`](../eval/canon-check-judge-2026-07-06.md)):**
even with the parser fixed, 3 repeated eval runs later the same session gave a STABLE 68.75%
accuracy / 33% recall (down from the original day's 93.75%/100%) — root-caused as genuine
model-reasoning/output inconsistency (the judge's OWN "why" text correctly identifies the
contradiction, but its `violated` boolean is sometimes wrong anyway), NOT a code regression
(verified: the exact request dict is byte-identical pre/post-refactor; mocked-LLM unit tests
pass identically). **Conclusion: this $0 quantized local model's judge reliability is noisier
session-to-session than any single eval run shows — report a RANGE from repeated runs, not a
point estimate, next time judge-model choice is revisited.** This reinforces (doesn't undercut)
the `quarantine`-not-hard-block wiring decision. Files: `services/knowledge-service/app/db/
neo4j_repos/entity_status.py`, `app/extraction/{canon_check.py,pass2_orchestrator.py}`,
`sdks/python/loreweave_canon_check/` (new), `sdks/python/pyproject.toml`, `services/
composition-service/app/engine/canon_check.py`, plus test files across all three.

**CONTEXT BUDGET LAW — ALL REMAINING PARKED ITEMS CLEARED 2026-07-06 (user: "i don't want a lot of debts, clear them").** Went through every remaining parked item and either BUILT it or made a FIRM recorded decision (a decision is not a debt). Updated disposition table in [`2026-07-05-context-budget-closeout.md`](../specs/2026-07-05-context-budget-closeout.md). **BUILT:** ① **Inspector D7 GUI-trace** — new `tool_result_content_capped_ex` returns the over-cap token count; `_stream_with_tools` gained a `trace` param and records a `T6/results/d7_overflow:<tool>` span so the Inspector shows WHY a tool result was withheld (was log-only). *(Caught a `_trace` vs `trace` scoping slip via the story04 suite — fixed; the call site is in `_emit_chat_turn` which takes `trace` as a param, not the `stream_response`-local `_trace`.)* ② **D-T1-SMALLRETURN-ENFORCE** — cleared via the **D7 runtime cap** as the real backstop (a heavy field on any small-return tool is now withheld+logged at runtime, no longer silent) + a closed-set pin `test_small_return_claims.py` (6 claims; a new `@small_return` claim turns it red → review). **FIRM DECISIONS (closed, not deferred):** ③ **T3 `Compiler` class** = won't-fix (a wrapper no caller needs is make-work; the render+compact mechanism + `Planner` seam are open+consumed by chat+voice). ④ **D7 reasoning-budget half** = won't-fix (reasoning disabled platform-wide; untestable against real behavior; trigger recorded: reasoning re-enabled + bloat). ⑤ **D13b resume-monotonicity** = satisfied-by-construction (auto-detect decides once; resume reuses frozen assembly). ⑥ **history-pressure at gate** + **auto-detect trace-span** = won't-add (compaction already handles long-chat pressure; the decision log covers observability; accumulator is created after the gate). **VERIFY:** full chat suite **1029 green**; new wire tests 65 (+capped_ex); knowledge pin 1; provider-gate clean. Files: `services/chat-service/app/services/{tool_result_wire.py,stream_service.py}`, `tests/test_tool_result_wire.py`, `services/knowledge-service/tests/unit/test_small_return_claims.py` (new), `docs/specs/{2026-07-05-context-budget-closeout.md,2026-07-06-long-work-auto-detect.md}`. **⇒ The Context Budget Law defer tail is now EMPTY — every item is shipped, built, or a firm recorded decision.**

**LONG-WORK CONTEXT AUTO-DETECT — CORE SHIPPED 2026-07-06 (`D-LONG-WORK-CONTEXT-MODE` UNPARKED; spec [`docs/specs/2026-07-06-long-work-auto-detect.md`](../specs/2026-07-06-long-work-auto-detect.md)).** User challenged the earlier "park" ("auto-detect is essential") — and was right: my "dead code" reasoning was circular (the "tiers inert" verdict came from THIN-book evals, the exact case auto-detect doesn't target; large books were never measured). **`context.mode="auto"` was a no-op passthrough** (`_ctx_tiers_allowed = context_mode != "off"`, then AND-ed with default-OFF env flags). Now it actually detects: new pure `app/services/context_autodetect.py::resolve_context_pressure` — biased-to-include, enables the T5/T4 tiers when EITHER (a) history ≥ 0.6×window OR (b) **glossary/known-entity size ≥ 300** (the cheap already-cached big-lore-book proxy; the gate runs pre-history-assembly so the glossary signal is the primary one, long-chat pressure stays with adaptive compaction). **Also fixed a SET-standard smell:** `t5_intent_gate_enabled`/`story_state_block_enabled` flipped from default-OFF *enablement* → **default-TRUE deploy KILL-SWITCH ceilings** (`effective = AND(deploy_ceiling, auto/user enablement)`) — env is a ceiling, not a per-user knob. **Full auto-enable per user's explicit call** (accepts turning eval-unproven tiers on in prod; threshold/ceiling are the tuning knobs). **VERIFY:** `test_context_autodetect` 9 (truth table) + `TestContextMode` 4 e2e wiring (off-bypasses / on-forces / auto-small-stays-off / **auto-large-ENABLES** through real `stream_response`); **full chat suite 1028 green** (flip broke nothing — auto keeps tiers off on the small/mock books every other test uses); provider-gate clean. **Live-calibrated on REAL data (= the R6 long-book re-measure, unblocked by the summaries fix): 万古神帝 (4233 ch) = 308 known-entities → trips → tiers ON; Dracula (6 ch) = 100 → stays off; unextracted = 0 → off** — the threshold discriminates the large-lore book exactly. **D13b resume-monotonicity = satisfied by construction** (decision computed ONCE in the main path; resume reuses the frozen assembly, never re-gates). **Follow-on (non-blocking):** surface the `_auto` decision as an Inspector trace field (a decision LOG ships now); optional history-pressure signal at the gate. Files: `services/chat-service/app/services/{context_autodetect.py (new),stream_service.py}`, `app/config.py`, `tests/{test_context_autodetect.py (new),test_stream_service.py,test_stream_service_story_state.py}`, `docs/specs/2026-07-06-long-work-auto-detect.md` (new) + closeout-spec row 7 unparked.

**`D-KG-EXTRACTION-CANON-GATE` JUDGE ACCURACY EVAL 2026-07-06 (follow-up to the 2026-07-05 POC below; report [`docs/eval/canon-check-judge-2026-07-06.md`](../eval/canon-check-judge-2026-07-06.md)).** The POC left judge accuracy on hard cases as an anecdotal open question ("inconsistent depending on thinking/token settings"). Built a scored fixture set (`services/knowledge-service/eval/canon_check_fixtures.py`, 16 scenarios — 10 expected NOT-contradiction incl. flashback/dream/metaphor/counterfactual/quoted-document/**narrated-explained-revival**/name-collision/twin/sarcasm, 6 expected IS-contradiction incl. the POC's original hard unexplained-revival case) + a CLI eval harness (`eval/run_canon_check_eval.py`, pure scoring logic unit-tested in `tests/unit/test_canon_check_eval_metrics.py`, 11 green) that runs `check_extraction_canon` per fixture per model and reports accuracy/precision/recall, never silently averaging an inconclusive (`confirmed=None`) verdict into the score. **Ran 2 models ($0 local via LM Studio/provider-registry, no paid gpt-4o spend — judged unnecessary, see below):** Gemma-4 26B QAT scored **93.75% accuracy / 100% recall / 1 false-positive** (name-collision "Alice Chen"); the "stronger" Qwen3 35B scored **worse — 87.5% / 100% recall / 2 false-positives** (same name-collision miss PLUS flagging a narrated/explained resurrection as a contradiction). **Non-obvious finding: bigger local model ≠ better judge here** — both models reason correctly about physical-presence ("she's acting, so she's alive") but neither reliably reasons about identity-distinctness (surnamed different person) or narrative-framing (an in-text narrated revival is new canon, not an error); this reads as a pragmatic-inference class limitation, not a raw-capacity gap. **Both models have PERFECT recall — never miss a real continuity error** (the safer failure mode for a gate). **Decision: recommend wiring with Gemma-4 26B QAT as a `quarantine+promote` gate (per the Narrative Forge Universal Gate Taxonomy), NOT a hard-block** — 85.7% precision is a defensible one-extra-review-per-16-mentions cost for quarantine, not for silent hard-blocking. Live infra hit one transient issue mid-run (a container restart between the two eval attempts wiped the docker-cp'd harness files from the container's writable layer — re-copied, not a code bug) and one real learning: the FIRST Qwen3 attempt failed outright with `Failed to load model: Operation canceled` because the user's local VRAM was full from other work — correctly paused mid-task on the user's explicit "stop the job, vram is full" rather than reporting a fabricated low-accuracy result, resumed cleanly once VRAM freed. **NOT done this session (tracked):** `D-KG-EXTRACTION-CANON-WIRE` (actually wiring into `pass2_orchestrator.py` Step 5 — needs its own PLAN, touches the extraction write path) and the still-carried `D-CANON-CHECK-SDK-UNIFY`. Files: `services/knowledge-service/eval/{canon_check_fixtures.py,run_canon_check_eval.py}` (new), `tests/unit/test_canon_check_eval_metrics.py` (new, 11 tests), `docs/eval/canon-check-judge-2026-07-06.md` (new).

**CONTEXT BUDGET LAW — OPEN-ITEMS CLOSEOUT 2026-07-05 (spec [`docs/specs/2026-07-05-context-budget-closeout.md`](../specs/2026-07-05-context-budget-closeout.md); "make spec/plan + clear all genuinely-open", autonomous run).** Re-verified all 7 remaining open items against CODE (the [[debt-batches-list-is-stale-verify-first]] rule) and disposed of each: 2 fixed, 1 partial-fix, 4 conscious records. **① D-KG-SUMMARIES-TARGET-NOOP — FIXED (root-caused).** Why chapter summaries never generated (`summary_chapters`/`summary_books` stay 0 → "where is X at chapter N" recall punts): the P3 summary pipeline (producer `pass2_orchestrator.enqueue_chapter_and_maybe_book_summaries` → `extraction.summarize` stream → worker-ai `SummaryConsumer` → `summary_processor`) is fully wired and `summaries` IS in DEFAULT_TARGETS — but **worker-ai `runner.py:2075` gates the whole P3 enqueue on `hierarchy.part is not None`, and book-service returns `part=null` + `chapter_path=null` for any UNDECOMPOSED chapter** (NULL `part_id`/`structural_path` — the common case for imported novels incl. the Dracula POC). So those books silently produce zero summaries. **Fix: synthesize a deterministic single implicit part** (`book/part-1`, `part_id=uuidv5(book_id,"book/part-1")`) + a synthesized `chapter_path` at the book-service hierarchy endpoint ([`hierarchy.go`](../../services/book-service/internal/api/hierarchy.go) new pure `resolveHierarchyPart`), so the existing Book→Part→Chapter pipeline runs unchanged for legacy/flat books; MERGE-on-path is idempotent+deterministic so a later real decomposition reuses the node (no graph drift). **Plus de-silenced the skip** (warn+diagnosis) at worker-ai `runner.py` and knowledge `internal_extraction.py` — was a totally silent no-op ([[silent-success-is-a-bug-not-environment]]). **② D7 cap — de-silenced:** `tool_result_wire._overflow_error` now WARNs on every trip (tool+tokens+cap), so a withheld tool result is diagnosable. **Records (gate-verified, not laziness):** T3 `Compiler` class = WON'T-FINISH (mechanism complete + 2 consumers; the class wrapper adds no behavior); **D-T1-SMALLRETURN-ENFORCE** = defer→A5 (real fix is a runtime byte-histogram executing ~13 tools/3 services; static proxies are theater); **Inspector D7 GUI-trace** = defer (accumulator not in the tool-loop scope; low value, now logged); **D13b resume-monotonicity** + **D7 reasoning-budget half** = defer w/ trigger (inert while gated tiers OFF / reasoning disabled repo-wide); **D-LONG-WORK-CONTEXT-MODE** = partial-resolved by Chat&AI M4 (per-session mode shipped) — note `mode="auto"` currently == "follow deploy default" (no real auto-detect; building it now = dead code since tiers are eval-inert behind a default-OFF ceiling). **VERIFY:** book-service 4 (new `hierarchy_test.go`) + knowledge `test_internal_extraction` 53 (+de-silence test) + chat `test_tool_result_wire` 17/`test_stream_tools` 47 (+2 de-silence tests) + worker-ai 106 (1 pre-existing unrelated fail, confirmed via git-stash); provider-gate clean. **`/review-impl` done** (commit `320122f5d`): no HIGH/MED — the two scary risks are schema-cleared (`chapter_index ge=1` holds since legacy import is `sortOrder=maxSort+1`; `summary_parts` has NO FK to `parts` + part/book summaries load children by `book_id`, so the synthetic part_id can't break storage). 3 LOW/COSMETIC accept-and-document items (worker de-silence untested, mixed-book edge, phantom `:Part` in graph views). **`D-KG-SUMMARIES-LIVE-SMOKE` — ✅ PASSED (full local stack).** Verified vs live data: EVERY dev-DB book is 100% NULL part_id/structural_path (Dracula 6ch, 万古神帝 4233ch); `summary_chapters` had **1 row total platform-wide** — the part-gate starved summaries universally, not just the POC. After rebuild: hierarchy endpoint returns the synthesized part; a real Dracula-ch.1 extraction enqueued all 3 levels (incl. `level=part node=db749273…` the synthetic part) and `summary_chapters/parts/books` went **0→1/1/1 with real coherent text**; Neo4j shows the synthetic `:Part`→`:Chapter`. **The smoke EXPOSED a second latent bug — FIXED:** book-service `getInternalChapterDraftText` did `SELECT cd.body::text::bytea`, which errors (`invalid input syntax for type bytea`) on any draft JSON containing a backslash escape (`\n`,`\"`) → 500 → the summary_processor's legacy-chapter text fallback returned empty → chapter summary deferred forever. Latent because summaries never ran before the part-gate fix. Fixed to `cd.body::text` + a DB-gated regression test (`scenes_draft_text_db_test.go`, passes vs real PG). **This is the live-smoke's value — the part-gate fix was necessary but NOT sufficient.** **VERIFY:** book-service 4 unit (`hierarchy_test.go`) + 1 DB (`scenes_draft_text_db_test.go`, real PG) + full api suite green; knowledge `test_internal_extraction` 53; chat `test_tool_result_wire` 17/`test_stream_tools` 47; worker-ai 106 (1 pre-existing unrelated); provider-gate clean. Files: `services/book-service/internal/api/{hierarchy.go,hierarchy_test.go,scenes.go,scenes_draft_text_db_test.go}`, `services/worker-ai/app/runner.py`, `services/knowledge-service/app/routers/internal_extraction.py` (+test), `services/chat-service/app/services/tool_result_wire.py` (+test), `docs/specs/2026-07-05-context-budget-closeout.md`.

**`D-KG-EXTRACTION-CANON-GATE` POC 2026-07-05 (Narrative Forge item 2, gate-reconciliation for Knowledge extraction).** Picked up the methodology's own Finding A (Knowledge extraction is the `none`-strictness worst offender). **First checked real KG data for 2 candidate signals and rejected both before writing code:** `confidence` clusters 0.9-1.0 with only 7 distinct values platform-wide (no variance); `evidence_count` flags 94.5% of Events/100% of Facts as "low" — meaningless for fiction, where a load-bearing plot fact is often stated exactly once (mention-count ≠ truth, unlike multi-source real-world fact-checking). **Pivoted to borrowing the ONE gate mechanism the methodology audit found is proven platform-wide:** composition-service's `app/engine/canon_check.py` (symbolic pre-filter → LLM-judge → advisory, never blocks). Built the knowledge-service-side equivalent, `app/extraction/canon_check.py` — checks CHAPTER TEXT BEING EXTRACTED against the KG's own `gone`-status (via existing `entity_status.py`'s `status_at_order`) instead of composition's direction (draft vs existing KG). 16 new unit tests (fake-judge, mirrors `test_canon_check.py`'s structure) — all green; full knowledge-service suite re-run, 3525 passed (4 pre-existing, unrelated failures in `test_mode_full.py`/`test_internal_dispatch.py` confirmed via `git stash` to predate this work — different track, not touched). **Live-smoke against REAL infra** (not mocks): seeded a synthetic `gone`-status entity directly into the real Neo4j, ran the real symbolic filter + a real judge call through provider-registry → LM Studio ($0 Gemma-4 26B). **Found + fixed a real bug live:** copied `response_format: json_object` from the wrong sibling pattern (`coref_detect.py`) instead of `canon_check.py`'s own `type: text` — LM Studio rejects `json_object`, fixed. **Honest result:** symbolic pre-filter is 100% reliable (proven in every run + 16 unit tests); the judge integration (submit→parse→degrade) is proven correct end-to-end, including degrading safely under a REAL Redis event-wait timeout mid-smoke (didn't crash, didn't block, fell back to symbolic-only exactly as designed — CC4 principle validated under a genuine fault, not just a mocked one); the EASY case (flashback → not a contradiction) is judged correctly every time. The HARD case (an unexplained cross-chapter revival → should be flagged) is judged INCONSISTENTLY by the $0 local model depending on `thinking`/token-budget settings — an expected model-tier limitation (same class as `D-AGENT-NEEDLE-CONFAB`), not a mechanism defect. **Conclusion: the gate MECHANISM works and is production-shaped; judge ACCURACY on nuanced cross-chapter reasoning needs a stronger model or a real calibration eval before this is trustworthy — tracked as the next step, not solved by this POC.** Deliberately NOT wired into the live extraction pipeline yet (POC scope was "prove the mechanism," per user's explicit choice) — the wiring point is `pass2_orchestrator.py`'s write step (Step 5), before `write_pass2_extraction` commits to Neo4j. **Tracked follow-up (not done, gate #2 — structural):** `D-CANON-CHECK-SDK-UNIFY` — this module is a deliberate near-duplicate of composition's `canon_check.py`; unifying into `sdks/python/` is appropriate only once wiring + a judge-accuracy fix validate the design, not before (premature unification from one untested use). **Also surfaced (unrelated infra, fixed in passing):** the whole local stack had gone down (postgres/knowledge-service/provider-registry all `Exited`) between sessions — same `infra-stray-postgres-network-drift` pattern as before; brought back up via `docker compose up -d`, no data loss. Files: `services/knowledge-service/app/extraction/canon_check.py` (new), `tests/unit/test_canon_check.py` (new, 16 tests).

**"NARRATIVE FORGE" METHODOLOGY — CLARIFY DONE, v0.2 LOCKED 2026-07-05** (spec [`docs/specs/2026-07-05-narrative-forge/00_METHODOLOGY.md`](../specs/2026-07-05-narrative-forge/00_METHODOLOGY.md)). User's framing after the Cursor-for-novels register closed: software engineering has a shared SDLC vocabulary every tool aligns to; novel writing never has, so LoreWeave built 8 substantial subsystems (PlanForge, Agent Mode, Composition drafting, Knowledge, Glossary/Wiki, Enrichment, Translation, Quality) that were never unified into one named lifecycle. Ran 7 parallel Explore-agent audits (one per subsystem, +PlanForge done directly) against CURRENT code, not docs (several docs proved stale — e.g. PlanForge's own blueprint checklist marks the Studio dock/MCP tools `[ ]` incomplete when they demonstrably work, live-tested this same session). **Headline findings:** (A) **6+ different "when does AI content become canon" gate philosophies** across the 8 areas — never-gated (Knowledge, writes straight to Neo4j), mandatory-quarantine (Enrichment's "H0" invariant), manual-status-flip (Glossary), auto-unless-flagged (Translation), spend-gated-not-canon-gated (Composition generate), hard-block (Composition publish — the ONE universal hard gate found). (B) Composition's own separate "Planning pipeline · Stage 0-5" (`cast_plan→...→plan_heal`) is NOT a duplicate of PlanForge — verified it operates one granularity level down (scene-decompose, consuming PlanForge's already-produced `PlanningPackage`) — a legitimate unnamed two-tier split. (C) The Studio "Quality" activity tab is a complete stub ("Built next.") — real critic/promise-audit/canon-check functionality is stranded on the legacy `CompositionPanel.tsx` workspace, same fragmentation shape as the closed Cursor-for-novels gaps. (D) `07S_studio_agent_standard.md`'s existing "Start/During/End/Exec × Supervised/Autonomous" gate-position table is the natural seed for a universal taxonomy. Web-researched human literary methodologies (Snowflake Method, Save the Cat, Story Grid, Truby's 22 Steps, Dan Harmon's Story Circle) and classified them as either *process* (informs the phase backbone) or *structure* (pluggable rule-sets for the Verify micro-step) — noted PlanForge's own 7-rule validator is unknowingly reinventing a slice of Story Grid's Five Commandments. **PO locked 5 decisions:** (1) macro-stage names de-SDLC'd to `Concept→Forge→Cast→Draft⇄Ground⇄Enrich→Hone→Localize→Publish` (Forge/Cast lean on names already in the repo); (2) the gate-philosophy inconsistency is a real defect to fix (direction only — Knowledge extraction is the worst offender), each subsystem's actual change is its own future scoped PLAN; (3) PlanForge's validator is NOT swapped for Story Grid/etc. — any framework addition needs its own POC scored against the same fixtures first; (4) Quality's Studio rebuild and (5) the tech-tree/graph visualization are BOTH spun off as separate future tracks, each needing its own draft-HTML+spec, explicitly sequenced after the methodology is in use (visualization is deliberately LAST, per the user's own "top-down from methodology" principle). Also resolved: React Flow (`@xyflow/react`, MIT) + dagre (MIT) confirmed AGPL-safe for whenever the visualization track starts; avoid elkjs (EPL-2.0, disputed GPL-compat). **NEXT:** nothing committed yet on picking up item 2 (gate reconciliation) or item 3 (rule-framework POC) — user's call whenever revisited.

**CHAT & AI SETTINGS UNIFY — M1a–M5 SHIPPED + ALL DEFERS CLEARED 2026-07-05 (spec [`docs/specs/2026-07-05-chat-ai-settings.md`](../specs/2026-07-05-chat-ai-settings.md); autonomous run, audit-at-end).** The fragmented chat/AI settings (7 surfaces, 3-way model split, silent fallbacks) are consolidated onto one resolution cascade; then `/review-impl` + standard + all 3 tracked defers cleared. **Commits:** `0172a4514`/`5944da242` (M1a), `a383c2a5f` (M2), `8843c7ba7` (M3), `fa935c26d` (M4), `8adbef9a1` (/review-impl fixes), `d81cea56b` (SET-1..8 standard), `9d1575cc8` (M1b book tier), `ccae0ce68` (M5 voice). **New repo standard:** [`docs/standards/settings-and-config.md`](../standards/settings-and-config.md) (SET-1..8) — user-setting vs platform-config boundary; env = ceiling not per-user knob; no silent fallback; must be consumed; closed-set ⇒ enum; registered in the index + CLAUDE.md Key Rules.
- **M1a — resolver + storage spine + FE studio inheritance.** `user_chat_ai_prefs` (Per-user Account-tier blob) + session override cols + `settings_resolution.py` (Session▸Book▸Account▸System, field-by-field deep-merge null=clear, per-tier model liveness → skip-dead/name-skipped/all-dead⇒no_model_configured). `GET/PATCH /v1/chat/ai-prefs` (412 version guard, deep-merge) + `GET /v1/chat/effective-settings` (resolved cascade, de-silenced System defaults VISIBLE). FE `features/chat-ai-settings` (ChatAiSettingsProvider hoisted OUTSIDE LiveStateProvider, memoized; `useEffectiveModel(role)`). **Every studio tool inherits through the CompositionPanel hub → real two-tier (book override wins over account default).**
- **M2 — consolidated "Chat & AI" settings tab.** `useAiPrefsEditor` (deep-merge PATCH, If-Match, invalidate-on-write, 412→reload). Models section (resolved model + source-tier chip + embedded DefaultModelsCard) + Behavior section (de-silenced: reasoning=was-off, tool-authority=was-write, temperature=blank-shows-provider-default, system prompt) each with source chips.
- **M3 — explicit grounding toggle.** Kills the "always on, no toggle" silent default: `grounding_enabled` resolves session▸account▸system(ON); OFF short-circuits the gate-disabled force-on → `build_context(grounding=False)` (verify-by-effect) and gates the T4 story-state net (EC-8) + FE amber "may invent lore" warning.
- **M4 — long-work context management.** Auto/On/Off mode writes ai-prefs.context; `mode='off'` force-disables the T5 gate + T4 net regardless of env (AND with deploy ceiling, §5; verify-by-effect). Folds in the standalone context mockup.
**Tests all green:** chat 1015, composition 1564, book-service ok, grants SDK 13, chat-ai-settings 12, settings 45; tsc-clean (the 1 `i18n/index.ts` error is PRE-EXISTING/unrelated).
**DEFERS — ALL CLEARED:**
- ✅ `D-CHATAI-M1B-BOOK-TIER` **SHIPPED** (`9d1575cc8`) — book-service `/internal/books/{id}/access` now returns `owner_user_id` (grantee-only, no oracle); `loreweave_grants` `resolve_owner()`; composition `GET /internal/composition/books/{id}/model-settings` (grant-gated, dual-reads legacy `default_model_ref`/`critic_model_ref`); chat `CompositionClient`; resolver Book tier now populated (Session▸Book▸Account). Two-tier model choice complete for chat sessions + shared-book collaborators.
- ✅ `D-CHATAI-M5-VOICE-UNIFY` **SHIPPED (core)** (`ccae0ce68`) — voice onto the unified home `user_chat_ai_prefs.voice`; `voice.py` resolves request▸saved-account-voice▸System-default (saved wins → kills the `af_heart` re-materialize); Voice panel section (TTS/STT ModelPicker + coupled voice); dead ReadingTab TTS controls removed (one home); fixed a latent runtime bug (`generate_tts_for_message` arity mismatch). *Small residual `D-CHATAI-M5-RESIDUAL`:* retire the legacy `VoiceSettingsPanel` into the new panel + optional auth-service `voice_prefs` lazy-seed — data model already unified (new home authoritative), this is UI-completeness only.
- ✅ `D-CHATAI-M4-TIER-CONSUMPTION` **RESOLVED — conscious WON'T-FIX** (defer gate #5, evidence-based). The context-budget tiers (T5/T4/D13a) are **eval-proven inert** (blind-judge A/B: baseline≡candidate on every dimension; compaction architecturally rare — never fired in the plant→recall probe). No per-tier expert toggles were built in the panel (only the `mode` switch, which IS consumed via M4), so there is **no write-only store to fix** (SET-5 clean). Building deep per-tier + size-based smart-detect consumption would construct machinery for zero-value behavior — a direct SET-5 violation ("don't build consumption for zero-value behavior"). **Revisit-gated:** implement only if a future eval shows the tiers add quality (e.g. genuine 1000-chapter books or small-context models). The shipped mode-level Off switch is the meaningful user control.

**`D-PLANFORGE-NO-RESUME` FOUND + FIXED 2026-07-05 (live UI verification the user asked for: "I've only ever called PlanForge's backend, never used it through the frontend — I don't know if it actually works").** Live-tested PlanForge for the first time via the real UI (Playwright, test account, book `019f1783…`): Propose (Rules mode, $0) → real run created (`019f3157…`, 3 artifacts) → Validate → real 7-rule linter report rendered, matching exactly what the pre-existing dev-DB rows already showed (2 rules fail on this braindump's shape: `arc2_discovery`, `open_questions_preserved` — a rules-parser input-shape quirk, not an engine bug) → Compile correctly gated off by the failed validation. **Conclusion: the PlanForge engine and its propose→validate→compile wiring genuinely work end-to-end.** But reloading the SAME page showed a completely blank Planner — the run vanished from view even though 3 real `plan_run` rows exist server-side for that book (verified directly in Postgres). **Root cause:** `usePlanRun.ts` only ever set `run` from `createRun()`'s own response — it never called the already-built, already-working `planForgeApi.listRuns()` on mount. Every reopen of the Planner (or a different device/session) looked exactly like the feature had never been used, which is exactly the user's own experience and a direct violation of this repo's "server is the source of truth" rule. **Fixed** (user chose "mirror Agent Mode's Runs-list pattern" over a cheaper auto-load-latest): added a "Runs" tab (default view) — `PlanRunsListView.tsx` (new) fetches and lists every plan run for the book via a new `usePlanRunsList.ts` hook (same imperative style as `usePlanRun.ts`, no react-query dependency added to this feature); clicking a row calls a new `usePlanRun.loadRun(runId)` (GET, not a re-propose) and switches to the "Run" tab, which is the ORIGINAL propose-form-plus-readout view, unchanged internally, now also reachable for a past run; "+ New propose" calls a new `usePlanRun.resetRun()` (local-state-only) before switching tabs. No backend/contract changes — this was purely an FE gap, `listRuns` already existed and worked. **VERIFY:** frontend 617 files/4385 tests (all pre-existing PlannerPanel tests adapted to the new tab default + 10 new tests: list-default-view, empty-state, real-list-render, row-click→loadRun+tab-switch, new-propose→resetRun+tab-switch, tabs-never-unmount + 3 new usePlanRun tests for loadRun/resetRun/stale-poll-after-reset), `tsc` clean (one PRE-EXISTING unrelated error in `src/i18n/index.ts` from a concurrent i18n commit, confirmed via `git log` predates this change). **Live re-verified end-to-end on the running vite dev server** (not just unit tests): reopened the Planner via the command palette on the SAME book — it now defaults to "Runs", shows all 3 real server-side runs (including the one created earlier in this same session, with its validation_report artifact intact), and clicking a row correctly loads + switches to the Run tab showing that exact run's real state. i18n: en/ja/vi/zh-TW (the 4 already-covered langs; did not touch the concurrent session's in-flight ru/zh-CN locale work). Files: `frontend/src/features/plan-forge/{hooks/usePlanRun.ts,hooks/usePlanRunsList.ts (new),components/PlannerPanel.tsx,components/PlanRunsListView.tsx (new)}` + 2 test files + 4 locale `studio.json`.

**"CURSOR-FOR-NOVELS" REGISTER — SESSION CLOSE-OUT 2026-07-05 (`D-AGENT-MODE-NOTIFY` closed, PlanForge live-smoke re-confirmed as a real out-of-scope defer).** User asked to clear remaining defers and close the register (memory `writing-studio-fragmented-not-underbuilt`, all 4 items #1-#4 already CLOSED as of the prior entries below). Re-verified both open rows against CURRENT code instead of trusting the handoff note (CLAUDE.md anti-laziness rule):
1. **`D-AGENT-MODE-NOTIFY` was WRONGLY SCOPED as "no notification mechanism exists" — it already did.** `authoring_run_service.py`'s `_notify_terminal()` (D4, pre-existing) already fires a real notification-service HTTP-ingest call on every `report_ready`/`failed`/`paused` (breaker AND `pause_after_each_unit`) transition — visible in the Bell/notifications panel today, just not live-pushed (that leg needs a new Python AMQP producer onto `loreweave.events`, a genuinely separate SDK-worthy primitive — correctly stays deferred, out of proportion for this pass). **What WAS a real, cheaply-closable gap:** the notification carried no `link`, so clicking it did nothing (a repo-wide gap — verified via grep that NO emitter in the codebase sets `metadata.link`/`url` today, not specific to this feature). **Fixed, scoped to this feature only:** `_notify_terminal` now sets `"link": f"/books/{book_id}/agent-mode/runs/{run_id}"`; `frontend/src/features/studio/host/studioLinks.ts` gained an `AGENT_MODE_RUN_RE` case (same-book → `openPanel('agent-mode', {runId})`; cross-book → external to that book's `/studio`, since there's no standalone run page to land on); `AgentModePanel.tsx` now reads `props.params.runId` at mount AND retargets via `onDidParametersChange` (exact `JobDetailPanel.tsx` singleton-retarget pattern, DOCK-6) to open straight on Mission Control for that run. **VERIFY:** composition-service 91/91 (2 new metadata-link assertions) + full suite 1623 passed/150 skipped; frontend 617 files/4375 tests (4 new), full `npx vitest run` re-run clean; `tsc` clean except a **pre-existing, unrelated** `src/i18n/index.ts` error from the concurrent Area7 i18n commit (`1e7f3a1cc`) — confirmed via `git log` it predates this change, not touched. Live-verified inside the REAL rebuilt+restarted `composition-service` container (not just pytest): `inspect.getsource` on the running module confirms the new `link` field is live.
2. **PlanForge live-smoke defer RE-CONFIRMED, not closed** (stays gate #1 — genuinely a different track/module). Traced whether `arc_id` was really "missing infra": it isn't (it's just a string matched against the proposed spec's own `spec["arcs"][*]["id"]`, `compile.py:8-9` — no external registry). The REAL blocker is that the only reachable dev-DB plan run's spec **fails PlanForge's own core validation rules** (`arc2_discovery` missing, `open_questions_preserved` count=0 of a required ≥6, `plan_run` id `019f1f49…`) — a PlanForge spec-quality/content gap, not an Agent Mode wiring gap. Hand-crafting a spec to fake-pass would be a fake test, not a real one — left as documented, correctly out-of-scope.
**Register status: CLOSED.** All 4 Cursor-for-novels items + both review-impl passes + this close-out pass have no outstanding Agent-Mode-specific defers. Remaining, correctly out-of-register: the AMQP live-push leg of notifications (needs a new Python producer primitive — candidate for its own SDK-First scoped task if ever prioritized), and the PlanForge spec-quality gap above (belongs to whoever next picks up PlanForge).

**D-AGENT-NEEDLE-CONFAB FIXED + LONG-WORK-CONTEXT-MODE proposed 2026-07-05** (report §8.5). **(A) FIXED the needle-confabulation:** gemma-4 was inventing a wrong firm name ("Holmgood, Voss & Co.") from its parametric memory of the *published* Dracula instead of declining/searching. Root cause: the grounding `<instructions>` (`knowledge-service/app/context/formatters/instructions.py`) said "trust the XML as authoritative" but had NO general anti-invention rule (only `_WITH_ABSENCES`, scoped to `<no_memory_for>` entities). **Fix:** always-on `_ANTI_CONFAB` guardrail — "THIS manuscript+memory is the ONLY source of truth, NOT your training knowledge of any published work (the user's version may differ); on a missing specific detail, search story_search first, then decline rather than invent." Also the correct product principle (a continue-writing user is diverging from the original → the model's memory of it is not canon). **Live-verified:** firm-name turn now honestly declines ("not recorded … he is a 'banking solicitor'"), no invented name, generation unaffected. 16 instructions tests green (+1 assertion). **(B) `D-LONG-WORK-CONTEXT-MODE` (proposed, needs CLARIFY/DESIGN — L):** the Context-Budget tiers (T5/T4/D13a) are inert on small books but earn their keep on large novels (1000s of chapters, where compaction actually fires). Move them from GLOBAL startup env flags → per-book/session config (DB column or user pref, resolved per-turn) + an advanced UI toggle (default Auto) + smart auto-detect (enable when `projected_grounding + expected_history > ~0.6×window`, or proxy thresholds: word_count>~500k / chapters>~150 / glossary>~300). User proposed it; deferred pending a spec — offer to write `docs/specs/…-long-work-context-mode.md` next.

**CLEAN BLIND-JUDGE A/B (pure gemma-4) 2026-07-05** (report §8.5; follows the eval-validity fix below). Re-ran the blind judge on TWO uncontaminated pure-gemma-4 runs (lore-scout=gemma-4 now): baseline (all tiers off) vs candidate (T5+T4+D13a on). **Means IDENTICAL on every dimension** (correctness 4.5=4.5, groundedness 4.67, continuity 4.67, helpfulness 4.83, craft 3.17). **Conclusions:** (1) protagonist confab GONE — `lore_recall` 5/5 both, correctly IDs Jonathan Harker (confirms the qwen retraction); (2) **the Context-Budget tiers add ZERO measurable quality** (baseline≡candidate) → **keep T5/T4/D13a DEFAULT-OFF** (cost, no benefit — consistent with the compaction-inert finding); (3) NEW model-tier defect `D-AGENT-NEEDLE-CONFAB`: on the firm-name needle it lacks indexed, gemma-4 CONFABULATES a wrong name ("Holmgood, Voss & Co."/"Seward & Co.") instead of using `story_search mode=exact "Hawkins"` or declining — caps continue_writing correctness at 2; wants tool-routing nudge or a stronger model (less severe than the qwen protagonist error; agent otherwise correct+grounded). Clean transcripts: `runs/continue-writing-2026-07-05/{baseline,candidate}_gemma4_puresubagent.transcript.jsonl`. Defaults restored, stack clean.

**#20 AGENT MODE — 2 DEFERRED `/review-impl` GAPS DESIGNED + FIXED 2026-07-05** (follow-up to the earlier `/review-impl` pass, user asked to actually design the 2 items that pass had marked out-of-scope rather than leave them as permanent deferrals). Both had a real design done, not just a note:
1. **IN-3 `tool_allowlist` is now a closed-set enum**, not a bare string list. Investigated first whether a live-registry-validation precedent existed anywhere in the repo (checked chat-service's `enabled_tools`/`enabled_skills`) — it doesn't; every similar "list of tool names" field in this codebase accepts arbitrary strings today, so this is a genuinely new pattern. Defined `ALLOWLISTABLE_TOOLS` (`authoring_run_service.py`) — the 14 prose/outline-adjacent `composition_*` tools a drafting seam could plausibly invoke (admin/motif/canon-rule/run-control tools excluded). Single source of truth: REST (`AuthoringRunCreate`) and MCP (`_AuthoringRunCreateArgs`) schemas both use `list[Literal[ALLOWLISTABLE_TOOLS]]`; `gate()` re-validates the same set as the shared backstop (the ONE chokepoint both entry points funnel through). This broke 71 pre-existing tests using a placeholder tool name (`"book_write_draft"`/`"t"`) that was never a real tool — confirmed via repo-wide grep it wasn't a real registered name anywhere, then fixed the fixtures to use a real allowlisted tool name instead of loosening the new check.
2. **IN-5 has a real Python primitive now: `TolerantArgs`** (`sdks/python/loreweave_mcp/errors.py`), a sibling to the existing `ForbidExtra` — `extra="ignore"` instead of `extra="forbid"`, identity/scope ids still never declared on either (same smuggling protection regardless). Ports the Go MCP kit's `relaxAdditionalProps` *intent*, not its mechanism (Pydantic has no schema-level `additionalProperties` to relax — Go's is the literal opposite-direction primitive, there was no existing Python sibling to mirror). Migrated this feature's 7 arg models to it — the first real adopter; deliberately did NOT touch `ForbidExtra` itself or the ~15 other composition tools / 3 other services (jobs/lore-enrichment/translation) still using it, out of proportion for this pass. `docs/standards/mcp-tool-io.md` updated with a pointer so the next new Python MCP tool knows this primitive exists.
**VERIFY:** composition-service 1622 passed/150 skipped (+5 new tests across both fixes), SDK 63 passed (+2), rebuilt+restarted the real container and confirmed BOTH behaviors live inside it (not just pytest) — the enum rejects an unknown tool name, `TolerantArgs` silently drops a hallucinated extra field, both exercised via a direct import inside the running `composition-service-1` container. Full detail + the "no existing precedent, no existing Go sibling" investigation notes: `docs/specs/2026-07-01-writing-studio/20_agent_mode.md`'s checklist follow-up section. **The Agent Mode register item (#20 / "Cursor-for-novels" #4) has no more open standards findings from either `/review-impl` pass.**

**EVAL VALIDITY FIX + RETRACTION + COMPACTION FINDING 2026-07-05** (report [`measurement-continue-writing-2026-07-05.md`](../eval/context-budget/measurement-continue-writing-2026-07-05.md) §8). **(1) MODEL CONTAMINATION found (by user):** the test account's `lore-scout` subagent (invoked via `run_subagent`) was pinned to **qwen-2.5-7b** (`model_ref 019eb620`), so lore-recall turns secretly ran on a weak 7B model while reports claimed gemma-4. NOT a source bug (subagents carry BYOK `model_ref`, provider-gateway-clean) — a data config. **FIX:** repointed `lore-scout` → gemma-4-26b-a4b-qat (`019ebb72`) in `agent_registry.subagent_defs`; verified via `/internal/subagents`. **(2) RETRACTION:** `D-KG-PROTAGONIST-SALIENCE` was a **qwen artifact, not a KG gap** — the "main character = Dracula" confab; re-run with pure gemma-4 (`baseline_gemma4_puresubagent`) correctly answers **"Jonathan Harker … the protagonist and narrator"**. Closed as not-a-bug. Tool-wiring fixes (federation/search-unify/book-body) + passage-ingestion resolution are model-independent and STAND (re-confirmed pure-gemma-4). **(3) D-T4-D13A-COMPACTION-EVAL — finding: compaction is architecturally rare.** Wired T4/D13a env passthrough in compose (`STORY_STATE_BLOCK_ENABLED`/`COMPACT_COLLAPSE_DUPLICATES_ENABLED`; only T5 was wired). Authored a 15-turn plant→recall scenario (`context_budget_scenarios_compaction.json`); ran on 40K + forced 10K windows → **compaction NEVER fired.** The compactor acts on message HISTORY only (~1.8K plateau — grounding is inline every turn, tool results don't persist); trigger is 0.75×window; the algebra (fixed grounding overhead ~7K + compacted-history ≤ W, history > 0.75W) needs W≥4×overhead AND ~40-60 substantial turns. So **T4 (needs T5-gated-empty grounding) + D13a (needs a compaction pass) are INERT in normal grounded sessions** on large-context models — correctness is unit-test-proven, live impact ~nil. **Recommendation: keep T4/D13a/T5 DEFAULT-OFF**; revisit only for pull-mode grounding or small-context models. Retention is a non-issue without compaction (the plant→recall probe recalled all 3 synthetic canon facts verbatim from the ~8K context). Files: `infra/docker-compose.yml` (env), `scripts/eval/context_budget_scenarios_compaction.json`, report §8, `runs/…/baseline_gemma4_puresubagent.transcript.jsonl`.

**PASSAGE AUTO-BACKFILL WIRED ON EXTRACTION-START 2026-07-05** (follows the passage-ingestion fix below). Closes the systemic follow-up: passages no longer need a manual backfill call. Extracted the backfill loop into a shared helper `app/extraction/passage_backfill.py::backfill_project_passages` (used by both the admin `POST /internal/projects/{id}/backfill-passages` route AND the new auto-trigger); the public `start_extraction_job` route now schedules it as a **best-effort FastAPI BackgroundTask** after the job is created — the user's "index my book" action guarantees embedding config + book link are present, so semantic search is never left empty by "publish predated the project's config". Best-effort + idempotent (content-hash skip): never blocks or fails extraction; Track-1 (no Neo4j) skips cleanly. **VERIFY:** knowledge internal_backfill (5) + extraction_start (28) tests green; **live-smoke** — started a real extraction → log `auto passage backfill on extraction start project=…: {'chapters_ingested': 4, 'passages_created': 0, 'chapters_failed': 0}` (idempotent, 0 new on the already-ingested Dracula project). Caught+fixed live: `get_book_client()` is SYNC (was wrongly `await`ed). Files: `services/knowledge-service/app/extraction/passage_backfill.py` (new), `app/routers/internal_backfill.py` (refactor to helper), `app/routers/public/extraction.py` (auto-trigger + `BackgroundTasks`), `tests/unit/test_internal_backfill.py`.

**#20 AGENT MODE — `/review-impl` PASS 2026-07-05 (commit `3fe1b6649` → follow-up fix commit).** Ran 3 parallel adversarial audits (standards gate: `docs/standards/mcp-tool-io.md` IN-1..8/OUT-1..6 + `docs/standards/dockable-gui.md` DOCK-1..11; exhaustive item-by-item cross-check of every line in `20_agent_mode.md`'s GUI checklist + the mockup HTML against the real built code) and fixed what was real. **Fixed:** (1) `mcp-tool-io.md` IN-4 — `budget_usd`/`limit`/`unit_index` had no schema bounds, added `Field(gt=0)`/`Field(ge=1,le=100)`/`Field(ge=0)` + 4 new tests; (2) OUT-5 — `composition_authoring_run_list` silently truncated at `limit` with no signal, now over-fetches by one and returns `has_more`; (3) the run-header **poll indicator was entirely missing from the UI** despite the real 5s poll already existing in `hooks.ts` — added a live "polling every Ns / last refreshed Ns ago / suspended" line reading `dataUpdatedAt`/`isFetching`; (4) the New-Run plan-empty state had no CTA to the `planner` panel — added; (5) the breaker-reason chip showed a raw DB string (`pause_after_each_unit`) instead of friendly copy — added a label map; (6) a real doc bug — the checklist said `_start`/`_resume` *require* `pause_after_each_unit` while the Locked Decisions table (correctly) says it's an *optional* override; the shipped code follows the table, the checklist wording was wrong, fixed. **Deliberately NOT fixed (documented, gate-checked):** IN-3 `tool_allowlist` isn't a closed-set enum — no defined "closed set of allowlistable tool names" exists anywhere in this service yet, a design gap needing its own scoping, not a build defect; IN-5 `ForbidExtra`'s all-extras-rejected posture (no Python analogue of the Go kit's `relaxAdditionalProps`) is a repo-wide `loreweave_mcp` SDK gap, out of this feature's scope. **A caught false positive, not a bug:** the exhaustive audit claimed keyboard-triage's no-op branch was untested — re-verification found `MissionControlView.test.tsx:209-220` already proves it end-to-end; **even an adversarial audit's own findings get re-verified before acting**, not trusted blind. Zero DOCK-1..11 violations found (one LOW stale-comment fixed). Full checklist in `20_agent_mode.md` now ticked with evidence, not left blank from CLARIFY. VERIFY: composition-service 1617 passed/150 skipped (+4), frontend 617 files/4363 tests, tsc/eslint clean — all re-run after fixes, not assumed. Remaining open (unchanged from before this pass, still tracked): `D-AGENT-MODE-NOTIFY`, and the full paid-LLM live-smoke across both UI/MCP entry points for `pause_after_each_unit` (needs a compiled plan run on a test book — an unrelated PlanForge fixture gap, not this feature's).

**PASSAGE INGESTION (D-KG-PASSAGES-NOT-INGESTED) — FIXED → the ch4-recall punt RESOLVED 2026-07-05** (report §7.5). Root cause: passages ingest on the `chapter.published` event (CM3c) but that path SKIPS when the project has no embedding config at publish time — the Dracula KG project was linked to the book AFTER its chapters were published → **0 passages** ever ingested → semantic memory/story search empty. **FIX:** ingested the 4 published chapters via the production `ingest_chapter_passages` path → **116 `:Passage` nodes embedded** (bge-m3, $0). Made durable with a new idempotent endpoint **`POST /internal/projects/{id}/backfill-passages`** (`services/knowledge-service/app/routers/internal_backfill.py` — enumerates published chapters, resolves user+embedding+book from `knowledge_projects`, skips on no-book/no-embedding/no-neo4j; 2 unit tests + live-smoke 200/4-chapters/idempotent). **RESULT (re-run continue-writing):** t0 "where is Harker at ch4" → **RESOLVED** (grounded from passages: "a prisoner in Count Dracula's castle… confined to his own room… the three female vampires… door hopelessly fast"); t6 firm-name → grounded+honest ("not explicitly mentioned… a 'banking solicitor'" — correct; exact "Peter Hawkins" needs `story_search mode=exact`, a retrieval-recall nuance). Cost: t0 ~85K tok (8 memory_search passage pulls → past the 32K compaction trigger, reinforces `D-T4-D13A-COMPACTION-EVAL`). **The eval is now genuinely objective — the agent's own preferred tool (memory_search) reaches the manuscript both lexically (any book) + semantically (indexed book), and it STOPS punting on chapter-narrative recall.** **NEXT systemic follow-up:** auto-trigger `backfill-passages` when a project links an already-published book (or fold into extraction-start) so it isn't manual; weak-model orchestration (won't read a whole chapter to chase a needle) is a model-tier limit, not a repo gap.

**#20 AGENT MODE / MISSION CONTROL — CLARIFY→BUILD SHIPPED 2026-07-05** (branch `feat/context-budget-law`, spec [`20_agent_mode.md`](../specs/2026-07-01-writing-studio/20_agent_mode.md), plan [`2026-07-05-agent-mode-implementation.md`](../plans/2026-07-05-agent-mode-implementation.md)). The "Cursor-for-novels" register's #4 (last) item — 0% frontend, 0 MCP tools over a fully-built `authoring_run_service.py` (1346 lines) — is now fully specced AND built in one continuous run (user explicitly authorized skipping PO checkpoints for this task, 2 parallel background sub-agents + orchestrator integration). **CLARIFY found a load-bearing fact the first mockup pass got wrong**: the driver does NOT wait for accept/reject between units — it drafts every chapter back-to-back until scope/budget/critic-severe stops it, and accept/reject/revert-all are server-gated to `report_ready`/`failed`/`paused` only (`_REVIEWABLE_STATUSES`, `authoring_run_service.py:148`). A follow-up edge-case pass then found the *fix* for that (a client-side "auto-pause after each unit") was ALSO wrong — client-poll-and-call-`/pause` silently no-ops for any run started via the new MCP tools with no Studio panel open, exactly the scenario those tools exist for. **Final design: `pause_after_each_unit` moved fully server-side** — a new `authoring_runs.pause_after_each_unit` boolean column the driver itself checks at its own unit-boundary re-claim (same guarded-transition code path as the pre-existing budget/critic-severe stops), so the policy holds regardless of entry point.
**Backend** (`services/composition-service/`): migration (idempotent `ALTER TABLE ADD COLUMN IF NOT EXISTS`, this service's existing pattern — no numbered-migration tool exists here); driver pause-after-unit check (never fires after the last unit); new `PATCH .../authoring-runs/{run_id}/pause-policy`; **11 new MCP tools** `composition_authoring_run_*` (list/get/pause/close/accept_unit/reject_unit direct; create/gate/start/resume/revert_all confirm-gated via the same `mint_confirm_token`→`confirm_action` mechanism as `composition_generate`; `create`'s `budget_usd`+`pause_after_each_unit` have no Python default — a missing arg is a validation error, not a silent guess; `start`/`resume` take an optional override applied via `set_pause_policy` BEFORE the transition). 1613 passed/150 skipped (pre-existing DB-integration tests needing a live Postgres — unaffected), independently re-run twice by the orchestrator (not just trusted from the sub-agent's report).
**Frontend**: one `agent-mode` Studio panel (Runs list / New run / Mission control, D1) + a thin `chapter-revision-compare` wrapper panel (D2, reuses the EXISTING `RevisionCompareView`/`RevisionDiff` diff renderer — not reinvented) + `frontend/src/features/composition/authoringRuns/` data layer (pure `fsm.ts` unit-testable without React, covering D8's single most correctness-critical rule: Accept/Reject hard-disabled outside `report_ready`/`failed`/`paused`). Keyboard triage (a/r/←/→), revert-all confirm modal WITH partial-failure rendering (the service can stop partway through a revert and NOT auto-close — a real edge case the first mockup pass only showed the happy path for), budget-danger threshold, breaker/heartbeat health chips. 46+ new tests, full frontend suite independently re-verified by the orchestrator: 617 files / 4363 tests, `tsc`/eslint clean.
**Orchestrator-caught gaps the sub-agents' own scoping missed** (both required touching a file OUTSIDE the sub-agent's assigned service, which is exactly why fanned-out work still needs a real integration pass, not just trusting each report): (1) the frontend agent correctly registered both new panels but marked `agent-mode` `hiddenFromPalette: true` because making it palette/agent-openable needs an enum entry in **chat-service** (`frontend_tools.py`'s `ui_open_studio_panel` `panel_id`), out of that agent's assigned scope — fixed by adding the enum value + regenerating `contracts/frontend-tools.contract.json` (`WRITE_FRONTEND_CONTRACT=1 pytest`). (2) That same VERIFY run surfaced a **pre-existing, unrelated bug**: `services/chat-service/tests/test_frontend_tools.py` had a second, hand-copied `panel_id` enum literal that had already drifted stale (missing `context-inspector`/`sharing`/`book-settings`/`translation`/`enrichment-*`/`user-guide` — added by past sessions without updating this duplicate) — root-caused and fixed by replacing the brittle hardcoded-list duplicate with a lighter assertion (non-empty, no dupes, contains `agent-mode`), since the REAL anti-drift mechanism is the already-existing `test_frontend_tools_contract.py`/committed contract JSON. Chat-service: 976/976 green (was 975/976 red before this fix).
**Live-smoke (honest, bounded — documented, not silently skipped):** DB migration verified against the REAL dev Postgres (`\d authoring_runs` shows the column live, not just in a fake-repo unit test) after rebuilding+restarting `composition-service`/`chat-service` with the new code (stale 5h-old images would have false-greened otherwise). All 11 MCP tools confirmed live-registered by querying `composition-service`'s actual running MCP server from inside its container (`mcp_server.list_tools()` — not a mock). **NOT run live**: the full plan→gate→start→auto-pause round trip through a real LLM seam — the only reachable plan runs on the dev DB were `status='proposed'` (need `validated`/`compiled` to pass `gate()`), and getting one to `compiled` required an unrelated PlanForge fixture (`arc_id`) outside this feature's scope; the mechanism under test (`pause_after_each_unit`'s pure state-machine check) has zero dependency on LLM output content and is already exhaustively covered by 12 targeted unit tests against the exact driver code path — judged a proportionate, reasoned tradeoff, not a shortcut.
**Not built (documented, gated, not silently dropped):** `D-AGENT-MODE-NOTIFY` — cross-Studio notification when a backgrounded run finishes/pauses/fails while the panel isn't open; gated "naturally-next-phase" pending a BUILD-time audit of whether a general Studio notification/badge primitive already exists elsewhere (if yes, this may not even need its own build).
**Files:** `docs/specs/2026-07-01-writing-studio/20_agent_mode.md` (spec+checklist, 00_OVERVIEW.md row #20), `docs/plans/2026-07-05-agent-mode-implementation.md`, `design-drafts/screens/studio/screen-studio-agent-mode.html` (v2, corrected post-CLARIFY), 7 `services/composition-service` app files + 5 test files (1 new), `services/chat-service/app/services/frontend_tools.py` + `tests/test_frontend_tools.py`, `contracts/frontend-tools.contract.json`, ~15 new/changed `frontend/` files (panels/hooks/tests) + 8 i18n locale files + `catalog.ts`. **NEXT:** nothing blocking — register is now fully specced+built end to end (#1/#2/#3 closed earlier, #4 closed today). A natural follow-up if picked up: `D-AGENT-MODE-NOTIFY` audit, or a live paid round-trip smoke once a compiled plan run exists on a test book.

**SEARCH-TOOL UNIFICATION (engine + surface) + CHAPTER-BODY READ — SHIPPED 2026-07-05** (report §7.4, plan [`docs/plans/2026-07-05-search-tool-unification.md`](../plans/2026-07-05-search-tool-unification.md)). User-approved "grep/glob minimalism": ONE canonical search tool + a real chapter read. **Engine-unify (knowledge `_handle_memory_search`):** `memory_search` now runs the SAME lexical-inclusive hybrid engine `story_search` uses over the linked book's chapters (needs NO embeddings) + its existing semantic passage leg for chat/glossary, merged/deduped — so whichever search tool the agent picks is NEVER empty when the chapter text lexically matches. Live-verified: `memory_search "Hawkins"` returns the chapter snippet (was 0 before). **Chapter-body read (book-service Go `book_get_chapter`):** opt-in `include_body=true` returns the chapter's plain-text prose from `chapter_blocks` (default omits — body can be large); live-verified 28.6k chars incl. Hawkins, absent without the flag. **Surface:** `story_search` hot/canonical (grep), `memory_search` lazy+redirecting-description, `book_get_chapter include_body` = read (Claude-Code shape). **VERIFY:** knowledge 13 executor + mcp_server + response_contract (107) green; book-service GetChapter/MCP tests green (new `mcp_get_chapter_body_db_test.go`); knowledge+book rebuilt+live-smoked. **HONEST RESIDUAL (NOT a wiring bug — clears `D-AGENT-PREFERS-EMPTY-MEMORY-SEARCH` as "tool now works"):** gemma STILL punts on *semantic* queries ("where is Harker at ch4", "what firm") because (a) its queries are semantic but only the lexical leg has data (no embedded passages → "firm" doesn't lexically match "Mr. Peter Hawkins"), and (b) gemma won't fall back to `book_get_chapter include_body` to read the chapter. So tools are correct+unified (a stronger model / ingested passages would use them); residual = `D-KG-PASSAGES-NOT-INGESTED` (semantic index) + weak-model orchestration. **The eval confound (dropped/hidden search tool) is REMOVED** — the measurement now reflects true agent+tool capability. **NEXT lever:** investigate/trigger passage ingestion (`D-KG-PASSAGES-NOT-INGESTED`) so semantic queries succeed, then re-measure; OR a stronger chat model.

**TOOL-SURFACE BUG FIX — `story_search` UN-DROPPED FROM FEDERATION + HOT-SEEDED 2026-07-05** (report §7). Root-caused why the agent punts on chapter-text recall even with KG built: **`story_search` (the universal manuscript find — `mode=exact` is lexical/keyword, needs NO embeddings/KG) was silently DROPPED by ai-gateway's C-GW prefix gate** (knowledge allowed `[memory_, kg_]`; `story_search` matches neither — proven in gateway logs). So the agent's catalog had NO manuscript-search tool → fell back to empty `memory_search` → punted. **FIX (committed):** added `story_` to knowledge's `EXTRA_PREFIX_MAP` (`services/ai-gateway/src/config/config.ts`) + hot-seeded the `story` domain on book/studio surfaces (`services/chat-service/app/services/tool_discovery.py`) — same lesson the code already recorded for `composition_*`. **VERIFIED:** catalog 175→176; `story_search mode=exact "Hawkins"` returns the RAW chapter prose (lexical, zero embeddings) — the keyword fallback that works on ANY book with no glossary/KG. ai-gateway (23) + chat tool-discovery/surface (39) tests green; both services rebuilt+restarted. **STILL OPEN (deeper, NOT wiring — 2 new rows):** (1) `D-KG-PASSAGES-NOT-INGESTED` — 0 Passage nodes in Neo4j → `memory_search`'s semantic leg has no chapter-body data → chapter-detail recall (e.g. the firm "Peter Hawkins") invisible to it; extraction wired passage_ingester but produced 0. (2) `D-AGENT-PREFERS-EMPTY-MEMORY-SEARCH` — live re-probe shows gemma STILL prefers `memory_search` (called 10× in one turn) over the now-available `story_search` and punts; fix = make `memory_search` fall back to the lexical leg on an empty semantic hit, and/or sharpen tool descriptions (agent-behavior work). **Net for the eval:** the wiring bug is fixed (manuscript search reachable + works with zero embeddings) — but the agent won't reliably stop punting on chapter-body recall until passages are ingested OR memory_search degrades-to-lexical.

**CONTEXT BUDGET MEASUREMENT — ROUND 2 (grounded re-measure) 2026-07-05** (report [`docs/eval/context-budget/measurement-continue-writing-2026-07-05.md`](../eval/context-budget/measurement-continue-writing-2026-07-05.md) §6; extends the Round-1 note further down). Ran KG extraction on the Dracula project (`POST …/extraction/start`, gemma+bge-m3, $0.016, job `019f2f46`) → populated **Neo4j: 63 entities (incl. Jonathan Harker, Mina), 114 events, 12 facts**; re-ran the A/B grounded + blind-judged. **KEY RESULT — the Round-1 T5 regression was GROUNDING-INDUCED:** grounded, T5's empty-turn-0 (0ch→723ch) and refuse-to-write-turn-1 (581ch→924ch prose) both RESOLVE; blind judge scores grounded-baseline ≈ grounded-T5 (helpfulness **4.5 = 4.5**, T5 slightly higher craft) — the ungrounded 4.33-vs-3.83 gap CLOSED. So the T5 N≥4 re-run should be on the GROUNDED project (clean comparison, not a regression-chase); T5 default flip still deferred (N=1 + a transient KG "project not found" blip to understand). **Grounding fixed** the cross-chapter arc-recall punt (→ grounded Traveler→Prisoner→Hunter arc). **Grounding did NOT fix two deeper, buildable gaps:** (1) `D-KG-PROTAGONIST-SALIENCE` — protagonist mislabel PERSISTS ("main character = Dracula" not Harker) even with Harker as an entity → a SALIENCE problem (no POV signal; Dracula wins by centrality), motivates the Track-4 salience substrate; (2) `D-KG-SUMMARIES-TARGET-NOOP` — `summary_chapters`/`summary_books` STILL 0 after extraction (no `Summary` nodes) → the extraction `summaries` target didn't populate per-chapter recaps (separate `summary_processor`/`summary_enqueue` job, or a silent no-op) → the "where is X at chapter N" recall still punts; investigate + re-measure. **Cost note:** grounded continue-writing t0 hit **50,432 tok, crossing the 32K compaction trigger** → this is the concrete scenario to run `D-T4-D13A-COMPACTION-EVAL` on. Round-2 artifacts: `runs/continue-writing-2026-07-05/{baseline,t5on}_grounded.transcript.jsonl`.

**LANGUAGETOOL 502/500 FIX + BOOKS→STUDIO ROUTING + CHAPTER READER MODE — SHIPPED 2026-07-05** (branch `feat/context-budget-law`). Four user-reported items this session:

1. **LanguageTool bad-gateway, TWO root causes fixed** (`infra/docker-compose.yml`): (a) `frontend`'s `depends_on: [languagetool]` was start-order only (`condition: service_started` implicitly) — LanguageTool's JVM takes 40s+ to actually accept connections, so any grammar-check hitting nginx during that boot window got a real 502, which opens the FE's circuit breaker for 60s. Changed to `condition: service_healthy` so `docker compose up` actually waits. (b) **Live-verified a second, more severe bug**: `Java_Xmx: 512m` OOMs (`java.lang.OutOfMemoryError: Java heap space`) within minutes of real editor usage on a multi-chapter book — confirmed via `docker logs infra-languagetool-1` showing the OOM + JVM crash + auto-restart, with every request in that window getting a 500. This can recur at ANY time during normal use, not just startup — the dominant cause of the reported bug. Bumped to `Xms: 512m, Xmx: 2g` (host has 88GB+ free, zero cost). Live-verified: 20+ concurrent real-editor grammar checks after the bump, zero 500s (vs. reproducible 500s before).
2. **`D-BOOKS-CREATE-TO-STUDIO`**: creating a book from `/books` used to just close the dialog and reload the list — user had to manually click the new row to enter it. `useBooksList().handleCreate()` now returns the new `book_id`; `BooksPage.tsx` navigates straight to `/books/:id/studio` on success.
3. **`D-STUDIO-BACK-TO-BOOKS`**: the Writing Studio's back button targeted `/books/:bookId` (the legacy tabbed workspace) — retargeted to `/books` (the list). Confirmed safe: other pages (`StudioActivityBar` settings link, `ReaderPage`'s back-to-book) link to the legacy route independently, nothing depended on the Studio back button specifically.
4. **`D-CHAPTER-READER-MODE`**: no way existed to open a distraction-free reading view of the chapter currently open in the Studio editor — `BookReaderPanel` existed only for browsing an OTHER book (from `BooksBrowserPanel`). Rather than fork a second reader implementation, `EditorPanel` got a new "Reader" toolbar button that opens the SAME `book-reader` singleton panel with the ACTIVE book + currently-open `chapterId` (params-retargeting, same seam `BooksBrowserPanel` already uses for another book). **Responsive fix bundled in** (the other half of this ask): the shared reader chrome (`TOCSidebar`, `ThemeCustomizer`, `TTSSettings`, `TTSBar` — reused as-is by both the standalone `/read` route and the Studio panel) used `fixed` positioning + `100vw`, which pins to the BROWSER WINDOW's edges — fine for the full-viewport route, but broke down inside a narrower dockview panel (TOC sidebar would render pinned to the window's left edge regardless of where the panel actually sits). Fixed by switching to `absolute` + `100%` + `max-w-full` — resolves against the nearest positioned ancestor (the panel's own `relative` wrapper for the Studio case, the full-viewport wrapper for the standalone route — both correct, zero regression). Live-verified via `getBoundingClientRect`/`offsetParent`: the TOC sidebar's `x` now exactly matches the panel's own left edge, not `x:0`.
5. **`D-READER-WIDTH-SCALE`** (follow-up, same session): the reader's article was capped at a fixed `--reader-width` (theme preference, default 680px) regardless of how wide the dock panel actually was — a wide panel (no split) left huge unused margins. Live-verified two candidates for the reported "chapter list stuck at 20" complaint (Manuscript Navigator, Reader's own TOC) against a real 40-chapter book — neither reproduces; the historical limit-20 backend bug is confirmed fixed. Fixed the width waste via a `containerType: inline-size` + `clamp(var(--reader-width, 680px), 85cqw, 1100px)` on the reading-area wrapper — scales the ceiling with the PANEL's own width (not the browser window), the user's preference still acts as a floor, 1100px caps it. **Caught + fixed a self-introduced regression before commit**: `.content-renderer` (reader.css, the actual prose container) computed the same `--reader-width` independently of the `<article>` wrapper's new clamp — widening the article alone left the inner prose box pinned at the old 680px, rendering text left-aligned inside the now-wider article (user caught this live: "render text bị lệch qua 1 bên"). Fixed by hoisting ONE derived `--reader-effective-width` custom property (set once on the wrapper) that both the article's inline style AND `.content-renderer`'s CSS rule key off — eliminates the two-independent-computations drift risk structurally, not just this one instance of it. Live re-verified: `.content-renderer`'s rect now matches the article's exactly. Full suite 4281/4281 green, tsc clean.

**VERIFY:** full frontend suite 4281/4281 green (612 files), tsc clean; live Playwright smoke against the vite dev server (`:5199`) confirmed all 4 fixes end-to-end (Welcome-default + back-button target + Reader button opening the singleton with real Vietnamese chapter content + grammar-check surviving real concurrent editor load post-heap-bump). Note: `/review-impl` (the deeper adversarial pass) was NOT run this session — only the standard build-time self-review — since none of the 4 items touch auth/tenancy/destructive-op surfaces; available on request.

**CONTEXT BUDGET LAW — MEASUREMENT PHASE RUN 2026-07-05** (branch `feat/context-budget-law`, report [`docs/eval/context-budget/measurement-continue-writing-2026-07-05.md`](../eval/context-budget/measurement-continue-writing-2026-07-05.md), raw transcripts under `docs/eval/context-budget/runs/continue-writing-2026-07-05/`). Ran the real chat agent (gemma-4-26b, BYOK, $0) over the **public-domain Dracula book** (`book_id 019eeb09`, 4 published Harker-journal chapters + KG `019f2be0`, 100 glossary entities) on a new **7-turn continue-writing arc** + 5 recall/continuity scenarios (`scripts/eval/context_budget_scenarios_continue.json`), A/B **baseline vs T5-intent-gate-ON**, blind-judged by a cold-start Agent. **Results:** (1) **the agent is a strong continue-writer** — craft 5/5 Gothic first-person Harker voice, correct revision behavior (kept prior text, layered darkness), accurate cross-chapter echo (Count scaling the wall "like a lizard"); **zero *invented* lore** (honest declines where data was missing). (2) **Context machinery healthy** — no-lore turns cheap (3.9–5.1K tok, 0 tools), first-lore fetch heavy (19–28K, driven by tool *results* not grounding), follow-up generative turns reuse context cheaply (5–6K), tool-discovery constant ~2K (agui hot-set, NOT 41K catalog); no compaction fired (max 27.7K<32K → **T4/D13a untested this run**). (3) **DO NOT flip T5 default ON yet** (`D-T5-CONTINUE-WRITING-REGRESS`) — single-run regression on continue-writing openings (empty turn-0 reply, refuse-to-write turn-1; blind judge scored baseline higher helpfulness 4.33 vs 3.83); needs **N≥4** to separate from gemma variance + root-cause the empty-reply tool-loop. (4) **HEADLINE FINDING — the continue-writing loop is GROUNDING-STARVED, not model/budget-limited:** this project's derived layer is **unbuilt** (`summary_chapters`=0, `entity_canonical_snapshots`=0, `stat_entity_count`=0; grounding = 100 glossary entities only). That one gap explains every quality miss — the protagonist mislabel (both runs confidently say "main character = Count Dracula" not Jonathan Harker: **shared critical_confabulation**, a grounding mislabel with no POV signal), the "where is Harker at ch4" punt, and the "firm name" punt. **NEXT (highest leverage for the user's actual goal):** `D-EVAL-BOOK-GROUNDING` — run the knowledge extraction/summarization pipeline on the Dracula project (buildable in-repo, not blocked), then re-measure (expect the punts + mislabel to resolve). Then `D-T4-D13A-COMPACTION-EVAL` (long ~30-turn scenario forcing ≥1 compaction; wire `STORY_STATE_BLOCK_ENABLED`/`COMPACT_COLLAPSE_DUPLICATES_ENABLED` env passthrough in docker-compose — only T5 is wired today) + the T5 N≥4 re-run.

**"CURSOR-FOR-NOVELS" REGISTER #3 LIVE-SYNC — AUDIT + FIX SHIPPED 2026-07-05** (branch `feat/context-budget-law`, memory `writing-studio-fragmented-not-underbuilt`). User picked #3 next after #1/#2 closed. Audited whether 3 previously-unmatched tool-name families (`composition_generate`, `authoring_run`, `translation_job`) leave a live Studio panel stale — **2 of 3 were NOT gaps**: `composition_generate` only mints a confirm-token (`services/composition-service/app/mcp/server.py:1130`), the actual persisting write is `composition_write_prose`, already matched by the existing `/^composition_.*(prose|draft)/` reconciler pattern; `authoring_run` has ZERO MCP tools (REST-only router, `app/routers/authoring_runs.py`) and zero frontend consumers — nothing can go stale if nothing can call it via chat. **The 3rd was a real gap:** `translation_job_control` (cancel/pause execute immediately at A-tier) writes `translation_jobs.status` but neither `TranslationTab.tsx`'s coverage matrix nor `ChapterTranslationsPanel.tsx` refreshed. Fixed: new `translationEffects.ts` Lane-B handler (mirrors `glossaryEffects.ts`'s shape) invalidates the matrix's react-query keys (`translation-coverage`, `segment-coverage`); `ChapterTranslationsPanel` (a plain useState/useEffect fetcher with no react-query of its own) got a minimal trivial-queryFn "refresh-signal" sentinel query so the SAME invalidation mechanism can trigger its `loadAll()` without restructuring its existing local optimistic-update state (`handleSetActive` et al — untouched, lower regression risk than a full react-query migration). resume/retry (W-tier, dispatch through the generic `confirm_action` tool) explicitly left out of scope — same "no domain-routable result shape" class `composition_generate` turned out to be a non-issue for, documented in the handler's file header, not silently dropped. Also fixed 2 stale comments the audit surfaced: `useStudioEffectReconciler.ts`/`effectRegistry.ts` both still said "SKELETON: handlers are stubbed" despite book/glossary/knowledge handlers being real for a while; `TranslationPanel.tsx` claimed "translation-service has no MCP tools federated" (false — confirmed federated via `infra/docker-compose.yml:955`). **VERIFY:** `tsc` clean; new `translationEffects.test.ts` (4 tests, mirrors `glossaryEffects.test.ts`'s registry-contract shape); full `studio/agent` suite 89/89 green, full `translation`+`book-tabs` suite 59/59 green (no regressions); live browser smoke on `ChapterTranslationsPanel` (clean single mount, zero console errors, Re-translate/Compare Mode/version-switch UI all rendered correctly) — no dedicated unit test existed for this component before (still doesn't; the sentinel-query addition is a small, additive, non-restructuring change to an otherwise-untested 250-line component, verified live instead). **NEXT for the register:** #4 AGENT-MODE (0% frontend, confirmed still true — `authoring_run_service.py` is 1346 lines server-side with zero client consumers) is the only remaining item; it needs its own CLARIFY+DESIGN before BUILD (mission-control UI: start/pause/resume a run, review+accept/reject per-unit reports) — user has not yet greenlit starting it.

**#16 CHAPTER-EDITOR-PARITY-AND-RETIREMENT — SPEC COMPLETE 2026-07-05** (branch `feat/context-budget-law`, spec [`16_chapter_editor_parity_and_retirement.md`](../specs/2026-07-01-writing-studio/16_chapter_editor_parity_and_retirement.md)). Phase 4 (the last phase) shipped in two parts:

1. **Phase 4a — M6 (mobile shell) resolved: responsive Studio chrome, not a separate mobile UI.** User's direction: Studio's dockview frame already renders acceptably on mobile for a single open panel — "the hard thing is only the tab control and individual panel responsive." Live-verified (chrome-devtools `emulate({viewport:'390x844x2,mobile,touch'})` — an earlier `resize_page` call had silently floored at 500px width and produced false readings) 4 real, severe bugs: (1) dockview's own tab overflow dropdown already works correctly, no fix needed; (2) `EditorPanel`'s action toolbar (Grammar/Save/Publish/…) had no overflow handling — Save/Publish were unreachable off-screen; (3) `FormatToolbar`'s `flex-wrap` rich-text toolbar wrapped to 2-3 rows that visually collided with the sticky-scrolled prose beneath; (4) `SceneRail`'s fixed 224px width left ~166px for prose on a 390px phone — confirmed live, real chapter text wrapped one word per line. Fixed: both toolbars → `flex-nowrap overflow-x-auto` (scroll, not wrap/clip); Scene Rail's auto-open-when-scenes-exist default now also checks `!useIsMobile()` (explicit user toggle still wins); `useStudioChrome`'s sidebar now defaults collapsed on a first mobile visit only (persisted preference always wins). Fixing (2)+(3) exposed a secondary bug — `InlineAiLayer`'s "Continue from cursor" floating button (`absolute right-2 top-2`, pinned regardless of toolbar scroll) then covered Undo/Redo at full scroll — fixed with a `w-60` trailing spacer in `FormatToolbar` reserving scroll room. **Caught mid-build:** my first `useIsMobile()` placement in `EditorPanel` was called AFTER the `!unit || !chapterId` early return — a Rules-of-Hooks violation React's dev overlay caught immediately ("Rendered more hooks than during the previous render") on live reload; fixed by moving the call above the early return. Files: `FormatToolbar.tsx`, `EditorPanel.tsx`, `useStudioChrome.ts` + tests. VERIFY: `tsc` clean, 19 unit tests (5 new) green, pure-CSS fixes verified by live before/after screenshots (jsdom can't assert real overflow/wrap layout); `/review-impl` self-check — no HIGH/MED, no standards touched (pure frontend layout).
2. **Phase 4b — M9 resolved: keep `ChapterEditorPage.tsx`, don't delete.** User's call, superseding the original "delete after a soak period" plan: the legacy page stays alive indefinitely (no route change either), marked with a prominent top-of-file deprecation banner instructing any agent/human that it's superseded by Studio's `EditorPanel`, new work belongs in Studio, and "the chapter editor" in a task almost always means Studio now. Cheaper and safer than an actual deletion (no risk of an undiscovered live dependency).

**Spec 16 is now fully complete** (Phases 1-4). The "Cursor-for-novels" #1 COHERENCE register item (memory `writing-studio-fragmented-not-underbuilt`) is done. **NEXT:** no further action required on #16; check `docs/specs/2026-07-01-writing-studio/00_OVERVIEW.md` for the next unscoped row if picking up fresh work in this track.

**STUDIO DEFAULT-WELCOME + COMPOSE SESSION/MODEL RESTORE — SHIPPED 2026-07-05** (branch `feat/context-budget-law`). Two user-reported UX papercuts:

1. **`D-STUDIO-DEFAULT-WELCOME`** (`frontend/src/features/studio/hooks/useStudioLayout.ts`): reopening the studio restored not just the panel layout but whichever panel was last ACTIVE, so leaving it on e.g. Chapter Browser meant every reopen landed there instead of the studio's own landing page. Fix: on a restored layout, if `welcome` is still present, `api.getPanel('welcome')?.api.setActive()`. Deliberately does NOT re-add Welcome if the user closed it (respects a deliberate close instead of fighting it every reopen).
2. **`D-COMPOSE-SESSION-RESTORE`** (chat-service + frontend): the Compose panel showed the "Start New Chat" model picker on every studio reopen, even with a prior session for the book — because a chat session had no durable link to its book, only an optional knowledge-project id (`project_id`), which stays NULL forever for a book with no KG project (the common case). Added a `book_id` column to `chat_sessions` (migration, model, create/list endpoints — `?book_id=` filter added to `GET /v1/chat/sessions`), set at creation time from the Compose host's `bookId`. `useEmbeddedChatBinding` now matches by `book_id` first, falls back to the pre-existing `project_id` match for never-retagged legacy sessions. **A second real bug surfaced live during verification, not caught by the first pass of unit tests**: a brand-new 0-message session has `last_message_at: null`, sorts to the very bottom under `ORDER BY ... NULLS LAST`, and can fall outside the generically-loaded session page — the exact `D-CHAT-URL-SESSION-ACTIVATION` bug class recurring in a second code path. Fixed with a direct `book_id`-scoped fallback fetch (reusing the new list filter) when no local match is found, mirroring the page-mode provider's own direct-fetch safety net. **VERIFY:** live-verified end-to-end (created a session, reloaded the studio, Compose restored the exact session + Gemma-4 26B-A4B QAT model with zero picker) — this second bug was only caught by that live pass, not by unit tests written from the first (incomplete) understanding of the fix. 15 hook tests (`useEmbeddedChatBinding`) + 7 layout tests (`useStudioLayout`) + 28 sessions-router tests, all green; full chat-service suite 974/975 (1 pre-existing unrelated failure — a concurrent session's studio-panel enum drift in `frontend_tools.py`); full FE chat+studio suites 1270/1270, tsc/eslint clean.

**#19 WAVE 2 — GUIDEBODYKEY CONTENT FANOUT + ROLE-SPECIFIC TOURS — SHIPPED 2026-07-05** (branch `feat/context-budget-law`, commit `aa4144d7c`, spec [`19_onboarding_and_user_guide.md`](../specs/2026-07-01-writing-studio/19_onboarding_and_user_guide.md)). Completes #19: `StudioPanelDef` gains `tourAnchor?: string` (the panel's root `data-testid`, catches the one outlier `knowledge` → `studio-knowledge-hub-panel` that a derived `studio-${id}-panel` string would get wrong); all 47 non-hidden catalog panels get a dedicated `guideBodyKey` paragraph across en/ja/vi/zh-TW — English drafted via 9 parallel category-scoped agents (mirroring #18's 9 categories), translated via 3 parallel per-language agents, merged with an idempotent Node script (same recovery pattern Wave 1 used for its locale-collision incident). 5 new role-specific tours (`writer`/`worldbuilder`/`translator`/`enricher`/`manager`) added to `tours.ts` via a `roleStep()` helper that reads `target` from the catalog `tourAnchor` (throws at module-init if missing, so a spec-authoring mistake fails loudly); "Studio: Start Guided Tour" now starts `tour.start(onboarding.role ?? 'core')`. **Live E2E caught a real cross-hook bug during VERIFY** (exactly the kind of thing unit tests can't see): `studioRole` is a server-synced ACCOUNT-level pref, so a role picked by one E2E test in `studio-onboarding.spec.ts` stuck for every later test in the file — the pre-existing "core tour" test silently ran the leftover `worldbuilder` tour instead and failed on an unrelated selector; also found the UI's own Skip button never clears a role (by design, only sets the seen-flag) — there was no UI-only way to reset. Fixed with a new `resetStudioRolePref` E2E API helper (direct `PATCH /v1/me/preferences`) plus a new live test running the `worldbuilder` tour end-to-end (glossary → wiki → knowledge), proving `tourAnchor` resolution actually works, including the `knowledge` outlier. **VERIFY:** 13 new unit tests, 744/744 studio suite green, tsc/eslint clean; live E2E 5/5 `studio-onboarding.spec.ts` + 13/13 adjacent Studio specs (`writing-studio`, `studio-palette`), all against the real vite dev server. **#19 is now fully done (Wave 1 + Wave 2).**

**CHAPTER-STATUS BUG + TOOLS/SKILLS BROWSER REDESIGN — SHIPPED 2026-07-05** (branch `feat/context-budget-law`). Three user-reported issues from this session:

1. **`D-CHAPTER-LIST-STATUS-MISSING` fixed** (`services/book-service/internal/api/server.go`): a published book's chapters showed as "draft" in the Chapter Browser. Root cause: `listChapters` (offset) and `listChaptersKeyset` (manuscript navigator) never included `editorial_status`/`published_revision_id` in their SELECT + JSON response — every chapter row came back with `editorial_status: undefined`, which the FE's `chapterStatusVariant` ternary (`ChapterBrowserTitleView.tsx`) silently defaults to `'draft'`. Fixed both endpoints (mirrors the pattern already correct in `getRevision`/`getInternalBookChapters`). New DB-gated regression test `chapter_list_editorial_status_db_test.go` (2 tests, real publish via `publishViaConfirm`) + live-verified against the real POC book (`019f1783-ebb4-78de-ac9d-0dfba6539b7c`): all 12 chapters now correctly show `published` + a real `published_revision_id`, confirmed via HTTP + a live browser screenshot.
2. **`D-CHAPTER-BLOCKS-STALE-EXTRACTION` re-verified holding** (no new code, per user's own call after confirming there's no second "draft-html" content type to generalize an audit tool for — `fn_extract_chapter_blocks` is the ONLY such extraction trigger in the repo). Dev-DB spot-check: 13989/13990 (99.99%) `chapter_drafts` rows have proper Tiptap-object bodies; the one exception is a single pre-existing stray row (chapter "Chương 1", book `019f16e4-1c94-7bfd-892d-0fe47fa9e018`) whose `body` is a raw string, not parsed Tiptap JSON — not reproducible from any current ingestion code path (all 6 real `INSERT INTO chapters` sites always set `title`+ well-formed bodies), practical fix is just reopening+resaving that one chapter in the editor. Not chased further (isolated one-off, not a systemic gap).
3. **Tools/skills browser full UI/UX redesign** (`frontend/src/features/chat/components/ToolSkillAddModal.tsx` + new `frontend/src/features/chat/hooks/useToolSkillCatalog.ts`): the chat-GUI "+ Add" modal (`AgentContextRack`) was a flat, uncategorized, hard-capped-at-50 list over what's now **175 real tools** — exactly the "too many, no way to find things" complaint. Rebuilt on `FormDialog` (was a hand-rolled `fixed inset-0` overlay) with: category chips computed from `item.domain` (the BE's already-shipped, always-in-sync tool-name-prefix field — deliberately NOT the rack's separate `serverKeyForTool`/`PREFIX_TO_SERVER` mirror, which is pinned 1:1 against a *different* backend table for a *different* feature and would have needed an unrelated cross-service pin change); an "All" view grouped by category with a 5-item preview + "See all N →" drill-in; a flat, real `Pagination` (20/page) once a category or search narrows it; `EmptyState` for no-results. Live-verified in the real studio (175 tools across 14 categories, category-chip narrowing, search+category combined empty state, Skills tab with all 4 real skills) via Playwright against the vite dev server. **`/review-impl` caught + fixed one real MVC-standard violation**: the first version was 351 lines mixing data-fetch/filter/pagination state directly in the component (violates CLAUDE.md's "hooks own logic, components render" + ~100-line guideline) — extracted into `useToolSkillCatalog` (161 lines); the extraction itself caught a real bug via `tsc` (arrow-key tab-switch passed a numeric index where a tab string was expected). Also added a pagination-boundary test (25+2 tools in one category → page-1/page-2 slice) that the original fixtures (4 tools total) never exercised. 10/10 component tests green, full chat suite 544/544 green, tsc + eslint clean.

**#19 WAVE 1 — STUDIO ONBOARDING + CATALOG-DRIVEN USER GUIDE — SHIPPED 2026-07-05** (branch `feat/context-budget-law`, spec [`19_onboarding_and_user_guide.md`](../specs/2026-07-01-writing-studio/19_onboarding_and_user_guide.md)). New `features/studio/onboarding/` module: `useStudioOnboarding` (server-synced `hasSeenStudioOnboarding`/`studioRole` prefs via the existing `@/lib/syncPrefs`, mirrors the global `useOnboarding` hook's shape) + `StudioOnboardingOverlay` (role-picker, built on the shared `FormDialog` — not a hand-rolled overlay) + `useStudioTour`/`StudioGuidedTour`/`StudioTourTooltip` (a `core` 4-step react-joyride tour with real resilience: idempotent `onOpenPanel` before every step so a manually-closed panel self-heals, a 4s anchor-wait timeout that skips instead of hanging, z-index above dockview/palette, palette-hotkey suppressed while active, custom accessible tooltip with focus management + Esc-to-skip + `aria-live`). New catalog-driven `user-guide` panel (`UserGuidePanel.tsx`) renders all 46 openable panels grouped by #18's category with working Open buttons — zero hand-authored docs, editing a catalog entry is the only maintenance surface. `WelcomePanel` extended (not replaced) with role-tailored quick-links + an Open User Guide button. Two new Command Palette commands ("Studio: Choose Your Focus" / "Studio: Start Guided Tour"). BE `panel_id` enum + `contracts/frontend-tools.contract.json` regenerated for `user-guide`. **Simplified from the original spec draft during BUILD** (documented in the spec's decision table, not silently): single-step `FormDialog`-based overlay instead of a two-step raw-`Dialog.*` flow; no catalog `tourAnchor` field yet (Wave 1's `core` tour hardcodes its 4 selectors directly, reusing testids that already exist); `WelcomePanel` has no direct tour-trigger button (the Command Palette already reaches it with zero new bus plumbing). **VERIFY:** 25 new unit tests + 721/721 full studio+pages suite green, tsc + eslint clean; live E2E (`studio-onboarding.spec.ts`, 4 tests against the real vite dev server) proves the role picker opens/dismisses/skips, the tour runs a real 3-step sequence including an actual Compose-panel-open and a clean mid-tour skip, and the User Guide panel's Open button actually opens the Editor panel — plus 26 pre-existing Studio E2E tests re-run green (zero regression from the `StudioFrame` wiring). **Environmental note:** this branch had unusually heavy concurrent-session contention on the shared i18n locale files (`studio.json` ×4) and `catalog.ts` during this build — at least 2 rounds of a concurrent session's own writes overwriting this session's in-flight additions were caught and reapplied (verified via direct `grep`/`node -e "JSON.parse(...)"` checks after every locale edit, not trusted from the harness's own "modified since read" notifications, which lagged behind actual disk state at least once). Final state re-verified key-by-key across all 4 locales before commit.

**`/review-impl` DONE (`851b4e401`) — 2 MED findings, both fixed:** (1) `[Multilingual]` `StudioTourTooltip`'s Skip/Back/Next/Done action labels were hardcoded English literals bypassing i18n entirely (every other string in the Wave 1 commit was properly localized) — fixed by routing through `t()` with new `intro.tour.actions.*` keys across en/ja/vi/zh-TW (`next` carries `{{current}}/{{total}}` interpolation); locked in with a new `StudioTourTooltip.test.tsx` asserting on keys. (2) `WelcomePanel`'s new role-highlight quick-links + Open User Guide button had zero test coverage, and a future catalog-id rename would silently drop a highlight (`getStudioPanelDef` returns undefined → filtered out → no signal) — fixed with `WelcomePanel.test.tsx`, including a drift guard asserting every `ROLE_HIGHLIGHTS` id resolves to a real catalog entry. **1 LOW finding tracked, not fixed (out of scope — see Deferred below):** `D-A11Y-AXE-CI` — the standards index claims WCAG 2.2 AA is axe-core-CI-enforced, but no axe-core wiring exists anywhere in the repo (pre-existing, repo-wide gap, not introduced by this milestone); this milestone's 2 new hand-built interactive surfaces (role dialog, tour tooltip) rely on manual a11y work (focus mgmt, Esc, aria-live) with no automated a11y-tree check. 731/731 unit tests green (10 new), tsc/eslint clean.

**NEXT:** Wave 2 (per-panel `guideBodyKey` copy + role-specific tours for the ~40 remaining panels × 4 locales) — a bounded, parallelizable content task, good agent-fanout candidate, batch per #18 category (~5 panels/batch) rather than one mega-diff.

**#18 BOOK-OPEN ROUTING + COMMAND PALETTE DOMAIN GROUPING — SHIPPED 2026-07-05** (branch `feat/context-budget-law`, spec [`18_book_open_and_palette_grouping.md`](../specs/2026-07-01-writing-studio/18_book_open_and_palette_grouping.md)). Workspace-browser book-open (`BooksPage.tsx` row) now links directly to `/books/:id/studio` instead of the classic `BookDetailPage` — classic routes are unchanged and still reachable by direct URL, just no longer the default landing surface. `StudioPanelDef` gained a `category` field (9 domain groups: editor/storyBible/knowledge/translation/enrichment/sharing/platform/discovery/jobs, assigned to all 46 openable panels, verified zero orphans); the Command Palette's flat "Panels" bucket now sub-groups by category via a fixed `CATEGORY_ORDER` sort in `useStudioCommands.ts` (i18n under the existing `palette.group.*` namespace, not a new one — reused the existing helper). A mechanical test (`panelCatalogContract.test.ts`) now fails loudly if a future panel omits `category`. **VERIFY:** 690/690 unit tests green, tsc + eslint clean, live Playwright E2E against the real vite dev server (not mocks) — new tests in `writing-studio.spec.ts` (row→Studio; `BooksPage.openBook()`→classic, no `/studio` suffix) and `studio-palette.spec.ts` (3 distinct category headers render, old flat "Panels" header gone) all pass. **Found + fixed incidentally:** `demo-pipeline-3a/3b/3c.spec.ts` all call `BooksPage.openBook()` post-creation — since the row's click target moved, `openBook()` now navigates directly to the classic route (extracted from the row's `href`) instead of clicking, so all 3 specs keep working unchanged; added `openBookInStudio()` for the new default path. **Deferred (gate #1, out of scope — different concern, found incidentally, not caused by this milestone):** `D-E2E-BOOKCREATE-SELECT-FILL` — `BooksPage.ts`'s `createBook()` calls `.languageInput.fill()` but the language field is a `<select>`, not an `<input>`/`<textarea>` — breaks `demo-pipeline-3a/3b/3c.spec.ts` at the create-book step (confirmed pre-existing; this milestone never touched that form or POM method). Fix: change to `.selectOption()`. **NEXT:** [`19_onboarding_and_user_guide.md`](../specs/2026-07-01-writing-studio/19_onboarding_and_user_guide.md) Wave 1 (Studio onboarding overlay + catalog-driven User Guide panel + `core` react-joyride tour) — spec adversarially reviewed already (found + fixed a DOCK-9 hand-rolled-overlay defect in the original draft before any code was written).

**CHAPTER BROWSER + KG UX FIXES + TRANSLATION/ENRICHMENT/SHARING/BOOK-SETTINGS DOCK FANOUT — ALL SHIPPED 2026-07-05** (this session, branch `feat/context-budget-law`, HEAD `56c8e17c6`).

1. **`D-CHAPTER-BLOCKS-STALE-EXTRACTION` cleared** (commit `a22d03642`): `fn_extract_chapter_blocks` read ONLY the client `_text` snapshot; a sibling `7b9cd4fda` fix unioned `_text`+nested-text-leaves for 4 READ paths but missed this WRITE-side trigger — any chapter saved without a client `_text` annotation got permanently-empty `chapter_blocks`, invisible until Chapter Browser's word_count/export made it visible live. Also found + fixed: the established `$.**.text` jsonpath ran in Postgres lax mode, double-visiting single-text-node blocks (silently duplicating text) — fixed to `strict $.**.text` across all 5 call sites (the trigger + 4 pre-existing reads). Added a batched backfill (`backfillChapterBlocksExtraction`), live-verified against the real dev DB: all 12 POC-book chapters got correct word counts, full-text search now finds previously-invisible chapters, bulk export returns real text.
2. **3 Knowledge-panel UX bugs fixed** (commit `73e6d9704`): `D-KG-HUB-EXTERNAL-OPEN` (opening THIS book's own KG project popped a new tab instead of the in-studio `kg-overview` panel — Phase B's 13 panels made the old fallback unnecessary for the same-book case); `D-KG-NO-CREATE-CTA` (every book-scoped `kg-*` panel's "no project yet" state had copy but no button — new shared `KgNoProjectState` component, reuses `ProjectFormModal` AS-IS with a new `initialBookId` lock); `D-KG-HUB-BOOK-SCOPE` (user-requested follow-up: the Knowledge hub panel defaulted to the global cross-book list even though it's opened FROM a book — `ProjectsBrowser` gained an optional `scopedBookId` prop, toggle-able back to "all books", never a silent narrowing).
3. **Translation/Enrichment/Sharing/Book-Settings dock fanout** (commit `56c8e17c6`, spec [`17_translation_enrichment_sharing_settings_docks.md`](../specs/2026-07-01-writing-studio/17_translation_enrichment_sharing_settings_docks.md)): 9 new panels — `sharing`, `book-settings`, `translation` + `translation-versions` (hidden singleton), and `enrichment-{compose,proposals,gaps,sources,jobs,settings}` (DOCK-8 split of `EnrichmentView`'s former 6-way tab switch, no hub). Built via 4 parallel background agents, one BE-touching fix-now along the way (`TranslateModal`/`SegmentDrilldownModal` DOCK-9 migration to `FormDialog`; `GapsPanel`'s dead-end "extract first" message got a real CTA opening `ExtractionWizard`). **`/review-impl` caught + fixed 1 real HIGH finding before commit:** the first version of `BookSettingsPanel` forked `SettingsTab`'s ~400 lines of logic instead of reusing it (DOCK-2 + SDK-First violation) — fixed by threading an optional `onOpenWorld` prop through `SettingsTab` itself (mirroring `BookWorldSection`'s own shape) so the panel could become a genuine thin wrapper. All 9 panels live-smoked in a real browser session (real API calls, Sharing's visibility toggle + full TranslateModal flow exercised as real actions). Full frontend suite green (4198/4199 — the 1 failure is a concurrent session's own in-flight work).
4. **Deferred (tracked, gate #2 — large/structural):** `D-SETTINGS-NO-GENRE-CTA` — Book Settings' "no genres" empty state has no create-CTA either, but genre-authoring's actual home (Glossary? a new admin surface?) needs a PLAN-time decision first.
5. **Multi-session note:** this branch ran several concurrent sessions throughout (context-budget-law/editor-craft, a JWT-auth refactor touching `services/translation-service/*`, a tenant-boundary-audit track) — every commit above was staged with exact pathspecs, verified via `git diff --cached --name-only` before committing, never `git add -A`.

**CONTEXT INSPECTOR GUI (Context Budget Law §11) — M1 + M2 SHIPPED 2026-07-05.** Plan [`docs/plans/2026-07-04-context-inspector-gui.md`](../plans/2026-07-04-context-inspector-gui.md) (3 milestones). **M1 BE telemetry (`54d3872c9`):** a `loreweave_context.TraceAccumulator` threads through chat assembly recording each tier decision it can MEASURE (T6 C_persist via `persist_auto_compact`, in-turn compaction, T0 wire-hygiene); the persisted per-turn `contextBudget` frame gained `raw_tokens` (= compiled + Σ savings), `reduction_pct`, ordered `trace[]` spans, `status_flags[]`, `retrieval_mode`, `intent` — all additive. New `GET /v1/chat/sessions/{id}/context-trace` (full frames + user message). `contracts/context-trace.contract.json` + `test_context_trace_contract` (conformance on the REAL emit fn) + `scripts/context-inspector-trace-gate.py` (live GATE, §13b). **Honesty:** chat claims only measurable savings (gated-grounding = status flag delta 0, not a fake cut); raw==compiled when nothing cut. *Also fixed broken HEAD:* the T3 `budget.py`/`plan.py` the committed kernel `__init__` imported were left untracked. VERIFY: chat 937 tests, provider-gate, **live real-turn GATE PASS** (every field non-null, raw==compiled+savings). **M2 FE (`6c5dea2e6` core + `887f4b246` registration):** dockable `context-inspector` panel — `features/chat/inspector/` (pure `inspectorMath` gauge/KPI/filters + `useContextTrace` self-contained hook + PressureGauge/AllocationMap[reuses ContextBreakdownPanel computeBreakdown+colors, extended to 15 cats]/CompileTrace waterfall/TurnList + ContextInspectorView container) → `ContextInspectorPanel` (studio dock) + registered in catalog/`ui_open_studio_panel` enum/contract/4 i18n. **Responsive** (rail stacks below `md`, top-bar/KPIs wrap). VERIFY: 46 FE tests + tsc clean + **live browser smoke** (vite→gateway→chat, 0 console errors, real `/context-trace` data rendered: gauge state + allocation segments). **ENTRY POINTS + AUDIT — DONE 2026-07-05 (user-requested "check lại rồi clear"):** (1) standalone `/context-inspector` route ✅ RESOLVED (App.tsx settled — route present + import; the page now reads `?session=` → `initialSessionId`). (2) Added a chat-header **Context Inspector icon** (`Gauge`, `ChatHeader`/`ChatView`) that deep-links `/context-inspector?session=<id>` on the full chat page only (embedded editor/studio surfaces withhold it — a nav-away would tear down the host). (3) Studio **command-palette** "Studio: Open Context Inspector" already catalog-driven — added a real-catalog assertion test. **All three LIVE-PROVEN in browser** (0 console errors): chat icon → deep-linked inspector renders real `/context-trace` (allocation map, compiled tokens, honest "nothing was cut" empty trace); palette opens the dock panel; empty session → honest empty state. **"(no message)" is smoke-data-only** — the W1 synthetic rows have null `parent_message_id`; real turns resolve the user message via the `parent_message_id` LEFT JOIN the normal insert path sets (`stream_service.py:2857`). 4 FE tests (`ChatHeader.inspector`, `ContextInspectorPage`, palette) + tsc clean. **M3 = §13 ENFORCEMENT — SHIPPED 2026-07-05.** Every §11a item (84) now carries `✓test:<path>::<needle>` (82) or `⊘manual:<reason>` (2 pure CSS animations). `scripts/context-inspector-checklist-gate.py` parses §11a + FAILS on any unproven box / dangling ref / needle-not-on-a-test-declaration-line; `--run` also EXECUTES the referenced pytest+vitest suites (§13c "(b) in the passing set"). Wired into `.githooks/pre-commit` (guarded to fire on spec/inspector changes) + the `lint-foundation` CI `p1-lints` matrix (static). Wrote the missing EFFECT-tests: PressureGauge/AllocationMap/CompileTrace/TurnList component tests + extended ContextInspectorView (click-load, j/k, filter-resets-page, loading/error, poll, enabled-gate, state-split, header chips, KPI values) + `test_context_trace_router.py` (endpoint/owner-gate/pagination) + ContextInspectorPanel mount/self-title. Fixed 2 real impl gaps en route: allocation tooltip missing `%`; a real interval **poll + focus-refetch** in `useContextTrace` (the "live update" item was only a manual refresh button). **§13d adversarial refute-pass** (cold-start subagent, refuted-unless-proven) found **6 real gaps — ALL FIXED**: NEW-cats (summary/chapter/reasoning) unasserted → new AllocationMap test; "live update" proven by a manual button → genuine poll; endpoint `?page&filter` over-claim → honest client-side clarifier; gate static-only → CI + parser now requires the needle on a real `it/test/def test` line (not a comment); KPI avg/saved asserted by label only → assert computed values. Gate teeth proven by 3 negative tests (unproven box / dangling needle / comment-only needle → exit 1). VERIFY: gate `--run` green (2 pytest + 12 vitest files), 72 inspector FE tests + tsc clean. **Committed live E2E** `frontend/tests/e2e/specs/context-inspector.spec.ts` (4 tests, real login/gateway/dockview; `/context-trace` mocked for determinism — BE already covered by pytest+trace-gate): chat-header icon deep-links `?session=<id>` + renders gauge/allocation/turn-list, status filter narrows live, studio Command Palette mounts the dock panel, empty session → honest empty state — **4/4 pass live** (vite :5210→gateway :3123; added `data-testid="chat-session-row"`). **`D-CHAT-URL-SESSION-ACTIVATION` — ✅ FIXED same session:** the `ChatSessionContext` restore-from-URL effect now falls back to a direct `chatApi.getSession` when the URL session is NOT in the loaded list (deep-link to an old session past page 1, or a fresh 0-message session sorting to the bottom by last-activity), so `/chat/{id}` always activates instead of silently showing an empty chat. Functional `setActiveSession` → no re-fetch loop; only fetches once the list settles (`sessionsLoading` guard). Regression-guarded by the direct-URL E2E (red pre-fix → green) + 11 chat-provider unit tests. *Multi-session note: committed via `git commit --only <paths>` to isolate from a concurrent #18 enrichment/translation-docks session's large staged index; that session also re-grouped the palette by domain (`context-inspector` now under the `editor` category) — my catalog-membership proof-ref survives it.*


**CONTEXT BUDGET LAW — T4 story_state PROJECTION WIRED 2026-07-05** (branch `feat/studio-agent-raid`, spec [`2026-07-03-context-budget-law.md`](../specs/2026-07-03-context-budget-law.md) §8 T4 row). The T4 substrate (distill/cadence/render `services/chat-service/app/services/story_state.py` + persistence/OCC `db/session_blocks.py`) was fully built + tested but had **ZERO callers** — the block was never projected. Now connected at the `stream_service.py` assembly seam via a new orchestrator `db.session_blocks.project_story_state`: each turn (flag on) it maintains the cached, bounded (≤1200 tok) story-bible block from the grounding prefix (refresh via `should_refresh` — hash/lore-gate/scene/cadence) and projects it as the **leading tail block ONLY when the turn has NO live grounding** (`kctx.context` empty — degraded / future T5-gated-empty) = the D4 safety net. New flag `story_state_block_enabled` (**default OFF** — while T5 gating is off, `build_context` returns a live prefix every turn so unconditional projection would only DUPLICATE it, a token regression; flip on together with `t5_intent_gate_enabled`). Added a `story_state` token-breakdown category. **REVIEW caught + fixed my own trigger bug:** keyed the projection on `full_context` not `stable_context` — `multi_project` mode has `stable_context=""` but a full live `context`, so keying on the prefix would false-fire and duplicate live lore (regression-guarded). **VERIFY:** 34 T4 tests green — 9 orchestrator decision-logic (incl. multi-project false-fire guard + degraded-projects-cache net) + **real-Postgres end-to-end** (maintain→degraded→project through actual `chat_session_blocks` SQL) + 3 stream wiring effect-tests (block in system prompt when on; absent + orchestrator-never-called when off) + existing story_state/session_blocks suites; **full chat suite 954 green** (1 unrelated pre-existing failure = a concurrent session's `frontend_tools.py` studio-panel enum drift, NOT T4 — I never touched that file); provider-gate clean. **D4 "unconditional projection that SUPERSEDES the live prefix" (killing the per-turn build_context pull) deferred with T5.** **NEXT for Context Budget Law:** flip T5/T4/D7/D13a defaults on + the answer-correctness gold Q&A set (sealed #7, user-validated) to measure the continuity-with-gating GATE; then D13b resume-monotonicity + close the small verified T1 gaps below.

**CONTEXT BUDGET LAW — T1 TAIL RECONCILED + composition_get_prose SHIPPED 2026-07-05** (branch `feat/context-budget-law`, manifest [`context-budget-t1-refactor-manifest.md`](../specs/context-budget-t1-refactor-manifest.md)). **The T1 manifest status table was heavily STALE** (the [[debt-batches-list-is-stale-verify-first]] pattern) — I reconciled every row against the actual `apply_response_contract` call sites + `*_REF_FIELDS` constants across all 4 services. **Finding: ~90 % of the "⏳ tracked" backlog was ALREADY done** (story_search/memory_search/memory_timeline, kg_graph/world/multi_query via a shared subgraph projection, kg_entity_edge_timeline/triage_list, composition motif_search/book_list/suggest/arc_suggest, translation list_versions/job_status) — the header table just never got updated. **Refactored the one clear remaining dump: `composition_get_prose`** — added `detail=summary` (drops the heavy chapter `body`, keeps `draft_version`+metadata+a `body_omitted` marker via the pure `_project_prose` helper; never a silent drop). Composition is single-schema-source (no `definitions.py` mirror — unlike knowledge's 3-source footgun). **VERIFY:** `test_prose_response_contract.py` (5) + MCP wire test (40, new `detail` arg registers cleanly) + full composition unit suite 1498 green; provider-gate clean. **T1 IS NOW COMPLETE:** I then verified every tool I'd flagged `⏳ verify-at-pickup` — all (`translation_coverage`/`segment_status`, `kg_schema_read`/`list_templates`/`view_read`/`project_list`, `motif_link_list`, `memory_recall_entity`) already carry a documented `@small_return:` note (scalar-only / bounded-metadata reads, no heavy body) → marked 🟢. So **every SET-returning MCP tool is either `apply_response_contract`-refactored or documented-exempt — no un-refactored dump-risk tools remain.** One latent hardening tracked (`D-T1-SMALLRETURN-ENFORCE`, LOW): `@small_return` is a self-report comment, unenforced by the snapshot harness — a heavy field added to a 🟢 tool wouldn't go red; fold a per-tool size-budget assertion into the A5 byte-histogram work.

**CONTEXT BUDGET LAW — T6/D13a REVERSIBLE DUP-READ COLLAPSE SHIPPED 2026-07-05** (branch `feat/context-budget-law`, spec §8 T6/D13a bullet). New deterministic tier-0 in the shared kernel `loreweave_context.compaction` (`_collapse_duplicate_reads`): when a compaction pass fires AND `settings.compact_collapse_duplicates_enabled` (**default OFF**), an EXACT-duplicate tool result (model re-read an unchanged resource) is replaced with a short reference, keeping the most-recent full copy. Reversible (raw stays in Postgres) + **orphan-safe by construction** (only rewrites `content`, never removes a message → all tool_call pairings survive). `CompactionReport.duplicates_collapsed` added; wired at both chat compaction call sites. The atom-integrity/orphan GATE was already met by the existing `TestToolPairSafety`; D13a adds the collapse transform + its own orphan test. **VERIFY:** 6 tests + full chat suite 972 green (default off → inert). **Deferred:** D13b resume-monotonicity stays PARTIAL (separate, structural). **This session's Context Budget Law run:** T4 story_state projection (`2cdfe340e`) · T6/D7 single-item overflow (`356d5d115`) · T2 LOW-2 category parity + story_state-drop fix (`e42ba73b0`) · T6/D13a dup-read collapse — 4 milestones, all chat-service/kernel, staged with exact pathspecs amid concurrent sessions.

**CONTEXT BUDGET LAW — T2 LOW-2 (category parity) CLEARED 2026-07-05** (branch `feat/context-budget-law`). Added a **cross-language parity guard** for the allocation-map category vocabulary: chat-service `token_budget.BREAKDOWN_CATEGORIES` (SoT) writes its ordered list into `contracts/context-trace.contract.json` (`breakdown_categories`); FE `ContextBreakdownPanel.BREAKDOWN_CATEGORIES` is asserted **equal** to it. **This surfaced + fixed a real regression from my own T4 commit:** `story_state` was added to the emit `categories` dict but NOT to `BREAKDOWN_CATEGORIES`, so `to_payload()` silently dropped it — the Inspector would never have shown the safety-net block's tokens. `story_state` is now first-class on both sides (BE tuple + `_BASELINE_CATEGORIES`; FE `BREAKDOWN_CATEGORIES` + `CATEGORY_COLORS`/`CATEGORY_HEX` + `ContextBreakdownMap` type). **VERIFY:** BE chat suite 962 green (+story_state-emitted test + contract regen), FE chat suite 545 green (+FE⇄BE parity test), tsc clean. Files: `token_budget.py`, `ContextBreakdownPanel.tsx`, `types.ts`, `contracts/context-trace.contract.json`, `test_token_budget.py`, `test_context_trace_contract.py`, `ContextBreakdownPanel.test.tsx`.

**CONTEXT BUDGET LAW — T6/D7 SINGLE-ITEM OVERFLOW SHIPPED 2026-07-05** (branch `feat/context-budget-law`, spec §8 T6/D7 bullet). A single successful MCP tool result over `settings.tool_result_token_cap` (**default 8000 est-tokens, ON**; 0 disables) is withheld at the generic dispatch site (`stream_service.py` success path) and replaced with a **self-correcting overflow notice** (`{"error":"tool_result_overflow", tool, tokens, cap, message}`; the message names the tool + remedies `detail=summary`/`limit`/`fields`/id-range) — never a silent truncation, never a window-blowing dump (the 146K single-dump class). New helper `tool_result_content_capped` in `tool_result_wire.py` (pure `tool_result_content` untouched). Caps ONLY re-requestable data dumps — generative `{"prose":…}` (different site) + error payloads bypass; the withheld message keeps its `tool_call_id` (no orphan). **Default ON** because it's *self-correcting* (model re-calls, turn preserved), not a token-neutral change. **VERIFY:** 7 tests (5 helper + 2 dispatch wiring); full chat suite 961 green (default cap trips nothing); provider-gate clean. **Concurrent-session heads-up:** this is a live behavior change on the tool loop — a tool returning >8000-tok results now gets the notice; flip `tool_result_token_cap=0` to disable. **Deferred (small):** Inspector trace surfacing of D7 (accumulator not threaded into the tool loop) + per-tool exempt-allowlist if a legit large un-scopable read tool surfaces; D7's reasoning-budget half is separate.

**▶ P2 ENTERPRISE STRUCTURAL HARDENING** (spec [`2026-07-04-enterprise-p2-structural.md`](../specs/2026-07-04-enterprise-p2-structural.md) = system-of-record). SHIPPED this run: **G** (no-op, verified) · **B1** (KEK sha256) · **A1** (10-Go-main obs fleet + `/review-impl` Standards gate) · **A2a** (Python `setup_logging`) · **B2** (retention sweeper + embed cost + route-parity D-S4C fix + outbox purge) · **C 4/6** (dedup, noop-warn, PII-redact, opt-out; 2 slices tracked) · **D** (latency SLO SoT + lint) · **F** (tenant-boundary audit — `tenant_access_audit` append-only table + coalesced first-per-window emit in book-service `authBook` + glossary-service `checkGrant`; injectable `emitTenantAudit` hook; 9 decision tests + insert-shape/bucket tests green). **E** (salience↔learning — ✅ RESOLVED, documented keep-separate: [`2026-07-05-salience-learning-boundary.md`](../specs/2026-07-05-salience-learning-boundary.md); tracked `D-E-SALIENCE-LEARNING-BRIDGE` revisit-gated) · **A2b** (✅ SHIPPED — RETIRED `contracts/logging` Go module [0 adopters] + repointed lint/inventory/standard to slog+`sdks/go/observability`; 0 backend TS `console.*` [api-gateway-bff & ai-gateway NestJS Logger + game-server `src/log.ts`]; tsc clean ×3, ai-gateway tests green). **✅ P2 STRUCTURAL HARDENING COMPLETE — all workstreams A1 · A2a · A2b · B1 · B2 · C-core · D · E · F · G shipped or resolved.** **✅ `/review-impl` DONE (2 cold-start adversarial reviewers on F tenant-iso + A2b deletion) + all findings fixed:** F MED-1 (glossary logged OD-8-denied as `granted` → fixed + regression test), MED-2 (write-amplification → in-process dedup cache), MED-3 (real-PG dedup test, **LIVE-PROVEN** vs dev PG); A2b MED (sdk-first.md contradicted the retire → fixed) + LOW (sdk-dup-gate/dashboard cleanup). **Recently cleared defers:** `D-A2B-TS-CONSOLE-LINT` (✅ BUILT — HARD backend-`console.*` lint check, baseline 0, negative-proven; A2b's regression gate); `D-F-AUDIT-LIVE-SMOKE` **partially cleared** (DB-effect dedup/ON-CONFLICT/CHECK live-proven; only the full HTTP cross-tenant E2E remains). **P2 Deferred tail (tracked, none blocking):** `D-F-AUDIT-HTTP-E2E` (cross-tenant read through the real HTTP stack → row; needs scratch stack) · `D-A1-CALLSITE-SWEEP` (per-service slog ctx-thread, Tempo-gated) · `D-D-PERF-NIGHTLY` (p95 assertion, no harness) · `D-C-PRODUCER-OUTBOX` · `D-C-FE-I18N` · B2 live-smokes (`D-B2-{RETENTION,PARITY}-LIVE-SMOKE`, `D-B2-RERANK-WEBSEARCH-PRICING`) · `D-C-DEDUP-LIVE-SMOKE`.

**▶ P3 = SDK-first: JWT verifier + shared types** (user-chosen next tier; audit had no P3). **CLARIFY finding: the audit was STALE** — the JWT consolidation was ~90% already done (Go: all 7 domain services import `contracts/platformjwt`, auth is minter, 0 left; `TerminalEvent` already aliased to `contracts/notifyevent`). **Slice 1 ✅ SHIPPED — the last 2 Python hand-rollers migrated** to `loreweave_authn`: translation-service (deps.py `get_current_user` + confirm-replay `verify_access_token` + removed dead `verify_request_jwt`) + video-gen (`extract_user_id`); test fixtures updated to mint realistic tokens (`exp` required + UUID `sub`, the SDK's stricter+correct posture). Full suites green (**translation 1038, video-gen 58**). **Slice 2 ✅ SHIPPED — TS alg-confusion fix:** 3 un-pinned `jwt.verify` sites in api-gateway-bff (notifications.controller / ws.events.gateway / ws.ticket-endpoint) now pin `{algorithms:['HS256']}` (matching tools.controller); tsc clean, 104 tests green. **Enforcement:** new `py-jwt-verifier` rule in `sdk-duplication-gate.py` (assignment-anchored HS256 `jwt.decode` → red; negative-proven, ignores docstrings/RS256-admin/verify_signature=False stub); baseline clean. **Slice 3 = `BaseInternalClient` — IN PROGRESS (user chose FULL build).** INVENTORY (subagent): ~48 client impls / ~40 files / 10 services. **Key design finding: a "one base, uniform policy" would be WRONG** — fail-posture is per-METHOD (degrade/raise/swallow/verbatim-passthrough coexist in one class), so the SDK provides COMPOSABLE MECHANICS, not imposed policy. **SDK built: `sdks/python/loreweave_internal_client`** (`build_internal_client` factory [token+JSON headers + uniform per-request X-Trace-Id event-hook + httpx.Timeout], `InternalClientError`+`is_retryable_status`/`RETRYABLE_STATUSES`={429,502,503} collapsing ~5 dup error classes, `resolve_model_name` collapsing the 5 byte-identical copies; 8 SDK tests green). Registered in shared `sdks/python/pyproject.toml` include (else `pip install /sdk` omits it → runtime ImportError). **Wave 1 ✅ — model_name collapse:** all 5 `model_name.py` (translation/knowledge/composition/campaign/video) → thin shims over the SDK; per-service tests green + a 6TH copy (lore-enrichment) collapsed to a shim during review (video 6, campaign 7, composition 65, knowledge 26, translation 41, LE 163 — respx/monkeypatch intercept the SDK's httpx transparently). **Wave 2 ✅ SHIPPED (`993c0297e`) — LE error unification:** the 5 lore-enrichment client error classes subclass `InternalClientError` (removed ~8 dup retryable-derivations); LE 955 passed. **Review-catch:** writeback's 2 SYNTHETIC `status_code=502` markers (missing-owner, unplaceable-kind) are hard semantic failures — given explicit `retryable=False` so the base doesn't flip them True. **✅ `/review-impl` DONE (cold-start reviewer) on SDK+W1+W2 — no HIGH; fixes applied:** MED (SDK had no regression gate) → new `py-model-name-copy` rule in `sdk-duplication-gate.py` (negative-proven; worker-ai's client-method copy baselined until its wave) + migrated LE's 6th `model_name` copy; LOW → `RETRYABLE_STATUSES` 504-caveat comment, `sdk-first.md` row, a `transport=None`-default SDK test (now 9). **✅ SLICE 3 COMPLETE — W2-tail + W3 + W4 all shipped (7 commits `9381ec46a`·`25cf4c10d`·`9ea37f8b9`·`cbac6dd35`·`07e7e1c7a`·`783ddd4ed`).** **W2-tail (`9381ec46a`):** knowledge+composition `EmbeddingError` → `InternalClientError` (raise site passes `status_code`, base derives retryable — inline `in (502,503,429)` gone); worker-ai degrade-posture result dataclasses use `is_retryable_status`; campaign `BookServiceError` → `InternalClientError`. New `py-inline-retryable` gate rule (matches EXACTLY the 3-element {429,502,503} set so LE's 504-INCLUSIVE `complete.py` list is correctly NOT flagged; regex teeth unit-checked; empty baseline). **W3 (`25cf`/`9ea3`/`cbac`):** `build_internal_client` adopted by 12 single-auth clients (LE book/kal; knowledge book/book_profile/embedding/reranker/translation/ontology; composition embedding/web_search/glossary/kal) + fixed the comp `grant_client` forgotten `trace_id_provider` (real live trace gap). **W4 (`07e7e1c7a`):** worker-ai `get_model_name` → `resolve_model_name` (LAST model_name copy gone → `py-model-name-copy` baseline now EMPTY; gate baseline 13→11); campaign `DispatchError` → `InternalClientError`; knowledge `glossary_client` → `build_internal_client` (13th; **circuit breaker preserved, transport-only swap**; `test_trace_id_propagation` updated to build via the factory so it exercises the REAL trace event-hook path). **Documented-bespoke (SDK's acknowledged per-method exceptions, `sdk-first.md`):** comp book/knowledge (JWT-Bearer-forward + `BookClientError` router-mapped status/code/detail), chat knowledge_client (2 hosts + MCP), LE glossary/knowledge (dual-auth), LE writeback (multi-host 3 base URLs), jobs control (verbatim passthrough) — composable-mechanics working as designed, NOT un-migrated backlog. **VERIFY:** per-service subsets green (LE 1557, knowledge glossary/circuit/trace 133, composition 96, campaign dispatch/saga 40, worker-ai provider 56); `sdk-duplication-gate` OK (baseline 11). **✅ `/review-impl` on W2-tail/W3/W4 DONE (cold-start reviewer, fixes `1e9910756`) — verdict CLEAN, no HIGH/MED** (empirically ruled out vs installed httpx 0.27.2: no `tid` NameError, `_headers` merge preserves the baked token, EmbeddingError retryable value-identity [400→F, 429/502/503→T, transport→explicit T, empty-probe→F], worker-ai model_name delegation identity, no URL double-prefix, provider-gateway invariant upheld). Fixed: COSMETIC (W4 kwarg deletions glued a few glossary_client call lines → re-split; py_compile OK + 280 tests green) + LOW (broadened `py-inline-retryable` regex to a permissive bracket class `[(\[{]…[)\]}]` so a future set/list `{429,502,503}`/`[429,502,503]` form is caught, not just a tuple). Accepted no-change LOW: the factory bakes `Content-Type: application/json` onto bodyless GETs (harmless — internal FastAPI routes with no body param ignore it; the factory's documented behavior). **P3 recently CLEARED:** ✅ `D-P3-LORE-ENRICH-JWT` (`c6f206ce3`) — it was NOT a harmless stub: LE `app/api/principal.py` decoded the bearer `verify_signature=False` while feeding user-scoped routes that run PAID BYOK compose + user-scoped data (a forgeable `sub` = impersonate any user). The "later auth cycle" defer failed the anti-laziness gate (JWT_SECRET already wired, `loreweave_authn` exists, 8 other services done) → fixed now: verifies via `loreweave_authn` (`UUID(claims.subject)` — subject is a STR, owner-checks compare UUID), anonymous-on-bad-token posture preserved; 6-test regression lock (forged-signature→None) + 11 fixture files re-minted; LE 956 green. **P3 recently CLEARED — `D-P3-EPHEMERAL-CLIENTS` ✅ (W5, user chose "all 45"):** the ephemeral per-call `async with httpx.AsyncClient(...)` sites now build via `build_internal_client` (token+JSON baked). **W5a (`4734851df`) non-translation — 12 sites/7 svcs:** chat billing/provider/voice, jobs control/reconcile, comp notification/billing, learning knowledge_client, knowledge default_model, video-gen generate, LE judge_binding/complete (LE kept the CJK-charset per-request Content-Type). **W5b translation — 31 sites/12 files:** book_client, mcp/estimate, routers/{extraction,glossary_translate}, workers/{chapter_worker,cost,extraction_replay,extraction_worker,glossary_client,kal_client,knowledge_client,mention_backfill}. Granular `httpx.Timeout(connect,read,…)` → `timeout_s`+`connect_timeout_s`; `mention_backfill` multi-host → `base_url=""` + absolute URLs; `kal_client` keeps per-request `X-User-Id` (merges with baked token). **2 sites deliberately EXCLUDED (no-auth public reads):** `extraction_model.py` + `chapter_worker.py:765` hit public `/v1/model-registry/` with no token — baking the platform token would be a credential-leak behavior change. **`/review-impl` (W5) DONE — 3 fixes applied:** MED orphaned-timeout-constant footgun (`_TIMEOUT`/`_CHAPTER_TIMEOUT` still `httpx.Timeout(...)` but call sites hardcoded the literal → silent no-op on edit; rewired to float constants) in cost/estimate/extraction_replay; LOW dead `import httpx` removed (extraction_worker, extraction_replay) — test_extraction_worker's 9 `patch.object(ew.httpx,"AsyncClient")` seams repointed to `ew.build_internal_client` (matches the other 4 repointed test files); COSMETIC duplicate `build_internal_client` import (sed double-insert) in the 2 routers. VERIFY: translation broad subset 399 green + 75 on the 4 repointed files + 40 on extraction_worker/replay/cost/estimate; provider-gate clean. Standards gate clean (cost/estimate hit provider-registry's internal pricing route, not a provider SDK; Python=AI/LLM; token via env).

**WIKI DOCKABLE MIGRATION — FULLY DONE 2026-07-04** (follows the same pattern as Glossary/KG:
CLARIFY → design-review-before-PLAN → BUILD → adversarial `/review-impl`). Narrow surface (no
Phase A/B split needed): `wiki` + `wiki-editor` (params-retargeting singleton, editor/book-reader/
json-editor precedent) are real dock panels; both classic routes (`WikiTab`, `WikiEditorPage`) are
now thin callers of shared `WikiWorkspace`/`WikiEditorWorkspace` components (DOCK-2). Fixed 2
DOCK-9 hand-rolled modals, 6 DOCK-7 navigate/Link sites, wired a previously-dead History button,
and — the one genuine new-risk finding from design review — added a **G7 dirty-guard** on
`wiki-editor`'s params-retargeting (a naive singleton would have silently discarded unsaved prose
the instant a user opened a different article mid-edit; also fixed the same pre-existing bug on
the classic page's Back button, which had no dirty-guard at all before this).
**Follow-up same day, user-requested — second `/review-impl` + live E2E + live smoke, ALL
CLOSED (`cc707dfd8`, `d42a00d69`, `88cbf0133`):** a fresh review-impl pass found a DOCK-10 gap
(unsaved edit lost on dock-tab CLOSE, not just retarget) — fixed with a module-level draft cache.
A new live Playwright E2E suite (`wiki-panels.spec.ts`, real backend/dockview/TiptapEditor, no
mocks) then found 3 MORE live-only bugs unit tests structurally couldn't catch (title-refinement
parent/child effect race, TiptapEditor's own spurious unmount `onUpdate`, a StrictMode-exposed
non-idempotent cache-restore effect) — all fixed. A manual live-smoke via Playwright MCP at
narrow dock widths (user asked "is this responsive?") then found and fixed 5 more overflow bugs
across both `wiki`/`wiki-editor` panels (clipped Save button, off-screen action buttons, a
fixed-width float squeezing prose unreadably narrow, a hardcoded height that first left dead
space then over-corrected into hard-clipping content, and an oversized fixed sidebar). Full
narrative + verify evidence for all three rounds: [`15a_wiki_panels.md`](../specs/2026-07-01-writing-studio/15a_wiki_panels.md).
**No defer/debt rows for Wiki** — every finding across all three rounds was fixed in-session, not
deferred. **Note for the next session:** this branch is running several concurrent sessions
at once (KG, Chapter-Editor-Parity/COHERENCE, context-budget-law, utility-panels all landed
commits mid-way through this one) — re-verify shared spine files (`catalog.ts`, `studio.json` x4,
`frontend_tools.py`, the contract) before trusting this note's file list is still current.

**KNOWLEDGE/KG DOCKABLE MIGRATION — FULLY DONE 2026-07-04** (commits `4c50f7ae2` Phase A, `5c43a36c9` Phase B, `d9d21a262`/`b88e07ba7` docs, `9098f9ce0` studioLinks wiring, `21bae112a` E2E). All 13 panels (`knowledge` hub + 12 `kg-*` capability panels) built, wired into the studio link resolver, and **live-proven**: `frontend/tests/e2e/specs/kg-panels.spec.ts` opens every one through the real Command Palette against the real backend — 17/17 passing (ran via `docker` stack + `vite --port 5199`; the baked `:5174` image is stale for this work). Decision recorded: `KnowledgePage`/`ProjectDetailShell`/`KnowledgeOntologyTab` are **NOT** retired into redirects — matches wave-1's own documented precedent (`11_dockable_migration.md`) of keeping classic routes as multi-device/non-studio entry points; Knowledge's case is harder than wave-1's (no reliable book to redirect a global hub or standalone project into, Studio is desktop-first). See [[kg-dockable-migration-phase-a]] memory for full detail. Remaining, still deferred: cross-panel E2E beyond what's already covered (hub → other capability panels).

> **"CURSOR-FOR-NOVELS" REGISTER — #1 COHERENCE Phase 2 ✅ COMPLETE 2026-07-05** (spec
> [`16_chapter_editor_parity_and_retirement.md`](../specs/2026-07-01-writing-studio/16_chapter_editor_parity_and_retirement.md),
> plan [`2026-07-04-writing-studio-phase2-editor-craft.md`](../plans/2026-07-04-writing-studio-phase2-editor-craft.md)).
> All 11 editor-craft UX gaps from the Phase 1 capability audit shipped in one continuous L-size
> run: grammar check, glossary inline decoration/autocomplete, mention heatmap, AI-provenance
> tracking+toolbar, selection toolbar/inline-AI, focus mode, auto-save (300s debounce),
> progress-reporting, image/video upload-context (**redesigned** module singleton →
> per-editor-instance via `editor.storage.mediaUpload` — a module singleton is a multi-tab/
> multi-window landmine), original-source viewer (`OriginalSourcePanel`, new dock panel), and
> popout Compose (`StudioPopoutHost` at `/studio/popout` — a REAL OS-window pop-out per the
> user's explicit ask for multi-monitor support, reusing the T5.4 M4 `PopoutBridge`/
> `popoutChannel` mechanism generalized with a `route` prop). M7 (Classic/AI editor-mode
> toggle) — user decision: **do NOT port**, conscious won't-fix (Studio has no such toggle
> concept; recorded in spec 16).
>
> **`/review-impl` found + fixed 1 HIGH:** the popout Compose Apply path was fire-and-forget —
> if the user pops out Compose on chapter A then switches the main-window editor to chapter B,
> the opener's `usePopoutInsertRelay` unsubscribes from channel (book, A) on chapterId change,
> so an Apply from the still-open popout would **silently drop the edit while reporting
> "Applied ✓"** to both user and LLM. Fixed with a request/ack correlation protocol: optional
> `reqId` on `insert-prose`, matching `insert-ack` reply, `Promise<boolean>` + 4s-timeout on the
> sender — backward-compatible with the legacy un-acked `PopoutHost` sender (no `reqId` ⇒ no ack
> expected). 6 new tests across `usePopoutInsertRelay`/`StudioPopoutHost`/`ProposeEditCard`.
> **1 MED accepted, not fixed:** `EditorPanel.tsx`/`ManuscriptUnitProvider.tsx` are now ~370
> lines each, over the React MVC ~100/200-line guideline — deliberate (avoids re-fragmenting 8
> file-convergent sub-tasks across a merge-collision-prone split mid-effort); a size-debt
> refactor is its own follow-up, not blocking.
>
> **VERIFY:** `tsc --noEmit` clean; 268 files / 1926 tests green (a 4-file KG-panel flake seen
> mid-sweep was confirmed cross-file test-pollution on rerun, not a regression — passes both
> isolated and on a clean full-sweep rerun). Live browser smoke (vite :5199, real backend, real
> local `google/gemma-4-26b-a4b-qat`): grammar/heatmap/focus/glossary-autocomplete/
> provenance-tag all exercised; cross-window relay proven end-to-end with a real second OS
> window (pop out → agent drafts → Apply → main-window editor updates). **2 pre-existing bugs
> found during smoke, confirmed NOT caused by Phase 2 (untouched by its diff), left as-is:**
> LanguageTool 500s (reproduces identically on the legacy route — infra flakiness) and a React
> "Cannot update ManuscriptUnitProvider while rendering TiptapEditor" warning (Phase 1's
> `content`/`onUpdate` wiring, predates Phase 2).
>
> **Environmental incidents hit + resolved mid-session on this shared checkout (not code
> defects):** (1) `git worktree remove --force` on a fan-out worktree followed a Windows
> junction back to the main checkout's real `node_modules` and deleted its TARGET content —
> fixed via `npm install` (785 packages restored, lockfile unchanged). Lesson: never let a
> worktree's `node_modules` be a junction to the main checkout's real one — run `npm install`
> fresh inside each worktree instead. (2) a concurrent session's `git reset` + `commit` on this
> shared checkout cleared the entire shared staging index (34 files) mid-review — recovered via
> the [[shared-file-collision-safe-staging-multi-agent-checkout]] reconstruct-stage-restore
> technique, re-verified via diff that no staged content was lost.
>
> **Playwright E2E added same day (`87e8508cd`), user asked "did you enforce standards + write
> E2E?" before greenlighting Phase 3** — `tests/e2e/specs/studio-editor-craft.spec.ts` (4 tests,
> real backend, no mocks, kg-panels/wiki-panels precedent): grammar/heatmap toggle round-trip,
> focus-mode hides the flanking Revision History strip, Original Source panel opens+loads, and
> the popout Compose full lifecycle (real second OS window via `window.open` → Dock-back closes
> it → opener re-enables Pop out) — the exact boundary the `/review-impl` HIGH lived on. Found 2
> dev-server-ONLY testing artifacts while writing it (not production bugs, both worked around in
> the test): `React.StrictMode` (main.tsx) double-invokes `PopoutBridge`'s open effect in `vite
> dev` (open → cleanup closes it → open again) — collect every new page, wait for whichever one
> stays open; and `window.close()` inside Dock-back's handler fires synchronously, so
> `waitForEvent('close')` must race the click instead of awaiting it first (same pattern as the
> popup-open wait) or the event can fire before the listener attaches. 4/4 green ×3 runs; the 4
> pre-existing studio specs (12 tests) still green. Standards gate (Dockable Panel Standard —
> `panelCatalogContract.test.ts`+`dockablePanelHygiene.test.ts`) was already confirmed passing
> during the `/review-impl` pass above; no new cross-cutting standard was introduced by Phase 2,
> so nothing further to enforce.
>
> **"CURSOR-FOR-NOVELS" REGISTER — #1 COHERENCE Phase 3 ✅ COMPLETE 2026-07-05 (Translate
> workmode).** Kickoff capability audit found the base port (`translation`/`translation-versions`
> panels) had **already shipped independently** via a parallel track on this shared checkout
> (`17_translation_enrichment_sharing_settings_docks.md`, commit `56c8e17c6`) — same deliverable,
> different framing. Re-verified against the post-commit code and found 3 real gaps (the Phase 3
> delta): no Studio panel for the block-aligned review workflow (`TranslationReviewPage`'s
> per-block correction + the "confirm corrected name into glossary" flywheel + the AC4 "adopt
> newer machine translation" banner); `TranslationViewer`'s Review button still `navigate()`d to
> the full-page route (DOCK-7 violation invisible to `dockablePanelHygiene.test.ts`, which only
> scans `features/studio/panels/**`); no one-click "Translate this chapter" affordance from an
> open `EditorPanel` (Studio only reached Translation via the matrix/palette/agent).
>
> **Explicitly rejected: porting legacy's Write/Translate/Read/Compose Workmode tab-switch
> itself** — would make `EditorPanel` internally swap its whole subtree by mode state, the exact
> DOCK-8 violation spec 17 just fixed for `EnrichmentView`'s 6-way switch. Shipped instead: (1)
> extracted `TranslationReviewView` (DOCK-2, props-based) out of `TranslationReviewPage.tsx` so
> the classic route and a new `translation-review` Studio panel (params-retargeting singleton,
> `{bookId, chapterId, versionId}`, hidden from palette + outside the agent enum — same precedent
> as `translation-versions`/`original-source`) both render it; (2) threaded an optional
> `onReview` callback through `TranslationViewer` → `ChapterTranslationsPanel` (both existing
> callers omit it, unchanged `navigate()` fallback proven via a new test) → `TranslationVersionsPanel`
> supplies `host.openPanel(...)`; (3) a "Translate" quick-access button in `EditorPanel.tsx`,
> same `host.openPanel` pattern as Phase 2's "Original Source" button.
>
> **`/review-impl`:** 1 LOW — `TranslationReviewView.tsx` sits outside `dockablePanelHygiene.test.ts`'s
> scan scope (same structural gap that let the original bug through), manually verified clean
> today; accepted as a repo-wide gap (Wiki/KG/Enrichment have the same exposure), not fixed
> narrowly here. **VERIFY:** tsc clean; 430/431 unit tests (the 1 failure is `user-guide`, a
> DIFFERENT concurrent session's in-flight panel not yet enum-synced — confirmed unrelated).
> **Live smoke with a REAL translate job** (local $0 model, ~10s): Editor → Translate button →
> Translation Versions → Review button → Translation Review panel renders real bilingual content,
> studio never navigates away. New committed `tests/e2e/specs/studio-translation-review.spec.ts`
> (2 tests, real job not a mock) green ×3 runs.
>
> **Shared-checkout collision hit + fixed same day (`a8700878c`):** the concurrent User-Guide
> session was actively iterating on `catalog.ts`/`studio.json` ×4 at the exact moment the Phase 3
> commit (`e26431432`) landed — `git commit -- <path>` reads the WORKING TREE for listed paths,
> not the index, so that commit accidentally swept the other session's uncommitted
> `UserGuidePanel` wiring in alongside Phase 3's own content. Caught by diffing `HEAD` against
> the known-good parent commit right after committing (habit worth keeping); fixed with a
> corrective follow-up commit re-isolating exactly Phase 3's own hunks, no `--amend`. See
> [[git-commit-pathspec-reads-working-tree-not-index]] for the reusable technique.
>
> **NEXT (register order, per spec 16's own roadmap):** Phase 4 (mobile-shell decision + full
> route retirement + `ChapterEditorPage` deletion), gated on a soak period per spec M9. #4
> AGENT-MODE (autonomy mission-control GUI) remains the largest unstarted "Cursor-for-novels"
> item — needs its own CLARIFY+DESIGN when picked up.

> **"CURSOR-FOR-NOVELS" REGISTER — #1 COHERENCE Phase 1 ✅ COMPLETE 2026-07-04.** User approved the
> spec+plan (`approve, go`) and asked to proceed into BUILD; all of Phase 1 (spec
> [`16_chapter_editor_parity_and_retirement.md`](../specs/2026-07-01-writing-studio/16_chapter_editor_parity_and_retirement.md))
> shipped in one continuous run, 4 commits:
> - **P1 `f548859db`** — `ManuscriptUnitProvider.applyProposedEdit({operation, text, provenance})`
>   added as a real Tier-4 hoist action (thin wrapper over the same `editorRef` — the write and its
>   `onUpdate→setBody` wiring are byte-identical, only the CALL SITE moved off the global
>   `editorBridge` singleton). `editorBridge.ts` gained an optional `applyProposedEdit` field;
>   `ProposeEditCard.tsx` prefers it when present, falls back to `target.handle.*` otherwise —
>   legacy `ChapterEditorPage` (no hoist, omits the field) untouched.
> - **1.2/1.3/1.4 `16286995e`** — Checkpoints, Revision History, Publish Gate, built as 3 parallel
>   background agents (disjoint new files: `useManuscriptCheckpoints`+`ManuscriptCheckpoints`,
>   `useRevisionHistory`+`RevisionHistorySection`, `EditorPublishGate`), then integrated serially
>   into `EditorPanel.tsx`. Both restore paths are G7-guarded (refuse to overwrite a dirty hoist).
>   **`/review-impl` found + fixed a MED cross-hook bug**: Checkpoints and Revision History are
>   independent hook instances that both restore the SAME chapter's revision spine, built by
>   separate agents who didn't know about each other — a Revision-History-triggered restore left
>   Checkpoints' internal "latest revision" pointer stale, so the next AI-edit checkpoint would
>   capture the WRONG restore point. Fixed by watching `state.version` (bumped by any
>   save/reload/restore, whoever triggers it) instead of each hook's own narrower signal; a new
>   `crossHookRevisionSync.test.tsx` mounts both hooks against one real `ManuscriptUnitProvider`
>   and proves the fix in both directions.
> - **1.5 `f9ca330f3`** — `ChaptersTab.tsx`'s row-click, pencil icon, and post-create navigation now
>   open `/books/:id/studio?chapter=<id>` instead of the legacy `/chapters/:id/edit` route (Phase 1
>   parity reached — Studio is no longer strictly worse). `WritingStudioPage`/`StudioFrame` gained a
>   small `?chapter=` deep-link seam calling `host.focusManuscriptUnit()` once on mount — the same
>   seam Quick Open/Navigator already use, not a new mechanism. Legacy route untouched, still
>   reachable by direct URL (deletion is Phase 4, gated on a soak period per spec M9).
>
> **VERIFY:** 1108+ tests green across `features/chat`+`features/studio`+`features/books`+`pages`,
> `tsc --noEmit` clean (2 unrelated errors seen mid-session in `PressureGauge.tsx`/`WikiEditorPanel.tsx`
> were concurrent-session WIP, confirmed via `git status`, not mine). **3 separate live browser
> smokes** (each on a fresh vite port + fresh login, real backend, book `019ef35c`): (1) propose_edit
> insert → hoist-routed Apply → editor updated live → saved; (2) full Phase 1 combined — propose_edit
> → Checkpoints strip appears → Restore disabled while dirty → Save → Restore enabled → click Restore
> reverts the editor content live, Revision History shows real v1-v8 data, Publish Gate's
> Re-publish/Unpublish reflect dirty state correctly; (3) the route switch — clicking a chapter row
> on the book detail page opens Studio with the CORRECT chapter's actual content auto-focused (not
> whatever was last active).
>
> **NEXT:** superseded — see the Phase 2 ✅ COMPLETE entry above (2026-07-05).

> **"CURSOR-FOR-NOVELS" REGISTER — #1 COHERENCE SPEC+PLAN DONE 2026-07-04 (docs only, no build
> yet — user-scoped this pass as CLARIFY+DESIGN+PLAN only).** After #2 APPLY-DIFF shipped
> (`fb98f161f`, below), user asked to continue straight to #1 COHERENCE. Dispatched an Explore
> agent for a full capability audit of `ChapterEditorPage.tsx` (legacy) vs Studio v2 before
> designing anything — found **15 legacy-only capabilities with no Studio equivalent**
> (Checkpoints, Revision History, Publish Gate, Translate workmode, grammar check, glossary
> inline decoration/autocomplete, mention heatmap, AI-provenance tracking, selection
> toolbar/inline-AI, focus mode, auto-save, progress-reporting, original-source viewer,
> image/video upload-context+version-history, mobile shell, popout-insert-relay) plus 2 route
> entry points that don't coordinate (every chapter-row click → legacy; only one promoted header
> CTA → Studio). User confirmed via `AskUserQuestion`: **retire `ChapterEditorPage`, Studio
> becomes the sole surface** (not just unify entry points); this pass writes **spec + plan only**.
> Shipped: [`16_chapter_editor_parity_and_retirement.md`](../specs/2026-07-01-writing-studio/16_chapter_editor_parity_and_retirement.md)
> (locked decisions M1–M9, a risk-ordered 4-phase roadmap: data-safety → editor-craft UX →
> Translate → route-retirement, mobile shell left as an explicit OPEN product decision not
> resolved here) + [`2026-07-04-chapter-editor-studio-merge.md`](../plans/2026-07-04-chapter-editor-studio-merge.md)
> (Phase 1 build plan: fan-out shape, phase-agent contract, risk notes) + a new row 16 in
> [`00_OVERVIEW.md`](../specs/2026-07-01-writing-studio/00_OVERVIEW.md). **Self-caught correction
> during spec-writing:** the initial audit claimed the G7 dirty-guard (spec 09) was an
> unimplemented design hole — re-checked against code and found it's **already implemented** for
> the Lane-B reconciler (`bookEffects.ts` calls `isChapterDirty` before reloading); corrected both
> docs so Phase 1 has only ONE true prerequisite (P1: replace the `editorBridge` global singleton
> with a real `ManuscriptUnitProvider.applyProposedEdit` Tier-4 hoist action, per spec 08's own
> "Migration: editorBridge → bus + reconciler" section which already described this target shape
> without building it) rather than two. **NEXT:** BUILD Phase 1 — start with P1 (isolated,
> load-bearing, touches the exact files `fb98f161f` touched today), then fan out
> 1.2 Checkpoints / 1.3 Revision History / 1.4 Publish Gate (disjoint new files, serial
> integration into `EditorPanel.tsx`), then 1.5 the `ChaptersTab.tsx` route switch. Read the plan
> doc's Risk Notes before starting (unconfirmed `ChaptersTab.tsx` path, re-verify P1's target
> files haven't drifted under concurrent-session edits).

> **"CURSOR-FOR-NOVELS" REGISTER — #2 APPLY-DIFF FIXED + COMMITTED 2026-07-04 (`fb98f161f`).** Resumed the
> parked register (memory [[writing-studio-fragmented-not-underbuilt]]) — user asked to pick up
> the GUI-quality gaps now that context-budget-law is being carried by a separate concurrent
> session. Re-verified all 4 items against CURRENT code (the memory was 3 days stale) before
> picking one: **#1 COHERENCE** still broken (`ChapterEditorPage.tsx` vs Studio v2 still two
> workspaces) · **#2 APPLY-DIFF** confirmed still broken, root cause pinned exactly · **#3
> LIVE-SYNC** turned out far more built than the memory said (`bookEffects`/`glossaryEffects`/
> `knowledgeEffects` handlers all real, G7 dirty-guard implemented — grew via the Glossary/KG
> dockable-migration work, not a dedicated LIVE-SYNC effort) · **#4 AGENT-MODE** confirmed still
> 0% frontend (grep for `authoring_run`/`autonomy` across `frontend/src` = 0 hits). User picked
> **#2 (cheapest, already pinned)** to build first via `AskUserQuestion`.
>
> **Fix:** `EditorPanel.tsx` already calls `registerEditorTarget` (the `propose_edit` write-back
> target) whenever a chapter is open, but `ComposePanel.tsx` only ever passed `studioContext` to
> `<Chat>` — never `editorContext` — so chat-service (`stream_service.py` `_editor = bool(editor_context)`,
> ~line 1924/1685) never advertised `propose_edit` on the studio surface; the agent had no way to
> initiate a human-gated prose diff there. Fix: `ComposePanel.tsx` now derives
> `editorContext = { book_id, chapter_id: unitMeta.activeChapterId }` (same shape the legacy
> `ChapterEditorPage.tsx` already passes) whenever a chapter is open in the manuscript hoist,
> `undefined` otherwise (no false advertisement with no chapter open). Verified no side effects:
> `book_scoped` was already `true` in studio via `bookContext`, so skill injection / hot-domains /
> tool-iteration counts are unchanged — the only behavioral delta is `propose_edit` becoming
> advertised, which was the whole point. 2 new `ComposePanel.test.tsx` cases (editorContext
> present/absent) + 3 pre-existing pass unchanged (5/5); `tsc --noEmit` clean; full
> `features/studio` suite 479/479 green (1 unrelated contract-test failure was a `--root` CLI
> invocation artifact of my own test run, not a regression — re-ran in isolation, 3/3 green).
> **LIVE BROWSER SMOKE (evidence, not raw-stream — vite :5199 → gateway :3123, real local
> `google/gemma-4-26b-a4b-qat` model, $0 spend, book `019ef35c` "Dracula (fresh agent journey)"):**
> opened Studio → opened Chapter II in the Editor panel → opened Compose → asked the agent to
> rewrite the first paragraph → agent called `composition_get_prose` then **`propose_edit`** → the
> C6 hunk-review card rendered in the Studio Compose panel for the first time ever → clicked
> Apply → the Studio manuscript editor updated live (55→74 words, "● unsaved") → Save persisted
> it. Closes the loop end-to-end on the surface where it was previously impossible. **`/review-impl`
> caught + fixed a HIGH before commit:** `AssistantMessage.tsx` renders `<ProposeEditCard record={tc} />`
> with no `chapterId` prop, so the card's own "never write into a different chapter" guard was
> DEAD CODE in production — on Studio's persistent Compose dock (unlike the legacy page, which
> only keys `<Chat>` by `bookId` and thus shares the same latent gap, just less reachable),
> switching chapters while a proposal is pending then clicking a stale Apply would silently splice
> text into the wrong chapter. Fixed in `ProposeEditCard.tsx` by self-deriving the guard's target
> chapter from the live editor bridge AT MOUNT instead of the never-supplied prop — 3 new
> regression tests, no prop-threading needed through the shared message-list chain. **Committed
> `fb98f161f`** (both the wiring fix and the review-impl fix, 4 files). #1 COHERENCE picked up
> next per the memory's own priority order — see the block above for its spec+plan output. #3
> LIVE-SYNC should still get an audit pass (does `composition_generate`/authoring-run/
> translation-job writes reach the reconciler?) before assuming full coverage. #4 AGENT-MODE
> (autonomy mission-control GUI) remains the largest unstarted lift (engine exists server-side,
> zero FE) — needs its own CLARIFY+DESIGN when picked up.

**KNOWLEDGE/KG DOCKABLE MIGRATION — PHASE A + PHASE B ✅ SHIPPED 2026-07-04.** Spec: [`docs/specs/2026-07-01-writing-studio/14a_kg_panels.md`](../specs/2026-07-01-writing-studio/14a_kg_panels.md) (row 14 in `00_OVERVIEW.md`). Phase A (commit `4c50f7ae2`, see prior entry below for detail) shipped the shared foundation: `useBookKnowledgeProject` hook, the `knowledge` hub launcher panel, `VersionsPanel`'s DOCK-9 fix, `knowledgeEffects.ts` Lane-B wiring. **Phase B — all 12 capability panels shipped via parallel fanout** (12 background agents, each building one panel + its own tests with zero shared-file edits, followed by ONE serial integration pass adding all catalog/i18n/BE-enum entries together — avoided the N-way race on `catalog.ts`): `kg-overview` (book-scoped, DOCK-7 fix on `OverviewSection`'s 2 backlink `<Link>`s → callback props), `kg-entities`/`kg-timeline`/`kg-evidence` (shared scope via optional `params.scopedProjectId`, K4), `kg-gap` (book-scoped), `kg-proposals` (book-scoped via `host.bookId`, DOCK-7 fix on `ProposalsInboxTab`'s `<Link>` → `onOpenRow` callback), `kg-schema` (book-scoped, the K6 bundle — absorbs the whole ontology adopt/schema/views/sync flow as ONE panel; 2 more DOCK-9 fixes — `GenerateSchemaDialog`+`SchemaWorkbench` → `FormDialog`/`ConfirmDialog` — plus a DOCK-7 fix on `CreateSchemaEntry`'s Link), `kg-graph` (book-scoped), `kg-insights`/`kg-jobs`/`kg-bio`/`kg-privacy` (user-scoped, global, no book/project resolution). All 12 use `followStudioLink`/`host.openPanel` instead of `navigate()` where they link out — unmapped paths fall through to a new-tab open today (honest, not a silent no-op), upgrading in-tab automatically as sibling routes gain panel mappings. **`/review-impl` (1 MED, fixed):** `useBookKnowledgeProject` filtered client-side over only the first cached page of the user's projects (`useProjects(false)` + `.find()`) instead of using the BE's existing server-side `book_id` query filter — a user with >100 KG projects whose linked project sorted past page 1 would silently get a false "no project linked" empty state across all 5 book-scoped panels. Fixed by threading a `bookId` param through `useProjects`/`ProjectsQueryParams` into the BE filter (confirmed live in `services/knowledge-service/app/routers/public/projects.py`), with a regression test simulating 150 filler projects. **VERIFY:** FE 562 files/3892 tests green + tsc clean; chat-service 927 tests green; `ai-provider-gate.py` clean — all re-run after this landed alongside Glossary's own Phase B and the separate "utility panels" dockable track on the same checkout (additive merges throughout, no collisions; contract regenerated to include every track's panel ids). **NEXT:** cross-panel E2E wiring (hub → capability panel drill-down) may defer per the spec's debt-stack convention until ≥2 panels are used together in a real flow; otherwise Phase B is feature-complete per the spec. **studioLinks.ts wiring done same session:** mapped every global KG path (`/knowledge`, `/knowledge/projects`, `/knowledge/{jobs,global,entities,timeline,raw,insights,privacy}`) to its `kg-*` panel, and same-book `/books/:id/glossary` → the `glossary` panel — these upgrade `kg-proposals`/`KnowledgeHubPanel`'s links from new-tab to in-tab automatically, zero panel-side changes needed. Deliberately did NOT map `/knowledge/projects/:id/:section` (project-id-keyed): the `kg-*` panels resolve "the CURRENT book's project" via `useBookKnowledgeProject`, not an arbitrary `:id` — mapping it would silently show the wrong project whenever `:id` isn't this book's project (e.g. the hub browsing a different book's or a standalone project). Wiki/enrichment pages stay external too (no dock panel exists for them yet).

> **UTILITY PANELS (Jobs / Books Browser+Reader / Leaderboard) — ✅ COMPLETE 2026-07-04.** Spec
> [`14b_utility_panels.md`](../specs/2026-07-01-writing-studio/14b_utility_panels.md) + fan-out plan
> [`2026-07-04-utility-panels-fanout.md`](../plans/2026-07-04-utility-panels-fanout.md). Scoped from
> a 5-area ask ("user settings, notifications, job monitor, book browser, leaderboard") down to 3
> real build items after investigation: **Settings/Notifications were already fully dockable** (no
> action), **Books/Leaderboard were structural mismatches** for a per-book studio dock (global,
> cross-book surfaces) but the user explicitly wanted them anyway — redesigned Books as a pure
> browse-then-read capability (no DOCK-7 exception needed) and Leaderboard as a DOCK-8 fix (4
> sibling panels instead of one internal tab-switch). **Shipped:** `jobs-list`+`job-detail`
> (`20e6019c5`), `books`+`book-reader` (`e4d64903e`), `leaderboard-{books,authors,translators,
> trending}` (bundled into `b767fb4c0` by a concurrent session's commit — see below), spine wiring
> (`e72f73b59`), `/review-impl` fixes (`37898fc16`: 2 HIGH — a campaign-kind job clicked inside the
> new Jobs panel opened the wrong detail view because the injectable onOpenDetail callback ignored
> job.kind, fixed in `JobRow.tsx`+`JobsMobile.tsx`; 1 MED — `useReadingTracker` could flush with an
> empty chapterId during BookReaderPanel's async first-chapter resolve, guarded in the shared hook).
> **Caught a real contract gap:** `panelCatalogContract.test.ts` enforces the agent enum ==
> palette-openable set EXACTLY (not a subset as the spec assumed) — `books` + all 4 leaderboard
> panels had to join `ui_open_studio_panel` too, not just `jobs-list`. **3 parallel Agent-tool
> subagents built B/C/D concurrently** (no worktree isolation — disjoint files only), then this
> session integrated serially (re-diffed spine files before each apply). **Live proof multi-session
> contention is real, not theoretical**, on this exact branch during this exact task: a concurrent
> session's bare `git commit` (no pathspec) swept this session's 11 already-staged Phase D files
> into an unrelated `docs(eval)` commit mid-integration; another concurrent session committed KG
> Phase A between this session's `git diff --cached` check and its next edit. Nothing was lost —
> content is correct and tested — but attribution in `git log` is muddled for `b767fb4c0`. No
> further utility-panel phases queued.

> **GLOSSARY DOCKABLE MIGRATION — ✅ PHASE A + PHASE B BOTH COMPLETE 2026-07-04 (committed `97e1b5a2a` + `4f0e1a1b8`).** Full history was in this file's top block before a concurrent commit (Knowledge Hub track, `4c50f7ae2`) overwrote it — detail lives in [`docs/specs/2026-07-01-writing-studio/13_glossary_panels.md`](../specs/2026-07-01-writing-studio/13_glossary_panels.md) (both phases, verify evidence, the `/review-impl` findings) and [`docs/standards/dockable-gui.md`](../standards/dockable-gui.md) (the new DOCK-8/DOCK-9 rules this effort authored). Short version: all 5 Glossary capabilities are now real studio dock panels (`glossary`/`glossary-ontology`/`glossary-unknown`/`glossary-ai-suggestions`/`glossary-merge-candidates`), all 6 hand-rolled modals are DOCK-9 compliant (`FormDialog` or raw `Dialog.*`). No further Glossary phases queued. **Note for future sessions:** this repo currently runs multiple concurrent Claude Code sessions against the SAME working tree/branch (`feat/context-budget-law` — unrelated name, just where everyone happened to be checked out) — shared spine files (`catalog.ts`, `frontend_tools.py`'s panel enum, all 4 `studio.json` locales, `contracts/frontend-tools.contract.json`, this file's top block) get swept into whichever session commits next, sometimes before the "owning" session's own commit. Verify `tsc --noEmit` after any commit involving these files — a dangling import (catalog.ts referencing a component file another session hasn't committed yet) is the concrete failure mode this hit once already.

**KNOWLEDGE/KG DOCKABLE MIGRATION — PHASE A ✅ SHIPPED 2026-07-04.** Spec: [`docs/specs/2026-07-01-writing-studio/14a_kg_panels.md`](../specs/2026-07-01-writing-studio/14a_kg_panels.md) (registered in `00_OVERVIEW.md` row 14). Scoping found the KG/Knowledge surface bigger than Glossary's (#13): 2 route-driven tab hubs (`KnowledgePage` 8 tabs + `ProjectDetailShell` 9 sections) collapsing to ~13 unique panels once shared components are recognized; a global cross-book hub (a KG project's `book_id` is optional) migrates too, per the human's K1 call, as **user-scoped** panels (same tenancy tier as Settings/Usage) rather than fighting the book-scoped Studio model. Shipped this session (A1-A4, shared foundation): **A1** `useBookKnowledgeProject(bookId)` hook extracted from `KnowledgeOntologyTab`'s inline lookup. **A2** `knowledge` hub launcher panel (DOCK-8's "launcher, not host" escape hatch) — `ProjectsBrowser` extracted from `ProjectsTab` (DOCK-2/DOCK-7, shared by the classic route and the new panel), opens a project via the studio link resolver (`followStudioLink`) instead of `navigate()` — falls through to a new-tab open on the classic route today (no Phase-B panel registered yet), upgrades to in-tab automatically once one lands; catalog+i18n×4+BE enum+contract all wired. **A3** `VersionsPanel`'s 2 hand-rolled `fixed inset-0` modals migrated to `FormDialog`/`ConfirmDialog` (the DOCK-9 adoption precedent) — the 4th grep hit (`MemoryIndicator`) was investigated and found to be a FALSE POSITIVE (an accepted anchored-popover pattern shared with `NotificationBell`, not a hand-rolled modal — spec corrected). **A4** `knowledgeEffects.ts` Lane-B handler for `kg_*` MCP writes, invalidation keys verified 1:1 against every actual read-hook query key (no drift) — wired into `useStudioEffectReconciler`. **`/review-impl` (1 MED, fixed):** the FormDialog/ConfirmDialog migration introduced a flash-of-blank-content during Radix's ~150ms close animation — same bug class already fixed once in `ProjectsBrowser`'s archive/delete dialogs (K8.2-R6); fixed with the same last-shown-value ref pattern (not jsdom-testable — same limitation as the precedent it mirrors). **VERIFY:** FE 546 files/3777 tests green + tsc clean · chat-service 927 tests green · `ai-provider-gate.py` clean — re-run AFTER a concurrent Glossary Phase B landing in the same shared spine files (`catalog.ts`, all 4 `studio.json` locales, the `ui_open_studio_panel` enum + contract) merged in cleanly (additive, no collision). **NEXT: Phase B fanout** — 12 disjoint panel slices (overview/entities/timeline/evidence/gap/proposals/schema-bundle/graph/insights/jobs/bio/privacy), safe to parallelize per [[fanout-independent-slices-parallel-build-serial-integrate]] now that Phase A's shared foundation exists.

> **⚠ BRANCH NOTE:** the work below (Dockable Panel Standard + Glossary Phase A+B) was done on the checked-out branch `feat/context-budget-law`, but is UNRELATED to that effort (studio/dockable-migration track vs. context-budget-law track — multiple parallel tracks landed on the same checkout, incl. a concurrent Knowledge Hub dockable-panel effort). Consider splitting onto its own branch. The context-budget-law history is preserved below, untouched.

**DOCKABLE PANEL STANDARD + GLOSSARY MIGRATION — ✅ PHASE A + PHASE B BOTH COMPLETE 2026-07-04 (Phase A committed `97e1b5a2a`; Phase B uncommitted).** Triggered by scoping the Glossary dockable migration (next in the [`12_json_document_standard.md`](../specs/2026-07-01-writing-studio/12_json_document_standard.md) cycle queue after chapter editor) — found the studio's dockable-panel rules were never consolidated into a standard doc (a known gap in `docs/standards/README.md`).

1. **[`docs/standards/dockable-gui.md`](../standards/dockable-gui.md)** (new) — consolidates 08/11/12 into DOCK-1..11, adds **DOCK-8** (no internal page-replacement view-switch) and **DOCK-9** (no hand-rolled `fixed inset-0` overlay — adopt `FormDialog`/`ConfirmDialog`, or raw `Dialog.*` from `@radix-ui/react-dialog` for custom-chrome dialogs like `EntityEditorModal`). Enforced by `dockablePanelHygiene.test.ts` (recursive scan, order-independent token check — a `/review-impl` pass caught and fixed 2 real gaps in the test itself).
2. **[`13_glossary_panels.md`](../specs/2026-07-01-writing-studio/13_glossary_panels.md)** (new) — Glossary re-scoped as **shared-foundation-then-fanout** (7 sub-features, 3 DOCK violations found — too large for a flat single cycle). **Phase A (serial, A1-A6):** `useGlossaryEntity` hook + `loreweave.glossary-entity.v1` JSON provider extracted from `EntityEditorModal` (→ raw `Dialog.*`) · `GlossaryEntityList` extracted from `GlossaryTab` (DOCK-2, shared with the new `glossary` panel) · `glossary` panel added to catalog + agent enum (contract regenerated) · `ResolveKindModal` → `FormDialog` (the DOCK-9 precedent) · `glossaryEffect` Lane-B handler · `StepConfig`'s settings link fixed via `useOptionalStudioHost()`. **Phase B (8-way parallel fanout, this session):** the 4 remaining glossary capabilities promoted to real sibling dock panels (`glossary-ontology`/`glossary-unknown`/`glossary-ai-suggestions`/`glossary-merge-candidates` — `GlossaryPanel`'s temporary internal view-switch is GONE, replaced with real `host.openPanel(...)` cross-panel jumps) + the last 4 hand-rolled modals migrated (`CreateEntityModal`/`BatchTranslateDialog` → `FormDialog`; `GlossaryTranslateWizard`/`ExtractionWizard` → raw `Dialog.*`, both having a pinned step-indicator FormDialog's template can't hold). Serial integration (catalog/i18n×4/BE-enum/contract, done by the orchestrating session, NOT the fanout agents) avoided the shared-file collision the parallel build would otherwise hit.
3. **NEW DEFERRED (tracked, gate #1 out-of-scope):** `AddModelCta.tsx` + ~14 consumers (incl. **already-shipped** `PlannerPanel`, `CompositionPanel`) have the SAME DOCK-7 route-navigate defect A6 just fixed locally — needs one fix at the shared component, not per-site. See `13_glossary_panels.md` for detail.

**VERIFY (Phase B):** full FE suite 545 files/3768 tests (1 unrelated failure — `VersionsPanel.test.tsx`, uncommitted WIP from the concurrent Knowledge Hub track, not this effort) · `tsc --noEmit` clean · the 14 Phase-B test files in isolation 112/112 · BE `test_frontend_tools.py`+`test_frontend_tools_contract.py`+`test_agent_surface.py` 74/74 (checked both known snapshot locations, learning from the Phase-A miss) · i18n parity clean for the 4 new key sets. **NEXT:** decide whether to commit Phase B (staged carefully to exclude the concurrent Knowledge Hub / context-budget-law files, same discipline as the Phase A commit) — Glossary's dockable migration is then fully done (all 5 capabilities are real panels, all 6 modals DOCK-9 compliant); no further Glossary phases queued.

**VERIFY:** FE full suite 524 files / 3628 tests green · `tsc --noEmit` clean · chat-service `test_frontend_tools_contract.py` 21/21 (regenerated + reverified) · i18n parity clean for new keys (pre-existing unrelated gaps untouched). **NOT committed** — user has not yet asked to commit. **NEXT:** Phase B fanout (4 remaining panels: ontology/unknown/ai_suggestions/merge_candidates + 4 remaining modal migrations: CreateEntityModal/ExtractionWizard/GlossaryTranslateWizard/BatchTranslateDialog) — genuinely disjoint files now, safe to parallelize per [[fanout-independent-slices-parallel-build-serial-integrate]]. Consider the `AddModelCta` sweep too (small, independent, high-value since it's a live bug in shipped panels).

---

**CONTEXT BUDGET LAW — IMPLEMENTATION IN PROGRESS on branch `feat/context-budget-law` (off merged main), 2026-07-04. STANDING RULES (autonomous run): test-model = local `google/gemma-4-26b-a4b-qat` (12b is 8K, too small); DEFER-DON'T-BLOCK (anything needing the user's judgment → a Deferred row here + continue, never hard-stop); quality-gate = a judge subagent CHATS the live agent + scores a rubric + writes an md report ([`docs/specs/context-budget-quality-gate.md`](../specs/context-budget-quality-gate.md)) → decide PASS/REGRESS/NEEDS-HUMAN; durability = git commits + spec §8a + this block (on resume: `git log --oneline`, spec §8a, the todo list); REVIEW-IMPL GATE = every todo item gets a cold-start adversarial review (parallel subagents) before it's marked done → fix HIGH/MED now, defer the rest (tracked here). DONE (committed): T0 wire-hygiene (−3.6% real), T1-flagship response-contract (outline −74%/−99% live + jobs_list + kit helper `apply_response_contract` + worst-first manifest), T2 task-elastic target + meter accuracy (live gate ±22% safe-high), T4-SUBSTRATE (`chat_session_blocks` + `story_state` + OCC, real-PG tested). REVIEW-IMPL GATE applied to T0/T1/T2/T4 (4 cold-start review subagents, commit `5706295a0`): all MED fixed (T0 meter over-counted VI/CJK; T1 get_outline_node had no IDOR test + was missing from the public-MCP allowlist; T4 distill blew the token cap 2-3× for CJK/VI) + cheap LOWs; only the T2 FE↔BE breakdown-vocab drift deferred → Inspector-FE. **⚠ DEFERRED — EVAL-BOOK GAP (D-EVAL-BOOK, gate #4 blocked-on-infra→BUILDABLE):** no dev-DB book currently has agent-retrievable KG lore (POC books have no knowledge project; `entity_canonical_snapshots` + knowledge passages are EMPTY globally, incl. Dracula). The quality-gate's *answer-correctness* A/B needs a lore-populated book → must SEED one (extraction pipeline; scripts `run_dracula_fresh_journey_kg.py`/`seed_fengshen_demo.py`). Unblocks: the T5 answer-correctness judge run + the harness real A/B. NOT blocked: T5 gate-decision correctness + token-savings smoke (a no-lore MESSAGE skips build_context regardless of book lore). NOW: quality-gate harness CODE (driver+judge+report — smoke-able on any session) → T5 grounding intent-gate (+T4 wiring: skip build_context on no-lore turns, project `story_state` net) validated by gate-decision + token-savings; answer-correctness deferred to D-EVAL-BOOK. Family B (MCP SET tools) + Inspector + §13 are fully unblocked in parallel. **FAMILY-B REFACTOR DONE (2026-07-04, commits `d856…`+`b458…`):** 18 SET tools refactored to reference-first across translation + composition-motif + knowledge (3 parallel disjoint-service subagents, each review-gated + re-verified; suites 1039/1490/3496 green), 6+ `@small_return` exemptions; see [`context-budget-t1-refactor-manifest.md`](../specs/context-budget-t1-refactor-manifest.md) §Family-B-completion. **Remaining B:** contract-snapshot harness (§13b) + live-e2e per tool (composition/outline drop proven −74%; knowledge/translation live drop gated on D-EVAL-BOOK data). **⏩ SESSION-CONTINUED 2026-07-04 (autonomous, 5 commits): (1) §13b RESPONSE-SHAPE SNAPSHOT HARNESS ✅ `78fcaa885` — `contracts/mcp-response-shapes/{composition,knowledge,translation,jobs}.json` pins all 15 ref-field constants; shared kit helper `loreweave_mcp.assert_or_write_shape_snapshot` (regen `WRITE_MCP_SHAPES=1`); catches drift BOTH ways; guard proven-to-bite; coverage-audited. (2) QUALITY-GATE HARNESS ✅ `1e2d84e6c` — `scripts/eval/{run_quality_gate.py,context_budget_scenarios.json,judge_prompt.md,README.md}`; in-container DRIVER (minted JWT, SSE+GET fallbacks) captures reply+contextBudget+tools/turn; BLIND judge template; mechanically proven live (gemma-4-26b). (3) T5 SLICE 1 ✅ `4f1d73ecb` — entity-presence gate substrate (`entity_presence.detect_entity_presence` word-bounded ASCII/CJK, BIAS-TO-INCLUDE on empty-set/anaphora/lore-intent) + `known_entities_client` (glossary `/internal/books/{id}/known-entities` VERIFIED route + TTL cache + degrade-to-empty) + config + lifespan. (4) T5 SLICE 2 ✅ `c9a6c46ad` — knowledge `build_context`+route take `grounding:bool=True` (False→light static path, ROUTING-only, mode fns byte-identical, +3 tests); chat forwards it + threads `entity_presence` telemetry through `_emit_chat_turn`; `T5_INTENT_GATE_ENABLED` kill-switch. **T5 LIVE A/B (docs/eval/context-budget/T5-2026-07-04.md):** gate CORRECT+SAFE cross-service (status_op gates OUT, all lore/discovery/continuity stay grounded, ZERO false-negatives, no correctness regression); **token-saving INCONCLUSIVE on Dracula POC** (gating status_op saved 0 tok — build_context retrieval is already query-relevance-scaled) → token win needs D1 pull mode OR a heavy-retrieval seeded KG (folds into D-EVAL-BOOK); gate ships safe/flag-gated/tested (114 chat+12 knowledge green). (5) §13 COVERAGE META-CHECK ✅ `41e3414ac` — `assert_or_write_shape_snapshot(…, scan_modules=[…])` introspects each service's tool modules for every `*_REF_FIELDS` and asserts it is snapshot-pinned (a new un-pinned constant → RED; "checklist→test not self-report"); bite-proven in the kit test; CI-wired via each service suite. **⚑⚑ SESSION SELF-AUDIT (2026-07-04) — the strategic decision-point below was RETRACTED.** A 3-reviewer cold-start audit + a T5 measurement re-audit found: (1) the T5 "token thesis weakened → T3 optional" decision was INVALID — the gate had a production NO-OP bug (fed a knowledge project_id to a book_id route → always []→ never fired) AND the A/B was confounded (Dracula book has no KG project → grounding degraded in both arms) AND the 28K→120K split was the 41K MCP tool catalog × tool-loop passes, not grounding. (2) A summary-truncation HIGH regression I introduced (D6 made summaries longer, no finish_reason guard → silent tail loss). (3) §13 meta-check over-claimed (convention- not call-site-scoped). FIXES SHIPPED: `f6707d65c` summary-truncation guard · `0c0b212cc` §13 call-site (reject inline ref literals) + eval-harness MEDs (_budget_total order, session cleanup, WRITE_MCP_SHAPES CI guard) · `33a954036` T5-BUG (project→book_id resolution route + cached resolve_book_id + multilingual bias-to-include CJK/VN/question, meta carve-out) · `b6ef10ba6` 2 live-caught gate bugs (em-dash non-ascii, junk 1-char token). **T5-BUG fix LIVE-VALIDATED** (Dracula-linked KG project `019f2be0`): the gate now FIRES correctly (smalltalk/status→gated out, lore/discovery/anaphora→open). **T5 token-SAVINGS NOW QUANTIFIED = ~0 → KILLED as a token optimization.** Pushed the full pipeline: created Dracula KG project `019f2be0` → fixed a `kg_run_benchmark` NameError (`c8edb30ec`) → benchmark PASSED → extracted 2 chapters (full mode) → clean gate ON vs OFF A/B on the SAME no-lore turn: **gate saves ~48 tok (~0.16%)** — grounding block is ~1.1K in BOTH static and full mode, negligible next to the **~41K `mcp_tool_schemas` catalog** that dominates every turn (lore turn 120K = catalog × tool-loop passes). **ACTION:** `t5_intent_gate_enabled` **defaulted OFF** (config+compose); code kept (correct/safe/tested — residual value = compute/latency + telemetry + D1 pull substrate). **⚠ CORRECTION #2 (same day): the "41K catalog is the real lever" was ALSO a measurement artifact** — the driver used LEGACY stream format (full catalog); the real frontend uses AGUI where tool DISCOVERY trims the catalog to **368 tok** (agui turn=4.9K vs legacy=29.7K on the same turn). So tool-catalog trimming is NOT a real-user lever — RETRACTED. Driver now defaults to agui. Real agui turns are lean (~5K simple; a lore turn's ~21K is AGENT BEHAVIOR — subagent spawn + kg_graph_query — not catalog/grounding). The effort's real wins were T0 (ensure_ascii) + T1 (reference-first tool RESULTS, the original 146K fix). **T5 net: default OFF stands, but honest reason = full≈static grounding for a THINLY-extracted book (gate saves ~40 tok); genuinely UNPROVEN for a rich book.** ROOT CAUSE the rich-book A/B couldn't be produced: the Dracula KG project `019f2be0` was created via SQL WITHOUT a graph schema → extraction yielded entities=0 → thin grounding (memory_knowledge 88–1126 tok, no passages section). A real rich-grounding seed needs the FULL KG authoring pipeline (schema→benchmark→extraction), several gates deep (a 2nd extraction also wedged — likely LM Studio queue). So T5's rich-book value is unmeasured-not-disproven; the honest measurement bottoms out here on the available infra. Bonus: `019f2be0` (Dracula KG, benchmark-passed, 2ch extracted) partially resolves D-EVAL-BOOK. Full findings: `docs/eval/context-budget/T5-2026-07-04-CORRECTED.md`. **⚑ NEW TRACKED BUG (user-identified during the seed) — D-EXTRACTION-SILENT-NOOP (MED, gate #2):** the extraction pipeline can report `status=complete` (success) having made 0 LLM calls / produced 0 entities, with NO signal — an observability + data-validation gap (no output-validation, no input schema-check, no stall detection). Evidence + fix plan in `docs/deferred/D-EXTRACTION-SILENT-NOOP.md`. A correct fix needs the extraction saga's finalization chokepoint located (distributed worker+saga+event; NOT `extraction_jobs.complete()`). **RETRACTED** ▼ (kept for history):
**⚑ STRATEGIC DECISION-POINT for the user (defer-don't-block, rule #3):** the T5 live A/B showed the token-saving thesis for intent-gating is largely REDUNDANT with build_context's existing query-relevance scaling on real workloads (the big 146K wins were already banked by T0 ensure_ascii + T1 reference-first). This weakens the token-win justification for the remaining PURE-REFACTOR **T3 kernel extraction** (byte-identical, no token win — its value is code-reuse for the roleplay consumer, not tokens). T6 (long-conversation fact-retention) + Inspector (observability, surfaces entity_presence) remain valuable REGARDLESS of the token thesis. **Recommendation pending user:** do T6 + Inspector next (valuable independent of tokens); treat T3 as OPTIONAL (do it only if the roleplay-consumer code-reuse is wanted). (6) T6/D6 FACT-PRESERVING SUMMARY ✅ `c7eddba66` — compaction summarizer now emits a two-section FACTS/SYNOPSIS structure (verbatim entity/decision/established/open-thread list = system of record, then prose; names EXACT; max_tokens 700→900). LIVE-PROVEN gemma-4-26b: 4/4 planted facts KEPT incl. VN name "Lâm Uyển" verbatim (docs/eval/context-budget/T6-summary-2026-07-04.md). NEXT unblocked (all LARGER central-path, for a fresh context): **T6-remainder** = atom-safe reversible collapse + resume-monotonic ([[compaction-resume-path-carries-tool-pairs]] class, partly handled by existing `_atoms`) + `conversation_search` recovery tool (design: where a session-history-search tool lives) + flip the compaction TRIGGER to the T2 task-elastic `compute_target`; **Inspector GUI** (BE TraceSpan telemetry + dockable FE panel + `context-trace.contract.json` + §11 86-item checklist — note `entity_presence` + `grounding` are ALREADY in the frame, ready to surface); **live-e2e per SET tool** (composition proven; rest gated on D-EVAL-BOOK data); **T3 kernel** — **IN PROGRESS (user chose to continue T3 as the optimization testbed). Plan: [`2026-07-04-t3-context-kernel.md`](../plans/2026-07-04-t3-context-kernel.md). T3.1 ✅ DONE (see COMMIT): new `sdks/python/loreweave_context` kernel + `build_system_message` renderer unifies chat's two lockstep system-prompt ladders (A1 footgun) into ONE ordered `tail_blocks` list, byte-identical (7 golden cases + 926 chat tests green — the 1 red is the parallel studio track's `ui_open_studio_panel` glossary-enum drift, NOT mine). NEXT SLICES: T3.2 CompilePlan+Planner (the swappable policy seam for A/B), T3.3 Compiler+CompactionStrategy, T3.4 package + voice/roleplay consumer. Then A/B optimization hypotheses via the quality-gate harness.** (7) T6/D6 CONVERSATION_SEARCH RECOVERY ENGINE ✅ `a910b415f` — `app/db/conversation_search.py::search_session_messages`: the search half of the D6 safety net (pull back a fact dropped from the summary; raw turns stay in PG). Case-insensitive ILIKE SUBSTRING (multilingual — a recovery query is a NAME `Lâm Uyển`/`万古神帝` that English `to_tsvector` stems wrong), session+owner+branch-scoped, error rows excluded, limit-clamped, LIKE-metachars escaped. Real-PG tested (7 — the live test CAUGHT a broken ESCAPE clause a mock passed). **PRECISE NEXT SLICES (all touch the central stream_service tool-dispatch loop / a large GUI — best for FRESH context):** (a) ✅ **DONE this session (see COMMIT below)** — conversation_search FULLY WIRED into the tool loop: advertised at depth 0 in `_stream_with_tools` ONLY when the pass already offers tools (guards `test_no_tools_no_schema_chunk`); local dispatch branch before run_subagent using `get_pool()` (pure read, no write-budget decrement, never a silent no-op); `run_conversation_search` SHAPER added to `app/db/conversation_search.py` (empty-query prompt / no-hits message / hits shape / DB-error→`{"error"}`); `conversation_search`→`SERVER_KEY_CHAT` in `agent_surface.server_key_for_tool`. 7 new tests (5 shaper + 2 dispatch-EFFECT proving the model call runs in-process + maps error→not-ok) + 5 exact-surface test updates (test_stream_tools/test_agent_surface/test_permission_modes/test_plan_mode). Full chat suite **917 green**. The ENGINE + tool DEF were already DONE+tested (`a910b415f`+`99188c5c1`). (b) ✅ **BUILT + LIVE-VALIDATED this session (see COMMIT below), default OFF** — task-elastic compaction trigger wired: `compact_messages(target=…)` fires at `compute_target(context_length, task_weight)` instead of flat `0.75×effective_limit`; `task_weight` = 1.0 for a grounding turn (T5 `entity_presence.grounding_needed`) else `compact_light_task_weight` (0.5); flag `COMPACT_TASK_ELASTIC_ENABLED` (config, default OFF) + 3 unit tests. **LIVE A/B (gemma-4-26b 40K reg, plant→pad→recall, `docs/eval/context-budget/T2-compaction-trigger-2026-07-04.md`): candidate compacts 17.5K→4.7K (~73% cut) at the soft 14K target AND recalls all 3 buried facts from the summary FACTS (tools=[]) — ZERO quality loss; baseline (flat 28K) never fires. The live run CAUGHT a `_grounding_presence` scope NameError (flag-ON path, unit-tests missed) → fixed to read the `entity_presence` telemetry dict.** DEFAULT STAYS OFF pending a broader gate (multi-fact-type + light-target judge run + summarizer-call-frequency cost across all users; big-window models rarely reach the target so the win is mainly small-window / long sessions). Safe to enable per-deployment. **BROADER JUDGE RUN (user-requested, same doc): 4 fact-types + LIGHT target (T5 gate ON + Dracula-KG-bound → status turns classify light ~9K) + blind judge subagent. Result MIXED — SAFE but LOSSY: candidate compacted 18.0K→5.6K (~69% cut), recalled 8/9 fact-tokens but DROPPED one number (the "seven star-anchors" count), and critically did NOT confabulate (honest "I don't have that info") — blind judge scored candidate correctness 4/5 vs baseline 5/5, `critical_confabulation=false` both. gemma did NOT self-recover via conversation_search (tools=[]) — the net is built but unused. DECISION: default STAYS OFF (safe but a real minor recall regression at the aggressive light target). Highest-leverage unblock to justify default-ON = a system hint to CALL conversation_search on a post-compaction turn (the net exists; the gap is USAGE).** **⇒ FIX SHIPPED (user insights): (1) recovery HINT (nudge model to call conversation_search post-compaction) — built + tested, but gemma IGNORES it (4 runs, 0 tool calls) → default OFF, kept for stronger models. (2) DETERMINISTIC BREADCRUMB (`compaction.extract_breadcrumb`, default ON): regex-extract number-sentences+quoted-names+proper-phrases VERBATIM from the compacted turns BEFORE the lossy LLM summary + a `Keywords:` recovery-index line in the summarizer prompt + a "don't over-compress" nudge. RESULT: light-target recall floor 1/9→9/9, variance ELIMINATED (3/3 runs 9/9 = matches uncompacted baseline) at ~68% token cut (~150 tok breadcrumb cost). QUALITY BLOCKER RESOLVED — task-elastic is now much closer to default-on-ready; remaining gate = operational (summarizer-call frequency cost + broader-scenario sweep), user's call. Full detail in the eval doc.** **⇒ FLIPPED DEFAULT-ON 2026-07-04 (user call) after a broader sweep: 2 scenario shapes (ALLCAPS + natural-cased date/qty/relationship/list, 8-turn) × 2 runs on the shipped default (task-elastic + breadcrumb ON) = ~9/9 recall all 4 (one 1-char name-spelling model slip) at ~68% cut. `COMPACT_TASK_ELASTIC_ENABLED` now True; operational notes stand (big-window 200K ≈ no-op since target caps ~32K; more summarizer calls on long chats; raise `_TARGET_MAX_CAP` for heavy-context headroom; set flag False to revert to flat 0.75×window).** Remaining (c); (c) INSPECTOR GUI (BE TraceSpan telemetry + dockable FE panel + `context-trace.contract.json` + §11 86-item checklist; `entity_presence`+`grounding`+`breakdown` ALREADY in the frame, ready to surface). This session: **11 commits** (78fcaa885 §13b · 1e2d84e6c quality-harness · 4f1d73ecb+c9a6c46ad T5 · 41e3414ac §13-meta · c7eddba66 T6/D6-summary · a910b415f T6/D6-convsearch-engine · 4 handoff). All green + live-proven; branch always-green.** ▼prior: NEXT unblocked: contract-snapshot harness · T5 gate-decision+token-savings · T3 kernel · T6 · Inspector · §13 CI-meta. REMAINING (maximal scope, user-approved 2026-07-04): **B** = ALL ~28 MCP SET tools reference-first + contract-snapshot harness + live-e2e each; **T3** = extract Planner/Compiler → `sdks/python/loreweave_context` kernel (reuse STANDARD, byte-identical, retire the roleplay byte-copy coupling); **T6** = atom-safe collapse + resume-monotonic + fact-preserving summary + `conversation_search` + flip compaction to the target; **Inspector GUI** (dockable studio panel + BE TraceSpan telemetry + `context-trace.contract.json`, §11 86-item checklist); **§13** full enforcement (CI meta-check unproven=red + adversarial refute-pass). THEN the Cursor-for-novels register [[writing-studio-fragmented-not-underbuilt]]. Tier-by-tier measured detail lives in spec §8a. ▼ superseded design-seal note (that prior work merged to main): CONTEXT-MANAGEMENT DESIGN SEALED 2026-07-03 (spec-only; implementation is a NEW SESSION + NEW BRANCH per the user). Spec: [`docs/specs/2026-07-03-context-budget-law.md`](../specs/2026-07-03-context-budget-law.md) v2 + memory [[context-budget-law-and-kernel]]. Root pain: the chat agent has NO per-request context planning — one real turn ("change scene status to drafting") cost 146K tokens (composition_list_outline dumps the whole outline; json.dumps ensure_ascii=True → Vietnamese \uXXXX 2-3×; full skill bodies + blind RAG for a turn needing neither). Deliverables designed: a repo-wide Context Budget Law SPLIT BY ENFORCEABILITY (L3 concise-wire = lint now; L1/L2 reference-first+detail/fields/limit = contract-snapshot tests + versioned default flip; L4/L5/L6 = compiler behavior), Planner(policy) vs Compiler(mechanism), 13 decisions folded from 2 cold-start adversarial reviews, a tier build T0–T6 with per-tier GATES (T0 ensure_ascii=false is shippable NOW & measurable on the 146K replay; committed T0–T3, re-decide T4–T6 after T0–T2 numbers), a reusable Context Kernel STANDARD (`sdks/python/loreweave_context`, ports via provider-registry, uniform TraceSpan telemetry — chat is consumer #1, role-play #2 [roleplay-service is thin Rust delegating to chat-service via a byte-compatible working_memory_seed], composition packer #3), and a dockable Inspector GUI (draft `design-drafts/context-management/context-compiler-inspector.html` + §11 86-line item-level BE/FE checklist; the TraceSpan telemetry is NEW BE work beyond today's context_breakdown). ▶ CURSOR-FOR-NOVELS REGISTER (north-star, don't drift) in [[writing-studio-fragmented-not-underbuilt]]: after context-mgmt, return to (1) merge the 2 workspaces, (2) pass editorContext in ComposePanel so propose_edit works in studio, (3) fill the Lane-B reconciler stub, (4) autonomy mission-control GUI, + Compose grouping/launcher, discuss→content, [[llm-client-first-tool-refactor]], C6 setDone-before-await shared-card refactor.** Prior: **C6 HUNK-REVIEW ✅ SHIPPED 2026-07-03 — the last RAID FE tail item is cleared. The `propose_edit` card now lets the user accept/reject INDIVIDUAL changes of an AI-proposed rewrite instead of all-or-nothing Apply. Pure FE, no contract/backend change. New pure helper `features/chat/utils/proseHunks.ts` — SENTENCE-granularity diff (ProseMirror hands the selection space-joined via `textBetween(...,' ')`, so line-granularity is impossible; sentence reads naturally for prose; Latin+CJK splitter with a lowercase-next guard for dialogue/abbrev; reuses wikiDiff `diffLines` LCS) → hunks → `reconstruct(accepted)`. ProposeEditCard renders per-hunk old/new with checkboxes (default accept-all); Apply writes the reconstructed merge, accept-all stays byte-identical to the old whole-text path, reject-all routes to Dismiss. Applies to `replace_selection` only; `insert_at_cursor`/no-selection fall back to the whole-text card. /review-impl (cold-start subagent) found 1 HIGH + 2 fixed + 1 deferred: HIGH — a partial accept flattened the NEW proposal's paragraph breaks to single spaces (accept-all preserved them) → reconstruct now carries a per-unit `breakAfter` and rejoins with `\n\n` at NEW-side paragraph seams. MED — mount-snapshot selection vs live selection: a partial merge re-injects OLD sentences, so Apply now re-checks the live selection still equals the mount snapshot and aborts with a toast on drift (no stale-range splice; run stays suspended for a re-ask). LOW — reject-all→Dismiss moved ABOVE the editor/chapter guards (dismissing needs no editor). DEFERRED (tracked): the optimistic `setDone`-before-`await submitToolResult` with no `catch` is a PRE-EXISTING shared pattern across every propose/confirm card (RecordDiffCard, ConfirmCard, …) — fixing it correctly (retry-RESUME-only, since the doc is already mutated) is a cross-card refactor, out of scope for C6. VERIFY: proseHunks 15 + ProposeEditCard 7 + full chat suite 438 green · tsc clean. FE-only (entirely under frontend/). The LLM-CLIENT-FIRST REFACTOR remains the user-chosen NEXT (new session; memory [[llm-client-first-tool-refactor]]).** Prior: **4-DEBT /review-impl HARDENING DONE 2026-07-03 (content on remote; my labeled commit was dropped as a duplicate on rebase after the concurrent agent-registry track swept the index — the FIXES ARE LIVE, verify by grep not by commit message). 4 adversarial reviewers over the 4 debts: 1 HIGH + 8 MED, all verified-then-fixed. HIGH: C1 steering list is a {items,total} ENVELOPE the FE consumed as a bare array → panel CRASHED on every load (mock-only-coverage trap; api.list now unwraps .items + a transport-level contract test). MED: (8) reorder race (NULL-all now locks ALL owner rows — the `IS NOT NULL` predicate locked nothing when all-NULL → concurrent corruption; + dedupe); (8) ModelPicker now flat-renders in server order when ANY model is ordered (favorites-hoist + provider-grouping were discarding the custom order); (5) context-history limit ge=1 (negative→500), CATEGORY_HEX⇄COLORS lockstep pin, useContextHistory race-guard + stale-clear, History tab mounted-hidden so enabled gates the fetch; C6 TurnCheckpoints filters to the CURRENT chapter (stale other-chapter row silently restored the wrong chapter), capture() TOCTOU closed via a sync-held latestRevIdRef, revKey bump + first-snippet fold; C1 code-point char count + 403 "no permission" message. VERIFY: FE 1262 (182 files) + tsc clean · chat 735 · provider-registry go (DB-gated reorder incl. dedupe). The LLM-CLIENT-FIRST REFACTOR is DEFERRED to a NEW SESSION per the user (memory [[llm-client-first-tool-refactor]]).** Prior: **4 DEBTS CLEARED 2026-07-03 (`1302d9f55` + 3 prior; 3 parallel sub-agents + C6 by hand). The user decided NOT to wait for the (still-active) studio track — the dockable migration is long done + the panel catalog is now additive-safe, so C6/C1 were built directly. (8) MODEL sort_order: `user_models.sort_order` + `PUT /user-models/reorder` + ModelOrderCard drag-reorder (favorites-first fallback; DB-gated live). (5) TOKEN HISTORY chart: `GET /sessions/{id}/context-history` over the persisted context_breakdown JSONB + a recharts Now/History tab on the ContextBreakdownPanel. C1 STEERING panel: features/steering CRUD + dockview SteeringPanel + catalog entry + `steering` added to the ui_open_studio_panel enum (contract JSON + frontend_tools.py + test pins). C6 TURN-CHECKPOINTS: useTurnCheckpoints captures the pre-edit revision at all 3 AI-apply seams (onAccept/applyPolish/popout-relay) → TurnCheckpoints UI above RevisionHistory restores "before the agent touched it" (pure FE over the existing restore spine; ChapterEditorPage not hot in the studio track). VERIFY: chat 734 · provider-registry go (DB-gated) · FE full sweep 181 files/1251 tests · tsc clean. REMAINING: C6 hunk-review (per-hunk accept on the propose_edit card — separate surface, deferred). NEXT (user-chosen): the big LLM-CLIENT-FIRST TOOL REFACTOR (memory [[llm-client-first-tool-refactor]]) — make every agent tool self-describing/enum-in-schema/tolerate-extras/self-correcting/explicit-context, the Frontend-Tool Contract swept across the whole MCP surface.** Prior: **W0 TOOL-ERROR SOAK ✅ DONE 2026-07-03 (`632077380`): baseline reconfirmed 27.7% over 30d (glossary_book_patch 58.5% = the base_version 409 storm = ~22% of ALL errors). The base_version root cause is ELIMINATED — deterministic live proof through chat→gateway→glossary: read emits base_version on all 13 kinds, patch round-trips one-shot, stale→409 WITH current version, OCC bump real again; the fresh-window storm = 0. The soak CAUGHT a systemic residual: the go-sdk infers additionalProperties:false on every MCP tool struct, so a weak model's harmless EXTRA field hard-fails validation before the handler runs — live-caught on glossary_book_patch's `changes` tolerance shim (gemma's `old_value` killed it) AND glossary_propose_batch (100%-error tool; stray root `type` + op-item extras). Fixed via `relaxAdditionalProps` (opens additionalProperties on model-constructed object/array schemas; ENUMS stay strict) + 2 schema tests + 2 deterministic live proofs. Remaining soak tail: fresh-window sample is small (gemma non-deterministic); residual errors are model hallucination (wrong codes) which is inherent — a longer real-usage soak will show the true steady-state (target <10%).** Prior: **WAVE /review-impl HARDENING ✅ SHIPPED 2026-07-03 (`3ce92d101` chat-surface + `6036dfc6a` MCP-surface; 4 parallel adversarial reviewers, every finding VERIFIED against code before fixing): 3 HIGH — (1) edit-below-compact-boundary made user messages INVISIBLE to the model → clear-compact-on-edit + branch-scoped assistant seq; (2) glossary reads NEVER emitted `base_version` (the W0 shim had become the MAIN path = silent overwrite of concurrent human edits; the 22% error bucket was a broken CONTRACT) → reads/creates emit it, OCC loop DB-proven completable end-to-end; (3) session reasoning "off"/"auto" crashed every tool-approval RESUME (raw session vocab ≠ wire vocab) → `_resolve_and_stash_reasoning` on all 3 paths (fresh/resume/voice). 13 MED fixed: Deep-effort persistence via the panel contract ({reasoning_effort, thinking:null}), manual-compact race-guard 409 + `{"clear":true}` escape for poisoned summaries + FE button, ModelPicker recents cross-USER pref pollution (per-user cache keys), serverKey FE/BE pinned to contracts/frontend-tools.contract.json, gateway 408/429/-32603→retryable, `kg_project_list` added to the public tool policy (the self-correct directive pointed at a denied tool), settings_model_set_default parity via shared defaultModelCapQuery, rack 0-tok flash, toast late-join replay, edit_attribute stale-error embeds current version, sanitizer host:port redaction, enum VALUE-SET pins. Accepted+documented: enum-rejects-"" (self-correcting 1-retry), voice-path compact splice, threshold-marker drift. Suites: chat 729 · FE 3349+13 · glossary (incl. DB-gated OCC-loop) · provider-registry · ai-gateway 114 · mcp-public 205 · tsc clean · provider-gate clean.** Prior: **CHAT QUALITY & UX WAVE ✅ COMPLETE 2026-07-03 ([plan](../plans/2026-07-03-chat-quality-ux-wave.md)) — ALL 7 MILESTONES SHIPPED + LIVE/BROWSER-SMOKED: W0 MCP reliability `8e870b363` (26-30% tool-error rate attacked at root; /internal/tool-health measures the after) · W1 breakdown spine `a3dd678ba` · test-infra xdist `a374d6807` (composition 418s→55s · translation 770s→37s; CLAUDE.md rule) · W2 context GUI + W4 effort/mode dropdowns `c18fdba1c` (browser-smoked: meter "until auto-compact: 72%", panel Skills 1,907/UI-tools 1,484/MCP 193, always-on token footer, both dropdowns) · W3 manual steerable compact `c5373c5a2` (PERSISTED; live: 200 {4 compacted}, steered summary kept "the moon fact", SPLICE PROVEN BY EFFECT — post-compact turn answered from the summary alone; live-caught fix: summarizer thinking-OFF, gemma burned max_tokens on ReasoningEvents → empty prose) · W5 shared ModelPicker `735598a47` (ALL ~19 sites swept; browser-smoked: chat picker = 6 chat-capable only, rerank/embed/tts GONE, provider groups + ctx/$0-local badges; BE: pricing exposed, favorites-first, chat default whitelisted) · vision-to-book tool/skill visibility `7a69f2ded` (agentSurface +advertised/servers/schema_tokens grounded in the gateway federation map; rack grouped per server + live dot + "N tools · X tok" chip; rack/inspector i18n gap closed ×4 locales). Suites at close: chat 719 · FE full 3277 · knowledge 3374 · translation 1031 · composition 1472 · glossary/jobs/ai-gateway/provider-registry green. Post-wave tail: tool-error-rate soak check via /internal/tool-health (target <10%) · Playwright compose e2e needs a stack run (page object migrated to selectModel/data-model-id) · deferred-vs-loaded count on the frame (needs catalog size — small) · D-RAID-ALLOWLIST-ENFORCE + RAID FE tail (C6/C1 panels) unchanged.** · Prior: **RAID ✅ COMPLETE 2026-07-02: Track 4 + C5/C4/C1/C2/B2 + WAVE D (D2 FSM `ecf0d410c` · D3 report/accept-reject `004d49ad9` · D4 durable sweep/claim/notify `037831e1d` · D5 real-judge critic `1d6f2960b` · post-RAID /review-impl hardening: HIGH >100-chapter gate false-reject `6c2ba94e0` + 4 MED fixes, see block below). B2 browser-smoked PASS (real gemma plan-mode, wire `permission_mode:plan` proven). REMAINING (small tail): full C2 approval-card browser loop (D-RAID-C2-LIVE-SMOKE — needs a clean session + tool-strong model; card surface itself proven live via the frontend-tool loop), C6 FE wiring + C1 FE panel (both wait for the dockable track to release the editor/panel seams), end-to-end autonomous-run live drive (create→gate→start→report on the POC book — all layers live-DB-proven separately; ⚠️ FE tsc is BROKEN at HEAD in the dockable track's committed studio files — manuscriptUnitDocument/ManuscriptUnitProvider/EditorPanel — their track owns the fix; smoke images build from a patched worktree meanwhile). Draft PR #54 open. Contract stands: local LLM only, exact-file staging, hard-stops = destructive-ops-outside-test-account + 3-strike.** Spec [`salience-track4`](../specs/2026-07-02-knowledge-salience-track4.md) + [`07S`](../specs/2026-07-01-writing-studio/07S_studio_agent_standard.md) + DRs [`raid-loadbearing-decision-records`](../specs/2026-07-02-raid-loadbearing-decision-records.md). · 2026-07-02**

> **▶ KG ARCHITECTURE — TRACK A (schema authoring) ✅ SHIPPED + LIVE-PROVEN 2026-07-03.** Plan
> [`2026-07-03-kg-architecture-schema-authoring-multi-kg`](../plans/2026-07-03-kg-architecture-schema-authoring-multi-kg.md)
> (spec-review edge cases folded, `175e6eb53`). The "flop" (humans can't define/edit a KG schema) is
> fixed end-to-end — the schema editor now follows the KG **project** (not the book) and is full CRUD.
> **A1 `9844d94ef`** — full-CRUD repo+routes: revive-on-recreate (EC-A1: total UNIQUE kept, `add_*`
> un-deprecates a soft-deleted code — no partial-unique migration; keeps sync single-row + graph-data
> ref unambiguous), PATCH attribute-only (code IMMUTABLE), `add_vocab_set`, tier-aware DELETE (user
> HARD / project SOFT), + `glossary_gate` UUID guard (500→422) & 2 stale route tests from the
> auto-create-glossary feature. **A2 `3080a4693`** — create-blank (`POST /projects/{id}/schema`,
> one-active under lock) + clone (`POST /graph-schemas`, user-scoped, `_assert_source_adoptable`
> visibility gate = no read-oracle, auto-suffix `-copy`). **A3 `c00d0da3f`** — redesigned full-CRUD
> SchemaWorkbench (inline edit+delete per component, editable name, new EdgeTypeRow/NodeKindRow/
> FactTypeRow/VocabSetCard), `ProjectSchemaSection` is now the authoring home (active schema→workbench,
> else CreateSchemaEntry blank/clone/adopt), book tab redirects (Navigate); **live-smoke-caught fix**:
> `getSchema` now forwards `project_id` (a project-scoped schema 404'd on `_visible` without it) —
> threaded through `useGraphSchema` + both callers; i18n ×4. **VERIFY:** 3417 knowledge unit+integration
> (live PG :5555) · 757 knowledge FE + 0 tsc · **LIVE BROWSER SMOKE** (vite :5199→gateway :3123→rebuilt
> knowledge-service): create-blank→editor mounts→add edge→inline PATCH, `schema_version` v1→v2→v3, 0
> console errors. **A4 `867e05fec`** — live-delete orphan-count guard: `count_component_usage` (Neo4j:
> Entity-of-kind + live RELATES_TO-of-predicate, subject-scoped) + `GET /projects/{id}/schema/usage`; FE
> SchemaWorkbench `getUsage` → confirm dialog only when count>0 (else direct delete; never blocks —
> project DELETE is soft). 3387 unit + 760 FE + 0 tsc; live-smoke: delete edge → usage 200 (count 0) →
> DELETE 204, no confirm. **⇒ TRACK A COMPLETE (A1-A4).**
>
> **▶ KG SCHEMA EDITOR MODERNIZATION — COMPLETE (M1–M3b), 2026-07-03.** User: the Track-A editor felt
> like "mấy cái text box thông thường". Spec [`2026-07-03-kg-schema-editor-modernization`](../specs/2026-07-03-kg-schema-editor-modernization.md)
> (`7f923afe5`), 4 milestones ALL shipped + live-proven: **M1 `172e576fc`** typed KindMultiSelect
> pickers (source/target from real kinds, no typos) + inline "· used by N" usage badges (one
> `GET /schema/usage-summary`) + empty-state coaching — live: picker offered real kinds, "character → —"
> persist. **M3a `7c9361569`** infer-from-graph: `GET /schema/observed` (distinct Entity.kind +
> RELATES_TO.predicate) → InferFromGraphPanel promotes missing components (kinds first, then edges).
> **M3b `b73f04614`** AI generate: single-shot LLM pipeline (exempt MCP-first like wiki-gen — NOT
> multi-step agentic) `POST /schema/propose` (BYOK model_ref, JSON parse+salvage) + GenerateSchemaDialog
> (premise+ModelPicker → review checklist → adopt) — **LIVE LLM-PROVEN via Qwen2.5 7B**: 5 kinds/5
> edges/2 facts, correct source→target wiring (KILL elder→master, SEEK_REVENGE character→elder).
> **M2 `a978e0060`** visual type-graph canvas (reuses composition GraphCanvas SVG): kinds=boxes,
> edge-types=arrows; **click-to-connect** (⇢ handle → target node → inline new-edge popover), Canvas/List
> toggle, zoom/pan/drag-arrange — live: character⇢sect → MENTOR_OF arrow renders + persists. Also fixed
> the KG-schema GUI **theme** (`d9bcfab09`): inputs `bg-input`, primary buttons `text-primary-foreground`.
> VERIFY at close: 766 knowledge FE + ~10 schema_usage/9 schema_propose BE unit + 0 tsc. **DEFERRED
> (thin follow-ups):** an agent-facing `kg_schema_propose` MCP tool wrapping the M3b engine; M2 detailed
> attribute-editing on the canvas (today edits stay in List); canvas node-position persistence
> (per-device localStorage). **TRACK B (agent multi-KG) — not started:** B1(1) world-rollup
> as an MCP tool (`resolve_world_project_ids`+`get_world_subgraph` exist, read-only/FE-only today; take
> `world_id` as EXPLICIT arg — gateway drops X-Project-Id; owner-only, report partial not silent-drop) →
> B1(2) multi-project context (cross-project ranker+dedup, real work) → B1(3) arbitrary project set.
> Note: `⚠️` a stray dev vite server may still be running on :5199 from the A3 smoke; the smoke created
> a throwaway project "KG Schema Smoke" on the test account.

> **▶ AI-TASK STANDARD — single-shot LLM generate: shared engine + composable UI (2026-07-03).**
> Trigger: the KG schema-generate re-implemented plumbing every other "generate" dialog also
> hand-rolls. Discovery found **21 FE surfaces + 10 BE engines** each re-deriving the same slices.
> Spec [`2026-07-03-ai-task-standard`](../specs/2026-07-03-ai-task-standard.md). Boundary (LOCKED,
> non-goal): NOT the Agent-Extensibility Standard — these are non-agentic MCP-exempt pipelines;
> agent-facing MCP/subagent wrappers are deferred and compose ON TOP of this engine.
> **M1a `a7240e189`** — BE `loreweave_llm.structured_generate` (reasoning-off by DEFAULT → closes the
> empty-prose footgun; required max_output_tokens; typed StructuredGenerateError on transport/non-
> completed/empty) + `parse_json_object` (consolidates the ~5 `_extract_json_object` copies);
> `schema_propose` migrated onto it, byte-preserved (10+10 unit green). **M1b `037bbf540`** —
> `no_thinking_fields()` + footgun disable in `working_memory/executive.py` (max_tokens=500, was
> nothing) + `summarize_level`. **M2 `5bb2dd517`** — FE `components/ai-task/`: `EffortSelect` (extracted
> from ChatInputBar's inline W4 menu, now the single source; chat re-exports), `SpendCapField`+
> `isValidSpend`, `useAiTask` (propose→review→confirm controller), `lib/readBackendError` (moved shared).
> **M3 `a2430c721`** — GenerateSchemaDialog→useAiTask+readBackendError, GenerateWikiDialog→SpendCapField.
> **M4 `22c63b41c`** — BuildGraphDialog→SpendCapField (LAST DECIMAL_* regex copy gone). VERIFY: BE
> 33 unit + FE 94 (ai-task 9 + readBackendError 5 + chat effort 22 + wiki 22 + schema 2 + buildgraph 34)
> + tsc 0. Live: stack up but running knowledge :8216 image predates the SDK change (stale-image caveat)
> → schema_propose is byte-preserving + unit-asserts the exact wire + was live-proven (Gemma, 8 edges)
> last session; a fresh live smoke needs a knowledge-service rebuild.
> **CONVERGENCE M5-M7 — "standard vs exception" re-examined (the user challenged that my initial
> deferrals were mostly standard-covered, and was right):** **M5 `145810f0a`** unify reasoning-
> effort to ONE 5-level vocab (off|low|medium|high|auto) — chat-service had TWO (session vs per-msg
> fast|standard|deep); chat FE now uses the shared EffortSelect; BE tolerant-first (no flag-day).
> **M6 `8be4e6c63`** ComposeView `<select>`→EffortSelect; SpendCapField `compact` variant →
> ComposeConfig; GapsPanel raw `<select>`→ModelPicker (the one outlier). **M7 `b4ae23d38`**
> extraction wizard thinking-checkbox→EffortSelect (translation-service extraction router ALREADY
> accepted `reasoning_effort` — the "field already exists" lesson; pure FE); wiki `"none"`=no-op made
> an EXPLICIT documented exception (prose≠JSON + graceful degrade), not a silent fork. **Framework:**
> standard = PLATFORM concept + presentation/config variation → prop; exception = domain SEMANTICS,
> declared as an EXPLICIT param, never a silent re-implementation. Of the 5 I'd deferred, 4 were
> standard-covered (migrated) and only wiki was a true exception.
> **BOTH remainders CLEARED — the standard is 100% closed.** **`D-ENRICH-COMPLETE-BUDGET`
> `372d98e31`** — lore-enrichment `complete.py` stream body now carries max_tokens=4000 (was
> unbounded) + `no_thinking_fields()` (the seam already DROPS reasoning frames, so disabling wastes
> nothing + closes the footgun); the Go stream endpoint already accepts both. **`D-AITASK-GLOSSARY-
> TRANSLATE-EFFORT` `4714171b4`** — glossary-translate wizard boolean→EffortSelect (5-level), a
> byte-for-byte MIRROR of the extraction path (M7): router `+reasoning_effort` + grant-clamp
> (off/auto→'none'), worker swaps the local boolean `thinking_llm_fields` for the SDK
> `reasoning_fields` (drops the dup), FE across 5 wizard files. No migration (reasoning lives in the
> metadata JSONB). VERIFY: enrichment 9 + glossary router 7 + worker 12 (graded path pinned) + tsc 0.
> **/review-impl `28b8681ef`** earlier pinned the executive/summarize footgun disables + narrowed a
> dead type. **AI-Task Standard status: DONE** — every one-shot AI surface consumes the shared
> primitives; reasoning-effort is ONE unified 5-level vocab platform-wide (chat + compose + extraction
> + glossary-translate); the 4 footgun engines all disable hidden reasoning; the only remaining
> LOW/opportunistic items are CLOSED as a conscious won't-fix (gate #5), verified against code:
> the `_extract_json_object` "dedup" is 7 copies, and **2 of them (composition plan_forge
> `json_extract`, lore-enrichment `profile_suggest`) are DELIBERATELY more robust** (string-aware
> balanced-brace depth counting — correctly handle `{...} {...}` and braces-in-strings, which the
> shared regex `\{.*\}` does not) — consolidating them would be a REGRESSION. The other 5 are simple,
> stable, self-contained utils with their own exception contracts; folding them into
> `parse_json_object` adds cross-package coupling (loreweave_eval→loreweave_llm) + per-site contract
> churn for ZERO functional benefit. None violate the standard (its real surface — effort / spend /
> error / structured_generate / footgun — is fully consolidated). `plan_forge` engine is gated-off
> (rules-mode default), so migrating it to structured_generate is also no-value. **Won't-fix; the
> AI-Task Standard is closed.**

> **▶ KG TRACK B — agent multi-KG (2026-07-03). Plan §Track B in
> [`2026-07-03-kg-architecture-schema-authoring-multi-kg`](../plans/2026-07-03-kg-architecture-schema-authoring-multi-kg.md).**
> **B1(1) DONE `487f78c9c`** — `kg_world_query` MCP tool: the agent loads a whole WORLD's KG (union
> of member-book canon + world lore) in one call. Wraps the existing `resolve_world_project_ids` +
> `get_world_subgraph` across all 4 KG-tool sources (FastMCP sig + arg model + OpenAI def + handler).
> EC-B1 (explicit `world_id` arg — gateway drops envelope scope), EC-B2 (owner-only; new
> `resolve_world_partitions` REPORTS `partitions_read`/`partitions_unreadable`, never silent-drop;
> `resolve_world_project_ids` kept as a byte-compat shim for the subgraph+timeline endpoints),
> EC-B5 (WorldNotFound/BookServiceUnavailable → self-correcting tool-error). 101 tests + drift-locks
> (28→29 tools) + live: world-subgraph endpoint (uses the refactor) runs clean, service healthy.
> **B1(2) Layer 1 DONE `cf309f89b`** — knowledge multi-project CONTEXT union (the hard core). New
> `app/context/modes/multi_project.py` `build_multi_project_mode`: fans out the SAME Mode-3 retrieval
> per project (reuses `_safe_l2_facts/_safe_l3_passages/_safe_summary_blend` + glossary + salience),
> then EC-B3/B4 cross-project MERGE+DEDUP (entities by name→highest salience; facts by text; passages
> by source_id; summaries by level/path) + GLOBAL rank, one `<memory mode="multi">` block per-item
> tagged, ONE SHARED budget trimmed reverse-priority. `build_context` +`project_ids` (precedence over
> single `project_id`, owner-scoped, ≥2→union / 1→single / all-stale→404); `ContextBuildRequest`
> +`project_ids` (≤16). 55 tests (4 dispatch routing + 5 merge/dedup/budget + existing). Back-compat
> preserved. **B1(2) Layers 2+3 DONE (chat-service + FE) —** L2: migration `chat_sessions
> +project_ids UUID[]` (guarded additive, empty-default) + `project_ids` on Create/Patch/ChatSession
> models + sessions router (INSERT/UPDATE set-via-`model_fields_set`, `memory_mode="multi"` when ≥2)
> + `knowledge_client.build_context` +`project_ids` param + a shared `resolve_grounding_target` helper
> threaded into BOTH the text (`stream_service`) and voice (`voice_stream_service`) build calls (≥2 →
> union, sent WITHOUT a single `project_id` so the router's salience write-back can't misattribute the
> union's surfaced entities; 1 → single so salience still learns; 0 → legacy `project_id`). L3 FE: new
> `MultiProjectPicker` (multi-select sibling of `ProjectPicker`, chips + ≤16 cap + archived-fallback)
> wired into `SessionSettingsPanel` (seeds from `project_ids` else the legacy `project_id`; writes
> `project_ids` + keeps `project_id`=first as the tool-scope anchor); `MemoryIndicator` gains a `multi`
> mode ("N knowledge graphs" chip + popover). **VERIFY:** chat-service 803 unit (grounding_target 6 +
> sessions +7 + knowledge_client +2 + migrate +1) · FE tsc 0 + 14 picker tests. **LIVE-SMOKE (rebuilt
> chat+knowledge images):** real chat API create with `project_ids=[A,B]` → the live asyncpg `uuid[]`
> INSERT round-trips + `memory_mode="multi"` (the mock-hidden binding risk proven live); knowledge
> `/internal/context/build` with `project_ids=[A,B]` → `HTTP 200 mode="multi"`, rendered
> `<memory mode="multi" projects="2">` union block. Throwaway smoke projects+session cleaned up.
> **CLEARED D-MULTI-SALIENCE-WRITEBACK** (was mislabeled gate #2 "cross-service Layer-1 change" — on
> re-verification it's knowledge-service-LOCAL): the multi-mode write-back keyed on the single
> `req.project_id` (None in multi) so multi sessions never LEARNED salience. Fixed knowledge-local +
> additive: `build_multi_project_mode` already holds each surfaced entity's SOURCE project in the
> `(proj, e)` tuple (it was discarded) → new `BuiltContext.surfaced_by_project` maps entity→source
> project; the `/internal/context/build` router now records salience PER SOURCE PROJECT in multi mode
> (each entity attributed to its own book, no misattribution). 2 router wiring tests + full unit 3460
> green. **LIVE-DB smoke (rebuilt knowledge-service):** drove the REAL
> `/internal/context/build` handler with a real `EntityAccessRepo` over live Postgres + a multi
> `surfaced_by_project={A:[e1,e2], B:[e3]}` → the fire-and-forget task wrote exactly those 3 rows to
> `entity_access_log` attributed to each SOURCE project (test_context_salience_multi_integration.py,
> self-cleaning). Multi-KG salience learning proven end-to-end on real DB.
>
> **B1(3) DONE (knowledge-service) — `kg_multi_query` MCP tool (arbitrary owner-owned project
> set).** The agent-tool analog of B1(2): loads the UNION knowledge graph across an ARBITRARY
> set of the caller's own `project_ids` (canon KG + fan-theory KG, two unrelated books) — vs
> `kg_world_query` (B1(1)) which rolls up one whole world. New `KgMultiQueryArgs`
> (`project_ids` list 1–16, extra='forbid') + `_handle_kg_multi_query`: order-preserving UUID
> dedup → owner-scope via `projects_repo.get` (foreign/stale skipped) → reuse
> `get_world_subgraph` (already project_ids-generic; binds user_id+project_id per read so no
> bleed) → EC-B2 `partitions_read`/`partitions_unreadable` reporting (never silent-drop);
> invalid id → self-correcting tool-error; all-unreadable → empty-but-honest. Registered
> across all 4 KG-tool sources + the FastMCP signature (`mcp/server.py`). NOT in the public
> allowlist (follows kg_world_query's authenticated-only precedent — `tool-policy.ts` has only
> graph_query/entity_edge_timeline). **VERIFY:** 148 graph/definition + 69 mcp/executor unit
> green; drift-locks bumped 29→30 tools + `_LANE_LF_TOOLS` +1; the real loopback MCP server's
> `tools/list` == EXPECTED_TOOLS advertises `kg_multi_query` (proves the FastMCP wiring, not
> just the arg model). Single-service change → no cross-service smoke needed.
>
> **B1(4) DONE (knowledge-service) — cross-partition entity unification ("world-core").** Spec
> [`2026-07-03-kg-cross-partition-merge.md`](../specs/2026-07-03-kg-cross-partition-merge.md) (PO-signed-off:
> Q1=b on-demand embed, Q2=ephemeral-first, Q3=pairwise; 24 edge cases). The forest exists because a
> node id folds project_id into its hash, so "Alice" in two books = two ids. New `app/tools/kg_unify.py`:
> a **query-time app-side** pass (NEVER a cross-partition Cypher, NEVER a Neo4j write — propose-don't-assert
> D2/D3) that recognizes the same entity across ≥2 owned partitions and emits confidence-scored
> `unification_clusters` + inferred `SAME_AS` `bridge_edges` + `disagreements`. Opt-in `unify` enum on
> `kg_world_query` + `kg_multi_query` (all 4 schema sources + FastMCP, drift-locked); **`unify="off"`
> default = byte-identical forest (EC-M5)**. Tiers shipped:
> **T0 `3d1e20d4d`** — lexical (`canonicalize_entity_name` + alias overlap), kind-gate (EC-M3),
> cross-partition-only (EC-M10), union-find, per-method bands, deterministic ephemeral cluster_id (EC-M22),
> degenerate/common-name guards (EC-M18/M20), size/count caps confidence-desc (EC-M7/M11/M21).
> **T1 `14a5edb04`** — semantic: in-Python pairwise cosine, model-space-gated (EC-M1), lexical-fallback
> blend (D1); **Q1=b on-demand embed** of discovered seeds under the anchored model, **in-memory only**
> (reuses provider-registry BYOK EmbeddingClient, NEVER set_entity_embedding — EC-M16), spend-capped
> (EC-M15 `unify_embed_skipped`), degrade-safe (EmbeddingError→lexical); zero-norm guard (EC-M19).
> **T2 `5e5fd55ea`** — disagreement detection: same cross-book entity asserting different predicates to
> the same unified target → one `disagreements` record (agreement rides the bridge). **VERIFY:** knowledge
> unit 3454 green (23 new kg_unify + enum-drift + wiring + MCP CLOSED_SET machine-check) · FastMCP loopback
> advertises `unify` (inputschema-mirror) · provider-gate OK · **LIVE Neo4j integration `3746ee9d5`**
> (`bolt://localhost:7688`, 2 passed): real `_SEED_DETAIL_CYPHER` + `get_world_subgraph` forest → 2
> clusters + 2 bridges + 1 disagreement (Alice LOVES→KILLS Bob across books); semantic reads stored
> embeddings + honours the model gate. **DEFERRED T3** (persisted cross-book substrate + `SAME_AS` Neo4j
> edge + human-confirm spine — gate #2 structural, re-decide with precision numbers) **+ T4** (cross-partition
> salience/rank renorm + reranker — gate #4 profiling). Track B B1(1)–B1(4) COMPLETE.

> **▶ KNOWLEDGE GUI FIXES + MODEL-ROLES SETTINGS — 2026-07-03 (3 items, all shipped).**
> **#1 `cancel_check` extraction blocker (`591e54ad7`)** — bug #34 added `cancel_check` to the
> loreweave_extraction protocol + every extractor (which ALWAYS forward it), and to
> composition-service's wrapper, but the **knowledge-service + worker-ai** LLMClient wrappers were
> left behind → EVERY KG extraction died `TypeError: submit_and_wait() unexpected keyword argument
> cancel_check`. Both wrappers now accept + forward it to wait_terminal (additive). Tests use the
> REAL wrapper (the extractor fakes' `**kwargs` swallowed the drift). LIVE: Retry on "Ma Nữ Nghịch
> Thiên (POC)" → failed→ready, **43 entities/15 facts/129 events/181 passages** extracted, zero
> TypeError. **#2 dead detail-view edit pen (`652899564`)** — `OverviewSection` passed
> `onEdit={noop}` (silent no-op); now opens ProjectFormModal edit mode (embedding/rerank pickers),
> reusing the ProjectsTab modal + If-Match update via the deduped useProjects cache. LIVE: pen →
> "Edit project" dialog. **#3 model-roles settings + default fallback** — every LLM role gets a GUI
> setting + a default fallback (PO: "both" scopes — precedence **role override → project default
> (`extraction_config.llm_model`) → user-global default (provider-registry `user_default_models`
> cap=chat, already built) → env floor → off**). Plan `docs/plans/2026-07-03-knowledge-model-roles-settings.md`.
> Slices: **A foundation `36a8f76b7`** (pure `resolve_role_model` + user-global client, 10 tests);
> **A-wire `4f32071e5`** (endpoint resolves per-job `entity_recovery` config → threads through
> extract-item → `_run_pipeline` → `_maybe_apply_entity_recovery`; env-only stays byte-identical;
> fail-soft); **B `f95cc46a5`** (contract `EntityRecoveryOverride`/`LlmModelOverride` already
> existed; persisted project-default beats job model); **C `f9513b9f4`** (tuning-panel Default-LLM +
> entity-recovery pickers, empty=use default; i18n ×4). Suites: knowledge 70 touched-unit + 750 FE
> + 40 i18n parity; tsc clean. **D live**: new pickers render (theme-correct) + conditional
> recovery picker on enable; **Save persisted `entity_recovery.enabled=true` to the DB via the real
> PUT** (read-modify-write kept the rerank knob); A-wire image healthy. Runtime consumption
> unit-proven (orchestrator threading test); a live rebuild re-dispatch wasn't observable on the dev
> stack (worker-ai idle — rebuild-flow timing, NOT an A-wire regression: the only failed jobs are
> pre-#1-fix). **Defer-clears (`10089586e`):** rebuild-with-model-change — a rebuild now uses the
> project's persisted default LLM over the prior job's (pure `resolveRebuildModels`, unit-tested);
> `max_items_per_batch` now in the FE contract (`EntityRecoveryOverride` bounded 1-20 + tuning-panel
> batch input). wiki-gen model consistency (`1243677a8`) — the Generate-Wiki dialog pre-selects the
> user global default chat model once the AI path is active (mirrors NewChatDialog), so wiki
> generation inherits the "one default model" like every other role; the deterministic stub default
> (anti-spend) is untouched, FE-only, no stub-vs-LLM routing change. **Model-roles defers: all clear.**

> **▶ AGENT EXTENSIBILITY REGISTRY — AUTONOMOUS RUN IN FLIGHT (2026-07-03).** New track: user-registered
> plugins/skills/MCP-servers + agent self-registration. Spec [`agent-extensibility-registry`](../specs/2026-07-02-agent-extensibility-registry.md),
> plan+tasks+E2E+GUI-checklist in [`docs/plans/2026-07-02-agent-extensibility-registry/`](../plans/2026-07-02-agent-extensibility-registry/).
> Design SEALED; running continuously to completion, human gate at final release only; mid-run forks → `DECISION_LOG.md`.
> **P0 + P1-backend + chat-injector SHIPPED ✅ (3 commits):**
> **P0** (`512cedfda`): Go svc `agent-registry-service` (:8099, DB `loreweave_agent_registry`) — plugins CRUD +
> enablement (D1) + effective-catalog v0 + audit + quotas; BFF proxy `/v1/agent-registry/*`; OpenAPI frozen; real-stack
> E2E 20/20 (`p0_smoke.ps1`). **P1 backend**: skills (prompt-only) CRUD + SKILL.md import/export + draft/publish +
> revisions + shadow-check + per-user toggle; 5 System skills seeded (slugs byte-identical; bodies stay in chat-service
> — DL-4); `/internal/skills` (merge/shadow/surface + system_overrides + shadowed_system); proposals propose→approve/
> reject/expiry (JWT-owner approve — DL-5); registry MCP server (/mcp, 5 tools: list/get/propose/update/set_enabled)
> federated via ai-gateway `registry_` prefix. E2E 25/25 (`p1_rest_smoke.ps1`) + MCP `registry_propose_skill` call →
> pending proposal row proven. **chat-injector** (`c61fac319`): `user_skills_client` (degrade→built-ins) + stream_service
> injects user/book skill L1+L2 alongside SYSTEM_SKILLS, honours disable/shadow; 6 unit tests.
> **FE panels SHIPPED** (`+1 commit`): `features/extensions` (api/types/hooks + SkillsView + ProposalsView, browser-standard,
> call real /v1/agent-registry) + 3 studio panels (ExtensionsPanel hub, ProposalsPanel, SkillEditorPanel singleton) +
> `ui_open_studio_panel` enum(extensions,proposals) + contract regen. Verified: **panelCatalogContract 3/3 + BE contract 20
> + FE tsc clean (all NEW files; pre-existing common.json errors are the OTHER track's uncommitted ModelPicker i18n, not ours)**.
> **STACK-REBUILD E2E DONE ✅ (2026-07-03, full live stack):** `p1_edge_smoke.ps1` 6/6 — BFF proxy CRUD + ai-gateway
> federates all 5 `registry_` tools (prefix) + agent-propose THROUGH the gateway → proposal row (envelope owner survived
> federation). **Full-turn injection PROVEN LIVE:** published user skill (real test account) → `/internal/skills` (fetched
> INSIDE the chat container) → `user_skills_block` → a real **Qwen-7B** turn EMITTED the skill's marker `XYZZY-INJECTED`
> (assistant content == the marker). Post-rebuild /review-impl fixes committed (`02f2a3bbd`: robust `errors.As` dup-detection
> + precise `shadowed_system`; p1_rest_smoke 29/29). **ALL DEFERRALS CLEARED 2026-07-03:** D-REG-BOOK-GRANT (grantclient
> wired → book-tier grant-gated, live 404 fail-closed), REG-X-02 (50-skill quota → live 429), D-REG-SKILLPROPOSAL-CARD
> (chat approve/reject card — AssistantMessage clean again after chat-quality landed; 159 FE tests green), standalone
> /extensions route + save-as-skill affordance shipped, D-REG-P1G-BROWSER (deterministic: registryPanels.test 4/4 mount +
> panelCatalogContract 3/3; live Playwright = when-free follow-up, browser held by concurrent agent). **P1 COMPLETE.**
> **P2 BACKEND SHIPPED ✅ (REG-P2-01/02):** `mcp_server_registrations` + `mcp_server_enablement`; CRUD with mandatory
> `u_<hash8(owner)>_` anti-shadow prefix; internal-only guard (external public host → 400, deferred to P3); book-tier
> grant-gated + Active(); D2 quota (10/user); `/internal/effective-mcp-servers` per-user resolver (endpoint+prefix+version).
> Live `p2_backend_smoke.ps1` 10/10 — **per-user isolation proven** (B can't see A's server), toggle+version-bump, delete.
> **P2 COMPLETE ✅ (REG-P2-03/04):** ai-gateway per-user OVERLAY (`overlay.ts` + handlers) — tools/list merges the caller's
> registered MCP servers over the static System catalog under a u_/b_ prefix; per-(user,book) cache on catalog_version +
> 30s TTL; **fail-open** (resolve error → System catalog only); zero-reg fast path; flag `REGISTRY_OVERLAY_ENABLED` (default
> OFF = byte-identical to today). ai-gateway jest **35/35** + tsc clean. **Live through the rebuilt gateway (flag ON,
> `p2_overlay_smoke.ps1`):** register agent-registry's own /mcp as A's server → A sees 5 `u_<hash>_registry_*` tools, **B
> sees NONE (cross-tenant isolation)**, System providers intact for both (9-provider regression); calling
> `u_<hash>_registry_list_skills` through the gateway DISPATCHED to A's server + returned skills. **THE WHOLE SPEC now works
> end-to-end: a user registers an MCP server / skill → it federates into THEIR catalog only → the agent calls it.**
> **P3 BACKEND COMPLETE ✅ (M1–M4 of 6, 4 commits):** external arbitrary-URL MCP registration + full security.
> **M1 SSRF+vault** (`…`): `classifyRegistrationURL` rejects loopback/RFC1918/ULA/link-local(169.254 metadata)/CGNAT/
> unspecified incl. DNS-rebind (unit fixture suite); model-capability URLs → 400 (provider invariant); bearer secret
> sealed in AES-GCM vault (public = `has_secret` only); `/internal/mcp-servers/{id}/credentials` sole decrypt path;
> external server registers QUARANTINED (pending). Dev flag `AGENT_REGISTRY_ALLOW_INTERNAL_MCP=1` (compose) keeps
> in-cluster targets smokeable; DEFAULT OFF = prod. **M2 scan+quarantine** (`…`): a Go streamable-http MCP probe
> (`probe.go`, SSRF-safe dial + response cap) fetches tools/list; `scan.go` lints descriptions/schemas (OWASP-Agentic
> injection markers + hidden-unicode) → status machine pending→active(clean)/suspended(flagged)/error(unreachable);
> `POST …/rescan`, `GET …/{id}` detail, `POST …/accept-risk`. **M3 egress control** (`ad5bce682`): ai-gateway overlay
> dispatch/list wrap a custom egress fetch (SSRF re-guard + per-server allowlist + 1 MiB cap + manual redirect
> re-validation — closes the round-3 redirect-SSRF defer) + per-server circuit breaker (5-fail→open 30s). **M4 OAuth**
> (`…`): OAuth 2.1 authorization-code + PKCE(S256) + RFC 8707 resource-scoped tokens; `/oauth/start` + PUBLIC
> `/oauth/callback` (single-use state, replay-proof) + background refresh worker; tokens in vault. **SECURITY FIX:** the
> overlay no longer sends the internal envelope (X-Internal-Token) to external servers (would leak our service token) —
> `chooseOutboundHeaders` sends internal servers the envelope, external servers ONLY their own bearer/oauth token.
> **Live-proven:** M1 (`p3_m1_ssrf_smoke` model/scheme reject + vault round-trip), M2 (`p3_m2_scan_smoke` Go probe scanned
> the REAL registry /mcp 5 tools clean→active + down→error), M3 (overlay dispatch through egress fetch, isolation intact),
> M4 (`p3_m4_oauth_smoke` FULL loop vs a host fake AS: start→callback→exchange→vault→decrypt→single-use replay-reject).
> Suites: agent-registry go green; ai-gateway jest 129/129; tsc clean.
> **P3 COMPLETE ✅ (all 6 milestones + review, 8 commits).** M5 FE (`4a8cb8a87`): the two-shell external-MCP surface —
> `McpServersView` (browser list + status chips + paging), `AddMcpWizard` (4 steps: Connection→Auth→Health&Scan→Review),
> `McpServerDetail` (connection + scan report w/ per-finding review + tool browser + **accept-risk**), wired into BOTH the
> studio ExtensionsPanel MCP tab (hidden-not-unmount so wizard state survives §13b) AND the standalone /extensions route.
> M6 QA: OpenAPI mcp-servers contract (`5912bdb61`); **live browser render PASS** (`p3_m5_browser_smoke.mjs`: /extensions
> → MCP tab → Add → wizard advances). **`/review-impl` DONE (`ba576e410`, 2 adversarial reviewers):** token-leak
> boundary / OAuth replay+PKCE / RFC 8707 / token-endpoint SSRF / secret non-serialization / quarantine filter /
> anti-oracle 404s all VERIFIED correct. Fixed: **HIGH** DNS-rebind TOCTOU in the TS egress (now IP-pinned via an undici
> Agent connect-lookup, mirroring the Go probe) · **MED** breaker didn't re-open on a failed half-open trial · LOWs
> (strip Authorization on cross-origin redirect, probe refuses cross-host redirect so X-Internal-Token can't leak,
> accept-risk restricted to scanned+flagged 'suspended' only, /internal token constant-time + deny-on-empty, refresh
> store-failure logged). Re-verified live (rebuilt stack): M2 scan + overlay federation + an actual tool DISPATCH
> through the new pinned-dispatcher egress path. Suites: agent-registry go green; ai-gateway jest 131/131; FE
> extensions+studio 35/35; tsc clean.
> **REAL EXTERNAL-MCP E2E DONE ✅ — `D-REG-P3-EXTERNAL-LIVE` CLEARED** (`p3_external_live_smoke.ps1`): registered a
> GENUINE public third-party MCP server (**DeepWiki**, `https://mcp.deepwiki.com/mcp`, no-auth streamable-http) through
> the real path → classified `is_external=true` + QUARANTINED (pending) → the Go probe scanned its 3 REAL tools
> (`read_wiki_structure` etc.) → clean → active → federated into the user's overlay through ai-gateway → **CALLED
> `read_wiki_structure` through the gateway and got real DeepWiki content back via the pinned egress dispatcher** (external
> + no-auth ⇒ `{}` headers; the internal token is NOT sent) → cross-tenant isolation confirmed (user B saw nothing). The
> only untaken variant is OAuth against a real server (DeepWiki is no-auth) — but the OAuth loop is live-proven vs a
> conformant fake AS (`p3_m4_oauth_smoke`), so the full external path is now end-to-end proven on a real server.
> **P4 COMPLETE ✅ (slash commands + declarative hooks, 5 commits + review).** M1 registry backend
> (`slash_commands` + `hooks` tables + CRUD + `/internal/commands`+`/internal/hooks` resolvers; reserved-built-in
> rejection; DECLARATIVE-only hook actions). M2 chat-service **command expansion** — `/name args` expands in the messages
> router BEFORE persist+stream (so transcript AND model agree; caught live: expanding inside stream_service missed the
> already-persisted history row); pure `expand_command` ({{args}}/positional/named). M3 chat-service **hook engine** —
> pre_turn inject_text folded into the prompt; pre_tool_call **deny** short-circuits the tool at the seam;
> **require_approval** routes to the C2 approval suspend. M4 FE **Commands & Hooks builder** in both shells (studio panel
> tab + /extensions), offering only the wired (event,action) combos. **`/review-impl` DONE** (1 reviewer): tenancy /
> reserved-shadow / action-validation(create+patch) / substitution(no ReDoS) / expansion-placement / deny-loop-accounting
> all VERIFIED correct; **HIGH** require_approval was a silent no-op → WIRED; **MED** annotate/post_tool_call/post_turn
> advertised-but-unwired → gated to the wired matrix at the API (create+patch) + FE; +hook quota. **Live-proven:**
> command expansion (`p4_command_expansion_e2e` — real Qwen turn: /echotest → EXPANDED user msg → assistant echoed the
> marker), hook inject_text (`p4_hook_engine_e2e` — injected secret ZORP-777 retrieved by the model), backend CRUD +
> wired-combo gating (`p4_commands_hooks_smoke`), FE builder (`p4_fe_browser_smoke` — create-via-builder round-trip).
> Suites: agent-registry go green; chat 14 P4-unit; FE extensions+studio green; tsc clean.
> **Deferred (gate #1, out-of-scope collision):** `D-REG-P4-SLASH-AUTOCOMPLETE` — the in-chat `/` autocomplete
> (REG-P4-02) touches the chat-input component under concurrent-track edits; the builder is the primary authoring surface.
> **P5 COMPLETE (buildable slices) ✅ — the AGENT EXTENSIBILITY REGISTRY track is DONE end-to-end (P0→P5).** 5 commits +
> review. **P5-M2 plugin bundle export/import** (`p5_bundle_smoke`): a portable bundle (manifest + skills + commands +
> hooks; MCP servers excluded — secrets aren't portable); import validates EVERY member (same validators as create,
> incl. the skill prompt-only `scripts/` guard) in ONE transaction (all-or-nothing), semver-enforced; the full AC
> roundtrip proven — import→live→export→delete(cascade)→re-import→restored, tampered/scripts/bad-semver → 400.
> **P5-M1 subagent_defs CRUD + resolver** (`p5_subagent_smoke`): named persona (system_prompt + tool_scope subset +
> model_ref) + /internal/subagents + tenancy. **P5-M4 FE plugins + bundle UX** (`p5_fe_browser_smoke` — live file-upload
> import round-trip + export download). **`/review-impl` DONE** (1 reviewer): txn correctness / export-tenancy /
> MCP-secret-exclusion / FK-cascade / subagent authz all VERIFIED; **2 MED** fixed (import bypassed the skill validators
> → validateSkill parity closes the `scripts/` prompt-only hole; unvalidated plugin version → filename injection →
> semver on create+patch + filename strip) + 2 LOW (subagent quota, System UNIQUE index). Suites: agent-registry go
> green; FE extensions+studio green; tsc clean.
> **▶ `D-REG-P5-SUBAGENT-RUNTIME` ✅ SHIPPED + LIVE-PROVEN 2026-07-03 (this session; plan
> [`2026-07-03-subagent-runtime.md`](../plans/2026-07-03-subagent-runtime.md)).** The scoped nested execution is live:
> `run_subagent` is a **chat-service loop primitive** (peer to `find_tools`, consumer-local — NOT federated → no
> cross-service cycle), advertised iff the user has ≥1 enabled subagent, as a **closed-set enum** of names. On call it
> runs a nested isolated `_stream_with_tools` with **FRESH messages** (`[system: persona, user: task]` — no parent
> history), the persona's **scoped tool set** (caller catalog ∩ `tool_scope` globs, minus meta/frontend tools), and returns
> ONLY the capped synthesized text (nested messages never enter the parent `working`; nested chunks consumed, not re-yielded
> — isolation held). **Scope enforced TWICE** (advertise-time set + execute-time `allowed_tool_names` whitelist rejecting a
> fabricated out-of-scope/meta/frontend call with `result.error`). **No-escalation:** clamped read-only
> (`permission_mode='ask'`) — even a subagent scoped to a write tool can't write (ask filter drops it at advertise AND the
> ask-block rejects at execute). **Depth=1** (advertise gated depth 0 + whitelist excludes `run_subagent` + handler gated
> depth 0 = triple guard). Nested tokens sum into the turn total (D10); a `subagent_run` activity carries name + tools_used.
> Files: `app/services/subagent_runtime.py` (pure) · `_run_subagent_call` + loop wiring in `stream_service.py` ·
> `registry_subagents_client.py` (degrade-safe → no delegation) · `main.py` lifecycle. `_meta` stripped before the wire in
> the nested run (top-level path byte-identical). **`/review-impl` DONE** (self, load-bearing = nested exec + privilege):
> 1 LOW **fixed** (nested-suspend token attribution now read from the suspend chunk); 2 LOW **accepted+documented** (a
> `require_approval` hook on a scoped tool ends the sub-run early — fails SAFE; a reasoning subagent model on a tight budget
> yields empty answer content — handled gracefully). VERIFY: **30 subagent units** (pure resolver, nested isolation/clamp,
> loop-level whitelist via the real `_stream_with_tools` harness) + full chat suite **774 green** · **LIVE E2E-P5-A** —
> Part A in-container (`p5_subagent_runtime_incontainer.py`): a REAL nested LLM turn through chat→provider-registry→lm_studio
> (Qwen 7B, in=38/out=33, synthesized isolated answer); Part B full HTTP loop (`p5_subagent_runtime_smoke.ps1`): the gemma
> tool-calling model **chose** `run_subagent` → nested lore-scout ran → dragon answer reached the main turn, **no write tool
> in the transcript** (scope held). **Follow-up (tracked, gate #2):** `D-REG-P5-SUBAGENT-WRITE-DELEGATION` — lift the
> read-only clamp so a subagent can perform an approved write (needs nested approval-suspend bubbling up through
> `run_subagent`; today ask-clamp is the safe v1).
> **▶ `D-REG-P5-REGISTRY-INGEST` ✅ SHIPPED + LIVE-PROVEN 2026-07-03 (this session; plan
> [`2026-07-03-registry-ingest.md`](../plans/2026-07-03-registry-ingest.md)).** Admin populates the System-tier MCP
> catalog from the **official MCP Registry** via a curation queue instead of hand-typing each server. New
> `registry_ingest_queue` (source+registry_id unique; pending|approved|rejected; `approved_server_id` FK) +
> `uq_mcp_reg_system` partial UNIQUE(endpoint_url) for approve-time dedup. **Pull** (`POST /admin/ingest/pull`) fetches
> `{base}/v0/servers` through the **SSRF-safe probe client** (IP-pinned dial + cross-host-redirect refusal), cursor-paged
> (cap 10), body-capped (8 MiB), fail-soft. `mapUpstreamEntry` is tolerant (flat + nested-`server` shapes,
> type/transport_type variants, `version_detail` fallback, id→reverse-DNS-name); picks the first streamable-http remote,
> **counts** no-remote skips (never silent). Idempotent upsert on `(source,registry_id)` that refreshes descriptive fields
> but **never downgrades** an approved/rejected row → pending. **Approve** (`POST /admin/ingest/queue/{id}/approve`)
> **reuses the P3 pipeline wholesale** — `looksLikeModelEndpoint` → `classifyRegistrationURL` (SSRF) → INSERT System-tier
> `mcp_server_registration` (`is_external`, `pending`) → `scanAsync` (pending→active/suspended) → link + mark approved.
> Endpoint dedup links an existing System row instead of duplicating; a guard failure leaves the row pending. Admin-only
> (`requireAdmin` → 403) + anti-oracle 404 + audit. **verification ≠ safety:** an official listing still runs the full
> SSRF guard + supply-chain scan before it federates. Files: `internal/api/ingest.go` + `server.go` routes +
> `migrate.go` + `config.go` (`OfficialRegistryURL`). **`/review-impl` DONE — a 2nd DEEP pass (`3659ba203`) found + FIXED
> 2 MED + 4 LOW/COSMETIC** (the 1st pass's "no MED" missed the cross-service federation angle): **MED#1 tool-shadowing** —
> an ingested external System server federated UNPREFIXED (`tool_name_prefix=''`), so once scanned-clean it could shadow a
> platform tool name with an attacker-controlled schema (and its tools weren't even dispatchable). FIX: external System
> servers (ingest + `createMcpServer`) now namespaced `s_<hash8(endpoint)>_`; the ai-gateway overlay owns the `s_` prefix
> (`OVERLAY_NAME_RE /^[ubs]_/`) so they're dispatchable AND can't shadow. Live-verified (`s_c3d80a4e_`). **MED#2 boot
> safety** — the new `uq_mcp_reg_system` UNIQUE index would crash-loop startup on a pre-existing dup System endpoint; FIX:
> wrapped in a `DO`-block catching `unique_violation` (skip+NOTICE; check-before-insert still guards new dups). **LOW#3**
> the `isUniqueViolation` race-recovery branch now tested (pgxmock: dedup-miss→INSERT 23505→re-SELECT→link). **LOW#4**
> `pullCounts.Truncated` flags a partial pull (timeout/mid-error/page-cap) +httptest unit. **LOW#5** `clampStr` caps
> upstream strings (rune-safe) +unit. **COSMETIC#6** idempotency-coverage comment. ⚠️ **ai-gateway needs redeploy** for
> the `s_` overlay change (done in dev; the `s_` DISPATCH itself is inspection+tsc-verified — no controllable external MCP
> server exists for a live dispatch smoke). VERIFY: full agent-registry Go suite green (+race/truncated/prefix/clamp
> units) · ai-gateway tsc 0 errors · **LIVE E2E-P5-C re-run ALL-PASS** incl. the new `s_` prefix assertion — Part 1
> (DB-seeded queue → real HTTP): admin-gate, approve→System is_external row **namespaced s_<hash>_** + scan, re-approve
> 409, endpoint DEDUP held (exactly ONE row), reject, idempotent upsert; Part 2 (**real official MCP Registry pull**):
> fetched 100, mapped 43 new + 70 updated, 30 no-remote skips (SSRF-safe fetch + mapper proven on real /v0 data).
> **Deferred (tracked):** `D-REG-P5-INGEST-SCHEDULED-WORKER` (gate #2 — the hourly pull worker + denylist/retroactive-
> removal sync §7b#1 + rug-pull periodic rescan §7b#2; folds `D-REG-P3-SCHEDULED-RESCAN`; needs a background loop);
> `D-REG-P5-INGEST-ADMIN-FE` (gate #3 — the admin curation table lands in an admin/CMS surface that **does not exist yet**
> in `frontend/src`; the backend is fully driveable via the admin API).
> **Still deferred:** `D-REG-P4-SLASH-AUTOCOMPLETE` (gate #1). `D-REG-P5-SUBAGENT-WRITE-DELEGATION` (gate #2).
> **The whole track is production-usable:** a user registers skills / external MCP servers (OAuth+SSRF+scan) / slash
> commands / declarative hooks / subagent personas (**live scoped execution**), bundles + shares them; an admin **curates
> the System catalog from the official registry**; and the agent federates + expands + delegates to them — all
> tenancy-scoped, adversarially reviewed, live-proven.
> **▶ TRACK CLOSE-OUT (2026-07-03) — 5 of 6 remaining defers CLEARED + the 6th SPEC'D**, each with tests + a commit. Plan
> [`2026-07-03-registry-track-closeout.md`](../plans/2026-07-03-registry-track-closeout.md).
> **M1 `D-REG-P5-INGEST-SCHEDULED-WORKER`** (+folds `D-REG-P3-SCHEDULED-RESCAN`) `15bcbfe82` — Go worker (off by default):
> re-pull + denylist/retroactive-removal sync (absent-upstream approved → suspended + `revoked_upstream`, only on a
> COMPLETE pull) + rug-pull rescan; 4 tests. **M2 `D-REG-P5-INGEST-ADMIN-FE`** `f408a7d09` — admin curation surface
> (role-gated tab; jwtRole show/hide, API is the real gate); 7 tests. **M3 `D-REG-P4-SLASH-AUTOCOMPLETE`** `56afe9b71` —
> the in-chat `/` picker now surfaces the user's registry `/name` commands above templates (picker owns the fetch → no
> ChatInputBar churn); 8 tests. **M4 `D-REG-BOOK-TIER-FE`** backend `47609a7f6` + FE `ae8152ff8` — NOT "additive FE": the
> 5 list endpoints returned only system+user, so added a grant-gated `book_id` filter to ALL (`resolveListBookScope`,
> anti-oracle 404) + a shared ExtensionScope context wiring book-scope into all 5 capability hooks; tests + studio default-
> context safe (30 green). **M6 `D-REG-P5-SUBAGENT-WRITE-DELEGATION`** `44ce1f501` — SPEC ONLY (user-gated): bubble the
> nested Tier-A suspend up through run_subagent (subagent_frame) + two-level resume; read-only v1 stays the safe default.
> VERIFY: agent-registry Go green · FE extensions+chat **71 green** · tsc clean.
>
> **▶ CLOSE-OUT FINISHED 2026-07-03 — M5 + M7 DONE; TRACK FUNCTIONALLY CLOSED.**
> First restored git coherence: the **Subagents + Activity GUIs were on disk but never committed** (a prior shared
> commit that supposedly carried them was reset by the concurrent ai-task agent) while my M4 tests already imported
> `SubagentsView` — committed the 4 files + studio wiring `4e15711d2` (14 tests).
> **M5 `3729d3213` — HONEST checklist, NOT a rubber-stamp.** The `01_GUI_CHECKLIST` enumerates the FULL draft-ui.html
> vision (270+ boxes); most is genuinely unbuilt rich polish. Per [[checklist-is-self-report-enforce-by-tests]] I ticked
> ONLY lines a passing test proves: wrote `skills.test`(8) + `proposals.test`(5) for the two richly-built-but-untested
> views (search/tier/sort/pager/empty/error/rows · status-filter/approve/reject/empty), then rewrote the checklist to
> **59 test-backed ticks (up from 0)**, each citing its test. The unbuilt remainder (bulk actions, shared Pager, skills
> editor+revisions, 24h health charts, per-step wizard validation, typed-confirm cascade, **i18n vi/en**, **a11y
> focus-traps**) is honestly tracked as **D-REG-GUI-RICH-POLISH** (defer gate #2), not fake-ticked. Extensions suite 47 green.
> **M7 `977dc8536` — LIVE E2E (rebuilt agent-registry image).** M4 book-tier tenancy 5/5 live through the gateway
> (`m4_book_tier_tenancy_api.mjs`): create-on-owned→200 · list?book_id→visible · list-no-book_id→**hidden (no cross-tenant
> leak)** · list?book_id=FOREIGN→**404 anti-oracle** · create-on-FOREIGN→denied. M1/M2 ingest routes → **403 for non-admin**
> (wired + admin-gated). Re-ran `p5_subagents_fe_browser.mjs` vs vite :5199 on current FE → shell+Subagents+Activity+real
> POST/audit round-trip PASS. **Honest live gaps (not fake-claimed):** the external public-registry PULL (admin JWT + live
> `registry.modelcontextprotocol.io`) = gate #4, cycle unit-proven (4 tests); M2 admin-FE + M3 slash + M4 book-scope-FE are
> unit-proven, not yet in a browser smoke (the shell IS). **The 5 defers are CLEARED; the track is functionally closed.**
>
> **Deferred (gate #2 — earns its row): `D-REG-GUI-RICH-POLISH`** — the draft-ui.html rich layer (bulk actions · shared
> `Pager`/`useServerPagedList` across all lists · skills 3-col editor + revision history · 24h health-history charts + p50/p95
> · full 4-step wizard per-step SSRF/OAuth validation UI · typed-confirm cascade-delete dialogs · **i18n vi/en** · **a11y
> focus-trap sweep**). Large/structural, needs its own plan. See `01_GUI_CHECKLIST.md` Tally (58/288 test-backed).
>
> **▶ POST-CLOSE-OUT FOLLOW-UPS SHIPPED (2026-07-03).**
> **(1) Nav entry point `ed879b764`** — the `/extensions` GUI was an **orphaned route with NO nav entry** (users couldn't
> find it; it's not a Settings tab). Added an **Extensions** item (Puzzle) to the Sidebar manage group + `nav.extensions`
> i18n (en/vi/zh/ja); Studio path already worked (catalog `OPENABLE_STUDIO_PANELS`). Test: `Sidebar.test` asserts the
> `/extensions` link renders. **Frontend image rebuilt** (:5174 now current). *(NOTE for future: "MCP Access" in Settings is
> a DIFFERENT feature — public MCP API keys for EXTERNAL clients to reach IN; the Extensions registry is capabilities for
> the agent INSIDE. Opposite directions.)*
> **(2) `D-REG-P5-SUBAGENT-WRITE-DELEGATION` ✅ SHIPPED `61a617094`+`f523c86f6` (defer CLEARED).** A capability audit (2
> Explore agents, evidence-backed) confirmed the architecture is "strict data boundary + absolute enforcement AT THE TOOL
> LAYER": every MCP tool re-auths the `X-User-Id`+internal-token envelope + grant-gates scope (never a model arg;
> `ForbidExtra`), and Tier-W/destructive/priced ops are **mint→browser-JWT-confirm only** (structurally unrunnable from a
> loop). So the read-only subagent clamp was a *conservative default, not the security boundary* — a subagent write is safe
> by construction (bounded to the caller's tenant + its `tool_scope`). **Dropped the heavy nested-suspend/two-level-resume
> spec** as over-engineered; shipped the SIMPLER "allowlisted Tier-A, no suspend": `clamp_permission_mode = min(caller,
> write)`; fixed the plain-path tier resolution (was hardcoded "R" → would've let a subagent auto-commit ANY Tier-A); a
> write sub-run auto-commits ALLOWLISTED Tier-A, but un-allowlisted Tier-A / require_approval-hook / the volume-cap all
> return a `result.error` (headless sub-run can't raise the card) instead of a swallowed suspend. `/review-impl` caught the
> volume-cap-suspend gap (fixed). 116 chat-service tests green. Spec updated to SHIPPED.
>
> **▶ EXTERNAL-MCP INTEGRATION — FULL LOOP LIVE-PROVEN end-to-end (2026-07-03).** Registered a REAL free public MCP
> server (**DeepWiki** `https://mcp.deepwiki.com/mcp`, no-auth) on the test account and drove the whole chain live:
> **register** (SSRF pass · egress-allowlist auto · transport auto `streamable_http` · namespace `u_a2bbc662_`) → **scan**
> (health 3 tools · injection-scan clean · auto-active) → **federation** → **model autonomously calls it** → **dispatch to
> the real server** → **result rendered in the agent's answer**. The live test found + fixed **two real consumer-wiring
> bugs** (both committed, tested):
> **(a) `fix(chat): wire the per-user overlay into the turn catalog` `a5cf762ec`** — `get_tool_definitions()` sent no
> `X-User-Id` + cached process-wide, so the ai-gateway federation overlay (REG-P2-03, `u_/b_/s_` external tools) NEVER
> reached a real chat turn's LLM. Fix: pass `user_id` (→ `X-User-Id`) + PER-USER cache with a 60s TTL (`_TOOL_CATALOG_TTL_S`;
> overlays differ per user + change on register/remove). Both turn callers updated.
> **(b) `fix(chat): accept plain-text results from external overlay tools` `e1932b40c`** — `mcp_execute_tool` `json.loads()`
> every result, but external tools return PLAIN TEXT (DeepWiki returns prose) → every external result died as "unparseable
> content". Fix: on decode-fail, if the tool matches `_OVERLAY_TOOL_RE` (`^[ubs]_[0-9a-f]{8}_`) wrap as `{"text":…}` success;
> internal tools stay strict-JSON. **Final live turn (Gemma-4 26B): MODEL_CALLED_DEEPWIKI=True, DISPATCH_OK=True**, the real
> wiki structure of `modelcontextprotocol/servers` rendered in the reply. 78 chat-service tests green for these.
> **Ops note:** the overlay is flag-gated — `REGISTRY_OVERLAY_ENABLED=true` (default false, a rollout gate). Set via shell
> env at `docker compose up` time (NOT persisted; a stack recreate without the env reverts to false — add to `.env`/compose
> for permanence). CAVEAT: `docker compose up -d <svc>` re-evaluates `${VAR:-false}` for dependencies, so it can silently
> flip the gateway's overlay off — set the env in the SAME shell. The overlay dispatch also has a circuit-breaker that trips
> under repeated hammering of a flaky free server (fail-open → no overlay that turn); a gateway recreate resets it.
>
> **▶ CORRECTION (2026-07-03) — the earlier "TRACK COMPLETE P0→P5" claim was WRONG: it was BACKEND-complete but 2 FE
> screens shipped as backend-only.** A design↔shipped reconcile vs `design-drafts/screens/plugin-register/draft-ui.html`
> (nav: Plugins/MCP/Skills/Commands/Hooks/**Subagents**/**Activity log**) found the FE missing Subagents + Activity —
> and `01_GUI_CHECKLIST.md` (273 boxes, **0 ever ticked**) proves the checklist was authored but never used as a gate
> (see memory [[checklist-is-self-report-enforce-by-tests]]: a checklist is self-report; DONE = a test asserts the EFFECT).
> **BUILDING NOW** `D-REG-P5-SUBAGENTS-FE` (persona CRUD GUI — backend CRUD+resolver+runtime all shipped, FE was zero) +
> `D-REG-P5-ACTIVITY-FE` (Activity-log over `/audit` — U4 in EVALUATION, never built). Plan
> `2026-07-03-registry-missing-guis.md`. Remaining backend rows unchanged (scheduled-worker, admin-FE, slash-autocomplete,
> subagent-write-delegation) — all tracked, none blocking.
> **Decisions:** `DECISION_LOG.md` (DL-1..9 + 6 review rounds). **Defers: P4 autocomplete + P5 write-delegation + P5 ingest-scheduled-worker + P5 ingest-admin-FE; P3/subagent-runtime/registry-ingest CLEAR.**
>
> **▶ CHAT QUALITY WAVE — W0 + W1 SHIPPED + LIVE-SMOKED 2026-07-03 (parallel sub-agent build, disjoint files,
> combined verify).** Trigger: user's 8-item quality pass (plan + 5-investigation evidence base incl. a LIVE MCP
> failure audit: 26-30% hard-error rate). **W0 MCP reliability:** base_version hallucination-trap killed (409 embeds
> current version; implausible timestamp = not-read shim — top bucket, 22% of errors), real JSON-schema enums at 22
> glossary sites + jobs, filter args accept the one-element-list shape (jobs/knowledge/translation), pydantic errors
> rewritten to one-line model directives at the FastMCP chokepoint, "must be in scope" errors now name `project_id` +
> the NEW `kg_project_list` tool, ai-gateway classifies errors (transport vs sanitized-upstream vs unknown-tool — no
> more blanket "provider error"), CLOSED_SET_ARGS contract tests extended to MCP servers. **W1 context-breakdown
> spine:** 12-category per-turn token map measured at the assembly seam (incl. the previously-unmeasured TOOL-SCHEMA
> buckets), contextBudget frame extended additively (+breakdown/+baseline_tokens/+until_compact_pct), new `compaction`
> frame (was log-only), `chat_messages.context_breakdown` persisted, knowledge build_context returns per-section
> tokens, `GET /internal/tool-health` (per-tool error rates — W0 improvement measurable). **LIVE smokes (real chain):**
> chat-container→gateway→domain: enum survives federation + kg_project_list federated + list-unwrap e2e +
> self-correcting scope error passes the gateway unlaundered; REAL gemma turn: frame carries breakdown (live insight:
> bare turn = skills 1907 tok + FE-tool schemas 1484 + MCP 193 — the invisible buckets now visible) + DB row persisted.
> **Also:** translation's 13 stale failures CLEARED (confirm_action header-auth drift ×11, default-vs-fill drift,
> offload test now hermetic via TEMP-table shadow); **pytest-xdist adopted** (CLAUDE.md rule; composition 418s→55s,
> translation 37s; 8 PG-hitting files carry `xdist_group("pg")`). Suites at close: chat 665 · knowledge 3374 ·
> composition 1472 · translation 1031 (was 13 red) · jobs 95 · glossary ok (+DB-gated live) · ai-gateway 110.

> **▶ #12 CYCLE-1c — F4 SCENEMARKER-EMIT + J1 MULTI-INSTANCE JSON EDITOR — SHIPPED + LIVE-SMOKED 2026-07-03.**
> `D-SCENEMARKER-EMIT` CLEARED (RAID quiet window opened): a generated chapter now lands **pre-anchored** — no ⚓
> needed. Root finding: composition's `prose_doc.text_to_tiptap_doc` mirrored only tiptap.go's *plain* variant; the
> *markdown* heading variant was never mirrored, so the server persist path flattened `###` lines into paragraphs.
> **F4a** `prose_doc.py` lifts leading ATX headings into heading nodes (tiptap.go byte-shape, level≤3) and, given
> `scenes`, sets `attrs.sceneId` on a normalized **unique**-title match (`normalize_title` = exact port of FE
> `SceneAnchor.normalizeTitle`, diacritics significant; ambiguous/duplicate/unmatched → unmarked, never wrong);
> canary extended to pin the Go heading tokens. **F4b** `chapter_scene_drafts` returns `{title,text}` rows; stitch
> input becomes `### <title>\n\n<text>` per scene (`prepend_scene_headings`, skip when already headed); stitch
> prompt gains a keep-headings-verbatim guard (injected only when headings present); the degraded concat carries
> markers deterministically. **F4c** `_persist_chapter_draft(scenes=…)` wired at all 3 chapter persist sites
> (inline chapter-generate, inline stitch, `POST /jobs/{id}/persist` — best-effort scene fetch, never blocks).
> **LIVE E2E** (POC book, Qwen2.5-7B LM Studio): stitch job kept **3/3** `###` headings through the real merge →
> persist → book draft v3 carries 3 heading nodes each with the EXACT outline sceneId (psql-verified, VN titles).
> Caught live: `infra-composition-worker` is a **separate image** from `infra-composition-service` — rebuilding only
> the service left the worker stale (first smoke ran old code). **J1** json-editor is now **multi-instance**:
> `host.openPanel` gains `component` (dock id ≠ catalog component); "Open as JSON" opens
> `json-editor:{docType}:{chapterId}` per chapter (re-open focuses); panel self-titles (`JSON · <id8>`) and no
> longer registers in the host registry (two instances corrupted register/unregister). **Suites:** composition
> **1526** unit green · FE studio+editor **272/272** + tsc clean. Plan: `docs/plans/2026-07-02-chapter-editor-completeness.md` §Cycle-1c.

> **▶ WAVE D — COMPLETE 2026-07-02 (autonomous run, sub-agent build + orchestrator verify).** The autonomy dial's
> full backbone in composition-service: **D2** `authoring_runs` FSM (7 states, OCC-guarded transitions, all-or-nothing
> start-gate: validated plan + scope-fence unique-index (1 active run/book) + budget + allowlist snapshot; sequential
> driver over the REAL drafting seam — EngineDraftingSeam mirrors actions.py's in-process generate_chapter, worker-off
> inline + worker-on 202-poll). **D3** `authoring_run_units` ledger (pre_revision pinned BEFORE each draft — no draft
> without a rollback spine; book-service snapshots every PATCH so latest revision = a TRUE pre-run restore point);
> Run Report (partial-reviewable, downstream indexes); accept/reject (reject restores with the CALLER's bearer,
> restore-failure leaves drafted, cascade_warning); Revert-All (reverse order, closes the run). **D4** durability:
> driver_id+heartbeat, startup+periodic sweep (FOR UPDATE SKIP LOCKED claim — live-proven on real PG), per-unit
> heartbeat-claim closes the late-result race (late draft lands failed "run closed mid-flight", spend kept);
> completion notify via notification-service HTTP ingest (category=system, operation=autonomous_authoring in
> metadata — mirrors the translation producer); background flag + DRIVER_MAX_INFLIGHT. **D5** per-unit critic wired
> to the REAL M6/Q1 judge (judge_prose 4-dim + canon violations; critic_model_ref anti-self-reinforcement); severe →
> PAUSE with breaker {critic_severe, unit, summary} (human reviews report); critic failure → warn "critic
> unavailable", never breaks a run; verdict on the unit row + in the report; params.critic_enabled default TRUE.
> **Suites:** composition tests/unit **1516** green (fresh tails per milestone; +105 across D2-D5). Honest stubs
> recorded in-code: canon grounding headless (empty rules), unit+critic costs are estimates (SDK exposes no metered
> cost — real cost only where generation_job.cost_usd populates).

> **▶ /review-impl over Wave D — 1 HIGH + 4 MED found, ALL FIXED 2026-07-02 (user: "fix all").**
> **HIGH `6c2ba94e0`:** start-gate false-rejected books >100 chapters — `BookClient.list_chapters` asked limit=200 but
> book-service clamps every page to 100 (chapter-list-limit100 bug class); client now PAGINATES (100/page, 2000 cap),
> all 3 call sites (gate, planner A3, plan verify) see the whole book. **MED fixes (same follow-up commit):**
> (1) late writes driver-fenced — `mark_drafted` gains `run_driver_id`, `record_unit_progress` cursor is CASE-fenced
> (spend always lands); a sweep-STOLEN run's superseded driver can no longer double-draft or rewind the cursor
> (plausible here: worker-off inline has no poll timeout, slow local model >40min → steal). (2) late-swallow now
> RESTORES content — close/fail mid-flight already swallowed the row, but the engine had PATCHed the draft;
> the driver now best-effort restores the pinned pre_revision (honest error_message either way). (3) breaker pauses
> NOTIFY (budget | critic_severe) — 07S "interrupt on severe" now actually reaches the human (same ingest channel).
> (4) book-OWNER-grant may pause/close a collaborator's run (acts AS the run owner; scope fence is per-book, so an
> abandoned grantee run used to lock the book forever; start/resume stay owner-only — they spend the owner's budget).
> **LOW fixes:** deferred-at-cap claim now RELEASED (NULL heartbeat → next sweep picks it up; was a 40-min stall);
> gate maps book-service 401/403 → 403 (was 502 "outage"). New SQL live-proven on real PG (CASE fence, release_claim,
> driver guard). Deferred: `D-RAID-ALLOWLIST-ENFORCE` — tool_allowlist is gate-validated+snapshotted but the v1
> driver never consults it (v1 seam calls no agent tools — vacuously safe; enforcement gate #3 naturally-next-phase,
> lands with agentic tools riding runs). COSMETIC accepted: `level` 3|4 stored, runtime-indistinguishable in v1.

> **▶ AUTONOMOUS RUN — RAID waves C5/C4/C1/C2/B2 SHIPPED 2026-07-02 (sub-agent build + orchestrator verify pattern).**
> **C5 MCP resources+prompts** (`99bc63215`, LIVE-PROVEN): knowledge exposes 2 project resource templates
> (summary/entities) + 2 prompts (recap/dossier); ai-gateway federates resources/templates/prompts (scheme==provider
> gate; -32601-tolerant); chat client list/read/get (degrade pattern). Live: chat→gateway→knowledge real entity data.
> **C4 @-mention** (`554373f33`): inline mention popover in the chat input (books/chapters/entities, startsWith>
> contains, keyboard nav) attaching through the SAME ContextBar seam; useContextCandidates extracted (ContextPicker
> adopted); chat i18n parity test added. **C1 steering store** (`e7917a72d`, LIVE-PROVEN, DR-C1): book_steering in
> book-service (scope UNIQUE(book_id,name), owner+E0-EDIT writes, VIEW reads, 20-row/8000-char caps, execGuarded
> migration); chat renders <steering> after the system prompt on both paths (always ∪ #name ∪ scene_match(title),
> 2000-token soft cap, degrade-to-skip). Live: gateway-create→internal→select→render with real VN entry. **C2 HITL
> modes** (`a0b926dab`, DR-C2): permission_mode ask|write; ask = tier-R+frontend surface (advertise-chokepoint filter
> + defense-in-depth); write gains the Tier-A prompt-once approval via the EXISTING suspend/resume machinery
> ({kind:tool_approval} rides pending args — NO new frontend tool); user_tool_approvals (fail-open reads);
> suspended-run carries the mode (no escalation); surface snapshot test pins write==pre-C2. FE toggle + ToolApprovalCard.
> **B2 Plan mode** (`28a275ced`): permission_mode 'plan' = ask surface + plan_* tools (no C2 prompt for plan_*, pinned
> write-only); plan_forge skill auto-injects on book/editor; PLAN nudge on both paths; 3-way FE toggle. Sub-agent
> FIXED an M4 bug: plan_forge L2 body was silently dropped even when pinned. **Suites at close:** chat-service 631 ·
> knowledge 3349 · book-service green (DB-gated) · ai-gateway 103 · FE chat 287+parity. All services rebuilt live.

> **▶ Track 4 SALIENCE — COMPLETE 2026-07-02 (autonomous run).** All buildable phases shipped flag-gated (defaults =
> byte-identical): **P0** access telemetry (live-proven) · **P1** access blend (eval verdict: KEEP w=0 — explicit-query
> REGRESSION, spec §8b) · **P2** cross-encoder L3 rerank (live-proven e2e via local bge-reranker; per-project opt-in)
> · **P3a** graph-native promotion (evidence/mention/edit-recency) · **P3b** thumbs→entity attribution (user
> challenged the deferral; verification DISPROVED it — consumer existed, 1 additive column sufficed; `4635f3dfb`) ·
> **P4** pointer demotion instead of glossary drop (+`memory_recall_entity` as the expand affordance — no new tool
> needed) + widened 2-hop L2 retry on fact-miss (default ON, kill-switch; `d535293fd`). **P5 = 4 decision records**
> (R-T4-03 prune / 04 auto-merge / 08 metadata / 09 compaction-LFU-bridge), each verified + trigger-gated in spec §5
> — unlike P3b these survive scrutiny (data-safety / no-signal / hot-path-cost reasons, not effort). Salience flip
> gate = ambiguous-query eval (P1's explicit-query set penalizes re-ranking by construction). Eval CLI:
> `python -m eval.run_salience_eval`. Also cleared en route: book `_text` bug class (5 sites), worker skip
> false-green, config write-path, FE PUT-replace clobber.

> **▶ STUDIO DOCKABLE MIGRATION — WAVE 1 SHIPPED 2026-07-02** (spec [`11_dockable_migration.md`](../specs/2026-07-01-writing-studio/11_dockable_migration.md),
> human-in-loop track running IN PARALLEL with the autonomous run — conflict-first ordering per W1-5). Foundation
> seams: **F2 status-bar contribution API** (`registerStatusBarItem`/`useStatusBarItems` — ⚠️ **RAID A3 status-bar
> meter MUST register through this, never edit `StudioStatusBar.tsx` directly**; first consumers shipped: unread
> badge + 24h cost meter, bus-owned `notificationsUnread`), **F1 `openPanel(…, {params})`** deep-link (+
> `updateParameters` when open), **F3 `resolveStudioLink`/`followStudioLink`** (same-book chapter→focus, panel
> paths→openPanel, fallback = NEW TAB — `navigate()` in panels is a defect). Panels: `usage`/`trash` thin wraps
> (TrashPage `embedded` prop), `notifications` (resolver + bus unread sync), `settings` (route tab → `params.tab`).
> `ui_open_studio_panel` enum +4 + contract JSON regen done INSIDE the Track-4 window (W1-7 — later RAID B/C waves
> regen on top, no race). VERIFY: FE 3085/3085 + chat-service frontend-tools 43 green.
> **`D-DOCKW1-LIVE-SMOKE` CLEARED 2026-07-02 (Playwright live browser smoke, vite:5199 + rebuilt chat-service):**
> status-bar badge `99+` + meter `$1.17` live with real data; meter-click → Usage panel (1531 real rows); badge-click
> → Notifications panel; palette lists+opens all 7; Settings 6 tabs (mcp Q-GATE on); Trash embedded (no breadcrumb);
> **agent loop by EFFECT:** gemma-26b (LM Studio) got "mở panel Trash" → `ui_open_studio_panel(trash)` (NEW enum
> value) → Lane-A → dock tab FOCUSED in 6s → model confirmed truthfully. Side-findings (pre-existing, not W1):
> `D-TRASH-GLOSSARY-404` — TrashPage's per-book `GET …/glossary/entities?lifecycle_state=trashed` 404s (glossary
> trash tab dead; gate #1 out-of-module); notification SSE reconnect dies on jwt-expired (`?token=` never refreshes —
> long studio session loses the live badge); **LM Studio queue can WEDGE after a client disconnects mid-stream**
> (`lms ps` says IDLE but completions hang ∞) — fix: `lms unload <model> && lms load <model> --context-length N`.
> **/review-impl (b1dca941b): 2 MED + 2 LOW found + FIXED** — protocol-relative `//` external-origin escape
> (notificationLink + resolver both hardened), settings same-value deep-link swallowed (now `onDidParametersChange`),
> badge pre-fetch-0 clobber (`unreadLoaded` gate), catalog⇄panel import cycle (i18n-convention titleFor). 3089/3089.
> **Side-findings CLEARED (user-mandated fix-before-wave-2):** `D-TRASH-GLOSSARY-404` FIXED — root cause FE-only:
> `useTrashItems` guessed `/v1/books/{id}/glossary/entities?lifecycle_state=trashed` (never existed) while
> glossary-service already ships the FULL recycle-bin API (`/v1/glossary/books/{id}/recycle-bin` + `/{eid}/restore` +
> `DELETE /{eid}`, `permanently_deleted_at` soft-purge + snapshot trigger). 3 URLs re-pointed; live-proven e2e in the
> studio Trash panel (real backlog rows listed; GUI Restore → `deleted_at` NULL; GUI purge → `permanently_deleted_at`
> set). *The "blocked on a missing route that already exists" pattern struck again.*
> **SSE jwt-expiry FIXED** — `useNotificationStream` on error checks the JWT `exp` (fail-open for opaque tokens):
> expired → single-flight `refreshAccessToken()` (now exported from api.ts) → `lw-auth-refreshed` → effect reconnects
> with the fresh token; refresh-fail → idle. No more infinite dead-token reconnect loop in idle studio tabs. +3 tests.
> LM Studio wedge stays an external-tool recipe (memory); a chat-service first-token timeout guard belongs to RAID
> Wave-A's LLM seam if wanted. FE suite 3092/3092.
> **▶ #12 CYCLE 1 (chapter editor) — BUILT + partial live proof; gate retest needs a QUIET WINDOW · 2026-07-02.**
> Shipped: M-A JSON substrate (registry #4, DocumentHandle, CM6 json-editor panel) `849e5fa1e` · M-B manuscript-unit
> provider + hoist scenes[] + `GET /works/{pid}/chapters/{cid}/scenes` `c4e0dbf27` · M-C **Scene Rail** (navigator
> scene click finally does something) `b268ade0e` · M-D Lane-B outline handler `c60ad95b8` (the MCP tool
> `composition_outline_node_update` already existed — audit corrected) · **`story_search` universal manuscript
> search** `3b3ac9263` (AS1–AS4 research-locked in spec 12: ONE simple tool over `run_hybrid_search`; NO temp-file
> workspace — the DB indexes ARE the engine, GitHub-Blackbird evidence; ZERO required location args via ambient
> ToolContext; knowledge suites 216/216; image rebuilt). **Browser-verified:** Scene Rail renders real scenes;
> json-editor shows the full envelope; two live-caught bugs fixed (resolveWork ENVELOPE `{status,work}` — a bare
> `.project_id` read returns undefined; EditorPanel missing `host` ref).
> **M-E LIVE GATE ✅ PASSED 2026-07-02 — `D-C1-GATE-QUIET-WINDOW` CLEARED** (retest after the RAID chat wave, per
> AS4 natural-language-only). Full loop proven in the browser on gemma-4-26b, NO hand-fed ids: VN prompt → agent
> `composition_get_work(book_id)` → `composition_list_outline(project_id)` → self-located the right scene node →
> **C2 Tier-A Approve** → DB `outline_node` synopsis v1→2 + status→drafting v2→3 (psql-verified) → truthful
> confirmation → **Scene Rail updated REALTIME (Lane B, no reload)**. Model even self-corrected an arg-name miss AND
> an OCC stale-version conflict (refetch→retry) — the schema/error-message contracts held. **5 live-caught fixes
> shipped en route (each unit-regression-tested):**
> 1. **Studio nav-kill** — the chat's generic C-NAV executor ran inside the Compose panel; an agent `ui_open_book`
>    on the CURRENT book navigated the SPA to `/books/{id}`, unmounting the WHOLE studio and orphaning the agent's
>    own resumed run (response lost). Fix: `UiNavInterceptorContext` seam in `useUiToolExecutor` +
>    `makeStudioNavInterceptor` (same-book `ui_open_chapter`→`focusManuscriptUnit`, same-book `ui_open_book`/
>    `ui_navigate`→already-here success; cross-book falls through) provided by ComposePanel.
> 2. **book→project bridge** — `composition_get_work` now also accepts `book_id` (resolve_by_book, 0→H13 deny,
>    >1→candidates); the model had dead-ended retrying the book_id AS a project_id (no tool bridged them).
> 3. **CTX-1 position pointer** — `studio_context` now carries `project_id` + `active_chapter_id` (FE: stable
>    `ManuscriptUnitMeta` context — no per-keystroke chat re-render; BE: `StudioContext` model + the system-message
>    note "this book's project is project_id=… (a book_id is NOT a project_id)").
> 4. **composition hot-domain** — the studio compose surface now seeds `composition_*` HOT (`_STUDIO_HOT_DOMAINS`,
>    fresh + resume paths); before, the family was find_tools-lazy and the local model spun in memory/glossary
>    searches concluding "no list_scenes tool exists".
> 5. **Lane-B envelope unwrap** — `chapterIdFromResult` read `chapter_id` top-level but the live stream delivers the
>    chat-service `{ok, result}` TOOL_CALL_RESULT envelope (inner result may be a JSON string) → Scene Rail never
>    reloaded while the DB was already updated (unit tests fed the payload unwrapped — the
>    cross-boundary-normalization bug class, again).
> Also: `manuscriptUnitDocument` TS narrow fix; json-editor empty-buffer-seed commit that was missed from
> `c8906f07a` landed as `a92f10217`. Residual (tracked, not studio-scoped): C-NAV navigation on the PLAIN /chat
> surface still unmounts that page mid-run (same orphaned-resume class — chat-service persists nothing for the
> continuation); intermediate multi-tool turns render "No response generated" chips (cosmetic); knowledge indicator
> flashes "Degraded" occasionally during heavy runs.

> **▶ #12 CYCLE-1b EDITOR COMPLETENESS (M-F…M-I) — SHIPPED + LIVE-SMOKED 2026-07-03** (plan
> [`2026-07-02-chapter-editor-completeness.md`](../plans/2026-07-02-chapter-editor-completeness.md); PO sign-off:
> sceneMarker NOW not later, ▲/▼ reorder, all 4 milestones). **M-F sceneMarker:** marker = `sceneId` ATTR on the
> heading node (`SceneAnchorExtension` GlobalAttributes — load-bearing: without it Tiptap's schema STRIPS markers
> on load→save); `jumpToScene` (rail title click / navigator / ⌘P via the bus scene slice) scrolls + sets the
> cursor; ⚓ backfill anchors headings↔scenes by unique normalized-title match in ONE transaction (explicit action
> → dirty → user ⌘S; diacritics preserved — VN tone marks are significant). LIVE: ⚓ 2/2 on Chương 1, markers
> persisted in the draft body (psql `sceneId` grep), jump scroll 0→856 with the cursor inside
> `h3[data-scene-id=<node id>]`. **`D-SCENEMARKER-EMIT` — CLEARED 2026-07-03 (cycle-1c, see block above):** emit
> at generation-persist time shipped once the RAID quiet window opened. **M-G rail CRUD:** ＋ create (uses the NEW `chapter_node_id` the scenes endpoint returns — works
> at 0 scenes), ✕ soft-archive with Undo (restore), ▲/▼ reorder (after_id + If-Match; BE renumbers story_order) —
> LIVE round-trip verified vs composition DB. **M-H word count:** real F2 status item (`\p{L}` NOT `\w` — JS \w is
> ASCII-only even under /u and shreds Vietnamese; CJK per-char); ManuscriptUnitProvider moved ABOVE the status bar
> (still above every chrome conditional → no remount on sidebar/bottom toggles); hoist derives textContent from the
> body when the server projection is empty ("1046 words" live). **M-I:** dirty-on-mount KILLED (setBody equality
> guard on the first update) — "Maximum update depth" went 8+→0 live; residual: ONE setState-in-render warning from
> mount-normalize (cosmetic; a real fix = microtask-defer inside the SHARED TiptapEditor — not worth it now);
> languagetool 500s on :5199 are a dev-proxy issue, not studio scope. Tests: FE +22 (SceneAnchor 5, SceneRail 15,
> WordCount 5), composition outline 19/19 + full 1459 unit green, image rebuilt.
> **⚠️ Parallel-run lesson (live hit):** Track-4 commit `ab0523df6` swept this track's STAGED F1/F3 files into its
> own commit (shared working tree) — protocol now: `git add … && git commit -- <explicit paths>` in ONE invocation.

> **▶ Track 4 SALIENCE (knowledge) — P0+P1+P2 SHIPPED + REVIEWED 2026-07-02.** Spec `85a0fb961`. **P0 substrate**
> (`20cf1e626` + review `e7e96fa13`): `entity_access_log` (tenancy PK user+project+entity), `EntityAccessRepo`
> (fire-and-forget, never raises), `BuiltContext.surfaced_entity_ids`, router records off-latency-path (strong task
> ref — GC footgun fixed), 19 tests. **P2 cross-encoder rerank** (`b514f6282`): step 7b in `select_l3_passages` via
> existing `RerankerClient` (BYOK `extraction_config["cross_encoder_rerank_model"]`), degrade→MMR on any bad shape,
> +8 tests. **P1 salience blend** (`a66f27bd8` + review `b53ed5de0`): `rank' = rank + w·norm(decayed_access)`,
> read-time Ebbinghaus (no cron), `salience_access_weight=0.0` default = byte-identical (no DB read), **pins ALWAYS
> lead** (review caught pin-vs-budget-trim drop), +12 tests. 483 context unit tests green.
> **Eval standup (in progress):** POC book = `019f1783-ebb4` (12ch VN, ~118K chars), knowledge project
> `019f1783-ecca`, embed bge-m3 `019eeb08-8bff` (dim 1024, benchmark PASS r@3=1.0), extraction LLM gemma QAT
> `019ebb72-27a2`. **Found+fixed a HIGH book-service bug class live:** publish guard + revision-text + getRevision +
> compare + canon-search all extracted ONLY the editor `_text` projection → standard-tiptap chapters false-rejected
> from publish AND silently skipped by extraction ("text unavailable") AND invisible to canon search. Fixed with
> `_text ∪ $.**.text` union (`12a702b2d`, `7b9cd4fda`; +4 DB-gated tests vs real PG18, BOOK_TEST_DATABASE_URL).
> Also: worker-ai image was STALE (cancel_check SDK drift — chat-scope job failed) → rebuilt worker-ai +
> knowledge-service. **Eval CLI** `python -m eval.run_salience_eval` seed/measure (`0170a414c`, +9 tests).
> **NEXT: extraction completes → seed (5 passes × 4 focus) → measure → P1/P2 flip decision by data → P3.**
>
> **▶ Track 4 EVAL EXECUTED + reviewed 2026-07-02 (`b1de69a13`, `ab0523df6`).** KG: 40 entities/125 events/181
> passages (re-publish re-armed passage ingest after the `_text` fix window). **P0 LIVE-PROVEN** (20 HTTP builds →
> access-log rows). **P1 verdict: KEEP w=0** — REGRESSION on explicit queries (MRR .531→.513; tier/FTS near-optimal
> when the query names the entity; seed boosts the whole co-surfaced cluster). Revisit trigger: ambiguous-query eval
> or P3 per-entity signals. **P2 LIVE-PROVEN** e2e (build → /internal/rerank 200 local bge-reranker → reorder logged;
> passage-hit .75→.80 n=12) — stays per-project opt-in. Spec §8b has the table. **Review fixes:** config write-path
> was unreachable (extra=forbid) → added; FE editor PUT-replace would silently CLEAR the rerank keys → preserved-on-
> omit/clear-on-explicit-empty (+2 tests). **`D-WORKER-SKIP-FALSE-GREEN` CLEARED (`b24143d2f`, user fix-now):**
> `extraction_jobs.items_skipped` column + `skipped_delta` threaded through `_advance_cursor(_and_emit_run)` (both
> skip sites, tx-fallback preserved) + `_complete_job` stamps error_message when skipped ≥ total ("no work
> performed") — status stays complete (failed would trip campaign breakers). +4 tests, worker-ai 299 green, DDL
> applied live, worker-ai rebuilt.

> **▶ STUDIO AGENT RAID — IN PROGRESS 2026-07-02 (`feat/studio-agent-raid`, autonomous run).** Big RAID: agentic
> chat to industry standard (context meter+compaction, plan-mode, steering, MCP resources/prompts, HITL modes,
> checkpoints, memory-for-canon, autonomy dial). **Wave P (PlanForge takeover) — DONE through M4:** P0 committed
> inherited M3 checkpoint (38 tests); **P1 review-impl** fixed patch no-spec 409→422 (+tests); **M4** shipped 8 MCP
> `plan_*` tools + chat `plan_forge` skill + D-PF-APPLY-HONESTY (`no_change` on unchanged refine) + review_checkpoint
> / handoff_autofix service methods (73 composition MCP + 9 chat skill + 50 plan_forge + provider-gate green).
> composition-service rebuilt. **M5 (Studio planner dock) DONE + browser-smoke-proven** (palette→Planner→paste→
> propose(rules)→run+artifacts→validate→S1-S8 report; a null `fidelity_score.toFixed()` crash was caught live
> and fixed + regression-tested). **Wave P COMPLETE (7 commits).** **NEXT: Wave A — context spine** (A1 script-aware
> tokenizer for VN/CJK → A2 budget + `contextBudget` event → A3 FE meter → A4 hybrid compaction micro→full→fail →
> A5 Anthropic overlay → A6 manual compact). Grounding facts in the RAID plan §1: `context_length` in chat-service
> `models.py:466`, provider_kind at `:462`, Anthropic passthrough via `streamRequest.Extra` + `anthropic_streamer.go:251`.
> Reconciliations: gateway forwards X-Project-Id (memory `gateway-drops-xprojectid-envelope` stale); saga breaker
> is probe-reconcile not XADD.
>
> **▶ Wave A (context spine) — CORE DONE + BROWSER-PROVEN 2026-07-02.** A1 script-aware tokenizer (CJK≈1 tok/char,
> VN denser, ASCII chars/4 — fixes edge #1; 8 tests, Chinese >3× the broken chars/4) → A2 `contextBudget` AG-UI event
> on RUN_FINISHED (used vs `context_length−max_tokens−safety`; NULL→"—") → A3 FE `ContextMeter` in the chat header
> (bands 70/85; 10 tests) → A4 provider-agnostic compaction (`compaction.py`: micro-evict tool-results keep-N+exclude
> web_search → optional summarize → hard-truncate; edge #2 summarize-fail→truncate, edge #4 overflow flag; 9 tests;
> wired GUARDED before the provider call, summarize=None). **LIVE browser proof:** the meter shows "46% · 18056/39488
> tokens" on a real gemma-26b turn; compaction correctly inert at 46%<75% (turn intact). **DEFERRED (tracked):**
> `D-RAID-A5-ANTHROPIC-OVERLAY` (Claude-only context-editing `clear_tool_uses`+memory tool via provider-registry Go
> plumbing — low ROI for the local-model POC that A4 already covers) · `D-RAID-A6-MANUAL-COMPACT` (manual Compact
> button + New-from-summary — enhancement over the working auto-compaction; needs a summarize endpoint). **NEXT: Wave C**
> (C1 steering store · C2 HITL modes+per-tool approval · C3 SKILL 3-tier · C4 @-mention · C5 MCP resources/prompts ·
> C6 turn checkpoints+hunk review), then Wave B (Plan mode — mostly delivered by Wave P PlanForge), then Wave D (autonomy dial).
>
> **▶ Wave C — C3 DONE 2026-07-02; comprehensive VERIFY green.** C3 SKILL 3-tier: L1 available-skills metadata block
> (`skill_metadata_block`, `SkillDef.description`) injected always (cheap discoverability) + the resolved skill's full
> L2 body; wired into both system-prompt paths (Anthropic parts + plain); 12 skill tests. **RAID-so-far VERIFY: BE 183
> (chat-service 110 + composition-service 73) + FE 385 (plan-forge+studio+chat) green; 2 live browser smokes (M5
> planner, A2/A3 meter) with auto-fix loops; provider-gate + tsc + i18n-parity clean.** ~17 commits on `feat/studio-agent-raid`.
> **REMAINING Wave C — classified for the resumer:** SAFE-ADDITIVE (do next): **C5** MCP resources/prompts (ai-gateway
> `src/mcp/handlers.ts`+`proxy-server.factory.ts`+`federation.service.ts` add List/Read handlers; server `@resource`/
> `@prompt` decorators; chat client `knowledge_client.py` add get_resource/read; X-Project-Id IS forwarded — no workaround).
> **C4** @-mention (FE `ContextPicker` inline). LOAD-BEARING (warrant a human POST-REVIEW — tenancy/schema/permission,
> the CLAUDE.md-flagged bug class): **C1** steering store (new `book_steering` table + owner+E0 tenancy + inclusion modes
> + `steering` bucket render), **C2** HITL modes + per-server-tool approval (tool-surface filter — can regress tool
> availability), **C6** turn checkpoints (book-service revision-restore endpoint + hunk review). **Wave D autonomy dial**
> (D2 start/end-gate FSM + guardrails) is the biggest load-bearing piece — reuse campaign-saga + PlanForge + Quality Report.

> **▶ CHECKPOINT — Wave A (context spine) SOLIDIFIED 2026-07-02 (user: "make previous implement solid before we
> continue").** Ran `/review-impl` over the whole context spine (token_budget, compaction, wiring, ContextMeter).
> **Caught + fixed a stale test first:** the A2 `contextBudget` CUSTOM frame was never added to the AG-UI happy-path
> exact-sequence assertion → the FULL chat-service suite was RED (prior "green" was a subset). Fixed (`128941136`),
> full suite now 525. **HIGH bug found + fixed (`42d003f42`):** compaction on the **resume path** (agent→GUI 2nd pass,
> `resume_stream_response` passes the live `working` array w/ assistant `tool_calls` + `role:tool` results) could
> orphan a tool-call/result pair on hard-truncate / summarize tail-slice → provider **400**. Unit tests missed it
> (plain user/assistant msgs). Fix: truncate on whole tool-exchange **atoms** (`_atoms`/`_recent_tail`) — keep/drop
> whole exchanges, never split. +3 TestToolPairSafety. **Summarizer WIRED (`356527c26`, per user decision "wire now"):**
> `compact_messages` now async; tier-2 compresses the droppable MIDDLE via the session's own model
> (`_summarize_for_compaction`, provider-agnostic gateway); failure → hard-truncate (edge #2). Cross-turn history is
> flattened `{role,content}` (no pairs there — safe); memory [[compaction-resume-path-carries-tool-pairs]].
> **LIVE SMOKE PASS (per user decision "do the live smoke"):** in-container against real gemma QAT (200K) — forced
> compaction (10034→~2880 tok), asserted **no orphan**, sent the compacted tool-containing array back to gemma →
> **provider accepted on BOTH paths** (run1 summarize-success w/ real synopsis; run2 summarize-fail→truncate fallback,
> both orphan-free + accepted). chat-service **525 passed**; compaction 13 tests. **Wave A is now solid.**
> **LOW items CLEARED (`2b25bd923`):** (1) the tool loop now re-compacts `working` at the top of EVERY pass
> (atom-grouped, guarded, summarizer=session model; `effective_limit` threaded into `_stream_with_tools`) so a long
> multi-tool turn can't overflow mid-turn — +2 wiring tests (fires per pass with limit / skips when None); (2)
> `estimate_messages_tokens` now counts assistant `tool_calls` (name + arguments JSON) — +1 test. In-loop compaction
> reuses the already-live-proven `compact_messages` (provider-accepts the compacted tool array) — covered transitively,
> not separately live-smoked. **chat-service 528 passed; provider-gate green. Wave A fully closed.**

> **▶ Writing Studio foundation SHIPPED + PROVEN + PR'd 2026-07-02 (`feat/writing-studio`, 130 commits → `main`).**
> Frame + palette (⌘P/⌘⇧P) + share-data (StudioHost/bus/registry #08) + navigator (#02 search/totals) + Compose
> panel (chat AS-IS via `actionBar`) + Tier-4 editor hoist (#04) + navigator→editor + agent Lanes A/B/C. **Live
> Playwright browser smoke** (real stack, gemma-26b, POC book) verified every axis AND caught a real bug the
> unit/integration/raw-stream tests all missed: `ui_open_studio_panel` schema↔resolver drift (model sent `panel`
> not `panel_id`, resolver silent no-op, model hallucinated success — `f1f9e9966`). **Standardized the fix into a
> machine-checked FRONTEND-TOOL CONTRACT (`0df466d15`)**: `contracts/frontend-tools.contract.json` +
> `test_frontend_tools_contract.py` (BE snapshot + closed-set-must-be-enum) + `frontendToolContract.test.ts`
> (FE Proxy-access proves each resolver reads every required arg + no-silent-no-op) + `panelCatalogContract.test.ts`
> (enum ⊆ dock catalog). CLAUDE.md § "Frontend-Tool Contract (LOCKED)". FE 232 chat + full studio green, BE 50 green.
> **NEXT = the agentic-chat deep-dive** — research + standard in [`07R_chat_agent_industry_research.md`](../specs/2026-07-01-writing-studio/07R_chat_agent_industry_research.md)
> (industry map: Claude Code/Cursor/Antigravity/Kiro/Copilot/Zed/Aider/Continue + cross-cutting; LoreWeave gap map;
> 3-tier recommended standard). **Priority 🥇1–3:** context meter + tiered warnings + typed buckets; compaction
> (auto microcompact + manual button; Anthropic context-editing/memory OR provider-agnostic — OPEN Q); web-search
> surfaced. Open questions (07R Part 7): paradigm depth, compaction ownership (BYOK-Claude vs local-model portable),
> bible-as-steering vs charter, sub-agent scope. **Decide the standard doc first, then build.**

> **▶ PlanForge BLUEPRINT SHIPPED 2026-07-01** — POC frozen at `scripts/plan-forge-poc/` (fidelity 1.0, elaboration 1.0, chat HIL I1–I4 100%). **SSOT implement handoff:** [`09_PLANFORGE_BLUEPRINT.md`](../specs/2026-07-01-plan-forge/09_PLANFORGE_BLUEPRINT.md) (acceptable bar tier A/B/C, MCP sketch, M1–M5, deferred). Eval chain: [`04_PO_REVIEW.md`](../specs/2026-07-01-plan-forge/04_PO_REVIEW.md) GO → [`06`](../specs/2026-07-01-plan-forge/06_FIDELITY_POC_EVAL.md)–[`08`](../specs/2026-07-01-plan-forge/08_CHAT_HIL_POC_EVAL.md). **NEXT (PlanForge implement session — not this Writing Studio track):** M1 port engine → `composition-service/app/engine/plan_forge/` per blueprint §6 + [`docs/plans/2026-07-01-plan-forge-promote.md`](../plans/2026-07-01-plan-forge-promote.md). POC CLI kept for regression until M2 green.
>
> **▶ PlanForge Deferred (implement session):** `D-PF-APPLY-HONESTY` (no false success when fidelity_delta=0), `D-PF-NORMALIZE` (placeholder name, VN mechanics), `D-PF-PARTIAL-REFINE` (focus_paths slice), `D-PF-CONVENIENCE-EVAL` (TTAS + Opus vs local), `D-PF-MULTI-DOC` (3 doc profiles). See blueprint §7.

> **▶ #02 Manuscript Navigator — BUILT + solid 2026-07-01 (`feat/writing-studio`, full-stack).** An adaptive
> **arc→chapter→scene** tree that scales to 10k+ chapters (VS Code Explorer recipe: virtualized rows + cursor
> paging + lazy expand). **Chapters spine = book-service keyset cursor** endpoint `GET /chapters/page?cursor&limit`
> (`(sort_order, id)` keyset, UUIDv7 tiebreak, `idx_chapters_keyset`, opaque base64 cursor, `402a92e1a`).
> **Arc/scene overlay = composition lazy-children** `GET /works/{id}/outline/children?parent_id&cursor` (keyset on
> `rank COLLATE "C", id`, `de893dae7`). **FE** `@tanstack/react-virtual` over a flattened row array; two data
> sources behind `useManuscriptTree` (no Work → flat chapters; Work → outline tree); pure `tree.ts` flatten;
> lazy expand + infinite paging + client filter; wired into `StudioSideBar` (`b21ed648e`). **`/review-impl`
> (cold-start) found + fixed:** H1 composition keyset index missing collation → full Sort (added
> `idx_outline_node_children_keyset (parent_id, rank COLLATE "C", id)`); M1 stale-response race on book switch
> (generation guard); L2 collation-qualified the `rank =` equality; C1 keyset default limit 100. M2 adaptive
> degenerate-collapse tracked as spec Debt #4. **Verified:** Go + Python unit tests, FE 19 manuscript unit
> tests (incl. M1 stale-guard, beat-filter, lazy-expand), tsc+eslint+i18n clean, **live E2E through the gateway**
> (rebuilt book+composition) — renders chapters, **keyset page-boundary no gap/dup**, filter. **Debt (spec 02):**
> #1 navigator→dock link (needs #03), #2 server chapter-search (shared `useManuscriptJump`/#06a), #3
> partial-outline merge, #4 adaptive collapse. Outline-path live E2E deferred (needs a parent-linked outline seed helper).

> **▶ Writing Studio (v2) — FRAME SKELETON built 2026-07-01 (`feat/writing-studio`, FE-only).** Incremental
> **build-while-plan** track (inverts plan-then-build): master spec + one file per component, written
> just-in-time — `docs/specs/2026-07-01-writing-studio/` (`00_OVERVIEW.md` + `01_skeleton.md`); frame mockup
> `design-drafts/screens/studio/screen-writing-studio-frame.html`. Shipped the full **fixed frame** as
> `features/studio/` (MVC): `StudioTopBar` (back·title·⌘P palette placeholder·settings), `StudioActivityBar`
> (icon rail: Manuscript/Bible/Search/Quality — switches the navigator; re-click active = collapse),
> `StudioSideBar` (active navigator, **content STUBBED**), `StudioDock` (dockview + Welcome + per-book layout
> persistence), `StudioBottomPanel` (toggle; Jobs/Generation/Issues stubs), `StudioStatusBar` (lang·⌘P·bottom
> toggle). Hooks: `useStudioChrome` (activeView/sidebar/bottom, per-book `lw_studio_chrome_<bookId>`) +
> `useStudioLayout` (dockview onReady+persist). **Verified:** tsc+eslint clean, studio i18n ×4 parity-clean,
> **browser-smoke** — all regions render, activity-switch + sidebar-collapse + bottom-toggle work, **dock never
> remounts** through chrome changes, chrome+layout persist & restore on reload, 0 console errors.
> **Solid (this track's stricter no-defer rule — unit+E2E per component):** 30 unit tests + 7 Playwright E2E
> (frame regions · activity-switch · collapse · bottom-toggle · persistence · **per-book isolation** ·
> **dock-no-remount**) all green; **`/review-impl`** (cold-start) found 2 HIGH — per-book state was frozen to the
> first `bookId` (in-session book switch corrupts the other book's storage) → fixed via a **keyed `StudioFrame`**
> remount — plus MED/LOW (persist-after-seed to dodge the upgrade trap; dropped a misleading disposable; stable
> `studio-dock` testid; removed dead `persist`), all fixed & re-verified. Debt tracked **LIFO** in the spec
> (nav→dock link · two-left-rails · top-bar Generate/Save). **NEXT (#02):**
> Manuscript navigator — real chapters→scenes tree in the Side Bar that opens/focuses a unit in the dock (the
> navigator→dock "wiring"); then #03 Compose panel (first stateful dock panel → wires the D4 state-hoist rule).
> See memory `[[editor-workmode-and-compose-must-keep-editor-mounted]]`.

> **▶ Writing Studio (v2) — BLANK SHELL shipped 2026-07-01 (branch `feat/writing-studio`, FE-only).** A NEW,
> from-scratch surface — does NOT touch `ChapterEditorPage`. **Build-vs-buy decided:** our in-house dock layer
> (`WorkspaceLayoutProvider`/`DockRail`/`FloatingWindow`/`PopoutBridge`) is a single linear tab-rail — it CANNOT
> do VS Code-style multi-region docking (splits, tab groups, nested regions, drag-split-merge). Adopted
> **`dockview-react` v7.0.2** (zero-dep, MIT, React-18, real tab-groups + split grids + floating groups + pop-out
> windows + `toJSON/fromJSON`). **Shipped:** `pages/WritingStudioPage.tsx` (empty dockview shell, `themeAbyss`,
> single Welcome panel, **per-book layout persistence** via `localStorage` `lw_studio_layout_<bookId>` on
> `onDidLayoutChange`); route `/books/:bookId/studio` under `EditorLayout`; **book-level** "Studio" CTA in
> `BookDetailPage` header (opens directly, no chapter needed); new i18n `studio` ns × en/vi/ja/zh-TW +
> `books.detail.open_studio`. **Verified:** tsc + eslint clean, production `vite build` OK (dockview bundles),
> browser-smoke — studio renders, welcome panel, layout persists (1 panel saved), 0 console errors, CTA links
> correctly. **Architecture rule carried forward:** live/in-flight state (co-writer streams, editor docs) must
> live ABOVE dockview; panels are thin views over hoisted state so closing/moving a panel never drops work —
> wire when the first stateful panel lands. **Next:** user directs which panel to add first (compose, planner,
> cast, quality…), one at a time. See memory `[[editor-workmode-and-compose-must-keep-editor-mounted]]`.

> **▶ GUI Workmode overhaul (M0 + M1 + Read) — SHIPPED 2026-07-01 (FE-only).** The chapter editor's
> "three overlapping hidden mode systems" collapse into ONE dropdown: **Write · Translate · Read · Compose**
> (`hooks/useWorkmode.ts` persisted `lw_editor_workmode`; `components/editor/WorkmodeSwitcher.tsx`). Folded
> away the scattered Pen/Sparkles toggle (now a Write-only sub-control), the Co-write bridge, the one-shot
> `handleTranslate` button (deleted), the view-translations Eye button, and the compose right-panel tab.
> **Center swaps by mode:** Write/Compose keep the manuscript editor mounted (Compose shows the studio in the
> right companion panel — the editor MUST stay mounted or the studio's insert/applyPolish ref no-ops:
> regression-tested); Translate embeds the full **`ChapterTranslationsPanel`** (extracted from
> `ChapterTranslationsPage`, which is now a thin wrapper seeding `?lang=`/`?vid=`); **Read** opens the
> existing full `ReaderPage` route (guarded) — reader already reads the draft with TTS/theme/TOC/lang-switch,
> so it's reused, not rebuilt. i18n `editor.workmode.*` × en/vi/ja/zh-TW. E2E page-object `openComposeTab`
> updated to drive the dropdown. **Tests:** useWorkmode 4 + WorkmodeSwitcher 4 + ChapterEditorPage 5 (incl.
> the Compose-keeps-editor-mounted regression guard); translation/composition/editor/pages/hooks **853 green**,
> tsc + eslint clean. **Not done:** live browser-smoke (mocked heavy components ≠ visual proof — do next);
> mobile still uses its own group shell (workmode switch is desktop-only, conscious).

> **▶ Q3 Book-level promise coverage — SHIPPED 2026-07-01.** Reframed from "auto arc-conformance":
> verified `compute_arc_report` hard-requires an `arc_template_id`, and arc templates come ONLY from the
> reference-import (`motif_deconstruct`) / authored path — the mainstream premise→pipeline flow creates
> none (no `work→arc_template` link), so auto arc-conformance is a **no-op for mainstream works** (already
> has a manual Tier-W path). The GUI-free, mainstream-valuable Q3 is the **book-level escalation of the
> promise audit** (v2 API): `quality_report.build_promise_coverage` = `extract_tracked_promises(premise,
> plan_text)` (STABLE set from the SPEC, not the prose) → `score_promise_coverage(full_book)` →
> **paid/progressing/abandoned/absent** + rates. Worker op `promise_coverage` (+ SUPPORTED_OPERATIONS +
> dispatch) + `POST /v1/composition/works/{id}/promise-coverage` (renders `plan_text` from the outline tree
> + assembles every ACTIVE chapter's prose — the ENDPOINT resolves, the worker runs). FE `promiseCoverage`
> api + `useBookPromiseCoverage` + `BookPromiseCoverageSection` in the **project-scoped `QualityPanel`**
> (threaded `modelRef`; NOT the per-chapter Polish gate). Read-only. Also fixed a duplicate `composition-quality`
> testid (QualityReportSection → `composition-quality-report`). **Live smoke** (Gemma-4-26b, vi plan+book):
> 4 tracked promises from the outline; 3 paid + **1 ABSENT** = the outline-promised "missing brother" thread
> the book never delivers — exactly the "does the book pay off the outline?" signal. `err:None`. Tests:
> quality_report 9 + worker_jobs (dispatch+serialize) + FE BookPromiseCoverageSection 5; FE 735 green.
> **Deferred:** `D-QUALITY-COVERAGE-CHUNK` (very long books overflow one score call — window it; gate #4).
> **★ Ceiling note (user):** the rest of the constellation (arc templates, motif library) each need a whole
> **CRUD GUI** — big features to plan separately, not just "wiring". See memory `constellation-wiring-ceiling-crud-guis`.

> **▶ Quality Report in the Polish gate (Q1+Q2) — SHIPPED 2026-07-01.** New track: make the **planner

> **▶ Quality Report in the Polish gate (Q1+Q2) — SHIPPED 2026-07-01.** New track: make the **planner
> exploit its own judges** (audit found the auto-loop runs critic/canon/narrative-thread/motif-conformance
> as advisory-but-BURIED, and `promise_audit` never runs at all). Q1+Q2 surface them as a **read-only
> Quality Report** in the M6 Polish gate: `engine/quality_report.py` runs the 4-dim **critic** +
> **promise_audit** (introduced/resolved/**dropped**) concurrently, degrade-safe; worker op `quality_report`
> (+ SUPPORTED_OPERATIONS + dispatch) + `POST /v1/composition/works/{id}/quality-report` (mirrors self-heal);
> FE `qualityReport` api + `useQualityReport` + `QualityReportSection` mounted in `PolishPanel` (diagnostic,
> NO accept/apply — do-no-harm). **Design:** promises are phrases not spans ⇒ read-only, not an EditProposal;
> Q2 re-runs critic FRESH (stale per-scene `_critic` is wrong after edits) — documented. **Live smoke**
> (composition→ai-gateway→provider-registry→LM Studio, Gemma-4-26b, vi CH1-style): critic scored 4 dims +
> caught the planted pronoun violation; promise audit caught the planted Chekhov's-gun as a **dropped promise
> (rate 1.0)**; both `err:None`. **Also fixed 3 PRE-EXISTING branch reds** (not mine, proven by stash):
> `test_motif_repo_signatures_frozen` (create/patch grew additive kwargs vs its exact-`==` — aligned to the
> file's own `[:N]`+`kw in` convention) + 2 `test_canon_reflect` (SimpleNamespace profile fake missing newer
> `BookProfile` fields → use real `BookProfile`). Plan: `docs/plans/2026-07-01-quality-report-polish-gate.md`.
> Tests: quality_report 4 + worker_jobs (dispatch+serialize) + FE QualityReportSection 5; full BE suite +
> FE 747 green. **Deferred:** `D-QUALITY-MOTIF-ROLLUP` (motif beat-not-realized rollup, gate #2),
> `D-QUALITY-ARC-LEVEL` (arc/book-level promise coverage v2, gate #1/#2).

> **▶ MERGE 2026-06-30: `origin/main` (Temporal-Knowledge / KAL) merged in (55 commits).** The
> knowledge-gateway (**KAL**) unifies glossary/KG reads under INV-KAL: composition's cast-roster read
> moved from `glossary.list_entities` → **`kal.roster()`** (drains the cursor — fixes the ~100-cast
> truncation). Conflict was ONLY `SESSION_HANDOFF.md`; router `plan.py` + `glossary_client.py`
> auto-merged (our `thread_state`/`exit_state`/`seed_entities` survived alongside KAL). Our `seed_entities`
> WRITE (glossary `extract-entities`) passes **both** INV-KAL gates (knowledge-access + http-surface).
> **Verified:** composition unit suite **1209 passed**; `kal.roster()` returns the 10 seeded cast;
> **e2e** on the rebuilt KAL stack — seed → KAL roster → decompose → **34/34 scenes grounded** with
> `present_entity_ids`. Our code is fully on the new standard (roster via KAL; `cast_plan`/`self_heal`
> don't touch glossary directly).


> **What this track is:** the editor/compose UX overhaul **pivoted (PO)** to fixing **output QUALITY first** — POC chapters read as concatenated scenes. Two design docs:
> - **[`docs/specs/2026-06-30-editor-compose-overhaul/`](../specs/2026-06-30-editor-compose-overhaul/)** — the GUI track (validate-first, milestones M0–M5 are a backlog menu, NOT a build order).
> - **[`docs/specs/2026-06-30-chapter-synthesis-self-healing.md`](../specs/2026-06-30-chapter-synthesis-self-healing.md)** — the synthesis track: **Phase 0** (planning connectivity, DO FIRST) → **Phase 2** (multi-pass self-heal). Ordering is locked: garbage-in (disconnected plan) can't be polished out.
>
> **▶ Shipped this session (validated, committed):**
> - **Phase 0 slice 1 (intra-chapter connectivity)** — enriched the decompose prompt (goal·conflict·outcome + causality + ending-guided). Fixed the 3 worst reviewer defects (causeless pursuit, grimoire-from-nowhere, disconnected scenes) at the synopsis level, prompt-only.
> - **Phase 0 slice 2 (cross-chapter threading)** — `engine/plan.py`: typed `ChapterExitState` (Character/World/Plot + `advances`) emitted as a same-call delta, threaded chapter→chapter (`thread_state` flag, **default OFF ⇒ today's concurrent fan-out byte-identical**; sequential when ON: prev-chapter exit = fine-grained backbone + cumulative advances = global anti-repeat). Wired through worker + router (additive optional). **Live worker smoke** (Gemma, `thread_state=True`, 12ch/36sc): chapters now open *"Tiếp nối từ…"* the prior exit-state, **arc repetition gone**. `/review-impl`: **0 HIGH**, 4 findings fixed (inline/worker response parity for `exit_state`; both-flags no-op warning; degrade-path test; advances-cap documented). **Tests:** composition unit suite **1180** + slice tests (test_plan 19, router 16, worker_jobs 18 — fixed 5 pre-existing `cancel_check` fake drift) green.
>
> **▶ Self-heal POC — the whole approach was de-risked this session (see the synthesis spec for the data):**
> - **stitch baseline** — the existing 1-pass `stitch` smooths transitions but is NOT a dedup/repair pass, and it **inflates length +68%** (a prompt cleanup did NOT fix it: Gemma rewrites-and-expands by nature; the token cap isn't a clean lever). ⇒ whole-chapter rewrite is the wrong primitive.
> - **L1 dropped** — the "scene-titles mid-chapter" complaint was a POC HARNESS artifact (`to_tiptap_doc` heading-per-scene), not a pipeline defect.
> - **Satellite editing is the answer (PO insight)** — surgical edit of a SMALL isolated span. Mechanism (2) structural isolation works on a small model: `selection-edit` on a 446-char span → ×1.01 length, motif 2→0, meaning preserved (vs whole-chapter ×1.68). Mechanism (1) trust-the-model fails on small models (the stitch result).
> - **The detector must be an LLM JUDGE, not code** (PO) — POC: Gemma returned **7 real findings** (2 logic holes incl. the fall-physics one, emotion-loop, motif, flat villain), each with a `fix` guide, **7/7 locatable (3 exact + 4 fuzzy)** ⇒ the locate step uses **fuzzy/shingle match, not exact**.
> - ⇒ **Full pipeline proven end-to-end:** `LLM JUDGE → fuzzy-locate (code) → satellite-edit (selection-edit) → splice → re-judge loop`. (POC scripts: `poc/judge_poc.py`, harness phases `satellite`/`stitch`.)
>
> **▶ Orchestrator BUILT + live-validated** — `engine/self_heal.py` (`run_self_heal`): judge→fuzzy-`locate_span`→satellite-edit→splice→re-judge; advisory skips (not-located/overlap/runaway-expansion). 12 unit tests. Live on ch1: 6 findings, **6/6 located, 4 edits, length ×1.014** (vs stitch ×1.68), surgical on-target edits. Fixed a false-zero re-judge bug (degraded re-judge now reports None). NOT yet wired to an endpoint (in-container script POC).
>
> **▶ PIVOT (PO) — re-architect PLANNING before drafting.** Reviewing the committed 12-ch plan surfaced many holes at once (no motif binding, empty cast / scene-presence, anonymous new characters, ch1 telescoped). Root cause = `decompose` is **one-shot** (same anti-pattern as whole-chapter stitch). Fix = a multi-step planning pipeline (decompose-and-refine, ONE arc). Spec: [`docs/specs/2026-06-30-planning-pipeline-architecture.md`](../specs/2026-06-30-planning-pipeline-architecture.md) · Build plan + **capability audit** (planning uses ~2/30 engines — the judge constellation promise_audit/succession_entailment/arc_conformance is idle): [`docs/plans/2026-06-30-planning-pipeline.md`](../plans/2026-06-30-planning-pipeline.md). Stages: 0 cast/world · 1 motif-select · 2 arc+tension · 3 char-arc/intro · 4 grounded decompose · 5 plan self-heal · 6 orchestration+checkpoints. Reuse-heavy (motif retriever, templates, arc_apply, self_heal pattern, the idle judges).
>
> **▶ PLANNING PIPELINE COMPLETE (Stages 0–6, all live-validated)** — replaced the one-shot decompose with a multi-step planner, each stage committed + unit-tested + live-POC'd on the Lâm Uyển premise:
> - **0 cast** (`cast_plan.py` propose_cast + `glossary_client.seed_entities`) — 10 cast (6 named + 4 new), seeded → roster → present_entity_ids.
> - **1 motifs** (`motif_plan.py` select_arc_motifs) — 4 arc motifs with roles (spine/recurring/foil/climax).
> - **2 tension** (`arc_plan.py` shape_tension_curve, deterministic) — fixes ch1=100; 100 only at climax.
> - **3 char-arcs** (`character_plan.py` plan_character_arcs) — arcs + introduction schedule (new chars @ fitting beats).
> - **4 grounded decompose** (`grounded_plan.py` + grounding block in `plan.py`) — feeds cast/motifs/tension/intros into the threaded L2.
> - **5 plan self-heal** (`plan_heal.py`) — plan-judge → satellite-edit a scene synopsis by (chapter,scene).
> - **6 orchestration** (`planning_pipeline.py` run_planning_pipeline) — chains 0→1→L1(once)→3→4→5.
> - **Capstone live POC** (`poc/io/full_pipeline.txt`): cast=10 · motifs=4 · arcs=10 · 12ch/30sc/30-with-present · **plan-heal 7/7 findings edited** (4× cross-chapter repetition, a character-before-introduction, a tension-vs-beat, a dangling setup — all real, all fixed).
>
> **▶ Production hardening DONE + the drive STARTED:**
> - **Task A (wired)** — `DecomposeRequest.pipeline=true` → the `/outline/decompose` endpoint runs `run_planning_pipeline` via the worker (`plan_pipeline` op + dispatch + allowlist). **Live e2e:** endpoint→202→worker→cast=9/motifs=4/12ch·35sc/plan-heal 8-8→committed to the outline.
> - **Task B (D-PLAN-CAST-ATTRS, resolved)** — `cast_attributes` maps role/traits/archetype/relationships/summary → the character kind's attr codes; `seed_entities` sends `attributes`+`attribute_actions`. Live-verified: glossary EAV persists role/personality/relationships/description. Drafting grounding now has DEPTH.
> - **Task C (the drive, in progress)** — the full grounded+healed 12-ch plan was generated + committed through the production endpoint; CH1 drafted (grounded) + chapter self-healed (`engine/self_heal.py`) as the prose sample. **NEXT:** draft + self-heal the remaining chapters (drive identically) for the full-story PO evaluation; optional: wire `self_heal` to its own endpoint (currently a script).
> - review-impl on the pipeline: 0 HIGH, 2 MED fixed (motif unrecognised-role drop; L1-once on degrade).
>
> **▶ Cheap quality stack — judge upgrade (SHIPPED 2026-07-01, `engine/self_heal.py`):** the bare judge
> was blind (0 findings on CH1 while real xưng-hô/canon errors stood; confabulated when prompted broad).
> Root cause = no canon grounding, not model size. POC'd 5 layers on the $0 local Gemma (data:
> `poc/io/poc_stack_out.json`), then implemented the validated subset — all **default-OFF ⇒ legacy
> byte-identical**: `canon` (grounds judge **and** satellite editor in a story bible + 2 false-positive
> guards), `vote_k`/`min_votes` (grounded judge ×K, must-quote folded in), `verify` (skeptical
> refute-or-confirm, fail-open), `prefilter` (dup-word + full-recall pronoun findings), `_snap_to_sentence`
> (edit whole sentences ⇒ no splice artifact). **Lesson:** voting alone does NOT kill *systematic*
> confab — only grounding suppresses it + verify refutes the leak. **CH1 re-healed:** 7 defects → near-zero,
> **x0.997**, incl. the canon contradiction (`từng dốc lòng che chở`→`luôn khinh miệt`) fixed by the grounded
> editor; remaining = 1 cosmetic + 1 borderline repetition left for the human/stronger gate. **Tests:**
> self_heal **21** (12 legacy + 9 new) green; full composition unit suite green. Result file:
> `poc/io/ch01_healed_cheapstack.txt`. Spec §"Cheap quality stack".
>   - **Full-book drive (CH1–12, book-level canon of all 9 cast) — `story-export-v2/` + `poc/io/heal_v2_summary.json`:**
>     **modern pronouns `ông/bà/ông ta/bà ta` = 0 real residuals book-wide** (deterministic prefilter is the
>     reliable workhorse); **no inflation anywhere** (x0.998–1.005). Two honest findings: (1) **verify is
>     stochastic + fail-toward-refute → occasionally drops a real finding** (CH01 `mẫu thân ngươi` regressed
>     vs the dedicated run; refuted=5/5 on CH03) — a precision/recall knob to tune (lower aggression, or vote
>     the verify), the human gate still matters most for the *semantic* findings. (2) **bug FIXED this commit:**
>     the dup-word collapser would flatten VALID Vietnamese reduplication (`chằm chằm`, `rắc rắc`) — now gated
>     OFF for `_REDUP_LANGS` (vi/zh/ja/ko/th/id/ms); only NFD-diacritic luck spared the v2 corpus, so the
>     exported v2 prose is unaffected.
>   - **(A) verify-recall + (B) canon-from-pipeline — SHIPPED 2026-07-01:**
>     **(A)** `run_self_heal(verify_k=…)` VOTES the verify (`_verify_vote`, majority-refute, tie→keep) so a
>     stochastic single refute can't drop a real finding. **(B)** new `engine/heal_canon.py`
>     (`render_canon` / `convention_for` / `canon_from_proposed`) builds the heal bible from the SAME
>     designed cast drafting grounds on; `PipelineResult.canon` now carries it (rendered in
>     `run_planning_pipeline`). **Live-validated on CH1** ($0 local, canon auto-rendered 2701 chars,
>     `verify_k=3`): the CH01 `mẫu thân ngươi` false-refute is **GONE** (residual=False; refuted 4→1), and
>     the rendered canon enabled a new canon catch (Hắc Sát Lão Nhân's role). Tests: self_heal 24 +
>     heal_canon 5.
>   - **⚠ CORRECTION (full-book re-drive, 2026-07-01) — the verify_k=3 "fix" was a lucky dedicated-run
>     sample.** Re-driving CH1–12 (`heal_all_v3.py` → `story-export-v3/` + `poc/io/heal_v3_summary.json`):
>     **pronouns ông/bà = 0 book-wide** (deterministic prefilter — rock-solid), **no inflation** (x0.998–1.007),
>     BUT **CH01 `mẫu thân ngươi` STILL residual** (present in both v2 and v3). Two real findings: (1) the
>     verify-vote was **mis-tuned** — majority-refute on a "default-REFUTED" prompt COMPOUNDS the refute-lean
>     (over-refuted: CH11 4/4, CH12 7/7). **Fixed:** `_verify_vote` now drops only on a **UNANIMOUS** refute
>     (keep if any vote confirms) — recall-biased, the human gate culls the rest. (2) **The verify model has a
>     genuine BLIND SPOT on `mẫu thân ngươi`** — it refutes 3/3 even grounded + recall-biased (0 confirms), so
>     NO vote threshold rescues it. **Conclusion (validates the M6 design):** the cheap stack is reliable on
>     CLOSED-CLASS (pronouns/dup, deterministic); semantic blind-spots are real + bounded → that residue is
>     exactly what the **human gate (M6 Polish) + stronger-model escalation** (deferred, story C7 #4) exist for.
>     Track **D-VERIFY-BLINDSPOT-ESCALATE**: wire the stronger-model gate for verify-refuted-but-real findings.
>   - **★ REDESIGN — DIRECT high-recall propose (PO diagnosis, 2026-07-01): the JUDGE pipeline was the bug,
>     not self-heal.** PO proved a BARE prompt on the same Gemma finds 7 splice-ready `{original,replacement,
>     explanation}` edits where our `judge→vote→verify→satellite` chain kept ~4 (verify default-REFUTED muted
>     real edits → v2≈v3). "The model detects + proposes correctly; only the judge is dumb." **Fix shipped:**
>     `propose_self_heal` now uses **`propose_edits_direct`** — ONE high-recall judge call that emits the
>     replacement inline (`build_direct_judge_messages`/`parse_direct_findings`), must-quote locate + dup-word
>     merge, **NO vote/verify** (the human gate IS the filter). Canon is CONTEXT, not a suppression guardrail.
>     **Live CH1:** 5 splice-ready edits incl. `mẫu thân ngươi`→`của ta` AND the canon contradiction
>     `dốc lòng che chở`→`khinh miệt` — the two cases the old pipeline never fixed — in 1 call (vs vote×5+verify×3).
>     Autonomous `run_self_heal` keeps the conservative `_compute_edits`. Tests: self_heal+worker 49 passed.
>   - **★ "Make the judge smart" — (1) surface rules + (2) comparative re-ranker (2026-07-01).** Smart-judge
>     POC pinned the root cause: the verifier wasn't dumb, it was **UNDERFED** — the rule was BURIED in an
>     800–2700-char bible. Fed the SAME rule concisely + with the example, EVEN the old skeptical judge
>     confirms `mẫu thân ngươi` 3/3 AND refutes the `lão` confab 3/3 (`poc/smart_judge_poc.py`). Two fixes:
>     **(1)** `heal_canon` — terser `render_canon` (description + relationship only, personality dropped) +
>     a NEGATIVE-example line in the convention (`hắn/y/lão/nàng/thị are VALID`) so the rule stands out + confabs
>     are pre-empted. **(2)** `_rerank_edit` — a COMPARATIVE re-ranker ("is the replacement better?", CoT,
>     default-APPLY, surfaced rules) that sets each semantic proposal's `EditProposal.recommended` (UI pre-check)
>     — it **RANKS, never vetoes** (every proposal still shown; recall preserved). `propose_edits_direct(rerank=)`,
>     worker op defaults rerank ON; FE pre-checks `recommended` (+ `rerank_reason`). Tests: self_heal+heal_canon+worker
>     57 + FE 142 vitest, tsc clean. **Live e2e CONFIRMED** (after a `docker compose up` recovered a cascading
>     Postgres→provider-registry/ai-gateway/composition drift): on v3-healed CH1 the direct+rerank returned 4
>     proposals — 3 PRE-CHECKED (`mẫu thân ngươi`→`ta` "violates third-person self-reference"; `che chở`→
>     `khinh miệt` "contradicts the canon Tô Yến never protected her"; dup-`từng`) + 1 UN-checked (a weak edit
>     "emotional weight is lost") — i.e. it RANKS, never vetoes, and each carries a cited reason. The exact case
>     the old verify pipeline refused 3/3 is now pre-checked with the rule cited.
>   - **Re-ranker made OPT-IN (default OFF) + 12-ch compare + no-op filter (2026-07-01).** Cost concern: rerank =
>     one extra LLM call PER semantic edit. **(A)** FE toggle "auto-tick (AI, costs more)", default OFF; worker/
>     endpoint default `rerank=False`; hook holds the toggle. **(B)** 12-ch compare (`poc/compare_rerank.py` +
>     `poc/io/compare_rerank_summary.json`): 55 splice-ready proposals, re-ranker approved 41 / declined 14 — and
>     **~all 14 declines are NO-OPs** (`replacement == original`; the direct auditor emits ~25% of these). The 41
>     approvals are real (pronouns, `mẫu thân ngươi`, canon: CH09 Lâm Tử Hàn/ma công, CH05 `Uyển nhi`-tone,
>     redundancy trims, CH04 bloat-delete x0.827). **(C) Cheap win found → shipped:** `propose_edits_direct` now
>     drops no-op edits (`after==located span`) in CODE (free) — so the human/re-ranker never sees the ~25% no-ops;
>     even without the paid re-ranker the human gets ~41 clean proposals not 55. Tests: self_heal 31 (+noop) + FE
>     PolishPanel 8 (+toggle).
>   - **★ Re-ranker made TYPE-ROUTED (RULE vs CRAFT) — a general judge is weak for novels (2026-07-01).**
>     PO: a general "is it better?" judge is shallow for fiction (quality isn't one axis). POC
>     (`poc/typerouted_compare.py` + `poc/io/typerouted_compare.log`) ran BOTH on all 50 proposals: the
>     **general judge APPLYed 47/50 (94%) — a rubber stamp that would AUTO-DELETE CH04's 8 passages**; the
>     type-routed auto-approved only **10 RULE** fixes (pronouns, `mẫu thân ngươi`, role/genre-term/typo) and
>     deferred **39 CRAFT** to the author + flagged 1 BAD. **Wired:** `_RERANK_SYSTEM` now classifies
>     **RULE** (objective convention/canon/typo/dup-word/grammar → auto-tick) vs **CRAFT** (rephrase/trim/
>     DELETE-passage/pacing/tone → author decides) vs **BAD**; `recommended = (verdict==RULE)`; degrade →
>     not-pre-checked (safe). Passage-deletion forced to CRAFT; RULE bucket widened to include typos (fixed
>     the POC's `món món` miss). Live CH1: all 5 = RULE, each citing the rule. Errs SAFE (defers borderline).
>     Tests: self_heal 31. **NEXT:** stronger-model escalate for the rare true blind spot.
>   - **M6 Polish — BE done (M6.1 engine + M6.2 wiring), 2026-07-01:**
>     **M6.1** (`c4db3792`) — `_compute_edits` shared step ⇒ `propose_self_heal` returns `EditProposal[]`
>     (id/tier deterministic|semantic/start/end/before/after) WITHOUT splicing; `apply_self_heal_edits(accepted_ids)`
>     splices the accepted subset; `run_self_heal` = propose+apply-all (byte-identical).
>     **M6.2** — worker op `self_heal_propose` (+ SUPPORTED_OPERATIONS + dispatch) + REST endpoint
>     `POST /v1/composition/projects/{id}/self-heal/propose` (resolve draft Tiptap→text + canon [override
>     or roster+convention] → propose → proposals; worker/inline like `plan_pipeline`). **Apply reuses the
>     existing `composition_write_prose`** — no new write tool / no confirm-token surgery. **Live-smoke:**
>     resolve path proven on the stack (get_draft `body` key + draft_version=2 → 7473-char prose; KAL roster
>     12 cast → 823-char canon); propose engine separately live-validated. Tests: self_heal 27 + worker_jobs
>     (dispatch + serialize).
>   - **M6.3 FE — DONE (Polish panel), 2026-07-01:** `PolishPanel` + `usePolishProposals` hook + `api.proposeSelfHeal`
>     / `applySelfHealEdits` (JS mirror of the engine splice); registered `polish` in the **Quality** group
>     (`workspace/types.ts` + `CompositionPanel` SubTab/stripIds/DockSlot, no-remount preserved); accept/reject
>     diff list (deterministic pre-checked, semantic unchecked); Apply → `ChapterEditorPage.handleApplyPolish`
>     replaces the doc via `setContent` (mirrors `handleTranslate`). Endpoint path fixed `/projects`→`/works`.
>     i18n `polish` label ×4 locales. Tests: tsc clean + **722 composition vitest** (incl. 6 new).
>     **NEXT:** re-drive CH1–12 with `verify_k=3` to refresh `story-export-v2/`.
>   - **Deferred D-POLISH-FE-BROWSER-SMOKE** (gate #4, needs FE image rebuild) — full click-through (open
>     chapter → Polish tab → Run → proposals → Apply) on a rebuilt FE image (running infra-frontend is the
>     old baked build). BE resolve-path + propose engine already live-smoked; FE↔BE call is typed + unit-tested.
>   - **/review-impl on M6 (2026-07-01):** **HIGH fixed** — stale cross-chapter proposals would Apply onto the
>     wrong chapter; fixed by `key={chapterId}` on PolishPanel (remount resets the snapshot). **MED fixed** —
>     FE `applySelfHealEdits` UTF-16-sliced Python code-point offsets; added a fail-safe (skip when
>     `slice≠before`). Tests: PolishPanel 7 + tsc clean. **Two MED deferred for a PO decision (snapshot
>     tradeoffs of whole-doc replace):** **D-POLISH-OCC** — Apply uses the propose-time `source_text` +
>     ignores `draft_version`, so edits made after Run (incl. unsaved buffer) are lost → compare version &
>     warn, or apply spans to the live doc. **D-POLISH-MARKS** — Apply rebuilds plain paragraphs ⇒ strips
>     inline marks (AI-provenance/bold) chapter-wide (same shape as handleTranslate). Plus LOW: no router
>     test for the propose endpoint.
>   - **Deferred D-SELFHEAL-CANON-ATTRS** (gate #2, structural) — heal canon is currently convention +
>     roster NAMES (KAL roster is names-only); rich per-character canon (descriptions → catches canon
>     contradictions like Tô Yến "che chở") needs a glossary "full cast WITH attributes" read. The
>     convention already grounds the dominant xưng-hô class; attribute-canon is the enrichment follow-up.
>
> **▶ Broader evaluation pass — DONE 2026-07-01 (`tests/e2e/eval_compose_quality.py` + `docs/specs/2026-06-30-editor-compose-overhaul/eval/2026-07-01-quality-eval.md`).** Drove all 3 surfaces × 12 real chapters + book coverage. Verdict: **critic** (10/10 violations real, 0 FP) + **book coverage** (v2, after windowing) are trustworthy; **self-heal** good (49 props, 0 no-ops) but hides its objective wins; the **per-chapter "dropped promises" is a false-positive machine** (30 flagged vs 0 abandoned book-wide — v1 audit mislabels still-*progressing* threads as dropped; the LLM's own "chưa/not-yet" annotations prove it). Ranked backlog below.
>
> **▶ Deferred (this track):**
> - ~~**D-QUALITY-DROPPED-FP**~~ — **RESOLVED 2026-07-01 (backlog #1).** The per-chapter Quality Report promise section is reframed from the misleading "dropped promises" alarm to **"threads RAISED in this chapter"** (informational) + any RESOLVED here; the false-positive "dropped" verdict is gone, and the book-level coverage owns paid/abandoned. `quality_report` now returns `{critic, threads:{raised, resolved, raised_count, resolved_count}}` (was `{critic, promises:{...dropped...}}`); `_chapter_threads` reshapes the audit; FE `QualityThreads` + `QualityReportSection` render "N thread(s) raised" (neutral) + "M paid off here" (green). E2E-confirmed (`raised` present, `dropped` absent). Tests: quality_report + worker + FE QualityReportSection updated green.
> - ~~**D-QUALITY-HONORIFIC-PRECHECK**~~ — **RESOLVED 2026-07-01 (backlog #2).** Data-driven: re-ran the eval with rerank=ON — the LLM re-ranker only pre-checked **8/15** honorific fixes (misclassifies ~half as CRAFT) at the cost of 49 extra calls. So "default rerank ON" was the WRONG fix. Instead: `self_heal._is_convention_fix(type)` code-detects the objective xưng-hô/address/typo class (a closed convention the auditor labels) and pre-checks it **deterministically + FREE** — even with rerank OFF, and it short-circuits the re-ranker when ON. E2E-confirmed on real ch1: 4/4 ADDRESS/HONORIFIC pre-checked, LOGIC/REPEATED (CRAFT) left unchecked. Tests: self_heal 34 (+3: _is_convention_fix, precheck-without/with-rerank).
> - ~~**D-QUALITY-CRITIC-HEAL-LINK**~~ — **RESOLVED 2026-07-01 (backlog #3).** The critic's canon violations ≈ self-heal's honorific edits (same issue, shown as diagnostic AND edit). `QualityReportSection` now takes the current `proposals` and marks each critic violation whose `span` overlaps a proposal's `before` with a **"fix proposed ↓"** badge (`_hasProposedFix`, normalized substring-either-way, min-len guard) — so the author sees "this violation already has a fix below" instead of double-counting. FE-only; PolishPanel passes `p.proposals`. Tests: QualityReportSection +2 (match / no-match); FE composition 737.
> - **D-QUALITY-COVERAGE-VARIANCE — LOW, DEFERRED (backlog #5, conscious).** Book-coverage paid↔progressing flips run-to-run (LM Studio/Gemma isn't fully deterministic even at temp 0). Stabilizing = a multi-sample majority vote per window = 3× the LLM cost for marginal gain on an ADVISORY signal. Gate #4 — fix only if the variance ever misleads a real decision. Trigger: a user reports a promise's verdict flipping confusingly.
> - **D-QUALITY-CH4-REGEN — LOW, NOT-A-CODE-FIX (backlog #4, conscious).** ch4's draft has a repetition LOOP; both critic (coh=2, "looping") and self-heal (10 "repeated") correctly flagged it — i.e. the TOOLS WORK. The resolution is regenerating ch4's DATA (a generation op), not a code change; near-zero product value on one POC chapter. Won't-fix as code; regenerate the draft opportunistically if the POC book is re-driven.
> - **D-QUALITY-MOTIF-ROLLUP** — surface `motif_conformance` beat-not-realized per chapter in the Quality Report (needs per-outline-node motif bindings aggregated across scenes). Gate #2 (structural). Target: a Q-follow-on to the Quality Report track.
> - ~~**D-QUALITY-COVERAGE-CHUNK**~~ — **RESOLVED 2026-07-01** (found by E2E → fixed → E2E-confirmed, the full loop). `build_promise_coverage` now WINDOWS the book (`_split_windows`, 12K-char paragraph-aligned) and scores each window against the same fixed promise set, MERGING per-promise by strongest engagement (paid > progressing > abandoned > absent); all windows failing → honest `coverage_unavailable`. **E2E-confirmed on the real 12-ch book:** was `coverage_unavailable` + all-10-absent → now `error:None`, 9 promises all **"progressing"** (a sensible read of a setup-heavy opening: promises live, none resolved/dropped yet). Tests: quality_report 12 (+3 windowing) + an E2E regression guard (`error != coverage_unavailable`).
>
> **▶ E2E harness — SHIPPED 2026-07-01 (`9687f6910`), replaces live-smoke/POC (per user).** `tests/e2e/quality_harness.py` + `tests/e2e/test_compose_quality_e2e.py`: drives the REAL `/v1/composition/*` quality endpoints through the gateway as the claude-test account, discovering a real target black-box (books → work → a DRAFTED chapter → chat model) + job-poll. 4 E2E green. First run surfaced (a) a STALE-IMAGE trap (running composition image predated the endpoints → 404; rebuilt composition-service+worker) and (b) the coverage-chunk bug above — both invisible to a crafted-input smoke. **Methodology (LOCKED, see memory `prefer-e2e-and-evaluation-over-live-smoke-poc`):** validate compose-quality via real E2E + evaluation analysis over the real book, not hand-fed smoke. **NEXT:** either fix D-QUALITY-COVERAGE-CHUNK (make Q3 work on real books) or run a broader evaluation pass across all 3 surfaces × 12 chapters to build the improvement backlog.
> - **D-ARC-TEMPLATE-CRUD-GUI / D-MOTIF-LIBRARY-CRUD-GUI** — auto arc-conformance + the motif-library judges are gated on GUI-managed artifacts (arc templates only from reference-import/authored; no `work→arc_template` link). Making them useful needs whole CRUD GUIs — big features. Gate #2 (structural). Target: discuss + plan as their own features.
> - **Recently cleared:** ~~D-QUALITY-ARC-LEVEL~~ — SHIPPED as Q3 (book-level promise coverage, 2026-07-01).
> - **D-THREAD-MOTIF-COMBINED** — `thread_state` + `motifs_enabled` together: typed-state threading is skipped on the motif path (motif `prev_effects` carry used; warned, not silent). Gate #2 (needs interleaving the motif sequential select with the threaded invent loop). Target: when motifs + threading are both wanted in one run.
> - **Book-service universal formatter** (slice 01: `tiptap.go`/`server.go` markdown→Tiptap) — built, **uncommitted**, awaiting the PO's read-mode test before a separate commit.
> - GUI milestones M0–M5 — paused behind the synthesis track (output quality first).

> ---

# ▶▶ (merged from origin/main 2026-06-30) **Temporal Knowledge — COMPLETE (foundation + close_fact + full fanout X1–X7 + FE temporal surfaces + REAL per-episode translation); branch ready for review/merge** · branch `feat/temporal-knowledge-architecture` · HEAD `pending` · 2026-06-30

> **▶ PER-EPISODE TRANSLATION — now a REAL feature (this run), not a degrade.** The §7.6 surface translates the
> entity's as-of folded canonical into the reader's display language, on-demand + cached immutable per (content,
> language) — mirror of KG-TL M3. NEW: glossary migration **0050** `canonical_snapshot_translations` (single-flight
> claim + background fill), `translation_client.go` (→ translation-service `/internal/translation/translate-text`,
> BYOK via provider-registry — no LLM in glossary), `canonical_translation_handler.go`; KAL read
> `GET …/canonical-translation?lang=&as_of=` + contract `CanonicalTranslation`; FE `useCanonicalTranslation` (polls
> while `translating`) + rewritten `EpisodeTranslationPanel` (language selector reuses the shared per-book
> `useGlossaryDisplayLanguage` → lockstep with the glossary browser; picks original ⇒ shows original, no LLM).
> **Verified:** glossary go tests (incl. state-machine integration on the real `loreweave_glossary` DB) · KAL jest
> 19 · FE 45 + tsc clean · both INV-KAL lints + provider-gate PASS · **live-smoke** FE→BFF→KAL→glossary→translation
> →provider-registry→lm_studio: zh canonical → `ready/translated/cached` real EN translation, single-flight = 1 call.
> Plan: `docs/plans/2026-06-30-per-episode-translation-surface.md`.
> **/review-impl pass (1 MED + 2 LOW, all fixed):** a per-user config error (no_model/no_user) no longer poisons the
> shared book-tier row / exhausts the retry budget — it's caller-specific + costs no LLM, so a configured viewer
> always heals it (provider/quota failures still respect `foldRetryBudget`); success-UPDATE got the `status='pending'`
> guard; added a heal-path integration test. **User-mode e2e through the BFF** (real login JWT → KAL dual-auth + book
> grant): owned book → `ready` real EN translation, no-auth → 401, non-granted book → 403.

> **▶▶ ENTIRE EFFORT COMPLETE — the Incremental Temporal Knowledge Architecture is built, verified, and
> committed end-to-end (F0–F4 foundation + close_fact + X1–X7 fanout + X6 FE). The branch is production-ready
> for review/merge.**
> - **Foundation** (bi-temporal `entity_facts` SSOT, `maintain_chain` single writer, episodes, fold loop, KG
>   ordinal valid-time, KAL service) — hardened across **4 /review-impl passes** (4 HIGH + 6 MED + LOWs fixed, e2e green).
> - **close_fact** — pinned valid-time close (0049 pin-aware maintain_chain); reviewed + live-smoked.
> - **Fanout:** X1 composition / X2 lore-enrichment / X5 translation → KAL (consumers read bi-temporal knowledge
>   through the KAL); X3 wiki / X4 chat verified no-ops; **X7 — BOTH INV-KAL lints ENFORCED** (table-read +
>   HTTP-surface); cross-service smoke green.
> - **X6 FE:** KAL **dual-auth** (JWT + book grant-check, anti-spoof) + BFF `/v1/kal` route (reviewed + live-verified
>   200/403/401); **6 temporal surfaces** (canonical card, time slider, change timeline, diff, retrieval,
>   per-episode translation) — 45 tests, tsc clean, real-KAL shapes validated, mounted in the entity panel's
>   "Temporal" tab.
> - **Honest limitations (not bugs, future enhancements):** per-episode translation is now REAL (built this run —
>   see the block above); KG `as_of` honored (F3 landed). A full browser/Playwright smoke of the Temporal tab is the
>   one remaining nice-to-have (shapes + the FE→BFF→KAL path + 45 component tests + the HTTP-chain live-smoke are verified).



> **▶ FOUNDATION COMPLETE — all verified (real DB / build / tests):** F0 KAL contract · F1a-h substrate
> (entity_facts/maintain_chain/episodes/cold-start) · F1d producer (facts flow from extraction, idempotent) ·
> F1f fact-chain merge + split · F1g bi-temporal name/aliases + as-of-name (0048 reconcile) · F2 canonical
> versioned-cache + the **fold loop** (glossary dirty/fetch/snapshot/degrade + the translation fold worker, LLM via
> provider-registry) · F3 KG ordinal valid-time + in-story dates · F4 KAL NestJS service (auth-guarded) with the full
> read surface (facts/timeline/attr-values/roster/canonical) + write surface (episode/append/close/retract/merge/
> resolve/split/fold) + the INV-KAL table-read lint (pre-commit). Three /review-impl passes, all HIGH/MED fixed
> (security: KAL inbound auth; tenancy: fact book-scoping; correctness: same-ordinal supersede, merge attr-set).
>
> **▶ PRE-FANOUT HARDENING REVIEW (this run) — 5 parallel adversarial reviewers over the whole foundation; 4 HIGH +
> 6 MED + LOWs found and ALL FIXED (15 files, 4 services), cross-service e2e GREEN on the rebuilt glossary image:**
> - HIGH: split cross-book leak (`internalSplitEntity` had no `entityInBook(source)` guard) · KG same-ordinal
>   `[base,base)` empty-interval data loss (4 cypher blocks → strictly-greater, mirrors PG core) · KAL `fold` write
>   unroutable → built the `internalTriggerFold` glossary backing + route (live-smoked HTTP 200) · KAL `facts/close`
>   doubled path. · MED: fold fingerprint lexical-vs-numeric max **livelock** (now numeric, live fingerprint `1638578`) ·
>   NULL-unsafe staleness probe · degrade-read book-scope + `refreshEAVProjection` hardcoded `'zh'` · 0048 re-run cold-start
>   scope · KAL downstream abort-signal + non-JSON-2xx guard + strict array coercion + NaN guard. · LOWs: fold worker
>   model_ref skip / cancelled≠backoff / prompt-injection delimiting. (The summary's `_cast_roster` drain bug = phantom.)
> - Verify: Go build/vet + 12 temporal Go tests (real DB) · jest 5/5 · fold pytest 3/3 · KG 15/15. E2E: KAL→glossary
>   forwards incl. the new fold write route + 401 auth guard, as-of reads, degrade-to-canon — all green.
> - **close_fact — DONE** `1e80637e` (PO: build-now): the frozen KAL close verb is now backed. Migration 0049 adds
>   `valid_to_pinned` + a pin-aware maintain_chain (CREATE OR REPLACE) — a manual close is an authored INPUT the single
>   deriver RESPECTS, never a competing deriver (the LOCKED §12.3.3 invariant holds). closeFact core + internalCloseFact
>   (book-scoped, validates in-book + valid_to > valid_from). Live-smoked: as-of 30 present, as-of 60 absent, 422/404 guards.
> - **/review-impl on close_fact — DONE** `fb3a34ed` (PO: commit-then-review): 3 MED found + fixed — overlap guard
>   (close past a successor → 422, was a double-value hole), split now PRESERVES the pin (`valid_to_ordinal`+`valid_to_pinned`
>   copied), and TestFactsHTTP regression-locks close half-open + overlap-422 + cross-book-404.
>
> **▶ FOUNDATION FULLY HARDENED + COMPLETE (incl. close_fact).**
>
> **▶ BACKEND FANOUT COMPLETE (X1–X5, X7) — consumers now read bi-temporal knowledge through the KAL; both
> INV-KAL lints ENFORCED:**
> - **X1 composition** `ae4016ea` — `KalClient.roster` DRAINS `next_cursor` (fixes the D4 truncation-at-100 bug);
>   `_cast_roster` migrated; dead `list_entities` removed. 1181 tests green.
> - **X2 lore-enrichment** `9af1c255` — `KalClient` (roster drain + facts/canonical/search); full-book cast from
>   the drained roster. Residual: `kind`/`short_description` supplemented from the authored entity-list (catalog,
>   not bi-temporal — out of INV-KAL scope, like the table-read gate's `glossary_entities` exemption).
> - **X5 translation** `0471b48c` — `KalClient` (get_facts/get_canonical) with **as-of-N inject** (threads
>   `chapter_sort_order`) + **immutable-once cache** (keyed on chapter content-hash + as-of). Default (no
>   `KNOWLEDGE_GATEWAY_URL`) byte-identical to today.
> - **X3 wiki / X4 chat — verified NO-OPs:** wiki is owner-side (glossary, lint-exempt); chat's entity reads are
>   MCP tools federated by name through ai-gateway (MCP-first invariant — must stay that way). No dead code added.
> - **X7** `7fb6e692` — built the INV-KAL **HTTP-surface lint** (was DEFERRED `D-KAL-HTTP-SURFACE-LINT`); BOTH
>   halves now ENFORCED in pre-commit. Both lints PASS full-scan (zero direct bi-temporal knowledge reads in consumers).
> - **KAL in docker-compose** `b695ab7d` — built + healthy in-stack; cross-service smoke: composition container →
>   `knowledge-gateway:3000` roster returns the contract shape.
>
> **▶ X6a/b — FE→KAL bridge DONE + live-verified** `bf772913` (PO: dual-auth chosen):
> - **KAL dual-auth** (read surface; writes stay internal-only): SERVICE mode (X-Internal-Token) OR USER mode —
>   validate the platform HS256 Bearer JWT (Node crypto, no dep; rejects alg=none/wrong-sig/expired, timing-safe) +
>   GRANT-CHECK the book against book-service (`/internal/books/{id}/access`) since the BFF is a dumb proxy. X-User-Id
>   PINNED from the JWT sub (anti-spoof). Fail-closed + 5s grant timeout + bounded positive-grant cache.
> - **BFF** `/v1/kal` → knowledge-gateway (dumb JWT passthrough, 503-on-down). KAL compose env: JWT_SECRET + BOOK_SERVICE_URL.
> - **Reviewed** (/review-impl: MED grant-timeout + LOW cache-bound fixed) + **live-smoked** the full FE path with a
>   REAL login JWT: owned-book→200, non-granted→403, no-auth/garbage→401, service-mode→200. KAL jest 17 green.
>
> **▶ ONLY REMAINING: X6c — the net-new FE TEMPORAL SURFACES (React, this branch):** canonical card (as-of folded
> canonical), time/version slider (scrub chapter ordinal), change timeline w/ citations, diff view (state between two
> ordinals), retrieval-not-scroll, per-episode translation (§7). Reads go through the BFF `/v1/kal/*` (now live).
>
> **▶ REMAINING = the consumer/FE FANOUT (parallel worktree agents, the locked strategy):**
> X1 composition→KAL (+fix `_cast_roster` cursor drain) · X2 lore-enrichment→KAL · X3 wiki→KAL (kill direct-EAV) ·
> X4 chat→KAL · X5 translation→KAL (as-of inject + immutable-once cache) · X6 FE temporal surfaces (canonical card,
> time slider, change timeline, diff, retrieval) + migrate FE reads to KAL · X7 flip BOTH INV-KAL lints (table-read +
> the new HTTP-surface lint) to ENFORCING. Each binds ONLY to the frozen `kal.v1.yaml` → provably disjoint, parallel-safe.

> **▶ Shipped this run (production-ready, all verified on real DB / build / tests):**
> - **F1d (producer)** `d5662b64` — facts FLOW from extraction: translation worker passes `chapter_ordinal`,
>   glossary writeback ingests the episode + opens append-only facts per written attr, idempotent. (`TestBulkExtract_EmitsTemporalFacts`)
> - **F4-live core** `c13d11bb` — glossary `/internal/facts/*`: GET facts/timeline/attr-values (bounded, as-of) + POST
>   episode/append/retract; KAL paths aligned. (`TestFactsHTTP`: append supersedes, retract restitches over the router)
> - **F4-writes** `41070247` — internal merge/resolve-entity/split routes + KAL wiring (resolve-or-create idempotent).
> - **in-story dates** `a5d0d80e` (merged) — `event_date_iso` additive valid-time on KG facts/relations (19 tests; chapter-ordinal stays primary).
> - **prod bugfix** `94caea91` — world-timeline `NameError: q` (pre-existing crash) fixed.
>
> **▶ Remaining foundation (then fanout):**
> - **F2-app — fold handler:** dirty queue + canonical_snapshot write + lazy rebuild-on-read + ordinal-bucketed re-ground
>   (B1) + compare-and-clear + backoff. LLM via provider-registry (likely a worker/knowledge pass like #26/#7 summarize).
>   Makes `get_canonical` return the FOLDED canonical (today it serves canon-content). Adds the KAL `fold` route.
> - **F1g — bi-temporal names:** name as `fact_kind='name'` (single) + aliases as `'alias'` (multi); as-of-name; resolver
>   matches the across-time alias set. RECONCILE: migration 0048 converts the cold-start/F1d `attribute` name/aliases
>   facts → name/alias kind, and `refreshEAVProjection` + the D5 check must project name-kind facts to the name EAV.
> - then **fanout X1–X7** (parallel worktree agents per the locked strategy).


> **What this branch is:** implementing the Incremental Temporal Knowledge Architecture
> ([spec](../specs/2026-06-29-incremental-temporal-knowledge-architecture.md) §12/§12.7.8 govern;
> [plan](../plans/2026-06-30-temporal-knowledge-architecture-impl.md)). Append-only bi-temporal facts as the
> sole SSOT (INV-FACTS §12.0); everything else a rebuildable cache. Execution = **serial foundation → parallel
> fanout** (user-directed: build foundation serially, checkpoint, then fan out consumer migrations).
>
> **▶ Shipped this session — the SSOT substrate spine, all real-DB verified on `loreweave_glossary`:**
> - **F0** `fc4c9a80` — froze the **KAL v1 contract** (`contracts/api/knowledge-gateway/kal.v1.yaml`), the keystone
>   every consumer binds to; `knowledge-gateway: missing` row in `language-rule.yaml` (→ typescript at F4 scaffold).
> - **F1a** `ae6f17fd` — `0044` **entity_facts + episodes** bi-temporal SSOT schema (content-addressed natural key,
>   `valid_to_eff` INT64_MAX null-sink, `coverage_xid` xid8, merge_journal fact/episode-move cols). Idempotent 2×.
> - **F1b** `728efaf9` — `0045` **maintain_chain** the single `valid_to` writer (§12.3.3). Verified all 3 scenarios:
>   out-of-order backfill (A2), retract restitch (A3), oscillation (A4).
> - **F1c** `8a2b8e6d` — **fact core** Go (`facts.go`): appendFact (idempotent NK), retractFacts (restitch),
>   ingestEpisode, refreshEAVProjection (repair/cutover), per-(entity,attr) chain lock. `TestFactCore` PASSES (real DB).
> - **F1h** `8eb419f9` — `0046` **cold-start seed**: 22,056 facts seeded from live EAV; **projection==flat_eav 0 mismatches** (§12.5.4/D5).
> - **F2 schema** `fdf6c0d8` — `0047` **canonical versioned-cache** tables (canonical_snapshot + canonical_fold_state), §12.1.
>
> ⚠ Migrations **0044–0047 are applied to the running dev `loreweave_glossary`** (by F1c's `RunChain`); a fresh stack
> picks them up from the ledger on boot.
>
> **▶ PARALLEL track (background agent, worktree):** **F3 — KG ordinal valid-time unify** in `knowledge-service`
> (Python/Neo4j) — substrate-independent from glossary. Ordinal valid-time unified with `from_order`, ordinal-aware
> close (A2 on the KG side), extraction-driven invalidate/retract, quote-on-citation, per-entity ordinal snapshot.
> **Merge its worktree branch at the integration node before F4.**
>
> **▶ F3 — KG ordinal valid-time unify — MERGED `f2d5ca3e`** (was a parallel worktree agent); 24 F3 unit tests
> re-verified green post-merge. All under `services/knowledge-service/` (disjoint from glossary).
>
> **▶ F1f — fact-chain merge + split (DONE):** `ecc7e587` **merge** (§12.4.1, `mergeFactChains`/`revertFactChains`,
> journal `repointed_fact_ids`+`invalidated_fact_ids`, same-ordinal tiebreak, chain locks both sides) +
> `f52e50f7` **split** (§12.4.2, `splitFactsByEpisode` re-attribute-by-provenance, originals reason='split').
> `TestMergeFactChains`/`TestSplitFactsByEpisode` green; existing Merge/Revert/Dedup suites green (no regression).
>
> **▶ F4 — KAL gateway service + INV-KAL lint (DONE, structure):**
> - `2ab5f710` **KAL NestJS service** (`services/knowledge-gateway`) implementing `kal.v1.yaml`: config/main/health +
>   `KalReadController` (get_canonical/get_facts/timeline/list_attr_values/roster/search/neighborhood/retrieve, each with
>   per-substrate `temporal_capability`, KG `as_of` dropped when `temporal_unsupported`) + `KalWriteController`
>   (append/close/retract/merge/split/fold/ingest_episode/resolve_entity forwarding to glossary `/internal/facts/*`).
>   **Verified: npm install + nest build clean; boots + serves /health + /health/ready (kgTemporal=ordinal_valid_time),
>   16 routes mapped.** `language-rule.yaml` `missing`→`typescript`; lint PASS.
> - `434894d8` **INV-KAL table-read lint** (`scripts/knowledge-access-gate.py`, wired into `.githooks/pre-commit`): no
>   consumer reads the glossary EAV / Neo4j directly. Full-scan PASS.
>
> **▶ NEXT — F4-FOLLOW-ON + remaining foundation, then fanout:**
> 1. **F4-follow-on (live writes):** add the glossary **`/internal/facts/*` HTTP routes** (Go handlers wrapping the F1c/F1f
>    fact core — appendFact/retract/mergeFactChains/splitFactsByEpisode/fold) so the KAL write verbs hit a real target;
>    then a **cross-service live-smoke** (KAL → glossary fact route → DB) + verify the read endpoints' downstream path
>    mapping against the actual glossary/KG routes. (KAL reads/writes build + the service boots; full delegation is the
>    cross-service smoke, currently unverified end-to-end.)
> 2. **F2 app** — the fold handler: lazy rebuild-on-read + ordinal-bucketed re-ground (B1) + compare-and-clear + backoff
>    (needs a provider-registry LLM call). Enhances `get_canonical` behind the frozen contract.
> 3. **F1g** — bi-temporal name/aliases (§12.4.3) + as-of-name. **Value partly gated on F1d** (deferred writeback wiring);
>    reconciles `D-TK-F1G-NAME-RECONCILE`.
> 4. **CHECKPOINT** → then parallel **fanout** X1–X7 (consumer migrations onto the KAL, FE temporal surfaces).
>
> **▶ SCOPE (locked 2026-06-30): this branch is the PRODUCTION-READY refactor — NO deferrals.** Everything below is
> in-branch work to COMPLETE (the repo adopts the KAL immediately after merge, so nothing core may be stubbed/parked).
> Includes the full consumer + FE fanout (X1–X7) and both INV-KAL lints flipped to ENFORCING. The items that were
> "deferred" are now must-complete work:
> - **F1d — writeback Path-A emission (must complete):** wire fact emission into the glossary writeback; extend the
>   bulk-extract request with `chapter_ordinal` and update the translation-service extraction caller to pass it.
> - **F4-live — glossary `/internal/facts/*` HTTP routes** wrapping the Go fact core (append/close/retract/merge/split/
>   fold/ingest_episode/resolve_entity) so the KAL writes are real; cross-service KAL→glossary→DB live-smoke.
> - **F2-app — fold handler:** lazy rebuild-on-read + ordinal-bucketed re-ground (B1) + compare-and-clear + backoff (LLM via provider-registry).
> - **F1g — bi-temporal name/aliases** (§12.4.3) + as-of-name + RECONCILE the cold-start name/aliases representation
>   (supersede the cold-start `attribute` name/alias facts → `name`/`alias` kind facts; the old `D-TK-F1G-NAME-RECONCILE`).
> - **In-story dates (must build — user pulled into v1):** detected in-story time (`event_date_iso`) as an additional KG
>   valid-time source (spec §9 dec-3). Knowledge-service.
> - **Fanout X1–X7 (in-branch):** migrate composition, chat, lore-enrichment, translation, wiki, FE to read/write through
>   the KAL; kill every direct EAV/KG read; flip BOTH INV-KAL lints (table-read + HTTP-surface) to ENFORCING.
>
> **▶ /review-impl (2026-06-30) — 7 findings, ALL FIXED (no HIGH):** MED-1 same-ordinal single-valued conflict → last-write-wins supersede + deterministic projection tiebreak (`TestFactSameOrdinalConflict`); MED-2 unenforced chain-lock → strengthened contract doc + `TestFactChainLockSerializes` (same-chain blocks, disjoint free); LOW-2 cold-start ordinal `0→-1` (chapter_index is 0-based); LOW-5 targeted `ON CONFLICT` on the natural-key expression index; LOW-3 `refreshEAVProjection` attr_def_id-coupling doc; LOW-4 `reconcileEpisode` F1d-obligation doc + now exercised; LOW-1 → `D-TK-F1G-NAME-RECONCILE` above. All 3 facts tests green on real DB; cold-start re-verified `projection==flat_eav` 0 mismatches with the `-1` sentinel.

---

# ▶▶ (prior) **Motif book-collaboration tier (model B) + shared-graph links + MCP edit SHIPPED** · branch `feat/narrative-pattern-library` · HEAD `8c4c45c2`+ · 2026-06-29

> **▶ MERGE 2026-06-29:** `origin/main` merged into this branch (179 commits — the **public-MCP gateway + lazy tool-loading** track, critical-UX fixes, glossary/knowledge/campaign work). Conflicts resolved (composition `actions.py` confirm = JWT-identity ∪ public-MCP spend-attribution; engine `plan.py`/`stitch.py` signatures = both; studio panels = `canonview` ∪ `motifs`/`conformance`; gateway test `mcpPublicGatewayUrl`). The motif MCP tools are exposed to the public-MCP gateway: `find_tools` (lazy discovery) picks them up dynamically from the federation catalog, and they are classified in the edge `TOOL_POLICY` allowlist (commit `2aa65765`). Below is this branch's motif work; the merged-in main tracks + all prior history are archived (see the pointer at the bottom).

> **▶ Follow-up this session (2nd commit) — both model-B deferrals CLOSED:** `D-MOTIF-LINK-SHARED-TIER` (shared-graph link editing — guard rewrite + repo/MCP book_id paths) and `D-MOTIF-MCP-PATCH-SHARED` (the `composition_motif_patch` MCP edit tool). Details in the "Deferred … BOTH NOW CLEARED" block below. 150 motif unit tests + 38 motif DB integration tests green; migration re-smoked idempotent on real `loreweave_composition`; provider-gate clean.

> **▶ Shipped this session — the two NEW future-feature rows (now CLOSED):**
> - **`D-MOTIF-ADOPT-BOOK-COLLAB-TIER` (model B) — a THIRD tenancy tier (the book SHARED library).** Spec: [docs/specs/2026-06-29-motif-book-collab-tier.md](../specs/2026-06-29-motif-book-collab-tier.md). A `motif.book_shared=true` row is owned by its creator (attribution) but VISIBLE to the book's VIEW-grantees and WRITABLE by its EDIT-grantees — access is the **book grant resolved at the caller**, never row ownership. User decisions (this session): **context-scoped reads** (per-book gate, no global "all my books"), **any-EDIT-grantee writes** (edit + archive), **adopt + create + mine** all produce shared rows. The base read predicate is **UNCHANGED** (a foreign shared row is fail-closed invisible to get_visible/list_for_caller/catalog/get_by_codes); shared rows surface ONLY through the gated book-context methods. Touch-points: schema (`book_shared` col + `motif_book_shared_shape` CHECK [shared ⇒ book+owner+private, the public-catalog-orthogonality guard] + per-book `uq_motif_book_shared` + re-narrowed `uq_motif_user_book WHERE …AND NOT book_shared`); repo (`clone/adopt/create/_clone_with_code` thread book_shared; new `list_in_book/get_in_book/patch_shared/archive_shared`; adopt locks per-BOOK + dedups per-(book,code) for the shared tier); MCP (`adopt target=book_shared`, `create target=book_shared`, `mine promote_target=book_shared`, `archive book_id=`, new `composition_motif_book_list`); confirm dispatch (`book_shared` rides the payload, re-gated EDIT); FE (3rd adopt target "Share with collaborators" + `Shared` badge).
> - **`D-MOTIF-HTTP-ADOPT-BOOK` — HTTP parity.** `POST /motifs/{id}/adopt` now takes `target=user|book|book_shared`+`book_id`, **EDIT-gated before the clone** (no softer than MCP); `GET /motifs/book/{id}` (VIEW-gated list); `PATCH`/`DELETE …?book_id=` (EDIT-gated shared edit/archive, visibility-flip refused 400). A book-shared pattern root does NOT auto-adopt its members (the half-shared-pattern guard).
>
> **VERIFY:** 90 motif unit tests + new repo/mcp/router cases green; **integration (real PG)**: new `test_motif_book_shared_db.py` (shape CHECK, per-book dedup, list/get scoping, any-grantee patch/archive) + 32 existing motif DB tests pass on a throwaway DB; **migration live-smoked idempotent on the REAL existing model-A `loreweave_composition`** (added book_shared col + CHECK + uq_motif_book_shared + re-narrowed uq_motif_user_book; two runs, no error). FE 152 motif tests + tsc + provider-gate clean. **`/review-impl` adversarial tenancy review: 0 HIGH / 0 MED** — all 9 read/write/leak/confirm/dedup checks PASS with file:line evidence; 3 LOW/COSMETIC notes (deferred below).
>
> **▶ Deferred (from the model-B review — BOTH NOW CLEARED 2026-06-29):**
> - ✅ **`D-MOTIF-LINK-SHARED-TIER`** — **CLEARED:** the `motif_link_guard` was rewritten (NULL-safe) to a precise 3-arm same-tier rule — both SYSTEM, or both the SAME book's SHARED tier (owners may differ — the point of a collaborator graph), or both the SAME user's PRIVATE tier. A shared↔private/system/cross-book link is rejected at the DB. Repo `list_links/create_link/delete_link` gained a `book_id` path (anchor via get_in_book; both endpoints must be `book_shared AND book_id`); MCP link tools take `book_id` (VIEW for list, EDIT for create/delete). Live-PG tested (same-book allowed, 3 cross-tier rejections, 3rd-grantee list/delete) + migration re-smoked idempotent on real `loreweave_composition`. **Caught+fixed a SQL three-valued-logic bug**: `owner = owner` with a NULL operand yields NULL so `IF NOT NULL` wouldn't fire (a user→system link would have slipped) — every arm is now NULL-guarded.
> - ✅ **`D-MOTIF-MCP-PATCH-SHARED`** — **CLEARED:** new `composition_motif_patch` MCP tool (Tier-A) — owner-keyed by default, or a SHARED-tier edit with `book_id` (EDIT-gated → patch_shared). Optimistic-lock `expected_version` (stale → applied_conflict), visibility/publish deliberately NOT editable (separate flow), honest undo that patches changed fields back to prior values. Owner path denies a foreign row before any write; shared path confirms the row is shared-in-this-book.
>
> ---
>
> # ▶▶ (prior) **Motif library COMPLETE — audit 7/7 closed (WI-1…WI-6)** · HEAD `04bab448`+ · 2026-06-29

> **What this branch is:** the narrative-pattern (motif/arc) library — Tier-W cost-gated MCP flows for mining, conformance, adopt, and 3-way publish-sync, fronted by the FE→MCP-tool bridge. The feature body landed across prior sessions; this session closed the **completeness-audit tail** AND shipped **WI-5 per-book adopt**.
>
> **▶ Shipped this session (all green — 1083+ backend unit + 151 FE motif tests, tsc + provider-gate clean):**
> - **Audit tail (committed `f1157b25`…`b8f0ddb3`):** BYOK model_ref threading through `motif_mine`/`arc_import`; the **tag-beats LLM extractor** (knowledge `POST /internal/extraction/tag-beats` → composition mine pre-pass; cross-tenant injection neutralized); **WI-3 arc semantic retrieve** (`composition_arc_suggest`); **WI-1/WI-2/WI-4 FE** (mine panel, full editor, publish-sync); `/review-impl` fixes (arc back-fill scoped to own/system; editor edit-loss). Completeness audit: [`docs/reports/2026-06-29-motif-completeness-audit.md`](../reports/2026-06-29-motif-completeness-audit.md).
> - **WI-5 per-book adopt (`D-MOTIF-ADOPT-PER-BOOK`) — model A "book-scoped filter" (user-chosen, NOT the tier-reversal):** `motif.book_id` is a per-book LABEL on a clone the adopter still owns. The read predicate + 2-tier tenancy are **UNCHANGED** (book_id only narrows the owner's view, never widens visibility). Design: [`docs/plans/2026-06-29-motif-adopt-per-book.md`](../plans/2026-06-29-motif-adopt-per-book.md). Touch-points: schema (`book_id` col + `uq_motif_user` scoped to `book_id IS NULL` + new `uq_motif_user_book` partial + `idx_motif_book`); `MotifRepo.clone/adopt/_clone_with_code/list_for_caller`; `_MotifAdoptArgs.target=Literal['user','book']`+`book_id` (EDIT-gated at propose **and** confirm); FE adopt-to-book toggle (api/hook/AdoptTargetModal/MotifLibraryView). **Live-smoked** on real `loreweave_composition`: migration idempotent; global+per-book coexist; same-book dup blocked by `uq_motif_user_book`; 0 leaked rows.
> - **WI-6 motif_link edge-walk (`D-MOTIF-LINK-EDGEWALK`) — the FINAL §5 gap, closing the audit 7/7:** 3 MCP tools — `composition_motif_link_list` (R, traverse out/in/both with neighbor code+name), `composition_motif_link_create` + `_delete` (A). User-scoped; WRITE requires **BOTH endpoints owned by the caller** (the system↔system hole the DB `motif_link_guard` same-tier check misses — a user may never reshape the shared graph). `MotifRepo.list_links/create_link/delete_link`. **Live-smoked**: own→own create/list/delete OK; own→system rejected by the guard; 0 leaked rows. The completeness audit is now **7/7 closed, nothing deferred**.
>
> **⚠ Two already-built misfires earlier this session** (memory [[verify-built-before-building]]): `D-W8-MOTIF-BEAT-EXTRACTOR` and `D-MOTIF-SYNC-3WAY-BASE` backend were **already shipped** — I rebuilt a duplicate sync router and reverted it (`a24d99ea`). **Before building ANY "missing"/deferred motif item: `git grep` the route/module/test first.**
>
> **▶ NEXT:** **PR `feat/narrative-pattern-library` → main** — the feature body + audit tail + WI-5 are complete, green, and live-smoked. (Note: the WI-5 migration was applied to the *running* dev `loreweave_composition` by the live-smoke; a fresh stack picks it up from `migrate.py` on boot.)
>
> **▶ Deferred (motif — the §5 audit tail is 7/7 CLOSED; these were NEW future-feature rows):**
> - ✅ **`D-MOTIF-ADOPT-BOOK-COLLAB-TIER`** — **CLEARED (2026-06-29):** model B shipped (see the top block). The shared book tier landed with a 0-HIGH/0-MED adversarial tenancy review.
> - ✅ **`D-MOTIF-HTTP-ADOPT-BOOK`** — **CLEARED (2026-06-29):** the HTTP adopt route exposes `target`+`book_id`, EDIT-gated (see the top block).

---

> **▶ Archived 2026-06-30** — older / other-track handoffs moved to [`SESSION_ARCHIVE.md`](SESSION_ARCHIVE.md) to keep this file to the **active branch** only. The 2026-06-29 merge pulled in main's `Critical UX` + `Public MCP` tracks and all prior session history (glossary / composition / roleplay / extraction / KG / campaign / Sessions 66–71); all of it (incl. each track's open-defer register) lives in the archive and on its own branch + `main`. Search `SESSION_ARCHIVE.md` for a `D-…` id if you need a prior-track defer.

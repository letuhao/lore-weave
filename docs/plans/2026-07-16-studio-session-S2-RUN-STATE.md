# Studio Session S2 — Plan & Structure — RUN-STATE

> Anchor for the 8-session Writing-Studio completeness build. **Re-read this file FIRST after any
> compaction**, then `git log --oneline -15`, then continue at the first non-DONE slice.
> Framework: docs/plans/2026-07-16-studio-completeness-8-session-orchestration.md (read §2 the bar, §4 your charter, §5 the rules).

## COMMITMENT
S2 is DONE when: arc-inspector + arc-templates + 拆文 are operable; the plan graph hands off to arcs — each to the §2 production-ready bar (operable · CRUD · reachable ·
no-silent-fail · agent-parity · loop-connected · live-browser-proven · i18n+responsive · scale).

## 🔒 DESIGN SEALED 2026-07-16 (PO approved) — BUILD PHASE
Design of record: **spec 32 + 32a** (B1), **spec 34 + a future 34a** (B2). PO cleared all open Qs; 3 structural rows pulled in (no defer); cadence B1→POST-REVIEW→B2; S2 owns 5 BE fixes in composition-service.
**Build defaults (PO-sanctioned):** (1) tracks/roster repair migration auto-applies NON-DESTRUCTIVE fixes + reports; STOPS for PO only if a true DROP (data loss) is required. (2) live-smoke via vite :5199 or a rebuilt FE image (baked :5174 is stale); track D-S2-INFRA-502 if the stack blocks it, never fake-green. (3) stage only S2 lines in shared files (migrate.py/server.py/catalog.ts); never `git add -A`; `git pull --rebase` before push.
**Now building: S2-B1e (PlanDrawer embed) → B1f → B2.**

## 🎯 GOAL (PO 2026-07-16) — clear ALL of S2, QC every slice
**Finish line:** every S2 panel (arc-inspector · arc-templates · 拆文 Import&Deconstruct) driven to the §2 bar — registered (catalog + `panel_id` enum + contract + i18n + guideBody), reachable, operable, agent-parity, loop-connected — AND each panel-close ran `/review-impl` (QC) with findings fixed-or-tracked, AND a cross-service live-browser smoke drove each panel end-to-end (pasted) or an explicit infra deferral row. The slice board shows every slice DONE with an evidence string; `git log` shows the commits.
- **QC per slice = mandatory:** `/review-impl` at each panel close; paste its verdict; fix or track every finding.
- **Smoke/QC LLM model = `gemma-4-26b-a4b-qat`** (local lm_studio, $0; test account BYOK). Resolve its `user_model_id` live before any priced/LLM smoke: `SELECT user_model_id FROM user_models WHERE owner_user_id='019d5e3c-7cc5-7e6a-8b27-1344e148bf7c' AND alias ILIKE '%gemma%' AND is_active` in `loreweave_provider_registry`. Estimator ±22% ([[context-budget-test-model-gemma26b]]).
- **Proof discipline:** claiming a check passed without pasting its actual output does NOT satisfy the goal. Stop only for the 4 critical classes (§5).

## SCOPE
- **Persona / files:** features/plan-hub, features/composition/arc*
- **Panels:** arc-inspector, arc-templates
- **Seam / note:** OWNS PlanDrawer.tsx — S4 mounts <MotifBindingLens/>, never edits it.

## MANDATE (do this, in order)
1. Role-play a real web-novel author using this tool family — what must they DO?
2. Audit the CURRENT surface against that — what works, what's a skeleton, what's a dead button.
3. Per capability decide PORT / ENHANCE / BUILD — record the call, never silently drop a legacy feature.
4. Write your own detailed design (specs 31–38 are reference; the SOURCE is truth — drift is normal).
5. Build to the §2 bar. `/review-impl` at each panel close, fix what it finds.

## RULES (same-folder)
- Build only under your file subtree. Add catalog rows in your block (catalog.ts, the 8-session section).
- Shared registry (enum/contract/i18n): keep enum == openable == contract; regen `WRITE_FRONTEND_CONTRACT=1 pytest`.
- Never `git add -A`. Commit small + often. `git pull --rebase` before push. Scoped tests during BUILD.
- Stop ONLY for the 4 critical classes: destructive/irreversible · a sealed decision proven wrong ·
  tenancy/security breach · a paid action that charges the user for nothing. Everything else = defer + continue.

## SLICE BOARD  (status: TODO / DOING / DONE — DONE requires an EVIDENCE string, not a checkbox)
| slice | status | evidence (test count / live-smoke line / commit sha) |
|---|---|---|
| S2-A1 · audit current surface (role-play user) | DONE | code-audit + LIVE drive (chrome-devtools on :5174, book 019f6553). Confirmed: sidebar has "plan" category → plan-hub; NO arc-templates / arc-inspector / 拆文 entry. arc_import_analyze = MCP-only (server.py:3125, import_source.py:17). arc-templates library returns 2 templates via API. |
| S2-A2 · PORT/ENHANCE/BUILD decisions per capability | DONE | table below; awaiting PO react before BUILD |
| **S2-B1 · arc-inspector (spec 32 + 32a) — DESIGN LOCKED, awaiting PO approval** | | |
| S2-B1a · BE-A2 (If-Match required) + D-ARC-TRACKS-ROSTER-SCHEMA (32a §A: schema both doors + repair migration) | DONE | BE-A2 ✅ (263fd5a4f). Schema BOTH doors ✅ (d22ab3032): 17/17 + 213 arc sweep. Dry-run scan dev DB `4 nodes / 0 garbage` → no DROP. Repair = on-demand non-destructive script `app/db/repairs/arc_entry_keys.py` (positional backfill, never drops) + test_arc_entry_repair.py 4/4. |
| S2-B1b · BE-A3 (assign-chapters null=unassign) + D-ARC-ARCHIVE-CHAPTER-STRANDING (32a §B: recovery col + archive/restore reattach) | DONE | BE-A3 (null=unassign) both doors + `archived_from_structure_node_id` col (migrate.py + applied to dev DB). archive→return-to-pool, restore→reattach (race-guarded), both in txn. Unit 22/22; **integration 4/4 on throwaway DB** (archive-stranding, restore no-clobber, unassign, saga cascade). |
| S2-B1c · BE-A1 (span→derived_blocks both doors, leave packer's span()) + BE tests | DONE | REST get_arc + MCP composition_arc_get now serve `derived_blocks(book_id)[id]` (dense-ranked ordinals + top-level chapter_count/is_contiguous); archived→null block (not 0). `span()` UNTOUCHED (packer axis). Unit 20/20 (detail reads derived_blocks, `span.assert_not_called`); integration 5/5 incl guard pinning span()'s raw min/max_story_order keys. |
| S2-B1d · FE ArcInspectorPanel/Body/useArcInspector + bus slice + widen ArcListNode + arcEffects.ts | DONE | bus slice `activeArcId`; ArcListNode widened + ArcDetail type; getArc/patchArc/archiveArc/restoreArc + assignChapters(null); useArcInspector (params→bus→picker, OCC chain, blast/ancestors); ArcInspectorBody (identity edit, cascade own/inherited+override, chapters, promises deep-link, provenance, danger); ArcInspectorPanel (picker+chrome); arcEffects `/^composition_arc_(?!get\|list)/` (committed DORMANT — registration+un-pend moved to B1f, see DRIFT collision). Vitest: ArcInspectorBody 6/6, coverage ledger 145 (verified locally w/ un-pend), plan-hub+studio 924 pass, tsc clean. |
| S2-B1e · PlanDrawer embed (delete ArcFacets stub → mount ArcInspectorBody, DOCK-2) | DONE | ArcFacets stub + rosterKeysOf + `plan-drawer-arc-gap` note DELETED; new ArcInspectorEmbed mounts the shared body; bookId threaded into DrawerBody. PlanDrawer.test updated (routing→embed, old testids gone) 13/13; tsc clean. |
| S2-B1f · registration (catalog/enum/contract/i18n/guide) + cross-service live smoke | DONE | Registration (1112970b2): catalog row + enum + contract regen (20 pass) + i18n en+17 + guideBody; drift-locks 42/42. **/review-impl QC** (c32b43a49): 1 HIGH FIXED (patchArc bare-node edit crash + regression test 9/9) + 2 MED + 1 LOW tracked (DEBT). **Live cross-service smoke PASTED** (gateway :3123→BFF→composition): create arc → GET enriched `resolved.tracks:['revenge']`+dense-span → PATCH no-If-Match **428** → PATCH If-Match:1 **200** → PATCH empty-key **422** → archive 200. BE-A1/A2/A3 + schema operable end-to-end. |
| S2-B1 · CLOSE — arc-inspector to §2 bar | DONE | operable ✓ · CRUD (minus +add cascade entry, MED-tracked) · reachable (drift-locks 42) · no-silent-fail (MutationCache + writeError) · agent-parity (arcEffects live) · loop-connected (PlanDrawer embed + quality-promises deep-link) · live-BE-proven ✓ · i18n 18 · **FE browser-drive → D-S2-B1-BROWSER-SMOKE** (baked :5174 stale, needs rebuilt image + arc-bearing book; BE loop already proven live). |
| **S2-B2 · arc-templates + 拆文 (spec 34)** | | |
| S2-B2a · BE-7a extract-template + BE-7b suggest (REST wrappers + BE tests) | TODO | |
| S2-B2b · FE ArcTemplatesPanel (lift motif Arc*, drop conformance) + library/catalog/detail/drift + AT-6 stamp | TODO | |
| S2-B2c · ImportDeconstructSection (拆文 cost-gate → confirm → poll motif-jobs) | TODO | |
| S2-B2d · registration + live-browser smoke (agent-open→deconstruct→materialize→drift, no dock teardown) | TODO | |
| **S2-B2 · arc-templates + 拆文 (spec 34 + 34a book-tier)** | | |
| S2-B2a · BE-7a extract-template REST + tests | DONE | BE-7a ✅ (7d2119285): `POST /arcs/{id}/extract-template`, VIEW gate, 409 dup-code map; engine verified real. test_arc_hub_routes 23/23. |
| S2-B2a2 · BE-7b suggest REST (`POST /arc-templates/suggest`) | TODO | Buildable (WorksRepo.get + retrieve_arcs both real). BLOCKER-CARE: needs the `_arc_public_projection` (B-3 privacy — must NOT expose another user's `source_ref`/imported-source in a non-owner candidate). That helper lives in mcp/server.py; do it RIGHT (shared-module extract OR careful replicate + a leak test), not a rushed inline projection. Privacy-sensitive → not rushed. |
| S2-B2b · FE ArcTemplatesPanel (lift motif Arc*, drop conformance AT-7) + library/catalog/detail/drift + AT-6 stamp | TODO | |
| S2-B2c · ImportDeconstructSection (拆文 cost-gate → confirm → poll motif-jobs) | TODO | |
| S2-B2d · D-ARC-TEMPLATE-BOOK-TIER (34a: schema + tenancy) | TODO | |
| S2-B2e · registration + live-browser smoke (agent-open→deconstruct→materialize→drift) + /review-impl | TODO | |
| S2-BE8 · agent-parity for `_apply`/`_template_drift` stubs | PARKED | defer row — post-panel (34 §5 BE-8) |

## AUDIT (S2-A1) — role-play: a web-novel author structuring a book
**What the author must DO** → **current surface**:
1. See whole structure (arcs/sub-arcs/chapters/scenes) → ✅ `plan-hub` canvas — rich, DONE (H8 keyset, drag, rollups).
2. Restructure by drag (move arc/chapter/scene, reorder reading order) → ✅ usePlanMoves — DONE.
3. Inspect+edit a chapter/scene → ✅ PlanDrawer chapter/scene facet (edit/archive/restore, ⚓ re-anchor, canon/thread deep-links) — DONE.
4. **Inspect an ARC deeply** (structure·roster·chapters·conformance·provenance) → ❌ PlanDrawer arc facet is a **minimal summary stub** (self-documented `plan-drawer-arc-gap`: "23-C3 not built"). Data IS on the wire.
5. **Edit an arc** (title/status/goal/summary/roster) → ❌ arc facet is read-only (no edit block).
6. **Browse/adopt/create arc TEMPLATES + apply to book** → ⚠️ `ArcTemplateLibraryView` lists + opens timeline + apply-preview + materialize (projectId) + conformance — but **only reachable via S4's motif Motifs|Arcs toggle**, NOT an S2 panel; and **no create/adopt/edit/archive UI** (arcApi has all of them).
7. **Import a raw book → deconstruct into scenes → arcs** → ⚠️ scene-decompile CTA (`materializeScenes`, $0 deterministic) exists as plan-hub PH21 empty-state; the **arc-grouping LLM step (`composition_arc_import_analyze`) is agent-only, 0 GUI** — violates §2 "0 agent-only tools".
8. Reachability → `plan-hub` ✅; arc-inspector / arc-templates / 拆文 ❌ not in catalog/enum/contract/palette/guide.

## DECISIONS (S2-A2) — PORT / ENHANCE / BUILD
| capability | call | rationale |
|---|---|---|
| plan-hub canvas + drag + chapter/scene drawer | KEEP | already at §2 bar (DONE by H8/PH20). |
| **arc-inspector** (deep arc view + arc edit) | **BUILD** | code self-declares "not built"; wire data (roster/tracks/conformance/provenance/span/template) into a full facet + PH20-style arc edit. S2 owns PlanDrawer.tsx → build here. |
| **arc-templates** panel | **PORT + ENHANCE** | PORT: surface the existing motif Arc* components as a first-class S2 `arc-templates` studio panel (import, don't edit S4 files). ENHANCE: add create/adopt/edit/archive UI on top of arcApi (API exists, UI missing) → CRUD-complete (§2.2). |
| **拆文 Import & Deconstruct** panel | **ENHANCE + BUILD** | ENHANCE: a proper panel that runs scene-decompile (reuse materializeScenes) with result reporting. BUILD: a GUI for `composition_arc_import_analyze` (priced LLM → propose→confirm mirror, the [[cost-gated-mcp-tool-confirm-runs-engine]] pattern) so a GUI-only user can group chapters into arcs. |
| reachability (all 3) | **BUILD** | catalog S2-block rows + `ui_open_studio_panel` enum + frontend-tools.contract.json + palette + guideBody, in sync (S0 stub skipped per PO). |

## RECONCILIATION (design of record = specs 32 + 34, verified vs HEAD 2026-07-16)
**Adopt specs `32_arc_inspector.md` + `34_arc_templates_and_deconstruct.md` as the locked detail design** (they are build-ready to the file/line). Below = only the DELTA where HEAD moved since they were written (Jul 13). Every claim re-verified against source.

### Spec 32 · arc-inspector — ACCURATE, build-ready. Scope = FE panel + 3 live BE fixes.
| item | spec says | verified at HEAD | verdict |
|---|---|---|---|
| 8 arc CRUD routes | exist | exist (`arc.py`) | ✅ |
| **BE-A1** span raw-strided unit in `GET /arcs/{id}` (+MCP) | must-fix (S) | `arc.py:455 out["span"]=await structures.span(node.id)` — STILL raw | 🔨 fix: serve `derived_blocks(book_id)[node.id]` at BOTH doors; leave `span()` (packer input) |
| **BE-A2** `PATCH /arcs/{id}` If-Match optional → blind clobber | must-fix (XS) | `arc.py:495 if_match=Header(default=None)` — STILL optional | 🔨 fix: require it, 428 if absent |
| **BE-A3** assign-chapters add-only, no unassign | must-build (S) | `arc.py:364 structure_node_id: UUID` non-null — STILL add-only | 🔨 build: allow `UUID\|None` both doors |
| FE seams (plan-hub cache, OCC chain, conformance badge, glossary roster) | reuse | exist | ✅ |
| category `editor` | valid | in CATEGORY_ORDER | ✅ |

### Spec 34 · arc-templates + 拆文 — ACCURATE; the HEADLINE BLOCKER IS GONE. Scope = FE panel (lift + 拆文 section) + 2 BE REST wrappers.
| item | spec says | verified at HEAD | verdict |
|---|---|---|---|
| **W0-BE1** (拆文/mine confirm 500 + Work-less job lane) | 🔴 blocker, built in Wave 0 | ✅ LANDED: `create_unbound()` (generation_jobs.py:223), synthetic-pid removed (actions.py:558/573), poll `GET /motif-jobs/{id}` (engine.py:1450) | ✅ no S2 work — VERIFY through producer only |
| motif `Arc*` FE components to lift | exist under composition/motif/ | exist | ✅ reuse-in-place (D-S2-ARC-SEAM) |
| **BE-7a** `POST /arcs/{id}/extract-template` REST | must-build (XS wrapper) | NOT present | 🔨 build (mirror MCP `server.py` handler) |
| **BE-7b** `POST /arc-templates/suggest` REST | must-build (XS wrapper) | NOT present | 🔨 build (mirror `retrieve_arcs`) |
| **AT-6** materialize→provenance stamp | FE, reuse planHubApi.assignArcChapters | route exists | 🔨 FE only; assert `assigned==len` (no silent 0) |
| **X-1** AddModelCta dock-teardown | hard prereq | ✅ FIXED: `AddModelCta.tsx` uses `followStudioLink`+`<button>` | ✅ |
| category `storyBible` | valid | in CATEGORY_ORDER | ✅ |
| **BE-8** agent-parity (2 stubbed tools `_apply`/`_template_drift`) | PARKED, after panel | still `_pending_engine` | ⏸ defer row, post-panel |

### Cross-cutting (both panels)
- **Enum baseline = 70** at HEAD (specs assumed 57). DoD tests MUST assert **delta (+1) + 3-way equality (py enum == contract == openable)**, NEVER a literal — waves/sessions land panels concurrently.
- **Both panels touch composition-service BE** (BE-A1/A2/A3, BE-7a/7b) → **cross-service ⇒ live-browser smoke MANDATORY** (§2.7 / spec-34 DoD #5). This widens S2 beyond `features/**` into `services/composition-service/app/routers/arc.py` (+ conformance/engine wrappers). No other session owns arc routes → safe, but it IS a scope note.
- No concurrent session has registered arc-inspector/arc-templates (or S4/S6 panels) yet.

### Open questions — status (from 32 §11 + 34 §11-12; nearly all self-dispositioned)
- **Self-cleared (no PO needed):** 32-OQ1..8 (suggest=Wave4 out-of-scope; tracks/roster schema DEFER; archive-count client-derived; status not-derived; X-12 REFUTED; roster/summary honest-label), 34-OQ1..3/5/6 (FE provenance stamp v1; match on (book,template) PATCH; premise=book.summary box; conformance handed to S6; no book-shared tier).
- **Genuinely PO-facing (need your call):** (1) confirm the BE scope-expansion into composition-service; (2) 34-OQ4 — is deconstructing the 20k-char import cap actually useful? (spec defers this to M2 POST-REVIEW with a real run — not a now-blocker); (3) confirm 3 defer rows stay deferred: `D-ARC-TRACKS-ROSTER-SCHEMA`, `D-ARC-ARCHIVE-CHAPTER-STRANDING`, `D-ARC-TEMPLATE-BOOK-TIER`.

## REGISTERS  (append as you go — an empty DRIFT log at the end is dishonest, not clean)
### DECISIONS
- **D-S2-BRANCH** — build on the CURRENT branch (`feat/context-budget-law`), NOT a new branch. PO: multiple sessions operate on this folder; switching branch would break them. ⇒ strict §5: never `git add -A`, stage only S2 files (by explicit path), edit ONLY the S2 block in catalog.ts, commit small+often, scoped tests during BUILD. 🔴 **NO REBASE, NO PUSH (PO 2026-07-16): 8 sessions run concurrently in THIS shared checkout — a `git pull --rebase` or push would rewrite/clobber their in-flight state. Commit LOCAL only; do not push unless the PO asks.** (Supersedes the earlier "git pull --rebase before push".)
- **D-S2-ARC-SEAM** — reuse the existing Arc* components in `composition/motif/` IN PLACE (import, never edit — respects S4 seam). New S2 panels compose them + arcApi. If a motif Arc* component needs an S2-only change, ship an S2 wrapper, don't cross-edit.
- **D-S2-S0-STUB** — skip the S0 19-stub pre-reservation; add S2's real catalog rows directly (only in the `// ── S2 ──` block). Concurrency-safe because block line-ranges are disjoint.
- **D-S2-BE-SCOPE** (PO 2026-07-16) — S2 OWNS the 5 BE fixes in composition-service: BE-A1/A2/A3 (arc routes+MCP) in B1, BE-7a/7b (REST wrappers) in B2. Cross-service ⇒ live-smoke mandatory. No other session owns arc routes.
- **D-S2-NO-DEFER** (PO 2026-07-16) — the 3 structural rows spec 32/34 DEFERRED are PULLED INTO S2 (no defer): `D-ARC-TRACKS-ROSTER-SCHEMA` + `D-ARC-ARCHIVE-CHAPTER-STRANDING` → B1; `D-ARC-TEMPLATE-BOOK-TIER` → B2. These were UNDESIGNED (deferred = no detail) ⇒ S2 must WRITE their detail design now. Each is a schema migration ⇒ **S2 is now XL**. BE-8 (agent-parity `_apply`/`_template_drift`; `_apply` needs the genuinely-unwritten `apply_arc_to_spec` M-engine) was NOT in the pulled-in set — remains its own post-panel slice; flag to PO when B2 closes.
- **D-S2-CADENCE** (PO 2026-07-16) — build B1 (arc-inspector, all-in) fully → POST-REVIEW → then B2. Design-lock per-milestone: lock B1's detail design (spec 32 + the 2 pulled-in structural rows) and get PO approval BEFORE building B1; design B2 when B1 closes.
### PARKED  (blocker -> defer row + continue)
- **D-S2-INFRA-502** — during the live A1 drive, composition reads via the FRONTEND nginx (:5174 → gateway) 502'd intermittently (raw 502 HTML dumped as text into the plan rail + manuscript rail), while a direct curl to the gateway :3123 for the SAME route returned 200. Not an S2 code defect; a stack-health issue. BLOCKS a clean §2.7 live-browser smoke — must be healthy (or use :5199 vite) before the loop-③ / panel-close smokes. Continue building against unit tests + direct-gateway smoke meanwhile.
- **FE-RESILIENCE (not S2)** — a failed /v1 fetch renders the raw 502 HTML body as a visible string in the rail instead of an error state. Belongs to the plan-hub/manuscript rail owners' error handling; note for whoever owns the global fetch layer. Not fixing in S2 (out of subtree).
### DEBT
- **B1 /review-impl VERDICT (2026-07-16) — 1 HIGH fixed, 2 MED + 1 LOW tracked:**
  - 🔴 **HIGH (FIXED):** `patchArc` returns the BARE node (arc.py:513 `updated.model_dump()`, no `resolved`/`open_promises`/derived block); `useArcInspector.edit` seeded it via `setDetail(updated)` → `ArcInspectorBody` reads `d.resolved.tracks` → **crash on EVERY successful edit**. The body test used a complete mock detail so it never exercised the patch path (controller was untested). FIX: refetch `getArc` after a successful patch (enriched + fresh version); `patchArc` retyped to the bare node so it can't be misused. Regression test `useArcInspector.test.tsx` (edit→getArc×2, resolved intact) + 412-reseed + blast-radius. 9/9.
  - 🟠 **MED (tracked) `D-ARC-EDITFIELD-MIDTYPE-RESET`:** `EditField`'s `if(seen!==value)` resets the draft when `value` changes; a concurrent AGENT write (arcEffects → getArc refetch → detail changes) mid-type discards the user's in-progress text. Edge (agent+human simultaneous on one arc). Fix: guard the reset on `document.activeElement !== the input`. Gate #1/#4.
  - 🟠 **MED (tracked) `D-ARC-NO-ADD-CASCADE-ENTRY`:** the body can Override an inherited track/role or Remove an own one, but there is **no "+ track / + role"** to CREATE a new cascade entry (needs a key input; server enforces non-empty+unique). §2 CRUD-completeness gap for the create verb (the agent can still add via MCP). Fix: a small add-form with a key field. Gate #2 (small feature).
  - 🔵 **LOW:** double-clicking Override on the same inherited entry sends a duplicate own-key → server 422 ARC_ENTRY_KEY_DUPLICATE (surfaced as writeError, not silent). Minor UX; disable the button after override. Accept.
  - **Standards gate:** provider-gateway ✓ ($0 CRUD, no SDK), no hardcoded models ✓, tenancy ✓ (recovery column stays inside grant-gated arc routes; no shared UNIQUE(code)), Frontend-Tool-Contract ✓ (enum==openable==contract, drift-locks 42/42), MCP-first ✓ (GUI mirrors existing composition_arc_* tools). No violations.
- **PRIOR-ART EXISTS — do NOT recreate.** Full design suite for all 3 S2 capabilities already shipped by track 30-38 (Jul 13): draft HTML `screen-arc-inspector.html` (84KB) + `screen-arc-templates.html` (107KB, includes 拆文 §⑤ cost-gate); detail specs `32_arc_inspector.md` (540L) + `34_arc_templates_and_deconstruct.md` (376L) + plan-hub `21`/`24`. These are source-verified design docs (states, BE-fix flags, DoD, open-Q dispositions), not stubs. Also Wave build-plans `2026-07-13-studio-wave-0/3/4`. ⇒ S2's real design work = RECONCILE vs today's HEAD + clear genuinely-open Qs + lock, NOT redraw.
- **SPECS PARTLY STALE (good direction) — W0-BE1 LANDED.** Spec 34 §0.1's headline blocker (拆文/mine confirm → HTTP 500, synthetic uuid4 pid) is FIXED at HEAD: `create_unbound()` (generation_jobs.py:223), `_enqueue_motif_job` calls it (actions.py:573), synthetic-pid removed (comment actions.py:558). Reconciliation must re-verify 32's BE-A1/A2/A3 the same way before treating them as TODO.
### DRIFT  (near-misses, bars nearly lowered, tests nearly skipped)
- **🔴 PRESTAGED-INDEX SWEEP (B1d 2c73b09da) — the `git commit takes whole INDEX` trap, HIT.** The shared git index already held S6's `git add`-ed but uncommitted work (compositionEffects.ts/.test, index.ts, effectCoverage test, AND server.py `composition_canon_rule_restore` + test_mcp_server). I `git add`-ed only my 9 files but did NOT `git reset`/check `--cached` first, so `git commit` swept in ALL 15 staged files — S6's canon-rule MCP tool now sits under my "B1d arc-inspector" commit. **Damage assessment: the commit is CONSISTENT, not build-broken** (every swept piece is complete — verified: effectCoverage 147 + compositionEffects 1 = 148 green). NOT reverted: a `git reset HEAD~1` in a live 8-session shared tree risks tangling concurrent commits — more dangerous than the misattribution. Silver lining: arcEffects registration + coverage un-pend rode in too, so **arcEffects is now LIVE** and B1f drops to panel-registration only.
- **GOING-FORWARD GUARD (D-S2-GITRESET):** before EVERY commit — `git reset` (unstage all) THEN `git add -- <only my files>` THEN `git diff --cached --name-only` to VERIFY before `git commit`. Never `git add` onto a shared index without clearing it first. (Memory: [[git-index-may-carry-prestaged-unrelated-changes]].)
- **NEAR-MISS: static-only audit.** A2 was first written from CODE READING alone and nearly presented as the audit. PO pushed "did you look as a USER?" — the live drive then CONFIRMED the reachability gaps (and surfaced D-S2-INFRA-502). The §2.7 lesson held: reading the wire ≠ proving the user can operate it.

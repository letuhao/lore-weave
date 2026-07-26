# W6 — Frontend / UX (studio-integrated) — DETAILED DESIGN

> **Workstream:** W6 of the Narrative Motif Library parallel build · **Phase:** P1 (Wave 1) · **Owner:** 1 FE agent.
> **Spec:** [`2026-06-26-narrative-motif-library.md`](../../specs/2026-06-26-narrative-motif-library.md) (read **§R1 + §R2** locked decisions; §3.5 manual authoring; §11 UX deltas; §14 conformance; §15 intrigue UI; §16 dials).
> **Master plan:** [`2026-06-26-motif-library-master-plan.md`](../2026-06-26-motif-library-master-plan.md) — **F0 §3.6 freezes the DTO/API contracts** W6 consumes; **§4 W6** is the scope row.
> **Audit:** [`2026-06-26-motif-library-audit.md`](../../reports/2026-06-26-motif-library-audit.md) — **H-8** is the load-bearing finding this WS resolves (studio-integrated, missing states, a11y, generate-link).
> **Integrate INTO:** the real composition studio — `frontend/src/features/composition/components/CompositionPanel.tsx` (dark IDE shell, dock + power-views), tokens from `docs/specs/composition-studio-mockup-v3.html`. **Re-skin the 8 light mockups** (`design-drafts/motif-library/*.html`) — they are content/IA references, **NOT** the visual target.
> **Architecture DECIDED.** This doc is file-by-file. **The doc IS the deliverable.**

---

## §1 Scope + the frozen contracts consumed (F0 §3.6)

### 1.1 In scope (P1)
W6 owns the **motif subtree** under `frontend/src/features/composition/` — new components/hooks/context/api/types, **namespaced `motif*`** (disjoint from the existing composition FE by name; no two WS edit the same file). Plus **i18n ×4** (the 4 locale `composition.json` files are the ONE shared-file exception W6 owns for motif keys — additive keys only, never editing existing keys).

P1 FE surfaces (mapped to studio locations in §2):
1. **Library + Catalog** — browse my motifs (system+user+public), facets, adopt. (mockup 01)
2. **Motif editor / viewer** — roles + ordered beats + conditions + examples; system read-only + "clone to edit". (mockup 02 — full editor is the form; we ship a P1 view + a quick-create form, defer the full link-graph editor surface to a later milestone with W10.)
3. **Planner-binding** — the decompose preview gains per-scene motif + `match_reason` + swap + role-binding + chain-it + overuse warning + **the bind→COMMIT→GENERATE link**. (mockup 03 — the ★ core value)
4. **Manual-build** — quick-create a motif by hand (the §3.5 baseline-not-fallback principle). (mockup 06)
5. **Trace + per-scene conformance** — planned │ realized │ conformance per scene + "regenerate to beat". (mockup 07-A; coarse chapter-level only — arc-level dashboard 07-B is P4/W10.)
6. **Simple mode** (§6) + **all missing states** (§4) + **a11y/multi-device** (§5).

### 1.2 Explicitly OUT (deferred — design the contract now, build later)
- **Arc-template timeline editor** (mockup 05/06-B, the thread×chapter drag-grid) → **P4 / W10** (W10 "extends FE timeline subtree", master §5). W6 **designs its keyboard model + mobile fallback contract now** (§5.4) so W10 builds against it.
- **Arc conformance dashboard** (07-B thread lanes) → **P4 / W10**.
- **Mining review queue** (mockup 04) → **P3 / W8** (the draft-card *visual* — `status='draft'` distinct styling — ships in the library list in P1 so a P3 mined draft has a home; the *mine-run trigger* UI is W8).
- **Import/deconstruct** (mockup 05 import) → **P4 / W9**.
- **Publish/visibility-flip + upstream-diff** UI → **P2 / W11** (the library card shows the `visibility` chip + "upstream update" badge in P1 read-only; the flip control + 3-way diff modal is W11).

### 1.3 The frozen contracts W6 builds against (F0 §3.6 / §3.3)

W6 is a **pure consumer** — it exposes nothing back-end. It builds against these frozen shapes (mirrored into `motif/types.ts`, §3.4). **W6 ships against these from day 1, mocking the API in tests** (the existing `api.poll.test.ts` MSW pattern) until W1/W2/W3/W5 land.

**Motif DTO** (read projection — note the catalog allow-list per audit B-3 excludes `embedding`, raw `source_ref`, and `examples[]` on imported-derived rows):
```ts
type MotifTier = 'system' | 'user' | 'public';          // DERIVED on FE from {owner_user_id, visibility} (§3.4)
type MotifKind = 'sequence'|'situation'|'hook'|'emotion_arc'|'trope'|'pattern'|'scheme';
type MotifStatus = 'draft' | 'active' | 'archived';
type MotifSource = 'authored' | 'mined' | 'adopted' | 'imported';
type MotifBeat = { key: string; label: string; intent?: string; tension_target?: number; order: number };
type MotifRole = { key: string; actant: 'subject'|'object'|'sender'|'receiver'|'helper'|'opponent'; label: string; constraints?: string };
type Motif = {
  id: string; owner_user_id: string | null; code: string; language: string;
  visibility: 'private'|'unlisted'|'public'; kind: MotifKind; category: string | null;
  name: string; summary: string; genre_tags: string[];
  roles: MotifRole[]; beats: MotifBeat[];
  preconditions: { text: string }[]; effects: { text: string }[];
  tension_target: number | null; emotion_target: string | null;
  info_asymmetry?: { knows: string[]; deceived: string[]; gap: string } | null;  // §15.1 (kind='scheme')
  examples: { text: string }[]; abstraction_confidence: 'high'|'med'|'low' | null;
  source: MotifSource; source_version: number | null;
  judge_score: number | null; mining_support: number | null;
  status: MotifStatus; version: number;
};
```

**Catalog DTO** (allow-list projection — strict subset; never `Motif`):
```ts
type CatalogMotif = Pick<Motif,'id'|'code'|'name'|'summary'|'kind'|'genre_tags'|'tension_target'> & {
  beats: { label: string; order: number }[];           // labels only, NO intent
  adopt_count?: number; rating?: number;               // P2+ social fields — optional, may be absent
};
```

**Decompose-preview node, motif-extended** (W2 exposes; the existing `DecomposePreview` gains these per scene):
```ts
type BoundMotif = {
  motif_id: string | null; motif_name: string; motif_source: MotifSource;
  role_bindings: Record<string, { entity_id: string | null; entity_name: string }>;  // role_key → cast (null = unresolved)
  match_reason: { tension: number; genre: string[]; precond: string; cosine: number; summary: string };
};
type DecomposeSceneNode = /* existing scene fields */ & {
  beat_key?: string; beat_label?: string; tension_target?: number;
  motif?: BoundMotif | null;                            // null = free-form (A3 invent fallback)
};
type OveruseWarning = { motif_id: string; motif_name: string; applied_in: string[] };  // chapter labels
type SuccessionHint = { from_motif_id: string; to_motif_code: string; to_motif_name: string; for_node_id: string };
```

**Conformance trace payload** (W5 exposes — `GET /works/{project}/conformance?scope=chapter`):
```ts
type SceneConformance = {
  outline_node_id: string; beat_label: string; planned_tension: number | null;
  role_bindings: Record<string, string>;
  realized_excerpt: string; realized_events: string[]; realized_tension: number | null;
  beat_realized: boolean; tension_band_match: boolean; calibrated: boolean;  // calibrated=false ⇒ "advisory, unverified"
  flags: string[];                                       // e.g. ['beat_drift','tension_low']
};
type ChapterConformance = { chapter_id: string; motif_name: string; conform_count: [number, number]; scenes: SceneConformance[] };
```

**Quota / cost-confirm** (Tier-W — W4/W1; the FE mints + confirms, never executes):
```ts
type ConfirmDescriptor = 'composition.motif_mine' | 'composition.arc_import' | 'composition.conformance_run';
type CostEstimate = { confirm_token: string; descriptor: ConfirmDescriptor; est_usd: number; est_tokens: number; quota_remaining: number | null };
type QuotaError = { code: 'quota_exceeded'; resource: 'publish'|'adopt'|'mine'; limit: number; used: number };
```

---

## §2 KEY decision (audit H-8 / R1): motif binding lives INSIDE the studio

**Verdict:** the 8 mockups read as a **separate app** (`max-w-6xl` light-theme pages with their own top-nav). That is the H-8 defect. The motif feature is **not a new app** — it is **new surfaces inside the existing composition studio** (`CompositionPanel`), which already has the exact host primitives: a `SubTab` union, a `DockRail`/`DockSlot` windowing system, a `PowerViewOverlay` full-screen layer, and the dark IDE palette. We **add panels + a power-view + a route**, re-skinned to the studio's tokens. Nothing bolts beside.

### 2.1 Surface → studio location map

| Motif surface | Mockup | Studio location | Mechanism |
|---|---|---|---|
| **Motif Library + Catalog** | 01 | **New dock panel `motifs`** (a `SubTab` + `WorkspacePanelId`) | `MotifLibraryView` in a `DockSlot` — sits in the dock rail next to `beats`/`cast`. Reuses the dock/float/popout/hidden machinery for free. |
| **Motif viewer / quick-create** | 02, 06-A | **Modal/drawer launched from the library panel** + an **inline create form** | `MotifDetailDrawer` (right-side sheet, mount-on-open) + `MotifQuickCreateForm`. NOT a route — the library is the hub. |
| **Planner-binding** | 03 | **The EXISTING `planner` power-view** (`PlannerView` + `PlannerSceneRow`) — extended in place | W6 adds **motif-aware child components** the planner renders per scene (`MotifBindingCard`, `MatchReasonChip`, `SwapMotifPopover`, `RoleBindingRow`, `OveruseBanner`, `ChainItHint`). The planner file is **W2's**, not W6's (disjointness) — W6 ships the children; **W2 wires them** (one integration seam, §9). |
| **bind → COMMIT → GENERATE link** | 03 (the dead-end audit flagged) | The planner's **Commit tree** → routes the author to **`compose`/`assemble`** with the bound scene selected | `useMotifBindingFlow` returns a `commitAndGenerate()` that commits the preview then calls the panel's existing `selectTab('compose')` + sets `sceneId` (the seam W2 owns; W6 designs the contract, §4.6). |
| **Per-scene conformance + trace** | 07-A | **New dock panel `conformance`** (a `SubTab`) | `ConformanceTraceView` in a `DockSlot`. Coarse chapter-scope only (P1). "Regenerate to beat" reuses the scene-regenerate (§11). |
| **Arc-template timeline** | 05, 06-B | **`arc` power-view (deferred to P4/W10)** | W6 **designs the keyboard/mobile contract** (§5.4); W10 builds the grid in the existing `arc` tab. |
| **Mining run** | 04 | **`flywheel` panel (P3/W8)** | the cost-confirm card (§4.5) is W6-designed P1; the run trigger is W8. |

### 2.2 Re-skin: light mockup tokens → studio dark tokens

The mockups use Tailwind utility colors on a light `bg-slate-50`. The studio is HSL-CSS-var dark (`docs/specs/composition-studio-mockup-v3.html` `:root`). **Map, do not copy:**

| Mockup (light) | Studio token (dark) | Use |
|---|---|---|
| `motif #d97706` (amber-600) | `--primary: 35 85% 55%` (amber) | motif accent — **already the studio primary**, perfect fit |
| `bg-white` card | `hsl(var(--card))` = `25 7% 11%` | every card/panel surface |
| `border` slate | `hsl(var(--border))` = `25 6% 18%` | borders |
| `text-slate-800` / `-600` / `-400` | `hsl(var(--fg))` / `--muted-fg` (`30 8% 62%`) | text hierarchy |
| tier `sys #64748b` / `user #6366f1` / `pub #059669` | `--muted-fg` / `--info (215 80% 60%)` / `--success (150 65% 48%)` | tier chips (§5.6 — co-encode w/ text, not color alone) |
| beat amber pill | `hsl(var(--primary)/.16)` bg + `hsl(var(--primary))` text | beat chips |
| conformance `ok/warn/bad` | `--success` / `--warning (38 92% 55%)` / `--destructive (0 72% 58%)` | conformance — **always paired with ✓/⚠/✗ glyph + text** |
| thread `combat #dc2626` / `cultiv #0891b2` / `romance #db2777` | keep as named thread hues (P4/W10) but **paired with ⚔/☯/♥ glyph** | arc threads |

**Implementation:** the studio already runs Tailwind with the shadcn HSL-var convention (the existing composition components use `dark:` variants + `bg-neutral-*` / `text-emerald-*`). W6 components follow the **same className conventions as the existing composition components** (`CompositionPanel.tsx` lines 547-560 are the template — `border-neutral-200 dark:border-neutral-700`, `bg-emerald-50/60 dark:bg-emerald-950/30`). The motif accent uses `amber-*` / `indigo-*` to match the studio's existing palette. **No new CSS file, no `tailwind.config` color extension** — use the existing tokens.

---

## §3 Component / hook / context tree (MVC)

Per CLAUDE.md React-MVC: **hooks = controllers** (logic + state, no JSX, <200 lines), **context = services** (shared cross-component state), **components = views** (render only, <100 lines). No API/business logic in components. No `useEffect` for event handling. No conditional unmount of stateful components (CSS `hidden`). Server is source of truth (no localStorage for motif data).

### 3.1 Directory layout (all under `frontend/src/features/composition/`, namespaced `motif*`)

```
features/composition/
  motif/                               ← W6's subtree (disjoint; new dir)
    api.ts                             ← motif API layer (relative /v1/composition/motifs*)
    types.ts                           ← the frozen DTOs mirrored (§1.3)
    simpleMode.ts                      ← jargon→plain-language label maps (§6) + tier helpers (pure)
    hooks/                             ← controllers
      useMotifLibrary.ts               ← list/search/facet state (react-query)
      useMotifDetail.ts                ← one motif + clone/adopt mutations
      useMotifQuickCreate.ts           ← manual quick-create form controller
      useMotifBinding.ts               ← planner-binding controller (swap/rebind/chain) — consumed BY W2's PlannerView
      useRoleResolver.ts               ← unresolved-role → cast picker (wraps glossary roster)
      useConformanceTrace.ts           ← chapter-scope conformance read + regenerate-to-beat
      useAdoptFlow.ts                  ← adopt target-picker + Tier-W confirm-token flow
    context/                           ← services
      MotifSimpleModeContext.tsx       ← the simple/expert toggle (per-device pref, write-through to /v1/me/preferences)
    components/                        ← views (each <100 lines)
      MotifLibraryView.tsx             ← the dock panel (scope tabs + facets + list) — orchestrates children
      MotifScopeTabs.tsx               ← My library | Public catalog
      MotifFacetRail.tsx               ← tier/kind/genre/tension facets
      MotifCard.tsx                    ← one library card (active | draft | public | adopted-edited variants)
      MotifEmptyState.tsx              ← first-run empty library (§4.2) — the load-bearing empty state
      MotifDetailDrawer.tsx            ← view one motif (roles/beats/conditions/examples) + read-only lock
      MotifQuickCreateForm.tsx         ← manual build (mockup 06-A)
      MotifBindingCard.tsx             ← per-chapter bound-motif card (planner) — rendered by W2
      MatchReasonChip.tsx              ← "why this motif" breakdown (+ simple-mode plain text)
      SwapMotifPopover.tsx             ← co-write top-N swap picker
      RoleBindingRow.tsx               ← role → cast chip (resolved | unresolved+picker)
      OveruseBanner.tsx                ← anti-repetition warning
      ChainItHint.tsx                  ← legal-succession "chain it" affordance
      AdoptTargetModal.tsx             ← adopt → User library | a book (§4)
      CostConfirmCard.tsx              ← Tier-W cost-confirm (mint_confirm_token) (§4.5)
      ConformanceTraceView.tsx         ← the conformance dock panel (07-A) — orchestrates rows
      ConformanceSceneRow.tsx          ← one planned│realized│conformance row + regenerate-to-beat
      InfoAsymmetryCard.tsx            ← §15.1 scheme intrigue (knows/deceived/gap) — render in detail + binding
      MotifStateBoundary.tsx           ← shared loading/error/permission wrapper (§4.1)
    __tests__/                         ← vitest (mirrors existing __tests__ layout)
```

**Why `motif/` as a sub-namespace, not flat into `components/`:** the existing `components/` dir has 195 files; a flat add risks a name collision (disjointness rule) and buries the feature. A `motif/` subtree is unambiguously W6-owned, keeps the contract test surface tidy, and matches how the `workspace/` subtree is already separated.

### 3.2 Controllers (hooks) — responsibilities

- **`useMotifLibrary(token, { scope, facets })`** — owns: the react-query list (`['composition','motifs', scope, facets]`), facet filter state (tier/kind/genre/tension — **client-side narrowing over the fetched page**; server does the heavy filter), search debounce, scope tab (`my` | `catalog`). Returns `{ motifs, isLoading, isError, error, facets, setFacet, search, setSearch, scope, setScope }`. No JSX.
- **`useMotifDetail(motifId, token)`** — one motif (`get_visible`); derives `isReadOnly = motif.owner_user_id == null` (system) `|| motif.visibility==='public' && motif.owner_user_id !== me`; exposes `clone()` (the ONE primitive = adopt/customize), `patch()`, `archive()` mutations with optimistic-lock `expected_version`. Returns the read-only flag so the view disables edits + shows "clone to edit".
- **`useMotifQuickCreate(token, { bookId })`** — manual-build form state (name/kind/genre/save-to + beats array with add/reorder), `submit()` → POST, on success opens the detail drawer. Mirrors the existing form-hook pattern (e.g. `useCanonRules`).
- **`useMotifBinding({ projectId, nodeId, token })`** — the planner-binding controller **consumed by W2's `PlannerView`** (W6 ships it; W2 imports it — the seam). Owns: the bound motif for a node, `swap(motifId)` (→ `PATCH …/outline/{node}/motif`, archive-not-delete per R2.6), `rebindRole(roleKey, entityId)`, `clearMotif()` (→ free-form fallback), `chainIt(hint)` (pre-seed next chapter), `regenerateScene(sceneId)` (→ scene-regenerate within beat). **Mutations invalidate the decompose-preview query** so the tree re-renders (no useEffect).
- **`useRoleResolver({ bookId, token })`** — wraps the existing `useGlossaryRoster`/`useCast` to resolve a role's unresolved entity; exposes `pick(roleKey, entity)` + `createEntity(name)` shortcut (mirrors `present_entity_names_unresolved`, §11).
- **`useConformanceTrace({ projectId, chapterId, token })`** — chapter-scope conformance read (`GET …/conformance?scope=chapter`), `regenerateToBeat(nodeId)`. Surfaces `calibrated` so the view can stamp "advisory / unverified" (R2.1 / AI-quality R1 honesty).
- **`useAdoptFlow({ token })`** — adopt target-picker state (User library | which book), calls `clone()`. For an **imported-derived public** motif the server strips `examples[]` (B-3) — the FE just reflects what comes back.

### 3.3 Context (service) — `MotifSimpleModeContext`

A small context holding `{ simple: boolean, setSimple }`. **Per-device preference, NOT motif data** → it follows the CLAUDE.md preference rule: read from `/v1/me/preferences` on mount, write-through on change, localStorage as cache only (it is a UI affordance, not user content). It is the ONE motif context — split from any volatile state (there is no per-frame streaming in the motif surfaces, so a single stable context is correct; do not over-split). Default: **simple = true for a first-run user** (beginner persona, §6), persisted thereafter.

### 3.4 Views (components) — render-only, each <100 lines

Each component receives data + callbacks from a hook/context and renders. The orchestrators (`MotifLibraryView`, `ConformanceTraceView`) call the hook and fan props to children but hold no logic. `MotifCard` is a pure switch on `{ status, tier, source }` → one of 4 visual variants (active / mined-draft-dashed / public-adoptable / adopted-edited). All interactive elements carry ARIA + keyboard (§5).

---

## §4 The MISSING STATES every screen needs (audit H-8 R4)

The mockups show only the happy path. Every screen gets the full state matrix. `MotifStateBoundary` (a shared wrapper) standardizes loading/error/permission; empty + cost-confirm are screen-specific.

### 4.1 The state matrix (per surface)

| Surface | empty | loading | error | permission-denied | cost-confirm |
|---|---|---|---|---|---|
| **Library** | `MotifEmptyState` — first-run (§4.2) | skeleton cards (3) | retry banner | n/a (read-only is the default state) | n/a |
| **Catalog** | "No public motifs match" + clear-filters | skeleton | retry | n/a | n/a |
| **Detail drawer** | n/a | spinner | "couldn't load" + close | **read-only lock + "Clone to edit"** (system / others' public) | n/a |
| **Quick-create** | the empty form IS the state | submit pending (disable) | inline field errors + toast | **no-grant on book** → disable "Save to Book", show why | n/a |
| **Planner-binding** | "No motif matched — free-form" (the A3 fallback, **not an error**) | per-scene skeleton while binding | swap failed → keep prior binding, toast | no `manage` grant → read-only preview | **Commit tree** → generate is a Tier-W spend → `CostConfirmCard` (§4.5/§4.6) |
| **Adopt** | n/a | adopt pending | adopt failed toast | **quota_exceeded** → §4.4 | adopt is Tier-W (R2.8) → confirm card |
| **Conformance** | "Not generated yet — generate scenes to see conformance" | skeleton rows | retry | n/a | **Re-run conformance** = Tier-W (R2.8) → confirm card |

### 4.2 First-run empty library (the load-bearing empty state)

`MotifEmptyState` — a fresh user has **system-tier seed motifs visible but zero user motifs**. The empty state must NOT read as "broken". It:
- Confirms the **seed packs are already there** ("12 starter motifs are ready — tu-tiên + báo-thù"), with a CTA to browse the System tier.
- Offers the **two doors** (mockup 06's principle): **"+ New motif"** (manual, no tokens) and a hint that the planner will auto-bind these during decompose.
- Plain-language (simple mode default): "Motifs are reusable plot shapes. The planner picks one per chapter so even a small model writes a solid scene." No "Greimas/Propp" words.
- **Never** a dead end — every empty state has a forward action.

### 4.3 Permission-denied (tenancy made visible)

The studio is multi-tenant (CLAUDE.md). Two permission shapes surface:
- **System / another user's public motif → read-only.** `MotifDetailDrawer` hard-disables every edit control (not just visually — the inputs are `disabled` + `aria-disabled`) and shows a prominent **"Clone to edit"** button (the glossary system-kind lock parity, §11). This is the kinds-bug lesson in the UI: a user never *edits a shared row*, they clone-down.
- **Book-tier write without `manage` grant** → the "Save to Book" target is disabled with a tooltip ("You need manage access on this book"). Reads still work.

### 4.4 Quota states (audit B-4)

Publish / adopt / mine-run are per-user quota-capped. On a `QuotaError` the FE shows a **non-blocking explainer** ("You've adopted 50/50 this month — archive some or wait") — never a silent failure. The mutation surfaces `quota_remaining` from the cost estimate so the UI can pre-warn before the action.

### 4.5 Tier-W cost-confirm card (`mint_confirm_token`)

`CostConfirmCard` is the studio's existing `composition_generate` confirm pattern, reused for motif Tier-W ops (adopt, mine, conformance-run, and the bind→generate spend). Flow (FE never executes the spend — it mints + confirms, the server effect runs in `/v1/composition/actions/*`):
1. The action (e.g. "Re-run conformance") calls the mint endpoint → `CostEstimate { confirm_token, est_usd, est_tokens, quota_remaining }`.
2. `CostConfirmCard` renders the **$ estimate + token count + quota remaining**, an explicit **Confirm** and **Cancel**, and a one-line "what this does".
3. Confirm → POST the `confirm_token` to the actions route → 202 + poll (the existing `_resolveJob` poll in `api.ts`). The card shows progress; on done, refresh.
4. **Idempotency:** the token is consumed server-side (R2.8 ledger) — the FE disables Confirm after first click (no double-spend) and treats a "token already consumed" response as success (replay-safe).

### 4.6 The bind → COMMIT → GENERATE link (the dead-end the audit flagged)

Mockup 03 ends at "Commit tree" with **no path to actually generating prose** — H-8's "dead-ends with no generate screen". The fix is a continuous flow:
```
Planner-binding preview  → [Commit tree]  → scenes persist with motif_application
                                          → studio routes to `compose`/`assemble` with the first bound scene selected
                                          → author hits Generate (existing ComposeView) — a Tier-W spend → CostConfirmCard
                                          → generation runs within the motif beat
                                          → (later) Conformance panel shows planned│realized for what was written
```
`useMotifBinding.commitAndGenerate()` returns the contract; **W2 wires it** to the panel's `selectTab` + `setSceneId` (the existing intra-panel navigation, e.g. `CompositionPanel` lines 697, 723). The loop **closes** at the conformance panel — bind → generate → verify is one path, not three islands. This is the single most important H-8 remediation and is called out as a contract test (§7).

---

## §5 Accessibility + multi-device (audit §3, H-8)

The mockups have ~0 ARIA, 0 keyboard, 0 responsive (H-8). Every interactive element in W6 is accessible by default. W6 reuses the studio's existing a11y conventions (the existing components already use `aria-label` on selects, `data-testid` on actions).

### 5.1 ARIA + keyboard (every interactive)
- Every button/control has an accessible name (`aria-label` or visible text); icon-only buttons (the ↻ regenerate, ✕ remove) get `aria-label`.
- **Scope tabs / facet groups** use `role="tablist"`/`role="tab"` + `role="group"` with `aria-pressed`/`aria-selected`; arrow-key navigation within a group.
- **Drawer / modal** (`MotifDetailDrawer`, `AdoptTargetModal`, `SwapMotifPopover`): focus-trap on open, `Esc` closes, focus returns to the trigger (mount-on-open like `PowerViewOverlay` — fresh each time, no stale focus). `role="dialog"` + `aria-modal` + labelled by the title.
- **Cards** are not buttons; the Open/Adopt actions inside them are real `<button>`/`<a>` (no click-div). The card is keyboard-reachable via its action, not the whole card.
- **Live regions:** binding/adopt/conformance results announce via `aria-live="polite"` (a swap result, a quota warning, a drift flag) so screen-reader users hear the outcome of an async action.

### 5.2 Focus management
- Optimistic-lock / mutation errors move focus to the error message.
- The bind→generate route change focuses the compose target (continuity, not a lost focus on tab switch).

### 5.3 Color + text co-encoding (no color-only — §5.6 below, restated as an a11y rule)
**Never** encode state in color alone. Tier chips carry the **word** ("System"/"User"/"Public") + color. Conformance carries the **glyph + word** ("✓ beat realized" / "⚠ beat drift" / "✗ succession") + color. Tension uses the **number (T1-T5)** + the spark bar height, never hue alone. This is both WCAG 1.4.1 and the audit §3 finding.

### 5.4 The timeline drag-grid — keyboard model + MOBILE FALLBACK (contract now, build P4/W10)

The arc-template timeline (mockup 05/06-B) is a thread×chapter drag-grid — the audit's "undesigned drag-grid (0 mobile/touch, 0 keyboard)". **It is P4 (W10)**, but W6 **freezes the interaction contract now** so W10 builds the right thing:

- **Desktop (edit-grid):** dnd-kit (the studio already uses dnd-kit — `Corkboard`, `DockRail` reorder) for drag-place/move/resize of a motif on a (thread, chapter-span) cell. **Keyboard model (mandatory):** Tab to a placement → `Enter`/`Space` "grab" → arrow keys move across chapters / `Shift+arrow` resize the span / `Enter` drop / `Esc` cancel (the dnd-kit `KeyboardSensor` pattern, same as the existing `DockRail`). A placement is a focusable element with `aria-grabbed` + an `aria-describedby` announcing "combat thread, chapters 2-3".
- **Mobile / touch (fallback — REQUIRED, not optional):** a drag-grid is unusable on a phone. The fallback is a **vertical, per-thread list**: each thread is a section, each placement a row (chapter range + motif name) with **explicit "move"/"resize" stepper buttons and a "+ place" affordance** — no dragging. The edit-grid is **desktop-only**, gated behind a breakpoint, with a **notice on mobile** ("The timeline grid is available on a larger screen — here's the list view you can edit"). Reads (viewing an arc) work on all sizes; the grid *edit* affordance is the desktop-only piece.
- W6 ships the **`ArcTimelineContract` type + the mobile-list component skeleton** as the frozen interface (a `.md`-documented type, not built UI) so W10 implements against it.

### 5.5 Multi-device responsive (P1 surfaces)
The motif panels live inside the studio's existing responsive dock. P1 rules:
- **Library / catalog:** the facet rail (`MotifFacetRail`) is a left column on desktop; on narrow widths it collapses into a **filter sheet** (a button → bottom drawer), cards go single-column. Reuses the studio's existing responsive idiom (`flex-wrap`, the dock already stacks).
- **Planner-binding:** the scene list is already vertical (mockup 03 center column) — stacks naturally. The swap popover becomes a bottom-sheet on mobile.
- **Conformance:** the 3-column planned│realized│conformance grid **reflows to stacked cards** on narrow widths (each scene = one card with the three sections vertical) — the `grid-cols-12` → `grid-cols-1` breakpoint.
- No horizontal scroll on phone; tap targets ≥44px (the studio's existing button sizing already meets this).

### 5.6 Color tokens recap (co-encoding)
Restated for implementers: tier (text+hue), kind (text+hue), tension (number+bar), conformance (glyph+text+hue), source (icon+text). The dark palette from §2.2.

---

## §6 SIMPLE MODE for the beginner persona

The PO's framing: motifs are a *data/architecture* surface, but the **beginner author shouldn't see Greimas/Propp jargon**. `MotifSimpleModeContext` toggles two label registries; **simple is the default for a first-run user**.

### 6.1 What simple mode hides / replaces (`simpleMode.ts` label maps — pure, testable)

| Expert label | Simple label |
|---|---|
| `actant: subject` | "the hero / who acts" |
| `actant: sender` | "who sets it in motion" |
| `actant: object` | "what's at stake" |
| `actant: opponent` | "who stands in the way" |
| `kind: sequence` | "a plot shape" |
| `kind: scheme` | "a plot / deception" |
| `kind: emotion_arc` | "a feeling arc" |
| `tension_target` | "intensity" |
| `preconditions` / `effects` | "needs before" / "leaves after" |
| `match_reason` (the breakdown) | a one-line **plain sentence** ("Picked because the intensity fits and the setup matches what just happened") |
| `info_asymmetry` (knows/deceived/gap) | "who's in the dark" ("Maren knows; Ada is fooled into thinking …") |

### 6.2 Lead with examples + match_reason (per the spec)
Simple mode **leads with the concrete** (the spec §R1/§11 `examples[]` + `match_reason`):
- A `MotifCard` in simple mode shows the **first `example.text`** prominently (a concrete instance) above the abstract beat chips — "show, don't define".
- `MatchReasonChip` in simple mode renders **only `match_reason.summary`** (the plain sentence) — the tension/genre/precond/cosine breakdown is the expert-mode expansion.
- The empty state and the binding card lead with examples, not formal definitions.

### 6.3 Expert mode (the toggle off)
Surfaces the full vocabulary: actant names, kind codes, the `match_reason` numeric breakdown, `category` (`cultivation.fortuitous_encounter`), `code`. For the author who wants the structural control. The toggle lives in the library panel header (and persists per-device).

---

## §7 Tests (vitest + tsc) + eval-gate

W6's gate (master §4 W6): **tsc + vitest green; empty/error/permission states render; a11y (ARIA, keyboard, focus); mobile stack-down.**

### 7.1 Unit / component tests (vitest + @testing-library/react + MSW, mirroring existing `__tests__`)
- **`simpleMode.test.ts`** — every expert label maps to a simple label; tier-derivation pure fn (`{owner_user_id, visibility}` → `MotifTier`) is correct for system/user/public/others'-private.
- **`MotifCard.test.tsx`** — the 4 variants render with the right chip + glyph (color co-encoding asserted by text presence, not color); a system card shows no edit affordance.
- **`MotifEmptyState.test.tsx`** — first-run renders the seed-pack reassurance + "+ New motif" CTA (the load-bearing empty state); has a forward action (not a dead end).
- **`MotifStateBoundary.test.tsx`** — loading → skeleton, error → retry, permission → read-only lock + "Clone to edit".
- **`useMotifBinding.test.tsx`** — swap invalidates the preview query; clear → free-form; `commitAndGenerate` returns the route contract; a failed swap keeps the prior binding (no destructive optimism).
- **`CostConfirmCard.test.tsx`** — shows $ estimate; Confirm disables after click (no double-spend); a consumed-token response is treated as success.
- **`ConformanceSceneRow.test.tsx`** — a drift row shows ⚠ + "Regenerate to beat"; `calibrated=false` stamps "advisory/unverified" (honesty per R2.1).
- **`useAdoptFlow.test.tsx`** — target picker (User | book); `quota_exceeded` → the explainer, not a silent fail.
- **a11y assertions** — drawer focus-traps + `Esc` closes + focus returns; icon buttons have `aria-label`; an async result announces via `aria-live` (assert the live region updates).
- **MSW handlers** mock W1/W2/W3/W5 endpoints against the frozen DTOs (so W6 is green before they land).

### 7.2 Contract tests (against F0 §3.6 — the seam to other WS)
- A typed fixture per frozen DTO (`Motif`, `CatalogMotif`, `BoundMotif`, `SceneConformance`, `CostEstimate`) — `tsc` fails if W1/W2/W3/W5's real responses drift from `motif/types.ts`. This is the parallelization safety net (master §1 "integration = contract tests, not big-bang merge").

### 7.3 eval-gate (the WS exit)
`npm run -w frontend test -- motif` green + `tsc --noEmit` clean + the **R-NODE-P1 live-smoke FE leg** (master §6): on the assembled stack, the FE renders a bound motif's `match_reason`, the conformance panel shows planned│realized, and the bind→commit→generate route reaches ComposeView. Token: `live smoke: motif bound + traced + FE-rendered on a real stack-up` (or `LIVE-SMOKE deferred to D-MOTIF-FE-LIVE-SMOKE` if the stack isn't bootable at W6 build time — W6 builds against mocks, so a deferral is legitimate until R-NODE-P1).

---

## §8 Audit risk-guards (H-8 carried as build-time checks)

Each H-8 sub-finding becomes a guard (a test or a design rule that fails loudly if violated):

| H-8 finding | Guard in W6 |
|---|---|
| **Separate app, not the studio** | The library + conformance are `SubTab`/`WorkspacePanelId` dock panels inside `CompositionPanel`; planner-binding extends the existing `planner` view. **No new top-level route except** the (deferred) arc editor. A test asserts the panels mount inside the dock (`dock-slot-motifs` testid). |
| **No empty/loading/error/permission/cost states** | `MotifStateBoundary` + the §4 matrix; tests assert each state renders. First-run empty + Tier-W cost-confirm explicitly tested. |
| **Undesigned drag-grid (0 mobile/0 keyboard)** | §5.4 freezes the keyboard model + mobile vertical-list fallback as a contract (P1) before W10 builds it; the edit-grid is desktop-only with a mobile notice. |
| **0 ARIA / ~0 responsive** | §5 — ARIA/keyboard/focus on every interactive (tested); responsive reflow for library/binding/conformance (P1). |
| **No UI for §15 intrigue** | `InfoAsymmetryCard` (knows/deceived/gap) renders in the detail drawer + binding card; simple-mode plain-language version. |
| **Planner-binding dead-ends, no generate** | §4.6 the bind→COMMIT→GENERATE link; `commitAndGenerate` contract + a test that the route reaches ComposeView. The single most important fix. |
| **Conformance over-claims (calibration)** | `calibrated=false` stamps "advisory / unverified self-report" in the UI (R2.1 / AI-quality R1) — never presented as ground truth. |
| **Tenancy (kinds-bug) in the UI** | system / others'-public motifs are hard-read-only + "Clone to edit"; a user never edits a shared row (the clone primitive is the only path). |

---

## §9 Open micro-decisions + recommendation

| # | Decision | Recommendation |
|---|---|---|
| **MD-1** | The planner-binding children (`MotifBindingCard` etc.) live in W6's `motif/` subtree but are **rendered by W2's `PlannerView`**. Who owns the wiring? | **W6 ships the components + `useMotifBinding`; W2 imports + renders them** (one documented seam). Disjointness holds (W6 never edits `PlannerView.tsx`). The seam is a contract test. *Alternative: a render-prop slot W2 exposes — more decoupled but more ceremony; not worth it for one seam.* |
| **MD-2** | Library as a **dock panel** vs a **power-view** (full-screen overlay like the Story Map). | **Dock panel** (`motifs` SubTab) — it's a browse/manage surface the author returns to alongside planning, not a transient full-screen mode. The detail *drawer* covers the focused-read case. *(A "browse catalog" full-screen could be a P2 power-view if the dock feels cramped — defer.)* |
| **MD-3** | Conformance as its own panel vs folded into `quality`/`critic`. | **Own panel `conformance`** — it's a distinct plan↔realized view (07-A), and the existing `QualityPanel`/`CriticPanel` are about generation critique, not arc conformance. Keeps each panel single-concern (CLAUDE.md). |
| **MD-4** | Simple-mode default: on or off for first-run? | **On for first-run**, persisted per-device after. The beginner persona is the spec's stated target; the expert opts in. *(Telemetry could revisit, but default-simple matches "even a weak model / a beginner produces sound plans".)* |
| **MD-5** | Catalog social fields (`adopt_count`/rating) — show in P1? | **Optional-render** (the DTO marks them `?`) — show if present, omit if the backend defers them (spec §11 leaves this P2+). No FE blocker either way. |
| **MD-6** | i18n: ship all 4 locales' strings in P1, or English + stubs? | **English complete; the other 3 get the keys with English fallback** (the existing `t(key, { defaultValue })` pattern degrades gracefully — see `CompositionPanel`). Real translations are a follow-up; the keys must exist so nothing is hardcoded. |

---

## §10 Task list (W6, P1)

Ordered; each is a small, independently-verifiable step. Build against F0 §3.6 mocks; integrate at R-NODE-P1.

1. **Scaffold** `motif/` subtree: `types.ts` (mirror the frozen DTOs §1.3), `api.ts` (motif endpoints, relative `/v1/composition/motifs*`, reuse `apiJson` + the `_resolveJob` poll for Tier-W), `simpleMode.ts` (label maps + tier-derivation pure fns). **Tests:** `simpleMode.test.ts`.
2. **`MotifSimpleModeContext`** + the per-device preference read/write-through. **Test:** toggle + persistence (mock `/v1/me/preferences`).
3. **`MotifStateBoundary`** (loading/error/permission shared wrapper) + **`MotifEmptyState`** (first-run). **Tests:** state-matrix + empty-state forward-action.
4. **Library panel:** `useMotifLibrary` + `MotifLibraryView` + `MotifScopeTabs` + `MotifFacetRail` + `MotifCard` (4 variants). Re-skin to dark tokens (§2.2). **Tests:** card variants, facet narrowing, scope tabs, color co-encoding.
5. **Register the `motifs` dock panel:** add `'motifs'` to the `SubTab` union + `WorkspacePanelId` + `DOCK_ORDER` + the fixed strip + a `DockSlot` in `CompositionPanel`. ⚠ **`CompositionPanel.tsx` / `workspace/types.ts` / `workspace/dock.ts` are existing files — confirm W6 is their sole feature-owner for this add** (per master §4 W6 "owns the motif subtree … disjoint by namespace"; the panel-registration lines are a 1-tier add, the seam to flag at integration). If another WS touches these, route the registration through that WS. **Tests:** panel mounts (`dock-slot-motifs`).
6. **Detail drawer + manual create:** `useMotifDetail` + `MotifDetailDrawer` (read-only lock + "Clone to edit") + `useMotifQuickCreate` + `MotifQuickCreateForm` + `InfoAsymmetryCard`. **Tests:** read-only lock, clone, quick-create submit, scheme intrigue render.
7. **Adopt flow:** `useAdoptFlow` + `AdoptTargetModal` + `CostConfirmCard` (Tier-W mint/confirm). **Tests:** target picker, quota explainer, confirm-disables-after-click, consumed-token-as-success.
8. **Planner-binding children:** `useMotifBinding` + `MotifBindingCard` + `MatchReasonChip` + `SwapMotifPopover` + `RoleBindingRow` (+ `useRoleResolver`) + `OveruseBanner` + `ChainItHint` + the `commitAndGenerate` contract. **Tests:** swap-invalidates-preview, clear→free-form, unresolved-role picker, the bind→generate route contract.
9. **Conformance panel:** `useConformanceTrace` + `ConformanceTraceView` + `ConformanceSceneRow` (+ register the `conformance` dock panel, same as step 5). Regenerate-to-beat; `calibrated=false` advisory stamp. **Tests:** drift row + regenerate, advisory stamp, stacked-card reflow.
10. **a11y pass:** focus-traps, `aria-live`, keyboard nav on tabs/facets/popover; **responsive pass:** facet sheet, single-column cards, conformance reflow. **Tests:** focus/keyboard/live-region assertions.
11. **Arc-timeline contract (design-only, P1):** write `ArcTimelineContract` type + the mobile-list skeleton + the keyboard model doc (§5.4) for W10. No built grid UI.
12. **i18n ×4:** add motif keys to `en/composition.json` (complete) + `vi`/`ja`/`zh-TW` (keys with English fallback). **Verify:** no hardcoded user-facing strings in W6 components (all via `t()`).
13. **Contract tests + tsc** (§7.2) + **eval-gate** (§7.3): `npm run -w frontend test -- motif` green, `tsc --noEmit` clean. Live-smoke at R-NODE-P1 (or defer with the token).

**Deferred-now, contract-frozen (W10/W11/W8/W9):** arc-timeline edit-grid, arc conformance dashboard (07-B), visibility-flip + upstream-diff modal, mining-run trigger, import/deconstruct UI. Each has its frozen type/contract in this doc so the Wave-2 WS build against it.

---

### Appendix — disjointness ledger (what W6 touches)

- **New (W6 sole-owner):** the entire `frontend/src/features/composition/motif/` subtree (§3.1).
- **Shared existing files W6 must add to (flag at integration — 1-tier additive each):**
  - `components/CompositionPanel.tsx` — register `motifs` + `conformance` dock panels (SubTab union, strip, DockSlots).
  - `workspace/types.ts` + `workspace/dock.ts` — add the 2 panel ids to `WorkspacePanelId` / `PANEL_IDS` / `DOCK_ORDER`.
  - `i18n/locales/{en,vi,ja,zh-TW}/composition.json` — additive motif keys only.
- **Imported-by-another-WS (the seam):** `motif/hooks/useMotifBinding.ts` + the `MotifBinding*` components are **rendered by W2's `PlannerView`** (MD-1). W6 owns the files; W2 owns the wiring line.

These 3 shared touch-points are the only non-namespaced edits; all are additive single-tier and listed so the parallel reconciliation is clean.

# S-10 · Tier-C FE orphans (no backend — reachability + mounts)

> **Tier C — FE only (no draft; each references an existing component/panel).** These are the parity gaps
> from rounds 1–5 (the audit's A-3..A-13). No backend build; each is a mount, a rail, or a reachability fix.
> Grouped because they share the GG-8 registration shape and none needs a data-layer change.

## O1 · `style-voice` panel (port) — F-1
`StyleVoicePanel` (legacy) is a live capability reachable ONLY from `ChapterEditorPage`; it belongs to NO
session charter. Backend is complete (S-03 handles references' missing verb; style/voice CRUD is already
full). **Build:** wrap `StyleVoicePanel` as a `style-voice` dock panel (category `editor`), GG-8 shape
(catalog + enum + contract + i18n `guideBodyKey` + CATEGORY_ORDER + Lane-B `styleVoiceEffects`). Surfaces
density/pace + per-character voice with effective-value + source-tier (SET-1..8). No draft — the legacy
component is the design.

## O2 · `reference-shelf` panel (port) + carries S-03's edit affordance — F-1
Wrap `ReferencesPanel` as `reference-shelf` (category `editor`), GG-8 shape. This panel HOSTS the S-03 edit
affordance (metadata inline + "Edit content…"). The id is `reference-shelf`, NOT `references` (collides with
`composition_find_references`, a different concept — the plan-30 rename decision). No draft.

## O3 · Wire the Issues tab + diagnostics (PO-approved) — F-5
`StudioBottomPanel`'s three tabs (`jobs`/`generation`/`issues`) are all stubs ("Feed appears here once
wired"). PO-1 approved amending AN-12 for `composition_diagnostics`. **Build:** `GET
/v1/composition/books/{bid}/diagnostics` (a read-only mirror over the shipped `agent_native.py` engine — the
one backend piece here) + wire the Issues tab to a ranked error→warn→info list, each row deep-linking to the
panel that owns the fix. `jobs`/`generation` tabs: wire to the existing jobs feeds. The Issues-tab layout is
a small inline decision (a ranked list) — no full draft, but see `screen-issues-feed.html` (the token-lint
template) for the house pattern.

## O4 · `bible` + `quality` activity-bar rails (reachability) — F-7
The activity-bar `bible` view renders "Coming soon" over **13 built storyBible panels**; `quality` similarly
over 9. **Build:** a rail that lists its category's panels (the data is in `catalog.ts` →
`PANELS_BY_CATEGORY`). `bible` lists glossary/wiki/motif/world/cast/arc panels; `quality` lists the 9 quality
panels. `search` stays "Coming soon" — it is a genuinely unbuilt feature (PO decision D-a). Pure FE over
existing panels.

## O5 · Mount `MotifBindingLens` in `PlanDrawer` (the handoff that never happened) — F-16
S4 built `MotifBindingLens.tsx`; S2 never mounted it (0 importers), so per-scene motif binding is legacy-only.
**Build:** add a Motifs `<Section>` to `PlanDrawer`'s `ChapterSceneFacets` mounting `<MotifBindingLens>`, and
thread `projectId`/`chapterId` into `PlanDrawerProps` (they aren't there today — the plan called it "one
line", it's a few). No backend (bind/unbind is complete). No draft — SceneMotifsSection is the design.

## O6 · The 3 arc agent-only surfaces (affordances) — F-17
- `composition_arc_extract_template` — add a "Save this arc as a template" action on the arc-inspector /
  plan-hub (route exists; extract is wired). 
- `composition_arc_suggest` — a "Suggest an arc for this premise" button (route `POST /arc-templates/suggest`
  exists, 0 callers). 
- `composition_decompile_arcs` — a "Group my chapters into arcs" action (confirm-gated; no FE). 
All three are buttons over shipped engines — no new panel, no backend.

## Registration + tests (shared)
Every new panel (O1/O2/O4-rail) goes through the GG-8 gate: `panelCatalogContract` (enum==openable==contract),
`legacyParityContract` (now capability-carrying — S-10 flips the `unported` rows for style/references to
`carries` once mounted), CATEGORY_ORDER, i18n parity, a Lane-B handler. O5 gets a mount test asserting
`PlanDrawer` renders `<MotifBindingLens>` (the handoff regression guard). O3's diagnostics route gets a
read-only endpoint test.

## The PO decisions this spec surfaces (do NOT build until decided)
- **D-a search:** build a real search panel, or retire the activity-bar icon? (a nav icon saying "Coming
  soon" is not an option.)
- **D-d `[[`-create:** build "type `[[NewCharacter` → create it", or leave the affordance hidden (F-9)?
- **G-WORKFLOWS:** ownership vs Track C's P-5 — not a build decision.

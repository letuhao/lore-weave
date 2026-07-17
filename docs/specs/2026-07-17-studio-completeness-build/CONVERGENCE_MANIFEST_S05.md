# Convergence manifest — S-05 kg-triage panel

> The panel COMPONENT + hook + effects are built & tested in this session (my files, no registry
> conflict). The shared studio registry wiring below is for the **convergence node** to apply (per the
> fanout rule: sibling sessions also touch catalog.ts / panel_id enum / studio.json — don't edit them
> here). Until wired, the panel is not reachable from the nav/palette; everything else is done.

## Built & committed by S-05 (no convergence needed)
- `frontend/src/features/knowledge/hooks/useTriageQueue.ts` — list + resolve (grouped-by-signature).
- `frontend/src/features/knowledge/components/TriageQueue.tsx` — the queue UI; offers ONLY the
  `suggested_actions` the backend permits ∩ the actions the FE can drive (Frontend-Tool-Contract).
- `frontend/src/features/studio/panels/KgTriagePanel.tsx` — the dock-panel wrapper (book→project via
  `useBookKnowledgeProject`; glossary-handoff deep-link via `followStudioLink`).
- `frontend/src/features/studio/agent/handlers/knowledgeEffects.ts` — added `['kg-triage']` to the
  invalidation list (Lane-B "triageEffects" — folded into the ONE `/^kg_/` handler, NOT a 2nd one, per
  the no-double-fire `effectCoverage <=1` rule).
- i18n `knowledge` namespace: `triage.*` (5 item-type + 11 action + 2 prompt + 6 status keys), 17 locales.

## Convergence node MUST wire (shared registry)

### 1. `frontend/src/features/studio/panels/catalog.ts`
Add the import + the catalog row:
```ts
import { KgTriagePanel } from './KgTriagePanel';
// …in PANEL_CATALOG, beside the other kg-* rows (category 'knowledge'):
{ id: 'kg-triage', component: KgTriagePanel, titleKey: 'panels.kg-triage.title',
  descKey: 'panels.kg-triage.desc', category: 'knowledge',
  guideBodyKey: 'panels.kg-triage.guideBody' },
```
- **Category = `knowledge`** (NOT `storyBible` as the spec draft said). Rationale: every sibling kg-*
  panel is `knowledge`; putting triage elsewhere fragments discoverability. `01_DECISIONS` did not seal
  the category (it left "S-11 category" open but never sealed S-05's), so this is a deliberate build-time
  call, recorded here.

### 2. panel_id closed set (so the agent's `ui_open_studio_panel` can open it)
- `services/chat-service/app/services/frontend_tools.py` — add `"kg-triage"` to `CLOSED_SET_ARGS`'
  `panel_id` enum.
- `contracts/frontend-tools.contract.json` — add `"kg-triage"` to the same enum (run
  `WRITE_FRONTEND_CONTRACT=1 pytest` to regenerate, then the FE resolver already resolves it via the
  catalog id). Without both sides an agent `ui_open_studio_panel(panel:"kg-triage")` silently no-ops
  (the shipped-once panel_id-no-enum bug).

### 3. i18n `studio` namespace (panel title/desc/guide) — en, then gap-fill
Add to `frontend/src/i18n/locales/en/studio.json` under `panels`:
```json
"kg-triage": {
  "title": "Triage",
  "desc": "Review extracted elements that didn't match your schema and resolve them.",
  "guideBody": "When extraction finds an entity kind, relationship, or value that isn't in your schema yet, it parks it here instead of guessing. Each row offers only the fixes that are valid for it — map it to something you already have, add it to your schema/vocabulary, or dismiss it."
}
```
Then `python scripts/i18n_translate.py --ns studio` to gap-fill the 17 locales.
(`useStudioPanel` falls back to the panelId string if these are missing, so the panel is not broken
without them — but it reads "kg-triage" in the palette until wired.)

### 4. Deep-links IN (reachability boosters — optional but spec-requested, B.2)
- Empty-graph state + KG panels should surface "N items need triage →" that opens `kg-triage`
  (`host.openPanel('kg-triage')`). Candidate hosts: `KgOverviewPanel`, the empty-graph state in
  `KgGraphPanel`/`ProjectGraphView`. These are additive affordances on existing panels; can land in a
  follow-up without blocking the panel's own operability (it's already reachable via the palette once
  step 1 lands).

## Deferred (honest, gate-passing)
- `ontologyApi.dismissTriageItem` (per-ITEM dismiss) stays unwired: the public triage LIST is
  grouped-by-signature and exposes no per-item `triage_id`, so a per-item dismiss has nothing to target.
  The grouped view dismisses via `resolve(signature, 'dismiss')` (fully operable). Gate #3
  (naturally-next-phase): wiring per-item dismiss needs a per-item public list endpoint that doesn't
  exist. Not an empty shell — the group-level dismiss covers the user need.

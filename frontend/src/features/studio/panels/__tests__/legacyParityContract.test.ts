/**
 * 36 §GG-4 / close-21-28 C0 — the LEGACY-PARITY CONTRACT.
 *
 * A machine-checked INVENTORY (not a pre-deletion gate): every one of the 25 legacy
 * `CompositionPanel` sub-tabs resolves to EITHER a Studio panel id that actually exists in the
 * catalog, OR a written retirement reason. It is the only mechanical guard that Wave 6 does not
 * delete a live capability by mapping it to a panel that was never built. Ported by close-21-28
 * from the settled map in docs/plans/studio-adjudication/wave-6-decisions.md (all 3 corrections
 * applied: `arc`→`kg-timeline`, the real export is OPENABLE_STUDIO_PANELS, only GroundingPanel
 * was genuinely already ported). The hygiene-grep second `it()` from the sketch is DROPPED on
 * purpose (it false-positives on prose — the repo's hygiene-grep-literal-token lesson).
 */
import { describe, expect, it } from 'vitest';

import { OPENABLE_STUDIO_PANELS } from '../catalog';

type Home = string | { retired: string } | { unported: string };

// The 25 legacy CompositionPanel sub-tabs (CompositionPanel.tsx:87), each → a Studio panel id or
// a retirement reason. 23 homed, 2 retired.
const LEGACY_SUBTAB_HOME: Record<string, Home> = {
  // — already ported / successor already ships —
  // S1 (2026-07-16) homed the ComposeView draft loop + ChapterAssembleView as DEDICATED dock panels
  // (scene-compose / chapter-assemble), reusing CompositionPanel in soloPanel mode. The legacy
  // `compose`/`assemble` sub-tabs now map to those faithful homes — NOT to the Chat (`compose`
  // panel) or `agent-mode`, which are different capabilities (conversational co-writing / autonomous
  // multi-chapter runs) and do NOT carry the draft→candidates→accept or generate/stitch loops.
  compose: 'scene-compose',      // S1 — the ComposeView draft/candidates/accept loop, homed as a dock panel
  cowriter: 'compose',           // the conversational co-writer — ComposePanel renders <Chat>
  assemble: 'chapter-assemble',  // S1 — ChapterAssembleView (generate/stitch + human gate + correction capture)
  planner: 'planner',            // PlanForge planner panel
  beats: 'plan-hub',             // Wave 6 M4a (drawer facet)
  graph: 'plan-hub',             // SceneGraphCanvas superseded — plan-hub IS the graph canvas
  relmap: 'kg-graph',            // KgGraphPanel wraps ProjectGraphView → RelationshipMap
  timeline: 'kg-timeline',
  grounding: 'scene-inspector',  // ALREADY PORTED — SceneInspectorPanel mounts GroundingPanel
  critic: 'quality-critic',
  quality: 'quality',            // QualityHubPanel (never mount QualityPanel whole — F-Q11)
  // — Waves 1/3/4 + Wave 6: these panels are settled HOMES in the studio-wave plan, but their
  //   wave has not shipped in THIS branch, so the panel id is not yet in the catalog. They are
  //   `unported` (an honest "still legacy-only, pending its wave"), NOT broken homes. When the
  //   wave lands, flip each back to its bare-string home and this row asserts the id exists. —
  settings: 'book-settings',
  style: { unported: 'pending Wave 6 M1 — style-voice panel not yet in this branch catalog' },
  references: { unported: 'pending Wave 6 M2 — reference-shelf panel not yet in this branch catalog' },
  canon: 'quality-canon-rules', // S6 M1 — CanonRulesPanel ported into the studio dock behind QualityWorkGate
  polish: 'quality-heal',        // S6 M3 — PolishPanel ported into the studio dock (server-side apply seam)
  progress: 'progress',          // S6 M4 — ProgressPanel homed as a dock panel (category editor)
  flywheel: { unported: 'pending Wave 1 — quality-corrections panel not yet in this branch catalog' },
  motifs: { unported: 'pending Wave 3 — motif-library panel not yet in this branch catalog' },
  conformance: { unported: 'pending Wave 3 — quality-conformance panel not yet in this branch catalog' },
  // — homes that need a real M5 mount (the panel exists; the capability lands in M5.a/b/c) —
  cast: 'kg-entities',           // M5.a
  arc: 'kg-timeline',            // M5.b — NOT arc-templates (spec sketch is wrong by code)
  canonview: 'scene-inspector',  // M5.c — beside the already-ported GroundingPanel
  // — retired —
  threads: { retired: 'duplicate of quality-promises — delete, do not port (00C Q-3c)' },
  worldmap: {
    retired:
      'the composition place-graph is a work.settings.world_map node-position blob over KG ' +
      'entities — kg-graph already renders that graph; its only unique write (createEntity/' +
      'createRelation) moves into the kg panels in Wave 8 M8a.1. Delete after Wave 8; do not port.',
  },
};

const openableIds = new Set(OPENABLE_STUDIO_PANELS.map((p) => p.id));

describe('legacy parity contract (close-21-28 C0)', () => {
  it('covers all 25 legacy CompositionPanel sub-tabs', () => {
    expect(Object.keys(LEGACY_SUBTAB_HOME)).toHaveLength(25);
  });

  it('every homed sub-tab resolves to a panel that EXISTS in the catalog', () => {
    const brokenHomes: string[] = [];
    for (const [tab, home] of Object.entries(LEGACY_SUBTAB_HOME)) {
      if (typeof home === 'string' && !openableIds.has(home)) {
        brokenHomes.push(`${tab} -> ${home}`);
      }
    }
    // A home pointing at a non-existent panel id is a deleted-capability lie — this is the guard.
    expect(brokenHomes).toEqual([]);
  });

  it('every retired / unported sub-tab carries a substantive reason (>20 chars)', () => {
    for (const [tab, home] of Object.entries(LEGACY_SUBTAB_HOME)) {
      if (typeof home === 'object') {
        const reason = 'retired' in home ? home.retired : home.unported;
        expect(reason.length, `${tab} needs a real reason`).toBeGreaterThan(20);
      }
    }
  });
});

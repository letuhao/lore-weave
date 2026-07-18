/**
 * 36 §GG-4 / close-21-28 C0 — the LEGACY-PARITY CONTRACT.
 *
 * Every one of the 25 legacy `CompositionPanel` sub-tabs resolves to EITHER a Studio panel that
 * actually CARRIES its capability, OR a written reason. It is the only mechanical guard that Wave 6
 * does not delete a live capability. Ported by close-21-28 from the settled map in
 * docs/plans/studio-adjudication/wave-6-decisions.md. The hygiene-grep second `it()` from the
 * sketch is DROPPED on purpose (it false-positives on prose — the repo's hygiene-grep-literal-token
 * lesson).
 *
 * ── 2026-07-17 · the completeness audit gave this guard TEETH ──────────────────────────────────
 * It used to accept a bare panel id and assert only that the id EXISTS in the catalog. That is not
 * the property it advertises: a row could name a real panel that does something else entirely, and
 * the guard went green while retirement deleted the feature. The audit found exactly that, three
 * times over (docs/plans/2026-07-17-studio-completeness-AUDIT.md, F-6):
 *   · `settings → book-settings`  — book-settings edits book info/cover/genre; the composition Work
 *                                   settings editor lives ONLY on the legacy page.
 *   · `beats → plan-hub`          — plan-hub has zero `beat` code; the "drawer facet" never landed.
 *   · `cast`/`arc → kg-*`         — the real homes (`cast`, `character-arc`) shipped later and the
 *                                   inventory was never corrected.
 * So a home must now declare WHICH capability it carries, and the test proves the panel's import
 * closure actually renders it. A deliberate reimplementation is still allowed — as `supersedes`,
 * which must say why. Both forms are machine-checked; neither can be satisfied by prose alone.
 */
import { readFileSync, existsSync, readdirSync, statSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

import { OPENABLE_STUDIO_PANELS } from '../catalog';

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = resolve(HERE, '../../../..');            // …/frontend/src
const CATALOG = resolve(HERE, '../catalog.ts');

type Home =
  /** The home panel must actually RENDER this legacy component (proven through its import closure). */
  | { panel: string; carries: string }
  /** The home panel deliberately REIMPLEMENTS the capability rather than mounting the old component. */
  | { panel: string; supersedes: string; why: string }
  | { retired: string }
  | { unported: string };

// The 25 legacy CompositionPanel sub-tabs (CompositionPanel.tsx:87). `carries` names the component
// the legacy DockSlot renders — grep `slot('<tab>')` in CompositionPanel.tsx to re-derive it.
//
// The honest tally after the 2026-07-17 audit: **18 homed** (13 proven-carried + 5 reasoned
// supersedes) · **5 NOT homed** (settings · beats · timeline · style · references) · 2 retired.
// UPDATE 2026-07-18 (H-1a): `references` is now HOMED (reference-shelf carries ReferencesPanel) →
// 19 homed · 4 NOT homed (settings · beats · timeline · style).
// UPDATE 2026-07-18 (S-10 O1): `style` is now HOMED (style-voice carries StyleVoicePanel) →
// 20 homed · 3 NOT homed (settings · beats · timeline).
// The header used to say "23 homed, 2 retired" — that count came from the id-existence check and
// was wrong by five. **GG-4 retirement is gated on those five**, not on a green test run.
const LEGACY_SUBTAB_HOME: Record<string, Home> = {
  // — S1 (2026-07-16) homed the ComposeView draft loop + ChapterAssembleView as DEDICATED dock
  //   panels, reusing CompositionPanel in soloPanel mode. NOT the Chat (`compose` panel) or
  //   `agent-mode`: different capabilities that do not carry the draft→candidates→accept loop.
  compose: { panel: 'scene-compose', carries: 'ComposeView' },
  cowriter: { panel: 'compose', supersedes: 'Chat', why: 'the conversational co-writer — ComposePanel renders <Chat> directly; there is no legacy component to carry' },
  assemble: { panel: 'chapter-assemble', carries: 'ChapterAssembleView' },
  planner: { panel: 'planner', carries: 'PlannerView' },
  graph: { panel: 'plan-hub', supersedes: 'SceneGraphCanvas', why: 'SceneGraphCanvas is superseded — plan-hub IS the graph canvas (Wave 6 M4a), a reimplementation, not a mount' },
  relmap: { panel: 'kg-graph', supersedes: 'RelationshipMap', why: 'KgGraphPanel wraps ProjectGraphView, which GENERALIZES RelationshipMap and reuses its useRelationshipMap hook — a superset, not a mount' },
  grounding: { panel: 'scene-inspector', carries: 'GroundingPanel' },
  // AUDIT 2026-07-17 — the hardened check flagged this, and investigating it CLEARED it: the
  // capability is homed, just split across three panels rather than mounted whole.
  critic: {
    panel: 'quality-critic',
    supersedes: 'CriticPanel',
    why:
      'CriticPanel is split, not lost. QualityCriticPanel reimplements the REPORT half via ' +
      'QualityReportSection + a chapter picker + a ModelPicker (an on-demand per-chapter critique). ' +
      "The live-draft half is in S1's compose panels: ComposeView renders <CriticFlags> with " +
      'regenerate/dismiss (scene-compose), and the C26 canon override-gate <CanonGatePanel> renders ' +
      'in BOTH ComposeView (scene-compose) and ChapterAssembleView (chapter-assemble). Verified by ' +
      'grep: <CriticPanel> itself renders in exactly one place — the legacy CompositionPanel.',
  },
  quality: { panel: 'quality', supersedes: 'QualityPanel', why: 'F-Q11 — QualityHubPanel deliberately never mounts QualityPanel whole; it re-homes the lenses as DOCK-8 siblings' },
  // AUDIT 2026-07-17 — this row USED to read `settings: 'book-settings'` and was a FALSE home: the
  // old id-existence check passed because book-settings exists, but BookSettingsPanel wraps
  // SettingsTab (book info / cover / genre / world cross-link) and has nothing to do with the
  // composition Work settings. <CompositionSettingsView> renders in exactly ONE place — the legacy
  // CompositionPanel — so retiring it would have silently deleted the editor for the Work's model
  // refs / capture_correction_prose / critic_model_ref / reference_embed_model_ref. This is plan
  // 30's G-WORK-SETTINGS, which no session charter owns. Demoted to the truth until it is homed.
  settings: {
    unported:
      'AUDIT 2026-07-17 — G-WORK-SETTINGS. The composition Work settings editor ' +
      '(CompositionSettingsView: model refs, capture_correction_prose, critic_model_ref, ' +
      'reference_embed_model_ref) is legacy-only; book-settings is a DIFFERENT surface (book info/' +
      'cover/genre). GG-4 must not retire the legacy page until this is homed.',
  },
  canon: { panel: 'quality-canon-rules', carries: 'CanonRulesPanel' },     // S6 M1
  polish: { panel: 'quality-heal', carries: 'PolishPanel' },               // S6 M3
  progress: { panel: 'progress', carries: 'ProgressPanel' },               // S6 M4
  flywheel: { panel: 'flywheel', carries: 'FlywheelPanel' },               // S6 M5
  motifs: { panel: 'motif-library', carries: 'MotifLibraryView' },         // S4 (Wave 3)
  conformance: { panel: 'quality-conformance', carries: 'ConformanceTraceView' }, // S4 (Wave 3)
  // — S7 shipped DEDICATED homes for these three; the inventory pointed at kg-* until the
  //   2026-07-17 audit caught it. `cast`/`arc` were never lost — only mis-recorded.
  cast: { panel: 'cast', carries: 'CastCodexPanel' },                      // S7 (was: kg-entities)
  arc: { panel: 'character-arc', carries: 'CharacterArcView' },            // S7 (was: kg-timeline)
  canonview: { panel: 'scene-inspector', carries: 'GroundingPanel' },      // M5.c — beside GroundingPanel
  beats: { unported: 'AUDIT 2026-07-17 — the `beats: plan-hub` home was FALSE: BeatSheetView (drag a node onto a beat card to assign beat_role) has NO counterpart in plan-hub, which contains zero `beat` code. The Wave 6 M4a drawer facet was never built. Legacy-only until it is; GG-4 must not retire before this lands.' },
  timeline: { unported: 'AUDIT 2026-07-17 — `timeline: kg-timeline` is only a PARTIAL home: KgTimelinePanel mounts knowledge TimelineTab, which has no spoiler support, while composition TimelineView is the spoiler-SAFE chronology with the "AI sees <= here" cutoff marker. The cutoff is a load-bearing authoring feature; homing it needs a decision (extend TimelineTab vs port TimelineView).' },
  // S-10 O1 — HOMED: style-voice carries StyleVoicePanel (density/pace + per-character voice), wrapped as
  // a dock panel (StyleVoiceStudioPanel → StyleVoicePanel) so it's no longer ChapterEditorPage-only.
  style: { panel: 'style-voice', carries: 'StyleVoicePanel' },
  references: { panel: 'reference-shelf', carries: 'ReferencesPanel' },  // H-1a — ported: ReferenceShelfPanel wraps ReferencesPanel (library-first mount)
  // — retired —
  threads: { retired: 'duplicate of quality-promises — delete, do not port (00C Q-3c)' },
  worldmap: {
    retired:
      'the composition place-graph is a work.settings.world_map node-position blob over KG ' +
      'entities — kg-graph already renders that graph; its only unique write (createEntity/' +
      'createRelation) moves into the kg panels in Wave 8 M8a.1. Delete after Wave 8; do not port.',
  },
};

// ── proving a panel CARRIES a component ───────────────────────────────────────────────────────
// Walk the panel's import closure and look for the component being RENDERED. Reading source is the
// only way to check this from a unit test, and it is worth it: this is the assertion that turns a
// paper inventory into a guard.

const SOURCE_FILES: string[] = [];
(function collect(dir: string) {
  for (const entry of readdirSync(dir)) {
    const p = join(dir, entry);
    if (statSync(p).isDirectory()) {
      if (entry !== 'node_modules' && entry !== '__tests__') collect(p);
    } else if (/\.tsx?$/.test(entry) && !/\.test\.tsx?$/.test(entry)) {
      SOURCE_FILES.push(p);
    }
  }
})(SRC);

const readCached = new Map<string, string>();
function read(file: string): string {
  let t = readCached.get(file);
  if (t === undefined) {
    t = readFileSync(file, 'utf8');
    readCached.set(file, t);
  }
  return t;
}

/** Resolve an import specifier ('@/x/y' | './y' | '../y') to a real file, or null for a package. */
function resolveImport(fromFile: string, spec: string): string | null {
  let base: string | null = null;
  if (spec.startsWith('@/')) base = join(SRC, spec.slice(2));
  else if (spec.startsWith('.')) base = resolve(dirname(fromFile), spec);
  if (!base) return null;
  for (const cand of [`${base}.tsx`, `${base}.ts`, join(base, 'index.tsx'), join(base, 'index.ts')]) {
    if (existsSync(cand)) return cand;
  }
  return null;
}

/** The file that defines/exports `name`, if any (used to enter the graph at a panel component). */
function fileDefining(name: string): string | undefined {
  const re = new RegExp(`export (?:default )?(?:function|const|class) ${name}\\b`);
  return SOURCE_FILES.find((f) => re.test(read(f)));
}

/** Is `<Target …>` rendered anywhere in the import closure of `entry`? */
function rendersInClosure(entry: string, target: string, maxDepth = 5): boolean {
  const rendered = new RegExp(`<${target}[\\s/>]`);
  const seen = new Set<string>();
  let frontier = [entry];
  for (let d = 0; d < maxDepth && frontier.length; d++) {
    const next: string[] = [];
    for (const file of frontier) {
      if (seen.has(file)) continue;
      seen.add(file);
      const src = read(file);
      if (rendered.test(src)) return true;
      for (const [, spec] of src.matchAll(/from '([^']+)'/g)) {
        const r = resolveImport(file, spec);
        if (r && !seen.has(r)) next.push(r);
      }
    }
    frontier = next;
  }
  return false;
}

const catalogSrc = readFileSync(CATALOG, 'utf8');
/** panel id → the component the catalog mounts for it. */
const PANEL_COMPONENT = new Map(
  [...catalogSrc.matchAll(/id: '([a-z0-9-]+)', component: (\w+)/g)].map((m) => [m[1], m[2]]),
);

const openableIds = new Set(OPENABLE_STUDIO_PANELS.map((p) => p.id));
const entries = Object.entries(LEGACY_SUBTAB_HOME);
const homed = entries.filter((e): e is [string, Extract<Home, { panel: string }>] => 'panel' in e[1]);

describe('legacy parity contract (close-21-28 C0)', () => {
  it('covers all 25 legacy CompositionPanel sub-tabs', () => {
    expect(Object.keys(LEGACY_SUBTAB_HOME)).toHaveLength(25);
  });

  it('every homed sub-tab resolves to a panel that EXISTS in the catalog', () => {
    const brokenHomes = homed
      .filter(([, h]) => !openableIds.has(h.panel))
      .map(([tab, h]) => `${tab} -> ${h.panel}`);
    // A home pointing at a non-existent panel id is a deleted-capability lie — this is the guard.
    expect(brokenHomes).toEqual([]);
  });

  it('every `carries` home ACTUALLY renders its legacy component (not just a panel that exists)', () => {
    const lies: string[] = [];
    for (const [tab, home] of homed) {
      if (!('carries' in home)) continue;
      const component = PANEL_COMPONENT.get(home.panel);
      if (!component) {
        lies.push(`${tab}: no catalog component for panel '${home.panel}'`);
        continue;
      }
      const entry = fileDefining(component);
      if (!entry) {
        lies.push(`${tab}: cannot find the file defining ${component}`);
        continue;
      }
      if (!rendersInClosure(entry, home.carries)) {
        lies.push(
          `${tab}: '${home.panel}' (${component}) never renders <${home.carries}> — ` +
            `the capability is NOT homed there, so retiring the legacy page DELETES it. ` +
            `Either home it for real, or declare a reasoned { supersedes, why }.`,
        );
      }
    }
    expect(lies).toEqual([]);
  });

  it('every retired / unported / superseded sub-tab carries a substantive reason (>20 chars)', () => {
    for (const [tab, home] of entries) {
      const reason =
        'retired' in home ? home.retired
        : 'unported' in home ? home.unported
        : 'supersedes' in home ? home.why
        : null;
      if (reason !== null) expect(reason.length, `${tab} needs a real reason`).toBeGreaterThan(20);
    }
  });

  it('the carries-check is a LIVE gate (negative control — a lint that cannot fail is not a gate)', () => {
    // The whole point of the 2026-07-17 hardening: prove the check FIRES on a panel that exists but
    // does not carry the capability. `book-settings` genuinely does not render <CastCodexPanel>.
    const entry = fileDefining('BookSettingsPanel')!;
    expect(entry, 'BookSettingsPanel must be findable for this control to mean anything').toBeTruthy();
    expect(rendersInClosure(entry, 'CastCodexPanel')).toBe(false);
    // …and that it does not just always return false: a real home resolves true.
    const cast = fileDefining(PANEL_COMPONENT.get('cast')!)!;
    expect(rendersInClosure(cast, 'CastCodexPanel')).toBe(true);
  });
});

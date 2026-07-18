import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, it, expect } from 'vitest';
import { ALL_CATEGORIES, OPENABLE_STUDIO_PANELS, STUDIO_PANEL_COMPONENTS } from '../catalog';
// No runtime cycle: useStudioCommands.ts:4 imports only TYPES from catalog, so the edge is erased.
import { CATEGORY_ORDER } from '../../palette/useStudioCommands';

// Frontend-tool contract — the EFFECT half for the studio Lane-A open-panel tool.
//
// The BE advertises ui_open_studio_panel with a `panel_id` enum (the panels the
// agent may open); the FE dock can only build ids in STUDIO_PANEL_COMPONENTS. If
// the two drift, the agent gets offered a panel the dock silently can't build
// (host.openPanel try/catch no-op) — the deterministic sibling of the bug the
// live browser smoke caught. This keeps the advertised set, the palette's
// openable set, and the buildable dock set in lockstep, on every CI run.

const contract: Record<string, { args: Record<string, { enum?: string[] }> }> = JSON.parse(
  readFileSync(resolve(process.cwd(), '../contracts/frontend-tools.contract.json'), 'utf-8'),
);

describe('studio open-panel tool ↔ dock catalog contract', () => {
  const enumIds = contract.ui_open_studio_panel?.args?.panel_id?.enum;

  it('ui_open_studio_panel advertises an explicit panel_id enum', () => {
    expect(Array.isArray(enumIds) && enumIds.length > 0).toBe(true);
  });

  it('every advertised panel_id is a buildable dock component (never a silent no-op)', () => {
    for (const id of enumIds ?? []) {
      expect(Object.keys(STUDIO_PANEL_COMPONENTS)).toContain(id);
    }
  });

  it('the advertised set == the palette-openable set (agent and palette stay in sync)', () => {
    const openable = OPENABLE_STUDIO_PANELS.map((p) => p.id).sort();
    expect([...(enumIds ?? [])].sort()).toEqual(openable);
  });

  // #18 B6 — every palette-openable panel must declare a category, or it silently falls into
  // the generic "Panels" fallback bucket and the whole point of domain grouping erodes one panel
  // at a time with no signal. A future panel that forgets `category` fails here, loudly.
  it('every palette-openable panel has a category (#18 domain grouping)', () => {
    const missing = OPENABLE_STUDIO_PANELS.filter((p) => !p.category).map((p) => p.id);
    expect(missing).toEqual([]);
  });

  // X-2 / B7 — B6 above asserts a category is PRESENT; nothing asserted it was a MEMBER of
  // CATEGORY_ORDER. That guards only the harmless half. The failure modes are INVERTED: a panel
  // with NO category sorts LAST (benign fallback), but a panel whose category is UNLISTED in
  // CATEGORY_ORDER indexOf()s to -1 and sorts FIRST — which is how 5 shipped `quality` panels
  // ended up above `editor` at the top of the Command Palette.
  it('every palette-openable panel category is a MEMBER of CATEGORY_ORDER (X-2)', () => {
    const unordered = OPENABLE_STUDIO_PANELS
      .filter((p) => p.category && !(CATEGORY_ORDER as readonly string[]).includes(p.category))
      .map((p) => `${p.id}:${p.category}`);
    expect(unordered).toEqual([]);
  });

  // …and catch the drift AT THE TYPE, which is where it was actually introduced: a category can
  // exist in the union with zero panels using it yet, and it must STILL be ordered.
  it('CATEGORY_ORDER and the StudioPanelCategory union are the same set (X-2)', () => {
    expect([...ALL_CATEGORIES].sort()).toEqual([...CATEGORY_ORDER].sort());
  });

  // X-2 second half — useStudioCommands.ts:60 calls group(p.category, p.category), so an ORDERED
  // category with no `palette.group.<cat>` i18n label renders its RAW LOWERCASE ID as the palette
  // group header ("quality" sitting next to "Editor & Chapters"). Sorting it correctly and leaving
  // it mislabeled is a half-fix — so guard the LABEL SET, not just the order.
  it('every CATEGORY_ORDER entry has a palette.group i18n label (X-2)', () => {
    const groups = (
      JSON.parse(
        readFileSync(resolve(process.cwd(), 'src/i18n/locales/en/studio.json'), 'utf-8'),
      ) as { palette: { group: Record<string, string> } }
    ).palette.group;
    expect(CATEGORY_ORDER.filter((c) => !groups[c])).toEqual([]);
  });

  // X-3 — the User Guide renders t(p.guideBodyKey ?? p.descKey, { defaultValue: '' })
  // (UserGuidePanel.tsx:120), so a missing KEY **or** missing COPY renders a SILENTLY EMPTY guide
  // row — no warning, no crash, just a blank. BOTH halves must be guarded: the declaration
  // assertion ALONE is GREEN on the live bug (4 quality panels DECLARE a guideBodyKey whose
  // English key does not exist, so English users read 4 blank rows today).
  //
  // THE LINE EVERY LATER WAVE COPIES: a new panel lands its `guideBodyKey` in catalog.ts AND its
  // `panels.<id>.guideBody` string in en/studio.json IN THE SAME SLICE — these two tests red
  // otherwise. `en` is the SSOT; the other 17 locales ride `fallbackLng: 'en'` (i18n/index.ts:48).
  const enStudio = JSON.parse(
    readFileSync(resolve(process.cwd(), 'src/i18n/locales/en/studio.json'), 'utf-8'),
  );
  const lookupEn = (key: string): unknown =>
    key.split('.').reduce<any>((o, k) => (o == null ? undefined : o[k]), enStudio);

  it('every palette-openable panel declares a guideBodyKey (#19 User Guide)', () => {
    const missing = OPENABLE_STUDIO_PANELS.filter((p) => !p.guideBodyKey).map((p) => p.id);
    expect(missing).toEqual([]);
  });

  it('every guideBodyKey resolves to non-empty English copy (no blank guide row)', () => {
    const empty = OPENABLE_STUDIO_PANELS.filter((p) => {
      const v = p.guideBodyKey ? lookupEn(p.guideBodyKey) : undefined;
      return typeof v !== 'string' || v.trim() === '';
    }).map((p) => p.id);
    expect(empty).toEqual([]);
  });
});

import { describe, expect, it } from 'vitest';
import { STUDIO_TOURS, EDITOR_TOUR_CATALOG } from '../tours';
import { getStudioPanelDef } from '../../panels/catalog';

// #19 Wave 2 — the 5 role tours build their `target` from each panel's catalog `tourAnchor`
// (see `roleStep` in tours.ts, which throws at module-init time if a referenced panel has no
// tourAnchor) rather than hardcoding the selector a second time. This test locks in that every
// role tour's steps stay in sync with the catalog — a future rename of a panel's tourAnchor (or
// removing it) breaks here loudly instead of silently producing a dead tour-step selector.
describe('STUDIO_TOURS (role tours)', () => {
  it('core is unchanged: 6 hardcoded steps, 2 chrome-only + compose + editor + grammar + heatmap toggles', () => {
    expect(STUDIO_TOURS.core).toHaveLength(6);
    expect(STUDIO_TOURS.core.filter((s) => s.panelId)).toHaveLength(4);
  });

  const ROLE_STEPS: Record<string, string[]> = {
    writer: ['compose', 'editor', 'editor', 'editor', 'planner'],
    worldbuilder: ['glossary', 'wiki', 'knowledge'],
    translator: ['translation', 'enrichment-compose'],
    enricher: ['enrichment-gaps', 'enrichment-sources'],
    manager: ['sharing', 'book-settings'],
  };

  it.each(Object.entries(ROLE_STEPS))('%s tour has the expected panel sequence', (role, panelIds) => {
    const steps = STUDIO_TOURS[role as keyof typeof STUDIO_TOURS];
    expect(steps.map((s) => s.panelId)).toEqual(panelIds);
  });

  it('every role-tour step target matches its panel\'s live catalog tourAnchor (no drift)', () => {
    for (const [, steps] of Object.entries(ROLE_STEPS)) {
      for (const panelId of steps) {
        const def = getStudioPanelDef(panelId);
        expect(def?.tourAnchor).toBeTruthy();
        const step = Object.values(STUDIO_TOURS).flat().find((s) => s.panelId === panelId && s.target.includes(def!.tourAnchor!));
        expect(step, `no STUDIO_TOURS step for "${panelId}" targets its catalog tourAnchor`).toBeTruthy();
      }
    }
  });

  it('every role-tour step has non-empty i18n title/body keys', () => {
    for (const steps of Object.values(STUDIO_TOURS)) {
      for (const step of steps) {
        expect(step.titleKey).toMatch(/^intro\.tour\./);
        expect(step.bodyKey).toMatch(/^intro\.tour\./);
      }
    }
  });
});

// #19 Wave 3 — editor deep-dive tours (docs/specs/2026-07-06-editor-feature-inventory.md), split
// by feature group so the tour-picker (UserGuidePanel) offers focused topics instead of one long
// walkthrough.
describe('STUDIO_TOURS (editor deep-dive tours, #19 Wave 3)', () => {
  it('every EDITOR_TOUR_CATALOG entry has a corresponding non-empty STUDIO_TOURS entry', () => {
    for (const tour of EDITOR_TOUR_CATALOG) {
      expect(STUDIO_TOURS[tour.id], `no STUDIO_TOURS entry for catalog tour "${tour.id}"`).toBeTruthy();
      expect(STUDIO_TOURS[tour.id].length).toBeGreaterThan(0);
    }
  });

  it('every editor deep-dive step targets a data-testid selector and opens the editor panel', () => {
    for (const tour of EDITOR_TOUR_CATALOG) {
      for (const step of STUDIO_TOURS[tour.id]) {
        expect(step.target).toMatch(/^\[data-testid="[a-z0-9-]+"\]$/);
        expect(step.panelId).toBe('editor');
      }
    }
  });

  it('every EDITOR_TOUR_CATALOG entry has non-empty label/desc i18n keys under tourPicker.*', () => {
    for (const tour of EDITOR_TOUR_CATALOG) {
      expect(tour.labelKey).toBe(`tourPicker.${tour.id}.label`);
      expect(tour.descKey).toBe(`tourPicker.${tour.id}.desc`);
    }
  });
});

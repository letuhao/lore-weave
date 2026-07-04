import { describe, expect, it } from 'vitest';
import { STUDIO_TOURS } from '../tours';
import { getStudioPanelDef } from '../../panels/catalog';

// #19 Wave 2 — the 5 role tours build their `target` from each panel's catalog `tourAnchor`
// (see `roleStep` in tours.ts, which throws at module-init time if a referenced panel has no
// tourAnchor) rather than hardcoding the selector a second time. This test locks in that every
// role tour's steps stay in sync with the catalog — a future rename of a panel's tourAnchor (or
// removing it) breaks here loudly instead of silently producing a dead tour-step selector.
describe('STUDIO_TOURS (role tours)', () => {
  it('core is unchanged: 4 hardcoded steps, 2 chrome-only + compose + editor', () => {
    expect(STUDIO_TOURS.core).toHaveLength(4);
    expect(STUDIO_TOURS.core.filter((s) => s.panelId)).toHaveLength(2);
  });

  const ROLE_STEPS: Record<string, string[]> = {
    writer: ['compose', 'editor', 'planner'],
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

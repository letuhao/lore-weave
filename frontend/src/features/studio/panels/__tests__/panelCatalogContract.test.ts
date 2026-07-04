import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, it, expect } from 'vitest';
import { OPENABLE_STUDIO_PANELS, STUDIO_PANEL_COMPONENTS } from '../catalog';

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
});

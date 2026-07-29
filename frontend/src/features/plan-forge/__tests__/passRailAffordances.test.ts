// Every link target the API declares must have somewhere a person can press.
//
// The bug this exists for: `relink` has always accepted `'skeleton' | 'scene_plan'` — the service
// method, the route, the api function and the hook's own union all carried both — and the panel had
// exactly ONE button, hardcoded to 'skeleton'. So an author who ran all seven passes got arcs and
// chapters, no scenes, and a Scene Browser still reading "not planned". The capability was complete
// everywhere except where a person could reach it.
//
// A static read rather than a render: the assertion is about the SURFACE (does a call site exist),
// which is exactly what was missing, and a render test would need the whole studio host to say it.
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

const root = join(process.cwd(), 'src', 'features', 'plan-forge');
const hook = readFileSync(join(root, 'hooks', 'usePassRail.ts'), 'utf8');
const panel = readFileSync(join(root, 'components', 'PassRailPanel.tsx'), 'utf8');

/** The union the hook declares, read from the source rather than restated here — a hand-copied list
 *  would just be a third place to be wrong, which is the same class as the bug. */
function declaredTargets(): string[] {
  const m = hook.match(/relink:\s*\(target:\s*([^)]+)\)/);
  expect(m, 'usePassRail no longer declares a relink union').toBeTruthy();
  return [...(m![1].matchAll(/'([a-z_]+)'/g))].map((x) => x[1]);
}

it('the hook declares both link targets', () => {
  expect(declaredTargets().sort()).toEqual(['scene_plan', 'skeleton']);
});

it('EVERY declared target has a button in the panel', () => {
  for (const target of declaredTargets()) {
    expect(panel, `no UI path calls relink('${target}')`).toContain(`relink('${target}')`);
  }
});

it('the scene link is gated on the pass that produces a scene plan', () => {
  // A button whose only outcome is the backend's "run the scenes pass first" is not an affordance,
  // it is a trap.
  expect(panel).toContain('scenesReady');
  expect(panel).toMatch(/pass_id === 'scenes'/);
});

it('the two buttons say which half they do', () => {
  // "Link to outline →" read as "link the plan", so nobody looked for a second one.
  expect(panel).toContain('Link arcs + chapters →');
  expect(panel).toContain('Link scenes →');
});

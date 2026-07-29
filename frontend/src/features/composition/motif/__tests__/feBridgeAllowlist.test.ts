// The seam the FE→MCP bridge actually sits on.
//
// `mcpExecute` is the frontend's ONLY route to a Tier-W propose, and it goes through
// the BFF, which enforces `FE_BRIDGE_TOOL_ALLOWLIST`. That list lives in another
// service, in another language, and nothing joined the two — so a new FE flow can ship
// completely built (api helper, hook, component, unit tests, even a green live smoke
// against the domain service's own /mcp) and still 403 in the browser, because the one
// door it must pass through was never opened.
//
// That is not hypothetical: `composition_motif_translate` shipped exactly that way and
// this file is the fix for the CLASS, not the instance. It reads the controller source
// rather than duplicating the list, because a duplicated list is the same drift again
// one level up.
//
// It lives on the frontend side because that is where the drift originates: the failure
// mode we actually hit was a NEW call site with no matching entry, and whoever writes
// that call site is the person who needs to see this red. The assertion is symmetric
// (removing an allowlist entry reds it too), so one copy is enough — a second on the BFF
// side would only duplicate the maintenance.
//
// (It was first written against the BFF's own jest suite, which appeared to be dead —
// all 14 suites failing to transform. That turned out to be an installed tree drifted off
// its own lockfile: `typescript` 7.0.2 present where the lock pins 5.9.3. `npm ci`
// restores it and all 14 suites pass. Worth recording because "the suite is broken" was
// a wrong diagnosis of a working repo.)
import { describe, expect, it } from 'vitest';
import { readFileSync, readdirSync } from 'node:fs';
import { join, resolve } from 'node:path';

const FE_SRC = resolve(__dirname, '../../../..');            // frontend/src
const CONTROLLER = resolve(
  FE_SRC, '../../services/api-gateway-bff/src/tools/tools.controller.ts',
);

function walk(dir: string, out: string[] = []): string[] {
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    const p = join(dir, e.name);
    if (e.isDirectory()) {
      if (e.name !== 'node_modules' && e.name !== 'dist' && e.name !== '__tests__') walk(p, out);
      // Tests are skipped: they never reach the BFF, and this file's own doc comment
      // contains an illustrative `mcpExecute('tool_name')` that the scanner would
      // otherwise report as a missing allowlist entry — the guard failing on itself.
    } else if (/\.(ts|tsx)$/.test(e.name) && !/\.(test|spec)\.tsx?$/.test(e.name)) {
      out.push(p);
    }
  }
  return out;
}

function allowlist(): Set<string> {
  const src = readFileSync(CONTROLLER, 'utf8');
  const block = src.slice(src.indexOf('FE_BRIDGE_TOOL_ALLOWLIST'));
  const body = block.slice(block.indexOf('['), block.indexOf(']'));
  return new Set([...body.matchAll(/['"]([a-z][a-z0-9_]+)['"]/g)].map((m) => m[1]));
}

function calledTools(): Set<string> {
  const out = new Set<string>();
  for (const file of walk(FE_SRC)) {
    // `mcpExecute<T>(\n  'tool_name',` — the name is the first string literal after the
    // call opens, so scan a short window rather than demanding it be on one line.
    for (const m of readFileSync(file, 'utf8')
      .matchAll(/mcpExecute\s*(?:<[^>]*>)?\s*\([\s\S]{0,80}?['"]([a-z][a-z0-9_]+)['"]/g)) {
      out.add(m[1]);
    }
  }
  return out;
}

describe('FE→MCP bridge: every tool the frontend calls is reachable', () => {
  it('finds both sides at all — a silent empty scan would make this vacuous', () => {
    expect(allowlist().size).toBeGreaterThan(0);
    expect(calledTools().size).toBeGreaterThan(0);
  });

  it('every mcpExecute(<tool>) name is on the BFF allowlist', () => {
    const allowed = allowlist();
    const missing = [...calledTools()].filter((t) => !allowed.has(t)).sort();
    expect(missing, `add these to FE_BRIDGE_TOOL_ALLOWLIST in ${CONTROLLER}`).toEqual([]);
  });
});

import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, it, expect } from 'vitest';
import { resolveUiTool, UI_TOOL_NAMES } from '../uiNav';
import { resolveStudioUiTool, STUDIO_UI_TOOLS } from '../../../studio/agent/studioUiNav';

// Frontend-tool CONTRACT guard — the FE half (see
// services/chat-service/tests/test_frontend_tools_contract.py for the BE half).
//
// The bug this class exists to kill: a chat-service tool schema and its browser
// resolver drift on an arg NAME, so the LLM (the only thing joining them) sends
// something the resolver ignores, and every isolated unit test stays green. Here
// we read the SAME committed contract the BE asserts against and prove, for each
// PURE resolver, that it actually reads every arg the schema declares required —
// by observing property access through a Proxy (no hand-maintained manifest to
// drift). We also enforce the no-silent-no-op convention: a rejected resolve must
// carry an `error` the model can self-correct from.
//
// (Card-based tools — propose_edit / confirm_action / propose_record_edit /
// glossary_* — are covered by the BE contract's closed-set-enum rule; they have
// no pure resolver, their args are consumed by the diff/confirm cards.)

const contract: Record<string, { required: string[]; args: Record<string, { type?: string; enum?: string[] }> }> =
  JSON.parse(readFileSync(resolve(process.cwd(), '../contracts/frontend-tools.contract.json'), 'utf-8'));

/** A well-formed args object per the schema: enum→first value, else a typed dummy. */
function sampleArgs(spec: { args: Record<string, { type?: string; enum?: string[] }> }): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [name, a] of Object.entries(spec.args)) {
    out[name] = a.enum ? a.enum[0] : a.type === 'array' ? [] : a.type === 'object' ? {} : 'x';
  }
  return out;
}

/** Run a resolver and record which arg keys it actually reads (via a get-trap). */
function accessedArgKeys(resolver: (t: string, a: Record<string, unknown>) => unknown, tool: string, spec: { args: Record<string, { type?: string; enum?: string[] }> }): Set<string> {
  const accessed = new Set<string>();
  const proxy = new Proxy(sampleArgs(spec), {
    get(target, key, recv) {
      if (typeof key === 'string') accessed.add(key);
      return Reflect.get(target, key, recv);
    },
  });
  resolver(tool, proxy);
  return accessed;
}

/** The pure resolvers and the tool names each owns — must partition the ui_* space. */
const RESOLVERS = [
  { name: 'uiNav (C-NAV)', fn: resolveUiTool as (t: string, a: Record<string, unknown>) => { result: Record<string, unknown> }, tools: UI_TOOL_NAMES as readonly string[] },
  { name: 'studioUiNav (Lane A)', fn: resolveStudioUiTool as (t: string, a: Record<string, unknown>) => { result: Record<string, unknown> }, tools: STUDIO_UI_TOOLS as readonly string[] },
];

describe('frontend-tool contract — FE resolvers honor the chat-service schema', () => {
  it('the committed contract covers every tool the pure resolvers handle', () => {
    for (const r of RESOLVERS) for (const tool of r.tools) {
      expect(contract[tool], `${tool} missing from contract JSON`).toBeTruthy();
    }
  });

  for (const r of RESOLVERS) {
    for (const tool of r.tools) {
      const spec = contract[tool];

      it(`${tool}: resolver reads every REQUIRED arg the schema declares`, () => {
        // The exact drift that shipped ui_open_studio_panel broken: schema requires
        // `panel_id`, but if the resolver read a different key nothing here would
        // access panel_id → red test instead of a runtime hallucination.
        const accessed = accessedArgKeys(r.fn, tool, spec);
        for (const req of spec.required) {
          expect(accessed.has(req), `${tool}: resolver never reads required arg "${req}"`).toBe(true);
        }
      });

      it(`${tool}: a rejected resolve surfaces a corrective error (no silent no-op)`, () => {
        // Empty args → the resolver must reject WITH an error string, so a weak
        // model learns what to fix rather than spinning on a bare false flag.
        const res = r.fn(tool, {});
        expect(res.result.error, `${tool}: reject path returned no error`).toBeTruthy();
      });
    }
  }
});

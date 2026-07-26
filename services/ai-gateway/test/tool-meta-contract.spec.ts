/**
 * K21 — every tool ai-gateway advertises must DECLARE its C-TOOL tier.
 *
 * The consumer's `tool_tier()` defaults a missing tier to "R" (read/inert). That default is a
 * safety choice — a missing tier must never auto-commit a write — but it also makes an
 * UNDECLARED tool indistinguishable from a deliberately-read-only one, which is how three
 * untiered tools once reached a federated tools/list unnoticed. K2 found the sharp version of
 * the same hole in the domain services: three `*_task_provide_input` tools carried no tier,
 * so the silent "R" let them pass the ask-mode READ-ONLY filter — a read-only turn could
 * drive a pending gate to completion, performing the very write ask mode exists to withhold.
 *
 * Every domain service is now forced to declare a tier: Go panics at boot
 * (MustValidateToolMeta), Python raises (require_meta). ai-gateway's OWN tools are
 * hand-written definitions that no service gate covers — `tool_list`/`tool_load` were fixed
 * when that gap was first noticed, but the 7 `ui_*` tools and `propose_edit` were missed, and
 * a catalog audit on 2026-07-23 still found exactly those 8 untiered.
 *
 * `UiToolDef._meta` is now a required field, so a new ui_* tool cannot COMPILE untiered. This
 * test covers what the type cannot: the assembled list actually served to consumers, which is
 * where an untiered tool would really appear.
 */
import { UI_TOOLS } from '../src/mcp/ui-tools.js';
import { PROPOSE_EDIT_TOOL } from '../src/mcp/propose-edit-tool.js';
import { TOOL_LIST_TOOL, TOOL_LOAD_TOOL } from '../src/federation/find-tools.js';

const VALID_TIERS = ['R', 'A', 'W', 'S'];

// Every tool ai-gateway OWNS (consumer-local — no downstream provider, so no domain
// service's wire gate ever covered them).
const OWNED_TOOLS: Array<{ name: string; _meta?: unknown }> = [
  TOOL_LIST_TOOL,
  TOOL_LOAD_TOOL,
  ...UI_TOOLS,
  PROPOSE_EDIT_TOOL,
];

describe('C-TOOL tier contract (K21)', () => {
  it('advertises no untiered tool', () => {
    const untiered = OWNED_TOOLS.filter((t) => {
      const meta = t._meta as { tier?: unknown } | undefined;
      return !meta || typeof meta.tier !== 'string';
    }).map((t) => t.name);

    expect(untiered).toEqual([]);
  });

  it('declares only valid tiers', () => {
    for (const t of OWNED_TOOLS) {
      const tier = (t._meta as { tier?: string }).tier;
      expect(VALID_TIERS).toContain(tier);
    }
  });

  it('covers every ui_* tool', () => {
    // Guards the guard: if UI_TOOLS were ever re-exported or split, this list could silently
    // stop covering them and the test above would pass over an empty set.
    expect(UI_TOOLS.length).toBeGreaterThan(0);
    for (const t of UI_TOOLS) {
      expect(t._meta.tier).toBe('R');
      expect(t._meta.scope).toBe('none');
    }
  });

  it('keeps ui_* and propose_edit at R — a change here is a PERMISSION change', () => {
    // Not a style assertion. `tool_tier()` feeds the ask-mode read-only filter, so moving any
    // of these off R removes it from ask mode (or, off R upward, subjects it to the write
    // budget and confirm machinery). Pinning the value makes that a deliberate edit with a
    // failing test to read, rather than a quiet behaviour change.
    //
    // Read through the LOOSELY-typed OWNED_TOOLS deliberately. Iterating the concrete consts
    // instead made a deleted `_meta` fail as a TS2339 compile error pointing at this line —
    // still red, but the reader gets a type complaint instead of the rule they broke.
    const tiers = OWNED_TOOLS.filter((t) => t.name !== 'tool_list' && t.name !== 'tool_load').map(
      (t) => [t.name, (t._meta as { tier?: string } | undefined)?.tier] as const,
    );
    for (const [name, tier] of tiers) {
      expect(`${name}=${tier}`).toBe(`${name}=R`);
    }
  });
});

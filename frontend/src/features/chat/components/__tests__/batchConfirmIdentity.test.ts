// DQ-V4 — the Tier-A cap gate must reach a card, by NAME.
//
// 🔴 WHY THIS TEST IS IN THE FRONTEND. The backend renamed the cap's suspend from
// `confirm_action` to `batch_confirm` (stream_service.py, DQ-V4). The backend test for that
// rename passes whether or not the browser can render the new name — it asserts what the server
// emitted, not what anything does with it. If `batch_confirm` is missing from FRONTEND_TOOLS,
// `isPendingFrontend` is false, the record never reaches `proposals`, and the card does not render
// AT ALL: the Tier-A auto-apply cap — the enforceable bound on injection damage — becomes an
// invisible stall with a Confirm nobody can click.
//
// That is not hypothetical. Hours earlier in the same run, `glossary_confirm_action` was given a
// directive marker it shared with `confirm_action`, so it suspended under the wrong name; the main
// chat UI accepted both names and looked fine while cms-frontend's admin card silently stopped
// rendering. TypeScript cannot see any of it — the name crosses the wire as a string. The only
// thing that catches a name contract is a test that asserts the name.
//
// This reads the SOURCE of AssistantMessage.tsx rather than mounting it. Mounting would need the
// whole chat provider tree, and the property under test is a membership fact, not a rendering one.
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

const SRC = readFileSync(join(__dirname, '../AssistantMessage.tsx'), 'utf-8');
const SERVER_KEY = readFileSync(join(__dirname, '../../utils/serverKey.ts'), 'utf-8');

/** The FRONTEND_TOOLS array literal, which gates whether a pending record renders at all.
 *
 * 🔴 COMMENTS ARE STRIPPED FIRST, and finding that out cost a green run. The array's comments
 * QUOTE tool names while explaining the rename ("it suspended as 'confirm_action' until..."), so a
 * naive scan of the literal reported confirm_action twice — and would have reported a name that
 * appears ONLY in a comment as a live member. This test exists to catch a name contract; a helper
 * that reads prose as membership is the same defect one level up.
 */
function frontendToolNames(): string[] {
  const m = SRC.match(/const FRONTEND_TOOLS = \[([\s\S]*?)\];/);
  if (!m) throw new Error('FRONTEND_TOOLS array not found — this test is reading stale source');
  const withoutComments = m[1].replace(/\/\/[^\n]*/g, '');
  return [...withoutComments.matchAll(/'([a-z_]+)'/g)].map((x) => x[1]);
}

describe('the Tier-A cap gate keeps its identity', () => {
  it('batch_confirm is in FRONTEND_TOOLS, so a pending record reaches the renderer', () => {
    expect(frontendToolNames()).toContain('batch_confirm');
  });

  it('batch_confirm has a render branch that returns a card', () => {
    // Not merely mentioned in a comment: the dispatch must return a component for it.
    expect(SRC).toMatch(/tc\.tool === 'batch_confirm'\)\s*return\s*<\w+Card/);
  });

  it('the old name is still handled — the rename must not orphan a real confirm', () => {
    // `confirm_action` remains a genuine model-called tool. The cap moving to its own name
    // must not remove the branch that renders an ordinary confirm.
    expect(frontendToolNames()).toContain('confirm_action');
    expect(SRC).toMatch(/tc\.tool === 'confirm_action'\)\s*return\s*<\w+Card/);
  });

  it('serverKey groups batch_confirm with the other browser-rendered tools', () => {
    // Otherwise it is attributed to a domain server that never served it.
    expect(SERVER_KEY).toContain("'batch_confirm'");
  });
});

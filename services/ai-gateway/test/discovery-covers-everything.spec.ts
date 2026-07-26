/**
 * K23 — the discovery pair must be able to reach EVERY tool that is served.
 *
 * F17 retired `find_tools` from the LLM's view for a stated reason: it is semantic top-K, so
 * it "structurally CANNOT surface a tool the agent needs when that tool falls outside the K
 * matches", whereas "tool_list (see every tool in a domain) + tool_load (load the exact one)
 * have no such blind spot."
 *
 * They had one. Measured live 2026-07-23: `tools/list` served 299 tools, `tool_list` could
 * enumerate 289. The missing 10 were the CONSUMER-LOCAL set — tool_list and tool_load
 * themselves, the 7 ui_* directives, and propose_edit — because both handlers walked
 * `federation.catalog()` alone, which by definition holds only federated PROVIDER tools.
 *
 * `tool_load('ui_open_book')` returned `not_found`, which does not mean "exists but is not
 * federated"; it tells the model the tool DOES NOT EXIST.
 *
 * It bit hardest where it was least visible. ui_* and propose_edit are advertised
 * CONDITIONALLY (chat-service's F7c nav-intent / editor-surface gates), so on a turn where
 * the gate withholds one, discovery was the only route back — and it denied the tool was
 * real. handleListTools' own comment already claimed the opposite intent: "ai-gateway lists
 * them so they are discoverable + validated at one seam."
 */
import { handleToolList, handleToolLoad, handleListTools } from '../src/mcp/handlers.js';
import { GROUP_DIRECTORY, CATEGORY_ENUM } from '../src/federation/find-tools.js';

/** Minimal FederationService stand-in: a couple of federated tools + no overlay. */
function fakeFederation(): any {
  const catalog = [
    { name: 'book_list', description: 'list books', inputSchema: { type: 'object', properties: {} } },
    { name: 'kg_build', description: 'build kg', inputSchema: { type: 'object', properties: {} } },
  ];
  return {
    catalog: () => catalog,
    overlayTools: async () => [],
    isPartial: () => false,
    providerAvailability: () => [],
  };
}

async function servedNames(): Promise<string[]> {
  const res: any = await handleListTools(fakeFederation());
  return res.tools.map((t: any) => t.name);
}

async function listedNames(): Promise<string[]> {
  const res: any = await handleToolList(fakeFederation(), { category: 'all', include_deprecated: true });
  const cats = res.structuredContent.categories as Record<string, Array<{ name: string }>>;
  return Object.values(cats).flat().map((t) => t.name);
}

describe('discovery covers everything served (K23)', () => {
  it('tool_list enumerates every tool tools/list serves', async () => {
    const served = await servedNames();
    const listed = new Set(await listedNames());
    const missing = served.filter((n) => !listed.has(n));
    expect(missing).toEqual([]);
  });

  it('tool_load resolves the remaining consumer-local tools; DEPRECATED ui_* are not_found', async () => {
    // 2026-07-25 — the ui_* GUI-nav tools are DEPRECATED (de-advertised, not discoverable). They
    // are no longer part of the served/discoverable surface, so tool_load reports them not_found;
    // propose_edit + the discovery meta-tools remain. (handleUiTool still dispatches a raw
    // ui_* call defensively — covered in handlers.spec — but the model can no longer discover them.)
    const res: any = await handleToolLoad(fakeFederation(), {
      names: ['ui_open_book', 'propose_edit', 'tool_load'],
    });
    expect(res.structuredContent.not_found ?? []).toEqual(['ui_open_book']);
    expect(res.structuredContent.tools.map((t: any) => t.name).sort()).toEqual(
      ['propose_edit', 'tool_load'],
    );
  });

  it('buckets the remaining consumer-local tools under a REAL category (ui_* deprecated → absent)', async () => {
    // Enumerable only counts if `category` accepts the bucket — otherwise the tools appear
    // under 'all' but no targeted listing can reach them.
    expect(Object.keys(GROUP_DIRECTORY)).toContain('meta');
    expect(CATEGORY_ENUM).toContain('meta');

    const res: any = await handleToolList(fakeFederation(), { category: 'meta' });
    const names = res.structuredContent.tools.map((t: any) => t.name);
    expect(names).toEqual(expect.arrayContaining(['tool_list', 'tool_load', 'propose_edit']));
    expect(names).not.toContain('ui_navigate'); // deprecated ui_* no longer discoverable
  });

  it('does not disturb the federated tools', async () => {
    const res: any = await handleToolList(fakeFederation(), { category: 'book' });
    expect(res.structuredContent.tools.map((t: any) => t.name)).toEqual(['book_list']);
  });
});

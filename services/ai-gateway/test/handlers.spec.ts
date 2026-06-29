import {
  extractEnvelope,
  handleCallTool,
  handleListTools,
  headerValue,
} from '../src/mcp/handlers.js';
import type { FederationService } from '../src/federation/federation.service.js';

function fakeFederation(over: Partial<FederationService>): FederationService {
  return {
    catalog: () => [],
    executeTool: async () => ({ ok: true }),
    providerAvailability: () => [],
    isPartial: () => false,
    ...over,
  } as unknown as FederationService;
}

describe('headerValue / extractEnvelope', () => {
  it('reads headers case-insensitively and unwraps arrays', () => {
    expect(headerValue({ 'x-user-id': 'u1' }, 'X-User-Id')).toBe('u1');
    expect(headerValue({ 'x-trace-id': ['t1', 't2'] }, 'x-trace-id')).toBe('t1');
    expect(headerValue(undefined, 'x-user-id')).toBeUndefined();
  });

  it('lifts the per-call envelope off the request headers', () => {
    const env = extractEnvelope({
      'x-user-id': 'u1',
      'x-session-id': 's1',
      'x-trace-id': 'tr1',
    });
    expect(env).toEqual({ userId: 'u1', sessionId: 's1', traceId: 'tr1' });
  });

  it('lifts X-Project-Id into the envelope so project-scoped tools resolve downstream', () => {
    const env = extractEnvelope({
      'x-user-id': 'u1',
      'x-project-id': 'proj-9',
    });
    expect(env.projectId).toBe('proj-9');
    // omitted when the header is absent (so it is forwarded only when present)
    expect(extractEnvelope({ 'x-user-id': 'u1' }).projectId).toBeUndefined();
  });

  it('lifts X-Mcp-Key-Id into the envelope (public-edge spend attribution, H-C)', () => {
    const env = extractEnvelope({
      'x-user-id': 'u1',
      'x-mcp-key-id': 'key-xyz',
    });
    expect(env.mcpKeyId).toBe('key-xyz');
    // absent (undefined) for first-party calls, so it forwards only when present
    expect(extractEnvelope({ 'x-user-id': 'u1' }).mcpKeyId).toBeUndefined();
  });

  it('lifts X-Mcp-Spend-Cap-Usd into the envelope (per-key cap carrier, H-K)', () => {
    const env = extractEnvelope({
      'x-user-id': 'u1',
      'x-mcp-key-id': 'key-xyz',
      'x-mcp-spend-cap-usd': '5',
    });
    expect(env.spendCapUsd).toBe('5');
    // absent for first-party calls + for public keys with no cap
    expect(extractEnvelope({ 'x-user-id': 'u1' }).spendCapUsd).toBeUndefined();
  });
});

describe('handleListTools', () => {
  it('prepends find_tools, then the federated catalog, with an availability _meta (H10)', () => {
    const fed = fakeFederation({ catalog: () => [{ name: 'memory_search' }] as any });
    const res = handleListTools(fed);
    // find_tools is advertised FIRST (the lazy-discovery meta-tool), then the catalog.
    expect(res.tools[0].name).toBe('find_tools');
    expect(res.tools.map((t: any) => t.name)).toEqual(['find_tools', 'memory_search']);
    expect(res._meta).toEqual({ unavailable_providers: [], partial: false });
  });

  it('reports a down provider in _meta.unavailable_providers (H10)', () => {
    const fed = fakeFederation({
      catalog: () => [] as any,
      providerAvailability: () => [
        { name: 'knowledge', available: true },
        { name: 'book', available: false },
      ],
      isPartial: () => true,
    });
    expect(handleListTools(fed)._meta).toEqual({
      unavailable_providers: ['book'],
      partial: true,
    });
  });
});

describe('handleCallTool', () => {
  it('routes to executeTool with name, args, envelope, and _meta; returns the result verbatim', async () => {
    const executeTool = jest.fn().mockResolvedValue({ content: [{ type: 'text', text: 'ok' }] });
    const fed = fakeFederation({ executeTool });
    const meta = { progressToken: 'p1' };
    const res = await handleCallTool(
      fed,
      'memory_search',
      { query: 'x' },
      { 'x-user-id': 'u1', 'x-session-id': 's1' },
      meta,
    );
    // AIGW-LOW2: the `_meta` channel is forwarded downstream as the 4th arg.
    expect(executeTool).toHaveBeenCalledWith(
      'memory_search',
      { query: 'x' },
      { userId: 'u1', sessionId: 's1', traceId: undefined },
      meta,
    );
    expect(res).toEqual({ content: [{ type: 'text', text: 'ok' }] });
  });

  it('carries X-Project-Id through the envelope to executeTool (M1 fix)', async () => {
    const executeTool = jest.fn().mockResolvedValue({ content: [] });
    const fed = fakeFederation({ executeTool });
    await handleCallTool(
      fed,
      'kg_build_wiki',
      { model_ref: 'm' },
      { 'x-user-id': 'u1', 'x-project-id': 'proj-9' },
    );
    const env = executeTool.mock.calls[0][2];
    expect(env.projectId).toBe('proj-9');
  });

  it('carries X-Mcp-Key-Id through the envelope to executeTool (H-C)', async () => {
    const executeTool = jest.fn().mockResolvedValue({ content: [] });
    const fed = fakeFederation({ executeTool });
    await handleCallTool(
      fed,
      'memory_search',
      { query: 'x' },
      { 'x-user-id': 'u1', 'x-mcp-key-id': 'key-xyz' },
    );
    const env = executeTool.mock.calls[0][2];
    expect(env.mcpKeyId).toBe('key-xyz');
  });

  it('handles find_tools LOCALLY (never routes downstream) and returns matched tools', async () => {
    const executeTool = jest.fn();
    const fed = fakeFederation({
      executeTool,
      catalog: () =>
        [
          { name: 'book_create', description: 'create a new book' },
          { name: 'translation_start_job', description: 'start a translation job' },
        ] as any,
    });
    const res = await handleCallTool(fed, 'find_tools', { intent: 'create a book' }, { 'x-user-id': 'u1' });
    // Consumer-local: find_tools must NOT be routed to a provider (which would throw "unknown tool").
    expect(executeTool).not.toHaveBeenCalled();
    const payload = res.structuredContent as { tools: Array<{ name: string }> };
    expect(payload.tools.map((t) => t.name)).toContain('book_create');
    // It also returns the standard MCP content block (a text JSON of the payload).
    expect(res.content[0].type).toBe('text');
  });

  it('turns a provider failure into an MCP tool error (isError), not a throw', async () => {
    const fed = fakeFederation({
      executeTool: async () => {
        throw new Error('provider down');
      },
    });
    const res = await handleCallTool(fed, 'memory_search', {}, {});
    expect(res.isError).toBe(true);
    // Generic LLM-facing message — names the tool, not the failure detail.
    expect(res.content[0].text).toBe("tool 'memory_search' failed: provider error");
  });

  it('does NOT leak the internal provider URL into the LLM-visible tool-error text', async () => {
    const fed = fakeFederation({
      executeTool: async () => {
        // A real transport failure embeds the internal endpoint in its message.
        throw new Error('fetch failed: connect ECONNREFUSED http://book-service:8082/mcp');
      },
    });
    const res = await handleCallTool(fed, 'book_create', {}, {});
    expect(res.isError).toBe(true);
    const text = res.content[0].text as string;
    expect(text).not.toContain('book-service');
    expect(text).not.toContain('8082');
    expect(text).not.toContain('ECONNREFUSED');
    expect(text).toBe("tool 'book_create' failed: provider error");
  });
});

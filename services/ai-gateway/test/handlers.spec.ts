import {
  classifyCallToolError,
  classifyCallToolErrorCode,
  extractEnvelope,
  handleCallTool,
  handleGetPrompt,
  handleListPrompts,
  handleListResources,
  handleListResourceTemplates,
  handleListTools,
  handleReadResource,
  headerValue,
  normalizeToolResult,
  sanitizeUpstreamErrorText,
  TOOL_ERROR_CODES,
} from '../src/mcp/handlers.js';
import { UI_TOOLS, UI_DIRECTIVE_TYPE } from '../src/mcp/ui-tools.js';
import { PROPOSE_EDIT_DIRECTIVE_TYPE } from '../src/mcp/propose-edit-tool.js';
import type { FederationService } from '../src/federation/federation.service.js';

function fakeFederation(over: Partial<FederationService>): FederationService {
  return {
    catalog: () => [],
    executeTool: async () => ({ ok: true }),
    providerAvailability: () => [],
    isPartial: () => false,
    // Wave C5 — resources + prompts surfaces
    resourceCatalog: () => [],
    resourceTemplateCatalog: () => [],
    promptCatalog: () => [],
    readResource: async () => ({ contents: [] }),
    getPrompt: async () => ({ messages: [] }),
    // REG-P2-03 — per-user overlay (default no-op: flag off / no registrations)
    overlayTools: async () => [],
    isOverlayTool: () => false,
    executeOverlay: async () => ({ ok: true }),
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
  it('prepends the discovery meta-tools (tool_list/tool_load), then the catalog (H10)', async () => {
    const fed = fakeFederation({ catalog: () => [{ name: 'memory_search' }] as any });
    const res = await handleListTools(fed);
    // WS-1a (OQ1): tool_list/tool_load are the deterministic discovery pair, advertised FIRST,
    // then the catalog. F17 — find_tools is no longer advertised to the LLM (handler retained).
    expect(res.tools[0].name).toBe('tool_list');
    // Phase 3 — the consumer-local ui_* directive tools sit after the discovery
    // meta-tools and before the federated catalog (sourced from the module so this
    // assertion tracks the tool set without drifting).
    expect(res.tools.map((t: any) => t.name)).toEqual([
      'tool_list', 'tool_load', ...UI_TOOLS.map((t) => t.name), 'propose_edit', 'memory_search',
    ]);
    expect(res._meta).toEqual({ unavailable_providers: [], partial: false });
  });

  it('REG-P2-03: appends the per-user overlay tools after the System catalog', async () => {
    const fed = fakeFederation({
      catalog: () => [{ name: 'memory_search' }] as any,
      overlayTools: async () => [{ name: 'u_deadbeef_search' }] as any,
    });
    const res = await handleListTools(fed, { 'x-user-id': 'u1' });
    expect(res.tools.map((t: any) => t.name)).toEqual([
      'tool_list',
      'tool_load',
      ...UI_TOOLS.map((t) => t.name),
      'propose_edit',
      'memory_search',
      'u_deadbeef_search',
    ]);
  });

  it('reports a down provider in _meta.unavailable_providers (H10)', async () => {
    const fed = fakeFederation({
      catalog: () => [] as any,
      providerAvailability: () => [
        { name: 'knowledge', available: true },
        { name: 'book', available: false },
      ],
      isPartial: () => true,
    });
    expect((await handleListTools(fed))._meta).toEqual({
      unavailable_providers: ['book'],
      partial: true,
    });
  });

  it('REG-P2-03: routes a u_ prefixed tool to the overlay dispatch, not executeTool', async () => {
    const executeTool = jest.fn().mockResolvedValue({ content: [] });
    const executeOverlay = jest.fn().mockResolvedValue({ content: [{ type: 'text', text: 'overlay' }] });
    const fed = fakeFederation({ executeTool, executeOverlay, isOverlayTool: (n: string) => /^u_/.test(n) });
    const res = await handleCallTool(fed, 'u_deadbeef_search', { q: 'x' }, { 'x-user-id': 'u1' });
    expect(executeOverlay).toHaveBeenCalledWith('u_deadbeef_search', { q: 'x' }, { userId: 'u1', sessionId: undefined, traceId: undefined, projectId: undefined, mcpKeyId: undefined, spendCapUsd: undefined }, undefined);
    expect(executeTool).not.toHaveBeenCalled();
    expect(res).toEqual({ content: [{ type: 'text', text: 'overlay' }] });
  });

  it('Phase 3: dispatches a ui_* tool LOCALLY (directive), never to a provider', async () => {
    const executeTool = jest.fn().mockResolvedValue({ content: [] });
    const fed = fakeFederation({ executeTool });
    const res = await handleCallTool(fed, 'ui_navigate', { path: '/books' }, { 'x-user-id': 'u1' });
    expect(executeTool).not.toHaveBeenCalled(); // no downstream provider owns ui_*
    expect((res as any).structuredContent).toEqual({ type: UI_DIRECTIVE_TYPE, tool: 'ui_navigate', args: { path: '/books' } });
  });

  it('Phase 3: a ui_* tool with an out-of-enum arg is an isError result, not a silent no-op', async () => {
    const fed = fakeFederation({ executeTool: jest.fn() });
    const res = await handleCallTool(fed, 'ui_open_studio_panel', { panel_id: 'not-real' }, { 'x-user-id': 'u1' });
    expect((res as any).isError).toBe(true);
    expect((res as any).structuredContent.type).not.toBe(UI_DIRECTIVE_TYPE);
  });

  it('Phase 2: dispatches propose_edit LOCALLY (gated proposal), never to a provider', async () => {
    const executeTool = jest.fn().mockResolvedValue({ content: [] });
    const fed = fakeFederation({ executeTool });
    const res = await handleCallTool(fed, 'propose_edit', { operation: 'insert_at_cursor', text: 'hi' }, { 'x-user-id': 'u1' });
    expect(executeTool).not.toHaveBeenCalled();
    expect((res as any).structuredContent).toEqual({ type: PROPOSE_EDIT_DIRECTIVE_TYPE, operation: 'insert_at_cursor', text: 'hi' });
  });

  it('Phase 2: propose_edit with the incident shape is an isError result, not a silent card', async () => {
    const fed = fakeFederation({ executeTool: jest.fn() });
    const res = await handleCallTool(fed, 'propose_edit', { domain: 'book', changes: [] }, { 'x-user-id': 'u1' });
    expect((res as any).isError).toBe(true);
    expect((res as any).structuredContent.type).not.toBe(PROPOSE_EDIT_DIRECTIVE_TYPE);
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
    // #19: the 5th arg is the (here absent) abort signal.
    expect(executeTool).toHaveBeenCalledWith(
      'memory_search',
      { query: 'x' },
      { userId: 'u1', sessionId: 's1', traceId: undefined },
      meta,
      undefined,
    );
    expect(res).toEqual({ content: [{ type: 'text', text: 'ok' }] });
  });

  it('D-PLANNER-INFLIGHT-ABORT (#19): forwards the abort signal to executeTool', async () => {
    const executeTool = jest.fn().mockResolvedValue({ content: [] });
    const fed = fakeFederation({ executeTool });
    const ac = new AbortController();
    await handleCallTool(
      fed,
      'glossary_plan',
      { goal: 'design' },
      { 'x-user-id': 'u1' },
      undefined,
      ac.signal,
    );
    // The inbound request's signal rides through as the 5th arg, so a chat-turn
    // stop cancels the in-flight downstream tool call.
    expect(executeTool.mock.calls[0][4]).toBe(ac.signal);
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

  it('handles tool_list LOCALLY and returns the deterministic category list (WS-1a)', async () => {
    const executeTool = jest.fn();
    const fed = fakeFederation({
      executeTool,
      catalog: () =>
        [
          { name: 'book_create', description: 'create a new book', _meta: { tier: 'A' } },
          { name: 'book_list', description: 'list books', _meta: { tier: 'R' } },
        ] as any,
    });
    const res = await handleCallTool(fed, 'tool_list', { category: 'book' }, { 'x-user-id': 'u1' });
    expect(executeTool).not.toHaveBeenCalled();
    const payload = res.structuredContent as { category: string; count: number; tools: Array<{ name: string }> };
    expect(payload.category).toBe('book');
    expect(payload.count).toBe(2);
    expect(payload.tools.map((t) => t.name).sort()).toEqual(['book_create', 'book_list']);
  });

  it('handles tool_load LOCALLY and returns exact schemas without executing (WS-1a)', async () => {
    const executeTool = jest.fn();
    const fed = fakeFederation({
      executeTool,
      catalog: () =>
        [
          {
            name: 'book_create',
            description: 'create a new book',
            _meta: { tier: 'A' },
            inputSchema: { type: 'object', properties: { title: { type: 'string' } } },
          },
        ] as any,
    });
    const res = await handleCallTool(fed, 'tool_load', { name: 'book_create' }, { 'x-user-id': 'u1' });
    // Pure disclosure — loading must NOT execute the tool.
    expect(executeTool).not.toHaveBeenCalled();
    const payload = res.structuredContent as { tools: Array<{ name: string; input_schema: unknown }> };
    expect(payload.tools[0].name).toBe('book_create');
    expect(payload.tools[0].input_schema).toEqual({ type: 'object', properties: { title: { type: 'string' } } });
  });

  it('turns an unclassifiable provider failure into the generic MCP tool error (isError), not a throw', async () => {
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

  it('W0 #5: classifies a transport failure as retryable, without leaking the internal URL', async () => {
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
    expect(text).toBe(
      "tool 'book_create' failed: backend temporarily unreachable — retry may succeed",
    );
  });

  it('W0 #5: an unknown tool tells the model to use tool_list/tool_load (not "provider error")', async () => {
    const fed = fakeFederation({
      executeTool: async () => {
        throw new Error("unknown tool 'book_lst'");
      },
    });
    const res = await handleCallTool(fed, 'book_lst', {}, {});
    expect(res.isError).toBe(true);
    const text = res.content[0].text as string;
    expect(text).toContain('unknown tool');
    expect(text).toContain('tool_list');
    expect(text).toContain('tool_load');
  });

  it('W0 #5: an upstream JSON-RPC rejection passes its (sanitized) message through', async () => {
    const fed = fakeFederation({
      executeTool: async () => {
        // The TS SDK's McpError message shape for a JSON-RPC error response.
        throw new Error('MCP error -32602: book_id must be a UUID (see http://glossary-service:8085/mcp)');
      },
    });
    const res = await handleCallTool(fed, 'glossary_book_patch', {}, {});
    expect(res.isError).toBe(true);
    const text = res.content[0].text as string;
    // The actionable upstream text survives…
    expect(text).toContain('book_id must be a UUID');
    // …but nothing address-shaped does.
    expect(text).not.toContain('glossary-service');
    expect(text).not.toContain('8085');
    expect(text).not.toContain('http://');
  });

  it('W0 #5: the SDK request-timeout JSON-RPC code (-32001) reads as retryable transport', async () => {
    const fed = fakeFederation({
      executeTool: async () => {
        throw new Error('MCP error -32001: Request timed out');
      },
    });
    const res = await handleCallTool(fed, 'glossary_plan', {}, {});
    expect(res.content[0].text).toBe(
      "tool 'glossary_plan' failed: backend temporarily unreachable — retry may succeed",
    );
  });
});

describe('classifyCallToolError / sanitizeUpstreamErrorText', () => {
  it('classifies an aborted in-flight call as retryable', () => {
    const abort = new Error('This operation was aborted');
    (abort as any).name = 'AbortError';
    expect(classifyCallToolError(abort)).toBe(
      'backend temporarily unreachable — retry may succeed',
    );
  });

  it('classifies a 4xx Streamable-HTTP error as an upstream rejection with sanitized text', () => {
    const e = new Error('Streamable HTTP error: Error POSTing to endpoint: invalid internal token');
    (e as any).code = 401;
    const text = classifyCallToolError(e);
    expect(text).toContain('rejected by the owning service');
    expect(text).toContain('invalid internal token');
  });

  it('classifies a 5xx Streamable-HTTP error as retryable', () => {
    const e = new Error('Streamable HTTP error: Error POSTing to endpoint: upstream exploded');
    (e as any).code = 503;
    expect(classifyCallToolError(e)).toBe(
      'backend temporarily unreachable — retry may succeed',
    );
  });

  it('classifies HTTP 429 (even with an empty body) as retryable, not a rejection', () => {
    const e = new Error('Streamable HTTP error: ');
    (e as any).code = 429;
    expect(classifyCallToolError(e)).toBe(
      'backend temporarily unreachable or rate-limited — retry may succeed',
    );
  });

  it('classifies HTTP 408 as retryable, not a rejection', () => {
    const e = new Error('Streamable HTTP error: Request Timeout');
    (e as any).code = 408;
    expect(classifyCallToolError(e)).toBe(
      'backend temporarily unreachable or rate-limited — retry may succeed',
    );
  });

  it('classifies the JSON-RPC internal-error code (-32603) as retryable transport', () => {
    const e = new Error('MCP error -32603: internal error');
    expect(classifyCallToolError(e)).toBe(
      'backend temporarily unreachable — retry may succeed',
    );
  });

  it('sanitizes URLs, service hosts, and IPs out of upstream text', () => {
    const raw =
      'call http://book-service:8082/mcp failed via 10.0.3.17:5432 (see also knowledge-service:8092)';
    const clean = sanitizeUpstreamErrorText(raw);
    expect(clean).not.toContain('book-service');
    expect(clean).not.toContain('8082');
    expect(clean).not.toContain('10.0.3.17');
    expect(clean).not.toContain('8092');
  });

  it('sanitizes generic host:port pairs that no specific rule matches', () => {
    const raw = 'dial tcp localhost:8082 refused; upstream postgres:5432 unavailable';
    const clean = sanitizeUpstreamErrorText(raw);
    expect(clean).not.toContain('localhost:8082');
    expect(clean).not.toContain('postgres:5432');
    expect(clean).not.toContain('8082');
    expect(clean).not.toContain('5432');
  });
});

// ── Wave C5 — resources + prompts handlers ─────────────────────────────

describe('handleListResources / handleListResourceTemplates / handleListPrompts', () => {
  it('returns the federated resource catalog with the availability _meta (H10)', () => {
    const fed = fakeFederation({
      resourceCatalog: () => [{ uri: 'knowledge://static' }] as any,
      providerAvailability: () => [
        { name: 'knowledge', available: true },
        { name: 'book', available: false },
      ],
      isPartial: () => true,
    });
    const res = handleListResources(fed);
    expect(res.resources.map((r: any) => r.uri)).toEqual(['knowledge://static']);
    expect(res._meta).toEqual({ unavailable_providers: ['book'], partial: true });
  });

  it('returns resource TEMPLATES on their own list (the knowledge resources are templates)', () => {
    const fed = fakeFederation({
      resourceTemplateCatalog: () =>
        [{ uriTemplate: 'knowledge://project/{project_id}/summary' }] as any,
    });
    const res = handleListResourceTemplates(fed);
    expect(res.resourceTemplates.map((t: any) => t.uriTemplate)).toEqual([
      'knowledge://project/{project_id}/summary',
    ]);
    expect(res._meta).toEqual({ unavailable_providers: [], partial: false });
  });

  it('returns the federated prompt catalog with the availability _meta', () => {
    const fed = fakeFederation({
      promptCatalog: () => [{ name: 'recap_story_so_far' }] as any,
    });
    const res = handleListPrompts(fed);
    expect(res.prompts.map((p: any) => p.name)).toEqual(['recap_story_so_far']);
    expect(res._meta).toEqual({ unavailable_providers: [], partial: false });
  });

  it('a federation with nothing federated lists empty — never throws', () => {
    const fed = fakeFederation({});
    expect(handleListResources(fed).resources).toEqual([]);
    expect(handleListResourceTemplates(fed).resourceTemplates).toEqual([]);
    expect(handleListPrompts(fed).prompts).toEqual([]);
  });
});

describe('handleReadResource', () => {
  it('routes to federation.readResource with uri, envelope, and signal; returns the result verbatim', async () => {
    const readResource = jest.fn().mockResolvedValue({
      contents: [{ uri: 'knowledge://project/p1/summary', mimeType: 'text/plain', text: 'sum' }],
    });
    const fed = fakeFederation({ readResource });
    const ac = new AbortController();
    const res = await handleReadResource(
      fed,
      'knowledge://project/p1/summary',
      { 'x-user-id': 'u1', 'x-session-id': 's1', 'x-project-id': 'p1' },
      ac.signal,
    );
    expect(readResource).toHaveBeenCalledWith(
      'knowledge://project/p1/summary',
      { userId: 'u1', sessionId: 's1', traceId: undefined, projectId: 'p1' },
      ac.signal,
    );
    expect(res.contents[0].text).toBe('sum');
  });

  it('a provider failure rejects with a GENERIC error — no internal URL leaks', async () => {
    const fed = fakeFederation({
      readResource: async () => {
        throw new Error('fetch failed: ECONNREFUSED http://knowledge-service:8092/mcp');
      },
    });
    await expect(
      handleReadResource(fed, 'knowledge://project/p1/summary', { 'x-user-id': 'u1' }),
    ).rejects.toThrow("resource 'knowledge://project/p1/summary' read failed: provider error");
    // and specifically never the internal endpoint:
    await handleReadResource(fed, 'knowledge://x', { 'x-user-id': 'u1' }).catch((e: Error) => {
      expect(e.message).not.toContain('knowledge-service');
      expect(e.message).not.toContain('8092');
    });
  });
});

describe('handleGetPrompt', () => {
  it('routes to federation.getPrompt with name, args, envelope, and signal; returns the result verbatim', async () => {
    const getPrompt = jest.fn().mockResolvedValue({
      description: 'recap',
      messages: [{ role: 'user', content: { type: 'text', text: 'Recap …' } }],
    });
    const fed = fakeFederation({ getPrompt });
    const ac = new AbortController();
    const res = await handleGetPrompt(
      fed,
      'recap_story_so_far',
      { project_id: 'p1' },
      { 'x-user-id': 'u1' },
      ac.signal,
    );
    expect(getPrompt).toHaveBeenCalledWith(
      'recap_story_so_far',
      { project_id: 'p1' },
      { userId: 'u1', sessionId: undefined, traceId: undefined },
      ac.signal,
    );
    expect(res.messages[0].content.text).toBe('Recap …');
  });

  it('a provider failure rejects with a GENERIC error — no internal URL leaks', async () => {
    const fed = fakeFederation({
      getPrompt: async () => {
        throw new Error('fetch failed: ECONNREFUSED http://knowledge-service:8092/mcp');
      },
    });
    await expect(handleGetPrompt(fed, 'recap_story_so_far', {}, {})).rejects.toThrow(
      "prompt 'recap_story_so_far' get failed: provider error",
    );
  });
});

describe('C4 — uniform tool-failure envelope + output uniformity', () => {
  it('classifyCallToolErrorCode maps each failure class to a stable closed-set code', () => {
    const unknown = new Error("unknown tool 'book_lst'");
    expect(classifyCallToolErrorCode(unknown)).toBe('NOT_DISCOVERED');

    const abort = new Error('aborted');
    (abort as any).name = 'AbortError';
    expect(classifyCallToolErrorCode(abort)).toBe('UPSTREAM_UNAVAILABLE');

    const rate = new Error('Streamable HTTP error: too many');
    (rate as any).code = 429;
    expect(classifyCallToolErrorCode(rate)).toBe('RATE_LIMITED');

    const notFound = new Error('Streamable HTTP error: nope');
    (notFound as any).code = 404;
    expect(classifyCallToolErrorCode(notFound)).toBe('NOT_FOUND');

    const forbidden = new Error('Streamable HTTP error: nope');
    (forbidden as any).code = 403;
    expect(classifyCallToolErrorCode(forbidden)).toBe('NOT_PERMITTED');

    const badReq = new Error('Streamable HTTP error: nope');
    (badReq as any).code = 400;
    expect(classifyCallToolErrorCode(badReq)).toBe('VALIDATION');

    const validation = new Error('MCP error -32602: book_id must be a UUID');
    expect(classifyCallToolErrorCode(validation)).toBe('VALIDATION');

    const rejection = new Error('MCP error -32000: that genre is already adopted');
    expect(classifyCallToolErrorCode(rejection)).toBe('BUSINESS_RULE');

    const internal = new Error('MCP error -32603: boom');
    expect(classifyCallToolErrorCode(internal)).toBe('UPSTREAM_UNAVAILABLE');

    // every produced code is inside the closed set
    for (const e of [unknown, abort, rate, notFound, forbidden, badReq, validation, rejection, internal]) {
      expect(TOOL_ERROR_CODES).toContain(classifyCallToolErrorCode(e));
    }
  });

  it('a thrown failure returns the {code,message} envelope in structuredContent AND the text wrapper', async () => {
    const fed = fakeFederation({
      executeTool: async () => {
        throw new Error('MCP error -32602: book_id must be a UUID');
      },
    });
    const res: any = await handleCallTool(fed, 'glossary_book_patch', {}, {});
    expect(res.isError).toBe(true);
    expect(res.code).toBe('VALIDATION');
    expect(res.structuredContent.code).toBe('VALIDATION');
    expect(res.structuredContent.message).toContain('book_id must be a UUID');
    // W0 #5 text wrapper preserved for the model that reads content
    expect(res.content[0].text).toContain("tool 'glossary_book_patch' failed:");
  });

  it('a provider-returned isError result is re-shaped to the same envelope (keeps a stable code)', async () => {
    const fed = fakeFederation({
      executeTool: async () => ({
        isError: true,
        structuredContent: { code: 'NOT_PERMITTED', message: 'you do not own this book' },
        content: [{ type: 'text', text: 'you do not own this book' }],
      }),
    });
    const res: any = await handleCallTool(fed, 'glossary_entity_delete', {}, {});
    expect(res.isError).toBe(true);
    expect(res.code).toBe('NOT_PERMITTED');
    expect(res.structuredContent.code).toBe('NOT_PERMITTED');
    expect(res.content[0].text).toBe('you do not own this book');
  });

  it('a provider isError with a NON-stable code is inferred into the closed set', async () => {
    const fed = fakeFederation({
      executeTool: async () => ({
        isError: true,
        structuredContent: { code: 'KG_ENDPOINT_NOT_NODE', message: 'endpoint is not yet a node' },
        content: [{ type: 'text', text: 'endpoint is not yet a node' }],
      }),
    });
    const res: any = await handleCallTool(fed, 'kg_propose_edge', {}, {});
    expect(TOOL_ERROR_CODES).toContain(res.code);
    expect(res.code).toBe('BUSINESS_RULE'); // ran, refused on merits
  });

  it('output uniformity: content that merely re-serializes structuredContent collapses to a placeholder', async () => {
    const payload = { count: 2, items: [{ a: 1 }, { b: 2 }] };
    const fed = fakeFederation({
      executeTool: async () => ({
        content: [{ type: 'text', text: JSON.stringify(payload) }],
        structuredContent: payload,
      }),
    });
    const res: any = await handleCallTool(fed, 'glossary_search', {}, {});
    expect(res.structuredContent).toEqual(payload); // real JSON lives here, once
    expect(res.content[0].text).toBe('ok — see structuredContent'); // no double dump
  });

  it('output uniformity: NON-duplicate content (real prose) is left untouched', async () => {
    const fed = fakeFederation({
      executeTool: async () => ({
        content: [{ type: 'text', text: 'Here is a human summary of the result.' }],
        structuredContent: { count: 1 },
      }),
    });
    const res: any = await handleCallTool(fed, 'glossary_search', {}, {});
    expect(res.content[0].text).toBe('Here is a human summary of the result.');
  });

  it('normalizeToolResult passes a plain success (no structuredContent) through unchanged', () => {
    const r = { content: [{ type: 'text', text: 'hello' }] };
    expect(normalizeToolResult('x', r)).toBe(r);
  });
});

describe('C4 — review-fix hardening', () => {
  it('a provider isError with an ARRAY structuredContent is not mangled (envelope replaces it)', async () => {
    const fed = fakeFederation({
      executeTool: async () => ({
        isError: true,
        structuredContent: [{ a: 1 }, { b: 2 }], // pathological, but must not corrupt
        content: [{ type: 'text', text: 'partial failure across items' }],
      }),
    });
    const res: any = await handleCallTool(fed, 'glossary_bulk', {}, {});
    expect(res.isError).toBe(true);
    // envelope is a proper object with code+message, NOT an index-keyed spread of the array
    expect(Array.isArray(res.structuredContent)).toBe(false);
    expect(res.structuredContent).toEqual({ code: res.code, message: 'partial failure across items' });
    expect((res.structuredContent as any)['0']).toBeUndefined();
  });

  it('inferCode: permission signal wins over a co-occurring "not found"', () => {
    const e = new Error('MCP error -32000: you are not permitted; the record was not found');
    expect(classifyCallToolErrorCode(e)).toBe('NOT_PERMITTED');
  });
});

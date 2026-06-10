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
});

describe('handleListTools', () => {
  it('returns the federated catalog', () => {
    const fed = fakeFederation({ catalog: () => [{ name: 'memory_search' }] as any });
    expect(handleListTools(fed)).toEqual({ tools: [{ name: 'memory_search' }] });
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

  it('turns a provider failure into an MCP tool error (isError), not a throw', async () => {
    const fed = fakeFederation({
      executeTool: async () => {
        throw new Error('provider down');
      },
    });
    const res = await handleCallTool(fed, 'memory_search', {}, {});
    expect(res.isError).toBe(true);
    expect(res.content[0].text).toContain('provider down');
  });
});

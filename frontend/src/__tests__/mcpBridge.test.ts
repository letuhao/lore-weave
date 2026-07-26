// FE→MCP-tool bridge client — POSTs {tool, args} to /v1/ai/tools/execute and unwraps
// the `{result}` envelope. Errors propagate from apiJson (a 403 = not allowlisted).
import { describe, expect, it, vi, beforeEach } from 'vitest';

const apiJson = vi.fn();
vi.mock('@/api', () => ({ apiJson: (...a: unknown[]) => apiJson(...a), apiBase: () => '' }));

import { mcpExecute } from '../mcpBridge';

beforeEach(() => apiJson.mockReset());

describe('mcpExecute', () => {
  it('POSTs the tool + args with the bearer token and unwraps result', async () => {
    apiJson.mockResolvedValue({ result: { confirm_token: 'ct', estimate: { estimated_usd: 0.5 } } });
    const out = await mcpExecute('composition_conformance_run', { project_id: 'p1', scope: 'arc' }, 'tok');
    expect(out).toEqual({ confirm_token: 'ct', estimate: { estimated_usd: 0.5 } });
    const [url, init] = apiJson.mock.calls[0];
    expect(url).toBe('/v1/ai/tools/execute');
    expect(init.method).toBe('POST');
    expect(init.token).toBe('tok');
    expect(JSON.parse(init.body)).toEqual({
      tool: 'composition_conformance_run',
      args: { project_id: 'p1', scope: 'arc' },
    });
  });

  // The error path (e.g. a 403 "not on the FE allowlist") is a trivial `await`
  // rethrow from apiJson; it's covered end-to-end by the BFF allowlist test and the
  // ArcConformancePanel propose-error test (where react-query catches the rejection).
});

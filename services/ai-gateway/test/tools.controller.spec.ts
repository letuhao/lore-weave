import { ToolsController } from '../src/tools/tools.controller.js';
import { resetConfigForTest } from '../src/config/config.js';
import type { FederationService } from '../src/federation/federation.service.js';

// FE→MCP-tool bridge (server side) — SO-1 gate + envelope-from-headers + dict
// unwrap of the federated CallToolResult (structuredContent → text-JSON → raw).

function mockReqRes(opts: {
  token?: string;
  userId?: string;
  projectId?: string;
  traceId?: string;
  body?: unknown;
}) {
  const headers: Record<string, string | undefined> = {
    'x-internal-token': opts.token,
    'x-user-id': opts.userId,
    'x-project-id': opts.projectId,
    'x-trace-id': opts.traceId,
  };
  const req: any = {
    header: (k: string) => headers[k.toLowerCase()],
    headers,
    body: opts.body ?? {},
  };
  const res: any = {
    statusCode: 200,
    body: undefined as unknown,
    status(c: number) {
      this.statusCode = c;
      return this;
    },
    json(b: unknown) {
      this.body = b;
      return this;
    },
  };
  return { req, res };
}

function fakeFederation(over: Partial<FederationService>): FederationService {
  return {
    providerFor: (t: string) => (t === 'unknown_tool' ? undefined : ({ name: 'composition' } as any)),
    executeTool: jest.fn(),
    ...over,
  } as unknown as FederationService;
}

describe('ToolsController (FE→MCP-tool bridge)', () => {
  beforeAll(() => {
    process.env.INTERNAL_SERVICE_TOKEN = 'tok';
    resetConfigForTest();
  });

  it('rejects a missing internal token with 401 (before any execute)', async () => {
    const exec = jest.fn();
    const ctrl = new ToolsController(fakeFederation({ executeTool: exec as any }));
    const { req, res } = mockReqRes({ token: undefined, body: { tool: 'composition_conformance_run' } });
    await ctrl.execute(req, res);
    expect(res.statusCode).toBe(401);
    expect(exec).not.toHaveBeenCalled();
  });

  it('400 when tool is missing', async () => {
    const ctrl = new ToolsController(fakeFederation({}));
    const { req, res } = mockReqRes({ token: 'tok', body: { args: {} } });
    await ctrl.execute(req, res);
    expect(res.statusCode).toBe(400);
  });

  it('404 for an unknown tool (no provider owns it)', async () => {
    const exec = jest.fn();
    const ctrl = new ToolsController(fakeFederation({ executeTool: exec as any }));
    const { req, res } = mockReqRes({ token: 'tok', body: { tool: 'unknown_tool', args: {} } });
    await ctrl.execute(req, res);
    expect(res.statusCode).toBe(404);
    expect(exec).not.toHaveBeenCalled();
  });

  it('forwards the per-call identity (X-User-Id) lifted off headers (SEC-1)', async () => {
    const exec = jest.fn().mockResolvedValue({ structuredContent: { confirm_token: 'ct', estimate: {} } });
    const ctrl = new ToolsController(fakeFederation({ executeTool: exec as any }));
    const { req, res } = mockReqRes({
      token: 'tok',
      userId: 'u1',
      projectId: 'p1',
      body: { tool: 'composition_conformance_run', args: { scope: 'arc' } },
    });
    await ctrl.execute(req, res);
    expect(exec).toHaveBeenCalledTimes(1);
    const [tool, args, env] = exec.mock.calls[0];
    expect(tool).toBe('composition_conformance_run');
    expect(args).toEqual({ scope: 'arc' });
    expect(env.userId).toBe('u1');
    expect(env.projectId).toBe('p1');
    expect(res.statusCode).toBe(200);
    expect(res.body).toEqual({ result: { confirm_token: 'ct', estimate: {} } });
  });

  it('unwraps a text-JSON content block when structuredContent is absent', async () => {
    const exec = jest
      .fn()
      .mockResolvedValue({ content: [{ type: 'text', text: JSON.stringify({ confirm_token: 'ct2' }) }] });
    const ctrl = new ToolsController(fakeFederation({ executeTool: exec as any }));
    const { req, res } = mockReqRes({ token: 'tok', body: { tool: 'composition_conformance_run', args: {} } });
    await ctrl.execute(req, res);
    expect(res.statusCode).toBe(200);
    expect(res.body).toEqual({ result: { confirm_token: 'ct2' } });
  });

  it('surfaces a tool error (isError) as 400 with the text', async () => {
    const exec = jest
      .fn()
      .mockResolvedValue({ isError: true, content: [{ type: 'text', text: 'EDIT grant required' }] });
    const ctrl = new ToolsController(fakeFederation({ executeTool: exec as any }));
    const { req, res } = mockReqRes({ token: 'tok', body: { tool: 'composition_conformance_run', args: {} } });
    await ctrl.execute(req, res);
    expect(res.statusCode).toBe(400);
    expect(res.body).toEqual({ error: 'EDIT grant required' });
  });

  it('502 when executeTool throws (provider transport failure, detail hidden)', async () => {
    const exec = jest.fn().mockRejectedValue(new Error('connect http://composition:8217/mcp ECONNREFUSED'));
    const ctrl = new ToolsController(fakeFederation({ executeTool: exec as any }));
    const { req, res } = mockReqRes({ token: 'tok', body: { tool: 'composition_conformance_run', args: {} } });
    await ctrl.execute(req, res);
    expect(res.statusCode).toBe(502);
    expect(res.body).toEqual({ error: 'tool execution failed' });
  });
});

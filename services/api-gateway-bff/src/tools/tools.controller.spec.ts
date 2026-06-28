import * as jwt from 'jsonwebtoken';
import { HttpException } from '@nestjs/common';

import { ToolsController, FE_BRIDGE_TOOL_ALLOWLIST } from './tools.controller';

const TEST_SECRET = 'fe-bridge-test-secret-32-characters!!';

function bearer(sub: string): string {
  return `Bearer ${jwt.sign({ sub }, TEST_SECRET)}`;
}

async function expectStatus(p: Promise<unknown>, status: number): Promise<HttpException> {
  try {
    await p;
  } catch (e) {
    expect(e).toBeInstanceOf(HttpException);
    expect((e as HttpException).getStatus()).toBe(status);
    return e as HttpException;
  }
  throw new Error(`expected an HttpException with status ${status}`);
}

describe('ToolsController (FE→MCP-tool bridge)', () => {
  let controller: ToolsController;

  beforeEach(() => {
    process.env.JWT_SECRET = TEST_SECRET;
    process.env.AI_GATEWAY_URL = 'http://ai-gateway:8210';
    process.env.INTERNAL_SERVICE_TOKEN = 'tok';
    controller = new ToolsController();
  });
  afterEach(() => {
    delete process.env.JWT_SECRET;
    delete process.env.AI_GATEWAY_URL;
    delete process.env.INTERNAL_SERVICE_TOKEN;
    (global as any).fetch = undefined;
  });

  it('401 on a missing bearer token (no fetch)', async () => {
    const f = jest.fn();
    (global as any).fetch = f;
    await expectStatus(controller.execute({ tool: 'composition_conformance_run' }, undefined), 401);
    expect(f).not.toHaveBeenCalled();
  });

  it('401 on an invalid JWT', async () => {
    await expectStatus(
      controller.execute({ tool: 'composition_conformance_run' }, 'Bearer not-a-jwt'),
      401,
    );
  });

  it('400 when tool is missing', async () => {
    await expectStatus(controller.execute({}, bearer('u1')), 400);
  });

  it('403 for a tool NOT on the FE allowlist (anti-enumeration) — no fetch', async () => {
    const f = jest.fn();
    (global as any).fetch = f;
    // confirm/bind/admin tools must never be reachable from the FE bridge.
    await expectStatus(controller.execute({ tool: 'composition_motif_bind' }, bearer('u1')), 403);
    expect(f).not.toHaveBeenCalled();
    expect(FE_BRIDGE_TOOL_ALLOWLIST.has('composition_motif_bind')).toBe(false);
  });

  it('forwards an allowlisted propose with server-derived X-User-Id + X-Project-Id, relaying result', async () => {
    const f = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      text: async () => JSON.stringify({ result: { confirm_token: 'ct', estimate: { estimated_usd: 0.5 } } }),
    });
    (global as any).fetch = f;
    const out = await controller.execute(
      { tool: 'composition_conformance_run', args: { project_id: 'p1', scope: 'arc' } },
      bearer('user-42'),
    );
    expect(f).toHaveBeenCalledTimes(1);
    const [url, init] = f.mock.calls[0];
    expect(url).toBe('http://ai-gateway:8210/internal/tools/execute');
    expect(init.headers['x-internal-token']).toBe('tok');
    expect(init.headers['x-user-id']).toBe('user-42'); // from the JWT sub, never the body
    expect(init.headers['x-project-id']).toBe('p1'); // from args.project_id
    expect(JSON.parse(init.body)).toEqual({
      tool: 'composition_conformance_run',
      args: { project_id: 'p1', scope: 'arc' },
    });
    expect(out).toEqual({ result: { confirm_token: 'ct', estimate: { estimated_usd: 0.5 } } });
  });

  it('relays the gateway error status + message (a tool gate denial → 400)', async () => {
    (global as any).fetch = jest.fn().mockResolvedValue({
      ok: false,
      status: 400,
      text: async () => JSON.stringify({ error: 'EDIT grant required' }),
    });
    const ex = await expectStatus(
      controller.execute({ tool: 'composition_conformance_run', args: {} }, bearer('u1')),
      400,
    );
    expect(ex.message).toBe('EDIT grant required');
  });

  it('502 when ai-gateway is unreachable', async () => {
    (global as any).fetch = jest.fn().mockRejectedValue(new Error('ECONNREFUSED'));
    await expectStatus(
      controller.execute({ tool: 'composition_get_mine_job', args: {} }, bearer('u1')),
      502,
    );
  });
});

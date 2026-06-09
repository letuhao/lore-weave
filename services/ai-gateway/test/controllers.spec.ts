import { McpController } from '../src/mcp/mcp.controller.js';
import { resetConfigForTest } from '../src/config/config.js';

function mockReqRes(token?: string) {
  const req: any = {
    header: (k: string) => (k.toLowerCase() === 'x-internal-token' ? token : undefined),
    on: () => undefined,
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
    on: () => undefined,
  };
  return { req, res };
}

const fed: any = {
  catalog: () => [{ name: 'echo', description: 'e', inputSchema: { type: 'object' } }],
};

describe('McpController SO-1 token gate', () => {
  beforeAll(() => {
    process.env.INTERNAL_SERVICE_TOKEN = 'tok';
    resetConfigForTest();
  });

  it('rejects a missing internal token with 401 (before any MCP processing)', async () => {
    const { req, res } = mockReqRes(undefined);
    await new McpController(fed).handle(req, res);
    expect(res.statusCode).toBe(401);
  });

  it('rejects a wrong internal token with 401', async () => {
    const { req, res } = mockReqRes('wrong');
    await new McpController(fed).handle(req, res);
    expect(res.statusCode).toBe(401);
  });
});

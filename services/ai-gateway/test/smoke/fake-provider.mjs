// Minimal fake MCP provider for the gateway integration smoke. One tool
// `echo_user` that returns the X-User-Id + X-Internal-Token it received — so the
// smoke can assert the gateway forwarded the per-call envelope (AC4/INV-7).
import http from 'node:http';
import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StreamableHTTPServerTransport } from '@modelcontextprotocol/sdk/server/streamableHttp.js';
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from '@modelcontextprotocol/sdk/types.js';

const PORT = Number(process.env.PORT || 8901);
const h1 = (h, k) => (Array.isArray(h?.[k]) ? h[k][0] : h?.[k]);

function build() {
  const s = new Server({ name: 'fake-provider', version: '0.0.1' }, { capabilities: { tools: {} } });
  s.setRequestHandler(ListToolsRequestSchema, async () => ({
    tools: [{ name: 'echo_user', description: 'echo caller identity', inputSchema: { type: 'object', properties: {} } }],
  }));
  s.setRequestHandler(CallToolRequestSchema, async (_req, extra) => {
    const h = extra.requestInfo?.headers;
    return {
      content: [
        {
          type: 'text',
          text: JSON.stringify({ saw_user: h1(h, 'x-user-id') ?? null, saw_token: h1(h, 'x-internal-token') ?? null }),
        },
      ],
    };
  });
  return s;
}

const server = http.createServer(async (req, res) => {
  if (!req.url?.startsWith('/mcp')) {
    res.statusCode = 404;
    res.end();
    return;
  }
  const chunks = [];
  for await (const c of req) chunks.push(c);
  const body = chunks.length ? JSON.parse(Buffer.concat(chunks).toString()) : undefined;
  const s = build();
  const t = new StreamableHTTPServerTransport({ sessionIdGenerator: undefined, enableJsonResponse: true });
  res.on('close', () => {
    Promise.resolve(t.close?.()).catch(() => {});
    Promise.resolve(s.close?.()).catch(() => {});
  });
  await s.connect(t);
  await t.handleRequest(req, res, body);
});
server.listen(PORT, () => console.log(`fake-provider on :${PORT}/mcp`));

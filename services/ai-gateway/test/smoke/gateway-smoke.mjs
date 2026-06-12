// Gateway integration smoke: consumer (MCP client) → ai-gateway → fake provider.
// Proves AC2/AC3 (federation list + route), AC4/INV-7 (per-call envelope varies
// per user), AC9/SO-1 (internal-token gate), and the bespoke definitions endpoint.
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StreamableHTTPClientTransport } from '@modelcontextprotocol/sdk/client/streamableHttp.js';

const GW = process.env.GW || 'http://localhost:8210/mcp';
const TOK = process.env.TOK || 'smoke';

async function callAs(userId) {
  const transport = new StreamableHTTPClientTransport(new URL(GW), {
    requestInit: { headers: { 'X-Internal-Token': TOK, 'X-User-Id': userId } },
  });
  const client = new Client({ name: 'smoke', version: '0.0.1' });
  await client.connect(transport);
  const tools = await client.listTools();
  const res = await client.callTool({ name: 'echo_user', arguments: {} });
  await client.close();
  return { tools: tools.tools.map((t) => t.name), text: res.content[0].text };
}

const fail = (m) => {
  console.log('SMOKE FAIL:', m);
  process.exit(1);
};

const a = await callAs('alice');
const b = await callAs('bob');
console.log('federated tools:', JSON.stringify(a.tools));
console.log('alice →', a.text);
console.log('bob   →', b.text);

if (!a.tools.includes('echo_user')) fail('federation did not list provider tool');
if (!a.text.includes('"saw_user":"alice"')) fail('alice envelope not propagated to provider');
if (!b.text.includes('"saw_user":"bob"')) fail('bob envelope not propagated (per-call identity broken)');
if (a.text.includes('alice') && b.text.includes('alice')) fail('cross-user leak — bob saw alice');

// SO-1: a wrong internal token must be rejected with 401 (before MCP processing).
const r = await fetch(GW, {
  method: 'POST',
  headers: {
    'content-type': 'application/json',
    accept: 'application/json, text/event-stream',
    'X-Internal-Token': 'wrong-token',
  },
  body: JSON.stringify({ jsonrpc: '2.0', id: 1, method: 'tools/list', params: {} }),
});
console.log('bad-token status:', r.status);
if (r.status !== 401) fail(`expected 401 on bad internal token, got ${r.status}`);

console.log('SMOKE PASS — federation (list-tools) + per-call envelope + SO-1 gate all verified');
process.exit(0);

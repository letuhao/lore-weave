import { buildAuditRows } from '../src/audit/audit-client.js';

const KEY = 'key-1';
const OWNER = 'owner-1';
const TRACE = 'trace-1';

describe('buildAuditRows (H-O)', () => {
  it('emits one row per tools/call with the tool name', () => {
    const body = { jsonrpc: '2.0', method: 'tools/call', params: { name: 'book_get' }, id: 1 };
    const rows = buildAuditRows(body, KEY, OWNER, TRACE, 'relayed');
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({
      key_id: KEY,
      owner_user_id: OWNER,
      method: 'tools/call',
      tool_name: 'book_get',
      outcome: 'relayed',
      trace_id: TRACE,
    });
  });

  it('emits N rows for a JSON-RPC batch of N calls (one per call)', () => {
    const body = [
      { method: 'tools/call', params: { name: 'book_get' }, id: 1 },
      { method: 'tools/call', params: { name: 'kg_graph_query' }, id: 2 },
    ];
    const rows = buildAuditRows(body, KEY, OWNER, TRACE, 'denied_scope');
    expect(rows.map((r) => r.tool_name)).toEqual(['book_get', 'kg_graph_query']);
    expect(rows.every((r) => r.outcome === 'denied_scope')).toBe(true);
  });

  it('does NOT audit a successfully relayed non-call (tools/list / initialize = noise)', () => {
    expect(buildAuditRows({ method: 'tools/list', id: 1 }, KEY, OWNER, TRACE, 'relayed')).toEqual([]);
    expect(buildAuditRows({ method: 'initialize', id: 1 }, KEY, OWNER, TRACE, 'relayed')).toEqual([]);
  });

  it('DOES audit a non-call request that was rate-limited / denied (method-only row)', () => {
    const rows = buildAuditRows({ method: 'tools/list', id: 1 }, KEY, OWNER, TRACE, 'rate_limited');
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({ method: 'tools/list', tool_name: null, outcome: 'rate_limited' });
  });

  it('emits nothing for an empty / methodless body', () => {
    expect(buildAuditRows(undefined, KEY, OWNER, TRACE, 'relayed')).toEqual([]);
    expect(buildAuditRows({}, KEY, OWNER, TRACE, 'rate_limited')).toEqual([]);
  });
});

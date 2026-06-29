import {
  descriptorDomain,
  detectProposeInItem,
  detectProposeResult,
  pendingApprovalForId,
  pendingApprovalResponse,
  proposeDivertError,
  proposeDivertErrorForId,
} from '../src/scope/propose-detect.js';
import { idKey, singleWriteConfirmToolName, writeConfirmCallsById } from '../src/scope/scope-filter.js';

describe('detectProposeResult', () => {
  it('extracts token + domain from structuredContent and strips the token from preview', () => {
    const text = JSON.stringify({
      jsonrpc: '2.0',
      id: 1,
      result: {
        content: [{ type: 'text', text: '...' }],
        structuredContent: { confirm_token: 'tok-abc', domain: 'composition', title: 'Generate scene' },
      },
    });
    const p = detectProposeResult(text);
    expect(p).not.toBeNull();
    expect(p!.confirmToken).toBe('tok-abc');
    expect(p!.domain).toBe('composition');
    expect(p!.preview).toEqual({ domain: 'composition', title: 'Generate scene' });
    expect('confirm_token' in p!.preview).toBe(false); // NEVER echo the token
  });

  it('extracts from a JSON-encoded content[].text block when structuredContent is absent', () => {
    const inner = JSON.stringify({ confirm_token: 'tok-2', domain: 'translation', cost_estimate_usd: 0.42 });
    const text = JSON.stringify({ jsonrpc: '2.0', id: 2, result: { content: [{ type: 'text', text: inner }] } });
    const p = detectProposeResult(text);
    expect(p!.confirmToken).toBe('tok-2');
    expect(p!.domain).toBe('translation');
    expect(p!.costEstimateUsd).toBe(0.42);
  });

  it('falls back to deriving the domain from a dotted descriptor', () => {
    const text = JSON.stringify({ result: { structuredContent: { confirm_token: 't', descriptor: 'book.publish' } } });
    expect(detectProposeResult(text)!.domain).toBe('book');
  });

  it('returns null when there is no confirm_token (a normal result is not diverted)', () => {
    const text = JSON.stringify({ result: { structuredContent: { outcome: 'action_done' } } });
    expect(detectProposeResult(text)).toBeNull();
  });

  it('returns null for a batch response (never diverted in v1)', () => {
    const text = JSON.stringify([{ result: { structuredContent: { confirm_token: 't', domain: 'book' } } }]);
    expect(detectProposeResult(text)).toBeNull();
  });

  it('returns null for non-JSON / error shapes (fail-safe — no divert)', () => {
    expect(detectProposeResult('not json')).toBeNull();
    expect(detectProposeResult(JSON.stringify({ error: { code: -1 } }))).toBeNull();
  });

  it('returns null when a token is present but no domain can be determined', () => {
    const text = JSON.stringify({ result: { structuredContent: { confirm_token: 't', descriptor: 'book_delete' } } });
    expect(detectProposeResult(text)).toBeNull(); // non-dotted descriptor, no domain → unroutable
  });

  it('extracts cost from a nested estimate.cost_usd', () => {
    const text = JSON.stringify({ result: { structuredContent: { confirm_token: 't', domain: 'translation', estimate: { cost_usd: 1.5 } } } });
    expect(detectProposeResult(text)!.costEstimateUsd).toBe(1.5);
  });
});

describe('descriptorDomain', () => {
  it('derives a dotted head, a kg_ prefix, else null', () => {
    expect(descriptorDomain('translation.start_job')).toBe('translation');
    expect(descriptorDomain('kg_schema_edit')).toBe('kg');
    expect(descriptorDomain('book_delete')).toBeNull();
    expect(descriptorDomain('')).toBeNull();
    expect(descriptorDomain(undefined)).toBeNull();
  });
});

describe('singleWriteConfirmToolName', () => {
  it('returns the name only for a single write_confirm tools/call', () => {
    const wc = { jsonrpc: '2.0', method: 'tools/call', params: { name: 'composition_generate' }, id: 1 };
    expect(singleWriteConfirmToolName(wc)).toBe('composition_generate');
  });
  it('returns null for a write_auto / read tool', () => {
    expect(singleWriteConfirmToolName({ method: 'tools/call', params: { name: 'book_create' } })).toBeNull();
    expect(singleWriteConfirmToolName({ method: 'tools/call', params: { name: 'book_get' } })).toBeNull();
  });
  it('returns null for a batch, a non-call, or an unknown tool', () => {
    expect(singleWriteConfirmToolName([{ method: 'tools/call', params: { name: 'composition_generate' } }])).toBeNull();
    expect(singleWriteConfirmToolName({ method: 'tools/list' })).toBeNull();
    expect(singleWriteConfirmToolName({ method: 'tools/call', params: { name: 'no_such_tool' } })).toBeNull();
  });
});

describe('divert response shaping', () => {
  it('pendingApprovalResponse carries the id and NO token, preserving the request id', () => {
    const out = pendingApprovalResponse({ id: 7 }, 'appr-1') as { id: unknown; result: { structuredContent: unknown } };
    expect(out.id).toBe(7);
    expect(out.result.structuredContent).toEqual({ status: 'pending_human_approval', approval_id: 'appr-1' });
    expect(JSON.stringify(out)).not.toContain('confirm_token');
  });
  it('proposeDivertError is an isError result (fail-closed, no token)', () => {
    const out = proposeDivertError({ id: 9 }) as { id: unknown; result: { isError: boolean } };
    expect(out.id).toBe(9);
    expect(out.result.isError).toBe(true);
  });
  it('pendingApprovalForId / proposeDivertErrorForId key off an explicit id (per-batch-item)', () => {
    const ok = pendingApprovalForId('b', 'appr-2') as { id: unknown; result: { structuredContent: unknown } };
    expect(ok.id).toBe('b');
    expect(ok.result.structuredContent).toEqual({ status: 'pending_human_approval', approval_id: 'appr-2' });
    const err = proposeDivertErrorForId(null) as { id: unknown; result: { isError: boolean } };
    expect(err.id).toBeNull();
    expect(err.result.isError).toBe(true);
  });
});

describe('detectProposeInItem (D-PMCP-BATCH-WCONFIRM-DIVERT)', () => {
  it('extracts a propose from an already-parsed batch response item', () => {
    const item = { jsonrpc: '2.0', id: 3, result: { structuredContent: { confirm_token: 'tok-i', domain: 'book' } } };
    const p = detectProposeInItem(item);
    expect(p!.confirmToken).toBe('tok-i');
    expect(p!.domain).toBe('book');
    expect('confirm_token' in p!.preview).toBe(false);
  });
  it('returns null for a non-propose item, a non-object, or an array', () => {
    expect(detectProposeInItem({ id: 1, result: { structuredContent: { ok: true } } })).toBeNull();
    expect(detectProposeInItem(null)).toBeNull();
    expect(detectProposeInItem('x')).toBeNull();
    expect(detectProposeInItem([{ result: { structuredContent: { confirm_token: 't', domain: 'book' } } }])).toBeNull();
  });
});

describe('writeConfirmCallsById (D-PMCP-BATCH-WCONFIRM-DIVERT)', () => {
  it('maps id→name for write_confirm calls in a batch, ignoring other tiers/methods', () => {
    const batch = [
      { method: 'tools/call', params: { name: 'composition_publish' }, id: 1 }, // write_confirm
      { method: 'tools/call', params: { name: 'book_get' }, id: 2 }, // read
      { method: 'tools/list', id: 3 },
    ];
    const m = writeConfirmCallsById(batch);
    expect(m.get(idKey(1))).toBe('composition_publish');
    expect(m.has(idKey(2))).toBe(false);
    expect(m.has(idKey(3))).toBe(false);
    expect(m.size).toBe(1);
  });
  it('also handles a single (non-batch) write_confirm body and empties for none', () => {
    expect(writeConfirmCallsById({ method: 'tools/call', params: { name: 'composition_publish' }, id: 9 }).get(idKey(9))).toBe('composition_publish');
    expect(writeConfirmCallsById([{ method: 'tools/call', params: { name: 'book_get' }, id: 1 }]).size).toBe(0);
  });
});

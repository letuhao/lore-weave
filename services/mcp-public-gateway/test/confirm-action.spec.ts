import {
  CONFIRM_ACTION_TOOL,
  confirmActionResult,
  denyConfirmAction,
  detectConfirmActionCall,
  injectConfirmActionTool,
} from '../src/scope/confirm-action.js';
import { isWriteRequest } from '../src/scope/scope-filter.js';

describe('confirm_action rate-limit classification', () => {
  it('is treated as a WRITE so it fails closed on a store outage (it executes a spend)', () => {
    expect(isWriteRequest({ method: 'tools/call', params: { name: 'confirm_action', arguments: { confirm_token: 't', domain: 'd' } } })).toBe(true);
  });
});

describe('detectConfirmActionCall', () => {
  it('extracts confirm_token + domain from a single confirm_action call', () => {
    const body = { jsonrpc: '2.0', method: 'tools/call', params: { name: 'confirm_action', arguments: { confirm_token: 'tok', domain: 'composition' } }, id: 1 };
    expect(detectConfirmActionCall(body)).toEqual({ confirmToken: 'tok', domain: 'composition' });
  });
  it('returns null for a different tool, a batch, or missing args', () => {
    expect(detectConfirmActionCall({ method: 'tools/call', params: { name: 'book_get' } })).toBeNull();
    expect(detectConfirmActionCall([{ method: 'tools/call', params: { name: 'confirm_action', arguments: { confirm_token: 't', domain: 'd' } } }])).toBeNull();
    expect(detectConfirmActionCall({ method: 'tools/call', params: { name: 'confirm_action', arguments: { confirm_token: 'tok' } } })).toBeNull(); // no domain
    expect(detectConfirmActionCall({ method: 'tools/call', params: { name: 'confirm_action', arguments: { domain: 'd' } } })).toBeNull(); // no token
  });
});

describe('injectConfirmActionTool', () => {
  it('adds confirm_action to a tools/list result, once', () => {
    const text = JSON.stringify({ jsonrpc: '2.0', id: 1, result: { tools: [{ name: 'book_get' }] } });
    const out = JSON.parse(injectConfirmActionTool(text));
    const names = out.result.tools.map((t: { name: string }) => t.name);
    expect(names).toContain('confirm_action');
    expect(names).toContain('book_get');
    // idempotent
    const again = JSON.parse(injectConfirmActionTool(injectConfirmActionTool(text)));
    expect(again.result.tools.filter((t: { name: string }) => t.name === 'confirm_action')).toHaveLength(1);
  });
  it('passes through unparseable text unchanged', () => {
    expect(injectConfirmActionTool('not json')).toBe('not json');
  });
  it('the injected tool has the required args schema', () => {
    expect(CONFIRM_ACTION_TOOL.inputSchema.required).toEqual(['confirm_token', 'domain']);
  });
});

describe('denyConfirmAction', () => {
  it('uses the SAME anti-oracle -32601 message as a scope-denied tool', () => {
    const out = denyConfirmAction({ id: 5 }) as { error: { code: number; message: string }; id: unknown };
    expect(out.error.code).toBe(-32601);
    expect(out.error.message).toContain('not available to this key');
    expect(out.id).toBe(5);
  });
});

describe('confirmActionResult', () => {
  it('shapes a 2xx as a success tool result', () => {
    const out = confirmActionResult({ id: 1 }, 200, JSON.stringify({ status: 'executed', result: { ok: true } })) as { result: { isError?: boolean; structuredContent: { status: string } } };
    expect(out.result.isError).toBeUndefined();
    expect(out.result.structuredContent.status).toBe('executed');
  });
  it('shapes a 409 reprice — a genuine domain outcome, not an error code — as the original raw pass-through', () => {
    const out = confirmActionResult({ id: 1 }, 409, JSON.stringify({ status: 'reprice_required' })) as { result: { isError: boolean; structuredContent: { status: string; code?: unknown } } };
    expect(out.result.isError).toBe(true);
    expect(out.result.structuredContent.status).toBe('reprice_required');
    // auth sent no `code` for this shape — never fabricate one.
    expect(out.result.structuredContent.code).toBeUndefined();
  });

  // item #10: when auth-service DOES send its {code, message} business-error shape (writeErr —
  // e.g. AUTH_APPROVAL_EXPIRED, AUTH_CONFIRM_EXECUTE_FAILED), it is routed through the SAME
  // buildErrorEnvelope helper invoke-tool.ts's malformedResult/notActivatedError use, which
  // now maps the code into the C4 closed set (message preserved verbatim).
  it('routes an auth {code, message} business error through the shared envelope, code mapped to C4', () => {
    const authBody = JSON.stringify({ code: 'AUTH_APPROVAL_EXPIRED', message: 'this confirmation has expired — propose it again' });
    const out = confirmActionResult({ id: 9 }, 410, authBody) as {
      id: unknown;
      result: { isError: boolean; content: Array<{ text: string }>; structuredContent: { code: string; message: string } };
    };
    expect(out.id).toBe(9);
    expect(out.result.isError).toBe(true);
    // AUTH_APPROVAL_EXPIRED → CONFIRM_FAILED (C4); the human message is untouched.
    expect(out.result.structuredContent).toEqual({ code: 'CONFIRM_FAILED', message: 'this confirmation has expired — propose it again' });
    expect(JSON.parse(out.result.content[0].text)).toEqual(out.result.structuredContent);
  });
});

import { buildErrorEnvelope, toC4Code, TOOL_ERROR_CODES } from '../src/scope/mcp-error-envelope.js';

describe('buildErrorEnvelope (item #10 / C4 — shared isError tool-result envelope)', () => {
  it('shapes {jsonrpc, id, result:{isError, code, content, structuredContent}} and maps the code to the C4 closed set', () => {
    const out = buildErrorEnvelope(7, 'SOME_CODE', 'something went wrong') as {
      jsonrpc: string;
      id: unknown;
      result: { isError: boolean; code: string; content: Array<{ type: string; text: string }>; structuredContent: { code: string; message: string } };
    };
    expect(out.jsonrpc).toBe('2.0');
    expect(out.id).toBe(7);
    expect(out.result.isError).toBe(true);
    // unknown code → BUSINESS_RULE (C4 default), mirrored at top-level + structuredContent
    expect(out.result.code).toBe('BUSINESS_RULE');
    expect(out.result.structuredContent).toEqual({ code: 'BUSINESS_RULE', message: 'something went wrong' });
    expect(out.result.content).toEqual([{ type: 'text', text: JSON.stringify({ code: 'BUSINESS_RULE', message: 'something went wrong' }) }]);
    expect(TOOL_ERROR_CODES).toContain(out.result.code);
  });

  it('C4 mapping: edge + auth codes fold into the closed set; an already-C4 code passes through', () => {
    expect(toC4Code('MALFORMED_INVOKE_ARGS')).toBe('VALIDATION');
    expect(toC4Code('TOOL_NOT_DISCOVERED')).toBe('NOT_DISCOVERED');
    expect(toC4Code('AUTH_APPROVAL_EXPIRED')).toBe('CONFIRM_FAILED');
    expect(toC4Code('some_rate_limit_hit')).toBe('RATE_LIMITED');
    expect(toC4Code('permission_denied')).toBe('NOT_PERMITTED');
    expect(toC4Code('NOT_FOUND')).toBe('NOT_FOUND'); // already C4
    expect(toC4Code('anything else entirely')).toBe('BUSINESS_RULE');
  });

  it('defaults a nullish id to null (JSON-RPC convention shared with the other envelopes)', () => {
    const out = buildErrorEnvelope(undefined, 'C', 'm') as { id: unknown };
    expect(out.id).toBeNull();
  });
});

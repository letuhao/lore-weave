import { buildErrorEnvelope } from '../src/scope/mcp-error-envelope.js';

describe('buildErrorEnvelope (item #10 — shared isError tool-result envelope)', () => {
  it('shapes {jsonrpc, id, result:{isError:true, content, structuredContent}} with the given code+message', () => {
    const out = buildErrorEnvelope(7, 'SOME_CODE', 'something went wrong') as {
      jsonrpc: string;
      id: unknown;
      result: { isError: boolean; content: Array<{ type: string; text: string }>; structuredContent: { code: string; message: string } };
    };
    expect(out.jsonrpc).toBe('2.0');
    expect(out.id).toBe(7);
    expect(out.result.isError).toBe(true);
    expect(out.result.content).toEqual([{ type: 'text', text: JSON.stringify({ code: 'SOME_CODE', message: 'something went wrong' }) }]);
    expect(out.result.structuredContent).toEqual({ code: 'SOME_CODE', message: 'something went wrong' });
  });

  it('defaults a nullish id to null (JSON-RPC convention shared with the other envelopes)', () => {
    const out = buildErrorEnvelope(undefined, 'C', 'm') as { id: unknown };
    expect(out.id).toBeNull();
  });
});

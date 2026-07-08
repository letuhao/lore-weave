import {
  clientSupportsStructuredContent,
  rehydrateContentForLegacyClients,
} from '../src/scope/structured-content-rehydration.js';

const PLACEHOLDER = 'ok — see structuredContent for the full result';

function singleResult(content: unknown, structuredContent: unknown) {
  return JSON.stringify({
    jsonrpc: '2.0',
    id: 1,
    result: { content, structuredContent },
  });
}

describe('clientSupportsStructuredContent', () => {
  it('true for the version structuredContent was introduced in', () => {
    expect(clientSupportsStructuredContent('2025-06-18')).toBe(true);
  });

  it('true for a later version (string-sorts correctly as a date)', () => {
    expect(clientSupportsStructuredContent('2025-11-25')).toBe(true);
  });

  it('false for every pre-2025-06-18 SDK-supported version', () => {
    expect(clientSupportsStructuredContent('2025-03-26')).toBe(false);
    expect(clientSupportsStructuredContent('2024-11-05')).toBe(false);
    expect(clientSupportsStructuredContent('2024-10-07')).toBe(false);
  });

  it('false (conservative default) when the header is absent or empty', () => {
    expect(clientSupportsStructuredContent(undefined)).toBe(false);
    expect(clientSupportsStructuredContent(null)).toBe(false);
    expect(clientSupportsStructuredContent('')).toBe(false);
  });
});

describe('rehydrateContentForLegacyClients', () => {
  it('rehydrates the exact placeholder back to the full structuredContent JSON for a legacy version', () => {
    const body = singleResult(
      [{ type: 'text', text: PLACEHOLDER }],
      { ontology: { kinds: ['character', 'place'] } },
    );
    const out = rehydrateContentForLegacyClients(body, '2024-11-05');
    const parsed = JSON.parse(out);
    expect(parsed.result.content[0].text).toBe(JSON.stringify({ ontology: { kinds: ['character', 'place'] } }));
    expect(parsed.result.structuredContent).toEqual({ ontology: { kinds: ['character', 'place'] } });
  });

  it('is a no-op for a client that negotiated 2025-06-18+', () => {
    const body = singleResult([{ type: 'text', text: PLACEHOLDER }], { a: 1 });
    const out = rehydrateContentForLegacyClients(body, '2025-06-18');
    expect(out).toBe(body); // untouched, same string
  });

  it('rehydrates when no protocol version header was sent (conservative default: unknown = legacy)', () => {
    const body = singleResult([{ type: 'text', text: PLACEHOLDER }], { a: 1 });
    const out = rehydrateContentForLegacyClients(body, undefined);
    expect(JSON.parse(out).result.content[0].text).toBe(JSON.stringify({ a: 1 }));
  });

  it('never touches content that is not our exact known placeholder', () => {
    const body = singleResult([{ type: 'text', text: 'some genuinely custom handler text' }], { a: 1 });
    const out = rehydrateContentForLegacyClients(body, '2024-11-05');
    expect(out).toBe(body); // untouched
  });

  it('never touches a response with no structuredContent at all', () => {
    const body = JSON.stringify({
      jsonrpc: '2.0',
      id: 1,
      result: { content: [{ type: 'text', text: 'plain result, no schema' }] },
    });
    const out = rehydrateContentForLegacyClients(body, '2024-11-05');
    expect(out).toBe(body);
  });

  it('leaves non-JSON bodies (e.g. SSE) completely untouched', () => {
    const sse = 'data: {"not":"real json-rpc"}\n\n';
    expect(rehydrateContentForLegacyClients(sse, '2024-11-05')).toBe(sse);
  });

  it('rehydrates every matching item in a JSON-RPC batch, independently', () => {
    const batch = JSON.stringify([
      { jsonrpc: '2.0', id: 1, result: { content: [{ type: 'text', text: PLACEHOLDER }], structuredContent: { a: 1 } } },
      { jsonrpc: '2.0', id: 2, result: { content: [{ type: 'text', text: 'untouched custom text' }] } },
    ]);
    const out = rehydrateContentForLegacyClients(batch, '2024-11-05');
    const parsed = JSON.parse(out);
    expect(parsed[0].result.content[0].text).toBe(JSON.stringify({ a: 1 }));
    expect(parsed[1].result.content[0].text).toBe('untouched custom text');
  });

  it('is a no-op for an error response (no result field)', () => {
    const body = JSON.stringify({ jsonrpc: '2.0', id: 1, error: { code: -32601, message: 'x' } });
    expect(rehydrateContentForLegacyClients(body, '2024-11-05')).toBe(body);
  });
});

import { buildEnvelopeHeaders } from '../src/federation/federation.service.js';

// The downstream-header forwarding contract for the /mcp surface. Pulled out of
// executeTool so the actual header writes are unit-tested (a deleted forward line
// now fails a test, instead of only being implied by the carry-to-executeTool test).

describe('buildEnvelopeHeaders', () => {
  it('always sets the synthesized X-Internal-Token', () => {
    const h = buildEnvelopeHeaders('itok', {});
    expect(h['X-Internal-Token']).toBe('itok');
  });

  it('forwards every present envelope field, including X-Mcp-Key-Id (H-C) + X-Mcp-Spend-Cap-Usd (H-K)', () => {
    const h = buildEnvelopeHeaders('itok', {
      userId: 'u1',
      sessionId: 's1',
      traceId: 't1',
      projectId: 'proj-9',
      mcpKeyId: 'key-xyz',
      spendCapUsd: '5',
    });
    expect(h).toEqual({
      'X-Internal-Token': 'itok',
      'X-User-Id': 'u1',
      'X-Session-Id': 's1',
      'X-Trace-Id': 't1',
      'X-Project-Id': 'proj-9',
      'X-Mcp-Key-Id': 'key-xyz',
      'X-Mcp-Spend-Cap-Usd': '5',
    });
  });

  it('omits each absent field — never forwards an empty string', () => {
    const h = buildEnvelopeHeaders('itok', { userId: 'u1' });
    expect(h['X-User-Id']).toBe('u1');
    expect('X-Mcp-Key-Id' in h).toBe(false);
    expect('X-Mcp-Spend-Cap-Usd' in h).toBe(false);
    expect('X-Project-Id' in h).toBe(false);
    expect('X-Session-Id' in h).toBe(false);
    expect('X-Trace-Id' in h).toBe(false);
  });

  it('forwards X-Mcp-Spend-Cap-Usd only when the key carries a cap (H-K)', () => {
    // A public key with no cap → header absent (owner guardrail only).
    expect('X-Mcp-Spend-Cap-Usd' in buildEnvelopeHeaders('itok', { userId: 'u1', mcpKeyId: 'k1' })).toBe(false);
    expect(
      buildEnvelopeHeaders('itok', { userId: 'u1', mcpKeyId: 'k1', spendCapUsd: '2.5' })['X-Mcp-Spend-Cap-Usd'],
    ).toBe('2.5');
  });

  it('forwards X-Mcp-Key-Id independently of X-User-Id presence', () => {
    // A first-party call has a user but no key id; a public call has both.
    expect('X-Mcp-Key-Id' in buildEnvelopeHeaders('itok', { userId: 'u1' })).toBe(false);
    expect(buildEnvelopeHeaders('itok', { userId: 'u1', mcpKeyId: 'k1' })['X-Mcp-Key-Id']).toBe('k1');
  });
});

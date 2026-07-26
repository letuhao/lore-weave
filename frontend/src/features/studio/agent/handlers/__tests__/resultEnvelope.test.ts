import { describe, expect, it } from 'vitest';
import { unwrapToolResult } from '../resultEnvelope';

describe('unwrapToolResult (M-E live-stream envelope class)', () => {
  it('unwraps an object payload nested under .result', () => {
    expect(unwrapToolResult({ ok: true, result: { entity_id: 'e1' } })).toEqual({ entity_id: 'e1' });
  });

  it('unwraps a JSON-STRING payload nested under .result (MCP text content)', () => {
    expect(unwrapToolResult({ ok: true, result: JSON.stringify({ entity_id: 'e1' }) })).toEqual({ entity_id: 'e1' });
  });

  it('a non-JSON string .result → null, no throw', () => {
    expect(unwrapToolResult({ ok: true, result: 'plain text outcome' })).toBeNull();
  });

  it('no .result field at all → null', () => {
    expect(unwrapToolResult({ ok: true })).toBeNull();
  });

  it('a non-object top-level result → null', () => {
    expect(unwrapToolResult('just a string')).toBeNull();
    expect(unwrapToolResult(null)).toBeNull();
  });
});

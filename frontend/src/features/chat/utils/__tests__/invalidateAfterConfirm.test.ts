import { describe, it, expect, vi } from 'vitest';
import type { QueryClient } from '@tanstack/react-query';
import { invalidateAfterConfirm } from '../invalidateAfterConfirm';

// bug #41 — verify the domain → query-key-prefix routing that refreshes the viewing
// page after an agent commit. We capture the predicate handed to invalidateQueries and
// run it against synthetic query keys (react-query prefix-matches on the first element).
function fakeClient() {
  const invalidateQueries = vi.fn();
  return { client: { invalidateQueries } as unknown as QueryClient, invalidateQueries };
}
const predicateOf = (fn: ReturnType<typeof vi.fn>) =>
  fn.mock.calls[0][0].predicate as (q: { queryKey: unknown[] }) => boolean;
const hits = (pred: (q: { queryKey: unknown[] }) => boolean, key: unknown[]) => pred({ queryKey: key });

describe('invalidateAfterConfirm', () => {
  it('kg domain invalidates every kg-* and knowledge-* read, not glossary', () => {
    const { client, invalidateQueries } = fakeClient();
    invalidateAfterConfirm(client, 'kg');
    const pred = predicateOf(invalidateQueries);
    expect(hits(pred, ['kg-graph-schemas'])).toBe(true);
    expect(hits(pred, ['kg-resolved-schema', 'proj-1'])).toBe(true);
    // distinct roots like knowledge-subgraph/-timeline are NOT under ['knowledge'] —
    // the first-element string-prefix rule still catches them.
    expect(hits(pred, ['knowledge-subgraph', 'proj-1'])).toBe(true);
    expect(hits(pred, ['knowledge-timeline', 'proj-1'])).toBe(true);
    expect(hits(pred, ['glossary-entities', 'book-1'])).toBe(false);
  });

  it('glossary domain invalidates glossary-* and the KG-anchored mirror, not the schema', () => {
    const { client, invalidateQueries } = fakeClient();
    invalidateAfterConfirm(client, 'glossary');
    const pred = predicateOf(invalidateQueries);
    expect(hits(pred, ['glossary-entities', 'book-1'])).toBe(true);
    expect(hits(pred, ['glossary-kinds'])).toBe(true);
    expect(hits(pred, ['kg-anchored-glossary-entity', 'e1'])).toBe(true);
    expect(hits(pred, ['kg-graph-schemas'])).toBe(false);
  });

  it('a batch invalidates the UNION of committed domains in ONE call', () => {
    const { client, invalidateQueries } = fakeClient();
    invalidateAfterConfirm(client, ['kg', 'glossary']);
    expect(invalidateQueries).toHaveBeenCalledTimes(1);
    const pred = predicateOf(invalidateQueries);
    expect(hits(pred, ['kg-graph-schemas'])).toBe(true);
    expect(hits(pred, ['glossary-entities', 'b'])).toBe(true);
  });

  it('an unknown domain is a no-op (never invalidates everything)', () => {
    const { client, invalidateQueries } = fakeClient();
    invalidateAfterConfirm(client, 'made-up-domain');
    expect(invalidateQueries).not.toHaveBeenCalled();
  });
});

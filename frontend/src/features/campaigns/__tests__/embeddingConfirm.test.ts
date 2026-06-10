import { describe, it, expect } from 'vitest';
import { needsEmbeddingConfirm } from '../types';

const EMB_A = 'aaaa1111-1111-1111-1111-111111111111';
const EMB_B = 'bbbb2222-2222-2222-2222-222222222222';

describe('needsEmbeddingConfirm (the destructive embedding-override gate)', () => {
  it('false when no embedding picked', () => {
    expect(needsEmbeddingConfirm({ embedding_model: EMB_A, extraction_status: 'ready' }, null)).toBe(false);
  });

  it('false when the project is fresh (no graph) — set freely', () => {
    // extraction_status 'disabled' = no vector space yet → no destructive change.
    expect(needsEmbeddingConfirm({ embedding_model: null, extraction_status: 'disabled' }, EMB_B)).toBe(false);
  });

  it('false when the pick matches the project model (no-op)', () => {
    expect(needsEmbeddingConfirm({ embedding_model: EMB_A, extraction_status: 'ready' }, EMB_A)).toBe(false);
  });

  it('TRUE when the project has a graph and the pick differs (destructive)', () => {
    // This is the case that MUST surface the confirm box — else launch 409s with no
    // visible way to confirm.
    expect(needsEmbeddingConfirm({ embedding_model: EMB_A, extraction_status: 'ready' }, EMB_B)).toBe(true);
  });

  it('false when the project is not loaded yet (undefined)', () => {
    expect(needsEmbeddingConfirm(undefined, EMB_B)).toBe(false);
  });
});

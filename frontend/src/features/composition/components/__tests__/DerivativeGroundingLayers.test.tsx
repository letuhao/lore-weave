import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';

vi.mock('../../../knowledge/api', () => ({
  knowledgeApi: {
    listEntities: vi.fn().mockResolvedValue({
      entities: [
        { id: 'e-zrc', name: '张若尘', kind: 'person' },
        { id: 'e-base', name: '林妃', kind: 'person' },
      ],
      total: 2,
    }),
  },
}));
vi.mock('../../../books/api', () => ({
  booksApi: {
    listChapters: vi.fn().mockResolvedValue({
      items: [
        { chapter_id: 'c0', sort_order: 0, title: 'Ch 1', original_filename: 'c0', lifecycle_state: 'active' },
        { chapter_id: 'c1', sort_order: 1, title: 'Ch 2', original_filename: 'c1', lifecycle_state: 'active' },
        { chapter_id: 'c2', sort_order: 2, title: 'Ch 3', original_filename: 'c2', lifecycle_state: 'active' },
      ],
      total: 3,
    }),
  },
}));

import { DerivativeGroundingLayers } from '../DerivativeGroundingLayers';
import type { DerivativeContext } from '../../hooks/useDerivativeContext';
import { classifyGroundingLayer } from '../../hooks/useDerivativeContext';

function makeCtx(overrideIds: string[], branchPoint: number | null): DerivativeContext {
  const set = new Set(overrideIds);
  return {
    isDerivative: true, sourceWorkId: 'sw', branchPoint, sourceProjectId: 'src',
    overrideIds: set, classify: (id) => classifyGroundingLayer(id, set),
  };
}

function renderLayers(ctx: DerivativeContext) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return render(
    <Wrapper>
      <DerivativeGroundingLayers ctx={ctx} sourceProjectId="src" bookId="book-1" token="tok" />
    </Wrapper>,
  );
}

describe('DerivativeGroundingLayers (DPS2 — 2-layer badges + read-only spine)', () => {
  it('labels an OVERRIDDEN entity OVERRIDDEN and a base entity INHERITED (real state)', async () => {
    renderLayers(makeCtx(['e-zrc'], 2));
    await waitFor(() => expect(screen.getByTestId('derivative-layer-entity-e-zrc')).toBeTruthy());
    // 张若尘 was overridden → its row carries the overridden badge, NEVER inherited
    const zrcRow = screen.getByTestId('derivative-layer-entity-e-zrc');
    expect(zrcRow.querySelector('[data-layer="overridden"]')).toBeTruthy();
    expect(zrcRow.querySelector('[data-layer="inherited"]')).toBeNull();
    // 林妃 was not overridden → inherited
    const baseRow = screen.getByTestId('derivative-layer-entity-e-base');
    expect(baseRow.querySelector('[data-layer="inherited"]')).toBeTruthy();
    expect(screen.getByTestId('grounding-layer-legend')).toBeTruthy();
  });

  it('surfaces the reference spine READ-ONLY (chapters ≤ branch point) with NO auto-insert affordance', async () => {
    renderLayers(makeCtx([], 1));
    // wait for the chapter rows to load (the booksApi query resolves async)
    await waitFor(() => expect(screen.getByTestId('reference-spine-chapter-c0')).toBeTruthy());
    // branch_point=1 → only chapters with sort_order ≤ 1 (c0, c1), not c2
    expect(screen.getByTestId('reference-spine-chapter-c0')).toBeTruthy();
    expect(screen.getByTestId('reference-spine-chapter-c1')).toBeTruthy();
    expect(screen.queryByTestId('reference-spine-chapter-c2')).toBeNull();
    // LOCKED: read-only — no "insert into draft" affordance, only an Open link.
    const spine = screen.getByTestId('derivative-reference-spine');
    expect(spine.textContent?.toLowerCase()).not.toContain('insert');
    expect(spine.querySelector('button')).toBeNull();
  });
});

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';

vi.mock('../../../knowledge/api', () => ({
  knowledgeApi: {
    listEntities: vi.fn().mockResolvedValue({
      entities: [
        // WS-B2: classify keys on glossary_entity_id (the anchor), NOT the node id.
        { id: 'e-zrc', name: '张若尘', kind: 'person', glossary_entity_id: 'g-zrc' },
        { id: 'e-base', name: '林妃', kind: 'person', glossary_entity_id: 'g-base' },
        { id: 'e-unanchored', name: '路人', kind: 'person', glossary_entity_id: null },
      ],
      total: 3,
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

function makeCtx(
  overrideIds: string[],
  branchPoint: number | null,
  overrides: Record<string, Record<string, unknown>> = {},
): DerivativeContext {
  const set = new Set(overrideIds);
  return {
    isDerivative: true, sourceWorkId: 'sw', branchPoint, sourceProjectId: 'src',
    overrideIds: set, overrides, taxonomy: null, povAnchor: null, canonRules: [],
    classify: (id) => classifyGroundingLayer(id, set), isLoading: false,
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

beforeEach(() => vi.clearAllMocks());

describe('DerivativeGroundingLayers (DPS2 — 2-layer badges + read-only spine)', () => {
  it('labels an OVERRIDDEN entity (by glossary anchor) OVERRIDDEN and a base entity INHERITED', async () => {
    renderLayers(makeCtx(['g-zrc'], 2, { 'g-zrc': { description: 'now a woman' } }));
    await waitFor(() => expect(screen.getByTestId('derivative-layer-entity-e-zrc')).toBeTruthy());
    // 张若尘 overridden via its glossary anchor g-zrc → overridden badge, never inherited
    const zrcRow = screen.getByTestId('derivative-layer-entity-e-zrc');
    expect(zrcRow.querySelector('[data-layer="overridden"]')).toBeTruthy();
    expect(zrcRow.querySelector('[data-layer="inherited"]')).toBeNull();
    // B2b — the durable "now" delta renders on the overridden row
    expect(screen.getByTestId('derivative-layer-delta-e-zrc').textContent).toContain('now a woman');
    // 林妃 not overridden → inherited
    expect(screen.getByTestId('derivative-layer-entity-e-base').querySelector('[data-layer="inherited"]')).toBeTruthy();
    // an UNANCHORED entity (no glossary id) can never be overridden → inherited
    expect(screen.getByTestId('derivative-layer-entity-e-unanchored').querySelector('[data-layer="inherited"]')).toBeTruthy();
    expect(screen.getByTestId('grounding-layer-legend')).toBeTruthy();
  });

  it('surfaces the reference spine READ-ONLY (chapters ≤ branch point) with NO auto-insert affordance', async () => {
    renderLayers(makeCtx([], 1));
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

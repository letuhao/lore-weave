import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';

// C9 (C9-promote-flow) — entity-detail panel: facts (provenance MVP),
// promote (discovered → glossary draft + anchor), unpin
// (is_pinned_for_context toggle), and the promote-button gating.

vi.mock('@/auth', () => ({
  useAuth: () => ({
    accessToken: 'tok',
    user: { user_id: 'u1', email: 'a@b', display_name: null, avatar_url: null },
  }),
}));

const toastMocks = vi.hoisted(() => ({
  success: vi.fn(),
  error: vi.fn(),
  info: vi.fn(),
}));
vi.mock('sonner', () => ({ toast: toastMocks }));

const useEntityDetailMock = vi.fn();
vi.mock('../../hooks/useEntityDetail', () => ({
  useEntityDetail: () => useEntityDetailMock(),
}));

const useEntityFactsMock = vi.fn();
const createFactMock = vi.fn();
const invalidateFactMock = vi.fn();
vi.mock('../../hooks/useEntityFacts', () => ({
  useEntityFacts: () => useEntityFactsMock(),
  // S-05 — the author + invalidate mutations the panel now consumes.
  useCreateEntityFact: (
    _entityId: string | null,
    opts?: { onSuccess?: () => void; onError?: (e: Error) => void },
  ) => ({
    create: (...args: unknown[]) => {
      const p = createFactMock(...args);
      return Promise.resolve(p)
        .then((r) => { opts?.onSuccess?.(); return r; })
        .catch((e) => { opts?.onError?.(e as Error); throw e; });
    },
    isPending: false,
  }),
  useInvalidateFact: (
    _entityId: string | null,
    opts?: { onSuccess?: () => void; onError?: (e: Error) => void },
  ) => ({
    invalidate: (...args: unknown[]) => {
      const p = invalidateFactMock(...args);
      return Promise.resolve(p)
        .then((r) => { opts?.onSuccess?.(); return r; })
        .catch((e) => { opts?.onError?.(e as Error); throw e; });
    },
    isPending: false,
  }),
}));

const promoteEntityMock = vi.fn();
const setGlossaryEntityPinnedMock = vi.fn();
const unlockEntityMock = vi.fn();
vi.mock('../../api', async () => {
  const actual = await vi.importActual<Record<string, unknown>>('../../api');
  return {
    ...actual,
    knowledgeApi: {
      unlockEntity: (...args: unknown[]) => unlockEntityMock(...args),
      promoteEntity: (...args: unknown[]) => promoteEntityMock(...args),
      setGlossaryEntityPinned: (...args: unknown[]) =>
        setGlossaryEntityPinnedMock(...args),
    },
  };
});

vi.mock('../EntityEditDialog', () => ({
  EntityEditDialog: () => <div data-testid="entity-edit-dialog-stub" />,
}));
vi.mock('../EntityMergeDialog', () => ({
  EntityMergeDialog: () => <div data-testid="entity-merge-dialog-stub" />,
}));

import { EntityDetailPanel } from '../EntityDetailPanel';

function Wrapper({ children }: PropsWithChildren) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

const BASE_ENTITY = {
  id: 'ent-1',
  user_id: 'u1',
  project_id: 'p-1',
  name: 'Zhang Ruochen',
  canonical_name: 'zhang ruochen',
  kind: 'character',
  aliases: ['Zhang Ruochen'],
  canonical_version: 1,
  source_types: ['chapter'],
  confidence: 0.9,
  glossary_entity_id: null as string | null,
  anchor_score: 0,
  archived_at: null as string | null,
  archive_reason: null,
  evidence_count: 0,
  mention_count: 42,
  user_edited: false,
  version: 5,
  created_at: null,
  updated_at: null,
  status: 'discovered' as 'discovered' | 'canonical' | 'archived',
};

function setDetail(overrides: Partial<typeof BASE_ENTITY> = {}) {
  useEntityDetailMock.mockReturnValue({
    detail: {
      entity: { ...BASE_ENTITY, ...overrides },
      relations: [],
      relations_truncated: false,
      total_relations: 0,
    },
    isLoading: false,
    error: null,
  });
}

function setFacts(facts: unknown[] = []) {
  useEntityFactsMock.mockReturnValue({
    facts,
    windowAvailable: true,
    isLoading: false,
    error: null,
  });
}

describe('EntityDetailPanel — C9 promote / facts / unpin', () => {
  beforeEach(() => {
    promoteEntityMock.mockReset();
    setGlossaryEntityPinnedMock.mockReset();
    unlockEntityMock.mockReset();
    toastMocks.success.mockReset();
    toastMocks.error.mockReset();
    useEntityDetailMock.mockReset();
    useEntityFactsMock.mockReset();
    createFactMock.mockReset();
    invalidateFactMock.mockReset();
    setFacts([]);
  });

  // ── promote gating ──────────────────────────────────────────────────

  it('shows Promote ONLY for a discovered entity', () => {
    setDetail({ status: 'discovered' });
    render(
      <EntityDetailPanel open onOpenChange={vi.fn()} entityId="ent-1" />,
      { wrapper: Wrapper },
    );
    expect(screen.getByTestId('entity-detail-promote')).toBeInTheDocument();
  });

  it('hides Promote for a canonical entity', () => {
    setDetail({
      status: 'canonical',
      glossary_entity_id: 'g-1',
      anchor_score: 1,
    });
    render(
      <EntityDetailPanel open onOpenChange={vi.fn()} entityId="ent-1" bookId="b-1" />,
      { wrapper: Wrapper },
    );
    expect(
      screen.queryByTestId('entity-detail-promote'),
    ).not.toBeInTheDocument();
  });

  it('hides Promote for an archived entity', () => {
    setDetail({ status: 'archived', archived_at: '2026-01-01T00:00:00Z' });
    render(
      <EntityDetailPanel open onOpenChange={vi.fn()} entityId="ent-1" />,
      { wrapper: Wrapper },
    );
    expect(
      screen.queryByTestId('entity-detail-promote'),
    ).not.toBeInTheDocument();
  });

  it('clicking Promote fires promoteEntity + toasts success', async () => {
    setDetail({ status: 'discovered' });
    promoteEntityMock.mockResolvedValue({
      ...BASE_ENTITY,
      status: 'canonical',
      glossary_entity_id: 'g-9',
      anchor_score: 1,
    });
    render(
      <EntityDetailPanel open onOpenChange={vi.fn()} entityId="ent-1" />,
      { wrapper: Wrapper },
    );
    fireEvent.click(screen.getByTestId('entity-detail-promote'));
    await waitFor(() => {
      expect(promoteEntityMock).toHaveBeenCalledWith('ent-1', 'tok');
    });
    await waitFor(() => {
      expect(toastMocks.success).toHaveBeenCalledTimes(1);
    });
  });

  it('promote failure toasts the error (no crash)', async () => {
    setDetail({ status: 'discovered' });
    promoteEntityMock.mockRejectedValue(new Error('glossary down'));
    render(
      <EntityDetailPanel open onOpenChange={vi.fn()} entityId="ent-1" />,
      { wrapper: Wrapper },
    );
    fireEvent.click(screen.getByTestId('entity-detail-promote'));
    await waitFor(() => {
      expect(toastMocks.error).toHaveBeenCalledTimes(1);
    });
  });

  // ── unpin (is_pinned_for_context) ───────────────────────────────────

  it('shows Unpin for a canonical entity with a glossary anchor + book', () => {
    setDetail({
      status: 'canonical',
      glossary_entity_id: 'g-1',
      anchor_score: 1,
    });
    render(
      <EntityDetailPanel open onOpenChange={vi.fn()} entityId="ent-1" bookId="b-1" />,
      { wrapper: Wrapper },
    );
    expect(screen.getByTestId('entity-detail-unpin')).toBeInTheDocument();
  });

  it('hides Unpin when no book is in scope', () => {
    setDetail({
      status: 'canonical',
      glossary_entity_id: 'g-1',
      anchor_score: 1,
    });
    render(
      <EntityDetailPanel open onOpenChange={vi.fn()} entityId="ent-1" />,
      { wrapper: Wrapper },
    );
    expect(
      screen.queryByTestId('entity-detail-unpin'),
    ).not.toBeInTheDocument();
  });

  it('clicking Unpin toggles is_pinned_for_context to false on the glossary entity', async () => {
    setDetail({
      status: 'canonical',
      glossary_entity_id: 'g-1',
      anchor_score: 1,
    });
    setGlossaryEntityPinnedMock.mockResolvedValue(undefined);
    render(
      <EntityDetailPanel open onOpenChange={vi.fn()} entityId="ent-1" bookId="b-1" />,
      { wrapper: Wrapper },
    );
    fireEvent.click(screen.getByTestId('entity-detail-unpin'));
    await waitFor(() => {
      // bookId, glossaryEntityId, pinned=false, token
      expect(setGlossaryEntityPinnedMock).toHaveBeenCalledWith(
        'b-1',
        'g-1',
        false,
        'tok',
      );
    });
    await waitFor(() => {
      expect(toastMocks.success).toHaveBeenCalledTimes(1);
    });
  });

  // ── facts (provenance MVP) ──────────────────────────────────────────

  it('renders the facts list with source_chapter', () => {
    setDetail({ status: 'discovered' });
    setFacts([
      {
        id: 'f-1',
        type: 'decision',
        content: 'Vowed revenge on the Nine Cauldrons.',
        confidence: 0.95,
        source_chapter: '12',
        from_order: 12,
      },
    ]);
    render(
      <EntityDetailPanel open onOpenChange={vi.fn()} entityId="ent-1" />,
      { wrapper: Wrapper },
    );
    expect(screen.getByTestId('entity-detail-facts')).toBeInTheDocument();
    expect(screen.getByTestId('entity-detail-fact')).toBeInTheDocument();
    expect(
      screen.getByText('Vowed revenge on the Nine Cauldrons.'),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId('entity-detail-fact-source'),
    ).toBeInTheDocument();
  });

  // S-05 — the section now ALWAYS renders (so an empty entity can still author).
  // Only the fact LIST rows are hidden when there are none; the "Add fact" CTA stays.
  it('keeps the facts section + Add-fact CTA even with zero facts (no empty-shell)', () => {
    setDetail({ status: 'discovered' });
    setFacts([]);
    render(
      <EntityDetailPanel open onOpenChange={vi.fn()} entityId="ent-1" />,
      { wrapper: Wrapper },
    );
    expect(screen.getByTestId('entity-detail-facts')).toBeInTheDocument();
    expect(screen.getByTestId('entity-detail-add-fact')).toBeInTheDocument();
    // no fact rows when the list is empty
    expect(screen.queryByTestId('entity-detail-fact')).not.toBeInTheDocument();
  });

  // ── S-05 author + invalidate ─────────────────────────────────────────

  it('authors a fact: opens form, offers all 6 types, POSTs, toasts success', async () => {
    setDetail({ status: 'discovered' });
    setFacts([]);
    createFactMock.mockResolvedValue({ id: 'f-new', type: 'statement' });
    render(
      <EntityDetailPanel open onOpenChange={vi.fn()} entityId="ent-1" />,
      { wrapper: Wrapper },
    );
    fireEvent.click(screen.getByTestId('entity-detail-add-fact'));
    const typeSelect = screen.getByTestId(
      'entity-detail-add-fact-type',
    ) as HTMLSelectElement;
    // all 6 FactType values are offered (the 4-vs-6 label drift is closed)
    expect(typeSelect.querySelectorAll('option')).toHaveLength(6);
    fireEvent.change(typeSelect, { target: { value: 'commitment' } });
    fireEvent.change(screen.getByTestId('entity-detail-add-fact-content'), {
      target: { value: 'Swears fealty to the Queen.' },
    });
    fireEvent.click(screen.getByTestId('entity-detail-add-fact-save'));
    await waitFor(() => expect(createFactMock).toHaveBeenCalledTimes(1));
    expect(createFactMock).toHaveBeenCalledWith({
      fact_type: 'commitment',
      content: 'Swears fealty to the Queen.',
      predicate: null,
      object: null,
    });
    await waitFor(() => expect(toastMocks.success).toHaveBeenCalled());
  });

  it('renders a statement fact without crashing (6-vs-4 label closed)', () => {
    // Pre-fix, FACT_TYPE_LABEL['statement'] was undefined → t(undefined). The map
    // now covers all 6, so a statement fact renders its row + content cleanly.
    setDetail({ status: 'discovered' });
    setFacts([
      {
        id: 'f-s',
        type: 'statement',
        content: 'Is the last heir of House Vaeth.',
        confidence: 1,
        source_chapter: null,
        from_order: null,
      },
    ]);
    render(
      <EntityDetailPanel open onOpenChange={vi.fn()} entityId="ent-1" />,
      { wrapper: Wrapper },
    );
    expect(screen.getByTestId('entity-detail-fact')).toBeInTheDocument();
    expect(
      screen.getByText('Is the last heir of House Vaeth.'),
    ).toBeInTheDocument();
    // the label span resolves to the statement key (not undefined / blank)
    expect(
      screen.getByText('entities.detail.factType.statement'),
    ).toBeInTheDocument();
  });

  it('marks a fact wrong: confirms then invalidates + toasts', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    setDetail({ status: 'discovered' });
    setFacts([
      {
        id: 'f-1',
        type: 'decision',
        content: 'Vowed revenge.',
        confidence: 0.95,
        source_chapter: null,
        from_order: null,
      },
    ]);
    invalidateFactMock.mockResolvedValue({ id: 'f-1' });
    render(
      <EntityDetailPanel open onOpenChange={vi.fn()} entityId="ent-1" />,
      { wrapper: Wrapper },
    );
    fireEvent.click(screen.getByTestId('entity-detail-fact-mark-wrong'));
    await waitFor(() =>
      expect(invalidateFactMock).toHaveBeenCalledWith('f-1'),
    );
    await waitFor(() => expect(toastMocks.success).toHaveBeenCalled());
    confirmSpy.mockRestore();
  });
});

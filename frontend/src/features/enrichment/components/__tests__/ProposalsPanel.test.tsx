import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// ── mock the data + actions hooks the panel owns (isolate from react-query/api) ──
const proposalsStub = vi.hoisted(() => ({
  current: {
    items: [] as unknown[],
    isLoading: false,
    isError: false,
    projectIds: [] as string[],
  },
}));
vi.mock('../../hooks/useProposals', () => ({
  useProposals: () => proposalsStub.current,
}));

const actionsStub = vi.hoisted(() => ({
  busy: false,
  approve: vi.fn(),
  reject: vi.fn(),
  edit: vi.fn(),
  promote: vi.fn(),
  retract: vi.fn(),
}));
vi.mock('../../hooks/useProposalActions', () => ({
  useProposalActions: () => actionsStub,
}));

import { ProposalsPanel } from '../ProposalsPanel';
import { EnrichmentProvider } from '../../context/EnrichmentContext';
import type { Proposal } from '../../types';

// Cast a partial — only the fields the panel + ProposalDetail read matter.
const P = (over: Partial<Proposal> = {}): Proposal =>
  ({
    proposal_id: 'p-1',
    project_id: 'proj-9',
    review_status: 'proposed',
    canonical_name: '玉虛宮',
    target_ref: null,
    content: 'a temple of the jade void',
    technique: 'recook', // P3
    confidence: 0.3,
    origin: 'enrichment',
    provenance_json: {},
    source_refs_json: [],
    ...over,
  } as Proposal);

// recook -> P3, retrieval -> P1 (two distinct tiers, per tierOf)
const PROP_RECOOK = P({
  proposal_id: 'p-recook',
  canonical_name: '玉虛宮',
  technique: 'recook',
  content: 'jade void palace',
});
const PROP_RETRIEVAL = P({
  proposal_id: 'p-retrieval',
  canonical_name: 'Nezha',
  technique: 'retrieval',
  content: 'a lotus-born warrior',
});

function setStub(over: Partial<typeof proposalsStub.current>) {
  proposalsStub.current = { items: [], isLoading: false, isError: false, projectIds: [], ...over };
}

function renderPanel() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <EnrichmentProvider bookId="book-1">
        <ProposalsPanel />
      </EnrichmentProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  setStub({});
  vi.clearAllMocks();
});

describe('ProposalsPanel', () => {
  it('loading with no items: renders the Skeleton placeholder, not the workspace or error', () => {
    setStub({ isLoading: true, items: [] });
    const { container } = renderPanel();
    expect(screen.queryByTestId('enrichment-proposals')).toBeNull();
    expect(screen.queryByTestId('enrichment-proposals-error')).toBeNull();
    // Skeletons are the only thing rendered in this branch.
    expect(container.querySelector('.space-y-3')).toBeInTheDocument();
  });

  it('isError: renders the error alert with role=alert + the proposals.error key', () => {
    setStub({ isError: true, items: [] });
    renderPanel();
    const err = screen.getByTestId('enrichment-proposals-error');
    expect(err).toBeInTheDocument();
    expect(err).toHaveAttribute('role', 'alert');
    expect(screen.getByText('proposals.error')).toBeInTheDocument();
    expect(screen.queryByTestId('enrichment-proposals')).toBeNull();
  });

  it('items resolve: renders the workspace + a ProposalDetail for the first proposal', () => {
    setStub({
      items: [PROP_RECOOK, PROP_RETRIEVAL],
      projectIds: ['proj-9'],
    });
    renderPanel();
    expect(screen.getByTestId('enrichment-proposals')).toBeInTheDocument();
    // Detail is shown for the selected (first) proposal.
    expect(screen.getByTestId('enrichment-detail')).toBeInTheDocument();
    expect(screen.getByTestId('enrichment-detail-name')).toHaveTextContent('玉虛宮');
  });

  it('search narrows the list client-side (selection follows to the surviving match)', () => {
    setStub({
      items: [PROP_RECOOK, PROP_RETRIEVAL],
      projectIds: ['proj-9'],
    });
    renderPanel();
    // Typing "lotus" should drop the recook (jade void) row, leaving the retrieval one.
    fireEvent.change(screen.getByTestId('enrichment-search'), { target: { value: 'lotus' } });
    // The retrieval proposal is now the only match -> it becomes the selected detail.
    expect(screen.getByTestId('enrichment-detail-name')).toHaveTextContent('Nezha');
  });

  it('search with no match: empties the list and shows the empty-detail state', () => {
    setStub({
      items: [PROP_RECOOK, PROP_RETRIEVAL],
      projectIds: ['proj-9'],
    });
    renderPanel();
    fireEvent.change(screen.getByTestId('enrichment-search'), { target: { value: 'zzz-no-hit' } });
    expect(screen.queryByTestId('enrichment-detail')).toBeNull();
    expect(screen.getByText('proposals.empty.title')).toBeInTheDocument();
  });

  it('tier filter narrows by tierOf(technique): selecting P1 keeps the retrieval proposal', () => {
    setStub({
      items: [PROP_RECOOK, PROP_RETRIEVAL],
      projectIds: ['proj-9'],
    });
    renderPanel();
    // Initially the recook (P3) proposal is selected (first in the list).
    expect(screen.getByTestId('enrichment-detail-name')).toHaveTextContent('玉虛宮');
    // Filter to P1 -> only the retrieval proposal (tierOf('retrieval') === 'P1') survives.
    fireEvent.click(screen.getByTestId('enrichment-tier-P1'));
    expect(screen.getByTestId('enrichment-detail-name')).toHaveTextContent('Nezha');
  });

  it('tier filter P3 keeps only the recook proposal', () => {
    setStub({
      items: [PROP_RECOOK, PROP_RETRIEVAL],
      projectIds: ['proj-9'],
    });
    renderPanel();
    fireEvent.click(screen.getByTestId('enrichment-tier-P3'));
    expect(screen.getByTestId('enrichment-detail-name')).toHaveTextContent('玉虛宮');
  });
});

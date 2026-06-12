import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import { ProposalList } from '../ProposalList';
import type { Proposal, ReviewStatus, Tier } from '../../types';

// ProposalList is a pure-props component. ProposalCard (its child) reads real
// fields (canonical_name, confidence.toFixed, provenance_json, source_refs_json),
// so fixtures carry those. react-i18next is mocked globally (vitest.setup.ts):
// t('a.b') returns the dotted key verbatim — assert on KEYS, never English.

const P = (over: Partial<Proposal> = {}): Proposal =>
  ({
    proposal_id: 'p-1',
    project_id: 'proj-9',
    review_status: 'proposed' as ReviewStatus,
    canonical_name: '玉虛宮',
    technique: 'recook',
    content: '...',
    confidence: 0.3,
    origin: 'enrichment',
    provenance_json: {},
    source_refs_json: [],
    ...over,
  } as Proposal);

function setup(over: Partial<Parameters<typeof ProposalList>[0]> = {}) {
  const props = {
    items: [P()],
    selectedId: null as string | null,
    onSelect: vi.fn(),
    search: '',
    onSearch: vi.fn(),
    status: 'all' as ReviewStatus | 'all',
    onStatus: vi.fn(),
    tier: 'all' as Tier | 'all',
    onTier: vi.fn(),
    projectIds: ['proj-9'],
    projectFilter: null as string | null,
    onProjectFilter: vi.fn(),
    ...over,
  };
  render(<ProposalList {...props} />);
  return props;
}

beforeEach(() => vi.clearAllMocks());

describe('ProposalList', () => {
  it('typing in the search input fires onSearch with the new value', () => {
    const p = setup();
    fireEvent.change(screen.getByTestId('enrichment-search'), {
      target: { value: '玉虛' },
    });
    expect(p.onSearch).toHaveBeenCalledWith('玉虛');
  });

  it('the search input reflects the search prop value', () => {
    setup({ search: '太乙' });
    expect(screen.getByTestId('enrichment-search')).toHaveValue('太乙');
  });

  it('renders all 5 status pills and each fires onStatus with its value', () => {
    // Empty items so the ONLY review.<status> text nodes come from the pills
    // (a rendered ProposalCard's ReviewStatusBadge also emits review.<status>).
    const p = setup({ items: [] });
    // 'all' renders proposals.status_all; the rest render review.<status>.
    // NOTE: the tier 'all' pill ALSO renders proposals.status_all, so the status
    // 'all' pill is the one match that is NOT the enrichment-tier-all button.
    const allPill = screen
      .getAllByText('proposals.status_all')
      .find((el) => el.getAttribute('data-testid') !== 'enrichment-tier-all')!;
    fireEvent.click(allPill);
    expect(p.onStatus).toHaveBeenCalledWith('all');

    fireEvent.click(screen.getByText('review.proposed'));
    expect(p.onStatus).toHaveBeenCalledWith('proposed');

    fireEvent.click(screen.getByText('review.approved'));
    expect(p.onStatus).toHaveBeenCalledWith('approved');

    fireEvent.click(screen.getByText('review.promoted'));
    expect(p.onStatus).toHaveBeenCalledWith('promoted');

    fireEvent.click(screen.getByText('review.rejected'));
    expect(p.onStatus).toHaveBeenCalledWith('rejected');
  });

  it('renders the 4 technique tier pills with their testids', () => {
    setup();
    expect(screen.getByTestId('enrichment-tier-all')).toBeInTheDocument();
    expect(screen.getByTestId('enrichment-tier-P1')).toBeInTheDocument();
    expect(screen.getByTestId('enrichment-tier-P2')).toBeInTheDocument();
    expect(screen.getByTestId('enrichment-tier-P3')).toBeInTheDocument();
  });

  it('each tier pill fires onTier with its value', () => {
    const p = setup();
    fireEvent.click(screen.getByTestId('enrichment-tier-all'));
    expect(p.onTier).toHaveBeenCalledWith('all');

    fireEvent.click(screen.getByTestId('enrichment-tier-P1'));
    expect(p.onTier).toHaveBeenCalledWith('P1');

    fireEvent.click(screen.getByTestId('enrichment-tier-P2'));
    expect(p.onTier).toHaveBeenCalledWith('P2');

    fireEvent.click(screen.getByTestId('enrichment-tier-P3'));
    expect(p.onTier).toHaveBeenCalledWith('P3');
  });

  it('does NOT render the project picker row when projectIds has a single id', () => {
    setup({ projectIds: ['proj-9'] });
    expect(screen.queryByText('proposals.project:')).toBeNull();
    expect(screen.queryByText('proposals.all_projects')).toBeNull();
  });

  it('renders the project picker row only when projectIds.length > 1; pills fire onProjectFilter', () => {
    const p = setup({ projectIds: ['proj-aaaaaaaa', 'proj-bbbbbbbb'] });
    // "All projects" pill resets filter to null
    fireEvent.click(screen.getByText('proposals.all_projects'));
    expect(p.onProjectFilter).toHaveBeenCalledWith(null);

    // per-project pill shows the first 8 chars of the id and forwards the full id
    fireEvent.click(screen.getByText('proj-aaa'));
    expect(p.onProjectFilter).toHaveBeenCalledWith('proj-aaaaaaaa');
  });

  it('shows proposals.none when items is empty (no cards rendered)', () => {
    setup({ items: [] });
    expect(screen.getByText('proposals.none')).toBeInTheDocument();
    expect(screen.queryAllByTestId('enrichment-proposal-card')).toHaveLength(0);
  });

  it('renders one ProposalCard per item when items is non-empty', () => {
    setup({
      items: [P({ proposal_id: 'p-1' }), P({ proposal_id: 'p-2' }), P({ proposal_id: 'p-3' })],
    });
    expect(screen.queryByText('proposals.none')).toBeNull();
    expect(screen.getAllByTestId('enrichment-proposal-card')).toHaveLength(3);
  });

  it('marks the card whose proposal_id matches selectedId as selected', () => {
    setup({
      items: [P({ proposal_id: 'p-1' }), P({ proposal_id: 'p-2' })],
      selectedId: 'p-2',
    });
    const cards = screen.getAllByTestId('enrichment-proposal-card');
    // selected card carries the border-l-primary marker class; unselected does not
    expect(cards[0].className).not.toContain('border-l-primary');
    expect(cards[1].className).toContain('border-l-primary');
  });

  it('clicking a card fires onSelect with that proposal_id', () => {
    const p = setup({
      items: [P({ proposal_id: 'p-1' }), P({ proposal_id: 'p-2' })],
    });
    fireEvent.click(screen.getAllByTestId('enrichment-proposal-card')[1]);
    expect(p.onSelect).toHaveBeenCalledWith('p-2');
  });

  it('renders the card content for each item (child wiring)', () => {
    setup({ items: [P({ proposal_id: 'p-1', content: 'a recooked myth fragment' })] });
    const card = screen.getByTestId('enrichment-proposal-card');
    expect(within(card).getByText('a recooked myth fragment')).toBeInTheDocument();
  });
});

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ProposalCard } from '../ProposalCard';
import type { Proposal } from '../../types';

// ProposalCard is a pure-props component: no context, no data hooks, no api calls.
// The badges (./badges) render inline; lucide / radix / shared need no mocking.

const P = (over: Partial<Proposal> = {}): Proposal =>
  ({
    proposal_id: 'p-1',
    project_id: 'proj-9',
    review_status: 'proposed',
    canonical_name: '玉虛宮',
    target_ref: null,
    content: 'a scannable summary line',
    technique: 'recook',
    confidence: 0.42,
    origin: 'enrichment',
    provenance_json: {},
    source_refs_json: [],
    rejected_reason: null,
    ...over,
  } as Proposal);

beforeEach(() => vi.clearAllMocks());

describe('ProposalCard', () => {
  it('name falls back canonical_name -> target_ref -> em dash', () => {
    const { rerender } = render(
      <ProposalCard proposal={P({ canonical_name: '玉虛宮' })} selected={false} onSelect={vi.fn()} />,
    );
    expect(screen.getByText('玉虛宮')).toBeInTheDocument();

    rerender(
      <ProposalCard
        proposal={P({ canonical_name: null, target_ref: 'entity:42' })}
        selected={false}
        onSelect={vi.fn()}
      />,
    );
    expect(screen.getByText('entity:42')).toBeInTheDocument();

    rerender(
      <ProposalCard
        proposal={P({ canonical_name: null, target_ref: null })}
        selected={false}
        onSelect={vi.fn()}
      />,
    );
    expect(screen.getByText('—')).toBeInTheDocument();
  });

  it('renders the TechniqueBadge, VerifyBadge, ReviewStatusBadge and the H0 marker', () => {
    render(
      <ProposalCard
        proposal={P({
          technique: 'recook',
          review_status: 'proposed',
          provenance_json: { verify_status: 'needs_review' },
        })}
        selected={false}
        onSelect={vi.fn()}
      />,
    );
    // TechniqueBadge renders "<tier> · <label>" where label is the i18n KEY (recook -> P3).
    expect(screen.getByText('P3 · technique.recook')).toBeInTheDocument();
    // VerifyBadge keys off provenance_json.verify_status.
    expect(screen.getByText('verify.status.needs_review')).toBeInTheDocument();
    // ReviewStatusBadge keys off review_status.
    expect(screen.getByText('review.proposed')).toBeInTheDocument();
    // H0 marker is always present.
    expect(screen.getByTestId('enrichment-h0-marker')).toBeInTheDocument();
  });

  it('omits the VerifyBadge text when there is no verify_status', () => {
    render(
      <ProposalCard
        proposal={P({ provenance_json: {} })}
        selected={false}
        onSelect={vi.fn()}
      />,
    );
    expect(screen.queryByText('verify.status.needs_review')).toBeNull();
  });

  it('renders the summary line keyed by card.summary', () => {
    render(<ProposalCard proposal={P()} selected={false} onSelect={vi.fn()} />);
    const summary = screen.getByTestId('enrichment-card-summary');
    expect(summary).toBeInTheDocument();
    // Dotted key has no {{x}} tokens, so the i18n mock returns it verbatim.
    expect(summary).toHaveTextContent('card.summary');
  });

  it('shows the advisory preview when not auto_rejected AND canon_verify.flags is non-empty', () => {
    render(
      <ProposalCard
        proposal={P({
          provenance_json: {
            verify_status: 'needs_review',
            canon_verify: {
              passed: false,
              verify_degraded: false,
              flags: [{ kind: 'contradiction', dimension: null, evidence: 'x', severity: 'high' }],
            },
          },
        })}
        selected={false}
        onSelect={vi.fn()}
      />,
    );
    const advisory = screen.getByTestId('enrichment-card-advisory');
    expect(advisory).toBeInTheDocument();
    expect(advisory).toHaveTextContent('card.advisory');
  });

  it('hides the advisory preview when canon_verify.flags is empty', () => {
    render(
      <ProposalCard
        proposal={P({
          provenance_json: {
            verify_status: 'needs_review',
            canon_verify: { passed: true, verify_degraded: false, flags: [] },
          },
        })}
        selected={false}
        onSelect={vi.fn()}
      />,
    );
    expect(screen.queryByTestId('enrichment-card-advisory')).toBeNull();
  });

  it('auto_rejected: dims the card (opacity-70) and shows the reject reason instead of advisory', () => {
    render(
      <ProposalCard
        proposal={P({
          rejected_reason: 'fabricated against canon',
          provenance_json: {
            verify_status: 'auto_rejected',
            // flags present, but auto_rejected suppresses the advisory preview.
            canon_verify: {
              passed: false,
              verify_degraded: false,
              flags: [{ kind: 'regurgitation', dimension: null, evidence: 'y', severity: 'high' }],
            },
          },
        })}
        selected={false}
        onSelect={vi.fn()}
      />,
    );
    const card = screen.getByTestId('enrichment-proposal-card');
    expect(card).toHaveClass('opacity-70');
    const reason = screen.getByTestId('enrichment-card-reject-reason');
    expect(reason).toHaveTextContent('fabricated against canon');
    expect(screen.queryByTestId('enrichment-card-advisory')).toBeNull();
  });

  it('auto_rejected with no rejected_reason falls back to card.auto_rejected', () => {
    render(
      <ProposalCard
        proposal={P({
          rejected_reason: null,
          provenance_json: { verify_status: 'auto_rejected' },
        })}
        selected={false}
        onSelect={vi.fn()}
      />,
    );
    expect(screen.getByTestId('enrichment-card-reject-reason')).toHaveTextContent(
      'card.auto_rejected',
    );
  });

  it('selected applies the border-l-primary highlight', () => {
    const { rerender } = render(
      <ProposalCard proposal={P()} selected={false} onSelect={vi.fn()} />,
    );
    expect(screen.getByTestId('enrichment-proposal-card')).not.toHaveClass('border-l-primary');

    rerender(<ProposalCard proposal={P()} selected={true} onSelect={vi.fn()} />);
    expect(screen.getByTestId('enrichment-proposal-card')).toHaveClass('border-l-primary');
  });

  it('clicking the card calls onSelect', () => {
    const onSelect = vi.fn();
    render(<ProposalCard proposal={P()} selected={false} onSelect={onSelect} />);
    fireEvent.click(screen.getByTestId('enrichment-proposal-card'));
    expect(onSelect).toHaveBeenCalledTimes(1);
  });
});

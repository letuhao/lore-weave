import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import type { Proposal } from '../../types';

// ProvenancePanel now resolves the gen model via react-query + provider-registry;
// it has its own dedicated test, so stub it here to keep this test infra-free.
vi.mock('../ProvenancePanel', () => ({
  ProvenancePanel: () => <div data-testid="enrichment-provenance" />,
}));

import { ProposalDetail } from '../ProposalDetail';

const P = (over: Partial<Proposal> = {}): Proposal =>
  ({
    proposal_id: 'p-1',
    project_id: 'proj-9',
    review_status: 'proposed',
    canonical_name: '玉虛宮',
    target_ref: null,
    technique: 'recook',
    content: 'the original draft text',
    confidence: 0.42,
    origin: 'enrichment',
    provenance_json: {},
    source_refs_json: [],
    ...over,
  } as Proposal);

function makeActions(over: Partial<Record<string, ReturnType<typeof vi.fn>>> = {}) {
  return {
    busy: false,
    approve: vi.fn().mockResolvedValue(undefined),
    reject: vi.fn().mockResolvedValue(undefined),
    edit: vi.fn().mockResolvedValue(undefined),
    promote: vi.fn().mockResolvedValue(undefined),
    retract: vi.fn().mockResolvedValue(undefined),
    ...over,
  };
}

function setup(proposal: Proposal = P(), actionsOver = {}) {
  const actions = makeActions(actionsOver);
  render(<ProposalDetail proposal={proposal} actions={actions} />);
  return actions;
}

beforeEach(() => vi.clearAllMocks());

describe('ProposalDetail', () => {
  it('renders the canonical name in the detail-name header', () => {
    setup(P({ canonical_name: '哪吒' }));
    expect(screen.getByTestId('enrichment-detail-name')).toHaveTextContent('哪吒');
  });

  it('falls back to target_ref, then the untitled key, for the name', () => {
    setup(P({ canonical_name: null, target_ref: 'ref-42' }));
    expect(screen.getByTestId('enrichment-detail-name')).toHaveTextContent('ref-42');
  });

  it('renders the live H0 banner with origin, confidence.toFixed(2) and the review key', () => {
    setup(P({ origin: 'enrichment', confidence: 0.42, review_status: 'proposed' }));
    const banner = screen.getByTestId('enrichment-h0-banner');
    expect(banner).toHaveTextContent('detail.h0_banner');
    expect(banner).toHaveTextContent('origin=enrichment');
    // confidence is rendered via toFixed(2)
    expect(banner).toHaveTextContent('confidence=0.42');
    // review status rendered via the t('review.<status>') key (i18n mock returns the key)
    expect(banner).toHaveTextContent('review.proposed');
  });

  it('shows DimensionList content by default (not a textarea)', () => {
    setup(P({ content: 'the original draft text' }));
    expect(screen.getByText('the original draft text')).toBeInTheDocument();
    expect(screen.queryByRole('textbox')).toBeNull();
  });

  it('Edit swaps DimensionList for a textarea seeded from the proposal content', () => {
    setup(P({ content: 'the original draft text' }));
    fireEvent.click(screen.getByText('actions.edit'));
    const textarea = screen.getByRole('textbox') as HTMLTextAreaElement;
    expect(textarea).toHaveValue('the original draft text');
  });

  it('Save calls actions.edit(proposal, draft) then exits edit mode', async () => {
    const proposal = P({ content: 'the original draft text' });
    const actions = setup(proposal);
    fireEvent.click(screen.getByText('actions.edit'));
    const textarea = screen.getByRole('textbox');
    fireEvent.change(textarea, { target: { value: 'a rewritten draft' } });
    fireEvent.click(screen.getByText('actions.save'));

    expect(actions.edit).toHaveBeenCalledWith(proposal, 'a rewritten draft');
    // await the async onClick (edit -> setEditing(false))
    await screen.findByText('the original draft text');
    expect(screen.queryByRole('textbox')).toBeNull();
  });

  it('Cancel discards the edit, restores content and exits edit mode', () => {
    const proposal = P({ content: 'the original draft text' });
    const actions = setup(proposal);
    fireEvent.click(screen.getByText('actions.edit'));
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'discarded' } });

    // the edit-mode Cancel button (there is only one cancel visible in edit mode)
    fireEvent.click(screen.getByText('actions.cancel'));

    expect(actions.edit).not.toHaveBeenCalled();
    expect(screen.queryByRole('textbox')).toBeNull();
    expect(screen.getByText('the original draft text')).toBeInTheDocument();
  });

  it('Promote opens the PromoteDialog and confirming calls actions.promote(proposal)', async () => {
    const proposal = P({ review_status: 'proposed' });
    const actions = setup(proposal);

    // dialog closed initially
    expect(screen.queryByTestId('enrichment-promote-dialog')).toBeNull();

    fireEvent.click(screen.getByTestId('enrichment-promote-trigger'));
    expect(screen.getByTestId('enrichment-promote-dialog')).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('enrichment-promote-confirm'));
    expect(actions.promote).toHaveBeenCalledWith(proposal);
  });

  it('for a promoted proposal, Retract opens the ConfirmDialog and confirming calls actions.retract(proposal)', async () => {
    const proposal = P({ review_status: 'promoted' });
    const actions = setup(proposal);

    fireEvent.click(screen.getByTestId('enrichment-retract-trigger'));
    // ConfirmDialog content rendered (radix Dialog.Content has role="dialog")
    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByText('actions.retract_confirm_title')).toBeInTheDocument();

    // The destructive confirm button (scoped to the dialog) carries
    // confirmLabel={t('actions.retract')} — the retract-trigger button outside
    // the dialog shares that label, so we must scope the query.
    fireEvent.click(within(dialog).getByText('actions.retract', { selector: 'button' }));
    expect(actions.retract).toHaveBeenCalledWith(proposal);
  });

  it('renders the author_only caption', () => {
    setup();
    expect(screen.getByText('actions.author_only')).toBeInTheDocument();
  });
});

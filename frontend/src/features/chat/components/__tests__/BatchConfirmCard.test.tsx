import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

// #27/#29/#30 — the coalesced "Confirm all" card. It commits a turn's N child tokens
// (glossary via the atomic /confirm-batch; other domains by looping single /confirm) and
// resumes the suspended run ONCE — replacing the N cards that used to orphan each other.

const submitToolResult = vi.fn().mockResolvedValue('');
const confirmActionBatch = vi.fn();
const confirmAction = vi.fn();

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('../../providers', () => ({ useChatStream: () => ({ submitToolResult }) }));
vi.mock('../../actionsApi', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../actionsApi')>();
  return {
    ...actual, // keep the REAL BATCH_CONFIRM_DOMAINS set
    actionsApi: {
      confirmActionBatch: (...a: unknown[]) => confirmActionBatch(...a),
      confirmAction: (...a: unknown[]) => confirmAction(...a),
    },
  };
});

import { BatchConfirmCard, type BatchChild } from '../BatchConfirmCard';

const glossaryChildren: BatchChild[] = [
  { token: 't1', domain: 'glossary', descriptor: 'schema_create_kind', title: 'Create kind A' },
  { token: 't2', domain: 'glossary', descriptor: 'schema_create_kind', title: 'Create kind B' },
];

describe('BatchConfirmCard', () => {
  beforeEach(() => {
    submitToolResult.mockClear();
    confirmActionBatch.mockReset();
    confirmAction.mockReset();
  });

  it('lists every child action in ONE card', () => {
    render(<BatchConfirmCard children={glossaryChildren} />);
    expect(screen.getByTestId('batch-confirm-card')).toBeTruthy();
    expect(screen.getByTestId('batch-confirm-rows').children).toHaveLength(2);
  });

  it('commits a glossary batch in ONE atomic call and resumes the run once', async () => {
    confirmActionBatch.mockResolvedValue({ applied: 2, skipped: 0, failed: 0, children: [] });
    render(<BatchConfirmCard children={glossaryChildren} resume={{ runId: 'r1', toolCallId: 'c1' }} />);
    fireEvent.click(screen.getByText('batchConfirm.confirm_all'));
    // ONE batch call with both tokens (not two single calls)
    await waitFor(() => expect(confirmActionBatch).toHaveBeenCalledWith('glossary', ['t1', 't2'], 'tok'));
    expect(confirmAction).not.toHaveBeenCalled();
    // run resumed exactly once with the aggregate outcome
    await waitFor(() => expect(submitToolResult).toHaveBeenCalledWith('r1', 'c1', 'action_done'));
    expect(submitToolResult).toHaveBeenCalledTimes(1);
  });

  it('loops single /confirm for a domain WITHOUT a batch endpoint', async () => {
    confirmAction.mockResolvedValue({});
    const bookChildren: BatchChild[] = [
      { token: 'b1', domain: 'book', descriptor: 'book.publish', title: 'Publish 1' },
      { token: 'b2', domain: 'book', descriptor: 'book.publish', title: 'Publish 2' },
    ];
    render(<BatchConfirmCard children={bookChildren} />);
    fireEvent.click(screen.getByText('batchConfirm.confirm_all'));
    await waitFor(() => expect(confirmAction).toHaveBeenCalledTimes(2));
    expect(confirmAction).toHaveBeenCalledWith('book', 'b1', 'tok');
    expect(confirmAction).toHaveBeenCalledWith('book', 'b2', 'tok');
    expect(confirmActionBatch).not.toHaveBeenCalled();
  });

  // #29 — KG schema-edit cards inherit the SAME coalesce: 'kg' is NOT in
  // BATCH_CONFIRM_DOMAINS, so N kg children take the single-confirm LOOP →
  // confirmAction('kg', token) → POST /v1/kg/actions/confirm. (Previously only the
  // structurally-identical 'book' loop was tested; this asserts the kg path directly.)
  it('loops single /confirm for KG schema-edit children (#29 inheritance)', async () => {
    confirmAction.mockResolvedValue({});
    const kgChildren: BatchChild[] = [
      { token: 'k1', domain: 'kg', descriptor: 'kg_schema_edit', title: 'Add edge_type HUNTS' },
      { token: 'k2', domain: 'kg', descriptor: 'kg_schema_edit', title: 'Add node_kind Beast' },
    ];
    render(<BatchConfirmCard children={kgChildren} />);
    fireEvent.click(screen.getByText('batchConfirm.confirm_all'));
    await waitFor(() => expect(confirmAction).toHaveBeenCalledTimes(2));
    expect(confirmAction).toHaveBeenCalledWith('kg', 'k1', 'tok');
    expect(confirmAction).toHaveBeenCalledWith('kg', 'k2', 'tok');
    expect(confirmActionBatch).not.toHaveBeenCalled();
  });

  it('mixes domains: glossary→batch endpoint, book→single loop', async () => {
    confirmActionBatch.mockResolvedValue({ applied: 1, skipped: 0, failed: 0, children: [] });
    confirmAction.mockResolvedValue({});
    const mixed: BatchChild[] = [
      { token: 'g1', domain: 'glossary', descriptor: 'merge', title: 'Merge' },
      { token: 'b1', domain: 'book', descriptor: 'book.publish', title: 'Publish' },
    ];
    render(<BatchConfirmCard children={mixed} />);
    fireEvent.click(screen.getByText('batchConfirm.confirm_all'));
    await waitFor(() => expect(confirmActionBatch).toHaveBeenCalledWith('glossary', ['g1'], 'tok'));
    await waitFor(() => expect(confirmAction).toHaveBeenCalledWith('book', 'b1', 'tok'));
  });

  it('the pure auto-confirm path (no resume) commits without resuming any run', async () => {
    confirmActionBatch.mockResolvedValue({ applied: 2, skipped: 0, failed: 0, children: [] });
    render(<BatchConfirmCard children={glossaryChildren} />);
    fireEvent.click(screen.getByText('batchConfirm.confirm_all'));
    await waitFor(() => expect(confirmActionBatch).toHaveBeenCalled());
    expect(submitToolResult).not.toHaveBeenCalled();
  });

  it('reports a partial failure honestly and still resumes once', async () => {
    confirmActionBatch.mockResolvedValue({ applied: 1, skipped: 0, failed: 1, children: [] });
    render(<BatchConfirmCard children={glossaryChildren} resume={{ runId: 'r1', toolCallId: 'c1' }} />);
    fireEvent.click(screen.getByText('batchConfirm.confirm_all'));
    await waitFor(() => expect(screen.getByTestId('batch-confirm-result')).toBeTruthy());
    // applied>0 → still action_done (some landed), resumed once
    await waitFor(() => expect(submitToolResult).toHaveBeenCalledWith('r1', 'c1', 'action_done'));
  });

  it('cancel resumes cancelled without committing anything', async () => {
    render(<BatchConfirmCard children={glossaryChildren} resume={{ runId: 'r1', toolCallId: 'c1' }} />);
    fireEvent.click(screen.getByText('batchConfirm.cancel'));
    await waitFor(() => expect(submitToolResult).toHaveBeenCalledWith('r1', 'c1', 'cancelled'));
    expect(confirmActionBatch).not.toHaveBeenCalled();
    expect(confirmAction).not.toHaveBeenCalled();
  });
});

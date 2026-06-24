import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

// MCP fan-out (C-CONFIRM) — the GENERIC confirm card: domain selects the confirm
// endpoint; on mount it previews (non-consuming); Confirm POSTs the token and
// resumes with the real outcome (H6). H2: with items[] it renders ONE card with
// N rows + a single Apply.

const submitToolResult = vi.fn().mockResolvedValue('');
const confirmAction = vi.fn();
const previewAction = vi.fn();

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
vi.mock('../../providers', () => ({ useChatStream: () => ({ submitToolResult }) }));
vi.mock('../../actionsApi', () => ({
  actionsApi: {
    confirmAction: (...a: unknown[]) => confirmAction(...a),
    previewAction: (...a: unknown[]) => previewAction(...a),
  },
}));

import { ConfirmActionCard, descriptorDomain } from '../ConfirmActionCard';
import type { ToolCallRecord } from '../../types';

function record(args: Record<string, unknown>): ToolCallRecord {
  return { tool: 'confirm_action', ok: true, pending: true, runId: 'r1', toolCallId: 'c1', args };
}

const baseArgs = { confirm_token: 'tok123', descriptor: 'book.publish', title: 'Publish chapter', domain: 'book' };

describe('ConfirmActionCard', () => {
  beforeEach(() => {
    submitToolResult.mockClear();
    confirmAction.mockReset();
    previewAction.mockReset();
    previewAction.mockResolvedValue({
      descriptor: 'book.publish', title: 'Publish chapter',
      preview_rows: [{ label: 'chapter', value: 'Chapter 5' }], destructive: false,
    });
  });

  it('previews against the domain on mount', async () => {
    confirmAction.mockResolvedValue({});
    render(<ConfirmActionCard record={record(baseArgs)} />);
    await waitFor(() => expect(previewAction).toHaveBeenCalledWith('book', 'tok123', 'tok'));
    await waitFor(() => expect(screen.getByText('Chapter 5')).toBeInTheDocument());
  });

  it('confirm POSTs the token to the domain and resumes action_done', async () => {
    confirmAction.mockResolvedValue({});
    render(<ConfirmActionCard record={record(baseArgs)} />);
    fireEvent.click(screen.getByText('actionConfirm.confirm'));
    await waitFor(() => expect(confirmAction).toHaveBeenCalledWith('book', 'tok123', 'tok'));
    await waitFor(() => expect(submitToolResult).toHaveBeenCalledWith('r1', 'c1', 'action_done'));
  });

  it('resumes token_expired on a 422', async () => {
    confirmAction.mockRejectedValue(Object.assign(new Error('expired'), { status: 422 }));
    render(<ConfirmActionCard record={record(baseArgs)} />);
    fireEvent.click(screen.getByText('actionConfirm.confirm'));
    await waitFor(() => expect(submitToolResult).toHaveBeenCalledWith('r1', 'c1', 'token_expired'));
  });

  it('cancel resumes cancelled without a confirm POST', async () => {
    render(<ConfirmActionCard record={record(baseArgs)} />);
    fireEvent.click(screen.getByText('actionConfirm.cancel'));
    await waitFor(() => expect(submitToolResult).toHaveBeenCalledWith('r1', 'c1', 'cancelled'));
    expect(confirmAction).not.toHaveBeenCalled();
  });

  it('H2: a batch (items[]) renders ONE card with N rows and a single Apply', async () => {
    // server returns NO enumeration → advisory fallback to items[], Confirm gated
    // on the preview having loaded (FIX 1).
    previewAction.mockResolvedValue({ descriptor: 'book.publish_batch', title: 'Publish 3 drafts', preview_rows: null, destructive: false });
    confirmAction.mockResolvedValue({});
    render(<ConfirmActionCard record={record({
      ...baseArgs, descriptor: 'book.publish_batch',
      items: [{ title: 'Chapter 1' }, { title: 'Chapter 2' }, { title: 'Chapter 3' }],
    })} />);

    // exactly ONE card
    expect(screen.getAllByTestId('confirm-action-card')).toHaveLength(1);
    // N rows
    const rows = screen.getByTestId('confirm-batch-rows').querySelectorAll('li');
    expect(rows).toHaveLength(3);
    expect(screen.getByText('Chapter 2')).toBeInTheDocument();
    // FIX 1: this fallback list is labelled advisory and sourced from items[]
    expect(screen.getByTestId('confirm-batch-rows')).toHaveAttribute('data-source', 'advisory');
    expect(screen.getByTestId('confirm-batch-advisory')).toBeInTheDocument();
    // Confirm is gated until the server preview resolves.
    await waitFor(() => expect(previewAction).toHaveBeenCalled());
    // a SINGLE Apply (Confirm all) commits the whole batch with one token
    fireEvent.click(screen.getByText('actionConfirm.confirm_all'));
    await waitFor(() => expect(confirmAction).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(submitToolResult).toHaveBeenCalledWith('r1', 'c1', 'action_done'));
  });

  it('FIX 1: a batch renders from the SERVER preview rows when it enumerates the token', async () => {
    // server preview enumerates the token's items → batch rows come from the
    // server (what actually commits), NOT from the LLM args.items.
    previewAction.mockResolvedValue({
      descriptor: 'book.publish_batch', title: 'Publish 2 drafts',
      preview_rows: [
        { label: 'Chapter A (server)', value: 'draft→published' },
        { label: 'Chapter B (server)', value: 'draft→published' },
      ],
      destructive: false,
    });
    confirmAction.mockResolvedValue({});
    render(<ConfirmActionCard record={record({
      ...baseArgs, descriptor: 'book.publish_batch',
      // LLM-supplied items differ from the server set on purpose — server wins.
      items: [{ title: 'Chapter X (llm)' }, { title: 'Chapter Y (llm)' }, { title: 'Chapter Z (llm)' }],
    })} />);

    // rows are server-sourced (2), NOT the 3 advisory items
    await waitFor(() =>
      expect(screen.getByTestId('confirm-batch-rows')).toHaveAttribute('data-source', 'server'),
    );
    const rows = screen.getByTestId('confirm-batch-rows').querySelectorAll('li');
    expect(rows).toHaveLength(2);
    expect(screen.getByText(/Chapter A \(server\)/)).toBeInTheDocument();
    // the LLM advisory items are NOT shown, and no advisory label is rendered
    expect(screen.queryByText(/Chapter X \(llm\)/)).toBeNull();
    expect(screen.queryByTestId('confirm-batch-advisory')).toBeNull();
    // Confirm commits with the single server-bound token.
    fireEvent.click(screen.getByText('actionConfirm.confirm_all'));
    await waitFor(() => expect(confirmAction).toHaveBeenCalledWith('book', 'tok123', 'tok'));
    await waitFor(() => expect(submitToolResult).toHaveBeenCalledWith('r1', 'c1', 'action_done'));
  });

  it('resumes action_error on a non-422 failure', async () => {
    confirmAction.mockRejectedValue(Object.assign(new Error('boom'), { status: 500 }));
    render(<ConfirmActionCard record={record(baseArgs)} />);
    fireEvent.click(screen.getByText('actionConfirm.confirm'));
    await waitFor(() => expect(submitToolResult).toHaveBeenCalledWith('r1', 'c1', 'action_error'));
  });

  // MCP-fanout seam fix (#3): on a book-scoped chat the model may confirm a
  // NON-glossary action via the legacy glossary_confirm_action tool, which carries
  // a descriptor but NO `domain` arg. The card must derive the domain from the
  // dotted descriptor so it still commits to /v1/<domain>/actions/* (not glossary).
  it('derives the domain from a dotted descriptor when args.domain is absent', async () => {
    confirmAction.mockResolvedValue({});
    const { confirm_token, descriptor, title } = baseArgs; // no `domain`
    render(<ConfirmActionCard record={record({ confirm_token, descriptor, title })} />);
    // previews + commits against `book` (derived from `book.publish`), not '' / glossary.
    await waitFor(() => expect(previewAction).toHaveBeenCalledWith('book', 'tok123', 'tok'));
    fireEvent.click(screen.getByText('actionConfirm.confirm'));
    await waitFor(() => expect(confirmAction).toHaveBeenCalledWith('book', 'tok123', 'tok'));
    await waitFor(() => expect(submitToolResult).toHaveBeenCalledWith('r1', 'c1', 'action_done'));
  });
});

describe('descriptorDomain', () => {
  it('maps dotted generic-domain descriptors to their domain', () => {
    expect(descriptorDomain('book.publish')).toBe('book');
    expect(descriptorDomain('translation.start_job')).toBe('translation');
    expect(descriptorDomain('composition.merge')).toBe('composition');
    expect(descriptorDomain('settings.set_default_model')).toBe('settings');
  });
  it('returns null for glossary (non-dotted) descriptors and junk', () => {
    expect(descriptorDomain('book_delete')).toBeNull();      // glossary's own
    expect(descriptorDomain('schema_create_kind')).toBeNull();
    expect(descriptorDomain('adopt')).toBeNull();
    expect(descriptorDomain('unknown.thing')).toBeNull();    // unknown domain head
    expect(descriptorDomain('.x')).toBeNull();
    expect(descriptorDomain(undefined)).toBeNull();
  });
  it('maps kg_-prefixed KG descriptors to the kg domain (not glossary)', () => {
    // KG class-C descriptors commit at /v1/kg/actions/* — must NOT fall through to
    // the glossary ConfirmCard (which would POST /v1/glossary/actions/confirm → 422).
    expect(descriptorDomain('kg_schema_edit')).toBe('kg');
    expect(descriptorDomain('kg_adopt')).toBe('kg');
    expect(descriptorDomain('kg_sync_apply')).toBe('kg');
    expect(descriptorDomain('kg_triage_schema_write')).toBe('kg');
  });
});

describe('ConfirmActionCard — KG domain routing', () => {
  it('previews + confirms a kg_ descriptor against the kg endpoint', async () => {
    confirmAction.mockResolvedValue({});
    previewAction.mockResolvedValue({ descriptor: 'kg_schema_edit', title: 'add edge_type HUNTS', preview_rows: [], destructive: false });
    // No explicit domain arg → the card derives it from the descriptor.
    render(<ConfirmActionCard record={record({ confirm_token: 'kgtok', descriptor: 'kg_schema_edit', title: 'add edge_type HUNTS' })} />);
    await waitFor(() => expect(previewAction).toHaveBeenCalledWith('kg', 'kgtok', 'tok'));
    fireEvent.click(screen.getByText('actionConfirm.confirm'));
    await waitFor(() => expect(confirmAction).toHaveBeenCalledWith('kg', 'kgtok', 'tok'));
  });
});

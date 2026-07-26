import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent, waitFor } from '@testing-library/react';
import { renderWithClient } from '@/test-utils/renderWithClient';

// MCP fan-out (C-CONFIRM) — the GENERIC confirm card: domain selects the confirm
// endpoint; on mount it previews (non-consuming); Confirm POSTs the token and
// resumes with the real outcome (H6). H2: with items[] it renders ONE card with
// N rows + a single Apply.

const submitToolResult = vi.fn().mockResolvedValue('');
const confirmAction = vi.fn();
const previewAction = vi.fn();

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
vi.mock('../../providers', () => ({ useChatStream: () => ({ submitToolResult }) }));
vi.mock('../../actionsApi', async (importOriginal) => {
  // Keep the REAL parseRepriceError (a pure function the card calls on a 409) —
  // only the API methods are stubbed.
  const actual = await importOriginal<typeof import('../../actionsApi')>();
  return {
    ...actual,
    actionsApi: {
      confirmAction: (...a: unknown[]) => confirmAction(...a),
      previewAction: (...a: unknown[]) => previewAction(...a),
    },
  };
});

import { ConfirmActionCard, descriptorDomain } from '../ConfirmActionCard';
import { parseRepriceError } from '../../actionsApi';
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
    renderWithClient(<ConfirmActionCard record={record(baseArgs)} />);
    await waitFor(() => expect(previewAction).toHaveBeenCalledWith('book', 'tok123', 'tok'));
    await waitFor(() => expect(screen.getByText('Chapter 5')).toBeInTheDocument());
  });

  it('confirm POSTs the token to the domain and resumes action_done', async () => {
    confirmAction.mockResolvedValue({});
    renderWithClient(<ConfirmActionCard record={record(baseArgs)} />);
    fireEvent.click(screen.getByText('actionConfirm.confirm'));
    await waitFor(() => expect(confirmAction).toHaveBeenCalledWith('book', 'tok123', 'tok'));
    await waitFor(() => expect(submitToolResult).toHaveBeenCalledWith('r1', 'c1', 'action_done'));
  });

  it('M0c — renders the server-built diff (book.meta changes) and confirms via the book endpoint', async () => {
    confirmAction.mockResolvedValue({});
    previewAction.mockRejectedValue(new Error('no preview for book.meta')); // preview is best-effort
    const diffArgs = {
      confirm_token: 'metatok',
      descriptor: 'book.meta',
      title: 'Update book details',
      domain: 'book',
      changes: [
        { field_label: 'Description', old_value: 'old desc', new_value: 'a dramatic new blurb', target: 'description' },
      ],
    };
    renderWithClient(<ConfirmActionCard record={record(diffArgs)} />);
    // the old→new diff renders (not a bare yes/no)
    expect(screen.getByTestId('confirm-diff-rows')).toBeInTheDocument();
    expect(screen.getByText('old desc')).toBeInTheDocument();
    expect(screen.getByText('a dramatic new blurb')).toBeInTheDocument();
    // apply still uses the confirm-token path against the book domain
    fireEvent.click(screen.getByText('actionConfirm.confirm'));
    await waitFor(() => expect(confirmAction).toHaveBeenCalledWith('book', 'metatok', 'tok'));
    await waitFor(() => expect(submitToolResult).toHaveBeenCalledWith('r1', 'c1', 'action_done'));
  });

  it('resumes token_expired on a 422', async () => {
    confirmAction.mockRejectedValue(Object.assign(new Error('expired'), { status: 422 }));
    renderWithClient(<ConfirmActionCard record={record(baseArgs)} />);
    fireEvent.click(screen.getByText('actionConfirm.confirm'));
    await waitFor(() => expect(submitToolResult).toHaveBeenCalledWith('r1', 'c1', 'token_expired'));
  });

  it('cancel resumes cancelled without a confirm POST', async () => {
    renderWithClient(<ConfirmActionCard record={record(baseArgs)} />);
    fireEvent.click(screen.getByText('actionConfirm.cancel'));
    await waitFor(() => expect(submitToolResult).toHaveBeenCalledWith('r1', 'c1', 'cancelled'));
    expect(confirmAction).not.toHaveBeenCalled();
  });

  it('H2: a batch (items[]) renders ONE card with N rows and a single Apply', async () => {
    // server returns NO enumeration → advisory fallback to items[], Confirm gated
    // on the preview having loaded (FIX 1).
    previewAction.mockResolvedValue({ descriptor: 'book.publish_batch', title: 'Publish 3 drafts', preview_rows: null, destructive: false });
    confirmAction.mockResolvedValue({});
    renderWithClient(<ConfirmActionCard record={record({
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
    renderWithClient(<ConfirmActionCard record={record({
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

  // Phase 2 — destructive plan ops: each renders an OPT-IN checkbox (default OFF).
  // Confirming with none checked sends NO enabled_ops (the executor skips them);
  // checking one sends its op_id in enabled_ops.
  const planArgs = { confirm_token: 'plantok', descriptor: 'execute_plan', title: 'Execute plan', domain: 'glossary' };
  function planPreview() {
    return {
      descriptor: 'execute_plan', title: 'Execute plan — 2 operation(s)', destructive: true,
      preview_rows: [
        { label: 'create kinds', value: '1 new', op_id: 'op-1', destructive: false },
        { label: 'delete kind', value: 'deity', note: 'deprecates the kind + 4 attribute(s)', op_id: 'op-2', destructive: true },
      ],
    };
  }

  it('a destructive plan op renders an opt-in checkbox and a skipped-unless-enabled hint', async () => {
    previewAction.mockResolvedValue(planPreview());
    renderWithClient(<ConfirmActionCard record={record(planArgs)} />);
    // the destructive row has a checkbox keyed by op_id, UNCHECKED by default
    const box = await screen.findByTestId('enable-op');
    expect(box).toHaveAttribute('data-op-id', 'op-2');
    expect(box).not.toBeChecked();
    // and the "will be skipped" hint counts the one un-enabled destructive op
    expect(screen.getByTestId('pending-destructive')).toBeInTheDocument();
  });

  it('confirm with nothing checked sends NO enabled_ops (destructive op is skipped)', async () => {
    previewAction.mockResolvedValue(planPreview());
    confirmAction.mockResolvedValue({ applied: [], skipped: [{ reason: 'not_confirmed' }], failed: [] });
    renderWithClient(<ConfirmActionCard record={record(planArgs)} />);
    await screen.findByTestId('enable-op');
    fireEvent.click(screen.getByText('actionConfirm.confirm'));
    // 3-arg call — no enabled_ops appended
    await waitFor(() => expect(confirmAction).toHaveBeenCalledWith('glossary', 'plantok', 'tok'));
  });

  it('checking a destructive op sends its op_id in enabled_ops on confirm', async () => {
    previewAction.mockResolvedValue(planPreview());
    confirmAction.mockResolvedValue({ applied: [{ reason: '' }], skipped: [], failed: [] });
    renderWithClient(<ConfirmActionCard record={record(planArgs)} />);
    const box = await screen.findByTestId('enable-op');
    fireEvent.click(box); // enable op-2
    expect(box).toBeChecked();
    // hint clears once the only destructive op is enabled
    expect(screen.queryByTestId('pending-destructive')).toBeNull();
    fireEvent.click(screen.getByText('actionConfirm.confirm'));
    await waitFor(() => expect(confirmAction).toHaveBeenCalledWith('glossary', 'plantok', 'tok', ['op-2']));
  });

  // H-J / H14 re-price-on-execute: a priced confirm route returns 409
  // reprice_required (FastAPI nests it under body.detail) when the actual cost
  // drifted up past the BE threshold. The card surfaces the NEW price and resumes
  // `reprice_required` (NOT token_expired / action_error) so the agent re-proposes
  // at the real price — never a silent overspend.
  it('resumes reprice_required on a 409 reprice and shows old→new cost', async () => {
    confirmAction.mockRejectedValue(
      Object.assign(new Error('reprice'), {
        status: 409,
        body: {
          detail: {
            code: 'TRANSL_REPRICE_REQUIRED',
            status: 'reprice_required',
            confirmed_cost_usd: 0.4,
            actual_cost_usd: 0.95,
            estimate: { cost_usd: 0.95 },
          },
        },
      }),
    );
    renderWithClient(<ConfirmActionCard record={record(baseArgs)} />);
    fireEvent.click(screen.getByText('actionConfirm.confirm'));
    await waitFor(() => expect(submitToolResult).toHaveBeenCalledWith('r1', 'c1', 'reprice_required'));
    // the new-price card renders (FE never recomputes the threshold — it reacts to
    // the BE 409). The i18n stub returns keys, so assert the card + its title key.
    const card = await screen.findByTestId('confirm-reprice');
    expect(card.textContent).toContain('actionConfirm.reprice_title');
  });

  // The reprice detail may arrive at body root (not under .detail) — e.g. a
  // non-FastAPI emitter or the headless edge replay; parse both shapes.
  it('handles a 409 reprice carried at body root (status marker)', async () => {
    confirmAction.mockRejectedValue(
      Object.assign(new Error('reprice'), {
        status: 409,
        body: { status: 'reprice_required', actual_cost_usd: 1.2, confirmed_cost_usd: 0.5 },
      }),
    );
    renderWithClient(<ConfirmActionCard record={record(baseArgs)} />);
    fireEvent.click(screen.getByText('actionConfirm.confirm'));
    await waitFor(() => expect(submitToolResult).toHaveBeenCalledWith('r1', 'c1', 'reprice_required'));
  });

  // A 409 that is NOT a reprice (e.g. a generic conflict) must fall through to
  // action_error, not be swallowed as a reprice.
  it('a non-reprice 409 resumes action_error', async () => {
    confirmAction.mockRejectedValue(
      Object.assign(new Error('conflict'), { status: 409, body: { code: 'SOME_OTHER', message: 'nope' } }),
    );
    renderWithClient(<ConfirmActionCard record={record(baseArgs)} />);
    fireEvent.click(screen.getByText('actionConfirm.confirm'));
    await waitFor(() => expect(submitToolResult).toHaveBeenCalledWith('r1', 'c1', 'action_error'));
  });

  it('resumes action_error on a non-422 failure', async () => {
    confirmAction.mockRejectedValue(Object.assign(new Error('boom'), { status: 500 }));
    renderWithClient(<ConfirmActionCard record={record(baseArgs)} />);
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
    renderWithClient(<ConfirmActionCard record={record({ confirm_token, descriptor, title })} />);
    // previews + commits against `book` (derived from `book.publish`), not '' / glossary.
    await waitFor(() => expect(previewAction).toHaveBeenCalledWith('book', 'tok123', 'tok'));
    fireEvent.click(screen.getByText('actionConfirm.confirm'));
    await waitFor(() => expect(confirmAction).toHaveBeenCalledWith('book', 'tok123', 'tok'));
    await waitFor(() => expect(submitToolResult).toHaveBeenCalledWith('r1', 'c1', 'action_done'));
  });
});

describe('parseRepriceError (H-J / H14)', () => {
  it('extracts the new estimate from a FastAPI-nested 409 reprice detail', () => {
    const r = parseRepriceError(
      Object.assign(new Error('x'), {
        status: 409,
        body: { detail: { code: 'TRANSL_REPRICE_REQUIRED', status: 'reprice_required', confirmed_cost_usd: 0.4, actual_cost_usd: 0.95, estimate: { cost_usd: 0.95 } } },
      }),
    );
    expect(r?.confirmed_cost_usd).toBe(0.4);
    expect(r?.actual_cost_usd).toBe(0.95);
    expect(r?.estimate?.cost_usd).toBe(0.95);
  });
  it('accepts the detail at body root (status marker), not just under .detail', () => {
    const r = parseRepriceError(Object.assign(new Error('x'), { status: 409, body: { status: 'reprice_required', actual_cost_usd: 1.2 } }));
    expect(r?.actual_cost_usd).toBe(1.2);
  });
  it('returns null for a non-409, a non-reprice 409, and a missing body', () => {
    expect(parseRepriceError(Object.assign(new Error('x'), { status: 422, body: { status: 'reprice_required' } }))).toBeNull();
    expect(parseRepriceError(Object.assign(new Error('x'), { status: 409, body: { code: 'OTHER' } }))).toBeNull();
    expect(parseRepriceError(Object.assign(new Error('x'), { status: 409 }))).toBeNull();
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
    renderWithClient(<ConfirmActionCard record={record({ confirm_token: 'kgtok', descriptor: 'kg_schema_edit', title: 'add edge_type HUNTS' })} />);
    await waitFor(() => expect(previewAction).toHaveBeenCalledWith('kg', 'kgtok', 'tok'));
    fireEvent.click(screen.getByText('actionConfirm.confirm'));
    await waitFor(() => expect(confirmAction).toHaveBeenCalledWith('kg', 'kgtok', 'tok'));
  });
});

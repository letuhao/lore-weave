import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import { renderWithClient } from '@/test-utils/renderWithClient';
import type { ToolCallRecord } from '../../types';

// Auto-rendered confirm card: a class-C glossary propose tool mints a confirm_token
// in its RESULT but the (weak) model never calls the frontend glossary_confirm_action
// tool. AssistantMessage must still surface an Approve card directly from the propose
// result so a GUI-only user can approve — independent of the model.

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok-1' }) }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('../../api', () => ({ chatApi: { submitMessageFeedback: vi.fn() } }));
// ConfirmCard deps: the chat stream provider + the glossary actions API.
vi.mock('../../providers', () => ({
  useChatStream: () => ({ submitToolResult: vi.fn() }),
  useChatStreamOptional: () => ({ submitToolResult: vi.fn() }),
}));
const { previewAction, confirmAction } = vi.hoisted(() => ({
  previewAction: vi.fn(), confirmAction: vi.fn(),
}));
vi.mock('@/features/glossary/api', () => ({ glossaryApi: { previewAction, confirmAction } }));

import { AssistantMessage } from '../AssistantMessage';

/** A 2-part action token whose base64url segment-0 carries `exp` (seconds). `jti`
 *  defaults unique-ish per call so two tokens in one test don't accidentally collide
 *  (the coalesce dedups by token, so distinct cards need distinct tokens). */
let _jti = 0;
function makeToken(expSecondsFromNow: number, jti = `x${_jti++}`): string {
  const claims = { jti, exp: Math.floor(Date.now() / 1000) + expSecondsFromNow };
  const seg = btoa(JSON.stringify(claims)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  return `${seg}.sig`;
}

function proposeCall(token: string, result?: unknown): ToolCallRecord {
  return {
    tool: 'glossary_propose_new_kind',
    ok: true,
    result: result ?? { confirm_token: token, descriptor: 'schema_create_kind', title: 'Create kind "Vampire"' },
  };
}

describe('AssistantMessage — auto-rendered confirm card', () => {
  beforeEach(() => { previewAction.mockReset(); previewAction.mockResolvedValue({ title: 'Create kind', preview_rows: [], destructive: false }); });

  it('renders an Approve card from a completed propose result with a live token', () => {
    renderWithClient(<AssistantMessage content="Proposed." toolCalls={[proposeCall(makeToken(3600))]} />);
    expect(screen.getByTestId('confirm-card')).toBeTruthy();
  });

  it('does NOT render a card for an EXPIRED token (stale replay)', () => {
    renderWithClient(<AssistantMessage content="Proposed." toolCalls={[proposeCall(makeToken(-3600))]} />);
    expect(screen.queryByTestId('confirm-card')).toBeNull();
  });

  it('handles the nested {result:{confirm_token}} shape', () => {
    const token = makeToken(3600);
    const nested = proposeCall(token, { ok: true, result: { confirm_token: token, descriptor: 'schema_create_attribute', title: 'Add attribute' } });
    renderWithClient(<AssistantMessage content="Proposed." toolCalls={[nested]} />);
    expect(screen.getByTestId('confirm-card')).toBeTruthy();
  });

  it('does NOT double-render when an explicit pending confirm card already handles the token', () => {
    const token = makeToken(3600);
    const explicit: ToolCallRecord = {
      tool: 'glossary_confirm_action', ok: true, pending: true,
      runId: 'r1', toolCallId: 'tc1',
      args: { confirm_token: token, descriptor: 'schema_create_kind', title: 'Create kind' },
    };
    renderWithClient(<AssistantMessage content="Proposed." toolCalls={[proposeCall(token), explicit]} />);
    // Exactly one confirm card (the explicit suspended one), not two.
    expect(screen.getAllByTestId('confirm-card')).toHaveLength(1);
  });

  // #27/#29/#30 — MORE THAN ONE live token in a turn coalesces into ONE batch card,
  // never N individual cards (the orphaning bug). One human "Confirm all".
  it('coalesces multiple live tokens into a SINGLE batch card (not N orphaning cards)', () => {
    const t1 = makeToken(3600);
    const t2 = makeToken(3600);
    const c1 = proposeCall(t1, { confirm_token: t1, descriptor: 'schema_create_kind', title: 'Create kind A' });
    const c2 = proposeCall(t2, { confirm_token: t2, descriptor: 'schema_create_kind', title: 'Create kind B' });
    renderWithClient(<AssistantMessage content="Proposed two." toolCalls={[c1, c2]} />);
    expect(screen.getByTestId('batch-confirm-card')).toBeTruthy();
    // the per-action cards are folded in — not rendered individually
    expect(screen.queryByTestId('confirm-card')).toBeNull();
    expect(screen.getByTestId('batch-confirm-rows').children).toHaveLength(2);
  });

  // #29 — KG schema-edit propose results coalesce by the SAME domain-agnostic path:
  // two kg_schema_edit results (descriptor → the `kg` domain) fold into ONE batch card
  // with kg-domain rows (proving the multi-card coalesce isn't glossary-only).
  it('coalesces multiple KG schema-edit tokens into one batch card with kg-domain rows (#29)', () => {
    const t1 = makeToken(3600);
    const t2 = makeToken(3600);
    const kg1: ToolCallRecord = { tool: 'kg_schema_edit', ok: true, result: { confirm_token: t1, descriptor: 'kg_schema_edit', summary: 'Add edge_type HUNTS' } };
    const kg2: ToolCallRecord = { tool: 'kg_schema_edit', ok: true, result: { confirm_token: t2, descriptor: 'kg_schema_edit', summary: 'Add node_kind Beast' } };
    renderWithClient(<AssistantMessage content="Proposed two KG edits." toolCalls={[kg1, kg2]} />);
    expect(screen.getByTestId('batch-confirm-card')).toBeTruthy();
    expect(screen.queryByTestId('confirm-card')).toBeNull();
    expect(screen.getByTestId('batch-confirm-rows').children).toHaveLength(2);
    // both rows route to the `kg` domain (not the glossary default)
    expect(screen.getAllByText('kg')).toHaveLength(2);
  });

  // A SINGLE live token is unchanged (no premature coalescing) — the legacy single card.
  it('does NOT coalesce a single token (keeps the single card)', () => {
    renderWithClient(<AssistantMessage content="Proposed one." toolCalls={[proposeCall(makeToken(3600))]} />);
    expect(screen.queryByTestId('batch-confirm-card')).toBeNull();
    expect(screen.getByTestId('confirm-card')).toBeTruthy();
  });
});

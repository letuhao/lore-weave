import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
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

/** A 2-part action token whose base64url segment-0 carries `exp` (seconds). */
function makeToken(expSecondsFromNow: number): string {
  const claims = { jti: 'x', exp: Math.floor(Date.now() / 1000) + expSecondsFromNow };
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
    render(<AssistantMessage content="Proposed." toolCalls={[proposeCall(makeToken(3600))]} />);
    expect(screen.getByTestId('confirm-card')).toBeTruthy();
  });

  it('does NOT render a card for an EXPIRED token (stale replay)', () => {
    render(<AssistantMessage content="Proposed." toolCalls={[proposeCall(makeToken(-3600))]} />);
    expect(screen.queryByTestId('confirm-card')).toBeNull();
  });

  it('handles the nested {result:{confirm_token}} shape', () => {
    const token = makeToken(3600);
    const nested = proposeCall(token, { ok: true, result: { confirm_token: token, descriptor: 'schema_create_attribute', title: 'Add attribute' } });
    render(<AssistantMessage content="Proposed." toolCalls={[nested]} />);
    expect(screen.getByTestId('confirm-card')).toBeTruthy();
  });

  it('does NOT double-render when an explicit pending confirm card already handles the token', () => {
    const token = makeToken(3600);
    const explicit: ToolCallRecord = {
      tool: 'glossary_confirm_action', ok: true, pending: true,
      runId: 'r1', toolCallId: 'tc1',
      args: { confirm_token: token, descriptor: 'schema_create_kind', title: 'Create kind' },
    };
    render(<AssistantMessage content="Proposed." toolCalls={[proposeCall(token), explicit]} />);
    // Exactly one confirm card (the explicit suspended one), not two.
    expect(screen.getAllByTestId('confirm-card')).toHaveLength(1);
  });
});

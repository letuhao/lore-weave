// The session settings panel is the "session-scoped subset" of G1. These tests pin the
// three things that make it more than a repaint of the old panel:
//
//   1. it reads the CASCADE (Session ▸ Book ▸ Account ▸ System) instead of inventing
//      client-side literals — `temperature ?? 0.7` displayed a number the request never sent;
//   2. the tier chip names where the value came from;
//   3. "clear · inherit X" writes an explicit `null`, which is the ONLY way the backend's
//      `model_fields_set` can tell "stop overriding" from "leave alone".
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import type { ChatSession } from '../../types';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

// The heavy children own their own tests; this file is about the cascade wiring.
vi.mock('@/components/model-picker', () => ({
  ModelPicker: () => <div data-testid="model-picker-stub" />,
  useUserModels: () => ({ data: [] }),
  invalidateUserModelsCache: () => undefined,
}));
vi.mock('@/components/shared/MultiProjectPicker', () => ({
  MultiProjectPicker: () => <div data-testid="project-picker-stub" />,
}));
vi.mock('../VoiceSettingsPanel', () => ({
  VoiceSettingsPanel: () => <div data-testid="voice-section-stub" />,
}));

const getEffective = vi.fn();
vi.mock('@/features/chat-ai-settings/api', () => ({
  aiSettingsApi: {
    getEffective: (...a: unknown[]) => getEffective(...a),
    patchPrefs: vi.fn(),
  },
}));

const patchSession = vi.fn();
vi.mock('../../api', () => ({ chatApi: { patchSession: (...a: unknown[]) => patchSession(...a) } }));

import { SessionSettingsPanel } from '../SessionSettingsPanel';

const SESSION: ChatSession = {
  session_id: 's1', owner_user_id: 'u1', title: 't',
  model_source: 'user_model', model_ref: 'm1',
  system_prompt: null, generation_params: {}, is_pinned: false, status: 'active',
  message_count: 3, last_message_at: null, created_at: '', updated_at: '', project_id: null,
} as unknown as ChatSession;

/** A cascade where temperature is UNSET everywhere and grounding comes from the account. */
function effective(over: Record<string, unknown> = {}) {
  return {
    context_ref: { book_id: null, session_id: 's1' },
    models: { chat: { effective_value: null, source_tier: 'account', tier_stack: {}, skipped: [] } },
    behavior: {
      reasoning_effort: { effective_value: 'off', source_tier: 'system', tier_stack: { system: 'off' } },
      temperature: { effective_value: null, source_tier: null, tier_stack: {} },
      top_p: { effective_value: null, source_tier: null, tier_stack: {} },
      max_tokens: { effective_value: null, source_tier: null, tier_stack: {} },
    },
    grounding: {
      grounding_enabled: { effective_value: true, source_tier: 'account', tier_stack: { account: true, system: true } },
    },
    context: { mode: { effective_value: 'auto', source_tier: 'account', tier_stack: { account: 'auto', system: 'auto' } } },
    voice: {},
    ...over,
  };
}

function renderPanel(session: ChatSession = SESSION) {
  const onSessionUpdate = vi.fn();
  render(
    <SessionSettingsPanel session={session} onSessionUpdate={onSessionUpdate} onClose={vi.fn()} />,
  );
  return { onSessionUpdate };
}

beforeEach(() => {
  getEffective.mockReset().mockResolvedValue(effective());
  patchSession.mockReset().mockImplementation(async (_t, _s, body) => ({ ...SESSION, ...body }));
});

describe('SessionSettingsPanel — reads the cascade', () => {
  it('resolves against THIS session (so the chip can ever say "this chat")', async () => {
    renderPanel();
    await waitFor(() => expect(getEffective).toHaveBeenCalled());
    expect(getEffective.mock.calls[0][1]).toMatchObject({ sessionId: 's1' });
  });

  it('shows the tier that supplied each value', async () => {
    renderPanel();
    await screen.findByTestId('session-grounding-section');
    // grounding came from the account; reasoning effort from the system default.
    expect(screen.getAllByTestId('tier-chip-account').length).toBeGreaterThan(0);
    expect(screen.getAllByTestId('tier-chip-system').length).toBeGreaterThan(0);
  });

  it('never invents 0.7 for an unset temperature — it says the provider decides', async () => {
    renderPanel();
    const slider = await screen.findByTestId('session-temperature');
    expect(slider.textContent).toContain('Not set');
    expect(slider.textContent).toContain("provider's own default");
    // and no range input exists to imply a value is in force
    expect(slider.querySelector('input[type="range"]')).toBeNull();
  });

  it('setting an unset value writes it as a session override', async () => {
    renderPanel();
    fireEvent.click(await screen.findByTestId('session-temperature-set'));
    await waitFor(() => expect(patchSession).toHaveBeenCalled());
    expect(patchSession.mock.calls[0][2]).toEqual({ generation_params: { temperature: 0.7 } });
  });
});

describe('SessionSettingsPanel — clear · inherit', () => {
  it('offers a clear ONLY where the session row carries the override', async () => {
    renderPanel();
    await screen.findByTestId('session-grounding-section');
    // nothing is overridden on this session
    expect(screen.queryByTestId('session-grounding-clear')).toBeNull();
    expect(screen.queryByTestId('session-context-mode-clear')).toBeNull();
  });

  it('shows clear + names the inherited value once the session overrides it', async () => {
    renderPanel({ ...SESSION, grounding_enabled: false } as ChatSession);
    const clear = await screen.findByTestId('session-grounding-clear');
    // "would inherit ON" — a clear button that doesn't say what you'd get is a dare.
    expect(clear.textContent).toContain('inherit on');
  });

  it('clearing sends an explicit null, not undefined', async () => {
    // `undefined` is dropped by JSON.stringify and read server-side as "leave alone",
    // so the override could be turned on but never off.
    renderPanel({ ...SESSION, grounding_enabled: false } as ChatSession);
    fireEvent.click(await screen.findByTestId('session-grounding-clear'));
    await waitFor(() => expect(patchSession).toHaveBeenCalled());
    const body = patchSession.mock.calls[0][2];
    expect(body).toHaveProperty('grounding_enabled', null);
    expect(JSON.stringify(body)).toContain('"grounding_enabled":null');
  });

  it('clearing a jsonb leaf sends a null LEAF, keeping siblings', async () => {
    renderPanel({ ...SESSION, context_overrides: { mode: 'off', trigger_ratio: 0.8 } } as ChatSession);
    fireEvent.click(await screen.findByTestId('session-context-mode-clear'));
    await waitFor(() => expect(patchSession).toHaveBeenCalled());
    expect(patchSession.mock.calls[0][2]).toEqual({ context_overrides: { mode: null } });
  });
});

describe('SessionSettingsPanel — the new sections exist at all', () => {
  it('renders grounding and context, which were impossible before the session tier was writable', async () => {
    renderPanel();
    expect(await screen.findByTestId('session-grounding-toggle')).toBeInTheDocument();
    expect(await screen.findByTestId('session-context-mode-off')).toBeInTheDocument();
  });

  it('folds voice in as a section rather than a rival slide-over', async () => {
    renderPanel();
    expect(await screen.findByTestId('voice-section-stub')).toBeInTheDocument();
  });

  it('degrades visibly when the resolver is unreachable — never a blank panel', async () => {
    getEffective.mockRejectedValueOnce(new Error('resolver down'));
    renderPanel();
    expect(await screen.findByText(/resolver down/)).toBeInTheDocument();
    expect(screen.getByTestId('session-models-section')).toBeInTheDocument();
  });
});

describe('SessionSettingsPanel — a pending edit belongs to the session it was made on', () => {
  it('never flushes session A\'s edit onto session B after a session switch', async () => {
    // The panel stays mounted across a session switch (ChatView keeps `settingsOpen`).
    // `send()` used to PATCH `latest.current.session_id`, and `latest.current` is
    // reassigned during render — so the debounced edit for A landed on B. A cross-session
    // write: the user's prompt for one chat silently overwrites another's.
    const onSessionUpdate = vi.fn();
    const A = { ...SESSION, session_id: 'A' } as ChatSession;
    const B = { ...SESSION, session_id: 'B' } as ChatSession;

    const { rerender } = render(
      <SessionSettingsPanel session={A} onSessionUpdate={onSessionUpdate} onClose={vi.fn()} />,
    );
    fireEvent.change(await screen.findByTestId('session-system-prompt'), {
      target: { value: 'A-only prompt' },
    });

    rerender(<SessionSettingsPanel session={B} onSessionUpdate={onSessionUpdate} onClose={vi.fn()} />);

    await waitFor(() => expect(patchSession).toHaveBeenCalled());
    const [, sessionId, body] = patchSession.mock.calls[0];
    expect(body).toMatchObject({ system_prompt: 'A-only prompt' });
    expect(sessionId).toBe('A');
  });

  it('does not push the flushed session\'s row into the now-active session', async () => {
    const onSessionUpdate = vi.fn();
    const A = { ...SESSION, session_id: 'A' } as ChatSession;
    const B = { ...SESSION, session_id: 'B' } as ChatSession;
    const { rerender } = render(
      <SessionSettingsPanel session={A} onSessionUpdate={onSessionUpdate} onClose={vi.fn()} />,
    );
    fireEvent.change(await screen.findByTestId('session-system-prompt'), { target: { value: 'x' } });
    rerender(<SessionSettingsPanel session={B} onSessionUpdate={onSessionUpdate} onClose={vi.fn()} />);
    await waitFor(() => expect(patchSession).toHaveBeenCalled());
    // A's updated row must NOT be handed to the provider while B is active.
    for (const [row] of onSessionUpdate.mock.calls) {
      expect((row as ChatSession).session_id).not.toBe('A');
    }
  });
});

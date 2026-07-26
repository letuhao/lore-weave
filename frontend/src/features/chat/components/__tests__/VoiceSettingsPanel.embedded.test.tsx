// VoiceSettingsPanel gained an `embedded` mode so the unified session panel can host it
// as a section. The refactor introduced a subtle, expensive bug: the wrapper `Shell` was a
// component defined INSIDE the render body, so every render produced a new component TYPE
// and React unmounted + remounted the whole voice subtree. Focus is lost mid-typing, a
// range-slider drag drops its pointer capture, and every child re-runs its effects (which
// here means re-fetching the provider voice list on every keystroke).
//
// These tests pin: the embedded shell renders inline (no rival `fixed` overlay), and
// changing a setting does NOT remount the children.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { useEffect } from 'react';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
// `getVoices` is a STATIC method on the class, not an instance one.
vi.mock('@/hooks/engines/BrowserTTSEngine', () => ({
  BrowserTTSEngine: { getVoices: () => [] },
}));

// Counts MOUNTS (not renders): a remount re-runs the effect with an empty dep array.
const mounts = { count: 0 };
vi.mock('@/components/model-picker', () => ({
  ModelPicker: () => {
    useEffect(() => { mounts.count += 1; }, []);
    return <div data-testid="voice-model-picker" />;
  },
  useUserModels: () => ({ data: [] }),
}));

vi.mock('@/features/chat-ai-settings/api', () => ({
  aiSettingsApi: { patchPrefs: vi.fn().mockResolvedValue({}) },
}));

import { VoiceSettingsPanel } from '../VoiceSettingsPanel';

beforeEach(() => {
  vi.clearAllMocks(); // the patchPrefs spy is module-level; counts would accumulate
  mounts.count = 0;
  localStorage.clear();
  // The ModelPicker only renders when the source is an AI model — seed that, or the
  // mount counter has nothing to count.
  localStorage.setItem('lw_voice_prefs', JSON.stringify({ sttSource: 'ai_model', ttsSource: 'ai_model' }));
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ voices: [] }) }));
  // jsdom has no Web Speech API; the panel subscribes to voiceschanged.
  vi.stubGlobal('speechSynthesis', {
    getVoices: () => [],
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
  });
});

describe('VoiceSettingsPanel — embedded mode', () => {
  it('renders inline, with no fixed slide-over to fight the host panel for the edge', () => {
    const { container } = render(<VoiceSettingsPanel open embedded onClose={vi.fn()} />);
    expect(screen.getByTestId('voice-settings-embedded')).toBeInTheDocument();
    expect(container.querySelector('.fixed.inset-y-0.right-0')).toBeNull();
    expect(container.querySelector('.fixed.inset-0')).toBeNull();
  });

  it('still renders its own slide-over when NOT embedded', () => {
    const { container } = render(<VoiceSettingsPanel open onClose={vi.fn()} />);
    expect(screen.queryByTestId('voice-settings-embedded')).toBeNull();
    expect(container.querySelector('.fixed.inset-y-0.right-0')).not.toBeNull();
  });

  it('does NOT remount its children when a setting changes', () => {
    const { container } = render(<VoiceSettingsPanel open embedded onClose={vi.fn()} />);
    const before = mounts.count;
    expect(before).toBeGreaterThan(0);

    // Any pref edit re-renders the panel. A `Shell` defined in the render body would
    // change component identity and blow the whole subtree away.
    fireEvent.change(container.querySelector('select')!, { target: { value: 'browser' } });

    expect(mounts.count).toBe(before);
  });

  it('does not remount when toggling between renders repeatedly', () => {
    const { rerender } = render(<VoiceSettingsPanel open embedded onClose={vi.fn()} />);
    const before = mounts.count;
    rerender(<VoiceSettingsPanel open embedded onClose={vi.fn()} />);
    rerender(<VoiceSettingsPanel open embedded onClose={vi.fn()} />);
    expect(mounts.count).toBe(before);
  });
});

// D-CHATAI-VOICE-TWO-STORES: the panel mirrors the SHARED leaves up to the account home
// (`user_chat_ai_prefs.voice`) so the two surfaces can never disagree. It must not mirror
// panel-only leaves, and must not mirror a no-op — each mirror is a network PATCH.
describe('VoiceSettingsPanel — account mirror', () => {
  it('does not PATCH the account home for a panel-only leaf', async () => {
    const { aiSettingsApi } = await import('@/features/chat-ai-settings/api');
    render(<VoiceSettingsPanel open embedded onClose={vi.fn()} />);
    // TTS speed lives only in the voice store.
    const speed = screen.getByText('1.5x');
    fireEvent.click(speed);
    expect(aiSettingsApi.patchPrefs).not.toHaveBeenCalled();
  });

  it('mirrors a shared leaf, emitting the ai_model vocabulary', async () => {
    const { aiSettingsApi } = await import('@/features/chat-ai-settings/api');
    const { container } = render(<VoiceSettingsPanel open embedded onClose={vi.fn()} />);
    // the first select is the STT source; flip it to browser (a shared leaf)
    fireEvent.change(container.querySelector('select')!, { target: { value: 'browser' } });
    expect(aiSettingsApi.patchPrefs).toHaveBeenCalledTimes(1);
    const [, patch] = (aiSettingsApi.patchPrefs as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(patch.voice.stt.source).toBe('browser');
    expect(JSON.stringify(patch)).not.toContain('user_model');
  });

  it('does not mirror when the value did not actually change', async () => {
    const { aiSettingsApi } = await import('@/features/chat-ai-settings/api');
    const { container } = render(<VoiceSettingsPanel open embedded onClose={vi.fn()} />);
    // seeded as 'ai_model'; re-selecting it is a no-op
    fireEvent.change(container.querySelector('select')!, { target: { value: 'ai_model' } });
    expect(aiSettingsApi.patchPrefs).not.toHaveBeenCalled();
  });
});

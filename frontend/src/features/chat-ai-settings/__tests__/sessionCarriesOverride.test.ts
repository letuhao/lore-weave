// Spec §3.1 finding UX-5: the tier chip and the "clear · inherit X" affordance key on
// **which tier supplied the value**, never on value-equality.
//
// If "overridden" were computed by comparing the session's value to the account's, then a
// user who deliberately set temperature to exactly their account default would see
// "inherited", the clear button would vanish, and they could never tell whether the chat
// was pinned or following. This function is the load-bearing predicate — it asks only:
// does the SESSION row itself carry this leaf?
import { describe, it, expect } from 'vitest';
import type { ChatSession } from '@/features/chat/types';
import { sessionCarriesOverride } from '../hooks/useSessionSettingsEditor';

const session = (over: Partial<ChatSession> = {}): ChatSession =>
  ({
    session_id: 's1',
    owner_user_id: 'u1',
    title: 't',
    model_source: 'user_model',
    model_ref: 'm1',
    system_prompt: null,
    generation_params: {},
    is_pinned: false,
    status: 'active',
    message_count: 0,
    last_message_at: null,
    created_at: '',
    updated_at: '',
    project_id: null,
    ...over,
  }) as unknown as ChatSession;

describe('sessionCarriesOverride — behavior', () => {
  it('sees a generation_params leaf as an override', () => {
    expect(sessionCarriesOverride(session({ generation_params: { temperature: 0.4 } }), 'behavior', 'temperature')).toBe(true);
  });

  it('does NOT treat an absent leaf as an override', () => {
    expect(sessionCarriesOverride(session(), 'behavior', 'temperature')).toBe(false);
  });

  it('treats a value EQUAL to the parent tier as an override anyway (the whole point)', () => {
    // The account default may also be 0.7. This is still "set on this chat".
    expect(sessionCarriesOverride(session({ generation_params: { temperature: 0.7 } }), 'behavior', 'temperature')).toBe(true);
  });

  it('treats a stored null as NOT an override — null is how a clear is represented', () => {
    expect(sessionCarriesOverride(session({ generation_params: { temperature: null } as never }), 'behavior', 'temperature')).toBe(false);
  });

  it('treats 0 and false as real overrides, not as absent', () => {
    expect(sessionCarriesOverride(session({ generation_params: { temperature: 0 } }), 'behavior', 'temperature')).toBe(true);
  });

  it('reads system_prompt off the dedicated column', () => {
    expect(sessionCarriesOverride(session({ system_prompt: 'x' }), 'behavior', 'system_prompt')).toBe(true);
    expect(sessionCarriesOverride(session({ system_prompt: '' }), 'behavior', 'system_prompt')).toBe(false);
    expect(sessionCarriesOverride(session({ system_prompt: null }), 'behavior', 'system_prompt')).toBe(false);
  });
});

describe('sessionCarriesOverride — grounding', () => {
  it('false is an OVERRIDE, not an absence — the tri-state must survive', () => {
    // `grounding_enabled: false` is precisely the interesting case: a naive falsy check
    // would report "inherited" and hide the clear button, stranding the user with
    // grounding off and no way to say "go back to following my account".
    expect(sessionCarriesOverride(session({ grounding_enabled: false }), 'grounding', 'grounding_enabled')).toBe(true);
    expect(sessionCarriesOverride(session({ grounding_enabled: true }), 'grounding', 'grounding_enabled')).toBe(true);
    expect(sessionCarriesOverride(session({ grounding_enabled: null }), 'grounding', 'grounding_enabled')).toBe(false);
    expect(sessionCarriesOverride(session(), 'grounding', 'grounding_enabled')).toBe(false);
  });

  it('project_ids is a session concept, not a cascading field', () => {
    expect(sessionCarriesOverride(session({ project_ids: ['p'] }), 'grounding', 'project_ids')).toBe(false);
  });
});

describe('sessionCarriesOverride — jsonb categories', () => {
  it('reads context_overrides / voice_overrides leaves', () => {
    expect(sessionCarriesOverride(session({ context_overrides: { mode: 'off' } }), 'context', 'mode')).toBe(true);
    expect(sessionCarriesOverride(session({ context_overrides: {} }), 'context', 'mode')).toBe(false);
    expect(sessionCarriesOverride(session(), 'context', 'mode')).toBe(false);
    expect(sessionCarriesOverride(session({ voice_overrides: { tts_voice_id: 'v' } }), 'voice', 'tts_voice_id')).toBe(true);
  });

  it('an unrelated leaf in the same blob is not this leaf', () => {
    expect(sessionCarriesOverride(session({ context_overrides: { trigger_ratio: 0.8 } }), 'context', 'mode')).toBe(false);
  });
});

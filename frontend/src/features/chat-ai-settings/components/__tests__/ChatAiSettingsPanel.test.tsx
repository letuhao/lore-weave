import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { ChatAiSettingsPanel } from '../ChatAiSettingsPanel';
import type { AiPrefsEditor } from '../../hooks/useAiPrefsEditor';
import type { EffectiveSettings } from '../../types';

const h = vi.hoisted(() => ({ ed: { current: null as AiPrefsEditor | null } }));
vi.mock('../../hooks/useAiPrefsEditor', () => ({ useAiPrefsEditor: () => h.ed.current }));
// DefaultModelsCard pulls auth + network; stub it (not under test here).
vi.mock('@/features/settings/DefaultModelsCard', () => ({ DefaultModelsCard: () => <div data-testid="default-models" /> }));

function eff(): EffectiveSettings {
  return {
    context_ref: { book_id: null, session_id: null },
    models: {
      chat: { effective_value: { model_source: 'user_model', model_ref: 'abcd1234ef' }, source_tier: 'account', tier_stack: {}, skipped: [] },
      composer: { effective_value: null, source_tier: 'no_model_configured', tier_stack: {}, skipped: [] },
    },
    behavior: {
      reasoning_effort: { effective_value: 'off', source_tier: 'system', tier_stack: {} },
      permission_mode: { effective_value: 'write', source_tier: 'system', tier_stack: {} },
      temperature: { effective_value: null, source_tier: null, tier_stack: {} },
      system_prompt: { effective_value: null, source_tier: null, tier_stack: {} },
    },
    grounding: {
      grounding_enabled: { effective_value: true, source_tier: 'system', tier_stack: {} },
    },
    voice: {},
    context: { mode: { effective_value: 'auto', source_tier: 'system', tier_stack: {} } },
  };
}

function makeEditor(over: Partial<AiPrefsEditor> = {}): AiPrefsEditor {
  return {
    prefs: { behavior: {}, grounding: {}, voice: {}, context: { mode: 'auto' }, version: 3 },
    effective: eff(),
    loading: false, saving: false, error: null,
    patch: vi.fn().mockResolvedValue(undefined),
    reload: vi.fn(),
    ...over,
  };
}

describe('ChatAiSettingsPanel', () => {
  beforeEach(() => { h.ed.current = makeEditor(); });

  it('shows the resolved model with its source tier (de-silenced)', () => {
    render(<ChatAiSettingsPanel />);
    expect(screen.getByText('Chat & drafting')).toBeInTheDocument();
    // the "system default" chips make the previously-silent behavior visible
    expect(screen.getAllByText('default').length).toBeGreaterThan(0);
    expect(screen.getByText('your default')).toBeInTheDocument();
    expect(screen.getByText('not set')).toBeInTheDocument(); // composer unset
  });

  it('editing reasoning effort patches the account prefs', () => {
    const patch = vi.fn().mockResolvedValue(undefined);
    h.ed.current = makeEditor({ patch });
    render(<ChatAiSettingsPanel />);
    fireEvent.click(screen.getByRole('button', { name: 'high' }));
    expect(patch).toHaveBeenCalledWith({ behavior: { reasoning_effort: 'high' } });
  });

  it('editing tool authority patches permission_mode', () => {
    const patch = vi.fn().mockResolvedValue(undefined);
    h.ed.current = makeEditor({ patch });
    render(<ChatAiSettingsPanel />);
    fireEvent.click(screen.getByRole('button', { name: 'ask' }));
    expect(patch).toHaveBeenCalledWith({ behavior: { permission_mode: 'ask' } });
  });

  it('toggling grounding off patches grounding_enabled and shows the warning', () => {
    const patch = vi.fn().mockResolvedValue(undefined);
    h.ed.current = makeEditor({ patch });
    render(<ChatAiSettingsPanel />);
    fireEvent.click(screen.getByRole('switch', { name: /ground answers/i }));
    expect(patch).toHaveBeenCalledWith({ grounding: { grounding_enabled: false } });
  });

  it('shows the memory-off warning when grounding is disabled', () => {
    const e = eff();
    e.grounding.grounding_enabled = { effective_value: false, source_tier: 'account', tier_stack: {} };
    h.ed.current = makeEditor({ effective: e });
    render(<ChatAiSettingsPanel />);
    expect(screen.getByText(/may invent lore as fact/i)).toBeInTheDocument();
  });

  it('switching long-work context mode to Off patches context.mode', () => {
    const patch = vi.fn().mockResolvedValue(undefined);
    h.ed.current = makeEditor({ patch });
    render(<ChatAiSettingsPanel />);
    fireEvent.click(screen.getByRole('button', { name: 'Off' }));
    expect(patch).toHaveBeenCalledWith({ context: { mode: 'off' } });
  });

  it('surfaces a save error (e.g. a 412 reload)', () => {
    h.ed.current = makeEditor({ error: 'settings changed on another device — reloaded' });
    render(<ChatAiSettingsPanel />);
    expect(screen.getByText(/another device/)).toBeInTheDocument();
  });
});

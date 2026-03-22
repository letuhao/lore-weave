import { beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import {
  AdvancedTranslationSettings,
  type AdvancedSettings,
} from './AdvancedTranslationSettings';

// ModelSelector makes real API calls — mock it
vi.mock('./ModelSelector', () => ({
  ModelSelector: ({ onChange }: { onChange: (v: { model_source: string; model_ref: string | null }) => void }) => (
    <div data-testid="model-selector">
      <button onClick={() => onChange({ model_source: 'user_model', model_ref: 'ref-123' })}>
        Select model
      </button>
    </div>
  ),
}));

const makeSettings = (overrides: Partial<AdvancedSettings> = {}): AdvancedSettings => ({
  compact_model_source:    null,
  compact_model_ref:       null,
  compact_system_prompt:   '',
  compact_user_prompt_tpl: '',
  chunk_size_tokens:       2000,
  invoke_timeout_secs:     300,
  ...overrides,
});

describe('AdvancedTranslationSettings', () => {
  beforeEach(() => { cleanup(); });

  // ── Structure ─────────────────────────────────────────────────────────────────

  it('renders "Advanced settings" summary', () => {
    render(
      <AdvancedTranslationSettings token="t" value={makeSettings()} onChange={vi.fn()} />,
    );
    expect(screen.getByText('Advanced settings')).toBeInTheDocument();
  });

  it('renders chunk size input', () => {
    render(
      <AdvancedTranslationSettings token="t" value={makeSettings()} onChange={vi.fn()} />,
    );
    expect(screen.getByLabelText(/Chunk size/)).toBeInTheDocument();
  });

  it('renders invoke timeout input', () => {
    render(
      <AdvancedTranslationSettings token="t" value={makeSettings()} onChange={vi.fn()} />,
    );
    expect(screen.getByLabelText(/AI timeout/)).toBeInTheDocument();
  });

  it('renders "Use same model" checkbox', () => {
    render(
      <AdvancedTranslationSettings token="t" value={makeSettings()} onChange={vi.fn()} />,
    );
    expect(screen.getByRole('checkbox')).toBeInTheDocument();
  });

  // ── Compact model prompts section ─────────────────────────────────────────────

  it('renders "Compact model prompts" disclosure', () => {
    render(
      <AdvancedTranslationSettings token="t" value={makeSettings()} onChange={vi.fn()} />,
    );
    expect(screen.getByText(/Compact model prompts/)).toBeInTheDocument();
  });

  it('compact prompt section is collapsed by default', () => {
    render(
      <AdvancedTranslationSettings token="t" value={makeSettings()} onChange={vi.fn()} />,
    );
    // Both <details> elements (outer "Advanced settings" + inner "Compact model prompts")
    // must be closed (no open attribute) by default.
    // Note: jsdom renders <details> children in the DOM regardless of open state,
    // so we check the element's .open property rather than counting textareas.
    const detailsElements = Array.from(document.querySelectorAll('details')) as HTMLDetailsElement[];
    expect(detailsElements.length).toBeGreaterThanOrEqual(1);
    detailsElements.forEach((d) => {
      expect(d.open).toBe(false);
    });
  });

  it('shows compact prompt hint referencing {history_text} when section is opened', () => {
    render(
      <AdvancedTranslationSettings token="t" value={makeSettings()} onChange={vi.fn()} />,
    );
    // Open the outer <details> first
    const outerSummary = screen.getByText('Advanced settings');
    fireEvent.click(outerSummary);
    // Open the compact prompts <details>
    const compactSummary = screen.getByText(/Compact model prompts/);
    fireEvent.click(compactSummary);
    expect(screen.getByText(/history_text/)).toBeInTheDocument();
  });

  it('does NOT show {chapter_text} hint inside compact prompt section', () => {
    render(
      <AdvancedTranslationSettings token="t" value={makeSettings()} onChange={vi.fn()} />,
    );
    const outerSummary = screen.getByText('Advanced settings');
    fireEvent.click(outerSummary);
    const compactSummary = screen.getByText(/Compact model prompts/);
    fireEvent.click(compactSummary);
    expect(screen.queryByText(/chapter_text/)).not.toBeInTheDocument();
  });

  // ── onChange with new fields ──────────────────────────────────────────────────

  it('onChange fires with compact_system_prompt when system textarea changes', () => {
    const onChange = vi.fn();
    render(
      <AdvancedTranslationSettings
        token="t"
        value={makeSettings()}
        onChange={onChange}
      />,
    );
    // Open both <details>
    fireEvent.click(screen.getByText('Advanced settings'));
    fireEvent.click(screen.getByText(/Compact model prompts/));

    const textareas = screen.getAllByRole('textbox') as HTMLTextAreaElement[];
    // First textarea = system prompt
    fireEvent.change(textareas[0], { target: { value: 'Custom compact sys' } });
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ compact_system_prompt: 'Custom compact sys' }),
    );
  });

  it('onChange fires with compact_user_prompt_tpl when user template textarea changes', () => {
    const onChange = vi.fn();
    render(
      <AdvancedTranslationSettings
        token="t"
        value={makeSettings()}
        onChange={onChange}
      />,
    );
    fireEvent.click(screen.getByText('Advanced settings'));
    fireEvent.click(screen.getByText(/Compact model prompts/));

    const textareas = screen.getAllByRole('textbox') as HTMLTextAreaElement[];
    // Second textarea = user prompt template
    fireEvent.change(textareas[1], { target: { value: '{history_text} summarise' } });
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ compact_user_prompt_tpl: '{history_text} summarise' }),
    );
  });

  it('onChange preserves other fields when compact prompts change', () => {
    const onChange = vi.fn();
    const settings = makeSettings({ chunk_size_tokens: 4000, invoke_timeout_secs: 120 });
    render(
      <AdvancedTranslationSettings token="t" value={settings} onChange={onChange} />,
    );
    fireEvent.click(screen.getByText('Advanced settings'));
    fireEvent.click(screen.getByText(/Compact model prompts/));

    const textareas = screen.getAllByRole('textbox') as HTMLTextAreaElement[];
    fireEvent.change(textareas[0], { target: { value: 'Sys' } });

    const emitted = onChange.mock.calls[0][0] as AdvancedSettings;
    expect(emitted.chunk_size_tokens).toBe(4000);
    expect(emitted.invoke_timeout_secs).toBe(120);
  });

  // ── chunk_size_tokens onChange ────────────────────────────────────────────────

  it('onChange fires with updated chunk_size_tokens', () => {
    const onChange = vi.fn();
    render(
      <AdvancedTranslationSettings token="t" value={makeSettings()} onChange={onChange} />,
    );
    fireEvent.click(screen.getByText('Advanced settings'));
    fireEvent.change(screen.getByLabelText(/Chunk size/), { target: { value: '3000' } });
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ chunk_size_tokens: 3000 }),
    );
  });

  it('chunk_size_tokens is floored at 100', () => {
    const onChange = vi.fn();
    render(
      <AdvancedTranslationSettings token="t" value={makeSettings()} onChange={onChange} />,
    );
    fireEvent.click(screen.getByText('Advanced settings'));
    fireEvent.change(screen.getByLabelText(/Chunk size/), { target: { value: '10' } });
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ chunk_size_tokens: 100 }),
    );
  });

  // ── Use same model toggle ─────────────────────────────────────────────────────

  it('checkbox is checked when compact model is null (same model)', () => {
    render(
      <AdvancedTranslationSettings
        token="t"
        value={makeSettings({ compact_model_source: null, compact_model_ref: null })}
        onChange={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByText('Advanced settings'));
    expect((screen.getByRole('checkbox') as HTMLInputElement).checked).toBe(true);
  });

  it('unchecking same-model sets compact_model_source to platform_model', () => {
    const onChange = vi.fn();
    render(
      <AdvancedTranslationSettings
        token="t"
        value={makeSettings({ compact_model_source: null, compact_model_ref: null })}
        onChange={onChange}
      />,
    );
    fireEvent.click(screen.getByText('Advanced settings'));
    fireEvent.click(screen.getByRole('checkbox'));
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ compact_model_source: 'platform_model', compact_model_ref: null }),
    );
  });
});

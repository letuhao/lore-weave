import { beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { PromptEditor } from './PromptEditor';

describe('PromptEditor', () => {
  beforeEach(() => { cleanup(); });

  // ── Rendering ────────────────────────────────────────────────────────────────

  it('renders System prompt label', () => {
    render(
      <PromptEditor
        systemPrompt=""
        userPromptTpl=""
        onSystemPromptChange={vi.fn()}
        onUserPromptTplChange={vi.fn()}
      />,
    );
    expect(screen.getByText('System prompt')).toBeInTheDocument();
  });

  it('renders User prompt template label', () => {
    render(
      <PromptEditor
        systemPrompt=""
        userPromptTpl=""
        onSystemPromptChange={vi.fn()}
        onUserPromptTplChange={vi.fn()}
      />,
    );
    expect(screen.getByText('User prompt template')).toBeInTheDocument();
  });

  it('shows current systemPrompt value', () => {
    render(
      <PromptEditor
        systemPrompt="You are a translator."
        userPromptTpl=""
        onSystemPromptChange={vi.fn()}
        onUserPromptTplChange={vi.fn()}
      />,
    );
    expect(screen.getByDisplayValue('You are a translator.')).toBeInTheDocument();
  });

  it('shows current userPromptTpl value', () => {
    render(
      <PromptEditor
        systemPrompt=""
        userPromptTpl="Translate: {chapter_text}"
        onSystemPromptChange={vi.fn()}
        onUserPromptTplChange={vi.fn()}
      />,
    );
    expect(screen.getByDisplayValue('Translate: {chapter_text}')).toBeInTheDocument();
  });

  // ── Default hint ──────────────────────────────────────────────────────────────

  it('shows default variables hint when hintOverride is not provided', () => {
    render(
      <PromptEditor
        systemPrompt=""
        userPromptTpl=""
        onSystemPromptChange={vi.fn()}
        onUserPromptTplChange={vi.fn()}
      />,
    );
    expect(screen.getByText(/\{source_lang\}/)).toBeInTheDocument();
    expect(screen.getByText(/\{chapter_text\}/)).toBeInTheDocument();
  });

  it('shows default hint when hintOverride is undefined', () => {
    render(
      <PromptEditor
        systemPrompt=""
        userPromptTpl=""
        onSystemPromptChange={vi.fn()}
        onUserPromptTplChange={vi.fn()}
        hintOverride={undefined}
      />,
    );
    expect(screen.getByText(/\{source_lang\}/)).toBeInTheDocument();
  });

  // ── hintOverride ──────────────────────────────────────────────────────────────

  it('renders hintOverride instead of default hint when provided', () => {
    render(
      <PromptEditor
        systemPrompt=""
        userPromptTpl=""
        onSystemPromptChange={vi.fn()}
        onUserPromptTplChange={vi.fn()}
        hintOverride={<p>Custom hint text</p>}
      />,
    );
    expect(screen.getByText('Custom hint text')).toBeInTheDocument();
    expect(screen.queryByText(/\{source_lang\}/)).not.toBeInTheDocument();
  });

  it('hintOverride suppresses {chapter_text} default hint', () => {
    render(
      <PromptEditor
        systemPrompt=""
        userPromptTpl=""
        onSystemPromptChange={vi.fn()}
        onUserPromptTplChange={vi.fn()}
        hintOverride={<span>Compact hint: {'{history_text}'}</span>}
      />,
    );
    expect(screen.getByText(/history_text/)).toBeInTheDocument();
    expect(screen.queryByText(/chapter_text/)).not.toBeInTheDocument();
  });

  it('hintOverride can render history_text hint for compact prompts', () => {
    render(
      <PromptEditor
        systemPrompt=""
        userPromptTpl=""
        onSystemPromptChange={vi.fn()}
        onUserPromptTplChange={vi.fn()}
        hintOverride={
          <p>Variable: {'{history_text}'} (required). Leave blank to use built-in defaults.</p>
        }
      />,
    );
    expect(screen.getByText(/history_text/)).toBeInTheDocument();
    expect(screen.getByText(/built-in defaults/)).toBeInTheDocument();
  });

  // ── onChange callbacks ────────────────────────────────────────────────────────

  it('calls onSystemPromptChange when system textarea changes', () => {
    const onSysChange = vi.fn();
    render(
      <PromptEditor
        systemPrompt=""
        userPromptTpl=""
        onSystemPromptChange={onSysChange}
        onUserPromptTplChange={vi.fn()}
      />,
    );
    const textareas = screen.getAllByRole('textbox');
    fireEvent.change(textareas[0], { target: { value: 'New system prompt' } });
    expect(onSysChange).toHaveBeenCalledWith('New system prompt');
  });

  it('calls onUserPromptTplChange when user template textarea changes', () => {
    const onTplChange = vi.fn();
    render(
      <PromptEditor
        systemPrompt=""
        userPromptTpl=""
        onSystemPromptChange={vi.fn()}
        onUserPromptTplChange={onTplChange}
      />,
    );
    const textareas = screen.getAllByRole('textbox');
    fireEvent.change(textareas[1], { target: { value: '{chapter_text}' } });
    expect(onTplChange).toHaveBeenCalledWith('{chapter_text}');
  });

  it('does not call onUserPromptTplChange when system textarea changes', () => {
    const onTplChange = vi.fn();
    render(
      <PromptEditor
        systemPrompt=""
        userPromptTpl=""
        onSystemPromptChange={vi.fn()}
        onUserPromptTplChange={onTplChange}
      />,
    );
    const textareas = screen.getAllByRole('textbox');
    fireEvent.change(textareas[0], { target: { value: 'changed' } });
    expect(onTplChange).not.toHaveBeenCalled();
  });

  // ── disabled ──────────────────────────────────────────────────────────────────

  it('both textareas are disabled when disabled=true', () => {
    render(
      <PromptEditor
        systemPrompt=""
        userPromptTpl=""
        onSystemPromptChange={vi.fn()}
        onUserPromptTplChange={vi.fn()}
        disabled
      />,
    );
    const textareas = screen.getAllByRole('textbox') as HTMLTextAreaElement[];
    expect(textareas[0].disabled).toBe(true);
    expect(textareas[1].disabled).toBe(true);
  });

  it('textareas are enabled when disabled is omitted', () => {
    render(
      <PromptEditor
        systemPrompt=""
        userPromptTpl=""
        onSystemPromptChange={vi.fn()}
        onUserPromptTplChange={vi.fn()}
      />,
    );
    const textareas = screen.getAllByRole('textbox') as HTMLTextAreaElement[];
    expect(textareas[0].disabled).toBe(false);
    expect(textareas[1].disabled).toBe(false);
  });
});

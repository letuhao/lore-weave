import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ComposeDraftForm } from '../ComposeDraftForm';

describe('ComposeDraftForm', () => {
  it('typing in the textarea calls onDraftChange', () => {
    const onDraftChange = vi.fn();
    render(
      <ComposeDraftForm
        draftText=""
        onDraftChange={onDraftChange}
        expandMode="rewrite"
        onExpandModeChange={vi.fn()}
      />,
    );
    fireEvent.change(screen.getByTestId('compose-draft-text'), { target: { value: '草稿' } });
    expect(onDraftChange).toHaveBeenCalledWith('草稿');
  });

  it('clicking add_only calls onExpandModeChange; rewrite is active by default', () => {
    const onExpandModeChange = vi.fn();
    render(
      <ComposeDraftForm
        draftText="x"
        onDraftChange={vi.fn()}
        expandMode="rewrite"
        onExpandModeChange={onExpandModeChange}
      />,
    );
    // rewrite is the active chip
    expect(screen.getByTestId('compose-expand-rewrite').className).toContain('border-primary');
    fireEvent.click(screen.getByTestId('compose-expand-add_only'));
    expect(onExpandModeChange).toHaveBeenCalledWith('add_only');
  });
});

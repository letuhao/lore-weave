// RAID C1 — SteeringEditor: mode switch shows/hides match_pattern, the auto v1-honesty note,
// the body char counter + over-cap disable, and the submitted payload shape.
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { SteeringEditor } from '../SteeringEditor';

const noop = () => {};

describe('SteeringEditor', () => {
  it('hides match_pattern until mode = scene_match', () => {
    render(<SteeringEditor initial={null} saving={false} errorKind={null} onSubmit={noop} onCancel={noop} />);
    expect(screen.queryByTestId('steering-form-match-pattern')).toBeNull();
    fireEvent.change(screen.getByTestId('steering-form-mode'), { target: { value: 'scene_match' } });
    expect(screen.getByTestId('steering-form-match-pattern')).toBeTruthy();
  });

  it('shows the auto v1-honesty note only for mode = auto', () => {
    render(<SteeringEditor initial={null} saving={false} errorKind={null} onSubmit={noop} onCancel={noop} />);
    expect(screen.queryByTestId('steering-form-auto-note')).toBeNull();
    fireEvent.change(screen.getByTestId('steering-form-mode'), { target: { value: 'auto' } });
    expect(screen.getByTestId('steering-form-auto-note')).toBeTruthy();
  });

  it('renders the char counter and disables save when the body exceeds 8000', () => {
    render(<SteeringEditor initial={null} saving={false} errorKind={null} onSubmit={noop} onCancel={noop} />);
    fireEvent.change(screen.getByTestId('steering-form-name'), { target: { value: 'Tone' } });
    const body = screen.getByTestId('steering-form-body');
    const counter = screen.getByTestId('steering-form-body-count');
    expect(counter).toBeTruthy();
    fireEvent.change(body, { target: { value: 'a'.repeat(8001) } });
    // Over-cap: counter flags destructive + save disabled (the number itself is i18n-interpolated,
    // which the key-returning test mock doesn't fill — assert the behavior, not the rendered count).
    expect(counter.className).toContain('text-destructive');
    expect((screen.getByTestId('steering-form-save') as HTMLButtonElement).disabled).toBe(true);
  });

  it('disables save while name or body is empty', () => {
    render(<SteeringEditor initial={null} saving={false} errorKind={null} onSubmit={noop} onCancel={noop} />);
    expect((screen.getByTestId('steering-form-save') as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(screen.getByTestId('steering-form-name'), { target: { value: 'Tone' } });
    fireEvent.change(screen.getByTestId('steering-form-body'), { target: { value: 'Keep it terse.' } });
    expect((screen.getByTestId('steering-form-save') as HTMLButtonElement).disabled).toBe(false);
  });

  it('submits a normalized payload; scene_match carries the pattern, others null it', () => {
    const onSubmit = vi.fn();
    render(<SteeringEditor initial={null} saving={false} errorKind={null} onSubmit={onSubmit} onCancel={noop} />);
    fireEvent.change(screen.getByTestId('steering-form-name'), { target: { value: '  Tone  ' } });
    fireEvent.change(screen.getByTestId('steering-form-body'), { target: { value: 'Keep it terse.' } });
    fireEvent.change(screen.getByTestId('steering-form-mode'), { target: { value: 'scene_match' } });
    fireEvent.change(screen.getByTestId('steering-form-match-pattern'), { target: { value: 'battle' } });
    fireEvent.click(screen.getByTestId('steering-form-save'));
    expect(onSubmit).toHaveBeenCalledWith({
      name: 'Tone', body: 'Keep it terse.', inclusion_mode: 'scene_match', match_pattern: 'battle', enabled: true,
    });
  });

  it('seeds fields from an existing entry (edit mode)', () => {
    render(
      <SteeringEditor
        initial={{
          id: 'e1', book_id: 'b1', name: 'Voice', body: 'First person.', inclusion_mode: 'manual',
          match_pattern: null, enabled: false, author_user_id: 'u1', created_at: '', updated_at: '',
        }}
        saving={false} errorKind={null} onSubmit={noop} onCancel={noop}
      />,
    );
    expect((screen.getByTestId('steering-form-name') as HTMLInputElement).value).toBe('Voice');
    expect((screen.getByTestId('steering-form-mode') as HTMLSelectElement).value).toBe('manual');
    expect((screen.getByTestId('steering-form-enabled') as HTMLInputElement).checked).toBe(false);
  });

  it('renders a classified error message', () => {
    render(<SteeringEditor initial={null} saving={false} errorKind="duplicate" onSubmit={noop} onCancel={noop} />);
    expect(screen.getByTestId('steering-form-error').textContent).toBe('steering.error.duplicate');
  });
});

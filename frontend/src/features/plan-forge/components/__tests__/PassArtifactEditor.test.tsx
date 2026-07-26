import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { PassArtifactEditor } from '../PassArtifactEditor';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (_k: string, o?: { defaultValue?: string }) => o?.defaultValue ?? _k }),
}));

describe('PassArtifactEditor (structured checkpoint edits)', () => {
  it('cast: edits a name and sends the whole roster', () => {
    const onSave = vi.fn();
    render(<PassArtifactEditor kind="cast_plan" content={{ cast: [{ name: 'Alice', role: 'lead' }] }} busy={false} onSave={onSave} onCancel={vi.fn()} />);
    fireEvent.change(screen.getByTestId('edit-cast-0-name'), { target: { value: 'Alicia' } });
    fireEvent.click(screen.getByTestId('edit-save'));
    expect(onSave).toHaveBeenCalledWith({ cast: [{ name: 'Alicia', role: 'lead' }] });
  });

  it('cast: reads a roster-keyed artifact too (cast|roster tolerance)', () => {
    render(<PassArtifactEditor kind="cast_plan" content={{ roster: [{ name: 'Bo' }] }} busy={false} onSave={vi.fn()} onCancel={vi.fn()} />);
    expect((screen.getByTestId('edit-cast-0-name') as HTMLInputElement).value).toBe('Bo');
  });

  it('add + remove change the emitted list length', () => {
    const onSave = vi.fn();
    render(<PassArtifactEditor kind="cast_plan" content={{ cast: [{ name: 'A' }, { name: 'B' }] }} busy={false} onSave={onSave} onCancel={vi.fn()} />);
    fireEvent.click(screen.getByTestId('edit-remove-0')); // drop A
    fireEvent.click(screen.getByTestId('edit-add-row'));
    fireEvent.change(screen.getByTestId('edit-cast-1-name'), { target: { value: 'C' } });
    fireEvent.click(screen.getByTestId('edit-save'));
    // B kept as-is; the added row carries the (blank) columns it was created with.
    expect(onSave).toHaveBeenCalledWith({ cast: [{ name: 'B' }, { name: 'C', role: '', trait: '' }] });
  });

  it('drops fully-empty rows so a blank add never ships', () => {
    const onSave = vi.fn();
    render(<PassArtifactEditor kind="cast_plan" content={{ cast: [{ name: 'A' }] }} busy={false} onSave={onSave} onCancel={vi.fn()} />);
    fireEvent.click(screen.getByTestId('edit-add-row')); // an all-blank row
    fireEvent.click(screen.getByTestId('edit-save'));
    expect(onSave).toHaveBeenCalledWith({ cast: [{ name: 'A' }] });
  });

  it('preserves non-column fields (e.g. ids) on a beat row', () => {
    const onSave = vi.fn();
    render(<PassArtifactEditor kind="beat_plan" content={{ beats: [{ id: 'b1', beat: 'Open', tension: '3' }] }} busy={false} onSave={onSave} onCancel={vi.fn()} />);
    fireEvent.change(screen.getByTestId('edit-beats-0-beat'), { target: { value: 'Opening' } });
    fireEvent.click(screen.getByTestId('edit-save'));
    expect(onSave).toHaveBeenCalledWith({ beats: [{ id: 'b1', beat: 'Opening', tension: '3' }] });
  });

  it('an unknown kind renders nothing (no editor)', () => {
    const { container } = render(<PassArtifactEditor kind="motif_plan" content={{}} busy={false} onSave={vi.fn()} onCancel={vi.fn()} />);
    expect(container.firstChild).toBeNull();
  });
});

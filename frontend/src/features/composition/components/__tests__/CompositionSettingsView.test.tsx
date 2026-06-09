import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { CompositionSettingsView } from '../CompositionSettingsView';

// vi.hoisted: vi.mock factories hoist above top-level consts.
const { mockSet } = vi.hoisted(() => ({ mockSet: { mutate: vi.fn(), isPending: false, isError: false } }));
vi.mock('../../hooks/useWork', () => ({ useSetWorkSettings: () => mockSet }));

const MODELS = [
  { user_model_id: 'm1', alias: 'Fast', provider_model_name: 'qwen-9b' },
  { user_model_id: 'm2', alias: null, provider_model_name: 'qwen-35b' },
];

beforeEach(() => {
  mockSet.mutate = vi.fn();
  mockSet.isPending = false;
  mockSet.isError = false;
});

const base = { projectId: 'p', bookId: 'b', models: MODELS, token: 'tok' };
const cb = () => screen.getByTestId('composition-settings-narrative-thread') as HTMLInputElement;

describe('CompositionSettingsView (FE work settings)', () => {
  it('reflects the persisted settings as initial values', () => {
    render(<CompositionSettingsView {...base} settings={{
      narrative_thread_enabled: true, assembly_mode: 'chapter', default_model_ref: 'm2',
    }} />);
    expect(cb().checked).toBe(true);
    expect((screen.getByTestId('composition-settings-assembly-mode') as HTMLSelectElement).value).toBe('chapter');
    expect((screen.getByTestId('composition-settings-default-model') as HTMLSelectElement).value).toBe('m2');
  });

  it('defaults sanely when settings are empty (toggle off, per_scene, no default model)', () => {
    render(<CompositionSettingsView {...base} settings={{}} />);
    expect(cb().checked).toBe(false);
    expect((screen.getByTestId('composition-settings-assembly-mode') as HTMLSelectElement).value).toBe('per_scene');
    expect((screen.getByTestId('composition-settings-default-model') as HTMLSelectElement).value).toBe('');
  });

  it('toggling narrative_thread MERGES the patch (never drops the other keys)', () => {
    render(<CompositionSettingsView {...base} settings={{ critic_model_ref: 'x', assembly_mode: 'chapter' }} />);
    fireEvent.click(cb());
    expect(mockSet.mutate).toHaveBeenCalledWith({
      projectId: 'p',
      currentSettings: { critic_model_ref: 'x', assembly_mode: 'chapter' },
      patch: { narrative_thread_enabled: true },
    });
  });

  it('turning the toggle OFF sends narrative_thread_enabled:false (not a drop)', () => {
    render(<CompositionSettingsView {...base} settings={{ narrative_thread_enabled: true }} />);
    fireEvent.click(cb());
    expect(mockSet.mutate).toHaveBeenCalledWith(expect.objectContaining({
      patch: { narrative_thread_enabled: false },
    }));
  });

  it('changing the default model patches default_model_ref', () => {
    render(<CompositionSettingsView {...base} settings={{}} />);
    fireEvent.change(screen.getByTestId('composition-settings-default-model'), { target: { value: 'm1' } });
    expect(mockSet.mutate).toHaveBeenCalledWith(expect.objectContaining({ patch: { default_model_ref: 'm1' } }));
  });

  it('changing assembly mode patches assembly_mode', () => {
    render(<CompositionSettingsView {...base} settings={{}} />);
    fireEvent.change(screen.getByTestId('composition-settings-assembly-mode'), { target: { value: 'chapter' } });
    expect(mockSet.mutate).toHaveBeenCalledWith(expect.objectContaining({ patch: { assembly_mode: 'chapter' } }));
  });

  it('disables the controls while a save is pending', () => {
    mockSet.isPending = true;
    render(<CompositionSettingsView {...base} settings={{}} />);
    expect(cb().disabled).toBe(true);
    expect((screen.getByTestId('composition-settings-default-model') as HTMLSelectElement).disabled).toBe(true);
  });

  it('shows an error when the save failed', () => {
    mockSet.isError = true;
    render(<CompositionSettingsView {...base} settings={{}} />);
    expect(screen.getByTestId('composition-settings-error')).toBeTruthy();
  });
});

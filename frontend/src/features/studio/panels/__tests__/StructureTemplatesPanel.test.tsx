// S-01 · StructureTemplatesPanel unit tests. The panel is a pure view over useStructureTemplates —
// mock the controller and assert the wiring (built-in vs own branching, the clone/save/archive
// affordances, the blank-name Save guard). The end-to-end behaviour is covered by the live
// browser journey; this locks the render logic without a real backend.
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (_k: string, o?: { defaultValue?: string }) => o?.defaultValue ?? _k }),
}));
vi.mock('../useStudioPanel', () => ({ useStudioPanel: () => 'Structure Templates' }));

const state = vi.hoisted(() => ({ value: {} as Record<string, unknown> }));
vi.mock('../useStructureTemplates', () => ({ useStructureTemplates: () => state.value }));

import { StructureTemplatesPanel } from '../StructureTemplatesPanel';
import type { StructureTemplate } from '@/features/composition/types';

const builtin: StructureTemplate = { id: 'b1', name: 'Save the Cat', kind: 'save_the_cat', owner_user_id: null, beats: [{ key: 'setup', label: 'Setup', purpose: 'p', order: 1 }] };
const mine: StructureTemplate = { id: 'm1', name: 'My Struct', kind: 'generic', owner_user_id: 'u1', version: 3, is_archived: false, beats: [{ key: 'a', label: 'A', purpose: 'pa', order: 1 }] };
const archived: StructureTemplate = { ...mine, id: 'm2', name: 'Archived One', is_archived: true };

function base(over: Record<string, unknown> = {}) {
  return {
    builtins: [builtin], mine: [mine], isLoading: false, error: null,
    selectedId: null, select: vi.fn(), selected: null,
    cloning: false, clone: vi.fn(), saving: false, saveError: null, save: vi.fn(),
    showArchived: false, setShowArchived: vi.fn(), archive: vi.fn(), restore: vi.fn(),
    ...over,
  };
}
const props = { api: {} } as never;

describe('StructureTemplatesPanel', () => {
  it('lists built-ins and own templates with badges', () => {
    state.value = base();
    render(<StructureTemplatesPanel {...props} />);
    expect(screen.getByText('Save the Cat')).toBeInTheDocument();
    expect(screen.getByText('My Struct')).toBeInTheDocument();
    expect(screen.getByText('system')).toBeInTheDocument();
    expect(screen.getByText('mine')).toBeInTheDocument();
  });

  it('a selected BUILT-IN is read-only with a clone CTA (no editor)', () => {
    const clone = vi.fn();
    state.value = base({ selectedId: 'b1', selected: builtin, clone });
    render(<StructureTemplatesPanel {...props} />);
    expect(screen.getByTestId('structtpl-readonly-note')).toBeInTheDocument();
    expect(screen.queryByTestId('structtpl-beat-editor')).toBeNull();
    fireEvent.click(screen.getByTestId('structtpl-clone'));
    expect(clone).toHaveBeenCalledWith('b1');
  });

  it('a selected OWN template shows the beat EDITOR + Save', () => {
    state.value = base({ selectedId: 'm1', selected: mine });
    render(<StructureTemplatesPanel {...props} />);
    expect(screen.getByTestId('structtpl-beat-editor')).toBeInTheDocument();
    expect(screen.queryByTestId('structtpl-readonly-note')).toBeNull();
    expect(screen.getByTestId('structtpl-save')).toBeEnabled();
    expect(screen.getByTestId('structtpl-archive')).toBeInTheDocument();
  });

  it('Save is DISABLED when the name is blanked (the empty-name guard)', () => {
    state.value = base({ selectedId: 'm1', selected: mine });
    render(<StructureTemplatesPanel {...props} />);
    fireEvent.change(screen.getByTestId('structtpl-name'), { target: { value: '   ' } });
    expect(screen.getByTestId('structtpl-save')).toBeDisabled();
  });

  it('an archived own template shows Restore, not the editor (no dead-end)', () => {
    const restore = vi.fn();
    state.value = base({ selectedId: 'm2', selected: archived, restore });
    render(<StructureTemplatesPanel {...props} />);
    expect(screen.getByTestId('structtpl-archived-note')).toBeInTheDocument();
    expect(screen.queryByTestId('structtpl-beat-editor')).toBeNull();
    fireEvent.click(screen.getByTestId('structtpl-restore'));
    expect(restore).toHaveBeenCalledWith('m2');
  });

  it('save sends only edited fields with the current version (OCC)', () => {
    const save = vi.fn();
    state.value = base({ selectedId: 'm1', selected: mine, save });
    render(<StructureTemplatesPanel {...props} />);
    fireEvent.change(screen.getByTestId('structtpl-name'), { target: { value: 'Renamed' } });
    fireEvent.click(screen.getByTestId('structtpl-save'));
    expect(save).toHaveBeenCalledWith('m1', 3, expect.objectContaining({ name: 'Renamed' }));
  });
});

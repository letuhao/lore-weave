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
    // S-01b — create-from-scratch + kind
    isCreating: false, startCreate: vi.fn(), cancelCreate: vi.fn(), creating: false, create: vi.fn(),
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
    expect(screen.getByText('built-in')).toBeInTheDocument();   // E3 — "built-in", not "system"
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

  // ── S-01b slice 2: create-from-scratch on-ramp + editable kind ──
  it('the "+ New structure" button starts create-mode (B1 on-ramp)', () => {
    const startCreate = vi.fn();
    state.value = base({ startCreate });
    render(<StructureTemplatesPanel {...props} />);
    fireEvent.click(screen.getByTestId('structtpl-new'));
    expect(startCreate).toHaveBeenCalled();
  });

  it('create-mode shows a blank editor with Create + Cancel (no Archive), and blank-name blocks Create', () => {
    state.value = base({ isCreating: true, selected: null });
    render(<StructureTemplatesPanel {...props} />);
    expect(screen.getByTestId('structtpl-beat-editor')).toBeInTheDocument();
    expect(screen.getByTestId('structtpl-cancel')).toBeInTheDocument();
    expect(screen.queryByTestId('structtpl-archive')).toBeNull();
    // blank draft name → Create disabled (the empty-name guard)
    expect(screen.getByTestId('structtpl-save')).toBeDisabled();
  });

  it('create sends name + kind + beats (B1/B2)', () => {
    const create = vi.fn();
    state.value = base({ isCreating: true, selected: null, create });
    render(<StructureTemplatesPanel {...props} />);
    fireEvent.change(screen.getByTestId('structtpl-name'), { target: { value: 'My Thriller' } });
    fireEvent.change(screen.getByTestId('structtpl-kind'), { target: { value: 'thriller' } });
    fireEvent.click(screen.getByTestId('structtpl-save'));
    expect(create).toHaveBeenCalledWith(expect.objectContaining({ name: 'My Thriller', kind: 'thriller' }));
  });

  it('editable kind is saved on an own template (B2)', () => {
    const save = vi.fn();
    state.value = base({ selectedId: 'm1', selected: mine, save });
    render(<StructureTemplatesPanel {...props} />);
    fireEvent.change(screen.getByTestId('structtpl-kind'), { target: { value: 'noir' } });
    fireEvent.click(screen.getByTestId('structtpl-save'));
    expect(save).toHaveBeenCalledWith('m1', 3, expect.objectContaining({ kind: 'noir' }));
  });

  // ── S-01b slice 3: safety layer ──
  it('archiving is gated by a confirm — the first click does NOT archive (C4)', () => {
    const archive = vi.fn();
    state.value = base({ selectedId: 'm1', selected: mine, archive });
    render(<StructureTemplatesPanel {...props} />);
    fireEvent.click(screen.getByTestId('structtpl-archive'));
    expect(archive).not.toHaveBeenCalled();
    expect(screen.getByText('Archive this structure?')).toBeInTheDocument();
  });

  it('a clean editor shows no Unsaved marker; editing reveals it (C1)', () => {
    state.value = base({ selectedId: 'm1', selected: mine });
    render(<StructureTemplatesPanel {...props} />);
    expect(screen.queryByTestId('structtpl-dirty')).toBeNull();
    fireEvent.change(screen.getByTestId('structtpl-name'), { target: { value: 'Edited name' } });
    expect(screen.getByTestId('structtpl-dirty')).toBeInTheDocument();
    expect(screen.getByTestId('structtpl-discard')).toBeInTheDocument();
  });

  it('switching rows while dirty is guarded by a discard confirm — select is NOT called yet (C1)', () => {
    const select = vi.fn();
    state.value = base({ selectedId: 'm1', selected: mine, select });
    render(<StructureTemplatesPanel {...props} />);
    fireEvent.change(screen.getByTestId('structtpl-name'), { target: { value: 'Edited' } });
    fireEvent.click(screen.getByText('Save the Cat'));   // try to switch to the built-in row
    expect(select).not.toHaveBeenCalled();
    expect(screen.getByText('Discard unsaved changes?')).toBeInTheDocument();
  });

  it('Discard resets the draft (clears the Unsaved marker) (C1)', () => {
    state.value = base({ selectedId: 'm1', selected: mine });
    render(<StructureTemplatesPanel {...props} />);
    fireEvent.change(screen.getByTestId('structtpl-name'), { target: { value: 'Edited' } });
    fireEvent.click(screen.getByTestId('structtpl-discard'));
    expect(screen.queryByTestId('structtpl-dirty')).toBeNull();
  });

  // ── S-01b slice 4: the A1 interim decompose hint (no silent dead-end) ──
  it('an own template shows the honest "how to use / decompose" hint (A1 interim)', () => {
    state.value = base({ selectedId: 'm1', selected: mine });
    render(<StructureTemplatesPanel {...props} />);
    expect(screen.getByTestId('structtpl-decompose-hint')).toBeInTheDocument();
  });

  // ── completeness-audit fixes ──
  it('create-mode is dirty-guarded too: typing a draft then clicking a row is intercepted (C1 gap fix)', () => {
    const select = vi.fn();
    state.value = base({ isCreating: true, selected: null, select });
    render(<StructureTemplatesPanel {...props} />);
    fireEvent.change(screen.getByTestId('structtpl-name'), { target: { value: 'Draft in progress' } });
    fireEvent.click(screen.getByText('Save the Cat'));   // try to leave the dirty new draft
    expect(select).not.toHaveBeenCalled();
    expect(screen.getByText('Discard unsaved changes?')).toBeInTheDocument();
  });

  it('the "+ New structure" button is a no-op while already creating (no misleading discard confirm)', () => {
    const startCreate = vi.fn();
    state.value = base({ isCreating: true, selected: null, startCreate });
    render(<StructureTemplatesPanel {...props} />);
    fireEvent.click(screen.getByTestId('structtpl-new'));
    expect(startCreate).not.toHaveBeenCalled();
  });
});

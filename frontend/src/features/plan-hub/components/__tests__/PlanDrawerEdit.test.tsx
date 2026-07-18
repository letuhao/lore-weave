// 24 PH16/PH20 — the drawer's EDIT surface. "The drawer edits the DESIRED state; Open in Editor
// goes to the ACTUAL."
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { NODE_STATUSES, PlanDrawerEdit } from '../PlanDrawerEdit';
import type { OutlineNode } from '@/features/composition/types';

const node = (o: Partial<OutlineNode> = {}): OutlineNode =>
  ({
    id: 'n1',
    kind: 'scene',
    project_id: 'p',
    parent_id: 'ch-1',
    rank: 'm',
    title: 'The Summons',
    chapter_id: 'bc-1',
    story_order: 1001,
    status: 'outline',
    synopsis: '',
    goal: '',
    version: 7,
    is_archived: false,
    beat_role: null,
    tension: 55,
    ...o,
  }) as OutlineNode;

const chapters = [
  { chapter_id: 'bc-1', title: 'Chapter One', sort_order: 1 },
  { chapter_id: 'bc-2', title: 'Chapter Two', sort_order: 2 },
];

function setup(o: Partial<OutlineNode> = {}) {
  const props = {
    node: node(o),
    chapters,
    onEdit: vi.fn(),
    onArchive: vi.fn(),
    onRestore: vi.fn(),
    onOpenInEditor: vi.fn(),
    saving: false,
  };
  render(<PlanDrawerEdit {...props} />);
  return props;
}

describe('PlanDrawerEdit (PH20)', () => {
  it('renames on blur — NOT on every keystroke', () => {
    // A per-keystroke write would bump `version` on each character and then 412 itself on the next.
    const { onEdit } = setup();
    const input = screen.getByTestId('plan-drawer-edit-title');
    fireEvent.change(input, { target: { value: 'A New Name' } });
    expect(onEdit).not.toHaveBeenCalled(); // still typing
    fireEvent.blur(input);
    expect(onEdit).toHaveBeenCalledWith({ title: 'A New Name' });
  });

  it('does not write when the value is unchanged', () => {
    const { onEdit } = setup();
    fireEvent.blur(screen.getByTestId('plan-drawer-edit-title'));
    expect(onEdit).not.toHaveBeenCalled();
  });

  it('status is a CLOSED SET mirroring the server enum — never a free-text box', () => {
    setup();
    const select = screen.getByTestId('plan-drawer-edit-status') as HTMLSelectElement;
    expect(select.tagName).toBe('SELECT');
    const values = [...select.options].map((o) => o.value);
    for (const s of NODE_STATUSES) expect(values).toContain(s);
    expect(NODE_STATUSES).toEqual(['empty', 'outline', 'drafting', 'done']); // == models.py
  });

  it('an UNKNOWN server status renders as itself — it must not silently snap to option 1', () => {
    // If the server gains a status this build doesn't know, a plain <select> would show the FIRST
    // option as selected and then WRITE that value on the next change — a silent downgrade.
    setup({ status: 'reviewing' as OutlineNode['status'] });
    const select = screen.getByTestId('plan-drawer-edit-status') as HTMLSelectElement;
    expect(select.value).toBe('reviewing');
  });

  it('tension commits on BLUR, not per keystroke - else it 412s ITSELF', () => {
    // It used to write on every onChange. Typing "45" fired TWO PATCHes, and the second carried the
    // pre-write `version` -> 412 -> "that node changed elsewhere", blaming a phantom collaborator
    // for your own keystroke (`instant-commit-control-over-occ-entity`).
    const { onEdit } = setup();
    const input = screen.getByTestId('plan-drawer-edit-tension');
    fireEvent.change(input, { target: { value: '45' } });
    expect(onEdit).not.toHaveBeenCalled();
    fireEvent.blur(input);
    expect(onEdit).toHaveBeenCalledTimes(1);
    expect(onEdit).toHaveBeenCalledWith({ tension: 45 });
  });

  it('an empty tension writes NULL, not 0', () => {
    // "unset" and "zero tension" are different facts; the sparkline reads them differently.
    const { onEdit } = setup();
    const input = screen.getByTestId('plan-drawer-edit-tension');
    fireEvent.change(input, { target: { value: '' } });
    fireEvent.blur(input);
    expect(onEdit).toHaveBeenCalledWith({ tension: null });
  });

  it('clamps tension into 0..100', () => {
    const { onEdit } = setup();
    const input = screen.getByTestId('plan-drawer-edit-tension');
    fireEvent.change(input, { target: { value: '400' } });
    fireEvent.blur(input);
    expect(onEdit).toHaveBeenCalledWith({ tension: 100 });
  });

  it('a FAILED chapter-spine read disables the picker and SAYS so - never a false "not anchored"', () => {
    // With an empty list the select would show "- not anchored -" as the selected option for an
    // ANCHORED node: a confident lie about its state, with Open-in-Editor still enabled.
    render(
      <PlanDrawerEdit
        node={node()}
        chapters={[]}
        chaptersError
        onEdit={vi.fn()}
        onArchive={vi.fn()}
        onRestore={vi.fn()}
        onOpenInEditor={vi.fn()}
        saving={false}
      />,
    );
    expect(screen.getByTestId('plan-drawer-anchor-error')).toBeTruthy();
    expect((screen.getByTestId('plan-drawer-edit-anchor') as HTMLSelectElement).disabled).toBe(true);
    expect(screen.queryByTestId('plan-drawer-no-anchor')).toBeNull(); // it IS anchored; don't lie
  });

  it('⚓ re-anchors to another chapter (BPS-13)', () => {
    const { onEdit } = setup();
    fireEvent.change(screen.getByTestId('plan-drawer-edit-anchor'), { target: { value: 'bc-2' } });
    expect(onEdit).toHaveBeenCalledWith({ chapter_id: 'bc-2' });
  });

  it('un-anchoring writes NULL, and the un-anchored state is CALLED OUT', () => {
    const { onEdit } = setup({ chapter_id: null });
    expect(screen.getByTestId('plan-drawer-no-anchor')).toBeTruthy();
    fireEvent.change(screen.getByTestId('plan-drawer-edit-anchor'), { target: { value: '' } });
    expect(onEdit).toHaveBeenCalledWith({ chapter_id: null });
  });

  it('"Open in Editor" goes to the ACTUAL (the manuscript chapter)', () => {
    const { onOpenInEditor } = setup();
    fireEvent.click(screen.getByTestId('plan-drawer-open-editor'));
    expect(onOpenInEditor).toHaveBeenCalledWith('bc-1');
  });

  it('with NO anchor there is nowhere to go — the button is visible but disabled, never dead', () => {
    const { onOpenInEditor } = setup({ chapter_id: null });
    const btn = screen.getByTestId('plan-drawer-open-editor') as HTMLButtonElement;
    expect(btn.disabled).toBe(true); // PH7's visible-fallback, not a hidden control
    fireEvent.click(btn);
    expect(onOpenInEditor).not.toHaveBeenCalled();
  });

  it('archive is offered on a live node; restore on an archived one — never both', () => {
    const { onArchive } = setup();
    expect(screen.queryByTestId('plan-drawer-restore')).toBeNull();
    fireEvent.click(screen.getByTestId('plan-drawer-archive'));
    expect(onArchive).toHaveBeenCalled();
  });

  it('an archived node offers RESTORE (the verified inverse — that is what makes archive Tier-A)', () => {
    const { onRestore } = setup({ is_archived: true });
    expect(screen.queryByTestId('plan-drawer-archive')).toBeNull();
    fireEvent.click(screen.getByTestId('plan-drawer-restore'));
    expect(onRestore).toHaveBeenCalled();
  });

  it('every control is disabled while a write is in flight', () => {
    render(
      <PlanDrawerEdit
        node={node()}
        chapters={chapters}
        onEdit={vi.fn()}
        onArchive={vi.fn()}
        onRestore={vi.fn()}
        onOpenInEditor={vi.fn()}
        saving
      />,
    );
    expect((screen.getByTestId('plan-drawer-edit-title') as HTMLInputElement).disabled).toBe(true);
    expect((screen.getByTestId('plan-drawer-edit-status') as HTMLSelectElement).disabled).toBe(true);
    expect((screen.getByTestId('plan-drawer-archive') as HTMLButtonElement).disabled).toBe(true);
  });
});

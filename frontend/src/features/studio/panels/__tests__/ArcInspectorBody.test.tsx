// 32 arc-inspector — the shared body is OPERABLE: it renders every section, commits an edit through
// the OCC `edit`, and degrades honestly (loading / archived / empty). Driven by a mock
// ArcInspectorState so the view is tested in isolation from react-query/bus.
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';

// S-10 O6a — the body now mounts the "Save as template" action (its own react-query mutation). Stub it
// so this stays a render-only ISOLATION test (no QueryClient); the widget has its own test.
vi.mock('@/features/composition/motif/components/ArcExtractTemplateAction', () => ({
  ArcExtractTemplateAction: () => <div data-testid="arc-extract-template-action" />,
}));

import { ArcInspectorBody } from '../ArcInspectorBody';
import type { ArcInspectorState } from '../useArcInspector';
import type { ArcDetail } from '@/features/plan-hub/types';

function makeDetail(over: Partial<ArcDetail> = {}): ArcDetail {
  return {
    id: 'arc1', kind: 'arc', parent_id: 'saga1', depth: 1, rank: '0m', title: 'The Betrayal',
    status: 'drafting', goal: 'She must choose.', summary: 'Cold Harbor falls.', version: 7,
    span: { from_order: 41, to_order: 58 }, first_story_order: 41000, is_contiguous: false, chapter_count: 18,
    is_archived: false, tracks: [{ key: 'revenge', label: 'Revenge line' }], roster: [],
    resolved: {
      tracks: [{ key: 'revenge', label: 'Revenge line' }, { key: 'romance', label: 'Cold Harbor girl' }],
      roster: [], roster_bindings: {},
    },
    open_promises: [{ id: 'p1', kind: 'promise', text: "the sword's true owner" }],
    ...over,
  };
}

function makeState(over: Partial<ArcInspectorState> = {}): ArcInspectorState {
  return {
    arcId: 'arc1', select: vi.fn(), shell: [], detail: makeDetail(), loading: false, error: null,
    saving: false, writeError: null, edit: vi.fn(), archive: vi.fn(), restore: vi.fn(),
    ancestors: [], blastRadius: 2, token: 't', ...over,
  };
}

describe('ArcInspectorBody', () => {
  it('renders every section and the dense-ranked span (not raw)', () => {
    render(<ArcInspectorBody state={makeState()} />);
    expect(screen.getByTestId('arc-f-title')).toHaveValue('The Betrayal');
    // the span range renders raw (numbers survive i18n); the "Chapters" label is now a t() key.
    expect(screen.getByTestId('arc-chapters').textContent).toContain('41–58');
    expect(screen.getByTestId('arc-noncontiguous')).toBeInTheDocument();
    expect(screen.getByTestId('arc-promises')).toBeInTheDocument();
    expect(screen.getByTestId('arc-blast')).toBeInTheDocument();   // blast shows when blastRadius > 0
  });

  it('marks an inherited track (override) distinctly from an own track (remove)', () => {
    render(<ArcInspectorBody state={makeState()} />);
    // own: revenge -> remove; inherited: romance -> override here
    expect(screen.getByTestId('arc-track-revenge')).toBeInTheDocument();
    expect(screen.getByTestId('arc-track-override-romance')).toBeInTheDocument();
    expect(screen.queryByTestId('arc-track-override-revenge')).toBeNull();
  });

  it('commits an edit through OCC on blur, only when changed', () => {
    const edit = vi.fn();
    render(<ArcInspectorBody state={makeState({ edit })} />);
    const title = screen.getByTestId('arc-f-title');
    fireEvent.blur(title);
    expect(edit).not.toHaveBeenCalled(); // unchanged -> no write
    fireEvent.change(title, { target: { value: 'New title' } });
    fireEvent.blur(title);
    expect(edit).toHaveBeenCalledWith({ title: 'New title' });
  });

  it('override copies the inherited entry into own (never a silent fork)', () => {
    const edit = vi.fn();
    render(<ArcInspectorBody state={makeState({ edit })} />);
    fireEvent.click(screen.getByTestId('arc-track-override-romance'));
    expect(edit).toHaveBeenCalledWith({ tracks: [{ key: 'revenge', label: 'Revenge line' }, { key: 'romance', label: 'Cold Harbor girl' }] });
  });

  it('D-ARC-NO-ADD-CASCADE-ENTRY: + track adds a NEW own entry with a fresh key', () => {
    const edit = vi.fn();
    render(<ArcInspectorBody state={makeState({ edit })} />);
    fireEvent.click(screen.getByTestId('arc-track-add'));
    fireEvent.change(screen.getByTestId('arc-track-add-key'), { target: { value: 'betrayal' } });
    fireEvent.change(screen.getByTestId('arc-track-add-label'), { target: { value: 'The knife' } });
    fireEvent.click(screen.getByTestId('arc-track-add-submit'));
    expect(edit).toHaveBeenCalledWith({ tracks: [{ key: 'revenge', label: 'Revenge line' }, { key: 'betrayal', label: 'The knife' }] });
  });

  it('add-entry refuses a key that already resolves (no dup-422): submit disabled + marker', () => {
    const edit = vi.fn();
    render(<ArcInspectorBody state={makeState({ edit })} />);
    fireEvent.click(screen.getByTestId('arc-track-add'));
    fireEvent.change(screen.getByTestId('arc-track-add-key'), { target: { value: 'romance' } }); // already inherited
    expect(screen.getByTestId('arc-track-add-submit')).toBeDisabled();
    expect(screen.getByTestId('arc-track-add-dup')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('arc-track-add-submit'));
    expect(edit).not.toHaveBeenCalled();
  });

  it('D-ARC-EDITFIELD-MIDTYPE-RESET: an agent write mid-type never clobbers the draft', () => {
    const edit = vi.fn();
    const { rerender } = render(<ArcInspectorBody state={makeState({ edit })} />);
    const title = screen.getByTestId('arc-f-title');
    fireEvent.focus(title);
    fireEvent.change(title, { target: { value: 'my half-typed edit' } });
    // a concurrent agent write refetches detail → the title value moves underneath the cursor.
    rerender(<ArcInspectorBody state={makeState({ edit, detail: makeDetail({ title: 'Agent changed it', version: 8 }) })} />);
    expect(screen.getByTestId('arc-f-title')).toHaveValue('my half-typed edit'); // draft preserved
    // when the user was focused-but-untouched, the external value DOES win (no stale clobber):
    const goal = screen.getByTestId('arc-f-goal');
    fireEvent.focus(goal);
    rerender(<ArcInspectorBody state={makeState({ edit, detail: makeDetail({ title: 'Agent changed it', goal: 'Agent goal', version: 9 }) })} />);
    expect(screen.getByTestId('arc-f-goal')).toHaveValue('Agent goal');
  });

  it('archived: dims, hides danger, offers restore, and never a computed 0 for a null block', () => {
    const detail = makeDetail({ is_archived: true, span: null, chapter_count: null as unknown as number, is_contiguous: null as unknown as boolean });
    render(<ArcInspectorBody state={makeState({ detail })} />);
    expect(screen.getByTestId('arc-inspector-archived')).toBeInTheDocument();
    expect(screen.getByTestId('arc-restore')).toBeInTheDocument();
    expect(screen.queryByTestId('arc-archive')).toBeNull();
    expect(screen.getByTestId('arc-chapters-null').textContent).toBe('—');
  });

  it('loading / error / empty are distinct honest states', () => {
    const { rerender } = render(<ArcInspectorBody state={makeState({ loading: true, detail: null })} />);
    expect(screen.getByTestId('arc-inspector-loading')).toBeInTheDocument();
    rerender(<ArcInspectorBody state={makeState({ error: 'boom', detail: null })} />);
    expect(screen.getByTestId('arc-inspector-error')).toBeInTheDocument();
    rerender(<ArcInspectorBody state={makeState({ detail: null })} />);
    expect(screen.getByTestId('arc-inspector-empty')).toBeInTheDocument();
  });
});

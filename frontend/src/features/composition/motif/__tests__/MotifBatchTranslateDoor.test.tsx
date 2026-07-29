// THE DOOR onto batch translate.
//
// The atom-edit track's most expensive lesson was F10: four editors that existed, were
// imported, had passing tests — and had no way to open them. Every editor test rendered
// the child directly, so the gate was never in the test path, and "5 of 6 atoms
// GUI-editable" was true of the components and false of the product.
//
// `MotifBatchTranslateBar` is directly tested next door. This file tests the terms that
// decide whether a user can ever reach it, and — the part the bar itself cannot check —
// which rows become selectable, because THAT is what makes the count in the button honest.
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@/api', () => ({ apiJson: vi.fn(), apiBase: () => '' }));
vi.mock('../components/ArcTemplateLibraryView', () => ({ ArcTemplateLibraryView: () => <div data-testid="arc-stub" /> }));
vi.mock('../components/MotifScopeTabs', () => ({
  MotifScopeTabs: ({ onScope }: { onScope: (s: string) => void }) => (
    <button type="button" data-testid="motif-scope-system" onClick={() => onScope('system')}>system</button>
  ),
}));
vi.mock('../components/MotifFacetRail', () => ({ MotifFacetRail: () => <div /> }));
vi.mock('../components/MotifEmptyState', () => ({ MotifEmptyState: () => <div /> }));
vi.mock('../components/MotifDetailDrawer', () => ({ MotifDetailDrawer: () => null }));
vi.mock('../components/MotifQuickCreateForm', () => ({ MotifQuickCreateForm: () => null }));
vi.mock('../components/MotifMinePanel', () => ({ MotifMinePanel: () => null }));
vi.mock('../components/AdoptTargetModal', () => ({ AdoptTargetModal: () => null }));
// The bar is stubbed to a probe: this file is about REACHING it and about what it is
// handed, not about its internals.
vi.mock('../components/MotifBatchTranslateBar', () => ({
  MotifBatchTranslateBar: ({ selectedIds, notSelectableCount }: {
    selectedIds: string[]; notSelectableCount: number;
  }) => (
    <div data-testid="bar-stub" data-selected={selectedIds.join(',')} data-excluded={notSelectableCount} />
  ),
}));
vi.mock('../hooks/useMotifDraftActions', () => ({
  useMotifDraftActions: () => ({
    promote: { mutate: vi.fn(), isPending: false },
    discard: { mutate: vi.fn(), isPending: false },
    restore: { mutate: vi.fn(), isPending: false },
  }),
}));
vi.mock('../context/MotifSimpleModeContext', () => ({ useMotifSimpleMode: () => ({ simple: true, toggle: vi.fn() }) }));
vi.mock('../hooks/useMotifDetail', () => ({ useMotifDetail: () => ({ motif: null, readOnly: false, isLoading: false, isError: false }) }));
vi.mock('../hooks/useMotifQuickCreate', () => ({ useMotifQuickCreate: () => ({}) }));
vi.mock('../hooks/useAdoptFlow', () => ({
  useAdoptFlow: () => ({
    isOpen: false, target: { kind: 'user' }, estimate: null, quota: null,
    mint: { isPending: false, mutate: vi.fn() }, confirm: { isPending: false, mutate: vi.fn() },
    setTarget: vi.fn(), cancel: vi.fn(), begin: vi.fn(),
  }),
}));

const ME = 'user-1';
function motif(id: string, owner: string | null) {
  return {
    id, owner_user_id: owner, code: `c.${id}`, original_language: 'en',
    visibility: 'private', kind: 'situation', category: null, name: `M ${id}`,
    summary: '', genre_tags: [], roles: [], beats: [], preconditions: [], effects: [],
    tension_target: null, emotion_target: null, examples: [],
    abstraction_confidence: null, source: 'authored', source_version: null,
    judge_score: null, mining_support: null, status: 'active', version: 1,
  };
}
vi.mock('../hooks/useMotifLibrary', () => ({
  useMotifLibrary: () => ({
    scope: 'my', setScope: vi.fn(), search: '', setSearch: vi.fn(), facets: {}, available: {},
    setFacet: vi.fn(), clearFacets: vi.fn(), isLoading: false, isError: false, isEmpty: false,
    // one of mine, one system, one someone else's public
    motifs: [motif('mine', ME), motif('sys', null), motif('theirs', 'user-2')],
    refetch: vi.fn(), truncated: false, hasMore: false, isLoadingMore: false, loadMore: vi.fn(),
  }),
}));

import { MotifLibraryView } from '../components/MotifLibraryView';

function open() {
  render(<MotifLibraryView token="t" meUserId={ME} />);
  fireEvent.click(screen.getByTestId('motif-batch-open'));
}

describe('the door exists and opens', () => {
  it('renders an entry point in the library toolbar', () => {
    render(<MotifLibraryView token="t" meUserId={ME} />);
    expect(screen.getByTestId('motif-batch-open')).toBeInTheDocument();
    // …and nothing before it is clicked: the library stays a reading surface.
    expect(screen.queryByTestId('bar-stub')).toBeNull();
  });

  it('opens the bar', () => {
    open();
    expect(screen.getByTestId('bar-stub')).toBeInTheDocument();
  });

  it('is absent on the ARCS tab — that library has its own per-item affordance', () => {
    render(<MotifLibraryView token="t" meUserId={ME} />);
    fireEvent.click(screen.getByTestId('motif-kind-arcs'));
    expect(screen.queryByTestId('motif-batch-open')).toBeNull();
  });
});

describe('only rows the caller may translate are selectable', () => {
  it('gives a checkbox to your own motif and to nothing else', () => {
    open();
    expect(screen.getByTestId('motif-select-mine')).toBeInTheDocument();
    // A system motif ships free in every language; someone else's public one must be
    // adopted first. Offering a tick and refusing it at propose would be a batch
    // narrowed after the fact — the silent-truncation bug with a price tag on it.
    expect(screen.queryByTestId('motif-select-sys')).toBeNull();
    expect(screen.queryByTestId('motif-select-theirs')).toBeNull();
  });

  it('shows no checkboxes at all until selection mode is on', () => {
    render(<MotifLibraryView token="t" meUserId={ME} />);
    expect(screen.queryByTestId('motif-select-mine')).toBeNull();
  });

  it('hands the bar the ticked ids and the count it must explain', () => {
    open();
    fireEvent.click(screen.getByTestId('motif-select-mine'));
    const bar = screen.getByTestId('bar-stub');
    expect(bar.getAttribute('data-selected')).toBe('mine');
    expect(bar.getAttribute('data-excluded')).toBe('2');   // sys + theirs
  });

  it('untick removes the id rather than re-adding it', () => {
    open();
    fireEvent.click(screen.getByTestId('motif-select-mine'));
    fireEvent.click(screen.getByTestId('motif-select-mine'));
    expect(screen.getByTestId('bar-stub').getAttribute('data-selected')).toBe('');
  });
});

describe('a selection describes the view it was made in', () => {
  // Change the view and the count stops describing anything visible: the button would
  // still say "Translate 3" over a list showing none of the three, and the author would
  // pay for rows they had lost sight of.
  it('clears on a scope change', () => {
    open();
    fireEvent.click(screen.getByTestId('motif-select-mine'));
    expect(screen.getByTestId('bar-stub').getAttribute('data-selected')).toBe('mine');
    fireEvent.click(screen.getByTestId('motif-scope-system'));
    expect(screen.getByTestId('bar-stub').getAttribute('data-selected')).toBe('');
  });

  it('clears on a search change', () => {
    open();
    fireEvent.click(screen.getByTestId('motif-select-mine'));
    fireEvent.change(screen.getByTestId('motif-search'), { target: { value: 'x' } });
    expect(screen.getByTestId('bar-stub').getAttribute('data-selected')).toBe('');
  });
});

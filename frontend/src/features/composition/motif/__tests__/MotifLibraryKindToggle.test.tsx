// W10 — the MotifLibraryView kind toggle (Motifs | Arc templates). Defaults to motifs
// (existing behavior unchanged); switching to "Arc templates" swaps in the arc library.
// The heavy motif children + hooks are stubbed so ONLY the toggle wiring is exercised.
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('../components/ArcTemplateLibraryView', () => ({ ArcTemplateLibraryView: () => <div data-testid="arc-template-library-stub" /> }));
vi.mock('../components/MotifScopeTabs', () => ({ MotifScopeTabs: () => <div data-testid="scope-tabs-stub" /> }));
vi.mock('../components/MotifFacetRail', () => ({ MotifFacetRail: () => <div /> }));
vi.mock('../components/MotifEmptyState', () => ({ MotifEmptyState: () => <div data-testid="motif-empty-stub" /> }));
vi.mock('../components/MotifDetailDrawer', () => ({ MotifDetailDrawer: () => null }));
vi.mock('../components/MotifQuickCreateForm', () => ({ MotifQuickCreateForm: () => null }));
vi.mock('../components/MotifMinePanel', () => ({ MotifMinePanel: () => null }));
vi.mock('../components/AdoptTargetModal', () => ({ AdoptTargetModal: () => null }));
vi.mock('../hooks/useMotifDraftActions', () => ({
  useMotifDraftActions: () => ({
    promote: { mutate: vi.fn(), isPending: false },
    discard: { mutate: vi.fn(), isPending: false },
    restore: { mutate: vi.fn(), isPending: false },
  }),
}));
vi.mock('../context/MotifSimpleModeContext', () => ({ useMotifSimpleMode: () => ({ simple: true, toggle: vi.fn() }) }));
vi.mock('../hooks/useMotifLibrary', () => ({
  useMotifLibrary: () => ({
    scope: 'my', setScope: vi.fn(), search: '', setSearch: vi.fn(), facets: {}, available: {},
    setFacet: vi.fn(), clearFacets: vi.fn(), isLoading: false, isError: false, isEmpty: true,
    motifs: [], refetch: vi.fn(),
  }),
}));
vi.mock('../hooks/useMotifDetail', () => ({ useMotifDetail: () => ({ motif: null, readOnly: false, isLoading: false, isError: false }) }));
vi.mock('../hooks/useMotifQuickCreate', () => ({ useMotifQuickCreate: () => ({}) }));
vi.mock('../hooks/useAdoptFlow', () => ({
  useAdoptFlow: () => ({
    isOpen: false, target: { kind: 'user' }, estimate: null, quota: null,
    mint: { isPending: false, mutate: vi.fn() }, confirm: { isPending: false, mutate: vi.fn() },
    setTarget: vi.fn(), cancel: vi.fn(), begin: vi.fn(),
  }),
}));

import { MotifLibraryView } from '../components/MotifLibraryView';

describe('MotifLibraryView kind toggle', () => {
  it('defaults to motifs and swaps to the arc library on the Arcs tab', () => {
    render(<MotifLibraryView token="tok" meUserId="u1" />);
    // default: the motif surface (scope tabs) is shown, arcs is not.
    expect(screen.getByTestId('scope-tabs-stub')).toBeInTheDocument();
    expect(screen.queryByTestId('arc-template-library-stub')).toBeNull();
    expect(screen.getByTestId('motif-kind-motifs')).toHaveAttribute('aria-selected', 'true');

    fireEvent.click(screen.getByTestId('motif-kind-arcs'));
    expect(screen.getByTestId('arc-template-library-stub')).toBeInTheDocument();
    expect(screen.queryByTestId('scope-tabs-stub')).toBeNull();
    expect(screen.getByTestId('motif-kind-arcs')).toHaveAttribute('aria-selected', 'true');

    fireEvent.click(screen.getByTestId('motif-kind-motifs'));
    expect(screen.getByTestId('scope-tabs-stub')).toBeInTheDocument();
  });
});

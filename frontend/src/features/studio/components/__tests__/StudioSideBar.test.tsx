import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

// The manuscript view mounts the real ManuscriptNavigator (which fetches); stub it so the
// side-bar test stays a pure chrome test. Capture its props to assert the wiring. Its own
// behaviour (incl. the header collapse button) is covered in its own tests.
const navProps = vi.hoisted(() => ({ value: null as Record<string, unknown> | null }));
vi.mock('../../manuscript/ManuscriptNavigator', () => ({
  ManuscriptNavigator: (p: Record<string, unknown>) => {
    navProps.value = p;
    return <div data-testid="manuscript-nav-stub" />;
  },
}));

import { StudioHostProvider } from '../../host/StudioHostProvider';
import { StudioSideBar } from '../StudioSideBar';

const props = { onCollapse: vi.fn(), bookId: 'b1', token: 't' as string | null, selectedId: null, onSelectNode: vi.fn(), width: 260, onResize: vi.fn() };

// StudioSideBar reads useStudioHost() (the 'quality' branch's Open button) — every render
// needs the real provider, not a bare component (matches every other panel test's pattern).
function renderSideBar(overrides: Partial<typeof props> & { activeView: string }) {
  const { activeView, ...rest } = { ...props, ...overrides };
  return render(
    <StudioHostProvider bookId={rest.bookId}>
      <StudioSideBar activeView={activeView as never} {...rest} />
    </StudioHostProvider>,
  );
}

describe('StudioSideBar', () => {
  it('S-11: the search view renders the real query rail, not the "Coming soon" stub', () => {
    renderSideBar({ activeView: 'search' });
    const sb = screen.getByTestId('studio-sidebar');
    // the real rail (query box) is present…
    expect(screen.getByTestId('studio-search-rail')).toBeInTheDocument();
    expect(screen.getByTestId('studio-search-rail-input')).toBeInTheDocument();
    // …and the old stub body is gone.
    expect(sb.textContent).not.toContain('navStub.search.body');
  });

  it('still shows the stub header + body for a genuinely not-yet-built view (quality keeps a stub body)', () => {
    renderSideBar({ activeView: 'quality' });
    const sb = screen.getByTestId('studio-sidebar');
    expect(sb.textContent).toContain('activity.quality');       // header label key
    expect(sb.textContent).toContain('navStub.quality.title');  // stub title key
  });

  it('H-1b: the bible view lists the bible-group panels as launchers (discoverable, not palette-only)', () => {
    renderSideBar({ activeView: 'bible' });
    expect(screen.getByTestId('studio-sidebar-bible')).toBeTruthy();
    // reference-shelf (H-1a) + divergence are tagged navGroup:'bible' → surfaced here.
    expect(screen.getByTestId('studio-sidebar-open-reference-shelf')).toBeTruthy();
    expect(screen.getByTestId('studio-sidebar-open-divergence')).toBeTruthy();
    // clicking goes through the real host.openPanel without throwing (chrome-test scope).
    fireEvent.click(screen.getByTestId('studio-sidebar-open-reference-shelf'));
  });

  it('mounts the ManuscriptNavigator (no duplicate chrome header) for the manuscript view', () => {
    renderSideBar({ activeView: 'manuscript' });
    expect(screen.getByTestId('manuscript-nav-stub')).toBeTruthy();
    // The Side Bar does NOT render its own header for manuscript — the navigator owns it.
    expect(screen.queryByTitle('sidebar.collapse')).toBeNull();
  });

  it('delegates sidebar collapse to the navigator header (onCollapseSidebar) for manuscript', () => {
    const onCollapse = vi.fn();
    renderSideBar({ activeView: 'manuscript', onCollapse });
    expect(navProps.value?.onCollapseSidebar).toBe(onCollapse);
  });

  // ⚠ THE REGRESSION TEST. This exact wiring was missing and shipped: the navigator renders its `+`
  // as `disabled={!onNewChapter}` and this is its ONLY consumer, so dropping the prop disabled the
  // button 100% of the time — for every user, on every book — and closed the Studio's zero-state
  // loop (docs/bugs/2026-07-17-studio-first-use-cold-start.md).
  //
  // The navigator's OWN test could never catch it: it passed its own `onNewChapter` in, so it proved
  // the mechanism while the app wired nothing. Only a test that mounts the CALLER can. Asserting the
  // prop is a function IS asserting the button is enabled — that is precisely what the navigator
  // gates on. Do not "simplify" this back into ManuscriptNavigator's tests.
  it('passes onNewChapter to the navigator — the `+` must never render disabled', () => {
    renderSideBar({ activeView: 'manuscript' });
    expect(typeof navProps.value?.onNewChapter).toBe('function');
  });

  it('the navigator `+` opens the plan hub (structure is a SPEC act, not a prose one)', () => {
    renderSideBar({ activeView: 'manuscript' });
    // Invoking it must not throw: it goes through the real host's openPanel. As with the quality
    // button above, dockview internals are out of scope for a chrome test — PlanHubPanel's own
    // tests cover what opening it renders.
    expect(() => (navProps.value?.onNewChapter as () => void)()).not.toThrow();
  });

  it('fires onCollapse from the chrome collapse button on a stub view', () => {
    const onCollapse = vi.fn();
    renderSideBar({ activeView: 'bible', onCollapse });
    fireEvent.click(screen.getByTitle('sidebar.collapse'));
    expect(onCollapse).toHaveBeenCalledTimes(1);
  });

  it('the quality view offers an Open Quality button that opens the quality hub panel', () => {
    renderSideBar({ activeView: 'quality' });
    fireEvent.click(screen.getByTestId('studio-sidebar-open-quality'));
    // No assertion on dockview internals here (out of scope for a chrome test) — the
    // button existing + being clickable without throwing proves the host wiring works;
    // QualityHubPanel's own tests cover what opening it actually renders.
  });

  it('applies the given width and renders a resize handle whose double-click resets to default', () => {
    const onResize = vi.fn();
    renderSideBar({ activeView: 'bible', width: 420, onResize });
    const sb = screen.getByTestId('studio-sidebar');
    expect(sb.style.width).toBe('420px');
    const handle = screen.getByTestId('studio-sidebar-resize');
    fireEvent.doubleClick(handle);
    expect(onResize).toHaveBeenCalledWith(260, true); // SIDEBAR_WIDTH_DEFAULT, persisted
  });
});

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

import { StudioSideBar } from '../StudioSideBar';

const props = { onCollapse: vi.fn(), bookId: 'b1', token: 't' as string | null };

describe('StudioSideBar', () => {
  it('shows a stub navigator header + body for a not-yet-built view (keys)', () => {
    render(<StudioSideBar activeView="bible" {...props} />);
    const sb = screen.getByTestId('studio-sidebar');
    expect(sb.textContent).toContain('activity.bible');       // header label key
    expect(sb.textContent).toContain('navStub.bible.title');  // stub title key
    expect(sb.textContent).toContain('navStub.bible.body');   // stub body key
  });

  it('mounts the ManuscriptNavigator (no duplicate chrome header) for the manuscript view', () => {
    render(<StudioSideBar activeView="manuscript" {...props} />);
    expect(screen.getByTestId('manuscript-nav-stub')).toBeTruthy();
    // The Side Bar does NOT render its own header for manuscript — the navigator owns it.
    expect(screen.queryByTitle('sidebar.collapse')).toBeNull();
  });

  it('delegates sidebar collapse to the navigator header (onCollapseSidebar) for manuscript', () => {
    const onCollapse = vi.fn();
    render(<StudioSideBar activeView="manuscript" {...props} onCollapse={onCollapse} />);
    expect(navProps.value?.onCollapseSidebar).toBe(onCollapse);
  });

  it('fires onCollapse from the chrome collapse button on a stub view', () => {
    const onCollapse = vi.fn();
    render(<StudioSideBar activeView="bible" {...props} onCollapse={onCollapse} />);
    fireEvent.click(screen.getByTitle('sidebar.collapse'));
    expect(onCollapse).toHaveBeenCalledTimes(1);
  });
});

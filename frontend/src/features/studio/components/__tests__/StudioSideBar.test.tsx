import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

// The manuscript view mounts the real ManuscriptNavigator (which fetches); stub it so the
// side-bar test stays a pure chrome test. Its own behaviour is covered in its own tests.
vi.mock('../../manuscript/ManuscriptNavigator', () => ({
  ManuscriptNavigator: () => <div data-testid="manuscript-nav-stub" />,
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

  it('mounts the ManuscriptNavigator for the manuscript view', () => {
    render(<StudioSideBar activeView="manuscript" {...props} />);
    expect(screen.getByTestId('manuscript-nav-stub')).toBeTruthy();
  });

  it('fires onCollapse from the collapse button', () => {
    const onCollapse = vi.fn();
    render(<StudioSideBar activeView="manuscript" {...props} onCollapse={onCollapse} />);
    fireEvent.click(screen.getByTitle('sidebar.collapse'));
    expect(onCollapse).toHaveBeenCalledTimes(1);
  });
});

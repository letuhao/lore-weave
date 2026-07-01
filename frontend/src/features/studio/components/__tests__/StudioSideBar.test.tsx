import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { StudioSideBar } from '../StudioSideBar';

describe('StudioSideBar', () => {
  it('shows the active navigator header + its stub body (keys)', () => {
    render(<StudioSideBar activeView="bible" onCollapse={vi.fn()} />);
    const sb = screen.getByTestId('studio-sidebar');
    expect(sb.textContent).toContain('activity.bible');       // header label key
    expect(sb.textContent).toContain('navStub.bible.title');  // stub title key
    expect(sb.textContent).toContain('navStub.bible.body');   // stub body key
  });

  it('fires onCollapse from the collapse button', () => {
    const onCollapse = vi.fn();
    render(<StudioSideBar activeView="manuscript" onCollapse={onCollapse} />);
    fireEvent.click(screen.getByTitle('sidebar.collapse'));
    expect(onCollapse).toHaveBeenCalledTimes(1);
  });
});

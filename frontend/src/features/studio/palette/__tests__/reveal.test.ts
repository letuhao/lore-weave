import { describe, expect, it, vi } from 'vitest';
import { revealManuscript } from '../reveal';

const chrome = (over: Partial<Parameters<typeof revealManuscript>[0]> = {}) => ({
  activeView: 'manuscript' as const, sidebarCollapsed: false,
  setActiveView: vi.fn(), toggleSidebar: vi.fn(), ...over,
});

describe('revealManuscript', () => {
  it('off Manuscript → switches view (which also opens the sidebar)', () => {
    const c = chrome({ activeView: 'bible' });
    revealManuscript(c);
    expect(c.setActiveView).toHaveBeenCalledWith('manuscript');
    expect(c.toggleSidebar).not.toHaveBeenCalled();
  });

  it('on Manuscript but collapsed → opens the sidebar, never re-sets the view', () => {
    const c = chrome({ activeView: 'manuscript', sidebarCollapsed: true });
    revealManuscript(c);
    expect(c.toggleSidebar).toHaveBeenCalledOnce();
    expect(c.setActiveView).not.toHaveBeenCalled();
  });

  it('on Manuscript + already open → NO-OP (never collapses the navigator we jump into)', () => {
    const c = chrome({ activeView: 'manuscript', sidebarCollapsed: false });
    revealManuscript(c);
    expect(c.setActiveView).not.toHaveBeenCalled();
    expect(c.toggleSidebar).not.toHaveBeenCalled();
  });
});

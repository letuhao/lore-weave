// 14_kg_panels.md A2 — ProjectsTab shrank to a thin route wrapper over ProjectsBrowser
// (DOCK-2/DOCK-7 extraction). Browsing behaviour (search/sort/filter/load-more) is now
// covered by ProjectsBrowser.test.tsx; this file only asserts the ONE thing that's still
// ProjectsTab's own responsibility — wiring onOpen to navigate().
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import type { Project } from '../../types';

const navigateMock = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<Record<string, unknown>>('react-router-dom');
  return { ...actual, useNavigate: () => navigateMock };
});

vi.mock('../ProjectsBrowser', () => ({
  ProjectsBrowser: ({ onOpen }: { onOpen: (p: Project) => void }) => (
    <button
      data-testid="open-proj-9"
      onClick={() => onOpen({ project_id: 'proj-9', name: 'Proj' } as Project)}
    >
      open
    </button>
  ),
}));

import { ProjectsTab } from '../ProjectsTab';

describe('ProjectsTab — thin route wrapper', () => {
  beforeEach(() => {
    navigateMock.mockReset();
  });

  it('routes a row INTO the C6 detail shell via navigate()', () => {
    render(
      <MemoryRouter>
        <ProjectsTab />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByTestId('open-proj-9'));
    expect(navigateMock).toHaveBeenCalledWith('/knowledge/projects/proj-9/overview');
  });
});

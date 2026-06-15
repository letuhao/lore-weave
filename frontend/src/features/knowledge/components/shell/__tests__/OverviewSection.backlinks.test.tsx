import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string, o?: { defaultValue?: string }) => o?.defaultValue ?? k }),
}));

// ProjectRow has heavy dialog deps; stub it — this test is about the backlinks.
vi.mock('../../ProjectRow', () => ({ ProjectRow: () => <div data-testid="stub-project-row" /> }));

const backlinks = vi.fn();
vi.mock('../../../hooks/useProjectBacklinks', () => ({
  useProjectBacklinks: () => backlinks(),
}));

import { OverviewSection } from '../OverviewSection';
import type { Project } from '../../../types';

const project = { project_id: 'p1', book_id: 'b1', embedding_model: null, rerank_model: null, extraction_enabled: true } as unknown as Project;

function renderOverview(p: Project | null) {
  render(
    <MemoryRouter>
      <OverviewSection project={p} onExploreGraph={vi.fn()} />
    </MemoryRouter>,
  );
}

beforeEach(() => backlinks.mockReset());

describe('OverviewSection backlinks (D-WORLD-PROJECT-BACKLINK)', () => {
  it('links to the book by title and to the world when grouped', () => {
    backlinks.mockReturnValue({ bookTitle: 'Cradle', worldId: 'w1', worldName: 'Aethyr', isLoading: false });
    renderOverview(project);
    const bookLink = screen.getByTestId('overview-book-link');
    expect(bookLink).toHaveAttribute('href', '/books/b1');
    expect(bookLink).toHaveTextContent('Cradle');
    const worldLink = screen.getByTestId('overview-world-link');
    expect(worldLink).toHaveAttribute('href', '/worlds/w1');
    expect(worldLink).toHaveTextContent('Aethyr');
  });

  it('omits the world link when the book is standalone', () => {
    backlinks.mockReturnValue({ bookTitle: 'Standalone', worldId: null, worldName: null, isLoading: false });
    renderOverview(project);
    expect(screen.getByTestId('overview-book-link')).toBeInTheDocument();
    expect(screen.queryByTestId('overview-world-link')).toBeNull();
  });

  it('falls back to the book id when the title has not resolved yet', () => {
    backlinks.mockReturnValue({ bookTitle: null, worldId: null, worldName: null, isLoading: true });
    renderOverview(project);
    expect(screen.getByTestId('overview-book-link')).toHaveTextContent('b1');
  });
});

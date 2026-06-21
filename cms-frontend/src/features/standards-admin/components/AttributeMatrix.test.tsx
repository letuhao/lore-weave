import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { AttributeMatrix } from './AttributeMatrix';
import type { SystemAttribute, SystemGenre } from '../types';

const genres: SystemGenre[] = [
  { genre_id: 'g1', code: 'fantasy', name: 'Fantasy', icon: null, color: null, sort_order: 1 },
  { genre_id: 'g2', code: 'scifi', name: 'Sci-Fi', icon: null, color: null, sort_order: 2 },
];

function attr(over: Partial<SystemAttribute>): SystemAttribute {
  return {
    attr_id: 'a',
    kind_id: 'k1',
    genre_id: 'g1',
    code: 'rank',
    name: 'Rank',
    description: null,
    field_type: 'text',
    is_required: false,
    sort_order: 1,
    options: null,
    ...over,
  };
}

describe('AttributeMatrix', () => {
  it('renders a grid with genre columns and a cell badge', () => {
    render(
      <AttributeMatrix
        activeGenres={genres}
        attributes={[attr({ attr_id: 'a1', genre_id: 'g1', code: 'rank', field_type: 'select' })]}
        selectedCell={null}
        onSelectCell={() => {}}
      />,
    );
    expect(screen.getByText('Fantasy')).toBeInTheDocument();
    expect(screen.getByText('Sci-Fi')).toBeInTheDocument();
    // cell present for rank in fantasy, badge shows field_type
    const cell = screen.getByTestId('matrix-cell-rank-fantasy');
    expect(cell).toHaveTextContent('select');
  });

  it('highlights a conflict row when a code spans 2+ genres', () => {
    const { container } = render(
      <AttributeMatrix
        activeGenres={genres}
        attributes={[
          attr({ attr_id: 'a1', genre_id: 'g1', code: 'rank' }),
          attr({ attr_id: 'a2', genre_id: 'g2', code: 'rank' }),
        ]}
        selectedCell={null}
        onSelectCell={() => {}}
      />,
    );
    const amberRow = container.querySelector('tr.bg-amber-50');
    expect(amberRow).not.toBeNull();
    expect(amberRow).toHaveTextContent('in 2 genres');
  });

  it('renders an empty-cell placeholder where a code has no attribute for a genre', () => {
    render(
      <AttributeMatrix
        activeGenres={genres}
        attributes={[attr({ attr_id: 'a1', genre_id: 'g1', code: 'rank' })]}
        selectedCell={null}
        onSelectCell={() => {}}
      />,
    );
    // rank exists in fantasy but not sci-fi → no testid cell for sci-fi
    expect(screen.getByTestId('matrix-cell-rank-fantasy')).toBeInTheDocument();
    expect(screen.queryByTestId('matrix-cell-rank-scifi')).toBeNull();
  });

  it('calls onSelectCell with {code, genreId} when a cell is clicked', () => {
    const onSelect = vi.fn();
    render(
      <AttributeMatrix
        activeGenres={genres}
        attributes={[attr({ attr_id: 'a1', genre_id: 'g1', code: 'rank' })]}
        selectedCell={null}
        onSelectCell={onSelect}
      />,
    );
    fireEvent.click(screen.getByTestId('matrix-cell-rank-fantasy'));
    expect(onSelect).toHaveBeenCalledWith({ code: 'rank', genreId: 'g1' });
  });
});

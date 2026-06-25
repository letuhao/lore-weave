import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import { OntologyColumn, type ColumnRow } from '../OntologyColumn';

const rows: ColumnRow[] = [
  { id: 'g1', label: 'Xianxia' },
  { id: 'g2', label: 'Romance' },
];

describe('OntologyColumn delete affordance', () => {
  it('renders a delete button per row when onDelete is provided and calls it with the row', () => {
    const onDelete = vi.fn();
    const onSelect = vi.fn();
    render(
      <OntologyColumn
        title="Genres"
        rows={rows}
        selectedId={null}
        onSelect={onSelect}
        emptyText="empty"
        onDelete={onDelete}
        deleteLabel="Delete genre"
      />,
    );
    const del = screen.getByTestId('ontology-delete-g1');
    fireEvent.click(del);
    expect(onDelete).toHaveBeenCalledTimes(1);
    expect(onDelete).toHaveBeenCalledWith(rows[0]);
    // delete must NOT trigger row selection (separate sibling buttons, no nesting).
    expect(onSelect).not.toHaveBeenCalled();
  });

  it('omits the delete button when onDelete is not provided (e.g. attributes column)', () => {
    render(
      <OntologyColumn title="Attributes" rows={rows} selectedId={null} onSelect={vi.fn()} emptyText="empty" />,
    );
    expect(screen.queryByTestId('ontology-delete-g1')).not.toBeInTheDocument();
    // the row is still selectable.
    expect(screen.getByTestId('ontology-row-g1')).toBeInTheDocument();
  });

  it('selecting a row still works alongside the delete button', () => {
    const onSelect = vi.fn();
    render(
      <OntologyColumn
        title="Genres"
        rows={rows}
        selectedId={null}
        onSelect={onSelect}
        emptyText="empty"
        onDelete={vi.fn()}
        deleteLabel="Delete genre"
      />,
    );
    fireEvent.click(screen.getByTestId('ontology-row-g2'));
    expect(onSelect).toHaveBeenCalledWith('g2');
  });
});

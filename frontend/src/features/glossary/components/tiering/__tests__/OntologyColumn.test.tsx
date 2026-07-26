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
    // Must be visible on touch devices — NOT hover-revealed (opacity-0/group-hover would
    // leave it unreachable on mobile, the original review-impl MED finding).
    expect(del.className).not.toMatch(/opacity-0|group-hover/);
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

  it('renders a links button per row when onLinks is provided and calls it without selecting the row', () => {
    const onLinks = vi.fn();
    const onSelect = vi.fn();
    render(
      <OntologyColumn
        title="Kinds"
        rows={rows}
        selectedId={null}
        onSelect={onSelect}
        emptyText="empty"
        onLinks={onLinks}
        linksLabel="Linked genres"
      />,
    );
    const links = screen.getByTestId('ontology-links-g1');
    // Must be reachable on touch — not hover-revealed (same rule as edit/delete).
    expect(links.className).not.toMatch(/opacity-0|group-hover/);
    fireEvent.click(links);
    expect(onLinks).toHaveBeenCalledWith(rows[0]);
    expect(onSelect).not.toHaveBeenCalled();
  });

  it('omits the links button when onLinks is not provided', () => {
    render(
      <OntologyColumn title="Genres" rows={rows} selectedId={null} onSelect={vi.fn()} emptyText="empty" />,
    );
    expect(screen.queryByTestId('ontology-links-g1')).not.toBeInTheDocument();
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

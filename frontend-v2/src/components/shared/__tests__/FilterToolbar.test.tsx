import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { FilterToolbar } from '../FilterToolbar';

describe('FilterToolbar', () => {
  it('renders search input when onSearchChange is provided', () => {
    render(<FilterToolbar search="" onSearchChange={vi.fn()} />);
    expect(screen.getByPlaceholderText('Search...')).toBeInTheDocument();
  });

  it('does not render search input when onSearchChange is not provided', () => {
    render(<FilterToolbar />);
    expect(screen.queryByPlaceholderText('Search...')).not.toBeInTheDocument();
  });

  it('calls onSearchChange on input', async () => {
    const onChange = vi.fn();
    render(<FilterToolbar search="" onSearchChange={onChange} />);
    await userEvent.type(screen.getByPlaceholderText('Search...'), 'hello');
    expect(onChange).toHaveBeenCalled();
  });

  it('renders custom placeholder', () => {
    render(<FilterToolbar search="" onSearchChange={vi.fn()} searchPlaceholder="Find books..." />);
    expect(screen.getByPlaceholderText('Find books...')).toBeInTheDocument();
  });

  it('renders active filter chips with remove button', async () => {
    const onRemove = vi.fn();
    render(
      <FilterToolbar
        activeFilters={[{ label: 'Status: Active', onRemove }]}
      />,
    );
    expect(screen.getByText('Status: Active')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button'));
    expect(onRemove).toHaveBeenCalled();
  });

  it('renders trailing content', () => {
    render(<FilterToolbar trailing={<span>10 results</span>} />);
    expect(screen.getByText('10 results')).toBeInTheDocument();
  });

  it('renders filter slot content', () => {
    render(<FilterToolbar filters={<select><option>All</option></select>} />);
    expect(screen.getByRole('combobox')).toBeInTheDocument();
  });
});

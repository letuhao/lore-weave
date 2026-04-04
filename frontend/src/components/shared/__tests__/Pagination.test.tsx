import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Pagination } from '../Pagination';

describe('Pagination', () => {
  it('returns null when total <= limit', () => {
    const { container } = render(
      <Pagination total={10} limit={20} offset={0} onChange={vi.fn()} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders when total > limit', () => {
    render(<Pagination total={50} limit={10} offset={0} onChange={vi.fn()} />);
    expect(screen.getByText('1')).toBeInTheDocument();
  });

  it('calls onChange with correct offset on page click', async () => {
    const onChange = vi.fn();
    render(<Pagination total={30} limit={10} offset={0} onChange={onChange} />);
    await userEvent.click(screen.getByText('2'));
    expect(onChange).toHaveBeenCalledWith(10);
  });

  it('calls onChange on next button click', async () => {
    const onChange = vi.fn();
    render(<Pagination total={30} limit={10} offset={0} onChange={onChange} />);
    // Next button is the last button
    const buttons = screen.getAllByRole('button');
    const nextBtn = buttons[buttons.length - 1];
    await userEvent.click(nextBtn);
    expect(onChange).toHaveBeenCalledWith(10);
  });

  it('disables prev button on first page', () => {
    render(<Pagination total={30} limit={10} offset={0} onChange={vi.fn()} />);
    const buttons = screen.getAllByRole('button');
    expect(buttons[0]).toBeDisabled();
  });

  it('disables next button on last page', () => {
    render(<Pagination total={30} limit={10} offset={20} onChange={vi.fn()} />);
    const buttons = screen.getAllByRole('button');
    expect(buttons[buttons.length - 1]).toBeDisabled();
  });

  it('shows ellipsis for many pages', () => {
    render(<Pagination total={100} limit={10} offset={0} onChange={vi.fn()} />);
    expect(screen.getByText('10')).toBeInTheDocument();
    expect(screen.getAllByText('...').length).toBeGreaterThanOrEqual(1);
  });
});

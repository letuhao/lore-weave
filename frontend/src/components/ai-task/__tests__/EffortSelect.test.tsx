import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { EffortSelect } from '../EffortSelect';

describe('EffortSelect', () => {
  it('opens the menu and emits the picked level', () => {
    const onChange = vi.fn();
    render(<EffortSelect value="fast" onChange={onChange} />);

    // menu closed initially
    expect(screen.queryByTestId('effort-select-menu')).toBeNull();
    fireEvent.click(screen.getByTestId('effort-select'));
    expect(screen.getByTestId('effort-select-menu')).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('effort-select-opt-deep'));
    expect(onChange).toHaveBeenCalledWith('deep');
    // closes after pick
    expect(screen.queryByTestId('effort-select-menu')).toBeNull();
  });

  it('marks the active level and respects disabled', () => {
    render(<EffortSelect value="standard" onChange={vi.fn()} disabled />);
    expect(screen.getByTestId('effort-select')).toBeDisabled();
  });
});

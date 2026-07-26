import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { EffortSelect } from '../EffortSelect';

describe('EffortSelect (unified 5-level)', () => {
  it('opens the menu, lists all 5 levels, emits the picked level', () => {
    const onChange = vi.fn();
    render(<EffortSelect value="off" onChange={onChange} />);

    expect(screen.queryByTestId('effort-select-menu')).toBeNull();
    fireEvent.click(screen.getByTestId('effort-select'));
    expect(screen.getByTestId('effort-select-menu')).toBeInTheDocument();
    for (const l of ['off', 'low', 'medium', 'high', 'auto']) {
      expect(screen.getByTestId(`effort-select-opt-${l}`)).toBeInTheDocument();
    }

    fireEvent.click(screen.getByTestId('effort-select-opt-high'));
    expect(onChange).toHaveBeenCalledWith('high');
    expect(screen.queryByTestId('effort-select-menu')).toBeNull(); // closes after pick
  });

  it('renders the auto level and respects disabled', () => {
    render(<EffortSelect value="auto" onChange={vi.fn()} disabled />);
    expect(screen.getByTestId('effort-select')).toBeDisabled();
  });
});

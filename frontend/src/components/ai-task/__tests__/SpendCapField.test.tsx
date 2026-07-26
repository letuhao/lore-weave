import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { SpendCapField, isValidSpend } from '../SpendCapField';

describe('isValidSpend', () => {
  it('accepts empty (no cap) and non-negative ≤2-dp decimals', () => {
    for (const v of ['', '0', '5', '5.5', '12.34', '100']) expect(isValidSpend(v)).toBe(true);
  });
  it('rejects negatives, 3+ dp, and non-numeric', () => {
    for (const v of ['-1', '1.234', 'abc', '1.', '.5', '1,5']) expect(isValidSpend(v)).toBe(false);
  });
});

describe('SpendCapField', () => {
  it('emits changes and flags invalid input via aria-invalid', () => {
    const onChange = vi.fn();
    const { rerender } = render(<SpendCapField value="" onChange={onChange} invalidLabel="bad" />);
    const input = screen.getByTestId('spend-cap');
    expect(input).toHaveAttribute('aria-invalid', 'false');
    fireEvent.change(input, { target: { value: '2.5' } });
    expect(onChange).toHaveBeenCalledWith('2.5');

    rerender(<SpendCapField value="1.234" onChange={onChange} invalidLabel="bad" />);
    expect(screen.getByTestId('spend-cap')).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByText('bad')).toBeInTheDocument();
  });
});

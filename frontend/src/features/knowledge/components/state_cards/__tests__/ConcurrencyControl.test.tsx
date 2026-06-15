import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ConcurrencyControl } from '../ConcurrencyControl';

// vitest.setup.ts globally mocks react-i18next so t(key) returns the key.

describe('ConcurrencyControl — C7 raise-cap (KN-7)', () => {
  it('seeds the editor from the current cap and applies a changed value', () => {
    const onSet = vi.fn();
    render(
      <ConcurrencyControl jobId="j1" current={4} onSetConcurrency={onSet} />,
    );
    const input = screen.getByTestId('concurrency-input') as HTMLInputElement;
    expect(input.value).toBe('4');

    fireEvent.change(input, { target: { value: '16' } });
    fireEvent.click(screen.getByTestId('concurrency-apply'));
    expect(onSet).toHaveBeenCalledWith('j1', 16);
  });

  it('clamps above-max input to 64 before submitting', () => {
    const onSet = vi.fn();
    render(
      <ConcurrencyControl jobId="j1" current={4} onSetConcurrency={onSet} />,
    );
    const input = screen.getByTestId('concurrency-input');
    fireEvent.change(input, { target: { value: '999' } });
    fireEvent.click(screen.getByTestId('concurrency-apply'));
    expect(onSet).toHaveBeenCalledWith('j1', 64);
  });

  it('clamps below-min input to 1', () => {
    const onSet = vi.fn();
    render(
      <ConcurrencyControl jobId="j1" current={4} onSetConcurrency={onSet} />,
    );
    const input = screen.getByTestId('concurrency-input');
    fireEvent.change(input, { target: { value: '0' } });
    fireEvent.click(screen.getByTestId('concurrency-apply'));
    expect(onSet).toHaveBeenCalledWith('j1', 1);
  });

  it('disables Apply when the value is unchanged from the current cap', () => {
    const onSet = vi.fn();
    render(
      <ConcurrencyControl jobId="j1" current={8} onSetConcurrency={onSet} />,
    );
    const apply = screen.getByTestId('concurrency-apply') as HTMLButtonElement;
    expect(apply.disabled).toBe(true);
  });

  it('seeds a default (4) and allows applying when the cap is unbounded (null)', () => {
    const onSet = vi.fn();
    render(
      <ConcurrencyControl jobId="j1" current={null} onSetConcurrency={onSet} />,
    );
    const input = screen.getByTestId('concurrency-input') as HTMLInputElement;
    expect(input.value).toBe('4');
    // current=null ⇒ Apply is enabled (nothing to compare against).
    const apply = screen.getByTestId('concurrency-apply') as HTMLButtonElement;
    expect(apply.disabled).toBe(false);
    fireEvent.click(apply);
    expect(onSet).toHaveBeenCalledWith('j1', 4);
  });
});

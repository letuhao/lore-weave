import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { WorkmodeSwitcher } from '../WorkmodeSwitcher';

// The global react-i18next mock returns KEYS, not English defaultValues (repo convention),
// so label assertions target keys.

describe('WorkmodeSwitcher', () => {
  it('shows the current mode on the trigger and opens the menu on click', () => {
    render(<WorkmodeSwitcher mode="translate" onChange={vi.fn()} onOpenReader={vi.fn()} />);
    expect(screen.getByTestId('workmode-switcher').textContent).toContain('workmode.translate');
    expect(screen.queryByTestId('workmode-menu')).toBeNull();
    fireEvent.click(screen.getByTestId('workmode-switcher'));
    expect(screen.getByTestId('workmode-menu')).toBeTruthy();
  });

  it('lists all four entries including Read', () => {
    render(<WorkmodeSwitcher mode="write" onChange={vi.fn()} onOpenReader={vi.fn()} />);
    fireEvent.click(screen.getByTestId('workmode-switcher'));
    expect(screen.getByTestId('workmode-item-write')).toBeTruthy();
    expect(screen.getByTestId('workmode-item-translate')).toBeTruthy();
    expect(screen.getByTestId('workmode-item-read')).toBeTruthy();
    expect(screen.getByTestId('workmode-item-compose')).toBeTruthy();
  });

  it('selecting an in-editor mode calls onChange (not onOpenReader) and closes', () => {
    const onChange = vi.fn();
    const onOpenReader = vi.fn();
    render(<WorkmodeSwitcher mode="write" onChange={onChange} onOpenReader={onOpenReader} />);
    fireEvent.click(screen.getByTestId('workmode-switcher'));
    fireEvent.click(screen.getByTestId('workmode-item-compose'));
    expect(onChange).toHaveBeenCalledWith('compose');
    expect(onOpenReader).not.toHaveBeenCalled();
    expect(screen.queryByTestId('workmode-menu')).toBeNull();
  });

  it('selecting Read calls onOpenReader (a route action, not a mode change)', () => {
    const onChange = vi.fn();
    const onOpenReader = vi.fn();
    render(<WorkmodeSwitcher mode="write" onChange={onChange} onOpenReader={onOpenReader} />);
    fireEvent.click(screen.getByTestId('workmode-switcher'));
    fireEvent.click(screen.getByTestId('workmode-item-read'));
    expect(onOpenReader).toHaveBeenCalledTimes(1);
    expect(onChange).not.toHaveBeenCalled();
  });
});

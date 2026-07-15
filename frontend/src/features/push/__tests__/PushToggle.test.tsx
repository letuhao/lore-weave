// M5 — the toggle renders the right control for each capability state and never shows one the
// platform can't honour.
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import type { PushCapability } from '../capability';

const state = {
  capability: { supported: true, iosNeedsInstall: false, permission: 'default', available: true } as PushCapability,
  enabled: false,
  busy: false,
  enable: vi.fn(),
  disable: vi.fn(),
};
vi.mock('../usePushSubscription', () => ({ usePushSubscription: () => state }));

import { PushToggle } from '../PushToggle';

describe('PushToggle', () => {
  it('renders nothing when push is unsupported', () => {
    state.capability = { supported: false, iosNeedsInstall: false, permission: 'denied', available: false };
    const { container } = render(<PushToggle />);
    expect(container.firstChild).toBeNull();
  });

  it('shows the Add-to-Home-Screen hint on iOS-not-installed', () => {
    state.capability = { supported: true, iosNeedsInstall: true, permission: 'default', available: false };
    render(<PushToggle />);
    expect(screen.getByTestId('push-ios-hint')).toBeTruthy();
    expect(screen.queryByTestId('push-toggle')).toBeNull();
  });

  it('shows a disabled toggle + settings hint when permission is denied', () => {
    state.capability = { supported: true, iosNeedsInstall: false, permission: 'denied', available: false };
    render(<PushToggle />);
    const toggle = screen.getByTestId('push-toggle') as HTMLButtonElement;
    expect(toggle.disabled).toBe(true);
    expect(screen.getByText(/device settings/i)).toBeTruthy();
  });

  it('enables on click when off, and states the copy is content-free', () => {
    state.capability = { supported: true, iosNeedsInstall: false, permission: 'default', available: true };
    state.enabled = false;
    render(<PushToggle />);
    const toggle = screen.getByTestId('push-toggle');
    expect(toggle.getAttribute('aria-checked')).toBe('false');
    expect(screen.getByText(/never shows your notes/i)).toBeTruthy();
    fireEvent.click(toggle);
    expect(state.enable).toHaveBeenCalled();
  });

  it('disables on click when on', () => {
    state.capability = { supported: true, iosNeedsInstall: false, permission: 'granted', available: true };
    state.enabled = true;
    render(<PushToggle />);
    const toggle = screen.getByTestId('push-toggle');
    expect(toggle.getAttribute('aria-checked')).toBe('true');
    fireEvent.click(toggle);
    expect(state.disable).toHaveBeenCalled();
  });
});

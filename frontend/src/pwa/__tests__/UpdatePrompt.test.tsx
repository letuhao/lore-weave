// M4/MB5 — the update prompt is hidden until a new SW is waiting, and accepting it calls
// applyUpdate (which posts SKIP_WAITING). No silent hot-swap.
import { render, screen, fireEvent, act } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';

let readyCb: (() => void) | null = null;
const applyUpdate = vi.fn();
vi.mock('../registerSW', () => ({
  onUpdateReady: (cb: () => void) => {
    readyCb = cb;
    return () => {
      readyCb = null;
    };
  },
  applyUpdate: () => applyUpdate(),
}));

import { UpdatePrompt } from '../UpdatePrompt';

describe('UpdatePrompt (MB5)', () => {
  it('is hidden until an update is ready, then shows and applies on click', () => {
    render(<UpdatePrompt />);
    expect(screen.queryByTestId('pwa-update-prompt')).toBeNull();

    // Simulate a new SW finishing install.
    act(() => readyCb?.());
    expect(screen.getByTestId('pwa-update-prompt')).toBeTruthy();

    fireEvent.click(screen.getByText('Refresh'));
    expect(applyUpdate).toHaveBeenCalledTimes(1);
  });
});

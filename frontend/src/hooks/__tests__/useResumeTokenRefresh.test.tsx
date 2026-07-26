// MB8 — on foreground resume (visibilitychange → visible) the hook proactively refreshes the
// access token so a resumed SSE/voice stream reconnects with a live token, not a dead one.
import { render } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

const refreshAccessToken = vi.fn();
vi.mock('@/api', () => ({ refreshAccessToken: () => refreshAccessToken() }));

import { useResumeTokenRefresh } from '../useResumeTokenRefresh';

function Probe() {
  useResumeTokenRefresh();
  return null;
}

function setVisibility(state: 'visible' | 'hidden') {
  Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => state });
}

describe('useResumeTokenRefresh (MB8)', () => {
  beforeEach(() => {
    refreshAccessToken.mockClear();
    setVisibility('visible');
  });

  it('refreshes the token when the tab becomes visible', () => {
    render(<Probe />);
    setVisibility('visible');
    document.dispatchEvent(new Event('visibilitychange'));
    expect(refreshAccessToken).toHaveBeenCalledTimes(1);
  });

  it('does NOT refresh when the tab goes hidden (only on resume)', () => {
    render(<Probe />);
    setVisibility('hidden');
    document.dispatchEvent(new Event('visibilitychange'));
    expect(refreshAccessToken).not.toHaveBeenCalled();
  });

  it('removes the listener on unmount (no refresh after teardown)', () => {
    const { unmount } = render(<Probe />);
    unmount();
    setVisibility('visible');
    document.dispatchEvent(new Event('visibilitychange'));
    expect(refreshAccessToken).not.toHaveBeenCalled();
  });
});

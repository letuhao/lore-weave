// M2 — the platform home renders each tile by its degrade status, and the assistant hero ALWAYS
// renders (the front door never blanks — even while loading or when every tile is down).
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, vi } from 'vitest';

const useHome = vi.fn();
vi.mock('../../hooks/useHome', () => ({ useHome: () => useHome() }));

import { PlatformHomePage } from '../PlatformHomePage';
import type { HomeResponse } from '../../types';

const okData: HomeResponse = {
  tiles: {
    activity: { status: 'ok', data: { unread: 4 } },
    books: { status: 'ok', data: [{ id: 'b1', title: 'My Novel' }] },
    jobs: { status: 'empty', data: [] },
  },
  generated_at: '2026-07-15T00:00:00Z',
};

function renderHome() {
  return render(
    <MemoryRouter>
      <PlatformHomePage />
    </MemoryRouter>,
  );
}

describe('PlatformHomePage', () => {
  it('renders the assistant hero even while loading (front door never blanks)', () => {
    useHome.mockReturnValue({ data: undefined, isLoading: true, refetch: vi.fn() });
    renderHome();
    expect(screen.getByTestId('home-assistant-hero')).toBeTruthy();
    expect(screen.getByTestId('home-assistant-hero').getAttribute('href')).toBe('/assistant');
  });

  it('renders ok tiles with data', () => {
    useHome.mockReturnValue({ data: okData, isLoading: false, refetch: vi.fn() });
    renderHome();
    expect(screen.getByTestId('home-unread').textContent).toContain('4 unread');
    expect(screen.getByText('My Novel')).toBeTruthy();
    // jobs tile is empty → honest empty copy, not a blank
    expect(screen.getByText(/No background jobs/i)).toBeTruthy();
  });

  it('a degraded tile shows a Retry that calls refetch — the page still renders', () => {
    const refetch = vi.fn();
    useHome.mockReturnValue({
      data: {
        tiles: {
          activity: { status: 'degraded', error: 'down' },
          books: { status: 'ok', data: [] },
          jobs: { status: 'ok', data: [] },
        },
        generated_at: 'x',
      },
      isLoading: false,
      refetch,
    });
    renderHome();
    // hero still there; the activity tile shows Retry
    expect(screen.getByTestId('home-assistant-hero')).toBeTruthy();
    const retry = screen.getAllByText('Retry')[0];
    fireEvent.click(retry);
    expect(refetch).toHaveBeenCalled();
  });

  it('shows a stale banner when the BFF served a cached snapshot', () => {
    useHome.mockReturnValue({ data: { ...okData, stale: true }, isLoading: false, refetch: vi.fn() });
    renderHome();
    expect(screen.getByText(/last-loaded home/i)).toBeTruthy();
  });
});

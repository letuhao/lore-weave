// The mobile Back affordance (fixes "cannot return"): hidden on the root tab routes, shown on every
// nested page, and it navigates back (never a dead-end).
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, vi } from 'vitest';

const navigate = vi.fn();
vi.mock('react-router-dom', async (orig) => {
  const actual = (await orig()) as Record<string, unknown>;
  return { ...actual, useNavigate: () => navigate };
});

import { MobileTopBar } from '../MobileTopBar';

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <MobileTopBar />
    </MemoryRouter>,
  );
}

describe('MobileTopBar', () => {
  it('renders nothing on a root tab route (tab bar handles it)', () => {
    renderAt('/home');
    expect(screen.queryByTestId('mobile-top-bar')).toBeNull();
  });

  it('shows a Back button on a nested page', () => {
    renderAt('/worlds/abc');
    expect(screen.getByTestId('mobile-top-bar')).toBeTruthy();
    expect(screen.getByTestId('mobile-back').getAttribute('aria-label')).toBe('Back');
  });

  it('Back navigates (never a no-op dead-end)', () => {
    navigate.mockClear();
    renderAt('/books/xyz');
    fireEvent.click(screen.getByTestId('mobile-back'));
    // Either navigate(-1) (has history) or navigate('/home') (cold deep-link) — both are a navigation.
    expect(navigate).toHaveBeenCalledTimes(1);
  });
});

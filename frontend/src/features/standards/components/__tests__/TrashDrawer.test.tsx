import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

const tiering = vi.hoisted(() => ({
  listUserGenreTrash: vi.fn(),
  listUserKindTrash: vi.fn(),
  restoreUserGenre: vi.fn(),
  purgeUserGenre: vi.fn(),
  restoreUserKind: vi.fn(),
  purgeUserKind: vi.fn(),
}));
vi.mock('@/features/glossary/tieringApi', () => ({ tieringApi: tiering }));

import { TrashDrawer } from '../TrashDrawer';

function wrap(children: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{children}</QueryClientProvider>);
}

beforeEach(() => {
  Object.values(tiering).forEach((m) => m.mockReset());
  tiering.listUserGenreTrash.mockResolvedValue([
    { genre_id: 'g1', tier: 'user', code: 'wuxia', name: 'Wuxia', icon: '🥋', color: '#000', sort_order: 0 },
  ]);
  tiering.listUserKindTrash.mockResolvedValue([
    { user_kind_id: 'k1', code: 'faction', name: 'Faction', icon: '🏴', color: '#000', is_active: false },
  ]);
  tiering.restoreUserGenre.mockResolvedValue({});
  tiering.purgeUserKind.mockResolvedValue(undefined);
});

describe('TrashDrawer', () => {
  it('lists trashed genres and kinds', async () => {
    wrap(<TrashDrawer onClose={vi.fn()} />);
    expect(await screen.findByTestId('restore-wuxia')).toBeInTheDocument();
    expect(screen.getByTestId('restore-faction')).toBeInTheDocument();
  });

  it('restores a trashed genre', async () => {
    wrap(<TrashDrawer onClose={vi.fn()} />);
    fireEvent.click(await screen.findByTestId('restore-wuxia'));
    await waitFor(() => expect(tiering.restoreUserGenre).toHaveBeenCalledWith('g1', 'tok'));
  });

  it('purges a trashed kind permanently', async () => {
    wrap(<TrashDrawer onClose={vi.fn()} />);
    fireEvent.click(await screen.findByTestId('purge-faction'));
    await waitFor(() => expect(tiering.purgeUserKind).toHaveBeenCalledWith('k1', 'tok'));
  });
});

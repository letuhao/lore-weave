import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import type { Genre } from '@/features/glossary/tieringTypes';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

const tiering = vi.hoisted(() => ({
  listUserKindGenres: vi.fn(),
  setUserKindGenres: vi.fn(),
}));
vi.mock('@/features/glossary/tieringApi', () => ({ tieringApi: tiering }));

import { KindGenresModal } from '../KindGenresModal';

function genre(id: string, code: string): Genre {
  return { genre_id: id, tier: 'user', code, name: code, icon: '🐉', color: '#000', sort_order: 0 };
}
const USER_GENRES = [genre('g-fan', 'fantasy'), genre('g-xx', 'xianxia'), genre('g-rom', 'romance')];

function wrap(children: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{children}</QueryClientProvider>);
}

beforeEach(() => {
  tiering.listUserKindGenres.mockReset();
  tiering.setUserKindGenres.mockReset();
  // The kind is currently linked to fantasy only.
  tiering.listUserKindGenres.mockResolvedValue([{ kind_id: 'k1', genre_id: 'g-fan' }]);
  tiering.setUserKindGenres.mockResolvedValue([]);
});

describe('KindGenresModal', () => {
  it('seeds checkboxes from the current links and saves the toggled set', async () => {
    wrap(
      <KindGenresModal userKindId="k1" kindName="Character" userGenres={USER_GENRES} onClose={vi.fn()} />,
    );
    // Wait for the links to load + seed.
    const fantasy = await screen.findByTestId('link-genre-fantasy');
    expect((fantasy as HTMLInputElement).checked).toBe(true);
    expect((screen.getByTestId('link-genre-xianxia') as HTMLInputElement).checked).toBe(false);

    // Add xianxia, remove fantasy.
    fireEvent.click(screen.getByTestId('link-genre-xianxia'));
    fireEvent.click(fantasy);
    fireEvent.click(screen.getByTestId('links-save'));

    await waitFor(() => expect(tiering.setUserKindGenres).toHaveBeenCalled());
    const [kindId, ids] = tiering.setUserKindGenres.mock.calls[0];
    expect(kindId).toBe('k1');
    expect([...ids].sort()).toEqual(['g-xx']);
  });
});

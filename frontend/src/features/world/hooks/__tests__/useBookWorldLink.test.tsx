import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';

vi.mock('@/auth', () => ({
  useAuth: () => ({ accessToken: 'tok', user: { user_id: 'u1' } }),
}));

const moveBookMock = vi.fn();
const removeBookMock = vi.fn();
vi.mock('../../api', () => ({
  worldsApi: {
    moveBookIntoWorld: (...a: unknown[]) => moveBookMock(...a),
    removeBookFromWorld: (...a: unknown[]) => removeBookMock(...a),
  },
}));

import { useBookWorldLink } from '../useBookWorldLink';

function wrapper({ children }: PropsWithChildren) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  moveBookMock.mockReset();
  removeBookMock.mockReset();
});

describe('useBookWorldLink (W6/G3)', () => {
  it('link attaches the book to a world', async () => {
    moveBookMock.mockResolvedValue({ book_id: 'b1', world_id: 'w1' });
    const { result } = renderHook(() => useBookWorldLink('b1'), { wrapper });
    await act(async () => { await result.current.link('w1'); });
    expect(moveBookMock).toHaveBeenCalledWith('tok', 'w1', 'b1');
  });

  it('unlink detaches the book from a world', async () => {
    removeBookMock.mockResolvedValue(undefined);
    const { result } = renderHook(() => useBookWorldLink('b1'), { wrapper });
    await act(async () => { await result.current.unlink('w1'); });
    expect(removeBookMock).toHaveBeenCalledWith('tok', 'w1', 'b1');
  });
});

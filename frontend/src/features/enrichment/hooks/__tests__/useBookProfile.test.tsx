import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

const toastMocks = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }));
vi.mock('sonner', () => ({ toast: toastMocks }));

const getMock = vi.fn();
const putMock = vi.fn();
const suggestMock = vi.fn();
vi.mock('../../api', async () => {
  const actual = await vi.importActual<Record<string, unknown>>('../../api');
  return {
    ...actual,
    enrichmentApi: {
      getBookProfile: (...a: unknown[]) => getMock(...a),
      putBookProfile: (...a: unknown[]) => putMock(...a),
      suggestBookProfile: (...a: unknown[]) => suggestMock(...a),
    },
  };
});

import { useBookProfile } from '../useBookProfile';
import type { BookProfile, BookProfileInput } from '../../types';

const BOOK = 'book-1';

const P = (over: Partial<BookProfile> = {}): BookProfile => ({
  book_id: BOOK,
  worldview: 'w',
  language: 'zh',
  era_policy: null,
  voice: null,
  anachronism_markers: [],
  anachronism_enabled: false,
  dimension_overrides: {},
  profile_source: 'manual',
  ...over,
});

const INPUT: BookProfileInput = {
  worldview: 'edited',
  language: 'zh',
  era_policy: null,
  voice: null,
  anachronism_markers: [{ term: '火车', reason: 'modern' }],
  dimension_overrides: {},
};

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const setSpy = vi.spyOn(qc, 'setQueryData');
  const Wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { Wrapper, setSpy };
}

beforeEach(() => {
  [getMock, putMock, suggestMock].forEach((m) => m.mockReset());
  Object.values(toastMocks).forEach((m) => m.mockReset());
  getMock.mockResolvedValue(P());
});

describe('useBookProfile', () => {
  it('loads the profile via getBookProfile(bookId, token)', async () => {
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useBookProfile(BOOK), { wrapper: Wrapper });
    await waitFor(() => expect(result.current.profile).not.toBeNull());
    expect(getMock).toHaveBeenCalledWith(BOOK, 'tok');
    expect(result.current.profile?.worldview).toBe('w');
  });

  it('save sends the FULL body, toasts, primes the cache, returns the saved profile', async () => {
    const saved = P({ worldview: 'edited', anachronism_markers: [{ term: '火车', reason: 'modern' }] });
    putMock.mockResolvedValue(saved);
    const { Wrapper, setSpy } = makeWrapper();
    const { result } = renderHook(() => useBookProfile(BOOK), { wrapper: Wrapper });

    let out: unknown;
    await act(async () => {
      out = await result.current.save(INPUT);
    });

    expect(putMock).toHaveBeenCalledWith(BOOK, INPUT, 'tok');
    expect(toastMocks.success).toHaveBeenCalledWith('settings.saved');
    expect(setSpy).toHaveBeenCalledWith(['book-profile', BOOK], saved);
    expect(out).toBe(saved);
  });

  it('save on API error toasts the message + returns null', async () => {
    putMock.mockRejectedValue(new Error('save boom'));
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useBookProfile(BOOK), { wrapper: Wrapper });
    let out: unknown;
    await act(async () => {
      out = await result.current.save(INPUT);
    });
    expect(out).toBeNull();
    expect(toastMocks.error).toHaveBeenCalledWith('save boom');
  });

  it('suggest calls suggestBookProfile with project_id:=bookId + model + ids, returns the draft', async () => {
    const draft = { worldview: 'ai', language: 'vi', era_policy: null, voice: null, dimension_overrides: {}, profile_source: 'ai_suggested' };
    suggestMock.mockResolvedValue(draft);
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useBookProfile(BOOK), { wrapper: Wrapper });
    let out: unknown;
    await act(async () => {
      out = await result.current.suggest('model-9', ['ch-1']);
    });
    expect(suggestMock).toHaveBeenCalledWith(
      BOOK,
      { project_id: BOOK, suggest_model_ref: 'model-9', sample_chapter_ids: ['ch-1'] },
      'tok',
    );
    expect(toastMocks.success).toHaveBeenCalledWith('settings.suggested');
    expect(out).toBe(draft);
  });

  it('suggest on API error toasts + returns null', async () => {
    suggestMock.mockRejectedValue(new Error('suggest boom'));
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useBookProfile(BOOK), { wrapper: Wrapper });
    let out: unknown;
    await act(async () => {
      out = await result.current.suggest('model-9');
    });
    expect(out).toBeNull();
    expect(toastMocks.error).toHaveBeenCalledWith('suggest boom');
  });
});

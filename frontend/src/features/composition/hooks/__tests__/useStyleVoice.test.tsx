import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  useDeleteVoiceProfile, useSetStyleProfile, useSetVoiceProfile, useStyleProfiles, useVoiceProfiles,
} from '../useStyleVoice';

const api = vi.hoisted(() => ({
  getStyleProfiles: vi.fn(),
  putStyleProfile: vi.fn(),
  getVoiceProfiles: vi.fn(),
  putVoiceProfile: vi.fn(),
  deleteVoiceProfile: vi.fn(),
}));
vi.mock('../../api', () => ({ compositionApi: api }));

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return ({ children }: { children: React.ReactNode }) => <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

beforeEach(() => Object.values(api).forEach((f) => f.mockReset()));

describe('useStyleVoice queries (T3.5)', () => {
  it('useStyleProfiles selects items[]', async () => {
    api.getStyleProfiles.mockResolvedValue({ items: [{ scope_type: 'work', scope_id: 'p1', density: 40, pace: 60 }] });
    const { result } = renderHook(() => useStyleProfiles('p1', 't'), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.data).toEqual([{ scope_type: 'work', scope_id: 'p1', density: 40, pace: 60 }]));
  });

  it('useVoiceProfiles selects items[]', async () => {
    api.getVoiceProfiles.mockResolvedValue({ items: [{ entity_id: 'e1', entity_name: 'Kael', tags: ['terse'] }] });
    const { result } = renderHook(() => useVoiceProfiles('p1', 't'), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.data?.[0].entity_name).toBe('Kael'));
  });
});

describe('useStyleVoice mutations (T3.5)', () => {
  it('useSetStyleProfile PUTs the scope row', async () => {
    api.putStyleProfile.mockResolvedValue({});
    const { result } = renderHook(() => useSetStyleProfile('p1', 't'), { wrapper: makeWrapper() });
    act(() => result.current.mutate({ scope_type: 'scene', scope_id: 's1', density: 80, pace: 20 }));
    await waitFor(() =>
      expect(api.putStyleProfile).toHaveBeenCalledWith('p1', { scope_type: 'scene', scope_id: 's1', density: 80, pace: 20 }, 't'),
    );
  });

  it('useSetVoiceProfile PUTs the voice row', async () => {
    api.putVoiceProfile.mockResolvedValue({});
    const { result } = renderHook(() => useSetVoiceProfile('p1', 't'), { wrapper: makeWrapper() });
    act(() => result.current.mutate({ entity_id: 'e1', entity_name: 'Kael', tags: ['wry'] }));
    await waitFor(() =>
      expect(api.putVoiceProfile).toHaveBeenCalledWith('p1', { entity_id: 'e1', entity_name: 'Kael', tags: ['wry'] }, 't'),
    );
  });

  it('useDeleteVoiceProfile DELETEs by entity id', async () => {
    api.deleteVoiceProfile.mockResolvedValue({ removed: true });
    const { result } = renderHook(() => useDeleteVoiceProfile('p1', 't'), { wrapper: makeWrapper() });
    act(() => result.current.mutate('e1'));
    await waitFor(() => expect(api.deleteVoiceProfile).toHaveBeenCalledWith('p1', 'e1', 't'));
  });
});

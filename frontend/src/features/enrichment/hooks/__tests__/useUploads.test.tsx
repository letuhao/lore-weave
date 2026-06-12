import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

const apiMocks = vi.hoisted(() => ({ uploadFile: vi.fn(), getUpload: vi.fn() }));
vi.mock('../../api', () => ({ enrichmentApi: apiMocks }));

import { useUploads } from '../useUploads';

const f = (name: string) => new File(['data'], name, { type: 'text/plain' });

beforeEach(() => {
  apiMocks.uploadFile.mockReset();
  apiMocks.getUpload.mockReset();
});

describe('useUploads', () => {
  it('upload that returns ready immediately lands as a ready item + readyId', async () => {
    apiMocks.uploadFile.mockResolvedValue({ upload_id: 'u1', filename: 'a.txt', status: 'ready', extracted_chars: 10 });
    const { result } = renderHook(() => useUploads('book-1'));
    await act(async () => { await result.current.upload(f('a.txt'), 'public_domain'); });
    await waitFor(() => expect(result.current.readyIds).toEqual(['u1']));
    expect(apiMocks.uploadFile).toHaveBeenCalledWith('book-1', expect.any(File), 'public_domain', 'tok');
    expect(result.current.items[0]).toMatchObject({ id: 'u1', status: 'ready' });
  });

  it('a failed upload marks the item failed (not ready)', async () => {
    apiMocks.uploadFile.mockRejectedValue(new Error('storage boom'));
    const { result } = renderHook(() => useUploads('book-1'));
    await act(async () => { await result.current.upload(f('b.txt'), 'owned'); });
    await waitFor(() => expect(result.current.items[0].status).toBe('failed'));
    expect(result.current.items[0].error).toBe('storage boom');
    expect(result.current.readyIds).toEqual([]);
  });

  it('remove drops an item by id', async () => {
    apiMocks.uploadFile.mockResolvedValue({ upload_id: 'u2', filename: 'c.txt', status: 'ready' });
    const { result } = renderHook(() => useUploads('book-1'));
    await act(async () => { await result.current.upload(f('c.txt'), 'licensed'); });
    await waitFor(() => expect(result.current.items).toHaveLength(1));
    act(() => result.current.remove('u2'));
    expect(result.current.items).toHaveLength(0);
  });
});

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';

// WS-2.6c / D17 — forget-a-person calls the BFF with the person's NAME. A failed SOURCE redaction is
// NON-FATAL (the structured memory is already erased): resolve `forgotten:true` + warn, never throw.

const forgetPerson = vi.fn();
const toastSuccess = vi.fn();
const toastWarning = vi.fn();
const toastError = vi.fn();

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
vi.mock('../../api', () => ({ assistantApi: { forgetPerson: (...a: unknown[]) => forgetPerson(...a) } }));
vi.mock('sonner', () => ({
  toast: {
    success: (...a: unknown[]) => toastSuccess(...a),
    warning: (...a: unknown[]) => toastWarning(...a),
    error: (...a: unknown[]) => toastError(...a),
  },
}));

import { useForgetEntity } from '../useForgetEntity';

beforeEach(() => {
  forgetPerson.mockReset();
  toastSuccess.mockReset();
  toastWarning.mockReset();
  toastError.mockReset();
});

describe('useForgetEntity', () => {
  it('forgets by name and reports full success when redaction also succeeded', async () => {
    forgetPerson.mockResolvedValue({ forgotten: true, name: 'Minh', entities_deleted: 1 });
    const { result } = renderHook(() => useForgetEntity('book-1'));
    let res: unknown;
    await act(async () => {
      res = await result.current.forget('  Minh  ');
    });
    expect(forgetPerson).toHaveBeenCalledWith('tok', { book_id: 'book-1', name: 'Minh' }); // trimmed
    expect((res as { forgotten: boolean }).forgotten).toBe(true);
    expect(toastSuccess).toHaveBeenCalled();
    expect(result.current.forgettingName).toBeNull();
  });

  it('treats a failed redaction as NON-FATAL — still forgotten:true, warns (name may linger in prose)', async () => {
    forgetPerson.mockResolvedValue({ forgotten: true, name: 'Minh', redaction_error: 'book down' });
    const { result } = renderHook(() => useForgetEntity('book-1'));
    let res: unknown;
    await act(async () => {
      res = await result.current.forget('Minh');
    });
    expect((res as { forgotten: boolean }).forgotten).toBe(true);
    expect(toastWarning).toHaveBeenCalled();
    expect(toastSuccess).not.toHaveBeenCalled();
  });

  it('returns null and toasts on a failed erase (never silently swallows)', async () => {
    forgetPerson.mockRejectedValue(new Error('403'));
    const { result } = renderHook(() => useForgetEntity('book-1'));
    let res: unknown = 'unset';
    await act(async () => {
      res = await result.current.forget('Minh');
    });
    expect(res).toBeNull();
    expect(toastError).toHaveBeenCalled();
  });

  it('no-ops on an empty name (never calls the destructive API)', async () => {
    const { result } = renderHook(() => useForgetEntity('book-1'));
    let res: unknown = 'unset';
    await act(async () => {
      res = await result.current.forget('  ');
    });
    expect(res).toBeNull();
    expect(forgetPerson).not.toHaveBeenCalled();
  });
});

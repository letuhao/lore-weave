import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';

// WS-2.6a / D17 — the correction hook resolves the re-extract model off the assistant session (like
// end-of-day), forwards the edited body, and treats a FAILED graph reconcile as NON-FATAL (the SSOT
// amend already landed): the promise still resolves `amended:true` and warns rather than throwing.

const listSessions = vi.fn();
const correctDiaryEntry = vi.fn();
const toastSuccess = vi.fn();
const toastWarning = vi.fn();
const toastError = vi.fn();

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
vi.mock('@/features/chat/api', () => ({ chatApi: { listSessions: (...a: unknown[]) => listSessions(...a) } }));
vi.mock('../../api', () => ({
  assistantApi: { correctDiaryEntry: (...a: unknown[]) => correctDiaryEntry(...a) },
}));
vi.mock('sonner', () => ({
  toast: {
    success: (...a: unknown[]) => toastSuccess(...a),
    warning: (...a: unknown[]) => toastWarning(...a),
    error: (...a: unknown[]) => toastError(...a),
  },
}));

import { useDiaryCorrection } from '../useDiaryCorrection';

beforeEach(() => {
  listSessions.mockReset();
  correctDiaryEntry.mockReset();
  toastSuccess.mockReset();
  toastWarning.mockReset();
  toastError.mockReset();
  listSessions.mockResolvedValue({
    items: [{ session_kind: 'assistant', model_source: 'byok', model_ref: 'uuid-123' }],
  });
});

describe('useDiaryCorrection', () => {
  it('forwards the edited body with the session model and reports success on a full reconcile', async () => {
    correctDiaryEntry.mockResolvedValue({ amended: true, reextract_enqueued: true, entry_date: '2026-07-14' });
    const { result } = renderHook(() => useDiaryCorrection('book-1'));

    let res: unknown;
    await act(async () => {
      res = await result.current.correct('c1', '  corrected text  ', 'A day');
    });

    expect(correctDiaryEntry).toHaveBeenCalledWith('tok', {
      book_id: 'book-1',
      chapter_id: 'c1',
      body: 'corrected text', // trimmed
      title: 'A day',
      model_source: 'byok',
      model_ref: 'uuid-123',
    });
    expect((res as { amended: boolean }).amended).toBe(true);
    expect(toastSuccess).toHaveBeenCalled();
    expect(result.current.correctingId).toBeNull(); // cleared in finally
  });

  it('treats a failed reconcile as NON-FATAL — still amended:true, warns (correction saved, sync pending)', async () => {
    correctDiaryEntry.mockResolvedValue({ amended: true, reextract_enqueued: false, reextract_error: 'chat down' });
    const { result } = renderHook(() => useDiaryCorrection('book-1'));
    let res: unknown;
    await act(async () => {
      res = await result.current.correct('c1', 'x');
    });
    expect((res as { amended: boolean }).amended).toBe(true);
    expect(toastWarning).toHaveBeenCalled();
    expect(toastSuccess).not.toHaveBeenCalled();
  });

  it('returns null (and toasts) with no reachable model, never calling correct blindly', async () => {
    listSessions.mockResolvedValue({ items: [] }); // no session ⇒ no model
    const { result } = renderHook(() => useDiaryCorrection('book-1'));
    let res: unknown = 'unset';
    await act(async () => {
      res = await result.current.correct('c1', 'x');
    });
    expect(res).toBeNull();
    expect(correctDiaryEntry).not.toHaveBeenCalled();
    expect(toastError).toHaveBeenCalled();
  });

  it('no-ops on empty body (does not resolve a session or call the API)', async () => {
    const { result } = renderHook(() => useDiaryCorrection('book-1'));
    let res: unknown = 'unset';
    await act(async () => {
      res = await result.current.correct('c1', '   ');
    });
    expect(res).toBeNull();
    expect(listSessions).not.toHaveBeenCalled();
    expect(correctDiaryEntry).not.toHaveBeenCalled();
  });
});

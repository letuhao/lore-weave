// A3 — the autonomous-schedule controller: reads EFFECTIVE per-job state (a job_kind with no server row
// is OFF — fail-closed), and writing re-reads the server truth rather than trusting the local flip.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';

const getSchedule = vi.fn();
const setSchedule = vi.fn();
vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
vi.mock('../../api', () => ({ assistantApi: { getSchedule: (...a: unknown[]) => getSchedule(...a), setSchedule: (...a: unknown[]) => setSchedule(...a) } }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { useAssistantSchedule } from '../useAssistantSchedule';

beforeEach(() => {
  getSchedule.mockReset();
  setSchedule.mockReset();
});

describe('useAssistantSchedule (A3)', () => {
  it('reflects effective state and is fail-closed for job_kinds with no row', async () => {
    getSchedule.mockResolvedValue({ schedules: [{ job_kind: 'eod_distill', enabled: true, next_fire_at: '2026-07-17T21:00:00Z' }] });
    const { result } = renderHook(() => useAssistantSchedule());
    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.isEnabled('eod_distill')).toBe(true);
    expect(result.current.nextFireAt('eod_distill')).toBe('2026-07-17T21:00:00Z');
    // No row for these → OFF, never assumed on.
    expect(result.current.isEnabled('nudge')).toBe(false);
    expect(result.current.isEnabled('weekly_reflection')).toBe(false);
  });

  it('enabling writes the opt-in then re-reads the server truth', async () => {
    getSchedule.mockResolvedValueOnce({ schedules: [] }); // initial: all OFF
    setSchedule.mockResolvedValueOnce({ enabled: true });
    getSchedule.mockResolvedValueOnce({ schedules: [{ job_kind: 'eod_distill', enabled: true }] }); // re-read after write
    const { result } = renderHook(() => useAssistantSchedule());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.isEnabled('eod_distill')).toBe(false);

    await act(async () => { await result.current.setEnabled('eod_distill', true, 'UTC'); });
    expect(setSchedule).toHaveBeenCalledWith('tok', { job_kind: 'eod_distill', enabled: true, timezone: 'UTC' });
    expect(result.current.isEnabled('eod_distill')).toBe(true); // reflects the RE-READ, not an optimistic flip
  });

  it('a read failure leaves every toggle at the fail-closed default (OFF)', async () => {
    getSchedule.mockRejectedValueOnce(new Error('scheduler down'));
    const { result } = renderHook(() => useAssistantSchedule());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.isEnabled('eod_distill')).toBe(false);
  });
});

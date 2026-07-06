import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { act, renderHook } from '@testing-library/react';

// Mock the api layer; the hook owns create → poll-while-active → terminal-stop + the actions.
const createRun = vi.fn();
const getRun = vi.fn();
const selfCheck = vi.fn();
const validate = vi.fn();
const compile = vi.fn();
vi.mock('../api', () => ({
  planForgeApi: {
    createRun: (...a: unknown[]) => createRun(...a),
    getRun: (...a: unknown[]) => getRun(...a),
    selfCheck: (...a: unknown[]) => selfCheck(...a),
    validate: (...a: unknown[]) => validate(...a),
    compile: (...a: unknown[]) => compile(...a),
  },
  // real isAck (an ack has run_id but no id)
  isAck: (r: { run_id?: string; id?: string }) => r.run_id !== undefined && r.id === undefined,
}));

import { usePlanRun } from '../hooks/usePlanRun';

const detail = (over: Record<string, unknown> = {}) => ({
  id: 'r1', book_id: 'b1', status: 'proposed', mode: 'llm', model_ref: 'm1',
  source_checksum: 'abc', active_job_id: null, job_status: null, error_detail: null,
  checkpoint_state: null, arcs: [], artifacts: [], created_at: '', updated_at: '', ...over,
});

beforeEach(() => {
  vi.useFakeTimers();
  createRun.mockReset(); getRun.mockReset(); selfCheck.mockReset(); validate.mockReset(); compile.mockReset();
});
afterEach(() => { vi.useRealTimers(); });

describe('usePlanRun', () => {
  it('rules mode: 201 full detail used directly, no poll (terminal)', async () => {
    createRun.mockResolvedValue(detail({ mode: 'rules', model_ref: null }));
    const { result } = renderHook(() => usePlanRun('b1', 'tok'));
    await act(async () => { await result.current.createRun({ source_markdown: '# x', mode: 'rules' }); });
    expect(createRun).toHaveBeenCalledWith('b1', { source_markdown: '# x', mode: 'rules' }, 'tok');
    expect(result.current.run?.id).toBe('r1');
    expect(result.current.polling).toBe(false);
    // no active job → the poll effect installs no timer
    await act(async () => { await vi.advanceTimersByTimeAsync(5000); });
    expect(getRun).not.toHaveBeenCalled();
  });

  it('llm mode: 202 ack → fetch detail → poll while running → stop on terminal', async () => {
    createRun.mockResolvedValue({ run_id: 'r1', job_id: 'j1', status: 'pending' }); // ack, no id
    getRun
      .mockResolvedValueOnce(detail({ status: 'pending', active_job_id: 'j1', job_status: 'running' })) // post-ack fetch
      .mockResolvedValueOnce(detail({ status: 'pending', active_job_id: 'j1', job_status: 'running' })) // poll tick 1
      .mockResolvedValueOnce(detail({ status: 'proposed', active_job_id: null, job_status: 'completed' })); // terminal

    const { result } = renderHook(() => usePlanRun('b1', 'tok'));
    await act(async () => { await result.current.createRun({ source_markdown: '# x', mode: 'llm', model_ref: 'm1' }); });
    // after the ack fetch the run has an active job → polling
    expect(result.current.polling).toBe(true);
    expect(getRun).toHaveBeenCalledTimes(1);

    // tick 1 — still running, re-arms
    await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
    expect(getRun).toHaveBeenCalledTimes(2);
    expect(result.current.polling).toBe(true);

    // tick 2 — terminal, stops
    await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
    expect(getRun).toHaveBeenCalledTimes(3);
    expect(result.current.run?.status).toBe('proposed');
    expect(result.current.polling).toBe(false);

    // no further polls after terminal
    await act(async () => { await vi.advanceTimersByTimeAsync(6000); });
    expect(getRun).toHaveBeenCalledTimes(3);
  });

  it('self-check + validate populate their slices', async () => {
    createRun.mockResolvedValue(detail({ mode: 'rules', model_ref: null }));
    selfCheck.mockResolvedValue({ gaps: [{ path: 'a', severity: 'warning', message: 'g' }], fidelity_score: 0.8 });
    validate.mockResolvedValue({ passed: true, rules: [{ id: 'r', passed: true, message: 'ok' }], fidelity_score: 0.9, fidelity_report_id: 'f1' });
    const { result } = renderHook(() => usePlanRun('b1', 'tok'));
    await act(async () => { await result.current.createRun({ source_markdown: '# x', mode: 'rules' }); });
    await act(async () => { await result.current.runSelfCheck(); });
    expect(result.current.selfCheck?.gaps).toHaveLength(1);
    await act(async () => { await result.current.runValidate(); });
    expect(result.current.validation?.passed).toBe(true);
  });

  it('surfaces a create error', async () => {
    createRun.mockRejectedValue(new Error('boom'));
    const { result } = renderHook(() => usePlanRun('b1', 'tok'));
    await act(async () => { await result.current.createRun({ source_markdown: '# x', mode: 'rules' }); });
    expect(result.current.error).toBe('boom');
    expect(result.current.run).toBeNull();
  });

  // D-PLANFORGE-NO-RESUME — the Runs-list "click a row" / "+ New propose" paths.
  it('loadRun fetches an existing run by id (GET, not a fresh propose) and clears prior readouts', async () => {
    getRun.mockResolvedValue(detail({ id: 'old-run', status: 'validated' }));
    const { result } = renderHook(() => usePlanRun('b1', 'tok'));
    await act(async () => { await result.current.loadRun('old-run'); });
    expect(getRun).toHaveBeenCalledWith('b1', 'old-run', 'tok');
    expect(createRun).not.toHaveBeenCalled();
    expect(result.current.run?.id).toBe('old-run');
    expect(result.current.selfCheck).toBeNull();
    expect(result.current.validation).toBeNull();
  });

  it('loadRun surfaces a fetch error the same way createRun does', async () => {
    getRun.mockRejectedValue(new Error('not found'));
    const { result } = renderHook(() => usePlanRun('b1', 'tok'));
    await act(async () => { await result.current.loadRun('missing'); });
    expect(result.current.error).toBe('not found');
    expect(result.current.run).toBeNull();
  });

  it('resetRun clears the run back to empty — local state only, no server call', async () => {
    createRun.mockResolvedValue(detail({ mode: 'rules', model_ref: null }));
    selfCheck.mockResolvedValue({ gaps: [], fidelity_score: 0.5 });
    const { result } = renderHook(() => usePlanRun('b1', 'tok'));
    await act(async () => { await result.current.createRun({ source_markdown: '# x', mode: 'rules' }); });
    await act(async () => { await result.current.runSelfCheck(); });
    expect(result.current.run).not.toBeNull();
    act(() => { result.current.resetRun(); });
    expect(result.current.run).toBeNull();
    expect(result.current.selfCheck).toBeNull();
    expect(getRun).not.toHaveBeenCalled();
    expect(createRun).toHaveBeenCalledTimes(1); // resetRun itself never calls the API
  });

  it('resetRun while a poll is active tears the poll down (run stays null after the tick)', async () => {
    createRun.mockResolvedValue({ run_id: 'r1', job_id: 'j1', status: 'pending' });
    getRun.mockResolvedValueOnce(detail({ status: 'pending', active_job_id: 'j1', job_status: 'running' }));
    const { result } = renderHook(() => usePlanRun('b1', 'tok'));
    await act(async () => { await result.current.createRun({ source_markdown: '# x', mode: 'llm', model_ref: 'm1' }); });
    expect(result.current.polling).toBe(true);
    act(() => { result.current.resetRun(); });
    expect(result.current.run).toBeNull();
    // run→null re-runs the poll effect, which sees no run and arms no new timer — the old
    // timer's cleanup already fired, so nothing resurrects the run on the next tick.
    await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
    expect(result.current.run).toBeNull();
    expect(getRun).toHaveBeenCalledTimes(1); // only the post-ack fetch — no poll tick after reset
  });
});

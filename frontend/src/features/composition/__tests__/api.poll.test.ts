/**
 * compositionApi auto/chapter/stitch submit+poll (LLM re-arch Phase 3 M4).
 *
 * When COMPOSITION_WORKER_ENABLED is on, generate(auto)/chapter/stitch answer
 * 202 `{ job_id, status: 'pending' }`; the api method then polls GET /jobs/{id}
 * to terminal and maps job.result to the inline shape — hidden from the hooks
 * (their "await the result" contract is unchanged). Flag-off (inline 200) returns
 * directly with no poll. A failed job throws. persistJob is the Option A
 * accept-step.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const apiJson = vi.fn();
vi.mock('@/api', () => ({
  apiJson: (...a: unknown[]) => apiJson(...a),
  apiBase: () => '',
}));

import { compositionApi } from '../api';

beforeEach(() => apiJson.mockReset());

describe('generateAuto (submit + poll)', () => {
  it('returns the inline result directly when the flag is off (no poll)', async () => {
    apiJson.mockResolvedValueOnce({
      job_id: 'j0', mode: 'auto', status: 'completed', text: 'winner',
      candidates: ['a', 'winner'], winner_index: 1, k: 2,
    });
    const out = await compositionApi.generateAuto(
      'p1', { outlineNodeId: 'n1', modelRef: 'm1' }, 'tok');
    expect(out.text).toBe('winner') && expect(out.status).toBe('completed');
    expect(apiJson).toHaveBeenCalledTimes(1); // POST only, no /jobs poll
  });

  it('polls a 202 pending job to completion and maps job.result', async () => {
    vi.useFakeTimers();
    try {
      apiJson
        .mockResolvedValueOnce({ job_id: 'j1', status: 'pending', mode: 'auto' }) // POST 202
        .mockResolvedValueOnce({ id: 'j1', status: 'running', result: null })      // poll 1
        .mockResolvedValueOnce({ id: 'j1', status: 'completed',
          result: { text: 'auto winner', candidates: ['x', 'auto winner'], winner_index: 1, k: 2, canon: { status: 'ok' } } });
      const p = compositionApi.generateAuto('p1', { outlineNodeId: 'n1', modelRef: 'm1' }, 'tok');
      await vi.runAllTimersAsync();
      const out = await p;
      expect(out.text).toBe('auto winner');
      expect(out.mode).toBe('auto') && expect(out.status).toBe('completed');
      expect(out.candidates).toEqual(['x', 'auto winner']);
      expect(apiJson.mock.calls[1][0]).toContain('/jobs/j1'); // polled the job
      expect(apiJson).toHaveBeenCalledTimes(3); // POST + 2 polls
    } finally {
      vi.useRealTimers();
    }
  });

  it('throws with the job error when the worker job fails', async () => {
    apiJson
      .mockResolvedValueOnce({ job_id: 'j2', status: 'pending', mode: 'auto' })
      .mockResolvedValueOnce({ id: 'j2', status: 'failed', result: { error: 'diverge produced nothing' } });
    await expect(
      compositionApi.generateAuto('p1', { outlineNodeId: 'n1', modelRef: 'm1' }, 'tok'),
    ).rejects.toThrow('diverge produced nothing');
  });
});

describe('generateChapter / stitchChapter (submit + poll)', () => {
  it('polls a 202 chapter job and surfaces persisted=false (Option A)', async () => {
    vi.useFakeTimers();
    try {
      apiJson
        .mockResolvedValueOnce({ job_id: 'c1', status: 'pending', assembly_mode: 'chapter' })
        .mockResolvedValueOnce({ id: 'c1', status: 'completed',
          result: { text: 'CHAPTER', assembly_mode: 'chapter', persisted: false, draft_version: null, chapter_id: 'ch1' } });
      const p = compositionApi.generateChapter('p1', 'ch1', { modelRef: 'm1' }, 'tok');
      await vi.runAllTimersAsync();
      const out = await p;
      expect(out.text).toBe('CHAPTER') && expect(out.assembly_mode).toBe('chapter');
      expect(out.persisted).toBe(false); // worker computed; accept-step persists
    } finally {
      vi.useRealTimers();
    }
  });

  it('stitch returns the inline result directly flag-off', async () => {
    apiJson.mockResolvedValueOnce({
      job_id: 's0', status: 'completed', text: 'STITCHED', assembly_mode: 'per_scene_stitch', persisted: true,
    });
    const out = await compositionApi.stitchChapter('p1', 'ch1', { modelRef: 'm1' }, 'tok');
    expect(out.text).toBe('STITCHED') && expect(out.persisted).toBe(true);
    expect(apiJson).toHaveBeenCalledTimes(1);
  });
});

describe('decomposePreview (submit + poll)', () => {
  it('returns the inline tree directly flag-off', async () => {
    apiJson.mockResolvedValueOnce({ arc: { title: 'A' }, chapters: [] });
    const out = await compositionApi.decomposePreview(
      'p1', { structure_template_id: 't', premise: 'x', model_source: 'user_model', model_ref: 'm' }, 'tok');
    expect((out as { arc: { title: string } }).arc.title).toBe('A');
    expect(apiJson).toHaveBeenCalledTimes(1);
  });

  it('polls a 202 job and returns job.result as the tree', async () => {
    apiJson
      .mockResolvedValueOnce({ job_id: 'd1', status: 'pending', enqueued: 'ok' })
      .mockResolvedValueOnce({ id: 'd1', status: 'completed', result: { arc: { title: 'WORKER ARC' }, chapters: [{ id: 'c1' }] } });
    const out = await compositionApi.decomposePreview(
      'p1', { structure_template_id: 't', premise: 'x', model_source: 'user_model', model_ref: 'm' }, 'tok');
    expect((out as { arc: { title: string } }).arc.title).toBe('WORKER ARC');
    expect(apiJson.mock.calls[1][0]).toContain('/jobs/d1');
  });
});

describe('persistJob (Option A accept-step)', () => {
  it('POSTs the persist with an optional commit message', async () => {
    apiJson.mockResolvedValueOnce({ job_id: 'c1', persisted: true, draft_version: 8 });
    const out = await compositionApi.persistJob('c1', 'tok', 'accept chapter');
    expect(out.persisted).toBe(true) && expect(out.draft_version).toBe(8);
    expect(apiJson.mock.calls[0][0]).toContain('/jobs/c1/persist');
    expect(JSON.parse((apiJson.mock.calls[0][1] as { body: string }).body)).toEqual({ commit_message: 'accept chapter' });
  });
});

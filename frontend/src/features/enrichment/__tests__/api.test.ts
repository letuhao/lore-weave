/**
 * enrichmentApi compose-task submit+poll (LLM re-arch Phase 3 M2).
 *
 * resolveIntent / suggestBookProfile now POST → 202 + task_id, then poll
 * GET /compose-tasks/{id} to terminal. The submit+poll is hidden inside the api
 * method (the hooks keep their "await the result" contract), so it's covered here
 * directly: a completed task returns its result; a failed task throws; polling
 * continues through pending/running.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const apiJson = vi.fn();
vi.mock('@/api', () => ({
  apiJson: (...a: unknown[]) => apiJson(...a),
  apiBase: () => '',
}));

import { enrichmentApi } from '../api';

beforeEach(() => apiJson.mockReset());

const RESOLVED = {
  target: { mode: 'existing', canonical_name: '姜子牙', entity_kind: 'character' },
  dimensions: ['历史'], technique: 'retrieval', rationale: 'in list',
};

describe('resolveIntent (submit + poll)', () => {
  it('POSTs then polls a completed task → returns the resolved result', async () => {
    apiJson
      .mockResolvedValueOnce({ task_id: 't-1', status: 'pending' }) // POST 202
      .mockResolvedValueOnce({ task_id: 't-1', kind: 'intent_resolve', status: 'completed', result: RESOLVED, error: null }); // poll
    const out = await enrichmentApi.resolveIntent('book-1', 'the kings advisor', 'g1', 'tok');
    expect(out).toEqual(RESOLVED);
    // first call is the POST, second is the compose-tasks poll for t-1.
    expect(apiJson.mock.calls[0][0]).toContain('/compose/resolve-intent');
    expect(apiJson.mock.calls[1][0]).toContain('/compose-tasks/t-1');
  });

  it('throws with the task error when the task fails', async () => {
    apiJson
      .mockResolvedValueOnce({ task_id: 't-2', status: 'pending' })
      .mockResolvedValueOnce({ task_id: 't-2', kind: 'intent_resolve', status: 'failed', result: null, error: 'llm down' });
    await expect(
      enrichmentApi.resolveIntent('book-1', 'x', 'g1', 'tok'),
    ).rejects.toThrow('llm down');
  });
});

describe('suggestBookProfile (submit + poll)', () => {
  it('keeps polling through pending/running until completed', async () => {
    vi.useFakeTimers();
    try {
      const draft = { worldview: 'w', language: 'vi', dimension_overrides: {}, profile_source: 'ai_suggested' };
      apiJson
        .mockResolvedValueOnce({ task_id: 's-1', status: 'pending' })   // POST
        .mockResolvedValueOnce({ task_id: 's-1', kind: 'profile_suggest', status: 'running', result: null, error: null })
        .mockResolvedValueOnce({ task_id: 's-1', kind: 'profile_suggest', status: 'completed', result: draft, error: null });
      const p = enrichmentApi.suggestBookProfile(
        'book-1', { project_id: 'book-1', suggest_model_ref: 'm1' }, 'tok',
      );
      await vi.runAllTimersAsync(); // advance through the 1.5s poll interval(s)
      expect(await p).toEqual(draft);
      expect(apiJson).toHaveBeenCalledTimes(3); // POST + 2 polls
    } finally {
      vi.useRealTimers();
    }
  });
});

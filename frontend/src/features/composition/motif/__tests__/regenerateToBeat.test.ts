// W6 "Regenerate to beat" — the REQUEST, which is where this feature failed three times.
//
// v1 POSTed to `/works/{p}/scenes/{s}/regenerate-to-beat`: a route composition-service never
// served. v2 moved to the real `/works/{p}/generate` and stopped there — it sent only
// `outline_node_id`, and `GenerateBody` requires `model_source` + `model_ref`, so every click
// 422'd. v3 (mine) was about to hand-roll the body again and omit `mode: 'auto'`, which would have
// STREAMED SSE into a JSON parser — caught only by firing it at the real stack.
//
// The lesson is in the shape of the fix: `regenerateScene` now DELEGATES to the shared
// `generateAuto`, so the only thing it can get wrong is the operation. These tests pin exactly
// that boundary — the delegation, and the one argument that is genuinely its own.
import { describe, expect, it, vi, beforeEach } from 'vitest';

const generateAuto = vi.hoisted(() => vi.fn());
vi.mock('../../api', () => ({ compositionApi: { generateAuto } }));
vi.mock('../../../../api', () => ({ apiJson: vi.fn() }));
vi.mock('../../../../mcpBridge', () => ({ mcpExecute: vi.fn() }));

import { motifApi } from '../api';

beforeEach(() => {
  generateAuto.mockReset();
  generateAuto.mockResolvedValue({ job_id: 'j1', text: 'prose' });
});

describe('motifApi.regenerateScene', () => {
  it('DELEGATES to the shared scene-generate call instead of hand-rolling the request', async () => {
    await motifApi.regenerateScene('p1', 'n1', 'model-1', 'tok');
    expect(generateAuto).toHaveBeenCalledTimes(1);
    const [projectId, params, token] = generateAuto.mock.calls[0];
    expect(projectId).toBe('p1');
    expect(params.outlineNodeId).toBe('n1');
    expect(params.modelRef).toBe('model-1');
    expect(token).toBe('tok');
  });

  it('names the regenerate_to_beat OPERATION — the one thing that makes this a retry', async () => {
    // An unregistered operation does not fail: `_OPERATION_INSTRUCTIONS.get(op, …)` quietly
    // returns a generic "Write the next passage of the scene." This project has already lost a
    // feature to that fallback (`useWhatIfTakes` sent a made-up 'diverge'), so the operation
    // travelling correctly is worth pinning on its own.
    await motifApi.regenerateScene('p1', 'n1', 'model-1', 'tok');
    expect(generateAuto.mock.calls[0][1].operation).toBe('regenerate_to_beat');
  });

  it('does NOT re-specify mode/url/model_source — those belong to the shared call', async () => {
    // The delegation is the point: anything this passes is something it can get wrong. `mode`
    // ('auto', without which the endpoint streams SSE) and the 202-poll live in generateAuto.
    await motifApi.regenerateScene('p1', 'n1', 'model-1', 'tok');
    expect(Object.keys(generateAuto.mock.calls[0][1]).sort())
      .toEqual(['modelRef', 'operation', 'outlineNodeId']);
  });
});

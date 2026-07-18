import { describe, it, expect, vi, beforeEach } from 'vitest';
import { parsePlanArtifactResourceId, registerPlanArtifactDocumentProvider, _resetPlanArtifactDocumentProvider, PLAN_ARTIFACT_DOC_TYPE } from '../planArtifactDocument';
import { getJsonDocumentProvider, _clearJsonDocuments } from '@/features/studio/documents/registry';

const api = vi.hoisted(() => ({ getArtifact: vi.fn() }));
vi.mock('../../api', () => ({ planForgeApi: api }));

beforeEach(() => {
  api.getArtifact.mockReset();
  _clearJsonDocuments();
  _resetPlanArtifactDocumentProvider();
});

describe('parsePlanArtifactResourceId', () => {
  it('splits {runId}:{artifactId} on the FIRST colon', () => {
    expect(parsePlanArtifactResourceId('run1:art1')).toEqual({ runId: 'run1', artifactId: 'art1' });
  });
  it('rejects a missing/edge colon', () => {
    expect(parsePlanArtifactResourceId('noColon')).toBeNull();
    expect(parsePlanArtifactResourceId(':art')).toBeNull();
    expect(parsePlanArtifactResourceId('run:')).toBeNull();
  });
});

describe('plan-artifact provider', () => {
  it('registers a READ-ONLY provider that fetches content via BE-3, save() is a no-op', async () => {
    api.getArtifact.mockResolvedValue({ artifact_id: 'art1', kind: 'cast_plan', content: { roster: [1] }, created_at: null });
    registerPlanArtifactDocumentProvider();
    const p = getJsonDocumentProvider(PLAN_ARTIFACT_DOC_TYPE);
    expect(p?.readOnly).toBe(true);
    const handle = await p!.open({ token: 't', bookId: 'b1' }, 'run1:art1');
    expect(api.getArtifact).toHaveBeenCalledWith('b1', 'run1', 'art1', 't');
    expect(handle.getSnapshot().doc).toEqual({ roster: [1] });
    expect(handle.getSnapshot().dirty).toBe(false);
    await handle.save(); // must not throw / must not write
    handle.release();
  });

  it('a malformed resourceId throws rather than fetching a bad id', async () => {
    registerPlanArtifactDocumentProvider();
    const p = getJsonDocumentProvider(PLAN_ARTIFACT_DOC_TYPE);
    await expect(p!.open({ token: 't', bookId: 'b1' }, 'bad')).rejects.toThrow(/malformed/);
    expect(api.getArtifact).not.toHaveBeenCalled();
  });
});

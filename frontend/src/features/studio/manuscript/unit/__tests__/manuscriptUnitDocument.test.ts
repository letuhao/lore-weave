// #12 cycle-1 — the manuscript-unit document provider: R2 active-unit semantics, the shared
// body buffer, the scenes working-copy, and the R5 two-phase save with per-part conflicts.
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { OutlineNode } from '@/features/composition/types';

const patchNode = vi.fn();
vi.mock('@/features/composition/api', () => ({
  compositionApi: { patchNode: (...a: unknown[]) => patchNode(...a) },
}));
vi.mock('@/lib/tiptap-utils', () => ({ extractText: (d: unknown) => `text(${JSON.stringify(d).length})` }));

import { _clearJsonDocuments, openJsonDocument } from '../../../documents/registry';
import {
  MANUSCRIPT_UNIT_DOC_TYPE, _resetManuscriptUnitDocumentProvider, _setManuscriptUnitBinding,
  emitManuscriptUnitChange, registerManuscriptUnitDocumentProvider,
} from '../manuscriptUnitDocument';
import type { ManuscriptUnitApi } from '../ManuscriptUnitProvider';

const scene = (id: string, over: Partial<OutlineNode> = {}): OutlineNode => ({
  id, project_id: 'p1', parent_id: 'chapnode', kind: 'scene', rank: 'm', title: `Scene ${id}`,
  chapter_id: 'ch1', story_order: 1, status: 'outline', synopsis: `syn ${id}`, version: 5,
  is_archived: false, beat_role: null,
});

function fakeUnit(chapterId = 'ch1') {
  const state = {
    chapterId, loadedBody: { type: 'doc' }, savedBody: { type: 'doc', v: 1 } as Record<string, unknown>,
    workingBody: null as Record<string, unknown> | null,
    version: 7, textContent: '', saveState: 'idle', error: null,
    scenes: [scene('s1'), scene('s2')],
  };
  const api = {
    state,
    get isDirty() { return state.workingBody != null; },
    editorRef: { current: null },
    openUnit: vi.fn(async (id: string) => { state.chapterId = id; }),
    setBody: vi.fn((doc: Record<string, unknown>) => { state.workingBody = doc; }),
    save: vi.fn(async () => { state.workingBody = null; state.saveState = 'saved'; }),
    revert: vi.fn(() => { state.workingBody = null; }),
    reload: vi.fn(async () => {}),
    reloadScenes: vi.fn(async () => {}),
    isChapterDirty: vi.fn(() => state.workingBody != null),
  } as unknown as ManuscriptUnitApi & { state: typeof state };
  return api;
}

const ctx = { token: 'tok', bookId: 'b1' };

async function openDoc(api: ManuscriptUnitApi) {
  _setManuscriptUnitBinding({ api, token: 'tok', projectId: 'p1' });
  registerManuscriptUnitDocumentProvider();
  return openJsonDocument(MANUSCRIPT_UNIT_DOC_TYPE, 'ch1', ctx);
}

beforeEach(() => {
  patchNode.mockReset();
  _clearJsonDocuments();
  _resetManuscriptUnitDocumentProvider();
});

describe('manuscript-unit document provider (#12 cycle 1)', () => {
  it('builds the envelope doc from the hoist (body + merged scenes; etag = draft_version)', async () => {
    const h = await openDoc(fakeUnit());
    const snap = h.getSnapshot();
    expect(snap.status).toBe('idle');
    expect(snap.etag).toBe(7);
    expect(snap.doc).toMatchObject({
      type: MANUSCRIPT_UNIT_DOC_TYPE,
      chapter_id: 'ch1',
      scenes: [
        { node_id: 's1', synopsis: 'syn s1', version: 5 },
        { node_id: 's2', synopsis: 'syn s2', version: 5 },
      ],
    });
  });

  it('R2: open() on a non-active chapter focuses it into the hoist first', async () => {
    const api = fakeUnit('other');
    await openDoc(api);
    expect(api.openUnit).toHaveBeenCalledWith('ch1');
  });

  it('update: body flows into the SHARED hoist buffer (setBody + extracted text)', async () => {
    const api = fakeUnit();
    const h = await openDoc(api);
    h.update({ type: MANUSCRIPT_UNIT_DOC_TYPE, chapter_id: 'ch1', body: { type: 'doc', v: 2 }, scenes: [] });
    expect(api.setBody).toHaveBeenCalledWith({ type: 'doc', v: 2 }, expect.stringContaining('text('));
    expect(h.getSnapshot().dirty).toBe(true);
  });

  it('update: scene edits only for KNOWN node_ids + editable fields; unknown entries ignored', async () => {
    const api = fakeUnit();
    const h = await openDoc(api);
    h.update({
      body: api.state.savedBody,
      scenes: [
        { node_id: 's1', title: 'Scene s1', synopsis: 'REWRITTEN', status: 'outline', version: 999 }, // version is read-only → ignored
        { node_id: 'ghost', synopsis: 'nope' },
      ],
    });
    const snap = h.getSnapshot();
    expect(snap.dirty).toBe(true);
    const scenes = (snap.doc as { scenes: Array<{ node_id: string; synopsis: string; version: number }> }).scenes;
    expect(scenes.find((s) => s.node_id === 's1')).toMatchObject({ synopsis: 'REWRITTEN', version: 5 });
    expect(scenes).toHaveLength(2); // ghost not added
  });

  it('R5 save: phase-1 body via hoist save, phase-2 scenes via patchNode with If-Match version', async () => {
    const api = fakeUnit();
    api.state.workingBody = { type: 'doc', v: 2 };
    patchNode.mockResolvedValue({});
    const h = await openDoc(api);
    h.update({ body: api.state.workingBody, scenes: [{ node_id: 's2', synopsis: 'edited', title: 'Scene s2', status: 'outline' }] });
    await h.save();
    expect(api.save).toHaveBeenCalledTimes(1);
    expect(patchNode).toHaveBeenCalledWith('s2', { synopsis: 'edited' }, 'tok', 5);
    expect(api.reloadScenes).toHaveBeenCalled();
    expect(h.getSnapshot().dirty).toBe(false);
  });

  it('R5 conflict: a 412 on a scene patch surfaces status=conflict with the scenes part', async () => {
    const api = fakeUnit();
    patchNode.mockRejectedValue(Object.assign(new Error('stale'), { status: 412 }));
    const h = await openDoc(api);
    h.update({ body: api.state.savedBody, scenes: [{ node_id: 's1', synopsis: 'x', title: 'Scene s1', status: 'outline' }] });
    await h.save();
    const snap = h.getSnapshot();
    expect(snap.status).toBe('conflict');
    expect(snap.detail).toContain('scenes: s1');
    expect(snap.dirty).toBe(true); // edits preserved for the user to reconcile
  });

  it('revert clears scene edits and reverts a dirty body', async () => {
    const api = fakeUnit();
    const h = await openDoc(api);
    h.update({ body: { type: 'doc', v: 9 }, scenes: [{ node_id: 's1', synopsis: 'x', title: 'Scene s1', status: 'outline' }] });
    h.revert();
    expect(api.revert).toHaveBeenCalled();
    expect(h.getSnapshot().dirty).toBe(false);
  });

  it('reload (Lane B): scenes always; body only when it has no local edits (R6/G7)', async () => {
    const api = fakeUnit();
    const h = await openDoc(api);
    await h.reload();
    expect(api.reloadScenes).toHaveBeenCalledTimes(1);
    expect(api.reload).toHaveBeenCalledTimes(1);

    api.state.workingBody = { type: 'doc', dirty: true };
    await h.reload();
    expect(api.reloadScenes).toHaveBeenCalledTimes(2);
    expect(api.reload).toHaveBeenCalledTimes(1); // body untouched while dirty
  });

  it('a unit switch away makes the handle surface an R2 error state', async () => {
    const api = fakeUnit();
    const h = await openDoc(api);
    api.state.chapterId = 'ch99';
    emitManuscriptUnitChange();
    expect(h.getSnapshot()).toMatchObject({ status: 'error', detail: expect.stringContaining('active chapter') });
  });
});

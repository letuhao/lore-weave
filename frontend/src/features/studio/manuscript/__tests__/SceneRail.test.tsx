// #12 M-C/M-F/M-G — Scene Rail: renders the hoist scenes[], bus scene slice highlights
// AND jumps the prose (M-F), edits save through composition patchNode (OCC If-Match)
// then reloadScenes, ＋/✕(+Undo)/▲▼ drive the outline REST (M-G).
import { act, fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { OutlineNode } from '@/features/composition/types';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string, o?: { defaultValue?: string }) => o?.defaultValue ?? k }),
}));
const patchNode = vi.fn();
const createNode = vi.fn();
const archiveNode = vi.fn();
const restoreNode = vi.fn();
const reorderNode = vi.fn();
vi.mock('@/features/composition/api', () => ({
  compositionApi: {
    patchNode: (...a: unknown[]) => patchNode(...a),
    createNode: (...a: unknown[]) => createNode(...a),
    archiveNode: (...a: unknown[]) => archiveNode(...a),
    restoreNode: (...a: unknown[]) => restoreNode(...a),
    reorderNode: (...a: unknown[]) => reorderNode(...a),
  },
}));

const busState = vi.hoisted(() => ({ activeSceneId: undefined as string | undefined }));
vi.mock('../../host/StudioHostProvider', () => ({
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  useStudioBusSelector: (sel: any) => sel({ activeSceneId: busState.activeSceneId }),
}));

const reloadScenes = vi.fn(async () => {});
const jumpToScene = vi.fn(() => true);
const anchorScenes = vi.fn(() => ({ anchored: 2, unmatched: 0, changed: true }));
const unitState = vi.hoisted(() => ({
  scenes: [] as unknown[],
  chapterId: 'ch1' as string | null,
  sceneChapterNodeId: 'chapnode' as string | null,
}));
vi.mock('../unit/ManuscriptUnitProvider', () => ({
  useManuscriptUnit: () => ({
    state: {
      scenes: unitState.scenes,
      chapterId: unitState.chapterId,
      sceneChapterNodeId: unitState.sceneChapterNodeId,
    },
    reloadScenes,
    jumpToScene,
    anchorScenes,
  }),
  useManuscriptUnitMeta: () => ({ projectId: 'p1', activeChapterId: unitState.chapterId }),
}));

import { SceneRail } from '../SceneRail';

const scene = (id: string, over: Partial<OutlineNode> = {}): OutlineNode => ({
  id, project_id: 'p1', parent_id: 'chapnode', kind: 'scene', rank: 'm', title: `Scene ${id}`,
  chapter_id: 'ch1', story_order: 1, status: 'outline', synopsis: `syn-${id}`, version: 4,
  is_archived: false, beat_role: null, ...over,
});

beforeEach(() => {
  patchNode.mockReset().mockResolvedValue({});
  createNode.mockReset().mockResolvedValue({});
  archiveNode.mockReset().mockResolvedValue({});
  restoreNode.mockReset().mockResolvedValue({});
  reorderNode.mockReset().mockResolvedValue({});
  reloadScenes.mockClear();
  jumpToScene.mockClear().mockReturnValue(true);
  anchorScenes.mockClear().mockReturnValue({ anchored: 2, unmatched: 0, changed: true });
  busState.activeSceneId = undefined;
  unitState.scenes = [scene('s1'), scene('s2'), scene('s3')];
  unitState.chapterId = 'ch1';
  unitState.sceneChapterNodeId = 'chapnode';
});

describe('SceneRail (#12 M-C)', () => {
  it('renders every scene with its synopsis; empty state when none', () => {
    const { rerender } = render(<SceneRail />);
    expect(screen.getByTestId('scene-rail-row-s1')).toBeTruthy();
    expect((screen.getByTestId('scene-rail-synopsis-s2') as HTMLTextAreaElement).value).toBe('syn-s2');

    unitState.scenes = [];
    rerender(<SceneRail />);
    expect(screen.queryByTestId('scene-rail-row-s1')).toBeNull();
  });

  it('the bus scene slice highlights its row', () => {
    busState.activeSceneId = 's2';
    render(<SceneRail />);
    expect(screen.getByTestId('scene-rail-row-s2').className).toContain('primary-muted');
    expect(screen.getByTestId('scene-rail-row-s1').className).not.toContain('primary-muted');
  });

  it('synopsis blur with a change PATCHes with the OCC version then reloads scenes', async () => {
    render(<SceneRail />);
    const ta = screen.getByTestId('scene-rail-synopsis-s1');
    fireEvent.focus(ta);
    fireEvent.change(ta, { target: { value: 'rewritten' } });
    await act(async () => { fireEvent.blur(ta); });
    expect(patchNode).toHaveBeenCalledWith('s1', { synopsis: 'rewritten' }, 'tok', 4);
    expect(reloadScenes).toHaveBeenCalled();
  });

  it('blur without a change does NOT patch', async () => {
    render(<SceneRail />);
    const ta = screen.getByTestId('scene-rail-synopsis-s1');
    fireEvent.focus(ta);
    await act(async () => { fireEvent.blur(ta); });
    expect(patchNode).not.toHaveBeenCalled();
  });

  it('status select PATCHes immediately', async () => {
    render(<SceneRail />);
    await act(async () => {
      fireEvent.change(screen.getByTestId('scene-rail-status-s1'), { target: { value: 'done' } });
    });
    expect(patchNode).toHaveBeenCalledWith('s1', { status: 'done' }, 'tok', 4);
  });

  it('a 412 (stale version) shows the stale notice AND reloads so the next edit lands', async () => {
    patchNode.mockRejectedValueOnce(Object.assign(new Error('stale'), { status: 412 }));
    render(<SceneRail />);
    const ta = screen.getByTestId('scene-rail-synopsis-s1');
    fireEvent.focus(ta);
    fireEvent.change(ta, { target: { value: 'x' } });
    await act(async () => { fireEvent.blur(ta); });
    expect(screen.getByTestId('scene-rail-error-s1')).toBeTruthy();
    expect(reloadScenes).toHaveBeenCalled();
  });
});

describe('SceneRail (#12 M-F — scene→prose jump + anchor)', () => {
  it('title click jumps the prose to the anchored heading', () => {
    render(<SceneRail />);
    fireEvent.click(screen.getByTestId('scene-rail-jump-s1'));
    expect(jumpToScene).toHaveBeenCalledWith('s1');
    expect(screen.queryByTestId('scene-rail-notice')).toBeNull();
  });

  it('title click on an UN-anchored scene shows the ⚓ hint (never a silent no-op)', () => {
    jumpToScene.mockReturnValue(false);
    render(<SceneRail />);
    fireEvent.click(screen.getByTestId('scene-rail-jump-s1'));
    expect(screen.getByTestId('scene-rail-notice')).toBeTruthy();
  });

  it('a NEW bus scene slice (navigator / Quick-Open) also jumps the prose', () => {
    busState.activeSceneId = 's3';
    render(<SceneRail />);
    expect(jumpToScene).toHaveBeenCalledWith('s3');
  });

  it('⚓ runs the backfill and reports the result', () => {
    render(<SceneRail />);
    fireEvent.click(screen.getByTestId('scene-rail-anchor'));
    expect(anchorScenes).toHaveBeenCalled();
    expect(screen.getByTestId('scene-rail-notice').textContent).toContain('2');
  });
});

describe('SceneRail (#12 M-G — CRUD)', () => {
  it('＋ opens the inline title input; Enter creates under the chapter node then reloads', async () => {
    render(<SceneRail />);
    fireEvent.click(screen.getByTestId('scene-rail-add'));
    const input = screen.getByTestId('scene-rail-new-title');
    fireEvent.change(input, { target: { value: 'Cảnh mới' } });
    await act(async () => { fireEvent.keyDown(input, { key: 'Enter' }); });
    expect(createNode).toHaveBeenCalledWith(
      'p1',
      { kind: 'scene', parent_id: 'chapnode', chapter_id: 'ch1', title: 'Cảnh mới', status: 'empty' },
      'tok',
    );
    expect(reloadScenes).toHaveBeenCalled();
  });

  it('＋ is disabled when the chapter has no outline node', () => {
    unitState.sceneChapterNodeId = null;
    render(<SceneRail />);
    expect((screen.getByTestId('scene-rail-add') as HTMLButtonElement).disabled).toBe(true);
  });

  it('✕ archives, shows Undo; Undo restores then reloads', async () => {
    render(<SceneRail />);
    await act(async () => { fireEvent.click(screen.getByTestId('scene-rail-delete-s2')); });
    expect(archiveNode).toHaveBeenCalledWith('s2', 'tok');
    await act(async () => { fireEvent.click(screen.getByTestId('scene-rail-undo-btn')); });
    expect(restoreNode).toHaveBeenCalledWith('s2', 'tok');
    expect(reloadScenes).toHaveBeenCalled();
  });

  it('▲ on the middle scene places it first (after_id null); ▼ places it after its successor', async () => {
    render(<SceneRail />);
    await act(async () => { fireEvent.click(screen.getByTestId('scene-rail-up-s2')); });
    expect(reorderNode).toHaveBeenCalledWith('s2', { new_parent_id: 'chapnode', after_id: null }, 'tok', 4);
    await act(async () => { fireEvent.click(screen.getByTestId('scene-rail-down-s2')); });
    expect(reorderNode).toHaveBeenCalledWith('s2', { new_parent_id: 'chapnode', after_id: 's3' }, 'tok', 4);
  });

  it('▲ disabled on the first scene, ▼ disabled on the last', () => {
    render(<SceneRail />);
    expect((screen.getByTestId('scene-rail-up-s1') as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByTestId('scene-rail-down-s3') as HTMLButtonElement).disabled).toBe(true);
  });
});

// #12 M-C — Scene Rail: renders the hoist scenes[], bus scene slice highlights, edits save
// through composition patchNode (OCC If-Match) then reloadScenes.
import { act, fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { OutlineNode } from '@/features/composition/types';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
const patchNode = vi.fn();
vi.mock('@/features/composition/api', () => ({
  compositionApi: { patchNode: (...a: unknown[]) => patchNode(...a) },
}));

const busState = vi.hoisted(() => ({ activeSceneId: undefined as string | undefined }));
vi.mock('../../host/StudioHostProvider', () => ({
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  useStudioBusSelector: (sel: any) => sel({ activeSceneId: busState.activeSceneId }),
}));

const reloadScenes = vi.fn(async () => {});
const unitState = vi.hoisted(() => ({ scenes: [] as unknown[] }));
vi.mock('../unit/ManuscriptUnitProvider', () => ({
  useManuscriptUnit: () => ({ state: { scenes: unitState.scenes }, reloadScenes }),
}));

import { SceneRail } from '../SceneRail';

const scene = (id: string, over: Partial<OutlineNode> = {}): OutlineNode => ({
  id, project_id: 'p1', parent_id: 'chap', kind: 'scene', rank: 'm', title: `Scene ${id}`,
  chapter_id: 'ch1', story_order: 1, status: 'outline', synopsis: `syn-${id}`, version: 4,
  is_archived: false, beat_role: null,
});

beforeEach(() => {
  patchNode.mockReset().mockResolvedValue({});
  reloadScenes.mockClear();
  busState.activeSceneId = undefined;
  unitState.scenes = [scene('s1'), scene('s2')];
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

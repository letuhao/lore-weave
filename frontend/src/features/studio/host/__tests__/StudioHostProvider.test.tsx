import { describe, expect, it, vi } from 'vitest';
import { act, render, renderHook, screen } from '@testing-library/react';
import { useRef } from 'react';
import type { ReactNode } from 'react';
import {
  StudioHostProvider, useRegisteredTools, useRegisterStudioTool, useRegisterStatusBarItem,
  useStatusBarItems, useStudioBus, useStudioBusSelector, useStudioHost,
} from '../StudioHostProvider';
import { applyBusEvent, type StudioBusSnapshot, type StudioStatusBarItem, type StudioToolRegistration } from '../types';

const wrapper = (bookId = 'b1') => ({ children }: { children: ReactNode }) => (
  <StudioHostProvider bookId={bookId}>{children}</StudioHostProvider>
);

const reg = (panelId: string, over: Partial<StudioToolRegistration> = {}): StudioToolRegistration => ({
  panelId, label: panelId, paletteCommand: `Studio: Open ${panelId}`, commandId: `studio.openPanel.${panelId}`, ...over,
});

describe('applyBusEvent (pure reducer)', () => {
  const s0: StudioBusSnapshot = { revision: 0, bookId: 'b1', activePanelIds: [] };
  it('bumps revision on every event', () => {
    expect(applyBusEvent(s0, { type: 'panels', activePanelIds: ['x'] }).revision).toBe(1);
  });
  it('chapter clears the stale scene; scene sets both', () => {
    const s1 = applyBusEvent({ ...s0, activeSceneId: 'old' }, { type: 'chapter', chapterId: 'c1', bookId: 'b1' });
    expect(s1).toMatchObject({ activeChapterId: 'c1', activeSceneId: undefined });
    const s2 = applyBusEvent(s1, { type: 'scene', sceneId: 's1', chapterId: 'c2' });
    expect(s2).toMatchObject({ activeSceneId: 's1', activeChapterId: 'c2' });
  });
  it('startGuidedTour increments guidedTourRequestSeq from unset, then from a prior value', () => {
    const s1 = applyBusEvent(s0, { type: 'startGuidedTour' });
    expect(s1.guidedTourRequestSeq).toBe(1);
    const s2 = applyBusEvent(s1, { type: 'startGuidedTour' });
    expect(s2.guidedTourRequestSeq).toBe(2);
  });
  it('startGuidedTour stores the requested tourId, or undefined when omitted (role-tour fallback)', () => {
    const s1 = applyBusEvent(s0, { type: 'startGuidedTour', tourId: 'editorBasics' });
    expect(s1.guidedTourRequestedId).toBe('editorBasics');
    const s2 = applyBusEvent(s1, { type: 'startGuidedTour' });
    expect(s2.guidedTourRequestedId).toBeUndefined();
  });
});

describe('StudioHost registry (#08 contract names)', () => {
  it('registerStudioTool / getRegisteredTool / list; unregister removes; re-register replaces (no dup)', () => {
    const { result } = renderHook(() => useStudioHost(), { wrapper: wrapper() });
    act(() => result.current.registerStudioTool(reg('compose')));
    act(() => result.current.registerStudioTool(reg('compose', { label: 'Compose v2' }))); // same id → replace
    expect(result.current.listRegisteredStudioTools()).toHaveLength(1);
    expect(result.current.getRegisteredTool('compose')?.label).toBe('Compose v2');
    act(() => result.current.unregisterStudioTool('compose'));
    expect(result.current.listRegisteredStudioTools()).toHaveLength(0);
    expect(result.current.getRegisteredTool('compose')).toBeNull();
  });

  it('useRegisteredTools re-renders when a tool (un)registers', () => {
    const { result } = renderHook(
      () => ({ host: useStudioHost(), tools: useRegisteredTools() }),
      { wrapper: wrapper() },
    );
    expect(result.current.tools).toHaveLength(0);
    act(() => result.current.host.registerStudioTool(reg('cast')));
    expect(result.current.tools.map((t) => t.panelId)).toEqual(['cast']);
    act(() => result.current.host.unregisterStudioTool('cast'));
    expect(result.current.tools).toHaveLength(0);
  });
});

describe('StudioContextBus', () => {
  it('publish + getSnapshot bump revision; useStudioBus is reactive', () => {
    const { result } = renderHook(
      () => ({ host: useStudioHost(), snap: useStudioBus() }),
      { wrapper: wrapper() },
    );
    expect(result.current.snap).toMatchObject({ revision: 0, bookId: 'b1', activePanelIds: [] });
    act(() => result.current.host.publish({ type: 'chapter', chapterId: 'c9', bookId: 'b1' }));
    expect(result.current.snap).toMatchObject({ revision: 1, activeChapterId: 'c9' });
    expect(result.current.host.getSnapshot().activeChapterId).toBe('c9');
  });

  it('focusManuscriptUnit publishes the active chapter to the bus', () => {
    const { result } = renderHook(() => ({ host: useStudioHost(), snap: useStudioBus() }), { wrapper: wrapper() });
    act(() => result.current.host.focusManuscriptUnit('ch42'));
    expect(result.current.snap.activeChapterId).toBe('ch42');
  });

  it('openPanel is a safe no-op before the dock api is ready', () => {
    const { result } = renderHook(() => useStudioHost(), { wrapper: wrapper() });
    expect(() => result.current.openPanel('editor')).not.toThrow();
  });

  it('openPanel passes params to addPanel; re-open updates parameters + focuses (#11 F1)', () => {
    const { result } = renderHook(() => useStudioHost(), { wrapper: wrapper() });
    const addPanel = vi.fn();
    const updateParameters = vi.fn();
    const setActive = vi.fn();
    let existing: unknown = null;
    result.current._dockApiRef.current = {
      getPanel: () => existing,
      addPanel,
    } as never;

    act(() => result.current.openPanel('settings', { title: 'Settings', params: { tab: 'providers' } }));
    expect(addPanel).toHaveBeenCalledWith({
      id: 'settings', component: 'settings', title: 'Settings', params: { tab: 'providers' },
      inactive: false,
    });

    existing = { api: { updateParameters, setActive } };
    act(() => result.current.openPanel('settings', { params: { tab: 'account' } }));
    expect(updateParameters).toHaveBeenCalledWith({ tab: 'account' });
    expect(setActive).toHaveBeenCalledTimes(1);
  });

  it('openPanel component opt decouples the panel id from the catalog component (J1 multi-instance)', () => {
    const { result } = renderHook(() => useStudioHost(), { wrapper: wrapper() });
    const addPanel = vi.fn();
    result.current._dockApiRef.current = { getPanel: () => null, addPanel } as never;
    act(() => result.current.openPanel('json-editor:loreweave.manuscript-unit.v1:ch1', {
      component: 'json-editor', title: 'JSON · ch1',
      params: { docType: 'loreweave.manuscript-unit.v1', resourceId: 'ch1' },
    }));
    expect(addPanel).toHaveBeenCalledWith({
      id: 'json-editor:loreweave.manuscript-unit.v1:ch1', component: 'json-editor',
      title: 'JSON · ch1', params: { docType: 'loreweave.manuscript-unit.v1', resourceId: 'ch1' },
      inactive: false,
    });
  });

  it('F15 — openPanel focus:false opens a CLOSED panel as an inactive tab (no focus theft)', () => {
    const { result } = renderHook(() => useStudioHost(), { wrapper: wrapper() });
    const addPanel = vi.fn();
    result.current._dockApiRef.current = { getPanel: () => null, addPanel } as never;
    act(() => result.current.openPanel('editor', { focus: false }));
    expect(addPanel).toHaveBeenCalledWith(expect.objectContaining({ id: 'editor', inactive: true }));
  });

  it('openPanel focus:false updates params without stealing focus', () => {
    const { result } = renderHook(() => useStudioHost(), { wrapper: wrapper() });
    const updateParameters = vi.fn();
    const setActive = vi.fn();
    result.current._dockApiRef.current = {
      getPanel: () => ({ api: { updateParameters, setActive } }),
      addPanel: vi.fn(),
    } as never;
    act(() => result.current.openPanel('settings', { focus: false, params: { tab: 'mcp' } }));
    expect(updateParameters).toHaveBeenCalledWith({ tab: 'mcp' });
    expect(setActive).not.toHaveBeenCalled();
  });

  it('subscribe(selector) fires only when the SELECTED slice changes', () => {
    const { result } = renderHook(() => useStudioHost(), { wrapper: wrapper() });
    const onChapter = vi.fn();
    act(() => { result.current.subscribe(onChapter, (s) => s.activeChapterId); });
    act(() => result.current.publish({ type: 'panels', activePanelIds: ['x'] })); // not the chapter slice
    expect(onChapter).not.toHaveBeenCalled();
    act(() => result.current.publish({ type: 'chapter', chapterId: 'c1', bookId: 'b1' }));
    expect(onChapter).toHaveBeenCalledTimes(1);
  });
});

describe('useStudioBusSelector (S4/D21 slice subscription)', () => {
  it('re-renders only when the selected slice changes, not on every publish', () => {
    const renders = { n: 0 };
    function Probe() {
      const host = useStudioHost();
      const hostRef = useRef(host);
      hostRef.current = host;
      const chapter = useStudioBusSelector((s) => s.activeChapterId);
      renders.n += 1;
      return <button data-testid="pub-panels" onClick={() => hostRef.current.publish({ type: 'panels', activePanelIds: ['a'] })}>{chapter ?? 'none'}</button>;
    }
    render(<StudioHostProvider bookId="b1"><Probe /></StudioHostProvider>);
    const before = renders.n;
    act(() => { screen.getByTestId('pub-panels').click(); }); // publishes a NON-chapter slice
    expect(renders.n).toBe(before); // selector value unchanged → no re-render
  });
});

describe('useRegisterStudioTool lifecycle', () => {
  function Panel({ id }: { id: string }) {
    useRegisterStudioTool(reg(id));
    return <div data-testid={`panel-${id}`} />;
  }
  it('registers on mount, unregisters on unmount', () => {
    let tools: StudioToolRegistration[] = [];
    function Probe() { tools = useRegisteredTools(); return null; }
    const { rerender } = render(
      <StudioHostProvider bookId="b1"><Probe /><Panel id="editor" /></StudioHostProvider>,
    );
    expect(tools.map((t) => t.panelId)).toEqual(['editor']);
    rerender(<StudioHostProvider bookId="b1"><Probe /></StudioHostProvider>);
    expect(tools).toHaveLength(0);
  });
});

describe('status-bar contributions (#11 F2)', () => {
  const item = (id: string, over: Partial<StudioStatusBarItem> = {}): StudioStatusBarItem => ({
    id, side: 'right', component: () => <span data-testid={`sbi-${id}`} />, ...over,
  });

  it('register / replace-by-id / unregister', () => {
    const { result } = renderHook(
      () => ({ host: useStudioHost(), right: useStatusBarItems('right') }),
      { wrapper: wrapper() },
    );
    act(() => result.current.host.registerStatusBarItem(item('meter')));
    act(() => result.current.host.registerStatusBarItem(item('meter', { order: 5 }))); // same id → replace
    expect(result.current.right).toHaveLength(1);
    expect(result.current.right[0]!.order).toBe(5);
    act(() => result.current.host.unregisterStatusBarItem('meter'));
    expect(result.current.right).toHaveLength(0);
  });

  it('useStatusBarItems filters by side and sorts by order (lower = edge-most)', () => {
    const { result } = renderHook(
      () => ({ host: useStudioHost(), left: useStatusBarItems('left'), right: useStatusBarItems('right') }),
      { wrapper: wrapper() },
    );
    act(() => {
      result.current.host.registerStatusBarItem(item('b', { side: 'right', order: 2 }));
      result.current.host.registerStatusBarItem(item('a', { side: 'right', order: 1 }));
      result.current.host.registerStatusBarItem(item('l', { side: 'left' }));
    });
    expect(result.current.right.map((i) => i.id)).toEqual(['a', 'b']);
    expect(result.current.left.map((i) => i.id)).toEqual(['l']);
  });

  it('useRegisterStatusBarItem registers on mount, unregisters on unmount', () => {
    function Item({ id }: { id: string }) { useRegisterStatusBarItem(item(id)); return null; }
    let items: StudioStatusBarItem[] = [];
    function Probe() { items = useStatusBarItems('right'); return null; }
    const { rerender } = render(
      <StudioHostProvider bookId="b1"><Probe /><Item id="badge" /></StudioHostProvider>,
    );
    expect(items.map((i) => i.id)).toEqual(['badge']);
    rerender(<StudioHostProvider bookId="b1"><Probe /></StudioHostProvider>);
    expect(items).toHaveLength(0);
  });
});

describe('guard', () => {
  it('useStudioHost throws outside a provider', () => {
    function Bad() { useStudioHost(); return null; }
    const orig = console.error;
    console.error = () => {};
    expect(() => render(<Bad />)).toThrow(/StudioHostProvider/);
    console.error = orig;
  });
});

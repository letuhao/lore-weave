import { describe, expect, it } from 'vitest';
import { act, render, renderHook, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import {
  StudioHostProvider, useRegisteredTools, useRegisterStudioTool, useStudioBus, useStudioHost,
} from '../StudioHostProvider';
import { applyBusEvent, type StudioBusSnapshot, type StudioToolRegistration } from '../types';

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
});

describe('StudioHost registry', () => {
  it('register / getTool / list; unregister removes; re-register is idempotent (no dup)', () => {
    const { result } = renderHook(() => useStudioHost(), { wrapper: wrapper() });
    act(() => result.current.register(reg('compose')));
    act(() => result.current.register(reg('compose', { label: 'Compose v2' }))); // same id → replace, not add
    expect(result.current.listTools()).toHaveLength(1);
    expect(result.current.getTool('compose')?.label).toBe('Compose v2');
    act(() => result.current.unregister('compose'));
    expect(result.current.listTools()).toHaveLength(0);
    expect(result.current.getTool('compose')).toBeNull();
  });

  it('useRegisteredTools re-renders when a tool (un)registers', () => {
    const { result } = renderHook(
      () => ({ host: useStudioHost(), tools: useRegisteredTools() }),
      { wrapper: wrapper() },
    );
    expect(result.current.tools).toHaveLength(0);
    act(() => result.current.host.register(reg('cast')));
    expect(result.current.tools.map((t) => t.panelId)).toEqual(['cast']);
    act(() => result.current.host.unregister('cast'));
    expect(result.current.tools).toHaveLength(0);
  });
});

describe('StudioContextBus', () => {
  it('publish updates the snapshot + bumps revision, reactively', () => {
    const { result } = renderHook(
      () => ({ host: useStudioHost(), snap: useStudioBus() }),
      { wrapper: wrapper() },
    );
    expect(result.current.snap).toMatchObject({ revision: 0, bookId: 'b1', activePanelIds: [] });
    act(() => result.current.host.publish({ type: 'chapter', chapterId: 'c9', bookId: 'b1' }));
    expect(result.current.snap).toMatchObject({ revision: 1, activeChapterId: 'c9' });
    // imperative getBusSnapshot agrees with the reactive value
    expect(result.current.host.getBusSnapshot().activeChapterId).toBe('c9');
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
    rerender(<StudioHostProvider bookId="b1"><Probe /></StudioHostProvider>); // Panel unmounts
    expect(tools).toHaveLength(0);
  });
});

describe('guard', () => {
  it('useStudioHost throws outside a provider', () => {
    function Bad() { useStudioHost(); return null; }
    // Swallow the expected error boundary noise.
    const spy = { error: console.error };
    console.error = () => {};
    expect(() => render(<Bad />)).toThrow(/StudioHostProvider/);
    console.error = spy.error;
    expect(screen.queryByTestId('x')).toBeNull();
  });
});

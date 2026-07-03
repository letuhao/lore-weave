import { describe, expect, it, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { degradedSurfaceFromSession, useAgentSurface } from '../useAgentSurface';
import type { AgentSurfaceState, ChatSession } from '../../types';

describe('useAgentSurface', () => {
  it('degraded mode derives counts from session pins', () => {
    const session = {
      session_id: 's1',
      enabled_tools: ['book_get_chapter'],
      enabled_skills: ['universal'],
      activated_tools: ['translation_start'],
    } as unknown as ChatSession;
    const state = degradedSurfaceFromSession(session);
    expect(state.pinned_count).toBe(1);
    expect(state.activated_count).toBe(1);
    expect(state.injected_skills).toEqual(['universal']);
    expect(state.phase).toBe('Idle');
  });

  it('applyEvent updates phase from SSE payload', () => {
    const session = { session_id: 's1' } as unknown as ChatSession;
    const { result } = renderHook(() => useAgentSurface(session));
    act(() => {
      result.current.applyEvent({
        phase: 'Curated',
        pinned_count: 2,
        hot_seed_count: 5,
        activated_count: 0,
        injected_skills: ['glossary'],
        running_tool: null,
        last_find_tools_query: null,
        find_tools_call_count: 0,
      });
    });
    expect(result.current.state.phase).toBe('Curated');
    expect(result.current.state.pinned_count).toBe(2);
  });

  it('accumulates a phase trail, resetting when a new turn leaves Idle', () => {
    const session = { session_id: 's1' } as unknown as ChatSession;
    const { result } = renderHook(() => useAgentSurface(session));
    const p = (phase: AgentSurfaceState['phase']): AgentSurfaceState => ({
      phase,
      pinned_count: 0,
      hot_seed_count: 0,
      activated_count: 0,
      injected_skills: [],
      running_tool: null,
      last_find_tools_query: null,
      find_tools_call_count: 0,
    });
    act(() => result.current.applyEvent(p('Curated')));
    act(() => result.current.applyEvent(p('Discovering')));
    act(() => result.current.applyEvent(p('Discovering'))); // same phase → no dup
    act(() => result.current.applyEvent(p('Idle')));
    expect(result.current.trail).toEqual(['Curated', 'Discovering', 'Idle']);
    // the next turn's first transition out of Idle resets the trail.
    act(() => result.current.applyEvent(p('Curated')));
    expect(result.current.trail).toEqual(['Curated']);
  });

  it('toggleExpanded persists to localStorage', () => {
    const session = { session_id: 's1' } as unknown as ChatSession;
    const { result } = renderHook(() => useAgentSurface(session));
    act(() => {
      result.current.toggleExpanded();
    });
    expect(localStorage.getItem('lw_chat_inspector_expanded')).toBe('1');
  });
});

describe('runChatStream buildRequest fields', () => {
  it('includes enabled_tools and enabled_skills when set', async () => {
    const { runChatStream } = await import('../runChatStream');
    let capturedBody: Record<string, unknown> = {};
    const mockFetch = vi.fn(async (_url: string, init?: RequestInit) => {
      capturedBody = JSON.parse(String(init?.body));
      const encoder = new TextEncoder();
      const stream = new ReadableStream({
        start(controller) {
          controller.enqueue(encoder.encode('data: {"type":"RUN_FINISHED","result":{}}\n\n'));
          controller.close();
        },
      });
      return new Response(stream, { status: 200 });
    });
    vi.stubGlobal('fetch', mockFetch);
    await runChatStream(
      {
        sessionId: 'sess',
        content: 'hi',
        enabledTools: ['book_get_chapter'],
        enabledSkills: ['universal'],
      },
      'token',
      {},
      new AbortController().signal,
    );
    expect(capturedBody.enabled_tools).toEqual(['book_get_chapter']);
    expect(capturedBody.enabled_skills).toEqual(['universal']);
    vi.unstubAllGlobals();
  });
});

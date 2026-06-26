import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// L-chat (M2 / D-T5.4-CHAT-HOIST) — the hub protocol + the pure runChatStream
// core, exercised WITHOUT a real SharedWorker (jsdom has none). Two suites:
//   1. runChatStream — every AG-UI event case → the correct accumulator facet
//      (proves none of the 7 handled cases was dropped in the extraction).
//   2. createChatStateHub — start→snapshot→stop, replay-to-new-port, the
//      callback→snapshot mapping, tool-result inbound, and supersede.

// chatApi.messagesUrl / toolResultsUrl are the only api surface the core touches.
vi.mock('../../api', () => ({
  chatApi: {
    messagesUrl: (sid: string) => `http://test/v1/chat/sessions/${sid}/messages`,
    toolResultsUrl: (sid: string) => `http://test/v1/chat/sessions/${sid}/tool-results`,
  },
}));

import { runChatStream } from '../../hooks/runChatStream';
import type { ChatCallbacks, ChatStreamArgs, ChatStreamResult } from '../../hooks/runChatStream';
import { createChatStateHub } from '../chatStateHub';
import type { HubPort, InboundMessage, OutboundMessage } from '../chatStateHub';

// ── SSE fetch stub (mirrors the existing chat-test helper) ────────────────────
function sseResponse(lines: string[]): Response {
  const encoder = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const line of lines) controller.enqueue(encoder.encode(`data: ${line}\n`));
      controller.close();
    },
  });
  return { ok: true, status: 200, statusText: 'OK', body } as unknown as Response;
}
function stubFetch(lines: string[]) {
  const fetchMock = vi.fn().mockResolvedValue(sseResponse(lines));
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}
function j(o: unknown) { return JSON.stringify(o); }

const ARGS: ChatStreamArgs = { sessionId: 's-1', content: 'hi' };

/** Collect every callback facet runChatStream emits. */
function collectingCallbacks() {
  const calls = {
    phases: [] as string[],
    reasoning: [] as string[],
    text: [] as string[],
    toolCalls: [] as unknown[],
    activities: [] as unknown[],
    memoryModes: [] as string[],
    composing: [] as boolean[],
    end: undefined as ChatStreamResult | undefined,
    aborted: undefined as ChatStreamResult | undefined,
    error: undefined as string | undefined,
  };
  const cb: ChatCallbacks = {
    onPhase: (p) => calls.phases.push(p),
    onReasoning: (acc) => calls.reasoning.push(acc),
    onText: (acc) => calls.text.push(acc),
    onToolCall: (r) => calls.toolCalls.push(r),
    onActivity: (a) => calls.activities.push(a),
    onMemoryMode: (m) => calls.memoryModes.push(m),
    onComposing: (a) => calls.composing.push(a),
    onError: (m) => { calls.error = m; },
    onEnd: (r) => { calls.end = r; },
    onAbort: (r) => { calls.aborted = r; },
  };
  return { calls, cb };
}

describe('runChatStream — every AG-UI event case is preserved', () => {
  beforeEach(() => vi.restoreAllMocks());
  afterEach(() => vi.unstubAllGlobals());

  it('1. REASONING_MESSAGE_CONTENT → onPhase(thinking) + accumulated reasoning', async () => {
    stubFetch([
      j({ type: 'REASONING_MESSAGE_CONTENT', delta: 'a ' }),
      j({ type: 'REASONING_MESSAGE_CONTENT', delta: 'b' }),
      j({ type: 'RUN_FINISHED', result: {} }),
    ]);
    const { calls, cb } = collectingCallbacks();
    const r = await runChatStream(ARGS, 't', cb, new AbortController().signal);
    expect(calls.phases[0]).toBe('thinking');
    expect(calls.reasoning).toEqual(['a ', 'a b']);
    expect(r.reasoning).toBe('a b');
  });

  it('2. TEXT_MESSAGE_CONTENT → onPhase(responding) + accumulated content', async () => {
    stubFetch([
      j({ type: 'TEXT_MESSAGE_CONTENT', delta: 'Hel' }),
      j({ type: 'TEXT_MESSAGE_CONTENT', delta: 'lo' }),
      j({ type: 'RUN_FINISHED', result: {} }),
    ]);
    const { calls, cb } = collectingCallbacks();
    const r = await runChatStream(ARGS, 't', cb, new AbortController().signal);
    expect(calls.phases).toContain('responding');
    expect(calls.text).toEqual(['Hel', 'Hello']);
    expect(r.content).toBe('Hello');
  });

  it('3+5. TOOL_CALL_START then TOOL_CALL_RESULT → one {tool, ok} record', async () => {
    stubFetch([
      j({ type: 'TOOL_CALL_START', toolCallId: 'c1', toolCallName: 'memory_search' }),
      j({ type: 'TOOL_CALL_RESULT', toolCallId: 'c1', content: j({ ok: true, result: { hits: 1 } }) }),
      j({ type: 'RUN_FINISHED', result: {} }),
    ]);
    const { calls, cb } = collectingCallbacks();
    const r = await runChatStream(ARGS, 't', cb, new AbortController().signal);
    expect(r.toolCalls).toEqual([expect.objectContaining({ tool: 'memory_search', ok: true })]);
    expect(calls.toolCalls).toHaveLength(1);
  });

  it('5. TOOL_CALL_RESULT with {ok:false} → ok=false (not misread)', async () => {
    stubFetch([
      j({ type: 'TOOL_CALL_START', toolCallId: 'c1', toolCallName: 't' }),
      j({ type: 'TOOL_CALL_RESULT', toolCallId: 'c1', content: j({ ok: false, error: 'x' }) }),
      j({ type: 'RUN_FINISHED', result: {} }),
    ]);
    const { cb } = collectingCallbacks();
    const r = await runChatStream(ARGS, 't', cb, new AbortController().signal);
    expect(r.toolCalls[0].ok).toBe(false);
  });

  it('5. TOOL_CALL_RESULT WITHOUT a START is skipped', async () => {
    stubFetch([
      j({ type: 'TOOL_CALL_RESULT', toolCallId: 'orphan', content: j({ ok: true }) }),
      j({ type: 'RUN_FINISHED', result: {} }),
    ]);
    const { cb } = collectingCallbacks();
    const r = await runChatStream(ARGS, 't', cb, new AbortController().signal);
    expect(r.toolCalls).toHaveLength(0);
  });

  it('6. CUSTOM memoryMode → onMemoryMode', async () => {
    stubFetch([
      j({ type: 'CUSTOM', name: 'memoryMode', value: { mode: 'degraded' } }),
      j({ type: 'RUN_FINISHED', result: {} }),
    ]);
    const { calls, cb } = collectingCallbacks();
    await runChatStream(ARGS, 't', cb, new AbortController().signal);
    expect(calls.memoryModes).toEqual(['degraded']);
  });

  it('6. CUSTOM persisted → messageId on result', async () => {
    stubFetch([
      j({ type: 'CUSTOM', name: 'persisted', value: { messageId: 'm-9' } }),
      j({ type: 'RUN_FINISHED', result: {} }),
    ]);
    const { cb } = collectingCallbacks();
    const r = await runChatStream(ARGS, 't', cb, new AbortController().signal);
    expect(r.messageId).toBe('m-9');
  });

  it('6. CUSTOM composing → onComposing on/off', async () => {
    stubFetch([
      j({ type: 'CUSTOM', name: 'composing', value: { active: true } }),
      j({ type: 'CUSTOM', name: 'composing', value: { active: false } }),
      j({ type: 'RUN_FINISHED', result: {} }),
    ]);
    const { calls, cb } = collectingCallbacks();
    await runChatStream(ARGS, 't', cb, new AbortController().signal);
    expect(calls.composing).toEqual([true, false]);
  });

  it('6. CUSTOM activity → accumulated; malformed (no op) ignored', async () => {
    stubFetch([
      j({ type: 'CUSTOM', name: 'activity', value: { op: 'chapter.create', summary: 'Made it' } }),
      j({ type: 'CUSTOM', name: 'activity', value: { summary: 'no op' } }),
      j({ type: 'RUN_FINISHED', result: {} }),
    ]);
    const { cb } = collectingCallbacks();
    const r = await runChatStream(ARGS, 't', cb, new AbortController().signal);
    expect(r.activities).toEqual([{ op: 'chapter.create', summary: 'Made it' }]);
  });

  it('7. RUN_FINISHED carries usage + timing', async () => {
    stubFetch([
      j({ type: 'RUN_FINISHED', result: { usage: { promptTokens: 3, completionTokens: 4 }, timing: { responseTimeMs: 100 } } }),
    ]);
    const { cb } = collectingCallbacks();
    const r = await runChatStream(ARGS, 't', cb, new AbortController().signal);
    expect(r.usage).toEqual({ promptTokens: 3, completionTokens: 4 });
    expect(r.timing).toEqual({ responseTimeMs: 100 });
  });

  it('7. RUN_FINISHED suspended → pending frontend-tool record with parsed args', async () => {
    stubFetch([
      j({ type: 'TOOL_CALL_START', toolCallId: 'c1', toolCallName: 'propose_edit' }),
      j({ type: 'TOOL_CALL_ARGS', toolCallId: 'c1', delta: '{"text":"hi"}' }),
      j({ type: 'RUN_FINISHED', result: { status: 'suspended', pendingToolCall: { runId: 'r1', toolCallId: 'c1', toolName: 'propose_edit' } } }),
    ]);
    const { cb } = collectingCallbacks();
    const r = await runChatStream(ARGS, 't', cb, new AbortController().signal);
    expect(r.toolCalls).toEqual([
      expect.objectContaining({ tool: 'propose_edit', pending: true, runId: 'r1', toolCallId: 'c1', args: { text: 'hi' } }),
    ]);
  });

  it('RUN_ERROR throws the server message', async () => {
    stubFetch([j({ type: 'RUN_ERROR', message: 'boom' })]);
    const { cb } = collectingCallbacks();
    await expect(runChatStream(ARGS, 't', cb, new AbortController().signal)).rejects.toThrow('boom');
  });

  it('non-OK response throws `${status}: detail`', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false, status: 503, statusText: 'busy', text: async () => 'overloaded',
    } as unknown as Response));
    const { cb } = collectingCallbacks();
    await expect(runChatStream(ARGS, 't', collectingCallbacks().cb, new AbortController().signal)).rejects.toThrow('503');
    void cb;
  });

  it('abort → onAbort(partial), resolves (does not throw)', async () => {
    // A fetch that rejects with AbortError once the signal fires.
    const fetchMock = vi.fn().mockImplementation((_u: string, init: RequestInit) =>
      new Promise((_res, rej) => {
        init.signal?.addEventListener('abort', () => rej(new DOMException('aborted', 'AbortError')));
      }),
    );
    vi.stubGlobal('fetch', fetchMock);
    const { calls, cb } = collectingCallbacks();
    const ctrl = new AbortController();
    const p = runChatStream(ARGS, 't', cb, ctrl.signal);
    ctrl.abort();
    await expect(p).resolves.toBeDefined();
    expect(calls.aborted).toBeDefined();
    expect(calls.end).toBeUndefined();
  });

  it('framing-only events (RUN_STARTED, *_START/*_END) are safe no-ops', async () => {
    stubFetch([
      j({ type: 'RUN_STARTED', threadId: 's', runId: 'r' }),
      j({ type: 'REASONING_START' }), j({ type: 'REASONING_MESSAGE_START' }),
      j({ type: 'REASONING_MESSAGE_END' }), j({ type: 'REASONING_END' }),
      j({ type: 'TEXT_MESSAGE_START' }), j({ type: 'TEXT_MESSAGE_END' }),
      j({ type: 'TOOL_CALL_END', toolCallId: 'c1' }),
      j({ type: 'TEXT_MESSAGE_CONTENT', delta: 'ok' }),
      j({ type: 'RUN_FINISHED', result: {} }),
    ]);
    const { cb } = collectingCallbacks();
    const r = await runChatStream(ARGS, 't', cb, new AbortController().signal);
    expect(r.content).toBe('ok'); // stream survived all framing events
  });

  it('sends x-loreweave-stream-format: agui header + body fields', async () => {
    const fetchMock = stubFetch([j({ type: 'RUN_FINISHED', result: {} })]);
    await runChatStream(
      { sessionId: 's-1', content: 'hi', editorContext: { book_id: 'b', chapter_id: 'c' }, displayLanguage: 'en', composeMode: true },
      't', collectingCallbacks().cb, new AbortController().signal,
    );
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('http://test/v1/chat/sessions/s-1/messages');
    expect((init.headers as Record<string, string>)['x-loreweave-stream-format']).toBe('agui');
    const body = JSON.parse(init.body as string);
    expect(body).toMatchObject({ content: 'hi', editor_context: { book_id: 'b', chapter_id: 'c' }, display_language: 'en', disable_tools: true });
  });

  it('override (resume) path uses the override url/body verbatim', async () => {
    const fetchMock = stubFetch([j({ type: 'RUN_FINISHED', result: {} })]);
    await runChatStream(
      { sessionId: 's-1', content: '', override: { url: 'http://test/resume', body: { run_id: 'r1' } } },
      't', collectingCallbacks().cb, new AbortController().signal,
    );
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('http://test/resume');
    expect(JSON.parse(init.body as string)).toEqual({ run_id: 'r1' });
  });
});

// ── Hub protocol ──────────────────────────────────────────────────────────────

/** A fake MessagePort that records outbound snapshots + lets a test push inbound. */
function fakePort() {
  const received: OutboundMessage[] = [];
  const port: HubPort = {
    postMessage: (m) => received.push(m),
    onmessage: null,
    start: vi.fn(),
  };
  const send = (msg: InboundMessage) => port.onmessage?.({ data: msg });
  const last = () => received[received.length - 1]?.state;
  return { port, received, send, last };
}

/** A controllable stub `run` — captures the callbacks so a test can drive the
 *  hub's snapshot transitions deterministically (no fetch / no timers). */
function stubRun() {
  let cbRef: ChatCallbacks | null = null;
  let signalRef: AbortSignal | null = null;
  let resolve: (r: ChatStreamResult) => void = () => {};
  const fn = vi.fn((_a: ChatStreamArgs, _t: string | null, cb: ChatCallbacks, signal: AbortSignal) => {
    cbRef = cb;
    signalRef = signal;
    return new Promise<ChatStreamResult>((res) => { resolve = res; });
  });
  return {
    fn,
    cb: () => cbRef!,
    signal: () => signalRef!,
    finish: (r: ChatStreamResult) => resolve(r),
  };
}

const EMPTY_RESULT: ChatStreamResult = {
  content: '', reasoning: '', toolCalls: [], activities: [],
  messageId: null, usage: {}, timing: {},
};

describe('createChatStateHub — protocol', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it('replays the current snapshot to a newly-connected port', () => {
    const run = stubRun();
    const hub = createChatStateHub(run.fn);
    const a = fakePort();
    hub.addPort(a.port);
    // The connect-replay fires immediately (the ACK-timeout health check).
    expect(a.received[0].type).toBe('state');
    expect(a.last().streamStatus).toBe('idle');
    expect(a.port.start).toHaveBeenCalled();
  });

  it('start → streaming snapshot fans to ALL ports; turnId bumps', () => {
    const run = stubRun();
    const hub = createChatStateHub(run.fn);
    const a = fakePort();
    const b = fakePort();
    hub.addPort(a.port);
    hub.addPort(b.port);
    a.send({ type: 'start', args: ARGS, token: 't' });
    expect(run.fn).toHaveBeenCalledTimes(1);
    expect(a.last().streamStatus).toBe('streaming');
    expect(b.last().streamStatus).toBe('streaming'); // fanned to the 2nd window
    expect(a.last().turnId).toBe(1);
  });

  it('maps every callback facet onto the snapshot', () => {
    const run = stubRun();
    const hub = createChatStateHub(run.fn);
    const a = fakePort();
    hub.addPort(a.port);
    a.send({ type: 'start', args: ARGS, token: 't' });
    const cb = run.cb();

    cb.onPhase!('thinking');
    expect(a.last().streamPhase).toBe('thinking');
    cb.onReasoning!('think', 'think');
    expect(a.last().streamingReasoning).toBe('think');
    cb.onPhase!('responding');
    expect(a.last().streamPhase).toBe('responding');
    cb.onText!('answer', 'answer');
    expect(a.last().streamingText).toBe('answer');
    cb.onMemoryMode!('static');
    expect(a.last().memoryMode).toBe('static');
    cb.onComposing!(true);
    expect(a.last().isComposing).toBe(true);
    cb.onActivity!({ op: 'chapter.create', summary: 's' });
    expect(a.last().activities).toEqual([{ op: 'chapter.create', summary: 's' }]);
    cb.onToolCall!({ tool: 'memory_search', ok: true });
    expect(a.last().toolCalls).toEqual([{ tool: 'memory_search', ok: true }]);
  });

  it('a suspended tool-call record surfaces the suspendedRun gate', () => {
    const run = stubRun();
    const hub = createChatStateHub(run.fn);
    const a = fakePort();
    hub.addPort(a.port);
    a.send({ type: 'start', args: ARGS, token: 't' });
    run.cb().onToolCall!({ tool: 'propose_edit', ok: true, pending: true, runId: 'r1', toolCallId: 'c1', args: { text: 'x' } });
    expect(a.last().suspendedRun).toEqual({ runId: 'r1', toolCallId: 'c1', toolName: 'propose_edit', args: { text: 'x' } });
  });

  it('onEnd → ended snapshot carrying the assembled result', () => {
    const run = stubRun();
    const hub = createChatStateHub(run.fn);
    const a = fakePort();
    hub.addPort(a.port);
    a.send({ type: 'start', args: ARGS, token: 't' });
    const result: ChatStreamResult = { ...EMPTY_RESULT, content: 'done', messageId: 'm-1' };
    run.cb().onEnd!(result);
    expect(a.last().ended).toBe(true);
    expect(a.last().streamStatus).toBe('idle');
    expect(a.last().result).toEqual(result);
  });

  it('stop aborts the run signal + settles the snapshot to idle', () => {
    const run = stubRun();
    const hub = createChatStateHub(run.fn);
    const a = fakePort();
    hub.addPort(a.port);
    a.send({ type: 'start', args: ARGS, token: 't' });
    const sig = run.signal();
    a.send({ type: 'stop' });
    expect(sig.aborted).toBe(true);
    expect(a.last().streamStatus).toBe('idle');
  });

  it('a 2nd start supersedes the in-flight run (abort + new turnId)', () => {
    const run = stubRun();
    const hub = createChatStateHub(run.fn);
    const a = fakePort();
    hub.addPort(a.port);
    a.send({ type: 'start', args: ARGS, token: 't' });
    const firstSignal = run.signal();
    a.send({ type: 'start', args: ARGS, token: 't' });
    expect(firstSignal.aborted).toBe(true);        // 1st superseded
    expect(a.last().turnId).toBe(2);
    expect(run.fn).toHaveBeenCalledTimes(2);
  });

  it('toolResult inbound re-enters the run loop with the override', () => {
    const run = stubRun();
    const hub = createChatStateHub(run.fn);
    const a = fakePort();
    hub.addPort(a.port);
    a.send({ type: 'toolResult', override: { url: 'http://test/resume', body: { run_id: 'r1' } }, token: 't' });
    expect(run.fn).toHaveBeenCalledTimes(1);
    const passedArgs = run.fn.mock.calls[0][0] as ChatStreamArgs;
    expect(passedArgs.override).toEqual({ url: 'http://test/resume', body: { run_id: 'r1' } });
    expect(a.last().streamStatus).toBe('streaming');
  });

  it('clear resets the streaming buffers without aborting', () => {
    const run = stubRun();
    const hub = createChatStateHub(run.fn);
    const a = fakePort();
    hub.addPort(a.port);
    a.send({ type: 'start', args: ARGS, token: 't' });
    run.cb().onText!('partial', 'partial');
    a.send({ type: 'clear' });
    expect(a.last().streamingText).toBe('');
    expect(a.last().toolCalls).toEqual([]);
  });

  it('a late-joining port replays the in-flight snapshot (pop-out late join)', () => {
    const run = stubRun();
    const hub = createChatStateHub(run.fn);
    const a = fakePort();
    hub.addPort(a.port);
    a.send({ type: 'start', args: ARGS, token: 't' });
    run.cb().onText!('streaming text', 'streaming text');
    // A new window connects mid-turn — it should immediately see the in-flight text.
    const b = fakePort();
    hub.addPort(b.port);
    expect(b.last().streamingText).toBe('streaming text');
    expect(b.last().streamStatus).toBe('streaming');
  });
});

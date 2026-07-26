// LOOM Composition (T5.4 M4 Slice B) — the SharedWorker's PURE protocol core.
//
// Owns ONE co-writer generation and fans its state to every connected window port, so
// the opener and any pop-outs share a single stream (and it survives the opener closing
// — the worker lives as long as ANY window keeps a port). Extracted from the worker
// shell so it's unit-testable without a real SharedWorker (jsdom has none).
//
// Protocol (deliberately snapshot-based, not incremental → drift-free): every state
// change broadcasts the FULL snapshot `{type:'state', state}`; a newly-connected port
// gets the current snapshot immediately (replay). Inbound: start / stop / clear.
import type { GenerateArgs, GenerationCallbacks, ReasoningInfo } from '../hooks/runCompositionGeneration';

export type LiveStreamState = {
  ghost: string;
  streaming: boolean;
  jobId: string | null;
  error: string | null;
  reasoning: ReasoningInfo | null;
};

export type InboundMessage =
  | { type: 'start'; args: GenerateArgs; token: string | null }
  | { type: 'stop' }
  | { type: 'clear' };

export type OutboundMessage = { type: 'state'; state: LiveStreamState };

/** Minimal port shape — a real MessagePort, or a fake in tests. */
export type HubPort = {
  postMessage: (m: OutboundMessage) => void;
  onmessage: ((e: { data: InboundMessage }) => void) | null;
  start?: () => void;
};

type RunFn = (args: GenerateArgs, token: string | null, cb: GenerationCallbacks, signal: AbortSignal) => Promise<void>;

const EMPTY: LiveStreamState = { ghost: '', streaming: false, jobId: null, error: null, reasoning: null };

export function createLiveStateHub(run: RunFn) {
  const ports = new Set<HubPort>();
  let state: LiveStreamState = { ...EMPTY };
  let ctrl: AbortController | null = null;

  const broadcast = () => {
    const msg: OutboundMessage = { type: 'state', state };
    for (const p of ports) { try { p.postMessage(msg); } catch { /* dead port (closed window) */ } }
  };
  const set = (patch: Partial<LiveStreamState>) => { state = { ...state, ...patch }; broadcast(); };

  function startRun(args: GenerateArgs, token: string | null) {
    ctrl?.abort();                       // a 2nd generate supersedes the in-flight one
    const c = new AbortController();
    ctrl = c;
    const isCurrent = () => ctrl === c;
    state = { ghost: '', streaming: true, jobId: null, error: null, reasoning: null };
    broadcast();
    run(
      args, token,
      {
        onJob: (id, r) => { if (!isCurrent()) return; set({ jobId: id, ...(r ? { reasoning: r } : {}) }); },
        onToken: (d) => { if (!isCurrent()) return; set({ ghost: state.ghost + d }); },
        onText: (t) => { if (!isCurrent()) return; set({ ghost: t }); },
        onError: (m) => { if (!isCurrent()) return; set({ error: m }); },
      },
      c.signal,
    )
      .catch((e: unknown) => { if (isCurrent() && (e as Error)?.name !== 'AbortError') set({ error: String(e) }); })
      .finally(() => { if (isCurrent()) { ctrl = null; set({ streaming: false }); } });
  }

  function handle(msg: InboundMessage) {
    if (msg.type === 'start') startRun(msg.args, msg.token);
    else if (msg.type === 'stop') { ctrl?.abort(); ctrl = null; set({ streaming: false }); }
    else if (msg.type === 'clear') set({ ghost: '' });
  }

  function addPort(port: HubPort) {
    ports.add(port);
    port.onmessage = (e) => handle(e.data);
    port.start?.();
    port.postMessage({ type: 'state', state });   // replay the current snapshot to the new window
  }

  return {
    addPort,
    /** test/inspection helpers */
    _state: () => state,
    _portCount: () => ports.size,
  };
}

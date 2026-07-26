// LOOM Composition (T5.4 M4 Slice B) — the SharedWorker shell.
//
// Thin wiring only (the protocol lives in the unit-tested liveStateHub): each window
// that connects hands its MessagePort to the hub, which owns the single co-writer
// stream and fans state snapshots to all ports. Because a SharedWorker lives as long as
// ANY connected port, an in-flight generation survives the opener window closing — a
// still-open pop-out keeps receiving tokens.
//
// Vite bundles this via `new SharedWorker(new URL('./liveState.shared-worker.ts',
// import.meta.url), { type: 'module' })`. It runs in a Worker global scope (no DOM);
// runCompositionGeneration is DOM-free and resolves the gateway via a relative URL.
/// <reference lib="webworker" />
import { runCompositionGeneration } from '../hooks/runCompositionGeneration';
import { createLiveStateHub, type HubPort } from './liveStateHub';

const hub = createLiveStateHub(runCompositionGeneration);

// SharedWorkerGlobalScope.onconnect fires once per connecting window; e.ports[0] is that
// window's MessagePort.
(self as unknown as SharedWorkerGlobalScope).onconnect = (e: MessageEvent) => {
  const port = e.ports[0] as unknown as HubPort;
  hub.addPort(port);
};

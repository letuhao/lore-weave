// L-chat (T5.4 M2 / D-T5.4-CHAT-HOIST) — the SharedWorker shell.
//
// Thin wiring only (the protocol lives in the unit-tested chatStateHub): each
// window that connects hands its MessagePort to the hub, which owns the single
// cowriter chat turn and fans state snapshots to all ports. Because a
// SharedWorker lives as long as ANY connected port, an in-flight turn survives
// the opener window closing — a still-open pop-out keeps receiving tokens.
//
// Vite bundles this via `new SharedWorker(new URL('./chatLiveState.shared-worker.ts',
// import.meta.url), { type: 'module' })`. It runs in a Worker global scope (no
// DOM); runChatStream is DOM-free and resolves the gateway via a relative URL.
/// <reference lib="webworker" />
import { runChatStream } from '../hooks/runChatStream';
import { createChatStateHub, type HubPort } from './chatStateHub';

const hub = createChatStateHub(runChatStream);

// SharedWorkerGlobalScope.onconnect fires once per connecting window; e.ports[0]
// is that window's MessagePort.
(self as unknown as SharedWorkerGlobalScope).onconnect = (e: MessageEvent) => {
  const port = e.ports[0] as unknown as HubPort;
  hub.addPort(port);
};

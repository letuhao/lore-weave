import { describe, expect, it, vi } from 'vitest';
import { createLiveStateHub, type HubPort, type LiveStreamState } from '../liveStateHub';
import type { GenerationCallbacks } from '../../hooks/runCompositionGeneration';

function fakePort() {
  const sent: LiveStreamState[] = [];
  const port: HubPort & { sent: LiveStreamState[]; started: boolean } = {
    sent,
    started: false,
    onmessage: null,
    postMessage: (m) => { if (m.type === 'state') sent.push(m.state); },
    start() { this.started = true; },
  };
  return port;
}

const ARGS = { projectId: 'p1', modelSource: 'user_model', modelRef: 'm1' };

/** A run() the test can drive: captures the callbacks and the resolve handle. */
function controllableRun() {
  let cb: GenerationCallbacks | null = null;
  let resolve!: () => void;
  let reject!: (e: unknown) => void;
  const run = vi.fn((_a: unknown, _t: unknown, callbacks: GenerationCallbacks) => {
    cb = callbacks;
    return new Promise<void>((res, rej) => { resolve = res; reject = rej; });
  });
  return { run, cb: () => cb!, resolve: () => resolve(), reject: (e: unknown) => reject(e) };
}
const flush = () => new Promise((r) => setTimeout(r, 0));

describe('liveStateHub (T5.4 M4 Slice B)', () => {
  it('replays the current snapshot to a newly-connected port', () => {
    const { run } = controllableRun();
    const hub = createLiveStateHub(run);
    const p = fakePort();
    hub.addPort(p);
    expect(p.started).toBe(true);
    expect(p.sent.at(-1)).toEqual({ ghost: '', streaming: false, jobId: null, error: null, reasoning: null });
  });

  it('start → broadcasts streaming snapshots; tokens grow the ghost across ALL ports', async () => {
    const drv = controllableRun();
    const hub = createLiveStateHub(drv.run);
    const a = fakePort();
    const b = fakePort();
    hub.addPort(a);
    hub.addPort(b);
    a.onmessage!({ data: { type: 'start', args: ARGS, token: 'tok' } });
    expect(drv.run).toHaveBeenCalledTimes(1);
    expect(a.sent.at(-1)).toMatchObject({ streaming: true, ghost: '' });
    expect(b.sent.at(-1)).toMatchObject({ streaming: true, ghost: '' });
    drv.cb().onJob!('j1', { source: 'auto', effort: 'low' });
    drv.cb().onToken!('Hello ');
    drv.cb().onToken!('world');
    // both windows see the same grown ghost (single shared stream)
    expect(a.sent.at(-1)).toMatchObject({ ghost: 'Hello world', jobId: 'j1', reasoning: { source: 'auto', effort: 'low' } });
    expect(b.sent.at(-1)).toMatchObject({ ghost: 'Hello world', jobId: 'j1' });
    drv.resolve();
    await flush();
    expect(a.sent.at(-1)).toMatchObject({ streaming: false, ghost: 'Hello world' });
  });

  it('a port that connects MID-stream replays the in-flight ghost (survive/late-join)', () => {
    const drv = controllableRun();
    const hub = createLiveStateHub(drv.run);
    const a = fakePort();
    hub.addPort(a);
    a.onmessage!({ data: { type: 'start', args: ARGS, token: 't' } });
    drv.cb().onToken!('partial');
    // a pop-out opens now → gets the current ghost immediately
    const late = fakePort();
    hub.addPort(late);
    expect(late.sent.at(-1)).toMatchObject({ ghost: 'partial', streaming: true });
  });

  it('stop aborts and flips streaming false', () => {
    const drv = controllableRun();
    const hub = createLiveStateHub(drv.run);
    const a = fakePort();
    hub.addPort(a);
    a.onmessage!({ data: { type: 'start', args: ARGS, token: 't' } });
    a.onmessage!({ data: { type: 'stop' } });
    expect(a.sent.at(-1)).toMatchObject({ streaming: false });
  });

  it('clear empties the shared ghost', () => {
    const drv = controllableRun();
    const hub = createLiveStateHub(drv.run);
    const a = fakePort();
    hub.addPort(a);
    a.onmessage!({ data: { type: 'start', args: ARGS, token: 't' } });
    drv.cb().onToken!('text');
    a.onmessage!({ data: { type: 'clear' } });
    expect(a.sent.at(-1)).toMatchObject({ ghost: '' });
  });

  it('a 2nd start supersedes the first — the stale run cannot clobber', async () => {
    const drv = controllableRun();
    const hub = createLiveStateHub(drv.run);
    const a = fakePort();
    hub.addPort(a);
    a.onmessage!({ data: { type: 'start', args: ARGS, token: 't' } });
    const firstCb = drv.cb();
    a.onmessage!({ data: { type: 'start', args: ARGS, token: 't' } });   // supersede
    // the FIRST run's late token must be ignored (it's no longer current)
    firstCb.onToken!('STALE');
    expect(a.sent.at(-1)).not.toMatchObject({ ghost: 'STALE' });
  });
});

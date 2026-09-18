import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// Cycle 9 (plan 2026-09-18): the controllerchange reload is for an ACCEPTED UPDATE only. A first
// install claims an uncontrolled page (sw.js `clients.claim()`), which also fires controllerchange;
// reloading then wiped a first-time visitor's half-typed form about a second after load.

type Listener = (e?: unknown) => void;

function fakeServiceWorker(controller: object | null) {
  const listeners: Record<string, Listener[]> = {};
  return {
    controller,
    register: vi.fn().mockResolvedValue({ waiting: null, addEventListener: vi.fn() }),
    addEventListener: (type: string, cb: Listener) => { (listeners[type] ??= []).push(cb); },
    fire: (type: string) => (listeners[type] ?? []).forEach((cb) => cb()),
  };
}

describe('registerServiceWorker — the controllerchange reload', () => {
  let reload: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    vi.resetModules();
    vi.stubEnv('PROD', true);
    reload = vi.fn();
    Object.defineProperty(window, 'location', { value: { ...window.location, reload }, configurable: true });
  });
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  async function boot(controller: object | null) {
    const sw = fakeServiceWorker(controller);
    Object.defineProperty(navigator, 'serviceWorker', { value: sw, configurable: true });
    // Capture THIS registration's `load` handler and call it directly: dispatching a real `load`
    // would also run the handlers earlier tests left on the shared jsdom window.
    const add = vi.spyOn(window, 'addEventListener');
    const { registerServiceWorker } = await import('../registerSW');
    registerServiceWorker();
    const onLoad = add.mock.calls.find(([type]) => type === 'load')?.[1] as () => void;
    add.mockRestore();
    onLoad();
    return sw;
  }

  it('does NOT reload on a first install (no controller before) — the visitor keeps what they typed', async () => {
    const sw = await boot(null);
    sw.fire('controllerchange');
    expect(reload).not.toHaveBeenCalled();
  });

  it('reloads exactly once when an already-controlled page switches to the accepted update', async () => {
    const sw = await boot({});
    sw.fire('controllerchange');
    sw.fire('controllerchange');
    expect(reload).toHaveBeenCalledTimes(1);
  });
});

import { vi } from 'vitest';

// DEFERRED #049 from TMP-Q6 chunk-C /review-impl LOW-5 — `@testing-library/jest-dom`
// matchers (`toBeInTheDocument`, `toBeEmptyDOMElement`, etc.) loaded
// once so React component tests under `tests/components/*.test.tsx`
// can use them without re-importing per file.
import '@testing-library/jest-dom/vitest';

// Phaser tries to detect WebGL/Canvas APIs at module load; jsdom doesn't
// have them. Tests that just need Phaser.Events.EventEmitter shape (e.g.
// EventBus contract tests) get a minimal Node-EventEmitter-backed stub.
//
// Tests that need real Phaser (rendering, scenes) should be e2e via
// Playwright, not unit tests in jsdom.

class StubEmitter {
  private readonly map = new Map<string, Set<(...args: unknown[]) => void>>();

  on(event: string, handler: (...args: unknown[]) => void): this {
    let s = this.map.get(event);
    if (!s) {
      s = new Set();
      this.map.set(event, s);
    }
    s.add(handler);
    return this;
  }

  off(event: string, handler: (...args: unknown[]) => void): this {
    this.map.get(event)?.delete(handler);
    return this;
  }

  emit(event: string, ...args: unknown[]): boolean {
    const s = this.map.get(event);
    if (!s) return false;
    for (const h of s) h(...args);
    return true;
  }

  removeAllListeners(event?: string): this {
    if (event) this.map.delete(event);
    else this.map.clear();
    return this;
  }
}

vi.mock('phaser', () => ({
  default: {
    Events: { EventEmitter: StubEmitter },
  },
  Events: { EventEmitter: StubEmitter },
}));

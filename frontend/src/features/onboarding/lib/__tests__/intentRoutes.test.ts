import { describe, it, expect } from 'vitest';
import { INTENT_CHOICES, routeForIntent } from '../intentRoutes';
import type { IntentId } from '../../types';

// C22 — the intent→surface map is the load-bearing contract (BL-15): each of the
// four intents must resolve to its OWN tailored surface + container, never a
// generic shell. A wrong route here defeats the whole cycle.

describe('intentRoutes (C22)', () => {
  it('presents the BL-15 intents incl. the work assistant (F1)', () => {
    const ids = INTENT_CHOICES.map((c) => c.id);
    expect(ids).toEqual(['write', 'world', 'translate', 'explore', 'assistant']);
  });

  it('routes Work-assistant → the assistant surface (/assistant)', () => {
    expect(routeForIntent('assistant')).toBe('/assistant');
  });

  it('routes Write → the book workspace container (/books)', () => {
    expect(routeForIntent('write')).toBe('/books');
  });

  it('routes Build-a-world → the C20/C21 world container (/worlds)', () => {
    expect(routeForIntent('world')).toBe('/worlds');
  });

  it('routes Translate → the translation surface (route-only, per-book entry)', () => {
    expect(routeForIntent('translate')).toBe('/books?intent=translate');
  });

  it('routes Explore → the read-only knowledge/graph browse surface', () => {
    expect(routeForIntent('explore')).toBe('/knowledge/projects');
  });

  it('every intent has a distinct route (no two land on the same surface)', () => {
    const routes = INTENT_CHOICES.map((c) => c.route);
    expect(new Set(routes).size).toBe(routes.length);
  });

  it('throws on an unknown intent', () => {
    expect(() => routeForIntent('nope' as IntentId)).toThrow();
  });
});

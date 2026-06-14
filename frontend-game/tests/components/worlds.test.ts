import { describe, it, expect } from 'vitest';
import { existsSync } from 'node:fs';
import { join } from 'node:path';
import { WORLDS, DEFAULT_WORLD, resolveWorld } from '@/components/globe/worlds';

describe('worlds catalog', () => {
  it('is non-empty and every entry is a well-formed /worlds/*.glb', () => {
    expect(WORLDS.length).toBeGreaterThan(0);
    for (const w of WORLDS) {
      expect(w.id).toBeTruthy();
      expect(w.label).toBeTruthy();
      expect(w.src).toMatch(/^\/worlds\/.+\.glb$/);
    }
  });

  it('has unique world ids', () => {
    const ids = WORLDS.map((w) => w.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it('resolveWorld returns the matching entry', () => {
    expect(resolveWorld(DEFAULT_WORLD.id)).toBe(DEFAULT_WORLD);
  });

  it('resolveWorld falls back to the default for an unknown or missing id', () => {
    expect(resolveWorld('does-not-exist')).toBe(DEFAULT_WORLD);
    expect(resolveWorld(undefined)).toBe(DEFAULT_WORLD);
  });

  it('DEFAULT_WORLD is the first catalog entry', () => {
    expect(WORLDS[0]).toBe(DEFAULT_WORLD);
  });

  it('every catalog .glb actually exists under public/', () => {
    // Guards the catalog↔asset link: a rename/typo would otherwise pass tests
    // and 404 at runtime (which now crashes into the viewer's error fallback).
    // vitest cwd is the frontend-game package root, so assets live at ./public.
    for (const w of WORLDS) {
      const path = join(process.cwd(), 'public', w.src);
      expect(existsSync(path), `missing asset for ${w.id}: ${path}`).toBe(true);
    }
  });
});

import { describe, expect, it, beforeEach } from 'vitest';
import { useGameStore } from '@/store/game-store';

// Reset store to defaults between tests since Zustand stores are singletons.
const INITIAL = useGameStore.getState();

describe('game-store', () => {
  beforeEach(() => {
    useGameStore.setState(INITIAL, true);
  });

  it('starts with default vitals 100/100 HP, 50/50 MP', () => {
    const s = useGameStore.getState();
    expect(s.hp).toBe(100);
    expect(s.maxHp).toBe(100);
    expect(s.mp).toBe(50);
    expect(s.maxMp).toBe(50);
  });

  it('setVitals updates hp + mp atomically', () => {
    useGameStore.getState().setVitals(75, 25);
    const s = useGameStore.getState();
    expect(s.hp).toBe(75);
    expect(s.mp).toBe(25);
    // max values unchanged
    expect(s.maxHp).toBe(100);
    expect(s.maxMp).toBe(50);
  });

  it('inventory starts empty', () => {
    expect(useGameStore.getState().inventory).toEqual([]);
  });
});

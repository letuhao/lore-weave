import { describe, expect, it, vi, beforeEach } from 'vitest';
import { Player } from '@/game/entities/Player';

// Tests for V0 cleanup additions: walkTo boundary check + queue dedup.
// We stub the Phaser scene shape minimally — Player only touches
// scene.add.sprite and scene.tweens.add in production paths.

function makeFakeScene() {
  const sprite = { x: 0, y: 0, setOrigin: vi.fn().mockReturnThis(), setDepth: vi.fn().mockReturnThis() };
  const tween = vi.fn();
  const scene = {
    add: { sprite: vi.fn().mockReturnValue(sprite) },
    tweens: { add: tween },
  };
  return { scene, sprite, tween };
}

function makePlayer(zoneWidth = 8, zoneHeight = 8) {
  const fixture = makeFakeScene();
  const p = new Player({
    scene: fixture.scene as unknown as Phaser.Scene,
    startTile: { x: 4, y: 4 },
    offsetX: 0,
    offsetY: 0,
    zoneWidth,
    zoneHeight,
  });
  return { player: p, ...fixture };
}

describe('Player.isInBounds', () => {
  it('accepts tiles inside the 8×8 zone', () => {
    const { player } = makePlayer();
    expect(player.isInBounds({ x: 0, y: 0 })).toBe(true);
    expect(player.isInBounds({ x: 7, y: 7 })).toBe(true);
    expect(player.isInBounds({ x: 4, y: 4 })).toBe(true);
  });

  it('rejects negative coordinates', () => {
    const { player } = makePlayer();
    expect(player.isInBounds({ x: -1, y: 4 })).toBe(false);
    expect(player.isInBounds({ x: 4, y: -1 })).toBe(false);
    expect(player.isInBounds({ x: -1, y: -1 })).toBe(false);
  });

  it('rejects coordinates at or past zone size', () => {
    const { player } = makePlayer(8, 8);
    expect(player.isInBounds({ x: 8, y: 4 })).toBe(false);
    expect(player.isInBounds({ x: 4, y: 8 })).toBe(false);
    expect(player.isInBounds({ x: 100, y: 100 })).toBe(false);
  });
});

describe('Player.walkTo', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('schedules a tween for an in-bounds target', () => {
    const { player, tween } = makePlayer();
    player.walkTo({ x: 5, y: 5 });
    expect(tween).toHaveBeenCalledTimes(1);
  });

  it('silently drops out-of-bounds targets', () => {
    const { player, tween } = makePlayer();
    player.walkTo({ x: -1, y: 0 });
    player.walkTo({ x: 100, y: 100 });
    expect(tween).not.toHaveBeenCalled();
  });

  it('dedupes spam-clicks on the same target tile', () => {
    const { player, tween } = makePlayer();
    player.walkTo({ x: 5, y: 5 });
    player.walkTo({ x: 5, y: 5 });
    player.walkTo({ x: 5, y: 5 });
    // First call starts a tween; subsequent dedupe because the tile is
    // already the last in queue (or current target while walking).
    expect(tween).toHaveBeenCalledTimes(1);
  });
});

import Phaser from 'phaser';
import { EventBus, type PlayerActionEvent } from '../EventBus';
import { worldToScreen } from '../../lib/iso-math';
import { DEFAULT_ZONE_HEIGHT, DEFAULT_ZONE_WIDTH } from '../config/constants';
import { Player } from '../entities/Player';
import { InputSystem } from '../systems/input-system';

// V0 World scene: renders a 32×32 iso grass field from the Kenney
// CC0 isometric-tiles-landscape pack and spawns a Player sprite at
// the center. Clicking any tile walks the Player to it (turn-based +
// idle MMO model per spec §1 #6).
//
// Session E+ replaces the static grass field with a server-fetched
// tilemap (via useTilemapHealth → tilemap-service /tilemaps/render).

export class WorldScene extends Phaser.Scene {
  private player: Player | null = null;
  private offsetX = 0;
  private offsetY = 0;
  private moveHandler: ((event: PlayerActionEvent) => void) | null = null;

  constructor() {
    super({ key: 'WorldScene' });
  }

  create(): void {
    EventBus.emit('scene-ready', { key: 'WorldScene' });

    // Use scale.gameSize (stable across scene transitions) instead of
    // cam.midPoint (which is a world-coord vector and varies with camera
    // scroll). For V0 single-zone demo this is correct; Session E+ uses
    // camera follow + viewport-relative offset.
    const viewW = this.scale.gameSize.width;
    const viewH = this.scale.gameSize.height;

    // Center the zone diamond in the viewport.
    const halfW = DEFAULT_ZONE_WIDTH / 2;
    const halfH = DEFAULT_ZONE_HEIGHT / 2;
    const originOffset = worldToScreen({ x: halfW, y: halfH });
    this.offsetX = viewW / 2 - originOffset.x;
    this.offsetY = viewH / 2 - originOffset.y;

    // Render the Kenney grass cubes. setOrigin(0.5, 0) anchors the
    // top diamond at the iso grid cell — the cube extends downward
    // visually, producing the stacked-cube look natural to this pack.
    for (let y = 0; y < DEFAULT_ZONE_HEIGHT; y++) {
      for (let x = 0; x < DEFAULT_ZONE_WIDTH; x++) {
        const s = worldToScreen({ x, y });
        this.add
          .image(this.offsetX + s.x, this.offsetY + s.y, 'tile-grass')
          .setOrigin(0.5, 0);
      }
    }

    // Spawn the Player at the zone center.
    this.player = new Player({
      scene: this,
      startTile: { x: Math.floor(halfW), y: Math.floor(halfH) },
      offsetX: this.offsetX,
      offsetY: this.offsetY,
    });

    // Attach input (canvas pointer → tile coords → move event).
    InputSystem.attach({ scene: this, offsetX: this.offsetX, offsetY: this.offsetY });

    // Listen for move actions and drive the Player.
    this.moveHandler = (event: PlayerActionEvent) => {
      if (event.kind === 'move' && event.target && this.player) {
        this.player.walkTo(event.target);
      }
    };
    EventBus.on('player-action', this.moveHandler);

    // Launch the optional Phaser-side HUD scene running in parallel.
    this.scene.launch('HudScene');
  }

  shutdown(): void {
    if (this.moveHandler) {
      EventBus.off('player-action', this.moveHandler);
      this.moveHandler = null;
    }
  }
}

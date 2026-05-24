import Phaser from 'phaser';
import { ValidationScene } from './scenes/ValidationScene';

// Phaser 4.1.0 ESM bundling shim — required for SpriteGPULayer and any
// other internal code path that references the bare `Phaser` global.
// The webpack-bundled ESM build exposes Phaser as the default export
// but internal code (e.g. `new Phaser.Structs.Map()` at dist line 88604,
// `texture instanceof Phaser.Textures.Texture` at lines 33884/34948/34969,
// etc.) still uses the global identifier. Without this shim, those code
// paths throw "Phaser is not defined" at runtime even though the import
// succeeds. Track upstream fix; remove this shim once Phaser ESM
// bundling is clean (likely a 4.x patch release).
// See: src/game/scenes/ValidationScene.ts header comment for details.
(globalThis as { Phaser?: typeof Phaser }).Phaser = Phaser;

// Phaser.Game factory. Called from PhaserGame.tsx with the React-managed
// container element. WebGL2 is REQUIRED for Phaser 4 GPU layers; no
// canvas-2D fallback for V0 per spec §11.1 (Phaser 3 LTS is the fallback
// if the gate fails).

export function startGame(parent: HTMLElement): Phaser.Game {
  const config: Phaser.Types.Core.GameConfig = {
    type: Phaser.WEBGL,
    parent,
    width: window.innerWidth,
    height: window.innerHeight,
    backgroundColor: '#0f172a',
    scale: {
      mode: Phaser.Scale.RESIZE,
      autoCenter: Phaser.Scale.CENTER_BOTH,
    },
    render: {
      pixelArt: false,
      antialias: true,
    },
    scene: [ValidationScene],
  };

  return new Phaser.Game(config);
}

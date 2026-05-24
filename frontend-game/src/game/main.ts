import Phaser from 'phaser';
import { BootScene } from './scenes/BootScene';
import { PreloaderScene } from './scenes/PreloaderScene';
import { MainMenuScene } from './scenes/MainMenuScene';
import { WorldScene } from './scenes/WorldScene';
import { HudScene } from './scenes/HudScene';

// Phaser 4.1.0 ESM bundling shim — required for SpriteGPULayer and any
// other internal code path that references the bare `Phaser` global.
// The webpack-bundled ESM build exposes Phaser as the default export
// but internal code (e.g. `new Phaser.Structs.Map()` at dist line 88604,
// `texture instanceof Phaser.Textures.Texture` at lines 33884/34948/34969)
// still uses the global identifier. Without this shim, those code paths
// throw "Phaser is not defined" at runtime even though the import
// succeeds. Track upstream fix; remove this shim once Phaser ESM
// bundling is clean (likely a 4.x patch release).
// See: memory/project_phaser4_quirks.md + Session C Phase 1 commit msg.
(globalThis as { Phaser?: typeof Phaser }).Phaser = Phaser;

// Phaser.Game factory. Called from PhaserGame.tsx with the React-managed
// container element. Scene chain (spec §9 pattern #1):
//   Boot → Preloader → MainMenu → World (HudScene parallel)

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
    scene: [BootScene, PreloaderScene, MainMenuScene, WorldScene, HudScene],
  };

  return new Phaser.Game(config);
}

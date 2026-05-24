import Phaser from 'phaser';
import { EventBus } from '../EventBus';

// Phaser 4 production-readiness validation gate (spec §11.1).
//
// Runs four checks and emits results via EventBus so the React DOM
// overlay can render pass/fail. Designed to NOT crash the scene if a
// Phaser 4 API turns out to be different than expected — instead, the
// failure surfaces as an error event so we know exactly what to fix
// (or whether to fall back to Phaser 3 LTS per spec §11.1).
//
// KEY FINDING from 2026-05-24 research of phaser@4.1.0 source:
// `TilemapGPULayer` is **orthographic-only** (see CHANGELOG-v4.0.0.md
// line 549: "Orthographic tilemaps only -- not suitable for isometric
// or hexagonal maps"). Our game uses iso 2:1 dimetric per spec §1 #10,
// so TilemapGPULayer is N/A for us. Gate #2 is therefore marked N/A
// rather than required-pass. Regular TilemapLayer handles iso fine.
//
// `SpriteGPULayer` factory signature: `this.add.spriteGPULayer(texture, size?)`
// followed by `layer.addMember({ x, y, ... })` per member.

const TILE_SIZE = 32;
const TILEMAP_WIDTH = 64;
const TILEMAP_HEIGHT = 64;
const SPRITE_COUNT = 100;

interface MovingSprite {
  x: number;
  y: number;
  phase: number;
  speed: number;
  cx: number;
  cy: number;
  radius: number;
}

export class ValidationScene extends Phaser.Scene {
  private fpsTimer = 0;
  private movers: MovingSprite[] = [];
  private gpuLayer: Phaser.GameObjects.SpriteGPULayer | null = null;

  constructor() {
    super({ key: 'ValidationScene' });
  }

  preload(): void {
    // Generate a 32×32 tile texture programmatically (no asset file).
    const g = this.add.graphics();
    g.fillStyle(0x4f46e5, 1);
    g.fillRect(0, 0, TILE_SIZE, TILE_SIZE);
    g.lineStyle(2, 0x1e1b4b, 1);
    g.strokeRect(0, 0, TILE_SIZE, TILE_SIZE);
    g.generateTexture('stub-tile', TILE_SIZE, TILE_SIZE);
    g.destroy();

    // Generate a 16×16 sprite texture.
    const s = this.add.graphics();
    s.fillStyle(0xf59e0b, 1);
    s.fillCircle(8, 8, 7);
    s.generateTexture('stub-sprite', 16, 16);
    s.destroy();
  }

  create(): void {
    this.checkWebGL2();
    this.renderTilemap();
    this.checkSpriteGPULayer();
  }

  private checkWebGL2(): void {
    // Phaser 4 by design requests a WebGL 1.0 context (see phaser.esm.js
    // line 186435: `canvas.getContext('webgl', config.contextCreation)`)
    // and polyfills WebGL 2 features via extensions: ANGLE_instanced_arrays,
    // OES_vertex_array_object, OES_standard_derivatives. So a WebGL1
    // context with these extensions is what Phaser 4 expects and works
    // with — NOT a fallback or browser issue.
    //
    // The original "expected WebGL 2.0" check was incorrect: even in real
    // Chrome (which supports WebGL2 natively), Phaser will still create a
    // WebGL1 context by default. To force WebGL2 you'd have to
    // pre-create the context yourself and pass it via game config.context.
    //
    // Correct gate: renderer is WebGLRenderer + the WebGL2-equivalent
    // extensions Phaser needs were obtained.
    try {
      const renderer = this.game.renderer;
      if (!(renderer instanceof Phaser.Renderer.WebGL.WebGLRenderer)) {
        EventBus.emit('validation', { kind: 'webgl', ok: false });
        EventBus.emit('validation', {
          kind: 'error',
          message: 'Renderer is not WebGLRenderer (canvas-2D fallback active).',
        });
        return;
      }
      const gl = renderer.gl;
      const version = gl.getParameter(gl.VERSION) as string;
      const requiredExts = [
        'ANGLE_instanced_arrays',
        'OES_vertex_array_object',
        'OES_standard_derivatives',
      ];
      const supported = gl.getSupportedExtensions() ?? [];
      const isWebGL2Native = typeof version === 'string' && version.toLowerCase().includes('webgl 2');
      const missing = isWebGL2Native
        ? []
        : requiredExts.filter((e) => !supported.includes(e));
      const ok = isWebGL2Native || missing.length === 0;
      EventBus.emit('validation', { kind: 'webgl', ok });
      if (!ok) {
        EventBus.emit('validation', {
          kind: 'error',
          message: `${version} present but missing required WebGL2-equivalent extensions: ${missing.join(', ')}`,
        });
      }
    } catch (err) {
      EventBus.emit('validation', { kind: 'webgl', ok: false });
      EventBus.emit('validation', {
        kind: 'error',
        message: `WebGL check threw: ${(err as Error).message}`,
      });
    }
  }

  private renderTilemap(): void {
    // Regular TilemapLayer — TilemapGPULayer is orthographic-only and
    // our game is iso 2:1 dimetric (spec §1 #10), so GPU layer is N/A.
    // We still render the tilemap to confirm the standard tile path
    // works under our Vite + ESM + TS-strict setup.
    try {
      const data: number[][] = [];
      for (let y = 0; y < TILEMAP_HEIGHT; y++) {
        const row: number[] = [];
        for (let x = 0; x < TILEMAP_WIDTH; x++) {
          row.push((x + y) % 4 === 0 ? 1 : 0);
        }
        data.push(row);
      }
      const map = this.make.tilemap({
        data,
        tileWidth: TILE_SIZE,
        tileHeight: TILE_SIZE,
      });
      const tileset = map.addTilesetImage('stub-tile', 'stub-tile', TILE_SIZE, TILE_SIZE);
      if (!tileset) {
        EventBus.emit('validation', { kind: 'tilemap', ok: false });
        EventBus.emit('validation', {
          kind: 'error',
          message: 'addTilesetImage returned null — texture not registered.',
        });
        return;
      }
      const layer = map.createLayer(0, tileset, 0, 0);
      EventBus.emit('validation', { kind: 'tilemap', ok: layer !== null });
      if (!layer) {
        EventBus.emit('validation', {
          kind: 'error',
          message: 'createLayer returned null.',
        });
      }
    } catch (err) {
      EventBus.emit('validation', { kind: 'tilemap', ok: false });
      EventBus.emit('validation', {
        kind: 'error',
        message: `Tilemap render threw: ${(err as Error).message}`,
      });
    }
  }

  private checkSpriteGPULayer(): void {
    // Correct Phaser 4 signature per phaser.d.ts:15354
    //   spriteGPULayer(texture, size?)  →  SpriteGPULayer instance
    //   .addMember({ x, y, scaleX, scaleY, ... })  per member
    //
    // Population strategy per CHANGELOG-v4.0.0.md line 506: reuse a
    // single mutable config object across addMember calls to avoid
    // GC pressure when adding many members.
    try {
      const layer = this.add.spriteGPULayer('stub-sprite', SPRITE_COUNT);
      this.gpuLayer = layer;

      const config: Partial<Phaser.Types.GameObjects.SpriteGPULayer.Member> = {
        scaleX: 1,
        scaleY: 1,
      };
      for (let i = 0; i < SPRITE_COUNT; i++) {
        const cx = (i % 10) * 80 + 100;
        const cy = Math.floor(i / 10) * 80 + 100;
        config.x = cx;
        config.y = cy;
        layer.addMember(config);
        this.movers.push({
          x: cx,
          y: cy,
          phase: Math.random() * Math.PI * 2,
          speed: 0.5 + Math.random() * 1.5,
          cx,
          cy,
          radius: 20 + Math.random() * 20,
        });
      }
      EventBus.emit('validation', { kind: 'sprite', ok: true });
    } catch (err) {
      EventBus.emit('validation', { kind: 'sprite', ok: false });
      EventBus.emit('validation', {
        kind: 'error',
        message: `SpriteGPULayer threw: ${(err as Error).message}`,
      });
      // Fallback: regular sprites so the screen isn't empty
      for (let i = 0; i < SPRITE_COUNT; i++) {
        const cx = (i % 10) * 80 + 100;
        const cy = Math.floor(i / 10) * 80 + 100;
        this.add.sprite(cx, cy, 'stub-sprite');
        this.movers.push({
          x: cx,
          y: cy,
          phase: Math.random() * Math.PI * 2,
          speed: 0.5 + Math.random() * 1.5,
          cx,
          cy,
          radius: 20 + Math.random() * 20,
        });
      }
    }
  }

  update(_time: number, delta: number): void {
    // Animate the 100 sprites in a circular orbit.
    if (this.gpuLayer) {
      const config: Partial<Phaser.Types.GameObjects.SpriteGPULayer.Member> = {};
      for (let i = 0; i < this.movers.length; i++) {
        const m = this.movers[i];
        if (!m) continue;
        m.phase += (m.speed * delta) / 1000;
        config.x = m.cx + Math.cos(m.phase) * m.radius;
        config.y = m.cy + Math.sin(m.phase) * m.radius;
        this.gpuLayer.editMember(i, config);
      }
    }

    // Emit FPS once per second.
    this.fpsTimer += delta;
    if (this.fpsTimer >= 1000) {
      this.fpsTimer = 0;
      EventBus.emit('validation', { kind: 'fps', value: this.game.loop.actualFps });
    }
  }
}

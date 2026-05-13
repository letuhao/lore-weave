import Phaser from 'phaser';
import { TilemapScene, type SelectInfo } from './scenes/TilemapScene';
import { composeTileMap } from './generators/tilemap';
import { KINGDOM_DEFAULT } from './data/skeleton';
import {
  TERRAIN_KIND_ORDER,
  indexToTerrain,
  type TileMapSkeleton,
  type TileMapView,
} from './data/types';
import { TERRAIN_COLOR } from './render/colors';
import { Minimap } from './render/minimap';
import { LlmDialog } from './ui/llm_dialog';

// ─── State ────────────────────────────────────────────────────────────────

let view: TileMapView;
let scene: TilemapScene;
let game: Phaser.Game;
let minimap: Minimap | null = null;
let llmDialog: LlmDialog | null = null;
let activeSkeleton: TileMapSkeleton = KINGDOM_DEFAULT;

// ─── DOM helpers ──────────────────────────────────────────────────────────

const $ = <T extends HTMLElement>(id: string): T => {
  const el = document.getElementById(id) as T | null;
  if (!el) throw new Error(`Missing element #${id}`);
  return el;
};

function setStatus(msg: string): void {
  $<HTMLElement>('status').textContent = msg;
}

function getSeedFromInput(): number {
  const v = parseInt(($<HTMLInputElement>('seedInput')).value || '42', 10);
  return Number.isFinite(v) && v >= 0 ? v : 42;
}

// ─── Pipeline orchestration ──────────────────────────────────────────────

function generate(seed: number): void {
  const t0 = performance.now();
  view = composeTileMap(activeSkeleton, seed, 'continent:nam_thien', 'Continent');
  const elapsedMs = (performance.now() - t0).toFixed(1);

  if (scene) {
    scene.rebuild(view);
  }
  if (minimap) {
    minimap.rebuild(view);
  }
  updateStats(elapsedMs);
  updateTerrainDist();
  setStatus(
    `seed=${seed} · skeleton=${activeSkeleton.skeleton_id} · ` +
      `${view.grid_size.width}×${view.grid_size.height} · ` +
      `${view.cell_placements.length} cells · ${view.roads.length} roads · ${elapsedMs}ms · ` +
      `generated ${view.generated_at}`,
  );
}

function applyLlmSkeleton(skeleton: TileMapSkeleton): void {
  activeSkeleton = skeleton;
  setStatus(`Applied LLM-generated skeleton: ${skeleton.skeleton_id}`);
  generate(getSeedFromInput());
}

function updateStats(elapsedMs: string): void {
  $<HTMLElement>('stats').innerHTML = `
    <div>grid: <code>${view.grid_size.width}×${view.grid_size.height}</code> = ${view.terrain_layer.length} tiles</div>
    <div>skeleton: <code>${view.skeleton_id}</code></div>
    <div>seed: <code>${view.procedural_seed}</code></div>
    <div>cells: <code>${view.cell_placements.length}</code></div>
    <div>landmarks: <code>${view.object_placements.length}</code></div>
    <div>roads: <code>${view.roads.length}</code></div>
    <div>L3 source: <code>${view.layer3_source.kind}</code></div>
    <div>gen time: <code>${elapsedMs}ms</code></div>
  `;
}

function updateTerrainDist(): void {
  const counts = new Map<number, number>();
  for (const idx of view.terrain_layer) {
    counts.set(idx, (counts.get(idx) ?? 0) + 1);
  }
  const total = view.terrain_layer.length;
  const sorted = [...counts.entries()].sort((a, b) => b[1] - a[1]);

  const html = sorted
    .map(([idx, count]) => {
      const kind = indexToTerrain(idx);
      const pct = ((count / total) * 100).toFixed(1);
      const color = TERRAIN_COLOR[kind];
      const hexColor = `#${color.toString(16).padStart(6, '0')}`;
      return `
        <div class="terrain-row">
          <span class="terrain-swatch" style="background: ${hexColor}"></span>
          <span class="terrain-name">${kind}</span>
          <span class="terrain-pct">${pct}% (${count})</span>
        </div>
      `;
    })
    .join('');
  $<HTMLElement>('terrain-dist').innerHTML = html;
}

function showSelected(info: SelectInfo): void {
  const div = $<HTMLElement>('info');
  div.innerHTML = `
    <div><strong>${info.name}</strong></div>
    <div>kind: <code>${info.kind}</code></div>
    <div>id: <code>${info.channel_id}</code></div>
    <div>position: <code>(${info.position.x}, ${info.position.y})</code></div>
    <div class="hint">→ would drill into ${info.category === 'cell' ? 'cell view (PF_001 + CSC_001)' : 'landmark detail panel'}</div>
  `;
}

function downloadJson(): void {
  const blob = new Blob([JSON.stringify(view, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `tilemap_view_seed_${view.procedural_seed}.json`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
  setStatus(`exported tilemap_view_seed_${view.procedural_seed}.json`);
}

// ─── Init ─────────────────────────────────────────────────────────────────

function calcGameSize(): { w: number; h: number } {
  const sidebar = 320;
  const topbar = 50;
  const status = 28;
  return {
    w: Math.max(400, window.innerWidth - sidebar),
    h: Math.max(300, window.innerHeight - topbar - status),
  };
}

function init(): void {
  // First gen — populates `view` before Phaser starts
  generate(getSeedFromInput());

  const { w, h } = calcGameSize();
  game = new Phaser.Game({
    type: Phaser.AUTO,
    width: w,
    height: h,
    parent: 'game-container',
    backgroundColor: '#0d1117',
    scale: {
      mode: Phaser.Scale.RESIZE,
      autoCenter: Phaser.Scale.NO_CENTER,
    },
    render: {
      pixelArt: false,
      antialias: true,
    },
  });

  scene = new TilemapScene();
  game.scene.add('TilemapScene', scene, true, {
    view,
    onSelect: showSelected,
  });

  // Minimap overlay (DOM canvas; positioned absolute top-right of #game-container)
  const gameContainer = $<HTMLElement>('game-container');
  minimap = new Minimap(view, gameContainer);
  minimap.setOnJump((worldX, worldY) => {
    if (!scene) return;
    scene.cameras.main.centerOn(worldX, worldY);
  });

  // Update minimap viewport rect on camera scroll/zoom (every frame is overkill;
  // throttle via Phaser scene update if it becomes a perf issue)
  setInterval(() => {
    if (!scene || !minimap) return;
    const cam = scene.cameras.main;
    const w = cam.width / cam.zoom;
    const h = cam.height / cam.zoom;
    minimap.setViewportRect(cam.scrollX, cam.scrollY, w, h);
  }, 100);

  // ─── UI bindings ────────────────────────────────────────────────────────

  $<HTMLButtonElement>('regenBtn').addEventListener('click', () => {
    generate(getSeedFromInput());
  });

  $<HTMLButtonElement>('randomBtn').addEventListener('click', () => {
    const r = Math.floor(Math.random() * 1_000_000);
    $<HTMLInputElement>('seedInput').value = String(r);
    generate(r);
  });

  $<HTMLButtonElement>('zoomInBtn').addEventListener('click', () => {
    if (scene) scene.zoomBy(0.25);
  });

  $<HTMLButtonElement>('zoomOutBtn').addEventListener('click', () => {
    if (scene) scene.zoomBy(-0.25);
  });

  $<HTMLButtonElement>('exportBtn').addEventListener('click', downloadJson);

  // LLM dialog — lazy-init on first click to avoid loading until needed
  $<HTMLButtonElement>('llmBtn').addEventListener('click', () => {
    if (!llmDialog) llmDialog = new LlmDialog();
    llmDialog.open((skeleton, attempts, tokens) => {
      applyLlmSkeleton(skeleton);
      const tokensStr = tokens ? ` · ${tokens} tokens` : '';
      setStatus(
        `LLM skeleton applied: ${skeleton.skeleton_id} (${attempts.length} attempts${tokensStr})`,
      );
    });
  });

  $<HTMLInputElement>('seedInput').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') generate(getSeedFromInput());
  });

  window.addEventListener('resize', () => {
    const { w, h } = calcGameSize();
    if (game) game.scale.resize(w, h);
  });
}

// Wait for DOM ready (Vite injects script at end of body so DOM is ready)
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}

// ─── Type assertion: confirm TERRAIN_KIND_ORDER matches color palette ─────
// Compile-time check — ensures any new TerrainKind has a color entry
type _AllTerrainsHaveColor = (typeof TERRAIN_KIND_ORDER)[number] extends keyof typeof TERRAIN_COLOR
  ? true
  : never;
const _check: _AllTerrainsHaveColor = true;
void _check;

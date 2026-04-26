# Tilemap World View — PoC v1

PoC validating SPIKE_03 architecture: HOMM3-style camera-rendered tilemap world view sitting alongside MAP_001 (logical graph) and CSC_001 (cell interior 16×16).

**Spec doc:** [`docs/03_planning/LLM_MMO_RPG/features/_spikes/SPIKE_03_tilemap_world_view.md`](../../docs/03_planning/LLM_MMO_RPG/features/_spikes/SPIKE_03_tilemap_world_view.md)

---

## Stack

- **Vite** + **TypeScript** + **Phaser 3.80** (game engine)
- **Vitest** (determinism tests)
- Pure Phaser (no React wrapper) — wrap in React when porting to `frontend/src/features/tilemap/`

---

## Quick start

```bash
cd poc/tilemap_world_view
npm install
npm run dev
```

Open `http://localhost:5174` in browser.

```bash
npm test          # determinism + validator schema tests (32 tests)
npm run typecheck # tsc --noEmit
npm run build     # production bundle
npm run preview   # serve production bundle
```

---

## Controls

- **Drag** on map: pan camera
- **Mouse wheel**: zoom in/out (zooms toward pointer)
- **Click cell/landmark**: show info in sidebar
- **Click on minimap**: jump main camera to that location
- **Toolbar**:
  - `seed` input + Enter or `Regen`: rebuild tilemap with seed
  - `Random`: pick new random seed
  - `+` / `−`: zoom buttons
  - `Export JSON`: download `tilemap_view_seed_<N>.json` matching aggregate schema
  - `⚡ LLM`: open prompt dialog → generate skeleton via local LLM (see LLM section below)

---

## Architecture (4-layer composition)

| Layer | Module | LLM cost | Status |
|---|---|---|---|
| **L1** Hand-authored skeleton | [`src/data/skeleton.ts`](src/data/skeleton.ts) | 0 | ✅ PoC v1 |
| **L2** Procedural terrain | [`src/generators/terrain.ts`](src/generators/terrain.ts) | 0 | ✅ PoC v1 |
| **L2** Road A\* pathfinding | [`src/generators/roads.ts`](src/generators/roads.ts) | 0 | ✅ PoC v1 |
| **L3** LLM zone classifier | (deferred) | ~3K tokens | 📦 V2 |
| **L4** LLM regional narration | (deferred) | ~1K tokens | 📦 V2 |

**Why this split:** matches CSC_001 v3→v4 architectural lesson — LLM is a **zone classifier**, not a spatial generator. Engine code generates grid; LLM picks "monster lair → forest_west" (categorical decision). Bounded LLM cost regardless of grid size.

---

## Project layout

```
poc/tilemap_world_view/
├── package.json
├── vite.config.ts
├── tsconfig.json
├── index.html
├── README.md (this file)
├── public/
│   └── assets/                        # optional asset packs (see below)
├── src/
│   ├── main.ts                        # entry point + UI bindings
│   ├── data/
│   │   ├── types.ts                   # TileMapView aggregate types (mirrors SPIKE_03 §4)
│   │   └── skeleton.ts                # L1 hardcoded "kingdom_default"
│   ├── generators/                    # PORTABLE TO RUST (services/world-service)
│   │   ├── prng.ts                    # Mulberry32 + hash2D
│   │   ├── noise.ts                   # value-noise 2D + fBm
│   │   ├── terrain.ts                 # L2 algorithm: skeleton + seed → tiles[]
│   │   ├── roads.ts                   # A* pathfinding with terrain-cost matrix
│   │   └── tilemap.ts                 # composeTileMap() entry point
│   ├── render/
│   │   └── colors.ts                  # terrain palette + emoji map
│   ├── scenes/
│   │   └── TilemapScene.ts            # Phaser scene: tile + road + object render
│   └── ui/
│       └── styles.css                 # GitHub-dark theme matching MAP_GUI demos
└── tests/
    └── generators.test.ts             # determinism + schema tests (Vitest)
```

---

## Reusability mapping (per SPIKE_03 reusability claim)

When TMP_001 graduates to a foundation feature, code ports as follows:

| PoC module | Production target |
|---|---|
| `src/generators/prng.ts` + `noise.ts` | Port TS → Rust at `services/world-service/src/tilemap/` (use `rand_chacha::ChaCha8Rng` to match CSC_001 §5.2) |
| `src/generators/terrain.ts` + `roads.ts` + `tilemap.ts` | Port TS → Rust; same algorithms, native types |
| `src/data/types.ts` | Mirror in `contracts/api/tilemap/` OpenAPI schema (request/response DTOs) |
| `src/scenes/TilemapScene.ts` + `src/render/*` | Lift to `frontend/src/features/tilemap/scenes/`; wrap Phaser game in React component |
| `src/data/skeleton.ts` (kingdom_default) | First entry in production skeleton library; per-genre packs (wuxia/scifi/modern) added V2 |
| `src/ui/styles.css` | Replace with Tailwind + shadcn tokens (frontend/) |
| `tests/generators.test.ts` | Promote to `services/world-service/tests/` Rust property tests; enforce determinism in CI per EVT-A9 |

---

## Asset strategy (PoC v2 ships Kenney pack 2026-04-27)

PoC v2 ships **Kenney Roguelike RPG Pack** (CC0) directly in `public/assets/`:
- `kenney_roguelike_sheet.png` — 968×526 spritesheet, 16×16 tiles + 1px margin (~95KB)
- `kenney_LICENSE.txt` — CC0 license verbatim
- `kenney_sample.png` — preview reference (used to calibrate sprite indices)

**Hybrid asset loader** in [`src/scenes/TilemapScene.ts`](src/scenes/TilemapScene.ts):
- If spritesheet loads → use Kenney sprites for decorations + cell/landmark objects
- If load fails → graceful fallback to colored squares + emoji (PoC v1 behavior)

**Sprite indices** ([`src/render/kenney_atlas.ts`](src/render/kenney_atlas.ts)):
- Decoration tiles (trees / flowers / rocks / mushrooms / lily pads) keyed per terrain
- Cell anchor sprites (capital, fortress, temple, tavern, port, cell, cave)
- Landmark sprites (Treasure, MonsterLair, Ruin, Mine, etc.)
- **All indices are TUNABLE** — if a sprite shows wrong, edit `kenney_atlas.ts` (col, row) values; sample at `public/assets/kenney_sample.png` shows expected look

### Other free packs supported (drop-in replacement)

If you want to swap to a different style, replace the Kenney sheet + edit `kenney_atlas.ts` indices:

**CC0 (no attribution required):**
- **Kenney Tiny Town** (16×16) — https://kenney.nl/assets/tiny-town
- **Kenney 1-Bit Pack** (16×16) — https://kenney.nl/assets/1-bit-pack

**CC-BY (attribution required):**
- **Pixel Art Top Down - Basic** by Cainos (itch.io)
- **Tiny World 16x16** community packs (itch.io)

V2 production: per-genre commissioned art OR Kenney/CC0 packs as defaults.

---

## Determinism (per EVT-A9)

Replay-determinism is a **hard invariant** for the production aggregate:

> `composeTileMap(skeleton, seed, _, _).terrain_layer` MUST equal itself across calls

Tested in [`tests/generators.test.ts`](tests/generators.test.ts):
- PRNG (Mulberry32) determinism
- hash2D pure function
- Value noise determinism
- L2 terrain determinism
- L2 road determinism
- Full composeTileMap determinism (modulo timestamp)
- JSON round-trip equivalence

When porting to Rust, replace Mulberry32 with ChaCha8 — but determinism property MUST hold across implementations.

---

## Demo data — `kingdom_default` skeleton

64×64 fantasy continent "Nam Thiên" with:

- **7 terrain zones**: northern mountain, foothill transition, central plain, western forest, eastern grass, southern lake, southern coast
- **7 cell anchors**: Kinh Đô (capital), Bắc Sơn Thái (fortress), Tây Vân Viện (temple), Đông Phương Lâu (tavern), Nam Hải Cảng (port), Tây Thị Quán + Yên Vũ Lâu (cells from SPIKE_01)
- **7 landmarks**: peaks, lake, ruin, monster lair, treasure, temple, mine
- **6 road connections**: highways + paths + trade routes (A\* generated)

Genre flavor: wuxia/xianxia leaning — Vietnamese display names. Easy to swap for sci-fi or modern by editing one file.

---

## Known PoC v1 limitations

| Limitation | V1+30d / V2 unblock |
|---|---|
| No sprite atlas loader | V1+30d: hybrid loader detects `public/assets/` |
| No auto-tile transitions (Wang-style) | V1+30d cosmetic |
| No rivers (only roads) | V1+30d (reuse A* with downhill flow) |
| No fog-of-war | V1+30d (depends on MAP-D10 unblock) |
| No mobile fallback | V2 (auto-detect → MAP_001 SVG) |
| No L3 LLM zones | V2 |
| No L4 LLM narration | V2 |
| Click cell does NOT actually drill into CSC_001 | Production wiring; PoC just shows toast |

---

## How to verify PoC success

Per SPIKE_03 §7 success criteria:

- [ ] (a) `npm install` completes without error
- [ ] (b) `npm run dev` boots; HMR works on edit
- [ ] (c) Camera pan/zoom feels natural; 60fps target on 64×64 grid
- [ ] (d) Regenerate produces visually distinct maps from different seeds
- [ ] (e) Export JSON output matches SPIKE_03 §4 aggregate shape
- [ ] (f) `npm test` passes — all determinism tests green
- [ ] (g) `npm run build` produces bundle < 2MB

---

## LLM skeleton generation (PoC v3)

Click `⚡ LLM` in toolbar → modal dialog → write natural-language prompt → engine calls local LLM via lmstudio → validates response → applies to map.

### Setup lmstudio

1. Install [lmstudio](https://lmstudio.ai/)
2. Download a Qwen 3 model — recommended: **Qwen 3 14B Instruct** or **Qwen 3 32B Instruct** (smaller models like 7B may struggle with structured output)
3. Open lmstudio → Local Server tab → Load model → Start server (default port 1234)
4. Ensure "Cross-Origin-Resource-Sharing (CORS)" toggle is ON in lmstudio settings (or just use Vite proxy — see below)
5. Restart `npm run dev` — Vite proxies `/api/llm/*` → `http://localhost:1234/v1/*`

Override endpoint via `.env.local` at `poc/tilemap_world_view/.env.local`:
```
VITE_LLM_ENDPOINT=http://localhost:1234
```

### Architecture (4-layer composition with LLM)

L1 here is now hybrid:
- **L1.a hand-authored** (`KINGDOM_DEFAULT` in `data/skeleton.ts`) — default ships with PoC
- **L1.b LLM-generated** (new V3) — user prompt → JSON skeleton via Qwen → validated → activated

L2/L3/L4 unchanged (engine procedural; L3/L4 V2 deferred).

### Prompt example

```
Tạo skeleton cho 1 sci-fi star sector 64×64. Trung tâm là 1 hành tinh thủ phủ
phát triển; có 4 trạm khai khoáng quanh; vành đai tiểu hành tinh phía bắc;
nebula phía nam; 1 trạm thương mại đông; 1 hangar quân sự tây. Roads connect
tất cả tới capital. 4 landmarks: 1 chiến hạm cổ đắm, 1 mỏ titanium, 1 hố sao
sụp, 1 trạm sửa chữa.
```

LLM should output ~1000-1500 token JSON skeleton. With Qwen 3 14B local: ~10-30s per call. With Qwen 3 32B: ~30-90s.

### Reliability — 3-retry feedback loop

Engine validates LLM output against schema + semantic rules:
- Required fields present
- TerrainKind / CellKind / RoadKind enums valid
- Positions in 0..63 bounds
- biome_weights sum to ~1.0
- All cell channel_ids prefixed `cell:` and snake_case
- All landmark object_ids prefixed `landmark:`
- Road graph forms connected component from capital (Town/District tier)
- No duplicate ids

If validation fails → retry with errors as user message → LLM self-corrects → max 3 attempts.

Tested validator: 13 test cases in `tests/llm_validator.test.ts` covering all rejection paths.

### Token budget per call

| Phase | Tokens |
|---|---|
| System prompt (schema + rules) | ~700 |
| Few-shot user prompt | ~200 |
| Few-shot assistant (KINGDOM_DEFAULT minified) | ~1500 |
| User prompt | ~100-300 |
| **Input total** | **~2500-2700** |
| Output (skeleton JSON) | ~1000-1500 |
| **Per call total** | **~3500-4200** |

With 1-2 retries (typical for Qwen 3 14B): ~5K-8K tokens total. Free with local lmstudio.

### Known limitations

- Some Qwen models don't honor `response_format: json_object` reliably — engine has `stripJsonFences()` to remove markdown wrapping if model ignores instruction
- Smaller models (Qwen 3 4B, 7B) may struggle with the schema constraints; recommended 14B+
- LLM output is non-deterministic by default (temperature=0.7); set `temperature: 0` in dialog for reproducibility
- L3 (zone classifier for landmark placements) and L4 (regional narration) NOT implemented in v3 — deferred to V2

---

## License

Same as parent repo (LoreWeave). Sprite assets if downloaded follow their respective licenses (Kenney = CC0; Cainos = CC-BY; etc.).

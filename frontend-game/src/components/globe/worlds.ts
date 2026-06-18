// Static catalog of pre-generated world globes (the `.glb` files exported by
// `crates/world-gen` and committed under `public/worlds/`).
//
// V1 = static delivery: the meshes are built offline by the CLI and shipped as
// assets, so the viewer needs no backend. The seam to swap in a live
// world-gen-service (generate on demand) is `resolveWorld` / this catalog —
// replace the static list with a fetched manifest later. Pure data + a pure
// resolver so it is unit-testable without touching three.js / WebGL.

export interface WorldEntry {
  /** Stable id (also the URL slug / `<select>` value). */
  id: string;
  /** Human label for the picker. */
  label: string;
  /** Path to the `.glb` under `public/` (served statically by Vite). */
  src: string;
}

// Named first so `DEFAULT_WORLD` is a typed `WorldEntry` (not `WORLDS[0]`, which
// is `WorldEntry | undefined` under `noUncheckedIndexedAccess`).
const SEED_7_CONTINENT: WorldEntry = {
  id: 'seed-7-continent',
  label: 'Seed 7 — Continent',
  src: '/worlds/seed-7-continent.glb',
};

/** The bundled worlds. `DEFAULT_WORLD` is shown on first load. */
export const WORLDS: readonly WorldEntry[] = [SEED_7_CONTINENT];

/** The default world (the picker's initial value + `resolveWorld` fallback). */
export const DEFAULT_WORLD: WorldEntry = SEED_7_CONTINENT;

/**
 * Resolve a world by id, falling back to [`DEFAULT_WORLD`] for an unknown or
 * missing id.
 */
export function resolveWorld(id?: string): WorldEntry {
  return WORLDS.find((w) => w.id === id) ?? DEFAULT_WORLD;
}

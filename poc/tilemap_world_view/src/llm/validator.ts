import type { TileMapSkeleton, TerrainKind, CellKind, MapObjectKind, RoadKind, ChannelTier } from '../data/types';
import { TERRAIN_KIND_ORDER } from '../data/types';
import type { ValidationResult } from './types';

const VALID_CELL_KINDS: readonly CellKind[] = [
  'capital',
  'fortress',
  'temple',
  'tavern',
  'port',
  'cell',
  'cave',
];

const VALID_OBJECT_KINDS: readonly MapObjectKind[] = [
  'Treasure',
  'MonsterLair',
  'Landmark',
  'Decoration',
  'Mine',
  'Portal',
  'Ruin',
];

const VALID_ROAD_KINDS: readonly RoadKind[] = ['Highway', 'Path', 'Trade'];

const VALID_TIERS: readonly ChannelTier[] = [
  'Continent',
  'Country',
  'District',
  'Town',
  'Cell',
];

/**
 * Validate that an unknown JSON value matches the TileMapSkeleton interface +
 * additional semantic constraints (positions in bounds, road graph connected, etc.).
 *
 * Returns aggregated errors so LLM retry can self-correct multiple issues at once.
 *
 * NOTE: this is a custom hand-rolled validator. We deliberately don't use Zod/Yup
 * to keep the bundle small and the error messages tunable for LLM consumption.
 * Errors are phrased in imperative form ("Fix X to be Y") for retry effectiveness.
 */
export function validateSkeleton(input: unknown): ValidationResult<TileMapSkeleton> {
  const errors: string[] = [];

  if (!isObject(input)) {
    return { valid: false, errors: ['Top-level value must be a JSON object'] };
  }

  const obj = input as Record<string, unknown>;

  // ─── skeleton_id ────────────────────────────────────────────────────────
  if (typeof obj.skeleton_id !== 'string' || !obj.skeleton_id.match(/^[a-z0-9_]+$/)) {
    errors.push('skeleton_id must be a snake_case string (lowercase + underscores + digits)');
  }

  // ─── grid_size ──────────────────────────────────────────────────────────
  const gs = obj.grid_size as { width?: unknown; height?: unknown } | undefined;
  if (!isObject(gs) || gs.width !== 64 || gs.height !== 64) {
    errors.push('grid_size must be { width: 64, height: 64 }');
  }

  // ─── terrain_zones ──────────────────────────────────────────────────────
  if (!Array.isArray(obj.terrain_zones)) {
    errors.push('terrain_zones must be an array');
  } else {
    if (obj.terrain_zones.length === 0) {
      errors.push('terrain_zones must contain at least 1 zone');
    }
    obj.terrain_zones.forEach((z: unknown, i: number) => {
      const zErrors = validateZone(z, i);
      errors.push(...zErrors);
    });
    // Coverage check — every position 0..63 should be inside at least one zone
    if (obj.terrain_zones.length > 0 && obj.terrain_zones.every((z) => isValidZoneShape(z))) {
      const coverage = computeZoneCoverage(obj.terrain_zones as ValidZoneLike[]);
      if (coverage < 1.0) {
        errors.push(
          `terrain_zones cover only ${(coverage * 100).toFixed(1)}% of the 64×64 grid; ` +
            `add zones to fill the gaps (zones can overlap; first-match wins)`,
        );
      }
    }
  }

  // ─── cell_anchors ───────────────────────────────────────────────────────
  if (!Array.isArray(obj.cell_anchors)) {
    errors.push('cell_anchors must be an array');
  } else {
    if (obj.cell_anchors.length < 3) {
      errors.push('cell_anchors must have at least 3 entries (recommend 5-8)');
    }
    if (obj.cell_anchors.length > 12) {
      errors.push('cell_anchors must not exceed 12 entries');
    }
    const seenIds = new Set<string>();
    let hasCapital = false;
    obj.cell_anchors.forEach((c: unknown, i: number) => {
      const cErrors = validateCellAnchor(c, i, seenIds);
      errors.push(...cErrors);
      if (isObject(c) && (c as Record<string, unknown>).kind === 'capital') {
        hasCapital = true;
      }
    });
    if (!hasCapital) {
      errors.push('cell_anchors must include exactly one entry with kind="capital"');
    }
  }

  // ─── landmark_anchors ───────────────────────────────────────────────────
  if (!Array.isArray(obj.landmark_anchors)) {
    errors.push('landmark_anchors must be an array');
  } else {
    if (obj.landmark_anchors.length > 12) {
      errors.push('landmark_anchors must not exceed 12 entries');
    }
    const seenIds = new Set<string>();
    obj.landmark_anchors.forEach((l: unknown, i: number) => {
      const lErrors = validateLandmark(l, i, seenIds);
      errors.push(...lErrors);
    });
  }

  // ─── road_connections ───────────────────────────────────────────────────
  if (!Array.isArray(obj.road_connections)) {
    errors.push('road_connections must be an array');
  } else {
    const cellIds = new Set<string>();
    if (Array.isArray(obj.cell_anchors)) {
      for (const c of obj.cell_anchors) {
        if (isObject(c) && typeof (c as Record<string, unknown>).channel_id === 'string') {
          cellIds.add((c as Record<string, unknown>).channel_id as string);
        }
      }
    }
    obj.road_connections.forEach((r: unknown, i: number) => {
      const rErrors = validateRoadConnection(r, i, cellIds);
      errors.push(...rErrors);
    });

    // Connectivity check — every cell must be reachable from capital via roads
    if (errors.length === 0 && Array.isArray(obj.cell_anchors)) {
      const connErrors = checkConnectivity(
        obj.cell_anchors as Array<{ channel_id: string; kind: string }>,
        obj.road_connections as Array<{ from: string; to: string }>,
      );
      errors.push(...connErrors);
    }
  }

  if (errors.length > 0) return { valid: false, errors };
  return { valid: true, value: input as unknown as TileMapSkeleton, errors: [] };
}

// ─── Sub-validators ──────────────────────────────────────────────────────

interface ValidZoneLike {
  shape: { kind: 'rect'; bounds: { x: number; y: number; w: number; h: number } };
}

function validateZone(z: unknown, idx: number): string[] {
  const errs: string[] = [];
  if (!isObject(z)) return [`terrain_zones[${idx}] must be an object`];
  const zone = z as Record<string, unknown>;

  if (typeof zone.zone_id !== 'string' || !zone.zone_id.match(/^[a-z0-9_]+$/)) {
    errs.push(`terrain_zones[${idx}].zone_id must be snake_case`);
  }

  const shape = zone.shape as { kind?: unknown; bounds?: unknown } | undefined;
  if (!isObject(shape) || shape.kind !== 'rect') {
    errs.push(`terrain_zones[${idx}].shape must be { kind: "rect", bounds: { x, y, w, h } }`);
  } else {
    const b = shape.bounds as { x?: unknown; y?: unknown; w?: unknown; h?: unknown } | undefined;
    if (
      !isObject(b) ||
      !isInt(b.x, 0, 63) ||
      !isInt(b.y, 0, 63) ||
      !isInt(b.w, 1, 64) ||
      !isInt(b.h, 1, 64)
    ) {
      errs.push(
        `terrain_zones[${idx}].shape.bounds must be { x: 0..63, y: 0..63, w: 1..64, h: 1..64 } integers`,
      );
    } else {
      if ((b.x as number) + (b.w as number) > 64) {
        errs.push(`terrain_zones[${idx}].shape.bounds: x + w must be ≤ 64`);
      }
      if ((b.y as number) + (b.h as number) > 64) {
        errs.push(`terrain_zones[${idx}].shape.bounds: y + h must be ≤ 64`);
      }
    }
  }

  if (!isObject(zone.biome_weights)) {
    errs.push(`terrain_zones[${idx}].biome_weights must be an object`);
  } else {
    const bw = zone.biome_weights as Record<string, unknown>;
    let sum = 0;
    let hasAny = false;
    for (const [k, v] of Object.entries(bw)) {
      if (!TERRAIN_KIND_ORDER.includes(k as TerrainKind)) {
        errs.push(
          `terrain_zones[${idx}].biome_weights: invalid TerrainKind "${k}"; allowed: ${TERRAIN_KIND_ORDER.join(', ')}`,
        );
        continue;
      }
      if (typeof v !== 'number' || v < 0 || v > 1) {
        errs.push(`terrain_zones[${idx}].biome_weights["${k}"] must be a number in 0..1`);
        continue;
      }
      sum += v;
      hasAny = true;
    }
    if (!hasAny) {
      errs.push(`terrain_zones[${idx}].biome_weights must have at least 1 entry`);
    } else if (Math.abs(sum - 1) > 0.05) {
      errs.push(
        `terrain_zones[${idx}].biome_weights sum to ${sum.toFixed(2)}; must sum to ~1.0 (±0.05)`,
      );
    }
  }

  if (!isInt(zone.noise_octaves, 1, 6)) {
    errs.push(`terrain_zones[${idx}].noise_octaves must be integer 1..6`);
  }
  if (!isPositiveNumber(zone.noise_scale)) {
    errs.push(`terrain_zones[${idx}].noise_scale must be a positive number`);
  }

  return errs;
}

function isValidZoneShape(z: unknown): z is ValidZoneLike {
  if (!isObject(z)) return false;
  const zone = z as Record<string, unknown>;
  const shape = zone.shape as { kind?: unknown; bounds?: unknown } | undefined;
  if (!isObject(shape) || shape.kind !== 'rect') return false;
  const b = shape.bounds as { x?: unknown; y?: unknown; w?: unknown; h?: unknown } | undefined;
  return (
    isObject(b) &&
    isInt(b.x, 0, 63) &&
    isInt(b.y, 0, 63) &&
    isInt(b.w, 1, 64) &&
    isInt(b.h, 1, 64)
  );
}

function computeZoneCoverage(zones: ValidZoneLike[]): number {
  const grid: boolean[] = new Array(64 * 64).fill(false);
  for (const z of zones) {
    const b = z.shape.bounds;
    for (let y = b.y; y < b.y + b.h && y < 64; y++) {
      for (let x = b.x; x < b.x + b.w && x < 64; x++) {
        grid[y * 64 + x] = true;
      }
    }
  }
  return grid.filter(Boolean).length / grid.length;
}

function validateCellAnchor(c: unknown, idx: number, seenIds: Set<string>): string[] {
  const errs: string[] = [];
  if (!isObject(c)) return [`cell_anchors[${idx}] must be an object`];
  const cell = c as Record<string, unknown>;

  if (typeof cell.channel_id !== 'string' || !cell.channel_id.startsWith('cell:')) {
    errs.push(`cell_anchors[${idx}].channel_id must be a string starting with "cell:"`);
  } else if (seenIds.has(cell.channel_id)) {
    errs.push(`cell_anchors[${idx}].channel_id "${cell.channel_id}" is duplicated`);
  } else {
    seenIds.add(cell.channel_id);
  }

  if (!VALID_TIERS.includes(cell.tier as ChannelTier)) {
    errs.push(`cell_anchors[${idx}].tier must be one of: ${VALID_TIERS.join(', ')}`);
  }

  if (!isObject(cell.position) || !isInt((cell.position as Record<string, unknown>).x, 0, 63) || !isInt((cell.position as Record<string, unknown>).y, 0, 63)) {
    errs.push(`cell_anchors[${idx}].position must be { x: 0..63, y: 0..63 } integers`);
  }

  if (!VALID_CELL_KINDS.includes(cell.kind as CellKind)) {
    errs.push(`cell_anchors[${idx}].kind must be one of: ${VALID_CELL_KINDS.join(', ')}`);
  }

  if (typeof cell.display_name !== 'string' || cell.display_name.length === 0) {
    errs.push(`cell_anchors[${idx}].display_name must be a non-empty string`);
  }

  return errs;
}

function validateLandmark(l: unknown, idx: number, seenIds: Set<string>): string[] {
  const errs: string[] = [];
  if (!isObject(l)) return [`landmark_anchors[${idx}] must be an object`];
  const lm = l as Record<string, unknown>;

  if (typeof lm.object_id !== 'string' || !lm.object_id.startsWith('landmark:')) {
    errs.push(`landmark_anchors[${idx}].object_id must start with "landmark:"`);
  } else if (seenIds.has(lm.object_id)) {
    errs.push(`landmark_anchors[${idx}].object_id "${lm.object_id}" is duplicated`);
  } else {
    seenIds.add(lm.object_id);
  }

  if (!VALID_OBJECT_KINDS.includes(lm.kind as MapObjectKind)) {
    errs.push(`landmark_anchors[${idx}].kind must be one of: ${VALID_OBJECT_KINDS.join(', ')}`);
  }

  if (!isObject(lm.position) || !isInt((lm.position as Record<string, unknown>).x, 0, 63) || !isInt((lm.position as Record<string, unknown>).y, 0, 63)) {
    errs.push(`landmark_anchors[${idx}].position must be { x: 0..63, y: 0..63 } integers`);
  }

  if (typeof lm.display_name !== 'string' || lm.display_name.length === 0) {
    errs.push(`landmark_anchors[${idx}].display_name must be non-empty`);
  }

  return errs;
}

function validateRoadConnection(r: unknown, idx: number, validCellIds: Set<string>): string[] {
  const errs: string[] = [];
  if (!isObject(r)) return [`road_connections[${idx}] must be an object`];
  const road = r as Record<string, unknown>;

  if (typeof road.from !== 'string' || !validCellIds.has(road.from)) {
    errs.push(
      `road_connections[${idx}].from "${road.from}" must reference an existing cell_anchor.channel_id`,
    );
  }
  if (typeof road.to !== 'string' || !validCellIds.has(road.to)) {
    errs.push(
      `road_connections[${idx}].to "${road.to}" must reference an existing cell_anchor.channel_id`,
    );
  }
  if (road.from === road.to) {
    errs.push(`road_connections[${idx}].from and .to must be different cells`);
  }
  if (!VALID_ROAD_KINDS.includes(road.kind as RoadKind)) {
    errs.push(`road_connections[${idx}].kind must be one of: ${VALID_ROAD_KINDS.join(', ')}`);
  }

  return errs;
}

function checkConnectivity(
  cells: Array<{ channel_id: string; kind: string; tier?: string }>,
  roads: Array<{ from: string; to: string }>,
): string[] {
  const capital = cells.find((c) => c.kind === 'capital');
  if (!capital) return []; // already caught in cell validation

  const adj = new Map<string, string[]>();
  for (const c of cells) adj.set(c.channel_id, []);
  for (const r of roads) {
    adj.get(r.from)?.push(r.to);
    adj.get(r.to)?.push(r.from); // undirected
  }

  const visited = new Set<string>();
  const queue = [capital.channel_id];
  while (queue.length > 0) {
    const cur = queue.shift()!;
    if (visited.has(cur)) continue;
    visited.add(cur);
    for (const next of adj.get(cur) ?? []) {
      if (!visited.has(next)) queue.push(next);
    }
  }

  // Only require connectivity for tier=Town/District/Country/Continent (major hubs).
  // tier=Cell entries represent sub-locations near a parent town and may be walked-to
  // without a dedicated road segment.
  const unreachable = cells
    .filter((c) => !visited.has(c.channel_id))
    .filter((c) => c.tier !== 'Cell')
    .map((c) => c.channel_id);

  if (unreachable.length > 0) {
    return [
      `road_connections do not form a connected graph from capital. ` +
        `Unreachable major cells (Town/District tier): ${unreachable.join(', ')}. ` +
        `Add roads connecting these to the capital. ` +
        `(tier=Cell entries are exempt — they represent sub-locations.)`,
    ];
  }
  return [];
}

// ─── Type helpers ────────────────────────────────────────────────────────

function isObject(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v);
}

function isInt(v: unknown, min: number, max: number): v is number {
  return typeof v === 'number' && Number.isInteger(v) && v >= min && v <= max;
}

function isPositiveNumber(v: unknown): v is number {
  return typeof v === 'number' && Number.isFinite(v) && v > 0;
}

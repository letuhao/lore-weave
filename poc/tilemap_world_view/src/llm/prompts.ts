import type { ChatMessage } from './types';
import { KINGDOM_DEFAULT } from '../data/skeleton';

/**
 * Prompt templates for L1 — TileMapSkeleton generation from natural-language description.
 *
 * Strategy (per CSC_001 §6 lessons):
 *   - System prompt sets role + constraints + output format
 *   - Few-shot example pairs user-prompt → JSON output (uses KINGDOM_DEFAULT as canonical)
 *   - User's actual request appended last
 *   - On retry, append validation errors as new user message for self-correction
 *
 * Output format: STRICT JSON matching TileMapSkeleton interface. We use OpenAI's
 * `response_format: json_object` request flag where supported (lmstudio, OpenAI).
 *
 * Token budget per call:
 *   - System: ~500 tokens
 *   - Schema description: ~700 tokens
 *   - Few-shot user: ~150 tokens
 *   - Few-shot assistant: ~1500 tokens (KINGDOM_DEFAULT minified)
 *   - User actual: ~100-300 tokens
 *   - Total input: ~2950-3150 tokens
 *   - Output: ~1000-1500 tokens
 *   - Grand total: ~4000-4500 tokens
 *
 * Qwen 3 14B+ comfortable at this size; Qwen 3 4B may struggle with consistency.
 */

const SYSTEM_PROMPT = `You are a fantasy world-map designer for an LLM-driven MMO RPG (LoreWeave).
Your job: given a natural-language description, output a JSON skeleton matching the TileMapSkeleton interface.

CONTEXT: The skeleton describes a 64×64 tile world that will be procedurally rendered. Engine code
generates terrain (Perlin noise within zones) + roads (A* pathfinding) + decorations (procedural scatter).
You only design the high-level layout: zones, cell anchors, landmarks, road connections.

CRITICAL CONSTRAINTS:
1. Output is PURE JSON. No markdown, no commentary, no code fences. Just the JSON object.
2. Grid is 64×64 (positions in 0..63 inclusive)
3. terrain_zones must cover the full grid (no gaps; can overlap, first match wins)
4. biome_weights must sum approximately to 1.0 per zone
5. Allowed TerrainKind: Grass, Forest, Mountain, Water, Sand, Snow, Swamp, Road, Rough, Subterranean
6. Allowed CellKind: capital, fortress, temple, tavern, port, cell, cave
7. Allowed MapObjectKind: Treasure, MonsterLair, Landmark, Decoration, Mine, Portal, Ruin
8. Allowed RoadKind: Highway, Path, Trade
9. Allowed ChannelTier: Continent, Country, District, Town, Cell
10. All channel_id MUST start with "cell:" prefix and be snake_case
11. All object_id MUST start with "landmark:" prefix and be snake_case
12. display_name in Vietnamese with diacritics (xianxia/wuxia genre flavor by default; respect user's genre)
13. Every cell anchor's position must lie within at least one zone
14. road_connections form a connected graph (every cell reachable from capital)
15. Cell positions should be 3+ tiles apart from siblings to avoid cluttering

OUTPUT SHAPE (strict TypeScript):

interface TileMapSkeleton {
  skeleton_id: string;                          // snake_case identifier
  grid_size: { width: 64; height: 64 };
  terrain_zones: Array<{
    zone_id: string;                            // snake_case
    shape: { kind: 'rect'; bounds: { x: number; y: number; w: number; h: number } };
    biome_weights: Partial<Record<TerrainKind, number>>;
    noise_octaves: number;                      // 1-5 typical
    noise_scale: number;                        // 4-12 typical (smaller = more detail)
  }>;
  cell_anchors: Array<{
    channel_id: string;                         // "cell:<snake_case>"
    tier: 'Continent' | 'Country' | 'District' | 'Town' | 'Cell';
    position: { x: number; y: number };
    kind: 'capital' | 'fortress' | 'temple' | 'tavern' | 'port' | 'cell' | 'cave';
    display_name: string;                       // Vietnamese
  }>;
  landmark_anchors: Array<{
    object_id: string;                          // "landmark:<snake_case>"
    kind: 'Treasure' | 'MonsterLair' | 'Landmark' | 'Decoration' | 'Mine' | 'Portal' | 'Ruin';
    position: { x: number; y: number };
    display_name: string;                       // Vietnamese
  }>;
  road_connections: Array<{
    from: string;                               // channel_id of cell
    to: string;                                 // channel_id of cell
    kind: 'Highway' | 'Path' | 'Trade';
  }>;
}`;

const FEWSHOT_USER = `Tạo skeleton cho 1 wuxia kingdom 64×64. Bắc là dãy núi cao, trung tâm có 1 đồng bằng lớn với kinh đô, tây có rừng nguyên thủy, đông có vùng cỏ và sa mạc, nam là hồ lớn rồi bờ biển. Cần 5-7 cells (1 kinh đô + 1 fortress phía bắc + 1 temple phía tây + 1 tavern phía đông + 1 port phía nam, có thể thêm 2 cell nhỏ gần kinh đô). 5-7 landmarks (đỉnh núi, hồ thiêng, di tích cổ, hang quái thú, mỏ kim loại quý, etc.). Roads connect kinh đô với mọi cell.`;

// FEWSHOT_ASSISTANT — minified KINGDOM_DEFAULT as canonical example
const FEWSHOT_ASSISTANT = JSON.stringify(KINGDOM_DEFAULT);

/**
 * Qwen 3 chat-template directive — disables internal "thinking" mode.
 *
 * Without this, Qwen 3 reasoning models burn the entire token budget on internal
 * <think>...</think> reasoning before producing actual output. Empirical evidence:
 * Qwen 3.6 35B-A3B used 4499/4500 tokens on reasoning, leaving 1 token for output =
 * empty content + finish_reason="length". (Same failure pattern as CSC_001 v3.)
 *
 * `/no_think` is a directive recognized by Qwen 3 chat templates and forwarded to
 * the model as "skip thinking, output directly". Harmless on non-Qwen models
 * (just appears as text in the prompt; Claude/GPT/Llama/Mistral all ignore it).
 *
 * Reference: https://qwenlm.github.io/blog/qwen3/ (thinking mode toggle)
 */
const NO_THINK_DIRECTIVE = '/no_think\n\n';

export function buildInitialMessages(userPrompt: string): ChatMessage[] {
  return [
    { role: 'system', content: SYSTEM_PROMPT },
    { role: 'user', content: NO_THINK_DIRECTIVE + FEWSHOT_USER },
    { role: 'assistant', content: FEWSHOT_ASSISTANT },
    { role: 'user', content: NO_THINK_DIRECTIVE + userPrompt },
  ];
}

/** Build retry message — appends validation errors so LLM can self-correct. */
export function buildRetryMessages(
  prior: ChatMessage[],
  invalidJson: string,
  errors: string[],
): ChatMessage[] {
  return [
    ...prior,
    { role: 'assistant', content: invalidJson },
    {
      role: 'user',
      content:
        NO_THINK_DIRECTIVE +
        `Your previous response had errors. Fix them and respond with ONLY corrected JSON ` +
        `(no markdown, no commentary). Errors:\n` +
        errors.map((e, i) => `${i + 1}. ${e}`).join('\n'),
    },
  ];
}

// W6 — tool-name → owning-MCP-server grouping key, the FE MIRROR of
// chat-service app/services/agent_surface.py server_key_for_tool (which itself
// mirrors the ai-gateway federation registry). Used to group the rack's tool
// chips by server; the live agentSurface frame's `servers` map (counts only)
// is the backend's own grouping of the ADVERTISED surface — this helper covers
// the names the FE holds locally (session pins + discovered).
//
// Keep in sync with the backend map — a drifted prefix only mis-groups a chip
// (cosmetic), it never breaks the loop.

// Exported so serverKey.test.ts can pin it against the BE table (see the
// mirror-drift pin there).
export const PREFIX_TO_SERVER: Record<string, string> = {
  memory: 'knowledge',
  kg: 'knowledge',
  knowledge: 'knowledge',
  glossary: 'glossary',
  book: 'book',
  composition: 'composition',
  plan: 'composition', // PlanForge tools are federated by composition-service
  translation: 'translation',
  jobs: 'jobs',
};

// Mirror of chat-service frontend_tools.FRONTEND_TOOL_NAMES — browser-executed
// tools group under "ui" regardless of prefix (glossary_confirm_action etc.).
// Pinned by serverKey.test.ts against contracts/frontend-tools.contract.json
// (the committed cross-language SoT) — a BE-side tool add/remove fails that
// test instead of silently mis-grouping a chip.
export const FRONTEND_TOOL_NAMES = new Set([
  'propose_edit',
  'glossary_propose_entity_edit',
  'glossary_confirm_action',
  'ui_navigate',
  'ui_open_book',
  'ui_open_chapter',
  'ui_show_panel',
  'ui_watch_job',
  'confirm_action',
  'ui_open_studio_panel',
  'ui_focus_manuscript_unit',
]);

export const SERVER_KEY_UI = 'ui';
export const SERVER_KEY_CHAT = 'chat';
export const SERVER_KEY_OTHER = 'other';

export function serverKeyForTool(name: string): string {
  if (!name) return SERVER_KEY_OTHER;
  if (name === 'find_tools') return SERVER_KEY_CHAT;
  if (FRONTEND_TOOL_NAMES.has(name)) return SERVER_KEY_UI;
  const prefix = name.includes('_') ? name.split('_', 1)[0] : '';
  return PREFIX_TO_SERVER[prefix] ?? SERVER_KEY_OTHER;
}

export interface ServerToolGroup {
  key: string;
  tools: string[];
}

/** Group tool names by server key, preserving each group's insertion order.
 *  Groups sort by size (desc) then key so the busiest server leads. */
export function groupToolsByServer(names: string[]): ServerToolGroup[] {
  const byKey = new Map<string, string[]>();
  for (const name of names) {
    const key = serverKeyForTool(name);
    const list = byKey.get(key);
    if (list) list.push(name);
    else byKey.set(key, [name]);
  }
  return [...byKey.entries()]
    .map(([key, tools]) => ({ key, tools }))
    .sort((a, b) => b.tools.length - a.tools.length || a.key.localeCompare(b.key));
}

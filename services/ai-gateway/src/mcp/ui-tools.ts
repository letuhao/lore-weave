// Phase 3 (frontend-tools → MCP migration) — the KIND-A `ui_*` navigation tools,
// relocated from chat-service's frontend_tools.py to ai-gateway as CONSUMER-LOCAL
// tools (the tool_list/tool_load/find_tools shape: handled in mcp/handlers.ts with
// NO downstream provider). Spec: docs/specs/2026-07-19-frontend-tools-mcp-migration.md
// §4.1 (KIND A) + D3 (ai-gateway-local host).
//
// These are RESOLVE-IMMEDIATELY tools (no human gate): the tool VALIDATES its args
// (required + closed-set enum) and returns a DIRECTIVE synchronously; the browser
// client acts on the tool result (navigate / open a panel). Validation here is the
// root-cause fix for the panel_id silent-no-op (a free-string panel_id once rendered
// a no-op the model reported as success): an out-of-enum value returns a tool ERROR
// carrying the `enum`/`required` signal — never a silent no-op.
//
// SoT: contracts/frontend-tools.contract.json is the single schema source. ai-gateway
// cannot read it at runtime (its Docker build context is the service dir, not the repo
// root), so these definitions are a COMMITTED MIRROR — ui-tools.contract.spec.ts is the
// drift test that reads the repo-root contract (from the checkout, not the image) and
// asserts this mirror's args/required/enums match. The prose descriptions are NOT in
// the contract; they move here from frontend_tools.py (a MOVE, not a duplication — P3.2
// removes chat-service's copy).

/** The studio-panel closed set (Frontend-Tool Contract: the enum IS correctness — a
 * free-string panel_id was the original silent-no-op bug; never trim it). Kept in
 * lockstep with the contract's ui_open_studio_panel.panel_id enum via the drift test. */
export const STUDIO_PANEL_IDS = [
  'compose', 'scene-compose', 'chapter-assemble', 'editor', 'planner', 'agent-mode',
  'usage', 'notifications', 'settings', 'trash', 'steering', 'style-voice', 'extensions',
  'proposals', 'workflows', 'workflow-proposals', 'glossary', 'glossary-ontology',
  'glossary-unknown', 'glossary-ai-suggestions', 'glossary-merge-candidates', 'wiki',
  'knowledge', 'kg-overview', 'kg-entities', 'kg-timeline', 'kg-evidence', 'kg-gap',
  'kg-proposals', 'kg-schema', 'kg-graph', 'kg-insights', 'kg-jobs', 'kg-bio', 'kg-privacy',
  'kg-triage', 'search', 'jobs-list', 'books', 'leaderboard-books', 'leaderboard-authors',
  'leaderboard-translators', 'leaderboard-trending', 'chapter-browser', 'scene-browser',
  'scene-inspector', 'plan-hub', 'decompose', 'arc-inspector', 'arc-templates',
  'structure-templates', 'plan-passes', 'whatif-canvas', 'divergence', 'reference-shelf',
  'canonview', 'book-import', 'context-inspector', 'sharing', 'book-settings', 'translation',
  'enrichment-compose', 'enrichment-proposals', 'enrichment-gaps', 'enrichment-sources',
  'enrichment-jobs', 'enrichment-settings', 'user-guide', 'quality', 'quality-promises',
  'quality-critic', 'quality-coverage', 'quality-canon', 'quality-canon-rules',
  'quality-corrections', 'quality-heal', 'progress', 'flywheel', 'motif-library',
  'motif-graph', 'quality-conformance', 'world-map', 'place-graph', 'cast', 'character-arc',
] as const;

// The rich per-panel guide (the default; the compact A/B variant is default-OFF and not
// ported to ai-gateway — tracked D-P3-COMPACT-PANEL-DESC).
const PANEL_ID_DESCRIPTION =
  "The studio panel to open. 'compose' = the AI co-writer chat; 'scene-compose' = draft a " +
  'scene with the AI — stream a ghost draft or Diverge into candidates, edit/accept one into ' +
  'the editor (the correction flywheel); \'chapter-assemble\' = assemble a whole chapter from ' +
  "its scenes; 'editor' = the manuscript editor; 'planner' = the PlanForge planner; " +
  "'agent-mode' = mission control for an autonomous multi-chapter authoring run; 'usage' = " +
  "spend/tokens; 'notifications' = job completions; 'settings' = account/providers/translation; " +
  "'trash' = restore deleted books/chapters; 'steering' = author the book's steering rules; " +
  "'extensions' = plugins/skills/MCP servers/commands/hooks; 'proposals' = review proposed " +
  "skills; 'workflows'/'workflow-proposals' = saved workflow recipes and their proposals; " +
  "'glossary'/'glossary-ontology'/'glossary-unknown'/'glossary-ai-suggestions'/" +
  "'glossary-merge-candidates' = the book's entities, kinds, and review queues; 'wiki' = the " +
  "book's generated wiki; 'knowledge'/'kg-*' = the knowledge-graph projects, entities, timeline, " +
  "evidence, gaps, proposals, schema, graph, insights, jobs, bio, privacy, triage; 'search' = " +
  "search the book's prose or lore; 'jobs-list' = background jobs; 'books' = the user's other " +
  "books (view-only); 'leaderboard-*' = top/trending books/authors/translators; " +
  "'chapter-browser'/'scene-browser'/'scene-inspector' = browse/inspect chapters and scenes; " +
  "'plan-hub'/'decompose'/'arc-inspector'/'arc-templates'/'structure-templates'/'plan-passes'/" +
  "'whatif-canvas'/'divergence'/'reference-shelf'/'canonview' = the planning + what-if surfaces; " +
  "'book-import' = import chapters/books; 'context-inspector' = trace context management; " +
  "'sharing' = visibility + collaborators; 'book-settings' = title/language/cover/genre; " +
  "'translation' = the translation coverage matrix; 'enrichment-*' = enriched-lore compose/" +
  "proposals/gaps/sources/jobs/settings; 'user-guide' = the catalog of every Studio tool; " +
  "'quality'/'quality-*'/'progress'/'flywheel' = the quality launcher, promises, critic, " +
  "coverage, canon issues, corrections, heal, conformance; 'motif-library'/'motif-graph' = the " +
  "narrative-craft motif library and graph; 'world-map'/'place-graph' = the world map and place " +
  "graph; 'cast' = the cast codex; 'character-arc' = one character's timeline. If unsure, open " +
  "'user-guide'.";

/** A ui_* tool definition (MCP tool shape) — mirrors the federation catalog's tool shape. */
export interface UiToolDef {
  name: string;
  description: string;
  inputSchema: {
    type: 'object';
    properties: Record<string, unknown>;
    required?: string[];
    additionalProperties: false;
  };
}

export const UI_TOOLS: UiToolDef[] = [
  {
    name: 'ui_navigate',
    description:
      "Navigate the user's browser to a page (e.g. '/books', '/jobs', '/settings'). Use this to " +
      'SHOW the user something rather than dumping data into chat. The browser navigates ' +
      'immediately — no confirmation.',
    inputSchema: {
      type: 'object',
      properties: {
        path: { type: 'string', description: "An allowlisted in-app route, e.g. '/books' or '/settings'." },
      },
      required: ['path'],
      additionalProperties: false,
    },
  },
  {
    name: 'ui_open_book',
    description:
      "Open a book's detail page, optionally on a specific tab. Use when the user wants to SEE a " +
      'book or one of its surfaces (translation, glossary, wiki...). Opens immediately.',
    inputSchema: {
      type: 'object',
      properties: {
        book_id: { type: 'string', description: 'The book to open (UUID).' },
        tab: {
          type: 'string',
          enum: ['overview', 'translation', 'glossary', 'enrichment', 'wiki', 'settings'],
          description: 'Optional tab to open the book on.',
        },
      },
      required: ['book_id'],
      additionalProperties: false,
    },
  },
  {
    name: 'ui_open_chapter',
    description:
      'Open a chapter in the editor or reader. Use when the user wants to write or read a specific ' +
      'chapter. Opens immediately.',
    inputSchema: {
      type: 'object',
      properties: {
        book_id: { type: 'string', description: 'The book (UUID).' },
        chapter_id: { type: 'string', description: 'The chapter (UUID).' },
        mode: {
          type: 'string',
          enum: ['edit', 'read'],
          description: 'edit = open the editor; read = open the reader.',
        },
      },
      required: ['book_id', 'chapter_id', 'mode'],
      additionalProperties: false,
    },
  },
  {
    name: 'ui_show_panel',
    description:
      'Open a tab or panel on the current view (e.g. the glossary, translation, or wiki panel). Use ' +
      'to reveal a surface without leaving the page. Opens immediately.',
    inputSchema: {
      type: 'object',
      properties: {
        panel: { type: 'string', description: 'The panel/tab name to show.' },
        args: { type: 'object', description: 'Optional panel-specific arguments.', additionalProperties: true },
      },
      required: ['panel'],
      additionalProperties: false,
    },
  },
  {
    name: 'ui_watch_job',
    description:
      'Open the jobs monitor focused on a running job so the user sees live progress. ALWAYS call ' +
      'this after starting a long-running job (translation, media generation): the job runs for ' +
      'minutes — say you STARTED it and offer this live view; NEVER claim it finished. Opens ' +
      'immediately.',
    inputSchema: {
      type: 'object',
      properties: { job_id: { type: 'string', description: 'The job to watch (UUID).' } },
      required: ['job_id'],
      additionalProperties: false,
    },
  },
  {
    name: 'ui_open_studio_panel',
    description:
      'Open a Writing Studio dock panel for the user (e.g. the AI compose chat, the manuscript ' +
      'editor). Use to bring a studio tool into view. Opens immediately — no confirmation.',
    inputSchema: {
      type: 'object',
      properties: {
        panel_id: { type: 'string', enum: [...STUDIO_PANEL_IDS], description: PANEL_ID_DESCRIPTION },
      },
      required: ['panel_id'],
      additionalProperties: false,
    },
  },
  {
    name: 'ui_focus_manuscript_unit',
    description:
      'Open and focus a specific chapter in the Writing Studio manuscript editor. Use when the user ' +
      'wants to write or see a particular chapter in the studio. Opens immediately — no confirmation.',
    inputSchema: {
      type: 'object',
      properties: {
        chapter_id: { type: 'string', description: 'The chapter to open in the editor (UUID).' },
        scene_id: { type: 'string', description: 'Optional scene to focus within the chapter (UUID).' },
      },
      required: ['chapter_id'],
      additionalProperties: false,
    },
  },
];

/** Name set for O(1) "is this a consumer-local ui_* tool?" checks in the dispatcher. */
export const UI_TOOL_NAMES: ReadonlySet<string> = new Set(UI_TOOLS.map((t) => t.name));

const UI_TOOL_BY_NAME: Map<string, UiToolDef> = new Map(UI_TOOLS.map((t) => [t.name, t]));

export const UI_DIRECTIVE_TYPE = 'io.loreweave/ui-directive';

export interface UiValidationError {
  ok: false;
  error: string;
}
export interface UiValidationOk {
  ok: true;
}

/** Validate ui_* args against the tool's schema: every `required` field present, and
 * every closed-set (`enum`) field within its enum. Returns the `enum`/`required` signal
 * on failure (the model already knows how to repair it) — NEVER a silent pass. */
/** JSON-Schema primitive-type match for the scalar arg types these tools declare
 * (string/object/number/integer/boolean). Arrays aren't used by any ui_* arg. */
function matchesType(val: unknown, type: string): boolean {
  switch (type) {
    case 'string': return typeof val === 'string';
    case 'object': return typeof val === 'object' && !Array.isArray(val) && val !== null;
    case 'number': return typeof val === 'number';
    case 'integer': return typeof val === 'number' && Number.isInteger(val);
    case 'boolean': return typeof val === 'boolean';
    default: return true; // unknown declared type → don't block
  }
}

export function validateUiToolArgs(name: string, args: Record<string, unknown>): UiValidationOk | UiValidationError {
  const def = UI_TOOL_BY_NAME.get(name);
  if (!def) return { ok: false, error: `unknown ui tool: ${name}` };
  const props = def.inputSchema.properties as Record<string, { enum?: unknown[]; type?: string }>;
  const a = args ?? {};

  for (const req of def.inputSchema.required ?? []) {
    if (a[req] === undefined || a[req] === null || a[req] === '') {
      return { ok: false, error: `required: missing property '${req}' for ${name}` };
    }
  }
  for (const [key, schema] of Object.entries(props)) {
    const val = a[key];
    if (val === undefined || val === null) continue; // optional-and-absent is fine
    // Declared-type check (the SDK-inputSchema-handler equivalent for these
    // consumer-local tools, which bypass the SDK's own schema validation): a wrong
    // type is rejected, not passed through to become a client-side no-op.
    if (schema.type && !matchesType(val, schema.type)) {
      return { ok: false, error: `type: ${key} must be a ${schema.type} for ${name}` };
    }
    if (schema.enum && !schema.enum.includes(val as never)) {
      return {
        ok: false,
        error: `enum: '${String(val)}' is not a valid ${key} for ${name} — allowed: ${schema.enum.join(', ')}`,
      };
    }
  }
  return { ok: true };
}

/** A consumer-local ui_* CallTool result. On valid args → a DIRECTIVE the browser acts
 * on (structuredContent carries {type, tool, args}); on invalid → an isError result with
 * the enum/required signal (never a silent no-op). Shape mirrors the other consumer-local
 * tool results (content + structuredContent), so the existing normalizeToolResult path and
 * the SDK handle it uniformly. */
export function handleUiTool(name: string, args: Record<string, unknown>): {
  content: { type: 'text'; text: string }[];
  structuredContent: Record<string, unknown>;
  isError?: boolean;
} {
  const check = validateUiToolArgs(name, args ?? {});
  if (!check.ok) {
    return {
      content: [{ type: 'text', text: check.error }],
      structuredContent: { code: 'ui_tool_invalid_args', message: check.error },
      isError: true,
    };
  }
  const directive = { type: UI_DIRECTIVE_TYPE, tool: name, args: args ?? {} };
  return {
    content: [{ type: 'text', text: `directive: ${name} — the client will act on this.` }],
    structuredContent: directive,
  };
}

// MCP fan-out (C-NAV) — resolve a `ui_*` navigation tool call into a concrete
// router path + the resume payload the agent reads back. Pure logic (no React,
// no router) so it is unit-testable on its own; the executor hook (useUiToolExecutor)
// performs the navigate + POSTs the resolve.
//
// These frontend tools suspend→browser like propose_edit, but RESOLVE IMMEDIATELY
// (no human Apply gate): the agent asked to move the UI, the FE just does it.
//
// Allowlisted route prefixes (C-NAV): a `ui_navigate(path)` is only honored when
// the path begins with one of these — defence against the model being talked
// into pushing an arbitrary route. ui_open_book / ui_open_chapter / ui_watch_job
// build their path from typed ids, so they are always allowlisted by construction.

// Phase 3 cutover — ai-gateway now returns a DIRECTIVE for a ui_* tool call (instead
// of chat-service suspending the run): the tool RESULT carries this shape, and the FE
// acts on it (navigate / open a panel) with no suspend to resolve.
export const UI_DIRECTIVE_TYPE = 'io.loreweave/ui-directive';

export interface UiDirective {
  type: typeof UI_DIRECTIVE_TYPE;
  tool: string;
  args: Record<string, unknown>;
}

/** Extract a ui directive from a tool-call RESULT, or null if it isn't one. The
 * result may be the directive object itself (structuredContent) or carry it under a
 * `structuredContent` key, depending on how the wire serialized it — accept both. */
export function uiDirectiveFromResult(result: unknown): UiDirective | null {
  const o = result as Record<string, unknown> | null | undefined;
  const cand =
    o && typeof o === 'object' && o.type === UI_DIRECTIVE_TYPE
      ? o
      : o && typeof (o as { structuredContent?: unknown }).structuredContent === 'object'
        ? ((o as { structuredContent?: Record<string, unknown> }).structuredContent as Record<string, unknown>)
        : null;
  if (cand && cand.type === UI_DIRECTIVE_TYPE && typeof cand.tool === 'string') {
    return { type: UI_DIRECTIVE_TYPE, tool: cand.tool as string, args: (cand.args as Record<string, unknown>) ?? {} };
  }
  return null;
}

/** The set of `ui_*` tool names this executor handles. */
export const UI_TOOL_NAMES = [
  'ui_navigate',
  'ui_open_book',
  'ui_open_chapter',
  'ui_show_panel',
  'ui_watch_job',
] as const;

export type UiToolName = (typeof UI_TOOL_NAMES)[number];

export function isUiTool(name: string): name is UiToolName {
  return (UI_TOOL_NAMES as readonly string[]).includes(name);
}

/** Route prefixes a `ui_navigate(path)` may target. Kept in sync with App.tsx. */
export const ALLOWED_NAV_PREFIXES = [
  '/books',
  '/chat',
  '/knowledge',
  '/worlds',
  '/campaigns',
  '/jobs',
  '/usage',
  '/standards',
  '/settings',
  '/notifications',
  '/browse',
  '/trash',
  '/onboarding',
  '/reading-history',
  '/leaderboard',
] as const;

const BOOK_TABS = [
  'overview',
  'translation',
  'glossary',
  'enrichment',
  'wiki',
  'settings',
] as const;
type BookTab = (typeof BOOK_TABS)[number];

/** A book tab → its route path. `overview` is the bare `/books/:id`; the rest
 *  map to the flat-tab routes declared in App.tsx. */
function bookTabPath(bookId: string, tab?: string): string {
  const base = `/books/${encodeURIComponent(bookId)}`;
  if (!tab || tab === 'overview') return base;
  if ((BOOK_TABS as readonly string[]).includes(tab)) return `${base}/${tab as BookTab}`;
  // Unknown tab → fall back to overview (never an invalid route).
  return base;
}

/** Outcome of resolving a `ui_*` tool: the path to navigate to (or null when the
 *  request is rejected, e.g. a disallowed nav target) + the resume payload to
 *  POST back to the agent. The boolean flag in `result` always reflects whether
 *  the navigation was performed, so the agent never falsely believes it moved. */
export interface UiNavResolution {
  /** router path to push; null ⇒ do not navigate (rejected) */
  path: string | null;
  /** resume payload (the tool's result), per the C-NAV table */
  result: Record<string, unknown>;
}

function isAllowed(path: string): boolean {
  if (!path.startsWith('/')) return false;
  return ALLOWED_NAV_PREFIXES.some(
    (p) => path === p || path.startsWith(`${p}/`) || path.startsWith(`${p}?`),
  );
}

/**
 * Resolve a `ui_*` tool call to a navigation + resume payload.
 * Returns `{ path, result }`; the caller navigates to `path` (when non-null) and
 * POSTs `result` as the tool resolve. The result key (navigated/opened/shown/
 * watching) matches the C-NAV contract per tool.
 */
export function resolveUiTool(tool: string, args: Record<string, unknown>): UiNavResolution {
  switch (tool) {
    case 'ui_navigate': {
      // Reject payloads carry a short `error` so a weak model self-corrects instead of
      // spinning on a silent flag (CLAUDE.md → Frontend-tool contract, no-silent-no-op).
      const path = typeof args.path === 'string' ? args.path : '';
      if (path && isAllowed(path)) return { path, result: { navigated: true } };
      return { path: null, result: { navigated: false, error: 'path is not an allowed in-app route' } };
    }
    case 'ui_open_book': {
      const bookId = typeof args.book_id === 'string' ? args.book_id : '';
      const tab = typeof args.tab === 'string' ? args.tab : undefined;
      if (!bookId) return { path: null, result: { opened: false, error: 'missing book_id' } };
      return { path: bookTabPath(bookId, tab), result: { opened: true } };
    }
    case 'ui_open_chapter': {
      const bookId = typeof args.book_id === 'string' ? args.book_id : '';
      const chapterId = typeof args.chapter_id === 'string' ? args.chapter_id : '';
      const mode = args.mode === 'read' ? 'read' : 'edit';
      if (!bookId || !chapterId) return { path: null, result: { opened: false, error: 'missing book_id or chapter_id' } };
      const path = `/books/${encodeURIComponent(bookId)}/chapters/${encodeURIComponent(chapterId)}/${mode}`;
      return { path, result: { opened: true } };
    }
    case 'ui_show_panel': {
      // A panel/tab on the CURRENT view. We model it as a query param the host
      // page reads (?panel=...&...). Resolve relative to the current location so
      // we don't navigate away from the page the user is on.
      const panel = typeof args.panel === 'string' ? args.panel : '';
      if (!panel) return { path: null, result: { shown: false, error: 'missing panel' } };
      const params = new URLSearchParams();
      params.set('panel', panel);
      const extra = args.args;
      if (extra && typeof extra === 'object') {
        for (const [k, v] of Object.entries(extra as Record<string, unknown>)) {
          if (v != null) params.set(k, String(v));
        }
      }
      const base = typeof window !== 'undefined' ? window.location.pathname : '';
      return { path: `${base}?${params.toString()}`, result: { shown: true } };
    }
    case 'ui_watch_job': {
      const jobId = typeof args.job_id === 'string' ? args.job_id : '';
      if (!jobId) return { path: null, result: { watching: false, error: 'missing job_id' } };
      return { path: `/jobs?focus=${encodeURIComponent(jobId)}`, result: { watching: true } };
    }
    default:
      return { path: null, result: {} };
  }
}

// #09 Lane A — resolve a studio `ui_*` frontend tool into a host side-effect + the resume payload
// the agent reads back. Pure (no React, no host in the signature — returns an `effect` closure the
// executor runs with the live host), so it's unit-testable on its own.
//
// These suspend→browser like propose_edit but RESOLVE IMMEDIATELY (no human Apply gate): the agent
// asked to move the studio UI, the FE just does it. Args carry IDs ONLY — never prose/draft blobs
// (G2: no data-bearing frontend tools).
import type { StudioHost } from '../host/StudioHostProvider';
import type { UiNavInterceptor } from '@/features/chat/nav/uiNavScope';

export const STUDIO_UI_TOOLS = ['ui_open_studio_panel', 'ui_focus_manuscript_unit'] as const;
export type StudioUiToolName = (typeof STUDIO_UI_TOOLS)[number];

export function isStudioUiTool(name: string): name is StudioUiToolName {
  return (STUDIO_UI_TOOLS as readonly string[]).includes(name);
}

export interface StudioUiResolution {
  /** resume payload POSTed back to the agent (always reflects whether the action was performed) */
  result: Record<string, unknown>;
  /** the side-effect to run against the live host (absent when the request was rejected) */
  effect?: (host: StudioHost) => void;
}

export function resolveStudioUiTool(tool: string, args: Record<string, unknown>): StudioUiResolution {
  switch (tool) {
    case 'ui_open_studio_panel': {
      // Read `panel_id` (the contract), tolerating the `panel`/`page` aliases a weaker model
      // reaches for by confusing this tool with ui_show_panel/ui_open_book (a live gemma-26b smoke
      // sent `panel:"editor"` → an undefined panel_id silently no-op'd). Alias here so the loop
      // still closes; the BE schema's `panel_id` enum steers competent models to the canonical name.
      const raw = args.panel_id ?? args.panel ?? args.page;
      const panelId = typeof raw === 'string' ? raw.trim() : '';
      if (!panelId) return { result: { opened: false, error: 'missing panel_id (e.g. "compose" or "editor")' } };
      return { result: { opened: true }, effect: (host) => host.openPanel(panelId) };
    }
    case 'ui_focus_manuscript_unit': {
      const chapterId = typeof args.chapter_id === 'string' ? args.chapter_id : '';
      if (!chapterId) return { result: { focused: false, error: 'missing chapter_id' } };
      return { result: { focused: true }, effect: (host) => host.focusManuscriptUnit(chapterId) };
    }
    default:
      return { result: {} };
  }
}

// ── Nav-scope interceptor (#12 M-E live-caught) ────────────────────────────────
// The generic C-NAV executor (useUiToolExecutor) is mounted inside the studio's Compose
// panel. Un-intercepted, an agent ui_open_book/ui_open_chapter on the CURRENT book
// navigates the SPA to /books/{id}... — unmounting the whole studio (and orphaning the
// agent's own resumed run). Inside the studio those calls are remapped to dock actions;
// anything genuinely outside this book falls through (null) to the real navigation.
export function makeStudioNavInterceptor(host: StudioHost): UiNavInterceptor {
  return (tool, args) => {
    const bookId = host.bookId;
    switch (tool) {
      case 'ui_open_chapter': {
        const chapterId = typeof args.chapter_id === 'string' ? args.chapter_id : '';
        const argBook = typeof args.book_id === 'string' && args.book_id ? args.book_id : bookId;
        if (!chapterId || argBook !== bookId) return null; // malformed → generic reject; cross-book → real nav
        return {
          path: null,
          result: { opened: true, note: 'opened in the studio editor' },
          effect: () => host.focusManuscriptUnit(chapterId),
        };
      }
      case 'ui_open_book': {
        const argBook = typeof args.book_id === 'string' ? args.book_id : '';
        if (argBook && argBook !== bookId) return null; // another book → real nav
        return { path: null, result: { opened: true, note: 'this book is already open in the studio' } };
      }
      case 'ui_navigate': {
        const path = typeof args.path === 'string' ? args.path : '';
        if (path === `/books/${bookId}` || path.startsWith(`/books/${bookId}/studio`)) {
          return { path: null, result: { navigated: true, note: "already in this book's studio" } };
        }
        return null;
      }
      default:
        return null;
    }
  };
}

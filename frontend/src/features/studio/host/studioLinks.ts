// #11 F3 — the studio link resolver: maps an in-app URL (notification metadata.link, cross-panel
// references, …) onto a host effect so the studio NEVER navigate()s away from itself. Pure like
// studioUiNav.ts (no React, host injected by the caller) so it's unit-testable on its own.
//
// Resolution contract (W1-2 LOCKED):
//   studio   — a known pattern for THIS book/user → run the effect (openPanel/focus)
//   external — everything else that is safely followable (http(s), an app path we don't map,
//              a chapter in ANOTHER book) → caller window.open()s it in a NEW TAB; the studio
//              stays mounted, dock layout intact
//   blocked  — not http(s) and not a '/'-prefixed app path (javascript:, data:, …) → do nothing
//              (same safety rule as NotificationsPage LOW-4)
import type { StudioHost } from './StudioHostProvider';

export type StudioLinkResolution =
  | { kind: 'studio'; effect: (host: StudioHost) => void }
  | { kind: 'external'; url: string }
  | { kind: 'blocked' };

export interface StudioLinkContext {
  /** The studio's current book (host is per-book — a chapter link into ANOTHER book is external). */
  bookId: string;
  /** Localized dock-tab title for a panel id (catalog + t). Optional: panels self-title on mount. */
  titleFor?: (panelId: string) => string | undefined;
}

const CHAPTER_RE = /^\/books\/([^/]+)\/chapters\/([^/]+)(?:\/|$)/;
const SETTINGS_RE = /^\/settings(?:\/([^/]+))?\/?$/;
// 14_kg_panels.md — a book-scoped page (glossary/wiki/enrichment) is only safely mappable
// when it's THIS studio's book (same-book rule, mirrors CHAPTER_RE) — a different book's
// page has no in-studio equivalent (this studio IS one book) and stays external.
const BOOK_SCOPED_PAGE_RE = /^\/books\/([^/]+)\/(glossary|wiki|enrichment)(?:\/|$)/;
/** Path → panel id for the book-scoped pages above that already have a dock panel. Wiki and
 *  enrichment don't have one yet (separate, not-yet-built tracks — 14_kg_panels.md "Out of
 *  scope") so they're deliberately absent here and fall through to external. */
const BOOK_SCOPED_PAGE_PANELS: Record<string, string> = {
  glossary: 'glossary',
};
// 20_agent_mode.md D-AGENT-MODE-NOTIFY — the autonomous-run terminal notification's
// `metadata.link` (authoring_run_service.py `_notify_terminal`). Same-book rule as
// BOOK_SCOPED_PAGE_RE, but there is no standalone page for a single run (Agent Mode
// is Studio-only) — a cross-book click can't land on the run itself, so it degrades
// to that OTHER book's Studio shell (a real route) rather than a 404.
const AGENT_MODE_RUN_RE = /^\/books\/([^/]+)\/agent-mode\/runs\/([^/]+)(?:\/|$)/;

/** Panel ids reachable by a bare app path (wave-1 user-scoped panels). */
const PATH_PANELS: Record<string, string> = {
  '/usage': 'usage',
  '/notifications': 'notifications',
  '/trash': 'trash',
  // 14_kg_panels.md — the classic KnowledgePage's global (book-independent) tabs. Each has a
  // real dock-panel equivalent now; `/knowledge` itself and `/knowledge/projects` both land on
  // the hub (KnowledgePage redirects the bare path to /knowledge/projects). The project-id-keyed
  // routes (`/knowledge/projects/:id/:section`) are deliberately NOT mapped here: the `kg-*`
  // capability panels resolve "the CURRENT book's project" via useBookKnowledgeProject, not an
  // arbitrary :id from the link — a project id that isn't this book's project (e.g. the hub
  // listing a DIFFERENT book's project, or a standalone project) would silently show the wrong
  // project if naively mapped. Safe to add once a caller can assert :id === this book's project.
  '/knowledge': 'knowledge',
  '/knowledge/projects': 'knowledge',
  '/knowledge/jobs': 'kg-jobs',
  '/knowledge/global': 'kg-bio',
  '/knowledge/entities': 'kg-entities',
  '/knowledge/timeline': 'kg-timeline',
  '/knowledge/raw': 'kg-evidence',
  '/knowledge/insights': 'kg-insights',
  '/knowledge/privacy': 'kg-privacy',
};

export function resolveStudioLink(link: string, ctx: StudioLinkContext): StudioLinkResolution {
  if (/^https?:\/\//i.test(link)) return { kind: 'external', url: link };
  // '//' is protocol-relative — window.open would resolve it to an EXTERNAL origin. Not an
  // app path, not declared-external → blocked (defense in depth with notificationLink).
  if (!link.startsWith('/') || link.startsWith('//')) return { kind: 'blocked' };

  // Match on the pathname only; the full link (query/hash intact) is what an external open gets.
  const path = link.split(/[?#]/, 1)[0]!.replace(/\/+$/, '') || '/';

  const openPanel = (panelId: string, params?: Record<string, unknown>): StudioLinkResolution => ({
    kind: 'studio',
    effect: (host) => host.openPanel(panelId, { title: ctx.titleFor?.(panelId), params }),
  });

  const chapter = CHAPTER_RE.exec(path);
  if (chapter) {
    const [, bookId, chapterId] = chapter;
    if (bookId === ctx.bookId) {
      return { kind: 'studio', effect: (host) => host.focusManuscriptUnit(chapterId!) };
    }
    return { kind: 'external', url: link }; // another book — full app in a new tab
  }

  const bookPage = BOOK_SCOPED_PAGE_RE.exec(path);
  if (bookPage) {
    const [, bookId, page] = bookPage;
    const mappedPanel = BOOK_SCOPED_PAGE_PANELS[page!];
    if (bookId === ctx.bookId && mappedPanel) return openPanel(mappedPanel);
    return { kind: 'external', url: link }; // another book, or a page with no panel yet (wiki/enrichment)
  }

  const agentRun = AGENT_MODE_RUN_RE.exec(path);
  if (agentRun) {
    const [, bookId, runId] = agentRun;
    if (bookId === ctx.bookId) return openPanel('agent-mode', { runId });
    return { kind: 'external', url: `/books/${bookId}/studio` };
  }

  const panelId = PATH_PANELS[path];
  if (panelId) return openPanel(panelId);

  const settings = SETTINGS_RE.exec(path);
  if (settings) return openPanel('settings', settings[1] ? { tab: settings[1] } : undefined);

  return { kind: 'external', url: link }; // unmapped app path — new tab, never navigate()
}

/** Convenience for click handlers: resolve + perform (studio effect, window.open, or nothing). */
export function followStudioLink(link: string, host: StudioHost, ctx: StudioLinkContext): StudioLinkResolution['kind'] {
  const r = resolveStudioLink(link, ctx);
  if (r.kind === 'studio') r.effect(host);
  else if (r.kind === 'external') window.open(r.url, '_blank', 'noopener,noreferrer');
  return r.kind;
}

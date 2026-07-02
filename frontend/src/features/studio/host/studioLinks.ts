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

/** Panel ids reachable by a bare app path (wave-1 user-scoped panels). */
const PATH_PANELS: Record<string, string> = {
  '/usage': 'usage',
  '/notifications': 'notifications',
  '/trash': 'trash',
};

export function resolveStudioLink(link: string, ctx: StudioLinkContext): StudioLinkResolution {
  if (/^https?:\/\//i.test(link)) return { kind: 'external', url: link };
  if (!link.startsWith('/')) return { kind: 'blocked' };

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

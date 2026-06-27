import { useEffect, useMemo, useRef, useState } from 'react';
import { Archive, ChevronsUpDown, Plus } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { useChatSession } from '../providers';
import type { ChatSession } from '../types';

interface SessionSwitcherProps {
  /**
   * Restrict the listed sessions to this knowledge project (a book's chats).
   * `undefined` = no filter (show every session). `null` = the unscoped pool
   * (sessions with no project). Passing the embedded binding's resolved project
   * id keeps the switcher to *this book's* chats and — critically — avoids the
   * embedded binding re-patching a foreign session into this book on switch.
   */
  scopeProjectId?: string | null;
  className?: string;
}

/**
 * Compact in-header session control for the embedded/workspace chat (book dock,
 * editor AI panel) — the chat-page's full {@link SessionSidebar} doesn't fit a
 * ~300px panel. Lets the user switch between this book's chats, archive a stale
 * one, and start a fresh chat without leaving the workspace (bug #17). Reads all
 * state/actions from {@link useChatSession}, so any host that mounts the chat
 * providers gets it for free.
 */
export function SessionSwitcher({ scopeProjectId, className }: SessionSwitcherProps) {
  const { t } = useTranslation('chat');
  const { sessions, activeSession, sessionsLoading, selectSession, setShowNewDialog, archiveSession, modelNameMap } =
    useChatSession();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  // Close on outside-click / Escape while open (a subscription, not event-handling).
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const scoped = useMemo(() => {
    const base =
      scopeProjectId === undefined ? sessions : sessions.filter((s) => s.project_id === scopeProjectId);
    // Always keep the active session visible/selectable even if its project_id
    // hasn't been bound yet (the embedded binding patches it asynchronously).
    if (activeSession && !base.some((s) => s.session_id === activeSession.session_id)) {
      return [activeSession, ...base];
    }
    return base;
  }, [sessions, scopeProjectId, activeSession]);

  function handleSelect(s: ChatSession) {
    selectSession(s);
    setOpen(false);
  }

  function handleNew() {
    setOpen(false);
    setShowNewDialog(true);
  }

  return (
    <div ref={rootRef} className={cn('relative min-w-0', className)}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="listbox"
        aria-expanded={open}
        data-testid="session-switcher-trigger"
        title={t('switcher.switch')}
        className="flex min-w-0 max-w-full items-center gap-1 rounded-md px-1.5 py-1 text-left hover:bg-secondary"
      >
        <span className="truncate text-sm font-semibold text-foreground">
          {activeSession?.title ?? t('switcher.no_active')}
        </span>
        <ChevronsUpDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
      </button>

      {open && (
        <div
          role="listbox"
          className="absolute left-0 top-full z-50 mt-1 max-h-[60vh] w-64 overflow-y-auto rounded-md border border-border bg-card py-1 shadow-xl"
        >
          {sessionsLoading && scoped.length === 0 && (
            <p className="px-3 py-2 text-xs text-muted-foreground">{t('switcher.loading')}</p>
          )}
          {!sessionsLoading && scoped.length === 0 && (
            <p className="px-3 py-2 text-xs text-muted-foreground">{t('switcher.empty')}</p>
          )}

          {scoped.map((s) => {
            const isActive = s.session_id === activeSession?.session_id;
            return (
              <div
                key={s.session_id}
                role="option"
                aria-selected={isActive}
                onClick={() => handleSelect(s)}
                className={cn(
                  'group flex cursor-pointer items-center gap-2 px-3 py-1.5 text-left transition-colors',
                  isActive ? 'bg-accent/10' : 'hover:bg-secondary',
                )}
              >
                <div className="min-w-0 flex-1">
                  <p
                    className={cn(
                      'truncate text-[13px] font-medium',
                      isActive ? 'text-foreground' : 'text-muted-foreground',
                    )}
                  >
                    {s.title}
                  </p>
                  <p className="truncate text-[10px] text-muted-foreground">
                    {modelNameMap?.get(s.model_ref) ??
                      (s.model_source === 'user_model' ? t('header.my_model') : t('header.platform'))}{' '}
                    &middot; {t('header.messages', { count: s.message_count })}
                  </p>
                </div>
                {/* Archive a stale/huge session without leaving the panel (bug #17). */}
                <button
                  type="button"
                  title={t('sidebar.archive')}
                  aria-label={t('sidebar.archive')}
                  onClick={(e) => {
                    e.stopPropagation();
                    void archiveSession(s.session_id);
                  }}
                  className="hidden shrink-0 rounded p-1 text-muted-foreground hover:text-foreground group-hover:block"
                >
                  <Archive className="h-3 w-3" />
                </button>
              </div>
            );
          })}

          <div className="mt-1 border-t border-border pt-1">
            <button
              type="button"
              onClick={handleNew}
              className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-[13px] font-medium text-accent hover:bg-secondary"
            >
              <Plus className="h-3.5 w-3.5 shrink-0" />
              {t('switcher.new_chat')}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

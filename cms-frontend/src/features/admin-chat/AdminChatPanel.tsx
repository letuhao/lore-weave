// T4d — the CMS admin chat panel (view; composes the controllers). The admin
// talks to the System-tier assistant: it advertises ONLY the admin tools and
// every System write is a human-confirmed card (INV-T3/T6). Token model: the
// USER (HS256) token streams the turn; the RS256 admin token rides
// X-Admin-Token (routing) + is the confirm bearer.
import { useEffect, useMemo, useState } from 'react';
import { Plus, Send } from 'lucide-react';
import { useAuth } from '@/auth';
import { useAdminSessions } from './hooks/useAdminSessions';
import { useAdminChat } from './hooks/useAdminChat';
import { MessageList } from './components/MessageList';
import { adminChatApi } from './api';

export function AdminChatPanel() {
  const { userToken, accessToken } = useAuth();
  const sessionsCtl = useAdminSessions(userToken);
  const { models, sessions, activeId, selectedModel, loading, error: sessErr } = sessionsCtl;
  const chat = useAdminChat(activeId, userToken, accessToken);
  const [draft, setDraft] = useState('');

  // Load history when the active session changes (synchronisation, not an event).
  useEffect(() => {
    chat.reset();
    if (!activeId || !userToken) return;
    let alive = true;
    adminChatApi
      .listMessages(userToken, activeId)
      .then((r) => {
        if (alive) chat.setMessages(r.items ?? []);
      })
      .catch(() => {
        /* a fresh session has no history */
      });
    return () => {
      alive = false;
    };
    // chat.reset / setMessages are stable; depend on the identifiers only.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeId, userToken]);

  const activeSession = useMemo(
    () => sessions.find((s) => s.session_id === activeId) ?? null,
    [sessions, activeId],
  );

  async function onSend() {
    const text = draft.trim();
    if (!text || chat.isStreaming || !activeId) return;
    setDraft('');
    await chat.send(text);
  }

  // Sending needs a live session (the hook binds its sessionId). A brand-new
  // admin picks a model → "New chat" (which sets activeId) → then types.
  const canChat = !!userToken && !!activeId;

  return (
    <div className="flex h-[calc(100vh-8rem)] gap-4">
      {/* Session + model rail */}
      <aside className="flex w-60 shrink-0 flex-col gap-2 rounded-md border border-border bg-card p-2">
        <div className="text-xs font-medium text-muted-foreground">Model</div>
        <select
          value={selectedModel ?? ''}
          onChange={(e) => sessionsCtl.setSelectedModel(e.target.value || null)}
          className="rounded-sm border border-border bg-background px-2 py-1 text-xs"
        >
          {models.length === 0 && <option value="">No models configured</option>}
          {models.map((m) => (
            <option key={m.user_model_id} value={m.user_model_id}>
              {m.alias || m.provider_model_name} ({m.provider_kind})
            </option>
          ))}
        </select>

        <button
          type="button"
          onClick={() => void sessionsCtl.createSession()}
          disabled={!selectedModel}
          className="mt-1 flex items-center justify-center gap-1 rounded-sm bg-secondary px-2 py-1 text-xs text-secondary-foreground hover:brightness-110 disabled:opacity-50"
        >
          <Plus className="h-3 w-3" /> New chat
        </button>

        <div className="mt-2 text-xs font-medium text-muted-foreground">Sessions</div>
        <div className="flex-1 space-y-0.5 overflow-y-auto">
          {sessions.map((s) => (
            <button
              key={s.session_id}
              type="button"
              onClick={() => sessionsCtl.setActiveId(s.session_id)}
              className={`block w-full truncate rounded-sm px-2 py-1 text-left text-xs ${
                s.session_id === activeId
                  ? 'bg-secondary text-secondary-foreground'
                  : 'text-muted-foreground hover:bg-secondary/60'
              }`}
            >
              {s.title || 'Untitled'}
            </button>
          ))}
          {!loading && sessions.length === 0 && (
            <div className="px-2 py-1 text-[10px] text-muted-foreground">No chats yet.</div>
          )}
        </div>
      </aside>

      {/* Conversation */}
      <section className="flex min-w-0 flex-1 flex-col rounded-md border border-border bg-card">
        <div className="border-b border-border px-4 py-2 text-sm font-medium">
          {activeSession?.title ?? 'System standards assistant'}
        </div>
        <MessageList
          messages={chat.messages}
          streamingText={chat.streamingText}
          isStreaming={chat.isStreaming}
          onResume={chat.submitToolResult}
        />
        {(chat.error || sessErr) && (
          <div className="border-t border-border bg-destructive/10 px-4 py-1 text-xs text-destructive">
            {chat.error || sessErr}
          </div>
        )}
        <div className="flex items-center gap-2 border-t border-border p-2">
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                void onSend();
              }
            }}
            disabled={!canChat || chat.isStreaming}
            placeholder={
              canChat
                ? 'Ask to add/edit a System genre, kind, or attribute…'
                : models.length === 0
                  ? 'Configure a model to start'
                  : 'Click “New chat” to start'
            }
            className="flex-1 rounded-sm border border-border bg-background px-3 py-2 text-sm disabled:opacity-50"
          />
          <button
            type="button"
            onClick={() => void onSend()}
            disabled={!canChat || chat.isStreaming || !draft.trim()}
            className="inline-flex items-center gap-1 rounded-sm bg-primary px-3 py-2 text-sm text-primary-foreground hover:brightness-110 disabled:opacity-50"
          >
            <Send className="h-3.5 w-3.5" />
          </button>
        </div>
      </section>
    </div>
  );
}

// The unified SESSION settings surface (spec 2026-07-05-chat-ai-settings.md G1, §8).
//
// "One place … + a session-scoped subset reachable from chat." The account half shipped;
// this is that subset. It replaces three fragmented surfaces — the old bespoke settings
// panel, the standalone VoiceSettingsPanel, and NewChatDialog's separate preset list —
// with sections that read the SAME cascade the turn resolves:
//
//     Session ▸ Book ▸ Account ▸ System
//
// Every row names the tier that supplied its value (TierChip) and, when this chat
// overrides it, offers "clear · inherit X". Nothing is a silent client-side literal any
// more: the old panel showed `temperature ?? 0.7` while sending the field UNSET, so the
// number on screen was never the number in force.
//
// MVC: this file is the SHELL (chrome + section order). Logic lives in
// `useSessionSettingsEditor`; each section is its own render-only component.
import { useEffect, useRef } from 'react';
import { Settings, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useSessionSettingsEditor } from '@/features/chat-ai-settings/hooks/useSessionSettingsEditor';
import type { ChatSession } from '../types';
import { ModelsSection } from './session-settings/ModelsSection';
import { BehaviorSection } from './session-settings/BehaviorSection';
import { GroundingSection } from './session-settings/GroundingSection';
import { ContextSection } from './session-settings/ContextSection';
import { VoiceSettingsPanel } from './VoiceSettingsPanel';

export type SessionSettingsSection = 'models' | 'behavior' | 'grounding' | 'context' | 'voice';

interface SessionSettingsPanelProps {
  session: ChatSession;
  onSessionUpdate: (updated: ChatSession) => void;
  onClose: () => void;
  /** Deep-link: scroll a section into view on open (the mic button opens 'voice'). */
  initialSection?: SessionSettingsSection;
}

export function SessionSettingsPanel({
  session,
  onSessionUpdate,
  onClose,
  initialSection,
}: SessionSettingsPanelProps) {
  const { t } = useTranslation('chat');
  const panelRef = useRef<HTMLDivElement>(null);
  const ed = useSessionSettingsEditor(session, onSessionUpdate);

  // Close on ESC / click-outside, flushing any debounced edit first — closing the panel
  // mid-debounce must never silently drop the setting the user just changed.
  useEffect(() => {
    const close = () => { void ed.flush().finally(onClose); };
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') close(); };
    const onDown = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) close();
    };
    document.addEventListener('keydown', onKey);
    document.addEventListener('mousedown', onDown);
    return () => {
      document.removeEventListener('keydown', onKey);
      document.removeEventListener('mousedown', onDown);
    };
  }, [ed, onClose]);

  useEffect(() => {
    if (!initialSection) return;
    panelRef.current
      ?.querySelector(`[data-section="${initialSection}"]`)
      ?.scrollIntoView({ block: 'start' });
  }, [initialSection]);

  return (
    <div
      ref={panelRef}
      data-testid="session-settings-panel"
      className="fixed top-0 right-0 bottom-0 z-50 flex w-full flex-col border-l border-border bg-card shadow-[-8px_0_30px_rgba(0,0,0,0.4)] sm:w-[380px]"
    >
      <div className="flex items-center justify-between border-b border-border px-5 py-4">
        <div className="flex items-center gap-2">
          <Settings className="h-4 w-4 text-muted-foreground" />
          <h3 className="text-sm font-semibold">{t('settings.title')}</h3>
          {ed.saving && <span className="text-[10px] text-muted-foreground">saving…</span>}
        </div>
        <button
          type="button"
          onClick={() => void ed.flush().finally(onClose)}
          aria-label="Close"
          className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      <p className="border-b border-border px-5 py-2 text-[10px] text-muted-foreground">
        Settings for <b>this chat</b>. Anything you don&apos;t set here is inherited from the
        book, then your account, then the system default — and each row says which.
      </p>

      {ed.error && (
        <p className="border-b border-border bg-amber-50 px-5 py-2 text-[11px] text-amber-800">
          {ed.error}
        </p>
      )}

      <div className="flex-1 space-y-6 overflow-y-auto p-5">
        <div data-section="models"><ModelsSection ed={ed} /></div>
        <div data-section="behavior"><BehaviorSection ed={ed} /></div>
        <div data-section="grounding"><GroundingSection ed={ed} /></div>
        <div data-section="context"><ContextSection ed={ed} /></div>

        {/* Voice folded in (spec §8 "VoiceSettingsPanel → Voice sub-panel"). Rendered
            embedded: same controls, no second slide-over fighting this one for the edge. */}
        <div data-section="voice">
          <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Voice
          </h4>
          <VoiceSettingsPanel open embedded onClose={onClose} />
        </div>

        <section className="rounded border border-border p-3 text-[11px] text-muted-foreground">
          <div className="flex justify-between"><span>Messages</span><span>{session.message_count}</span></div>
          <div className="flex justify-between"><span>Status</span><span>{session.status}</span></div>
        </section>
      </div>
    </div>
  );
}

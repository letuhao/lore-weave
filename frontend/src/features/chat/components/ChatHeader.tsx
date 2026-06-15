import { useEffect, useRef, useState } from 'react';
import { Download, Menu, Pencil, Settings, Mic, SlidersHorizontal } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { SPEECH_RECOGNITION_SUPPORTED } from '@/hooks/useSpeechRecognition';
import { MEDIA_RECORDER_SUPPORTED } from '@/hooks/useBackendSTT';
import { cn } from '@/lib/utils';
import { MemoryIndicator } from '@/features/knowledge/components/MemoryIndicator';
import { chatApi } from '../api';
import type { ChatSession } from '../types';

interface ChatHeaderProps {
  session: ChatSession;
  modelNameMap?: Map<string, string>;
  /** Actual message count from loaded messages (overrides session.message_count which may be stale) */
  messageCount?: number;
  onRename?: () => void;
  onOpenSettings?: () => void;
  isVoiceModeActive?: boolean;
  onToggleVoiceMode?: () => void;
  onOpenVoiceSettings?: () => void;
  /** Mobile: open session sidebar */
  onOpenSidebar?: () => void;
}

export function ChatHeader({ session, modelNameMap, messageCount, onRename, onOpenSettings, isVoiceModeActive, onToggleVoiceMode, onOpenVoiceSettings, onOpenSidebar }: ChatHeaderProps) {
  const { t } = useTranslation('chat');
  // Self-measure: when the header (its container) is narrow — e.g. the editor
  // AI panel at ~300px — collapse the memory chip to icon-only so the action
  // buttons stay visible. A manual container query (no plugin needed); works
  // regardless of viewport width, unlike md:* breakpoints.
  const rootRef = useRef<HTMLDivElement>(null);
  const [compact, setCompact] = useState(false);
  useEffect(() => {
    const el = rootRef.current;
    if (!el || typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver(([entry]) => setCompact(entry.contentRect.width < 380));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  function handleExport(format: 'markdown' | 'json') {
    const url = chatApi.exportUrl(session.session_id, format);
    window.open(url, '_blank');
  }

  return (
    <div ref={rootRef} className="flex shrink-0 items-center justify-between gap-2 border-b border-border bg-card px-3 py-3 md:px-6">
      <div className="flex min-w-0 items-center gap-2">
        {onOpenSidebar && (
          <button
            type="button"
            onClick={onOpenSidebar}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-muted md:hidden"
            aria-label={t('header.open_conversations')}
          >
            <Menu className="h-5 w-5" />
          </button>
        )}
        <div className="min-w-0">
        <h2 className="truncate text-sm font-semibold text-foreground">{session.title}</h2>
        <p className="mt-0.5 truncate text-[11px] text-muted-foreground">
          {modelNameMap?.get(session.model_ref) ?? (session.model_source === 'user_model' ? t('header.my_model') : t('header.platform'))} &middot;{' '}
          {t('header.messages', { count: messageCount ?? session.message_count })}
          {session.status === 'archived' && (
            <span className="ml-1.5 rounded bg-secondary px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
              {t('header.archived')}
            </span>
          )}
        </p>
        </div>
      </div>
      <div className="flex min-w-0 shrink-0 items-center gap-1">
        <MemoryIndicator projectId={session.project_id} memoryMode={session.memory_mode} compact={compact} />
        {(SPEECH_RECOGNITION_SUPPORTED || MEDIA_RECORDER_SUPPORTED) && onToggleVoiceMode && session.status !== 'archived' && (
          <button
            type="button"
            onClick={onToggleVoiceMode}
            title={t('header.voice_mode')}
            aria-label={t('header.voice_mode')}
            aria-pressed={isVoiceModeActive}
            className={cn(
              'rounded-md p-2 transition-colors',
              isVoiceModeActive
                ? 'bg-primary/10 text-primary'
                : 'text-muted-foreground hover:bg-secondary hover:text-foreground',
            )}
          >
            <Mic className="h-4 w-4" />
          </button>
        )}
        {onOpenVoiceSettings && session.status !== 'archived' && (
          <button
            type="button"
            onClick={onOpenVoiceSettings}
            title={t('header.voice_settings')}
            className="rounded-md p-2 text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors"
          >
            <SlidersHorizontal className="h-4 w-4" />
          </button>
        )}
        <button
          type="button"
          onClick={() => handleExport('markdown')}
          title={t('header.export')}
          className="rounded-md p-2 text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors"
        >
          <Download className="h-4 w-4" />
        </button>
        {onRename && (
          <button
            type="button"
            onClick={onRename}
            title={t('header.rename')}
            className="rounded-md p-2 text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors"
          >
            <Pencil className="h-4 w-4" />
          </button>
        )}
        {onOpenSettings && (
          <button
            type="button"
            onClick={onOpenSettings}
            data-testid="chat-session-settings-button"
            title={t('header.session_settings')}
            className="rounded-md p-2 text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors"
          >
            <Settings className="h-4 w-4" />
          </button>
        )}
      </div>
    </div>
  );
}

import { Download, Menu, Pencil, Settings, Mic, SlidersHorizontal } from 'lucide-react';
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
  function handleExport(format: 'markdown' | 'json') {
    const url = chatApi.exportUrl(session.session_id, format);
    window.open(url, '_blank');
  }

  return (
    <div className="flex shrink-0 items-center justify-between border-b border-border bg-card px-3 py-3 md:px-6">
      <div className="flex items-center gap-2">
        {onOpenSidebar && (
          <button
            type="button"
            onClick={onOpenSidebar}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-muted md:hidden"
            aria-label="Open conversations"
          >
            <Menu className="h-5 w-5" />
          </button>
        )}
        <div>
        <h2 className="text-sm font-semibold text-foreground">{session.title}</h2>
        <p className="mt-0.5 text-[11px] text-muted-foreground">
          {modelNameMap?.get(session.model_ref) ?? (session.model_source === 'user_model' ? 'My Model' : 'Platform')} &middot;{' '}
          {messageCount ?? session.message_count} message{(messageCount ?? session.message_count) !== 1 ? 's' : ''}
          {session.status === 'archived' && (
            <span className="ml-1.5 rounded bg-secondary px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
              Archived
            </span>
          )}
        </p>
        </div>
      </div>
      <div className="flex items-center gap-1.5">
        <MemoryIndicator projectId={session.project_id} memoryMode={session.memory_mode} />
        {(SPEECH_RECOGNITION_SUPPORTED || MEDIA_RECORDER_SUPPORTED) && onToggleVoiceMode && session.status !== 'archived' && (
          <button
            type="button"
            onClick={onToggleVoiceMode}
            title="Voice Mode"
            aria-label="Voice Mode"
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
            title="Voice Settings"
            className="rounded-md p-2 text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors"
          >
            <SlidersHorizontal className="h-4 w-4" />
          </button>
        )}
        <button
          type="button"
          onClick={() => handleExport('markdown')}
          title="Export"
          className="rounded-md p-2 text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors"
        >
          <Download className="h-4 w-4" />
        </button>
        {onRename && (
          <button
            type="button"
            onClick={onRename}
            title="Rename"
            className="rounded-md p-2 text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors"
          >
            <Pencil className="h-4 w-4" />
          </button>
        )}
        {onOpenSettings && (
          <button
            type="button"
            onClick={onOpenSettings}
            title="Session Settings"
            className="rounded-md p-2 text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors"
          >
            <Settings className="h-4 w-4" />
          </button>
        )}
      </div>
    </div>
  );
}

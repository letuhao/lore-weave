import { BookOpen, GitCompare, RefreshCw } from 'lucide-react';
import type { LanguageVersionGroup, VersionSummary } from '../api';
import { cn } from '@/lib/utils';

const STATUS_STYLES: Record<string, string> = {
  completed: 'text-[#3dba6a]',
  running: 'text-[#5496e8]',
  failed: 'text-[#dc4e4e]',
  pending: 'text-muted-foreground',
};

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

interface VersionSidebarProps {
  chapterTitle: string;
  originalLanguage?: string;
  wordCount?: number;
  languages: LanguageVersionGroup[];
  selectedLang: string | null;
  selectedVersionId: string | null;
  onLangChange: (lang: string | null) => void;
  onVersionSelect: (id: string) => void;
  onRetranslate: () => void;
  onCompareToggle: () => void;
  compareMode: boolean;
}

export function VersionSidebar({
  chapterTitle,
  originalLanguage,
  wordCount,
  languages,
  selectedLang,
  selectedVersionId,
  onLangChange,
  onVersionSelect,
  onRetranslate,
  onCompareToggle,
  compareMode,
}: VersionSidebarProps) {
  const selectedGroup = languages.find((g) => g.target_language === selectedLang);

  return (
    <div className="flex h-full w-[240px] shrink-0 flex-col border-r border-border bg-card">
      {/* Chapter info */}
      <div className="border-b border-border px-4 py-3">
        <h2 className="font-serif text-sm font-semibold leading-tight">{chapterTitle}</h2>
        <p className="mt-1 text-[10px] text-muted-foreground">
          {wordCount ? `${wordCount.toLocaleString()} words` : ''}
          {wordCount && originalLanguage ? ' · ' : ''}
          {originalLanguage ?? ''}
        </p>
      </div>

      {/* Language tabs */}
      <div className="px-3 py-2.5">
        <p className="mb-1.5 text-[9px] font-semibold uppercase tracking-wider text-muted-foreground">Languages</p>
        <div className="flex flex-col gap-1">
          {/* Original */}
          <button
            type="button"
            onClick={() => onLangChange(null)}
            className={cn(
              'flex items-center gap-2 rounded-md px-3 py-2 text-xs font-medium transition-colors',
              selectedLang === null
                ? 'bg-primary/10 text-primary'
                : 'text-muted-foreground hover:bg-secondary',
            )}
          >
            <span className="font-mono text-[10px] opacity-60">{originalLanguage ?? '??'}</span>
            Original
          </button>

          {/* Target languages */}
          {languages.map((g) => (
            <button
              key={g.target_language}
              type="button"
              onClick={() => onLangChange(g.target_language)}
              className={cn(
                'flex items-center justify-between rounded-md px-3 py-2 text-xs font-medium transition-colors',
                selectedLang === g.target_language
                  ? 'border border-accent/20 bg-accent/5 text-accent'
                  : 'text-muted-foreground hover:bg-secondary',
              )}
            >
              <span className="flex items-center gap-2">
                <span className="font-mono text-[10px] opacity-60">{g.target_language}</span>
                {g.target_language}
              </span>
              <span className={cn('text-[9px]', g.versions.some((v) => v.status === 'running') ? 'text-[#5496e8]' : 'text-muted-foreground')}>
                {g.versions.some((v) => v.status === 'running') ? 'running' : `${g.versions.length} ver`}
              </span>
            </button>
          ))}
        </div>
      </div>

      {/* Versions for selected language */}
      {selectedGroup && (
        <div className="flex-1 overflow-y-auto px-3 pb-3">
          <p className="mb-1.5 text-[9px] font-semibold uppercase tracking-wider text-muted-foreground">
            {selectedGroup.target_language} Versions
          </p>
          <div className="flex flex-col gap-1">
            {selectedGroup.versions.map((v) => (
              <button
                key={v.id}
                type="button"
                onClick={() => onVersionSelect(v.id)}
                className={cn(
                  'flex items-center justify-between rounded-md border px-2.5 py-2 text-left transition-colors',
                  selectedVersionId === v.id
                    ? 'border-accent/20 bg-accent/5'
                    : 'border-transparent hover:bg-card-foreground/5',
                )}
              >
                <div>
                  <p className="text-xs font-medium">v{v.version_num}</p>
                  <p className="text-[9px] text-muted-foreground">
                    {v.model_source === 'user_model' ? 'User model' : v.model_ref?.slice(0, 8) ?? '?'}
                    {' · '}
                    {relativeTime(v.created_at)}
                  </p>
                </div>
                <div className="flex items-center gap-1.5">
                  <span className={cn('text-[9px] font-medium', STATUS_STYLES[v.status] ?? 'text-muted-foreground')}>
                    {v.status}
                  </span>
                  {v.is_active && (
                    <span className="rounded-full bg-[#3dba6a]/10 px-1.5 py-0.5 text-[8px] font-medium text-[#3dba6a]">
                      Active
                    </span>
                  )}
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Actions */}
      <div className="flex flex-col gap-1.5 border-t border-border p-3">
        <button
          type="button"
          onClick={onRetranslate}
          className="flex w-full items-center justify-center gap-1.5 rounded-md bg-accent px-3 py-2 text-xs font-medium text-white transition-colors hover:brightness-110"
        >
          <RefreshCw className="h-3 w-3" />
          Re-translate
        </button>
        <button
          type="button"
          onClick={onCompareToggle}
          className={cn(
            'flex w-full items-center justify-center gap-1.5 rounded-md border px-3 py-2 text-xs font-medium transition-colors',
            compareMode
              ? 'border-accent/30 bg-accent/10 text-accent'
              : 'border-border text-foreground hover:bg-secondary',
          )}
        >
          <GitCompare className="h-3 w-3" />
          {compareMode ? 'Exit Compare' : 'Compare Mode'}
        </button>
      </div>
    </div>
  );
}

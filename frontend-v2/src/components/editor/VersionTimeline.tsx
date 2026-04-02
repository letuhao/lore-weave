import { RotateCcw, Download, Trash2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { MediaVersion } from '@/features/books/api';

interface VersionTimelineProps {
  versions: MediaVersion[];
  selectedId: string | null;
  onSelect: (version: MediaVersion) => void;
  onRestore: (version: MediaVersion) => void;
  onDownload: (version: MediaVersion) => void;
  onDelete: (version: MediaVersion) => void;
}

const TAG_STYLES: Record<string, string> = {
  prompt: 'bg-info/10 text-info',
  media: 'bg-warning/10 text-warning',
  caption: 'bg-secondary text-secondary-foreground',
  regenerated: 'bg-warning/10 text-warning',
  'first generation': 'bg-warning/10 text-warning',
  'prompt added': 'bg-info/10 text-info',
  upload: 'bg-success/10 text-success',
  manual: 'bg-accent/10 text-accent-foreground',
};

function formatTimeAgo(dateStr: string): string {
  const now = Date.now();
  const then = new Date(dateStr).getTime();
  const diff = now - then;
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days === 1) return 'Yesterday';
  if (days < 7) return `${days} days ago`;
  return new Date(dateStr).toLocaleDateString();
}

function formatSize(bytes: number | null): string {
  if (!bytes) return '';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function VersionTimeline({
  versions,
  selectedId,
  onSelect,
  onRestore,
  onDownload,
  onDelete,
}: VersionTimelineProps) {
  const selected = versions.find((v) => v.id === selectedId);
  const isLatest = selected?.id === versions[0]?.id;

  return (
    <div className="flex w-[340px] flex-shrink-0 flex-col border-l bg-card">
      {/* Header */}
      <div className="flex items-center justify-between border-b px-3.5 py-3">
        <div className="flex items-center gap-1.5 text-xs font-semibold">
          Versions
        </div>
        <span className="rounded-full bg-secondary px-2 py-0.5 text-[10px] text-muted-foreground">
          {versions.length}
        </span>
      </div>

      {/* Timeline */}
      <div className="flex-1 overflow-y-auto">
        {versions.map((v, i) => (
          <div
            key={v.id}
            className={cn(
              'relative cursor-pointer border-b px-3.5 py-3 pl-8 transition-colors',
              v.id === selectedId
                ? 'bg-primary/5'
                : 'hover:bg-card-hover',
            )}
            onClick={() => onSelect(v)}
          >
            {/* Selected indicator */}
            {v.id === selectedId && (
              <div className="absolute bottom-0 left-0 top-0 w-0.5 bg-primary" />
            )}

            {/* Timeline dot */}
            <div
              className={cn(
                'absolute left-3 top-4 h-2.5 w-2.5 rounded-full border-2',
                v.id === selectedId
                  ? 'border-primary bg-primary'
                  : 'border-border bg-card',
              )}
            />
            {/* Timeline line */}
            {i < versions.length - 1 && (
              <div className="absolute bottom-0 left-[17px] top-7 w-px bg-border" />
            )}

            {/* Content */}
            <div className="text-xs font-medium">{getVersionTitle(v)}</div>
            <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[10px] text-muted-foreground">
              <span>{formatTimeAgo(v.created_at)}</span>
              {v.changes.map((change) => (
                <span
                  key={change}
                  className={cn(
                    'rounded px-1.5 py-px text-[9px] font-medium',
                    TAG_STYLES[change] || 'bg-secondary text-muted-foreground',
                  )}
                >
                  {change}
                </span>
              ))}
              {v.action !== 'upload' && (
                <span
                  className={cn(
                    'rounded px-1.5 py-px text-[9px] font-medium',
                    TAG_STYLES[v.action] || 'bg-secondary text-muted-foreground',
                  )}
                >
                  {v.action.replace('_', ' ')}
                </span>
              )}
            </div>
            {v.prompt_snapshot && (
              <div className="mt-1 truncate text-[10px] text-muted-foreground/60">
                {v.prompt_snapshot.slice(0, 80)}
                {v.prompt_snapshot.length > 80 ? '...' : ''}
              </div>
            )}
            {v.ai_model && (
              <div className="mt-0.5 font-mono text-[9px] text-muted-foreground/40">
                {v.ai_model}
                {v.size_bytes ? ` · ${formatSize(v.size_bytes)}` : ''}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Action bar */}
      {selected && (
        <div className="flex gap-1.5 border-t px-3.5 py-2.5">
          {!isLatest && (
            <button
              type="button"
              onClick={() => onRestore(selected)}
              className="flex flex-1 items-center justify-center gap-1.5 rounded border border-accent/30 bg-accent-muted px-2 py-1 text-[10px] font-medium text-accent-foreground transition-colors hover:bg-accent hover:text-white"
            >
              <RotateCcw className="h-3 w-3" />
              Restore v{selected.version}
            </button>
          )}
          {selected.media_url && (
            <a
              href={selected.media_url}
              download
              onClick={(e) => {
                e.stopPropagation();
                onDownload(selected);
              }}
              className="flex items-center gap-1 rounded px-2 py-1 text-[10px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
            >
              <Download className="h-3 w-3" />
            </a>
          )}
          {!isLatest && (
            <button
              type="button"
              onClick={() => onDelete(selected)}
              className="flex items-center gap-1 rounded px-2 py-1 text-[10px] text-destructive transition-colors hover:bg-destructive/10"
            >
              <Trash2 className="h-3 w-3" />
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function getVersionTitle(v: MediaVersion): string {
  switch (v.action) {
    case 'upload': return 'Media uploaded';
    case 'regenerate': return 'Re-generated with refined prompt';
    case 'caption_edit': return 'Caption updated';
    case 'prompt_edit': return 'Prompt updated';
    default: return v.action.replace(/_/g, ' ');
  }
}

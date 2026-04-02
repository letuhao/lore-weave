import { ArrowLeft, X, ImageIcon, Loader2 } from 'lucide-react';
import { useState, useEffect, useCallback } from 'react';
import { booksApi, type MediaVersion } from '@/features/books/api';
import { VersionTimeline } from './VersionTimeline';
import { PromptDiff } from './PromptDiff';
import { cn } from '@/lib/utils';

interface VersionHistoryPanelProps {
  token: string;
  bookId: string;
  chapterId: string;
  blockId: string;
  blockTitle: string;         // e.g. "throne-room-concept.png"
  currentMediaUrl: string | null;
  onClose: () => void;
  onRestore: (version: MediaVersion) => void;  // caller updates block attrs
}

function formatSize(bytes: number | null): string {
  if (!bytes) return '';
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function VersionHistoryPanel({
  token, bookId, chapterId, blockId, blockTitle,
  currentMediaUrl, onClose, onRestore,
}: VersionHistoryPanelProps) {
  const [versions, setVersions] = useState<MediaVersion[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  // Fetch versions
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    booksApi.listMediaVersions(token, bookId, chapterId, blockId).then(
      (data) => {
        if (cancelled) return;
        setVersions(data.items);
        if (data.items.length > 0) setSelectedId(data.items[0].id);
        setLoading(false);
      },
      (err) => {
        if (cancelled) return;
        setError(err.message);
        setLoading(false);
      },
    );
    return () => { cancelled = true; };
  }, [token, bookId, chapterId, blockId]);

  const selected = versions.find((v) => v.id === selectedId) ?? null;
  const latest = versions[0] ?? null;

  // Find the version just before the selected one (for comparison)
  const selectedIdx = versions.findIndex((v) => v.id === selectedId);
  const compareWith = selectedIdx >= 0 && selectedIdx < versions.length - 1 ? versions[selectedIdx + 1] : null;

  const handleRestore = useCallback(
    (version: MediaVersion) => {
      onRestore(version);
    },
    [onRestore],
  );

  const handleDelete = useCallback(
    async (version: MediaVersion) => {
      if (!confirm(`Delete version ${version.version}? This cannot be undone.`)) return;
      try {
        await booksApi.deleteMediaVersion(token, bookId, chapterId, version.id);
        setVersions((prev) => prev.filter((v) => v.id !== version.id));
        if (selectedId === version.id) {
          setSelectedId(versions[0]?.id !== version.id ? versions[0]?.id : versions[1]?.id ?? null);
        }
      } catch (err: any) {
        setError(err.message);
      }
    },
    [token, bookId, chapterId, selectedId, versions],
  );

  const handleDownload = useCallback((_version: MediaVersion) => {
    // Download is handled by the <a download> in VersionTimeline — this is a no-op callback
  }, []);

  // Stats
  const totalSize = versions.reduce((sum, v) => sum + (v.size_bytes ?? 0), 0);

  if (loading) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-3 text-muted-foreground">
        <Loader2 className="h-6 w-6 animate-spin" />
        <span className="text-xs">Loading version history...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-3 text-muted-foreground">
        <span className="text-xs text-destructive">{error}</span>
        <button type="button" onClick={onClose} className="text-xs underline">Close</button>
      </div>
    );
  }

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      {/* Toolbar */}
      <div className="flex h-[42px] flex-shrink-0 items-center justify-between border-b bg-card px-4">
        <div className="flex items-center gap-2">
          <button type="button" onClick={onClose} className="rounded p-1 text-muted-foreground hover:bg-secondary hover:text-foreground">
            <ArrowLeft className="h-3.5 w-3.5" />
          </button>
          <span className="text-xs">
            <span className="text-muted-foreground">Block &rsaquo;</span>{' '}
            <strong>Version History</strong>
          </span>
        </div>
        <button type="button" onClick={onClose} className="flex items-center gap-1 rounded px-2 py-1 text-xs text-muted-foreground hover:bg-secondary hover:text-foreground">
          <X className="h-3 w-3" /> Close
        </button>
      </div>

      {/* Panel area */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left: preview + comparison */}
        <div className="flex flex-1 flex-col overflow-hidden">
          {/* Preview header */}
          <div className="flex items-center gap-2.5 border-b px-5 py-3 text-xs">
            <ImageIcon className="h-3.5 w-3.5 text-primary" />
            <span className="font-semibold">{blockTitle}</span>
            {selected && compareWith && (
              <span className="text-muted-foreground">
                Comparing v{compareWith.version} → v{selected.version}
              </span>
            )}
          </div>

          {/* Side-by-side comparison */}
          <div className="flex flex-1 overflow-hidden">
            {selected && compareWith ? (
              <div className="flex flex-1 gap-px bg-border">
                {/* Old version */}
                <div className="flex flex-1 flex-col bg-background">
                  <div className="flex items-center justify-between border-b px-3.5 py-2 text-[10px] font-semibold">
                    <span><span className="font-mono">v{compareWith.version}</span> — Previous</span>
                    <span className="rounded bg-secondary px-1.5 py-px text-[9px] text-muted-foreground">old</span>
                  </div>
                  <div className="flex flex-1 items-center justify-center p-4">
                    {compareWith.media_url ? (
                      <img src={compareWith.media_url} alt={`Version ${compareWith.version}`} className="max-h-full max-w-full rounded-md" />
                    ) : (
                      <div className="flex flex-col items-center gap-2 text-muted-foreground">
                        <ImageIcon className="h-8 w-8 opacity-20" />
                        <span className="text-[10px]">No media</span>
                      </div>
                    )}
                  </div>
                </div>
                {/* Current/selected version */}
                <div className="flex flex-1 flex-col bg-background">
                  <div className="flex items-center justify-between border-b px-3.5 py-2 text-[10px] font-semibold">
                    <span><span className="font-mono">v{selected.version}</span> — {selected.id === latest?.id ? 'Current' : 'Selected'}</span>
                    <span className={cn(
                      'rounded px-1.5 py-px text-[9px]',
                      selected.id === latest?.id ? 'bg-success/10 text-success' : 'bg-info/10 text-info',
                    )}>
                      {selected.id === latest?.id ? 'current' : `v${selected.version}`}
                    </span>
                  </div>
                  <div className="flex flex-1 items-center justify-center p-4">
                    {selected.media_url ? (
                      <img src={selected.media_url} alt={`Version ${selected.version}`} className="max-h-full max-w-full rounded-md" />
                    ) : (
                      <div className="flex flex-col items-center gap-2 text-muted-foreground">
                        <ImageIcon className="h-8 w-8 opacity-20" />
                        <span className="text-[10px]">No media</span>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ) : selected ? (
              /* Single version — show just the image */
              <div className="flex flex-1 items-center justify-center bg-background p-4">
                {selected.media_url ? (
                  <img src={selected.media_url} alt={`Version ${selected.version}`} className="max-h-full max-w-full rounded-md" />
                ) : (
                  <div className="flex flex-col items-center gap-2 text-muted-foreground">
                    <ImageIcon className="h-8 w-8 opacity-20" />
                    <span className="text-xs">No media in this version</span>
                  </div>
                )}
              </div>
            ) : (
              <div className="flex flex-1 items-center justify-center text-xs text-muted-foreground">
                No versions yet
              </div>
            )}
          </div>

          {/* Prompt diff (below the image comparison) */}
          {selected && compareWith && (selected.prompt_snapshot || compareWith.prompt_snapshot) && (
            <PromptDiff
              oldPrompt={compareWith.prompt_snapshot || ''}
              newPrompt={selected.prompt_snapshot || ''}
              oldLabel={`v${compareWith.version}`}
              newLabel={`v${selected.version}`}
            />
          )}
        </div>

        {/* Right: version timeline */}
        <VersionTimeline
          versions={versions}
          selectedId={selectedId}
          onSelect={(v) => setSelectedId(v.id)}
          onRestore={handleRestore}
          onDownload={handleDownload}
          onDelete={handleDelete}
        />
      </div>

      {/* Bottom bar */}
      <div className="flex h-7 flex-shrink-0 items-center justify-between border-t bg-card px-4 text-[10px] text-muted-foreground">
        <span>
          {blockTitle} · {versions.length} version{versions.length !== 1 ? 's' : ''}
          {totalSize > 0 ? ` · ${formatSize(totalSize)} total` : ''}
        </span>
        <span>MinIO: books/{bookId}/chapters/{chapterId}/{blockId}/</span>
      </div>
    </div>
  );
}

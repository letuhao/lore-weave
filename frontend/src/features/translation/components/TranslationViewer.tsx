import { useEffect, useState } from 'react';
import { Check, Copy } from 'lucide-react';
import { toast } from 'sonner';
import { versionsApi, type ChapterTranslation } from '../api';
import { useAuth } from '@/auth';
import { ContentRenderer } from '@/components/reader/ContentRenderer';

interface TranslationViewerProps {
  chapterId: string;
  versionId: string;
  isActive: boolean;
  onSetActive: (versionId: string) => void;
}

export function TranslationViewer({ chapterId, versionId, isActive, onSetActive }: TranslationViewerProps) {
  const { accessToken } = useAuth();
  const [version, setVersion] = useState<ChapterTranslation | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!accessToken || !versionId) return;
    let mounted = true;
    setLoading(true);
    versionsApi.getChapterVersion(accessToken, chapterId, versionId)
      .then((data) => { if (mounted) setVersion(data); })
      .catch((e) => { if (mounted) toast.error(`Failed to load version: ${(e as Error).message}`); })
      .finally(() => { if (mounted) setLoading(false); });
    return () => { mounted = false; };
  }, [accessToken, chapterId, versionId]);

  async function handleCopy() {
    if (!version?.translated_body) return;
    await navigator.clipboard.writeText(version.translated_body);
    toast.success('Copied to clipboard');
  }

  async function handleSetActive() {
    if (!accessToken) return;
    try {
      await versionsApi.setActiveVersion(accessToken, chapterId, versionId);
      onSetActive(versionId);
      toast.success('Set as active version');
    } catch (e) {
      toast.error(`Failed: ${(e as Error).message}`);
    }
  }

  if (loading) {
    return (
      <div className="flex flex-1 flex-col">
        <div className="border-b border-border px-5 py-3">
          <div className="h-4 w-48 animate-pulse rounded bg-muted" />
        </div>
        <div className="flex-1 p-6">
          <div className="mx-auto max-w-[680px] space-y-3">
            <div className="h-4 w-full animate-pulse rounded bg-muted" />
            <div className="h-4 w-5/6 animate-pulse rounded bg-muted" />
            <div className="h-4 w-4/6 animate-pulse rounded bg-muted" />
          </div>
        </div>
      </div>
    );
  }

  if (!version) {
    return (
      <div className="flex flex-1 items-center justify-center text-sm text-muted-foreground">
        Version not found.
      </div>
    );
  }

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      {/* Toolbar */}
      <div className="flex items-center justify-between border-b border-border px-5 py-2.5 shrink-0">
        <div className="flex items-center gap-2.5">
          <h3 className="text-[13px] font-semibold">
            {version.target_language} &mdash; v{version.version_num ?? '?'}
          </h3>
          <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${
            version.status === 'completed' ? 'bg-[#3dba6a]/10 text-[#3dba6a]'
            : version.status === 'running' ? 'bg-[#5496e8]/10 text-[#5496e8]'
            : version.status === 'failed' ? 'bg-[#dc4e4e]/10 text-[#dc4e4e]'
            : 'bg-secondary text-muted-foreground'
          }`}>
            {version.status}
          </span>
          {isActive && (
            <span className="flex items-center gap-1 rounded-full border border-[#3dba6a]/15 bg-[#3dba6a]/10 px-2 py-0.5 text-[10px] font-medium text-[#3dba6a]">
              <Check className="h-2.5 w-2.5" />
              Active
            </span>
          )}
          {version.translated_body_format === 'json' ? (
            <span className="rounded-full bg-[#8b5cf6]/10 px-2 py-0.5 text-[10px] font-medium text-[#8b5cf6]">
              Block {Array.isArray(version.translated_body_json) ? `(${version.translated_body_json.length})` : ''}
            </span>
          ) : version.status === 'completed' && (
            <span className="rounded-full bg-secondary px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
              Text
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {version.input_tokens != null && (
            <span className="font-mono text-[10px] text-muted-foreground">
              &uarr;{version.input_tokens?.toLocaleString()} &darr;{version.output_tokens?.toLocaleString()}
            </span>
          )}
          <button
            type="button"
            onClick={handleCopy}
            disabled={!version.translated_body}
            className="flex items-center gap-1 rounded px-2 py-1 text-[11px] text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors disabled:opacity-30"
          >
            <Copy className="h-3 w-3" />
            Copy
          </button>
          {version.status === 'completed' && !isActive && (
            <button
              type="button"
              onClick={handleSetActive}
              className="flex items-center gap-1 rounded px-2 py-1 text-[11px] text-accent hover:bg-accent/10 transition-colors"
            >
              <Check className="h-3 w-3" />
              Set Active
            </button>
          )}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-6">
        {version.translated_body_format === 'json' && Array.isArray(version.translated_body_json) ? (
          <div className="mx-auto max-w-[680px]">
            <ContentRenderer blocks={version.translated_body_json as any} />
          </div>
        ) : version.translated_body ? (
          <div className="mx-auto max-w-[680px] whitespace-pre-wrap font-serif text-[15px] leading-[1.9] text-foreground/90">
            {version.translated_body}
          </div>
        ) : (
          <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
            {version.status === 'running' ? 'Translation in progress...'
              : version.status === 'failed' ? `Translation failed: ${version.error_message || 'Unknown error'}`
              : 'No translated content available.'}
          </div>
        )}
      </div>
    </div>
  );
}

import { useEffect, useState } from 'react';
import type { ChapterTranslation } from '@/features/translation/api';
import type { VersionSummary } from '@/features/translation/versionsApi';
import { versionsApi } from '@/features/translation/versionsApi';
import { Skeleton } from '@/components/ui/skeleton';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';

type Props = {
  token: string;
  chapterId: string;
  /** The version whose content to display (null = show original placeholder) */
  version: VersionSummary | null;
  isActiveVersion: boolean;
  onSetActive: (versionId: string) => void;
  onToggleCompare: () => void;
  compareMode: boolean;
};

export function TranslationViewer({
  token,
  chapterId,
  version,
  isActiveVersion,
  onSetActive,
  onToggleCompare,
  compareMode,
}: Props) {
  const [ct, setCt] = useState<ChapterTranslation | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [settingActive, setSettingActive] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!version) { setCt(null); return; }
    setLoading(true);
    setError('');
    versionsApi.getChapterVersion(token, chapterId, version.id)
      .then(setCt)
      .catch((e) => setError(e.message || 'Failed to load'))
      .finally(() => setLoading(false));
  }, [token, chapterId, version?.id]);

  async function handleSetActive() {
    if (!version) return;
    setSettingActive(true);
    try {
      await versionsApi.setActiveVersion(token, chapterId, version.id);
      onSetActive(version.id);
    } catch (e) {
      setError((e as Error).message || 'Failed to set active');
    } finally {
      setSettingActive(false);
    }
  }

  function handleCopy() {
    if (ct?.translated_body) {
      void navigator.clipboard.writeText(ct.translated_body);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  }

  return (
    <div className="flex h-full flex-col gap-3">
      {/* Action bar */}
      {version && (
        <div className="flex flex-wrap items-center gap-2">
          <Button
            size="sm"
            variant={compareMode ? 'default' : 'outline'}
            onClick={onToggleCompare}
          >
            {compareMode ? 'Exit compare' : 'Compare with original'}
          </Button>
          {!isActiveVersion && version.status === 'completed' && (
            <Button size="sm" onClick={handleSetActive} disabled={settingActive}>
              {settingActive ? 'Saving…' : 'Set as active'}
            </Button>
          )}
          {isActiveVersion && (
            <span className="text-xs font-medium text-green-600">● Active version</span>
          )}
          {ct?.translated_body && (
            <button
              onClick={handleCopy}
              className="text-xs text-muted-foreground hover:text-foreground"
            >
              {copied ? 'Copied!' : 'Copy text'}
            </button>
          )}
          {ct?.input_tokens != null && ct?.output_tokens != null && (
            <span className="ml-auto text-xs text-muted-foreground">
              {ct.input_tokens} → {ct.output_tokens} tokens
            </span>
          )}
        </div>
      )}

      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        {loading && <Skeleton className="h-64 w-full" />}
        {!loading && !version && (
          <p className="text-sm text-muted-foreground">Select a language and version to view the translation.</p>
        )}
        {!loading && version && ct && (
          <>
            {(ct.status === 'pending' || ct.status === 'running') && (
              <p className="text-sm text-muted-foreground">Processing…</p>
            )}
            {ct.status === 'failed' && (
              <Alert variant="destructive">
                <AlertDescription>{ct.error_message || 'Translation failed'}</AlertDescription>
              </Alert>
            )}
            {ct.status === 'completed' && ct.translated_body && (
              <div className="whitespace-pre-wrap rounded border bg-muted p-4 text-sm leading-relaxed">
                {ct.translated_body}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

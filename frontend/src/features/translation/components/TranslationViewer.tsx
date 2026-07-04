import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Check, Copy, SplitSquareVertical, AlertTriangle, History, Pencil, X } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { versionsApi, type ChapterTranslation } from '../api';
import { useAuth } from '@/auth';
import { ContentRenderer } from '@/components/reader/ContentRenderer';
import { ConfirmDialog } from '@/components/shared/ConfirmDialog';
import { TiptapEditor } from '@/components/editor/TiptapEditor';
import { useEditTranslation } from '../hooks/useEditTranslation';

interface TranslationViewerProps {
  bookId?: string;
  chapterId: string;
  versionId: string;
  isActive: boolean;
  onSetActive: (versionId: string) => void;
  // M7c-2: a human edit saved a new version — let the parent refresh/select it.
  onSaved?: (saved: ChapterTranslation) => void;
  // #16 Phase 3 DOCK-7 fix — when embedded in the Studio `translation-versions` dock panel, a
  // full-page `navigate()` to the review route would tear the whole studio down. Optional so the
  // classic route (ChapterTranslationsPage) and the legacy editor's Translate workmode, neither of
  // which pass it, keep navigating exactly as before.
  onReview?: (versionId: string) => void;
}

export function TranslationViewer({ bookId, chapterId, versionId, isActive, onSetActive, onSaved, onReview }: TranslationViewerProps) {
  const { t } = useTranslation('translation');
  const navigate = useNavigate();
  const { accessToken } = useAuth();
  const [version, setVersion] = useState<ChapterTranslation | null>(null);
  const [loading, setLoading] = useState(true);
  const [confirmOpen, setConfirmOpen] = useState(false);

  // M7c-2: human-edit controller. Saving creates a new human version (gold).
  const edit = useEditTranslation(chapterId, version, (saved) => {
    setVersion(saved);
    onSaved?.(saved);
  });

  useEffect(() => {
    if (!accessToken || !versionId) return;
    let mounted = true;
    setLoading(true);
    versionsApi.getChapterVersion(accessToken, chapterId, versionId)
      .then((data) => { if (mounted) setVersion(data); })
      .catch((e) => { if (mounted) toast.error(t('viewer.load_failed', { error: (e as Error).message })); })
      .finally(() => { if (mounted) setLoading(false); });
    return () => { mounted = false; };
  }, [accessToken, chapterId, versionId]);

  async function handleCopy() {
    if (!version?.translated_body) return;
    await navigator.clipboard.writeText(version.translated_body);
    toast.success(t('viewer.copied'));
  }

  function handleSetActive() {
    // M5b: hold publishing a verifier-flagged version behind a confirm. The 409
    // TRANSL_NEEDS_REVIEW gate is the server-side backstop; we pre-confirm here
    // (we already know the count) to avoid a failed round-trip.
    if (version && version.unresolved_high_count > 0) {
      setConfirmOpen(true);
      return;
    }
    void doSetActive(false);
  }

  async function doSetActive(acknowledge: boolean) {
    if (!accessToken) return;
    try {
      await versionsApi.setActiveVersion(accessToken, chapterId, versionId, acknowledge);
      onSetActive(versionId);
      toast.success(t('viewer.set_active_success'));
    } catch (e) {
      const err = e as Error & { code?: string };
      if (err.code === 'TRANSL_NEEDS_REVIEW') {
        setConfirmOpen(true);  // server backstop (e.g. count changed under us)
        return;
      }
      toast.error(t('viewer.set_active_failed', { error: err.message }));
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
        {t('viewer.version_not_found')}
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
            {t(`status.${version.status}`, { defaultValue: version.status })}
          </span>
          {isActive && (
            <span className="flex items-center gap-1 rounded-full border border-[#3dba6a]/15 bg-[#3dba6a]/10 px-2 py-0.5 text-[10px] font-medium text-[#3dba6a]">
              <Check className="h-2.5 w-2.5" />
              {t('viewer.active')}
            </span>
          )}
          {version.translated_body_format === 'json' ? (
            <span className="rounded-full bg-[#8b5cf6]/10 px-2 py-0.5 text-[10px] font-medium text-[#8b5cf6]">
              {t('viewer.block_badge')} {Array.isArray(version.translated_body_json) ? `(${version.translated_body_json.length})` : ''}
            </span>
          ) : version.status === 'completed' && (
            <span className="rounded-full bg-secondary px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
              {t('viewer.text_badge')}
            </span>
          )}
          {version.unresolved_high_count > 0 && (
            <span
              title={t('viewer.needs_review_title')}
              className="flex items-center gap-1 rounded-full bg-[#e8a33d]/10 px-2 py-0.5 text-[10px] font-medium text-[#e8a33d]"
            >
              <AlertTriangle className="h-2.5 w-2.5" />
              {t('viewer.needs_review', { count: version.unresolved_high_count })}
            </span>
          )}
          {version.is_glossary_stale && (
            <span
              title={t('viewer.glossary_stale_title')}
              className="flex items-center gap-1 rounded-full bg-[#5496e8]/10 px-2 py-0.5 text-[10px] font-medium text-[#5496e8]"
            >
              <History className="h-2.5 w-2.5" />
              {t('viewer.glossary_stale')}
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
            disabled={!version.translated_body && !version.translated_body_json}
            className="flex items-center gap-1 rounded px-2 py-1 text-[11px] text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors disabled:opacity-30"
          >
            <Copy className="h-3 w-3" />
            {t('viewer.copy')}
          </button>
          {bookId && version.status === 'completed' && (
            <button
              type="button"
              onClick={() => (onReview ? onReview(versionId) : navigate(`/books/${bookId}/chapters/${chapterId}/review/${versionId}`))}
              className="flex items-center gap-1 rounded px-2 py-1 text-[11px] text-[#8b5cf6] hover:bg-[#8b5cf6]/10 transition-colors"
            >
              <SplitSquareVertical className="h-3 w-3" />
              {t('viewer.review')}
            </button>
          )}
          {version.status === 'completed' && !isActive && !edit.editing && (
            <button
              type="button"
              onClick={handleSetActive}
              className="flex items-center gap-1 rounded px-2 py-1 text-[11px] text-accent hover:bg-accent/10 transition-colors"
            >
              <Check className="h-3 w-3" />
              {t('viewer.set_active')}
            </button>
          )}
          {/* M7c-2: human-edit a translation → Save creates a new version (gold) */}
          {version.status === 'completed' && !edit.editing && (
            <button
              type="button"
              onClick={edit.startEdit}
              className="flex items-center gap-1 rounded px-2 py-1 text-[11px] text-[#3da692] hover:bg-[#3da692]/10 transition-colors"
            >
              <Pencil className="h-3 w-3" />
              {t('viewer.edit')}
            </button>
          )}
          {edit.editing && (
            <>
              <button
                type="button"
                onClick={edit.cancel}
                disabled={edit.saving}
                className="flex items-center gap-1 rounded px-2 py-1 text-[11px] text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors disabled:opacity-40"
              >
                <X className="h-3 w-3" />
                {t('viewer.cancel')}
              </button>
              <button
                type="button"
                onClick={edit.save}
                disabled={edit.saving}
                className="flex items-center gap-1 rounded bg-[#3da692] px-2.5 py-1 text-[11px] font-medium text-white hover:brightness-110 transition-all disabled:opacity-50"
              >
                <Check className="h-3 w-3" />
                {edit.saving ? t('viewer.saving') : t('viewer.save_edit')}
              </button>
            </>
          )}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-6">
        {edit.editing ? (
          <div className="mx-auto max-w-[680px]">
            {edit.isJson ? (
              <TiptapEditor
                content={edit.editorContent()}
                editable
                onUpdate={(json) => edit.onEditorUpdate(json)}
              />
            ) : (
              <textarea
                value={edit.draftText}
                onChange={(e) => edit.setDraftText(e.target.value)}
                className="min-h-[60vh] w-full resize-y rounded border border-border bg-transparent p-3 font-serif text-[15px] leading-[1.9] text-foreground/90 focus:border-[#3da692] focus:outline-none"
              />
            )}
          </div>
        ) : version.translated_body_format === 'json' && Array.isArray(version.translated_body_json) ? (
          <div className="mx-auto max-w-[680px]">
            <ContentRenderer blocks={version.translated_body_json as any} />
          </div>
        ) : version.translated_body ? (
          <div className="mx-auto max-w-[680px] whitespace-pre-wrap font-serif text-[15px] leading-[1.9] text-foreground/90">
            {version.translated_body}
          </div>
        ) : (
          <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
            {version.status === 'running' ? t('viewer.in_progress')
              : version.status === 'failed' ? t('viewer.failed_msg', { error: version.error_message || t('viewer.unknown_error') })
              : t('viewer.no_content')}
          </div>
        )}
      </div>

      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title={t('viewer.publish_confirm_title')}
        description={t('viewer.publish_confirm', { count: version?.unresolved_high_count ?? 0 })}
        confirmLabel={t('viewer.publish_anyway')}
        cancelLabel={t('viewer.cancel')}
        onConfirm={() => { setConfirmOpen(false); void doSetActive(true); }}
        icon={<AlertTriangle className="h-5 w-5 text-amber-500" />}
      />
    </div>
  );
}

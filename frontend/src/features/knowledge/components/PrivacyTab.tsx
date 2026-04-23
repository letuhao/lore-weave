import { useState } from 'react';
import { Download, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
import { useQueryClient } from '@tanstack/react-query';
import { FormDialog } from '@/components/shared';
import { useAuth } from '@/auth';
import { cn } from '@/lib/utils';
import { knowledgeApi } from '../api';
import { TOUCH_TARGET_MOBILE_ONLY_CLASS } from '../lib/touchTarget';

// GDPR tab — two irreversible actions against /v1/knowledge/user-data.
// Export streams a file attachment (handled in knowledgeApi via raw
// fetch + Blob), Delete is guarded by a FormDialog with a
// type-to-confirm token so accidental clicks can't nuke the user's
// whole knowledge graph. (ConfirmDialog doesn't accept children,
// so FormDialog is the right primitive for the token input.)

// K19a.7 review-impl F5 — DELETE is the literal string the user must
// type, in EVERY locale. It intentionally bypasses i18n: the input
// match below requires exact equality, and translating the token per
// locale would either break the check or force users to know the
// localised word for "DELETE" from memory. Surround text is localised
// via projects.privacy.dialog.description interpolation ({{token}}).
const DELETE_CONFIRM_TOKEN = 'DELETE';

export function PrivacyTab() {
  const { t } = useTranslation('knowledge');
  const { accessToken } = useAuth();
  const queryClient = useQueryClient();

  const [exporting, setExporting] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleteToken, setDeleteToken] = useState('');
  const [deleting, setDeleting] = useState(false);

  const handleExport = async () => {
    if (!accessToken) return;
    setExporting(true);
    try {
      const { blob, filename } = await knowledgeApi.exportUserData(accessToken);
      // Standard Blob → <a download> trigger. Object URL is revoked
      // after the click so we don't leak it for the session.
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      toast.success(t('privacy.export.success'));
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t('privacy.export.failed'));
    } finally {
      setExporting(false);
    }
  };

  const handleDelete = async () => {
    if (!accessToken || deleteToken !== DELETE_CONFIRM_TOKEN) return;
    setDeleting(true);
    try {
      const res = await knowledgeApi.deleteAllUserData(accessToken);
      // Drop every knowledge-* query so downstream tabs re-fetch the
      // now-empty state instead of showing stale cached rows.
      await queryClient.invalidateQueries({
        predicate: (q: { queryKey: readonly unknown[] }) =>
          typeof q.queryKey[0] === 'string' &&
          (q.queryKey[0] as string).startsWith('knowledge-'),
      });
      toast.success(
        t('privacy.delete.success', {
          projects: res.deleted.projects,
          summaries: res.deleted.summaries,
        }),
      );
      setDeleteOpen(false);
      setDeleteToken('');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t('privacy.delete.failed'));
    } finally {
      setDeleting(false);
    }
  };

  const openDelete = () => {
    setDeleteToken('');
    setDeleteOpen(true);
  };

  const closeDelete = (open: boolean) => {
    if (open) return;
    setDeleteOpen(false);
    setDeleteToken('');
  };

  return (
    <div className="space-y-6">
      <section>
        <h2 className="mb-1 font-serif text-sm font-semibold">
          {t('privacy.export.title')}
        </h2>
        <p className="mb-3 text-[12px] text-muted-foreground">
          {t('privacy.export.description')}
        </p>
        <button
          onClick={() => void handleExport()}
          disabled={exporting || !accessToken}
          className={cn(
            'flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs font-medium text-foreground hover:bg-secondary disabled:opacity-50',
            TOUCH_TARGET_MOBILE_ONLY_CLASS,
          )}
        >
          <Download className="h-3.5 w-3.5" />
          {exporting ? t('privacy.export.preparing') : t('privacy.export.button')}
        </button>
      </section>

      <section className="rounded-lg border border-destructive/30 bg-destructive/5 p-4">
        <h2 className="mb-1 font-serif text-sm font-semibold text-destructive">
          {t('privacy.delete.title')}
        </h2>
        <p className="mb-3 text-[12px] text-muted-foreground">
          {t('privacy.delete.description')}
        </p>
        <button
          onClick={openDelete}
          disabled={!accessToken}
          className={cn(
            'flex items-center gap-1.5 rounded-md bg-destructive px-3 py-1.5 text-xs font-medium text-destructive-foreground hover:bg-destructive/90 disabled:opacity-50',
            TOUCH_TARGET_MOBILE_ONLY_CLASS,
          )}
        >
          <Trash2 className="h-3.5 w-3.5" />
          {t('privacy.delete.button')}
        </button>
      </section>

      <FormDialog
        open={deleteOpen}
        onOpenChange={closeDelete}
        title={t('privacy.dialog.title')}
        description={t('privacy.dialog.description', { token: DELETE_CONFIRM_TOKEN })}
        footer={
          <>
            <button
              onClick={() => closeDelete(false)}
              className={cn(
                'rounded-md border px-3 py-1.5 text-sm text-muted-foreground hover:bg-secondary hover:text-foreground',
                TOUCH_TARGET_MOBILE_ONLY_CLASS,
              )}
            >
              {t('privacy.dialog.cancel')}
            </button>
            <button
              onClick={() => void handleDelete()}
              disabled={deleting || deleteToken !== DELETE_CONFIRM_TOKEN}
              className={cn(
                'rounded-md bg-destructive px-3 py-1.5 text-sm font-medium text-destructive-foreground hover:bg-destructive/90 disabled:opacity-50',
                TOUCH_TARGET_MOBILE_ONLY_CLASS,
              )}
            >
              {deleting ? t('privacy.delete.deleting') : t('privacy.delete.button')}
            </button>
          </>
        }
      >
        <input
          type="text"
          value={deleteToken}
          onChange={(e) => setDeleteToken(e.target.value)}
          placeholder={DELETE_CONFIRM_TOKEN}
          className="w-full rounded-md border bg-input px-3 py-2 font-mono text-xs outline-none focus:border-ring"
          autoFocus
        />
      </FormDialog>
    </div>
  );
}

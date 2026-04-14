import { useState } from 'react';
import { Download, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { useQueryClient } from '@tanstack/react-query';
import { FormDialog } from '@/components/shared';
import { useAuth } from '@/auth';
import { knowledgeApi } from '../api';

// GDPR tab — two irreversible actions against /v1/knowledge/user-data.
// Export streams a file attachment (handled in knowledgeApi via raw
// fetch + Blob), Delete is guarded by a destructive ConfirmDialog
// with a type-to-confirm token so accidental clicks can't nuke the
// user's whole knowledge graph.

const DELETE_CONFIRM_TOKEN = 'DELETE';

export function PrivacyTab() {
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
      toast.success('Export downloaded');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Export failed');
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
        `Deleted ${res.deleted.projects} project(s) and ${res.deleted.summaries} summary item(s)`,
      );
      setDeleteOpen(false);
      setDeleteToken('');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Delete failed');
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
        <h2 className="mb-1 font-serif text-sm font-semibold">Export your data</h2>
        <p className="mb-3 text-[12px] text-muted-foreground">
          Download every project and summary the AI has stored for you, as a
          single JSON file. GDPR Article 20.
        </p>
        <button
          onClick={() => void handleExport()}
          disabled={exporting || !accessToken}
          className="flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs font-medium text-foreground hover:bg-secondary disabled:opacity-50"
        >
          <Download className="h-3.5 w-3.5" />
          {exporting ? 'Preparing…' : 'Download export'}
        </button>
      </section>

      <section className="rounded-lg border border-destructive/30 bg-destructive/5 p-4">
        <h2 className="mb-1 font-serif text-sm font-semibold text-destructive">
          Delete all knowledge data
        </h2>
        <p className="mb-3 text-[12px] text-muted-foreground">
          Permanently erase every project and summary. This does not touch
          your books, chapters, or account — only what the memory system has
          stored. This cannot be undone.
        </p>
        <button
          onClick={openDelete}
          disabled={!accessToken}
          className="flex items-center gap-1.5 rounded-md bg-destructive px-3 py-1.5 text-xs font-medium text-destructive-foreground hover:bg-destructive/90 disabled:opacity-50"
        >
          <Trash2 className="h-3.5 w-3.5" />
          Delete everything
        </button>
      </section>

      <FormDialog
        open={deleteOpen}
        onOpenChange={closeDelete}
        title="Delete all knowledge data?"
        description={`This will permanently delete every project and summary. Type ${DELETE_CONFIRM_TOKEN} below to confirm.`}
        footer={
          <>
            <button
              onClick={() => closeDelete(false)}
              className="rounded-md border px-3 py-1.5 text-sm text-muted-foreground hover:bg-secondary hover:text-foreground"
            >
              Cancel
            </button>
            <button
              onClick={() => void handleDelete()}
              disabled={deleting || deleteToken !== DELETE_CONFIRM_TOKEN}
              className="rounded-md bg-destructive px-3 py-1.5 text-sm font-medium text-destructive-foreground hover:bg-destructive/90 disabled:opacity-50"
            >
              {deleting ? 'Deleting…' : 'Delete everything'}
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

import { RotateCcw } from 'lucide-react';
import { useRecycleBin } from './hooks/useRecycleBin';
import { StatusBanner } from './components/StatusBanner';
import type { SystemTrashRow } from './types';

type SectionProps = {
  title: string;
  rows: SystemTrashRow[];
  pending: boolean;
  onRestore: (id: string) => void;
  /** attributes show their kind×genre cell context */
  showCell?: boolean;
};

function TrashSection({ title, rows, pending, onRestore, showCell }: SectionProps) {
  return (
    <div>
      <h3 className="mb-2 text-sm font-semibold text-muted-foreground">
        {title} <span className="font-normal">({rows.length})</span>
      </h3>
      {rows.length === 0 ? (
        <p className="rounded-md border border-dashed border-border px-3 py-3 text-sm text-muted-foreground">
          Nothing here.
        </p>
      ) : (
        <div className="overflow-hidden rounded-md border border-border">
          <table className="w-full text-sm">
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className="border-t border-border first:border-t-0">
                  <td className="px-3 py-2 font-medium text-foreground">{r.name}</td>
                  <td className="px-3 py-2 font-mono text-xs text-muted-foreground">
                    {showCell && r.kind_code ? `${r.kind_code} × ${r.genre_code} / ` : ''}
                    {r.code}
                    {showCell && r.field_type ? ` · ${r.field_type}` : ''}
                  </td>
                  <td className="px-3 py-2 text-right">
                    <button
                      type="button"
                      aria-label={`Restore ${r.name}`}
                      onClick={() => onRestore(r.id)}
                      disabled={pending}
                      className="inline-flex items-center gap-1.5 rounded-md px-2 py-1.5 text-xs font-medium text-foreground hover:bg-secondary/60 disabled:opacity-50"
                    >
                      <RotateCcw className="h-3.5 w-3.5" /> Restore
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export function RecycleBinPanel() {
  const { list, restoreGenre, restoreKind, restoreAttribute, status, clearStatus } = useRecycleBin();
  const trash = list.data;

  return (
    <section className="space-y-4">
      <header>
        <h2 className="text-lg font-semibold">Recycle Bin</h2>
        <p className="text-sm text-muted-foreground">
          Soft-deleted System standards. Restore brings a row back for every tenant. An attribute can
          only be restored once its parent kind &amp; genre are live.
        </p>
      </header>

      <StatusBanner status={status} onDismiss={clearStatus} />

      {list.isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
      {list.isError && <p className="text-sm text-destructive">Failed to load the recycle bin.</p>}

      {trash && (
        <div className="space-y-5">
          <TrashSection
            title="Genres"
            rows={trash.genres}
            pending={restoreGenre.isPending}
            onRestore={(id) => restoreGenre.mutate(id)}
          />
          <TrashSection
            title="Kinds"
            rows={trash.kinds}
            pending={restoreKind.isPending}
            onRestore={(id) => restoreKind.mutate(id)}
          />
          <TrashSection
            title="Attributes"
            rows={trash.attributes}
            pending={restoreAttribute.isPending}
            onRestore={(id) => restoreAttribute.mutate(id)}
            showCell
          />
        </div>
      )}
    </section>
  );
}

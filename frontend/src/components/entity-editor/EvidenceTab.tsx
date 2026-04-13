import { useState } from 'react';
import { ChevronLeft, ChevronRight, FileText, Loader2 } from 'lucide-react';
import { ConfirmDialog } from '@/components/shared';
import type { EvidenceListItem } from '@/features/glossary/types';
import { useEvidenceList } from './useEvidenceList';
import { EvidenceFilterBar } from './EvidenceFilterBar';
import { EvidenceCreateForm } from './EvidenceCreateForm';
import { EvidenceCard } from './EvidenceCard';

interface EvidenceTabProps {
  bookId: string;
  entityId: string;
  bookOriginalLanguage?: string;
  onCountChange?: (delta: number) => void;
}

export function EvidenceTab({ bookId, entityId, bookOriginalLanguage, onCountChange }: EvidenceTabProps) {
  const ev = useEvidenceList(bookId, entityId, bookOriginalLanguage);
  const [creating, setCreating] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<EvidenceListItem | null>(null);

  const handleCreate = async (attrValueId: string, payload: Parameters<typeof ev.createEvidence>[1]) => {
    const ok = await ev.createEvidence(attrValueId, payload);
    if (ok) {
      setCreating(false);
      onCountChange?.(1);
    }
    return ok;
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    await ev.deleteEvidence(deleteTarget);
    setDeleteTarget(null);
    onCountChange?.(-1);
  };

  return (
    <div className="space-y-4">
      <EvidenceFilterBar
        typeFilter={ev.typeFilter}
        onTypeFilter={ev.changeTypeFilter}
        availAttrs={ev.availAttrs}
        attrFilter={ev.attrFilter}
        onAttrFilter={ev.changeAttrFilter}
        availChapters={ev.availChapters}
        chapterFilter={ev.chapterFilter}
        onChapterFilter={ev.changeChapterFilter}
        availLanguages={ev.availLanguages}
        language={ev.language}
        onLanguage={ev.changeLanguage}
        sortBy={ev.sortBy}
        onSortBy={ev.changeSortBy}
        sortDir={ev.sortDir}
        onSortDir={ev.changeSortDir}
        onAdd={() => setCreating(true)}
      />

      {creating && (
        <EvidenceCreateForm
          availAttrs={ev.availAttrs}
          saving={ev.createSaving}
          onSave={handleCreate}
          onCancel={() => setCreating(false)}
        />
      )}

      {/* Loading */}
      {ev.loading && (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </div>
      )}

      {/* Empty state */}
      {!ev.loading && ev.items.length === 0 && (
        <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
          <FileText className="h-8 w-8 mb-2 opacity-40" />
          <p className="text-xs">No evidences found</p>
          {(ev.typeFilter || ev.attrFilter || ev.chapterFilter) && (
            <button type="button" onClick={ev.clearFilters} className="mt-2 text-[10px] text-primary hover:underline">
              Clear filters
            </button>
          )}
        </div>
      )}

      {/* Evidence list */}
      {!ev.loading && ev.items.length > 0 && (
        <div className="space-y-2">
          {ev.items.map((item) => (
            <EvidenceCard
              key={item.evidence_id}
              item={item}
              isEditing={ev.editingId === item.evidence_id}
              editForm={ev.editForm}
              editSaving={ev.editSaving}
              onEdit={() => ev.startEdit(item)}
              onCancelEdit={ev.cancelEdit}
              onSaveEdit={() => void ev.saveEdit(item)}
              onEditFormChange={ev.setEditForm}
              onDelete={() => setDeleteTarget(item)}
            />
          ))}
        </div>
      )}

      {/* Pagination */}
      {ev.total > ev.PAGE_SIZE && (
        <div className="flex items-center justify-between pt-2">
          <span className="text-[10px] text-muted-foreground">
            {ev.offset + 1}&ndash;{Math.min(ev.offset + ev.PAGE_SIZE, ev.total)} of {ev.total}
          </span>
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => ev.setOffset(Math.max(0, ev.offset - ev.PAGE_SIZE))}
              disabled={ev.offset === 0}
              className="rounded p-1 text-muted-foreground hover:bg-secondary disabled:opacity-30 transition-colors"
              title="Previous page"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
            <span className="text-[10px] text-muted-foreground px-2">
              {ev.currentPage} / {ev.totalPages}
            </span>
            <button
              type="button"
              onClick={() => ev.setOffset(ev.offset + ev.PAGE_SIZE)}
              disabled={ev.offset + ev.PAGE_SIZE >= ev.total}
              className="rounded p-1 text-muted-foreground hover:bg-secondary disabled:opacity-30 transition-colors"
              title="Next page"
            >
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}

      {/* Delete confirmation dialog */}
      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={(open) => { if (!open) setDeleteTarget(null); }}
        title="Delete evidence?"
        description={`This evidence from "${deleteTarget?.attribute_name ?? ''}" will be permanently deleted.`}
        confirmLabel="Delete"
        variant="destructive"
        onConfirm={() => void handleDelete()}
      />
    </div>
  );
}

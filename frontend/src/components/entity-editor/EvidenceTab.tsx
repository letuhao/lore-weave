import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight, FileText, Loader2 } from 'lucide-react';
import { ConfirmDialog } from '@/components/shared';
import type { EvidenceListItem } from '@/features/glossary/types';
import { useEvidenceList, PAGE_SIZE_OPTIONS } from './useEvidenceList';
import { EvidenceFilterBar } from './EvidenceFilterBar';
import { EvidenceCreateForm } from './EvidenceCreateForm';
import { EvidenceCard } from './EvidenceCard';

interface EvidenceTabProps {
  bookId: string;
  entityId: string;
  bookOriginalLanguage?: string;
  defaultDisplayLanguage?: string;
  onCountChange?: (delta: number) => void;
}

export function EvidenceTab({ bookId, entityId, bookOriginalLanguage, defaultDisplayLanguage, onCountChange }: EvidenceTabProps) {
  const { t } = useTranslation('entityEditor');
  const ev = useEvidenceList(bookId, entityId, bookOriginalLanguage, defaultDisplayLanguage);
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
          <p className="text-xs">{t('evidence.tab.no_evidences')}</p>
          {(ev.typeFilter || ev.attrFilter || ev.chapterFilter) && (
            <button type="button" onClick={ev.clearFilters} className="mt-2 text-[10px] text-primary hover:underline">
              {t('evidence.tab.clear_filters')}
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
              bookId={bookId}
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

      {/* Pagination — first/prev/jump/next/last + page-size, so hundreds of pages (a major
          entity has >10k evidence rows) are navigable instead of one-step prev/next. */}
      {ev.total > ev.pageSize && (
        <div className="flex flex-wrap items-center justify-between gap-2 pt-2">
          <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
            <span>{ev.offset + 1}&ndash;{Math.min(ev.offset + ev.pageSize, ev.total)} of {ev.total}</span>
            <select
              value={ev.pageSize}
              onChange={(e) => ev.changePageSize(Number(e.target.value))}
              className="rounded border bg-background px-1 py-0.5 focus:outline-none"
              aria-label={t('evidence.tab.page_size')}
            >
              {PAGE_SIZE_OPTIONS.map((n) => (
                <option key={n} value={n}>{t('evidence.tab.per_page', { n })}</option>
              ))}
            </select>
          </div>
          <div className="flex items-center gap-1">
            <button type="button" onClick={() => ev.goToPage(1)} disabled={ev.currentPage === 1}
              className="rounded p-1 text-muted-foreground hover:bg-secondary disabled:opacity-30 transition-colors" title={t('evidence.tab.first_page')}>
              <ChevronsLeft className="h-4 w-4" />
            </button>
            <button type="button" onClick={() => ev.setOffset(Math.max(0, ev.offset - ev.pageSize))} disabled={ev.offset === 0}
              className="rounded p-1 text-muted-foreground hover:bg-secondary disabled:opacity-30 transition-colors" title={t('evidence.tab.prev_page')}>
              <ChevronLeft className="h-4 w-4" />
            </button>
            <span className="flex items-center gap-1 px-1 text-[10px] text-muted-foreground">
              <input
                type="number"
                min={1}
                max={ev.totalPages}
                value={ev.currentPage}
                onChange={(e) => ev.goToPage(Number(e.target.value))}
                className="w-10 rounded border bg-background px-1 py-0.5 text-center focus:outline-none"
                aria-label={t('evidence.tab.jump_to_page')}
              />
              / {ev.totalPages}
            </span>
            <button type="button" onClick={() => ev.setOffset(ev.offset + ev.pageSize)} disabled={ev.offset + ev.pageSize >= ev.total}
              className="rounded p-1 text-muted-foreground hover:bg-secondary disabled:opacity-30 transition-colors" title={t('evidence.tab.next_page')}>
              <ChevronRight className="h-4 w-4" />
            </button>
            <button type="button" onClick={() => ev.goToPage(ev.totalPages)} disabled={ev.currentPage === ev.totalPages}
              className="rounded p-1 text-muted-foreground hover:bg-secondary disabled:opacity-30 transition-colors" title={t('evidence.tab.last_page')}>
              <ChevronsRight className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}

      {/* Delete confirmation dialog */}
      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={(open) => { if (!open) setDeleteTarget(null); }}
        title={t('evidence.tab.delete_title')}
        description={t('evidence.tab.delete_desc', { attr: deleteTarget?.attribute_name ?? '' })}
        confirmLabel={t('evidence.tab.delete_confirm')}
        variant="destructive"
        onConfirm={() => void handleDelete()}
      />
    </div>
  );
}

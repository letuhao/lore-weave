import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { ExternalLink, Loader2, Pencil, Trash2, X } from 'lucide-react';
import type { EvidenceListItem, EvidenceType, PatchEvidencePayload } from '@/features/glossary/types';

const EVIDENCE_TYPES: EvidenceType[] = ['quote', 'summary', 'reference'];
const TYPE_COLORS: Record<EvidenceType, string> = {
  quote: 'bg-emerald-500/15 text-emerald-400',
  summary: 'bg-blue-500/15 text-blue-400',
  reference: 'bg-amber-500/15 text-amber-400',
};

// Trust badge per provenance_status (D-EVIDENCE-PROVENANCE-OVERHAUL M1). `exact`/`resolved` =
// the quote was validated against the real chapter text → trustworthy; `unmatched` = the quote
// couldn't be found in the source (likely an LLM hallucination) → warn; `unverified` = no
// validation ran → neutral. Hidden for the benign verified cases to keep the row clean.
const PROVENANCE_STYLE: Record<string, string> = {
  exact: 'bg-emerald-500/15 text-emerald-400',
  resolved: 'bg-emerald-500/15 text-emerald-400',
  ambiguous: 'bg-amber-500/15 text-amber-400',
  unmatched: 'bg-red-500/15 text-red-400',
  unverified: 'bg-muted text-muted-foreground',
};

// A reference's source URL is stored in block_or_line (the deep-research attach path).
function asUrl(v: string): string | null {
  return /^https?:\/\//i.test(v.trim()) ? v.trim() : null;
}

interface EvidenceCardProps {
  item: EvidenceListItem;
  bookId: string;
  isEditing: boolean;
  editForm: PatchEvidencePayload;
  editSaving: boolean;
  onEdit: () => void;
  onCancelEdit: () => void;
  onSaveEdit: () => void;
  onEditFormChange: (form: PatchEvidencePayload) => void;
  onDelete: () => void;
}

export function EvidenceCard({
  item, bookId, isEditing, editForm, editSaving,
  onEdit, onCancelEdit, onSaveEdit, onEditFormChange, onDelete,
}: EvidenceCardProps) {
  const { t } = useTranslation('entityEditor');
  // Deep-link to the source: the reader at this chapter, carrying the validated offset range as
  // a hint the reader can highlight (only when the quote was offset-matched + trusted).
  const readerHref = item.chapter_id
    ? `/books/${bookId}/chapters/${item.chapter_id}/read` +
      (item.char_start != null && item.char_end != null &&
        (item.provenance_status === 'exact' || item.provenance_status === 'resolved')
        ? `?hl=${item.char_start}-${item.char_end}`
        : '')
    : null;
  const refUrl = item.evidence_type === 'reference' ? asUrl(item.block_or_line) : null;
  if (isEditing) {
    return (
      <div className="rounded-lg border bg-card p-3 space-y-2">
        <div className="flex items-center gap-2">
          <select
            value={editForm.evidence_type ?? item.evidence_type}
            onChange={(e) => onEditFormChange({ ...editForm, evidence_type: e.target.value as EvidenceType })}
            className="rounded border bg-background px-2 py-0.5 text-[10px] focus:outline-none"
            aria-label={t('evidence.card.edit_type_aria')}
          >
            {EVIDENCE_TYPES.map((ty) => (
              <option key={ty} value={ty}>{t(`evidence.type.${ty}`)}</option>
            ))}
          </select>
          <span className="flex-1" />
          <button type="button" onClick={onCancelEdit} className="p-1 text-muted-foreground hover:text-foreground" title={t('evidence.card.cancel_title')}>
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
        <textarea
          value={editForm.original_text ?? item.original_text}
          onChange={(e) => onEditFormChange({ ...editForm, original_text: e.target.value })}
          rows={3}
          className="w-full rounded border bg-background px-2 py-1.5 text-xs focus:outline-none resize-y"
        />
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-[10px] text-muted-foreground">{t('evidence.card.block_line')}</label>
            <input
              value={editForm.block_or_line ?? item.block_or_line}
              onChange={(e) => onEditFormChange({ ...editForm, block_or_line: e.target.value })}
              className="w-full rounded border bg-background px-2 py-1.5 text-xs focus:outline-none"
            />
          </div>
          <div>
            <label className="text-[10px] text-muted-foreground">{t('evidence.card.note')}</label>
            <input
              value={editForm.note ?? item.note ?? ''}
              onChange={(e) => onEditFormChange({ ...editForm, note: e.target.value || null })}
              className="w-full rounded border bg-background px-2 py-1.5 text-xs focus:outline-none"
            />
          </div>
        </div>
        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancelEdit}
            className="rounded-md border px-3 py-1 text-xs text-muted-foreground hover:bg-secondary transition-colors"
          >
            {t('evidence.card.cancel')}
          </button>
          <button
            type="button"
            onClick={onSaveEdit}
            disabled={editSaving}
            className="inline-flex items-center gap-1 rounded-md bg-primary px-3 py-1 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
          >
            {editSaving && <Loader2 className="h-3 w-3 animate-spin" />}
            {t('evidence.card.save')}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-lg border bg-card p-3 space-y-2">
      <div className="flex items-center gap-2 text-[10px]">
        <span className={`rounded-full px-2 py-0.5 font-medium ${TYPE_COLORS[item.evidence_type]}`}>
          {t(`evidence.type.${item.evidence_type}`)}
        </span>
        <span className="rounded bg-muted px-1.5 py-0.5 font-medium text-muted-foreground">
          {item.attribute_name}
        </span>
        {/* Trust badge — only for quote-type evidence with a meaningful (non-verified) status. */}
        {item.evidence_type === 'quote' && item.provenance_status && item.provenance_status !== 'exact' && item.provenance_status !== 'resolved' && (
          <span
            className={`rounded-full px-2 py-0.5 font-medium ${PROVENANCE_STYLE[item.provenance_status] ?? PROVENANCE_STYLE.unverified}`}
            title={t(`evidence.provenance.${item.provenance_status}_hint`)}
          >
            {t(`evidence.provenance.${item.provenance_status}`)}
          </span>
        )}
        {item.chapter_title && (
          readerHref ? (
            <Link
              to={readerHref}
              className="inline-flex items-center gap-0.5 text-primary hover:underline"
              title={t('evidence.card.open_source')}
            >
              {item.chapter_title}{item.char_start != null ? ` \u00b7 @${item.char_start}` : ''}
              <ExternalLink className="h-2.5 w-2.5" />
            </Link>
          ) : (
            <span className="text-muted-foreground">
              {item.chapter_title}{item.block_or_line ? ` \u00b7 ${item.block_or_line}` : ''}
            </span>
          )
        )}
        {/* Reference evidence: its source URL lives in block_or_line \u2014 render as a real link. */}
        {refUrl && (
          <a
            href={refUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-0.5 text-primary hover:underline truncate max-w-[160px]"
            title={refUrl}
          >
            {refUrl.replace(/^https?:\/\//, '')}
            <ExternalLink className="h-2.5 w-2.5 shrink-0" />
          </a>
        )}
        <span className="flex-1" />
        <span className="text-muted-foreground">
          {new Date(item.created_at).toLocaleDateString()}
        </span>
        <button type="button" onClick={onEdit} className="p-1 text-muted-foreground hover:text-foreground transition-colors" title={t('evidence.card.edit_title')}>
          <Pencil className="h-3 w-3" />
        </button>
        <button type="button" onClick={onDelete} className="p-1 text-muted-foreground hover:text-destructive transition-colors" title={t('evidence.card.delete_title')}>
          <Trash2 className="h-3 w-3" />
        </button>
      </div>
      <p className="text-xs leading-relaxed whitespace-pre-wrap">
        {item.display_text}
      </p>
      {item.display_language !== item.original_language && (
        <p className="text-[10px] text-muted-foreground italic">
          {t('evidence.card.translated', { lang: item.display_language })}
        </p>
      )}
      {item.note && (
        <p className="text-[10px] text-muted-foreground italic">
          {t('evidence.card.note_label', { note: item.note })}
        </p>
      )}
    </div>
  );
}

import { Loader2, Pencil, Trash2, X } from 'lucide-react';
import type { EvidenceListItem, EvidenceType, PatchEvidencePayload } from '@/features/glossary/types';

const EVIDENCE_TYPES: EvidenceType[] = ['quote', 'summary', 'reference'];
const TYPE_COLORS: Record<EvidenceType, string> = {
  quote: 'bg-emerald-500/15 text-emerald-400',
  summary: 'bg-blue-500/15 text-blue-400',
  reference: 'bg-amber-500/15 text-amber-400',
};

interface EvidenceCardProps {
  item: EvidenceListItem;
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
  item, isEditing, editForm, editSaving,
  onEdit, onCancelEdit, onSaveEdit, onEditFormChange, onDelete,
}: EvidenceCardProps) {
  if (isEditing) {
    return (
      <div className="rounded-lg border bg-card p-3 space-y-2">
        <div className="flex items-center gap-2">
          <select
            value={editForm.evidence_type ?? item.evidence_type}
            onChange={(e) => onEditFormChange({ ...editForm, evidence_type: e.target.value as EvidenceType })}
            className="rounded border bg-background px-2 py-0.5 text-[10px] focus:outline-none"
            aria-label="Edit evidence type"
          >
            {EVIDENCE_TYPES.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
          <span className="flex-1" />
          <button type="button" onClick={onCancelEdit} className="p-1 text-muted-foreground hover:text-foreground" title="Cancel">
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
            <label className="text-[10px] text-muted-foreground">Block / Line</label>
            <input
              value={editForm.block_or_line ?? item.block_or_line}
              onChange={(e) => onEditFormChange({ ...editForm, block_or_line: e.target.value })}
              className="w-full rounded border bg-background px-2 py-1.5 text-xs focus:outline-none"
            />
          </div>
          <div>
            <label className="text-[10px] text-muted-foreground">Note</label>
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
            Cancel
          </button>
          <button
            type="button"
            onClick={onSaveEdit}
            disabled={editSaving}
            className="inline-flex items-center gap-1 rounded-md bg-primary px-3 py-1 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
          >
            {editSaving && <Loader2 className="h-3 w-3 animate-spin" />}
            Save
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-lg border bg-card p-3 space-y-2">
      <div className="flex items-center gap-2 text-[10px]">
        <span className={`rounded-full px-2 py-0.5 font-medium capitalize ${TYPE_COLORS[item.evidence_type]}`}>
          {item.evidence_type}
        </span>
        <span className="rounded bg-muted px-1.5 py-0.5 font-medium text-muted-foreground">
          {item.attribute_name}
        </span>
        {item.chapter_title && (
          <span className="text-muted-foreground">
            {item.chapter_title}{item.block_or_line ? ` \u00b7 ${item.block_or_line}` : ''}
          </span>
        )}
        <span className="flex-1" />
        <span className="text-muted-foreground">
          {new Date(item.created_at).toLocaleDateString()}
        </span>
        <button type="button" onClick={onEdit} className="p-1 text-muted-foreground hover:text-foreground transition-colors" title="Edit">
          <Pencil className="h-3 w-3" />
        </button>
        <button type="button" onClick={onDelete} className="p-1 text-muted-foreground hover:text-destructive transition-colors" title="Delete">
          <Trash2 className="h-3 w-3" />
        </button>
      </div>
      <p className="text-xs leading-relaxed whitespace-pre-wrap">
        {item.display_text}
      </p>
      {item.display_language !== item.original_language && (
        <p className="text-[10px] text-muted-foreground italic">
          Translated ({item.display_language})
        </p>
      )}
      {item.note && (
        <p className="text-[10px] text-muted-foreground italic">
          Note: {item.note}
        </p>
      )}
    </div>
  );
}

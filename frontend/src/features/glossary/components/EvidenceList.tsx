import { useState } from 'react';
import type { Evidence, EvidenceType } from '../types';
import type { CreateEvidenceBody } from '../api';
import { AddEvidenceModal } from './AddEvidenceModal';

type Props = {
  evidences: Evidence[];
  defaultLanguage?: string;
  onAdd: (body: CreateEvidenceBody) => Promise<void>;
  onDelete: (evidenceId: string) => Promise<void>;
};

const TYPE_STYLES: Record<EvidenceType, string> = {
  quote: 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300',
  summary: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
  reference: 'bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300',
};

export function EvidenceList({ evidences, defaultLanguage, onAdd, onDelete }: Props) {
  const [showModal, setShowModal] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  async function handleDelete(evidenceId: string) {
    setDeletingId(evidenceId);
    try {
      await onDelete(evidenceId);
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <>
      <div className="space-y-1.5">
        {evidences.map((ev) => (
          <div
            key={ev.evidence_id}
            className="group relative rounded border bg-muted/30 p-2 text-xs"
          >
            {/* Header row: type badge + location + lang + delete */}
            <div className="flex items-center gap-1.5">
              <span className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium ${TYPE_STYLES[ev.evidence_type]}`}>
                {ev.evidence_type}
              </span>
              {ev.chapter_title && (
                <span className="truncate text-muted-foreground">{ev.chapter_title}</span>
              )}
              {ev.block_or_line && (
                <span className="shrink-0 text-muted-foreground">· {ev.block_or_line}</span>
              )}
              <span className="ml-auto shrink-0 font-mono text-[10px] text-muted-foreground">
                {ev.original_language}
              </span>
              <button
                type="button"
                onClick={() => handleDelete(ev.evidence_id)}
                disabled={deletingId === ev.evidence_id}
                className="shrink-0 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100 hover:text-destructive disabled:opacity-50"
                aria-label="Delete evidence"
              >
                ✕
              </button>
            </div>

            {/* Original text */}
            <p className="mt-1 line-clamp-3 text-foreground/80">{ev.original_text}</p>

            {/* Note */}
            {ev.note && (
              <p className="mt-0.5 italic text-muted-foreground">{ev.note}</p>
            )}
          </div>
        ))}

        <button
          type="button"
          onClick={() => setShowModal(true)}
          className="w-full rounded border border-dashed px-2 py-1.5 text-xs text-muted-foreground hover:border-solid hover:bg-muted/40"
        >
          + Add evidence
        </button>
      </div>

      {showModal && (
        <AddEvidenceModal
          defaultLanguage={defaultLanguage}
          onAdd={onAdd}
          onClose={() => setShowModal(false)}
        />
      )}
    </>
  );
}

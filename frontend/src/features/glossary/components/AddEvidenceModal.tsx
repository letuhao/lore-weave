import { useState } from 'react';
import type { EvidenceType } from '../types';
import type { CreateEvidenceBody } from '../api';

const COMMON_LANGUAGES = [
  { code: 'zh', label: 'Chinese' },
  { code: 'en', label: 'English' },
  { code: 'ja', label: 'Japanese' },
  { code: 'ko', label: 'Korean' },
  { code: 'vi', label: 'Vietnamese' },
  { code: 'th', label: 'Thai' },
];

const EVIDENCE_TYPE_OPTIONS: { value: EvidenceType; label: string }[] = [
  { value: 'quote', label: 'Quote' },
  { value: 'summary', label: 'Summary' },
  { value: 'reference', label: 'Reference' },
];

type Props = {
  defaultLanguage?: string;
  onAdd: (body: CreateEvidenceBody) => Promise<void>;
  onClose: () => void;
};

export function AddEvidenceModal({ defaultLanguage = 'zh', onAdd, onClose }: Props) {
  const [evidenceType, setEvidenceType] = useState<EvidenceType>('quote');
  const [originalText, setOriginalText] = useState('');
  const [originalLanguage, setOriginalLanguage] = useState(defaultLanguage);
  const [chapterTitle, setChapterTitle] = useState('');
  const [blockOrLine, setBlockOrLine] = useState('');
  const [note, setNote] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  async function handleSubmit() {
    if (!originalText.trim()) return;
    setSaving(true);
    setError('');
    try {
      const body: CreateEvidenceBody = {
        evidence_type: evidenceType,
        original_text: originalText.trim(),
        original_language: originalLanguage,
      };
      if (chapterTitle.trim()) body.chapter_title = chapterTitle.trim();
      if (blockOrLine.trim()) body.block_or_line = blockOrLine.trim();
      if (note.trim()) body.note = note.trim();
      await onAdd(body);
      onClose();
    } catch (e: unknown) {
      setError((e as Error).message || 'Failed to add evidence');
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      {/* Backdrop — z-[60] sits above EntityDetailPanel (z-50) */}
      <div
        className="fixed inset-0 z-[60] bg-black/30"
        onClick={onClose}
        aria-hidden="true"
      />
      {/* Dialog */}
      <div className="fixed left-1/2 top-1/2 z-[61] w-96 -translate-x-1/2 -translate-y-1/2 rounded-lg border bg-background p-4 shadow-xl">
        <h3 className="mb-3 text-sm font-semibold">Add Evidence</h3>

        <div className="space-y-2">
          {/* Evidence type */}
          <div>
            <label className="mb-0.5 block text-xs text-muted-foreground">Type</label>
            <select
              value={evidenceType}
              onChange={(e) => setEvidenceType(e.target.value as EvidenceType)}
              className="w-full rounded border bg-background px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
            >
              {EVIDENCE_TYPE_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </div>

          {/* Original language */}
          <div>
            <label className="mb-0.5 block text-xs text-muted-foreground">Language</label>
            <select
              value={originalLanguage}
              onChange={(e) => setOriginalLanguage(e.target.value)}
              className="w-full rounded border bg-background px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
            >
              {COMMON_LANGUAGES.map((l) => (
                <option key={l.code} value={l.code}>{l.label} ({l.code})</option>
              ))}
            </select>
          </div>

          {/* Original text */}
          <div>
            <label className="mb-0.5 block text-xs text-muted-foreground">Text</label>
            <textarea
              value={originalText}
              onChange={(e) => setOriginalText(e.target.value)}
              rows={4}
              placeholder="Paste the original text here…"
              className="w-full resize-y rounded border bg-background px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
            />
          </div>

          {/* Chapter (optional) */}
          <div>
            <label className="mb-0.5 block text-xs text-muted-foreground">Chapter title (optional)</label>
            <input
              type="text"
              value={chapterTitle}
              onChange={(e) => setChapterTitle(e.target.value)}
              placeholder="e.g. Chapter 3: The Forest"
              className="w-full rounded border bg-background px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
            />
          </div>

          {/* Block / line location (optional) */}
          <div>
            <label className="mb-0.5 block text-xs text-muted-foreground">Location (optional)</label>
            <input
              type="text"
              value={blockOrLine}
              onChange={(e) => setBlockOrLine(e.target.value)}
              placeholder="e.g. paragraph 4, line 12"
              className="w-full rounded border bg-background px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
            />
          </div>

          {/* Note (optional) */}
          <div>
            <label className="mb-0.5 block text-xs text-muted-foreground">Note (optional)</label>
            <input
              type="text"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Translator note or context…"
              className="w-full rounded border bg-background px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
            />
          </div>

          {error && <p className="text-xs text-destructive">{error}</p>}
        </div>

        <div className="mt-3 flex justify-end gap-2">
          <button
            onClick={onClose}
            className="rounded border px-3 py-1 text-sm text-muted-foreground hover:bg-muted"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={!originalText.trim() || saving}
            className="rounded border px-3 py-1 text-sm font-medium hover:bg-muted disabled:opacity-50"
          >
            {saving ? 'Adding…' : 'Add'}
          </button>
        </div>
      </div>
    </>
  );
}

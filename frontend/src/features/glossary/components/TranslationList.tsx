import { useState } from 'react';
import type { Translation, Confidence } from '../types';
import { ConfidenceBadge } from './ConfidenceBadge';
import { AddTranslationModal } from './AddTranslationModal';

type Props = {
  translations: Translation[];
  onAdd: (languageCode: string, value: string, confidence: Confidence) => Promise<void>;
  onDelete: (translationId: string) => Promise<void>;
};

export function TranslationList({ translations, onAdd, onDelete }: Props) {
  const [showAdd, setShowAdd] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [error, setError] = useState('');

  async function handleDelete(id: string) {
    setDeletingId(id);
    setError('');
    try {
      await onDelete(id);
    } catch (e: unknown) {
      setError((e as Error).message || 'Failed to delete translation');
    } finally {
      setDeletingId(null);
    }
  }

  const usedLanguages = translations.map((t) => t.language_code);

  return (
    <div className="space-y-1">
      {translations.length === 0 && (
        <p className="text-xs text-muted-foreground">No translations yet.</p>
      )}

      {translations.map((tr) => (
        <div key={tr.translation_id} className="flex items-start gap-2 rounded bg-muted/40 px-2 py-1 text-xs">
          <span className="shrink-0 w-8 font-mono font-medium text-muted-foreground">{tr.language_code}</span>
          <span className="min-w-0 flex-1 break-words">{tr.value || '—'}</span>
          <ConfidenceBadge confidence={tr.confidence} />
          <button
            onClick={() => handleDelete(tr.translation_id)}
            disabled={deletingId === tr.translation_id}
            className="shrink-0 rounded p-0.5 text-muted-foreground hover:text-destructive disabled:cursor-not-allowed disabled:opacity-50"
            aria-label="Delete translation"
          >
            {deletingId === tr.translation_id ? '…' : '✕'}
          </button>
        </div>
      ))}

      {error && <p className="text-xs text-destructive">{error}</p>}

      <button
        onClick={() => setShowAdd(true)}
        className="text-xs text-muted-foreground hover:text-foreground"
      >
        + Add translation
      </button>

      {showAdd && (
        <AddTranslationModal
          usedLanguages={usedLanguages}
          onAdd={onAdd}
          onClose={() => setShowAdd(false)}
        />
      )}
    </div>
  );
}

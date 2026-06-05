// LOOM Composition (V1 slice 3) — one candidate card in the controlled-auto gate.
//
// View only: renders a draft, badges the reranker's winner, and surfaces the
// human-gate actions. "Use this" accepts the card as-is (winner → plain accept;
// non-winner → pick-different correction, decided by the parent). Edit opens an
// inline textarea (FE-local, §13 SC4 — never autosaved until accept).
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

type Props = {
  text: string;
  index: number;
  isWinner: boolean;
  disabled: boolean;
  onUse: () => void;
  onEdit: (editedText: string) => void;
};

export function CandidateCard({ text, index, isWinner, disabled, onUse, onEdit }: Props) {
  const { t } = useTranslation('composition');
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(text);

  return (
    <div
      data-testid="candidate-card"
      data-winner={isWinner ? 'true' : 'false'}
      className={`flex min-w-0 flex-1 flex-col gap-2 rounded border p-2 text-sm ${
        isWinner ? 'border-indigo-400 dark:border-indigo-600' : 'border-neutral-300 dark:border-neutral-600'
      }`}
    >
      <div className="flex items-center justify-between text-xs">
        <span className="font-medium text-neutral-500">
          {t('candidateN', { defaultValue: 'Option {{n}}', n: index + 1 })}
        </span>
        {isWinner && (
          <span data-testid="candidate-winner-badge" className="rounded bg-indigo-100 px-1.5 py-0.5 text-[11px] text-indigo-700 dark:bg-indigo-900 dark:text-indigo-200">
            {t('candidatePicked', { defaultValue: 'AI pick' })}
          </span>
        )}
      </div>

      {editing ? (
        <>
          <textarea
            data-testid="candidate-edit-box"
            className="min-h-[8rem] w-full resize-y rounded border border-neutral-300 bg-transparent p-1.5 text-sm dark:border-neutral-600"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
          />
          <div className="flex gap-2">
            <button
              data-testid="candidate-edit-save"
              className="rounded bg-emerald-600 px-2.5 py-1 text-xs text-white disabled:opacity-50"
              disabled={disabled}
              onClick={() => onEdit(draft)}
            >
              {t('saveAccept', { defaultValue: 'Save & accept' })}
            </button>
            <button
              className="rounded border border-neutral-300 px-2.5 py-1 text-xs dark:border-neutral-600"
              onClick={() => { setDraft(text); setEditing(false); }}
            >
              {t('cancel', { defaultValue: 'Cancel' })}
            </button>
          </div>
        </>
      ) : (
        <>
          <p className="whitespace-pre-wrap break-words text-neutral-800 dark:text-neutral-200">{text}</p>
          <div className="mt-auto flex gap-2">
            <button
              data-testid="candidate-use"
              className="rounded bg-emerald-600 px-2.5 py-1 text-xs text-white disabled:opacity-50"
              disabled={disabled}
              onClick={onUse}
            >
              {isWinner ? t('accept', { defaultValue: 'Accept' }) : t('useThis', { defaultValue: 'Use this' })}
            </button>
            <button
              data-testid="candidate-edit"
              className="rounded border border-neutral-300 px-2.5 py-1 text-xs dark:border-neutral-600"
              onClick={() => { setDraft(text); setEditing(true); }}
            >
              {t('edit', { defaultValue: 'Edit' })}
            </button>
          </div>
        </>
      )}
    </div>
  );
}

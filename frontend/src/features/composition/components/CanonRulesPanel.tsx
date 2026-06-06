// LOOM Composition (M8) — canon-rules management (view). List + add + archive.
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { useCanonRules } from '../hooks/useCanonRules';
import type { CanonRule } from '../types';

export function CanonRulesPanel({ projectId, token }: { projectId: string; token: string | null }) {
  const { t } = useTranslation('composition');
  const { list, create, remove } = useCanonRules(projectId, token);
  const [text, setText] = useState('');
  const [scope, setScope] = useState<CanonRule['scope']>('world');

  const add = () => {
    if (!text.trim()) return;
    create.mutate(
      { text: text.trim(), scope },
      { onSuccess: () => setText(''), onError: (e) => toast.error((e as Error).message) },
    );
  };

  return (
    <div className="flex flex-col gap-2 p-3 text-sm">
      <div className="flex flex-col gap-1">
        <textarea
          data-testid="composition-canon-input"
          className="w-full resize-none rounded border border-neutral-300 bg-transparent p-2 dark:border-neutral-600"
          rows={2}
          placeholder={t('rulePlaceholder', { defaultValue: 'A canon rule the co-writer must respect…' })}
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        <div className="flex gap-2">
          <select
            data-testid="composition-canon-scope"
            className="rounded border border-neutral-300 bg-transparent px-2 py-1 text-xs dark:border-neutral-600"
            value={scope}
            onChange={(e) => setScope(e.target.value as CanonRule['scope'])}
            aria-label={t('scope', { defaultValue: 'Scope' })}
          >
            <option value="world">{t('world', { defaultValue: 'world' })}</option>
            <option value="entity">{t('entity', { defaultValue: 'entity' })}</option>
            <option value="reveal_gate">{t('reveal_gate', { defaultValue: 'reveal gate' })}</option>
          </select>
          <button
            data-testid="composition-canon-add"
            className="rounded bg-indigo-600 px-3 py-1 text-xs text-white disabled:opacity-50"
            disabled={create.isPending || !text.trim()}
            onClick={add}
          >
            {t('addRule', { defaultValue: 'Add rule' })}
          </button>
        </div>
      </div>

      {list.isLoading && <div className="text-neutral-500">{t('loading', { defaultValue: 'Loading…' })}</div>}
      <ul className="flex flex-col gap-1">
        {(list.data ?? []).map((r) => (
          <li key={r.id} data-testid="composition-canon-rule" className="flex items-start justify-between gap-2 rounded border border-neutral-200 p-2 dark:border-neutral-700">
            <div>
              <span className="mr-1 rounded bg-neutral-100 px-1 py-0.5 text-[10px] uppercase text-neutral-500 dark:bg-neutral-800">{r.scope}</span>
              <span>{r.text}</span>
            </div>
            <button
              data-testid="composition-canon-archive"
              className="shrink-0 text-xs text-neutral-400 hover:text-red-600"
              onClick={() => remove.mutate(r.id)}
              aria-label={t('archive', { defaultValue: 'Archive' })}
            >
              ✕
            </button>
          </li>
        ))}
        {!list.isLoading && !list.data?.length && (
          <li className="text-xs text-neutral-500">{t('noRules', { defaultValue: 'No canon rules yet.' })}</li>
        )}
      </ul>
    </div>
  );
}

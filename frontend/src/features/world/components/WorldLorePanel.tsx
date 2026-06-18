import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { Sparkles } from 'lucide-react';
import { useWorldLore } from '../hooks/useWorldLore';

interface WorldLorePanelProps {
  /** The world's bible book — lore entities are created here. */
  bibleBookId: string | null;
  /** The world's bible chapter — every authored entity anchors to THIS id. */
  bibleChapterId: string | null;
}

// C21 — author lore against the world's bible chapter. Picks a glossary kind,
// names nothing (the glossary create contract is kind-only; the entity is a
// draft the user fills in afterward in the glossary) and anchors it to the bible
// chapter. Extraction is presented as OPTIONAL — the bible chapter, not
// extracted prose, is the anchor. All logic in useWorldLore (FE MVC).
export function WorldLorePanel({ bibleBookId, bibleChapterId }: WorldLorePanelProps) {
  const { t } = useTranslation('world');
  // `lastLink`/`error` from the hook are unused here — error feedback is handled
  // inline via the submit catch + toast, so only the fields this view needs are
  // destructured.
  const { kinds, kindsLoading, authorLore, isAuthoring } = useWorldLore(bibleBookId, bibleChapterId);
  const [kindId, setKindId] = useState('');
  const anchorReady = !!bibleBookId && !!bibleChapterId;

  const submit = async () => {
    if (!kindId || !anchorReady) return;
    try {
      await authorLore({ kindId });
      toast.success(t('lore.added', { defaultValue: 'Lore added to your world bible.' }));
      setKindId('');
    } catch (e) {
      toast.error((e as Error).message || t('lore.error', { defaultValue: 'Failed to add lore' }));
    }
  };

  return (
    <section className="space-y-3 rounded-lg border bg-card p-4" data-testid="world-lore-panel">
      <header className="space-y-1">
        <h2 className="flex items-center gap-2 font-medium">
          <Sparkles className="h-4 w-4 text-muted-foreground" />
          {t('lore.title', { defaultValue: 'World bible' })}
        </h2>
        <p className="text-xs text-muted-foreground" data-testid="extraction-optional-note">
          {t('lore.extractionOptional', {
            defaultValue:
              'Author lore directly — characters, places, factions. No manuscript needed. Extraction from prose is optional; this world bible is the anchor.',
          })}
        </p>
      </header>

      {!anchorReady ? (
        <p className="text-xs text-amber-600 dark:text-amber-400" data-testid="anchor-unavailable">
          {t('lore.anchorUnavailable', {
            defaultValue: 'This world has no bible anchor yet — lore authoring is unavailable.',
          })}
        </p>
      ) : (
        <div className="flex flex-wrap items-end gap-2">
          <label className="space-y-1">
            <span className="block text-xs font-medium">{t('lore.kindLabel', { defaultValue: 'Kind' })}</span>
            <select
              value={kindId}
              onChange={(e) => setKindId(e.target.value)}
              disabled={kindsLoading}
              className="rounded-md border bg-background px-3 py-2 text-sm"
              data-testid="world-lore-kind"
            >
              <option value="">{t('lore.kindPlaceholder', { defaultValue: 'Choose a kind…' })}</option>
              {kinds.map((k) => (
                <option key={k.kind_id} value={k.kind_id}>
                  {k.name}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            onClick={submit}
            disabled={!kindId || isAuthoring}
            className="rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
            data-testid="world-lore-add"
          >
            {isAuthoring
              ? t('lore.adding', { defaultValue: 'Adding…' })
              : t('lore.add', { defaultValue: 'Add lore' })}
          </button>
        </div>
      )}
    </section>
  );
}

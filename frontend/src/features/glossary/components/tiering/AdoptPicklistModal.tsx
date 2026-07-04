import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Check } from 'lucide-react';
import { FormDialog } from '@/components/shared';
import type { AdoptRequest } from '../../tieringTypes';
import type { StandardPick } from '../../hooks/useStandards';
import { TierChip } from './TierChip';

type Props = {
  genres: StandardPick[];
  kinds: StandardPick[];
  loading: boolean;
  onAdopt: (req: AdoptRequest) => Promise<void>;
  onClose: () => void;
};

/** R1 pick-list: choose which standard genres + kinds to copy down into the book.
 *  `universal` is always adopted (O4) and the `unknown` kind is always adopted (E6),
 *  so they're shown pre-checked + disabled. */
export function AdoptPicklistModal({ genres, kinds, loading, onAdopt, onClose }: Props) {
  const { t } = useTranslation('glossaryTiering');
  const [pickedGenres, setPickedGenres] = useState<Set<string>>(new Set());
  const [pickedKinds, setPickedKinds] = useState<Set<string>>(new Set());
  const [submitting, setSubmitting] = useState(false);

  const toggle = (set: Set<string>, setter: (s: Set<string>) => void, code: string) => {
    const next = new Set(set);
    if (next.has(code)) next.delete(code);
    else next.add(code);
    setter(next);
  };

  const submit = async () => {
    setSubmitting(true);
    try {
      await onAdopt({ genres: [...pickedGenres], kinds: [...pickedKinds] });
      onClose();
    } finally {
      setSubmitting(false);
    }
  };

  const canSubmit = !submitting && (pickedGenres.size > 0 || pickedKinds.size > 0);

  const renderItem = (
    item: StandardPick,
    picked: Set<string>,
    setter: (s: Set<string>) => void,
    mandatory: boolean,
  ) => {
    const on = mandatory || picked.has(item.code);
    return (
      <button
        key={item.tier + item.code}
        type="button"
        disabled={mandatory || submitting}
        onClick={() => toggle(picked, setter, item.code)}
        data-testid={`adopt-pick-${item.code}`}
        className={`flex w-full items-center gap-2 rounded-md border px-2.5 py-1.5 text-left text-sm transition-colors ${
          on ? 'border-primary/50 bg-primary/5' : 'hover:bg-secondary'
        } ${mandatory ? 'opacity-70' : ''}`}
      >
        <span
          className={`flex h-4 w-4 items-center justify-center rounded border ${on ? 'border-primary bg-primary text-primary-foreground' : 'border-input'}`}
        >
          {on && <Check className="h-3 w-3" />}
        </span>
        <span className="flex-1 truncate">
          {item.icon} {item.code}
        </span>
        {mandatory ? (
          <span className="text-[10px] text-muted-foreground">{t('adopt.universal_mandatory')}</span>
        ) : (
          <TierChip tier={item.tier} />
        )}
      </button>
    );
  };

  return (
    <FormDialog
      open
      onOpenChange={(next) => { if (!next && !submitting) onClose(); }}
      title={t('adopt.title')}
      description={t('adopt.subtitle')}
      size="2xl"
      footer={
        <>
          <span className="mr-auto text-[11px] text-muted-foreground">
            {!canSubmit && !submitting ? t('adopt.none_selected') : ''}
          </span>
          <button onClick={onClose} disabled={submitting} className="rounded-md border px-3 py-1.5 text-xs font-medium hover:bg-secondary disabled:opacity-50">
            {t('adopt.cancel')}
          </button>
          <button
            onClick={() => void submit()}
            disabled={!canSubmit}
            className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
          >
            {submitting ? t('adopt.adopting') : t('adopt.submit')}
          </button>
        </>
      }
    >
      <div className="grid grid-cols-2 gap-4">
        <section>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            {t('adopt.genres')}
          </h3>
          <div className="space-y-1">
            {loading && <p className="text-xs text-muted-foreground">{t('adopt.loading')}</p>}
            {!loading && genres.length === 0 && (
              <p className="text-xs text-muted-foreground">{t('adopt.empty')}</p>
            )}
            {genres.map((g) => renderItem(g, pickedGenres, setPickedGenres, g.code === 'universal'))}
          </div>
        </section>
        <section>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            {t('adopt.kinds')}
          </h3>
          <div className="space-y-1">
            {kinds.map((k) => renderItem(k, pickedKinds, setPickedKinds, k.code === 'unknown'))}
          </div>
          <p className="mt-2 text-[11px] text-muted-foreground">{t('adopt.unknown_auto')}</p>
        </section>
      </div>
    </FormDialog>
  );
}

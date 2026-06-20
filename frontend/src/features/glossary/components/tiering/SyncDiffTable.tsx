import { useTranslation } from 'react-i18next';
import type { SyncChoice, SyncUpdateItem, SyncVals } from '../../tieringTypes';
import { FieldTypeBadge } from './FieldTypeBadge';

/** Compact before→after summary of one row's semantic fields. */
function ValsCell({ v }: { v?: SyncVals | null }) {
  if (!v) return <span className="italic text-muted-foreground">—</span>;
  return (
    <div className="space-y-0.5">
      <div className="font-medium">{v.name}</div>
      {v.field_type && <FieldTypeBadge fieldType={v.field_type} />}
      {v.description && <div className="text-[11px] text-muted-foreground">{v.description}</div>}
    </div>
  );
}

type Props = {
  updates: SyncUpdateItem[];
  choiceFor: (id: string) => SyncChoice;
  setChoice: (id: string, c: SyncChoice) => void;
};

/** 04-sync diff table. Each backend update is one atomic row (genre/kind/attribute).
 *  update_available rows carry a keep_mine|take_theirs toggle; source_retired rows are
 *  informational (the book copy stays frozen — nothing to apply). */
export function SyncDiffTable({ updates, choiceFor, setChoice }: Props) {
  const { t } = useTranslation('glossaryTiering');

  return (
    <div className="overflow-auto rounded-lg border bg-card">
      <table className="w-full text-left text-[13px]">
        <thead className="border-b bg-muted/40 text-xs uppercase tracking-wide text-muted-foreground">
          <tr>
            <th className="px-3 py-2 font-semibold">{t('matrix.col_attribute')}</th>
            <th className="px-3 py-2 font-semibold">{t('sync.mine')}</th>
            <th className="px-3 py-2 font-semibold">{t('sync.theirs')}</th>
            <th className="px-3 py-2 text-right font-semibold">{t('sync.choice')}</th>
          </tr>
        </thead>
        <tbody className="divide-y">
          {updates.map((u) => {
            const retired = u.status === 'source_retired';
            const choice = choiceFor(u.id);
            return (
              <tr key={u.entity + u.id} className={retired ? 'bg-rose-50 dark:bg-rose-950/30' : ''}>
                <td className="px-3 py-2 align-top">
                  <div className="font-mono font-semibold">{u.code}</div>
                  <div className="text-[10px] uppercase text-muted-foreground">{t(`sync.entity_${u.entity}`)}</div>
                </td>
                <td className="px-3 py-2 align-top">
                  <ValsCell v={u.mine} />
                </td>
                <td className="px-3 py-2 align-top">
                  {retired ? (
                    <span className="text-[11px] font-medium text-rose-600">{t('sync.source_retired')}</span>
                  ) : (
                    <ValsCell v={u.theirs} />
                  )}
                </td>
                <td className="px-3 py-2 text-right align-top">
                  {retired ? (
                    <span className="text-[11px] text-muted-foreground">{t('sync.source_retired')}</span>
                  ) : (
                    <div className="inline-flex overflow-hidden rounded-md border text-[11px]" role="group">
                      <button
                        type="button"
                        onClick={() => setChoice(u.id, 'keep_mine')}
                        data-testid={`sync-keep-${u.id}`}
                        className={`px-2 py-1 ${choice === 'keep_mine' ? 'bg-primary text-primary-foreground' : 'hover:bg-secondary'}`}
                      >
                        {t('sync.keep_mine')}
                      </button>
                      <button
                        type="button"
                        onClick={() => setChoice(u.id, 'take_theirs')}
                        data-testid={`sync-take-${u.id}`}
                        className={`px-2 py-1 ${choice === 'take_theirs' ? 'bg-sky-500 text-white' : 'hover:bg-secondary'}`}
                      >
                        {t('sync.take_theirs')}
                      </button>
                    </div>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

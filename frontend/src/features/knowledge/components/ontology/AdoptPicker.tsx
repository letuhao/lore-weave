import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { OntologyChip } from './OntologyChip';
import type {
  GraphSchemaSummary,
  NeedsGlossary,
} from '../../types/ontology';

// Render-only adopt picker (mirrors 01-adopt.html). Lists adoptable templates
// (system read-only + user), lets the user pick one + adopt. When the M1
// adopt-gate fires, `needsGlossary` is rendered as the blocker list with a
// glossary deep-link. All logic lives in useOntologyAdopt; this only renders.

interface Props {
  schemas: GraphSchemaSummary[];
  selectedId: string | null;
  onSelect: (schemaId: string) => void;
  onAdopt: (schemaId: string) => void;
  isAdopting: boolean;
  needsGlossary: NeedsGlossary | null;
  onOpenGlossary: (bookId: string | null | undefined) => void;
  onClearGate: () => void;
}

export function AdoptPicker({
  schemas,
  selectedId,
  onSelect,
  onAdopt,
  isAdopting,
  needsGlossary,
  onOpenGlossary,
  onClearGate,
}: Props) {
  const { t } = useTranslation('kgOntology');
  const blocked = !!needsGlossary;

  return (
    <div className="space-y-4" data-testid="adopt-picker">
      <h2 className="text-sm font-bold">{t('adopt.chooseTemplate')}</h2>
      <ul className="grid gap-2 sm:grid-cols-2">
        {schemas.map((s) => {
          const isSel = s.schema_id === selectedId;
          return (
            <li key={s.schema_id}>
              <button
                type="button"
                onClick={() => onSelect(s.schema_id)}
                className={cn(
                  'w-full rounded-md border px-3 py-2 text-left transition',
                  isSel ? 'border-primary ring-1 ring-primary' : 'hover:bg-muted/40',
                )}
                aria-pressed={isSel}
                data-testid={`adopt-template-${s.code}`}
              >
                <div className="flex items-center justify-between">
                  <b className="text-sm">{s.name}</b>
                  <OntologyChip variant={s.scope}>{s.scope}</OntologyChip>
                </div>
                {s.description && (
                  <p className="mt-1 text-[11px] text-muted-foreground">
                    {s.description}
                  </p>
                )}
                <span className="mt-2 inline-block text-[11px] font-medium text-primary">
                  {isSel ? t('adopt.selected') : t('adopt.select')}
                </span>
              </button>
            </li>
          );
        })}
        {schemas.length === 0 && (
          <li className="text-[12px] text-muted-foreground">
            {t('adopt.noTemplates')}
          </li>
        )}
      </ul>

      {blocked && (
        <div
          className="rounded-md border border-rose-200 bg-rose-50 p-3 text-[12px]"
          data-testid="adopt-needs-glossary"
          role="alert"
        >
          <b className="text-rose-700">{t('adopt.blockedTitle')}</b>
          <p className="mt-1 text-slate-600">{t('adopt.blockedHelp')}</p>
          <ul className="mt-2 space-y-1">
            {needsGlossary!.needs_glossary.kinds.map((k) => (
              <li
                key={k}
                className="flex items-center justify-between rounded bg-white/70 px-2 py-1"
              >
                <b>{k}</b>
                <span className="text-rose-700">{t('adopt.missing')}</span>
              </li>
            ))}
          </ul>
          <div className="mt-3 flex gap-2">
            <button
              type="button"
              onClick={() => onOpenGlossary(needsGlossary!.needs_glossary.book_id)}
              className="rounded-md bg-primary px-3 py-1.5 text-[12px] font-medium text-white"
              data-testid="adopt-open-glossary"
            >
              {t('adopt.openGlossary')}
            </button>
            <button
              type="button"
              onClick={onClearGate}
              className="rounded-md border px-3 py-1.5 text-[12px]"
            >
              {t('common.dismiss')}
            </button>
          </div>
        </div>
      )}

      <button
        type="button"
        disabled={!selectedId || isAdopting || blocked}
        onClick={() => selectedId && onAdopt(selectedId)}
        className={cn(
          'w-full rounded-md py-2 text-[12px] font-medium',
          !selectedId || blocked
            ? 'cursor-not-allowed bg-slate-200 text-slate-400'
            : 'bg-primary text-white',
        )}
        data-testid="adopt-submit"
      >
        {blocked
          ? t('adopt.blockedButton', { count: needsGlossary!.needs_glossary.kinds.length })
          : isAdopting
            ? t('adopt.adopting')
            : t('adopt.adoptButton')}
      </button>
    </div>
  );
}

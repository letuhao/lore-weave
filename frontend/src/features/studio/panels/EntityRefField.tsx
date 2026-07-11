// 22-C3b (F2 completion) — the scene-inspector's glossary-ref pickers. A scene's `pov_entity_id`,
// `present_entity_ids`, and `location_entity_id` were the last F2 fields still human-invisible: raw
// UUIDs at best. This resolves them against the book's glossary roster (`useGlossaryRoster` — the
// SAME source the planner cast + canon picker use, DOCK-2 no fork) and renders names, not ids.
//
// Honesty rule: a stored ref that is NOT in the loaded roster (archived entity, or a stale id) is
// shown as a short-id chip, NEVER silently blanked — the reference is a fact even when unresolved.
import { useTranslation } from 'react-i18next';
import type { RosterOption } from '@/features/composition/hooks/useGlossaryRoster';

const shortId = (id: string) => `${id.slice(0, 8)}…`;

interface BaseProps {
  label: string;
  roster: RosterOption[];
  rosterLoading?: boolean;
  testid: string;
}
type SingleProps = BaseProps & { mode: 'single'; value: string | null | undefined; onChange: (id: string | null) => void };
type MultiProps = BaseProps & { mode: 'multi'; value: string[] | undefined; onChange: (ids: string[]) => void };

export function EntityRefField(props: SingleProps | MultiProps) {
  const { t } = useTranslation('studio');
  const { label, roster, rosterLoading, testid } = props;
  const labelFor = (id: string) => roster.find((o) => o.id === id)?.label ?? shortId(id);
  const none = t('panels.scene-inspector.ref.none', { defaultValue: '— none —' });
  const add = t('panels.scene-inspector.ref.add', { defaultValue: '+ add' });

  return (
    <label className="block" data-testid={testid}>
      <span className="mb-0.5 block text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
        {label}
        {rosterLoading && <span className="ml-1 opacity-60">{t('panels.scene-inspector.ref.loading', { defaultValue: '(loading…)' })}</span>}
      </span>

      {props.mode === 'single' ? (
        <select
          data-testid={`${testid}-select`}
          value={props.value ?? ''}
          onChange={(e) => props.onChange(e.target.value || null)}
          className="w-full rounded border bg-background px-2 py-1 text-xs"
        >
          <option value="">{none}</option>
          {/* A stored ref missing from the roster still shows as an option so it is never dropped. */}
          {props.value && !roster.some((o) => o.id === props.value) && (
            <option value={props.value}>{shortId(props.value)}</option>
          )}
          {roster.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
        </select>
      ) : (
        <MultiRef {...props} labelFor={labelFor} addLabel={add} />
      )}
    </label>
  );
}

function MultiRef({ value, roster, onChange, testid, labelFor, addLabel }: MultiProps & { labelFor: (id: string) => string; addLabel: string }) {
  const { t } = useTranslation('studio');
  const ids = value ?? [];
  const inSet = new Set(ids);
  const addable = roster.filter((o) => !inSet.has(o.id));
  const addOne = (id: string) => { if (id && !inSet.has(id)) onChange([...ids, id]); };
  const removeOne = (id: string) => onChange(ids.filter((x) => x !== id));

  return (
    <div className="flex flex-wrap items-center gap-1" data-testid={`${testid}-chips`}>
      {ids.length === 0 && <span className="text-[11px] text-muted-foreground">{t('panels.scene-inspector.ref.empty', { defaultValue: 'none' })}</span>}
      {ids.map((id) => (
        <span key={id} data-testid={`${testid}-chip`} className="inline-flex items-center gap-1 rounded bg-muted px-1.5 py-0.5 text-[11px]">
          {labelFor(id)}
          <button
            type="button"
            data-testid={`${testid}-remove-${id}`}
            className="text-muted-foreground hover:text-destructive"
            onClick={() => removeOne(id)}
            aria-label={t('panels.scene-inspector.ref.remove', { name: labelFor(id), defaultValue: `Remove ${labelFor(id)}` })}
          >×</button>
        </span>
      ))}
      {addable.length > 0 && (
        <select
          data-testid={`${testid}-add`}
          value=""
          onChange={(e) => { addOne(e.target.value); e.currentTarget.value = ''; }}
          className="rounded border bg-background px-1 py-0.5 text-[11px]"
          aria-label={addLabel}
        >
          <option value="">{addLabel}</option>
          {addable.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
        </select>
      )}
    </div>
  );
}

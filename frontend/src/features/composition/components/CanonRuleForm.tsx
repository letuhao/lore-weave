// FD-16 — canon-rule editor (shared by create + edit-in-place). Renders the
// scope-conditional fields the BE already accepts but the old create form
// dropped: an entity picker (scope=entity|reveal_gate) and a reading-order
// reveal window (scope=reveal_gate), plus an active toggle. Pure view: it owns
// only ephemeral form state and calls `onSubmit` with the full payload.
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { CanonRule } from '../types';
import type { RosterOption } from '../hooks/useGlossaryRoster';

export type CanonRulePayload = {
  text: string;
  scope: CanonRule['scope'];
  entity_id: string | null;
  from_order: number | null;
  until_order: number | null;
  active: boolean;
};

type Props = {
  initial?: CanonRule;
  roster: RosterOption[];
  rosterLoading: boolean;
  pending: boolean;
  submitLabel: string;
  onSubmit: (payload: CanonRulePayload) => void;
  onCancel?: () => void;
};

const numOrNull = (v: string): number | null => (v.trim() === '' ? null : Number(v));

export function CanonRuleForm({
  initial, roster, rosterLoading, pending, submitLabel, onSubmit, onCancel,
}: Props) {
  const { t } = useTranslation('composition');
  const [text, setText] = useState(initial?.text ?? '');
  const [scope, setScope] = useState<CanonRule['scope']>(initial?.scope ?? 'world');
  const [entityId, setEntityId] = useState<string>(initial?.entity_id ?? '');
  const [fromOrder, setFromOrder] = useState<string>(initial?.from_order?.toString() ?? '');
  const [untilOrder, setUntilOrder] = useState<string>(initial?.until_order?.toString() ?? '');
  const [active, setActive] = useState<boolean>(initial?.active ?? true);

  const from = numOrNull(fromOrder);
  const until = numOrNull(untilOrder);
  const windowInverted = from !== null && until !== null && from > until;
  const canSubmit = !!text.trim() && !windowInverted && !pending;

  const submit = () => {
    if (!canSubmit) return;
    onSubmit({
      text: text.trim(),
      scope,
      // entity_id only meaningful for entity/reveal_gate scopes.
      entity_id: scope === 'world' ? null : (entityId || null),
      from_order: scope === 'reveal_gate' ? from : null,
      until_order: scope === 'reveal_gate' ? until : null,
      active,
    });
  };

  return (
    <div className="flex flex-col gap-1">
      <textarea
        data-testid="composition-canon-input"
        className="w-full resize-none rounded border border-neutral-300 bg-transparent p-2 dark:border-neutral-600"
        rows={2}
        placeholder={t('rulePlaceholder', { defaultValue: 'A canon rule the co-writer must respect…' })}
        value={text}
        onChange={(e) => setText(e.target.value)}
      />
      <div className="flex flex-wrap items-center gap-2">
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

        {scope !== 'world' && (
          <select
            data-testid="composition-canon-entity"
            className="rounded border border-neutral-300 bg-transparent px-2 py-1 text-xs dark:border-neutral-600"
            value={entityId}
            onChange={(e) => setEntityId(e.target.value)}
            aria-label={t('canonEntity', { defaultValue: 'Entity' })}
            disabled={rosterLoading}
          >
            <option value="">{t('canonEntityNone', { defaultValue: '— any/none —' })}</option>
            {roster.map((o) => (
              <option key={o.id} value={o.id}>{o.label}</option>
            ))}
          </select>
        )}

        {scope === 'reveal_gate' && (
          <>
            <input
              data-testid="composition-canon-from"
              type="number"
              className="w-20 rounded border border-neutral-300 bg-transparent px-2 py-1 text-xs dark:border-neutral-600"
              placeholder={t('canonFrom', { defaultValue: 'from' })}
              aria-label={t('canonFrom', { defaultValue: 'From (reading order)' })}
              value={fromOrder}
              onChange={(e) => setFromOrder(e.target.value)}
            />
            <input
              data-testid="composition-canon-until"
              type="number"
              className="w-20 rounded border border-neutral-300 bg-transparent px-2 py-1 text-xs dark:border-neutral-600"
              placeholder={t('canonUntil', { defaultValue: 'until' })}
              aria-label={t('canonUntil', { defaultValue: 'Until (reading order)' })}
              value={untilOrder}
              onChange={(e) => setUntilOrder(e.target.value)}
            />
          </>
        )}

        <label className="flex items-center gap-1 text-xs text-neutral-500">
          <input
            data-testid="composition-canon-active"
            type="checkbox"
            checked={active}
            onChange={(e) => setActive(e.target.checked)}
          />
          {t('canonActive', { defaultValue: 'active' })}
        </label>

        <button
          data-testid="composition-canon-submit"
          className="rounded bg-indigo-600 px-3 py-1 text-xs text-white disabled:opacity-50"
          disabled={!canSubmit}
          onClick={submit}
        >
          {submitLabel}
        </button>
        {onCancel && (
          <button
            data-testid="composition-canon-cancel"
            className="rounded px-2 py-1 text-xs text-neutral-500 hover:text-neutral-800 dark:hover:text-neutral-200"
            onClick={onCancel}
          >
            {t('cancel', { defaultValue: 'Cancel' })}
          </button>
        )}
      </div>
      {windowInverted && (
        <span data-testid="composition-canon-window-error" className="text-[11px] text-red-600">
          {t('canonWindowInverted', { defaultValue: "'From' must be ≤ 'Until'." })}
        </span>
      )}
    </div>
  );
}

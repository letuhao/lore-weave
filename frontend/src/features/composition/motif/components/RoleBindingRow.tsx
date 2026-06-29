// W6 §3.4 — role → cast chip. Resolved → a chip with the cast name; unresolved →
// an inline picker (the present_entity_names_unresolved pattern, §11). Render-only.
import { useTranslation } from 'react-i18next';
import type { RoleBinding } from '../types';
import type { RosterOption } from '../../hooks/useGlossaryRoster';

type Props = {
  roleKey: string;
  roleLabel: string;
  binding: RoleBinding;
  options: RosterOption[];
  onPick: (entityId: string) => void;
};

export function RoleBindingRow({ roleKey, roleLabel, binding, options, onPick }: Props) {
  const { t } = useTranslation('composition');
  const resolved = binding.entity_id != null;

  return (
    <div data-testid={`motif-role-${roleKey}`} className="flex items-center justify-between gap-2 text-xs">
      <span className="text-neutral-500">{roleLabel}</span>
      {resolved ? (
        <span data-testid={`motif-role-${roleKey}-resolved`} className="rounded bg-indigo-100 px-1.5 py-0.5 text-indigo-700 dark:bg-indigo-950/40 dark:text-indigo-300">
          {binding.entity_name}
        </span>
      ) : (
        <select
          data-testid={`motif-role-${roleKey}-picker`}
          aria-label={t('motif.role.pickFor', { role: roleLabel, defaultValue: 'Pick cast for {{role}}' })}
          className="rounded border border-amber-400 px-1 py-0.5 text-amber-700 dark:bg-neutral-800 dark:text-amber-300"
          value=""
          onChange={(e) => e.target.value && onPick(e.target.value)}
        >
          <option value="">{t('motif.role.unresolved', { defaultValue: '⚠ pick…' })}</option>
          {options.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
        </select>
      )}
    </div>
  );
}

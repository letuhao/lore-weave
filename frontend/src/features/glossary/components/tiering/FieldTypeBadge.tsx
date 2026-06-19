// G6 — monospace field-type badge (the draft's `ft` chip).
import type { FieldType } from '../../tieringTypes';

export function FieldTypeBadge({ fieldType }: { fieldType: FieldType }) {
  return (
    <span className="rounded bg-sky-50 px-1 py-0.5 font-mono text-[10px] text-slate-500">
      {fieldType}
    </span>
  );
}

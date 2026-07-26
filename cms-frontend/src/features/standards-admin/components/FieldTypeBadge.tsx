// G-C2 — monospace field-type badge (ported from the user-tier tiering badge),
// typed to the CMS FieldType. No i18n.
import type { FieldType } from '../types';

export function FieldTypeBadge({ fieldType }: { fieldType: FieldType }) {
  return (
    <span className="rounded bg-sky-50 px-1 py-0.5 font-mono text-[10px] text-slate-500">
      {fieldType}
    </span>
  );
}

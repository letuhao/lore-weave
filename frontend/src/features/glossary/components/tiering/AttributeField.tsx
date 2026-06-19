import type { BookAttribute } from '../../tieringTypes';
import { TierChip } from './TierChip';
import { tierFromSourceRef } from '../../lib/tiering';

const INPUT_CLASS =
  'w-full rounded-md border bg-background px-2.5 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-ring/40';

/** A single entity-form field, rendered by the attribute's field_type. Controlled —
 *  value is the string form of the attribute value (mirrors entity_attribute_values
 *  original_value); the host owns persistence. `labelCode` carries the namespaced
 *  code·genre when the same code appears across genres (keep-both). */
export function AttributeField({
  attr,
  labelCode,
  value,
  onChange,
}: {
  attr: BookAttribute;
  labelCode: string;
  value: string;
  onChange: (v: string) => void;
}) {
  const field = (() => {
    switch (attr.field_type) {
      case 'textarea':
        return <textarea value={value} onChange={(e) => onChange(e.target.value)} rows={2} className={INPUT_CLASS} />;
      case 'select':
        return (
          <select value={value} onChange={(e) => onChange(e.target.value)} className={INPUT_CLASS}>
            <option value="">—</option>
            {attr.options.map((o) => (
              <option key={o} value={o}>
                {o}
              </option>
            ))}
          </select>
        );
      case 'boolean':
        return (
          <input
            type="checkbox"
            checked={value === 'true'}
            onChange={(e) => onChange(e.target.checked ? 'true' : 'false')}
          />
        );
      case 'number':
        return <input type="number" value={value} onChange={(e) => onChange(e.target.value)} className={INPUT_CLASS} />;
      case 'date':
        return <input type="date" value={value} onChange={(e) => onChange(e.target.value)} className={INPUT_CLASS} />;
      default:
        return (
          <input
            type={attr.field_type === 'url' ? 'url' : 'text'}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            placeholder={attr.description ?? ''}
            className={INPUT_CLASS}
          />
        );
    }
  })();

  return (
    <label className="block">
      <span className="mb-1 flex items-center gap-1.5 text-xs font-medium">
        <span className="font-mono">{labelCode}</span>
        {attr.is_required && <span className="text-destructive">*</span>}
        <TierChip tier={tierFromSourceRef(attr.source_ref)} />
      </span>
      {field}
    </label>
  );
}

// G-C2 — read-only side inspector for a System attribute (adapted from the user-tier
// MatrixCellInspector). System is single-tier, so there is NO TierChip / source_ref here.
import type { SystemAttribute, SystemGenre } from '../types';
import { FieldTypeBadge } from './FieldTypeBadge';

export function AttributeInspector({
  attribute,
  genre,
}: {
  attribute: SystemAttribute | null;
  genre?: SystemGenre | null;
}) {
  if (!attribute) {
    return (
      <div className="rounded-lg border border-border bg-card p-4 text-xs text-muted-foreground">
        Select an attribute to inspect.
      </div>
    );
  }

  const options = attribute.options ?? [];

  return (
    <div className="space-y-3 rounded-lg border border-border bg-card p-4">
      <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Attribute detail
      </div>
      <div className="flex items-center gap-2">
        <span className="font-mono text-sm font-semibold text-foreground">{attribute.code}</span>
        {genre && (
          <span className="text-xs" style={genre.color ? { color: genre.color } : undefined}>
            · {genre.name}
          </span>
        )}
      </div>
      <div className="text-sm font-medium text-foreground">{attribute.name}</div>
      <div>
        <FieldTypeBadge fieldType={attribute.field_type} />
      </div>
      {attribute.description && (
        <p className="text-[13px] text-foreground/80">{attribute.description}</p>
      )}
      {attribute.field_type === 'select' && options.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {options.map((o) => (
            <span
              key={o}
              className="rounded border border-border bg-secondary px-1.5 py-0.5 text-[11px]"
            >
              {o}
            </span>
          ))}
        </div>
      )}
      <div className="text-[11px] text-muted-foreground">
        required: {attribute.is_required ? 'yes' : 'no'} · sort: {attribute.sort_order}
      </div>
    </div>
  );
}

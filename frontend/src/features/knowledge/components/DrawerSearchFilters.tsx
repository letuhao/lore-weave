import { useId } from 'react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { DRAWER_SOURCE_TYPES, type DrawerSourceType } from '../api';

// C8 (D-K19e-γa-01) — single-select pill row for filtering drawer
// search hits by source_type. Uses native <input type="radio"> + label
// for free WAI-ARIA radio-group keyboard semantics (arrow keys, tab
// into the group, space/enter to select). Styled as pills via
// `peer` + `peer-checked:` tailwind classes on the label.
//
// ``value = null`` means "Any" (no filter); the BE handler treats
// omission as "no source_type filter".
//
// Counts are passed in from useDrawerSearch.sourceTypeCounts — always
// padded with the 3 known types at 0 when data isn't loaded yet, so
// the pill layout is stable across loading / disabled / error states.

export interface DrawerSearchFiltersProps {
  value: DrawerSourceType | null;
  counts: Record<string, number>;
  onChange: (value: DrawerSourceType | null) => void;
  disabled?: boolean;
}

// C8 /review-impl [MED#2]: derived from DRAWER_SOURCE_TYPES so a 4th
// type is a single edit in api.ts + locale JSON — no drift here.
// "Any" row is prepended because it has no matching source_type value.
const OPTIONS: ReadonlyArray<{
  value: DrawerSourceType | null;
  i18nKey: string;
  testid: string;
}> = [
  { value: null, i18nKey: 'any', testid: 'drawers-filter-any' },
  ...DRAWER_SOURCE_TYPES.map((v) => ({
    value: v,
    i18nKey: v,
    testid: `drawers-filter-${v}`,
  })),
];

export function DrawerSearchFilters({
  value,
  counts,
  onChange,
  disabled,
}: DrawerSearchFiltersProps) {
  const { t } = useTranslation('knowledge');
  const groupId = useId();

  return (
    <fieldset
      className="flex flex-col gap-1 text-[11px]"
      data-testid="drawers-filter-source-type"
      disabled={disabled}
    >
      <legend className="text-muted-foreground">
        {t('drawers.filters.sourceType.label')}
      </legend>
      <div
        role="radiogroup"
        aria-label={t('drawers.filters.sourceType.label')}
        className="flex flex-wrap items-center gap-1.5"
      >
        {OPTIONS.map((opt) => {
          const checked = value === opt.value;
          const id = `${groupId}-${opt.i18nKey}`;
          // Count: omitted for "Any" (total isn't useful when no filter);
          // shown for each type as "(N)".
          // Parens anchor reader intent: "Any" has no count; typed
          // pills show 0 when BE omits the key (defense-in-depth).
          const count =
            opt.value == null ? undefined : (counts[opt.value] ?? 0);
          return (
            <span key={opt.i18nKey}>
              <input
                id={id}
                type="radio"
                name={`${groupId}-source-type`}
                className="peer sr-only"
                checked={checked}
                onChange={() => onChange(opt.value)}
                data-testid={opt.testid}
                disabled={disabled}
              />
              <label
                htmlFor={id}
                className={cn(
                  'inline-flex cursor-pointer select-none items-center gap-1 rounded-full border px-2.5 py-1 text-[11px] transition-colors',
                  'hover:bg-secondary',
                  'peer-focus-visible:ring-2 peer-focus-visible:ring-ring peer-focus-visible:ring-offset-1',
                  'peer-checked:border-primary peer-checked:bg-primary/10 peer-checked:text-foreground',
                  'peer-disabled:cursor-not-allowed peer-disabled:opacity-50',
                )}
              >
                {t(`drawers.filters.sourceType.${opt.i18nKey}`)}
                {count != null && (
                  <span
                    className="tabular-nums text-muted-foreground"
                    data-testid={`${opt.testid}-count`}
                  >
                    ({count})
                  </span>
                )}
              </label>
            </span>
          );
        })}
      </div>
    </fieldset>
  );
}

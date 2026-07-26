import { LANGUAGE_NAMES, getLanguageName } from '../../lib/languages';

export interface LanguagePickerProps {
  /** Current language code (controlled). Empty string means "none selected". */
  value: string;
  onChange: (code: string) => void;
  /**
   * When provided, renders a leading empty option with this label
   * (e.g. "Select language…"). Omit for a required picker with no empty slot.
   */
  placeholder?: string;
  /**
   * D13 — restrict the option set to exactly these codes, in this order (e.g. the closed
   * TRANSLATION_TARGETS for a translate-target picker). Omit to offer the full registry.
   */
  codes?: readonly string[];
  /** Codes to omit from the list (e.g. languages already added elsewhere). */
  exclude?: string[];
  id?: string;
  className?: string;
  disabled?: boolean;
  'aria-label'?: string;
  'data-testid'?: string;
}

const BASE_CLS =
  'h-9 w-full rounded-md border bg-background px-3 text-sm focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30';

/**
 * Reusable language picker — a dropdown over the canonical {@link LANGUAGE_NAMES}
 * list, rendering each as "Native name (code)". Replaces the free-text language
 * inputs scattered across book creation, settings, campaigns, and entity editing.
 *
 * Data-loss guard: if {@link value} is a code that is not in the list (or is
 * excluded), it is still rendered as a selectable option so editing an existing
 * resource never silently blanks an unrecognised language.
 */
export function LanguagePicker({
  value,
  onChange,
  placeholder,
  codes,
  exclude,
  id,
  className,
  disabled,
  'aria-label': ariaLabel,
  'data-testid': dataTestId,
}: LanguagePickerProps) {
  const excludeSet = new Set(exclude ?? []);
  const base: [string, string][] = codes
    ? codes.map((code) => [code, LANGUAGE_NAMES[code] ?? code])
    : Object.entries(LANGUAGE_NAMES);
  const options = base.filter(([code]) => !excludeSet.has(code));
  const valueInOptions = options.some(([code]) => code === value);
  const showOrphanValue = value !== '' && !valueInOptions;

  return (
    <select
      id={id}
      value={value}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value)}
      className={className ?? BASE_CLS}
      aria-label={ariaLabel}
      data-testid={dataTestId}
    >
      {placeholder !== undefined && <option value="">{placeholder}</option>}
      {showOrphanValue && (
        <option value={value}>
          {LANGUAGE_NAMES[value] ? `${getLanguageName(value)} (${value})` : value}
        </option>
      )}
      {options.map(([code, name]) => (
        <option key={code} value={code}>
          {name} ({code})
        </option>
      ))}
    </select>
  );
}

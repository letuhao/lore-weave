// AI-Task Standard — one decimal-validated USD spend-cap input, consolidating the
// copy-pasted `DECIMAL_RE` / `DECIMAL_REGEX` / ad-hoc `<input type=number>` across
// GenerateWikiDialog, BuildGraphDialog, ComposeConfig, GapsPanel.

const DECIMAL_RE = /^\d+(\.\d{1,2})?$/;

/** An empty string is VALID (no cap); otherwise it must be a non-negative decimal
 *  with ≤2 fraction digits. Callers send the cap only when non-empty + valid. */
export function isValidSpend(value: string): boolean {
  return value === '' || DECIMAL_RE.test(value);
}

interface Props {
  value: string;
  onChange: (value: string) => void;
  label?: string;
  hint?: string;
  invalidLabel?: string;
  placeholder?: string;
  disabled?: boolean;
  testid?: string;
}

export function SpendCapField({
  value, onChange, label, hint, invalidLabel, placeholder = '0.00', disabled, testid = 'spend-cap',
}: Props) {
  const valid = isValidSpend(value);
  return (
    <label className="flex flex-col gap-1">
      {label && <span className="text-xs font-medium text-muted-foreground">{label}</span>}
      <input
        type="text"
        inputMode="decimal"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        aria-invalid={!valid}
        disabled={disabled}
        data-testid={testid}
        className="rounded-md border bg-input px-3 py-2 text-sm outline-none focus:border-ring aria-[invalid=true]:border-destructive disabled:opacity-50"
      />
      {hint && <span className="text-[11px] text-muted-foreground">{hint}</span>}
      {!valid && invalidLabel && <span className="text-[11px] text-destructive">{invalidLabel}</span>}
    </label>
  );
}

// K19b.6 — USD formatter shared between CostSummary and any other
// surface that renders a Decimal-shaped USD amount (e.g. BuildGraphDialog's
// monthly-remaining hint). BE ships Decimal fields as JSON strings like
// "1234.56" / "0.0001"; `Intl.NumberFormat` adds locale-default grouping
// and the currency symbol. Falls back to a plain `$X` if the value isn't
// a finite number.

const USD_FORMATTER = new Intl.NumberFormat(undefined, {
  style: 'currency',
  currency: 'USD',
  minimumFractionDigits: 2,
  maximumFractionDigits: 4,
});

export function formatUSD(raw: string | null): string {
  if (raw == null) return '—';
  const n = Number(raw);
  return Number.isFinite(n) ? USD_FORMATTER.format(n) : `$${raw}`;
}

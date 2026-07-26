// F2 (DBT-14) — the timezone-confirm banner. Shows once (until the user sets a zone) so the distiller
// buckets each day by the right LOCAL day. Pure view: the detected zone + the confirm action come from
// the hook. A curated common-zone list + the detected zone cover the picker without a full tz database.
import { useState } from 'react';

interface Props {
  detected: string;
  saving: boolean;
  onConfirm: (tz: string) => void;
}

// A small curated set of common IANA zones (+ the detected one is always injected first).
const COMMON_ZONES = [
  'UTC',
  'America/Los_Angeles',
  'America/New_York',
  'America/Sao_Paulo',
  'Europe/London',
  'Europe/Berlin',
  'Europe/Moscow',
  'Africa/Cairo',
  'Asia/Kolkata',
  'Asia/Bangkok',
  'Asia/Shanghai',
  'Asia/Tokyo',
  'Asia/Ho_Chi_Minh',
  'Australia/Sydney',
];

export function TimezoneConfirm({ detected, saving, onConfirm }: Props) {
  const [picking, setPicking] = useState(false);
  const [choice, setChoice] = useState(detected);
  const zones = COMMON_ZONES.includes(detected) ? COMMON_ZONES : [detected, ...COMMON_ZONES];

  return (
    <div
      data-testid="timezone-confirm"
      className="rounded-lg border border-border bg-card p-3 text-sm"
    >
      <div className="font-medium">Confirm your time zone</div>
      <p className="mt-1 text-xs text-muted-foreground">
        Your journal groups each day by your local time. We detected{' '}
        <span data-testid="tz-detected" className="font-medium text-foreground">
          {detected}
        </span>
        .
      </p>
      {!picking ? (
        <div className="mt-2 flex items-center gap-2">
          <button
            type="button"
            data-testid="tz-use-detected"
            disabled={saving}
            onClick={() => onConfirm(detected)}
            className="rounded-md border border-border bg-secondary px-3 py-1 text-xs font-medium disabled:opacity-50"
          >
            {saving ? 'Saving…' : 'Use this'}
          </button>
          <button
            type="button"
            data-testid="tz-pick-another"
            disabled={saving}
            onClick={() => setPicking(true)}
            className="text-xs text-muted-foreground underline-offset-2 hover:underline disabled:opacity-50"
          >
            Pick another
          </button>
        </div>
      ) : (
        <div className="mt-2 flex items-center gap-2">
          <select
            data-testid="tz-select"
            value={choice}
            onChange={(e) => setChoice(e.target.value)}
            className="rounded-md border border-border bg-background px-2 py-1 text-xs"
          >
            {zones.map((z) => (
              <option key={z} value={z}>
                {z}
              </option>
            ))}
          </select>
          <button
            type="button"
            data-testid="tz-save-choice"
            disabled={saving}
            onClick={() => onConfirm(choice)}
            className="rounded-md border border-border bg-secondary px-3 py-1 text-xs font-medium disabled:opacity-50"
          >
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
      )}
    </div>
  );
}

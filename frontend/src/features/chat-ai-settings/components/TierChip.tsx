// The ONE tier chip (spec 2026-07-05-chat-ai-settings.md §3.1, finding UX-5).
//
// Every settings row shows the tier that supplied its value. This is the whole
// anti-silent affordance: a blank control that quietly carries a provider default is
// the bug class G2 exists to kill, and "the system default, surfaced" must look
// different from "you set this".
//
// **Chips key on `source_tier`, never on value-equality.** "Set here · happens to equal
// your account default" is NOT "inherited" — the user must still be able to clear it.
// A component that compared values would render the two identically and hide the
// override, so the clear affordance would never appear.

const CLS: Record<string, string> = {
  session: 'bg-indigo-50 text-indigo-700 border-indigo-200',
  book: 'bg-violet-50 text-violet-700 border-violet-200',
  account: 'bg-teal-50 text-teal-700 border-teal-200',
  system: 'bg-amber-50 text-amber-700 border-amber-200',
  unavailable: 'bg-rose-50 text-rose-700 border-rose-200',
  no_model_configured: 'bg-muted text-muted-foreground border-border',
};

const LABEL: Record<string, string> = {
  session: 'this chat',
  book: 'this book',
  account: 'your default',
  system: 'default',
  unavailable: 'unavailable',
  no_model_configured: 'not set',
};

const TITLE: Record<string, string> = {
  session: 'Set on this chat — overrides your account and book defaults.',
  book: "Inherited from this book's settings.",
  account: 'Inherited from your account default.',
  system: 'The system default. Nobody has set this — the value is shown, not hidden.',
  unavailable: 'The tier that owns this value could not be reached, so it is not applied.',
  no_model_configured: 'No live model at any tier. Pick one before sending.',
};

export function TierChip({ tier }: { tier: string | null | undefined }) {
  if (!tier) return null;
  return (
    <span
      title={TITLE[tier] ?? tier}
      data-testid={`tier-chip-${tier}`}
      className={`ml-2 rounded border px-1.5 py-0.5 text-[10px] font-medium ${
        CLS[tier] ?? 'bg-muted text-muted-foreground border-border'
      }`}
    >
      {LABEL[tier] ?? tier}
    </span>
  );
}

/**
 * "Clear override → inherit (would be Z)". Rendered only when the SESSION row actually
 * carries the field, and it always names the value that would take over — a clear button
 * that doesn't say what you'd get is a dare, not an affordance (finding UX-5).
 */
export function ClearOverride({
  show,
  inherited,
  onClear,
  testId,
}: {
  show: boolean;
  inherited: unknown;
  onClear: () => void;
  testId: string;
}) {
  if (!show) return null;
  const shown =
    inherited === null || inherited === undefined ? 'the default'
    : typeof inherited === 'boolean' ? (inherited ? 'on' : 'off')
    : String(inherited);
  return (
    <button
      type="button"
      data-testid={testId}
      onClick={onClear}
      className="ml-2 text-[10px] font-medium text-muted-foreground underline underline-offset-2 hover:text-foreground"
    >
      clear · inherit {shown}
    </button>
  );
}

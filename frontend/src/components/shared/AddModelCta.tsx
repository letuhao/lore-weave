import { Link, useLocation } from 'react-router-dom';
import { Plus } from 'lucide-react';
import { cn } from '@/lib/utils';

/**
 * C0 (G6) — reusable "register a model" call-to-action.
 *
 * The model-registration surface is the settings Providers tab
 * (`/settings/providers`), opened as a modal per provider. When a form needs a
 * model the user hasn't registered yet (e.g. BuildGraphDialog with no embedding
 * model — C5, or Compose with no chat model — C15), this CTA deep-links there
 * AND carries a `return` path so the user can round-trip back to where they
 * were. ProvidersTab reads `?return=` and renders a "← Back" banner.
 *
 * Honoring the return path is the point: a one-way link that drops it would
 * leave the user stranded on the settings page after registering (the G6
 * book-workspace navigation glue, adversary-flagged in the C0 brief).
 */
const REGISTRATION_PATH = '/settings/providers';

interface Props {
  /** Where to send the user back after they register. Defaults to the current location. */
  returnTo?: string;
  /** Optional capability hint surfaced in the default label (e.g. "embedding", "chat"). */
  capability?: string;
  /** Override the button label entirely. */
  label?: string;
  /** Visual variant. `button` = filled CTA; `link` = inline text link. */
  variant?: 'button' | 'link';
  className?: string;
}

export function AddModelCta({ returnTo, capability, label, variant = 'button', className }: Props) {
  const location = useLocation();
  // Default the return target to wherever the CTA is rendered, preserving query.
  const back = returnTo ?? `${location.pathname}${location.search}`;
  const to = `${REGISTRATION_PATH}?return=${encodeURIComponent(back)}`;

  const text =
    label ?? (capability ? `Add a ${capability} model` : 'Add a model');

  if (variant === 'link') {
    return (
      <Link
        to={to}
        className={cn(
          'inline-flex items-center gap-1 text-xs font-medium text-primary underline-offset-2 hover:underline',
          className,
        )}
      >
        <Plus className="h-3 w-3" />
        {text}
      </Link>
    );
  }

  return (
    <Link
      to={to}
      className={cn(
        'inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground transition-colors hover:bg-primary/90',
        className,
      )}
    >
      <Plus className="h-3.5 w-3.5" />
      {text}
    </Link>
  );
}

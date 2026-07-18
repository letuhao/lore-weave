import { Link, useLocation } from 'react-router-dom';
import { Plus } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useOptionalStudioHost } from '@/features/studio/host/StudioHostProvider';
import { followStudioLink } from '@/features/studio/host/studioLinks';

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
 *
 * X-1 / DOCK-7 — this CTA is rendered by EVERY ModelPicker empty state, and those pickers live
 * both on classic route pages AND inside studio dock panels (Motif Mine, Conformance Run, Arc
 * Import, every plan_* BYOK pass). A bare <Link> inside a dock panel navigates the SPA away from
 * the studio and unmounts the ENTIRE dockview layout — the user loses their whole workspace just
 * by clicking "Add a model". So branch on whether a StudioHost exists, exactly as StepConfig.tsx
 * does (the shipped precedent).
 *
 * ⚠ The studio branch renders a real <button>, NOT a <Link> with onClick+preventDefault: a
 * preventDefault-ed <Link> still emits an <a href> that a middle-click or ⌘-click NAVIGATES,
 * tearing the dock down by the exact path this fix exists to close.
 *
 * ⚠ It follows the BARE REGISTRATION_PATH, not `to`. resolveStudioLink strips the query before
 * matching (studioLinks.ts:76) and SETTINGS_RE (:110-111) maps `/settings/providers` →
 * openPanel('settings', { tab: 'providers' }). The `?return=` round-trip is MEANINGLESS in the
 * studio: the dock never navigates away, so the caller's panel stays mounted and there is nothing
 * to come back from. Re-deriving that path→panel mapping here would be a second copy of a rule
 * studioLinks.ts already owns.
 *
 * The ~8 call sites (ModelPicker, CompositionPanel, BuildGraphDialog, EmbeddingModelPicker,
 * RerankModelPicker, DefaultModelsCard, + the two picker re-exports) inherit this for free —
 * fixing it per-call-site would guarantee the 9th one forgets.
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
  // null outside the studio (classic route pages) — the DOCK-7 branch. Safe either way:
  // useLocation() also works inside the studio, whose panels mount under /books/:id/studio.
  const studioHost = useOptionalStudioHost();
  // Default the return target to wherever the CTA is rendered, preserving query.
  const back = returnTo ?? `${location.pathname}${location.search}`;
  const to = `${REGISTRATION_PATH}?return=${encodeURIComponent(back)}`;

  const text =
    label ?? (capability ? `Add a ${capability} model` : 'Add a model');

  // Identical styling on both branches, so `variant` behaves the same in the studio and out of it.
  const isLinkVariant = variant === 'link';
  const classes = isLinkVariant
    ? cn(
        'inline-flex items-center gap-1 text-xs font-medium text-primary underline-offset-2 hover:underline',
        className,
      )
    : cn(
        'inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground transition-colors hover:bg-primary/90',
        className,
      );
  const icon = isLinkVariant ? <Plus className="h-3 w-3" /> : <Plus className="h-3.5 w-3.5" />;

  // STUDIO — open the settings panel in the dock. Never an <a>, never a navigation.
  if (studioHost) {
    return (
      <button
        type="button"
        className={classes}
        onClick={() =>
          followStudioLink(REGISTRATION_PATH, studioHost, { bookId: studioHost.bookId })
        }
      >
        {icon}
        {text}
      </button>
    );
  }

  // CLASSIC ROUTE — the original <Link>, `?return=` intact (ProvidersTab honors it there).
  return (
    <Link to={to} className={classes}>
      {icon}
      {text}
    </Link>
  );
}

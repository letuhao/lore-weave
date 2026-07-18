/**
 * Shared Tailwind tap-target constants (promoted from features/knowledge/lib, H-5a).
 * 44×44px is the iOS / Material minimum tap target. Compose via `cn()`.
 *
 * Promoted so studio panels (and any component) can use the convention without a
 * cross-feature import into `features/knowledge`. The knowledge lib re-exports these.
 */

/** Unconditional 44px min-height — for mobile-only shells (`components/mobile/*`). */
export const TOUCH_TARGET_CLASS = 'min-h-[44px]';

/**
 * Mobile-only variant — 44px min-height on <768px, back to default on ≥768px. Use on
 * components that render on BOTH viewports (like studio dock panels) so the dense desktop
 * layout is preserved and only touch gets the comfortable hit area.
 *
 *     className={cn('rounded border px-3 py-1.5 text-xs', TOUCH_TARGET_MOBILE_ONLY_CLASS)}
 */
export const TOUCH_TARGET_MOBILE_ONLY_CLASS = 'min-h-[44px] md:min-h-0';

/**
 * Icon-only mobile-only variant — adds min-width so a small icon still gets a 44px box on
 * touch (pair with `inline-flex items-center justify-center` so the icon re-centers).
 */
export const TOUCH_TARGET_SQUARE_MOBILE_ONLY_CLASS =
  'min-h-[44px] min-w-[44px] md:min-h-0 md:min-w-0';

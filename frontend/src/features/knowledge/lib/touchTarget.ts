/**
 * K19f.5 groundwork — shared Tailwind class constant for interactive
 * elements on mobile shells. 44×44 pixels is the minimum tap target
 * per iOS / Material Design guidelines; mobile variants (GlobalMobile
 * in this cycle, ProjectsMobile + JobsMobile in follow-up cycles)
 * compose this on their buttons / links so the "tap-target audit"
 * doesn't have to chase dozens of one-off sizes.
 *
 * Usage:
 *     className={cn(TOUCH_TARGET_CLASS, 'bg-primary text-primary-foreground')}
 *
 * Only ``min-h`` is applied because most mobile buttons are full-width
 * or wide enough for a comfortable hit area; the min-height is the
 * axis users actually miss on thumbs-flat. Future cycles can add a
 * ``TOUCH_TARGET_SQUARE_CLASS`` variant for icon-only buttons (X,
 * settings, etc.) where width also needs the floor.
 */
export const TOUCH_TARGET_CLASS = 'min-h-[44px]';

/**
 * C5 (D-K19f-ε-01) — conditional variant of ``TOUCH_TARGET_CLASS``
 * for desktop-shared components that need the mobile hit area but
 * must stay at their original size on desktop.
 *
 * Use this when a component renders on BOTH viewports (unlike the
 * mobile-variant components under ``components/mobile/`` which take
 * ``TOUCH_TARGET_CLASS`` unconditionally because they never render
 * on desktop).
 *
 * Composes cleanly via ``cn()``:
 *
 *     className={cn(
 *       'rounded-md border px-3 py-1.5 text-xs',
 *       TOUCH_TARGET_MOBILE_ONLY_CLASS,
 *     )}
 *
 * Result: 44px min-height on <768px viewports; returns to the
 * default (effectively driven by ``text-xs + py-1.5``) on ≥768px.
 */
export const TOUCH_TARGET_MOBILE_ONLY_CLASS = 'min-h-[44px] md:min-h-0';

/**
 * C5 /review-impl HIGH — icon-only variant of
 * ``TOUCH_TARGET_MOBILE_ONLY_CLASS``. Square buttons (X close,
 * settings gear, more-menu kebab) need BOTH min-height AND min-width
 * on mobile because their content (a 16-20px icon) doesn't fill
 * width via padding.
 *
 * Use for any icon-only button that renders on mobile and is the
 * primary interaction point. Triggered by the C5 EntityDetailPanel
 * change — going full-width on mobile meant the overlay-dismiss
 * path disappeared (overlay sits entirely behind the panel), so
 * the X close button became the sole dismiss. A 24×24px X on a
 * phone is a fat-finger magnet.
 *
 * Composes cleanly via ``cn()``:
 *
 *     className={cn(
 *       'rounded-sm p-1 text-muted-foreground hover:text-foreground',
 *       'inline-flex items-center justify-center',
 *       TOUCH_TARGET_SQUARE_MOBILE_ONLY_CLASS,
 *     )}
 *
 * Note the ``inline-flex items-center justify-center`` alongside:
 * the added min-width expands the box, so the icon needs to re-
 * center via flex. Without it the icon sticks to the top-left.
 */
export const TOUCH_TARGET_SQUARE_MOBILE_ONLY_CLASS =
  'min-h-[44px] min-w-[44px] md:min-h-0 md:min-w-0';

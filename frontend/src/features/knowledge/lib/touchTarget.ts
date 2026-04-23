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

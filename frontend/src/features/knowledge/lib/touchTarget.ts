// Promoted to the shared `@/lib/touchTarget` (H-5a) so non-knowledge components (studio
// panels) can use the convention without a cross-feature import. Re-exported here so the
// existing knowledge/mobile consumers keep their import path unchanged.
export {
  TOUCH_TARGET_CLASS,
  TOUCH_TARGET_MOBILE_ONLY_CLASS,
  TOUCH_TARGET_SQUARE_MOBILE_ONLY_CLASS,
} from '@/lib/touchTarget';

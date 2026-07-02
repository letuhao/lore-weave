// #11 F2 — frame-level status-bar contributions. Mounted once inside StudioFrame (inside the
// host provider, OUTSIDE dockview) so every item stays alive while its panel is closed — that's
// the whole point of a badge. New ambient indicators register here, never inside a panel.
import type { StudioStatusBarItem } from '../host/types';
import { useRegisterStatusBarItem } from '../host/StudioHostProvider';
import { NotificationsStatusItem } from './NotificationsStatusItem';
import { UsageCostStatusItem } from './UsageCostStatusItem';
import { WordCountStatusItem } from './WordCountStatusItem';

// Module-level defs = stable identities (no re-register churn on frame re-renders).
const NOTIFICATIONS_ITEM: StudioStatusBarItem = {
  id: 'notifications-unread', side: 'right', order: 10, component: NotificationsStatusItem,
};
const USAGE_ITEM: StudioStatusBarItem = {
  id: 'usage-cost', side: 'right', order: 20, component: UsageCostStatusItem,
};
// #12 M-H — live word count from the manuscript hoist (was a "— words" placeholder).
const WORD_COUNT_ITEM: StudioStatusBarItem = {
  id: 'word-count', side: 'right', order: 30, component: WordCountStatusItem,
};

export function StudioStatusContributions() {
  useRegisterStatusBarItem(NOTIFICATIONS_ITEM);
  useRegisterStatusBarItem(USAGE_ITEM);
  useRegisterStatusBarItem(WORD_COUNT_ITEM);
  return null;
}

import { Bell, Languages, Heart, PenLine, Sparkles, type LucideIcon } from 'lucide-react';

// Single source of truth for notification category metadata, shared by the
// NotificationBell dropdown and the full-page NotificationsPage. (Do NOT inline
// per-component copies — that is the divergence class that bit us in F-3.)

export const CATEGORIES = ['all', 'translation', 'social', 'wiki', 'system'] as const;
export type NotificationCategory = (typeof CATEGORIES)[number];

/** Tinted background per category (matches design-drafts/screen-notifications.html). */
export const CATEGORY_COLORS: Record<string, string> = {
  translation: 'rgba(61,186,106,0.1)',
  social: 'rgba(232,93,117,0.1)',
  wiki: 'rgba(61,166,146,0.1)',
  system: 'rgba(232,168,50,0.1)',
  // R3 (D-PROACTIVE-DELIVERY) — the work-assistant proactive check-in. Given an icon/tint so it renders
  // distinctly; it is intentionally NOT a top-level filter tab (consistent with the other producer-only
  // categories billing/campaign/mcp_approval that also have no tab).
  assistant: 'rgba(120,120,232,0.1)',
};

/** Icon per category (the design uses varied glyphs; we key them by category). */
export const CATEGORY_ICON: Record<string, LucideIcon> = {
  translation: Languages,
  social: Heart,
  wiki: PenLine,
  system: Bell,
  assistant: Sparkles,
};

export function categoryIcon(category: string): LucideIcon {
  return CATEGORY_ICON[category] ?? Bell;
}

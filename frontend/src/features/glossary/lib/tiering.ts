// G6 — shared helpers for the tiered model (provenance + visual coding).

import type { Tier } from '../tieringTypes';

/** Derive a book row's provenance tier from its source_ref ('system:<id>' |
 *  'user:<id>' | null=book-native). Book-native rows render as the 'book' tier. */
export function tierFromSourceRef(sourceRef?: string | null): Tier {
  if (sourceRef?.startsWith('system:')) return 'system';
  if (sourceRef?.startsWith('user:')) return 'user';
  return 'book';
}

/** Tailwind classes for a tier chip — matches the design drafts (slate/indigo/sky). */
export const TIER_CHIP_CLASS: Record<Tier, string> = {
  system: 'bg-slate-100 text-slate-600 border-slate-300',
  user: 'bg-indigo-50 text-indigo-600 border-indigo-300',
  book: 'bg-sky-50 text-sky-700 border-sky-300',
};

export const TIER_LABEL: Record<Tier, string> = {
  system: 'SYS',
  user: 'USER',
  book: 'BOOK',
};

/** A book row sourced from System is read-only here — a regular user clones/overrides
 *  it into their own tier rather than editing the shared original (CLAUDE.md tenancy). */
export function isSystemSourced(sourceRef?: string | null): boolean {
  return tierFromSourceRef(sourceRef) === 'system';
}

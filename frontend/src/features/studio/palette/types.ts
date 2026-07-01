import type { ReactNode } from 'react';

// A palette row (shared by #06a Quick Open + #06b Command Palette). `entries` handed to the
// shell are already filtered + ordered by the owner; the shell only renders + drives keyboard
// selection. `group` (optional) renders a sticky-ish header before the first entry of each group.
export interface PaletteEntry {
  id: string;
  label: string;
  sublabel?: string;   // breadcrumb (Quick Open) / description (Command Palette)
  meta?: ReactNode;    // right-aligned trailing slot (Quick Open: chapter number + status badge)
  group?: string;      // group header label (Command Palette)
  icon?: ReactNode;
}

import { readFileSync, readdirSync } from 'node:fs';
import { resolve, join } from 'node:path';
import { describe, it, expect } from 'vitest';

// Dockable Panel Standard (docs/standards/dockable-gui.md) — DOCK-7 + DOCK-9 mechanical gate.
//
// A panel that route-navigates (DOCK-7) breaks the "studio never unmounts itself" rule; a panel
// that hand-rolls its own viewport overlay (DOCK-9) collides with the studio palette's z-[60] and
// dockview's reserved --dv-overlay-z-index:999 (no shared scale exists), and — per SDK-First
// SDK-1 — duplicates what must be one shared primitive (`components/shared/{FormDialog,
// ConfirmDialog}`). This only scans panels/** (the panels themselves), the same scope
// panelCatalogContract.test.ts uses for the enum — it does not retroactively fail pre-migration
// feature code that hasn't been ported into a panel yet.

const PANELS_DIR = resolve(__dirname, '..');

// Recursive — a panel is not guaranteed to stay a single flat .tsx file (a large migration like
// Glossary is likely to land as panels/glossary/GlossaryPanel.tsx + subcomponents). A non-recursive
// scan would silently stop covering DOCK-7/DOCK-9 the moment a panel grows a subfolder — the
// __tests__ dir is the only skip since it holds this file itself plus co-located unit tests.
function panelSourceFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    if (entry.isDirectory()) {
      return entry.name === '__tests__' ? [] : panelSourceFiles(join(dir, entry.name));
    }
    return entry.name.endsWith('.tsx') && !entry.name.endsWith('.test.tsx')
      ? [join(dir, entry.name)]
      : [];
  });
}

describe('dockable panel hygiene (Dockable Panel Standard DOCK-7 / DOCK-9)', () => {
  const files = panelSourceFiles(PANELS_DIR);

  it('found at least one panel file to scan (guards against a silently-empty glob)', () => {
    expect(files.length).toBeGreaterThan(0);
  });

  it.each(files)('%s does not route-navigate (DOCK-7: useNavigate/useParams/<Link>)', (file) => {
    const src = readFileSync(file, 'utf-8');
    expect(src).not.toMatch(/useNavigate\s*\(/);
    expect(src).not.toMatch(/useParams\s*[<(]/);
    expect(src).not.toMatch(/<Link[\s>]/);
  });

  it.each(files)('%s does not hand-roll a viewport overlay (DOCK-9: fixed + inset-0)', (file) => {
    const src = readFileSync(file, 'utf-8');
    // A file that renders its overlay through Radix (`@radix-ui/react-dialog` directly, or the
    // shared FormDialog/ConfirmDialog wrappers) is DOCK-9-compliant even though its own
    // `Dialog.Overlay`/`Dialog.Content` className literally contains "fixed"+"inset-0" — that's
    // the accepted pattern for a dialog with custom chrome too rich for FormDialog's template
    // (see EntityEditorModal, and the pre-existing EntityDetailPanel precedent). Only a file with
    // NEITHER import is a genuine hand-roll.
    const usesRadixDialog = /@radix-ui\/react-dialog/.test(src) || /from ['"]@\/components\/shared['"]/.test(src);
    if (usesRadixDialog) return;
    // Token-based, not `/fixed\s+inset-0/` — this repo has no Tailwind class-sorter
    // (no prettier-plugin-tailwindcss configured), so "inset-0 fixed ..." is a legal,
    // undetected reorder of the exact anti-pattern an adjacency-only regex would miss.
    const hasFixed = /\bfixed\b/.test(src);
    const hasInset0 = /\binset-0\b/.test(src);
    expect(hasFixed && hasInset0).toBe(false);
  });
});

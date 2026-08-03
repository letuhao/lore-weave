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

// Comments are PROSE, not markup, and must not be scanned. DOCK-9 matches the tokens `fixed`
// and `inset-0` anywhere in a file (deliberately — see the note at the assertion), so an
// ordinary English sentence like "the rail's fixed w-56 leaves too little room" tripped the
// gate on a panel whose only overlay was a correct, panel-scoped `absolute inset-0`. That is
// the same trap the deferral gate hit (CLAUDE.md: a `// TODO(D-…)` comment and a docstring are
// "prose that happens to live in a source file") and it is worth fixing rather than working
// around, because the alternative — contorting real code to dodge a word — teaches the next
// author to distrust the gate. Strings are preserved, so every className still gets scanned.
function stripComments(src: string): string {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, ' ')   // block + JSDoc
    .replace(/(^|[^:])\/\/[^\n]*/g, '$1'); // line — the [^:] keeps `https://…` in a string intact
}

function handRollsViewportOverlay(rawSrc: string): boolean {
  const src = stripComments(rawSrc);
  // A file that renders its overlay through Radix (`@radix-ui/react-dialog` directly, or the
  // shared FormDialog/ConfirmDialog wrappers) is DOCK-9-compliant even though its own
  // `Dialog.Overlay`/`Dialog.Content` className literally contains "fixed"+"inset-0" — that's
  // the accepted pattern for a dialog with custom chrome too rich for FormDialog's template
  // (see EntityEditorModal, and the pre-existing EntityDetailPanel precedent). Only a file with
  // NEITHER import is a genuine hand-roll.
  const usesRadixDialog = /@radix-ui\/react-dialog/.test(src) || /from ['"]@\/components\/shared['"]/.test(src);
  if (usesRadixDialog) return false;
  // Token-based, not `/fixed\s+inset-0/` — this repo has no Tailwind class-sorter
  // (no prettier-plugin-tailwindcss configured), so "inset-0 fixed ..." is a legal,
  // undetected reorder of the exact anti-pattern an adjacency-only regex would miss.
  // Whole-file rather than per-string for the same reason: `cn('fixed', 'inset-0')`
  // splits the anti-pattern across two literals.
  return /\bfixed\b/.test(src) && /\binset-0\b/.test(src);
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
    expect(handRollsViewportOverlay(readFileSync(file, 'utf-8'))).toBe(false);
  });

  // The gate now pre-processes its input, and a stripper that over-reaches would quietly
  // delete the very classNames it is meant to scan — turning DOCK-9 into a check that
  // cannot fail. These pin both directions on synthetic sources: what must still be
  // caught, and what must stop being reported.
  describe('the DOCK-9 predicate itself', () => {
    it('catches a hand-rolled viewport overlay', () => {
      expect(handRollsViewportOverlay(
        `export function P() { return <div className="fixed inset-0 z-50 bg-black/50" />; }`,
      )).toBe(true);
    });

    it('catches it with the classes reordered (no class-sorter in this repo)', () => {
      expect(handRollsViewportOverlay(
        `export function P() { return <div className="inset-0 z-50 fixed bg-black/50" />; }`,
      )).toBe(true);
    });

    it('catches it split across cn() arguments', () => {
      expect(handRollsViewportOverlay(
        `export function P() { return <div className={cn('fixed z-50', 'inset-0')} />; }`,
      )).toBe(true);
    });

    it('ignores the word "fixed" in prose when the overlay is panel-scoped', () => {
      expect(handRollsViewportOverlay(
        `// the rail's fixed w-56 leaves too little room on a narrow viewport\n` +
        `export function P() { return <div className="absolute inset-0 z-10" />; }`,
      )).toBe(false);
    });

    it('ignores it in a block comment too', () => {
      expect(handRollsViewportOverlay(
        `/* a fixed header used to live here */\n` +
        `export function P() { return <div className="absolute inset-0" />; }`,
      )).toBe(false);
    });

    it('still exempts a file that renders through Radix', () => {
      expect(handRollsViewportOverlay(
        `import * as Dialog from '@radix-ui/react-dialog';\n` +
        `export function P() { return <Dialog.Overlay className="fixed inset-0" />; }`,
      )).toBe(false);
    });

    it('does not strip a // inside a URL string', () => {
      expect(handRollsViewportOverlay(
        `const doc = 'https://example.test/x'; export function P() {` +
        ` return <div className="fixed inset-0" />; }`,
      )).toBe(true);
    });
  });
});

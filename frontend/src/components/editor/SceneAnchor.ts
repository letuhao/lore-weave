// #12 M-F — sceneMarker: scene→prose anchoring (plan 2026-07-02-chapter-editor-completeness).
//
// The marker is a `sceneId` ATTRIBUTE on the existing heading node (never a new node
// type): zero visual change, opaque to book-service, and it rides body_json like
// ProvenanceMark. The extension's GlobalAttributes declaration is LOAD-BEARING — without
// it Tiptap's schema strips the attr on load, so opening a marked chapter and saving
// would silently erase every marker.
//
// Three pure-ish helpers operate on a live editor instance (unit-testable with a
// headless editor): jump, backfill-anchor, and the anchor summary the rail's notice uses.
import { Extension, type Editor } from '@tiptap/core';

export const SceneAnchorExtension = Extension.create({
  name: 'sceneAnchor',
  addGlobalAttributes() {
    return [
      {
        types: ['heading'],
        attributes: {
          sceneId: {
            default: null,
            keepOnSplit: false,
            parseHTML: (el: HTMLElement) => el.getAttribute('data-scene-id'),
            renderHTML: (attrs: Record<string, unknown>) =>
              attrs.sceneId ? { 'data-scene-id': String(attrs.sceneId) } : {},
          },
        },
      },
    ];
  },
});

/** Normalize a title for heading↔scene matching: NFC, casefold, collapse whitespace,
 *  strip trailing punctuation. Diacritics are PRESERVED (Vietnamese titles differ by
 *  tone marks — stripping them would create false matches). */
export function normalizeTitle(s: string): string {
  return s
    .normalize('NFC')
    .toLowerCase()
    .replace(/[\s ]+/g, ' ')
    .replace(/[\s.,:;!?…–—-]+$/u, '')
    .trim();
}

interface HeadingHit {
  pos: number;
  text: string;
  sceneId: string | null;
}

function collectHeadings(editor: Editor): HeadingHit[] {
  const out: HeadingHit[] = [];
  editor.state.doc.descendants((node, pos) => {
    if (node.type.name === 'heading') {
      out.push({ pos, text: node.textContent, sceneId: (node.attrs.sceneId as string | null) ?? null });
      return false; // never nested
    }
    return true;
  });
  return out;
}

/** Scroll + place the cursor at the heading anchored to `sceneId`.
 *  Returns false when no heading carries the marker (caller shows the ⚓ hint —
 *  never a silent no-op). */
export function jumpToSceneAnchor(editor: Editor, sceneId: string): boolean {
  const hit = collectHeadings(editor).find((h) => h.sceneId === sceneId);
  if (!hit) return false;
  editor.chain().focus().setTextSelection(hit.pos + 1).run();
  const dom = editor.view.nodeDOM(hit.pos);
  if (dom instanceof HTMLElement) dom.scrollIntoView?.({ block: 'start', behavior: 'smooth' });
  return true;
}

export interface AnchorResult {
  /** scenes that ended up anchored (pre-existing + newly matched) */
  anchored: number;
  /** scenes with no (unique) matching heading — left unmarked, reported to the user */
  unmatched: number;
  /** whether the doc was modified (→ dirty → the user saves) */
  changed: boolean;
}

/** F3 backfill — match un-anchored headings to un-anchored scenes by normalized title
 *  EQUALITY (unique matches only; an ambiguous title anchors nothing) and set the
 *  `sceneId` attrs in ONE transaction. Explicit user action; never runs on open. */
export function applySceneAnchors(
  editor: Editor,
  scenes: ReadonlyArray<{ id: string; title: string }>,
): AnchorResult {
  const headings = collectHeadings(editor);
  const anchoredSceneIds = new Set(headings.map((h) => h.sceneId).filter(Boolean) as string[]);

  // Group free headings by normalized text — only a UNIQUE heading text may anchor.
  const freeByText = new Map<string, HeadingHit[]>();
  for (const h of headings) {
    if (h.sceneId) continue;
    const key = normalizeTitle(h.text);
    if (!key) continue;
    const list = freeByText.get(key) ?? [];
    list.push(h);
    freeByText.set(key, list);
  }

  let anchored = 0;
  let unmatched = 0;
  const toSet: Array<{ pos: number; sceneId: string }> = [];
  for (const scene of scenes) {
    if (anchoredSceneIds.has(scene.id)) { anchored += 1; continue; }
    const candidates = freeByText.get(normalizeTitle(scene.title));
    if (candidates && candidates.length === 1) {
      toSet.push({ pos: candidates[0].pos, sceneId: scene.id });
      freeByText.delete(normalizeTitle(scene.title)); // a heading anchors at most once
      anchored += 1;
    } else {
      unmatched += 1;
    }
  }

  if (toSet.length) {
    const tr = editor.state.tr;
    for (const { pos, sceneId } of toSet) {
      const node = editor.state.doc.nodeAt(pos);
      if (node) tr.setNodeMarkup(pos, undefined, { ...node.attrs, sceneId });
    }
    editor.view.dispatch(tr);
  }
  return { anchored, unmatched, changed: toSet.length > 0 };
}

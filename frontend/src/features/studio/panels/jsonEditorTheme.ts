// #12 J2 — CM6 theme for the json-editor built ENTIRELY from the app's CSS variables
// (index.css [data-theme=…] tokens), so the editor follows ALL themes (dark default /
// light / sepia / oled) live, with no JS theme detection or re-render on switch.
// Pass `theme="none"` to <CodeMirror> alongside this — @uiw's built-in default is a
// hard-coded LIGHT palette (white background), which is the bug this fixes.
import { EditorView } from '@codemirror/view';
import { HighlightStyle, syntaxHighlighting } from '@codemirror/language';
import { tags } from '@lezer/highlight';
import type { Extension } from '@codemirror/state';

const chrome = EditorView.theme({
  '&': {
    backgroundColor: 'hsl(var(--background))',
    color: 'hsl(var(--foreground))',
    height: '100%',
    fontSize: '12px',
  },
  '.cm-content': { caretColor: 'hsl(var(--foreground))' },
  '.cm-cursor, .cm-dropCursor': { borderLeftColor: 'hsl(var(--foreground))' },
  '&.cm-focused': { outline: 'none' },
  '&.cm-focused > .cm-scroller > .cm-selectionLayer .cm-selectionBackground, .cm-selectionBackground, ::selection':
    { backgroundColor: 'hsl(var(--primary) / 0.25)' },
  '.cm-activeLine': { backgroundColor: 'hsl(var(--muted) / 0.35)' },
  '.cm-gutters': {
    backgroundColor: 'hsl(var(--background))',
    color: 'hsl(var(--muted-foreground))',
    borderRight: '1px solid hsl(var(--border))',
  },
  '.cm-activeLineGutter': {
    backgroundColor: 'hsl(var(--muted) / 0.35)',
    color: 'hsl(var(--foreground))',
  },
  '.cm-foldGutter, .cm-foldPlaceholder': { color: 'hsl(var(--muted-foreground))' },
  '.cm-foldPlaceholder': {
    backgroundColor: 'hsl(var(--secondary))',
    border: '1px solid hsl(var(--border))',
  },
  '.cm-matchingBracket, &.cm-focused .cm-matchingBracket': {
    backgroundColor: 'hsl(var(--accent) / 0.25)',
    outline: '1px solid hsl(var(--accent) / 0.5)',
  },
  '.cm-searchMatch': { backgroundColor: 'hsl(var(--warning) / 0.3)' },
  // codemirror-json-schema hover docs + lint tooltips (popover tokens).
  '.cm-tooltip': {
    backgroundColor: 'hsl(var(--popover))',
    color: 'hsl(var(--popover-foreground))',
    border: '1px solid hsl(var(--border))',
  },
  '.cm-tooltip .cm-tooltip-arrow:after': { borderTopColor: 'hsl(var(--popover))' },
  '.cm-diagnostic': { borderLeftColor: 'hsl(var(--destructive))' },
  '.cm-lintRange-error': {
    backgroundImage: 'none',
    textDecoration: 'underline wavy hsl(var(--destructive))',
  },
});

// JSON token palette from the same tokens — every theme keeps these readable
// because the variables themselves adapt per [data-theme].
const highlight = HighlightStyle.define([
  { tag: tags.propertyName, color: 'hsl(var(--primary))' },
  { tag: tags.string, color: 'hsl(var(--success))' },
  { tag: tags.number, color: 'hsl(var(--info))' },
  { tag: [tags.bool, tags.null], color: 'hsl(var(--accent))' },
  { tag: [tags.punctuation, tags.separator, tags.brace, tags.squareBracket],
    color: 'hsl(var(--muted-foreground))' },
  { tag: tags.invalid, color: 'hsl(var(--destructive))' },
]);

/** The full theme bundle for the json-editor CodeMirror instance. */
export const jsonEditorTheme: Extension[] = [chrome, syntaxHighlighting(highlight)];

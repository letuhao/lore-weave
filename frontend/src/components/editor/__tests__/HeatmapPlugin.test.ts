import { Editor } from '@tiptap/core';
import StarterKit from '@tiptap/starter-kit';
import { afterEach, describe, expect, it } from 'vitest';
import { HeatmapExtension, setHeatmapTerms, setHeatmapEnabled } from '../HeatmapPlugin';

// Headless editor — locks the in-prose mention-heatmap decoration: tints entity-name
// occurrences with a band class, only when enabled, on word boundaries, longest-first.

let editor: Editor | null = null;
afterEach(() => { editor?.destroy(); editor = null; });

function mk(content: string): Editor {
  editor = new Editor({ element: document.createElement('div'), extensions: [StarterKit, HeatmapExtension], content });
  return editor;
}
const marks = (e: Editor) =>
  [...e.view.dom.querySelectorAll('.heat-band')].map((el) => ({
    text: el.textContent, band: el.getAttribute('data-heat-band'),
  }));

describe('HeatmapPlugin (T5.2)', () => {
  it('emits NO decorations until enabled', () => {
    const e = mk('<p>Kael walked in.</p>');
    setHeatmapTerms(e, [{ name: 'Kael', band: 4 }]);
    expect(marks(e)).toEqual([]); // terms set but disabled → inert
  });

  it('tints an entity name with its band class once enabled', () => {
    const e = mk('<p>Kael walked in.</p>');
    setHeatmapTerms(e, [{ name: 'Kael', band: 4 }]);
    setHeatmapEnabled(e, true);
    expect(marks(e)).toEqual([{ text: 'Kael', band: '4' }]);
  });

  it('matches on word boundaries (not inside a longer word)', () => {
    const e = mk('<p>The Kaelite army, led by Kael.</p>');
    setHeatmapTerms(e, [{ name: 'Kael', band: 2 }]);
    setHeatmapEnabled(e, true);
    // only the standalone "Kael", not the "Kael" inside "Kaelite"
    expect(marks(e)).toEqual([{ text: 'Kael', band: '2' }]);
  });

  it('toggles back off', () => {
    const e = mk('<p>Mira spoke.</p>');
    setHeatmapTerms(e, [{ name: 'Mira', band: 1 }]);
    setHeatmapEnabled(e, true);
    expect(marks(e)).toHaveLength(1);
    setHeatmapEnabled(e, false);
    expect(marks(e)).toEqual([]);
  });

  it('does not serialize the decoration into the document JSON', () => {
    const e = mk('<p>Kael.</p>');
    setHeatmapTerms(e, [{ name: 'Kael', band: 3 }]);
    setHeatmapEnabled(e, true);
    expect(JSON.stringify(e.getJSON())).not.toContain('heat-band');
  });
});

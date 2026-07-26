// W6 §8 (H-8 guard: "Separate app, not the studio") — the motif library +
// conformance are registered as dock panels INSIDE the studio's workspace, not a
// separate app. This asserts the additive studio-shell registration (the only
// non-namespaced W6 edit) — the panel ids are known WorkspacePanelIds and appear in
// the default dock layout in order.
import { describe, expect, it } from 'vitest';
import { isWorkspacePanelId, defaultLayout } from '../../workspace/types';

describe('motif dock panel registration (additive studio-shell)', () => {
  it('motifs + conformance are valid WorkspacePanelIds', () => {
    expect(isWorkspacePanelId('motifs')).toBe(true);
    expect(isWorkspacePanelId('conformance')).toBe(true);
  });

  it('both appear in the default dock layout', () => {
    const layout = defaultLayout();
    expect(layout.panels.motifs).toBeDefined();
    expect(layout.panels.conformance).toBeDefined();
  });

  it('order: motifs + conformance sit after flywheel, before settings', () => {
    const layout = defaultLayout();
    const order = (id: string) => layout.panels[id as 'motifs']?.order ?? -1;
    expect(order('motifs')).toBeGreaterThan(order('flywheel'));
    expect(order('conformance')).toBeGreaterThan(order('motifs'));
    expect(order('settings')).toBeGreaterThan(order('conformance'));
  });
});

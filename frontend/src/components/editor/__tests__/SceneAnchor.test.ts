// #12 M-F — sceneMarker: the heading `sceneId` attr survives the schema (load→save),
// jump finds the anchored heading, and the backfill matches by unique normalized title.
import { describe, expect, it } from 'vitest';
import { Editor } from '@tiptap/core';
import StarterKit from '@tiptap/starter-kit';
import { SceneAnchorExtension, applySceneAnchors, jumpToSceneAnchor, normalizeTitle } from '../SceneAnchor';

function makeEditor(content: object) {
  return new Editor({
    extensions: [StarterKit.configure({ heading: { levels: [1, 2, 3] } }), SceneAnchorExtension],
    content,
  });
}

const doc = (...nodes: object[]) => ({ type: 'doc', content: nodes });
const heading = (text: string, sceneId?: string) => ({
  type: 'heading',
  attrs: { level: 3, ...(sceneId ? { sceneId } : {}) },
  content: [{ type: 'text', text }],
});
const para = (text: string) => ({ type: 'paragraph', content: [{ type: 'text', text }] });

describe('normalizeTitle', () => {
  it('casefolds, collapses whitespace, strips trailing punctuation — keeps diacritics', () => {
    expect(normalizeTitle('  Cuộc  Truy Sát Trong Đêm… ')).toBe('cuộc truy sát trong đêm');
    // tone marks are significant in Vietnamese — must NOT be equal
    expect(normalizeTitle('Truy Sát')).not.toBe(normalizeTitle('Truy Sat'));
  });
});

describe('SceneAnchorExtension (schema round-trip)', () => {
  it('the sceneId attr SURVIVES load→getJSON (without the extension it would be stripped)', () => {
    const editor = makeEditor(doc(heading('Cảnh Một', 'scene-1'), para('văn')));
    const json = editor.getJSON();
    const h = json.content?.[0];
    expect(h?.attrs?.sceneId).toBe('scene-1');
    editor.destroy();
  });
});

describe('jumpToSceneAnchor', () => {
  it('moves the selection to the anchored heading; false when un-anchored', () => {
    const editor = makeEditor(doc(para('mở đầu'), heading('Cảnh Hai', 'scene-2'), para('thân')));
    expect(jumpToSceneAnchor(editor, 'scene-2')).toBe(true);
    // cursor sits inside the heading
    const $from = editor.state.selection.$from;
    expect($from.parent.type.name).toBe('heading');
    expect(jumpToSceneAnchor(editor, 'scene-MISSING')).toBe(false);
    editor.destroy();
  });
});

describe('applySceneAnchors (backfill)', () => {
  it('anchors headings to scenes by unique normalized-title match in one transaction', () => {
    const editor = makeEditor(doc(
      heading('Sự Phản Bội Của Gia Tộc'), para('a'),
      heading('Cuộc Truy Sát Trong Đêm'), para('b'),
    ));
    const r = applySceneAnchors(editor, [
      { id: 's1', title: 'Sự Phản Bội Của Gia Tộc' },
      { id: 's2', title: 'cuộc truy sát trong đêm' }, // case-insensitive
    ]);
    expect(r).toEqual({ anchored: 2, unmatched: 0, changed: true });
    const ids = (editor.getJSON().content ?? [])
      .filter((n) => n.type === 'heading')
      .map((n) => n.attrs?.sceneId);
    expect(ids).toEqual(['s1', 's2']);
    editor.destroy();
  });

  it('already-anchored scenes count as anchored without touching the doc', () => {
    const editor = makeEditor(doc(heading('Cảnh', 'sX'), para('a')));
    const r = applySceneAnchors(editor, [{ id: 'sX', title: 'khác hẳn' }]);
    expect(r).toEqual({ anchored: 1, unmatched: 0, changed: false });
    editor.destroy();
  });

  it('an AMBIGUOUS heading title (duplicated) anchors nothing for that title', () => {
    const editor = makeEditor(doc(heading('Hồi Tưởng'), para('a'), heading('Hồi Tưởng'), para('b')));
    const r = applySceneAnchors(editor, [{ id: 's1', title: 'Hồi Tưởng' }]);
    expect(r).toEqual({ anchored: 0, unmatched: 1, changed: false });
    editor.destroy();
  });

  it('a scene with no matching heading is reported unmatched', () => {
    const editor = makeEditor(doc(heading('Khởi Đầu'), para('a')));
    const r = applySceneAnchors(editor, [
      { id: 's1', title: 'Khởi Đầu' },
      { id: 's2', title: 'Không Tồn Tại' },
    ]);
    expect(r).toEqual({ anchored: 1, unmatched: 1, changed: true });
    editor.destroy();
  });
});

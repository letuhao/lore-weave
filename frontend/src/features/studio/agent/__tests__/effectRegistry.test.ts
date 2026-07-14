import { describe, expect, it, vi, beforeEach } from 'vitest';
import {
  registerEffectHandler, matchEffectHandlers, runEffectHandlers, clearEffectHandlers, type EffectContext,
} from '../effectRegistry';
import { bookDraftEffect, outlineEffect, registerDefaultEffectHandlers } from '../handlers/bookEffects';
import type { StudioHost } from '../../host/StudioHostProvider';

beforeEach(() => clearEffectHandlers());

const ctx = (over: Partial<EffectContext> = {}): EffectContext => ({
  tool: 'book_save_chapter_draft',
  result: { chapter_id: 'ch1' },
  bookId: 'b1',
  host: { publish: vi.fn() } as unknown as StudioHost,
  queryClient: { invalidateQueries: vi.fn() } as unknown as EffectContext['queryClient'],
  reloadChapter: vi.fn(),
  ...over,
});

describe('effect registry matching', () => {
  it('RegExp patterns match by test', () => {
    const s = vi.fn(); const r = vi.fn();
    registerEffectHandler(/^book_save/, s);
    registerEffectHandler(/draft$/, r);
    expect(matchEffectHandlers('book_save')).toContain(s);        // anchored prefix
    expect(matchEffectHandlers('book_save_chapter')).toContain(s);
    expect(matchEffectHandlers('composition_draft')).toContain(r);
    expect(matchEffectHandlers('unrelated_tool')).toHaveLength(0);
  });

  it('runEffectHandlers awaits every matching handler', async () => {
    const a = vi.fn(); const b = vi.fn();
    registerEffectHandler(/^book_/, a);
    registerEffectHandler(/book/, b);
    await runEffectHandlers(ctx({ tool: 'book_x' }));
    expect(a).toHaveBeenCalledOnce();
    expect(b).toHaveBeenCalledOnce();
  });
});

// X-4.0 (Q-30-REGISTEREFFECT-STRING-BRANCH) — the string branch is DELETED, not documented.
// It was `tool === p || tool.startsWith(p)` — exact-or-prefix, NOT a pattern. A caller writing
// 'composition_(style|voice)_' as a STRING matched NOTHING and shipped a silent no-op handler that
// no per-handler unit test could see (the test registers and calls its own fake, so it stays green).
// tsc now rejects a string; this asserts the RUNTIME throw too, because TS types are erased and an
// `as any` / a JS caller must still fail loudly.
describe('registerEffectHandler REJECTS the string-pattern bug class (X-4.0)', () => {
  it('REJECTS a string pattern — an alternation string would silently match nothing (§8.0b)', () => {
    expect(() => registerEffectHandler('composition_(style|voice)_' as unknown as RegExp, vi.fn()))
      .toThrow(/must be a RegExp/);
    expect(matchEffectHandlers('composition_style_set')).toHaveLength(0);
  });

  it('the RegExp form of the same pattern DOES match', () => {
    const h = vi.fn();
    registerEffectHandler(/^composition_(style|voice)_/, h);
    expect(matchEffectHandlers('composition_style_set')).toContain(h);
    expect(matchEffectHandlers('composition_voice_apply')).toContain(h);
  });

  it('REJECTS the /g flag (test() advances lastIndex and alternates true/false across calls)', () => {
    expect(() => registerEffectHandler(/^book_/g, vi.fn())).toThrow(/\/g flag/);
  });
});

describe('bookDraftEffect (Lane B v1 handler)', () => {
  it('invalidates the chapter query + reloads the Tier-4 hoist (does NOT publish a chapter — no editor hijack)', () => {
    const c = ctx();
    bookDraftEffect(c);
    expect(c.queryClient.invalidateQueries).toHaveBeenCalledWith({ queryKey: ['chapter', 'b1', 'ch1'] });
    expect(c.reloadChapter).toHaveBeenCalledWith('ch1');
    expect(c.host.publish).not.toHaveBeenCalled(); // reconcile must not switch the user's editor
  });

  it('G7: skips the reload when the hoist is DIRTY (never clobbers unsaved edits); still invalidates cache', () => {
    const reloadChapter = vi.fn();
    const c = ctx({ isChapterDirty: () => true, reloadChapter });
    bookDraftEffect(c);
    expect(c.queryClient.invalidateQueries).toHaveBeenCalled();
    expect(reloadChapter).not.toHaveBeenCalled();
  });

  it('no chapter id in the result → no-op (never guesses)', () => {
    const c = ctx({ result: { ok: true } });
    bookDraftEffect(c);
    expect(c.queryClient.invalidateQueries).not.toHaveBeenCalled();
    expect(c.reloadChapter).not.toHaveBeenCalled();
  });
});

describe('outlineEffect (#12 M-D — agent scene-metadata writes)', () => {
  it('invalidates outline queries AND reloads the active unit scenes for the node chapter', () => {
    const reloadScenes = vi.fn();
    const c = ctx({ tool: 'composition_outline_node_update', result: { id: 'n1', chapter_id: 'ch1' }, reloadScenes });
    outlineEffect(c);
    expect(c.queryClient.invalidateQueries).toHaveBeenCalledWith({ queryKey: ['composition', 'outline'] });
    expect(reloadScenes).toHaveBeenCalledWith('ch1');
  });

  it('no chapter_id (scene_link results, arc nodes) → still invalidates, never guesses a reload', () => {
    const reloadScenes = vi.fn();
    const c = ctx({ tool: 'composition_scene_link_create', result: { id: 'l1' }, reloadScenes });
    outlineEffect(c);
    expect(c.queryClient.invalidateQueries).toHaveBeenCalledWith({ queryKey: ['composition', 'outline'] });
    expect(reloadScenes).not.toHaveBeenCalled();
  });

  it('default registration routes composition_outline_node_update → outlineEffect (wiring proof)', async () => {
    registerDefaultEffectHandlers();
    const reloadScenes = vi.fn();
    await runEffectHandlers(ctx({
      tool: 'composition_outline_node_update', result: { chapter_id: 'ch9' }, reloadScenes,
    }));
    expect(reloadScenes).toHaveBeenCalledWith('ch9');
  });

  // M-E live-caught: the live stream wraps the domain payload in the chat-service
  // TOOL_CALL_RESULT envelope {ok, result} (and `result` can itself be a JSON string —
  // MCP text content). The bare top-level read returned null → Lane B never reloaded
  // the Scene Rail while the DB was already updated.
  it('unwraps the live-stream {ok, result} envelope (object payload)', () => {
    const reloadScenes = vi.fn();
    const c = ctx({
      tool: 'composition_outline_node_update',
      result: { ok: true, result: { id: 'n1', chapter_id: 'ch1' } },
      reloadScenes,
    });
    outlineEffect(c);
    expect(reloadScenes).toHaveBeenCalledWith('ch1');
  });

  it('unwraps the envelope when the inner result is a JSON STRING (MCP text content)', () => {
    const reloadScenes = vi.fn();
    const c = ctx({
      tool: 'composition_outline_node_update',
      result: { ok: true, result: JSON.stringify({ id: 'n1', chapter_id: 'ch2' }) },
      reloadScenes,
    });
    outlineEffect(c);
    expect(reloadScenes).toHaveBeenCalledWith('ch2');
  });

  it('envelope with a non-JSON string result → no reload, no throw', () => {
    const reloadScenes = vi.fn();
    const c = ctx({
      tool: 'composition_outline_node_update',
      result: { ok: true, result: 'plain text outcome' },
      reloadScenes,
    });
    outlineEffect(c);
    expect(reloadScenes).not.toHaveBeenCalled();
  });
});

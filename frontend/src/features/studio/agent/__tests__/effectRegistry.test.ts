import { describe, expect, it, vi, beforeEach, afterAll } from 'vitest';
import {
  registerEffectHandler, matchEffectHandlers, runEffectHandlers, clearEffectHandlers, type EffectContext,
} from '../effectRegistry';
import { bookDraftEffect, outlineEffect, registerDefaultEffectHandlers } from '../handlers/bookEffects';
import type { StudioHost } from '../../host/StudioHostProvider';

vi.mock('sonner', () => ({
  toast: { warning: vi.fn(), info: vi.fn(), error: vi.fn(), success: vi.fn() },
}));
vi.mock('@/i18n', () => ({
  default: { t: (key: string, opts?: { defaultValue?: string }) => opts?.defaultValue ?? key },
}));

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const toastWarning = (await import('sonner')).toast.warning as any;

// T4's G7 notice is debounced on wall-clock time. Left real, the FIRST test's toast would suppress
// the SECOND test's — a cross-test dependency that makes a green run meaningless. Drive the clock.
let nowMs = 1_000_000;
vi.spyOn(Date, 'now').mockImplementation(() => nowMs);
afterAll(() => vi.restoreAllMocks());

beforeEach(() => {
  clearEffectHandlers();
  nowMs += 60_000; // past any debounce window, so each test starts clean
});

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
  it('invalidates the chapter query + reloads the Tier-4 hoist + publishes manuscriptChanged (tree refresh), but NEVER the chapter focus event (no editor hijack)', () => {
    const c = ctx();
    bookDraftEffect(c);
    expect(c.queryClient.invalidateQueries).toHaveBeenCalledWith({ queryKey: ['chapter', 'b1', 'ch1'] });
    expect(c.reloadChapter).toHaveBeenCalledWith('ch1');
    // The hand-rolled navigator tree only reloads on this bus event — dogfood 2026-07-18: an agent
    // chapter create left the rail on "0 chapters" until a full page reload without it.
    expect(c.host.publish).toHaveBeenCalledWith({ type: 'manuscriptChanged' });
    // …but STILL never the `chapter` FOCUS event — reconcile must not switch the user's editor.
    expect(c.host.publish).not.toHaveBeenCalledWith(expect.objectContaining({ type: 'chapter' }));
  });

  it('publishes manuscriptChanged BEFORE the G7 dirty-guard, so a dirty editor never hides a new sibling chapter', () => {
    const c = ctx({ isChapterDirty: () => true });
    bookDraftEffect(c);
    expect(c.host.publish).toHaveBeenCalledWith({ type: 'manuscriptChanged' }); // tree still refreshes
    expect(c.reloadChapter).not.toHaveBeenCalled(); // …but the dirty hoist is protected
  });

  it('G7: skips the reload when the hoist is DIRTY (never clobbers unsaved edits); still invalidates cache', () => {
    const reloadChapter = vi.fn();
    const c = ctx({ isChapterDirty: () => true, reloadChapter });
    bookDraftEffect(c);
    expect(c.queryClient.invalidateQueries).toHaveBeenCalled();
    expect(reloadChapter).not.toHaveBeenCalled();
  });

  // T4 — G7's second half. The guard shipped; spec 09's "no-op + toast" lost its toast, so an agent
  // write onto the chapter the user was editing vanished silently: the agent believed it wrote, the
  // editor showed older content, and nothing said the two had diverged. Protecting the keystrokes
  // without saying so is still a divergence the author cannot see.
  it('G7: TELLS the user when a dirty hoist blocked the reload, and offers the reload as their choice', () => {
    toastWarning.mockClear();
    const reloadChapter = vi.fn();
    const c = ctx({ isChapterDirty: () => true, reloadChapter });
    bookDraftEffect(c);

    expect(toastWarning).toHaveBeenCalledOnce();
    const [message, opts] = toastWarning.mock.calls[0];
    expect(String(message)).not.toHaveLength(0);
    // The action must actually reload THIS chapter — a label with no working handler would be a
    // worse lie than silence.
    const action = (opts as { action?: { onClick: () => void } } | undefined)?.action;
    expect(action).toBeTruthy();
    action!.onClick();
    expect(reloadChapter).toHaveBeenCalledWith('ch1');
  });

  it('G7 notice is debounced — one agent turn firing the handler repeatedly is one warning, not three', () => {
    toastWarning.mockClear();
    const c = ctx({ isChapterDirty: () => true });
    bookDraftEffect(c);
    bookDraftEffect(c);
    bookDraftEffect(c);
    expect(toastWarning).toHaveBeenCalledOnce();
  });

  it('G7 notice does NOT fire on the clean path — a warning that always fires means nothing (NV-7)', () => {
    toastWarning.mockClear();
    bookDraftEffect(ctx({ isChapterDirty: () => false }));
    expect(toastWarning).not.toHaveBeenCalled();
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

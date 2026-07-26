// 13_glossary_panels.md A5 — Lane B effect handler for glossary_* MCP writes.
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { clearEffectHandlers, runEffectHandlers, matchEffectHandlers, type EffectContext } from '../effectRegistry';
import type { StudioHost } from '../../host/StudioHostProvider';

const reloadBoundGlossaryEntity = vi.hoisted(() => vi.fn());
vi.mock('@/features/glossary/documents/entityDocument', () => ({ reloadBoundGlossaryEntity }));

import {
  glossaryEffect, registerGlossaryEffectHandlers, GLOSSARY_WRITE_PATTERN, _resetGlossaryEffectHandlers,
} from '../handlers/glossaryEffects';

beforeEach(() => {
  clearEffectHandlers();
  _resetGlossaryEffectHandlers();
  reloadBoundGlossaryEntity.mockReset();
});

const ctx = (over: Partial<EffectContext> = {}): EffectContext => ({
  tool: 'glossary_propose_new_entity',
  result: { entity_id: 'e1' },
  bookId: 'b1',
  host: { publish: vi.fn() } as unknown as StudioHost,
  queryClient: { invalidateQueries: vi.fn() } as unknown as EffectContext['queryClient'],
  ...over,
});

describe('glossaryEffect (Lane B v1 handler)', () => {
  it('invalidates every glossary panel query key', () => {
    const c = ctx();
    glossaryEffect(c);
    const keys = (c.queryClient.invalidateQueries as ReturnType<typeof vi.fn>).mock.calls.map((call) => call[0].queryKey);
    expect(keys).toContainEqual(['glossary-entities', 'b1']);
    expect(keys).toContainEqual(['glossary-translation-languages', 'b1']);
    expect(keys).toContainEqual(['glossary-ontology', 'b1']);
    expect(keys).toContainEqual(['glossary-kinds']);
    expect(keys).toContainEqual(['glossary-unknown', 'b1']);
    expect(keys).toContainEqual(['glossary-ai-suggestions', 'b1']);
    expect(keys).toContainEqual(['glossary-merge-candidates', 'b1']);
  });

  it('reloads the bound entity editor hoist when the result carries an entity_id', () => {
    glossaryEffect(ctx({ result: { entity_id: 'e42' } }));
    expect(reloadBoundGlossaryEntity).toHaveBeenCalledWith('e42');
  });

  it('never guesses a reload when the result has no entity_id (e.g. a batch/kind proposal)', () => {
    glossaryEffect(ctx({ result: { batch_id: 'bx' } }));
    expect(reloadBoundGlossaryEntity).not.toHaveBeenCalled();
  });

  // /review-impl HIGH-ish: caught missing the M-E envelope unwrap (resultEnvelope.ts) that
  // bookEffects.ts already needed — the flat `{entity_id}` mocks above would stay green even if
  // this regressed, exactly the trap the live gate exists to catch. These two prove the real wire
  // shape (chat-service TOOL_CALL_RESULT `{ok, result}`, `.result` sometimes a JSON string).
  it('unwraps the live-stream {ok, result} envelope (object payload)', () => {
    glossaryEffect(ctx({ result: { ok: true, result: { entity_id: 'e9' } } }));
    expect(reloadBoundGlossaryEntity).toHaveBeenCalledWith('e9');
  });

  it('unwraps the envelope when the inner result is a JSON STRING (MCP text content)', () => {
    glossaryEffect(ctx({ result: { ok: true, result: JSON.stringify({ entity_id: 'e10' }) } }));
    expect(reloadBoundGlossaryEntity).toHaveBeenCalledWith('e10');
  });
});

describe('GLOSSARY_WRITE_PATTERN (write vs read tool names)', () => {
  it.each([
    'glossary_propose_new_entity', 'glossary_propose_status_change', 'glossary_book_patch',
    'glossary_book_delete', 'glossary_book_sync_apply', 'glossary_entity_set_genres',
    'glossary_create_evidence', 'glossary_create_chapter_link', 'glossary_adopt_standards',
    'glossary_admin_create', 'glossary_user_patch',
  ])('matches %s (a write)', (tool) => {
    expect(GLOSSARY_WRITE_PATTERN.test(tool)).toBe(true);
  });

  it.each([
    'glossary_get_entity', 'glossary_list_unknown_entities', 'glossary_search',
    'glossary_deep_research', 'glossary_web_search', 'glossary_list_ai_suggestions',
  ])('does NOT match %s (a read) — avoids thrashing the cache on a chatty read loop', (tool) => {
    expect(GLOSSARY_WRITE_PATTERN.test(tool)).toBe(false);
  });

  it('does not match a non-glossary tool', () => {
    expect(GLOSSARY_WRITE_PATTERN.test('book_save_chapter_draft')).toBe(false);
  });
});

describe('registerGlossaryEffectHandlers wiring', () => {
  it('routes a real write tool through the registry: invalidates + reloads', async () => {
    registerGlossaryEffectHandlers();
    expect(matchEffectHandlers('glossary_propose_status_change')).toContain(glossaryEffect);
    await runEffectHandlers(ctx({ tool: 'glossary_propose_status_change', result: { entity_id: 'e7' } }));
    expect(reloadBoundGlossaryEntity).toHaveBeenCalledWith('e7');
  });
});

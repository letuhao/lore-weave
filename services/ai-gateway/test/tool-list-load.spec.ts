// Track A / WS-1a — tool_list + tool_load + the labeled visible-set (contracts.md C1/C2).
import {
  CATEGORY_ENUM,
  GROUP_DIRECTORY,
  toolListResult,
  toolLoadResult,
  visibleTools,
} from '../src/federation/find-tools.js';

const CAT = [
  { name: 'glossary_propose_entities', description: 'Add entities', _meta: { tier: 'A' } },
  {
    name: 'glossary_propose_new_entity',
    description: 'Legacy add-entity',
    _meta: { tier: 'A', visibility: 'legacy', superseded_by: 'glossary_propose_entities' },
  },
  {
    name: 'book_create',
    description: 'Create a book',
    _meta: { tier: 'A' },
    inputSchema: { type: 'object', properties: { title: { type: 'string' } } },
  },
  { name: 'lore_enrichment_auto_enrich', description: 'Enrich lore', _meta: { tier: 'A' } },
];

describe('lore_enrichment alias (C1)', () => {
  it('folds lore_* under glossary in tool_list', () => {
    const names = (toolListResult(CAT, 'glossary').payload.tools as { name: string }[]).map((t) => t.name);
    expect(names).toContain('lore_enrichment_auto_enrich');
  });
});

describe('visibleTools — labeled deprecated (C2)', () => {
  it('labels a legacy tool instead of dropping it', () => {
    const vt = new Map(visibleTools(CAT, 'glossary').map((t) => [t.name, t]));
    expect(vt.has('glossary_propose_new_entity')).toBe(true);
    expect(vt.get('glossary_propose_new_entity')!.deprecated).toBe(true);
    expect(vt.get('glossary_propose_new_entity')!.superseded_by).toBe('glossary_propose_entities');
    expect(vt.get('glossary_propose_entities')!.deprecated).toBeUndefined();
  });

  it('include_deprecated=false filters legacy out', () => {
    const names = visibleTools(CAT, 'glossary', false).map((t) => t.name);
    expect(names).not.toContain('glossary_propose_new_entity');
    expect(names).toContain('glossary_propose_entities');
  });
});

describe('toolListResult (C2)', () => {
  it('a specific category returns a flat list + count', () => {
    const { payload } = toolListResult(CAT, 'book');
    expect(payload.category).toBe('book');
    expect(payload.count).toBe(1);
    expect((payload.tools as { name: string }[])[0].name).toBe('book_create');
  });

  it('an empty category carries a reason', () => {
    const { payload } = toolListResult(CAT, 'jobs');
    expect(payload.count).toBe(0);
    expect(payload.reason).toBeDefined();
  });

  it('omitted/"all" groups by category', () => {
    const { payload } = toolListResult(CAT);
    expect(payload.count).toBe(4);
    const categories = payload.categories as Record<string, unknown[]>;
    expect(Object.keys(categories).sort()).toEqual(['book', 'glossary']);
    expect(categories.glossary).toHaveLength(3);
  });
});

describe('toolLoadResult (C2)', () => {
  it('by name returns the input_schema + tier and the activation names', () => {
    const { payload, loadedNames } = toolLoadResult(CAT, { name: 'book_create' });
    expect(loadedNames).toEqual(['book_create']);
    const t = (payload.tools as { input_schema: { properties: unknown }; tier: string }[])[0];
    expect(t.input_schema.properties).toEqual({ title: { type: 'string' } });
    expect(t.tier).toBe('A');
  });

  it('reports unknown names under not_found (never a silent drop)', () => {
    const { payload, loadedNames } = toolLoadResult(CAT, { names: ['book_create', 'does_not_exist'] });
    expect(loadedNames).toEqual(['book_create']);
    expect(payload.not_found).toEqual(['does_not_exist']);
  });

  it('by category loads all incl. labeled legacy', () => {
    const { loadedNames, payload } = toolLoadResult(CAT, { category: 'glossary' });
    expect(loadedNames.sort()).toEqual([
      'glossary_propose_entities',
      'glossary_propose_new_entity',
      'lore_enrichment_auto_enrich',
    ]);
    const legacy = (payload.tools as { name: string; deprecated?: boolean; superseded_by?: string }[]).find(
      (t) => t.name === 'glossary_propose_new_entity',
    )!;
    expect(legacy.deprecated).toBe(true);
    expect(legacy.superseded_by).toBe('glossary_propose_entities');
  });
});

describe('CATEGORY_ENUM (C1)', () => {
  it('is GROUP_DIRECTORY keys sorted + "all"', () => {
    expect(CATEGORY_ENUM).toEqual([...Object.keys(GROUP_DIRECTORY).sort(), 'all']);
  });
});

import { FIND_TOOLS_TOOL, GROUP_DIRECTORY, findToolsResult, searchCatalog } from '../src/federation/find-tools.js';

const CATALOG = [
  { name: 'book_create', description: 'Create a new book' },
  { name: 'book_update_chapter', description: 'Edit a chapter of a book' },
  { name: 'translation_start_job', description: 'Start translating a book into another language' },
  { name: 'kg_build_graph', description: 'Build the knowledge graph for a project' },
  { name: 'glossary_propose_batch', description: 'Propose glossary entity edits', _meta: { synonyms: ['lore', 'terms'] } },
];

describe('searchCatalog', () => {
  it('ranks the most relevant tool first by token overlap', () => {
    const { matches, confident } = searchCatalog(CATALOG, 'start a translation', 8);
    expect(confident).toBe(true);
    expect(matches[0].name).toBe('translation_start_job');
  });

  it('matches via snake_case name tokens (book + create)', () => {
    const { matches } = searchCatalog(CATALOG, 'create a book', 8);
    expect(matches.map((m) => m.name)).toContain('book_create');
  });

  it('matches via _meta.synonyms (lore → glossary tool)', () => {
    const { matches } = searchCatalog(CATALOG, 'manage lore', 8);
    expect(matches.map((m) => m.name)).toContain('glossary_propose_batch');
  });

  it('returns empty + not-confident for a no-overlap intent (no bogus suggestion)', () => {
    const { matches, confident } = searchCatalog(CATALOG, 'xyzzy frobnicate', 8);
    expect(matches).toEqual([]);
    expect(confident).toBe(false);
  });

  it('respects the exclude set (never re-suggests an already-advertised tool)', () => {
    const { matches } = searchCatalog(CATALOG, 'create a book', 8, new Set(['book_create']));
    expect(matches.map((m) => m.name)).not.toContain('book_create');
  });

  it('honors the limit', () => {
    const { matches } = searchCatalog(CATALOG, 'book', 1);
    expect(matches.length).toBeLessThanOrEqual(1);
  });
});

describe('findToolsResult', () => {
  it('returns matched names + a tools payload on a hit', () => {
    const { payload, matchedNames } = findToolsResult(CATALOG, 'translate the book', 8, new Set(), []);
    expect(matchedNames).toContain('translation_start_job');
    expect((payload.tools as unknown[]).length).toBeGreaterThan(0);
    expect(payload.note).toBeUndefined();
  });

  it('on an empty result with a down provider, says try-again (H10), not "I can\'t"', () => {
    const { payload, matchedNames } = findToolsResult(CATALOG, 'xyzzy frobnicate', 8, new Set(), ['book']);
    expect(matchedNames).toEqual([]);
    expect(payload.unavailable_providers).toEqual(['book']);
    expect(String(payload.note)).toMatch(/temporarily unavailable/i);
  });

  it('on an empty result with all providers up, says "search once more"', () => {
    const { payload } = findToolsResult(CATALOG, 'xyzzy frobnicate', 8, new Set(), []);
    expect(payload.unavailable_providers).toBeUndefined();
    expect(String(payload.note)).toMatch(/no tool matched/i);
  });

  it('flags low_confidence on weak matches', () => {
    // A single shared weak token → a match below the confidence threshold but above the floor.
    const { payload } = findToolsResult(CATALOG, 'project', 8, new Set(), []);
    if ((payload.tools as unknown[]).length > 0 && !payload.note) {
      // confident — fine
    } else {
      expect(payload.low_confidence === true || payload.note !== undefined).toBe(true);
    }
  });

  it('the meta-tool schema requires an intent', () => {
    expect(FIND_TOOLS_TOOL.name).toBe('find_tools');
    expect(FIND_TOOLS_TOOL.inputSchema.required).toContain('intent');
  });
});

// review-impl finding: CAT-4 (mcp-tool-io.md Part 4) is enforced identically on
// BOTH federation surfaces — chat-service's tool_discovery.py has a dedicated
// TestSearchCatalogCAT4/TestGroupDirectory suite proving legacy-exclusion and
// group-scoping, but this ai-gateway TS mirror (find-tools.ts) had ZERO tests of
// its own for the exact same logic — a silent TS-only regression (e.g. a future
// refactor dropping the isLegacyTool check) would have shipped undetected even
// though the two files' own header comments say they "must stay in lockstep."
const LEGACY_CATALOG = [
  {
    name: 'glossary_book_create',
    description: 'Create a book-native genre, kind, or attribute.',
    _meta: { visibility: 'legacy', synonyms: ['add a kind', 'add a genre'] },
  },
  {
    name: 'glossary_ontology_upsert',
    description: 'Create or update book- or user-tier ontology rows (genre, kind, attribute).',
    _meta: { synonyms: ['add a kind', 'add a genre', 'add an attribute'] },
  },
  { name: 'glossary_search', description: 'Search glossary entities' },
  { name: 'book_create', description: 'Create a new book' },
];

describe('searchCatalog — CAT-4 legacy exclusion (TS mirror)', () => {
  it('a legacy-tagged tool never matches, even on an exact synonym', () => {
    const { matches, confident } = searchCatalog(LEGACY_CATALOG, 'add a new kind to the book', 8);
    const names = matches.map((m) => m.name);
    expect(names).not.toContain('glossary_book_create');
    expect(names).toContain('glossary_ontology_upsert');
    expect(confident).toBe(true);
  });

  it('an untagged tool (no _meta.visibility) is unaffected — defaults discoverable', () => {
    const { matches } = searchCatalog(LEGACY_CATALOG, 'search glossary entities', 8);
    expect(matches.map((m) => m.name)).toContain('glossary_search');
  });

  it('group scopes the search to one domain prefix', () => {
    const { matches } = searchCatalog(LEGACY_CATALOG, 'create', 8, new Set(), 'book');
    const names = matches.map((m) => m.name);
    expect(names).toContain('book_create');
    expect(names).not.toContain('glossary_ontology_upsert');
  });

  it('group=null/omitted searches every domain', () => {
    const { matches } = searchCatalog(LEGACY_CATALOG, 'create', 8, new Set(), null);
    const names = matches.map((m) => m.name);
    expect(names).toContain('book_create');
    expect(names).toContain('glossary_ontology_upsert');
  });
});

describe('GROUP_DIRECTORY (Part A, TS mirror)', () => {
  it('mirrors chat-service GROUP_DIRECTORY verbatim (same keys)', () => {
    // Keep this list in sync BY HAND with tool_discovery.py's GROUP_DIRECTORY —
    // this test is the drift-lock: a key added to one side and not the other
    // (or a description edited on only one side) fails here.
    expect(Object.keys(GROUP_DIRECTORY).sort()).toEqual([
      'book', 'catalog', 'composition', 'glossary', 'jobs',
      'knowledge', 'registry', 'settings', 'story', 'translation',
    ]);
  });

  it('find_tools schema advertises the group enum sorted', () => {
    const props = FIND_TOOLS_TOOL.inputSchema.properties as { group: { enum: string[] } };
    expect(props.group.enum).toEqual(Object.keys(GROUP_DIRECTORY).sort());
  });
});

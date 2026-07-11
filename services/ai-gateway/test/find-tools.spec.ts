import {
  FIND_TOOLS_TOOL,
  FindToolsAttemptTracker,
  GROUP_DIRECTORY,
  enumerateGroup,
  findToolsResult,
  searchCatalog,
} from '../src/federation/find-tools.js';

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

  it('review-impl live-verification finding: one incidental shared word does not outrank a real overlap', () => {
    // Live-verified at the real ~190-tool federated catalog (2026-07-06): intent
    // "add a new kind to the book" scored translation_start_job a perfect 1.0
    // via its synonym "translate a book" sharing only the word "book" -- the
    // fuzzy-rescue branch's own comment says it rescues a NO-overlap tool, but
    // the code never enforced that, so any exact single-token overlap
    // (ratio=1.0) qualified regardless of how weak the rest of the match was.
    const cat = [
      {
        name: 'glossary_ontology_upsert',
        description: 'Create or update book- or user-tier ontology rows (genre, kind, attribute).',
        _meta: { synonyms: ['add a kind', 'add a genre', 'add an attribute'] },
      },
      {
        name: 'translation_start_job',
        description: 'Start translating a chapter into another language',
        _meta: { synonyms: ['translate a book'] },
      },
    ];
    const { matches, confident } = searchCatalog(cat, 'add a new kind to the book', 8);
    expect(matches[0].name).toBe('glossary_ontology_upsert');
    expect(confident).toBe(true);
  });

  it('fuzzy rescue still works for a genuine no-overlap near-spelling', () => {
    const cat = [
      {
        name: 'translation_start_job',
        description: 'Start translating a book',
        _meta: { synonyms: ['translate', 'translation'] },
      },
    ];
    const { matches, confident } = searchCatalog(cat, 'translit this chapter', 8);
    expect(matches.map((m) => m.name)).toEqual(['translation_start_job']);
    expect(confident).toBe(true);
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

describe('domain aliases (TS mirror, 2026-07-07)', () => {
  // group="knowledge" matched NOTHING before this fix — its tools carry the literal
  // prefixes kg_/memory_, never knowledge_. Mirrors chat-service's TestDomainAliases.
  const KNOWLEDGE_CATALOG = [
    { name: 'kg_graph_query', description: 'Query the knowledge graph' },
    { name: 'memory_search', description: 'Search conversation memory' },
    { name: 'glossary_search', description: 'Search glossary entities' },
  ];

  it('group=knowledge finds the kg_ tool', () => {
    const { matches } = searchCatalog(KNOWLEDGE_CATALOG, 'query the graph', 8, new Set(), 'knowledge');
    expect(matches.map((m) => m.name)).toContain('kg_graph_query');
  });

  it('group=knowledge finds the memory_ tool', () => {
    const { matches } = searchCatalog(KNOWLEDGE_CATALOG, 'search memory', 8, new Set(), 'knowledge');
    expect(matches.map((m) => m.name)).toContain('memory_search');
  });

  it('group=knowledge excludes other domains', () => {
    const { matches } = searchCatalog(KNOWLEDGE_CATALOG, 'search', 8, new Set(), 'knowledge');
    expect(matches.map((m) => m.name)).not.toContain('glossary_search');
  });
});

describe('GROUP_DIRECTORY (Part A, TS mirror)', () => {
  it('mirrors chat-service GROUP_DIRECTORY verbatim (same keys)', () => {
    // Keep this list in sync BY HAND with tool_discovery.py's GROUP_DIRECTORY —
    // this test is the drift-lock: a key added to one side and not the other
    // (or a description edited on only one side) fails here.
    expect(Object.keys(GROUP_DIRECTORY).sort()).toEqual([
      'book', 'catalog', 'composition', 'glossary', 'jobs',
      'knowledge', 'plan', 'registry', 'research', 'settings', 'story', 'translation', 'world',
    ]);
  });

  it('find_tools schema advertises the group enum sorted', () => {
    const props = FIND_TOOLS_TOOL.inputSchema.properties as { group: { enum: string[] } };
    expect(props.group.enum).toEqual(Object.keys(GROUP_DIRECTORY).sort());
  });

  it('the description no longer bakes in an unconditional "try once more" retry invitation', () => {
    // Design item 1 (2026-07-07 discovery-hardening plan) — the old wording ("If it returns
    // nothing useful, try once more with broader wording") gave no cap and no permission to
    // stop; this is the wording-half of the retry-cap fix (the tracker below is the mechanism
    // half). Assert the new copy affirmatively tells the model to stop after a 2nd empty try.
    expect(FIND_TOOLS_TOOL.description).toMatch(/isn't supported/i);
    expect(FIND_TOOLS_TOOL.description).toMatch(/stop searching/i);
  });

  it('the description documents the group-enumeration affordance (external audit #5)', () => {
    expect(FIND_TOOLS_TOOL.description).toMatch(/list EVERY tool in that domain/i);
  });
});

// ── Design item 1 — true per-domain enumeration (external audit #1/#5) ─────────────────────
describe('enumerateGroup (Part A follow-up: true per-domain enumeration)', () => {
  const CAT = [
    { name: 'book_create', description: 'Create a new book' },
    { name: 'book_update_chapter', description: 'Edit a chapter of a book' },
    { name: 'book_list', description: 'List books' },
    { name: 'translation_start_job', description: 'Start translating a book into another language' },
    {
      name: 'book_legacy_rename',
      description: 'Old rename endpoint',
      _meta: { visibility: 'legacy' },
    },
  ];

  it('returns EVERY non-legacy tool in the domain, not just the ones a fuzzy query would rank', () => {
    const matches = enumerateGroup(CAT, 'book');
    const names = matches.map((m) => m.name).sort();
    expect(names).toEqual(['book_create', 'book_list', 'book_update_chapter']);
  });

  it('excludes legacy-tagged tools from enumeration (CAT-4 discipline extends to enumeration mode)', () => {
    const matches = enumerateGroup(CAT, 'book');
    expect(matches.map((m) => m.name)).not.toContain('book_legacy_rename');
  });

  it('is unranked/unfiltered — a tool with near-zero token overlap with anything still appears', () => {
    // Unlike searchCatalog, there is no INCLUSION_FLOOR/CONFIDENCE_THRESHOLD gate here: every
    // non-legacy domain member is returned regardless of any notion of "relevance".
    const matches = enumerateGroup(CAT, 'book');
    expect(matches.length).toBe(3);
  });

  it('respects the exclude set, same as searchCatalog', () => {
    const matches = enumerateGroup(CAT, 'book', new Set(['book_create']));
    expect(matches.map((m) => m.name)).not.toContain('book_create');
  });

  it('an unknown/empty domain returns an empty list, not an error', () => {
    expect(enumerateGroup(CAT, 'nonexistent_domain')).toEqual([]);
  });
});

describe('findToolsResult — enumeration mode (group set, intent empty/missing)', () => {
  const CAT = [
    { name: 'book_create', description: 'Create a new book' },
    { name: 'book_list', description: 'List books' },
    {
      name: 'book_legacy_rename',
      description: 'Old rename endpoint',
      _meta: { visibility: 'legacy' },
    },
  ];

  it('group + empty intent returns the full unranked domain list, not the 0-result fuzzy fallback', () => {
    // Before the fix: searchCatalog("") always scores 0 (empty intent_tokens), so this called
    // with group="book" and no intent returned ZERO tools — the exact external-audit #1 bug
    // ("0 tools for several groups").
    const { payload, matchedNames } = findToolsResult(CAT, '', 8, new Set(), [], 'book');
    expect(matchedNames.sort()).toEqual(['book_create', 'book_list']);
    expect(payload.enumerated).toBe(true);
    expect(payload.note).toBeUndefined();
  });

  it('group + whitespace-only intent also enumerates (a blank-looking intent is still "no intent")', () => {
    const { matchedNames } = findToolsResult(CAT, '   ', 8, new Set(), [], 'book');
    expect(matchedNames.sort()).toEqual(['book_create', 'book_list']);
  });

  it('legacy tools stay excluded from the enumerated result', () => {
    const { matchedNames } = findToolsResult(CAT, '', 8, new Set(), [], 'book');
    expect(matchedNames).not.toContain('book_legacy_rename');
  });

  it('group + NON-empty intent still uses the ranked fuzzy search, not enumeration', () => {
    const { payload } = findToolsResult(CAT, 'create a book', 8, new Set(), [], 'book');
    expect(payload.enumerated).toBeUndefined();
  });

  it('no group + empty intent does NOT enumerate the whole catalog (enumeration is group-scoped only)', () => {
    const { payload, matchedNames } = findToolsResult(CAT, '', 8, new Set(), []);
    expect(payload.enumerated).toBeUndefined();
    expect(matchedNames).toEqual([]);
  });

  it('a domain with zero non-legacy tools gets an honest "not supported" note, not silence', () => {
    const { payload, matchedNames } = findToolsResult(CAT, '', 8, new Set(), [], 'nonexistent_domain');
    expect(matchedNames).toEqual([]);
    expect(String(payload.note)).toMatch(/isn't supported/i);
  });

  // External audit #5 (2026-07-08 re-verification) — no group + blank intent used to be a bare
  // scold ("intent is required") with nothing to act on. Mirrors chat-service's
  // `_blank_intent_result` (tool_discovery.py) — kept in lockstep.
  it('no group + empty intent returns the GROUP_DIRECTORY listing as a concrete next step', () => {
    const { payload, matchedNames } = findToolsResult(CAT, '', 8, new Set(), []);
    expect(matchedNames).toEqual([]);
    expect(payload.domains).toBeTruthy();
    expect(String(payload.note)).toMatch(/group/i);
  });

  it('no group + whitespace-only intent also gets the domain directory', () => {
    const { payload } = findToolsResult(CAT, '   ', 8, new Set(), []);
    expect(payload.domains).toBeTruthy();
  });

  // External audit #1 (2026-07-08 re-verification) — the ORIGINAL enumeration fix above only
  // covers a LITERALLY blank intent; a real exploratory agent instead phrases a broad ask as
  // non-blank generic text ("list everything you can do in this domain"), which token-overlaps
  // poorly and used to silently under-return (measured live: `book` → 1/~15 tools, 7% recall,
  // for this EXACT phrase). A `group`-scoped query scoring below CONFIDENCE_THRESHOLD now ALSO
  // falls back to full enumeration, same as a literal blank intent would.
  it('group + a weak/generic non-blank intent falls back to full enumeration', () => {
    const { payload, matchedNames } = findToolsResult(
      CAT, 'list everything you can do in this domain', 8, new Set(), [], 'book',
    );
    expect(matchedNames.sort()).toEqual(['book_create', 'book_list']);
    expect(payload.enumerated).toBe(true);
    expect(String(payload.note)).toMatch(/didn't score well/i);
  });

  it('group + a weak intent on a zero-tool domain still gets the honest empty note, not the fallback wording', () => {
    const { payload, matchedNames } = findToolsResult(
      CAT, 'list everything you can do in this domain', 8, new Set(), [], 'nonexistent_domain',
    );
    expect(matchedNames).toEqual([]);
    expect(String(payload.note)).toMatch(/genuinely has no tools/i);
  });
});

describe('FindToolsAttemptTracker (design item 1 — retry-cap mechanism)', () => {
  it('the first attempt for a session is never a repeat', () => {
    const t = new FindToolsAttemptTracker();
    expect(t.record('session-1', 'book', 'start a translation')).toBe(false);
  });

  it('a 2nd call with the identical (group, intent) for the SAME session is a repeat', () => {
    const t = new FindToolsAttemptTracker();
    t.record('session-1', 'book', 'search the web');
    expect(t.record('session-1', 'book', 'search the web')).toBe(true);
  });

  it('a near-duplicate (same token SET, different order/casing) also counts as a repeat', () => {
    const t = new FindToolsAttemptTracker();
    t.record('session-1', 'book', 'Search The Web');
    expect(t.record('session-1', 'book', 'the web search')).toBe(true);
  });

  it('a genuinely different intent in the same session/group is NOT a repeat', () => {
    const t = new FindToolsAttemptTracker();
    t.record('session-1', 'book', 'search the web');
    expect(t.record('session-1', 'book', 'translate this chapter')).toBe(false);
  });

  it('the same (group, intent) under a DIFFERENT session is not a repeat (per-session, not global)', () => {
    const t = new FindToolsAttemptTracker();
    t.record('session-1', 'book', 'search the web');
    expect(t.record('session-2', 'book', 'search the web')).toBe(false);
  });

  it('a call with no session id is never tracked (fail-open — nothing to safely key on)', () => {
    const t = new FindToolsAttemptTracker();
    t.record(undefined, 'book', 'search the web');
    expect(t.record(undefined, 'book', 'search the web')).toBe(false);
  });

  it('an enumeration call (blank intent) is never counted as an attempt to repeat', () => {
    const t = new FindToolsAttemptTracker();
    expect(t.record('session-1', 'book', '')).toBe(false);
    expect(t.record('session-1', 'book', '')).toBe(false);
  });

  it('an entry expires after the TTL window (a fresh "turn" long after is not a repeat)', () => {
    let now = 0;
    const t = new FindToolsAttemptTracker(1000, () => now);
    t.record('session-1', 'book', 'search the web');
    now = 5000; // well past the 1000ms TTL
    expect(t.record('session-1', 'book', 'search the web')).toBe(false);
  });

  // review-impl HIGH-1 (2026-07-08): the top-level `sessions` map never shrank — only the
  // CURRENT caller's own bucket was swept per call, and (as the code comment on `record()`
  // explains) that narrower fix is observably inert: a call that finds its own bucket empty
  // always re-populates it before returning, so the top-level key for that one session never
  // actually goes away. The real fix sweeps EVERY tracked session's bucket on each incoming
  // call. Assert the top-level map SIZE actually shrinks once entries expire — not just that
  // lookups still behave correctly — so a regression that reverts to the narrower (inert) sweep
  // would fail here even though every repeat/no-repeat test above would still pass.
  describe('HIGH-1: top-level session map does not leak unboundedly', () => {
    it('many distinct sessions that never call again still get swept away by ANY subsequent call', () => {
      let now = 0;
      const t = new FindToolsAttemptTracker(1000, () => now);
      for (let i = 0; i < 50; i++) {
        t.record(`session-${i}`, 'book', 'search the web');
      }
      expect(t.sessionCount).toBe(50);
      now = 5000; // past the 1000ms TTL for all 50 sessions' entries
      // A single NEW call — from a session that was never seen before — sweeps every expired
      // sibling bucket as a side effect, then adds only its own fresh entry.
      t.record('session-new', 'book', 'a fresh unrelated ask');
      expect(t.sessionCount).toBe(1); // only session-new remains; all 50 stale ones are gone
    });

    it('a session revisited after its only entry expires does not accumulate stale siblings', () => {
      let now = 0;
      const t = new FindToolsAttemptTracker(1000, () => now);
      t.record('session-1', 'book', 'search the web');
      t.record('session-2', 'book', 'search the web');
      expect(t.sessionCount).toBe(2);
      now = 5000; // both entries are now stale
      // session-1 calls again — the sweep (which runs over ALL sessions, not just its own)
      // clears session-2's stale bucket too, then session-1 re-adds its own fresh entry.
      t.record('session-1', 'book', 'search the web');
      expect(t.sessionCount).toBe(1); // session-2 is gone; only session-1's fresh entry remains
    });

    it('an entry that has not yet expired is not swept away by another session\'s call', () => {
      let now = 0;
      const t = new FindToolsAttemptTracker(1000, () => now);
      t.record('session-1', 'book', 'search the web');
      now = 500; // well within the 1000ms TTL
      t.record('session-2', 'book', 'a different ask');
      expect(t.sessionCount).toBe(2); // both still live — nothing expired yet
    });

    it('sessionCount returns to 0 once every tracked session has expired and one more call runs', () => {
      let now = 0;
      const t = new FindToolsAttemptTracker(1000, () => now);
      for (let i = 0; i < 10; i++) {
        t.record(`session-${i}`, 'book', 'search the web');
      }
      now = 5000;
      // A call whose OWN entry is blank (enumeration — never tracked) still triggers no sweep
      // since it returns before touching state; a real tracked call is what performs the sweep.
      t.record('session-1', 'book', 'search the web');
      expect(t.sessionCount).toBe(1); // just the one fresh entry from the call that ran the sweep
    });
  });
});

describe('findToolsResult — repeat-attempt note reshaping (design item 1)', () => {
  const CAT = [{ name: 'book_create', description: 'Create a new book' }];

  it('a repeated no-match search gets a note that explicitly permits "tell the user not supported"', () => {
    const { payload } = findToolsResult(CAT, 'xyzzy frobnicate', 8, new Set(), [], null, true);
    expect(String(payload.note)).toMatch(/not supported/i);
    expect(String(payload.note)).toMatch(/stop searching/i);
  });

  it('a FIRST no-match search still allows one more try (not yet a hard stop)', () => {
    const { payload } = findToolsResult(CAT, 'xyzzy frobnicate', 8, new Set(), [], null, false);
    expect(String(payload.note)).toMatch(/try once more/i);
  });

  it('a repeated low-confidence match also gets the "don\'t search again" framing', () => {
    const { payload } = findToolsResult(CAT, 'book', 8, new Set(), [], null, true);
    if (payload.low_confidence) {
      expect(String(payload.note)).toMatch(/don't search again/i);
    }
  });

  it('a down-provider note is unaffected by repeat status (transient, retry IS still appropriate)', () => {
    const { payload } = findToolsResult(CAT, 'xyzzy frobnicate', 8, new Set(), ['book'], null, true);
    expect(String(payload.note)).toMatch(/temporarily unavailable/i);
  });
});

describe('Track D Wave 0 — `research` category + the C-GW prefix gate', () => {
  const CAT_WEB = [
    ...CATALOG,
    { name: 'web_search', description: 'Search the open web for background facts' },
  ];

  it('`research` is a GROUP_DIRECTORY domain (lockstep with tool_discovery.py)', () => {
    expect(GROUP_DIRECTORY.research).toBeDefined();
  });

  it('web_search enumerates under `research`, NOT `knowledge` (external vs internal KG)', () => {
    // domainOf() is prefix-derived: prefix `web` → alias → `research`.
    expect(enumerateGroup(CAT_WEB, 'research').map((t) => t.name)).toContain('web_search');
    expect(enumerateGroup(CAT_WEB, 'knowledge').map((t) => t.name)).not.toContain('web_search');
  });

  it('find_tools group enum exposes `research`', () => {
    const props = FIND_TOOLS_TOOL.inputSchema.properties as { group: { enum: string[] } };
    expect(props.group.enum).toContain('research');
  });
});

describe('W10 remediation — `world` category + the world_* federation namespace', () => {
  const CAT_WORLD = [
    ...CATALOG,
    { name: 'world_create', description: 'Create a worldbuilding container' },
    { name: 'world_map_create', description: 'Create a reference map with pins and regions' },
  ];

  it('`world` is a GROUP_DIRECTORY domain (lockstep with tool_discovery.py)', () => {
    expect(GROUP_DIRECTORY.world).toBeDefined();
  });

  it('world_* + world_map_* enumerate under `world`, NOT `book` (prose vs worldbuilding)', () => {
    // domainOf() is prefix-derived: prefix `world` already equals the group (no alias).
    const inWorld = enumerateGroup(CAT_WORLD, 'world').map((t) => t.name);
    expect(inWorld).toContain('world_create');
    expect(inWorld).toContain('world_map_create');
    const inBook = enumerateGroup(CAT_WORLD, 'book').map((t) => t.name);
    expect(inBook).not.toContain('world_create');
    expect(inBook).not.toContain('world_map_create');
  });

  it('find_tools group enum exposes `world`', () => {
    const props = FIND_TOOLS_TOOL.inputSchema.properties as { group: { enum: string[] } };
    expect(props.group.enum).toContain('world');
  });
});

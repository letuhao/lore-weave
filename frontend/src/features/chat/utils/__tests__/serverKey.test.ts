import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, it, expect } from 'vitest';
import {
  FRONTEND_TOOL_NAMES,
  PREFIX_TO_SERVER,
  groupToolsByServer,
  serverKeyForTool,
} from '../serverKey';

// W6 — the FE mirror of chat-service agent_surface.server_key_for_tool.
// Cases mirror services/chat-service/tests/test_agent_surface.py so a drift
// between the two maps shows up as a failing pair.

// Mirror-drift pins — serverKey.ts hand-copies two BE tables; these tests make
// a BE-side change fail SOMETHING on the FE instead of silently mis-grouping.

describe('serverKey mirror pins', () => {
  it('FRONTEND_TOOL_NAMES equals the committed cross-language contract exactly', () => {
    // contracts/frontend-tools.contract.json is the SoT chat-service's
    // test_frontend_tools_contract.py snapshots — same read pattern as
    // nav/__tests__/frontendToolContract.test.ts.
    const contract: Record<string, unknown> = JSON.parse(
      readFileSync(resolve(process.cwd(), '../contracts/frontend-tools.contract.json'), 'utf-8'),
    );
    expect([...FRONTEND_TOOL_NAMES].sort()).toEqual(Object.keys(contract).sort());
  });

  it('PREFIX_TO_SERVER matches the BE _SERVER_KEY_BY_PREFIX table', () => {
    // Inline copy of chat-service app/services/agent_surface.py
    // _SERVER_KEY_BY_PREFIX (asserted by tests/test_agent_surface.py) — a
    // BE-side prefix add/change must be mirrored here AND in serverKey.ts.
    expect(PREFIX_TO_SERVER).toEqual({
      memory: 'knowledge',
      kg: 'knowledge',
      knowledge: 'knowledge',
      glossary: 'glossary',
      book: 'book',
      composition: 'composition',
      plan: 'composition',
      translation: 'translation',
      jobs: 'jobs',
    });
  });
});

describe('serverKeyForTool', () => {
  it.each([
    ['memory_search', 'knowledge'],
    ['kg_query_paths', 'knowledge'],
    ['knowledge_lookup', 'knowledge'],
    ['glossary_search', 'glossary'],
    ['glossary_propose_batch', 'glossary'],
    ['book_create', 'book'],
    ['composition_outline_create', 'composition'],
    ['plan_create_run', 'composition'],
    ['translation_start_job', 'translation'],
    ['jobs_list', 'jobs'],
  ])('%s → %s (owning MCP server)', (name, key) => {
    expect(serverKeyForTool(name)).toBe(key);
  });

  it.each([
    'ui_navigate',
    'ui_open_book',
    'confirm_action',
    'propose_edit',
    'propose_record_edit',
    // frontend check has precedence over the glossary_ prefix.
    'glossary_confirm_action',
    'glossary_propose_entity_edit',
  ])('%s → ui (frontend tools regardless of prefix)', (name) => {
    expect(serverKeyForTool(name)).toBe('ui');
  });

  it('find_tools is consumer-local → chat', () => {
    expect(serverKeyForTool('find_tools')).toBe('chat');
  });

  it.each(['settings_list_models', 'frobnicate', ''])('%s → other', (name) => {
    expect(serverKeyForTool(name)).toBe('other');
  });
});

describe('groupToolsByServer', () => {
  it('groups by server, busiest first, key as tiebreak', () => {
    const groups = groupToolsByServer([
      'glossary_search',
      'memory_search',
      'kg_query_paths',
      'book_create',
    ]);
    expect(groups).toEqual([
      { key: 'knowledge', tools: ['memory_search', 'kg_query_paths'] },
      { key: 'book', tools: ['book_create'] },
      { key: 'glossary', tools: ['glossary_search'] },
    ]);
  });

  it('empty input → no groups', () => {
    expect(groupToolsByServer([])).toEqual([]);
  });
});

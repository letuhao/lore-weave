import { describe, it, expect } from 'vitest';
import { groupToolsByServer, serverKeyForTool } from '../serverKey';

// W6 — the FE mirror of chat-service agent_surface.server_key_for_tool.
// Cases mirror services/chat-service/tests/test_agent_surface.py so a drift
// between the two maps shows up as a failing pair.

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

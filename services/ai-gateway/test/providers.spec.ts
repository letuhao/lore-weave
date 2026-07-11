import { parseProviders, DEFAULT_PREFIX_MAP } from '../src/config/config.js';

describe('parseProviders (C-GW env-driven registry)', () => {
  it('parses a comma-separated name=url list and resolves prefixes by name', () => {
    const warn = jest.fn();
    const ps = parseProviders(
      'knowledge=http://k:8092/mcp,glossary=http://g:8088/mcp,book=http://b:8080/mcp',
      warn,
    );
    expect(ps.map((p) => p.name)).toEqual(['knowledge', 'glossary', 'book']);
    expect(ps[0].mcpUrl).toBe('http://k:8092/mcp');
    expect(ps[0].prefix).toBe(DEFAULT_PREFIX_MAP.knowledge);
    expect(ps[2].prefix).toBe('book_');
    expect(warn).not.toHaveBeenCalled();
  });

  it('falls back to the knowledge+glossary defaults when unset/empty (back-compat)', () => {
    const def = parseProviders(undefined, jest.fn());
    expect(def.map((p) => p.name)).toEqual(['knowledge', 'glossary']);
    expect(def[0].prefix).toBe('memory_');
    expect(def[1].prefix).toBe('glossary_');

    const empty = parseProviders('   ', jest.fn());
    expect(empty.map((p) => p.name)).toEqual(['knowledge', 'glossary']);
  });

  it('skips a malformed entry (no =) with a warning, keeps the valid ones', () => {
    const warn = jest.fn();
    const ps = parseProviders('knowledge=http://k/mcp,garbage,glossary=http://g/mcp', warn);
    expect(ps.map((p) => p.name)).toEqual(['knowledge', 'glossary']);
    expect(warn).toHaveBeenCalledWith(expect.stringContaining('garbage'));
  });

  it('skips entries with an empty name or url', () => {
    const warn = jest.fn();
    const ps = parseProviders('=http://nope/mcp,book=,glossary=http://g/mcp', warn);
    expect(ps.map((p) => p.name)).toEqual(['glossary']);
    expect(warn).toHaveBeenCalledTimes(2);
  });

  it('honors an inline prefix override (name|prefix_=url)', () => {
    const ps = parseProviders('myprov|my_=http://m:9000/mcp', jest.fn());
    expect(ps[0]).toEqual({ name: 'myprov', mcpUrl: 'http://m:9000/mcp', prefix: 'my_' });
  });

  it('resolves knowledge extraPrefixes (kg_, story_, lore_) by name so kg_* + story_* + lore_* tools are allowed (HIGH-1; lore_ = W11-M2 reader tools)', () => {
    const ps = parseProviders('knowledge=http://k:8092/mcp', jest.fn());
    expect(ps[0].prefix).toBe('memory_');
    expect(ps[0].extraPrefixes).toEqual(['kg_', 'story_', 'lore_']);
    // defaults path carries the same extras
    const def = parseProviders(undefined, jest.fn());
    expect(def[0].extraPrefixes).toEqual(['kg_', 'story_', 'lore_']);
  });

  it('resolves book extraPrefixes (world_) so the W10-M1 world-container tools are federated, not dropped', () => {
    const ps = parseProviders('book=http://b:8082/mcp', jest.fn());
    expect(ps[0].prefix).toBe('book_');
    expect(ps[0].extraPrefixes).toEqual(['world_']);
  });

  it('resolves composition extraPrefixes (plan_) for PlanForge MCP tools', () => {
    const ps = parseProviders('composition=http://c:8091/mcp', jest.fn());
    expect(ps[0].prefix).toBe('composition_');
    expect(ps[0].extraPrefixes).toEqual(['plan_']);
  });

  it('honors an inline multi-prefix override (name|canon_+extra_=url)', () => {
    const ps = parseProviders('prov|a_+b_+c_=http://m/mcp', jest.fn());
    expect(ps[0]).toEqual({
      name: 'prov',
      mcpUrl: 'http://m/mcp',
      prefix: 'a_',
      extraPrefixes: ['b_', 'c_'],
    });
  });

  it('derives a default `${name}_` prefix for an unmapped provider with no override (so it is still policed)', () => {
    const ps = parseProviders('weird=http://w/mcp', jest.fn());
    expect(ps[0].name).toBe('weird');
    expect(ps[0].prefix).toBe('weird_');
  });

  it('drops a duplicate provider name with a warning', () => {
    const warn = jest.fn();
    const ps = parseProviders('book=http://b1/mcp,book=http://b2/mcp', warn);
    expect(ps).toHaveLength(1);
    expect(ps[0].mcpUrl).toBe('http://b1/mcp');
    expect(warn).toHaveBeenCalledWith(expect.stringContaining('duplicate'));
  });

  it('skips a second provider claiming an already-taken prefix (keeps first, warns)', () => {
    const warn = jest.fn();
    // Two distinct names both forced onto the `book_` namespace via inline override.
    const ps = parseProviders('book=http://b1/mcp,shadow|book_=http://b2/mcp', warn);
    expect(ps.map((p) => p.name)).toEqual(['book']);
    expect(ps[0].mcpUrl).toBe('http://b1/mcp');
    expect(warn).toHaveBeenCalledWith(expect.stringContaining('prefix'));
  });

  it('skips a second provider whose DERIVED prefix collides with an earlier one', () => {
    const warn = jest.fn();
    // First claims `dup_` via override; second is named `dup` so derives `dup_`.
    const ps = parseProviders('first|dup_=http://a/mcp,dup=http://b/mcp', warn);
    expect(ps.map((p) => p.name)).toEqual(['first']);
    expect(warn).toHaveBeenCalledWith(expect.stringContaining('prefix'));
  });

  it('falls back to defaults when the whole list is malformed (never zero providers)', () => {
    const warn = jest.fn();
    const ps = parseProviders('garbage,,nope', warn);
    expect(ps.map((p) => p.name)).toEqual(['knowledge', 'glossary']);
  });
});

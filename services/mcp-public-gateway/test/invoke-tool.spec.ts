import {
  detectInvokeToolCall,
  injectInvokeToolTool,
  INVOKE_TOOL_NAME,
  INVOKE_TOOL_TOOL,
  notActivatedError,
  requiresActivation,
} from '../src/scope/invoke-tool.js';

describe('detectInvokeToolCall', () => {
  it('unwraps a single invoke_tool call into a normal tools/call for the real target', () => {
    const body = {
      jsonrpc: '2.0',
      method: 'tools/call',
      id: 7,
      params: { name: INVOKE_TOOL_NAME, arguments: { name: 'book_list', arguments: { limit: 5 } } },
    };
    const out = detectInvokeToolCall(body);
    expect(out).toEqual({
      kind: 'rewrite',
      targetName: 'book_list',
      rewritten: {
        jsonrpc: '2.0',
        method: 'tools/call',
        id: 7,
        params: { name: 'book_list', arguments: { limit: 5 } },
      },
    });
  });

  it('defaults missing/non-object target arguments to {}', () => {
    const body = { method: 'tools/call', params: { name: INVOKE_TOOL_NAME, arguments: { name: 'jobs_list' } } };
    const out = detectInvokeToolCall(body);
    expect(out).toMatchObject({ kind: 'rewrite', targetName: 'jobs_list', rewritten: { params: { name: 'jobs_list', arguments: {} } } });
  });

  it('reports a malformed call (missing name) as an isError tool result, not a silent drop', () => {
    const out = detectInvokeToolCall({ method: 'tools/call', id: 3, params: { name: INVOKE_TOOL_NAME, arguments: {} } });
    expect(out?.kind).toBe('malformed');
    const resp = (out as { response: { result: { isError: boolean; content: Array<{ text: string }>; structuredContent: { code: string; message: string } }; id: unknown } }).response;
    expect(resp.result.isError).toBe(true);
    expect(resp.id).toBe(3);
    // item #10: shares the same {code, message} envelope as notActivatedError/confirmActionResult.
    expect(resp.result.structuredContent.code).toBe('VALIDATION'); // C4-mapped from MALFORMED_INVOKE_ARGS
    expect(resp.result.structuredContent.message).toContain('invoke_tool requires a string "name"');
    expect(JSON.parse(resp.result.content[0].text)).toEqual(resp.result.structuredContent);
  });

  it('returns null for a different tool, a batch, or a non-call', () => {
    expect(detectInvokeToolCall({ method: 'tools/call', params: { name: 'book_get' } })).toBeNull();
    expect(detectInvokeToolCall([{ method: 'tools/call', params: { name: INVOKE_TOOL_NAME, arguments: { name: 'book_get' } } }])).toBeNull();
    expect(detectInvokeToolCall({ method: 'tools/list' })).toBeNull();
    expect(detectInvokeToolCall(null)).toBeNull();
  });

  it('carries the confirm_action call through unwrapped-as-if-direct (no special-casing needed)', () => {
    const body = {
      method: 'tools/call',
      id: 1,
      params: { name: INVOKE_TOOL_NAME, arguments: { name: 'confirm_action', arguments: { confirm_token: 't', domain: 'd' } } },
    };
    const out = detectInvokeToolCall(body);
    expect(out).toMatchObject({ kind: 'rewrite', targetName: 'confirm_action', rewritten: { params: { name: 'confirm_action', arguments: { confirm_token: 't', domain: 'd' } } } });
  });
});

describe('requiresActivation', () => {
  it('exempts find_tools, confirm_action, and invoke_tool itself', () => {
    expect(requiresActivation('find_tools')).toBe(false);
    expect(requiresActivation('confirm_action')).toBe(false);
    expect(requiresActivation(INVOKE_TOOL_NAME)).toBe(false);
  });
  it('requires activation for every real domain tool', () => {
    expect(requiresActivation('book_list')).toBe(true);
    expect(requiresActivation('kg_graph_query')).toBe(true);
  });
});

describe('notActivatedError', () => {
  it('shapes an isError tool result naming find_tools as the fix, not a silent no-op', () => {
    const out = notActivatedError(5, 'book_list') as { id: unknown; result: { isError: boolean; content: Array<{ text: string }>; structuredContent: { code: string; message: string } } };
    expect(out.id).toBe(5);
    expect(out.result.isError).toBe(true);
    expect(JSON.parse(out.result.content[0].text).message).toContain('find_tools');
    // item #10: same shared envelope as malformedResult/confirmActionResult, with its own code.
    expect(out.result.structuredContent.code).toBe('NOT_DISCOVERED'); // C4-mapped
  });

  // 2026-07-08: docs/bugs/2026-07-07-mcp-discoverability-external-audit.md issue #4 — the prior
  // "is not available yet" wording reads as "this tool doesn't exist", which is false (raw
  // tools/call for the same name succeeds; invoke_tool's allowlist is advisory only, per OQ1 in
  // docs/specs/2026-07-07-mcp-discovery-and-reliability-hardening.md §3). The fix is wording-only.
  it('does not imply the tool is nonexistent, and names the tool by its real identifier', () => {
    const out = notActivatedError(5, 'kg_graph_query') as { result: { content: Array<{ text: string }> } };
    const message = JSON.parse(out.result.content[0].text).message as string;
    expect(message).toContain("'kg_graph_query'");
    expect(message).not.toMatch(/is not available/i);
    expect(message).not.toMatch(/does ?n'?t exist/i);
    expect(message).toContain("hasn't been discovered yet this session");
    expect(message).toContain('immediately callable once find_tools returns it');
  });
});

describe('injectInvokeToolTool', () => {
  it('appends invoke_tool to a tools/list result, once', () => {
    const text = JSON.stringify({ jsonrpc: '2.0', id: 1, result: { tools: [{ name: 'find_tools' }] } });
    const out = JSON.parse(injectInvokeToolTool(text));
    const names = out.result.tools.map((t: { name: string }) => t.name);
    expect(names).toEqual(['find_tools', 'invoke_tool']);
    // idempotent
    const again = JSON.parse(injectInvokeToolTool(injectInvokeToolTool(text)));
    expect(again.result.tools.filter((t: { name: string }) => t.name === INVOKE_TOOL_NAME)).toHaveLength(1);
  });

  it('rewrites the find_tools description to state the edge-specific invoke_tool flow', () => {
    const text = JSON.stringify({
      jsonrpc: '2.0', id: 1,
      result: { tools: [{ name: 'find_tools', description: 'generic ai-gateway description' }] },
    });
    const out = JSON.parse(injectInvokeToolTool(text));
    const ft = out.result.tools.find((t: { name: string }) => t.name === 'find_tools');
    expect(ft.description).toContain('invoke_tool');
  });

  it('passes through unparseable text unchanged', () => {
    expect(injectInvokeToolTool('not json')).toBe('not json');
  });

  it('the injected tool requires a string name and forbids extra args', () => {
    expect(INVOKE_TOOL_TOOL.inputSchema.required).toEqual(['name']);
    expect(INVOKE_TOOL_TOOL.inputSchema.additionalProperties).toBe(false);
  });

  // Fix 3 (bonus nit): glossary_* descriptions federated verbatim from glossary-service tell the
  // caller to confirm via `glossary_confirm_action` — correct on the authenticated chat-service
  // surface, but on THIS public edge the real confirm tool is the domain-agnostic `confirm_action`.
  it('rewrites a stale "glossary_confirm_action" mention in ANY tool description to "confirm_action"', () => {
    const text = JSON.stringify({
      jsonrpc: '2.0',
      id: 1,
      result: {
        tools: [
          { name: 'glossary_propose_new_kind', description: 'Propose a kind; confirm via glossary_confirm_action.' },
          { name: 'glossary_book_delete', description: 'Delete a book; confirm via glossary_confirm_action.' },
          { name: 'book_get', description: 'no mention here' },
        ],
      },
    });
    const out = JSON.parse(injectInvokeToolTool(text));
    const byName = (n: string) => out.result.tools.find((t: { name: string }) => t.name === n).description;
    expect(byName('glossary_propose_new_kind')).toBe('Propose a kind; confirm via confirm_action.');
    expect(byName('glossary_book_delete')).toBe('Delete a book; confirm via confirm_action.');
    expect(byName('book_get')).toBe('no mention here');
    // no tool description on this edge should ever still mention the stale name after the pass.
    expect(out.result.tools.some((t: { description?: string }) => t.description?.includes('glossary_confirm_action'))).toBe(false);
  });

  it('the generic rewrite applies regardless of tool name (not a hardcoded 9-name list)', () => {
    const text = JSON.stringify({
      jsonrpc: '2.0',
      id: 1,
      result: { tools: [{ name: 'some_future_federated_tool', description: 'see glossary_confirm_action to finish.' }] },
    });
    const out = JSON.parse(injectInvokeToolTool(text));
    expect(out.result.tools[0].description).toBe('see confirm_action to finish.');
  });
});

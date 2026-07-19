import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import {
  UI_TOOLS,
  UI_TOOL_NAMES,
  STUDIO_PANEL_IDS,
  UI_DIRECTIVE_TYPE,
  validateUiToolArgs,
  handleUiTool,
} from '../src/mcp/ui-tools.js';

// Phase 3 (P3.1) — the ai-gateway ui_* directive tools. Two guarantees under test:
//  1) DRIFT: the committed mirror's args/required/enums equal the contract SoT
//     (contracts/frontend-tools.contract.json) — read here from the repo checkout,
//     which the Docker image can't do (why the mirror exists).
//  2) NO SILENT NO-OP: an out-of-enum/missing-required arg is a tool ERROR, never a
//     pass — the exact bug the migration exists to kill.

const CONTRACT = JSON.parse(
  readFileSync(join(__dirname, '../../../contracts/frontend-tools.contract.json'), 'utf-8'),
) as Record<string, { args: Record<string, { type?: string; enum?: string[] }>; required?: string[] }>;

describe('ui-tools drift vs contracts/frontend-tools.contract.json', () => {
  const uiNames = UI_TOOLS.map((t) => t.name).sort();
  const contractUiNames = Object.keys(CONTRACT).filter((k) => k.startsWith('ui_')).sort();

  it('mirrors exactly the contract ui_* tool set (no missing / extra)', () => {
    expect(uiNames).toEqual(contractUiNames);
  });

  for (const tool of UI_TOOLS) {
    describe(tool.name, () => {
      const c = CONTRACT[tool.name];
      const props = tool.inputSchema.properties as Record<string, { enum?: unknown[] }>;

      it('required matches the contract', () => {
        expect((tool.inputSchema.required ?? []).slice().sort()).toEqual((c.required ?? []).slice().sort());
      });

      it('property names match the contract', () => {
        expect(Object.keys(props).sort()).toEqual(Object.keys(c.args).sort());
      });

      it('every closed-set enum matches the contract exactly', () => {
        for (const [key, schema] of Object.entries(c.args)) {
          if (schema.enum) {
            expect(props[key]?.enum).toEqual(schema.enum);
          }
        }
      });
    });
  }

  it('STUDIO_PANEL_IDS equals the contract panel_id enum (the correctness closed set)', () => {
    expect([...STUDIO_PANEL_IDS]).toEqual(CONTRACT['ui_open_studio_panel'].args['panel_id'].enum);
  });
});

describe('validateUiToolArgs — no silent no-op', () => {
  it('accepts valid args', () => {
    expect(validateUiToolArgs('ui_open_studio_panel', { panel_id: 'compose' })).toEqual({ ok: true });
    expect(validateUiToolArgs('ui_navigate', { path: '/books' })).toEqual({ ok: true });
  });

  it('rejects an out-of-enum panel_id with the enum signal (the original silent-no-op bug)', () => {
    const r = validateUiToolArgs('ui_open_studio_panel', { panel_id: 'not-a-real-panel' });
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error).toMatch(/enum: 'not-a-real-panel' is not a valid panel_id/);
  });

  it('rejects a missing required field with the required signal', () => {
    const r = validateUiToolArgs('ui_open_chapter', { book_id: 'b', chapter_id: 'c' }); // mode missing
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error).toMatch(/required: missing property 'mode'/);
  });

  it('rejects an out-of-enum mode / tab', () => {
    expect(validateUiToolArgs('ui_open_chapter', { book_id: 'b', chapter_id: 'c', mode: 'delete' }).ok).toBe(false);
    expect(validateUiToolArgs('ui_open_book', { book_id: 'b', tab: 'nope' }).ok).toBe(false);
  });

  it('allows an absent OPTIONAL enum field (tab/scene_id)', () => {
    expect(validateUiToolArgs('ui_open_book', { book_id: 'b' })).toEqual({ ok: true });
    expect(validateUiToolArgs('ui_focus_manuscript_unit', { chapter_id: 'c' })).toEqual({ ok: true });
  });

  it('rejects a wrong-typed arg (a non-string path is not a silent pass)', () => {
    const r = validateUiToolArgs('ui_navigate', { path: 123 as unknown as string });
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error).toMatch(/type: path must be a string/);
  });

  it('rejects an unknown ui tool', () => {
    expect(validateUiToolArgs('ui_bogus', {}).ok).toBe(false);
  });
});

describe('handleUiTool — returns a directive or an isError result', () => {
  it('valid → a directive the client acts on', () => {
    const res = handleUiTool('ui_navigate', { path: '/settings' });
    expect(res.isError).toBeUndefined();
    expect(res.structuredContent).toEqual({ type: UI_DIRECTIVE_TYPE, tool: 'ui_navigate', args: { path: '/settings' } });
  });

  it('invalid → isError with the enum/required signal, NOT a silent success', () => {
    const res = handleUiTool('ui_open_studio_panel', { panel_id: 'zzz' });
    expect(res.isError).toBe(true);
    expect((res.structuredContent as { code: string }).code).toBe('ui_tool_invalid_args');
    // it must NOT look like a directive (which the client would act on)
    expect((res.structuredContent as { type?: string }).type).not.toBe(UI_DIRECTIVE_TYPE);
  });

  it('UI_TOOL_NAMES covers every advertised ui_* tool', () => {
    for (const t of UI_TOOLS) expect(UI_TOOL_NAMES.has(t.name)).toBe(true);
    expect(UI_TOOL_NAMES.size).toBe(UI_TOOLS.length);
  });
});

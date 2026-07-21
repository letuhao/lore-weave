import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import {
  PROPOSE_EDIT_TOOL,
  PROPOSE_EDIT_NAME,
  PROPOSE_EDIT_DIRECTIVE_TYPE,
  PROPOSE_EDIT_OPERATIONS,
  validateProposeEditArgs,
  handleProposeEdit,
} from '../src/mcp/propose-edit-tool.js';

// Phase 2 (P2.1) — the ai-gateway propose_edit tool. Same two guarantees as ui-tools:
//  1) DRIFT: the mirror's operation enum + required equal the contract SoT.
//  2) NO SILENT NO-OP: a bad/missing arg is a tool ERROR — the exact incident
//     (propose_edit called with propose_record_edit's args) is rejected here.

const CONTRACT = JSON.parse(
  readFileSync(join(__dirname, '../../../contracts/frontend-tools.contract.json'), 'utf-8'),
) as Record<string, { args: Record<string, { type?: string; enum?: string[] }>; required?: string[] }>;

describe('propose-edit-tool drift vs the contract', () => {
  const c = CONTRACT['propose_edit'];
  const props = PROPOSE_EDIT_TOOL.inputSchema.properties as Record<string, { enum?: unknown[] }>;

  it('mirrors the contract required', () => {
    expect((PROPOSE_EDIT_TOOL.inputSchema.required ?? []).slice().sort()).toEqual((c.required ?? []).slice().sort());
  });
  it('mirrors the contract property names', () => {
    expect(Object.keys(props).sort()).toEqual(Object.keys(c.args).sort());
  });
  it('operation enum matches the contract exactly', () => {
    expect(props.operation?.enum).toEqual(c.args.operation.enum);
    expect([...PROPOSE_EDIT_OPERATIONS]).toEqual(c.args.operation.enum);
  });
});

describe('validateProposeEditArgs — no silent no-op (the incident guard)', () => {
  it('accepts valid args (with + without rationale)', () => {
    expect(validateProposeEditArgs({ operation: 'insert_at_cursor', text: 'hi' })).toEqual({ ok: true });
    expect(validateProposeEditArgs({ operation: 'replace_selection', text: 'hi', rationale: 'why' })).toEqual({ ok: true });
  });
  it('rejects an out-of-enum operation with the enum signal', () => {
    const r = validateProposeEditArgs({ operation: 'delete_everything', text: 'x' });
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error).toMatch(/enum: 'delete_everything' is not a valid operation/);
  });
  it('rejects missing operation / missing text with the required signal', () => {
    expect(validateProposeEditArgs({ text: 'x' }).ok).toBe(false);
    expect(validateProposeEditArgs({ operation: 'insert_at_cursor' }).ok).toBe(false);
  });
  it('rejects the INCIDENT shape (propose_record_edit args) — no operation/text', () => {
    const r = validateProposeEditArgs({ domain: 'book', changes: [], base_version: 1, resource_ref: 'x' });
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error).toMatch(/required: missing property 'operation'/);
  });
  it('rejects wrong-typed text/rationale', () => {
    expect(validateProposeEditArgs({ operation: 'insert_at_cursor', text: 123 }).ok).toBe(false);
    expect(validateProposeEditArgs({ operation: 'insert_at_cursor', text: 'x', rationale: 5 }).ok).toBe(false);
  });
});

describe('handleProposeEdit — gated proposal directive or isError', () => {
  it('valid → a GATED proposal directive (not resolve-immediately)', () => {
    const res = handleProposeEdit({ operation: 'insert_at_cursor', text: 'new prose', rationale: 'clarity' });
    expect(res.isError).toBeUndefined();
    expect(res.structuredContent).toEqual({
      type: PROPOSE_EDIT_DIRECTIVE_TYPE, operation: 'insert_at_cursor', text: 'new prose', rationale: 'clarity',
    });
  });
  it('omits rationale when absent', () => {
    const res = handleProposeEdit({ operation: 'replace_selection', text: 'x' });
    expect(res.structuredContent).toEqual({ type: PROPOSE_EDIT_DIRECTIVE_TYPE, operation: 'replace_selection', text: 'x' });
  });
  it('invalid → isError with the signal, NOT a directive', () => {
    const res = handleProposeEdit({ operation: 'nope', text: 'x' });
    expect(res.isError).toBe(true);
    expect((res.structuredContent as { code: string }).code).toBe('propose_edit_invalid_args');
    expect((res.structuredContent as { type?: string }).type).not.toBe(PROPOSE_EDIT_DIRECTIVE_TYPE);
  });
  it('the directive type is DISTINCT from the ui-directive (needs a human gate)', () => {
    expect(PROPOSE_EDIT_DIRECTIVE_TYPE).toBe('io.loreweave/propose-edit');
    expect(PROPOSE_EDIT_NAME).toBe('propose_edit');
  });
});

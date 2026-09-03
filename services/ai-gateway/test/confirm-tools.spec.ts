import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import {
  CONFIRM_DIRECTIVE_TYPE,
  GLOSSARY_CONFIRM_DIRECTIVE_TYPE,
  RECORD_EDIT_DIRECTIVE_TYPE,
  validateConfirmAction,
  validateGlossaryConfirmAction,
  validateGlossaryProposeEntityEdit,
  handleConfirmAction,
  handleGlossaryConfirmAction,
  handleGlossaryProposeEntityEdit,
} from '../src/mcp/confirm-tools.js';
import { PROPOSE_EDIT_DIRECTIVE_TYPE } from '../src/mcp/propose-edit-tool.js';

// V7 / DQ-V9 — the three KIND-C tools as ai-gateway DIRECTIVE tools.
//
// 🔴 THE INVARIANT THESE TESTS EXIST FOR IS "A HUMAN IS STILL IN THE LOOP", and it is the one
// thing a refactor here can destroy while every other test stays green. DQ-V5 originally ruled
// these should become glossary-service MCP tools; that would have given them a SERVER EXECUTOR,
// letting the model complete its own confirmation. Nothing in the old suite asserted a human was
// involved, so that change would have shipped silently. These assert the directive shape — no
// executor, a gate the client must honour — rather than "the function returned something".

const CONTRACT = JSON.parse(
  readFileSync(join(__dirname, '../../../contracts/browser-tools.contract.json'), 'utf-8'),
) as Record<string, { args: Record<string, { type?: string; enum?: string[] }>; required?: string[] }>;

describe('the human gate survives the move to ai-gateway', () => {
  it('confirm_action returns a GATED directive, never a completed action', () => {
    const r = handleConfirmAction({
      confirm_token: 'tok', descriptor: 'book.publish', title: 'Publish ch. 3', domain: 'book',
    });
    expect(r.isError).toBeFalsy();
    expect(r.structuredContent.type).toBe(CONFIRM_DIRECTIVE_TYPE);
    // The directive carries the token for the BROWSER to redeem. It does not carry a result,
    // a job id, or anything implying the write already happened.
    expect(r.structuredContent.confirm_token).toBe('tok');
    for (const forbidden of ['status', 'result', 'job_id', 'applied', 'outcome']) {
      expect(r.structuredContent[forbidden]).toBeUndefined();
    }
    // And the prose must not tell the model the change is done.
    expect(r.content[0].text).toMatch(/ONLY on an action_done outcome/);
  });

  it('every gated TOOL emits a distinct directive type', () => {
    // One name for one concept (IN-7). A shared marker makes the FE render the wrong card — the
    // silent-no-op class this contract exists to prevent.
    //
    // 🔴 THIS TEST WAS GREEN WHILE EXACTLY THAT HAPPENED. It used to read
    //     const all = [CONFIRM_DIRECTIVE_TYPE, RECORD_EDIT_DIRECTIVE_TYPE, PROPOSE_EDIT_...];
    //     expect(new Set(all).size).toBe(3);
    // — three CONSTANTS, all trivially distinct from one another. But there are FOUR gated tools,
    // and `glossary_confirm_action` emitted `CONFIRM_DIRECTIVE_TYPE`. The assertion's population
    // was the markers, not the tools, so the one thing that could go wrong was outside it.
    // Enumerate by TOOL and the collision cannot hide.
    const byTool: Record<string, string> = {
      confirm_action: (handleConfirmAction({
        confirm_token: 't', descriptor: 'd', title: 'x', domain: 'book',
      }).structuredContent as { type: string }).type,
      glossary_confirm_action: (handleGlossaryConfirmAction({
        confirm_token: 't', descriptor: 'd', title: 'x',
      }).structuredContent as { type: string }).type,
      glossary_propose_entity_edit: (handleGlossaryProposeEntityEdit({
        book_id: 'b', entity_id: 'e', base_version: '1', changes: [{ a: 1 }],
      }).structuredContent as { type: string }).type,
      propose_edit: PROPOSE_EDIT_DIRECTIVE_TYPE,
    };
    const markers = Object.values(byTool);
    expect(new Set(markers).size).toBe(Object.keys(byTool).length);
    expect(byTool.glossary_confirm_action).toBe(GLOSSARY_CONFIRM_DIRECTIVE_TYPE);
  });

  it('glossary_confirm_action implies its domain rather than accepting one', () => {
    const r = handleGlossaryConfirmAction({
      confirm_token: 'tok', descriptor: 'glossary.adopt', title: 'Adopt standards',
    });
    expect(r.structuredContent.domain).toBe('glossary');
    // Passing a domain must not be able to redirect a glossary confirm at another service.
    const spoofed = handleGlossaryConfirmAction({
      confirm_token: 'tok', descriptor: 'glossary.adopt', title: 'x', domain: 'settings',
    });
    expect(spoofed.structuredContent.domain).toBe('glossary');
  });

  it('glossary_propose_entity_edit returns a record-edit directive, not a PATCH', () => {
    const r = handleGlossaryProposeEntityEdit({
      book_id: 'b', entity_id: 'e', base_version: '7',
      changes: [{ target: 'name', value: 'Aldric' }],
    });
    expect(r.isError).toBeFalsy();
    expect(r.structuredContent.type).toBe(RECORD_EDIT_DIRECTIVE_TYPE);
    expect(r.structuredContent.base_version).toBe('7');
  });
});

describe('no silent no-op: a bad arg is a tool ERROR', () => {
  it('a domain outside the closed set is REFUSED on the wire', () => {
    const r = handleConfirmAction({
      confirm_token: 't', descriptor: 'd', title: 'x', domain: 'editor',
    });
    expect(r.isError).toBe(true);
    expect(r.content[0].text).toMatch(/^enum: domain must be one of/);
    // The measured incident this mirrors: a free-string arg reached a resolver that silently
    // no-op'd, and the model reported success.
    expect(r.structuredContent.type).toBeUndefined();
  });

  it('a missing base_version is REFUSED — it is the If-Match that prevents a lost update', () => {
    const r = handleGlossaryProposeEntityEdit({
      book_id: 'b', entity_id: 'e', changes: [{ target: 'name' }],
    });
    expect(r.isError).toBe(true);
    expect(r.content[0].text).toMatch(/base_version/);
  });

  it('an empty changes array is REFUSED — a card with nothing on it is a no-op card', () => {
    const r = handleGlossaryProposeEntityEdit({
      book_id: 'b', entity_id: 'e', base_version: '1', changes: [],
    });
    expect(r.isError).toBe(true);
  });

  it('every required arg is individually enforced', () => {
    const full = {
      confirm_token: 't', descriptor: 'd', title: 'x', domain: 'book',
    } as Record<string, unknown>;
    for (const k of Object.keys(full)) {
      const partial = { ...full };
      delete partial[k];
      expect(validateConfirmAction(partial).ok).toBe(false);
    }
    expect(validateConfirmAction(full).ok).toBe(true);
  });
});

describe('a tool keeps its identity across the re-homing', () => {
  // The ai-gateway half of the same invariant asserted in chat-service's
  // test_a_tools_identity_survives_its_rehoming.py. Both halves are needed: this one proves the
  // marker is emitted distinctly, that one proves it maps back to the right name. Each alone
  // stayed green while the confirm card silently stopped rendering in cms-frontend.
  it('glossary_confirm_action does NOT reuse the plain confirm marker', () => {
    const g = handleGlossaryConfirmAction({
      confirm_token: 't', descriptor: 'd', title: 'x',
    }).structuredContent as { type: string; domain: string };
    const plain = handleConfirmAction({
      confirm_token: 't', descriptor: 'd', title: 'x', domain: 'glossary',
    }).structuredContent as { type: string };
    expect(g.type).toBe(GLOSSARY_CONFIRM_DIRECTIVE_TYPE);
    expect(g.type).not.toBe(plain.type);
    // The domain is still pinned server-side, whatever the model passed.
    expect(g.domain).toBe('glossary');
  });

  it('a plain confirm_action carrying domain=glossary is still the PLAIN marker', () => {
    // The two are distinguishable ONLY by marker: `domain` cannot discriminate, because a
    // legitimate confirm_action may target the glossary domain.
    const plain = handleConfirmAction({
      confirm_token: 't', descriptor: 'd', title: 'x', domain: 'glossary',
    }).structuredContent as { type: string };
    expect(plain.type).toBe(CONFIRM_DIRECTIVE_TYPE);
  });
});

describe('drift vs the contract SoT', () => {
  it('confirm_action required matches the contract', () => {
    const c = CONTRACT['confirm_action'];
    for (const k of c.required ?? []) {
      const partial: Record<string, unknown> = {
        confirm_token: 't', descriptor: 'd', title: 'x', domain: 'book',
      };
      delete partial[k];
      expect(validateConfirmAction(partial).ok).toBe(false);
    }
  });

  it('the domain enum equals the contract enum', () => {
    const fromContract = CONTRACT['confirm_action'].args.domain.enum ?? [];
    expect(fromContract.length).toBeGreaterThan(0);
    for (const d of fromContract) {
      expect(
        validateConfirmAction({ confirm_token: 't', descriptor: 'd', title: 'x', domain: d }).ok,
      ).toBe(true);
    }
  });

  it('glossary_confirm_action + glossary_propose_entity_edit required match the contract', () => {
    for (const [name, validate, full] of [
      ['glossary_confirm_action', validateGlossaryConfirmAction,
        { confirm_token: 't', descriptor: 'd', title: 'x' }],
      ['glossary_propose_entity_edit', validateGlossaryProposeEntityEdit,
        { book_id: 'b', entity_id: 'e', base_version: '1', changes: [{ a: 1 }] }],
    ] as [string, (a: Record<string, unknown>) => { ok: boolean }, Record<string, unknown>][]) {
      expect(validate(full).ok).toBe(true);
      for (const k of CONTRACT[name].required ?? []) {
        const partial = { ...full };
        delete partial[k];
        expect(validate(partial).ok).toBe(false);
      }
    }
  });
});

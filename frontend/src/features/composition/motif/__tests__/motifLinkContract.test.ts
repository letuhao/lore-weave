// The frontend's motif-link types, checked against the OpenAPI contract that describes
// what the server actually sends.
//
// Why this file exists. `MotifLinkRow` declared the neighbour FLAT — `neighbor_id`,
// `neighbor_code`, `neighbor_name` — while `motif_repo.list_links` has always nested it
// under `neighbor`. Every edge in the graph panel rendered two blank labels, live, for a
// release. Nothing caught it:
//
//   · the FE unit tests passed — their fixtures were written from the FE TYPE, so both
//     sides of the test agreed on a shape the server never sent;
//   · tsc passed — a type is only wrong relative to something, and it had nothing to be
//     wrong relative to;
//   · the contract passed — its `links` items were `{ type: object }`, freeform, so
//     neither side had a spec to conform to. That was the root cause.
//
// So the contract now pins both shapes, and this test is the joint. It reads the YAML
// rather than restating the fields, because a restated list is the same drift one level up
// (the lesson of `feBridgeAllowlist.test.ts`, which reads the BFF controller for the same
// reason).
//
// The loop is closed by TWO links, and needs both:
//   tsc:        mirror ↔ type      via `satisfies Record<keyof T, true>` in api.ts
//   this test:  mirror ↔ contract
// With only the first, the mirror tracks a type that is free to be wrong. With only the
// second, the mirror can drift from the type it claims to mirror and the check is vacuous.
//
// SCOPE, stated so nobody over-trusts it: this compares field NAMES, not types,
// nullability or `required`. Name drift is the failure that actually shipped (flat vs
// nested), and it is the one a reviewer cannot see by reading either side alone. A wrong
// `string` vs `number` on a correctly-named field would still get through here.
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { load } from 'js-yaml';

import {
  MOTIF_LINK_NEIGHBOR_FIELDS,
  MOTIF_LINK_ROW_FIELDS,
} from '../api';

const CONTRACT = resolve(
  __dirname, '../../../..', '../../contracts/api/composition/v1/openapi.yaml',
);

type Schema = { properties?: Record<string, unknown>; required?: string[] };

function schemas(): Record<string, Schema> {
  const doc = load(readFileSync(CONTRACT, 'utf8')) as {
    components?: { schemas?: Record<string, Schema> };
  };
  const s = doc?.components?.schemas;
  // A missing block would make every assertion below vacuously pass, so fail loudly
  // instead — an empty comparison set is the classic way a green gate protects nothing.
  if (!s) throw new Error(`no components.schemas in ${CONTRACT}`);
  return s;
}

describe('motif-link wire contract', () => {
  it('MotifLinkRow matches the contract field-for-field', () => {
    const spec = schemas().MotifLinkRow;
    expect(spec, 'MotifLinkRow missing from the contract').toBeDefined();
    expect(Object.keys(MOTIF_LINK_ROW_FIELDS).sort())
      .toEqual(Object.keys(spec.properties ?? {}).sort());
  });

  it('MotifLinkNeighbor matches the contract field-for-field', () => {
    const spec = schemas().MotifLinkNeighbor;
    expect(spec, 'MotifLinkNeighbor missing from the contract').toBeDefined();
    expect(Object.keys(MOTIF_LINK_NEIGHBOR_FIELDS).sort())
      .toEqual(Object.keys(spec.properties ?? {}).sort());
  });

  it('the neighbour is NESTED, not flattened onto the row', () => {
    // The specific regression, named. The generic field-list check above would also catch
    // it, but this states the thing that was actually wrong so a future reader sees the
    // bug rather than inferring it from a diff.
    const spec = schemas().MotifLinkRow;
    expect(spec.properties).toHaveProperty('neighbor');
    for (const flat of ['neighbor_id', 'neighbor_code', 'neighbor_name']) {
      expect(spec.properties, `${flat} is the flat shape the server never sent`)
        .not.toHaveProperty(flat);
      expect(MOTIF_LINK_ROW_FIELDS).not.toHaveProperty(flat);
    }
  });

  it('the GET row and the POST 201 edge are kept distinct', () => {
    // `createLink` was typed as returning `MotifLinkRow`; the 201 actually carries
    // from/to ids and no neighbour join. Two endpoints, two shapes.
    const row = schemas().MotifLinkRow;
    const edge = schemas().MotifLinkEdge;
    expect(edge, 'MotifLinkEdge missing from the contract').toBeDefined();
    expect(edge.properties).toHaveProperty('from_motif_id');
    expect(edge.properties).not.toHaveProperty('neighbor');
    expect(row.properties).not.toHaveProperty('from_motif_id');
  });
});

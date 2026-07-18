import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { describe, it, expect } from 'vitest';
import {
  AUTHORABLE_ENTITY_KINDS,
  RELATION_PREDICATES,
  isAuthorableEntityKind,
} from '../entityKinds';

const HERE = dirname(fileURLToPath(import.meta.url));

describe('AUTHORABLE_ENTITY_KINDS', () => {
  it('is the sealed 5-kind authorable set (no faction, no browse-only kinds)', () => {
    expect([...AUTHORABLE_ENTITY_KINDS]).toEqual([
      'character',
      'location',
      'organization',
      'concept',
      'item',
    ]);
  });

  it('does not contain the retired faction misnomer or non-authorable kinds', () => {
    for (const bad of ['faction', 'event_ref', 'preference']) {
      expect(isAuthorableEntityKind(bad)).toBe(false);
    }
  });

  // Machine-check BOTH sides (mcp-tool-io closed-set discipline): the FE
  // picker vocabulary MUST equal the server gate AUTHORABLE_KINDS, or a create
  // option silently 422s. We read the Python source of truth and compare the
  // set membership (order-independent — Python holds a tuple, not ordered UX).
  it('equals the server-side AUTHORABLE_KINDS gate (cross-language lock)', () => {
    const pyPath = resolve(
      HERE,
      '../../../../../../services/knowledge-service/app/db/neo4j_repos/entities.py',
    );
    const src = readFileSync(pyPath, 'utf8');
    // The vocabulary moved into the `AuthorableKind` Literal, from which AUTHORABLE_KINDS is now
    // DERIVED (`get_args`) — done so the FastMCP tool signature can reuse the type and finally
    // advertise `kind` as a real enum instead of describing the closed set in prose. Read the
    // Literal: it is the source of truth, and the tuple can no longer disagree with it.
    const m = src.match(/AuthorableKind\s*=\s*Literal\[([\s\S]*?)\]/);
    expect(m, 'the AuthorableKind Literal not found in entities.py').toBeTruthy();
    const pyKinds = [...m![1].matchAll(/"([a-z_]+)"/g)].map((x) => x[1]);
    expect(pyKinds.length, 'the Literal parsed to no kinds — the regex has drifted').toBeGreaterThan(0);
    expect(new Set(pyKinds)).toEqual(new Set(AUTHORABLE_ENTITY_KINDS));
    // …and the exported tuple the server gate actually checks against must still derive from it.
    expect(src).toContain('AUTHORABLE_KINDS: tuple[str, ...] = get_args(AuthorableKind)');
  });
});

describe('RELATION_PREDICATES', () => {
  it('is a non-empty curated GUI vocabulary (superset of the shipped place-links)', () => {
    for (const p of ['contains', 'borders', 'route_to']) {
      expect(RELATION_PREDICATES).toContain(p);
    }
    expect(RELATION_PREDICATES.length).toBeGreaterThanOrEqual(8);
  });
});

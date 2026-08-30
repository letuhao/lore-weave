import { isUnroutedDownstream } from '../src/kal/downstream';

// T55b — a 404 from a route that DOES NOT EXIST is not a 404 about the caller's resource.
//
// Measured on the live stack by sweeping all 14 KAL routes and probing each declared downstream
// directly: **two** federate to paths nobody built, and both answered with their framework's
// default page. At the KAL's edge that was indistinguishable from "your book has no such
// entity", so a caller had no way to tell a missing feature from a missing row.
//
//     GET  /v1/kal/books/{bookId}/search    -> glossary /internal/books/{id}/entities/search
//                                              "404 page not found"        (Go router)
//     POST /v1/kal/books/{bookId}/retrieve  -> knowledge /internal/books/{id}/retrieve
//                                              {"detail":"Not Found"}      (FastAPI)
//
// The KAL now answers 501 naming the path it federates to. Rule 9: a facade that cannot honour
// an operation refuses by name rather than passing something half-written through.

describe('isUnroutedDownstream — a framework 404 is not a resource 404', () => {
  it('recognises Go\'s default router page — the `search` case, verbatim', () => {
    expect(isUnroutedDownstream('404 page not found')).toBe(true);
    expect(isUnroutedDownstream('404 page not found\n')).toBe(true);
  });

  it('recognises FastAPI\'s unmatched-path body — the `retrieve` case, verbatim', () => {
    expect(isUnroutedDownstream('{"detail":"Not Found"}')).toBe(true);
    expect(isUnroutedDownstream('{"detail": "Not Found"}')).toBe(true);
  });

  it('recognises Nest\'s default', () => {
    expect(isUnroutedDownstream('Cannot GET /internal/books/x/thing')).toBe(true);
    expect(isUnroutedDownstream('Cannot POST /internal/books/x/thing')).toBe(true);
  });

  // ── the controls, and they matter more than the cases above ──────────────────────────────
  //
  // A classifier that said `true` too readily would turn every genuine "this entity is not in
  // this book" into a 501 "not implemented", which is a far worse lie than the one it replaces:
  // the caller would stop asking for rows that are simply absent today and present tomorrow.

  it('a REAL resource 404 still forwards as a 404 — glossary\'s own vocabulary', () => {
    expect(isUnroutedDownstream(
      '{"code":"GLOSS_NOT_FOUND","message":"entity not found in this book"}')).toBe(false);
  });

  it('a FastAPI 404 that carries a REASON is a resource 404, not an unrouted one', () => {
    expect(isUnroutedDownstream('{"detail":"book has no live knowledge project"}')).toBe(false);
    expect(isUnroutedDownstream('{"detail":"Not Found","hint":"x"}')).toBe(false);
  });

  it('an empty body is NOT claimed as unrouted', () => {
    // A 404 with no body says nothing about which kind it is, and guessing "not implemented"
    // would be the classifier inventing a diagnosis it does not have.
    expect(isUnroutedDownstream('')).toBe(false);
    expect(isUnroutedDownstream('   ')).toBe(false);
  });

  it('prose that merely MENTIONS the phrase is not a framework page', () => {
    expect(isUnroutedDownstream(
      '{"detail":"the upstream said 404 page not found for the chapter"}')).toBe(false);
  });

  // T48av — the needles are a claim ABOUT EXTERNAL SOFTWARE: 'each framework's DEFAULT 404
  // page'. Nothing verified it, and one was wrong. These three bodies were captured from the
  // running iso stack on 2026-08-30 by hitting a path that does not exist on each service.
  describe('the bodies the LIVE frameworks actually emit', () => {
    it('FastAPI (knowledge-service :28216)', () => {
      expect(isUnroutedDownstream('{"detail":"Not Found"}')).toBe(true);
    });

    it('Go/chi (glossary-service :28211)', () => {
      expect(isUnroutedDownstream(`404 page not found${String.fromCharCode(10)}`)).toBe(true);
    });

    it('Nest ENVELOPE (knowledge-gateway :23210) — this one did NOT match', () => {
      // The raw needle requires the body to START with `Cannot`; Nest wraps it in JSON, so a
      // KAL route federating to an unbuilt Nest path forwarded a 404 — the lie T55b fixed,
      // surviving for one of the three frameworks the doc-comment names.
      expect(isUnroutedDownstream(
        '{"message":"Cannot GET /no-such-route-xyz","error":"Not Found","statusCode":404}',
      )).toBe(true);
    });

    it('...and a HANDLER saying the resource is absent still forwards as 404', () => {
      // The distinction is the whole point: glossary answers in its own vocabulary when the
      // entity is missing, and that must NOT become a 501 about the KAL's wiring.
      expect(isUnroutedDownstream(
        '{"code":"GLOSS_NOT_FOUND","message":"entity not found in this book"}',
      )).toBe(false);
    });
  });
});

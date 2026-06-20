# Plan — T1 BOOK tools · Glossary Tiered MCP Tools

**Date:** 2026-06-20 · **Size:** L (serial, human-in-loop) · **Branch:** `feat/glossary-assistant-coverage`
**Spec:** [`…tiered-tools.md`](../specs/2026-06-20-glossary-assistant-tiered-tools.md) §3a/§11 #2,#10/§12.6-8 · **Buildplan:** §4 · **Builds on:** Foundation (`25c16879`)
**PO (CLARIFY):** extract shared cores + refactor HTTP (DRY/no-divergence) · delta add/remove (W) for set-replace · `base_version = updated_at` (uniform book tier).

## Goal
Full book-tier ontology control on `/mcp`: adopt (C), shape (create/patch/delete), genre matrix (active/kind-genres delta W), per-entity genre override (R/W). Establishes the per-stream pattern T2/T3 copy.

## Build order (serial; commit at CP-2)

### 1. Core extraction (no behavior change — refactor under green tests)
- `book_ontology_handler.go`: extract `createBookGenreCore` / `createBookKindCore` / `createBookAttributeCore` + `patchBook{Genre,Kind,Attribute}Core` (take params + bookID, return resp/err); refactor the 6 HTTP handlers to call them.
- `book_adopt_handler.go`: extract `adoptBookOntologyCore(ctx, bookID, userID, genres, kinds) error` (the caller-scoped user→system copy-down tx); HTTP `adoptBookOntology` calls it.

### 2. New `adopt` descriptor (extends Foundation spine)
- `action_confirm_token.go`: `descAdopt = "adopt"` in `liveDescriptor`.
- `action_confirm.go`: `effectAdopt` (wraps `adoptBookOntologyCore`) + `previewAdopt` (count picked genres/kinds new-vs-present from current `book_genres`/`book_kinds`); dispatch in `confirmAction`/`previewAction`.
- `action_propose_tools.go`: `toolAdoptStandards` (C — Manage-gated, mint adopt token + card, destructive=false).

### 3. `book_tools.go` — `RegisterBookTools(srv)` (own file, parallelism enabler)
Register: `book_ontology_read` (move from mcp_server.go), `book_delete` (move registration), + new:
- `glossary_book_create` (W, `level` genre|kind|attribute, code-addressed; attr needs kind_code+genre_code) → `createBook*Core`.
- `glossary_book_patch` (W, `level` + code + `base_version` updated_at → 409 via `compareBaseVersion`) → `patchBook*Core`.
- `glossary_book_set_active_genres` (W delta: `add[]`/`remove[]` codes → INSERT/DELETE book_active_genres).
- `glossary_book_set_kind_genres` (W delta: kind_code + `add[]`/`remove[]` genre codes → book_kind_genres).
- `glossary_entity_set_genres` (W) / `glossary_entity_get_genres` (R) → wrap entity_genres core.
- `glossary_adopt_standards` (C) — registered here, handler in action_propose_tools.go.
- `mcpHandler()`: replace inline book-tool registration with `s.RegisterBookTools(srv)`.

### 4. Skill prompt (light)
- `glossary_skill.py`: one line on adopt (scaffold a book) + book-shaping tools.

## VERIFY
- glossary `go test ./internal/api -p 1` green incl new: adopt round-trip (propose→preview new-vs-present→confirm→ontology grows), book_create W (all 3 levels), book_patch 409-on-stale-updated_at, set-active/kind-genres delta add+remove, entity-genres set/get + tenancy; refactor leaves the 6 HTTP handler tests green. gofmt/vet/provider-gate clean.
- chat-service pytest (skill-prompt drift guard).
- **CP-2 cross-service live-smoke** (chat→adopt→confirm→ontology read→create kind→entity) OR `LIVE-SMOKE deferred to D-GKA-T1-LIVE-SMOKE`.

## CP-2 exit
All book tools on `/mcp`, each live-smoked or unit-proven; pattern documented for T2/T3; `/review-impl` on the adopt confirm path + W-tool tenancy.

## Risks
- Core extraction touches 7 shipped handlers → rely on their existing tests staying green (regression guard).
- Delta set-ops must validate each code is a live book row (tenancy) before INSERT.
- adopt re-validates at confirm (idempotent ON CONFLICT) — preview new-vs-present is advisory, confirm re-counts.

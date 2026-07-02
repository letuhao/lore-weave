package api

import (
	"context"
	"errors"
	"fmt"
	"slices"
	"strings"

	"github.com/google/jsonschema-go/jsonschema"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
)

// Shared helpers for the tiered MCP tools (F2): code→id resolvers (so tools take
// human-stable codes, not transposition-prone UUIDs — §6.8/§11 #9), and a
// base-version concurrency check (the H5 lesson — patch tools 409 on drift).

// errVersionConflict is returned by compareBaseVersion when the caller's base
// version no longer matches the live row (optimistic-concurrency drift → 409).
var errVersionConflict = errors.New("base version conflict")

// compareBaseVersion implements the optimistic-concurrency check for patch tools
// (§12.6). `base` is the version the caller read before editing (content_hash for
// genres/attrs, updated_at for kinds); `current` is the live row's version now.
// An empty base means the caller opted out of the check (explicit last-write-wins),
// so it passes. A non-empty base that differs from current → errVersionConflict.
func compareBaseVersion(current, base string) error {
	if base == "" {
		return nil
	}
	if current != base {
		return errVersionConflict
	}
	return nil
}

// resolveBookGenreID maps a book-local genre code to its id (live rows only).
// pgx.ErrNoRows when no such live genre — callers map that to a clean "not found".
func (s *Server) resolveBookGenreID(ctx context.Context, bookID uuid.UUID, code string) (uuid.UUID, error) {
	var id uuid.UUID
	err := s.pool.QueryRow(ctx,
		`SELECT genre_id FROM book_genres
		   WHERE book_id = $1 AND code = $2 AND deprecated_at IS NULL`, bookID, code).Scan(&id)
	return id, err
}

// resolveBookKindID maps a book-local kind code to its book_kind_id (live rows only).
func (s *Server) resolveBookKindID(ctx context.Context, bookID uuid.UUID, code string) (uuid.UUID, error) {
	var id uuid.UUID
	err := s.pool.QueryRow(ctx,
		`SELECT book_kind_id FROM book_kinds
		   WHERE book_id = $1 AND code = $2 AND deprecated_at IS NULL`, bookID, code).Scan(&id)
	return id, err
}

// resolveBookAttrID maps a (kind_code, genre_code, attr_code) triple to a book
// attribute id — attributes are keyed by (kind × genre × code), so the code alone
// is not unique (§ tiering model). Live rows only.
func (s *Server) resolveBookAttrID(ctx context.Context, bookID uuid.UUID, kindCode, genreCode, attrCode string) (uuid.UUID, error) {
	var id uuid.UUID
	err := s.pool.QueryRow(ctx, `
		SELECT a.attr_id
		  FROM book_attributes a
		  JOIN book_kinds  k ON k.book_kind_id = a.kind_id  AND k.deprecated_at IS NULL
		  JOIN book_genres g ON g.genre_id     = a.genre_id AND g.deprecated_at IS NULL
		 WHERE a.book_id = $1 AND k.code = $2 AND g.code = $3 AND a.code = $4
		   AND a.deprecated_at IS NULL`,
		bookID, kindCode, genreCode, attrCode).Scan(&id)
	return id, err
}

// isNoRows is a small predicate so resolver callers read cleanly.
func isNoRows(err error) bool { return errors.Is(err, pgx.ErrNoRows) }

// ── closed-set tool-arg schemas (W0 #2 — the FE-tools LOCKED rule, extended
// to MCP) ─────────────────────────────────────────────────────────────────────
//
// A tool arg whose valid values are a FINITE, code-known set MUST declare a real
// JSON-schema `enum` — prose like "genre | kind | attribute" in the description
// is invisible to a weak model, which then guesses a value (or drifts the arg
// name) and the call dies. The go-sdk infers a tool's inputSchema from the input
// struct and the `jsonschema` tag only carries a description, so closed-set
// tools pre-build their schema here and pass it as Tool.InputSchema (the SDK
// then also VALIDATES calls against the enum, giving the model a self-
// correctable "not one of: [...]" error instead of a silent mis-dispatch).

// The canonical closed sets shared by the ontology tools.
var (
	enumLevels     = []any{"genre", "kind", "attribute"}
	enumFieldTypes = []any{"text", "textarea", "select", "number", "date", "tags", "url", "boolean"}
)

// closedSetSchemaFor infers the input schema for T, then pins each listed arg
// path to its enum. Paths use the FE-contract dotted form ("level",
// "ops[].type") — a "[]" segment descends into an array's item schema. Panics
// at registration time on a path that doesn't resolve (a typo must fail the
// process + tests, never silently advertise an un-enumed schema).
func closedSetSchemaFor[T any](enums map[string][]any) *jsonschema.Schema {
	s, err := jsonschema.For[T](nil)
	if err != nil {
		panic(fmt.Sprintf("closedSetSchemaFor: infer failed: %v", err))
	}
	for path, vals := range enums {
		p := schemaPropAt(s, path)
		// A pointer field infers as types ["null","string"]; keep an explicit
		// JSON null legal (it means "field not supplied") by admitting it to the
		// enum, else a null the handler tolerates would now be schema-rejected.
		if slices.Contains(p.Types, "null") {
			vals = append([]any{nil}, vals...)
		}
		p.Enum = vals
	}
	return s
}

// schemaPropAt walks a dotted path (arrays via "[]") into a property schema.
func schemaPropAt(s *jsonschema.Schema, dotted string) *jsonschema.Schema {
	node := s
	for _, seg := range strings.Split(dotted, ".") {
		key := strings.TrimSuffix(seg, "[]")
		next := node.Properties[key]
		if next == nil {
			panic(fmt.Sprintf("closedSetSchemaFor: no property %q (path %q)", key, dotted))
		}
		node = next
		if strings.HasSuffix(seg, "[]") {
			if node.Items == nil {
				panic(fmt.Sprintf("closedSetSchemaFor: %q is not an array (path %q)", key, dotted))
			}
			node = node.Items
		}
	}
	return node
}

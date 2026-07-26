package api

import (
	"fmt"
	"slices"
	"strings"

	"github.com/google/jsonschema-go/jsonschema"
)

// ── closed-set tool-arg schemas (W0 #2 — the FE-tools LOCKED rule, extended to
// MCP; mirrors glossary-service's internal/api/tool_helpers.go) ─────────────
//
// A tool arg whose valid values are a FINITE, code-known set MUST declare a
// real JSON-schema `enum` — prose like "(chat, compose, translate, admin)" in
// the description is invisible to a weak model, which then guesses a value and
// the call silently mis-dispatches. The go-sdk infers a tool's inputSchema
// from the input struct and the `jsonschema` tag only carries a description,
// so closed-set tools pre-build their schema here and pass it as
// Tool.InputSchema (the SDK then also VALIDATES calls against the enum,
// giving the model a self-correctable "not one of: [...]" error instead of a
// silent mis-dispatch).

// enumSurfaces is the MCP-schema form of validSurfaces (skills.go) — the
// closed set of skill surfaces (where a skill is advertised): chat, compose,
// translate sessions, and the admin panel. Derived from the same slice the
// REST-path validation (validateSkill, patchSkill) checks against, so the
// MCP schema enum and the REST validation can never silently drift apart.
var enumSurfaces = func() []any {
	out := make([]any, len(validSurfaces))
	for i, v := range validSurfaces {
		out[i] = v
	}
	return out
}()

// closedSetSchemaFor infers the input schema for T, then pins each listed arg
// path to its enum. Paths use the FE-contract dotted form ("surface",
// "surfaces[]") — a "[]" segment descends into an array's item schema. Panics
// at registration time on a path that doesn't resolve (a typo must fail the
// process + tests, never silently advertise an un-enumed schema).
func closedSetSchemaFor[T any](enums map[string][]any) *jsonschema.Schema {
	s, err := jsonschema.For[T](nil)
	if err != nil {
		panic(fmt.Sprintf("closedSetSchemaFor: infer failed: %v", err))
	}
	for path, vals := range enums {
		p := schemaPropAt(s, path)
		// A pointer/omitempty field infers as types ["null","string"]; keep an
		// explicit JSON null legal (it means "field not supplied") by admitting
		// it to the enum, else a null the handler tolerates would now be
		// schema-rejected.
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

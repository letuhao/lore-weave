package loreweave_mcp

// Closed-set arg schemas — the shared implementation of the Frontend-Tool Contract's
// sharpest input rule: A CLOSED-SET ARG MUST CARRY AN `enum`.
//
// The rule exists because breaking it shipped a live bug: `panel_id` was advertised as a
// bare string, gemma sent `panel:"editor"`, the resolver matched nothing, and the model
// then reported success for work that never happened. A closed set the schema does not
// declare is a set the model is free to miss.
//
// The failure has a signature that is easy to spot once you look for it: the author KNEW
// the set — they wrote it in the description ("the structure operation: create_part |
// rename_part | …") — but wrote it where only a human reads it. The validator never sees
// prose. Audited live 2026-07-23 over all 299 federated tools, four such args were found,
// including `book_structure_edit.op` and `book_list.kind` — the two ENUM DISCRIMINATORS
// this migration itself introduced, where a dispatch miss is the whole failure mode.
//
// This lives in the kit because glossary-service already had it (`closedSetSchemaFor`) and
// book-service did not, which is exactly how the second service ended up without it. One
// implementation, every service.
//
// See `docs/standards/mcp-tool-io.md` (IN-1..8).

import (
	"fmt"
	"slices"
	"strings"

	"github.com/google/jsonschema-go/jsonschema"
)

// ClosedSetSchema infers the input schema for In and attaches an `enum` to each named
// property. `enums` is keyed by a dotted path (`"op"`, `"changes[].field"`); "[]" steps
// into an array's items.
//
// Panics on an unknown path — a typo'd key would otherwise silently leave the arg
// enum-less, which is the very defect this helper exists to prevent, and a boot-time panic
// on a programming error is the same contract MustValidateToolMeta already uses.
func ClosedSetSchema[In any](enums map[string][]any) *jsonschema.Schema {
	s, err := jsonschema.For[In](nil)
	if err != nil {
		panic(fmt.Sprintf("ClosedSetSchema: infer failed: %v", err))
	}
	for path, vals := range enums {
		p := SchemaPropAt(s, path)
		// A POINTER field infers as types ["null","string"]. Keep an explicit JSON null
		// legal (it means "not supplied") by admitting it to the enum — otherwise a null
		// the handler already tolerates would start being schema-rejected, turning an
		// optional arg into a required one as a side effect of documenting its values.
		if slices.Contains(p.Types, "null") {
			vals = append([]any{nil}, vals...)
		}
		p.Enum = vals
	}
	return s
}

// SchemaPropAt walks a dotted path into a schema's properties. A "[]" suffix on a segment
// steps into that property's array items.
func SchemaPropAt(s *jsonschema.Schema, dotted string) *jsonschema.Schema {
	node := s
	for _, seg := range strings.Split(dotted, ".") {
		key := strings.TrimSuffix(seg, "[]")
		next := node.Properties[key]
		if next == nil {
			panic(fmt.Sprintf("SchemaPropAt: no property %q (path %q)", key, dotted))
		}
		node = next
		if strings.HasSuffix(seg, "[]") {
			if node.Items == nil {
				panic(fmt.Sprintf("SchemaPropAt: %q is not an array (path %q)", key, dotted))
			}
			node = node.Items
		}
	}
	return node
}

// EnumeratedValuesInDescription extracts a closed set that a description ENUMERATES in
// prose — `a | b | c`, with or without spaces, and tolerating quotes. Returns nil when the
// text does not enumerate one.
//
// This is the detector behind the drift gate: prose that lists the legal values while the
// schema advertises a bare string is the exact shape of the bug above, and it is
// mechanically findable. Deliberately conservative — it requires at least two pipe-joined
// bare tokens, so ordinary prose containing a stray "|" does not trip it.
func EnumeratedValuesInDescription(desc string) []string {
	// Cut a leading "…:" label ("the structure operation: a | b | c").
	body := desc
	if i := strings.LastIndex(desc, ":"); i >= 0 && i < len(desc)-1 {
		body = desc[i+1:]
	}
	// Stop at the first sentence end / parenthetical so trailing prose is not swallowed.
	for _, stop := range []string{"(", ". ", "—", " -- "} {
		if i := strings.Index(body, stop); i > 0 {
			body = body[:i]
		}
	}
	parts := strings.Split(body, "|")
	if len(parts) < 2 {
		return nil
	}
	out := make([]string, 0, len(parts))
	for _, p := range parts {
		tok := strings.TrimSpace(p)
		tok = strings.Trim(tok, `"'`)
		// A legal value is a bare token: letters/digits/_/-, no spaces. Anything else
		// means this is prose that merely contains a pipe, not an enumeration.
		if tok == "" || strings.ContainsAny(tok, " \t") {
			return nil
		}
		for _, r := range tok {
			if !(r == '_' || r == '-' || r == '.' ||
				(r >= 'a' && r <= 'z') || (r >= 'A' && r <= 'Z') || (r >= '0' && r <= '9')) {
				return nil
			}
		}
		out = append(out, tok)
	}
	return out
}

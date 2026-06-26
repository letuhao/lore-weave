package api

// G3b — shared PATCH plumbing for the book-tier ontology handlers. A small,
// spec-driven decoder so each handler declares WHICH fields it accepts (and how to
// validate them) without re-deriving the same map[string]RawMessage loop, and a
// single book-scoped UPDATE builder. Table/column names passed here are internal
// constants (never request input), so the fmt-built SQL carries no injection risk.

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"

	"github.com/google/uuid"
)

type updateField struct {
	col string
	val any
}

type fieldKind int

const (
	fkString         fieldKind = iota // any string
	fkStringNonEmpty                  // trimmed non-empty string
	fkInt
	fkBool
	fkStringPtr // nullable text: a string or JSON null
	fkOptions   // []string (TEXT[])
)

type patchSpec struct {
	json string
	col  string
	kind fieldKind
}

// scanPatchFields decodes a partial JSON body, keeping only the declared fields
// that are present, validating each per its kind. Writes 400 + returns false on
// any malformed value.
func scanPatchFields(w http.ResponseWriter, r *http.Request, specs []patchSpec) ([]updateField, bool) {
	var in map[string]json.RawMessage
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid JSON")
		return nil, false
	}
	fields := []updateField{}
	for _, sp := range specs {
		raw, ok := in[sp.json]
		if !ok {
			continue
		}
		switch sp.kind {
		case fkString:
			var v string
			if err := json.Unmarshal(raw, &v); err != nil {
				return nil, badPatch(w, sp.json)
			}
			fields = append(fields, updateField{sp.col, v})
		case fkStringNonEmpty:
			var v string
			if err := json.Unmarshal(raw, &v); err != nil || strings.TrimSpace(v) == "" {
				return nil, badPatch(w, sp.json)
			}
			fields = append(fields, updateField{sp.col, v})
		case fkInt:
			var v int
			if err := json.Unmarshal(raw, &v); err != nil {
				return nil, badPatch(w, sp.json)
			}
			fields = append(fields, updateField{sp.col, v})
		case fkBool:
			var v bool
			if err := json.Unmarshal(raw, &v); err != nil {
				return nil, badPatch(w, sp.json)
			}
			fields = append(fields, updateField{sp.col, v})
		case fkStringPtr:
			var v *string
			if err := json.Unmarshal(raw, &v); err != nil {
				return nil, badPatch(w, sp.json)
			}
			fields = append(fields, updateField{sp.col, v})
		case fkOptions:
			var v []string
			if err := json.Unmarshal(raw, &v); err != nil {
				return nil, badPatch(w, sp.json)
			}
			fields = append(fields, updateField{sp.col, v})
		}
	}
	return fields, true
}

func badPatch(w http.ResponseWriter, field string) bool {
	writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid "+field)
	return false
}

// applyBookUpdate runs a book-scoped partial UPDATE (no-op when no fields changed).
// `table`/`idCol` are caller-supplied constants, not request input.
func (s *Server) applyBookUpdate(ctx context.Context, table, idCol string, bookID, id uuid.UUID, fields []updateField) error {
	if len(fields) == 0 {
		return nil
	}
	setClauses := make([]string, 0, len(fields)+1)
	args := make([]any, 0, len(fields)+2)
	argN := 1
	for _, f := range fields {
		setClauses = append(setClauses, fmt.Sprintf("%s = $%d", f.col, argN))
		args = append(args, f.val)
		argN++
	}
	setClauses = append(setClauses, "updated_at = now()")
	args = append(args, bookID, id)
	sql := fmt.Sprintf(
		"UPDATE %s SET %s WHERE book_id = $%d AND %s = $%d AND deprecated_at IS NULL",
		table, strings.Join(setClauses, ", "), argN, idCol, argN+1)
	_, err := s.pool.Exec(ctx, sql, args...)
	return err
}

// ── per-resource field sets ────────────────────────────────────────────────────

func scanStringIntFields(w http.ResponseWriter, r *http.Request, strCols, intCols []string) ([]updateField, bool) {
	specs := make([]patchSpec, 0, len(strCols)+len(intCols))
	for _, c := range strCols {
		kind := fkString
		if c == "name" {
			kind = fkStringNonEmpty
		}
		specs = append(specs, patchSpec{json: c, col: c, kind: kind})
	}
	for _, c := range intCols {
		specs = append(specs, patchSpec{json: c, col: c, kind: fkInt})
	}
	return scanPatchFields(w, r, specs)
}

func scanBookKindFields(w http.ResponseWriter, r *http.Request) ([]updateField, bool) {
	return scanPatchFields(w, r, []patchSpec{
		{json: "name", col: "name", kind: fkStringNonEmpty},
		{json: "description", col: "description", kind: fkStringPtr},
		{json: "icon", col: "icon", kind: fkString},
		{json: "color", col: "color", kind: fkString},
		{json: "sort_order", col: "sort_order", kind: fkInt},
		{json: "is_hidden", col: "is_hidden", kind: fkBool},
	})
}

func scanBookAttrFields(w http.ResponseWriter, r *http.Request) ([]updateField, bool) {
	return scanPatchFields(w, r, []patchSpec{
		{json: "name", col: "name", kind: fkStringNonEmpty},
		{json: "description", col: "description", kind: fkStringPtr},
		{json: "field_type", col: "field_type", kind: fkString},
		{json: "is_required", col: "is_required", kind: fkBool},
		{json: "sort_order", col: "sort_order", kind: fkInt},
		{json: "options", col: "options", kind: fkOptions},
		{json: "auto_fill_prompt", col: "auto_fill_prompt", kind: fkStringPtr},
		{json: "translation_hint", col: "translation_hint", kind: fkStringPtr},
		// D-EXTRACT-ATTR-MERGE-DEFAULTS — let an author override the seeded heuristic
		// (fill_if_empty / append / overwrite / replace / manual) per attribute.
		{json: "merge_strategy", col: "merge_strategy", kind: fkString},
	})
}

package api

import (
	"fmt"
	"strings"
	"unicode"
)

// Raw lexical search for the glossary entity list — the entity-side mirror of
// the chapter raw search (book-service search.go). Plan:
// docs/plans/2026-06-14-glossary-list-overhaul.md (Feature C / P3).
//
// The matcher strategy is identical to chapters: ILIKE exact-substring is the
// PRIMARY leg (CJK-safe), pg_trgm similarity() only ranks. The SQL leg lives in
// entity_handler.go (listEntities, search_mode=raw); the pure helpers here build
// the per-hit `match` payload (which field matched + verbatim snippet + rune
// offsets) so the logic is unit-testable without a live Postgres.

const (
	// maxEntitySearchRunes caps the search query length (cost/injection guard),
	// mirroring book-service's maxSearchQueryRunes.
	maxEntitySearchRunes = 256
	// entitySnippetWindow — total context runes around a match. Entity surfaces
	// (names/aliases) are short, but a long alias list joined into one string can
	// exceed this, so we still window.
	entitySnippetWindow = 120
)

// entityMatch is the per-row "why it matched" payload returned in raw search
// mode. Highlights are Unicode CODE-POINT (rune) offsets within Snippet, not
// UTF-16 units — clients index by code point (mirrors the chapter search).
type entityMatch struct {
	FieldCode  string  `json:"field_code"` // name | alias | translation
	Snippet    string  `json:"snippet"`
	Highlights [][]int `json:"highlights"`
}

// escapeLikePattern wraps q in %…% for an ILIKE substring match, escaping the
// LIKE metacharacters (\ % _) so a literal "100%" or "a_b" matches literally.
// Default ILIKE ESCAPE is backslash. (Copied from book-service search.go — the
// two services don't share a package.)
func escapeLikePattern(q string) string {
	r := strings.NewReplacer(`\`, `\\`, `%`, `\%`, `_`, `\_`)
	return "%" + r.Replace(q) + "%"
}

// indexRunesFold returns the rune index of the first case-insensitive occurrence
// of q in t, or -1. Pure rune comparison so CJK offsets are exact.
func indexRunesFold(t, q []rune) int {
	if len(q) == 0 || len(q) > len(t) {
		return -1
	}
	for i := 0; i+len(q) <= len(t); i++ {
		match := true
		for j := 0; j < len(q); j++ {
			if unicode.ToLower(t[i+j]) != unicode.ToLower(q[j]) {
				match = false
				break
			}
		}
		if match {
			return i
		}
	}
	return -1
}

type entityHighlight struct {
	Snippet string
	HLStart int
	HLEnd   int
	Matched bool
}

// computeEntityHighlight locates query in text and returns a windowed verbatim
// snippet plus rune offsets within the snippet. When the query is not an exact
// substring (trigram-only hit) it returns a leading window with Matched=false.
func computeEntityHighlight(text, query string, window int) entityHighlight {
	tr := []rune(text)
	mi := indexRunesFold(tr, []rune(query))
	if mi < 0 {
		end := len(tr)
		if end > window {
			end = window
		}
		return entityHighlight{Snippet: string(tr[:end])}
	}
	matchEnd := mi + len([]rune(query))
	ctx := window / 2
	winStart := mi - ctx
	if winStart < 0 {
		winStart = 0
	}
	winEnd := matchEnd + ctx
	if winEnd > len(tr) {
		winEnd = len(tr)
	}
	return entityHighlight{
		Snippet: string(tr[winStart:winEnd]),
		HLStart: mi - winStart,
		HLEnd:   matchEnd - winStart,
		Matched: true,
	}
}

// buildEntityMatch picks the field that best explains why an entity matched the
// raw query and returns its highlighted snippet. Preference order mirrors what
// the SQL ranks on: the canonical name, then each alias, then the display-
// language translated name. The first field with an EXACT substring hit wins
// (these are the rows the ILIKE-first ORDER BY floats to the top). If nothing
// matches exactly (a trigram-only hit), it falls back to a leading window of the
// name with no highlight span — so the UI still shows a sensible snippet.
func buildEntityMatch(name string, aliases []string, translation *string, q string) entityMatch {
	type cand struct {
		field string
		text  string
	}
	cands := make([]cand, 0, 2+len(aliases))
	if name != "" {
		cands = append(cands, cand{"name", name})
	}
	for _, a := range aliases {
		if a != "" {
			cands = append(cands, cand{"alias", a})
		}
	}
	if translation != nil && *translation != "" {
		cands = append(cands, cand{"translation", *translation})
	}

	for _, c := range cands {
		hl := computeEntityHighlight(c.text, q, entitySnippetWindow)
		if hl.Matched {
			return entityMatch{
				FieldCode:  c.field,
				Snippet:    hl.Snippet,
				Highlights: [][]int{{hl.HLStart, hl.HLEnd}},
			}
		}
	}

	// Trigram-only hit (no exact substring in any field) — show the name (or the
	// first available field) as context with no highlight span.
	if len(cands) > 0 {
		hl := computeEntityHighlight(cands[0].text, q, entitySnippetWindow)
		return entityMatch{FieldCode: cands[0].field, Snippet: hl.Snippet, Highlights: [][]int{}}
	}
	return entityMatch{FieldCode: "name", Snippet: "", Highlights: [][]int{}}
}

// entityOrderBy maps the ?sort= query value to a fixed, whitelisted ORDER BY
// clause (no user input is ever interpolated). An unrecognised value falls back
// to the default (most-recently-updated first), matching the previous lenient
// behaviour.
//
// When rawMode is true and the caller did not pick an explicit sort (or asked
// for "relevance"), ordering is by relevance: exact-substring hits first, then
// trigram similarity desc, then name. relevanceArgs is "$<qArg>"/"$<patArg>"
// resolved by the caller (the bound positions of the raw query + escaped
// pattern); if they are unset (no raw query) we fall back to the default.
func entityOrderBy(sortKey string, rawMode bool, qArg, patArg int) string {
	const aliasesExpr = "glossary_aliases_text(e.cached_aliases)"
	const defaultOrder = "ORDER BY e.updated_at DESC"
	const byNameTiebreak = "e.cached_name ASC NULLS LAST, e.entity_id"

	if rawMode && (sortKey == "" || sortKey == "relevance") {
		if qArg > 0 && patArg > 0 {
			return fmt.Sprintf(
				"ORDER BY (e.cached_name ILIKE $%d OR %s ILIKE $%d) DESC, "+
					"GREATEST(similarity(coalesce(e.cached_name,''), $%d), similarity(%s, $%d)) DESC, %s",
				patArg, aliasesExpr, patArg, qArg, aliasesExpr, qArg, byNameTiebreak)
		}
		return defaultOrder // raw mode requested but no query bound — nothing to rank
	}

	switch sortKey {
	case "name":
		return "ORDER BY " + byNameTiebreak
	case "name_desc":
		return "ORDER BY e.cached_name DESC NULLS LAST, e.entity_id"
	case "updated_at_asc":
		return "ORDER BY e.updated_at ASC"
	case "updated_at", "":
		return defaultOrder
	case "created_at":
		return "ORDER BY e.created_at DESC, e.entity_id"
	case "created_at_asc":
		return "ORDER BY e.created_at ASC, e.entity_id"
	case "kind":
		return "ORDER BY ek.sort_order ASC, ek.name ASC, " + byNameTiebreak
	case "status":
		return "ORDER BY e.status ASC, " + byNameTiebreak
	case "alive":
		return "ORDER BY e.alive DESC, " + byNameTiebreak
	default:
		return defaultOrder
	}
}

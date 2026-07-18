package api

// D-2-ONTOLOGY-BLOAT — the MCP `glossary_book_ontology_read` tool returned the FULL book ontology
// with every attribute's complete definition inlined (description, options, auto_fill_prompt — the
// last is a whole LLM prompt). A /review-impl measured up to 117KB, 88.7% of real books over 32KB.
// It is the same bloat class the `list_system_standards` bomb was (44KB, called 24x, built nothing):
// the bulk is prose/machinery the reader does not act on, and it crowds a mid-tier model's context
// out of the window.
//
// The sibling `toolListKinds` already solved this by projecting to a compact view (see standardKind).
// This does the same for the book ontology — but with the ONE piece of care the debt row flagged:
// glossary_book_patch keys an edit by {level, code, kind_code, genre_code} + base_version (the
// updated_at you read). So the compact shape MUST keep those identifiers AND every row's
// base_version, or a read→patch flow breaks (the OCC token would be un-obtainable without a re-read).
// What it drops is the per-attribute PROSE + MACHINERY that is the actual bloat: description, options,
// auto_fill_prompt, translation_hint, source_ref, merge_strategy, attr_id, sort_order.

type compactGenre struct {
	Code        string `json:"code"`
	Name        string `json:"name"`
	BaseVersion string `json:"base_version"` // OCC token for glossary_book_patch(level=genre)
}

type compactKind struct {
	Code           string `json:"code"`
	Name           string `json:"name"`
	Description    *string `json:"description,omitempty"`
	AttributeCount int    `json:"attribute_count"` // the "count/summary" — full attr defs come with the kind
	BaseVersion    string `json:"base_version"`    // OCC token for glossary_book_patch(level=kind)
}

// compactAttr keeps exactly what a reader needs to UNDERSTAND the attribute and to PATCH it —
// its identity (code + kind_code + genre_code), its shape (field_type, is_required), and its OCC
// token. The heavy fields (description/options/auto_fill_prompt/translation_hint/…) are dropped.
type compactAttr struct {
	Code        string `json:"code"`
	KindCode    string `json:"kind_code"`
	GenreCode   string `json:"genre_code,omitempty"`
	Name        string `json:"name"`
	FieldType   string `json:"field_type"`
	IsRequired  bool   `json:"is_required"`
	BaseVersion string `json:"base_version"` // OCC token for glossary_book_patch(level=attribute)
}

type compactBookOntology struct {
	BookID     string         `json:"book_id"`
	Genres     []compactGenre `json:"genres"`
	Kinds      []compactKind  `json:"kinds"`
	Attributes []compactAttr  `json:"attributes"`
	Note       string         `json:"note"`
}

// compactBookOntologyOf projects the full ontology to the reader-sized view. It resolves each
// attribute's kind_code/genre_code from the kind/genre id maps so a patch can target it by code.
func compactBookOntologyOf(ont *bookOntologyResp) *compactBookOntology {
	if ont == nil {
		return nil
	}
	// id → code, so an attribute (which carries kind_id/genre_id) can be addressed by CODE (what
	// glossary_book_patch takes).
	kindCodeByID := make(map[string]string, len(ont.Kinds))
	attrCountByKindID := make(map[string]int, len(ont.Kinds))
	for _, k := range ont.Kinds {
		kindCodeByID[k.BookKindID] = k.Code
	}
	genreCodeByID := make(map[string]string, len(ont.Genres))
	for _, g := range ont.Genres {
		genreCodeByID[g.GenreID] = g.Code
	}
	for _, a := range ont.Attributes {
		attrCountByKindID[a.KindID]++
	}

	out := &compactBookOntology{
		BookID: ont.BookID,
		Genres: make([]compactGenre, 0, len(ont.Genres)),
		Kinds:  make([]compactKind, 0, len(ont.Kinds)),
		Note: "Compact view: each attribute's heavy definition fields (its long description, its " +
			"choice list, and its auto-fill instruction) are omitted — you do not need them to reason " +
			"about or patch the structure. To edit any row, call glossary_book_patch with the code + " +
			"base_version shown here.",
	}
	for _, g := range ont.Genres {
		out.Genres = append(out.Genres, compactGenre{Code: g.Code, Name: g.Name, BaseVersion: g.BaseVersion})
	}
	for _, k := range ont.Kinds {
		out.Kinds = append(out.Kinds, compactKind{
			Code:           k.Code,
			Name:           k.Name,
			Description:    k.Description,
			AttributeCount: attrCountByKindID[k.BookKindID],
			BaseVersion:    k.BaseVersion,
		})
	}
	// Attributes stay listed (patch needs their per-row base_version) but compact.
	out.Attributes = make([]compactAttr, 0, len(ont.Attributes))
	for _, a := range ont.Attributes {
		out.Attributes = append(out.Attributes, compactAttr{
			Code:        a.Code,
			KindCode:    kindCodeByID[a.KindID],
			GenreCode:   genreCodeByID[a.GenreID],
			Name:        a.Name,
			FieldType:   a.FieldType,
			IsRequired:  a.IsRequired,
			BaseVersion: a.BaseVersion,
		})
	}
	return out
}

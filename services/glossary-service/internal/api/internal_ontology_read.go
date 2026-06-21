package api

import (
	"errors"
	"net/http"

	"github.com/jackc/pgx/v5/pgconn"
)

// D-KG-LG-REAL — the glossary "LG" internal-ontology read the knowledge-service
// KG ontology resolver / adopt-gate anchors to (knowledge-service
// app/clients/glossary_ontology_client.py, contract _deps/glossary-ontology-read.yaml).
// Two variants, both internal-token gated (registered under /internal):
//   * GET /internal/books/{book_id}/ontology      — node-kinds for a specific book.
//   * GET /internal/users/{user_id}/glossary-standards — the shared System kind
//     catalog (the standards baseline for a book-less project).
// Response shape mirrors the KG-side `OntologyKinds` Pydantic model exactly.

type internalOntologyKind struct {
	Code string `json:"code"`
	Name string `json:"name"`
	Tier string `json:"tier"`
}

type internalOntologyKinds struct {
	Source string                 `json:"source"`
	BookID *string                `json:"book_id,omitempty"`
	Kinds  []internalOntologyKind `json:"kinds"`
}

// internalBookOntology — GET /internal/books/{book_id}/ontology. Returns the
// book's node-kinds (book tier) for the KG adopt-gate cross-check. Reuses the
// same book-local read as the public getBookOntology; the trust boundary is the
// internal token (no per-user grant — the consumer is knowledge-service S2S).
func (s *Server) internalBookOntology(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	ont, err := s.loadBookOntology(r.Context(), bookID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "load book ontology failed")
		return
	}
	bid := bookID.String()
	kinds := make([]internalOntologyKind, 0, len(ont.Kinds))
	for _, k := range ont.Kinds {
		kinds = append(kinds, internalOntologyKind{Code: k.Code, Name: k.Name, Tier: "book"})
	}
	writeJSON(w, http.StatusOK, internalOntologyKinds{Source: "book", BookID: &bid, Kinds: kinds})
}

// internalUserGlossaryStandards — GET /internal/users/{user_id}/glossary-standards.
// Returns the user's resolved kind catalog (the standards baseline) for a
// book-less project's adopt-gate cross-check. Per CLAUDE.md › User Boundaries,
// resolution merges tiers lowest-precedence first: System defaults, then the
// user's own per-user kinds (user_kinds) shadow System by code. So the KG
// resolver sees a user's custom kinds, not just the shared System baseline.
func (s *Server) internalUserGlossaryStandards(w http.ResponseWriter, r *http.Request) {
	userID, ok := parsePathUUID(w, r, "user_id")
	if !ok {
		return
	}
	sysKinds, err := s.loadKinds(r.Context())
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "load glossary standards failed")
		return
	}
	// System tier first; byCode tracks each code's slot so a per-user kind with a
	// matching code overwrites in place (shadow), preserving System ordering.
	byCode := make(map[string]int, len(sysKinds))
	out := make([]internalOntologyKind, 0, len(sysKinds))
	for _, k := range sysKinds {
		byCode[k.Code] = len(out)
		out = append(out, internalOntologyKind{Code: k.Code, Name: k.Name, Tier: "system"})
	}

	// Per-user tier: active, non-trashed user_kinds owned by this user. If the
	// user_kinds table isn't present yet (un-migrated glossary DB), degrade to the
	// System-only baseline rather than 500 — the gate still gets the defaults.
	rows, err := s.pool.Query(r.Context(), `
		SELECT code, name FROM user_kinds
		WHERE owner_user_id = $1 AND is_active = true
		  AND deleted_at IS NULL AND permanently_deleted_at IS NULL
		ORDER BY code`, userID)
	if err != nil {
		var pgErr *pgconn.PgError
		if errors.As(err, &pgErr) && pgErr.Code == "42P01" {
			writeJSON(w, http.StatusOK, internalOntologyKinds{Source: "user_standards", Kinds: out})
			return
		}
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "load user kinds failed")
		return
	}
	defer rows.Close()
	for rows.Next() {
		var code, name string
		if err := rows.Scan(&code, &name); err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "scan user kind failed")
			return
		}
		uk := internalOntologyKind{Code: code, Name: name, Tier: "user"}
		if idx, dup := byCode[code]; dup {
			out[idx] = uk // user shadows the System kind of the same code
		} else {
			byCode[code] = len(out)
			out = append(out, uk)
		}
	}
	if err := rows.Err(); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "user kind rows error")
		return
	}
	writeJSON(w, http.StatusOK, internalOntologyKinds{Source: "user_standards", Kinds: out})
}

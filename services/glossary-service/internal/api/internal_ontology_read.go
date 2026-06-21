package api

import "net/http"

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
// Returns the global SYSTEM kind catalog (the shared standards baseline) for a
// book-less project's adopt-gate cross-check. The user_id rides in the path for
// symmetry/logging; the System catalog is global (per-user kind additions are a
// later refinement — the baseline is what the gate needs today).
func (s *Server) internalUserGlossaryStandards(w http.ResponseWriter, r *http.Request) {
	if _, ok := parsePathUUID(w, r, "user_id"); !ok {
		return
	}
	kinds, err := s.loadKinds(r.Context())
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "load glossary standards failed")
		return
	}
	out := make([]internalOntologyKind, 0, len(kinds))
	for _, k := range kinds {
		out = append(out, internalOntologyKind{Code: k.Code, Name: k.Name, Tier: "system"})
	}
	writeJSON(w, http.StatusOK, internalOntologyKinds{Source: "user_standards", Kinds: out})
}

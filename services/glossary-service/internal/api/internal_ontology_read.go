package api

import (
	"context"
	"encoding/json"
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
	// KG-ML M5 (C4 / DD4) — localized kind labels {language: label}. Empty/omitted
	// ⇒ the consumer falls back to the canonical `Name`. Inherits the tier's scope.
	NameI18n map[string]string `json:"name_i18n,omitempty"`
}

// loadKindNameI18n runs a `(code, name_i18n)` query and returns code → label map.
// JSONB is scanned as []byte then unmarshalled (the pgx-portable path) so a NULL /
// malformed value degrades to an empty map rather than failing the read. Used to
// attach localized labels to the internal ontology reads without disturbing the
// public kinds-CRUD load path.
func (s *Server) loadKindNameI18n(ctx context.Context, query string, args ...any) (map[string]map[string]string, error) {
	rows, err := s.pool.Query(ctx, query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := make(map[string]map[string]string)
	for rows.Next() {
		var code string
		var raw []byte
		if err := rows.Scan(&code, &raw); err != nil {
			return nil, err
		}
		labels := map[string]string{}
		if len(raw) > 0 {
			_ = json.Unmarshal(raw, &labels) // malformed → empty, never fatal
		}
		if len(labels) > 0 {
			out[code] = labels
		}
	}
	return out, rows.Err()
}

// mergeLabels overlays override onto base (override wins per-language) — the
// tier-merge for name_i18n: System defaults shadowed by the higher tier's own
// labels, BY language. Either may be nil/empty; returns nil when the result is
// empty so the `omitempty` JSON tag drops it (consumer falls back to canonical).
func mergeLabels(base, override map[string]string) map[string]string {
	if len(base) == 0 && len(override) == 0 {
		return nil
	}
	out := make(map[string]string, len(base)+len(override))
	for k, v := range base {
		out[k] = v
	}
	for k, v := range override {
		out[k] = v
	}
	return out
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
	// KG-ML M5 (C4) — localized book-kind labels (graceful: nil map if the column
	// is absent on an un-migrated DB, so the adopt-gate read never breaks). Per the
	// LOCKED tier-merge (CLAUDE.md › User Boundaries): System defaults → Per-book,
	// higher shadows lower BY CODE. A book kind therefore INHERITS the System vi
	// label (admin-seeded in C4) unless the book authored its own override — so a
	// book-bound KG project localizes kinds even though per-book label authoring is
	// deferred. Merge per-language (book wins).
	sysI18n, _ := s.loadKindNameI18n(r.Context(), `SELECT code, name_i18n FROM system_kinds`)
	bookI18n, _ := s.loadKindNameI18n(r.Context(),
		`SELECT code, name_i18n FROM book_kinds WHERE book_id = $1`, bookID)
	kinds := make([]internalOntologyKind, 0, len(ont.Kinds))
	for _, k := range ont.Kinds {
		kinds = append(kinds, internalOntologyKind{
			Code: k.Code, Name: k.Name, Tier: "book",
			NameI18n: mergeLabels(sysI18n[k.Code], bookI18n[k.Code]),
		})
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

	// KG-ML M5 (C4) — attach localized labels per tier (graceful: a nil map on an
	// un-migrated DB just yields no labels, never a 500). A System row's vi label is
	// admin-seeded; a per-user row carries its owner's (deferred authoring, so empty
	// today). Resolution stays tier-correct: a user kind shadows by code AND label.
	sysI18n, _ := s.loadKindNameI18n(r.Context(), `SELECT code, name_i18n FROM system_kinds`)
	userI18n, _ := s.loadKindNameI18n(r.Context(),
		`SELECT code, name_i18n FROM user_kinds
		 WHERE owner_user_id = $1 AND is_active = true
		   AND deleted_at IS NULL AND permanently_deleted_at IS NULL`, userID)
	for i := range out {
		if out[i].Tier == "user" {
			// A user kind shadowing a System code inherits the System vi label
			// unless it authored its own (tier-merge: System default ⊕ user
			// override). A brand-new per-user code just gets its own (empty today).
			out[i].NameI18n = mergeLabels(sysI18n[out[i].Code], userI18n[out[i].Code])
		} else {
			out[i].NameI18n = sysI18n[out[i].Code]
		}
	}
	writeJSON(w, http.StatusOK, internalOntologyKinds{Source: "user_standards", Kinds: out})
}

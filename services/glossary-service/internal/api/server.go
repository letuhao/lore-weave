package api

import (
	"encoding/json"
	"fmt"
	"net/http"
	"strings"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
	"github.com/golang-jwt/jwt/v5"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/glossary-service/internal/config"
)

// Server holds shared dependencies for all handlers.
type Server struct {
	pool   *pgxpool.Pool
	cfg    *config.Config
	secret []byte
}

func NewServer(pool *pgxpool.Pool, cfg *config.Config) *Server {
	return &Server{pool: pool, cfg: cfg, secret: []byte(cfg.JWTSecret)}
}

func (s *Server) Router() http.Handler {
	r := chi.NewRouter()
	r.Use(middleware.RequestID)
	r.Use(middleware.RealIP)
	r.Use(middleware.Recoverer)

	r.Get("/health", func(w http.ResponseWriter, r *http.Request) {
		if s.pool != nil {
			if err := s.pool.Ping(r.Context()); err != nil {
				w.WriteHeader(http.StatusServiceUnavailable)
				_, _ = w.Write([]byte("db ping failed"))
				return
			}
		}
		_, _ = w.Write([]byte("ok"))
	})
	r.Get("/health/ready", func(w http.ResponseWriter, r *http.Request) {
		if s.pool == nil {
			writeJSON(w, http.StatusServiceUnavailable, map[string]string{"status": "not ready", "error": "no db pool"})
			return
		}
		var n int
		if err := s.pool.QueryRow(r.Context(), "SELECT 1").Scan(&n); err != nil {
			w.WriteHeader(http.StatusServiceUnavailable)
			writeJSON(w, http.StatusServiceUnavailable, map[string]string{"status": "not ready", "error": err.Error()})
			return
		}
		writeJSON(w, http.StatusOK, map[string]string{"status": "ready"})
	})

	// ── Internal service-to-service endpoints ─────────────────────────────
	r.Route("/internal", func(r chi.Router) {
		r.Use(s.requireInternalToken)
		r.Get("/books/{book_id}/translation-glossary", s.internalTranslationGlossary)
		r.Get("/books/{book_id}/extraction-profile", s.internalExtractionProfile)
		r.Get("/books/{book_id}/known-entities", s.getKnownEntities)
	})

	r.Route("/v1/glossary", func(r chi.Router) {
		r.Get("/kinds", s.listKinds)
		r.Post("/kinds", s.createKind)
		r.Patch("/kinds/reorder", s.reorderKinds)
		r.Route("/kinds/{kind_id}", func(r chi.Router) {
			r.Patch("/", s.patchKind)
			r.Delete("/", s.deleteKind)
			r.Post("/attributes", s.createAttrDef)
			r.Patch("/attributes/reorder", s.reorderAttrDefs)
			r.Route("/attributes/{attr_def_id}", func(r chi.Router) {
				r.Patch("/", s.patchAttrDef)
				r.Delete("/", s.deleteAttrDef)
			})
		})

		r.Route("/books/{book_id}", func(r chi.Router) {
			r.Get("/extraction-profile", s.getExtractionProfile)
			r.Get("/export", s.exportGlossary)
			r.Route("/genres", func(r chi.Router) {
				r.Get("/", s.listGenres)
				r.Post("/", s.createGenre)
				r.Route("/{genre_id}", func(r chi.Router) {
					r.Patch("/", s.patchGenre)
					r.Delete("/", s.deleteGenre)
				})
			})
			r.Route("/recycle-bin", func(r chi.Router) {
				r.Get("/", s.listEntityTrash)
				r.Post("/{entity_id}/restore", s.restoreEntity)
				r.Delete("/{entity_id}", s.purgeEntity)
			})
			r.Route("/wiki", func(r chi.Router) {
				r.Get("/", s.listWikiArticles)
				r.Post("/", s.createWikiArticle)
				r.Post("/generate", s.generateWikiStubs)
				r.Get("/suggestions", s.listWikiSuggestions)
				r.Get("/public", s.publicListWikiArticles)
				r.Get("/public/{article_id}", s.publicGetWikiArticle)
				r.Route("/{article_id}", func(r chi.Router) {
					r.Get("/", s.getWikiArticle)
					r.Patch("/", s.patchWikiArticle)
					r.Delete("/", s.deleteWikiArticle)
					r.Post("/suggestions", s.submitWikiSuggestion)
					r.Route("/suggestions/{sug_id}", func(r chi.Router) {
						r.Patch("/", s.reviewWikiSuggestion)
					})
					r.Route("/revisions", func(r chi.Router) {
						r.Get("/", s.listWikiRevisions)
						r.Route("/{rev_id}", func(r chi.Router) {
							r.Get("/", s.getWikiRevision)
							r.Post("/restore", s.restoreWikiRevision)
						})
					})
				})
			})
			r.Get("/entity-names", s.listEntityNames)
			r.Route("/entities", func(r chi.Router) {
				r.Get("/", s.listEntities)
				r.Post("/", s.createEntity)
				r.Route("/{entity_id}", func(r chi.Router) {
					r.Get("/", s.getEntityDetail)
					r.Patch("/", s.patchEntity)
					r.Delete("/", s.deleteEntity)
					r.Route("/chapter-links", func(r chi.Router) {
						r.Get("/", s.listChapterLinks)
						r.Post("/", s.createChapterLink)
						r.Route("/{link_id}", func(r chi.Router) {
							r.Patch("/", s.updateChapterLink)
							r.Delete("/", s.deleteChapterLink)
						})
					})
					r.Route("/attributes/{attr_value_id}", func(r chi.Router) {
						r.Patch("/", s.patchAttributeValue)
						r.Route("/translations", func(r chi.Router) {
							r.Post("/", s.createTranslation)
							r.Route("/{translation_id}", func(r chi.Router) {
								r.Patch("/", s.updateTranslation)
								r.Delete("/", s.deleteTranslation)
							})
						})
						r.Route("/evidences", func(r chi.Router) {
							r.Post("/", s.createEvidence)
							r.Route("/{evidence_id}", func(r chi.Router) {
								r.Patch("/", s.updateEvidence)
								r.Delete("/", s.deleteEvidence)
							})
						})
					})
				})
			})
		})
	})

	return r
}

// ── helpers ──────────────────────────────────────────────────────────────────

type errorBody struct {
	Code    string `json:"code"`
	Message string `json:"message"`
}

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}

func writeError(w http.ResponseWriter, status int, code, message string) {
	writeJSON(w, status, errorBody{Code: code, Message: message})
}

// ── auth ─────────────────────────────────────────────────────────────────────

type accessClaims struct {
	jwt.RegisteredClaims
}

// requireUserID extracts and validates the Bearer JWT, returning the user UUID.
func (s *Server) requireUserID(r *http.Request) (uuid.UUID, bool) {
	auth := r.Header.Get("Authorization")
	if !strings.HasPrefix(auth, "Bearer ") {
		return uuid.Nil, false
	}
	tokenStr := strings.TrimPrefix(auth, "Bearer ")
	tok, err := jwt.ParseWithClaims(tokenStr, &accessClaims{}, func(t *jwt.Token) (any, error) {
		if t.Method != jwt.SigningMethodHS256 {
			return nil, fmt.Errorf("unexpected signing method")
		}
		return s.secret, nil
	})
	if err != nil || !tok.Valid {
		return uuid.Nil, false
	}
	claims, ok := tok.Claims.(*accessClaims)
	if !ok {
		return uuid.Nil, false
	}
	id, err := uuid.Parse(claims.Subject)
	if err != nil {
		return uuid.Nil, false
	}
	return id, true
}

// requireInternalToken validates the X-Internal-Token header for service-to-service calls.
func (s *Server) requireInternalToken(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if s.cfg.InternalServiceToken != "" && r.Header.Get("X-Internal-Token") != s.cfg.InternalServiceToken {
			writeJSON(w, http.StatusUnauthorized, map[string]string{"error": "invalid internal token"})
			return
		}
		next.ServeHTTP(w, r)
	})
}

// ── internal endpoints ────────────────────────────────────────────────────

// internalTranslationGlossary returns a compact glossary for translation prompts.
//
//	GET /internal/books/{book_id}/translation-glossary
//	Query: target_language (required), chapter_id (optional), max_entries (optional, default 50)
//
// Returns array of: {"zh":["name1","alias"],"vi":["translation"],"kind":"character"}
func (s *Server) internalTranslationGlossary(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	targetLang := r.URL.Query().Get("target_language")
	if targetLang == "" {
		writeError(w, http.StatusBadRequest, "GLOSS_BAD_REQUEST", "target_language query param required")
		return
	}
	chapterIDStr := r.URL.Query().Get("chapter_id")
	maxEntries := 50
	if v := r.URL.Query().Get("max_entries"); v != "" {
		if n, err := fmt.Sscanf(v, "%d", &maxEntries); n != 1 || err != nil || maxEntries < 1 {
			maxEntries = 50
		}
		if maxEntries > 200 {
			maxEntries = 200
		}
	}

	ctx := r.Context()

	// Build query: fetch entities with original name + target translation + kind code.
	// If chapter_id given, prioritize chapter-linked entities (Tier 1),
	// then fill remaining budget with most-linked entities across book (Tier 0).
	//
	// Strategy: UNION of chapter-linked + globally-popular, deduped, limited.
	var query string
	var args []any

	if chapterIDStr != "" {
		chapterID, err := uuid.Parse(chapterIDStr)
		if err != nil {
			writeError(w, http.StatusBadRequest, "GLOSS_BAD_REQUEST", "invalid chapter_id")
			return
		}
		// Tier 1 (chapter-linked) + Tier 0 (most-linked) + Tier 2 (all active), deduped
		query = `
WITH chapter_entities AS (
    -- Tier 1: entities linked to this chapter
    SELECT e.entity_id, 1 AS tier
    FROM glossary_entities e
    JOIN chapter_entity_links cel ON cel.entity_id = e.entity_id AND cel.chapter_id = $3
    WHERE e.book_id = $1 AND e.status = 'active' AND e.deleted_at IS NULL
),
popular_entities AS (
    -- Tier 0: most-linked entities in the book (pinned)
    SELECT e.entity_id, 0 AS tier
    FROM glossary_entities e
    JOIN chapter_entity_links cel ON cel.entity_id = e.entity_id
    WHERE e.book_id = $1 AND e.status = 'active' AND e.deleted_at IS NULL
    GROUP BY e.entity_id
    ORDER BY COUNT(*) DESC
    LIMIT $4
),
fallback_entities AS (
    -- Tier 2: all active entities (fallback when no chapter links exist)
    SELECT e.entity_id, 2 AS tier
    FROM glossary_entities e
    WHERE e.book_id = $1 AND e.status = 'active' AND e.deleted_at IS NULL
    LIMIT $4
),
all_entities AS (
    SELECT entity_id, MIN(tier) AS best_tier FROM (
        SELECT * FROM chapter_entities
        UNION ALL
        SELECT * FROM popular_entities
        UNION ALL
        SELECT * FROM fallback_entities
    ) combined GROUP BY entity_id
)
SELECT
    eav.original_value AS name_zh,
    COALESCE(at.value, '') AS name_target,
    ek.code AS kind_code,
    ae.best_tier
FROM all_entities ae
JOIN glossary_entities e ON e.entity_id = ae.entity_id
JOIN entity_kinds ek ON ek.kind_id = e.kind_id
LEFT JOIN entity_attribute_values eav ON eav.entity_id = e.entity_id
    AND eav.attr_def_id = (
        SELECT attr_def_id FROM attribute_definitions
        WHERE kind_id = e.kind_id AND code = 'name' LIMIT 1
    )
LEFT JOIN attribute_translations at ON at.attr_value_id = eav.attr_value_id
    AND at.language_code = $2
WHERE eav.original_value IS NOT NULL AND eav.original_value != ''
ORDER BY ae.best_tier ASC, length(eav.original_value) DESC
LIMIT $4`
		args = []any{bookID, targetLang, chapterID, maxEntries}
	} else {
		// No chapter scoping — return most-linked entities across the book
		query = `
SELECT
    eav.original_value AS name_zh,
    COALESCE(at.value, '') AS name_target,
    ek.code AS kind_code,
    0 AS best_tier
FROM glossary_entities e
JOIN entity_kinds ek ON ek.kind_id = e.kind_id
LEFT JOIN entity_attribute_values eav ON eav.entity_id = e.entity_id
    AND eav.attr_def_id = (
        SELECT attr_def_id FROM attribute_definitions
        WHERE kind_id = e.kind_id AND code = 'name' LIMIT 1
    )
LEFT JOIN attribute_translations at ON at.attr_value_id = eav.attr_value_id
    AND at.language_code = $2
LEFT JOIN chapter_entity_links cel ON cel.entity_id = e.entity_id
WHERE e.book_id = $1 AND e.status = 'active' AND e.deleted_at IS NULL
    AND eav.original_value IS NOT NULL AND eav.original_value != ''
GROUP BY e.entity_id, eav.original_value, at.value, ek.code
ORDER BY COUNT(cel.link_id) DESC, length(eav.original_value) DESC
LIMIT $3`
		args = []any{bookID, targetLang, maxEntries}
	}

	rows, err := s.pool.Query(ctx, query, args...)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "query failed")
		return
	}
	defer rows.Close()

	type glossaryEntry struct {
		ZH   []string `json:"zh"`
		Tgt  []string `json:"tgt,omitempty"`
		Kind string   `json:"kind"`
	}

	items := make([]map[string]any, 0, maxEntries)
	for rows.Next() {
		var nameZH, nameTarget, kindCode string
		var tier int
		if err := rows.Scan(&nameZH, &nameTarget, &kindCode, &tier); err != nil {
			continue
		}
		entry := map[string]any{
			"zh":   []string{nameZH},
			"kind": kindCode,
		}
		if nameTarget != "" {
			entry[targetLang] = []string{nameTarget}
		}
		items = append(items, entry)
	}
	if err := rows.Err(); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "row iteration failed")
		return
	}

	writeJSON(w, http.StatusOK, items)
}

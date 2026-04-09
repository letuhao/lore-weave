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
				r.Route("/{article_id}", func(r chi.Router) {
					r.Get("/", s.getWikiArticle)
					r.Patch("/", s.patchWikiArticle)
					r.Delete("/", s.deleteWikiArticle)
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

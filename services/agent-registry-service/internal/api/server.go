package api

import (
	"context"
	"crypto/aes"
	"crypto/cipher"
	"crypto/rand"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
	"github.com/golang-jwt/jwt/v5"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"

	"github.com/loreweave/agent-registry-service/internal/config"
	"github.com/loreweave/grantclient"
	"github.com/loreweave/observability"
)

// PgxDB is the subset of *pgxpool.Pool the server uses, so unit tests can inject
// a pgxmock pool (go-db-mock-harness pattern).
type PgxDB interface {
	Exec(ctx context.Context, sql string, args ...any) (pgconn.CommandTag, error)
	Query(ctx context.Context, sql string, args ...any) (pgx.Rows, error)
	QueryRow(ctx context.Context, sql string, args ...any) pgx.Row
	Begin(ctx context.Context) (pgx.Tx, error)
	Ping(ctx context.Context) error
}

type Server struct {
	db        PgxDB
	cfg       *config.Config
	jwtSecret []byte
	vaultKey  []byte // 32 bytes for AES-256-GCM
	// grants resolves E0 book grants for book-tier writes (D-REG-BOOK-GRANT).
	// nil when BOOK_SERVICE_INTERNAL_URL is unset → book-tier writes 501.
	grants *grantclient.Client
}

// NewServer constructs the HTTP server. db may be nil for router-only tests;
// handlers return 503 when a DB op is attempted against a nil pool.
func NewServer(db PgxDB, cfg *config.Config) *Server {
	s := &Server{
		db:        db,
		cfg:       cfg,
		jwtSecret: []byte(cfg.JWTSecret),
		vaultKey:  deriveKey(cfg.VaultKey),
	}
	if cfg.BookServiceInternalURL != "" {
		if gc, err := grantclient.NewClient(grantclient.Options{
			BaseURL:       cfg.BookServiceInternalURL,
			InternalToken: cfg.InternalServiceToken,
		}); err == nil {
			s.grants = gc
		}
	}
	return s
}

// requireBookGrant gates a book-tier write on the caller holding ≥edit on the
// book (E0). Fail-closed: no grant client → 501; forbidden → 404 (anti-oracle —
// a book the user can't touch is indistinguishable from absent); authority
// unavailable → 503. Returns true when the caller may proceed.
func (s *Server) requireBookGrant(w http.ResponseWriter, r *http.Request, bookID, uid uuid.UUID) bool {
	if s.grants == nil {
		writeError(w, http.StatusNotImplemented, "NOT_IMPLEMENTED", "book-tier requires BOOK_SERVICE_INTERNAL_URL (grant wiring)")
		return false
	}
	if bookID == uuid.Nil {
		writeError(w, http.StatusBadRequest, "VALIDATION_ERROR", "book_id required for book tier")
		return false
	}
	// Resolve grant + lifecycle together: a write must have >=edit AND the book
	// must be active. /review-impl: gating on grant level alone let a user with
	// edit on a TRASHED/purge_pending book create book-tier resources on a book
	// being deleted (the grantclient SDK: "Edit/manage operations should gate on
	// Active()").
	acc, err := s.grants.ResolveAccess(r.Context(), bookID, uid)
	if err != nil { // ErrUnavailable — fail closed
		writeError(w, http.StatusServiceUnavailable, "GRANT_UNAVAILABLE", "grant authority unavailable")
		return false
	}
	if !acc.Level.AtLeast(grantclient.GrantEdit) {
		writeError(w, http.StatusNotFound, "NOT_FOUND", "book not found") // anti-oracle
		return false
	}
	if !acc.Active() {
		writeError(w, http.StatusConflict, "BOOK_NOT_ACTIVE", "book is not active (trashed or pending purge)")
		return false
	}
	return true
}

// authorizeRowWrite decides whether the caller may mutate/inspect a loaded row by
// tier: user → own; system → admin; book → ≥edit grant on an ACTIVE book. The book
// path resolves the grant per request (fail-closed). Used by get/patch/delete so a
// book-tier resource is manageable by the book's grantees (its rows carry no owner).
func (s *Server) authorizeRowWrite(r *http.Request, tier string, owner, book *uuid.UUID, uid uuid.UUID, role string) bool {
	switch tier {
	case "user":
		return owner != nil && *owner == uid
	case "system":
		return role == "admin"
	case "book":
		if s.grants == nil || book == nil {
			return false
		}
		acc, err := s.grants.ResolveAccess(r.Context(), *book, uid)
		return err == nil && acc.Level.AtLeast(grantclient.GrantEdit) && acc.Active()
	}
	return false
}

func deriveKey(s string) []byte {
	key := []byte(s)
	if len(key) >= 32 {
		return key[:32]
	}
	padded := make([]byte, 32)
	copy(padded, key)
	return padded
}

func (s *Server) Router() http.Handler {
	r := chi.NewRouter()
	r.Use(middleware.RequestID)
	r.Use(middleware.RealIP)
	r.Use(observability.ChiMiddleware())
	r.Use(middleware.Recoverer)

	r.Method(http.MethodGet, "/metrics", metricsHandler())

	r.Get("/health", func(w http.ResponseWriter, r *http.Request) {
		if s.db != nil {
			if err := s.db.Ping(r.Context()); err != nil {
				w.WriteHeader(http.StatusServiceUnavailable)
				_, _ = w.Write([]byte("db ping failed"))
				return
			}
		}
		_, _ = w.Write([]byte("ok"))
	})
	r.Get("/health/ready", func(w http.ResponseWriter, r *http.Request) {
		if s.db == nil {
			writeJSON(w, http.StatusServiceUnavailable, map[string]string{"status": "not ready", "error": "no db pool"})
			return
		}
		var n int
		if err := s.db.QueryRow(r.Context(), "SELECT 1").Scan(&n); err != nil {
			writeJSON(w, http.StatusServiceUnavailable, map[string]string{"status": "not ready", "error": err.Error()})
			return
		}
		writeJSON(w, http.StatusOK, map[string]string{"status": "ready"})
	})

	// Public API — JWT-gated; owner derived from the token, never the body.
	r.Route("/v1/agent-registry", func(r chi.Router) {
		r.Get("/plugins", s.listPlugins)
		r.Post("/plugins", s.createPlugin)
		r.Get("/plugins/{plugin_id}", s.getPlugin)
		r.Patch("/plugins/{plugin_id}", s.patchPlugin)
		r.Delete("/plugins/{plugin_id}", s.deletePlugin)
		r.Get("/plugins/{plugin_id}/cascade-preview", s.cascadePreview)
		r.Put("/plugins/{plugin_id}/enablement", s.putEnablement)

		// Skills (P1, prompt-only)
		r.Get("/skills", s.listSkills)
		r.Post("/skills", s.createSkill)
		r.Post("/skills/import", s.importSkill)
		r.Get("/skills/shadow-check", s.shadowCheck)
		r.Get("/skills/{skill_id}", s.getSkill)
		r.Patch("/skills/{skill_id}", s.patchSkill)
		r.Delete("/skills/{skill_id}", s.deleteSkill)
		r.Get("/skills/{skill_id}/export", s.exportSkill)
		r.Get("/skills/{skill_id}/revisions", s.listSkillRevisions)
		r.Put("/skills/{skill_id}/enablement", s.setSkillEnabled)

		// Proposals (P1 agent self-registration — propose→approve/reject)
		r.Get("/proposals", s.listProposals)
		r.Get("/proposals/{proposal_id}", s.getProposal)
		r.Put("/proposals/{proposal_id}/approve", s.approveProposal)
		r.Post("/proposals/{proposal_id}/reject", s.rejectProposal)

		r.Get("/usage", s.getUsage)
		r.Get("/audit", s.listAudit)
	})

	// Agent-facing MCP server (spec §12b) — federated through ai-gateway with the
	// "registry_" prefix. Identity from the envelope (X-User-Id), never a tool arg.
	r.Handle("/mcp", s.mcpHandler())
	r.Handle("/mcp/*", s.mcpHandler())

	// Internal API — X-Internal-Token gated; consumers (ai-gateway, chat) pass user_id.
	r.Route("/internal", func(r chi.Router) {
		r.Use(s.requireInternalToken)
		r.Get("/effective-catalog", s.effectiveCatalog)
		r.Get("/skills", s.internalSkills)
	})

	return r
}

func (s *Server) requireInternalToken(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if s.cfg.InternalServiceToken != "" && r.Header.Get("X-Internal-Token") != s.cfg.InternalServiceToken {
			writeError(w, http.StatusUnauthorized, "INTERNAL_UNAUTHORIZED", "invalid internal token")
			return
		}
		next.ServeHTTP(w, r)
	})
}

// ── auth ──────────────────────────────────────────────────────────────────

type accessClaims struct {
	jwt.RegisteredClaims
	Role string `json:"role,omitempty"`
}

// authUser parses the user JWT (HS256) and returns (user_id, role). ok=false
// on any failure; the caller responds 401.
func (s *Server) authUser(r *http.Request) (uuid.UUID, string, bool) {
	authz := r.Header.Get("Authorization")
	if !strings.HasPrefix(authz, "Bearer ") {
		return uuid.Nil, "", false
	}
	tok, err := jwt.ParseWithClaims(strings.TrimPrefix(authz, "Bearer "), &accessClaims{}, func(t *jwt.Token) (any, error) {
		if t.Method != jwt.SigningMethodHS256 {
			return nil, fmt.Errorf("unexpected signing method")
		}
		return s.jwtSecret, nil
	})
	if err != nil || !tok.Valid {
		return uuid.Nil, "", false
	}
	claims, ok := tok.Claims.(*accessClaims)
	if !ok {
		return uuid.Nil, "", false
	}
	id, err := uuid.Parse(claims.Subject)
	if err != nil {
		return uuid.Nil, "", false
	}
	return id, claims.Role, true
}

// requireUser is the common preamble for JWT routes.
func (s *Server) requireUser(w http.ResponseWriter, r *http.Request) (uuid.UUID, string, bool) {
	uid, role, ok := s.authUser(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "UNAUTHORIZED", "missing or invalid token")
		return uuid.Nil, "", false
	}
	if s.db == nil {
		writeError(w, http.StatusServiceUnavailable, "NO_DB", "database unavailable")
		return uuid.Nil, "", false
	}
	return uid, role, true
}

// ── AES-GCM vault (DECISION-1 — used from P3 for MCP secrets) ───────────────

func (s *Server) encryptSecret(raw string) (ciphertext, keyRef string, err error) {
	block, err := aes.NewCipher(s.vaultKey)
	if err != nil {
		return "", "", err
	}
	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return "", "", err
	}
	nonce := make([]byte, gcm.NonceSize())
	if _, err := rand.Read(nonce); err != nil {
		return "", "", err
	}
	sealed := gcm.Seal(nil, nonce, []byte(raw), nil)
	return base64.StdEncoding.EncodeToString(append(nonce, sealed...)), uuid.NewString(), nil
}

func (s *Server) decryptSecret(ciphertext string) (string, error) {
	if ciphertext == "" {
		return "", nil
	}
	block, err := aes.NewCipher(s.vaultKey)
	if err != nil {
		return "", err
	}
	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return "", err
	}
	joined, err := base64.StdEncoding.DecodeString(ciphertext)
	if err != nil {
		return "", err
	}
	if len(joined) < gcm.NonceSize() {
		return "", fmt.Errorf("invalid ciphertext")
	}
	plain, err := gcm.Open(nil, joined[:gcm.NonceSize()], joined[gcm.NonceSize():], nil)
	if err != nil {
		return "", err
	}
	return string(plain), nil
}

// ── audit + catalog-version helpers ─────────────────────────────────────────

func (s *Server) audit(ctx context.Context, actor uuid.UUID, actorKind, kind, action string, targetID *uuid.UUID, targetName, tier string, detail map[string]any) {
	if s.db == nil {
		return
	}
	det, _ := json.Marshal(detail)
	if det == nil {
		det = []byte("{}")
	}
	var actorArg any
	if actor != uuid.Nil {
		actorArg = actor
	}
	_, _ = s.db.Exec(ctx,
		`INSERT INTO registry_audit (actor_user_id, actor_kind, kind, action, target_id, target_name, tier, detail)
		 VALUES ($1,$2,$3,$4,$5,$6,$7,$8)`,
		actorArg, actorKind, kind, action, targetID, targetName, nullStr(tier), string(det))
}

// bumpCatalogVersion advances the monotonic catalog version (Q-CACHE substrate).
func (s *Server) bumpCatalogVersion(ctx context.Context) {
	if s.db == nil {
		return
	}
	_, _ = s.db.Exec(ctx, `UPDATE registry_meta SET catalog_version = catalog_version + 1 WHERE id = TRUE`)
}

func (s *Server) catalogVersion(ctx context.Context) int64 {
	if s.db == nil {
		return 0
	}
	var v int64
	_ = s.db.QueryRow(ctx, `SELECT catalog_version FROM registry_meta WHERE id = TRUE`).Scan(&v)
	return v
}

// ── small helpers ────────────────────────────────────────────────────────────

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

func parseUUIDParam(w http.ResponseWriter, r *http.Request, name string) (uuid.UUID, bool) {
	id, err := uuid.Parse(chi.URLParam(r, name))
	if err != nil {
		writeError(w, http.StatusBadRequest, "VALIDATION_ERROR", "invalid "+name)
		return uuid.Nil, false
	}
	return id, true
}

func decodeJSON(w http.ResponseWriter, r *http.Request, dst any) bool {
	if err := json.NewDecoder(r.Body).Decode(dst); err != nil {
		writeError(w, http.StatusBadRequest, "VALIDATION_ERROR", "invalid JSON body")
		return false
	}
	return true
}

// nullStr maps "" → SQL NULL so a NULLable text column stays NULL not empty.
func nullStr(s string) any {
	if s == "" {
		return nil
	}
	return s
}

// queryInt runs a scalar COUNT/int query, returning 0 on error.
func (s *Server) queryInt(ctx context.Context, sql string, args ...any) int {
	var n int
	_ = s.db.QueryRow(ctx, sql, args...).Scan(&n)
	return n
}

func atoiDefault(s string, def int) int {
	if s == "" {
		return def
	}
	n, err := strconv.Atoi(s)
	if err != nil {
		return def
	}
	return n
}

// clampLimit bounds a page size to [1,100] with a default of 20.
func clampLimit(raw string) int {
	n := atoiDefault(raw, 20)
	if n < 1 {
		return 20
	}
	if n > 100 {
		return 100
	}
	return n
}

var _ = time.Now // reserved for later phases

package api

import (
	"context"
	"crypto/aes"
	"crypto/cipher"
	"crypto/rand"
	"crypto/rsa"
	"crypto/subtle"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"slices"
	"strconv"
	"strings"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"

	"github.com/loreweave/agent-registry-service/internal/config"
	"github.com/loreweave/foundation/contracts/adminjwt"
	"github.com/loreweave/foundation/contracts/platformjwt"
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
	// adminPub verifies RS256 admin JWTs for the System-tier write paths + the
	// admin-only ingest routes (D-JWT-ROLE-GATE, contracts/adminjwt). nil when
	// ADMIN_JWT_PUBLIC_KEY_PEM is unset → those paths fail closed (503).
	// adminKID = KeyFingerprint(adminPub).
	adminPub *rsa.PublicKey
	adminKID string
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
	if raw := strings.TrimSpace(cfg.AdminJWTPublicKeyPEM); raw != "" {
		if pub, err := adminjwt.ParseRSAPublicKeyPEM(pemOrBase64(raw)); err != nil {
			// Misconfigured key → leave admin disabled (fail closed) + log loudly.
			slog.Error("agent-registry: ADMIN_JWT_PUBLIC_KEY_PEM parse failed; System-tier + ingest admin paths DISABLED", "err", err)
		} else if kid, err := adminjwt.KeyFingerprint(pub); err != nil {
			slog.Error("agent-registry: admin key fingerprint failed; System-tier + ingest admin paths DISABLED", "err", err)
		} else {
			s.adminPub = pub
			s.adminKID = kid
			slog.Info("agent-registry: System-tier + ingest admin paths ENABLED", "kid", kid)
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
// tier: user → own; system → RS256 admin token (admin:write); book → ≥edit grant on
// an ACTIVE book. The book path resolves the grant per request (fail-closed). Used by
// get/patch/delete so a book-tier resource is manageable by the book's grantees (its
// rows carry no owner).
//
// D-JWT-ROLE-GATE: the System-tier branch delegates to requireAdminScope, which WRITES
// its own error (401/403/503) and returns ok. So a caller must NOT write an anti-oracle
// 404 for a System-tier row (requireAdminScope already responded) — only for the
// user/book branches, which return false WITHOUT writing. See the caller pattern
// `if !ok { if tier != "system" { writeError(404) }; return }`.
func (s *Server) authorizeRowWrite(w http.ResponseWriter, r *http.Request, tier string, owner, book *uuid.UUID, uid uuid.UUID) bool {
	switch tier {
	case "user":
		return owner != nil && *owner == uid
	case "system":
		_, ok := s.requireAdminScope(w, r, scopeAdminWrite)
		return ok
	case "book":
		if s.grants == nil || book == nil {
			return false
		}
		acc, err := s.grants.ResolveAccess(r.Context(), *book, uid)
		return err == nil && acc.Level.AtLeast(grantclient.GrantEdit) && acc.Active()
	}
	return false
}

// resolveListBookScope validates an optional `book_id` query param on a LIST request.
// Returns (bookID, true) — bookID=uuid.Nil when no scope was requested; a validated
// book UUID when the caller holds ≥edit on it (so its book-tier rows may be listed).
// A malformed id → 400; an unknown/ungranted book → 404 (anti-oracle) with ok=false
// (the handler must return). This lets the Extensions UI surface a book's book-tier
// skills/commands/hooks/subagents/servers for management, grant-gated.
func (s *Server) resolveListBookScope(w http.ResponseWriter, r *http.Request, uid uuid.UUID) (uuid.UUID, bool) {
	v := r.URL.Query().Get("book_id")
	if v == "" {
		return uuid.Nil, true
	}
	bid, err := uuid.Parse(v)
	if err != nil {
		writeError(w, http.StatusBadRequest, "VALIDATION_ERROR", "invalid book_id")
		return uuid.Nil, false
	}
	if s.grants == nil {
		writeError(w, http.StatusNotFound, "NOT_FOUND", "book not found")
		return uuid.Nil, false
	}
	acc, err := s.grants.ResolveAccess(r.Context(), bid, uid)
	if err != nil || !acc.Level.AtLeast(grantclient.GrantEdit) {
		writeError(w, http.StatusNotFound, "NOT_FOUND", "book not found") // anti-oracle
		return uuid.Nil, false
	}
	return bid, true
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
		r.Post("/plugins/import", s.importBundle)              // P5 bundle import
		r.Get("/plugins/{plugin_id}/export", s.exportBundle)   // P5 bundle export

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

		// MCP server registrations (P2 — internal-only; external+security = P3)
		r.Get("/mcp-servers", s.listMcpServers)
		r.Post("/mcp-servers", s.createMcpServer)
		r.Get("/mcp-servers/{mcp_server_id}", s.getMcpServer)                     // P3 detail
		r.Delete("/mcp-servers/{mcp_server_id}", s.deleteMcpServer)
		r.Put("/mcp-servers/{mcp_server_id}/enablement", s.setMcpEnabled)
		r.Post("/mcp-servers/{mcp_server_id}/rescan", s.rescanMcpServer)          // P3 supply-chain scan
		r.Post("/mcp-servers/{mcp_server_id}/accept-risk", s.acceptRiskMcpServer) // P3 quarantine override
		r.Post("/mcp-servers/{mcp_server_id}/oauth/start", s.startOAuth)         // P3 OAuth 2.1 + PKCE
		r.Get("/oauth/callback", s.oauthCallback)                                // P3 OAuth callback (PUBLIC — AS redirect)

		// Slash commands (P4)
		r.Get("/commands", s.listCommands)
		r.Post("/commands", s.createCommand)
		r.Patch("/commands/{command_id}", s.patchCommand)
		r.Delete("/commands/{command_id}", s.deleteCommand)

		// Declarative hooks (P4)
		r.Get("/hooks", s.listHooks)
		r.Post("/hooks", s.createHook)
		r.Patch("/hooks/{hook_id}", s.patchHook)
		r.Delete("/hooks/{hook_id}", s.deleteHook)

		// Subagent definitions (P5)
		r.Get("/subagents", s.listSubagents)
		r.Post("/subagents", s.createSubagent)
		r.Patch("/subagents/{subagent_id}", s.patchSubagent)
		r.Delete("/subagents/{subagent_id}", s.deleteSubagent)

		// Official MCP Registry ingest — admin-only curation (P5 REG-P5-03).
		r.Post("/admin/ingest/pull", s.ingestPull)
		r.Get("/admin/ingest/queue", s.listIngestQueue)
		r.Post("/admin/ingest/queue/{ingest_id}/approve", s.approveIngest)
		r.Post("/admin/ingest/queue/{ingest_id}/reject", s.rejectIngest)

		// Proposals (P1 agent self-registration — propose→approve/reject)
		r.Get("/proposals", s.listProposals)
		r.Get("/proposals/{proposal_id}", s.getProposal)
		r.Put("/proposals/{proposal_id}/approve", s.approveProposal)
		r.Post("/proposals/{proposal_id}/reject", s.rejectProposal)

		// Workflow proposals (WS-2a — same propose→approve/reject HITL spine)
		// Mode → capability binding (WS-3 / C6) — a USER setting (own tier or a book
		// they hold EDIT on); the System tier is seeded + read-only here.
		r.Get("/mode-bindings/{mode}", s.getModeBinding)
		r.Put("/mode-bindings/{mode}", s.putModeBinding)

		// M5 — the FE workflow rack lists a user's visible recipes (System + own + granted book).
		r.Get("/workflows", s.listUserWorkflows)

		r.Get("/workflow-proposals", s.listWorkflowProposals)
		r.Get("/workflow-proposals/{proposal_id}", s.getWorkflowProposal)
		r.Put("/workflow-proposals/{proposal_id}/approve", s.approveWorkflowProposal)
		r.Post("/workflow-proposals/{proposal_id}/reject", s.rejectWorkflowProposal)

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
		r.Get("/workflows", s.internalWorkflows) // WS-2b step-runner source (full defs)
		r.Get("/effective-mcp-servers", s.internalEffectiveMcpServers)              // P2 federation overlay source
		r.Get("/mcp-servers/{mcp_server_id}/credentials", s.internalMcpCredentials) // P3 vault decrypt (egress auth)
		r.Get("/commands", s.internalCommands)                                      // P4 command-expansion resolver
		r.Get("/hooks", s.internalHooks)                                            // P4 hook-engine resolver
		r.Get("/subagents", s.internalSubagents)                                    // P5 subagent resolver
	})

	return r
}

func (s *Server) requireInternalToken(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Fail CLOSED: an empty configured token denies all /internal routes (never
		// fail-open to an unauthenticated secret-decrypt oracle). Constant-time compare
		// to avoid a timing side channel on the shared secret.
		want := s.cfg.InternalServiceToken
		got := r.Header.Get("X-Internal-Token")
		if want == "" || subtle.ConstantTimeCompare([]byte(got), []byte(want)) != 1 {
			writeError(w, http.StatusUnauthorized, "INTERNAL_UNAUTHORIZED", "invalid internal token")
			return
		}
		next.ServeHTTP(w, r)
	})
}

// ── auth ──────────────────────────────────────────────────────────────────

// authUser verifies the platform-user HS256 JWT via the shared contracts/platformjwt
// verifier and returns the authenticated user id. It NO LONGER returns a role: the
// platform user token never carries one (D-JWT-ROLE-GATE) — admin authority is the
// RS256 admin token's job (see requireAdminScope). ok=false on any failure; the caller
// responds 401.
func (s *Server) authUser(r *http.Request) (uuid.UUID, bool) {
	authz := r.Header.Get("Authorization")
	if !strings.HasPrefix(authz, "Bearer ") {
		return uuid.Nil, false
	}
	claims, err := platformjwt.Verify(strings.TrimPrefix(authz, "Bearer "), s.jwtSecret)
	if err != nil {
		return uuid.Nil, false
	}
	id, err := claims.UserID()
	if err != nil {
		return uuid.Nil, false
	}
	return id, true
}

// requireUser is the common preamble for JWT routes.
func (s *Server) requireUser(w http.ResponseWriter, r *http.Request) (uuid.UUID, bool) {
	uid, ok := s.authUser(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "UNAUTHORIZED", "missing or invalid token")
		return uuid.Nil, false
	}
	if s.db == nil {
		writeError(w, http.StatusServiceUnavailable, "NO_DB", "database unavailable")
		return uuid.Nil, false
	}
	return uid, true
}

// scopeAdminWrite is the admin scope required to mutate System-tier rows + run the
// admin-only ingest routes. Mirrors glossary/provider-registry's System-tier admin gate.
const scopeAdminWrite = "admin:write"

// requireAdminScope verifies the Bearer admin RS256 JWT and that it carries the required
// scope, writing the error + returning false on any failure. System-tier rows are
// platform-owned: only an admin principal (never a regular user) may mutate them
// (CLAUDE.md › User Boundaries). Fail closed when the verify key is unconfigured. A
// regular HS256 user token never satisfies adminjwt.Verify (RS256 only), so this is not
// bypassable with a normal login.
func (s *Server) requireAdminScope(w http.ResponseWriter, r *http.Request, scope string) (adminjwt.AdminClaims, bool) {
	if s.adminPub == nil {
		writeError(w, http.StatusServiceUnavailable, "ADMIN_UNAVAILABLE", "admin administration is not configured")
		return adminjwt.AdminClaims{}, false
	}
	authz := r.Header.Get("Authorization")
	if !strings.HasPrefix(authz, "Bearer ") {
		writeError(w, http.StatusUnauthorized, "ADMIN_UNAUTHORIZED", "valid admin Bearer token required")
		return adminjwt.AdminClaims{}, false
	}
	claims, err := adminjwt.Verify(strings.TrimPrefix(authz, "Bearer "), s.adminPub, s.adminKID)
	if err != nil {
		writeError(w, http.StatusUnauthorized, "ADMIN_UNAUTHORIZED", "invalid admin token")
		return adminjwt.AdminClaims{}, false
	}
	if !slices.Contains(claims.Scopes, scope) {
		writeError(w, http.StatusForbidden, "ADMIN_FORBIDDEN", "missing required admin scope")
		return adminjwt.AdminClaims{}, false
	}
	return claims, true
}

// pemOrBase64 accepts either a raw PEM ("BEGIN") or a base64-encoded PEM (an
// env-var-friendly single line).
func pemOrBase64(v string) []byte {
	if strings.Contains(v, "BEGIN") {
		return []byte(v)
	}
	if dec, err := base64.StdEncoding.DecodeString(strings.TrimSpace(v)); err == nil {
		return dec
	}
	return []byte(v)
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

package api

import (
	"net/http"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/observability"

	"github.com/loreweave/auth-service/internal/config"
	"github.com/loreweave/auth-service/internal/ratelimit"
)

type Server struct {
	pool         *pgxpool.Pool
	cfg          *config.Config
	secret       []byte
	rl           *ratelimit.Limiter
	mcpResolveRL *ratelimit.Limiter // per-prefix Argon2-DoS guard for /internal/mcp-keys/resolve (H-H)
	admin        *adminDeps         // nil => admin-JWT issuance (074/075) disabled
	oauth        *oauthDeps         // nil => P5 public-MCP OAuth endpoints disabled
	// WS-1.0 — the KEK that WRAPS each user's DEK (DIARY_ENCRYPTION_KEY). auth-service
	// only ever wraps; it never sees a user's plaintext content, and it hands out the
	// WRAPPED dek so the plaintext key never crosses the network.
	// Empty => /internal/users/{id}/dek fails CLOSED with 503 rather than letting a
	// deployment quietly store private content unencrypted.
	dekKEK []byte
}

func NewServer(pool *pgxpool.Pool, cfg *config.Config) *Server {
	return &Server{
		pool:         pool,
		cfg:          cfg,
		secret:       []byte(cfg.JWTSecret),
		dekKEK:       deriveKEK(cfg.DiaryEncryptionKey),
		rl:           ratelimit.New(cfg.RateLimitWindow, cfg.RateLimitMax),
		mcpResolveRL: newMcpResolveLimiter(),
	}
}

func (s *Server) Router() http.Handler {
	r := chi.NewRouter()
	r.Use(middleware.RequestID)
	r.Use(middleware.RealIP)
	// Phase 6c — OpenTelemetry SERVER span. Before Recoverer so the span
	// survives (and is marked 500) when a handler panics.
	r.Use(observability.ChiMiddleware())
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

	// P5 public-MCP OAuth 2.1 discovery (slice 1) — spec-standard unversioned paths,
	// no JWT (public discovery). The handlers 404 when OAuth is disabled (s.oauth nil).
	// The authorize/token/register endpoints land in slices 2–3.
	r.Get("/.well-known/oauth-authorization-server", http.HandlerFunc(s.oauthASMetadata))
	r.Get("/oauth/jwks", http.HandlerFunc(s.oauthJWKS))
	// P5 slice 2 — auth-code + PKCE flow (public endpoints).
	r.Get("/oauth/authorize", http.HandlerFunc(s.oauthAuthorize))
	r.Post("/oauth/token", http.HandlerFunc(s.oauthToken))
	// P5 slice 3 — open Dynamic Client Registration (RFC 7591). Public; the handler
	// self-gates on the DCR flag + a per-IP rate limit + writes an audit row.
	r.Post("/oauth/register", http.HandlerFunc(s.oauthRegister))

	// Internal (service-to-service, no JWT required)
	r.Route("/internal", func(r chi.Router) {
		r.Get("/users/{user_id}/profile", http.HandlerFunc(s.internalGetUserProfile))
		// E0-5 collaborators email-invite: resolve an email → user (book-service calls it).
		r.Get("/users/by-email", http.HandlerFunc(s.internalGetUserByEmail))

		// S-SETTINGS (MCP fan-out): full editable profile read + update for the
		// settings MCP server hosted in provider-registry-service. Token-gated
		// (defense in depth) — a profile WRITE reachable cross-service must require
		// the platform service token, even though /internal is network-isolated.
		r.Group(func(r chi.Router) {
			r.Use(s.requireInternalServiceToken)
			// WS-1.0 (PO-2) — the per-user DEK, WRAPPED. Consumers unwrap it with the KEK
			// from their own env, so the plaintext key never crosses the network.
			// Token-gated: an anonymous wrapped-DEK read would hand an attacker exactly
			// the blob they need to attack offline the moment they also obtain the KEK.
			// Provisions on first read, idempotently — there is no separate "enable
			// encryption" step that could be skipped and leave content in the clear.
			r.Get("/users/{user_id}/dek", http.HandlerFunc(s.internalGetUserDEK))
			// WS-2.7 (D18 / PO-4) — the crypto-shred. Irreversibly destroys the user's
			// wrapped DEK so content encrypted under it cannot be recovered, even from a
			// backup. The explicit erasure worker calls this AFTER removing the content
			// rows; it is intentionally NOT the account soft-delete path (see user_dek.go).
			r.Delete("/users/{user_id}/dek", http.HandlerFunc(s.internalDeleteUserDEK))
			r.Get("/users/{user_id}/full-profile", http.HandlerFunc(s.internalGetFullProfile))
			r.Patch("/users/{user_id}/full-profile", http.HandlerFunc(s.internalUpdateFullProfile))
			// Public MCP credential resolve — the mcp-public-gateway edge turns an
			// external agent's API key into {user_id, scopes, policy} here (P1).
			r.Post("/mcp-keys/resolve", http.HandlerFunc(s.internalResolveMcpKey))
			// Public MCP per-key call audit ingest (P3 / H-O) — the edge fires a
			// best-effort batch of audit rows (one per tools/call) after each request.
			r.Post("/mcp-keys/audit", http.HandlerFunc(s.internalIngestMcpAudit))
			// Public MCP human-approval divert (P4 / OD-2) — the edge diverts a default
			// key's Tier-W propose here instead of handing the agent the confirm token.
			r.Post("/mcp-keys/approvals", http.HandlerFunc(s.internalCreateApproval))
			// Public MCP self-confirm (P4 slice B) — the edge calls this when an
			// allow_self_confirm key executes a Tier-W action via confirm_action; replays
			// the token to the domain with X-Mcp-Key-Id (no approval row).
			r.Post("/mcp-keys/confirm", http.HandlerFunc(s.internalSelfConfirm))
			// P5 slice 2 — seed/register an OAuth client (slice 3 adds the public RFC
			// 7591 self-registration endpoint on top of the same insert).
			r.Post("/oauth/clients", http.HandlerFunc(s.internalRegisterOAuthClient))
		})

		// Admin-JWT issuance (074/075) — mounted only when enabled. Gated by the
		// DEDICATED issuer secret (NOT InternalServiceToken) + rate-limited.
		if s.admin != nil {
			r.Route("/admin", func(r chi.Router) {
				r.Use(func(next http.Handler) http.Handler {
					return s.requireAdminIssuerToken(next)
				})
				r.Post("/token", func(w http.ResponseWriter, req *http.Request) {
					ratelimit.Middleware(s.admin.rl, "admin_token", http.HandlerFunc(s.adminToken)).ServeHTTP(w, req)
				})
				r.Post("/break-glass-token", func(w http.ResponseWriter, req *http.Request) {
					ratelimit.Middleware(s.admin.rl, "break_glass_token", http.HandlerFunc(s.breakGlassToken)).ServeHTTP(w, req)
				})
			})
		}
	})

	r.Route("/v1", func(r chi.Router) {
		r.Post("/auth/register", func(w http.ResponseWriter, r *http.Request) {
			ratelimit.Middleware(s.rl, "register", http.HandlerFunc(s.register)).ServeHTTP(w, r)
		})
		r.Post("/auth/login", func(w http.ResponseWriter, r *http.Request) {
			ratelimit.Middleware(s.rl, "login", http.HandlerFunc(s.login)).ServeHTTP(w, r)
		})
		// Browser-facing admin-session exchange (admin CMS): a logged-in admin
		// principal self-mints an RS256 admin JWT. Handler 404s when admin issuance
		// is disabled. Rate-limited (admin sessions are low-volume).
		r.Post("/admin/session", func(w http.ResponseWriter, req *http.Request) {
			ratelimit.Middleware(s.rl, "admin_session", http.HandlerFunc(s.adminSession)).ServeHTTP(w, req)
		})
		r.Post("/auth/refresh", http.HandlerFunc(s.refresh))
		r.Post("/auth/logout", http.HandlerFunc(s.logout))

		r.Post("/auth/verify-email/request", func(w http.ResponseWriter, r *http.Request) {
			ratelimit.Middleware(s.rl, "verify_req", http.HandlerFunc(s.verifyEmailRequest)).ServeHTTP(w, r)
		})
		r.Post("/auth/verify-email/confirm", http.HandlerFunc(s.verifyEmailConfirm))
		r.Post("/auth/password-reset/request", func(w http.ResponseWriter, r *http.Request) {
			ratelimit.Middleware(s.rl, "reset_req", http.HandlerFunc(s.passwordResetRequest)).ServeHTTP(w, r)
		})
		r.Post("/auth/password-reset/confirm", http.HandlerFunc(s.passwordResetConfirm))

		r.Post("/auth/change-password", http.HandlerFunc(s.changePassword))

		r.Get("/account/profile", http.HandlerFunc(s.getProfile))
		r.Patch("/account/profile", http.HandlerFunc(s.patchProfile))
		r.Get("/account/security/preferences", http.HandlerFunc(s.getSecurityPrefs))
		r.Patch("/account/security/preferences", http.HandlerFunc(s.patchSecurityPrefs))

		r.Get("/me/preferences", http.HandlerFunc(s.getPreferences))
		r.Patch("/me/preferences", http.HandlerFunc(s.patchPreferences))
		r.Delete("/account", http.HandlerFunc(s.deleteAccount))

		// Public MCP API keys (the "new security setting") — owner-only; handlers
		// parse the JWT themselves. Creation is additionally Q-GATE-flag-gated.
		r.Get("/account/mcp-keys", http.HandlerFunc(s.listMcpKeys))
		// P4 / OD-2 approval queue (static segment — declared BEFORE the {key_id} routes
		// so chi matches "approvals" exactly, never as a key_id).
		r.Get("/account/mcp-keys/approvals", http.HandlerFunc(s.listMcpApprovals))
		r.Post("/account/mcp-keys/approvals/{approval_id}/approve", http.HandlerFunc(s.approveMcpApproval))
		r.Post("/account/mcp-keys/approvals/{approval_id}/deny", http.HandlerFunc(s.denyMcpApproval))
		r.Get("/account/mcp-keys/{key_id}/audit", http.HandlerFunc(s.listMcpKeyAudit))
		r.Post("/account/mcp-keys", http.HandlerFunc(s.createMcpKey))
		r.Patch("/account/mcp-keys/{key_id}", http.HandlerFunc(s.patchMcpKey))
		r.Delete("/account/mcp-keys/{key_id}", http.HandlerFunc(s.revokeMcpKey))
		// P5 slice 2 — OAuth consent (owner approves a downscoped grant → mints the auth code).
		r.Post("/account/oauth/consent", http.HandlerFunc(s.oauthConsent))

		// Public user profiles + follow system
		r.Route("/users/{user_id}", func(r chi.Router) {
			r.Get("/", http.HandlerFunc(s.getPublicProfile))
			r.Post("/follow", http.HandlerFunc(s.followUser))
			r.Delete("/follow", http.HandlerFunc(s.unfollowUser))
			r.Get("/followers", http.HandlerFunc(s.listFollowers))
			r.Get("/following", http.HandlerFunc(s.listFollowing))
		})
	})
	return r
}

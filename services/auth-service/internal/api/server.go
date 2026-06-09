package api

import (
	"log/slog"
	"net/http"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/observability"

	"github.com/loreweave/auth-service/internal/config"
	"github.com/loreweave/serviceacl"
	"github.com/loreweave/auth-service/internal/ratelimit"
)

type Server struct {
	pool   *pgxpool.Pool
	cfg    *config.Config
	secret []byte
	rl     *ratelimit.Limiter
}

func NewServer(pool *pgxpool.Pool, cfg *config.Config) *Server {
	return &Server{
		pool:   pool,
		cfg:    cfg,
		secret: []byte(cfg.JWTSecret),
		rl:     ratelimit.New(cfg.RateLimitWindow, cfg.RateLimitMax),
	}
}

func (s *Server) requireInternalToken(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if s.cfg.InternalServiceToken == "" || r.Header.Get("X-Internal-Token") != s.cfg.InternalServiceToken {
			writeJSON(w, http.StatusUnauthorized, map[string]string{"error": "invalid internal token"})
			return
		}
		next.ServeHTTP(w, r)
	})
}

func (s *Server) internalAudit(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		slog.Info("internal_rpc",
			"caller", r.Header.Get("X-Caller-Service"),
			"method", r.Method,
			"path", r.URL.Path,
			"request_id", r.Header.Get("X-Request-Id"),
		)
		next.ServeHTTP(w, r)
	})
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

	// Internal (service-to-service, X-Internal-Token required)
	r.Route("/internal", func(r chi.Router) {
		r.Use(s.requireInternalToken)
		r.Use(serviceacl.OptionalMiddleware)
		r.Use(s.internalAudit)
		r.Get("/users/{user_id}/profile", http.HandlerFunc(s.internalGetUserProfile))
	})

	r.Route("/v1", func(r chi.Router) {
		r.Post("/auth/register", func(w http.ResponseWriter, r *http.Request) {
			ratelimit.Middleware(s.rl, "register", http.HandlerFunc(s.register)).ServeHTTP(w, r)
		})
		r.Post("/auth/login", func(w http.ResponseWriter, r *http.Request) {
			ratelimit.Middleware(s.rl, "login", http.HandlerFunc(s.login)).ServeHTTP(w, r)
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
		r.Post("/auth/stream-ticket", func(w http.ResponseWriter, r *http.Request) {
			ratelimit.Middleware(s.rl, "stream-ticket", http.HandlerFunc(s.issueStreamTicket)).ServeHTTP(w, r)
		})

		r.Get("/account/profile", http.HandlerFunc(s.getProfile))
		r.Patch("/account/profile", http.HandlerFunc(s.patchProfile))
		r.Get("/account/security/preferences", http.HandlerFunc(s.getSecurityPrefs))
		r.Patch("/account/security/preferences", http.HandlerFunc(s.patchSecurityPrefs))

		r.Get("/me/preferences", http.HandlerFunc(s.getPreferences))
		r.Patch("/me/preferences", http.HandlerFunc(s.patchPreferences))
		r.Delete("/account", http.HandlerFunc(s.deleteAccount))

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


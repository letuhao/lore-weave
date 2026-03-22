package api

import (
	"net/http"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/auth-service/internal/config"
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

func (s *Server) Router() http.Handler {
	r := chi.NewRouter()
	r.Use(middleware.RequestID)
	r.Use(middleware.RealIP)
	r.Use(middleware.Recoverer)
	r.Get("/health", s.health)

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

		r.Get("/account/profile", http.HandlerFunc(s.getProfile))
		r.Patch("/account/profile", http.HandlerFunc(s.patchProfile))
		r.Get("/account/security/preferences", http.HandlerFunc(s.getSecurityPrefs))
		r.Patch("/account/security/preferences", http.HandlerFunc(s.patchSecurityPrefs))
	})
	return r
}

func (s *Server) health(w http.ResponseWriter, r *http.Request) {
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write([]byte("ok"))
}

package api

import (
	"context"
	"crypto/subtle"
	"net/http"
	"slices"

	"github.com/loreweave/foundation/contracts/adminjwt"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

// T4 — the SEPARATE System-tier admin MCP server, mounted at /mcp/admin (distinct
// from /mcp). The physical-endpoint-separation barrier (spec §4c, INV-T6): admin
// tools live ONLY here, behind a transport gate that verifies an RS256 admin:write
// JWT in X-Admin-Token BEFORE tools/list or any tools/call. A non-admin caller cannot
// even ENUMERATE the admin tools — three independent barriers for any System write:
// (1) /mcp/admin unreachable without a verified admin token, (2) admin tools absent
// from /mcp, (3) every System write still human-confirm-gated (class C).

const ctxKeyAdminSub mcpCtxKey = "x-admin-sub"

// adminMCPHandler builds the admin MCP server (admin-tier tools only) wrapped in the
// RS256 admin-identity middleware. Mounted at /mcp/admin by Router().
func (s *Server) adminMCPHandler() http.Handler {
	srv := mcp.NewServer(&mcp.Implementation{Name: "glossary-admin", Version: "0.1.0"}, nil)
	s.RegisterAdminTools(srv)
	streamable := mcp.NewStreamableHTTPHandler(
		func(*http.Request) *mcp.Server { return srv },
		&mcp.StreamableHTTPOptions{Stateless: true, JSONResponse: true},
	)
	return s.adminMCPIdentityMiddleware(streamable)
}

// adminMCPIdentityMiddleware is the transport gate. It runs BEFORE the MCP handler,
// so an unauthenticated request is rejected before tools/list ever executes. Two
// checks, both fail-closed: (1) the SO-1 service token (only the gateway reaches
// here); (2) a valid RS256 admin:write JWT in X-Admin-Token (the admin authority —
// INV-T2: never X-User-Id). The verified admin subject is lifted into ctx.
func (s *Server) adminMCPIdentityMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		tok := r.Header.Get("X-Internal-Token")
		if s.cfg.InternalServiceToken == "" ||
			subtle.ConstantTimeCompare([]byte(tok), []byte(s.cfg.InternalServiceToken)) != 1 {
			writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "invalid internal token")
			return
		}
		// Admin disabled (no key configured) → fail closed, before any enumeration.
		if s.adminPub == nil {
			writeError(w, http.StatusUnauthorized, "GLOSS_ADMIN_UNAVAILABLE", "system-tier administration is not configured")
			return
		}
		adminTok := r.Header.Get("X-Admin-Token")
		if adminTok == "" {
			writeError(w, http.StatusUnauthorized, "GLOSS_ADMIN_UNAUTHORIZED", "admin token required")
			return
		}
		claims, err := adminjwt.Verify(adminTok, s.adminPub, s.adminKID)
		if err != nil || !slices.Contains(claims.Scopes, scopeAdminWrite) {
			writeError(w, http.StatusUnauthorized, "GLOSS_ADMIN_UNAUTHORIZED", "invalid admin token")
			return
		}
		ctx := context.WithValue(r.Context(), ctxKeyAdminSub, claims.Subject)
		next.ServeHTTP(w, r.WithContext(ctx))
	})
}

func adminSubFromCtx(ctx context.Context) (string, bool) {
	v, _ := ctx.Value(ctxKeyAdminSub).(string)
	return v, v != ""
}

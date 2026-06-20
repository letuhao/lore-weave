// Package loreweave_mcp is the shared Go MCP kit for LoreWeave provider services.
//
// It factors the cross-cutting concerns every Go MCP provider (book, settings,
// …) would otherwise re-derive: the identity middleware (lift the per-call
// envelope into ctx after a constant-time internal-token check, SEC-1), the
// stateless StreamableHTTP wiring (INV-4), the three per-domain ownership guards
// (book/user/project scope, H15/SEC-2), the uniform not-accessible error (H13),
// the Tier-S/W confirm-token spine, and the C-TOOL `_meta` validator.
//
// Identity and scope ids come ONLY from the envelope/headers — NEVER from tool
// args (SEC-1).
package loreweave_mcp

import (
	"context"
	"crypto/subtle"
	"net/http"

	"github.com/google/uuid"
)

// ctxKey is an unexported context key type so kit-set values can't collide with
// any other package's context keys.
type ctxKey string

const (
	ctxKeyUserID    ctxKey = "lw-mcp-user-id"
	ctxKeySessionID ctxKey = "lw-mcp-session-id"
	ctxKeyTraceID   ctxKey = "lw-mcp-trace-id"
)

// Envelope header names the gateway forwards on every per-call MCP request.
const (
	HeaderInternalToken = "X-Internal-Token"
	HeaderUserID        = "X-User-Id"
	HeaderSessionID     = "X-Session-Id"
	HeaderTraceID       = "X-Trace-Id"
)

// IdentityMiddleware validates X-Internal-Token in constant time (SEC-1) and,
// on success, lifts the X-User-Id / X-Session-Id / X-Trace-Id envelope headers
// into the request context for the tool handlers to read via UserIDFromCtx etc.
//
// A missing/empty configured internalToken, or a mismatching presented token,
// is rejected with 401 — fail closed. The token is the platform service token,
// never a hardcoded secret: pass it from config/env (no defaulting here).
func IdentityMiddleware(internalToken string, next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		tok := r.Header.Get(HeaderInternalToken)
		if internalToken == "" ||
			subtle.ConstantTimeCompare([]byte(tok), []byte(internalToken)) != 1 {
			http.Error(w, "invalid internal token", http.StatusUnauthorized)
			return
		}
		ctx := r.Context()
		ctx = context.WithValue(ctx, ctxKeyUserID, r.Header.Get(HeaderUserID))
		ctx = context.WithValue(ctx, ctxKeySessionID, r.Header.Get(HeaderSessionID))
		ctx = context.WithValue(ctx, ctxKeyTraceID, r.Header.Get(HeaderTraceID))
		next.ServeHTTP(w, r.WithContext(ctx))
	})
}

// UserIDFromCtx returns the caller's user id (lifted from X-User-Id by
// IdentityMiddleware). ok is false when no/blank/malformed id is present — a
// tool MUST treat that as "missing caller identity" and refuse, never proceed
// with uuid.Nil.
func UserIDFromCtx(ctx context.Context) (uuid.UUID, bool) {
	v, _ := ctx.Value(ctxKeyUserID).(string)
	if v == "" {
		return uuid.Nil, false
	}
	id, err := uuid.Parse(v)
	if err != nil {
		return uuid.Nil, false
	}
	return id, true
}

// SessionIDFromCtx returns the chat session id (X-Session-Id). ok is false when
// absent. The session id is opaque (not a UUID by contract), so it is returned
// as a string.
func SessionIDFromCtx(ctx context.Context) (string, bool) {
	v, _ := ctx.Value(ctxKeySessionID).(string)
	if v == "" {
		return "", false
	}
	return v, true
}

// TraceIDFromCtx returns the distributed-trace id (X-Trace-Id). ok is false when
// absent.
func TraceIDFromCtx(ctx context.Context) (string, bool) {
	v, _ := ctx.Value(ctxKeyTraceID).(string)
	if v == "" {
		return "", false
	}
	return v, true
}

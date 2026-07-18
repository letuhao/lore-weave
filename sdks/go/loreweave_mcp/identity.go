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
	ctxKeyMcpKeyID  ctxKey = "lw-mcp-key-id"
)

// Envelope header names the gateway forwards on every per-call MCP request.
const (
	HeaderInternalToken = "X-Internal-Token"
	HeaderUserID        = "X-User-Id"
	HeaderSessionID     = "X-Session-Id"
	HeaderTraceID       = "X-Trace-Id"
	// HeaderMcpKeyID identifies the public MCP API key a request was authenticated
	// with at the public edge (mcp-public-gateway). Present ONLY on public-key
	// traffic; absent for first-party (FE→chat→gateway) calls. The edge mints it,
	// ai-gateway forwards it (additive). Carrier for per-key spend attribution
	// (H-C) and the owned-resources-only default (OD-8).
	HeaderMcpKeyID = "X-Mcp-Key-Id"
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
		ctx = context.WithValue(ctx, ctxKeyMcpKeyID, r.Header.Get(HeaderMcpKeyID))
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

// ContextWithMcpKeyID injects the public MCP key id (X-Mcp-Key-Id) under the kit's
// private context key, so a provider running its OWN identity middleware (e.g.
// glossary — services that use IdentityMiddleware / NewStatelessHandler, like
// book-service, already get this for free) can still light up McpKeyIDFromCtx /
// OwnerOnlyFromCtx (OD-8). Pass the raw header value; an empty string leaves the
// call first-party (OwnerOnlyFromCtx stays false). IdentityMiddleware does this
// internally — use this only when wiring a bespoke middleware.
func ContextWithMcpKeyID(ctx context.Context, keyID string) context.Context {
	return context.WithValue(ctx, ctxKeyMcpKeyID, keyID)
}

// McpKeyIDFromCtx returns the public MCP API key id (X-Mcp-Key-Id). ok is false
// when absent — i.e. this is a first-party (non-public-key) call. The id is
// opaque to providers (the auth-service mints/owns it); a tool only needs to know
// it is set to attribute spend (H-C) and apply the owned-only default (OD-8).
func McpKeyIDFromCtx(ctx context.Context) (string, bool) {
	v, _ := ctx.Value(ctxKeyMcpKeyID).(string)
	if v == "" {
		return "", false
	}
	return v, true
}

// OwnerOnlyFromCtx reports whether ownership resolution must be restricted to
// resources the caller OWNS — dropping grant-derived (shared-with-me) access
// (OD-8). It is true exactly for public MCP-key traffic (X-Mcp-Key-Id present):
// a third-party agent acting as user U must not reach books merely shared with U
// by their true owner, who never consented to a third-party agent. First-party
// calls return false (grant-aware resolution unchanged). A guard honours this by
// using owner-equality instead of a grant check when true.
func OwnerOnlyFromCtx(ctx context.Context) bool {
	_, ok := McpKeyIDFromCtx(ctx)
	return ok
}

// ResolveEnvelopeOrBearerCaller returns the trusted caller's user id for a
// confirm/preview-style HTTP route that must accept EITHER a trusted
// internal-service envelope (X-Internal-Token, constant-time-compared against
// internalToken, + X-User-Id) OR the caller's own Bearer-JWT verifier
// (bearerFallback). JWT secrets/verification differ per service, so that half
// deliberately stays out of this shared kit — only the envelope's
// compare-then-lift-X-User-Id logic (identical to IdentityMiddleware above) is
// consolidated here.
//
// The internal-token branch is checked FIRST and, once the header is present,
// is authoritative: a matching token with a missing/malformed X-User-Id fails
// closed (ok=false) rather than falling through to bearerFallback — an
// internal caller that got the envelope wrong must not silently succeed via
// some unrelated Bearer header it happens to also carry. When X-Internal-Token
// is absent entirely, control passes to bearerFallback unconditionally (the
// ordinary browser-JWT path).
//
// This consolidates the identical resolveConfirmCaller logic independently
// duplicated across glossary-service, book-service, and
// provider-registry-service's settings confirm routes (SDK-First) — each
// service passes its own requireUserID/auth as bearerFallback.
func ResolveEnvelopeOrBearerCaller(r *http.Request, internalToken string, bearerFallback func(*http.Request) (uuid.UUID, bool)) (uuid.UUID, bool) {
	if tok := r.Header.Get(HeaderInternalToken); tok != "" {
		if internalToken == "" ||
			subtle.ConstantTimeCompare([]byte(tok), []byte(internalToken)) != 1 {
			return uuid.Nil, false
		}
		uid, err := uuid.Parse(r.Header.Get(HeaderUserID))
		if err != nil {
			return uuid.Nil, false
		}
		return uid, true
	}
	return bearerFallback(r)
}

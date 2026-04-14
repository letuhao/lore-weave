package api

import (
	"context"
	"encoding/json"
	"log"
	"net/http"
	"runtime/debug"

	"github.com/google/uuid"
)

// K7e: end-to-end X-Trace-Id propagation. Glossary-service is the final
// hop in the chat → knowledge → glossary chain, so this middleware
// only needs to parse the incoming header (or mint one), stash it on
// the request context, and echo it back on the response so upstream
// services can correlate their logs.
//
// We deliberately do NOT replace chi's middleware.RequestID — that
// one generates its own per-request id scoped to the request lifecycle
// (used by middleware.Recoverer's panic logs). X-Trace-Id is the
// cross-service id a caller hands us; the two are independent.

// traceIDCtxKey is unexported so callers can only read via TraceIDFromContext.
type traceIDCtxKey struct{}

const traceIDHeader = "X-Trace-Id"

// newTraceID returns a fresh 32-char hex id, matching the format
// knowledge-service and chat-service use (uuid4().hex). Using uuid.New()
// + hex encoding keeps the wire format identical across the three
// services so log aggregators can match ids as raw strings.
func newTraceID() string {
	u := uuid.New()
	b := u[:]
	const hextable = "0123456789abcdef"
	out := make([]byte, 32)
	for i, v := range b {
		out[i*2] = hextable[v>>4]
		out[i*2+1] = hextable[v&0x0f]
	}
	return string(out)
}

// TraceIDFromContext returns the trace id for the in-flight request,
// or "" if the middleware did not run (e.g. background workers that
// build their own context.Context).
func TraceIDFromContext(ctx context.Context) string {
	v, _ := ctx.Value(traceIDCtxKey{}).(string)
	return v
}

// jsonRecovererMiddleware replaces chi's middleware.Recoverer so panic
// responses carry the trace id in a JSON body instead of the default
// "Internal Server Error" plain text. Must run AFTER traceIDMiddleware
// so the id is already on the context when a panic is caught.
func jsonRecovererMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		defer func() {
			if rec := recover(); rec != nil {
				tid := TraceIDFromContext(r.Context())
				log.Printf("panic recovered: %v trace_id=%s\n%s", rec, tid, debug.Stack())
				w.Header().Set("Content-Type", "application/json")
				w.Header().Set(traceIDHeader, tid)
				w.WriteHeader(http.StatusInternalServerError)
				_ = json.NewEncoder(w).Encode(map[string]string{
					"detail":   "internal server error",
					"trace_id": tid,
				})
			}
		}()
		next.ServeHTTP(w, r)
	})
}

// traceIDMiddleware adopts the inbound X-Trace-Id header or generates
// a fresh one, stores it on the context, and echoes it on the response.
func traceIDMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		tid := r.Header.Get(traceIDHeader)
		if tid == "" {
			tid = newTraceID()
		}
		// Set the header on the response BEFORE next.ServeHTTP so it
		// survives even if the handler writes the status immediately.
		w.Header().Set(traceIDHeader, tid)
		ctx := context.WithValue(r.Context(), traceIDCtxKey{}, tid)
		next.ServeHTTP(w, r.WithContext(ctx))
	})
}

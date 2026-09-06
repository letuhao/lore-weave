package api

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
)

// Which transport dispatched a command, and the ONE place every entity event is written
// (plan T50).
//
// WHY THE TRANSPORT IS WORTH RECORDING
// ------------------------------------
// The `*Core` surface T27–T29 built is explicitly shared: `entity_handler.go` calls
// `softDeleteEntityCore` *"the single source of truth for the REST DELETE route AND the
// glossary_entity_delete Tier-W confirm effect"*, and since T29 a third transport — the KAL's
// service command — lands on the same core. That sharing is the design working. It also means
// that when a delete misbehaves in production, the event it wrote says WHAT happened and
// nothing about WHO asked, and three transports are indistinguishable in the log.
//
// This repo has recorded the drift twice already (FastMCP strips undeclared fields; the REST
// mirror drops fields the MCP tool accepts), and both times the tell would have been "the MCP
// path and the HTTP path stopped agreeing" — which you cannot see without knowing which path
// you are looking at.
//
// It is a LOG field, not a payload field. Consumers act on what changed, not on who dialled
// in; putting the transport on the wire would invite a consumer to branch on it, and a
// consumer that behaves differently for an MCP delete than an HTTP one is the split-brain this
// whole phase exists to remove.

type commandCtxKey string

const ctxKeyTransport commandCtxKey = "lw-command-transport"

// The closed set. `unknown` is not a failure mode to fix at the call site — it means a
// transport that never marked itself, and seeing it in the log is the point.
const (
	transportHTTP     = "http"
	transportMCP      = "mcp"
	transportInternal = "internal"
	transportUnknown  = "unknown"
)

// withTransport tags a context at the transport boundary. Called by middleware, never by a
// handler: a handler that tagged its own context would be describing itself rather than
// reporting how it was reached, and the two diverge the first time a handler is reused.
func withTransport(ctx context.Context, transport string) context.Context {
	return context.WithValue(ctx, ctxKeyTransport, transport)
}

// transportMiddleware tags every request under a router subtree. Applied at the ROOT as
// `http` and re-applied on `/internal` as `internal`; chi runs a subrouter's middleware after
// the parent's, so the more specific tag wins. The MCP handler tags its own ctx in
// `mcpIdentityMiddleware` (it is mounted with Handle, not a Route subtree).
func transportMiddleware(transport string) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			next.ServeHTTP(w, r.WithContext(withTransport(r.Context(), transport)))
		})
	}
}

func transportFromCtx(ctx context.Context) string {
	if v, ok := ctx.Value(ctxKeyTransport).(string); ok && v != "" {
		return v
	}
	return transportUnknown
}

// insertOutboxEventTx is the ONE place an entity event row is written.
//
// It exists because there were three: `emitEntityLifecycleTx`, `emitEntityStatusChangedTx` and
// `insertEntityOutboxEvent` each held their own `INSERT INTO outbox_events`. Three copies of
// one statement is three places for a column to be added to two of them — and this plan has
// spent T27, T28 and T29 on variations of exactly that. Converging them also gives the
// transport log a single home, so "every command dispatch is logged" is a property of the
// code's shape rather than a promise about remembering.
//
// `exec` is the caller's transaction — the whole contract of these events is that the row and
// the mutation commit together, so this deliberately takes no pool.
func insertOutboxEventTx(
	ctx context.Context,
	exec func(ctx context.Context, sql string, args ...any) error,
	aggregateID any,
	eventType string,
	payload any,
	logAttrs ...any,
) error {
	payloadJSON, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("outbox marshal (%s): %w", eventType, err)
	}
	if err := exec(ctx, `
		INSERT INTO outbox_events (aggregate_type, aggregate_id, event_type, payload)
		VALUES ('glossary', $1, $2, $3)`,
		aggregateID, eventType, payloadJSON,
	); err != nil {
		return fmt.Errorf("outbox insert (%s): %w", eventType, err)
	}
	attrs := append([]any{
		"event_type", eventType,
		"aggregate_id", fmt.Sprint(aggregateID),
		"transport", transportFromCtx(ctx),
	}, logAttrs...)
	slog.Debug("entity command dispatched", attrs...)
	return nil
}

package api

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"net/http/httptest"

	"github.com/google/uuid"
	"github.com/loreweave/grantclient"
	"github.com/modelcontextprotocol/go-sdk/mcp"

	lwmcp "github.com/loreweave/loreweave_mcp"
)

// Durable ext-tasks human gate for glossary's KIND-C propose tools (spec
// docs/specs/2026-07-19-mcp-tasks-durable-gate.md, T3c) — the Go mirror of book-service's
// book_chapter_delete gate, generalized to glossary's WHOLE class-C confirm surface via a
// SINGLE dispatching resolver.
//
// Each class-C propose tool builds exactly the confirm card + params it always has, then
// instead of returning the {confirm_token, …} card unconditionally it calls a gate helper:
// GateOrConfirm branches on the client's declared ext-tasks capability. A tasks-capable
// client gets a durable input_required TASK (persisted in the PgTaskStore) whose executor
// runs the SAME confirm effect the /v1/glossary/actions/confirm route would; EVERY other
// client gets today's byte-identical confirm_token card (the confirmFallback), so nothing
// is stranded. Only the RETURN changes — every propose-time authorization/validation check
// and the confirm_token itself are preserved exactly.
//
// The resolver is DISPATCHING: one registered function handles every migrated descriptor,
// reconstructing actionClaims from the persisted {ownerUserID, payload} and re-running the
// existing per-descriptor effect through dispatchConfirmEffect. Reuse is total — no effect
// is rewritten. (Book extracted its single effect into a repo helper; glossary has 14 live
// descriptors, so a copy-of-effects extraction would be a large, risky refactor of
// load-bearing write code. Instead the resolver captures the effect's HTTP response via an
// httptest recorder and translates it to the (any, error) a task result needs — the minimal
// refactor that keeps every effect byte-identical between the confirm route and the gate.)

// taskInputRequests is the rich card the tasks-capable client renders while the human
// decides (the task path has NO confirm_token — the task itself is the gate). Built from
// the same card the confirm_token fallback returns, minus the token.
func taskInputRequests(card confirmCardOut) map[string]any {
	req := map[string]any{
		"descriptor":   card.Descriptor,
		"authority":    card.Authority,
		"title":        card.Title,
		"preview_rows": card.PreviewRows,
		"destructive":  card.Destructive,
		"domain":       "glossary", // selects the FE confirm surface (C-CONFIRM), mirrors book
		"expires_at":   card.ExpiresAt,
	}
	if card.Warning != "" {
		req["warning"] = card.Warning
	}
	return req
}

// reqMeta reads the per-request _meta (client capabilities) off a tool request,
// nil-safely — a nil req or nil Params (e.g. a unit test calling a tool directly)
// yields nil, which ClientSupportsTasks reads as "no tasks support" ⇒ confirm_token.
func reqMeta(req *mcp.CallToolRequest) lwmcp.Meta {
	if req == nil || req.Params == nil {
		return nil
	}
	return req.Params.Meta
}

// gateOrFallback is the ONE gate call a glossary KIND-C tool makes. It captures the
// serializable propose-time payload (descriptor + book + params) the resolver will replay,
// then GateOrConfirm opens a durable task for a tasks-capable client or returns fallback()
// (today's result) for every other client. params is re-marshaled to the SAME bytes the
// confirm_token carries, so the gate path and the confirm path execute byte-identical intent.
func (s *Server) gateOrFallback(ctx context.Context, req *mcp.CallToolRequest, descriptor string, bookID, userID uuid.UUID, params any, card confirmCardOut, fallback func() any) (any, error) {
	raw, err := json.Marshal(params)
	if err != nil {
		return nil, errors.New("failed to encode proposal")
	}
	payload := map[string]any{
		"descriptor":  descriptor,
		"book_id":     bookID.String(),
		"params_json": string(raw),
	}
	return lwmcp.GateOrConfirm(ctx, reqMeta(req), s.actionTasks, descriptor, userID.String(),
		payload, taskInputRequests(card), fallback, 0)
}

// gateOrCard is the common wrapper for a propose tool whose result is the confirmCardOut
// itself: the fallback returns that exact card (byte-identical to today). cardErr short-
// circuits (a mint failure surfaces as before).
func (s *Server) gateOrCard(ctx context.Context, req *mcp.CallToolRequest, descriptor string, bookID, userID uuid.UUID, params any, card confirmCardOut, cardErr error) (*mcp.CallToolResult, any, error) {
	if cardErr != nil {
		return nil, confirmCardOut{}, cardErr
	}
	out, err := s.gateOrFallback(ctx, req, descriptor, bookID, userID, params, card, func() any { return card })
	return nil, out, err
}

// resolveGlossaryAction is the DISPATCHING durable-gate resolver, registered for every
// migrated descriptor at startup. It runs ONLY on accept, reconstructed on any replica from
// the persisted {ownerUserID, payload} — no closure. It re-binds the caller to the proposing
// user and re-checks the Manage grant (authorizeAction's authorityGrant branch: the accept
// arrives on a later request, the grant may have been revoked meanwhile), then replays the
// SAME per-descriptor effect the /actions/confirm route runs via dispatchConfirmEffect. The
// task single-winner claim is the single-use equivalent of consumeToken.
func (s *Server) resolveGlossaryAction(ctx context.Context, ownerUserID string, payload map[string]any, inputs map[string]any) (any, error) {
	// Caller re-bind — parity with confirmAction's claims.UserID == redeeming caller check.
	// Uniform "not accessible" (no oracle), matching uniformOwnershipError.
	caller, ok := userIDFromCtx(ctx)
	if !ok || caller.String() != ownerUserID {
		return nil, errors.New("book not accessible")
	}
	owner, err := uuid.Parse(ownerUserID)
	if err != nil {
		return nil, errors.New("book not accessible")
	}
	descriptor := taskPayloadString(payload["descriptor"])
	if !liveDescriptor(descriptor) {
		return nil, errors.New("unknown action")
	}
	bookID, err := uuid.Parse(taskPayloadString(payload["book_id"]))
	if err != nil {
		return nil, errors.New("book_id must be a UUID")
	}
	// Grant re-check at accept time (defense in depth; every migrated descriptor is
	// authorityGrant + Manage-gated, exactly like authorizeAction).
	if err := s.checkGrant(ctx, bookID, owner, grantclient.GrantManage); err != nil {
		return nil, uniformOwnershipError(err)
	}

	claims := actionClaims{
		Authority:  authorityGrant,
		UserID:     owner,
		BookID:     bookID,
		Descriptor: descriptor,
		Params:     json.RawMessage(taskPayloadString(payload["params_json"])),
	}
	// execute_plan carries per-op destructive opt-ins; on the task path the human's
	// response supplies them (absent ⇒ additive-only, the SAFE default). Every other
	// descriptor ignores enabledOps.
	var enabledOps []string
	if raw, ok := inputs["enabled_ops"]; ok {
		enabledOps = taskStringSlice(raw)
	}

	// Replay the SAME effect the confirm route runs, capturing its HTTP response so the
	// resolver can RETURN a value (the effects write to an http.ResponseWriter).
	rec := httptest.NewRecorder()
	s.dispatchConfirmEffect(rec, ctx, claims, enabledOps)
	return effectResultFromRecorder(rec)
}

// effectResultFromRecorder translates a captured effect response into the (result, error)
// a task terminal outcome needs: a 2xx body becomes the task Result (completed); a 4xx/5xx
// becomes a failed task carrying the effect's own error message; an empty 2xx (e.g. a 204
// book_delete) becomes a uniform action_done result.
func effectResultFromRecorder(rec *httptest.ResponseRecorder) (any, error) {
	body := rec.Body.Bytes()
	if rec.Code >= 400 {
		msg := extractErrorMessage(body)
		if msg == "" {
			msg = "action failed"
		}
		return nil, errors.New(msg)
	}
	if len(bytes.TrimSpace(body)) == 0 {
		return map[string]any{"outcome": "action_done"}, nil
	}
	var v any
	if err := json.Unmarshal(body, &v); err != nil {
		return nil, errors.New("action produced an unreadable result")
	}
	return v, nil
}

// extractErrorMessage pulls the human message out of a writeError body ({code,message}).
func extractErrorMessage(body []byte) string {
	var eb struct {
		Message string `json:"message"`
	}
	if err := json.Unmarshal(body, &eb); err != nil {
		return ""
	}
	return eb.Message
}

// taskPayloadString reads a string field from a round-tripped jsonb payload map.
func taskPayloadString(v any) string {
	s, _ := v.(string)
	return s
}

// taskStringSlice coerces a round-tripped jsonb value into a []string (enabled_ops).
func taskStringSlice(v any) []string {
	arr, ok := v.([]any)
	if !ok {
		return nil
	}
	out := make([]string, 0, len(arr))
	for _, e := range arr {
		if s, ok := e.(string); ok {
			out = append(out, s)
		}
	}
	return out
}

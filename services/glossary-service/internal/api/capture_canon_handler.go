package api

// WS-4C Half A — POST /internal/books/{book_id}/capture-canon.
// Spec: docs/specs/2026-07-10-ws4c-half-a-canon-auto-capture.md
//
// Closes the F4 write-side gap: chat-service calls this every Nth assistant turn with the
// turn's text; we extract the NEW named entities the exchange established and land them in
// the book's existing review inbox as `draft` + `ai-suggested` entities. Never canon — a
// draft is invisible to L1/L2 auto-recall until a human promotes it, and a name the human
// previously rejected (the `ai-rejected` tombstone) is never re-proposed.
//
// TENANCY — the load-bearing part. Unlike its `/internal` siblings (which the extraction
// worker calls for a job it already owns), this route is driven by a *chat session*, whose
// book_id ultimately traces back to user-supplied data. An internal-token caller is NOT
// implicitly authorized to write into an arbitrary book, so we grant-check the supplied
// owner_user_id against book_id at GrantEdit — the same uniform, anti-oracle check every
// MCP write tool performs (403 covers both "no grant" and "no such book").
//
// No new write path: each candidate goes through proposeNewEntity — the exact core
// glossary_propose_entities uses (per-book advisory lock, (kind,name-or-alias,scope) dedup,
// tombstone gate, `[ai-suggested, assistant]` tags). Capture therefore CANNOT mutate an
// entity that already exists: proposeNewEntity short-circuits to skipped_exists before it
// ever touches attributes.

import (
	"encoding/json"
	"errors"
	"log/slog"
	"net/http"
	"strings"

	"github.com/google/uuid"
	"github.com/loreweave/grantclient"
)

const (
	// maxCaptureSourceRunes caps the exchange text. Far smaller than a seed doc
	// (maxSourceMarkdownLen) because a single turn is small and this runs on a cadence —
	// an unbounded body would let one pathological turn dominate the user's token spend.
	// This is a GUARD, not a strategy: chat already caps each side of the exchange before
	// sending. Over-length is truncated (rejecting would silently lose the whole turn) and
	// the truncation is REPORTED, never a silent partial success. Counted in runes, not
	// bytes — byte-slicing splits a CJK rune and hands the model invalid UTF-8.
	maxCaptureSourceRunes = 12000
	// captureCandidateCap / captureCandidateDefault bound how many drafts ONE capture may
	// mint. The inbox is a human work queue: a cadence tick that mints 200 drafts is a
	// denial-of-attention bug, not a feature. The model is additionally told to emit only
	// entities the exchange introduces (flavorChatCapture).
	captureCandidateCap     = 24
	captureCandidateDefault = 12
)

type captureCanonRequest struct {
	// OwnerUserID is grant-checked against book_id at Edit. REQUIRED — an internal caller
	// must name the user on whose behalf it is writing; there is no ambient identity here.
	OwnerUserID string `json:"owner_user_id"`
	// SourceText is the conversation exchange. Treated strictly as DATA (never
	// instructions) by the extractor prompt.
	SourceText string `json:"source_text"`
	// ModelRef optionally pins the extracting model (a provider-registry user_model UUID).
	// Omitted → provider-registry resolves the user's planner/chat default. glossary never
	// holds a provider key; the call is billed to OwnerUserID like any other of their calls.
	ModelRef string `json:"model_ref"`
	// MaxCandidates clamps the drafts one capture may mint. Server-clamped to
	// [1, captureCandidateCap]; omitted/0 → captureCandidateDefault.
	MaxCandidates int `json:"max_candidates"`
}

type capturedEntity struct {
	Name     string `json:"name"`
	Kind     string `json:"kind"`
	EntityID string `json:"entity_id"`
}

type captureCanonResponse struct {
	Created []capturedEntity `json:"created"`
	// Skipped counts candidates that already exist OR were previously rejected. Both are
	// the SAME outcome for the caller ("nothing to review"), and collapsing them here
	// avoids telling chat which names a user has rejected.
	Skipped int `json:"skipped"`
	Failed  int `json:"failed"`
	// Notes carries whatever the model could not map to a kind, plus the candidate-cap
	// notice. Surfaced so a truncated capture is never silently reported as complete.
	Notes []string `json:"notes,omitempty"`
	// Truncated is true when SourceText exceeded maxCaptureSourceLen and was cut.
	Truncated bool `json:"truncated,omitempty"`
}

// captureCanon handles POST /internal/books/{book_id}/capture-canon.
func (s *Server) captureCanon(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	var req captureCanonRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid JSON body")
		return
	}
	userID, err := uuid.Parse(strings.TrimSpace(req.OwnerUserID))
	if err != nil {
		writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "owner_user_id must be a UUID")
		return
	}
	text := strings.TrimSpace(req.SourceText)
	if text == "" {
		writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "source_text is required")
		return
	}
	truncated := false
	if runes := []rune(text); len(runes) > maxCaptureSourceRunes {
		text = string(runes[:maxCaptureSourceRunes])
		truncated = true
	}
	maxCandidates := req.MaxCandidates
	if maxCandidates <= 0 {
		maxCandidates = captureCandidateDefault
	}
	if maxCandidates > captureCandidateCap {
		maxCandidates = captureCandidateCap
	}

	ctx := r.Context()
	// Edit — capture WRITES drafts. Uniform 403 on under-grant or missing book (no oracle);
	// 409 on a trashed book; 503 when book-service is unreachable (fail closed).
	if !s.requireGrant(w, ctx, bookID, userID, grantclient.GrantEdit) {
		return
	}

	// WS-1.6 (spec 05 §Q3) — select the extraction flavor SERVER-SIDE from the book's kind,
	// NEVER a caller-supplied arg (the caller is a chat session; its inputs trace to user
	// data). A kind='diary' book is the work assistant: capture the user's REAL colleagues /
	// projects / meetings (flavorWorkCapture); anything else keeps the fiction chat flavor
	// that excludes real people. ResolveAccess is served from the grant cache the requireGrant
	// check just populated — not an extra hop; and kind is "" to a non-grantee (no oracle), so
	// it defaults safely to the fiction flavor.
	flavor := flavorChatCapture
	if acc, aerr := s.grantClient.ResolveAccess(ctx, bookID, userID); aerr == nil && acc.Kind == "diary" {
		flavor = flavorWorkCapture
	}

	out, err := s.extractEntityCandidates(ctx, userID, bookID, text, nil, req.ModelRef, flavor, maxCandidates)
	if err != nil {
		if errors.Is(err, errNoBookKinds) {
			// A distinct, terminal-for-now code: the book has no ontology, so capture can
			// never succeed until the user sets one up. Chat logs it and stops re-firing,
			// rather than treating it as a transient failure and burning a model call per
			// cadence tick forever.
			writeError(w, http.StatusConflict, "GLOSS_NO_KINDS", "book has no entity kinds to ground capture against")
			return
		}
		slog.Warn("canon capture: extraction failed", "book_id", bookID, "err", err)
		writeError(w, http.StatusBadGateway, "GLOSS_EXTRACT_FAILED", "entity extraction failed")
		return
	}

	resp := captureCanonResponse{
		Created:   []capturedEntity{},
		Notes:     out.Notes,
		Truncated: truncated,
	}
	if len(out.Candidates) == 0 {
		// The expected common case: the exchange established nothing new.
		writeJSON(w, http.StatusOK, resp)
		return
	}

	kindMap, err := s.loadKindMap(ctx, bookID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to resolve kinds")
		return
	}
	for _, c := range out.Candidates {
		res := s.proposeOneEntity(ctx, bookID, kindMap, proposeEntityItemIn{
			Kind:       c.Kind,
			Name:       c.Name,
			Attributes: attrsAsAny(c.Attributes),
			ScopeLabel: c.ScopeLabel,
		})
		switch res.Status {
		case "created":
			resp.Created = append(resp.Created, capturedEntity{Name: res.Name, Kind: c.Kind, EntityID: res.EntityID})
		case "skipped_exists", "skipped_tombstoned":
			resp.Skipped++
		default:
			resp.Failed++
		}
	}
	slog.Info("canon capture",
		"book_id", bookID, "user_id", userID,
		"candidates", len(out.Candidates), "created", len(resp.Created),
		"skipped", resp.Skipped, "failed", resp.Failed, "truncated", truncated,
	)
	writeJSON(w, http.StatusOK, resp)
}

// attrsAsAny widens the extractor's map[string]string to the map[string]any that
// proposeNewEntity's attribute writer takes. Returns nil (not an empty map) when there is
// nothing to write, so the create path treats it as "no attributes" rather than "an empty
// attribute set".
func attrsAsAny(in map[string]string) map[string]any {
	if len(in) == 0 {
		return nil
	}
	out := make(map[string]any, len(in))
	for k, v := range in {
		out[k] = v
	}
	return out
}

package api

// S-BOOK Tier-W (confirm-via-token) — the class-C action spine, generalized from
// glossary (action_confirm*.go). The propose MCP tools below MINT a confirm
// token (NO write) bound to user+resource+descriptor+payload+expiry, and return
// a confirm card {confirm_token, descriptor, title}. The ONLY write path is the
// NET-NEW token-gated POST /v1/book/actions/confirm route (INV-9); a separate
// non-consuming GET /v1/book/actions/preview re-renders the card from current
// state. A buggy/compromised consumer routing through the gateway can MINT but
// never MUTATE — there is deliberately no MCP tool that performs a Tier-W write.
//
// The token is the kit's stateless HMAC (loreweave_mcp.MintConfirmToken/Verify),
// keyed by the service JWT secret with a domain separator (never a real JWT).
// The descriptor is the confused-deputy guard: confirm checks the token's
// descriptor matches the action, so a token minted for book.delete can never
// confirm book.publish.

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"net/http"
	"strings"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/modelcontextprotocol/go-sdk/mcp"

	lwmcp "github.com/loreweave/loreweave_mcp"
)

// Action descriptors (intent). Grouped to the §4 confirm descriptors.
const (
	descBookPublish = "book.publish" // chapter publish / unpublish
	descBookDelete  = "book.delete"  // book/chapter delete (trash) + purge
	descBookMedia   = "book.media"   // priced: set_cover / media_generate / audio_generate
)

// actionTokenTTL — the human has time to read the card and confirm.
const actionTokenTTL = 10 * time.Minute

// actionPayload is the opaque action-spec captured at propose time. It carries
// the precise operation so confirm can re-validate + execute without trusting a
// re-supplied arg. op disambiguates within a descriptor (e.g. publish vs unpublish).
type actionPayload struct {
	Op          string `json:"op"`                     // publish|unpublish|delete_book|delete_chapter|purge_book|purge_chapter|set_cover|media_generate|audio_generate
	ChapterID   string `json:"chapter_id,omitempty"`   // chapter-scoped ops
	EstimateUSD string `json:"estimate_usd,omitempty"` // priced ops — shown on the card
}

// confirmCardOut is the propose result fed to the LLM and rendered by the FE
// confirm card (descriptor-keyed). The FE re-fetches current-state rows via
// /v1/book/actions/preview before the human confirms.
type confirmCardOut struct {
	ConfirmToken string `json:"confirm_token"`
	Descriptor   string `json:"descriptor"`
	Title        string `json:"title"`
	Domain       string `json:"domain"` // "book" — selects the FE confirm endpoint (C-CONFIRM)
	Destructive  bool   `json:"destructive"`
	EstimateUSD  string `json:"estimate_usd,omitempty"`
	ExpiresAt    string `json:"expires_at"`
}

// mintBookActionCard mints a kit confirm token bound to user+resource(book)+
// descriptor+payload and returns the confirm card. An empty token (missing
// secret) fails closed — no proposal can proceed.
func (s *Server) mintBookActionCard(userID, bookID uuid.UUID, descriptor, title string, p actionPayload, destructive bool) (*mcp.CallToolResult, confirmCardOut, error) {
	tok, err := lwmcp.MintConfirmToken(s.cfg.ConfirmTokenSigningSecret, userID, bookID, descriptor, p, actionTokenTTL)
	if err != nil {
		return nil, confirmCardOut{}, errors.New("confirmation is unavailable")
	}
	return nil, confirmCardOut{
		ConfirmToken: tok, Descriptor: descriptor, Title: title, Domain: "book",
		Destructive: destructive, EstimateUSD: p.EstimateUSD,
		ExpiresAt: time.Now().Add(actionTokenTTL).UTC().Format(time.RFC3339),
	}, nil
}

// registerActionProposeTools registers the Tier-W propose tools on the MCP
// server. Each is tier=W, scope=book; each MINTS only.
func (s *Server) registerActionProposeTools(srv *mcp.Server) {
	addTool(srv, "book_chapter_publish",
		"Propose PUBLISHING a chapter (snapshot the draft as canon). High-impact: "+
			"returns a confirm_token + card a human must confirm — it does NOT publish. "+
			"Pass the confirm_token to confirm_action (domain=book).",
		lwmcp.NewToolMeta(lwmcp.TierW, lwmcp.ScopeBook, nil, []string{"publish", "canonize", "make canon"}),
		s.toolProposePublish)

	addTool(srv, "book_chapter_unpublish",
		"Propose UNPUBLISHING a chapter (revert canon → draft). Returns a "+
			"confirm_token + card a human must confirm via confirm_action (domain=book).",
		lwmcp.NewToolMeta(lwmcp.TierW, lwmcp.ScopeBook, nil, []string{"unpublish", "revert canon", "withdraw"}),
		s.toolProposeUnpublish)

	addTool(srv, "book_delete",
		"Propose DELETING a book (move to trash; recoverable until purge). Returns "+
			"a confirm_token + card a human must confirm via confirm_action (domain=book).",
		lwmcp.NewToolMeta(lwmcp.TierW, lwmcp.ScopeBook, nil, []string{"delete book", "trash book", "remove book"}),
		s.toolProposeBookDelete)

	addTool(srv, "book_chapter_delete",
		"Propose DELETING a chapter (move to trash; recoverable until purge). "+
			"Returns a confirm_token + card a human must confirm via confirm_action.",
		lwmcp.NewToolMeta(lwmcp.TierW, lwmcp.ScopeBook, nil, []string{"delete chapter", "trash chapter", "remove chapter"}),
		s.toolProposeChapterDelete)

	addTool(srv, "book_purge",
		"Propose PERMANENTLY purging a trashed book (irreversible). Returns a "+
			"confirm_token + card a human must explicitly confirm via confirm_action.",
		lwmcp.NewToolMeta(lwmcp.TierW, lwmcp.ScopeBook, nil, []string{"purge book", "permanently delete book"}),
		s.toolProposeBookPurge)

	addTool(srv, "book_chapter_purge",
		"Propose PERMANENTLY purging a trashed chapter (irreversible). Returns a "+
			"confirm_token + card a human must explicitly confirm via confirm_action.",
		lwmcp.NewToolMeta(lwmcp.TierW, lwmcp.ScopeBook, nil, []string{"purge chapter", "permanently delete chapter"}),
		s.toolProposeChapterPurge)

	addTool(srv, "book_set_cover",
		"Propose generating/replacing a book cover image (priced). Returns a "+
			"confirm_token + cost estimate a human must confirm via confirm_action.",
		lwmcp.NewToolMeta(lwmcp.TierW, lwmcp.ScopeBook, nil, []string{"cover", "book cover", "cover art"}),
		s.toolProposeSetCover)

	addTool(srv, "book_media_generate",
		"Propose generating chapter media/illustration (priced). Returns a "+
			"confirm_token + cost estimate a human must confirm via confirm_action.",
		lwmcp.NewToolMeta(lwmcp.TierW, lwmcp.ScopeBook, nil, []string{"illustration", "generate image", "art"}),
		s.toolProposeMediaGenerate)

	addTool(srv, "book_audio_generate",
		"Propose generating chapter audio narration (priced). Returns a "+
			"confirm_token + cost estimate a human must confirm via confirm_action.",
		lwmcp.NewToolMeta(lwmcp.TierW, lwmcp.ScopeBook, nil, []string{"audio", "narration", "tts", "read aloud"}),
		s.toolProposeAudioGenerate)
}

// ── propose tool args ─────────────────────────────────────────────────────────

type chapterActionIn struct {
	BookID    string `json:"book_id" jsonschema:"the book the chapter belongs to (UUID)"`
	ChapterID string `json:"chapter_id" jsonschema:"the chapter to act on (UUID)"`
}
type bookActionIn struct {
	BookID string `json:"book_id" jsonschema:"the book to act on (UUID)"`
}

// proposeChapterAction is the shared mint path for chapter-scoped W ops. It
// resolves identity, checks the grant, verifies the chapter belongs to the book,
// and mints the card.
func (s *Server) proposeChapterAction(ctx context.Context, in chapterActionIn, need GrantLevel, descriptor, op, title string, destructive bool) (*mcp.CallToolResult, confirmCardOut, error) {
	userID, ok := mcpUserID(ctx)
	if !ok {
		return nil, confirmCardOut{}, errMissingIdentity
	}
	bookID, err := uuid.Parse(in.BookID)
	if err != nil {
		return nil, confirmCardOut{}, errors.New("book_id must be a UUID")
	}
	chID, err := uuid.Parse(in.ChapterID)
	if err != nil {
		return nil, confirmCardOut{}, errors.New("chapter_id must be a UUID")
	}
	if _, err := s.mcpRequireGrant(ctx, bookID, userID, need); err != nil {
		return nil, confirmCardOut{}, mcpOwnershipError(err)
	}
	// Mint-time existence check so the agent never shows a card destined to 404.
	var exists bool
	if err := s.pool.QueryRow(ctx, `SELECT EXISTS(SELECT 1 FROM chapters WHERE id=$1 AND book_id=$2 AND lifecycle_state!='purge_pending')`, chID, bookID).Scan(&exists); err != nil || !exists {
		return nil, confirmCardOut{}, errBookNotAccessible
	}
	return s.mintBookActionCard(userID, bookID, descriptor, title, actionPayload{Op: op, ChapterID: chID.String()}, destructive)
}

func (s *Server) proposeBookAction(ctx context.Context, in bookActionIn, need GrantLevel, descriptor, op, title string, destructive bool) (*mcp.CallToolResult, confirmCardOut, error) {
	userID, ok := mcpUserID(ctx)
	if !ok {
		return nil, confirmCardOut{}, errMissingIdentity
	}
	bookID, err := uuid.Parse(in.BookID)
	if err != nil {
		return nil, confirmCardOut{}, errors.New("book_id must be a UUID")
	}
	if _, err := s.mcpRequireGrant(ctx, bookID, userID, need); err != nil {
		return nil, confirmCardOut{}, mcpOwnershipError(err)
	}
	return s.mintBookActionCard(userID, bookID, descriptor, title, actionPayload{Op: op}, destructive)
}

func (s *Server) toolProposePublish(ctx context.Context, _ *mcp.CallToolRequest, in chapterActionIn) (*mcp.CallToolResult, confirmCardOut, error) {
	return s.proposeChapterAction(ctx, in, GrantEdit, descBookPublish, "publish", "Publish chapter (canonize)", false)
}
func (s *Server) toolProposeUnpublish(ctx context.Context, _ *mcp.CallToolRequest, in chapterActionIn) (*mcp.CallToolResult, confirmCardOut, error) {
	return s.proposeChapterAction(ctx, in, GrantEdit, descBookPublish, "unpublish", "Unpublish chapter (revert canon)", false)
}
func (s *Server) toolProposeBookDelete(ctx context.Context, _ *mcp.CallToolRequest, in bookActionIn) (*mcp.CallToolResult, confirmCardOut, error) {
	// Book-level lifecycle is owner-only (E0-2).
	return s.proposeBookAction(ctx, in, GrantOwner, descBookDelete, "delete_book", "Delete book (move to trash)", true)
}
func (s *Server) toolProposeChapterDelete(ctx context.Context, _ *mcp.CallToolRequest, in chapterActionIn) (*mcp.CallToolResult, confirmCardOut, error) {
	return s.proposeChapterAction(ctx, in, GrantEdit, descBookDelete, "delete_chapter", "Delete chapter (move to trash)", true)
}
func (s *Server) toolProposeBookPurge(ctx context.Context, _ *mcp.CallToolRequest, in bookActionIn) (*mcp.CallToolResult, confirmCardOut, error) {
	return s.proposeBookAction(ctx, in, GrantOwner, descBookDelete, "purge_book", "Permanently purge book (irreversible)", true)
}
func (s *Server) toolProposeChapterPurge(ctx context.Context, _ *mcp.CallToolRequest, in chapterActionIn) (*mcp.CallToolResult, confirmCardOut, error) {
	return s.proposeChapterAction(ctx, in, GrantManage, descBookDelete, "purge_chapter", "Permanently purge chapter (irreversible)", true)
}

// Priced ops — mint a token + a (placeholder) estimate. Execution of the actual
// generation is the existing browser route's job (multipart/streaming/llmgw);
// the confirm route returns an "open the UI" outcome for these (see confirm).
func (s *Server) toolProposeSetCover(ctx context.Context, _ *mcp.CallToolRequest, in bookActionIn) (*mcp.CallToolResult, confirmCardOut, error) {
	userID, ok := mcpUserID(ctx)
	if !ok {
		return nil, confirmCardOut{}, errMissingIdentity
	}
	bookID, err := uuid.Parse(in.BookID)
	if err != nil {
		return nil, confirmCardOut{}, errors.New("book_id must be a UUID")
	}
	if _, err := s.mcpRequireGrant(ctx, bookID, userID, GrantEdit); err != nil {
		return nil, confirmCardOut{}, mcpOwnershipError(err)
	}
	return s.mintBookActionCard(userID, bookID, descBookMedia, "Generate book cover (priced)",
		actionPayload{Op: "set_cover", EstimateUSD: "~0.04"}, false)
}
func (s *Server) toolProposeMediaGenerate(ctx context.Context, _ *mcp.CallToolRequest, in chapterActionIn) (*mcp.CallToolResult, confirmCardOut, error) {
	return s.proposeChapterAction(ctx, in, GrantEdit, descBookMedia, "media_generate", "Generate chapter illustration (priced)", false)
}
func (s *Server) toolProposeAudioGenerate(ctx context.Context, _ *mcp.CallToolRequest, in chapterActionIn) (*mcp.CallToolResult, confirmCardOut, error) {
	return s.proposeChapterAction(ctx, in, GrantEdit, descBookMedia, "audio_generate", "Generate chapter audio (priced)", false)
}

// ── NET-NEW token routes: /v1/book/actions/{preview,confirm} ──────────────────
// Both are reachable ONLY with the user's browser JWT (requireUserID); the MCP
// mint path can never call them. confirm is the single write path; preview never
// consumes the token.

// registerActionRoutes mounts the two NET-NEW per-domain action routes. Called
// from Router(). Kept here (not in server.go) so the whole class-C spine lives
// in one file.
func (s *Server) registerActionRoutes(mount func(method, pattern string, h http.HandlerFunc)) {
	mount(http.MethodGet, "/v1/book/actions/preview", s.previewBookAction)
	mount(http.MethodPost, "/v1/book/actions/confirm", s.confirmBookAction)
}

// decodeActionToken verifies a confirm token from the request (query `token` for
// preview, JSON `confirm_token` for confirm) and re-checks the bound user matches
// the live JWT caller. Writes the 4xx itself and returns ok=false on failure.
func (s *Server) decodeActionToken(w http.ResponseWriter, userID uuid.UUID, tok string) (lwmcp.ConfirmClaims, bool) {
	tok = strings.TrimSpace(tok)
	if tok == "" {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "confirm_token is required")
		return lwmcp.ConfirmClaims{}, false
	}
	claims, err := lwmcp.VerifyConfirmToken(s.cfg.ConfirmTokenSigningSecret, tok)
	if errors.Is(err, lwmcp.ErrConfirmTokenExpired) {
		writeError(w, http.StatusUnprocessableEntity, "BOOK_ACTION_TOKEN", "confirmation expired — propose again")
		return lwmcp.ConfirmClaims{}, false
	}
	if err != nil {
		writeError(w, http.StatusUnprocessableEntity, "BOOK_ACTION_TOKEN", "invalid confirmation")
		return lwmcp.ConfirmClaims{}, false
	}
	// Bind to the proposing user — a different signed-in user cannot redeem it
	// even with the string (checked before any effect).
	if claims.UserID != userID {
		writeError(w, http.StatusForbidden, "BOOK_FORBIDDEN", "confirmation not valid for this user")
		return lwmcp.ConfirmClaims{}, false
	}
	return claims, true
}

// previewBookAction — GET /v1/book/actions/preview?token= . JWT-gated, read-only,
// NEVER consumes the token. Re-renders the card from current state so the human
// confirms against what is true now.
func (s *Server) previewBookAction(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "BOOK_FORBIDDEN", "unauthorized")
		return
	}
	claims, ok := s.decodeActionToken(w, userID, r.URL.Query().Get("token"))
	if !ok {
		return
	}
	// Re-check the grant at preview time (defense in depth).
	need := neededGrantFor(claims.Descriptor, payloadOp(claims))
	if _, err := s.mcpRequireGrant(r.Context(), claims.ResourceID, userID, need); err != nil {
		writeError(w, http.StatusNotFound, "BOOK_NOT_FOUND", "not accessible")
		return
	}
	var p actionPayload
	_ = json.Unmarshal(claims.Payload, &p)
	writeJSON(w, http.StatusOK, map[string]any{
		"descriptor":   claims.Descriptor,
		"op":           p.Op,
		"book_id":      claims.ResourceID,
		"chapter_id":   nullableString(p.ChapterID),
		"estimate_usd": nullableString(p.EstimateUSD),
		"destructive":  isDestructiveOp(p.Op),
	})
}

// confirmBookAction — POST /v1/book/actions/confirm . JWT-gated; THE only write
// path. Order: verify token → re-check grant → re-validate + execute the bound op.
func (s *Server) confirmBookAction(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "BOOK_FORBIDDEN", "unauthorized")
		return
	}
	var body struct {
		ConfirmToken string `json:"confirm_token"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "invalid payload")
		return
	}
	claims, ok := s.decodeActionToken(w, userID, body.ConfirmToken)
	if !ok {
		return
	}
	var p actionPayload
	if err := json.Unmarshal(claims.Payload, &p); err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "bad proposal payload")
		return
	}
	need := neededGrantFor(claims.Descriptor, p.Op)
	if _, err := s.mcpRequireGrant(r.Context(), claims.ResourceID, userID, need); err != nil {
		// Uniform deny (no oracle).
		writeError(w, http.StatusNotFound, "BOOK_NOT_FOUND", "not accessible")
		return
	}
	// Single-use: claim the token hash NOW — after verify + authorize, BEFORE the
	// effect (HIGH /review-impl). A REPLAY of a still-valid token (within the
	// 10-min TTL) hits the PK → 0 rows → refused, so the effect (publish revision +
	// chapter.published outbox event, delete, etc.) runs at most once per token.
	claimed, err := s.consumeBookActionToken(r.Context(), actionTokenHash(body.ConfirmToken), time.Unix(claims.Exp, 0))
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "confirmation failed")
		return
	}
	if !claimed {
		writeError(w, http.StatusUnprocessableEntity, "BOOK_ACTION_TOKEN", "already confirmed — propose again")
		return
	}
	s.executeBookAction(w, r, userID, claims.ResourceID, claims.Descriptor, p)
}

// actionTokenHash is the single-use ledger key for a stateless confirm token (the
// kit token carries no jti). SHA-256 over the full token string.
func actionTokenHash(tok string) string {
	sum := sha256.Sum256([]byte(tok))
	return hex.EncodeToString(sum[:])
}

// consumeBookActionToken records the token hash, enforcing single-use. Returns
// claimed=true the first time; a replay hits the PK (ON CONFLICT DO NOTHING → 0
// rows) → claimed=false. Mirrors provider-registry consumeSettingsToken.
func (s *Server) consumeBookActionToken(ctx context.Context, hash string, exp time.Time) (bool, error) {
	tag, err := s.pool.Exec(ctx,
		`INSERT INTO book_consumed_tokens (token_hash, exp) VALUES ($1,$2)
		 ON CONFLICT (token_hash) DO NOTHING`, hash, exp)
	if err != nil {
		return false, err
	}
	return tag.RowsAffected() > 0, nil
}

// executeBookAction dispatches a verified action to its effect. The descriptor
// is the confused-deputy guard: each effect re-asserts that the payload op
// belongs to the descriptor it was minted under.
func (s *Server) executeBookAction(w http.ResponseWriter, r *http.Request, userID, bookID uuid.UUID, descriptor string, p actionPayload) {
	ctx := r.Context()
	switch descriptor {
	case descBookPublish:
		s.effectPublish(w, ctx, userID, bookID, p)
	case descBookDelete:
		s.effectDelete(w, ctx, bookID, p)
	case descBookMedia:
		// Op-whitelist symmetry with effectPublish/effectDelete: a media token may
		// only carry a priced media op. Reject anything else (the confused-deputy
		// guard already pins the descriptor; this re-asserts the op within it).
		switch p.Op {
		case "set_cover", "media_generate", "audio_generate":
		default:
			writeError(w, http.StatusUnprocessableEntity, "BOOK_ACTION_TOKEN", "op does not match descriptor")
			return
		}
		// Priced generation runs through the existing browser routes (multipart /
		// streaming / llmgw). The MCP confirm acknowledges + directs the human to
		// the UI rather than half-running a priced job here (scope honesty, H4).
		writeJSON(w, http.StatusOK, map[string]any{
			"outcome":    "open_ui",
			"op":         p.Op,
			"book_id":    bookID,
			"chapter_id": nullableString(p.ChapterID),
			"message":    "confirmed — open the book in the app to run this priced generation",
		})
	default:
		writeError(w, http.StatusUnprocessableEntity, "BOOK_ACTION_TOKEN", "unknown action")
	}
}

func (s *Server) effectPublish(w http.ResponseWriter, ctx context.Context, userID, bookID uuid.UUID, p actionPayload) {
	chID, err := uuid.Parse(p.ChapterID)
	if err != nil {
		writeError(w, http.StatusUnprocessableEntity, "BOOK_ACTION_TOKEN", "bad chapter ref")
		return
	}
	switch p.Op {
	case "publish":
		revID, perr := s.mcpPublishChapter(ctx, userID, bookID, chID)
		if perr != nil {
			s.writeActionEffectError(w, perr)
			return
		}
		writeJSON(w, http.StatusOK, map[string]any{"outcome": "action_done", "op": "publish", "chapter_id": chID, "revision_id": revID})
	case "unpublish":
		if perr := s.mcpUnpublishChapter(ctx, bookID, chID); perr != nil {
			s.writeActionEffectError(w, perr)
			return
		}
		writeJSON(w, http.StatusOK, map[string]any{"outcome": "action_done", "op": "unpublish", "chapter_id": chID})
	default:
		writeError(w, http.StatusUnprocessableEntity, "BOOK_ACTION_TOKEN", "op does not match descriptor")
	}
}

func (s *Server) effectDelete(w http.ResponseWriter, ctx context.Context, bookID uuid.UUID, p actionPayload) {
	switch p.Op {
	case "delete_book":
		if err := s.mcpTransitionBook(ctx, bookID, "trashed"); err != nil {
			s.writeActionEffectError(w, err)
			return
		}
		writeJSON(w, http.StatusOK, map[string]any{"outcome": "action_done", "op": "delete_book", "book_id": bookID})
	case "purge_book":
		if err := s.mcpTransitionBook(ctx, bookID, "purge_pending"); err != nil {
			s.writeActionEffectError(w, err)
			return
		}
		writeJSON(w, http.StatusOK, map[string]any{"outcome": "action_done", "op": "purge_book", "book_id": bookID})
	case "delete_chapter", "purge_chapter":
		chID, err := uuid.Parse(p.ChapterID)
		if err != nil {
			writeError(w, http.StatusUnprocessableEntity, "BOOK_ACTION_TOKEN", "bad chapter ref")
			return
		}
		target := "trashed"
		if p.Op == "purge_chapter" {
			target = "purge_pending"
		}
		if err := s.mcpTransitionChapter(ctx, bookID, chID, target); err != nil {
			s.writeActionEffectError(w, err)
			return
		}
		writeJSON(w, http.StatusOK, map[string]any{"outcome": "action_done", "op": p.Op, "book_id": bookID, "chapter_id": chID})
	default:
		writeError(w, http.StatusUnprocessableEntity, "BOOK_ACTION_TOKEN", "op does not match descriptor")
	}
}

// writeActionEffectError maps a sentinel from an effect to the right status.
func (s *Server) writeActionEffectError(w http.ResponseWriter, err error) {
	switch {
	case errors.Is(err, errActionTargetGone):
		writeError(w, http.StatusUnprocessableEntity, "BOOK_ACTION_TOKEN", "the target no longer exists — propose again")
	case errors.Is(err, errActionBadState):
		writeError(w, http.StatusConflict, "BOOK_INVALID_LIFECYCLE", "the target is not in the right state for this action")
	default:
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "action failed")
	}
}

var (
	errActionTargetGone = errors.New("action target gone")
	errActionBadState   = errors.New("action bad state")
)

// neededGrantFor maps a descriptor+op to the grant level confirm/preview require.
func neededGrantFor(descriptor, op string) GrantLevel {
	switch op {
	case "delete_book", "purge_book":
		return GrantOwner
	case "purge_chapter":
		return GrantManage
	default:
		return GrantEdit
	}
}

func payloadOp(claims lwmcp.ConfirmClaims) string {
	var p actionPayload
	_ = json.Unmarshal(claims.Payload, &p)
	return p.Op
}

func isDestructiveOp(op string) bool {
	switch op {
	case "delete_book", "delete_chapter", "purge_book", "purge_chapter":
		return true
	default:
		return false
	}
}

// ── effects reusing book-service write logic (re-validated at confirm) ────────

func (s *Server) mcpPublishChapter(ctx context.Context, caller, bookID, chID uuid.UUID) (uuid.UUID, error) {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return uuid.Nil, err
	}
	defer tx.Rollback(ctx)
	var curr int64
	var body json.RawMessage
	var format string
	err = tx.QueryRow(ctx, `
SELECT d.draft_version, d.body, d.draft_format FROM chapter_drafts d JOIN chapters c ON c.id=d.chapter_id
WHERE d.chapter_id=$1 AND c.book_id=$2 AND c.lifecycle_state='active' FOR UPDATE OF d`, chID, bookID).Scan(&curr, &body, &format)
	if errors.Is(err, pgx.ErrNoRows) {
		return uuid.Nil, errActionTargetGone
	}
	if err != nil {
		return uuid.Nil, err
	}
	// Empty-prose guard — union of the editor `_text` projection AND standard
	// tiptap nested text leaves ($.**.text); see publishChapter for the rationale
	// (the `_text`-only selector false-rejected standard tiptap bodies).
	var prose string
	_ = tx.QueryRow(ctx, `
SELECT COALESCE((
  SELECT string_agg(t #>> '{}', '') FROM jsonb_path_query(($1)::jsonb, '$.content[*]._text') AS x(t)
), '') || COALESCE((
  SELECT string_agg(t #>> '{}', '') FROM jsonb_path_query(($1)::jsonb, '$.**.text') AS y(t)
), '')`, body).Scan(&prose)
	if strings.TrimSpace(prose) == "" {
		return uuid.Nil, errActionBadState
	}
	var revID uuid.UUID
	if err := tx.QueryRow(ctx, `
INSERT INTO chapter_revisions(chapter_id, body, body_format, message, author_user_id)
VALUES($1,$2,$3,'publish',$4) RETURNING id`, chID, body, format, caller).Scan(&revID); err != nil {
		return uuid.Nil, err
	}
	if _, err := tx.Exec(ctx, `
UPDATE chapters SET editorial_status='published', published_revision_id=$2,
  draft_revision_count=draft_revision_count+1, updated_at=now() WHERE id=$1`, chID, revID); err != nil {
		return uuid.Nil, err
	}
	if err := insertOutboxEvent(ctx, tx, "chapter.published", chID, map[string]any{"book_id": bookID, "chapter_id": chID, "revision_id": revID}); err != nil {
		return uuid.Nil, err
	}
	if err := tx.Commit(ctx); err != nil {
		return uuid.Nil, err
	}
	return revID, nil
}

func (s *Server) mcpUnpublishChapter(ctx context.Context, bookID, chID uuid.UUID) error {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx)
	ct, err := tx.Exec(ctx, `
UPDATE chapters SET editorial_status='draft', published_revision_id=NULL, updated_at=now()
WHERE id=$1 AND book_id=$2 AND lifecycle_state='active'`, chID, bookID)
	if err != nil {
		return err
	}
	if ct.RowsAffected() == 0 {
		return errActionTargetGone
	}
	if err := insertOutboxEvent(ctx, tx, "chapter.unpublished", chID, map[string]any{"book_id": bookID, "chapter_id": chID}); err != nil {
		return err
	}
	return tx.Commit(ctx)
}

// mcpTransitionBook applies a book lifecycle transition (trashed|purge_pending),
// enforcing the same state preconditions as transitionBookLifecycle.
func (s *Server) mcpTransitionBook(ctx context.Context, bookID uuid.UUID, target string) error {
	var lifecycle string
	if err := s.pool.QueryRow(ctx, `SELECT lifecycle_state FROM books WHERE id=$1`, bookID).Scan(&lifecycle); err != nil {
		return errActionTargetGone
	}
	switch target {
	case "trashed":
		if lifecycle != "active" {
			return errActionBadState
		}
		_, _ = s.pool.Exec(ctx, `UPDATE books SET lifecycle_state='trashed', trashed_at=now(), updated_at=now() WHERE id=$1`, bookID)
		_, _ = s.pool.Exec(ctx, `UPDATE chapters SET lifecycle_state='trashed', trashed_at=now(), updated_at=now() WHERE book_id=$1 AND lifecycle_state='active'`, bookID)
	case "purge_pending":
		if lifecycle != "trashed" {
			return errActionBadState
		}
		_, _ = s.pool.Exec(ctx, `UPDATE books SET lifecycle_state='purge_pending', purge_eligible_at=now(), updated_at=now() WHERE id=$1`, bookID)
		_, _ = s.pool.Exec(ctx, `UPDATE chapters SET lifecycle_state='purge_pending', purge_eligible_at=now(), updated_at=now() WHERE book_id=$1`, bookID)
	default:
		return errActionBadState
	}
	return nil
}

// mcpTransitionChapter applies a chapter lifecycle transition.
func (s *Server) mcpTransitionChapter(ctx context.Context, bookID, chID uuid.UUID, target string) error {
	var bState, cState string
	if err := s.pool.QueryRow(ctx, `
SELECT b.lifecycle_state,c.lifecycle_state FROM books b JOIN chapters c ON c.book_id=b.id
WHERE b.id=$1 AND c.id=$2`, bookID, chID).Scan(&bState, &cState); err != nil {
		return errActionTargetGone
	}
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx)
	switch target {
	case "trashed":
		if bState != "active" || cState != "active" {
			return errActionBadState
		}
		_, _ = tx.Exec(ctx, `UPDATE chapters SET lifecycle_state='trashed', trashed_at=now(), updated_at=now() WHERE id=$1`, chID)
		if err := insertOutboxEvent(ctx, tx, "chapter.trashed", chID, map[string]any{"book_id": bookID}); err != nil {
			return err
		}
	case "purge_pending":
		if cState != "trashed" {
			return errActionBadState
		}
		_, _ = tx.Exec(ctx, `UPDATE chapters SET lifecycle_state='purge_pending', purge_eligible_at=now(), updated_at=now() WHERE id=$1`, chID)
		if err := insertOutboxEvent(ctx, tx, "chapter.deleted", chID, map[string]any{"book_id": bookID}); err != nil {
			return err
		}
	default:
		return errActionBadState
	}
	return tx.Commit(ctx)
}

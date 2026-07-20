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
	"log/slog"
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
//
// book_chapter_delete additionally supports the ext-tasks DURABLE GATE (spec
// docs/specs/2026-07-19-mcp-tasks-durable-gate.md, T3c): a tasks-capable client
// gets a durable input_required TASK (held in `actionTasks`) instead of a
// confirm_token, and drives it to completion via the `book_task_provide_input`
// tool — the executor runs the SAME trash transition the confirm route would,
// after re-binding the caller + re-checking the grant (defense-in-depth parity
// with confirmBookAction). A non-tasks client is unchanged (confirm_token). The
// store is per-server-instance in-memory; it persists across the propose and
// provide-input calls because NewStatelessHandler returns one *mcp.Server for the
// process (multi-replica ⇒ a persistent TaskStore, deferred: D-MCPTASKS-GO-STORE).
func (s *Server) registerActionProposeTools(srv *mcp.Server) {
	// The durable-gate store, bound to a resolver registry (descriptor → the write to
	// run on accept). The store persists only DATA ({descriptor, ownerUserID, payload});
	// the resolver is reconstructed by descriptor. PERSISTENT (Postgres `mcp_gate_tasks`)
	// so a propose on one replica + its accept on another (or after a restart/deploy)
	// resolve the same task exactly once (D-MCPTASKS-GO-STORE). book_chapter_delete's
	// resolver re-binds the caller + re-checks the grant (confirmBookAction parity).
	// One DISPATCHING resolver serves every book write descriptor (delete/trash/purge
	// via descBookDelete; publish/unpublish via descBookPublish) — it switches on the
	// payload op and calls the SAME underlying logic the /actions/confirm effects run.
	actionTasks := NewPgTaskStore(s.pool, lwmcp.TaskResolverRegistry{
		descBookDelete:  s.resolveBookAction,
		descBookPublish: s.resolveBookAction,
	})

	addTool(srv, "book_chapter_publish",
		"Propose PUBLISHING a chapter (snapshot the draft as canon). High-impact: "+
			"returns a confirm_token + card a human must confirm — it does NOT publish. "+
			"Pass the confirm_token to confirm_action (domain=book).",
		lwmcp.NewToolMeta(lwmcp.TierW, lwmcp.ScopeBook, nil, []string{"publish", "canonize", "make canon"}),
		s.toolProposePublishGated(actionTasks))

	addTool(srv, "book_chapter_unpublish",
		"Propose UNPUBLISHING a chapter (revert canon → draft). Returns a "+
			"confirm_token + card a human must confirm via confirm_action (domain=book).",
		lwmcp.NewToolMeta(lwmcp.TierW, lwmcp.ScopeBook, nil, []string{"unpublish", "revert canon", "withdraw"}),
		s.toolProposeUnpublishGated(actionTasks))

	// book_delete (agent-proposed book trash) REMOVED 2026-07-19 — deleting a whole
	// book is not an agent-invocable capability. Users delete a book directly via the
	// GUI (DELETE /v1/books/{id}); the agent has no path to it. The confirm-side
	// `delete_book` op remains defensively unreachable (no tool mints its token).

	addTool(srv, "book_chapter_delete",
		"Propose DELETING a chapter (move to trash; recoverable until purge). "+
			"Returns a confirm_token + card a human must confirm via confirm_action.",
		lwmcp.NewToolMeta(lwmcp.TierW, lwmcp.ScopeBook, nil, []string{"delete chapter", "trash chapter", "remove chapter"}),
		s.toolProposeChapterDelete(actionTasks))

	addTool(srv, "book_purge",
		"Propose PERMANENTLY purging a trashed book (irreversible). Returns a "+
			"confirm_token + card a human must explicitly confirm via confirm_action.",
		lwmcp.NewToolMeta(lwmcp.TierW, lwmcp.ScopeBook, nil, []string{"purge book", "permanently delete book"}),
		s.toolProposeBookPurgeGated(actionTasks))

	addTool(srv, "book_chapter_purge",
		"Propose PERMANENTLY purging a trashed chapter (irreversible). Returns a "+
			"confirm_token + card a human must explicitly confirm via confirm_action.",
		lwmcp.NewToolMeta(lwmcp.TierW, lwmcp.ScopeBook, nil, []string{"purge chapter", "permanently delete chapter"}),
		s.toolProposeChapterPurgeGated(actionTasks))

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

	// The input step for the durable gate (book_chapter_delete on a tasks-capable
	// client). Gateway-routed by name → the `book` prefix is required. The callerID
	// wrapper lets the kit owner-check BOTH accept + decline (the resolver only re-binds
	// on accept), so a stranger can't cancel another user's gate.
	lwmcp.RegisterTaskProvideInput(srv, actionTasks, "book", func(ctx context.Context) (string, bool) {
		u, ok := mcpUserID(ctx)
		if !ok {
			return "", false
		}
		return u.String(), true
	})
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

// ── durable-gate propose helpers (M3) — the write actions (publish/unpublish/
// delete/purge) run task-shaped: GateOrConfirm returns a durable input_required TASK
// for a tasks-capable client, else the SAME confirm_token card (no regression). The
// mint is kept as the fallback (side-effect-free HMAC). Priced tools (set_cover/media/
// audio) keep the plain mint path — their "confirm" only opens the UI, nothing to gate. ──

func (s *Server) proposeChapterActionGated(ctx context.Context, meta lwmcp.Meta, store lwmcp.TaskStore, in chapterActionIn, need GrantLevel, descriptor, op, title string, destructive bool) (*mcp.CallToolResult, any, error) {
	userID, ok := mcpUserID(ctx)
	if !ok {
		return nil, nil, errMissingIdentity
	}
	bookID, err := uuid.Parse(in.BookID)
	if err != nil {
		return nil, nil, errors.New("book_id must be a UUID")
	}
	chID, err := uuid.Parse(in.ChapterID)
	if err != nil {
		return nil, nil, errors.New("chapter_id must be a UUID")
	}
	if _, err := s.mcpRequireGrant(ctx, bookID, userID, need); err != nil {
		return nil, nil, mcpOwnershipError(err)
	}
	var exists bool
	if err := s.pool.QueryRow(ctx, `SELECT EXISTS(SELECT 1 FROM chapters WHERE id=$1 AND book_id=$2 AND lifecycle_state!='purge_pending')`, chID, bookID).Scan(&exists); err != nil || !exists {
		return nil, nil, errBookNotAccessible
	}
	_, card, cerr := s.mintBookActionCard(userID, bookID, descriptor, title, actionPayload{Op: op, ChapterID: chID.String()}, destructive)
	if cerr != nil {
		return nil, nil, cerr
	}
	payload := map[string]any{"op": op, "book_id": bookID.String(), "chapter_id": chID.String()}
	inputRequests := map[string]any{
		"descriptor": descriptor, "op": op, "title": title, "domain": "book",
		"book_id": bookID.String(), "chapter_id": chID.String(), "destructive": destructive,
	}
	out, err := lwmcp.GateOrConfirm(ctx, meta, store, descriptor, userID.String(), payload, inputRequests, func() any { return card }, 0)
	if err != nil {
		return nil, nil, err
	}
	return nil, out, nil
}

func (s *Server) proposeBookActionGated(ctx context.Context, meta lwmcp.Meta, store lwmcp.TaskStore, in bookActionIn, need GrantLevel, descriptor, op, title string, destructive bool) (*mcp.CallToolResult, any, error) {
	userID, ok := mcpUserID(ctx)
	if !ok {
		return nil, nil, errMissingIdentity
	}
	bookID, err := uuid.Parse(in.BookID)
	if err != nil {
		return nil, nil, errors.New("book_id must be a UUID")
	}
	if _, err := s.mcpRequireGrant(ctx, bookID, userID, need); err != nil {
		return nil, nil, mcpOwnershipError(err)
	}
	_, card, cerr := s.mintBookActionCard(userID, bookID, descriptor, title, actionPayload{Op: op}, destructive)
	if cerr != nil {
		return nil, nil, cerr
	}
	payload := map[string]any{"op": op, "book_id": bookID.String()}
	inputRequests := map[string]any{
		"descriptor": descriptor, "op": op, "title": title, "domain": "book",
		"book_id": bookID.String(), "destructive": destructive,
	}
	out, err := lwmcp.GateOrConfirm(ctx, meta, store, descriptor, userID.String(), payload, inputRequests, func() any { return card }, 0)
	if err != nil {
		return nil, nil, err
	}
	return nil, out, nil
}

// (publish/unpublish/purge propose tools are now the *Gated durable-gate variants
// below — the old mint-only versions were retired in M3.)

// toolProposeChapterDelete is the ext-tasks DURABLE-GATE variant of a KIND-C
// propose tool (T3c). Propose-time it resolves identity + checks the grant +
// verifies the chapter exists (exactly like proposeChapterAction). Then
// GateOrConfirm branches on the client's declared capability: a tasks-capable
// client gets a durable input_required task whose executor performs the trash
// transition on accept; every other client gets today's confirm_token card
// (proposeChapterAction's exact result), so nothing is stranded. The Out is `any`
// because the two branches return different shapes (a task handle vs a card).
func (s *Server) toolProposeChapterDelete(store lwmcp.TaskStore) func(context.Context, *mcp.CallToolRequest, chapterActionIn) (*mcp.CallToolResult, any, error) {
	return func(ctx context.Context, req *mcp.CallToolRequest, in chapterActionIn) (*mcp.CallToolResult, any, error) {
		return s.proposeChapterActionGated(ctx, req.Params.Meta, store, in, GrantEdit,
			descBookDelete, "delete_chapter", "Delete chapter (move to trash)", true)
	}
}

func (s *Server) toolProposePublishGated(store lwmcp.TaskStore) func(context.Context, *mcp.CallToolRequest, chapterActionIn) (*mcp.CallToolResult, any, error) {
	return func(ctx context.Context, req *mcp.CallToolRequest, in chapterActionIn) (*mcp.CallToolResult, any, error) {
		return s.proposeChapterActionGated(ctx, req.Params.Meta, store, in, GrantEdit,
			descBookPublish, "publish", "Publish chapter (canonize)", false)
	}
}

func (s *Server) toolProposeUnpublishGated(store lwmcp.TaskStore) func(context.Context, *mcp.CallToolRequest, chapterActionIn) (*mcp.CallToolResult, any, error) {
	return func(ctx context.Context, req *mcp.CallToolRequest, in chapterActionIn) (*mcp.CallToolResult, any, error) {
		return s.proposeChapterActionGated(ctx, req.Params.Meta, store, in, GrantEdit,
			descBookPublish, "unpublish", "Unpublish chapter (revert canon → draft)", false)
	}
}

func (s *Server) toolProposeChapterPurgeGated(store lwmcp.TaskStore) func(context.Context, *mcp.CallToolRequest, chapterActionIn) (*mcp.CallToolResult, any, error) {
	return func(ctx context.Context, req *mcp.CallToolRequest, in chapterActionIn) (*mcp.CallToolResult, any, error) {
		return s.proposeChapterActionGated(ctx, req.Params.Meta, store, in, GrantManage,
			descBookDelete, "purge_chapter", "Permanently purge chapter (irreversible)", true)
	}
}

func (s *Server) toolProposeBookPurgeGated(store lwmcp.TaskStore) func(context.Context, *mcp.CallToolRequest, bookActionIn) (*mcp.CallToolResult, any, error) {
	return func(ctx context.Context, req *mcp.CallToolRequest, in bookActionIn) (*mcp.CallToolResult, any, error) {
		return s.proposeBookActionGated(ctx, req.Params.Meta, store, in, GrantOwner,
			descBookDelete, "purge_book", "Permanently purge book (irreversible)", true)
	}
}

// grantForOp is the grant level a book action's ACCEPT re-checks (defense-in-depth,
// derived from the op so the resolver never trusts a weaker level than propose-time).
func grantForOp(op string) GrantLevel {
	switch op {
	case "purge_book", "delete_book":
		return GrantOwner
	case "purge_chapter":
		return GrantManage
	default: // publish, unpublish, delete_chapter
		return GrantEdit
	}
}

// resolveBookAction is the durable-gate resolver for ALL book write descriptors
// (descBookDelete / descBookPublish), registered at startup. It runs ONLY on accept,
// reconstructed on any replica from the persisted {ownerUserID, payload} — no closure. It
// re-binds the caller to the proposing user + re-checks the op-appropriate grant
// (confirmBookAction defense-in-depth: the accept arrives on a later request, the grant may
// have been revoked meanwhile). The task single-winner guard = single-use (consumeBookActionToken
// equivalent). It dispatches by op to the SAME underlying logic the /actions/confirm effects run.
func (s *Server) resolveBookAction(exctx context.Context, ownerUserID string, payload map[string]any, _ map[string]any) (any, error) {
	caller, ok := mcpUserID(exctx)
	if !ok || caller.String() != ownerUserID {
		return nil, errBookNotAccessible // caller-binding parity with claims.UserID==caller
	}
	owner, err := uuid.Parse(ownerUserID)
	if err != nil {
		return nil, errBookNotAccessible
	}
	bookID, err := uuid.Parse(asString(payload["book_id"]))
	if err != nil {
		return nil, errors.New("book_id must be a UUID")
	}
	op := asString(payload["op"])
	if _, err := s.mcpRequireGrant(exctx, bookID, owner, grantForOp(op)); err != nil {
		return nil, mcpOwnershipError(err)
	}
	chapter := func() (uuid.UUID, error) { return uuid.Parse(asString(payload["chapter_id"])) }
	switch op {
	case "publish":
		chID, err := chapter()
		if err != nil {
			return nil, errors.New("chapter_id must be a UUID")
		}
		revID, counts, perr := s.mcpPublishChapter(exctx, owner, bookID, chID)
		if perr != nil {
			return nil, perr
		}
		return map[string]any{"outcome": "action_done", "op": "publish", "book_id": bookID.String(),
			"chapter_id": chID.String(), "revision_id": revID.String(), "reparse": counts}, nil
	case "unpublish":
		chID, err := chapter()
		if err != nil {
			return nil, errors.New("chapter_id must be a UUID")
		}
		if perr := s.mcpUnpublishChapter(exctx, bookID, chID); perr != nil {
			return nil, perr
		}
		return map[string]any{"outcome": "action_done", "op": "unpublish",
			"book_id": bookID.String(), "chapter_id": chID.String()}, nil
	case "delete_chapter", "purge_chapter":
		chID, err := chapter()
		if err != nil {
			return nil, errors.New("chapter_id must be a UUID")
		}
		target := "trashed"
		if op == "purge_chapter" {
			target = "purge_pending"
		}
		if err := s.mcpTransitionChapter(exctx, bookID, chID, target); err != nil {
			return nil, err
		}
		return map[string]any{"outcome": "action_done", "op": op,
			"book_id": bookID.String(), "chapter_id": chID.String()}, nil
	case "delete_book", "purge_book":
		target := "trashed"
		if op == "purge_book" {
			target = "purge_pending"
		}
		if err := s.mcpTransitionBook(exctx, bookID, target); err != nil {
			return nil, err
		}
		return map[string]any{"outcome": "action_done", "op": op, "book_id": bookID.String()}, nil
	default:
		return nil, errors.New("op does not match descriptor")
	}
}

// asString reads a string field from a payload map (empty string if absent/non-string).
func asString(v any) string {
	s, _ := v.(string)
	return s
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

// resolveConfirmCaller returns the redeeming user's ID for the confirm route,
// trusting EITHER a valid Bearer JWT (browser UI) or a trusted internal-service
// envelope (X-Internal-Token, constant-time compare, + X-User-Id) — the shape
// auth-service's public-MCP confirm-replay (`mcp_approvals.go::replayConfirm`)
// sends, since it is a trusted internal caller and can never present the owner's
// Bearer JWT. Mirrors glossary-service's identical retrofit
// (action_confirm.go::resolveConfirmCaller) and composition/translation/
// knowledge-service's existing Python dual-auth pattern (D-PMCP-WORKER-CARRIER).
// Found live 2026-07-08: this route 401'd every confirm-replay unconditionally.
// The internal-token branch is checked first and fails closed (never falls
// through to the Bearer path) if X-User-Id is missing/malformed.
func (s *Server) resolveConfirmCaller(r *http.Request) (uuid.UUID, bool) {
	return lwmcp.ResolveEnvelopeOrBearerCaller(r, s.cfg.InternalServiceToken, s.requireUserID)
}

// confirmBookAction — POST /v1/book/actions/confirm . JWT- or internal-envelope-
// gated (see resolveConfirmCaller); THE only write path. Order: verify token →
// re-check grant → re-validate + execute the bound op.
func (s *Server) confirmBookAction(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.resolveConfirmCaller(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "BOOK_FORBIDDEN", "unauthorized")
		return
	}
	// Token comes from the `token` query param (auth-service's internal
	// confirm-replay, nil body) or the JSON body (the browser UI).
	confirmToken := strings.TrimSpace(r.URL.Query().Get("token"))
	if confirmToken == "" {
		var body struct {
			ConfirmToken string `json:"confirm_token"`
		}
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "invalid payload")
			return
		}
		confirmToken = body.ConfirmToken
	}
	claims, ok := s.decodeActionToken(w, userID, confirmToken)
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
	claimed, err := s.consumeBookActionToken(r.Context(), actionTokenHash(confirmToken), time.Unix(claims.Exp, 0))
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
		revID, counts, perr := s.mcpPublishChapter(ctx, userID, bookID, chID)
		if perr != nil {
			s.writeActionEffectError(w, perr)
			return
		}
		writeJSON(w, http.StatusOK, map[string]any{"outcome": "action_done", "op": "publish", "chapter_id": chID, "revision_id": revID, "reparse": counts})
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
	case errors.Is(err, errActionKGExcluded):
		// WS-0.4: refuse LOUDLY and say why. A generic 500 (or worse, a silent 200 that
		// indexed nothing) would leave the user re-clicking "add to knowledge" forever
		// with no idea their own kg_exclude flag is what's blocking it.
		writeError(w, http.StatusConflict, "BOOK_KG_EXCLUDED",
			"this chapter is excluded from your knowledge graph — clear kg_exclude first")
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

func (s *Server) mcpPublishChapter(ctx context.Context, caller, bookID, chID uuid.UUID) (uuid.UUID, reparseCounts, error) {
	// 26 IX-2: parse the to-be-pinned body BEFORE the Tx (never a cross-service
	// call inside the transaction); the draftVersion guard below skips the upsert
	// on a concurrent save. Mirrors publishChapter exactly (both publish sites,
	// F10) so heal and produce share one path.
	prep := s.prepareReparse(ctx, bookID, chID)

	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return uuid.Nil, reparseCounts{}, err
	}
	defer tx.Rollback(ctx)
	var curr int64
	var body json.RawMessage
	var format string
	err = tx.QueryRow(ctx, `
SELECT d.draft_version, d.body, d.draft_format FROM chapter_drafts d JOIN chapters c ON c.id=d.chapter_id
WHERE d.chapter_id=$1 AND c.book_id=$2 AND c.lifecycle_state='active' FOR UPDATE OF d`, chID, bookID).Scan(&curr, &body, &format)
	if errors.Is(err, pgx.ErrNoRows) {
		return uuid.Nil, reparseCounts{}, errActionTargetGone
	}
	if err != nil {
		return uuid.Nil, reparseCounts{}, err
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
		return uuid.Nil, reparseCounts{}, errActionBadState
	}
	var revID uuid.UUID
	if err := tx.QueryRow(ctx, `
INSERT INTO chapter_revisions(chapter_id, body, body_format, message, author_user_id)
VALUES($1,$2,$3,'publish',$4) RETURNING id`, chID, body, format, caller).Scan(&revID); err != nil {
		return uuid.Nil, reparseCounts{}, err
	}
	// WS-0.3: publish also advances the KG pointer, so today's behavior (publish ⇒
	// indexed) is preserved exactly under the re-keyed sweeper. kg_exclude is
	// PRODUCER-side authoritative (spec §3.7): when the user has asked to keep this
	// chapter out of their knowledge graph, publishing it must NOT drag it back in,
	// so we leave the pointer untouched.
	// RETURNING kg_exclude: the emitted chapter.published must CARRY the exclusion, or
	// knowledge-service (which cannot see this column) will index the chapter anyway.
	// Refusing to move the pointer here is not enough — the EVENT is what drives the
	// graph write. See the review-impl P0 note on the emit below.
	var kgExcluded bool
	if err := tx.QueryRow(ctx, `
UPDATE chapters SET editorial_status='published', published_revision_id=$2,
  kg_indexed_revision_id=CASE WHEN kg_exclude THEN kg_indexed_revision_id ELSE $2 END,
  draft_revision_count=draft_revision_count+1, updated_at=now() WHERE id=$1
RETURNING kg_exclude`, chID, revID).Scan(&kgExcluded); err != nil {
		return uuid.Nil, reparseCounts{}, err
	}
	// 26 IX-2 step 3(b–d): same-Tx re-parse when the parse succeeded and describes
	// the pinned body (draftVersion match). Otherwise the marker stays behind and
	// the sweeper heals — a parse failure never blocks publish (OQ-1).
	var counts reparseCounts
	if prep.ok && prep.draftVersion == curr {
		counts, err = s.upsertChapterScenes(ctx, tx, bookID, chID, prep.structuralPath, prep.tree)
		if err != nil {
			return uuid.Nil, reparseCounts{}, err
		}
		if _, err := tx.Exec(ctx, `UPDATE chapters SET last_parsed_revision_id=$2 WHERE id=$1`, chID, revID); err != nil {
			return uuid.Nil, reparseCounts{}, err
		}
		// RB5-1: emit only when the index changed (a no-op re-parse must not wipe the
		// book's extraction cache via the knowledge consumer).
		if counts.changed() {
			if err := emitScenesReparsed(ctx, tx, bookID, chID, revID, counts.ParseVersion); err != nil {
				return uuid.Nil, reparseCounts{}, err
			}
			// SC11-amendment Phase 0 — writer #2 of `scenes.source_scene_id` (see kg_index.go).
			if err := emitScenesLinked(ctx, tx, bookID, chID); err != nil {
				return uuid.Nil, reparseCounts{}, err
			}
		}
	} else {
		slog.WarnContext(ctx, "mcp publish: re-parse skipped; index left stale for the sweeper",
			"chapter_id", chID, "parse_ok", prep.ok, "draft_version_match", prep.draftVersion == curr)
	}
	// review-impl P0: `kg_exclude` rides the payload. Refusing to set the pointer above
	// does NOT keep an excluded chapter out of the graph — `handle_chapter_published` is
	// what enqueues extraction and ingests canon passages, and it cannot see the column.
	// Without this field, publishing a chapter the user asked us to forget silently
	// re-indexes it. (We must not simply suppress the event: chapter.published has other
	// consumers — glossary wiki-staleness among them — that still need it.)
	if err := insertOutboxEvent(ctx, tx, "chapter.published", chID, map[string]any{
		"book_id": bookID, "chapter_id": chID, "revision_id": revID, "kg_exclude": kgExcluded,
	}); err != nil {
		return uuid.Nil, reparseCounts{}, err
	}
	if err := tx.Commit(ctx); err != nil {
		return uuid.Nil, reparseCounts{}, err
	}
	return revID, counts, nil
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

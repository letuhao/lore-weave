package api

// S-BOOK (MCP fan-out) tests. These exercise the kit-based MCP surface WITHOUT a
// live DB (the pool is nil): tool-catalog metadata, the identity gate, the scope
// guard (non-owner rejected), the Tier-A undo_hint shape, the H8 mandatory
// base_version, and the Tier-W confirm-token round-trip (mint→confirm dispatch;
// expired/forged/wrong-user refused). DB-touching effects are covered at
// COMPOSE B live-smoke.

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/google/uuid"
	"github.com/modelcontextprotocol/go-sdk/mcp"

	"github.com/loreweave/book-service/internal/config"
	lwmcp "github.com/loreweave/loreweave_mcp"
)

const mcpTestSecret = "test-secret-at-least-32-characters-long!"

// mcpConfirmSecret is the DISTINCT confirm-token signing secret (key-split from
// JWTSecret). Tier-W tokens are minted/verified with THIS secret, never mcpTestSecret.
const mcpConfirmSecret = "confirm-token-secret-32-chars-min-yes!!!"
const mcpTestToken = "internal-tok-xyz"

// mcpTestServer returns a Server with a config (JWT secret + confirm secret +
// internal token) and a stubbed grant resolver reporting `level` for the caller
// on an active book.
func mcpTestServer(level GrantLevel) *Server {
	s := NewServer(nil, &config.Config{
		JWTSecret:                 mcpTestSecret,
		ConfirmTokenSigningSecret: mcpConfirmSecret,
		InternalServiceToken:      mcpTestToken,
	})
	s.resolveBook = func(ctx context.Context, bookID, userID uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
		return level, uuid.New(), "active", nil
	}
	return s
}

func mcpJWT(t *testing.T, userID uuid.UUID) string {
	t.Helper()
	tok := jwt.NewWithClaims(jwt.SigningMethodHS256, jwt.RegisteredClaims{
		Subject:   userID.String(),
		ExpiresAt: jwt.NewNumericDate(time.Now().Add(time.Hour)),
	})
	signed, err := tok.SignedString([]byte(mcpTestSecret))
	if err != nil {
		t.Fatalf("sign jwt: %v", err)
	}
	return signed
}

// ── C-TOOL: every tool carries valid tier+scope _meta ─────────────────────────

func TestMCP_AllToolsCarryValidMeta(t *testing.T) {
	s := mcpTestServer(GrantOwner)
	// newMCPServer runs MustValidateToolMeta on every tool at registration; if any
	// were missing tier/scope it would panic here. Reaching this line proves the
	// whole catalog is C-TOOL-compliant.
	srv := s.newMCPServer()
	if srv == nil {
		t.Fatal("newMCPServer returned nil")
	}
}

// Independently assert the kit meta builder accepts each tier we use and that a
// representative tool definition validates (guards against a future tier/scope typo).
func TestMCP_ToolMetaValidatorAcceptsCatalogShapes(t *testing.T) {
	cases := []struct {
		name string
		meta mcp.Meta
	}{
		{"read", lwmcp.NewToolMeta(lwmcp.TierR, lwmcp.ScopeBook, nil, []string{"x"})},
		{"auto", lwmcp.NewToolMeta(lwmcp.TierA, lwmcp.ScopeBook, map[string]any{"tool": "book_purge"}, nil)},
		{"write", lwmcp.NewToolMeta(lwmcp.TierW, lwmcp.ScopeBook, nil, nil)},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			if err := lwmcp.ValidateToolMeta(&mcp.Tool{Name: "book_x", Meta: c.meta}); err != nil {
				t.Fatalf("ValidateToolMeta = %v, want nil", err)
			}
			if c.meta[lwmcp.MetaKeyScope] != "book" {
				t.Errorf("scope = %v, want book", c.meta[lwmcp.MetaKeyScope])
			}
		})
	}
}

// ── SEC-1: identity gate rejects a missing/invalid internal token ─────────────

func TestMCP_IdentityGate_RejectsBadToken(t *testing.T) {
	s := mcpTestServer(GrantOwner)
	h := s.mcpHandler()

	// no token → 401
	rr := httptest.NewRecorder()
	h.ServeHTTP(rr, httptest.NewRequest(http.MethodPost, "/mcp", nil))
	if rr.Code != http.StatusUnauthorized {
		t.Fatalf("no-token status = %d, want 401", rr.Code)
	}

	// wrong token → 401
	req := httptest.NewRequest(http.MethodPost, "/mcp", nil)
	req.Header.Set(lwmcp.HeaderInternalToken, "wrong")
	rr2 := httptest.NewRecorder()
	h.ServeHTTP(rr2, req)
	if rr2.Code != http.StatusUnauthorized {
		t.Fatalf("wrong-token status = %d, want 401", rr2.Code)
	}
}

// ── SEC-2 / H13: the scope guard rejects a non-owner uniformly ────────────────

func TestMCP_ScopeGuard_NonOwnerRejected(t *testing.T) {
	caller := uuid.New()
	bookID := uuid.New()

	// A caller with NO grant on the book → ErrNotAccessible (uniform, no oracle).
	none := mcpTestServer(GrantNone)
	if _, err := none.mcpRequireGrant(context.Background(), bookID, caller, GrantView); err != lwmcp.ErrNotAccessible {
		t.Fatalf("no-grant err = %v, want ErrNotAccessible", err)
	}

	// A view-only caller cannot satisfy an Edit-tier write → ErrNotAccessible.
	view := mcpTestServer(GrantView)
	if _, err := view.mcpRequireGrant(context.Background(), bookID, caller, GrantEdit); err != lwmcp.ErrNotAccessible {
		t.Fatalf("below-need err = %v, want ErrNotAccessible", err)
	}

	// An owner satisfies Edit.
	owner := mcpTestServer(GrantOwner)
	if _, err := owner.mcpRequireGrant(context.Background(), bookID, caller, GrantEdit); err != nil {
		t.Fatalf("owner err = %v, want nil", err)
	}

	// A resolver outage → ErrCheckUnavailable ("try again"), fail-closed.
	outage := mcpTestServer(GrantOwner)
	outage.resolveBook = func(ctx context.Context, b, u uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
		return GrantNone, uuid.Nil, "", context.DeadlineExceeded
	}
	if _, err := outage.mcpRequireGrant(context.Background(), bookID, caller, GrantView); err != lwmcp.ErrCheckUnavailable {
		t.Fatalf("outage err = %v, want ErrCheckUnavailable", err)
	}
}

// OD-8: book_list (the "my library" enumeration, no per-book guard) must not list
// books merely SHARED to the caller for a public key — the filter drops the
// collaborator clause when owner-only.
func TestBookListFilter_OD8_OwnedOnly(t *testing.T) {
	firstParty := bookListFilter(false)
	if !strings.Contains(firstParty, "book_collaborators") {
		t.Fatalf("first-party filter must include shared books, got %q", firstParty)
	}
	ownerOnly := bookListFilter(true)
	if strings.Contains(ownerOnly, "book_collaborators") {
		t.Fatalf("OD-8 owner-only filter must NOT include the collaborator clause, got %q", ownerOnly)
	}
	if !strings.Contains(ownerOnly, "b.owner_user_id=$1") {
		t.Fatalf("OD-8 filter must still scope to the owner, got %q", ownerOnly)
	}
}

// OD-8: a PUBLIC MCP key (X-Mcp-Key-Id in ctx) reaches a book ONLY as its OWNER.
// A caller holding a SHARE (manage) on a book owned by someone else — allowed
// first-party — is denied for a public key; the owner still passes.
func TestMCP_ScopeGuard_OD8_OwnedOnly(t *testing.T) {
	caller := uuid.New()
	otherOwner := uuid.New()
	bookID := uuid.New()

	// Caller holds a Manage SHARE; the book is owned by otherOwner.
	shared := mcpTestServer(GrantManage)
	shared.resolveBook = func(ctx context.Context, b, u uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
		return GrantManage, otherOwner, "active", nil
	}
	firstParty := context.Background()
	publicKey := lwmcp.ContextWithMcpKeyID(context.Background(), "key-xyz")

	// First-party: the share satisfies a view-tier read.
	if _, err := shared.mcpRequireGrant(firstParty, bookID, caller, GrantView); err != nil {
		t.Fatalf("first-party share read err = %v, want nil", err)
	}
	// Public key: the same shared book is denied (OD-8 requires owner-equality).
	if _, err := shared.mcpRequireGrant(publicKey, bookID, caller, GrantView); err != lwmcp.ErrNotAccessible {
		t.Fatalf("public-key shared-book err = %v, want ErrNotAccessible (OD-8)", err)
	}

	// Caller IS the owner → passes even for a public key.
	owned := mcpTestServer(GrantOwner)
	owned.resolveBook = func(ctx context.Context, b, u uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
		return GrantOwner, caller, "active", nil // owner == caller
	}
	if _, err := owned.mcpRequireGrant(publicKey, bookID, caller, GrantView); err != nil {
		t.Fatalf("public-key owner read err = %v, want nil", err)
	}
}

// mcpOwnershipError maps the sentinels to distinct caller messages (retryable vs not).
func TestMCP_OwnershipErrorMapping(t *testing.T) {
	if mcpOwnershipError(lwmcp.ErrNotAccessible) != errBookNotAccessible {
		t.Error("ErrNotAccessible should map to errBookNotAccessible")
	}
	if mcpOwnershipError(lwmcp.ErrCheckUnavailable) != errBookCheckUnavailable {
		t.Error("ErrCheckUnavailable should map to errBookCheckUnavailable (try again)")
	}
}

// ── C-ACTIVITY: Tier-A undo_hint shape ────────────────────────────────────────

func TestMCP_UndoResult_CarriesHint(t *testing.T) {
	res := undoResult("book_chapter_delete", map[string]any{"book_id": "b", "chapter_id": "c"})
	hint, ok := res.Meta["undo_hint"].(map[string]any)
	if !ok {
		t.Fatalf("undo_hint missing or wrong type: %#v", res.Meta)
	}
	if hint["tool"] != "book_chapter_delete" {
		t.Errorf("undo tool = %v, want book_chapter_delete", hint["tool"])
	}
	args, ok := hint["args"].(map[string]any)
	if !ok || args["chapter_id"] != "c" {
		t.Errorf("undo args = %#v, want chapter_id=c", hint["args"])
	}
}

// ── H8: book_chapter_save_draft REQUIRES base_version ─────────────────────────

func TestMCP_SaveDraft_RequiresBaseVersion(t *testing.T) {
	s := mcpTestServer(GrantOwner)
	ctx := identityCtxForTest(t, uuid.New())
	in := saveDraftIn{
		BookID:      uuid.NewString(),
		ChapterID:   uuid.NewString(),
		BaseVersion: 0, // missing → must be rejected before any DB access
		Body:        "some prose",
	}
	_, _, err := s.toolChapterSaveDraft(ctx, nil, in)
	if err == nil || !strings.Contains(err.Error(), "base_version is required") {
		t.Fatalf("err = %v, want 'base_version is required'", err)
	}
}

// A negative base_version is also rejected (H8 — only a positive version read
// from the draft is acceptable).
func TestMCP_SaveDraft_RejectsNonPositiveBaseVersion(t *testing.T) {
	s := mcpTestServer(GrantOwner)
	ctx := identityCtxForTest(t, uuid.New())
	in := saveDraftIn{
		BookID:      uuid.NewString(),
		ChapterID:   uuid.NewString(),
		BaseVersion: -3,
		Body:        "some prose",
	}
	if _, _, err := s.toolChapterSaveDraft(ctx, nil, in); err == nil || !strings.Contains(err.Error(), "base_version is required") {
		t.Fatalf("err = %v, want base_version rejection", err)
	}
}

// identityCtxForTest produces a context populated by the kit IdentityMiddleware
// exactly as a real /mcp request would (X-Internal-Token + X-User-Id headers →
// ctx), so a tool handler reads the caller via lwmcp.UserIDFromCtx. This avoids
// reaching into the kit's unexported ctx keys.
func identityCtxForTest(t *testing.T, userID uuid.UUID) context.Context {
	t.Helper()
	var captured context.Context
	h := lwmcp.IdentityMiddleware(mcpTestToken, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		captured = r.Context()
	}))
	req := httptest.NewRequest(http.MethodPost, "/mcp", nil)
	req.Header.Set(lwmcp.HeaderInternalToken, mcpTestToken)
	req.Header.Set(lwmcp.HeaderUserID, userID.String())
	h.ServeHTTP(httptest.NewRecorder(), req)
	if captured == nil {
		t.Fatal("identity middleware did not pass the request through")
	}
	if got, ok := lwmcp.UserIDFromCtx(captured); !ok || got != userID {
		t.Fatalf("ctx user id = %v ok=%v, want %v", got, ok, userID)
	}
	return captured
}

// ── Tier-W confirm-token round-trip (mint → confirm dispatch) ─────────────────

func TestMCP_ConfirmToken_RefusesExpired(t *testing.T) {
	s := mcpTestServer(GrantOwner)
	userID := uuid.New()
	bookID := uuid.New()
	// ttl=-1s → already expired. Minted with the DISTINCT confirm secret.
	tok, err := lwmcp.MintConfirmToken(mcpConfirmSecret, userID, bookID, descBookDelete,
		actionPayload{Op: "delete_book"}, -1*time.Second)
	if err != nil {
		t.Fatalf("mint: %v", err)
	}
	body, _ := json.Marshal(map[string]string{"confirm_token": tok})
	req := httptest.NewRequest(http.MethodPost, "/v1/book/actions/confirm", strings.NewReader(string(body)))
	req.Header.Set("Authorization", "Bearer "+mcpJWT(t, userID))
	rr := httptest.NewRecorder()
	s.confirmBookAction(rr, req)
	if rr.Code != http.StatusUnprocessableEntity {
		t.Fatalf("expired status = %d, want 422; body=%s", rr.Code, rr.Body.String())
	}
}

func TestMCP_ConfirmToken_RefusesForged(t *testing.T) {
	s := mcpTestServer(GrantOwner)
	userID := uuid.New()
	bookID := uuid.New()
	// Token minted with a DIFFERENT secret → signature mismatch → invalid.
	forged, err := lwmcp.MintConfirmToken("a-totally-different-secret-key-32chars!!", userID, bookID, descBookDelete,
		actionPayload{Op: "delete_book"}, actionTokenTTL)
	if err != nil {
		t.Fatalf("mint: %v", err)
	}
	body, _ := json.Marshal(map[string]string{"confirm_token": forged})
	req := httptest.NewRequest(http.MethodPost, "/v1/book/actions/confirm", strings.NewReader(string(body)))
	req.Header.Set("Authorization", "Bearer "+mcpJWT(t, userID))
	rr := httptest.NewRecorder()
	s.confirmBookAction(rr, req)
	if rr.Code != http.StatusUnprocessableEntity {
		t.Fatalf("forged status = %d, want 422; body=%s", rr.Code, rr.Body.String())
	}
}

func TestMCP_ConfirmToken_RefusesWrongUser(t *testing.T) {
	s := mcpTestServer(GrantOwner)
	proposer := uuid.New()
	attacker := uuid.New()
	bookID := uuid.New()
	tok, err := lwmcp.MintConfirmToken(mcpConfirmSecret, proposer, bookID, descBookMedia,
		actionPayload{Op: "set_cover"}, actionTokenTTL)
	if err != nil {
		t.Fatalf("mint: %v", err)
	}
	body, _ := json.Marshal(map[string]string{"confirm_token": tok})
	req := httptest.NewRequest(http.MethodPost, "/v1/book/actions/confirm", strings.NewReader(string(body)))
	// A DIFFERENT signed-in user submits the proposer's token.
	req.Header.Set("Authorization", "Bearer "+mcpJWT(t, attacker))
	rr := httptest.NewRecorder()
	s.confirmBookAction(rr, req)
	if rr.Code != http.StatusForbidden {
		t.Fatalf("wrong-user status = %d, want 403; body=%s", rr.Code, rr.Body.String())
	}
}

// confused-deputy: a token minted for book.media must not dispatch a delete op.
// (The effect dispatch keys on the descriptor; a media descriptor never reaches
// effectDelete.) Here we assert the descriptor→grant mapping is destructive-aware.
func TestMCP_NeededGrant_DestructiveOpsRequireHigher(t *testing.T) {
	if neededGrantFor(descBookDelete, "delete_book") != GrantOwner {
		t.Error("delete_book must require owner")
	}
	if neededGrantFor(descBookDelete, "purge_chapter") != GrantManage {
		t.Error("purge_chapter must require manage")
	}
	if neededGrantFor(descBookPublish, "publish") != GrantEdit {
		t.Error("publish must require edit")
	}
}

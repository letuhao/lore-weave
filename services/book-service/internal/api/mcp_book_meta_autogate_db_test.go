package api

// M0 (agent write auto-gate spec) — book_update_details is now a Tier-W PROPOSE, not
// a Tier-A write. Calling the tool MUST NOT mutate the book; it returns a server-
// built DIFF CARD. The write happens only on confirm, guarded by optimistic
// concurrency (base_version = updated_at). Gated on BOOK_TEST_DATABASE_URL.

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/google/uuid"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

func TestMCP_BookUpdateMeta_ProposesDiff_NoWrite_ThenConfirmApplies_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	var bookID uuid.UUID
	if err := pool.QueryRow(ctx,
		`INSERT INTO books(owner_user_id,title,description) VALUES($1,'Old Title','old desc') RETURNING id`,
		owner).Scan(&bookID); err != nil {
		t.Fatalf("seed: %v", err)
	}
	s.resolveBook = ownerResolver(owner)
	tctx := identityCtxForTest(t, owner)

	newDesc := "In a drowning port city, a glassmaker's daughter can save or shatter the harbor."
	_, card, err := s.toolBookUpdateMeta(tctx, nil, bookUpdateMetaIn{
		BookID: bookID.String(), Description: &newDesc,
	})
	if err != nil {
		t.Fatalf("propose: %v", err)
	}
	// (1) it returns a book.meta DIFF card with a confirm token — not a write result.
	if card.ConfirmToken == "" || card.Descriptor != descBookMeta || card.Domain != "book" {
		t.Fatalf("want a book.meta diff card, got %+v", card)
	}
	if len(card.Changes) != 1 || card.Changes[0].Target != "description" ||
		card.Changes[0].OldValue != "old desc" || card.Changes[0].NewValue != newDesc {
		t.Fatalf("diff changes wrong: %+v", card.Changes)
	}
	// (2) NOTHING is written at propose time.
	var descNow string
	if err := pool.QueryRow(ctx, `SELECT description FROM books WHERE id=$1`, bookID).Scan(&descNow); err != nil {
		t.Fatalf("read-back: %v", err)
	}
	if descNow != "old desc" {
		t.Fatalf("propose must NOT write; description already = %q", descNow)
	}
	// (3) confirm → the edit is applied.
	rr := confirmReq(t, s, owner, card.ConfirmToken)
	if rr.Code != http.StatusOK {
		t.Fatalf("confirm = %d; body=%s", rr.Code, rr.Body.String())
	}
	if err := pool.QueryRow(ctx, `SELECT description FROM books WHERE id=$1`, bookID).Scan(&descNow); err != nil {
		t.Fatalf("read-back 2: %v", err)
	}
	if descNow != newDesc {
		t.Fatalf("confirm must apply the edit; description = %q", descNow)
	}
}

// M0d (deterministic live proof) — drive book_update_details THROUGH the real /mcp
// handler (identity middleware + stateless StreamableHTTP transport + the go-sdk
// output validator), exactly as the gateway does. The "rewrite the description"
// request must return a DIFF CARD (confirm_token + server-built old→new changes,
// descriptor book.meta) and write NOTHING. This proves the deployed mechanism
// independent of any LLM's tool-selection (which is the model's job).
func TestMCP_BookUpdateMeta_ThroughMCPHandler_ReturnsDiffCard_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	var bookID uuid.UUID
	if err := pool.QueryRow(ctx,
		`INSERT INTO books(owner_user_id,title,description) VALUES($1,'The Tidewright','old blurb') RETURNING id`,
		owner).Scan(&bookID); err != nil {
		t.Fatalf("seed: %v", err)
	}
	s.resolveBook = ownerResolver(owner)

	srv := httptest.NewServer(s.mcpHandler())
	t.Cleanup(srv.Close)
	transport := &mcp.StreamableClientTransport{
		Endpoint: srv.URL,
		HTTPClient: &http.Client{
			Transport: headerRoundTripper{rt: http.DefaultTransport, userID: owner.String()},
		},
		DisableStandaloneSSE: true,
	}
	client := mcp.NewClient(&mcp.Implementation{Name: "test", Version: "0.0.1"}, nil)
	cs, err := client.Connect(ctx, transport, nil)
	if err != nil {
		t.Fatalf("connect /mcp: %v", err)
	}
	t.Cleanup(func() { _ = cs.Close() })

	// Discovery: the tool MUST be enumerated in tools/list under its new name (so the
	// gateway federates it and the model can tool_load + call it). A registered-but-
	// unlisted tool is callable by a test yet invisible to an agent.
	lt, err := cs.ListTools(ctx, nil)
	if err != nil {
		t.Fatalf("list tools: %v", err)
	}
	var listed []string
	found := false
	for _, tl := range lt.Tools {
		listed = append(listed, tl.Name)
		if tl.Name == "book_update_details" {
			found = true
		}
	}
	if !found {
		t.Fatalf("book_update_details NOT in tools/list — invisible to discovery. listed=%v", listed)
	}

	newDesc := "In a drowning port city, a glassmaker's daughter learns her gift can either save the harbor or shatter it forever."
	res, err := cs.CallTool(ctx, &mcp.CallToolParams{
		Name:      "book_update_details",
		Arguments: map[string]any{"book_id": bookID.String(), "description": newDesc},
	})
	if err != nil {
		t.Fatalf("book_update_details call failed: %v", err)
	}
	if res.IsError {
		t.Fatalf("book_update_details returned isError=true: %+v", res.Content)
	}
	raw, _ := json.Marshal(res.StructuredContent)
	var card struct {
		ConfirmToken string `json:"confirm_token"`
		Descriptor   string `json:"descriptor"`
		Domain       string `json:"domain"`
		Changes      []struct {
			FieldLabel string `json:"field_label"`
			OldValue   string `json:"old_value"`
			NewValue   string `json:"new_value"`
			Target     string `json:"target"`
		} `json:"changes"`
	}
	if err := json.Unmarshal(raw, &card); err != nil {
		t.Fatalf("unmarshal card: %v (raw=%s)", err, raw)
	}
	if card.ConfirmToken == "" || card.Descriptor != descBookMeta || card.Domain != "book" {
		t.Fatalf("want a book.meta diff card, got %s", raw)
	}
	if len(card.Changes) != 1 || card.Changes[0].Target != "description" ||
		card.Changes[0].OldValue != "old blurb" || card.Changes[0].NewValue != newDesc {
		t.Fatalf("server-built diff wrong: %+v", card.Changes)
	}
	// NOTHING written at propose time (the write waits for confirm).
	var descNow string
	_ = pool.QueryRow(ctx, `SELECT description FROM books WHERE id=$1`, bookID).Scan(&descNow)
	if descNow != "old blurb" {
		t.Fatalf("propose through /mcp must NOT write; description = %q", descNow)
	}
}

// OCC (I7): a diff proposed against one version must NOT clobber a book edited since.
func TestMCP_BookUpdateMeta_StaleVersion_Conflicts_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	var bookID uuid.UUID
	if err := pool.QueryRow(ctx,
		`INSERT INTO books(owner_user_id,title,description) VALUES($1,'T','v1 desc') RETURNING id`,
		owner).Scan(&bookID); err != nil {
		t.Fatalf("seed: %v", err)
	}
	s.resolveBook = ownerResolver(owner)
	tctx := identityCtxForTest(t, owner)

	d := "proposed against v1"
	_, card, err := s.toolBookUpdateMeta(tctx, nil, bookUpdateMetaIn{BookID: bookID.String(), Description: &d})
	if err != nil {
		t.Fatalf("propose: %v", err)
	}
	// A concurrent edit bumps updated_at AFTER the diff was proposed.
	if _, err := pool.Exec(ctx, `UPDATE books SET description='v2 concurrent', updated_at=now() WHERE id=$1`, bookID); err != nil {
		t.Fatalf("concurrent edit: %v", err)
	}
	rr := confirmReq(t, s, owner, card.ConfirmToken)
	if rr.Code == http.StatusOK {
		t.Fatalf("stale confirm must NOT succeed (would clobber the concurrent edit)")
	}
	var descNow string
	_ = pool.QueryRow(ctx, `SELECT description FROM books WHERE id=$1`, bookID).Scan(&descNow)
	if descNow != "v2 concurrent" {
		t.Fatalf("the concurrent edit must survive; description = %q", descNow)
	}
}

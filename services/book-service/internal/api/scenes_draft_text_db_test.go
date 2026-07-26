package api

// D-KG-SUMMARIES-LIVE-SMOKE regression — the internal draft-text endpoint
// (consumed by knowledge-service's summary_processor as the legacy-chapter text
// fallback) used to `SELECT cd.body::text::bytea`, which makes Postgres parse
// the Tiptap JSON as a bytea ESCAPE literal and errors ("invalid input syntax
// for type bytea") on ANY draft whose text values contain a backslash escape
// (\n, \", …). That 500 was latent until legacy-chapter summaries began reading
// the draft, then blocked every flat-book summary. This DB-gated test seeds a
// draft with backslash-bearing text and asserts a 200 with extracted prose.

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	lwmcp "github.com/loreweave/loreweave_mcp"

	"github.com/google/uuid"
)

func TestGetInternalChapterDraftText_BackslashBody_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()

	// A text value with an embedded quote + newline → the jsonb text
	// representation carries `\"` and `\n`, exactly what broke `::bytea`.
	body := json.RawMessage(`{"type":"doc","content":[{"type":"paragraph","content":[{"type":"text","text":"He said \"hello\"\nthen left"}]}]}`)
	bookID, chID := seedChapterWithBody(t, ctx, pool, owner, body)

	url := "/internal/books/" + bookID.String() + "/chapters/" + chID.String() + "/draft-text"
	req := httptest.NewRequest(http.MethodGet, url, nil)
	req.Header.Set(lwmcp.HeaderInternalToken, mcpTestToken)
	rr := httptest.NewRecorder()
	s.Router().ServeHTTP(rr, req)

	if rr.Code != http.StatusOK {
		t.Fatalf("draft-text = %d, want 200 (the ::bytea cast regression)\n%s", rr.Code, rr.Body.String())
	}
	var out struct {
		Text   string `json:"text"`
		Length int    `json:"length"`
	}
	if err := json.Unmarshal(rr.Body.Bytes(), &out); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if !strings.Contains(out.Text, "He said") || out.Length == 0 {
		t.Fatalf("expected extracted prose, got text=%q length=%d", out.Text, out.Length)
	}
}

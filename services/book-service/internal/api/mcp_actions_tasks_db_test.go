package api

// T3c — the ext-tasks DURABLE GATE, proven through the REAL /mcp handler + real
// Postgres. book_chapter_delete on a tasks-capable client must HOLD at
// input_required (nothing trashed) until the input step accepts it; a non-tasks
// client must still get today's confirm_token card (no regression). This is the
// Go-domain mirror of composition's live gate proof (spec §6.2 / T3c).
//
// Gated by BOOK_TEST_DATABASE_URL like the sibling _DB tests (skips without a DB).

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/google/uuid"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

// tasksClientMeta is the per-request _meta a tasks-capable client attaches to
// DECLARE it drives the ext-tasks extension — byte-identical to chat-service's
// tasks_capability_meta() and what the Go ClientSupportsTasks reads.
func tasksClientMeta() mcp.Meta {
	return mcp.Meta{
		"io.modelcontextprotocol/clientCapabilities": map[string]any{
			"extensions": map[string]any{
				"io.modelcontextprotocol/tasks": map[string]any{},
			},
		},
	}
}

func chapterLifecycle(t *testing.T, ctx context.Context, s *Server, chID uuid.UUID) string {
	t.Helper()
	var state string
	if err := s.pool.QueryRow(ctx, `SELECT lifecycle_state FROM chapters WHERE id=$1`, chID).Scan(&state); err != nil {
		t.Fatalf("read chapter lifecycle: %v", err)
	}
	return state
}

func connectBookMCP(t *testing.T, srvURL, userID string) *mcp.ClientSession {
	t.Helper()
	transport := &mcp.StreamableClientTransport{
		Endpoint: srvURL,
		HTTPClient: &http.Client{
			Transport: headerRoundTripper{rt: http.DefaultTransport, userID: userID},
		},
		DisableStandaloneSSE: true,
	}
	client := mcp.NewClient(&mcp.Implementation{Name: "test", Version: "0.0.1"}, nil)
	cs, err := client.Connect(context.Background(), transport, nil)
	if err != nil {
		t.Fatalf("connect /mcp: %v", err)
	}
	t.Cleanup(func() { _ = cs.Close() })
	return cs
}

func structured(t *testing.T, res *mcp.CallToolResult) map[string]any {
	t.Helper()
	raw, err := json.Marshal(res.StructuredContent)
	if err != nil {
		t.Fatalf("marshal structured content: %v", err)
	}
	var m map[string]any
	if err := json.Unmarshal(raw, &m); err != nil {
		t.Fatalf("unmarshal structured content: %v; raw=%s", err, raw)
	}
	return m
}

// TestMCP_ChapterDelete_DurableGate_AcceptTrashes_DB drives the full gate loop:
// tasks-capable delete → input_required handle, chapter untouched → accept via
// book_task_provide_input → chapter trashed.
func TestMCP_ChapterDelete_DurableGate_AcceptTrashes_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	bookID, chID := seedChapter(t, ctx, pool, owner)
	_ = bookID

	srv := httptest.NewServer(s.mcpHandler())
	t.Cleanup(srv.Close)
	cs := connectBookMCP(t, srv.URL, owner.String())

	// 1) Propose delete WITH tasks capability → durable gate handle, nothing trashed.
	res, err := cs.CallTool(ctx, &mcp.CallToolParams{
		Name:      "book_chapter_delete",
		Arguments: map[string]any{"book_id": bookID.String(), "chapter_id": chID.String()},
		Meta:      tasksClientMeta(),
	})
	if err != nil {
		t.Fatalf("book_chapter_delete (tasks) call: %v", err)
	}
	if res.IsError {
		t.Fatalf("book_chapter_delete (tasks) isError: %+v", res.Content)
	}
	handle := structured(t, res)
	if handle["type"] != "io.loreweave/task-handle" {
		t.Fatalf("expected a task-handle, got type=%v (full=%v)", handle["type"], handle)
	}
	if handle["status"] != "input_required" {
		t.Fatalf("gate status = %v, want input_required", handle["status"])
	}
	if got := chapterLifecycle(t, ctx, s, chID); got != "active" {
		t.Fatalf("chapter lifecycle = %q after gate-open, want active (nothing trashed until accept)", got)
	}
	taskID, _ := handle["taskId"].(string)
	if taskID == "" {
		t.Fatalf("no taskId on handle: %v", handle)
	}

	// 2) Accept via the input step → executor trashes the chapter.
	res2, err := cs.CallTool(ctx, &mcp.CallToolParams{
		Name:      "book_task_provide_input",
		Arguments: map[string]any{"task_id": taskID, "accepted": true},
	})
	if err != nil {
		t.Fatalf("book_task_provide_input call: %v", err)
	}
	if res2.IsError {
		t.Fatalf("provide_input isError: %+v", res2.Content)
	}
	done := structured(t, res2)
	if done["status"] != "completed" {
		t.Fatalf("provide_input status = %v, want completed (result=%v)", done["status"], done)
	}
	result, _ := done["result"].(map[string]any)
	if result["outcome"] != "action_done" || result["op"] != "delete_chapter" {
		t.Fatalf("executor result = %v, want action_done/delete_chapter", done["result"])
	}
	if got := chapterLifecycle(t, ctx, s, chID); got != "trashed" {
		t.Fatalf("chapter lifecycle = %q after accept, want trashed", got)
	}

	// 3) Double-accept is refused (single-winner guard = single-use parity).
	res3, err := cs.CallTool(ctx, &mcp.CallToolParams{
		Name:      "book_task_provide_input",
		Arguments: map[string]any{"task_id": taskID, "accepted": true},
	})
	if err != nil {
		t.Fatalf("second provide_input call: %v", err)
	}
	if !res3.IsError {
		t.Fatalf("second accept must be refused (double-confirm guard), got %v", structured(t, res3))
	}
}

// TestMCP_ChapterDelete_NonTasksClient_ConfirmToken_DB proves the capability
// fallback: a client that does NOT declare tasks gets today's confirm_token card
// and the chapter is untouched (no regression for the public edge / pre-driver).
func TestMCP_ChapterDelete_NonTasksClient_ConfirmToken_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	bookID, chID := seedChapter(t, ctx, pool, owner)

	srv := httptest.NewServer(s.mcpHandler())
	t.Cleanup(srv.Close)
	cs := connectBookMCP(t, srv.URL, owner.String())

	res, err := cs.CallTool(ctx, &mcp.CallToolParams{
		Name:      "book_chapter_delete",
		Arguments: map[string]any{"book_id": bookID.String(), "chapter_id": chID.String()},
		// no Meta → not tasks-capable
	})
	if err != nil {
		t.Fatalf("book_chapter_delete (no-tasks) call: %v", err)
	}
	if res.IsError {
		t.Fatalf("book_chapter_delete (no-tasks) isError: %+v", res.Content)
	}
	card := structured(t, res)
	if card["confirm_token"] == nil || card["confirm_token"] == "" {
		t.Fatalf("expected a confirm_token card, got %v", card)
	}
	if card["descriptor"] != "book.delete" {
		t.Fatalf("card descriptor = %v, want book.delete", card["descriptor"])
	}
	if card["type"] == "io.loreweave/task-handle" {
		t.Fatalf("non-tasks client must NOT get a task handle: %v", card)
	}
	if got := chapterLifecycle(t, ctx, s, chID); got != "active" {
		t.Fatalf("chapter lifecycle = %q, want active (mint never writes)", got)
	}
}

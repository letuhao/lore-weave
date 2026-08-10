package api

import (
	"bytes"
	"context"
	"encoding/json"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
)

// HTTP vs MCP vs KAL: one transition, one emission (plan T50).
//
// The `*Core` surface is explicitly shared — `entity_handler.go` calls `softDeleteEntityCore`
// "the single source of truth for the REST DELETE route AND the glossary_entity_delete Tier-W
// confirm effect", and since T29 the KAL's service command lands on the same core. Sharing is
// the design. The risk it carries is that a change updates ONE transport's schema and the
// others drift silently — a class this repo has recorded twice (FastMCP strips undeclared
// fields; the REST mirror drops fields the MCP tool accepts).
//
// These tests compare the OUTBOX PAYLOAD each transport produces, because that is what
// downstream actually consumes. Comparing HTTP status codes would prove nothing: all three
// return 2xx while emitting whatever they like.

// latestEventPayload returns the newest event of a type as a map, minus the fields that
// legitimately differ per call. `emitted_at` is wall-clock and `actor_id` identifies WHO
// asked — neither can be equal across two separate calls, and requiring them to be would make
// the test assert the opposite of what it means.
func latestEventPayload(
	t *testing.T, pool *pgxpool.Pool, entityID uuid.UUID, eventType string,
) map[string]any {
	t.Helper()
	var raw []byte
	if err := pool.QueryRow(context.Background(),
		`SELECT payload FROM outbox_events
		  WHERE aggregate_id=$1 AND event_type=$2
		  ORDER BY created_at DESC, id DESC LIMIT 1`,
		entityID, eventType).Scan(&raw); err != nil {
		t.Fatalf("no %s event for %s: %v", eventType, entityID, err)
	}
	var m map[string]any
	if err := json.Unmarshal(raw, &m); err != nil {
		t.Fatalf("payload not JSON: %v", err)
	}
	delete(m, "emitted_at")
	delete(m, "actor_id")
	return m
}

// keysOf is the drift signal that matters most: a transport that stops populating a field, or
// starts populating a new one, changes the key set. Comparing keys catches the FastMCP-strips
// class even when every shared value happens to match.
func keysOf(m map[string]any) []string {
	out := make([]string, 0, len(m))
	for k := range m {
		out = append(out, k)
	}
	return out
}

func sameKeySet(a, b map[string]any) bool {
	if len(a) != len(b) {
		return false
	}
	for k := range a {
		if _, ok := b[k]; !ok {
			return false
		}
	}
	return true
}

// seedSecondEntity mints another live entity in the same book, so each transport can act on
// its OWN entity. Driving three transports at one entity would make each depend on the state
// the previous left, and the second delete would be a no-op that emits nothing.
func seedSecondEntity(t *testing.T, pool *pgxpool.Pool, f *versionFixture) uuid.UUID {
	t.Helper()
	var kindID uuid.UUID
	if err := pool.QueryRow(context.Background(),
		`SELECT kind_id FROM glossary_entities WHERE entity_id=$1`, f.entityID).Scan(&kindID); err != nil {
		t.Fatalf("read kind: %v", err)
	}
	var id uuid.UUID
	if err := pool.QueryRow(context.Background(),
		`INSERT INTO glossary_entities(book_id,kind_id,status,tags)
		 VALUES($1,$2,'active','{}') RETURNING entity_id`,
		f.bookID, kindID).Scan(&id); err != nil {
		t.Fatalf("seed second entity: %v", err)
	}
	return id
}

func TestDeleteEmission_IdenticalAcrossHttpMcpAndKal(t *testing.T) {
	pool := openTestDB(t)
	f := newVersionFixture(t, pool)
	ctx := context.Background()

	mcpEntity := seedSecondEntity(t, pool, f)
	kalEntity := seedSecondEntity(t, pool, f)

	// 1. HTTP — the browser's REST DELETE.
	req := httptest.NewRequest(http.MethodDelete,
		"/v1/glossary/books/"+f.bookID.String()+"/entities/"+f.entityID.String(), nil)
	req.Header.Set("Authorization", "Bearer "+f.token)
	w := httptest.NewRecorder()
	f.srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusNoContent {
		t.Fatalf("HTTP delete: want 204, got %d (%s)", w.Code, w.Body.String())
	}

	// 2. MCP — the Tier-W confirm EFFECT, which is where the MCP delete actually writes
	//    (the tool itself only mints a card; a human approves before anything is deleted).
	params, _ := json.Marshal(entityDeleteParams{EntityID: mcpEntity.String()})
	rec := httptest.NewRecorder()
	f.srv.effectEntityDelete(rec, ctx, actionClaims{
		UserID: f.ownerID, BookID: f.bookID,
		Descriptor: descEntityDelete, Params: params,
	})
	if rec.Code != http.StatusOK {
		t.Fatalf("MCP confirm effect: want 200, got %d (%s)", rec.Code, rec.Body.String())
	}

	// 3. KAL — the service command added in T29.
	kw := internalCmd(t, f,
		"/internal/books/"+f.bookID.String()+"/entities/"+kalEntity.String()+"/delete",
		"", f.ownerID.String())
	if kw.Code != http.StatusOK {
		t.Fatalf("KAL delete: want 200, got %d (%s)", kw.Code, kw.Body.String())
	}

	httpPayload := latestEventPayload(t, pool, f.entityID, "glossary.entity_deleted")
	mcpPayload := latestEventPayload(t, pool, mcpEntity, "glossary.entity_deleted")
	kalPayload := latestEventPayload(t, pool, kalEntity, "glossary.entity_deleted")

	for name, p := range map[string]map[string]any{"mcp": mcpPayload, "kal": kalPayload} {
		if !sameKeySet(httpPayload, p) {
			t.Errorf("%s delete emits a DIFFERENT field set than HTTP:\n  http=%v\n  %s=%v",
				name, keysOf(httpPayload), name, keysOf(p))
		}
		// Every field except the per-call ones must agree. `op` in particular: a transport
		// that announced a delete as something else would route the consumer to the wrong
		// handler while returning a perfectly good 2xx.
		for _, k := range []string{"op", "book_id", "actor_type"} {
			if httpPayload[k] != p[k] {
				t.Errorf("%s delete disagrees with HTTP on %q: http=%v %s=%v",
					name, k, httpPayload[k], name, p[k])
			}
		}
		// The one field that MUST differ — it identifies the entity acted on.
		if httpPayload["glossary_entity_id"] == p["glossary_entity_id"] {
			t.Errorf("%s and HTTP report the same entity; the test is not comparing two writes", name)
		}
	}
}

func TestStatusEmission_IdenticalAcrossHttpAndKal(t *testing.T) {
	// The T28 axis. There is no MCP status tool that writes directly — `glossary_propose_
	// curation` mints a card and the confirm effect writes — so the two live transports for
	// this transition are HTTP and the KAL, and both must say the same thing.
	pool := openTestDB(t)
	f := newVersionFixture(t, pool)

	kalEntity := seedSecondEntity(t, pool, f)

	if code := bulkStatus(t, f, "rejected", f.entityID); code != http.StatusOK {
		t.Fatalf("HTTP bulk-status: want 200, got %d", code)
	}
	body := `{"status":"rejected","entity_ids":["` + kalEntity.String() + `"]}`
	kw := internalCmd(t, f, "/internal/books/"+f.bookID.String()+"/entities/status",
		body, f.ownerID.String())
	if kw.Code != http.StatusOK {
		t.Fatalf("KAL status: want 200, got %d (%s)", kw.Code, kw.Body.String())
	}

	httpPayload := latestEventPayload(t, pool, f.entityID, "glossary.entity_status_changed")
	kalPayload := latestEventPayload(t, pool, kalEntity, "glossary.entity_status_changed")

	if !sameKeySet(httpPayload, kalPayload) {
		t.Errorf("the KAL status change emits a DIFFERENT field set than HTTP:\n  http=%v\n  kal=%v",
			keysOf(httpPayload), keysOf(kalPayload))
	}
	for _, k := range []string{"status", "prior_status", "book_id", "actor_type"} {
		if httpPayload[k] != kalPayload[k] {
			t.Errorf("the two transports disagree on %q: http=%v kal=%v",
				k, httpPayload[k], kalPayload[k])
		}
	}
}

func TestTransportIsTaggedAtTheBoundaryNotTheHandler(t *testing.T) {
	// The tag has to come from HOW the request arrived, not from what the handler thinks it
	// is — a handler that tagged itself would be describing its own name, and the two diverge
	// the first time a handler is reused by a second transport (which is this whole surface).
	if got := transportFromCtx(context.Background()); got != transportUnknown {
		t.Errorf("an untagged ctx must read as %q, got %q", transportUnknown, got)
	}
	if got := transportFromCtx(withTransport(context.Background(), transportMCP)); got != transportMCP {
		t.Errorf("tagged ctx: want %q, got %q", transportMCP, got)
	}

	// And the middleware must actually reach a handler's ctx — a tag that never arrives is
	// the "gate reading zero" failure: every log line would read `http` forever and look fine.
	var seen string
	h := transportMiddleware(transportInternal)(http.HandlerFunc(
		func(_ http.ResponseWriter, r *http.Request) { seen = transportFromCtx(r.Context()) }))
	h.ServeHTTP(httptest.NewRecorder(), httptest.NewRequest(http.MethodGet, "/x", nil))
	if seen != transportInternal {
		t.Errorf("middleware did not reach the handler ctx: want %q, got %q", transportInternal, seen)
	}
}

func TestCommandDispatchLogsItsTransport(t *testing.T) {
	// The plan asks for the transport on every command dispatch. Asserting the FIELD REACHES
	// THE LOG, not just that a helper returns the right string: a tag that is computed and
	// never emitted looks identical, in code review, to one that is — and reads as working
	// forever. Captured at the logger rather than eyeballed in a container, so it stays true.
	pool := openTestDB(t)
	f := newVersionFixture(t, pool)

	var buf bytes.Buffer
	prev := slog.Default()
	slog.SetDefault(slog.New(slog.NewJSONHandler(&buf, &slog.HandlerOptions{Level: slog.LevelDebug})))
	t.Cleanup(func() { slog.SetDefault(prev) })

	kalEntity := seedSecondEntity(t, pool, f)
	if w := internalCmd(t, f,
		"/internal/books/"+f.bookID.String()+"/entities/"+kalEntity.String()+"/delete",
		"", f.ownerID.String()); w.Code != http.StatusOK {
		t.Fatalf("KAL delete: want 200, got %d", w.Code)
	}
	kalLog := buf.String()
	if !strings.Contains(kalLog, `"transport":"internal"`) {
		t.Errorf("the KAL dispatch did not log transport=internal:\n%s", kalLog)
	}

	buf.Reset()
	req := httptest.NewRequest(http.MethodDelete,
		"/v1/glossary/books/"+f.bookID.String()+"/entities/"+f.entityID.String(), nil)
	req.Header.Set("Authorization", "Bearer "+f.token)
	w := httptest.NewRecorder()
	f.srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusNoContent {
		t.Fatalf("HTTP delete: want 204, got %d", w.Code)
	}
	httpLog := buf.String()
	if !strings.Contains(httpLog, `"transport":"http"`) {
		t.Errorf("the HTTP dispatch did not log transport=http:\n%s", httpLog)
	}
	// The two must be DISTINGUISHABLE. A tag that reported the same value everywhere would
	// satisfy both assertions above and tell an operator nothing.
	if strings.Contains(httpLog, `"transport":"internal"`) {
		t.Error("the HTTP dispatch logged the internal transport — the tag is not per-request")
	}
}

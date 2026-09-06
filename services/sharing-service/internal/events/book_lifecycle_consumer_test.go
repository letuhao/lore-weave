package events

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"
)

// DQ-T38's residue, owner ruling 2026-09-02: a sharing policy must not outlive its book.
//
// 🔴 THE MEASURED STATE THIS FIXES, 2026-09-02: 57 of 58 sharing_policies rows point at a book
// that no longer exists, including all 44 marked PUBLIC. Nothing cleaned them up and nothing
// could — sharing subscribed to nothing, and the two stores are separate databases so there is
// no FK cascade.
//
// The assertions below are mostly about the case where the consumer must do NOTHING, because
// that is where a cleanup turns into data loss: this code DELETES, and the input it deletes on
// is "book-service did not return the book".

type fakeReader struct {
	exists bool
	err    error
	calls  int
}

func (f *fakeReader) BookExists(context.Context, uuid.UUID) (bool, error) {
	f.calls++
	return f.exists, f.err
}

func msgFor(bookID string) redis.XMessage {
	return redis.XMessage{ID: "1-1", Values: map[string]any{
		"payload": `{"book_id":"` + bookID + `"}`,
	}}
}

// 🔴 THE ONE THAT MATTERS MOST. An unreachable book-service is NOT evidence a book is gone.
// Deleting here would make a live public book private with no audit trail and no way for the
// author to learn why — a far worse outcome than the orphan rows this consumer exists to remove.
func TestAnUnreachableBookServiceDefersRatherThanDeleting(t *testing.T) {
	r := &fakeReader{err: errors.New("connection refused")}
	c := &BookLifecycleConsumer{books: r} // nil pool: reaching the DELETE would panic, which is
	                                      // itself the assertion — the delete must be unreachable
	err := c.Apply(context.Background(), msgFor(uuid.NewString()))
	if err == nil {
		t.Fatal("a transport failure was treated as a decided outcome — the message would be " +
			"ACKED and the policy silently kept or dropped on a guess")
	}
	if r.calls != 1 {
		t.Errorf("book existence was checked %d times, want 1", r.calls)
	}
}

// A book that still exists must be left completely alone.
func TestALiveBookIsUntouched(t *testing.T) {
	r := &fakeReader{exists: true}
	c := &BookLifecycleConsumer{books: r} // nil pool again: any DELETE would panic
	if err := c.Apply(context.Background(), msgFor(uuid.NewString())); err != nil {
		t.Fatalf("Apply on a live book: %v", err)
	}
}

// Malformed input is not retryable — it must be acked (nil error) rather than redelivered forever.
func TestUnusableMessagesAreAckedNotRetriedForever(t *testing.T) {
	c := &BookLifecycleConsumer{books: &fakeReader{}}
	for name, m := range map[string]redis.XMessage{
		"no payload":    {ID: "1-1", Values: map[string]any{}},
		"not json":      {ID: "1-2", Values: map[string]any{"payload": "not json"}},
		"no book_id":    {ID: "1-3", Values: map[string]any{"payload": `{"other":1}`}},
		"bad uuid":      {ID: "1-4", Values: map[string]any{"payload": `{"book_id":"nope"}`}},
	} {
		if err := c.Apply(context.Background(), m); err != nil {
			t.Errorf("%s: returned an error, so it would be redelivered forever: %v", name, err)
		}
	}
}

// The consumer is DISABLED rather than half-wired when a dependency is missing. A consumer with
// no reader would answer "the book is gone" for every event and delete the whole table.
func TestItRefusesToRunHalfWired(t *testing.T) {
	pool := (*struct{})(nil) // stand-in; the constructor only nil-checks
	_ = pool
	c, err := NewBookLifecycleConsumer("redis://localhost:6379", nil, &fakeReader{})
	if err != nil || c != nil {
		t.Errorf("a nil pool produced a live consumer (c=%v err=%v)", c, err)
	}
	c, err = NewBookLifecycleConsumer("redis://localhost:6379", nil, nil)
	if err != nil || c != nil {
		t.Errorf("a nil reader produced a live consumer (c=%v err=%v)", c, err)
	}
}

// The HTTP reader must map book-service's answers the way the delete depends on: only a 404 is
// "gone". Anything it does not understand is an error, never a "no".
func TestTheReaderTreatsOnlyA404AsGone(t *testing.T) {
	cases := map[int]struct {
		exists bool
		isErr  bool
	}{
		http.StatusOK:                  {true, false},
		http.StatusNotFound:            {false, false},
		http.StatusInternalServerError: {false, true},
		http.StatusUnauthorized:        {false, true},
		http.StatusBadGateway:          {false, true},
	}
	for code, want := range cases {
		srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
			w.WriteHeader(code)
		}))
		r := &HTTPBookReader{BaseURL: srv.URL, InternalToken: "t"}
		exists, err := r.BookExists(context.Background(), uuid.New())
		if want.isErr && err == nil {
			t.Errorf("status %d was read as a decided answer (exists=%v) — a 5xx or a 401 must "+
				"never be treated as 'the book is gone'", code, exists)
		}
		if !want.isErr && err != nil {
			t.Errorf("status %d returned an error: %v", code, err)
		}
		if !want.isErr && exists != want.exists {
			t.Errorf("status %d -> exists=%v, want %v", code, exists, want.exists)
		}
		srv.Close()
	}
}

// It must send the internal token, or every check 401s and (per the test above) defers forever.
func TestTheReaderAuthenticates(t *testing.T) {
	var got string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		got = req.Header.Get("X-Internal-Token")
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()
	r := &HTTPBookReader{BaseURL: srv.URL, InternalToken: "sekrit"}
	if _, err := r.BookExists(context.Background(), uuid.New()); err != nil {
		t.Fatalf("BookExists: %v", err)
	}
	if got != "sekrit" {
		t.Errorf("X-Internal-Token = %q — an unauthenticated check 401s, which this consumer "+
			"correctly refuses to read as 'gone', so the orphan is never cleaned", got)
	}
}

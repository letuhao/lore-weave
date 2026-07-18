package loreweavecrypto

import (
	"context"
	"encoding/hex"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"
	"time"
)

// a fake auth-service that wraps a fixed DEK for whatever user is asked, recording fetch count.
func fakeAuth(t *testing.T, ring Keyring, dek []byte, fetches *int32) *httptest.Server {
	t.Helper()
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("X-Internal-Token") != "tok" {
			w.WriteHeader(http.StatusUnauthorized)
			return
		}
		atomic.AddInt32(fetches, 1)
		// path: /internal/users/<uid>/dek
		uid := r.URL.Path[len("/internal/users/") : len(r.URL.Path)-len("/dek")]
		wrapped, ref, err := WrapDEK(ring, dek, uid)
		if err != nil {
			w.WriteHeader(http.StatusInternalServerError)
			return
		}
		json.NewEncoder(w).Encode(map[string]string{"wrapped_dek": wrapped, "key_ref": ref})
	}))
}

func TestDEKClient_FetchesUnwrapsAndCaches(t *testing.T) {
	ring := NewKeyring(mustKey(t, "kek-1"))
	dek, _ := NewDEK()
	var fetches int32
	srv := fakeAuth(t, ring, dek, &fetches)
	defer srv.Close()

	c := NewDEKClient(srv.URL, "tok", ring)
	got, err := c.Get(context.Background(), "alice")
	if err != nil {
		t.Fatal(err)
	}
	if hex.EncodeToString(got) != hex.EncodeToString(dek) {
		t.Fatal("client returned the wrong DEK")
	}
	// second call is served from cache — no second fetch.
	if _, err := c.Get(context.Background(), "alice"); err != nil {
		t.Fatal(err)
	}
	if fetches != 1 {
		t.Fatalf("expected 1 auth fetch (cache hit on the 2nd), got %d", fetches)
	}
}

func TestDEKClient_ForgetForcesRefetch(t *testing.T) {
	ring := NewKeyring(mustKey(t, "kek-1"))
	dek, _ := NewDEK()
	var fetches int32
	srv := fakeAuth(t, ring, dek, &fetches)
	defer srv.Close()

	c := NewDEKClient(srv.URL, "tok", ring)
	c.Get(context.Background(), "alice")
	c.Forget("alice") // crypto-shred / rotation prompt path
	c.Get(context.Background(), "alice")
	if fetches != 2 {
		t.Fatalf("Forget must force a re-fetch: got %d fetches, want 2", fetches)
	}
}

func TestDEKClient_TTLExpiryRefetches(t *testing.T) {
	ring := NewKeyring(mustKey(t, "kek-1"))
	dek, _ := NewDEK()
	var fetches int32
	srv := fakeAuth(t, ring, dek, &fetches)
	defer srv.Close()

	now := time.Unix(1000, 0)
	c := NewDEKClient(srv.URL, "tok", ring, WithTTL(60*time.Second), withClock(func() time.Time { return now }))
	c.Get(context.Background(), "alice")
	now = now.Add(61 * time.Second) // past TTL — the backstop that bounds a shredded key's lifetime
	c.Get(context.Background(), "alice")
	if fetches != 2 {
		t.Fatalf("TTL expiry must re-fetch: got %d, want 2", fetches)
	}
}

func TestDEKClient_503RefusesNeverPlaintext(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusServiceUnavailable) // no KEK configured
	}))
	defer srv.Close()
	c := NewDEKClient(srv.URL, "tok", NewKeyring(mustKey(t, "kek-1")))
	if _, err := c.Get(context.Background(), "alice"); err == nil {
		t.Fatal("a 503 (no KEK) must be an error, never a silent fallback to plaintext")
	}
}

func TestDEKClient_WrongKEKCannotUnwrap(t *testing.T) {
	authRing := NewKeyring(mustKey(t, "auth-kek")) // auth wraps under one KEK
	dek, _ := NewDEK()
	var fetches int32
	srv := fakeAuth(t, authRing, dek, &fetches)
	defer srv.Close()
	// the client holds a DIFFERENT KEK — it must fail closed, not return garbage.
	c := NewDEKClient(srv.URL, "tok", NewKeyring(mustKey(t, "different-kek")))
	if _, err := c.Get(context.Background(), "alice"); err == nil {
		t.Fatal("a KEK that cannot unwrap must error (fail closed), never yield a wrong key")
	}
}

package loreweavecrypto

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"sync"
	"time"
)

// DEKClient fetches + unwraps + caches per-user DEKs from auth-service. The Go analogue of the Python
// DEKClient — a service that stores/reads a user's private content (here: book-service, for diary
// chapters) gets that user's DEK this one way:
//
//	auth-service ──(wrapped dek, over the internal network)──> DEKClient
//	                                                              │ unwrap with OUR KEK (Keyring)
//	                                                     plaintext DEK, in memory only
//
// The plaintext key never crosses the network, and auth-service stores only an opaque blob.
//
// A cached plaintext DEK is exactly what an operator with server access can read — the documented,
// accepted limit of this design (a server-side AI/render path must see plaintext). The cache does not
// make it worse (the key is unavoidably in memory whenever we decrypt), but do not pretend otherwise.
type DEKClient struct {
	base    string
	token   string
	ring    Keyring
	http    *http.Client
	ttl     time.Duration
	now     func() time.Time
	mu      sync.Mutex
	cache   map[string]dekEntry
	maxSize int
}

type dekEntry struct {
	dek       []byte
	expiresAt time.Time
}

// DEKClientOption configures a DEKClient.
type DEKClientOption func(*DEKClient)

// WithTTL overrides the cache TTL (default 5m). The TTL is a SAFETY BACKSTOP for erasure/rotation:
// Forget() is the prompt path, but a bounded lifetime bounds how long a shredded/rotated key can
// linger letting this process decrypt content that is supposed to be gone.
func WithTTL(ttl time.Duration) DEKClientOption { return func(c *DEKClient) { c.ttl = ttl } }

// WithHTTPClient injects an *http.Client (timeouts, test transport).
func WithHTTPClient(h *http.Client) DEKClientOption { return func(c *DEKClient) { c.http = h } }

// withClock is test-only (deterministic TTL expiry).
func withClock(now func() time.Time) DEKClientOption { return func(c *DEKClient) { c.now = now } }

// NewDEKClient builds a client. authBaseURL is auth-service's internal base; internalToken gates the
// boundary; ring is THIS service's KEK set (the one that can unwrap what auth wrapped).
func NewDEKClient(authBaseURL, internalToken string, ring Keyring, opts ...DEKClientOption) *DEKClient {
	c := &DEKClient{
		base:    trimSlash(authBaseURL),
		token:   internalToken,
		ring:    ring,
		http:    &http.Client{Timeout: 5 * time.Second},
		ttl:     5 * time.Minute,
		now:     time.Now,
		cache:   make(map[string]dekEntry),
		maxSize: 512,
	}
	for _, o := range opts {
		o(c)
	}
	return c
}

func trimSlash(s string) string {
	for len(s) > 0 && s[len(s)-1] == '/' {
		s = s[:len(s)-1]
	}
	return s
}

// Forget drops a cached key. Call on erasure (crypto-shred) and on KEK rotation — a stale cached DEK
// for a user whose key was destroyed would let this process keep decrypting content that is supposed
// to be unrecoverable. The TTL is the backstop; this is the prompt path.
func (c *DEKClient) Forget(userID string) {
	c.mu.Lock()
	delete(c.cache, userID)
	c.mu.Unlock()
}

// Get returns the user's plaintext DEK, provisioning it on first use (auth mints on first read).
// Returns an error on ANY failure — auth down, no KEK configured (503), a blob we cannot unwrap. The
// caller MUST abort, never degrade to plaintext: a "temporarily unencrypted" write is permanent and
// looks identical to an encrypted row to every future reader.
func (c *DEKClient) Get(ctx context.Context, userID string) ([]byte, error) {
	c.mu.Lock()
	if e, ok := c.cache[userID]; ok {
		if c.now().Before(e.expiresAt) {
			dek := e.dek
			c.mu.Unlock()
			return dek, nil
		}
		delete(c.cache, userID) // expired → re-fetch (a shredded key re-fetches to a NEW one or fails)
	}
	c.mu.Unlock()

	url := fmt.Sprintf("%s/internal/users/%s/dek", c.base, userID)
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return nil, fmt.Errorf("%w: build DEK request for %s: %v", ErrCrypto, userID, err)
	}
	req.Header.Set("X-Internal-Token", c.token)
	resp, err := c.http.Do(req)
	if err != nil {
		return nil, fmt.Errorf("%w: auth-service unreachable fetching the DEK for %s (%v). Refusing "+
			"to continue — writing this content unencrypted is not an option", ErrCrypto, userID, err)
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusServiceUnavailable {
		return nil, fmt.Errorf("%w: auth-service reports no diary encryption key is configured — "+
			"private content cannot be stored; fix the deployment, do not store plaintext", ErrCrypto)
	}
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("%w: auth-service returned %d fetching the DEK for %s",
			ErrCrypto, resp.StatusCode, userID)
	}

	var body struct {
		WrappedDEK string `json:"wrapped_dek"`
		KeyRef     string `json:"key_ref"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&body); err != nil || body.WrappedDEK == "" {
		return nil, fmt.Errorf("%w: malformed DEK response for %s", ErrCrypto, userID)
	}

	// Pass userID — auth bound the wrap to it (AAD); a wrapped_dek belonging to a different user
	// (a row-swap) fails to unwrap here.
	dek, err := UnwrapDEK(c.ring, body.WrappedDEK, userID)
	if err != nil {
		return nil, fmt.Errorf("%w: could not unwrap the DEK for %s (key_ref=%q) with this service's "+
			"KEK. If the KEK was rotated, the PREVIOUS value must be in the retired keyring: %v",
			ErrCrypto, userID, body.KeyRef, err)
	}

	c.mu.Lock()
	c.cache[userID] = dekEntry{dek: dek, expiresAt: c.now().Add(c.ttl)}
	if len(c.cache) > c.maxSize {
		// bounded: evict an arbitrary entry (a large multi-tenant worker must not pin every key).
		for k := range c.cache {
			if k != userID {
				delete(c.cache, k)
				break
			}
		}
	}
	c.mu.Unlock()
	return dek, nil
}

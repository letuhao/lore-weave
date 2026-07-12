package grantclient

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"net/url"
	"strings"
	"sync"
	"time"

	"github.com/google/uuid"
)

// Sentinels returned by RequireGrant / ResolveGrant.
var (
	// ErrForbidden — the resolved grant does not satisfy the required level.
	ErrForbidden = errors.New("grant: not accessible")
	// ErrUnavailable — book-service could not be reached (or returned non-200),
	// so the grant is UNKNOWN and the caller must fail closed (deny).
	ErrUnavailable = errors.New("grant: authority unavailable")
)

// DefaultCacheTTL is the positive-grant cache lifetime. 45s (not 60s) so the
// worst-case revoke→deny wall-clock — TTL plus request/poll overhead — stays
// comfortably under the AC4 ≤60s bound (a live-smoke measured ~66s at a 60s TTL;
// D-E0-CACHE-TTL-TUNE).
const DefaultCacheTTL = 45 * time.Second

// Options configures NewClient.
type Options struct {
	// BaseURL of book-service, e.g. "http://book-service:8082". Required.
	BaseURL string
	// InternalToken sent as X-Internal-Token on every /access call. Required.
	InternalToken string
	// CacheTTL overrides DefaultCacheTTL when > 0.
	CacheTTL time.Duration
	// Transport overrides http.DefaultTransport. Inject an instrumented
	// RoundTripper (e.g. observability.HTTPTransport(nil)) for trace
	// propagation; nil uses the default (no tracing).
	Transport http.RoundTripper
}

// Access is a resolved (grant, book-lifecycle, kind) triple from the /access authority.
type Access struct {
	Level     GrantLevel
	Lifecycle string // book lifecycle_state: "active"|"trashed"|"purge_pending"; "" if book absent
	// Kind is the book's kind ("novel"|"document"|"lore"|"diary"); "" if the book is
	// absent, the caller holds no grant (book-service only returns kind to a grantee — no
	// existence oracle, WS-1.2 D16), or the deployment predates the WS-1.2 kind contract.
	// Lets a server-side consumer branch on kind WITHOUT trusting a caller-supplied arg
	// (e.g. the work-capture flavor selected from kind='diary', WS-1.6 spec 05 §Q3).
	Kind string
}

// Active reports whether the book is in its normal editable state. Edit/manage
// operations should gate on this (a trashed/purge_pending book is read-only).
func (a Access) Active() bool { return a.Lifecycle == "active" }

type cacheEntry struct {
	access Access
	exp    time.Time
}

// Client resolves (user, book) grants against book-service with a short-TTL
// positive-only cache. Goroutine-safe; construct one per process.
type Client struct {
	baseURL       string
	internalToken string
	ttl           time.Duration
	http          *http.Client
	cache         sync.Map // key "userID:bookID" -> cacheEntry
	now           func() time.Time
}

// NewClient validates options and returns a usable Client.
func NewClient(opts Options) (*Client, error) {
	if strings.TrimSpace(opts.BaseURL) == "" {
		return nil, errors.New("grantclient: BaseURL is required")
	}
	if strings.TrimSpace(opts.InternalToken) == "" {
		return nil, errors.New("grantclient: InternalToken is required")
	}
	ttl := opts.CacheTTL
	if ttl <= 0 {
		ttl = DefaultCacheTTL
	}
	transport := opts.Transport
	if transport == nil {
		transport = http.DefaultTransport
	}
	return &Client{
		baseURL:       strings.TrimRight(opts.BaseURL, "/"),
		internalToken: opts.InternalToken,
		ttl:           ttl,
		http:          &http.Client{Transport: transport, Timeout: 10 * time.Second},
		now:           time.Now,
	}, nil
}

// ResolveAccess returns the grant level userID holds on bookID plus the book's
// lifecycle state. Positive grants are cached for the TTL; `none` and transport
// errors are never cached. On a book-service failure it returns
// (zero Access, ErrUnavailable) — fail closed.
func (c *Client) ResolveAccess(ctx context.Context, bookID, userID uuid.UUID) (Access, error) {
	key := userID.String() + ":" + bookID.String()
	if v, ok := c.cache.Load(key); ok {
		if e := v.(cacheEntry); c.now().Before(e.exp) {
			return e.access, nil
		}
	}
	acc, err := c.fetch(ctx, bookID, userID)
	if err != nil {
		return Access{}, err
	}
	if acc.Level > GrantNone {
		c.cache.Store(key, cacheEntry{access: acc, exp: c.now().Add(c.ttl)})
	}
	return acc, nil
}

// ResolveGrant returns just the grant level (see ResolveAccess). Fail-closed:
// a book-service failure returns (GrantNone, ErrUnavailable).
func (c *Client) ResolveGrant(ctx context.Context, bookID, userID uuid.UUID) (GrantLevel, error) {
	acc, err := c.ResolveAccess(ctx, bookID, userID)
	return acc.Level, err
}

// RequireGrant resolves the grant and returns nil iff it satisfies need.
// Returns ErrForbidden when under-privileged, ErrUnavailable when the authority
// can't be reached (propagated from ResolveGrant — fail closed).
func (c *Client) RequireGrant(ctx context.Context, bookID, userID uuid.UUID, need GrantLevel) error {
	lvl, err := c.ResolveGrant(ctx, bookID, userID)
	if err != nil {
		return err
	}
	if !lvl.AtLeast(need) {
		return ErrForbidden
	}
	return nil
}

// Invalidate drops the cached (user, book) grant so the next resolve re-fetches.
// Powers instant revoke (D-GRANT-INSTANT-REVOKE): the consuming service tails the
// book-service grant_revoke stream and calls this on each event, so a revoke takes
// effect at once instead of after the TTL. Goroutine-safe (sync.Map). Returns true
// if an entry was actually removed (false = nothing cached, a safe no-op). The SDK
// stays redis-free — the stream transport lives in the consuming service.
func (c *Client) Invalidate(bookID, userID uuid.UUID) bool {
	key := userID.String() + ":" + bookID.String()
	_, existed := c.cache.LoadAndDelete(key)
	return existed
}

func (c *Client) fetch(ctx context.Context, bookID, userID uuid.UUID) (Access, error) {
	u := fmt.Sprintf("%s/internal/books/%s/access?user_id=%s",
		c.baseURL, bookID.String(), url.QueryEscape(userID.String()))
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, u, nil)
	if err != nil {
		return Access{}, ErrUnavailable
	}
	req.Header.Set("X-Internal-Token", c.internalToken)
	resp, err := c.http.Do(req)
	if err != nil {
		return Access{}, ErrUnavailable
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return Access{}, ErrUnavailable
	}
	var body struct {
		GrantLevel string `json:"grant_level"`
		Lifecycle  string `json:"lifecycle_state"`
		Kind       string `json:"kind"` // grant-gated by book-service; "" to a non-grantee
	}
	if err := json.NewDecoder(resp.Body).Decode(&body); err != nil {
		return Access{}, ErrUnavailable
	}
	return Access{Level: ParseGrantLevel(body.GrantLevel), Lifecycle: body.Lifecycle, Kind: body.Kind}, nil
}

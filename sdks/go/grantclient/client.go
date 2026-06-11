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

// DefaultCacheTTL is the positive-grant cache lifetime (AC4: revoke ≤60s).
const DefaultCacheTTL = 60 * time.Second

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

type cacheEntry struct {
	level GrantLevel
	exp   time.Time
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

// ResolveGrant returns the level userID holds on bookID. Positive grants are
// cached for the TTL; `none` and transport errors are never cached. On a
// book-service failure it returns (GrantNone, ErrUnavailable) — fail closed.
func (c *Client) ResolveGrant(ctx context.Context, bookID, userID uuid.UUID) (GrantLevel, error) {
	key := userID.String() + ":" + bookID.String()
	if v, ok := c.cache.Load(key); ok {
		if e := v.(cacheEntry); c.now().Before(e.exp) {
			return e.level, nil
		}
	}
	lvl, err := c.fetch(ctx, bookID, userID)
	if err != nil {
		return GrantNone, err
	}
	if lvl > GrantNone {
		c.cache.Store(key, cacheEntry{level: lvl, exp: c.now().Add(c.ttl)})
	}
	return lvl, nil
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

func (c *Client) fetch(ctx context.Context, bookID, userID uuid.UUID) (GrantLevel, error) {
	u := fmt.Sprintf("%s/internal/books/%s/access?user_id=%s",
		c.baseURL, bookID.String(), url.QueryEscape(userID.String()))
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, u, nil)
	if err != nil {
		return GrantNone, ErrUnavailable
	}
	req.Header.Set("X-Internal-Token", c.internalToken)
	resp, err := c.http.Do(req)
	if err != nil {
		return GrantNone, ErrUnavailable
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return GrantNone, ErrUnavailable
	}
	var body struct {
		GrantLevel string `json:"grant_level"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&body); err != nil {
		return GrantNone, ErrUnavailable
	}
	return ParseGrantLevel(body.GrantLevel), nil
}

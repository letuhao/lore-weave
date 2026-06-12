// Package glossary_client is the L5.F.4 Go HTTP/JSON client for
// glossary-service canon RPCs.
//
// RAID cycle 25 DPS 2. Per Q-L5-4 LOCKED: HTTP/JSON V1. The client is
// hand-written (not generated from canon_read.yaml + canon_write.yaml)
// for cycle-25 minimal surface; codegen via `tools/contractgen` ships
// in L4.G / a future cycle (D-CONTRACTGEN-GLOSSARY-CLIENT).
//
// # Surface
//
//   - GetCanonEntry(book_id, attribute_path, [reality_id]) — single read
//   - ListCanonEntries(book_id, since=, limit, cursor) — bulk since= sync
//   - WriteCanonEntry(req) — admin/extraction write (Q-L5-5 guardrail
//     check happens server-side)
//   - ExportCanonForSeed(book_id) — NDJSON stream for L5.G reality seed
//
// # Wiring
//
//   - svidToken — caller supplies the SPIFFE SVID JWT per request via
//     ClientConfig.SVIDProvider. Production wires a workload-API
//     fetcher (cycle 4 SPIFFE binding); tests use a static func.
//   - HTTP client — default is http.DefaultClient with a 5s timeout.
//     Production wires the cycle-18 resilience.Bulkhead + retry budget.
//   - Errors — typed (ErrNotFound / ErrForbidden / ErrGuardrailRejected
//     / generic *HTTPError). Callers branch on errors.As.
//
// # Q-IDs honored
//
//   - Q-L5-4: HTTP/JSON V1
//   - Q-L5-5: WriteCanonEntry surfaces 409 GuardrailViolation as a typed
//     *GuardrailRejectedError
//   - Q-L5-3: CanonLayer enum strings match cycle-23 contract
//
// # Retry semantics (cycle 18 resilience integration)
//
// The client itself is RETRY-FREE — callers wrap with cycle-18
// `resilience.WithRetry` / `WithTimeout` / `Bulkhead`. The reason: this
// keeps the client surface inspectable and tests deterministic; cross-
// cutting policy (backoff, deadline, jitter) is the caller's choice.
package glossary_client

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"
)

// ─────────────────────────────────────────────────────────────────────────
// Errors.
// ─────────────────────────────────────────────────────────────────────────

// ErrNotFound — HTTP 404 from GetCanonEntry.
var ErrNotFound = errors.New("glossary_client: canon entry not found")

// ErrForbidden — HTTP 403 (ACL mismatch).
var ErrForbidden = errors.New("glossary_client: caller SVID not authorized")

// ErrUnauthorized — HTTP 401 (missing / invalid SVID).
var ErrUnauthorized = errors.New("glossary_client: missing or invalid SVID")

// HTTPError wraps an unexpected HTTP response.
type HTTPError struct {
	StatusCode int
	Code       string
	Message    string
}

// Error implements error.
func (e *HTTPError) Error() string {
	return fmt.Sprintf("glossary_client: HTTP %d code=%s msg=%s", e.StatusCode, e.Code, e.Message)
}

// GuardrailRejectedError — HTTP 409 from WriteCanonEntry per Q-L5-5.
// The body carries the GuardrailViolation; callers MUST surface this
// to the user.
type GuardrailRejectedError struct {
	Code          string         `json:"code"`
	Axiom         CanonReference `json:"axiom"`
	ProposedValue json.RawMessage `json:"proposed_value"`
	Reason        string         `json:"reason"`
}

// Error implements error.
func (e *GuardrailRejectedError) Error() string {
	return fmt.Sprintf("glossary_client: guardrail rejected (Q-L5-5) book=%s attr=%s reason=%s",
		e.Axiom.BookID, e.Axiom.AttributePath, e.Reason)
}

// CanonReference is the L1 axiom info inside a GuardrailRejectedError.
type CanonReference struct {
	BookID        string          `json:"book_id"`
	AttributePath string          `json:"attribute_path"`
	CanonLayer    string          `json:"canon_layer"`
	Value         json.RawMessage `json:"value"`
}

// ─────────────────────────────────────────────────────────────────────────
// Wire types — mirror contracts/api/glossary-service/canon_read.yaml +
// canon_write.yaml schemas.
// ─────────────────────────────────────────────────────────────────────────

// CanonEntry is the per-canon response shape.
type CanonEntry struct {
	CanonEntryID            string          `json:"canon_entry_id"`
	BookID                  string          `json:"book_id"`
	AttributePath           string          `json:"attribute_path"`
	Value                   json.RawMessage `json:"value"`
	CanonLayer              string          `json:"canon_layer"`
	LockLevel               string          `json:"lock_level"`
	RealityID               *string         `json:"reality_id,omitempty"`
	OverriddenByL3EventID   *string         `json:"overridden_by_l3_event_id,omitempty"`
	LastSyncedAt            time.Time       `json:"last_synced_at"`
}

// CanonEntryPage is the bulk-read response.
type CanonEntryPage struct {
	Entries    []CanonEntry `json:"entries"`
	NextCursor *string      `json:"next_cursor,omitempty"`
}

// CanonWriteRequest is the POST /v1/canon body.
type CanonWriteRequest struct {
	CanonEntryID  *string         `json:"canon_entry_id,omitempty"`
	BookID        string          `json:"book_id"`
	AttributePath string          `json:"attribute_path"`
	Value         json.RawMessage `json:"value"`
	CanonLayer    string          `json:"canon_layer"`
	LockLevel     string          `json:"lock_level,omitempty"`
	RealityID     *string         `json:"reality_id,omitempty"`
}

// CanonWriteResponse is the POST /v1/canon success body.
type CanonWriteResponse struct {
	CanonEntryID string    `json:"canon_entry_id"`
	WrittenAt    time.Time `json:"written_at"`
	CanonLayer   string    `json:"canon_layer"`
}

// ─────────────────────────────────────────────────────────────────────────
// Client.
// ─────────────────────────────────────────────────────────────────────────

// SVIDProvider returns the SPIFFE SVID JWT to attach to outbound
// requests. Production wires a workload-API client; tests use a static
// func.
type SVIDProvider func(ctx context.Context) (string, error)

// Client is the glossary-service HTTP/JSON client.
type Client struct {
	baseURL  string
	http     *http.Client
	svid     SVIDProvider
	clientID string
}

// ClientConfig bundles construction parameters.
type ClientConfig struct {
	// BaseURL e.g. "https://glossary-service.loreweave.dev" — no trailing slash.
	BaseURL string
	// HTTP client; defaults to one with 5s Timeout.
	HTTP *http.Client
	// SVID provider (required).
	SVID SVIDProvider
	// ClientID is a free-form identifier emitted via X-Client-ID header
	// for server-side audit.
	ClientID string
}

// New constructs a Client. BaseURL + SVID are required.
func New(cfg ClientConfig) (*Client, error) {
	if cfg.BaseURL == "" {
		return nil, errors.New("glossary_client: BaseURL empty")
	}
	if cfg.SVID == nil {
		return nil, errors.New("glossary_client: SVID provider nil")
	}
	httpCli := cfg.HTTP
	if httpCli == nil {
		httpCli = &http.Client{Timeout: 5 * time.Second}
	}
	return &Client{
		baseURL:  strings.TrimRight(cfg.BaseURL, "/"),
		http:     httpCli,
		svid:     cfg.SVID,
		clientID: cfg.ClientID,
	}, nil
}

// ─────────────────────────────────────────────────────────────────────────
// Methods.
// ─────────────────────────────────────────────────────────────────────────

// GetCanonEntry reads a single canon entry. If realityID is non-empty,
// applies per-reality projection (L3 overrides honored).
func (c *Client) GetCanonEntry(ctx context.Context, bookID, attributePath, realityID string) (*CanonEntry, error) {
	if bookID == "" || attributePath == "" {
		return nil, errors.New("glossary_client: bookID + attributePath required")
	}
	u := fmt.Sprintf("%s/v1/canon/%s/%s", c.baseURL, url.PathEscape(bookID), url.PathEscape(attributePath))
	if realityID != "" {
		u += "?reality_id=" + url.QueryEscape(realityID)
	}
	resp, err := c.do(ctx, http.MethodGet, u, nil)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if err := classifyStatus(resp); err != nil {
		return nil, err
	}
	var entry CanonEntry
	if err := json.NewDecoder(resp.Body).Decode(&entry); err != nil {
		return nil, fmt.Errorf("glossary_client: decode GetCanonEntry: %w", err)
	}
	return &entry, nil
}

// ListCanonEntries fetches a page of canon entries with optional
// since= filter for incremental sync. Pass cursor "" for first page.
func (c *Client) ListCanonEntries(ctx context.Context, bookID string, since *time.Time, limit int, cursor string) (*CanonEntryPage, error) {
	if bookID == "" {
		return nil, errors.New("glossary_client: bookID required")
	}
	q := url.Values{}
	if since != nil {
		q.Set("since", since.UTC().Format(time.RFC3339Nano))
	}
	if limit > 0 {
		q.Set("limit", strconv.Itoa(limit))
	}
	if cursor != "" {
		q.Set("cursor", cursor)
	}
	u := fmt.Sprintf("%s/v1/canon/%s/entries", c.baseURL, url.PathEscape(bookID))
	if encoded := q.Encode(); encoded != "" {
		u += "?" + encoded
	}
	resp, err := c.do(ctx, http.MethodGet, u, nil)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if err := classifyStatus(resp); err != nil {
		return nil, err
	}
	var page CanonEntryPage
	if err := json.NewDecoder(resp.Body).Decode(&page); err != nil {
		return nil, fmt.Errorf("glossary_client: decode ListCanonEntries: %w", err)
	}
	return &page, nil
}

// WriteCanonEntry POSTs a canon write. Q-L5-5: returns
// *GuardrailRejectedError on HTTP 409.
func (c *Client) WriteCanonEntry(ctx context.Context, req CanonWriteRequest) (*CanonWriteResponse, error) {
	if req.BookID == "" || req.AttributePath == "" || req.CanonLayer == "" {
		return nil, errors.New("glossary_client: BookID + AttributePath + CanonLayer required")
	}
	body, err := json.Marshal(req)
	if err != nil {
		return nil, fmt.Errorf("glossary_client: marshal WriteCanonEntry: %w", err)
	}
	u := c.baseURL + "/v1/canon"
	resp, err := c.do(ctx, http.MethodPost, u, body)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode == http.StatusConflict {
		var v GuardrailRejectedError
		if err := json.NewDecoder(resp.Body).Decode(&v); err != nil {
			return nil, fmt.Errorf("glossary_client: decode GuardrailViolation: %w", err)
		}
		return nil, &v
	}
	if err := classifyStatus(resp); err != nil {
		return nil, err
	}
	var out CanonWriteResponse
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return nil, fmt.Errorf("glossary_client: decode WriteCanonEntry: %w", err)
	}
	return &out, nil
}

// ExportCanonForSeed streams the bulk canon export for L5.G reality
// seeding. visit is called once per CanonEntry; final envelope is
// returned (or error).
func (c *Client) ExportCanonForSeed(ctx context.Context, bookID string, visit func(CanonEntry) error) (*SeedExportEnvelope, error) {
	if bookID == "" {
		return nil, errors.New("glossary_client: bookID required")
	}
	u := fmt.Sprintf("%s/v1/canon/%s/seed_export", c.baseURL, url.PathEscape(bookID))
	resp, err := c.do(ctx, http.MethodGet, u, nil)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if err := classifyStatus(resp); err != nil {
		return nil, err
	}
	dec := json.NewDecoder(resp.Body)
	dec.UseNumber()
	var env SeedExportEnvelope
	for {
		var raw json.RawMessage
		if err := dec.Decode(&raw); err != nil {
			if errors.Is(err, io.EOF) {
				break
			}
			return nil, fmt.Errorf("glossary_client: NDJSON decode: %w", err)
		}
		// Probe for the envelope sentinel.
		var probe struct {
			Envelope string `json:"_envelope"`
		}
		if err := json.Unmarshal(raw, &probe); err == nil && probe.Envelope == "seed_export_complete" {
			if err := json.Unmarshal(raw, &env); err != nil {
				return nil, fmt.Errorf("glossary_client: parse envelope: %w", err)
			}
			break
		}
		var entry CanonEntry
		if err := json.Unmarshal(raw, &entry); err != nil {
			return nil, fmt.Errorf("glossary_client: parse CanonEntry: %w", err)
		}
		if visit != nil {
			if err := visit(entry); err != nil {
				return nil, err
			}
		}
	}
	return &env, nil
}

// SeedExportEnvelope is the final NDJSON line from ExportCanonForSeed.
type SeedExportEnvelope struct {
	Envelope   string    `json:"_envelope"`
	SnapshotAt time.Time `json:"snapshot_at"`
	EntryCount int       `json:"entry_count"`
	NextCursor *string   `json:"next_cursor,omitempty"`
}

// ─────────────────────────────────────────────────────────────────────────
// Internals.
// ─────────────────────────────────────────────────────────────────────────

func (c *Client) do(ctx context.Context, method, url string, body []byte) (*http.Response, error) {
	var reqBody io.Reader
	if body != nil {
		reqBody = strings.NewReader(string(body))
	}
	req, err := http.NewRequestWithContext(ctx, method, url, reqBody)
	if err != nil {
		return nil, fmt.Errorf("glossary_client: new request: %w", err)
	}
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	req.Header.Set("Accept", "application/json")
	if c.clientID != "" {
		req.Header.Set("X-Client-ID", c.clientID)
	}
	svid, err := c.svid(ctx)
	if err != nil {
		return nil, fmt.Errorf("glossary_client: fetch SVID: %w", err)
	}
	if svid == "" {
		return nil, errors.New("glossary_client: SVID empty")
	}
	req.Header.Set("Authorization", "Bearer "+svid)

	return c.http.Do(req)
}

func classifyStatus(resp *http.Response) error {
	if resp.StatusCode >= 200 && resp.StatusCode < 300 {
		return nil
	}
	switch resp.StatusCode {
	case http.StatusNotFound:
		return ErrNotFound
	case http.StatusUnauthorized:
		return ErrUnauthorized
	case http.StatusForbidden:
		return ErrForbidden
	}
	// Best-effort decode an error envelope.
	var env struct {
		Code    string `json:"code"`
		Message string `json:"message"`
	}
	_ = json.NewDecoder(resp.Body).Decode(&env)
	return &HTTPError{StatusCode: resp.StatusCode, Code: env.Code, Message: env.Message}
}

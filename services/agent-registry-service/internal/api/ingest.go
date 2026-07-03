package api

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"
	"unicode/utf8"

	"github.com/google/uuid"
)

// ── P5 REG-P5-03: official MCP Registry ingest + admin curation ──────────────
//
// An admin pulls the public server list from the official MCP Registry into a
// curation queue; nothing federates until an explicit approve creates a
// System-tier mcp_server_registration that then passes the SAME P3 supply-chain
// scan. verification ≠ safety — an official listing is untrusted until scanned.
// No credentials are ingested. Admin-only + anti-oracle 404 on unknown ids.

const (
	maxIngestPages = 10        // page cap (upstream courtesy + bound)
	ingestBodyCap  = 8 << 20   // 8 MiB per page
)

type ingestRow struct {
	IngestID         uuid.UUID       `json:"ingest_id"`
	Source           string          `json:"source"`
	RegistryID       string          `json:"registry_id"`
	Name             string          `json:"name"`
	Description      string          `json:"description"`
	Version          string          `json:"version"`
	EndpointURL      string          `json:"endpoint_url"`
	Raw              json.RawMessage `json:"raw"`
	Status           string          `json:"status"`
	ReviewedBy       *uuid.UUID      `json:"reviewed_by,omitempty"`
	ApprovedServerID *uuid.UUID      `json:"approved_server_id,omitempty"`
	RejectReason     string          `json:"reject_reason"`
	FirstSeenAt      time.Time       `json:"first_seen_at"`
	UpdatedAt        time.Time       `json:"updated_at"`
}

const ingestCols = `ingest_id, source, registry_id, name, description, version, endpoint_url, raw, status, reviewed_by, approved_server_id, reject_reason, first_seen_at, updated_at`

func scanIngest(row interface{ Scan(...any) error }, g *ingestRow) error {
	return row.Scan(&g.IngestID, &g.Source, &g.RegistryID, &g.Name, &g.Description, &g.Version,
		&g.EndpointURL, &g.Raw, &g.Status, &g.ReviewedBy, &g.ApprovedServerID, &g.RejectReason,
		&g.FirstSeenAt, &g.UpdatedAt)
}

// ── upstream entry mapping ───────────────────────────────────────────────────

type upstreamRemote struct {
	Type          string `json:"type"`
	TransportType string `json:"transport_type"`
	URL           string `json:"url"`
}

type upstreamVersionDetail struct {
	Version string `json:"version"`
}

type upstreamServer struct {
	ID            string                 `json:"id"`
	Name          string                 `json:"name"`
	Description   string                 `json:"description"`
	Version       string                 `json:"version"`
	VersionDetail *upstreamVersionDetail `json:"version_detail"`
	Remotes       []upstreamRemote       `json:"remotes"`
}

type ingestMapped struct {
	RegistryID  string
	Name        string
	Description string
	Version     string
	Endpoint    string
	Raw         json.RawMessage
}

// normTransport lowercases + hyphenates a transport tag ("streamable_http" →
// "streamable-http"), preferring `type` then `transport_type`.
func normTransport(typ, transportType string) string {
	t := typ
	if t == "" {
		t = transportType
	}
	return strings.ReplaceAll(strings.ToLower(strings.TrimSpace(t)), "_", "-")
}

// mapUpstreamEntry maps one upstream server entry to a queue row. Returns
// reason="" on success, "no_remote" when the entry has no usable streamable-http
// remote (a COUNTED skip — we never silently drop coverage), or "invalid" when it
// has no name. Tolerant of both the flat and the nested-`server` upstream shapes
// (the /v0 schema is young — spec §10).
func mapUpstreamEntry(raw json.RawMessage) (ingestMapped, string) {
	var e upstreamServer
	_ = json.Unmarshal(raw, &e)
	if e.Name == "" {
		var wrap struct {
			Server upstreamServer `json:"server"`
		}
		if json.Unmarshal(raw, &wrap) == nil && wrap.Server.Name != "" {
			e = wrap.Server
		}
	}
	if strings.TrimSpace(e.Name) == "" {
		return ingestMapped{}, "invalid"
	}
	endpoint := ""
	for _, rm := range e.Remotes {
		if normTransport(rm.Type, rm.TransportType) == "streamable-http" && strings.TrimSpace(rm.URL) != "" {
			endpoint = strings.TrimSpace(rm.URL)
			break
		}
	}
	if endpoint == "" {
		return ingestMapped{}, "no_remote"
	}
	version := e.Version
	if version == "" && e.VersionDetail != nil {
		version = e.VersionDetail.Version
	}
	regID := e.ID
	if regID == "" {
		regID = e.Name // reverse-DNS name is stable across pulls
	}
	// Cap upstream-controlled strings so a hostile listing can't bloat the queue
	// (the raw entry is already bounded by the per-page body cap).
	return ingestMapped{
		RegistryID:  clampStr(regID, 512),
		Name:        clampStr(e.Name, 512),
		Description: clampStr(e.Description, 4096),
		Version:     clampStr(version, 64),
		Endpoint:    clampStr(endpoint, 2048),
		Raw:         raw,
	}, ""
}

// clampStr truncates s to at most n bytes (rune-safe: never splits a multi-byte rune).
func clampStr(s string, n int) string {
	if len(s) <= n {
		return s
	}
	for n > 0 && !utf8.RuneStart(s[n]) {
		n--
	}
	return s[:n]
}

// ── the pull ─────────────────────────────────────────────────────────────────

type pullCounts struct {
	Fetched         int  `json:"fetched"`
	New             int  `json:"new"`
	Updated         int  `json:"updated"`
	SkippedNoRemote int  `json:"skipped_no_remote"`
	// Truncated is true when the pull stopped before exhausting the upstream cursor
	// (a timeout / mid-pull error / the page cap) — so the admin knows the counts are
	// PARTIAL, not a complete snapshot (a denylist-sync must not treat it as complete).
	Truncated bool `json:"truncated"`
}

// pullOfficialRegistry fetches the upstream server list through the SSRF-safe probe
// client and upserts each usable entry into the queue. Bounded (page cap, body cap,
// deadline) and fail-soft: a page-0 failure is returned; a later-page failure ends
// the pull with a partial result (logged via counts).
func (s *Server) pullOfficialRegistry(ctx context.Context) (pullCounts, error) {
	base := strings.TrimRight(s.cfg.OfficialRegistryURL, "/")
	if base == "" {
		return pullCounts{}, fmt.Errorf("official registry URL not configured")
	}
	client := newProbeClient(s.cfg.AllowInternalMcpTargets)
	counts := pullCounts{}
	cursor := ""
	for page := 0; page < maxIngestPages; page++ {
		u := base + "/v0/servers?limit=100"
		if cursor != "" {
			u += "&cursor=" + url.QueryEscape(cursor)
		}
		req, err := http.NewRequestWithContext(ctx, http.MethodGet, u, nil)
		if err != nil {
			return counts, err
		}
		req.Header.Set("Accept", "application/json")
		resp, err := client.Do(req)
		if err != nil {
			if page == 0 {
				return counts, err
			}
			counts.Truncated = true
			break // fail-soft — a partial pull, flagged as such
		}
		body, _ := io.ReadAll(io.LimitReader(resp.Body, ingestBodyCap))
		_ = resp.Body.Close()
		if resp.StatusCode != http.StatusOK {
			if page == 0 {
				return counts, fmt.Errorf("upstream registry returned %d", resp.StatusCode)
			}
			counts.Truncated = true
			break
		}
		var pageResp struct {
			Servers  []json.RawMessage `json:"servers"`
			Data     []json.RawMessage `json:"data"`
			Metadata struct {
				NextCursor string `json:"next_cursor"`
			} `json:"metadata"`
		}
		if err := json.Unmarshal(body, &pageResp); err != nil {
			if page == 0 {
				return counts, fmt.Errorf("upstream registry response not JSON")
			}
			counts.Truncated = true
			break
		}
		entries := pageResp.Servers
		if len(entries) == 0 {
			entries = pageResp.Data
		}
		for _, raw := range entries {
			counts.Fetched++
			m, reason := mapUpstreamEntry(raw)
			if reason == "no_remote" {
				counts.SkippedNoRemote++
				continue
			}
			if reason != "" {
				continue
			}
			inserted, err := s.upsertIngest(ctx, m)
			if err != nil {
				continue
			}
			if inserted {
				counts.New++
			} else {
				counts.Updated++
			}
		}
		cursor = pageResp.Metadata.NextCursor
		if cursor == "" {
			break
		}
	}
	// Reached the page cap with more pages still pending → the pull is partial.
	if cursor != "" {
		counts.Truncated = true
	}
	return counts, nil
}

// upsertIngest inserts or refreshes a queue row keyed by (source, registry_id).
// The upsert updates only descriptive fields — it NEVER touches `status`, so a
// re-pull never downgrades an approved/rejected row back to pending. Returns true
// when the row was newly inserted (xmax=0 idiom).
func (s *Server) upsertIngest(ctx context.Context, m ingestMapped) (bool, error) {
	raw := m.Raw
	if len(raw) == 0 {
		raw = json.RawMessage("{}")
	}
	var inserted bool
	err := s.db.QueryRow(ctx,
		`INSERT INTO registry_ingest_queue (source, registry_id, name, description, version, endpoint_url, raw)
		 VALUES ('official',$1,$2,$3,$4,$5,$6)
		 ON CONFLICT (source, registry_id) DO UPDATE
		   SET name=EXCLUDED.name, description=EXCLUDED.description, version=EXCLUDED.version,
		       endpoint_url=EXCLUDED.endpoint_url, raw=EXCLUDED.raw, updated_at=now()
		 RETURNING (xmax = 0)`,
		m.RegistryID, m.Name, m.Description, m.Version, m.Endpoint, string(raw)).Scan(&inserted)
	return inserted, err
}

// ── admin gate ───────────────────────────────────────────────────────────────

// requireAdmin is the preamble for the ingest routes: a valid JWT AND role==admin.
// A non-admin gets 403 (the route is admin-only); an unknown ingest id later gets
// anti-oracle 404.
func (s *Server) requireAdmin(w http.ResponseWriter, r *http.Request) (uuid.UUID, bool) {
	uid, role, ok := s.requireUser(w, r)
	if !ok {
		return uuid.Nil, false
	}
	if role != "admin" {
		writeError(w, http.StatusForbidden, "FORBIDDEN", "admin only")
		return uuid.Nil, false
	}
	return uid, true
}

// ── handlers ─────────────────────────────────────────────────────────────────

// ingestPull — POST /admin/ingest/pull. Fetch the official registry → upsert queue.
func (s *Server) ingestPull(w http.ResponseWriter, r *http.Request) {
	uid, ok := s.requireAdmin(w, r)
	if !ok {
		return
	}
	ctx, cancel := context.WithTimeout(r.Context(), 30*time.Second)
	defer cancel()
	counts, err := s.pullOfficialRegistry(ctx)
	if err != nil {
		writeError(w, http.StatusBadGateway, "UPSTREAM_ERROR", "official registry pull failed: "+err.Error())
		return
	}
	s.audit(r.Context(), uid, "admin", "registry_ingest", "pull", nil, "official", "system", map[string]any{
		"fetched": counts.Fetched, "new": counts.New, "updated": counts.Updated,
		"skipped_no_remote": counts.SkippedNoRemote, "truncated": counts.Truncated,
	})
	writeJSON(w, http.StatusOK, counts)
}

// listIngestQueue — GET /admin/ingest/queue?status=&limit=&offset=.
func (s *Server) listIngestQueue(w http.ResponseWriter, r *http.Request) {
	if _, ok := s.requireAdmin(w, r); !ok {
		return
	}
	q := r.URL.Query()
	limit := clampLimit(q.Get("limit"))
	offset := atoiDefault(q.Get("offset"), 0)
	if offset < 0 {
		offset = 0
	}
	where := "1=1"
	args := []any{}
	if v := q.Get("status"); v != "" {
		args = append(args, v)
		where = "status = $1"
	}
	total := s.queryInt(r.Context(), `SELECT COUNT(*) FROM registry_ingest_queue WHERE `+where, args...)
	args = append(args, limit, offset)
	rows, err := s.db.Query(r.Context(),
		`SELECT `+ingestCols+` FROM registry_ingest_queue WHERE `+where+
			` ORDER BY first_seen_at DESC LIMIT $`+strconv.Itoa(len(args)-1)+` OFFSET $`+strconv.Itoa(len(args)), args...)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "could not list queue")
		return
	}
	defer rows.Close()
	items := []ingestRow{}
	for rows.Next() {
		var g ingestRow
		if err := scanIngest(rows, &g); err == nil {
			items = append(items, g)
		}
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items, "total": total, "limit": limit, "offset": offset})
}

// approveIngest — POST /admin/ingest/queue/{id}/approve. Reuses the P3 model-cap +
// SSRF guard, dedups the endpoint, creates a System-tier registration (pending) and
// fires the P3 scan, then links + marks the queue row approved. A guard failure
// leaves the row pending.
func (s *Server) approveIngest(w http.ResponseWriter, r *http.Request) {
	uid, ok := s.requireAdmin(w, r)
	if !ok {
		return
	}
	gid, ok := parseUUIDParam(w, r, "ingest_id")
	if !ok {
		return
	}
	var name, endpoint, status string
	if err := s.db.QueryRow(r.Context(),
		`SELECT name, endpoint_url, status FROM registry_ingest_queue WHERE ingest_id=$1`, gid).
		Scan(&name, &endpoint, &status); err != nil {
		writeError(w, http.StatusNotFound, "NOT_FOUND", "ingest entry not found")
		return
	}
	if status != "pending" {
		writeError(w, http.StatusConflict, "ALREADY_REVIEWED", "this entry is already "+status)
		return
	}
	// Provider-gateway invariant first (syntactic), then the SSRF resolve.
	if m := looksLikeModelEndpoint(endpoint, name); m != "" {
		writeError(w, http.StatusBadRequest, "MODEL_CAPABILITY_NOT_ALLOWED",
			"this looks like a model endpoint ("+m+"); it cannot federate as an MCP tool server")
		return
	}
	class, err := classifyRegistrationURL(r.Context(), nil, endpoint, s.cfg.AllowInternalMcpTargets)
	if err != nil {
		writeError(w, http.StatusBadRequest, "SSRF_BLOCKED", err.Error())
		return
	}
	// Endpoint dedup (§7b#3): a System server for this endpoint already exists → link,
	// don't create a second row.
	var existingID uuid.UUID
	if err := s.db.QueryRow(r.Context(),
		`SELECT mcp_server_id FROM mcp_server_registrations WHERE tier='system' AND endpoint_url=$1`,
		class.Normalized).Scan(&existingID); err == nil {
		s.finishApprove(r, gid, existingID, uid, name)
		writeJSON(w, http.StatusOK, map[string]any{"ingest_id": gid, "status": "approved", "mcp_server_id": existingID, "linked_existing": true})
		return
	}
	// Create the System-tier registration (is_external, pending until the scan clears).
	// Namespaced under s_<hash>_ so the ingested server can't shadow a platform tool
	// name and is dispatchable via the overlay (matches createMcpServer's external path).
	egress := buildEgressAllowlist(class.Normalized, nil)
	prefix := systemToolPrefix(class.Normalized)
	var newID uuid.UUID
	err = s.db.QueryRow(r.Context(),
		`INSERT INTO mcp_server_registrations
		   (tier, display_name, endpoint_url, tool_name_prefix, status, auth_kind, is_external, egress_allowlist)
		 VALUES ('system',$1,$2,$3,'pending','none',true,$4) RETURNING mcp_server_id`,
		name, class.Normalized, prefix, egress).Scan(&newID)
	if err != nil {
		// A concurrent approve of the same endpoint raced us → link to the winner.
		if isUniqueViolation(err) {
			if e2 := s.db.QueryRow(r.Context(),
				`SELECT mcp_server_id FROM mcp_server_registrations WHERE tier='system' AND endpoint_url=$1`,
				class.Normalized).Scan(&existingID); e2 == nil {
				s.finishApprove(r, gid, existingID, uid, name)
				writeJSON(w, http.StatusOK, map[string]any{"ingest_id": gid, "status": "approved", "mcp_server_id": existingID, "linked_existing": true})
				return
			}
		}
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "could not create System server")
		return
	}
	s.bumpCatalogVersion(r.Context())
	s.scanAsync(newID) // pending → active (clean) / suspended (flagged)
	s.finishApprove(r, gid, newID, uid, name)
	writeJSON(w, http.StatusOK, map[string]any{"ingest_id": gid, "status": "approved", "mcp_server_id": newID, "scan": "started"})
}

// finishApprove marks the queue row approved + linked + audited.
func (s *Server) finishApprove(r *http.Request, gid, serverID, uid uuid.UUID, name string) {
	_, _ = s.db.Exec(r.Context(),
		`UPDATE registry_ingest_queue SET status='approved', approved_server_id=$2, reviewed_by=$3, updated_at=now()
		 WHERE ingest_id=$1`, gid, serverID, uid)
	s.audit(r.Context(), uid, "admin", "registry_ingest", "approve", &gid, name, "system",
		map[string]any{"mcp_server_id": serverID.String()})
}

// rejectIngest — POST /admin/ingest/queue/{id}/reject.
func (s *Server) rejectIngest(w http.ResponseWriter, r *http.Request) {
	uid, ok := s.requireAdmin(w, r)
	if !ok {
		return
	}
	gid, ok := parseUUIDParam(w, r, "ingest_id")
	if !ok {
		return
	}
	var body struct {
		Reason string `json:"reason"`
	}
	_ = decodeJSON(w, r, &body) // reason optional; a bad body just yields empty reason
	ct, err := s.db.Exec(r.Context(),
		`UPDATE registry_ingest_queue SET status='rejected', reject_reason=$2, reviewed_by=$3, updated_at=now()
		 WHERE ingest_id=$1 AND status='pending'`, gid, body.Reason, uid)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "could not reject entry")
		return
	}
	if ct.RowsAffected() == 0 {
		writeError(w, http.StatusNotFound, "NOT_FOUND", "no pending ingest entry with that id")
		return
	}
	s.audit(r.Context(), uid, "admin", "registry_ingest", "reject", &gid, "", "system", map[string]any{"reason": body.Reason})
	writeJSON(w, http.StatusOK, map[string]any{"ingest_id": gid, "status": "rejected"})
}

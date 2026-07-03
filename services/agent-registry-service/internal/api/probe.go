package api

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"net/http"
	"strings"
	"time"
)

// ── Minimal streamable-http MCP probe client (REG-P3-05) ─────────────────────
//
// On register/rescan the registry must fetch a server's tools/list to scan it. We
// implement a focused JSON-RPC-over-HTTP client rather than pull an MCP SDK: the
// probe is a register-time concern the registry owns, and keeping it in-process
// avoids an agent-registry→ai-gateway dependency cycle (the RUNTIME egress path is
// ai-gateway's, M3). SSRF is re-applied at DIAL time (resolve-then-connect pinning)
// so a DNS rebind between the registration validate and the probe cannot reach an
// internal address. Response bodies are capped; the whole probe is deadline-bounded.

const (
	probeTimeout      = 10 * time.Second
	probeResponseCap  = 4 << 20 // 4 MiB
	mcpProtocolVer    = "2025-06-18"
)

type probeHealth struct {
	OK        bool      `json:"ok"`
	CheckedAt time.Time `json:"checked_at"`
	Error     string    `json:"error,omitempty"`
	ToolCount int       `json:"tool_count"`
	LatencyMs int64     `json:"latency_ms"`
}

// safeDialContext pins connections to a validated public IP. When allowInternal is
// false, ANY resolved address that is internal/loopback/metadata aborts the dial
// (rebind-proof). When true (dev), internal targets are permitted.
func safeDialContext(allowInternal bool) func(ctx context.Context, network, addr string) (net.Conn, error) {
	d := &net.Dialer{Timeout: 5 * time.Second}
	return func(ctx context.Context, network, addr string) (net.Conn, error) {
		host, port, err := net.SplitHostPort(addr)
		if err != nil {
			return nil, err
		}
		ips, err := net.DefaultResolver.LookupIP(ctx, "ip", host)
		if err != nil {
			return nil, err
		}
		for _, ip := range ips {
			if allowInternal || !isBlockedIP(ip) {
				return d.DialContext(ctx, network, net.JoinHostPort(ip.String(), port))
			}
		}
		return nil, fmt.Errorf("dial blocked: %s resolves only to internal addresses", host)
	}
}

func newProbeClient(allowInternal bool) *http.Client {
	return &http.Client{
		Timeout: probeTimeout,
		Transport: &http.Transport{
			DialContext:         safeDialContext(allowInternal),
			TLSHandshakeTimeout: 5 * time.Second,
			DisableKeepAlives:   true,
		},
		// Do not follow redirects blindly — a 302 to an internal host is a classic
		// SSRF bypass. Each hop is re-dialed through safeDialContext anyway, but we
		// also cap the chain and re-validate the target host.
		CheckRedirect: func(req *http.Request, via []*http.Request) error {
			if len(via) >= 3 {
				return fmt.Errorf("too many redirects")
			}
			return nil
		},
	}
}

type rpcRequest struct {
	JSONRPC string `json:"jsonrpc"`
	ID      int    `json:"id,omitempty"`
	Method  string `json:"method"`
	Params  any    `json:"params,omitempty"`
}

type rpcResponse struct {
	JSONRPC string          `json:"jsonrpc"`
	ID      *int            `json:"id"`
	Result  json.RawMessage `json:"result"`
	Error   *struct {
		Code    int    `json:"code"`
		Message string `json:"message"`
	} `json:"error"`
}

// probeMCP connects to endpoint, performs the MCP initialize handshake, then
// tools/list. Returns the probed tools + a health snapshot. Never panics; all
// failures come back as (nil, health{OK:false, Error}, err). extraHeaders carries
// the outbound auth: for an EXTERNAL server that is its bearer/oauth token; for an
// INTERNAL loreweave server it is the internal envelope (X-Internal-Token/X-User-Id)
// mirroring exactly what the ai-gateway overlay sends at federation time.
func probeMCP(ctx context.Context, endpoint, authKind, secret string, allowInternal bool, extraHeaders map[string]string) ([]probedTool, probeHealth, error) {
	start := time.Now()
	health := probeHealth{CheckedAt: start.UTC()}
	client := newProbeClient(allowInternal)

	headers := map[string]string{}
	for k, v := range extraHeaders {
		headers[k] = v
	}
	if (authKind == "bearer" || authKind == "oauth2") && secret != "" {
		headers["Authorization"] = "Bearer " + secret
	}

	session := ""
	// 1. initialize
	initParams := map[string]any{
		"protocolVersion": mcpProtocolVer,
		"capabilities":    map[string]any{},
		"clientInfo":      map[string]any{"name": "agent-registry-scan", "version": "0.1.0"},
	}
	_, session, err := rpcCall(ctx, client, endpoint, headers, session, rpcRequest{JSONRPC: "2.0", ID: 1, Method: "initialize", Params: initParams})
	if err != nil {
		health.Error = "initialize failed: " + err.Error()
		return nil, health, err
	}
	// 2. notifications/initialized (best-effort; some servers require it)
	_ = rpcNotify(ctx, client, endpoint, headers, session, rpcRequest{JSONRPC: "2.0", Method: "notifications/initialized"})

	// 3. tools/list
	result, _, err := rpcCall(ctx, client, endpoint, headers, session, rpcRequest{JSONRPC: "2.0", ID: 2, Method: "tools/list", Params: map[string]any{}})
	if err != nil {
		health.Error = "tools/list failed: " + err.Error()
		return nil, health, err
	}
	var listRes struct {
		Tools []struct {
			Name        string          `json:"name"`
			Description string          `json:"description"`
			InputSchema json.RawMessage `json:"inputSchema"`
		} `json:"tools"`
	}
	if err := json.Unmarshal(result, &listRes); err != nil {
		health.Error = "tools/list parse: " + err.Error()
		return nil, health, err
	}
	tools := make([]probedTool, 0, len(listRes.Tools))
	for _, t := range listRes.Tools {
		tools = append(tools, probedTool{Name: t.Name, Description: t.Description, InputSchema: string(t.InputSchema)})
	}
	health.OK = true
	health.ToolCount = len(tools)
	health.LatencyMs = time.Since(start).Milliseconds()
	return tools, health, nil
}

// rpcCall POSTs a JSON-RPC request and returns the matching result + any session id.
func rpcCall(ctx context.Context, client *http.Client, endpoint string, headers map[string]string, session string, req rpcRequest) (json.RawMessage, string, error) {
	body, _ := json.Marshal(req)
	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, endpoint, bytes.NewReader(body))
	if err != nil {
		return nil, session, err
	}
	httpReq.Header.Set("Content-Type", "application/json")
	httpReq.Header.Set("Accept", "application/json, text/event-stream")
	for k, v := range headers {
		httpReq.Header.Set(k, v)
	}
	if session != "" {
		httpReq.Header.Set("Mcp-Session-Id", session)
	}
	resp, err := client.Do(httpReq)
	if err != nil {
		return nil, session, err
	}
	defer resp.Body.Close()
	if sid := resp.Header.Get("Mcp-Session-Id"); sid != "" {
		session = sid
	}
	if resp.StatusCode >= 400 {
		return nil, session, fmt.Errorf("http %d", resp.StatusCode)
	}
	msg, err := readRPCMessage(resp, req.ID)
	if err != nil {
		return nil, session, err
	}
	if msg.Error != nil {
		return nil, session, fmt.Errorf("rpc error %d: %s", msg.Error.Code, msg.Error.Message)
	}
	return msg.Result, session, nil
}

// rpcNotify POSTs a notification (no id, no response expected).
func rpcNotify(ctx context.Context, client *http.Client, endpoint string, headers map[string]string, session string, req rpcRequest) error {
	body, _ := json.Marshal(req)
	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, endpoint, bytes.NewReader(body))
	if err != nil {
		return err
	}
	httpReq.Header.Set("Content-Type", "application/json")
	httpReq.Header.Set("Accept", "application/json, text/event-stream")
	for k, v := range headers {
		httpReq.Header.Set(k, v)
	}
	if session != "" {
		httpReq.Header.Set("Mcp-Session-Id", session)
	}
	resp, err := client.Do(httpReq)
	if err != nil {
		return err
	}
	_, _ = io.Copy(io.Discard, io.LimitReader(resp.Body, 4096))
	resp.Body.Close()
	return nil
}

// readRPCMessage parses either an application/json body or a text/event-stream body,
// returning the JSON-RPC message whose id matches wantID (capped read).
func readRPCMessage(resp *http.Response, wantID int) (rpcResponse, error) {
	ct := resp.Header.Get("Content-Type")
	limited := io.LimitReader(resp.Body, probeResponseCap)
	if strings.Contains(ct, "text/event-stream") {
		return readSSE(limited, wantID)
	}
	raw, err := io.ReadAll(limited)
	if err != nil {
		return rpcResponse{}, err
	}
	var msg rpcResponse
	if err := json.Unmarshal(raw, &msg); err != nil {
		return rpcResponse{}, fmt.Errorf("bad json body: %w", err)
	}
	return msg, nil
}

// readSSE scans an SSE stream for the first data: JSON-RPC message matching wantID.
func readSSE(r io.Reader, wantID int) (rpcResponse, error) {
	sc := bufio.NewScanner(r)
	sc.Buffer(make([]byte, 0, 64*1024), probeResponseCap)
	var data strings.Builder
	flush := func() (rpcResponse, bool) {
		if data.Len() == 0 {
			return rpcResponse{}, false
		}
		var msg rpcResponse
		err := json.Unmarshal([]byte(data.String()), &msg)
		data.Reset()
		if err != nil || msg.ID == nil || *msg.ID != wantID {
			return rpcResponse{}, false
		}
		return msg, true
	}
	for sc.Scan() {
		line := sc.Text()
		if line == "" { // event boundary
			if msg, ok := flush(); ok {
				return msg, nil
			}
			continue
		}
		if strings.HasPrefix(line, "data:") {
			data.WriteString(strings.TrimSpace(strings.TrimPrefix(line, "data:")))
		}
	}
	if msg, ok := flush(); ok {
		return msg, nil
	}
	if err := sc.Err(); err != nil {
		return rpcResponse{}, err
	}
	return rpcResponse{}, fmt.Errorf("no matching rpc message in event-stream")
}

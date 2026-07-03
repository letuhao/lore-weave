package api

import (
	"context"
	"encoding/json"
	"fmt"
	"net"
	"net/url"
	"strings"
	"time"
)

// ── P3 SSRF guard + capability rejection ────────────────────────────────────
//
// P2 shipped isInternalHost, a SCOPING guard that only ALLOWED internal endpoints
// (external → 400). P3 inverts the model: a user may register an arbitrary EXTERNAL
// MCP URL, but a user-supplied URL must NEVER be allowed to point the platform's
// fetch at an internal/loopback/metadata address (that is the SSRF hole). So the P3
// validator ALLOWS public hosts and REJECTS private/loopback/link-local/metadata/
// unspecified — the exact inverse — with a dev-only escape hatch (allowInternal) so
// the overlay/scan/egress paths stay live-smokeable against an in-cluster MCP server.

// ipResolver resolves a hostname to its IPs. Injected so the SSRF classifier is
// unit-testable without real DNS (a public host resolving to a private IP is the
// DNS-rebind shape the fixture suite must reject).
type ipResolver func(ctx context.Context, host string) ([]net.IP, error)

func defaultResolver(ctx context.Context, host string) ([]net.IP, error) {
	c, cancel := context.WithTimeout(ctx, 3*time.Second)
	defer cancel()
	return net.DefaultResolver.LookupIP(c, "ip", host)
}

// isBlockedIP reports whether an IP is off-limits for a user-supplied MCP target:
// loopback, RFC1918 / ULA (IsPrivate), link-local (incl. 169.254.169.254 cloud
// metadata), multicast, and the unspecified address. Everything else is public.
func isBlockedIP(ip net.IP) bool {
	if ip == nil {
		return true // unparseable → fail closed
	}
	if ip4 := ip.To4(); ip4 != nil {
		// 0.0.0.0/8 (incl. 0.0.0.0) and 100.64.0.0/10 (CGNAT) are also non-routable.
		if ip4[0] == 0 || (ip4[0] == 100 && ip4[1] >= 64 && ip4[1] <= 127) {
			return true
		}
	}
	return ip.IsLoopback() || ip.IsPrivate() || ip.IsLinkLocalUnicast() ||
		ip.IsLinkLocalMulticast() || ip.IsMulticast() || ip.IsUnspecified() ||
		ip.IsInterfaceLocalMulticast()
}

// urlClass is the classification result: the normalized URL + whether it is external.
type urlClass struct {
	Normalized string
	IsExternal bool
}

// classifyRegistrationURL parses + SSRF-validates a user-supplied MCP endpoint.
// Returns (class, nil) when acceptable; (_, err) with a model-friendly message on
// reject. When allowInternal is true (dev flag), internal targets are permitted and
// classified IsExternal=false (used to keep the P3 paths smokeable in-cluster).
func classifyRegistrationURL(ctx context.Context, resolve ipResolver, raw string, allowInternal bool) (urlClass, error) {
	u, err := url.Parse(strings.TrimSpace(raw))
	if err != nil {
		return urlClass{}, fmt.Errorf("endpoint_url is not a valid URL")
	}
	if u.Scheme != "http" && u.Scheme != "https" {
		return urlClass{}, fmt.Errorf("endpoint_url must be http(s) (streamable-http transport only)")
	}
	host := u.Hostname()
	if host == "" {
		return urlClass{}, fmt.Errorf("endpoint_url has no host")
	}
	lower := strings.ToLower(host)

	// Literal IP → check the block list directly (no DNS).
	if ip := net.ParseIP(host); ip != nil {
		if isBlockedIP(ip) {
			if allowInternal {
				return urlClass{Normalized: u.String(), IsExternal: false}, nil
			}
			return urlClass{}, ssrfError(host)
		}
		return urlClass{Normalized: u.String(), IsExternal: true}, nil
	}

	// A name with no dots (bare docker service), *.internal, or localhost is an
	// internal name — allowed ONLY under the dev flag.
	if lower == "localhost" || strings.HasSuffix(lower, ".internal") || strings.HasSuffix(lower, ".local") || !strings.Contains(host, ".") {
		if allowInternal {
			return urlClass{Normalized: u.String(), IsExternal: false}, nil
		}
		return urlClass{}, ssrfError(host)
	}

	// Public-looking hostname → resolve and reject if ANY answer is a blocked IP
	// (DNS-rebind protection). Unresolvable → fail closed.
	if resolve == nil {
		resolve = defaultResolver
	}
	ips, err := resolve(ctx, host)
	if err != nil || len(ips) == 0 {
		return urlClass{}, fmt.Errorf("endpoint_url host could not be resolved")
	}
	for _, ip := range ips {
		if isBlockedIP(ip) {
			if allowInternal {
				return urlClass{Normalized: u.String(), IsExternal: false}, nil
			}
			return urlClass{}, ssrfError(host)
		}
	}
	return urlClass{Normalized: u.String(), IsExternal: true}, nil
}

func ssrfError(host string) error {
	return fmt.Errorf("endpoint_url %q resolves to an internal/loopback/metadata address; only public MCP servers may be registered", host)
}

// modelCapabilityMarkers are substrings that betray a MODEL endpoint (chat/embed/
// rerank/completions) rather than a tool MCP server. Registering one would smuggle a
// provider around the provider-registry BYOK invariant, so we reject it with a pointer.
var modelCapabilityMarkers = []string{
	"/v1/chat/completions", "/v1/completions", "/v1/embeddings", "/v1/rerank",
	"/v1/responses", "/v1/messages", "/api/generate", "/api/chat", "/api/embeddings",
	"/embeddings", "/rerank", "/generatecontent", ":11434", // ollama default port
	"api.openai.com", "api.anthropic.com", "generativelanguage.googleapis.com",
	"api.cohere.ai", "api.mistral.ai", "api.groq.com",
	"ollama", "lm_studio", "lmstudio", "reranker", "text-embedding",
}

// looksLikeModelEndpoint returns the matched marker (or "") when the URL/name reads
// as a model-capability endpoint that must go through provider-registry BYOK instead.
func looksLikeModelEndpoint(rawURL, displayName string) string {
	hay := strings.ToLower(rawURL + " " + displayName)
	for _, m := range modelCapabilityMarkers {
		if strings.Contains(hay, m) {
			return m
		}
	}
	return ""
}

// buildEgressAllowlist returns the per-server outbound host allowlist the ai-gateway
// egress path (REG-P3-04) enforces: always the endpoint's own host:port, plus any
// caller-supplied extra hosts (deduped, lowercased). Marshalled to a JSON array.
func buildEgressAllowlist(endpoint string, extra []string) []byte {
	seen := map[string]bool{}
	out := []string{}
	add := func(h string) {
		h = strings.ToLower(strings.TrimSpace(h))
		if h == "" || seen[h] {
			return
		}
		seen[h] = true
		out = append(out, h)
	}
	if u, err := url.Parse(endpoint); err == nil {
		add(u.Host) // host:port as it appears in the endpoint
	}
	for _, h := range extra {
		add(h)
	}
	b, _ := json.Marshal(out)
	return b
}

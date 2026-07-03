package api

import (
	"context"
	"encoding/json"
	"net"
	"strings"
	"testing"
)

// fakeResolver maps a hostname to fixed IPs so the SSRF classifier is testable
// without real DNS. An unmapped host returns an error (unresolvable → fail-closed).
func fakeResolver(m map[string][]string) ipResolver {
	return func(_ context.Context, host string) ([]net.IP, error) {
		ips, ok := m[host]
		if !ok {
			return nil, &net.DNSError{Err: "no such host", Name: host}
		}
		out := make([]net.IP, 0, len(ips))
		for _, s := range ips {
			out = append(out, net.ParseIP(s))
		}
		return out, nil
	}
}

// REG-P3-01 — the SSRF guard. External public hosts are ALLOWED; internal/loopback/
// link-local/metadata (incl. DNS-rebind: a public name resolving to a private IP)
// are REJECTED. allowInternal=false = the prod posture.
func TestClassifyRegistrationURL_SSRF(t *testing.T) {
	res := fakeResolver(map[string][]string{
		"mcp.example.com":      {"93.184.216.34"},              // public → allow
		"tools.example.org":    {"93.184.216.34"},              // public → allow
		"rebind.attacker.net":  {"10.0.0.5"},                   // DNS-rebind → private → reject
		"rebind6.attacker.net": {"fd00::1"},                    // ULA → reject
		"mixed.attacker.net":   {"93.184.216.34", "127.0.0.1"}, // ANY private → reject
	})

	allow := []string{
		"https://mcp.example.com/mcp",
		"http://93.184.216.34/mcp", // public literal IP
		"https://tools.example.org/mcp/",
	}
	reject := []string{
		"http://169.254.169.254/latest/meta-data", // cloud metadata
		"http://169.254.169.254/mcp",
		"http://127.0.0.1:8099/mcp",   // loopback
		"http://10.0.0.5/mcp",         // RFC1918
		"http://172.16.3.4:8080/mcp",  // RFC1918
		"http://192.168.1.10/mcp",     // RFC1918
		"http://[::1]/mcp",            // IPv6 loopback
		"http://0.0.0.0/mcp",          // unspecified
		"http://100.100.0.1/mcp",      // CGNAT
		"http://localhost:1234/mcp",   // internal name
		"http://agent-registry:8099/mcp", // bare service name
		"https://svc.internal/mcp",    // *.internal
		"http://rebind.attacker.net/mcp",  // DNS-rebind → private
		"http://rebind6.attacker.net/mcp", // DNS-rebind → ULA
		"http://mixed.attacker.net/mcp",   // one private answer
		"http://unresolvable.nx/mcp",  // NXDOMAIN → fail-closed
		"ftp://mcp.example.com/mcp",   // wrong scheme
		"not-a-url-at-all",            // unparseable / no host
		"http:///mcp",                 // no host
	}
	for _, u := range allow {
		c, err := classifyRegistrationURL(context.Background(), res, u, false)
		if err != nil {
			t.Errorf("expected ALLOW %q, got err: %v", u, err)
			continue
		}
		if !c.IsExternal {
			t.Errorf("expected %q classified EXTERNAL", u)
		}
	}
	for _, u := range reject {
		if _, err := classifyRegistrationURL(context.Background(), res, u, false); err == nil {
			t.Errorf("expected REJECT %q, but it was allowed", u)
		}
	}
}

// The dev flag permits internal targets (classified NOT-external) so the P3 paths
// stay smokeable in-cluster; a public host is still external.
func TestClassifyRegistrationURL_AllowInternal(t *testing.T) {
	res := fakeResolver(map[string][]string{"mcp.example.com": {"93.184.216.34"}})
	internal := []string{
		"http://agent-registry-service:8099/mcp",
		"http://127.0.0.1:8099/mcp",
		"http://host.docker.internal:9000/mcp",
	}
	for _, u := range internal {
		c, err := classifyRegistrationURL(context.Background(), res, u, true)
		if err != nil {
			t.Errorf("dev flag should ALLOW internal %q: %v", u, err)
			continue
		}
		if c.IsExternal {
			t.Errorf("internal %q must not be classified external", u)
		}
	}
	c, err := classifyRegistrationURL(context.Background(), res, "https://mcp.example.com/mcp", true)
	if err != nil || !c.IsExternal {
		t.Errorf("public host stays external under the dev flag; got %+v err=%v", c, err)
	}
}

// REG-P3-01 — a model-capability endpoint is rejected with a provider-registry pointer.
func TestLooksLikeModelEndpoint(t *testing.T) {
	hits := []struct{ url, name string }{
		{"http://ollama:11434/mcp", ""},
		{"https://api.openai.com/v1/chat/completions", ""},
		{"https://host/v1/embeddings", ""},
		{"https://host/mcp", "Ollama Local Models"}, // name betrays it
		{"https://api.anthropic.com/v1/messages", ""},
	}
	for _, h := range hits {
		if m := looksLikeModelEndpoint(h.url, h.name); m == "" {
			t.Errorf("expected model-endpoint reject for %q / %q", h.url, h.name)
		}
	}
	if m := looksLikeModelEndpoint("https://tools.example.com/mcp", "Weather Tools"); m != "" {
		t.Errorf("a genuine tool server must NOT be flagged, got marker %q", m)
	}
}

func TestBuildEgressAllowlist(t *testing.T) {
	b := buildEgressAllowlist("https://mcp.example.com:8443/mcp", []string{"cdn.example.com", "MCP.EXAMPLE.COM:8443", ""})
	var hosts []string
	if err := json.Unmarshal(b, &hosts); err != nil {
		t.Fatalf("bad json: %v", err)
	}
	joined := strings.Join(hosts, ",")
	if !strings.Contains(joined, "mcp.example.com:8443") {
		t.Errorf("endpoint host must be in the allowlist, got %v", hosts)
	}
	if !strings.Contains(joined, "cdn.example.com") {
		t.Errorf("extra host missing, got %v", hosts)
	}
	// deduped + lowercased: the endpoint host appears once.
	n := 0
	for _, h := range hosts {
		if h == "mcp.example.com:8443" {
			n++
		}
	}
	if n != 1 {
		t.Errorf("endpoint host should be deduped to 1, got %d in %v", n, hosts)
	}
}

package api

import "testing"

// /review-impl — isInternalHost is the P2 scoping guard (external URLs are P3).
// Its most important property: it must REJECT link-local (169.254.169.254 cloud
// metadata) and any public host, while allowing legit internal endpoints.
func TestIsInternalHost(t *testing.T) {
	allow := []string{
		"http://host.docker.internal:9000/mcp",
		"http://agent-registry-service:8099/mcp", // bare docker service name
		"http://localhost:1234/mcp",
		"http://127.0.0.1:1234/mcp",
		"http://10.0.0.5/mcp",       // RFC1918
		"http://172.16.3.4:8080/mcp", // RFC1918
		"http://192.168.1.10/mcp",   // RFC1918
		"http://[::1]/mcp",          // IPv6 loopback
		"https://svc.internal/mcp",
	}
	reject := []string{
		"http://169.254.169.254/latest/meta-data",   // cloud metadata SSRF — MUST reject
		"http://169.254.169.254/mcp",                //
		"https://mcp.example.com/mcp",               // public domain
		"http://8.8.8.8/mcp",                        // public IP
		"http://0.0.0.0/mcp",                        // unspecified
		"ftp://internal/mcp",                        // wrong scheme
		"not-a-url",                                 // unparseable
		"http:///mcp",                               // no host
		"http://evil.com.attacker.net/mcp",          // public multi-dot
	}
	for _, u := range allow {
		if _, ok := isInternalHost(u); !ok {
			t.Errorf("expected ALLOW: %q", u)
		}
	}
	for _, u := range reject {
		if _, ok := isInternalHost(u); ok {
			t.Errorf("expected REJECT: %q", u)
		}
	}
}

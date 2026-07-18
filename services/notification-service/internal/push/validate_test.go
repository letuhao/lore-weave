package push

import "testing"

// HIGH-1 — the SSRF guard. https-only + reject private/loopback/link-local (incl. the cloud metadata
// IP). A real public https push endpoint passes.
func TestValidatePushEndpoint(t *testing.T) {
	bad := []string{
		"http://push.example.com/x",                 // not https
		"https://127.0.0.1/x",                        // loopback
		"https://localhost/x",                        // loopback name
		"https://169.254.169.254/latest/meta-data/",  // cloud metadata (the classic SSRF target)
		"https://10.0.0.5/x",                         // RFC1918
		"https://192.168.1.1/x",                      // RFC1918
		"https://[::1]/x",                            // ipv6 loopback
		"https:///nohost",                            // no host
		"not a url at all ::::",                      // unparseable
	}
	for _, e := range bad {
		if err := ValidatePushEndpoint(e); err == nil {
			t.Errorf("expected %q to be REJECTED", e)
		}
	}

	// A public https host with a public IP literal passes (avoids a DNS dependency in the test).
	if err := ValidatePushEndpoint("https://93.184.216.34/wp/xyz"); err != nil {
		t.Errorf("expected a public https endpoint to pass, got %v", err)
	}
}

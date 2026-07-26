package api

import "testing"

func TestValidRegistrationRedirectURI(t *testing.T) {
	ok := []string{
		"https://app.example/cb",
		"https://app.example/cb?x=1",
		"http://localhost:9999/cb",        // http loopback (native dev client)
		"http://127.0.0.1:1234/callback",  // http loopback
		"com.example.app:/oauth/callback", // custom scheme (native app)
	}
	for _, u := range ok {
		if !validRegistrationRedirectURI(u) {
			t.Errorf("expected %q to be valid", u)
		}
	}
	bad := []string{
		"",                            // empty
		"https://app.example/cb#frag", // fragment not allowed (RFC 7591/OAuth)
		"http://",                     // http without a host
		"/relative/only",              // not absolute (no scheme)
		"not a url",                   // no scheme
	}
	for _, u := range bad {
		if validRegistrationRedirectURI(u) {
			t.Errorf("expected %q to be invalid", u)
		}
	}
}

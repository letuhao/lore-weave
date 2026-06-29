package api

import (
	"crypto/sha256"
	"encoding/base64"
	"testing"
)

func TestPkceVerifyS256(t *testing.T) {
	verifier := "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
	sum := sha256.Sum256([]byte(verifier))
	challenge := base64.RawURLEncoding.EncodeToString(sum[:])

	if !pkceVerifyS256(verifier, challenge) {
		t.Fatal("valid verifier+challenge should pass")
	}
	if pkceVerifyS256("wrong-verifier", challenge) {
		t.Fatal("a wrong verifier must fail")
	}
	if pkceVerifyS256(verifier, "wrong-challenge") {
		t.Fatal("a wrong challenge must fail")
	}
	if pkceVerifyS256("", challenge) || pkceVerifyS256(verifier, "") {
		t.Fatal("empty inputs must fail")
	}
}

func TestRedirectURIRegistered(t *testing.T) {
	reg := []string{"https://app.example/cb", "http://localhost:9999/cb"}
	if !redirectURIRegistered("https://app.example/cb", reg) {
		t.Fatal("exact match should pass")
	}
	// No prefix/substring escape — anti-open-redirect.
	if redirectURIRegistered("https://app.example/cb/../evil", reg) {
		t.Fatal("non-exact must fail")
	}
	if redirectURIRegistered("https://app.example/cb?x=1", reg) {
		t.Fatal("appended query must fail (exact match only)")
	}
	if redirectURIRegistered("", reg) {
		t.Fatal("empty must fail")
	}
}

func TestSplitScopeParam(t *testing.T) {
	got := splitScopeParam("read  domain:book read * domain:book")
	want := []string{"read", "domain:book"} // deduped, '*' dropped
	if len(got) != len(want) {
		t.Fatalf("got %v", got)
	}
	for i := range want {
		if got[i] != want[i] {
			t.Fatalf("got %v want %v", got, want)
		}
	}
	if len(splitScopeParam("")) != 0 || len(splitScopeParam("*")) != 0 {
		t.Fatal("empty / wildcard-only must yield no scopes")
	}
}

func TestScopesAllKnownAndSubset(t *testing.T) {
	if !scopesAllKnown([]string{"read", "domain:book", "write_confirm"}) {
		t.Fatal("known scopes should pass")
	}
	if scopesAllKnown([]string{"read", "domain:bogus"}) {
		t.Fatal("an unknown scope must fail")
	}
	if !scopesSubset([]string{"read"}, []string{"read", "domain:book"}) {
		t.Fatal("subset should pass")
	}
	if scopesSubset([]string{"write_auto"}, []string{"read"}) {
		t.Fatal("a scope not in the request must fail (no widening)")
	}
}

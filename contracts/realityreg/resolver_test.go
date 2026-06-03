package realityreg

import (
	"strings"
	"testing"
)

func TestDSN_ProdShape(t *testing.T) {
	c := DSNConfig{User: "app", Password: "s3cr3t", Port: 5432, SSLMode: "require"}
	got, err := c.DSN("pg-shard-3.prod", "reality_abc")
	if err != nil {
		t.Fatal(err)
	}
	want := "postgres://app:s3cr3t@pg-shard-3.prod:5432/reality_abc?sslmode=require"
	if got != want {
		t.Errorf("DSN=%q want %q", got, want)
	}
}

func TestDSN_DefaultsPortAndSSL(t *testing.T) {
	c := DSNConfig{User: "app", Password: "p"}
	got, err := c.DSN("pg-shard-0.internal", "r0")
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(got, "@pg-shard-0.internal:5432/") {
		t.Errorf("expected default port 5432 in %q", got)
	}
	if !strings.Contains(got, "sslmode=require") {
		t.Errorf("expected default sslmode=require in %q", got)
	}
}

func TestDSN_ExplicitHostOverrideWins(t *testing.T) {
	c := DSNConfig{
		User: "foundation", Password: "foundation", SSLMode: "disable",
		HostOverride: map[string]string{
			"pg-shard-0.internal": "localhost:55432",
			"*":                   "localhost:9999",
		},
	}
	got, err := c.DSN("pg-shard-0.internal", "reality_a")
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(got, "@localhost:55432/reality_a") {
		t.Errorf("explicit override should win, got %q", got)
	}
}

func TestDSN_WildcardOverrideRemapsAll(t *testing.T) {
	c := DSNConfig{
		User: "foundation", Password: "foundation", SSLMode: "disable",
		HostOverride: map[string]string{"*": "localhost:55432"},
	}
	got, err := c.DSN("pg-shard-7.staging", "reality_z")
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(got, "@localhost:55432/reality_z") {
		t.Errorf("wildcard override should remap, got %q", got)
	}
	if !strings.Contains(got, "sslmode=disable") {
		t.Errorf("expected sslmode=disable, got %q", got)
	}
}

func TestDSN_EmptyDBName(t *testing.T) {
	c := DSNConfig{User: "a", Password: "b"}
	if _, err := c.DSN("pg-shard-0.internal", ""); err == nil {
		t.Error("expected ErrEmptyDBName")
	}
}

func TestDSN_EmptyHostNoWildcard(t *testing.T) {
	c := DSNConfig{User: "a", Password: "b"}
	if _, err := c.DSN("", "r0"); err == nil {
		t.Error("expected ErrEmptyDBHost when db_host empty and no wildcard")
	}
}

func TestDSN_EmptyHostWithWildcard(t *testing.T) {
	c := DSNConfig{User: "a", Password: "b", HostOverride: map[string]string{"*": "localhost:55432"}}
	got, err := c.DSN("", "r0")
	if err != nil {
		t.Fatalf("wildcard should cover empty host: %v", err)
	}
	if !strings.Contains(got, "@localhost:55432/r0") {
		t.Errorf("got %q", got)
	}
}

func TestDSN_PasswordIsURLEscaped(t *testing.T) {
	c := DSNConfig{User: "app", Password: "p@ss:w/rd", SSLMode: "disable"}
	got, err := c.DSN("pg-shard-0.internal", "r0")
	if err != nil {
		t.Fatal(err)
	}
	// Raw special chars must not appear unescaped in the userinfo.
	if strings.Contains(got, "p@ss:w/rd") {
		t.Errorf("password not escaped in %q", got)
	}
}

func TestParseHostOverride(t *testing.T) {
	m, err := ParseHostOverride("pg-shard-0.internal=localhost:55432, *=localhost:55432 ")
	if err != nil {
		t.Fatal(err)
	}
	if m["pg-shard-0.internal"] != "localhost:55432" || m["*"] != "localhost:55432" {
		t.Errorf("parsed map wrong: %v", m)
	}
}

func TestParseHostOverride_Empty(t *testing.T) {
	m, err := ParseHostOverride("   ")
	if err != nil {
		t.Fatal(err)
	}
	if m != nil {
		t.Errorf("empty input should yield nil map, got %v", m)
	}
}

func TestParseHostOverride_Malformed(t *testing.T) {
	for _, bad := range []string{"noeq", "=novalue", "key="} {
		if _, err := ParseHostOverride(bad); err == nil {
			t.Errorf("expected error for %q", bad)
		}
	}
}

func TestDrainableStatuses_ExcludesTerminal(t *testing.T) {
	got := DrainableStatuses()
	excluded := map[string]bool{
		"provisioning": true, "archived": true, "archived_verified": true,
		"soft_deleted": true, "dropped": true,
	}
	for _, s := range got {
		if excluded[s] {
			t.Errorf("drainable set must not include terminal status %q", s)
		}
	}
	// Sanity: the live working states are present.
	want := map[string]bool{"active": false, "frozen": false, "migrating": false, "pending_close": false, "seeding": false}
	for _, s := range got {
		if _, ok := want[s]; ok {
			want[s] = true
		}
	}
	for s, seen := range want {
		if !seen {
			t.Errorf("expected drainable status %q present", s)
		}
	}
}

package serviceacl

import "testing"

func TestAllowedSharingService(t *testing.T) {
	if err := LoadFromEnv(); err != nil {
		t.Skip("matrix file not in cwd:", err)
	}
	if !Allowed("sharing-service", "GET", "/internal/books/00000000-0000-0000-0000-000000000001/projection") {
		t.Fatal("expected sharing-service allowed on book projection")
	}
	if Allowed("unknown-service", "GET", "/internal/books/x") {
		t.Fatal("expected unknown caller denied")
	}
}

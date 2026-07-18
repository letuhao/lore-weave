package api

import (
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
)

// P3 (D-DEK-MULTICONSUMER-TRIPWIRE) — the per-USER DEK is shared across ALL of a user's encrypted
// content, and diary-erase SHREDS it (auth DELETE user_deks). That is correct TODAY only because the
// diary (book-service) is the SOLE consumer: erasing the diary can't collateral-shred anything else.
// The moment a 2nd service (chat, knowledge, …) starts encrypting content under the same user DEK,
// "erase my diary" would silently make THAT service's data unreadable too — a data-loss surprise.
//
// This tripwire reds if any service OUTSIDE the allowlist references the DEK substrate (the `user_deks`
// table or a DEK client). A red is not "you did it wrong" — it is "STOP: a 2nd DEK consumer now exists,
// so the diary-erase shred semantics need a conscious decision (scope the erase, or re-key per content
// type) before this ships." See D-DEK-MULTICONSUMER-TRIPWIRE in the clearance plan.
func TestDEK_IsStillSingleConsumer(t *testing.T) {
	// allowlist: the DEK ISSUER (auth) + the sole content CONSUMER (book/diary). A new entry here must be
	// a deliberate act accompanied by resolving the shared-shred hazard above.
	allowed := map[string]bool{"auth-service": true, "book-service": true}

	// the crypto SDK itself is the substrate, not a consumer — exclude it.
	skipDirs := map[string]bool{"node_modules": true, ".git": true, "testdata": true}

	// signals that a service TOUCHES the per-user DEK substrate.
	signals := []string{"user_deks", "DEKClient", "loreweave_crypto", "wrapped_dek", "unwrapDEK", "UnwrapDEK"}

	_, thisFile, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("cannot locate this test file")
	}
	// services/book-service/internal/api/<thisFile> → walk up to the `services` dir.
	dir := filepath.Dir(thisFile)
	var servicesDir string
	for i := 0; i < 8 && dir != filepath.Dir(dir); i++ {
		if filepath.Base(dir) == "services" {
			servicesDir = dir
			break
		}
		dir = filepath.Dir(dir)
	}
	if servicesDir == "" {
		// cold-review LOW — FAIL, not skip: a green skip is indistinguishable from a pass, which would
		// silently disarm the tripwire. runtime.Caller returns this file's compile-time path (always under
		// services/), so this is unreachable in a normal checkout; failing loudly is strictly safer.
		t.Fatal("could not locate the services/ dir from the test path — the tripwire cannot run")
	}

	entries, err := os.ReadDir(servicesDir)
	if err != nil {
		t.Fatalf("read services dir: %v", err)
	}

	type hit struct{ service, file, signal string }
	var offenders []hit
	for _, e := range entries {
		if !e.IsDir() || allowed[e.Name()] {
			continue
		}
		svc := e.Name()
		root := filepath.Join(servicesDir, svc)
		_ = filepath.WalkDir(root, func(path string, d os.DirEntry, werr error) error {
			if werr != nil {
				return nil // unreadable path — skip, never fail the scan on an IO hiccup
			}
			if d.IsDir() {
				if skipDirs[d.Name()] {
					return filepath.SkipDir
				}
				return nil
			}
			ext := strings.ToLower(filepath.Ext(path))
			// cold-review LOW — include .rs/.tsx so a future Rust or TSX consumer can't slip the scan.
			switch ext {
			case ".go", ".py", ".ts", ".tsx", ".rs", ".sql":
			default:
				return nil
			}
			// don't count a test file that is ITSELF asserting DEK boundaries (mirror of this tripwire).
			if strings.HasSuffix(path, "_test.go") || strings.HasSuffix(path, "_test.py") {
				return nil
			}
			b, rerr := os.ReadFile(path)
			if rerr != nil {
				return nil
			}
			content := string(b)
			for _, sig := range signals {
				if strings.Contains(content, sig) {
					offenders = append(offenders, hit{svc, path, sig})
					break
				}
			}
			return nil
		})
	}

	if len(offenders) > 0 {
		var msgs []string
		for _, o := range offenders {
			msgs = append(msgs, o.service+" ("+o.signal+") in "+o.file)
		}
		t.Fatalf("D-DEK-MULTICONSUMER-TRIPWIRE: a 2nd per-user-DEK consumer appeared outside the allowlist "+
			"{auth-service, book-service}:\n  %s\n\nSTOP: diary-erase shreds the shared user DEK. Before "+
			"shipping a 2nd consumer, resolve the collateral-shred hazard (scope the erase to assistant "+
			"data, or re-key content per type), then add the service to the allowlist in this test.",
			strings.Join(msgs, "\n  "))
	}
}

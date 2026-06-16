//go:build !prod

package logging

// IsProdBuild is the compile-time constant flipped by the `prod` build tag.
//
// Default (this file, !prod) — IsProdBuild = false. Debug emits are allowed;
// FieldKindSensitive is visible at LevelDebug; FieldKindPII is hashed but
// not masked (Redactor.Redact returns hash digest, not "***@***.***").
//
// PROD build (compile_guard_prod.go, +build prod) — IsProdBuild = true.
// Debug emits are DROPPED at the Logger.Emit boundary; FieldKindSensitive
// is dropped at all levels; FieldKindPII is masked via Redactor.Redact and
// the Logger refuses to start with a NoopRedactor (NewLogger returns
// ErrNilRedactor for a noop).
//
// Per S08 §12X.8 this MUST be a compile-time const (not a runtime env var)
// so accidental flips at runtime cannot happen. Verify by:
//
//	$ go build -tags=prod ./...   # ensure prod build compiles
//	$ go test ./...               # default build keeps debug visible
const IsProdBuild = false

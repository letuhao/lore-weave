package logging

import (
	"errors"
	"fmt"
)

// FieldKind is the typed-tag attached to every Field. The kind decides
// HOW the value flows through the Logger pipeline:
//
//   - FieldKindNormal     — no redaction, no drop. Standard business field.
//   - FieldKindSensitive  — visible only at LevelDebug in DEV build; dropped
//     at LevelInfo and above; dropped entirely in PROD build (compile guard).
//   - FieldKindPII        — auto-masked via the Redactor interface in PROD
//     build; hashed (Redactor may choose SHA-256 prefix) in DEV build.
//
// Per S08 §12X.8 the helper constructors (PII / Sensitive / Normal in
// helpers.go) are the ONLY supported way to construct a Field — direct
// struct-literal use is discouraged because it bypasses the FieldKind
// validation in NewField.
type FieldKind int

const (
	// FieldKindNormal — standard fields (counts, ids, durations, etc.).
	FieldKindNormal FieldKind = iota
	// FieldKindSensitive — emails, internal user IDs, IP addresses, etc.
	// Debug-build dev visibility; PROD drops entirely.
	FieldKindSensitive
	// FieldKindPII — personally-identifying data (names, addresses, free-
	// text user input). MUST be redacted via Redactor interface in PROD.
	FieldKindPII
)

// String returns the stable wire-form ("normal", "sensitive", "pii").
func (k FieldKind) String() string {
	switch k {
	case FieldKindNormal:
		return "normal"
	case FieldKindSensitive:
		return "sensitive"
	case FieldKindPII:
		return "pii"
	}
	return fmt.Sprintf("invalid(%d)", int(k))
}

// IsValid returns true for the 3 enumerated kinds.
func (k FieldKind) IsValid() bool {
	return k >= FieldKindNormal && k <= FieldKindPII
}

// Field is a single structured log field.
//
// Stable wire-form: {"k": "<name>", "v": <value>, "kind": "<FieldKind>"}.
// The kind is serialized so downstream log-ingest scrubbers can apply
// belt-and-suspenders defense (cycle 33+ L7.F vector scrubber pipeline).
type Field struct {
	// Name is the field key. Must be non-empty and match the cycle-19
	// observability convention (snake_case, no dots) when used as a metric
	// label. Logger does NOT enforce regex at emit time (perf); the
	// sensitive-field-lint script (L7.E.10) does.
	Name string

	// Value is the raw payload — interface{} to keep the helper API
	// terse. JSON serialization is the Logger's responsibility.
	Value any

	// Kind controls redaction policy. See FieldKind doc above.
	Kind FieldKind
}

// ErrInvalidField is returned by NewField for empty name or invalid kind.
var ErrInvalidField = errors.New("logging: invalid Field (name required + kind must be enumerated)")

// NewField is the constructor that enforces the FieldKind invariant.
// Returns ErrInvalidField on empty name or unknown kind.
//
// Tests rely on NewField (not helper functions) when they need to assert
// a specific FieldKind on the resulting struct.
func NewField(name string, value any, kind FieldKind) (Field, error) {
	if name == "" {
		return Field{}, fmt.Errorf("%w: name=\"\"", ErrInvalidField)
	}
	if !kind.IsValid() {
		return Field{}, fmt.Errorf("%w: kind=%d", ErrInvalidField, int(kind))
	}
	return Field{Name: name, Value: value, Kind: kind}, nil
}

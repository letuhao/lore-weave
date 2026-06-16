package logging

// PII constructs a FieldKindPII field. PROD build redacts via Redactor;
// DEV build hashes (Redactor.Redact returns hash digest in dev — but
// noopRedactor returns the raw value, so DEV+NoopRedactor is "what you
// see is what you'd see in plaintext but the kind tag is set to pii").
//
// Per S08 §12X.8 — typed helper, not a regex. Cycle 22 PII SDK supplies
// the production Redactor.
func PII(name string, value any) Field {
	return Field{Name: name, Value: value, Kind: FieldKindPII}
}

// Sensitive constructs a FieldKindSensitive field. PROD build drops at
// all levels (debug, info, warn, error). DEV build shows at LevelDebug
// only.
//
// Use for: emails (when not technically PII), internal user IDs, IP
// addresses, raw URLs that may contain query-string tokens.
func Sensitive(name string, value any) Field {
	return Field{Name: name, Value: value, Kind: FieldKindSensitive}
}

// Normal constructs a FieldKindNormal field. No redaction, no drop.
//
// Use for: counts, durations, status codes, error class enums (not the
// raw error string — that should be Sensitive if it may contain PII), DB
// row IDs (UUIDs are non-PII by themselves).
func Normal(name string, value any) Field {
	return Field{Name: name, Value: value, Kind: FieldKindNormal}
}

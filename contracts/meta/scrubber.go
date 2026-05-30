package meta

import (
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"reflect"
	"regexp"
	"strings"
	"time"
)

// Scrubber rewrites free-text fields to remove PII before they land in any
// audit table. S08 §12X.5 is the canonical specification.
//
// The interface is **intentionally shaped so callers cannot trivially keep
// the raw text alive**:
//
//   - Scrub() returns ONLY the post-scrub fields (hash + scrubbed text +
//     version + timestamp). The original string is dropped on the floor.
//   - There is no Unscrub / Reverse / GetRaw method, and there never will be —
//     audit consumers correlate via hash, NOT raw text.
//   - The hash is SHA-256 so two error reports with the same underlying text
//     produce the same forensic key without anyone storing the original.
//
// Cycle 4 (this file) ships the **interface + a passthrough stub**. The
// production scrubber (regex rules, allowlist tokens, KEK-aware redaction)
// ships with the S08 §12X.5 implementation cycle — out of L1.A-3 scope.
// admin-cli (cycle 36) will inject a real Scrubber; until then the stub
// is enough for libraries that need to *carry* a Scrubber dependency but
// don't yet *invoke* it on hot paths.
//
// IMPORTANT: PassthroughScrubber is **test-only**. It is named explicitly so
// CI lint (cycle 7 L1.K) can refuse it in non-test files, mirroring the
// DeterministicTestKMS pattern from cycle 3.
type Scrubber interface {
	// Scrub takes a free-text input and returns the four post-scrub fields
	// that admin_action_audit + meta_read_audit (parameters) etc. persist.
	//
	// The raw text MUST be discarded by the caller after this returns; the
	// interface gives nothing back that would let the raw text be reconstructed.
	Scrub(raw string) ScrubbedField
}

// ScrubbedField is the post-scrub envelope persisted into audit tables.
// Fields map 1:1 to admin_action_audit.error_detail_{raw_hash,scrubbed},
// scrub_version, and scrubbed_at columns.
type ScrubbedField struct {
	// RawHash is the SHA-256 of the original input (32 bytes).
	// Persisted as BYTEA in audit tables; lets forensics correlate two
	// occurrences of the same error text without storing either copy.
	RawHash []byte

	// Scrubbed is the rewritten text with PII placeholders.
	// Safe to log and search.
	Scrubbed string

	// Version identifies the scrubber ruleset that produced Scrubbed.
	// Used by retroactive re-scrub jobs and policy-audit dashboards.
	Version string

	// ScrubbedAt is when Scrub() ran. Stored as TIMESTAMPTZ in audit tables.
	ScrubbedAt time.Time
}

// IsEmpty reports whether the field carries no scrub data (caller should
// leave the four DB columns NULL — see the
// `admin_action_audit_scrubber_quad_consistent` CHECK constraint).
func (s ScrubbedField) IsEmpty() bool {
	return len(s.RawHash) == 0 && s.Scrubbed == "" && s.Version == "" && s.ScrubbedAt.IsZero()
}

// PassthroughScrubber is a TEST-ONLY Scrubber that hashes the raw text and
// returns it verbatim as the "scrubbed" form. Suitable ONLY for unit tests
// that need to satisfy the Scrubber dependency without exercising redaction.
//
// CI lint MUST reject this type appearing in non-test files (cycle 7 L1.K).
type PassthroughScrubber struct {
	// Version identifies the ruleset; tests typically set "passthrough-v0".
	Version string

	// Clock is the timestamp source; nil = time.Now.
	Clock Clock
}

// Scrub implements Scrubber. The "scrubbed" output is the raw text itself
// (passthrough) — explicitly NOT a redaction. Tests that assert behavior on
// scrubbed text should use a custom Scrubber, not this stub.
func (p PassthroughScrubber) Scrub(raw string) ScrubbedField {
	h := sha256.Sum256([]byte(raw))
	var ts time.Time
	if p.Clock != nil {
		ts = time.Unix(0, p.Clock.NowUnixNano())
	} else {
		ts = time.Now().UTC()
	}
	version := p.Version
	if strings.TrimSpace(version) == "" {
		version = "passthrough-v0"
	}
	return ScrubbedField{
		RawHash:    h[:],
		Scrubbed:   raw,
		Version:    version,
		ScrubbedAt: ts,
	}
}

// ─────────────────────────────────────────────────────────────────────────────
// RegexScrubber — production Scrubber (S08 §12X.5, PRR-01)
// ─────────────────────────────────────────────────────────────────────────────

// regexScrubberVersion identifies the ruleset that produced a Scrubbed value.
// Bump when regexScrubRules change so retroactive re-scrub jobs can target old rows.
const regexScrubberVersion = "regex-v1"

// scrubRule pairs a compiled pattern with the placeholder that replaces it.
type scrubRule struct {
	re          *regexp.Regexp
	placeholder string
}

// regexScrubRules are applied IN ORDER (most specific first). The scrubber is
// security-first: over-redaction is acceptable, under-redaction is the risk.
// Covers the seven L4.Q.6 pattern classes: email, SSN, IPv6, IPv4,
// credit-card, API-key/token, phone.
var regexScrubRules = []scrubRule{
	{regexp.MustCompile(`[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}`), "[EMAIL]"},
	{regexp.MustCompile(`\b\d{3}-\d{2}-\d{4}\b`), "[SSN]"},
	{regexp.MustCompile(`\b(?:[0-9A-Fa-f]{1,4}:){3,7}[0-9A-Fa-f]{1,4}\b`), "[IPV6]"},
	{regexp.MustCompile(`\b(?:\d{1,3}\.){3}\d{1,3}\b`), "[IPV4]"},
	{regexp.MustCompile(`\b(?:\d[ -]?){13,19}\b`), "[CC]"},
	{regexp.MustCompile(`(?i)\b(?:sk|pk|api|key|token|secret|bearer)[_\-][A-Za-z0-9_\-]{12,}\b`), "[APIKEY]"},
	{regexp.MustCompile(`\b(?:\+?\d{1,3}[ .\-])?\(?\d{2,4}\)?[ .\-]\d{2,4}[ .\-]\d{2,4}\b`), "[PHONE]"},
}

// RegexScrubber is the production Scrubber. It rewrites the seven PII pattern
// classes to placeholders before free text lands in any audit table, and
// records SHA-256(original) for forensic correlation. There is deliberately no
// way to recover the raw text. This is the non-test Scrubber the write path
// and admin-cli inject (PRR-01).
type RegexScrubber struct {
	// Clock is the timestamp source; nil = time.Now().UTC().
	Clock Clock
}

// NewRegexScrubber returns a production RegexScrubber. clock=nil → time.Now.
func NewRegexScrubber(clock Clock) RegexScrubber { return RegexScrubber{Clock: clock} }

// ScrubText implements TextScrubber: the redaction WITHOUT the SHA-256/timestamp
// of Scrub(). Used by ScrubValue for structured leaves (which discard the hash).
func (r RegexScrubber) ScrubText(s string) string { return scrubString(s) }

// Scrub implements Scrubber: PII patterns → placeholders; RawHash = SHA-256(raw).
func (r RegexScrubber) Scrub(raw string) ScrubbedField {
	h := sha256.Sum256([]byte(raw))
	scrubbed := scrubString(raw)
	var ts time.Time
	if r.Clock != nil {
		ts = time.Unix(0, r.Clock.NowUnixNano())
	} else {
		ts = time.Now().UTC()
	}
	return ScrubbedField{
		RawHash:    h[:],
		Scrubbed:   scrubbed,
		Version:    regexScrubberVersion,
		ScrubbedAt: ts,
	}
}

// maxScrubDepth caps recursion into nested audit values. Intent maps are
// caller-constructed (not schema-bounded), so a pathologically deep or
// self-referential structure could otherwise stack-overflow. Beyond the cap we
// drop the sub-tree to a placeholder rather than recurse further.
const maxScrubDepth = 64

// ScrubValue returns a DEEP-COPIED, PII-redacted view of an arbitrary audit
// value, redacting every string leaf via sc (the injected Scrubber). It NEVER
// mutates its input: meta_write_audit's before/after maps are shared by
// reference with the persisted data write AND the outbox event payload, so
// in-place mutation would ship redaction placeholders to every downstream
// projection.
//
// Security-first / fail-closed (under-redaction is the risk): EVERY string leaf
// in ANY container is redacted, not just the three well-known JSON shapes. A
// reflection fallback covers typed containers ([]byte, map[string]string,
// []string, named string types, json.RawMessage); only non-string scalars
// (numbers/bools/nil) and opaque structs pass through. The result is a
// normalized any-tree (map[string]any / []any) suitable for JSON marshaling.
//
// Struct values are handled too: the reflect fallback round-trips them through
// JSON (exported fields only, honoring json tags) and scrubs the result, so a
// domain struct placed as an audit value does not leak string fields.
func ScrubValue(v any, sc Scrubber) any { return scrubValueDepth(v, leafScrubber(sc), 0) }

// TextScrubber is an OPTIONAL fast-path: a Scrubber that can redact a string
// without the per-call SHA-256/timestamp of Scrub(). ScrubValue prefers it so
// scrubbing a wide structured map does not compute N throwaway hashes.
type TextScrubber interface {
	ScrubText(s string) string
}

// leafScrubber resolves the per-string transform ONCE: the ScrubText fast-path
// when available (RegexScrubber), else Scrub().Scrubbed.
func leafScrubber(sc Scrubber) func(string) string {
	if ts, ok := sc.(TextScrubber); ok {
		return ts.ScrubText
	}
	return func(s string) string { return sc.Scrub(s).Scrubbed }
}

func scrubValueDepth(v any, scrub func(string) string, depth int) any {
	if v == nil {
		return nil
	}
	if depth > maxScrubDepth {
		return "[TRUNCATED]"
	}
	switch t := v.(type) {
	case string:
		return scrub(t)
	case []byte:
		return []byte(scrub(string(t)))
	case map[string]any:
		out := make(map[string]any, len(t))
		for k, val := range t {
			out[scrub(k)] = scrubValueDepth(val, scrub, depth+1) // scrub keys too
		}
		return out
	case []any:
		out := make([]any, len(t))
		for i, val := range t {
			out[i] = scrubValueDepth(val, scrub, depth+1)
		}
		return out
	}
	return scrubReflect(reflect.ValueOf(v), scrub, depth)
}

// scrubReflect is the fail-closed fallback for typed containers + named string
// kinds the type switch above does not enumerate. Redacts any reflect.String
// leaf (incl. map keys) and any byte slice; walks maps/slices/arrays; derefs
// ptr/interface.
func scrubReflect(rv reflect.Value, scrub func(string) string, depth int) any {
	if depth > maxScrubDepth {
		return "[TRUNCATED]"
	}
	switch rv.Kind() {
	case reflect.String:
		return scrub(rv.String())
	case reflect.Pointer, reflect.Interface:
		if rv.IsNil() {
			return nil
		}
		return scrubReflect(rv.Elem(), scrub, depth+1)
	case reflect.Slice, reflect.Array:
		if rv.Kind() == reflect.Slice && rv.Type().Elem().Kind() == reflect.Uint8 {
			return []byte(scrub(string(rv.Bytes())))
		}
		out := make([]any, rv.Len())
		for i := 0; i < rv.Len(); i++ {
			out[i] = scrubReflect(rv.Index(i), scrub, depth+1)
		}
		return out
	case reflect.Map:
		out := make(map[string]any, rv.Len())
		for _, k := range rv.MapKeys() {
			out[scrub(fmt.Sprint(k.Interface()))] = scrubReflect(rv.MapIndex(k), scrub, depth+1)
		}
		return out
	case reflect.Struct:
		// Scrub a struct VALUE by round-tripping through JSON: json.Marshal sees
		// ONLY exported fields (no unexported-field reflect panic) and honors
		// json tags, so the scrubbed map matches the on-the-wire shape. Then
		// scrub the resulting any-tree. Fail-closed if it can't be marshaled.
		if !rv.CanInterface() {
			return "[UNSCRUBBABLE]"
		}
		b, err := json.Marshal(rv.Interface())
		if err != nil {
			return "[UNSCRUBBABLE]"
		}
		var m any
		if err := json.Unmarshal(b, &m); err != nil {
			return "[UNSCRUBBABLE]"
		}
		return scrubValueDepth(m, scrub, depth+1)
	default:
		// Numbers, bools, and other scalars carry no scrubbable free text.
		return rv.Interface()
	}
}

// ScrubValuesMap is the map-typed convenience wrapper for ScrubValue. Returns a
// fresh map (nil input → nil) — never the same backing map as the input.
func ScrubValuesMap(m map[string]any, sc Scrubber) map[string]any {
	if m == nil {
		return nil
	}
	scrub := leafScrubber(sc)
	out := make(map[string]any, len(m))
	for k, v := range m {
		out[scrub(k)] = scrubValueDepth(v, scrub, 1)
	}
	return out
}

// scrubString applies the 7 regexScrubRules in order. Used by RegexScrubber.
func scrubString(s string) string {
	for _, rule := range regexScrubRules {
		s = rule.re.ReplaceAllString(s, rule.placeholder)
	}
	return s
}

// MustValidateScrubbedField fail-fasts if the four fields aren't
// internally consistent (matches the DB CHECK constraint
// admin_action_audit_scrubber_quad_consistent). Callers that hand-construct
// a ScrubbedField (rare — almost everyone gets one from Scrub) can call
// this to catch local bugs before DB rejection.
func MustValidateScrubbedField(s ScrubbedField) error {
	if s.IsEmpty() {
		return nil
	}
	if len(s.RawHash) != 32 {
		return fmt.Errorf("meta: scrubbed field hash must be SHA-256 (32 bytes), got %d", len(s.RawHash))
	}
	if s.Scrubbed == "" || s.Version == "" || s.ScrubbedAt.IsZero() {
		return fmt.Errorf("meta: scrubbed field partial population (all-or-nothing); got %+v", s)
	}
	return nil
}

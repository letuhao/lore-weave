package events

import "fmt"

// ErrInvalidEnvelopeText is a typed string-error for structural envelope
// validation failures. Kept distinct from ErrUnknownEventSchema and
// ErrSchemaViolation (L2.I) to make caller error-handling unambiguous.
type ErrInvalidEnvelopeText string

func (e ErrInvalidEnvelopeText) Error() string {
	return fmt.Sprintf("invalid envelope: %s", string(e))
}

// ErrInvalidEnvelope constructs the structural-validation error.
func ErrInvalidEnvelope(msg string) error {
	return ErrInvalidEnvelopeText(msg)
}

// ErrUnknownEventSchemaText is returned by registry lookups when no struct
// is registered for (event_type, event_version).
type ErrUnknownEventSchemaText struct {
	EventType    string
	EventVersion uint32
}

func (e ErrUnknownEventSchemaText) Error() string {
	return fmt.Sprintf("unknown event schema: type=%s version=%d", e.EventType, e.EventVersion)
}

// ErrUnknownEventSchema constructs the L2.I unknown-schema error. R03 §12C.4
// requires this is raised at write time, not at projection rebuild.
func ErrUnknownEventSchema(eventType string, eventVersion uint32) error {
	return ErrUnknownEventSchemaText{EventType: eventType, EventVersion: eventVersion}
}

// ErrSchemaViolationText is returned when the payload does not match the
// registered struct's required fields / types.
type ErrSchemaViolationText struct {
	EventType    string
	EventVersion uint32
	Detail       string
}

func (e ErrSchemaViolationText) Error() string {
	return fmt.Sprintf("schema violation: type=%s version=%d: %s",
		e.EventType, e.EventVersion, e.Detail)
}

// ErrSchemaViolation constructs the L2.I schema-violation error.
func ErrSchemaViolation(eventType string, eventVersion uint32, detail string) error {
	return ErrSchemaViolationText{EventType: eventType, EventVersion: eventVersion, Detail: detail}
}

// ErrRegistryParseText is returned by LoadRegistry when `_registry.yaml` is
// malformed (duplicate name, missing version, etc.). Fail-fast at service
// startup per L2.F acceptance criteria.
type ErrRegistryParseText struct {
	Detail string
}

func (e ErrRegistryParseText) Error() string {
	return fmt.Sprintf("registry parse error: %s", e.Detail)
}

// ErrRegistryParse constructs the registry-parse error.
func ErrRegistryParse(detail string) error {
	return ErrRegistryParseText{Detail: detail}
}

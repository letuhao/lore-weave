package meta

import "errors"

// Canonical errors surfaced by MetaWrite / AttemptStateTransition / read paths.
// Services match these via errors.Is to keep retry/fallback logic uniform across
// the monorepo (per L1.B §"errors.go" — entry L1.B.17).
var (
	// ErrConcurrentStateTransition is returned when a CAS UPDATE matches 0 rows
	// — another writer modified the resource between read and write.
	// Caller MUST refresh and retry (no auto-retry inside MetaWrite to keep
	// the audit row honest about the lost race).
	ErrConcurrentStateTransition = errors.New("meta: concurrent state transition")

	// ErrInvalidTransition is returned by AttemptStateTransition when the
	// (FromState, ToState) pair is not in the resource's transitions.yaml
	// graph. NEVER retry; caller has a logic bug.
	ErrInvalidTransition = errors.New("meta: invalid state transition")

	// ErrMutualExclusion is returned when a resource is in a state that
	// forbids the requested transition for mutual-exclusion reasons
	// (e.g., attempting `pending_close` while `status=migrating`).
	ErrMutualExclusion = errors.New("meta: mutual-exclusion conflict")

	// ErrPreconditionFailed signals a domain precondition (e.g., archive
	// verification missing) was not met for the transition.
	ErrPreconditionFailed = errors.New("meta: precondition failed")

	// ErrDegradedMode is surfaced when the meta layer is in degraded mode
	// (primary + all sync replicas unreachable) and the requested op is
	// not safe to buffer.
	ErrDegradedMode = errors.New("meta: degraded mode — request rejected")

	// ErrBadIntent is returned when a MetaWriteIntent fails validation
	// (empty table, missing PK, op-not-in-set, etc.). NEVER retry.
	ErrBadIntent = errors.New("meta: bad MetaWriteIntent")

	// ErrTableNotAllowlisted is returned when the intent targets a table
	// the library has not been told about. Defense-in-depth so a service
	// can't accidentally write to a table its design didn't anticipate.
	ErrTableNotAllowlisted = errors.New("meta: table not in allowlist")

	// ErrUnknownResource is returned by AttemptStateTransition when
	// ResourceType has no entry in transitions.yaml.
	ErrUnknownResource = errors.New("meta: unknown resource type for transition")

	// ErrTransitionGraphInvalid is returned by the transitions_validator on
	// load when transitions.yaml fails sanity checks (unreachable states,
	// undefined target states, etc.).
	ErrTransitionGraphInvalid = errors.New("meta: transitions.yaml graph invalid")
)

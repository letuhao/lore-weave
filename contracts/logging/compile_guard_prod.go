//go:build prod

package logging

// IsProdBuild — see compile_guard.go for the contract.
//
// This file is compiled ONLY under the `prod` build tag. It flips
// IsProdBuild to true. The Logger.Emit boundary then:
//
//   - Drops all LevelDebug emits unconditionally
//   - Drops all FieldKindSensitive fields at all levels
//   - Masks FieldKindPII values via Redactor.Redact
//   - Refuses NewLogger(...) with a NoopRedactor (returns ErrNilRedactor)
const IsProdBuild = true

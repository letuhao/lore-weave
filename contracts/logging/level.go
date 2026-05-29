package logging

import (
	"errors"
	"fmt"
)

// Level is the canonical structured-logging level.
//
// Stable wire-form is the lowercase string ("debug", "info", "warn", "error").
// The integer ordering (Debug < Info < Warn < Error) is load-bearing — used
// by Logger to gate emission below the configured floor.
type Level int

const (
	// LevelDebug — verbose diagnostics. DROPPED at compile time in prod
	// build (`IsProdBuild == true`) per S08 §12X.8.
	LevelDebug Level = iota
	// LevelInfo — normal operational events; emitted in all builds.
	LevelInfo
	// LevelWarn — recoverable degradations; emitted in all builds.
	LevelWarn
	// LevelError — service-level failures; emitted in all builds and SHOULD
	// trigger an alert via cycle 22 contracts/alerts.
	LevelError
)

// String returns the stable lowercase wire-form.
func (l Level) String() string {
	switch l {
	case LevelDebug:
		return "debug"
	case LevelInfo:
		return "info"
	case LevelWarn:
		return "warn"
	case LevelError:
		return "error"
	}
	return fmt.Sprintf("invalid(%d)", int(l))
}

// IsValid returns true for the 4 enumerated levels.
func (l Level) IsValid() bool {
	return l >= LevelDebug && l <= LevelError
}

// ErrInvalidLevel is returned by ParseLevel for unknown inputs.
var ErrInvalidLevel = errors.New("logging: invalid level (must be debug|info|warn|error)")

// ParseLevel parses the stable wire-form back to Level.
// Case-sensitive — wire-form is always lowercase.
func ParseLevel(s string) (Level, error) {
	switch s {
	case "debug":
		return LevelDebug, nil
	case "info":
		return LevelInfo, nil
	case "warn":
		return LevelWarn, nil
	case "error":
		return LevelError, nil
	}
	return LevelDebug, fmt.Errorf("%w: got %q", ErrInvalidLevel, s)
}

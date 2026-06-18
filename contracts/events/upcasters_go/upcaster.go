package upcastersgo

import "fmt"

// Upcaster is the one-step transformation from version_from →
// version_from + 1. Implementors are typically plain functions wrapped via
// FnUpcaster.
type Upcaster interface {
	VersionFrom() uint32
	Apply(payload map[string]any) (map[string]any, error)
}

// FnUpcaster wraps a plain function as an Upcaster.
type FnUpcaster struct {
	From uint32
	Fn   func(map[string]any) (map[string]any, error)
}

func (f *FnUpcaster) VersionFrom() uint32 { return f.From }
func (f *FnUpcaster) Apply(p map[string]any) (map[string]any, error) {
	return f.Fn(p)
}

// Registry maps (event_type, from_version) → Upcaster.
type Registry struct {
	byKey map[key]Upcaster
}

type key struct {
	eventType string
	from      uint32
}

func NewRegistry() *Registry {
	return &Registry{byKey: map[key]Upcaster{}}
}

// Register inserts a one-step upcaster. Panics on duplicate (drift caught at init).
func (r *Registry) Register(eventType string, u Upcaster) {
	k := key{eventType, u.VersionFrom()}
	if _, dup := r.byKey[k]; dup {
		panic(fmt.Sprintf("upcastersgo: duplicate upcaster for %s v%d", eventType, u.VersionFrom()))
	}
	r.byKey[k] = u
}

// Errors returned by Upcast.
type errBackwardUpcast struct{ EventType string; From, To uint32 }

func (e errBackwardUpcast) Error() string {
	return fmt.Sprintf("backward upcast forbidden: type=%s from=%d to=%d (must be from < to)",
		e.EventType, e.From, e.To)
}

type errMissingUpcaster struct{ EventType string; From, To uint32 }

func (e errMissingUpcaster) Error() string {
	return fmt.Sprintf("missing upcaster: type=%s %d -> %d", e.EventType, e.From, e.To)
}

type errUpcasterFailed struct{ EventType string; From, To uint32; Detail string }

func (e errUpcasterFailed) Error() string {
	return fmt.Sprintf("upcaster failure: type=%s %d->%d: %s", e.EventType, e.From, e.To, e.Detail)
}

// IsBackwardUpcast / IsMissingUpcaster / IsUpcasterFailed are typed
// type-predicates so callers can match on category without a type assertion
// helper in every site.
func IsBackwardUpcast(err error) bool { _, ok := err.(errBackwardUpcast); return ok }
func IsMissingUpcaster(err error) bool { _, ok := err.(errMissingUpcaster); return ok }
func IsUpcasterFailed(err error) bool  { _, ok := err.(errUpcasterFailed); return ok }

// Upcast runs the chain from `from` to `to` on the supplied payload.
//
//   - from > to → errBackwardUpcast
//   - from == to → payload returned unchanged (no-op)
//   - any gap in registered hops → errMissingUpcaster
//   - upcaster returns error → errUpcasterFailed (wrapping detail)
//
// Implementation walks one hop at a time so chain composition is the same
// shape as the Rust side.
func (r *Registry) Upcast(eventType string, payload map[string]any, from, to uint32) (map[string]any, error) {
	if from > to {
		return nil, errBackwardUpcast{EventType: eventType, From: from, To: to}
	}
	if from == to {
		return payload, nil
	}
	cur := from
	val := payload
	for cur < to {
		u, ok := r.byKey[key{eventType, cur}]
		if !ok {
			return nil, errMissingUpcaster{EventType: eventType, From: cur, To: cur + 1}
		}
		next, err := u.Apply(val)
		if err != nil {
			return nil, errUpcasterFailed{EventType: eventType, From: cur, To: cur + 1, Detail: err.Error()}
		}
		val = next
		cur++
	}
	return val, nil
}

package loreweave_mcp

import (
	"context"
	"strings"

	"github.com/google/uuid"
)

// BookScope is the resolved book for a call plus HOW it was resolved (spec
// 2026-07-22-studio-context-binding §2.2). A tool uses CrossBook to decide the soft
// confirm: a READ adds an advisory note, a WRITE pre-confirms (it must never mutate a
// different book than the studio is bound to before the user reacts). Source is exposed
// so a human/trace can always see which book a call actually hit (SET discipline).
type BookScope struct {
	BookID    uuid.UUID
	Source    string // "arg" | "envelope"
	CrossBook bool   // resolved from an explicit arg that DIFFERS from the ambient (bound) book
}

// ResolveBookScope implements the fail-closed resolution cascade:
//
//	explicit valid-UUID arg   → {arg,     source:"arg",      CrossBook: arg≠ambient}
//	malformed arg + ambient   → {ambient, source:"envelope"}  (SILENT repair of a mistranscription)
//	blank arg + ambient       → {ambient, source:"envelope"}  (the studio binding — model omitted it)
//	blank/malformed, no amb.   → ok=false                      (caller emits its required/invalid error)
//
// The ambient book (X-Book-Id) is NEVER authorization — the caller still grant-checks
// BookID exactly as it would an explicit arg (SEC-1 spirit; a spoofed/stale/foreign
// ambient grants nothing). A malformed arg is a mistranscription, never a deliberate
// cross-book intent, so it repairs silently and does NOT set CrossBook (only a valid,
// DIFFERENT UUID does — the intent path a write must pre-confirm).
func ResolveBookScope(ctx context.Context, argBookID string) (BookScope, bool) {
	ambient, hasAmbient := BookIDFromCtx(ctx)
	arg := strings.TrimSpace(argBookID)
	if arg != "" {
		if id, err := uuid.Parse(arg); err == nil {
			return BookScope{BookID: id, Source: "arg", CrossBook: hasAmbient && id != ambient}, true
		}
		if hasAmbient { // malformed arg → repair from the ambient book
			return BookScope{BookID: ambient, Source: "envelope"}, true
		}
		return BookScope{}, false
	}
	if hasAmbient { // omitted arg on a bound surface → the studio's book
		return BookScope{BookID: ambient, Source: "envelope"}, true
	}
	return BookScope{}, false
}

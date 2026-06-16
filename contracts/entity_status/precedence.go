package entity_status

// precedence.go — compound-state precedence helper.
//
// If a single entity matches multiple states (e.g., the row is severed AND
// the reality is dropped), we need a deterministic winner. The S10 §12Z
// precedence order is:
//
//	dropped > user_erased > severed > archived > active
//
// Higher number = wins.

// precedenceRank returns a comparable rank where higher = stronger.
// Internal — callers use [Higher] for clarity.
func precedenceRank(s GoneState) int {
	switch s {
	case StateDropped:
		return 5
	case StateUserErased:
		return 4
	case StateSevered:
		return 3
	case StateArchived:
		return 2
	case StateActive:
		return 1
	default:
		return 0
	}
}

// Higher returns whichever of (a, b) has stronger precedence per S10 §12Z.
// Ties prefer 'a' (deterministic for tests).
func Higher(a, b GoneState) GoneState {
	if precedenceRank(a) >= precedenceRank(b) {
		return a
	}
	return b
}

// Reduce collapses N candidate states into the strongest one. Empty input
// returns StateActive (safe default — "if no signal says gone, then active").
func Reduce(states ...GoneState) GoneState {
	winner := StateActive
	for _, s := range states {
		winner = Higher(winner, s)
	}
	return winner
}

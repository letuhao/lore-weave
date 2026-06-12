package prompt

import "context"

// IntentClassifier is the trait that maps an untrusted user utterance
// to one of the 7 Intent values. Cycle 31 L6.L.1 ships the trait + a
// no-op default per Q-L6L-1 (LOCKED).
//
// **Q-L6L-1 (LOCKED):** foundation V1 default returns
// IntentSessionTurn for every input. The real classifier — pattern
// scan + small-model heuristic + admin-trigger detection — lands in
// the LLM-safety sub-program. The default is INTENTIONALLY permissive
// because the alternative (failing closed on every turn) breaks the
// happy path; the LLM-safety sub-program owns the policy decision.
//
// **Why an interface at all if it's no-op V1:** the foundation owns
// the signature freeze. Cycles that consume prompt assembly can take
// the dependency NOW and swap impls in their service wiring once the
// LLM-safety sub-program lands. Without the trait, every service
// would hand-roll its own classifier signature, then ALL of them
// would have to change when the policy ships.
type IntentClassifier interface {
	// Classify returns the Intent for an utterance. Returns an error
	// only on adversarial input the classifier CANNOT safely classify
	// (V1 never returns an error — that's the LLM-safety sub-program's
	// future fail-closed behavior).
	Classify(ctx context.Context, utterance string) (Intent, error)
}

// NoopIntentClassifier is the V1 default per Q-L6L-1. Returns
// IntentSessionTurn unconditionally. The LLM-safety sub-program will
// swap this for a real classifier.
type NoopIntentClassifier struct{}

// Classify — see IntentClassifier. V1: always IntentSessionTurn.
func (NoopIntentClassifier) Classify(_ context.Context, _ string) (Intent, error) {
	return IntentSessionTurn, nil
}

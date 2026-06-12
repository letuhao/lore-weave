package prompt

import "context"

// InjectionDetection is the result of one defense layer. Cycle 31
// L6.L.3 ships the shape; concrete detection lives in LLM-safety.
type InjectionDetection struct {
	// Detected — true iff this layer flagged the input as a potential
	// injection. V1 stubs always return false (Q-L6L-1).
	Detected bool

	// Layer — which defense layer fired (e.g., "pattern_scan",
	// "canary_post_scan", "instruction_hierarchy"). Foundation does
	// not enumerate; LLM-safety owns the layer namespace.
	Layer string

	// Reason — opaque short string for audit logs. Empty when
	// Detected=false.
	Reason string

	// Severity — opaque tier marker (e.g., "low", "med", "high").
	// LLM-safety sub-program defines the scale.
	Severity string
}

// InjectionDefense is the 5-layer defense surface from S09 §12Y.6.
// Cycle 31 L6.L.3 ships the trait + an identity (no-op) default per
// Q-L6L-1 (LOCKED).
//
// **Q-L6L-1 (LOCKED):** foundation V1 default returns "no detection"
// for every input. The LLM-safety sub-program ships the concrete
// 5-layer impl:
//
//  1. Input pattern scan (jailbreak phrases, marker forgery)
//  2. Section boundary check (user bytes in non-INPUT sections)
//  3. Canary post-scan (regurgitated system prompt)
//  4. Instruction-hierarchy guard (template-owned vs user-issued)
//  5. Output rejection (model attempting to bypass safety)
//
// **Why no fail-closed at foundation level:** classifying benign vs
// malicious requires (a) a curated attack corpus and (b) a tuned
// pattern set — both are governance work that belongs downstream. A
// half-baked fail-closed at foundation would false-positive benign
// turns + erode user trust. The trait freeze here lets services
// wire the dep so the swap is a single line of config when LLM-safety
// ships.
type InjectionDefense interface {
	// ScanInput runs layers 1+2 BEFORE prompt assembly. Returns the
	// detection result; caller decides whether to FAIL the call.
	ScanInput(ctx context.Context, sections SectionMap) (InjectionDetection, error)

	// ScanOutput runs layers 3+4+5 AFTER the LLM response returns.
	// `known` is the per-turn canary token(s) embedded in SYSTEM.
	ScanOutput(ctx context.Context, output []byte, known []CanaryToken) (InjectionDetection, error)
}

// NoopInjectionDefense is the V1 default per Q-L6L-1. Every scan
// returns InjectionDetection{Detected:false}. The LLM-safety
// sub-program will swap this for the concrete 5-layer impl.
type NoopInjectionDefense struct{}

// ScanInput — see InjectionDefense. V1: never detects.
func (NoopInjectionDefense) ScanInput(_ context.Context, _ SectionMap) (InjectionDetection, error) {
	return InjectionDetection{Detected: false}, nil
}

// ScanOutput — see InjectionDefense. V1: never detects.
func (NoopInjectionDefense) ScanOutput(_ context.Context, _ []byte, _ []CanaryToken) (InjectionDetection, error) {
	return InjectionDetection{Detected: false}, nil
}

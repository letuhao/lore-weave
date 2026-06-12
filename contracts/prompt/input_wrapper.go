package prompt

import (
	"bytes"
	"errors"
)

// WrapUserInput XML-escapes user-controlled bytes and wraps them in
// <user_input>...</user_input> delimiters. Cycle 31 L6.I.1.
//
// **Why a separate wrapper:** the Composer's section_validator REJECTS
// any non-INPUT section containing the <user_input> open marker
// (cycle 31 section_renderer.go). The wrapper is the ONLY sanctioned
// path that produces those markers — defense in depth at type level.
//
// **Escape set (6 patterns per S09 §12Y.4):**
//
//   <    → &lt;
//   >    → &gt;
//   &    → &amp;
//   "    → &quot;
//   '    → &apos;
//   NUL  → "" (drop — NUL has no benign use in prompt input and is
//                a common smuggling vector for null-byte-aware parsers)
//
// Order matters: & MUST be escaped first to avoid double-encoding.
func WrapUserInput(raw []byte) []byte {
	escaped := escapeUserInput(raw)
	out := make([]byte, 0, len(escaped)+len(userInputMarkerPrefix)+len(userInputMarkerSuffix))
	out = append(out, userInputMarkerPrefix...)
	out = append(out, escaped...)
	out = append(out, userInputMarkerSuffix...)
	return out
}

// userInputMarkerSuffix mirrors userInputMarkerPrefix (defined in
// section_renderer.go).
var userInputMarkerSuffix = []byte("</user_input>")

// escapeUserInput applies the 6-pattern XML escape set described
// above. Returns a fresh slice; raw is not modified.
func escapeUserInput(raw []byte) []byte {
	// Fast path — most user input is plain text + an occasional space.
	if !bytes.ContainsAny(raw, "<>&\"'\x00") {
		return raw
	}
	out := make([]byte, 0, len(raw)+16)
	for _, b := range raw {
		switch b {
		case '&':
			out = append(out, []byte("&amp;")...)
		case '<':
			out = append(out, []byte("&lt;")...)
		case '>':
			out = append(out, []byte("&gt;")...)
		case '"':
			out = append(out, []byte("&quot;")...)
		case '\'':
			out = append(out, []byte("&apos;")...)
		case 0:
			// drop NUL — smuggling vector
		default:
			out = append(out, b)
		}
	}
	return out
}

// ErrInputMarkerSmuggling is returned when a caller passes raw input
// that already contains the <user_input> sentinel — the only way that
// can happen is if (a) the wrapper was double-applied (programming bug)
// or (b) an attacker is trying to forge the marker. Either way: FAIL.
var ErrInputMarkerSmuggling = errors.New("input_wrapper: user input contains <user_input> marker — refused to wrap (Q-L6H-1)")

// WrapUserInputStrict is the same as WrapUserInput but additionally
// REFUSES to wrap raw input that contains a literal <user_input> open
// marker. Use this in service code where the input came from an
// external boundary; reserve WrapUserInput for internal callers
// (cycle 4 prompt_audit replay reconstructors).
func WrapUserInputStrict(raw []byte) ([]byte, error) {
	if bytes.Contains(raw, userInputMarkerPrefix) {
		return nil, ErrInputMarkerSmuggling
	}
	return WrapUserInput(raw), nil
}

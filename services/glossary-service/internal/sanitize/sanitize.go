// Package sanitize provides minimal injection-neutralization for untrusted text
// that crosses INTO the glossary canon boundary.
//
// Why this exists (lore-enrichment 050/C12 "treat enriched text as DATA"):
//
//	The canon-content endpoint (internalSetCanonContent) stores enriched LLM
//	short_description as CANON. The lore-enrichment Python caller neutralizes
//	the text before sending it, but the canon boundary should be self-defending
//	regardless of caller (a future caller, or a direct internal call, must not
//	be able to write raw chat-template / role-spoofing markers into canon that
//	a downstream LLM — wiki gen, chat context injection — could then obey).
//
// This is a deliberately MINIMAL Go mirror of the lore-enrichment neutralizers
// (app/clients/sanitize.py + app/verify/sanitize.py): it is NOT a full phrase
// scanner. It:
//
//   - strips zero-width / bidi control chars used to smuggle hidden directives
//     (mirrors the Python _INVISIBLE set);
//   - NFC-normalizes (CJK-safe canonical form — 封神演义 names pass through
//     untouched; only hidden combining tricks collapse);
//   - replaces the obvious chat-template / role-spoofing markers with a
//     visible, inert placeholder so the span is preserved for a human reader
//     but cannot act as an instruction.
//
// Tag-don't-delete: legitimate in-story villain speech ("无视一切指令") is fiction,
// so we do NOT drop it; only structural injection MARKERS are neutralized. The
// Python side additionally [FICTIONAL]-tags natural-language injection phrases —
// that richer phrase layer stays the caller's job; this layer is the additive
// last-line canon-boundary defense for the structural markers.
//
// NO LLM call, NO DB, NO network. Pure functions.
package sanitize

import (
	"regexp"
	"strings"

	"golang.org/x/text/unicode/norm"
)

// invisible is the set of zero-width / bidi-control runes used to smuggle hidden
// instructions across an otherwise-innocuous span (mirrors the Python
// _INVISIBLE map in app/clients/sanitize.py / app/verify/sanitize.py).
var invisible = map[rune]struct{}{
	0x200B: {}, 0x200C: {}, 0x200D: {}, 0x200E: {}, 0x200F: {},
	0x2028: {}, 0x2029: {},
	0x202A: {}, 0x202B: {}, 0x202C: {}, 0x202D: {}, 0x202E: {},
	0xFEFF: {},
	0x2066: {}, 0x2067: {}, 0x2068: {}, 0x2069: {},
}

// markers matches the structural chat-template / role-spoofing tokens that must
// never reach canon as live instructions (mirrors the Python _MARKERS regex).
//
//	<|im_start|> / <|system|> …   chat-template tokens
//	[INST] / [/INST]              instruct-template tokens
//	<s> / </s>                    sentence/role tokens
//	system: / assistant: / user:  role prefixes
//	ignore [all] previous instructions   the canonical override phrase
var markers = regexp.MustCompile(`(?is)(` +
	`<\|[a-z_]+\|>` +
	`|\[/?(?:INST|SYSTEM|ADMIN)\]` +
	`|</?s>` +
	`|\b(?:system|assistant|user)\s*:` +
	`|ignore\s+(?:all\s+)?previous\s+instructions` +
	`)`)

// placeholder is the inert, visible replacement for a neutralized marker. It
// preserves "something was here" for a human reviewer without acting as an
// instruction on a downstream LLM.
const placeholder = "[neutralized]"

// stripInvisible drops every zero-width / bidi-control rune.
func stripInvisible(s string) string {
	if s == "" {
		return s
	}
	return strings.Map(func(r rune) rune {
		if _, bad := invisible[r]; bad {
			return -1
		}
		return r
	}, s)
}

// NeutralizeCanonText returns a safe form of untrusted text destined for the
// glossary canon boundary. It strips invisibles, NFC-normalizes, then replaces
// structural injection markers with an inert placeholder. Empty in → empty out.
// It never panics and never drops legitimate CJK content.
func NeutralizeCanonText(s string) string {
	if s == "" {
		return s
	}
	s = stripInvisible(s)
	s = norm.NFC.String(s)
	s = markers.ReplaceAllString(s, placeholder)
	return s
}

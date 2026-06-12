// Package expunge implements the conformance suite's known-failures list
// (xfstests `-E` / LTP skiplist semantics).
//
// A case whose id is listed is "known-broken, tracked, doesn't block the gate":
// a Fail on it is downgraded to Skip(expunged) carrying its Deferred-Items ref.
// Every expunge MUST name a ref — there are no silent skips; the list is the
// audit trail wiring catastrophic-rebuild (DEFERRED 149), monthly L3.F, etc.
// into the gate (plan §1.3, §2.4).
package expunge

import (
	"errors"
	"fmt"
	"io/fs"
	"os"
	"sort"
	"strings"

	"gopkg.in/yaml.v3"

	"github.com/loreweave/foundation/tests/conformance/internal/verdict"
)

// ReasonPrefix marks a result that was downgraded by the expunge list. The
// summary detects expunged downgrades by this prefix (see WasExpunged).
const ReasonPrefix = "expunged → "

// List is the parsed known-failures list: case-id → Deferred-Items ref.
type List struct {
	refs map[string]string
}

// Load reads the expunge list from path. A missing file is NOT an error — an
// empty expunge list is the normal, healthy state. Every present entry must
// carry a non-empty ref, else Load fails (no untracked expunges).
func Load(path string) (List, error) {
	raw, err := os.ReadFile(path)
	if errors.Is(err, fs.ErrNotExist) {
		return List{refs: map[string]string{}}, nil
	}
	if err != nil {
		return List{}, err
	}
	m := map[string]string{}
	if err := yaml.Unmarshal(raw, &m); err != nil {
		return List{}, fmt.Errorf("%s: %w", path, err)
	}
	for id, ref := range m {
		if strings.TrimSpace(id) == "" {
			return List{}, fmt.Errorf("%s: empty case id in expunge list", path)
		}
		if strings.TrimSpace(ref) == "" {
			return List{}, fmt.Errorf("%s: case %q expunged with no Deferred-Items ref (every expunge must be tracked)", path, id)
		}
	}
	return List{refs: m}, nil
}

// Len reports the number of expunged ids.
func (l List) Len() int { return len(l.refs) }

// Has reports whether id is expunged.
func (l List) Has(id string) bool {
	_, ok := l.refs[id]
	return ok
}

// Dangling returns expunged ids that are NOT in known (the set of real case
// ids), sorted. A dangling entry means the list has rotted — a case was renamed
// or removed, so the expunge no longer suppresses anything and the audit trail
// is stale. The caller should treat a non-empty result as a hard error.
func (l List) Dangling(known map[string]bool) []string {
	var out []string
	for id := range l.refs {
		if !known[id] {
			out = append(out, id)
		}
	}
	sort.Strings(out)
	return out
}

// Downgrade returns a copy of results in which any Fail on a listed id becomes
// Skip(expunged), its reason rewritten to name the ref (preserving the original
// failure reason for forensics). Non-Fail verdicts and non-listed ids are
// untouched — so an expunged case that unexpectedly passes still reports pass.
func (l List) Downgrade(results []verdict.Result) []verdict.Result {
	out := make([]verdict.Result, len(results))
	copy(out, results)
	for i := range out {
		if out[i].Verdict != verdict.Fail {
			continue
		}
		ref, ok := l.refs[out[i].ID]
		if !ok {
			continue
		}
		orig := out[i].Reason
		out[i].Verdict = verdict.Skip
		out[i].Reason = ReasonPrefix + ref
		if orig != "" {
			out[i].Reason += " (was: " + orig + ")"
		}
	}
	return out
}

// WasExpunged reports whether a result is an expunge downgrade (a Skip carrying
// the expunge reason prefix). Used by the summary to list expunged cases.
func WasExpunged(r verdict.Result) bool {
	return r.Verdict == verdict.Skip && strings.HasPrefix(r.Reason, ReasonPrefix)
}

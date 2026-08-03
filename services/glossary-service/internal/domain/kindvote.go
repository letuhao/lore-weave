package domain

import "github.com/google/uuid"

// Entity-kind resolution — spec `docs/specs/2026-08-03-glossary-kg-entity-refactor/2026-08-02-entity-kind-resolution.md`.
//
// An entity's kind used to be decided by whichever extraction batch named it FIRST and was
// never revisited: `findEntityCrossKind` is oldest-wins and returns the STORED kind, so an
// incoming answer was discarded silently. Measured on 封神演義, 173 of 1,531 stored entities
// (11%) held a kind the model disagreed with by majority -- including the protagonist, frozen
// as `species` by the book's very first extraction run.
//
// The model is not the problem. Over ~84 observations it called 姜子牙 a `character` 64 times
// and a `species` 20. The store kept the first draw instead of the argmax over all of them.
//
// This file is the estimator, as a PURE function over (incumbent, votes, parents) so it can be
// tested directly. The DB plumbing lives in the api package; nothing here touches a pool.

// The thresholds. Each exists to stop a specific failure, named at its declaration.
const (
	// MinSwitchVotes -- a single stray observation must never re-kind a settled entity.
	// One mis-tag in one batch is exactly what oldest-wins was protecting against, and
	// that protection was correct; it was the "never revisit" part that was wrong.
	MinSwitchVotes = 2

	// SwitchRatio -- the challenger must LEAD, not merely tie. Without hysteresis the kind
	// flips on every near-tie and each flip re-emits an outbox event, so the KG re-syncs
	// forever over a coin toss.
	SwitchRatio = 1.5

	// DescendShare -- when descending the hierarchy, a child takes over from its parent only
	// with a majority of the parent's support. Two children splitting it evenly means the
	// text genuinely has not decided between them, and the honest answer is the PARENT.
	// This is what makes "if unsure, use the generic kind" a rule rather than a hope.
	DescendShare = 0.5

	// LabelMinVotes / LabelMinShare -- a secondary label is a real second reading, not a
	// stray. 西岐 is an organization 52 times and a location 38: both are true, and erasing
	// one is the lossy behaviour multi-label exists to end.
	LabelMinVotes = 2
	LabelMinShare = 0.2

	// maxDepth bounds the ancestor walk. A parent chain is authored data (an admin, or a
	// book-tier edit), so a cycle is reachable by a mistake, and an unbounded walk would
	// hang the writeback rather than mis-answer it.
	maxDepth = 16
)

// KindVote is one row of the observation ledger: how many times extraction proposed this kind
// for this entity.
type KindVote struct {
	KindID uuid.UUID
	Votes  int
}

// Resolution is what the ledger says the entity's kind should be, and why.
type Resolution struct {
	// Primary is the kind to store. Always set -- it equals the incumbent when nothing wins.
	Primary uuid.UUID
	// Changed reports that Primary differs from the incumbent (the caller journals + emits).
	Changed bool
	// Refinement reports that the change was parent -> descendant. It is exempt from the
	// vote threshold because it loses no information: `terminology` -> `technique` is the
	// same claim, stated more precisely.
	Refinement bool
	// Conflict is a challenger that LED but failed the threshold. Recorded rather than
	// dropped: the writeback used to report `updated` and never `conflict`, so a persistent
	// disagreement between the model and the store was invisible for as long as it lasted.
	Conflict uuid.UUID
	// Secondary are the other readings worth keeping -- the facets. Ancestors and descendants
	// of Primary are excluded: an ancestor is implied by Primary, and a descendant would be a
	// refinement rather than a second axis.
	Secondary []uuid.UUID
}

// ancestorsOf walks up the parent chain, excluding the node itself. Depth-bounded.
func ancestorsOf(k uuid.UUID, parents map[uuid.UUID]uuid.UUID) []uuid.UUID {
	var out []uuid.UUID
	seen := map[uuid.UUID]bool{k: true}
	cur := k
	for i := 0; i < maxDepth; i++ {
		p, ok := parents[cur]
		if !ok || p == uuid.Nil || seen[p] {
			break
		}
		out = append(out, p)
		seen[p] = true
		cur = p
	}
	return out
}

// isDescendant reports whether child sits below ancestor in the kind tree.
func isDescendant(child, ancestor uuid.UUID, parents map[uuid.UUID]uuid.UUID) bool {
	if child == ancestor {
		return false
	}
	for _, a := range ancestorsOf(child, parents) {
		if a == ancestor {
			return true
		}
	}
	return false
}

// rollUp gives every node its own votes plus every descendant's. This is what lets branches be
// compared fairly: {technique 10, power_system 8} means "some kind of concept" has 18 against
// `character`'s 5, even though no single concept kind beats 5 on its own votes.
func rollUp(votes []KindVote, parents map[uuid.UUID]uuid.UUID) map[uuid.UUID]int {
	rolled := map[uuid.UUID]int{}
	for _, v := range votes {
		rolled[v.KindID] += v.Votes
		for _, a := range ancestorsOf(v.KindID, parents) {
			rolled[a] += v.Votes
		}
	}
	return rolled
}

// childrenOf inverts the parent map for the nodes actually under consideration.
func childrenOf(rolled map[uuid.UUID]int, parents map[uuid.UUID]uuid.UUID) map[uuid.UUID][]uuid.UUID {
	kids := map[uuid.UUID][]uuid.UUID{}
	for k := range rolled {
		if p, ok := parents[k]; ok && p != uuid.Nil {
			kids[p] = append(kids[p], k)
		}
	}
	return kids
}

// descend walks from the best-supported root down to the most SPECIFIC kind that still holds a
// majority of its parent's support, and stops where the children split it.
func descend(start uuid.UUID, rolled map[uuid.UUID]int, kids map[uuid.UUID][]uuid.UUID) uuid.UUID {
	cur := start
	for i := 0; i < maxDepth; i++ {
		best, bestN := uuid.Nil, 0
		for _, c := range kids[cur] {
			// Deterministic on a tie: the lower UUID wins, so two runs over the same
			// ledger never disagree (a flapping primary re-emits to the KG each time).
			if rolled[c] > bestN || (rolled[c] == bestN && best != uuid.Nil && c.String() < best.String()) {
				best, bestN = c, rolled[c]
			}
		}
		// STRICTLY greater. At exactly half, the children have split their parent's support
		// evenly and the text has not decided between them -- descending there would pick one
		// on a map-iteration coin toss and then freeze it, which is the whole defect this
		// resolver replaces. Written `<` first, and a 5-5 split descended.
		if best == uuid.Nil || float64(bestN) <= DescendShare*float64(rolled[cur]) {
			return cur
		}
		cur = best
	}
	return cur
}

// ResolveKind is the estimator. `parents` maps a kind to its parent (absent or Nil = a root);
// pass an empty map for a flat catalogue, where this degrades to a plain modal vote.
func ResolveKind(incumbent uuid.UUID, votes []KindVote, parents map[uuid.UUID]uuid.UUID) Resolution {
	res := Resolution{Primary: incumbent}
	if len(votes) == 0 {
		return res
	}
	rolled := rollUp(votes, parents)
	kids := childrenOf(rolled, parents)

	// The best ROOT among the kinds observed, then descend into it.
	bestRoot, bestRootN := uuid.Nil, -1
	for k, n := range rolled {
		p, hasP := parents[k]
		if hasP && p != uuid.Nil {
			continue // not a root of the observed set
		}
		if n > bestRootN || (n == bestRootN && bestRoot != uuid.Nil && k.String() < bestRoot.String()) {
			bestRoot, bestRootN = k, n
		}
	}
	if bestRoot == uuid.Nil {
		return res
	}
	challenger := descend(bestRoot, rolled, kids)

	switch {
	case challenger == incumbent:
		// nothing to do
	case incumbent != uuid.Nil && isDescendant(challenger, incumbent, parents):
		// Refinement: strictly more specific, so no majority is required.
		res.Primary, res.Changed, res.Refinement = challenger, true, true
	case rolled[challenger] >= MinSwitchVotes &&
		float64(rolled[challenger]) > SwitchRatio*float64(rolled[incumbent]):
		res.Primary, res.Changed = challenger, true
	default:
		// It led and lost. Say so rather than dropping it.
		if rolled[challenger] > rolled[incumbent] {
			res.Conflict = challenger
		}
	}

	// Facets: other readings with real support, on a different axis from the primary.
	total := 0
	for _, v := range votes {
		total += v.Votes
	}
	for _, v := range votes {
		if v.KindID == res.Primary || v.Votes < LabelMinVotes {
			continue
		}
		if float64(v.Votes) < LabelMinShare*float64(total) {
			continue
		}
		if isDescendant(v.KindID, res.Primary, parents) || isDescendant(res.Primary, v.KindID, parents) {
			continue
		}
		res.Secondary = append(res.Secondary, v.KindID)
	}
	return res
}

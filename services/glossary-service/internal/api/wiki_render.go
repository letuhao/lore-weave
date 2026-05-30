package api

import (
	"encoding/json"
	"fmt"
	"sort"
)

// ── C5 (D4-03) — deterministic KG → wiki body renderer ───────────────────────
//
// Replaces the empty `{}` stub body with a structured article body
// assembled from the entity + its 1-hop KG neighborhood. Pure +
// deterministic (no LLM): it RENDERS known facts into prose-ish
// ProseMirror/TipTap nodes — it does NOT invent canon (Q4 LOCKED).
//
// The output is a TipTap `doc` (the same `{"type":"doc","content":[...]}`
// shape the wiki body_json already uses), so the existing FE renderer +
// public endpoint consume it unchanged.
//
// H0 LOCKED — every neighborhood fact is tagged with its `source_type`:
//   - "glossary" (authored canon) renders plainly;
//   - "enriched" (quarantined makeup) is wrapped in a visibly distinct
//     marker so it is NEVER silently presented as canon.

// wikiRenderInput is the renderer's pure input. The caller (the wiki
// generate handler) assembles it from glossary Postgres (display name,
// kind, attributes) + the knowledge-service neighborhood read.
type wikiRenderInput struct {
	DisplayName string
	KindName    string
	// Attributes are glossary-authored canon (source_type='glossary').
	Attributes []wikiRenderAttr
	// Neighborhood is the KG 1-hop read; nil when unavailable/empty.
	Neighborhood *kgNeighborhood
}

type wikiRenderAttr struct {
	Label string
	Value string
}

// sourceTypeEnriched is the H0 quarantine marker. Kept as a constant so
// the renderer and its tests agree on the exact string.
const sourceTypeEnriched = "enriched"
const sourceTypeGlossary = "glossary"

// renderWikiBody builds the TipTap body_json document. It always
// returns a non-empty doc: even an entity with no attributes and no KG
// neighborhood gets a lead paragraph so the article is never blank
// (graceful minimal body — no crash on a sparse entity).
func renderWikiBody(in wikiRenderInput) json.RawMessage {
	content := []any{}

	name := in.DisplayName
	if name == "" {
		name = "(unnamed entity)"
	}

	// ── Lead paragraph ───────────────────────────────────────────────
	lead := name
	if in.KindName != "" {
		lead = fmt.Sprintf("%s（%s）", name, in.KindName)
	}
	content = append(content, paragraphNode(lead))

	// ── Attributes section (glossary canon) ──────────────────────────
	if len(in.Attributes) > 0 {
		content = append(content, headingNode(2, "基本资料"))
		items := make([]any, 0, len(in.Attributes))
		for _, a := range in.Attributes {
			if a.Value == "" {
				continue
			}
			items = append(items, listItemNode(fmt.Sprintf("%s：%s", a.Label, a.Value)))
		}
		if len(items) > 0 {
			content = append(content, bulletListNode(items))
		}
	}

	// ── KG neighborhood: relationships, split by source_type ─────────
	canon, enriched := splitRelations(in.Neighborhood)

	if len(canon) > 0 {
		content = append(content, headingNode(2, "关系"))
		items := make([]any, 0, len(canon))
		for _, r := range canon {
			items = append(items, listItemNode(relationSentence(name, r)))
		}
		content = append(content, bulletListNode(items))
	}

	if len(enriched) > 0 {
		// H0: enriched material is structurally distinct. Heading
		// explicitly labels it as unverified makeup, and each item
		// carries the marker prefix so it can never read as canon.
		content = append(content, headingNode(2, "补充关系（增补·待校验）"))
		content = append(content, paragraphNode(
			"以下内容为自动增补（enriched），尚未经作者校验，非原典正史。",
		))
		items := make([]any, 0, len(enriched))
		for _, r := range enriched {
			items = append(items, enrichedListItemNode(relationSentence(name, r)))
		}
		content = append(content, bulletListNode(items))
	}

	if in.Neighborhood != nil && in.Neighborhood.RelationsTruncated {
		content = append(content, paragraphNode(fmt.Sprintf(
			"（仅显示前 %d 条关系，共 %d 条。）",
			len(in.Neighborhood.Relations), in.Neighborhood.TotalRelations,
		)))
	}

	doc := map[string]any{
		"type":    "doc",
		"content": content,
	}
	raw, _ := json.Marshal(doc)
	return raw
}

// splitRelations partitions the neighborhood's relations into canon
// (source_type='glossary') and enriched (everything else), each sorted
// deterministically by (predicate, peer) so renders are reproducible.
func splitRelations(n *kgNeighborhood) (canon, enriched []kgNeighborRelation) {
	if n == nil {
		return nil, nil
	}
	for _, r := range n.Relations {
		// H0 fail-safe: anything not explicitly 'glossary' is treated
		// as enriched/quarantined, never silently merged as canon.
		if r.SourceType == sourceTypeGlossary {
			canon = append(canon, r)
		} else {
			enriched = append(enriched, r)
		}
	}
	sortRelations(canon)
	sortRelations(enriched)
	return canon, enriched
}

func sortRelations(rs []kgNeighborRelation) {
	sort.SliceStable(rs, func(i, j int) bool {
		if rs[i].Predicate != rs[j].Predicate {
			return rs[i].Predicate < rs[j].Predicate
		}
		return relationPeer(rs[i]) < relationPeer(rs[j])
	})
}

// relationSentence renders one edge as a readable line. The neighborhood
// edges are directional (subject -predicate-> object); we phrase it from
// the article entity's perspective when it is one of the endpoints.
func relationSentence(entityName string, r kgNeighborRelation) string {
	subj := deref(r.SubjectName)
	obj := deref(r.ObjectName)
	pred := r.Predicate
	if pred == "" {
		pred = "关联"
	}
	switch {
	case subj == entityName && obj != "":
		return fmt.Sprintf("%s → %s（%s）", pred, obj, obj)
	case obj == entityName && subj != "":
		return fmt.Sprintf("%s ← %s（%s）", pred, subj, subj)
	case subj != "" && obj != "":
		return fmt.Sprintf("%s %s %s", subj, pred, obj)
	default:
		return pred
	}
}

func relationPeer(r kgNeighborRelation) string {
	if obj := deref(r.ObjectName); obj != "" {
		return obj
	}
	return deref(r.SubjectName)
}

func deref(s *string) string {
	if s == nil {
		return ""
	}
	return *s
}

// ── TipTap node builders ─────────────────────────────────────────────────────

func textNode(s string) map[string]any {
	return map[string]any{"type": "text", "text": s}
}

func paragraphNode(s string) map[string]any {
	return map[string]any{
		"type":    "paragraph",
		"content": []any{textNode(s)},
	}
}

func headingNode(level int, s string) map[string]any {
	return map[string]any{
		"type":    "heading",
		"attrs":   map[string]any{"level": level},
		"content": []any{textNode(s)},
	}
}

func listItemNode(s string) map[string]any {
	return map[string]any{
		"type":    "listItem",
		"content": []any{paragraphNode(s)},
	}
}

// enrichedListItemNode marks the text with a `source_type` attr + a
// visible "增补" prefix so enriched content is distinguishable both
// structurally (attrs) and visually (prefix). H0.
func enrichedListItemNode(s string) map[string]any {
	return map[string]any{
		"type":  "listItem",
		"attrs": map[string]any{"source_type": sourceTypeEnriched},
		"content": []any{
			map[string]any{
				"type": "paragraph",
				"attrs": map[string]any{
					"source_type": sourceTypeEnriched,
				},
				"content": []any{textNode("【增补】" + s)},
			},
		},
	}
}

func bulletListNode(items []any) map[string]any {
	return map[string]any{
		"type":    "bulletList",
		"content": items,
	}
}

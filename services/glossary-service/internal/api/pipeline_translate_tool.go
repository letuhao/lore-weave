package api

// Pipeline M4 — glossary-entry translation. Make the S4/S26 scenario agent-reachable:
// the LLM can propose target-language NAMES for a book's entities. Each proposal is
// written to attribute_translations on the entity's DISPLAY (name/term) attribute value
// at confidence='draft' — a reviewable suggestion, NOT canon. The upsert NEVER overwrites
// a human-'verified' rendering (RowsAffected()==0 ⇒ reported as skipped). Because it is
// additive + reversible + never clobbers verified, it is class W (Edit) — the same call
// the M2 chapter-link/evidence writes use, not the confirm spine.
//
// Scope (v1): the entity's display name only (the S4 use case). Per-attribute translation
// of arbitrary fields, and per-language ALIASES (S6, a data-model decision), are out of
// scope — tracked as D-GLOSSARY-PERLANG-ALIASES.

import (
	"context"
	"errors"
	"strings"

	"github.com/google/uuid"
	"github.com/loreweave/grantclient"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

// translateBatchCap bounds one proposal call (each item does per-entity DB work).
const translateBatchCap = 200

// RegisterPipelineTranslateTools adds the M4 entity-translation tool to the /mcp server.
func (s *Server) RegisterPipelineTranslateTools(srv *mcp.Server) {
	mcp.AddTool(srv, &mcp.Tool{
		Name: "glossary_propose_translation",
		Description: "Propose target-language NAMES for a book's entities (additive, takes effect " +
			"immediately as DRAFT for review; Edit). book_id + language_code (BCP-47, e.g. 'en' | 'vi') + " +
			"items: a list of {entity_id, value} where value is the translated name. Each lands at " +
			"confidence='draft' on the entity's display name. NEVER overwrites a human-'verified' " +
			"translation (those are reported as skipped). Returns per-entity results. Use " +
			"glossary_search / glossary_list_* first to get entity_ids.",
	}, s.toolProposeTranslation)
}

type translateItem struct {
	EntityID string `json:"entity_id" jsonschema:"the entity (UUID)"`
	Value    string `json:"value" jsonschema:"the target-language name for this entity"`
}

type proposeTranslationToolIn struct {
	BookID       string          `json:"book_id" jsonschema:"the book (UUID)"`
	LanguageCode string          `json:"language_code" jsonschema:"target language (BCP-47, e.g. en | vi)"`
	Items        []translateItem `json:"items" jsonschema:"the entities + their translated names"`
}

type translateItemResult struct {
	EntityID string `json:"entity_id"`
	Status   string `json:"status"` // written | skipped
	Reason   string `json:"reason,omitempty"`
}

type proposeTranslationOut struct {
	LanguageCode string                `json:"language_code"`
	Written      int                   `json:"written"`
	Skipped      int                   `json:"skipped"`
	Results      []translateItemResult `json:"results"`
}

func (s *Server) toolProposeTranslation(ctx context.Context, _ *mcp.CallToolRequest, in proposeTranslationToolIn) (*mcp.CallToolResult, proposeTranslationOut, error) {
	_, bookID, err := s.bookToolAuth(ctx, in.BookID, grantclient.GrantEdit)
	if err != nil {
		return nil, proposeTranslationOut{}, err
	}
	lang := strings.TrimSpace(in.LanguageCode)
	if lang == "" {
		return nil, proposeTranslationOut{}, errors.New("language_code is required")
	}
	if len(in.Items) == 0 {
		return nil, proposeTranslationOut{}, errors.New("at least one item is required")
	}
	if len(in.Items) > translateBatchCap {
		return nil, proposeTranslationOut{}, errors.New("too many items (max 200 per call)")
	}

	out := proposeTranslationOut{LanguageCode: lang, Results: make([]translateItemResult, 0, len(in.Items))}
	for _, it := range in.Items {
		entityID, ok, perr := s.resolveEntityInBook(ctx, it.EntityID, bookID)
		if perr != nil {
			out.Results = append(out.Results, translateItemResult{EntityID: it.EntityID, Status: "skipped", Reason: "could not resolve the entity"})
			out.Skipped++
			continue
		}
		if !ok {
			out.Results = append(out.Results, translateItemResult{EntityID: it.EntityID, Status: "skipped", Reason: "entity not found in this book"})
			out.Skipped++
			continue
		}
		value := strings.TrimSpace(it.Value)
		if value == "" {
			out.Results = append(out.Results, translateItemResult{EntityID: it.EntityID, Status: "skipped", Reason: "empty value"})
			out.Skipped++
			continue
		}
		attrValueID, hasName, derr := s.entityDisplayAttrValue(ctx, entityID)
		if derr != nil {
			out.Results = append(out.Results, translateItemResult{EntityID: it.EntityID, Status: "skipped", Reason: "could not resolve the entity's name"})
			out.Skipped++
			continue
		}
		if !hasName {
			out.Results = append(out.Results, translateItemResult{EntityID: it.EntityID, Status: "skipped", Reason: "entity has no name/term attribute to translate"})
			out.Skipped++
			continue
		}
		wrote, werr := s.upsertDraftTranslation(ctx, attrValueID, lang, value)
		if werr != nil {
			out.Results = append(out.Results, translateItemResult{EntityID: it.EntityID, Status: "skipped", Reason: "write failed"})
			out.Skipped++
			continue
		}
		if !wrote {
			out.Results = append(out.Results, translateItemResult{EntityID: it.EntityID, Status: "skipped", Reason: "a verified translation already exists (protected)"})
			out.Skipped++
			continue
		}
		// Propagate target-language staleness to translation-service (M6b), as the HTTP path does.
		s.emitTranslationChanged(ctx, bookID, entityID, lang)
		out.Results = append(out.Results, translateItemResult{EntityID: it.EntityID, Status: "written"})
		out.Written++
	}
	return nil, out, nil
}

// entityDisplayAttrValue resolves an entity's display-name attribute VALUE id — the
// 'name' (preferred) or 'term' attribute value. ok=false when the entity carries neither.
func (s *Server) entityDisplayAttrValue(ctx context.Context, entityID uuid.UUID) (uuid.UUID, bool, error) {
	var id uuid.UUID
	err := s.pool.QueryRow(ctx, `
		SELECT av.attr_value_id
		FROM entity_attribute_values av
		JOIN book_attributes ba ON ba.attr_id = av.attr_def_id
		JOIN book_genres g ON g.genre_id = ba.genre_id
		WHERE av.entity_id = $1 AND ba.code IN ('name','term')
		ORDER BY CASE ba.code WHEN 'name' THEN 0 ELSE 1 END,
		         (g.code = 'universal') DESC, ba.sort_order
		LIMIT 1`, entityID).Scan(&id)
	if err != nil {
		if isNoRows(err) {
			return uuid.Nil, false, nil
		}
		return uuid.Nil, false, err
	}
	return id, true, nil
}

// upsertDraftTranslation writes (or refreshes) a DRAFT translation for an attribute value
// in a language, NEVER overwriting a 'verified' rendering. wrote=false ⇒ a verified
// translation already exists (the WHERE gate produced 0 rows). Mirrors the never-clobber
// upsert the internal apply-translations path uses, at confidence='draft' (agent proposal).
func (s *Server) upsertDraftTranslation(ctx context.Context, attrValueID uuid.UUID, lang, value string) (bool, error) {
	ct, err := s.pool.Exec(ctx, `
		INSERT INTO attribute_translations (attr_value_id, language_code, value, confidence, translator)
		VALUES ($1, $2, $3, 'draft', 'assistant')
		ON CONFLICT (attr_value_id, language_code) DO UPDATE
		  SET value = EXCLUDED.value, confidence = 'draft',
		      translator = EXCLUDED.translator, updated_at = now()
		  WHERE attribute_translations.confidence <> 'verified'`,
		attrValueID, lang, value)
	if err != nil {
		return false, err
	}
	return ct.RowsAffected() > 0, nil
}

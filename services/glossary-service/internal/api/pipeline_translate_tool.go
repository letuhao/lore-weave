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
	"encoding/json"
	"errors"
	"strings"

	"github.com/google/uuid"
	"github.com/loreweave/grantclient"
	lwmcp "github.com/loreweave/loreweave_mcp"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

// translateBatchCap bounds one proposal call (each item does per-entity DB work).
const translateBatchCap = 200

// RegisterPipelineTranslateTools adds the M4 entity-translation tool to the /mcp server.
func (s *Server) RegisterPipelineTranslateTools(srv *mcp.Server) {
	lwmcp.RegisterTool(srv, &mcp.Tool{
		Name: "glossary_propose_translation",
		Description: "Propose target-language NAMES for a book's entities (additive, takes effect " +
			"immediately as DRAFT for review; Edit). book_id + language_code (BCP-47, e.g. 'en' | 'vi') + " +
			"items: a list of {entity_id, value} where value is the translated name. Each lands at " +
			"confidence='draft' on the entity's display name. NEVER overwrites a human-'verified' " +
			"translation (those are reported as skipped). Returns per-entity results. Use " +
			"glossary_search / glossary_list_* first to get entity_ids.",
		// Despite the "propose" name, this writes a draft translation DIRECTLY (confidence=
		// 'draft', never clobbers verified) — no confirm_token — so it is Tier A, not W.
		Meta: lwmcp.NewToolMeta(lwmcp.TierA, lwmcp.ScopeBook, nil, nil),
	}, s.toolProposeTranslation)

	lwmcp.RegisterTool(srv, &mcp.Tool{
		Name: "glossary_propose_aliases",
		Description: "Propose target-language ALIASES (alternate names) for a book's entities (additive, " +
			"takes effect immediately as DRAFT for review; Edit). book_id + language_code (BCP-47, e.g. " +
			"'en' | 'vi') + items: a list of {entity_id, aliases: [name, ...]} where aliases are the " +
			"alternate names in that language. Stored as a per-language alias set on the entity (one set " +
			"per language); NEVER overwrites a human-'verified' alias set (reported as skipped). Use this " +
			"so an entity is findable by its name in each language. Returns per-entity results.",
		// Direct draft write (confidence='draft', never clobbers verified), no confirm_token ⇒ Tier A.
		Meta: lwmcp.NewToolMeta(lwmcp.TierA, lwmcp.ScopeBook, nil, nil),
	}, s.toolProposeAliases)
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

// ── per-language aliases (S6) ─────────────────────────────────────────────────

type aliasItem struct {
	EntityID string   `json:"entity_id" jsonschema:"the entity (UUID)"`
	Aliases  []string `json:"aliases" jsonschema:"the entity's alternate names in this language"`
}

type proposeAliasesToolIn struct {
	BookID       string      `json:"book_id" jsonschema:"the book (UUID)"`
	LanguageCode string      `json:"language_code" jsonschema:"target language (BCP-47, e.g. en | vi)"`
	Items        []aliasItem `json:"items" jsonschema:"the entities + their alias sets in this language"`
}

// toolProposeAliases writes a per-language alias SET for each entity — modeled (S6,
// Option a) as a DRAFT translation of the entity's `aliases` attribute value, whose
// value is a JSON array. Never overwrites a 'verified' alias set. Class W (additive,
// reversible), like glossary_propose_translation.
func (s *Server) toolProposeAliases(ctx context.Context, _ *mcp.CallToolRequest, in proposeAliasesToolIn) (*mcp.CallToolResult, proposeTranslationOut, error) {
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
		skip := func(reason string) {
			out.Results = append(out.Results, translateItemResult{EntityID: it.EntityID, Status: "skipped", Reason: reason})
			out.Skipped++
		}
		entityID, ok, perr := s.resolveEntityInBook(ctx, it.EntityID, bookID)
		if perr != nil {
			skip("could not resolve the entity")
			continue
		}
		if !ok {
			skip("entity not found in this book")
			continue
		}
		// Clean: trim, drop empties, dedup. An empty set is a no-op (nothing to propose).
		cleaned := dedupStrings(func() []string {
			t := make([]string, 0, len(it.Aliases))
			for _, a := range it.Aliases {
				if v := strings.TrimSpace(a); v != "" {
					t = append(t, v)
				}
			}
			return t
		}())
		if len(cleaned) == 0 {
			skip("no non-empty aliases")
			continue
		}
		attrValueID, aerr := s.resolveOrCreateEntityAliasesValue(ctx, entityID)
		if errors.Is(aerr, errNoAliasesAttr) {
			skip("this entity's kind has no aliases attribute")
			continue
		}
		if aerr != nil {
			skip("could not resolve the entity's alias attribute")
			continue
		}
		payload, merr := json.Marshal(cleaned)
		if merr != nil {
			skip("could not encode the aliases")
			continue
		}
		wrote, werr := s.upsertDraftTranslation(ctx, attrValueID, lang, string(payload))
		if werr != nil {
			skip("write failed")
			continue
		}
		if !wrote {
			skip("a verified alias set already exists (protected)")
			continue
		}
		s.emitTranslationChanged(ctx, bookID, entityID, lang)
		out.Results = append(out.Results, translateItemResult{EntityID: it.EntityID, Status: "written"})
		out.Written++
	}
	return nil, out, nil
}

// errNoAliasesAttr — the entity's kind carries no 'aliases' attribute.
var errNoAliasesAttr = errors.New("no aliases attribute for this entity's kind")

// resolveOrCreateEntityAliasesValue returns the entity's `aliases` attribute VALUE id,
// creating an empty ('[]') source-language value row if none exists yet (a translation
// must attach to an attr_value_id). The aliases attr_def is resolved for the entity's
// kind, universal-genre-preferred.
func (s *Server) resolveOrCreateEntityAliasesValue(ctx context.Context, entityID uuid.UUID) (uuid.UUID, error) {
	var attrDefID uuid.UUID
	if err := s.pool.QueryRow(ctx, `
		SELECT ba.attr_id
		FROM glossary_entities e
		JOIN book_attributes ba ON ba.kind_id = e.kind_id
		JOIN book_genres g ON g.genre_id = ba.genre_id
		WHERE e.entity_id = $1 AND ba.code = 'aliases'
		ORDER BY (g.code = 'universal') DESC, ba.sort_order
		LIMIT 1`, entityID).Scan(&attrDefID); err != nil {
		if isNoRows(err) {
			return uuid.Nil, errNoAliasesAttr
		}
		return uuid.Nil, err
	}
	var avID uuid.UUID
	// Resolve-or-create: the UNIQUE(entity_id, attr_def_id) makes the ON CONFLICT a
	// no-op that still RETURNs the existing row's id.
	err := s.pool.QueryRow(ctx, `
		INSERT INTO entity_attribute_values (entity_id, attr_def_id, original_language, original_value)
		VALUES ($1, $2, 'zh', '[]')
		ON CONFLICT (entity_id, attr_def_id) DO UPDATE
		  SET original_value = entity_attribute_values.original_value
		RETURNING attr_value_id`, entityID, attrDefID).Scan(&avID)
	return avID, err
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

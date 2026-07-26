package api

import (
	"context"
	"errors"
	"net/http"

	"github.com/google/uuid"
	"github.com/modelcontextprotocol/go-sdk/mcp"

	lwmcp "github.com/loreweave/loreweave_mcp"
)

// Agent-registry MCP server (spec §12b — agent self-registration). Exposes the
// skills catalog as MCP tools so a chat agent can list/read skills and PROPOSE
// new ones (never a direct write — propose→human-approve). Federated through
// ai-gateway with the mandatory prefix "registry_". Identity comes from the
// envelope X-User-Id (kit IdentityMiddleware), NEVER a tool arg (SEC-1).
func (s *Server) mcpHandler() http.Handler {
	srv := mcp.NewServer(&mcp.Implementation{Name: "registry", Version: "0.1.0"}, nil)

	registerARTool(srv, &mcp.Tool{
		Name:        "registry_list_skills",
		Description: "List the skills visible to the signed-in user (System defaults + their own). Returns each skill's slug + description (the L1 metadata) — not the full body. Use to see what skills exist before proposing a new one or reading one in full.",
		Meta:        lwmcp.NewToolMeta(lwmcp.TierR, lwmcp.ScopeUser, nil, []string{"skills", "list skills", "my skills", "what skills"}),
		InputSchema: closedSetSchemaFor[listSkillsIn](map[string][]any{
			"surface": enumSurfaces,
		}),
	}, s.toolListSkills)

	registerARTool(srv, &mcp.Tool{
		Name:        "registry_get_skill",
		Description: "Get the full SKILL.md body of one skill the user can see, by slug. Read-only.",
		Meta:        lwmcp.NewToolMeta(lwmcp.TierR, lwmcp.ScopeUser, nil, []string{"read skill", "skill body", "get skill", "show skill"}),
	}, s.toolGetSkill)

	registerARTool(srv, &mcp.Tool{
		Name:        "registry_propose_skill",
		Description: "PROPOSE a new prompt-only skill (SKILL.md) for the user. Does NOT create it — it records a proposal the user must approve in the UI. Provide slug (lowercase a-z0-9-), a one-line description, and the markdown body (instructions). Use this to save a useful workflow as a reusable skill.",
		Meta:        lwmcp.NewToolMeta(lwmcp.TierA, lwmcp.ScopeUser, nil, []string{"save skill", "propose skill", "create skill", "author a reusable skill"}),
		InputSchema: closedSetSchemaFor[proposeSkillIn](map[string][]any{
			"surfaces[]": enumSurfaces,
		}),
	}, s.toolProposeSkill)

	registerARTool(srv, &mcp.Tool{
		Name:        "registry_update_skill",
		Description: "PROPOSE an update to one of the user's OWN skills (by slug). Does NOT apply immediately — the user approves the diff in the UI. Provide the slug and the new description and/or body.",
		Meta:        lwmcp.NewToolMeta(lwmcp.TierA, lwmcp.ScopeUser, nil, []string{"update skill", "edit skill", "change skill"}),
		InputSchema: closedSetSchemaFor[updateSkillIn](map[string][]any{
			"surfaces[]": enumSurfaces,
		}),
	}, s.toolUpdateSkill)

	registerARTool(srv, &mcp.Tool{
		Name:        "registry_set_skill_enabled",
		Description: "Enable or disable a skill for the signed-in user (by slug). Disabling a System skill applies only to this user; the shared skill is never changed.",
		Meta:        lwmcp.NewToolMeta(lwmcp.TierA, lwmcp.ScopeUser, nil, []string{"enable skill", "disable skill", "turn off skill", "turn on skill"}),
	}, s.toolSetSkillEnabled)

	// WS-2a — curated multi-step WORKFLOWS (C3). A workflow is an ordered list of
	// tool steps the user runs as one named capability; authoring is propose→approve
	// (never a direct write), same HITL spine as skills.
	registerARTool(srv, &mcp.Tool{
		Name:        "registry_list_workflows",
		Description: "List the curated multi-step workflows visible to the signed-in user (System defaults + their own). Returns each workflow's slug + title + description — not the full step list. Use to see what workflows exist before proposing a new one or reading one in full.",
		Meta:        lwmcp.NewToolMeta(lwmcp.TierR, lwmcp.ScopeUser, nil, []string{"workflows", "list workflows", "my workflows", "what workflows", "recipes"}),
		InputSchema: closedSetSchemaFor[listWorkflowsIn](map[string][]any{
			"surface": enumSurfaces,
		}),
	}, s.toolListWorkflows)

	registerARTool(srv, &mcp.Tool{
		Name:        "registry_get_workflow",
		Description: "Get the full definition of one workflow the user can see, by slug — its inputs and ordered steps. Read-only.",
		Meta:        lwmcp.NewToolMeta(lwmcp.TierR, lwmcp.ScopeUser, nil, []string{"read workflow", "workflow steps", "get workflow", "show workflow"}),
	}, s.toolGetWorkflow)

	registerARTool(srv, &mcp.Tool{
		Name:        "registry_propose_workflow",
		Description: "PROPOSE a new curated multi-step workflow. Does NOT create or run it — it records a proposal the user must approve in the UI. Provide slug, title, a one-line description, and an ordered list of steps (each with a tool name and a gate: none | confirm | approval). Optionally declare inputs. By default it's saved as the user's own private workflow; pass book_id to share it with a book you can edit (book-tier). Use this to save a repeatable sequence of tool calls as a reusable workflow.",
		Meta:        lwmcp.NewToolMeta(lwmcp.TierA, lwmcp.ScopeUser, nil, []string{"save workflow", "propose workflow", "create workflow", "remember this as a workflow", "make a recipe"}),
		InputSchema: closedSetSchemaFor[proposeWorkflowIn](map[string][]any{
			"surfaces[]":   enumSurfaces,
			"steps[].gate": enumWorkflowGates,
		}),
	}, s.toolProposeWorkflow)

	registerARTool(srv, &mcp.Tool{
		Name:        "registry_update_workflow",
		Description: "PROPOSE an update to one of the user's OWN workflows (by slug). Does NOT apply immediately — the user approves the diff in the UI. Provide the slug and the new title/description/inputs/steps.",
		Meta:        lwmcp.NewToolMeta(lwmcp.TierA, lwmcp.ScopeUser, nil, []string{"update workflow", "edit workflow", "change workflow"}),
		InputSchema: closedSetSchemaFor[updateWorkflowIn](map[string][]any{
			"surfaces[]":   enumSurfaces,
			"steps[].gate": enumWorkflowGates,
		}),
	}, s.toolUpdateWorkflow)

	return lwmcp.NewStatelessHandler(srv, s.cfg.InternalServiceToken)
}

func registerARTool[In, Out any](srv *mcp.Server, t *mcp.Tool, h func(context.Context, *mcp.CallToolRequest, In) (*mcp.CallToolResult, Out, error)) {
	lwmcp.MustValidateToolMeta(t)
	lwmcp.RegisterTool(srv, t, h)
}

func arCallerID(ctx context.Context) (uuid.UUID, error) {
	uid, ok := lwmcp.UserIDFromCtx(ctx)
	if !ok {
		return uuid.Nil, errors.New("missing caller identity")
	}
	return uid, nil
}

// resolveVisibleSkillBySlug finds a skill (System ∪ own) by slug for the caller,
// preferring the user's own row when it shadows a System slug.
func (s *Server) resolveVisibleSkillBySlug(ctx context.Context, uid uuid.UUID, slug string) (id uuid.UUID, tier string, owner *uuid.UUID, found bool) {
	err := s.db.QueryRow(ctx,
		`SELECT skill_id, tier, owner_user_id FROM skills
		 WHERE slug = $1 AND (tier = 'system' OR (tier = 'user' AND owner_user_id = $2))
		 ORDER BY (tier = 'user') DESC LIMIT 1`, slug, uid).Scan(&id, &tier, &owner)
	if err != nil {
		return uuid.Nil, "", nil, false
	}
	return id, tier, owner, true
}

// ── Tier R ──────────────────────────────────────────────────────────────────

type listSkillsIn struct {
	Surface string `json:"surface,omitempty" jsonschema:"filter to skills advertised on this surface: chat | compose | translate | admin — omit this argument to see all surfaces; do not send an empty string"`
}
type skillMeta struct {
	Slug        string `json:"slug"`
	Description string `json:"description"`
	Tier        string `json:"tier"`
	Status      string `json:"status"`
}
type listSkillsOut struct {
	Skills []skillMeta `json:"skills"`
}

func (s *Server) toolListSkills(ctx context.Context, _ *mcp.CallToolRequest, in listSkillsIn) (*mcp.CallToolResult, listSkillsOut, error) {
	uid, err := arCallerID(ctx)
	if err != nil {
		return nil, listSkillsOut{}, err
	}
	rows, err := s.db.Query(ctx,
		`SELECT slug, description, tier, status, surfaces FROM skills
		 WHERE tier = 'system' OR (tier = 'user' AND owner_user_id = $1) ORDER BY slug`, uid)
	if err != nil {
		return nil, listSkillsOut{}, errors.New("failed to list skills")
	}
	defer rows.Close()
	out := listSkillsOut{Skills: []skillMeta{}}
	for rows.Next() {
		var m skillMeta
		var surfaces []string
		if err := rows.Scan(&m.Slug, &m.Description, &m.Tier, &m.Status, &surfaces); err != nil {
			continue
		}
		if in.Surface != "" && len(surfaces) > 0 && !contains(surfaces, in.Surface) {
			continue
		}
		out.Skills = append(out.Skills, m)
	}
	return nil, out, nil
}

type getSkillIn struct {
	Slug string `json:"slug" jsonschema:"the skill slug to read"`
}
type getSkillOut struct {
	Slug        string `json:"slug"`
	Description string `json:"description"`
	BodyMD      string `json:"body_md"`
	Tier        string `json:"tier"`
}

func (s *Server) toolGetSkill(ctx context.Context, _ *mcp.CallToolRequest, in getSkillIn) (*mcp.CallToolResult, getSkillOut, error) {
	uid, err := arCallerID(ctx)
	if err != nil {
		return nil, getSkillOut{}, err
	}
	if in.Slug == "" {
		return nil, getSkillOut{}, errors.New("slug is required")
	}
	var out getSkillOut
	err = s.db.QueryRow(ctx,
		`SELECT slug, description, body_md, tier FROM skills
		 WHERE slug = $1 AND (tier = 'system' OR (tier = 'user' AND owner_user_id = $2))
		 ORDER BY (tier = 'user') DESC LIMIT 1`, in.Slug, uid).Scan(&out.Slug, &out.Description, &out.BodyMD, &out.Tier)
	if err != nil {
		return nil, getSkillOut{}, errors.New("skill not found: " + in.Slug)
	}
	return nil, out, nil
}

// ── Tier A (propose→approve; never a direct write) ──────────────────────────

type proposeSkillIn struct {
	Slug        string   `json:"slug" jsonschema:"lowercase a-z0-9- slug, 2-64 chars"`
	Description string   `json:"description" jsonschema:"one-line description (required)"`
	BodyMD      string   `json:"body_md" jsonschema:"the SKILL.md markdown body (instructions)"`
	Surfaces    []string `json:"surfaces,omitempty" jsonschema:"surfaces where this applies (chat, compose, translate, admin)"`
	SessionID   string   `json:"session_id,omitempty" jsonschema:"the chat session this came from (optional)"`
}
type proposeSkillOut struct {
	ProposalID string `json:"proposal_id"`
	Status     string `json:"status"`
	Message    string `json:"message"`
}

func (s *Server) toolProposeSkill(ctx context.Context, _ *mcp.CallToolRequest, in proposeSkillIn) (*mcp.CallToolResult, proposeSkillOut, error) {
	uid, err := arCallerID(ctx)
	if err != nil {
		return nil, proposeSkillOut{}, err
	}
	skIn := &skillInput{Slug: in.Slug, Description: in.Description, BodyMD: in.BodyMD, Surfaces: in.Surfaces}
	p, msg := s.doProposeSkill(ctx, uid, "create", nil, skIn, in.SessionID, "")
	if msg != "" {
		return nil, proposeSkillOut{}, errors.New(msg)
	}
	return nil, proposeSkillOut{
		ProposalID: p.ProposalID.String(),
		Status:     "pending",
		Message:    "Proposed skill '" + in.Slug + "'. Awaiting the user's approval in the UI — nothing is saved until they approve.",
	}, nil
}

type updateSkillIn struct {
	Slug        string   `json:"slug" jsonschema:"the slug of the user's OWN skill to update"`
	Description string   `json:"description,omitempty" jsonschema:"new description"`
	BodyMD      string   `json:"body_md" jsonschema:"the new SKILL.md body"`
	Surfaces    []string `json:"surfaces,omitempty" jsonschema:"surfaces where this applies (chat, compose, translate, admin)"`
	SessionID   string   `json:"session_id,omitempty"`
}

func (s *Server) toolUpdateSkill(ctx context.Context, _ *mcp.CallToolRequest, in updateSkillIn) (*mcp.CallToolResult, proposeSkillOut, error) {
	uid, err := arCallerID(ctx)
	if err != nil {
		return nil, proposeSkillOut{}, err
	}
	id, tier, owner, found := s.resolveVisibleSkillBySlug(ctx, uid, in.Slug)
	if !found {
		return nil, proposeSkillOut{}, errors.New("skill not found: " + in.Slug)
	}
	if tier != "user" || owner == nil || *owner != uid {
		return nil, proposeSkillOut{}, errors.New("only your own skills can be updated (System skills are read-only — clone one instead)")
	}
	desc := in.Description
	if desc == "" {
		// keep existing description when omitted
		_ = s.db.QueryRow(ctx, `SELECT description FROM skills WHERE skill_id=$1`, id).Scan(&desc)
	}
	skIn := &skillInput{Slug: in.Slug, Description: desc, BodyMD: in.BodyMD, Surfaces: in.Surfaces}
	p, msg := s.doProposeSkill(ctx, uid, "update", &id, skIn, in.SessionID, "")
	if msg != "" {
		return nil, proposeSkillOut{}, errors.New(msg)
	}
	return nil, proposeSkillOut{ProposalID: p.ProposalID.String(), Status: "pending", Message: "Proposed an update to '" + in.Slug + "'. Awaiting the user's approval."}, nil
}

type setEnabledIn struct {
	Slug    string `json:"slug" jsonschema:"the skill slug to toggle"`
	Enabled bool   `json:"enabled" jsonschema:"true to enable, false to disable (for this user)"`
}
type setEnabledOut struct {
	Slug    string `json:"slug"`
	Enabled bool   `json:"enabled"`
}

func (s *Server) toolSetSkillEnabled(ctx context.Context, _ *mcp.CallToolRequest, in setEnabledIn) (*mcp.CallToolResult, setEnabledOut, error) {
	uid, err := arCallerID(ctx)
	if err != nil {
		return nil, setEnabledOut{}, err
	}
	id, _, _, found := s.resolveVisibleSkillBySlug(ctx, uid, in.Slug)
	if !found {
		return nil, setEnabledOut{}, errors.New("skill not found: " + in.Slug)
	}
	_, err = s.db.Exec(ctx,
		`INSERT INTO skill_enablement (skill_id, owner_user_id, enabled) VALUES ($1,$2,$3)
		 ON CONFLICT (skill_id, owner_user_id) DO UPDATE SET enabled = EXCLUDED.enabled, updated_at = now()`,
		id, uid, in.Enabled)
	if err != nil {
		return nil, setEnabledOut{}, errors.New("failed to set skill enablement")
	}
	s.bumpCatalogVersion(ctx)
	return nil, setEnabledOut{Slug: in.Slug, Enabled: in.Enabled}, nil
}

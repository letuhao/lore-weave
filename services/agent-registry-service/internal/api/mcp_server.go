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
		Description: "Get one skill the user can see, by slug — its metadata plus body_md. Read-only. NOTE: a SYSTEM-tier skill (glossary, knowledge, plan_forge, universal, admin) stores no body here; body_md is a marker saying chat-service's skill_registry serves it, so do not treat that sentence as the skill.",
		Meta:        lwmcp.NewToolMeta(lwmcp.TierR, lwmcp.ScopeUser, nil, []string{"read skill", "skill body", "get skill", "show skill", "body of the", "show me the body", "what does this skill do", "skill instructions"}),
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
		Meta:        lwmcp.NewToolMeta(lwmcp.TierA, lwmcp.ScopeUser, nil, []string{"update skill", "edit skill", "change skill", "change the skill description", "rename skill", "change the skill", "edit the skill", "change the description"}),
		InputSchema: closedSetSchemaFor[updateSkillIn](map[string][]any{
			"surfaces[]": enumSurfaces,
		}),
	}, s.toolUpdateSkill)

	registerARTool(srv, &mcp.Tool{
		Name:        "registry_set_skill_enabled",
		Description: "Enable or disable a skill for the signed-in user (by slug). Disabling a System skill applies only to this user; the shared skill is never changed.",
		Meta:        lwmcp.NewToolMeta(lwmcp.TierA, lwmcp.ScopeUser, nil, []string{"enable skill", "disable skill", "turn off skill", "turn on skill", "turn off the skill", "turn on the skill", "switch off skill", "stop using the skill", "turn off", "turn on"}),
	}, s.toolSetSkillEnabled)

	// WS-2a — curated multi-step WORKFLOWS (C3). A workflow is an ordered list of
	// tool steps the user runs as one named capability; authoring is propose→approve
	// (never a direct write), same HITL spine as skills.
	registerARTool(srv, &mcp.Tool{
		Name:        "registry_list_workflows",
		// 🔴 D-REGISTRY-LIST-WORKFLOWS-UNDER-DECLARES-ITS-PAYLOAD-TOO, OWNER 2026-08-28: correct
		// the field list fully and accept the measured cost — truth over score. The prior
		// wording claimed "slug + title + description"; workflowMeta returns FIVE fields (tier
		// and status too), and naming all five was measured to move a surface question from 5/5
		// to 3/5 (c-regwf7 vs c-regwf8/c-regwf6). That regression is a SEPARATE cause — the
		// routing appears keyed on description length/field-name overlap rather than meaning —
		// and is recorded, not silently absorbed by reverting the accuracy fix again.
		//
		// AND, OWNER 2026-08-28 (DQ-T39): renamed for PURPOSE alongside the accuracy fix, per the
		// owner's own rule that a duplicated-looking pair gets its descriptions changed rather
		// than one tool retired. This is the CATALOGUE half — chat-service's workflow_list (the
		// always-on consumer-local twin) is the RUNNER half, turn-scoped to what can actually be
		// loaded right now. Neither name changed; only what each says it is.
		Description: "List EVERY workflow the platform ships (System defaults + the signed-in user's own) — the full catalogue, regardless of what this book/surface can currently run. Pass `surface` to narrow to one (book | editor | studio); omit to see all. Returns slug, title, description, tier and status per workflow — not the full step list. For \"what can I run right now\", the chat surface's own workflow_list is scoped to the current turn instead.",
		Meta:        lwmcp.NewToolMeta(lwmcp.TierR, lwmcp.ScopeUser, nil, []string{"workflows", "list workflows", "my workflows", "what workflows", "recipes"}),
		InputSchema: closedSetSchemaFor[listWorkflowsIn](map[string][]any{
			"surface": enumWorkflowSurfaces,
		}),
	}, s.toolListWorkflows)

	registerARTool(srv, &mcp.Tool{
		Name:        "registry_get_workflow",
		Description: "Get the full definition of one workflow the user can see, by slug — its inputs and ordered steps. Read-only.",
		Meta:        lwmcp.NewToolMeta(lwmcp.TierR, lwmcp.ScopeUser, nil, []string{"read workflow", "workflow steps", "get workflow", "show workflow", "steps of the", "show me the steps", "what does this workflow do", "workflow recipe"}),
	}, s.toolGetWorkflow)

	registerARTool(srv, &mcp.Tool{
		Name:        "registry_propose_workflow",
		Description: "PROPOSE a new curated multi-step workflow. Does NOT create or run it — it records a proposal the user must approve in the UI. Provide slug, title, a one-line description, and an ordered list of steps (each with a tool name and a gate: none | confirm | approval). Optionally declare inputs. By default it's saved as the user's own private workflow; pass book_id to share it with a book you can edit (book-tier). Use this to save a repeatable sequence of tool calls as a reusable workflow.",
		Meta:        lwmcp.NewToolMeta(lwmcp.TierA, lwmcp.ScopeUser, nil, []string{"save workflow", "propose workflow", "create workflow", "remember this as a workflow", "make a recipe"}),
		InputSchema: closedSetSchemaFor[proposeWorkflowIn](map[string][]any{
			"surfaces[]":   enumWorkflowSurfaces,
			"steps[].gate": enumWorkflowGates,
		}),
	}, s.toolProposeWorkflow)

	registerARTool(srv, &mcp.Tool{
		Name:        "registry_update_workflow",
		Description: "PROPOSE an update to one of the user's OWN workflows (by slug). Does NOT apply immediately — the user approves the diff in the UI. Provide the slug and the new title/description/inputs/steps.",
		Meta:        lwmcp.NewToolMeta(lwmcp.TierA, lwmcp.ScopeUser, nil, []string{"update workflow", "edit workflow", "change workflow", "change the title of the", "rename workflow", "change the workflow", "edit the workflow"}),
		InputSchema: closedSetSchemaFor[updateWorkflowIn](map[string][]any{
			"surfaces[]":   enumWorkflowSurfaces,
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
	Slug        string `json:"slug" jsonschema:"the slug of the user's OWN skill to update"`
	Description string `json:"description,omitempty" jsonschema:"new description"`
	// omitempty (and therefore NOT required) so a description-only update works, which is
	// what this tool's own description promises: "the new description and/or body". It was
	// required, so an agent fixing a typo in the description had to resend the whole body —
	// and if it did not have the body to hand it would fail, or invent one. The keep-
	// existing-when-omitted pattern below is the one `description` already used.
	BodyMD    string   `json:"body_md,omitempty" jsonschema:"the new SKILL.md body — omit to keep the current one"`
	Surfaces  []string `json:"surfaces,omitempty" jsonschema:"surfaces where this applies (chat, compose, translate, admin)"`
	SessionID string   `json:"session_id,omitempty"`
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
	body := in.BodyMD
	if desc == "" || body == "" {
		// keep whichever of description / body was omitted — a partial update must not
		// blank the field it did not mention.
		var curDesc, curBody string
		_ = s.db.QueryRow(ctx, `SELECT description, body_md FROM skills WHERE skill_id=$1`, id).
			Scan(&curDesc, &curBody)
		if desc == "" {
			desc = curDesc
		}
		if body == "" {
			body = curBody
		}
	}
	skIn := &skillInput{Slug: in.Slug, Description: desc, BodyMD: body, Surfaces: in.Surfaces}
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

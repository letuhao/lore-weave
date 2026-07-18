package api

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"regexp"
	"strconv"
	"strings"
	"time"

	"github.com/google/uuid"
	"github.com/loreweave/grantclient"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

// workflows.go (WS-2a, agent-discoverability spec §4.4 / C3) — curated multi-step
// WORKFLOWS: an authored, ordered list of tool steps a user/agent runs as one named
// capability. Same shape as skills — 3-tier tenancy (System/user/book), propose→approve
// HITL, revisions — but the payload is the C3 `steps` object, executed by the
// chat-service step-runner (WS-2b), NOT a prompt body. Authoring here is
// structural-validation only; the runner enforces "tool ∈ catalog ∩ policy-allowed"
// at run time (it owns the catalog + policy) and fails a bad step gracefully per C3.

// enumWorkflowGates — the closed set of per-step HITL gates (C3). A weak model must
// see a real schema enum, not prose, or it guesses (the FE-tools LOCKED rule).
var validWorkflowGates = []string{"none", "confirm", "approval"}

var enumWorkflowGates = func() []any {
	out := make([]any, len(validWorkflowGates))
	for i, v := range validWorkflowGates {
		out[i] = v
	}
	return out
}()

// ── the C3 payload types (author-facing MCP shape) ──────────────────────────

type workflowStepIn struct {
	ID        string            `json:"id" jsonschema:"unique kebab-case step id"`
	Tool      string            `json:"tool" jsonschema:"exact tool name to call (must be a discoverable, policy-allowed tool)"`
	Gate      string            `json:"gate" jsonschema:"per-step HITL gate: none | confirm | approval"`
	When      string            `json:"when,omitempty" jsonschema:"optional predicate over prior step results / inputs (evaluated by the runner)"`
	Repeat    string            `json:"repeat,omitempty" jsonschema:"none | per_item:<inputs key> — fan the step over a list input"`
	InputsMap map[string]string `json:"inputs_map,omitempty" jsonschema:"map of tool arg -> reference to a workflow input or a prior step output"`
	// AsyncJob — set true when this step's tool STARTS a background job (queued, not
	// done on return). AUTHORITATIVE when present: the runner's name-heuristic is only a
	// fallback for steps that omit it, so a new async tool the heuristic doesn't know is
	// still honored when the author marks it. Pointer so "unset" is distinct from false.
	AsyncJob *bool `json:"async_job,omitempty" jsonschema:"true if this step starts a background job (queued, not done on return)"`
	// DoneWhen (Track C Phase 2 — the rail driver) — the OBSERVABLE artifact that proves
	// this step actually landed, as a predicate over the book's state:
	// "<key> > <n>" with key in {categories, cast, connections, plan, chapters, prose}.
	//
	// This is what lets the consumer answer "where is the user?" from the BOOK instead of
	// from the model's memory — and, critically, refuse to be fooled by a tool that
	// returned "success" and wrote nothing (the flagship's signature failure: the cast
	// landed 0/0/0/0 across four runs while the calls all looked fine). A step with no
	// done_when falls back to the session's real tool-call log.
	//
	// NOTE this field MUST exist on the struct: `steps` round-trips through
	// json.Unmarshal into []workflowStepIn, so an authored key that is not declared here
	// is SILENTLY DROPPED on the way out and the consumer never sees it.
	DoneWhen string `json:"done_when,omitempty" jsonschema:"artifact predicate proving the step landed: '<key> <op> <n>', key in categories|cast|connections|plan|chapters|prose|suggestions, op in > >= < <= == (use < for a DRAIN step, e.g. 'suggestions < 1')"`
}

// validDoneWhen — the closed grammar for a step's done_when. Parsed, never evaluated.
// A free-string predicate would be a setting that reads back as effective and does
// nothing (the write-only-behavior bug), so it is rejected at the write.
//
// Keys + operators MUST stay in lockstep with the chat-service consumer
// (rail_progress.py: BOOK_STATE_KEYS + _PREDICATE_RE). `suggestions` and the drain operators
// (< <= ==) were added for the entity-triage rail, whose completion is a pile shrinking to 0
// rather than an artifact appearing — a BUILD-only grammar could not express "done when empty".
var doneWhenRe = regexp.MustCompile(`^\s*(categories|cast|connections|plan|chapters|prose|suggestions)\s*(>=|<=|==|>|<)\s*\d+\s*$`)

type proposeWorkflowIn struct {
	Slug        string            `json:"slug" jsonschema:"lowercase a-z0-9- slug, 2-64 chars (unique per tier)"`
	Title       string            `json:"title" jsonschema:"human title (one line)"`
	Description string            `json:"description" jsonschema:"one-line description shown in the L1 menu (required)"`
	Surfaces    []string          `json:"surfaces,omitempty" jsonschema:"surfaces where this applies (chat, compose, translate, admin)"`
	Inputs      map[string]string `json:"inputs,omitempty" jsonschema:"declared inputs: name -> 'required' | 'optional'"`
	Steps       []workflowStepIn  `json:"steps" jsonschema:"ordered tool steps (C3) — at least one"`
	NotesMD     string            `json:"notes_md,omitempty" jsonschema:"prose the agent reads (gotchas, plain-language framing) — NOT executed"`
	// BookID — OPTIONAL. Omit ⇒ a personal (user-tier) workflow. Set ⇒ a book-tier
	// workflow shared with everyone who has the book — this is a CROSS-TENANT write, so
	// it is gated on the caller holding an ≥edit grant on an ACTIVE book (checked in
	// toolProposeWorkflow AND re-checked at approve). A caller without the grant gets a
	// plain "book not found" (anti-oracle).
	BookID    string `json:"book_id,omitempty" jsonschema:"optional — set to share this workflow with a book you can edit (book-tier); omit for a personal workflow"`
	SessionID string `json:"session_id,omitempty" jsonschema:"the chat session this came from (optional)"`
}

type updateWorkflowIn struct {
	Slug        string            `json:"slug" jsonschema:"the slug of the workflow to update (your own, or a book-tier one you can edit)"`
	Title       string            `json:"title,omitempty" jsonschema:"new title"`
	Description string            `json:"description,omitempty" jsonschema:"new description"`
	Surfaces    []string          `json:"surfaces,omitempty" jsonschema:"surfaces where this applies (chat, compose, translate, admin)"`
	Inputs      map[string]string `json:"inputs,omitempty" jsonschema:"declared inputs: name -> 'required' | 'optional'"`
	Steps       []workflowStepIn  `json:"steps" jsonschema:"ordered tool steps (C3) — at least one"`
	NotesMD     string            `json:"notes_md,omitempty"`
	BookID      string            `json:"book_id,omitempty" jsonschema:"set to update a BOOK-tier workflow of that book (needs ≥edit grant); omit to update your own personal workflow"`
	SessionID   string            `json:"session_id,omitempty"`
}

type proposeWorkflowOut struct {
	ProposalID string `json:"proposal_id"`
	Status     string `json:"status"`
	Message    string `json:"message"`
	// Warnings — CD4. Non-empty when the workflow references a tool that has not passed
	// the liveness gates. The proposal is still admitted (the tool may simply have no
	// probe yet); a PROVEN-BROKEN tool is rejected outright by validateWorkflow instead.
	// Omitted when clean, so the existing response shape is unchanged for a proven set.
	Warnings []string `json:"warnings,omitempty"`
}

// workflowInput — the normalized, validated internal shape (post-MCP / REST).
type workflowInput struct {
	Slug        string
	Title       string
	Description string
	Surfaces    []string
	Inputs      map[string]string
	Steps       []workflowStepIn
	NotesMD     string
	Tier        string
	BookID      *uuid.UUID
}

// ── validation (C3 structural — the runner does the catalog/policy check) ────

// validateWorkflow enforces the C3 shape: valid slug/surfaces, an input map of
// required|optional, and ≥1 step each with a unique kebab id, a non-empty tool, a
// gate in the closed set, and a well-formed repeat clause referencing a declared
// input. It deliberately does NOT check tool-catalog membership — the step-runner
// (chat-service, WS-2b) owns the catalog + policy and fails an unknown/forbidden
// tool gracefully at run time (a workflow authored before a tool exists stays valid).
func validateWorkflow(in *workflowInput) (string, bool) {
	if !skillSlugRe.MatchString(in.Slug) {
		return "slug must be lowercase [a-z0-9-], 2-64 chars", false
	}
	if strings.TrimSpace(in.Description) == "" {
		return "description is required", false
	}
	if bad := invalidSurface(in.Surfaces); bad != "" {
		return "invalid surface '" + bad + "' — must be one of: chat, compose, translate, admin", false
	}
	for name, req := range in.Inputs {
		if strings.TrimSpace(name) == "" {
			return "input names must be non-empty", false
		}
		if req != "required" && req != "optional" {
			return "input '" + name + "' must be 'required' or 'optional' (got '" + req + "')", false
		}
	}
	if len(in.Steps) == 0 {
		return "a workflow needs at least one step", false
	}
	if len(in.Steps) > maxWorkflowSteps {
		return "too many steps (max " + strconv.Itoa(maxWorkflowSteps) + ")", false
	}
	seen := map[string]bool{}
	for i, st := range in.Steps {
		where := "step " + strconv.Itoa(i+1)
		if !skillSlugRe.MatchString(st.ID) {
			return where + ": id must be lowercase [a-z0-9-], 2-64 chars", false
		}
		if seen[st.ID] {
			return where + ": duplicate step id '" + st.ID + "'", false
		}
		seen[st.ID] = true
		if strings.TrimSpace(st.Tool) == "" {
			return where + " ('" + st.ID + "'): tool is required", false
		}
		// CD4 ship gate — reject a step whose tool is PROVEN BROKEN: the liveness matrix
		// called it correctly, with valid args, and it failed. Authoring a workflow around
		// such a tool guarantees a broken run. An *unproven* tool only warns (see
		// livenessWarnings). A tool the model merely fails to SELECT is fine here, because
		// a workflow step names its tool directly — no selection is involved. See liveness.go.
		if toolBlocked(st.Tool) {
			return where + " ('" + st.ID + "'): tool '" + st.Tool + "' is known-broken — it " +
				"fails when called with valid arguments (liveness gate G3/capability). " +
				"Fix the tool, or use a different one.", false
		}
		if st.Gate != "" && !contains(validWorkflowGates, st.Gate) {
			return where + " ('" + st.ID + "'): gate must be none | confirm | approval", false
		}
		if msg, ok := validateRepeat(st.Repeat, in.Inputs); !ok {
			return where + " ('" + st.ID + "'): " + msg, false
		}
		// Track C Phase 2 — done_when is a CLOSED grammar, enforced here. An unparseable
		// predicate cannot mark a step done, so accepting one would ship a step that can
		// never be recognised as complete: the agent would redo it forever, and the author
		// would get a cheerful 200 telling them it was fine.
		if strings.TrimSpace(st.DoneWhen) != "" && !doneWhenRe.MatchString(st.DoneWhen) {
			return where + " ('" + st.ID + "'): done_when must be '<key> > <n>' with key in " +
				"categories|cast|connections|plan|chapters|prose (got '" + st.DoneWhen + "')", false
		}
	}
	return "", true
}

// validateRepeat accepts "", "none", or "per_item:<key>" where <key> is a declared input.
func validateRepeat(repeat string, inputs map[string]string) (string, bool) {
	if repeat == "" || repeat == "none" {
		return "", true
	}
	if !strings.HasPrefix(repeat, "per_item:") {
		return "repeat must be 'none' or 'per_item:<inputs key>'", false
	}
	key := strings.TrimPrefix(repeat, "per_item:")
	if key == "" {
		return "repeat 'per_item:' needs an inputs key", false
	}
	if _, ok := inputs[key]; !ok {
		return "repeat 'per_item:" + key + "' references an undeclared input", false
	}
	return "", true
}

const maxWorkflowSteps = 40

// normalizeWorkflowSteps drops zero-valued optional fields so stored JSON stays lean
// and the runner reads a canonical shape.
func stepsToJSON(steps []workflowStepIn) []byte {
	if steps == nil {
		steps = []workflowStepIn{}
	}
	for i := range steps {
		if steps[i].Gate == "" {
			steps[i].Gate = "none"
		}
	}
	b, _ := json.Marshal(steps)
	return b
}

func inputsToJSON(m map[string]string) []byte {
	if m == nil {
		m = map[string]string{}
	}
	b, _ := json.Marshal(m)
	return b
}

// ── MCP tools (registered in mcpHandler) ────────────────────────────────────

type listWorkflowsIn struct {
	Surface string `json:"surface,omitempty" jsonschema:"filter to workflows advertised on this surface: chat | compose | translate | admin — omit to see all; do not send an empty string"`
}
type workflowMeta struct {
	Slug        string `json:"slug"`
	Title       string `json:"title"`
	Description string `json:"description"`
	Tier        string `json:"tier"`
	Status      string `json:"status"`
}
type listWorkflowsOut struct {
	Workflows []workflowMeta `json:"workflows"`
}

func (s *Server) toolListWorkflows(ctx context.Context, _ *mcp.CallToolRequest, in listWorkflowsIn) (*mcp.CallToolResult, listWorkflowsOut, error) {
	uid, err := arCallerID(ctx)
	if err != nil {
		return nil, listWorkflowsOut{}, err
	}
	rows, err := s.db.Query(ctx,
		`SELECT slug, title, description, tier, status, surfaces FROM workflows
		 WHERE status = 'published' AND (tier = 'system' OR (tier = 'user' AND owner_user_id = $1)) ORDER BY slug`, uid)
	if err != nil {
		return nil, listWorkflowsOut{}, errors.New("failed to list workflows")
	}
	defer rows.Close()
	out := listWorkflowsOut{Workflows: []workflowMeta{}}
	for rows.Next() {
		var m workflowMeta
		var surfaces []string
		if err := rows.Scan(&m.Slug, &m.Title, &m.Description, &m.Tier, &m.Status, &surfaces); err != nil {
			continue
		}
		if in.Surface != "" && len(surfaces) > 0 && !contains(surfaces, in.Surface) {
			continue
		}
		out.Workflows = append(out.Workflows, m)
	}
	return nil, out, nil
}

type getWorkflowIn struct {
	Slug   string `json:"slug" jsonschema:"the workflow slug to read"`
	BookID string `json:"book_id,omitempty" jsonschema:"set to read a BOOK-tier workflow of that book (needs ≥view grant); omit for System/your own"`
}
type getWorkflowOut struct {
	Slug        string            `json:"slug"`
	Title       string            `json:"title"`
	Description string            `json:"description"`
	Tier        string            `json:"tier"`
	Surfaces    []string          `json:"surfaces"`
	Inputs      map[string]string `json:"inputs"`
	Steps       []workflowStepIn  `json:"steps"`
	NotesMD     string            `json:"notes_md"`
}

func (s *Server) toolGetWorkflow(ctx context.Context, _ *mcp.CallToolRequest, in getWorkflowIn) (*mcp.CallToolResult, getWorkflowOut, error) {
	uid, err := arCallerID(ctx)
	if err != nil {
		return nil, getWorkflowOut{}, err
	}
	if in.Slug == "" {
		return nil, getWorkflowOut{}, errors.New("slug is required")
	}
	if in.BookID != "" {
		// Book-tier read — gate on an ≥view grant (anti-oracle "not found" without it).
		bid, perr := uuid.Parse(in.BookID)
		if perr != nil {
			return nil, getWorkflowOut{}, errors.New("invalid book_id")
		}
		if ok, _ := s.bookGrantOK(ctx, bid, uid, grantclient.GrantView); !ok {
			return nil, getWorkflowOut{}, errors.New("workflow not found: " + in.Slug)
		}
		out, err := s.loadBookWorkflow(ctx, bid, in.Slug)
		if err != nil {
			return nil, getWorkflowOut{}, err
		}
		return nil, out, nil
	}
	out, err := s.loadVisibleWorkflow(ctx, uid, in.Slug)
	if err != nil {
		return nil, getWorkflowOut{}, err
	}
	return nil, out, nil
}

// loadBookWorkflow reads a book-tier workflow by (book_id, slug). Caller MUST have
// grant-checked the book first (this is a raw read).
func (s *Server) loadBookWorkflow(ctx context.Context, bookID uuid.UUID, slug string) (getWorkflowOut, error) {
	var out getWorkflowOut
	var inputsJSON, stepsJSON []byte
	err := s.db.QueryRow(ctx,
		`SELECT slug, title, description, tier, surfaces, inputs, steps, notes_md FROM workflows
		 WHERE tier='book' AND book_id=$1 AND slug=$2 LIMIT 1`, bookID, slug).
		Scan(&out.Slug, &out.Title, &out.Description, &out.Tier, &out.Surfaces, &inputsJSON, &stepsJSON, &out.NotesMD)
	if err != nil {
		return getWorkflowOut{}, errors.New("workflow not found: " + slug)
	}
	_ = json.Unmarshal(inputsJSON, &out.Inputs)
	_ = json.Unmarshal(stepsJSON, &out.Steps)
	if out.Inputs == nil {
		out.Inputs = map[string]string{}
	}
	if out.Steps == nil {
		out.Steps = []workflowStepIn{}
	}
	return out, nil
}

// loadVisibleWorkflow resolves a workflow (System ∪ own) by slug, preferring the
// user's own row when it shadows a System slug. Shared by the MCP get + REST reader.
func (s *Server) loadVisibleWorkflow(ctx context.Context, uid uuid.UUID, slug string) (getWorkflowOut, error) {
	var out getWorkflowOut
	var inputsJSON, stepsJSON []byte
	err := s.db.QueryRow(ctx,
		`SELECT slug, title, description, tier, surfaces, inputs, steps, notes_md FROM workflows
		 WHERE slug = $1 AND (tier = 'system' OR (tier = 'user' AND owner_user_id = $2))
		 ORDER BY (tier = 'user') DESC LIMIT 1`, slug, uid).
		Scan(&out.Slug, &out.Title, &out.Description, &out.Tier, &out.Surfaces, &inputsJSON, &stepsJSON, &out.NotesMD)
	if err != nil {
		return getWorkflowOut{}, errors.New("workflow not found: " + slug)
	}
	_ = json.Unmarshal(inputsJSON, &out.Inputs)
	_ = json.Unmarshal(stepsJSON, &out.Steps)
	if out.Inputs == nil {
		out.Inputs = map[string]string{}
	}
	if out.Steps == nil {
		out.Steps = []workflowStepIn{}
	}
	return out, nil
}

func (s *Server) toolProposeWorkflow(ctx context.Context, _ *mcp.CallToolRequest, in proposeWorkflowIn) (*mcp.CallToolResult, proposeWorkflowOut, error) {
	uid, err := arCallerID(ctx)
	if err != nil {
		return nil, proposeWorkflowOut{}, err
	}
	wfIn, msg := in.normalize()
	if msg != "" {
		return nil, proposeWorkflowOut{}, errors.New(msg)
	}
	// Book-tier is cross-tenant — gate on an ≥edit grant on an ACTIVE book BEFORE storing
	// the proposal (fail-closed; anti-oracle "book not found" when the caller has no grant).
	if wfIn.Tier == "book" {
		if ok, why := s.bookGrantOK(ctx, *wfIn.BookID, uid, grantclient.GrantEdit); !ok {
			return nil, proposeWorkflowOut{}, errors.New(why)
		}
	}
	p, msg := s.doProposeWorkflow(ctx, uid, "create", nil, wfIn, in.SessionID, "")
	if msg != "" {
		return nil, proposeWorkflowOut{}, errors.New(msg)
	}
	return nil, proposeWorkflowOut{
		ProposalID: p.ProposalID.String(),
		Status:     "pending",
		Warnings:   livenessWarnings(wfIn.Steps), // CD4: loud, but non-blocking
		Message:    "Proposed workflow '" + in.Slug + "'. Nothing runs or is saved until the user approves it. Tell them to open the \"Workflow Proposals\" panel (⌘/Ctrl-K → \"Workflow Proposals\") to review its steps and approve or reject — or open it for them with ui_open_studio_panel(panel_id=\"workflow-proposals\").",
	}, nil
}

func (s *Server) toolUpdateWorkflow(ctx context.Context, _ *mcp.CallToolRequest, in updateWorkflowIn) (*mcp.CallToolResult, proposeWorkflowOut, error) {
	uid, err := arCallerID(ctx)
	if err != nil {
		return nil, proposeWorkflowOut{}, err
	}
	var id uuid.UUID
	if in.BookID != "" {
		// Book-tier update — resolve within the named book, then gate on an ≥edit grant.
		bid, perr := uuid.Parse(in.BookID)
		if perr != nil {
			return nil, proposeWorkflowOut{}, errors.New("invalid book_id")
		}
		if ok, why := s.bookGrantOK(ctx, bid, uid, grantclient.GrantEdit); !ok {
			return nil, proposeWorkflowOut{}, errors.New(why)
		}
		if err := s.db.QueryRow(ctx,
			`SELECT workflow_id FROM workflows WHERE tier='book' AND book_id=$1 AND slug=$2`, bid, in.Slug).Scan(&id); err != nil {
			return nil, proposeWorkflowOut{}, errors.New("workflow not found: " + in.Slug)
		}
	} else {
		wid, tier, owner, found := s.resolveVisibleWorkflowBySlug(ctx, uid, in.Slug)
		if !found {
			return nil, proposeWorkflowOut{}, errors.New("workflow not found: " + in.Slug)
		}
		if tier != "user" || owner == nil || *owner != uid {
			return nil, proposeWorkflowOut{}, errors.New("only your own workflows can be updated (System workflows are read-only — clone one instead)")
		}
		id = wid
	}
	pIn := proposeWorkflowIn{
		Slug: in.Slug, Title: in.Title, Description: in.Description,
		Surfaces: in.Surfaces, Inputs: in.Inputs, Steps: in.Steps, NotesMD: in.NotesMD,
		BookID: in.BookID,
	}
	if pIn.Description == "" {
		_ = s.db.QueryRow(ctx, `SELECT description FROM workflows WHERE workflow_id=$1`, id).Scan(&pIn.Description)
	}
	wfIn, msg := pIn.normalize()
	if msg != "" {
		return nil, proposeWorkflowOut{}, errors.New(msg)
	}
	p, msg := s.doProposeWorkflow(ctx, uid, "update", &id, wfIn, in.SessionID, "")
	if msg != "" {
		return nil, proposeWorkflowOut{}, errors.New(msg)
	}
	return nil, proposeWorkflowOut{
		ProposalID: p.ProposalID.String(),
		Status:     "pending",
		Warnings:   livenessWarnings(wfIn.Steps), // CD4: loud, but non-blocking
		Message:    "Proposed an update to '" + in.Slug + "'. The change won't apply until the user approves it in the \"Workflow Proposals\" panel — tell them to open it (⌘/Ctrl-K → \"Workflow Proposals\") to review the changed steps, or open it for them with ui_open_studio_panel(panel_id=\"workflow-proposals\").",
	}, nil
}

// normalize validates + converts the MCP input into the internal workflowInput. A
// book_id promotes the tier to book (STRUCTURAL only — the cross-tenant GRANT check is
// done by the caller, toolProposeWorkflow, which has the ctx to resolve it).
func (in *proposeWorkflowIn) normalize() (*workflowInput, string) {
	title := in.Title
	if strings.TrimSpace(title) == "" {
		title = in.Slug
	}
	wfIn := &workflowInput{
		Slug: in.Slug, Title: title, Description: in.Description,
		Surfaces: in.Surfaces, Inputs: in.Inputs, Steps: in.Steps, NotesMD: in.NotesMD,
		Tier: "user",
	}
	if in.BookID != "" {
		bid, err := uuid.Parse(in.BookID)
		if err != nil {
			return nil, "invalid book_id"
		}
		wfIn.Tier = "book"
		wfIn.BookID = &bid
	}
	if msg, ok := validateWorkflow(wfIn); !ok {
		return nil, msg
	}
	return wfIn, ""
}

// bookGrantOK — ctx-based book grant check for the MCP path (no HTTP w/r, unlike
// requireBookGrant). Fail-closed: no grant client OR resolve error OR insufficient
// level OR inactive book ⇒ (false, anti-oracle reason). `need` is GrantView for reads,
// GrantEdit for writes. Mirrors requireBookGrant's decisions exactly.
func (s *Server) bookGrantOK(ctx context.Context, bookID, uid uuid.UUID, need grantclient.GrantLevel) (bool, string) {
	if s.grants == nil {
		return false, "book-scoped workflows aren't available here yet (grant wiring not configured)"
	}
	if bookID == uuid.Nil {
		return false, "book_id required for a book-tier workflow"
	}
	acc, err := s.grants.ResolveAccess(ctx, bookID, uid)
	if err != nil {
		return false, "book access authority unavailable — try again shortly"
	}
	if !acc.Level.AtLeast(need) {
		return false, "book not found" // anti-oracle: no grant is indistinguishable from absent
	}
	if !acc.Active() {
		return false, "book is not active (trashed or pending purge)"
	}
	return true, ""
}

// resolveVisibleWorkflowBySlug finds a workflow (System ∪ own) by slug for the caller.
func (s *Server) resolveVisibleWorkflowBySlug(ctx context.Context, uid uuid.UUID, slug string) (id uuid.UUID, tier string, owner *uuid.UUID, found bool) {
	err := s.db.QueryRow(ctx,
		`SELECT workflow_id, tier, owner_user_id FROM workflows
		 WHERE slug = $1 AND (tier = 'system' OR (tier = 'user' AND owner_user_id = $2))
		 ORDER BY (tier = 'user') DESC LIMIT 1`, slug, uid).Scan(&id, &tier, &owner)
	if err != nil {
		return uuid.Nil, "", nil, false
	}
	return id, tier, owner, true
}

// ── HITL proposal store + confirm routes (mirrors proposals.go for skills) ───

type workflowProposalRow struct {
	ProposalID       uuid.UUID       `json:"proposal_id"`
	OwnerUserID      uuid.UUID       `json:"owner_user_id"`
	BookID           *uuid.UUID      `json:"book_id,omitempty"`
	Action           string          `json:"action"`
	TargetWorkflowID *uuid.UUID      `json:"target_workflow_id,omitempty"`
	Slug             string          `json:"slug"`
	Title            string          `json:"title"`
	Description      string          `json:"description"`
	Surfaces         []string        `json:"surfaces"`
	Inputs           json.RawMessage `json:"inputs"`
	Steps            json.RawMessage `json:"steps"`
	NotesMD          string          `json:"notes_md"`
	Status           string          `json:"status"`
	RejectReason     string          `json:"reject_reason"`
	SessionID        string          `json:"from_session_id"`
	SessionLabel     string          `json:"from_session_label"`
	ConfirmToken     string          `json:"confirm_token,omitempty"`
	CreatedAt        time.Time       `json:"created_at"`
	ExpiresAt        time.Time       `json:"expires_at"`
}

const workflowProposalCols = `proposal_id, owner_user_id, book_id, action, target_workflow_id, slug, title,
	description, surfaces, inputs, steps, notes_md, status, reject_reason, from_session_id, from_session_label, created_at, expires_at`

func scanWorkflowProposal(row interface{ Scan(...any) error }, p *workflowProposalRow) error {
	return row.Scan(&p.ProposalID, &p.OwnerUserID, &p.BookID, &p.Action, &p.TargetWorkflowID, &p.Slug, &p.Title,
		&p.Description, &p.Surfaces, &p.Inputs, &p.Steps, &p.NotesMD, &p.Status, &p.RejectReason,
		&p.SessionID, &p.SessionLabel, &p.CreatedAt, &p.ExpiresAt)
}

func (s *Server) doProposeWorkflow(ctx context.Context, uid uuid.UUID, action string, target *uuid.UUID, in *workflowInput, sessionID, sessionLabel string) (*workflowProposalRow, string) {
	surfaces := in.Surfaces
	if surfaces == nil {
		surfaces = []string{}
	}
	token := uuid.NewString()
	var p workflowProposalRow
	err := scanWorkflowProposal(s.db.QueryRow(ctx,
		`INSERT INTO workflow_proposals (owner_user_id, book_id, action, target_workflow_id, slug, title, description, surfaces, inputs, steps, notes_md, confirm_token, from_session_id, from_session_label)
		 VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14) RETURNING `+workflowProposalCols,
		uid, in.BookID, action, target, in.Slug, in.Title, in.Description, surfaces,
		string(inputsToJSON(in.Inputs)), string(stepsToJSON(in.Steps)), in.NotesMD, token, sessionID, sessionLabel), &p)
	if err != nil {
		return nil, "could not store workflow proposal"
	}
	s.audit(ctx, uid, "agent", "workflow_proposal", "propose", &p.ProposalID, in.Slug, "user", map[string]any{"action": action})
	return &p, ""
}

func (s *Server) listWorkflowProposals(w http.ResponseWriter, r *http.Request) {
	uid, ok := s.requireUser(w, r)
	if !ok {
		return
	}
	q := r.URL.Query()
	limit := clampLimit(q.Get("limit"))
	offset := atoiDefault(q.Get("offset"), 0)
	if offset < 0 {
		offset = 0
	}
	where := []string{"owner_user_id = $1"}
	args := []any{uid}
	if v := q.Get("status"); v == "pending" || v == "approved" || v == "rejected" || v == "expired" {
		args = append(args, v)
		where = append(where, "status = $"+strconv.Itoa(len(args)))
	}
	_, _ = s.db.Exec(r.Context(), `UPDATE workflow_proposals SET status='expired', updated_at=now() WHERE owner_user_id=$1 AND status='pending' AND expires_at < now()`, uid)
	whereSQL := strings.Join(where, " AND ")
	total := s.queryInt(r.Context(), `SELECT COUNT(*) FROM workflow_proposals WHERE `+whereSQL, args...)
	args = append(args, limit, offset)
	rows, err := s.db.Query(r.Context(),
		`SELECT `+workflowProposalCols+` FROM workflow_proposals WHERE `+whereSQL+` ORDER BY created_at DESC`+
			` LIMIT $`+strconv.Itoa(len(args)-1)+` OFFSET $`+strconv.Itoa(len(args)), args...)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "could not list workflow proposals")
		return
	}
	defer rows.Close()
	items := []workflowProposalRow{}
	for rows.Next() {
		var p workflowProposalRow
		if err := scanWorkflowProposal(rows, &p); err != nil {
			continue
		}
		p.ConfirmToken = ""
		items = append(items, p)
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items, "total": total, "limit": limit, "offset": offset})
}

func (s *Server) getWorkflowProposal(w http.ResponseWriter, r *http.Request) {
	uid, ok := s.requireUser(w, r)
	if !ok {
		return
	}
	pid, ok := parseUUIDParam(w, r, "proposal_id")
	if !ok {
		return
	}
	var p workflowProposalRow
	err := scanWorkflowProposal(s.db.QueryRow(r.Context(),
		`SELECT `+workflowProposalCols+` FROM workflow_proposals WHERE proposal_id = $1 AND owner_user_id = $2`, pid, uid), &p)
	if err != nil {
		writeError(w, http.StatusNotFound, "NOT_FOUND", "proposal not found")
		return
	}
	p.ConfirmToken = ""
	writeJSON(w, http.StatusOK, p)
}

// approveWorkflowProposal (JWT owner) — the human accepts; creates/updates the workflow
// in the user's (or book's) tier + snapshots a revision. Mirrors approveProposal.
func (s *Server) approveWorkflowProposal(w http.ResponseWriter, r *http.Request) {
	uid, ok := s.requireUser(w, r)
	if !ok {
		return
	}
	pid, ok := parseUUIDParam(w, r, "proposal_id")
	if !ok {
		return
	}
	var p workflowProposalRow
	err := scanWorkflowProposal(s.db.QueryRow(r.Context(),
		`SELECT `+workflowProposalCols+` FROM workflow_proposals WHERE proposal_id = $1 AND owner_user_id = $2`, pid, uid), &p)
	if err != nil {
		writeError(w, http.StatusNotFound, "NOT_FOUND", "proposal not found")
		return
	}
	if p.Status != "pending" {
		writeError(w, http.StatusConflict, "NOT_PENDING", "proposal is "+p.Status)
		return
	}
	if p.ExpiresAt.Before(time.Now()) {
		_, _ = s.db.Exec(r.Context(), `UPDATE workflow_proposals SET status='expired', updated_at=now() WHERE proposal_id=$1`, pid)
		writeError(w, http.StatusConflict, "proposal_expired", "proposal expired")
		return
	}
	surfaces := p.Surfaces
	if surfaces == nil {
		surfaces = []string{}
	}
	// Book-tier is cross-tenant: RE-verify the ≥edit grant at approve time — a grant can
	// be revoked (or the book trashed) between propose and approve. requireBookGrant
	// writes its own 404/503 response, so just return on failure.
	if p.BookID != nil {
		if !s.requireBookGrant(w, r, *p.BookID, uid) {
			return
		}
	}
	if p.Action == "update" && p.TargetWorkflowID != nil {
		var owner *uuid.UUID
		var tier string
		if err := s.db.QueryRow(r.Context(), `SELECT tier, owner_user_id FROM workflows WHERE workflow_id=$1`, *p.TargetWorkflowID).Scan(&tier, &owner); err != nil {
			writeError(w, http.StatusConflict, "TARGET_GONE", "target workflow not writable")
			return
		}
		switch tier {
		case "system":
			if _, ok := s.requireAdminScope(w, r, scopeAdminWrite); !ok {
				return
			}
		case "book":
			// authorized by the p.BookID grant re-check above (book-tier rows have no
			// single owner — any ≥edit grantee may update).
		default: // user
			if owner == nil || *owner != uid {
				writeError(w, http.StatusConflict, "TARGET_GONE", "target workflow not writable")
				return
			}
		}
		s.snapshotWorkflowRevision(r.Context(), *p.TargetWorkflowID)
		if _, err := s.db.Exec(r.Context(),
			`UPDATE workflows SET title=$1, description=$2, surfaces=$3, inputs=$4, steps=$5, notes_md=$6, updated_at=now() WHERE workflow_id=$7`,
			p.Title, p.Description, surfaces, string(p.Inputs), string(p.Steps), p.NotesMD, *p.TargetWorkflowID); err != nil {
			writeError(w, http.StatusInternalServerError, "DB_ERROR", "could not apply update")
			return
		}
		s.audit(r.Context(), uid, "user", "workflow", "update", p.TargetWorkflowID, p.Slug, "user", map[string]any{"via": "proposal"})
	} else {
		var newID uuid.UUID
		if err := s.db.QueryRow(r.Context(),
			`INSERT INTO workflows (tier, owner_user_id, book_id, slug, title, description, surfaces, inputs, steps, notes_md, status, source)
			 VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,'published','agent') RETURNING workflow_id`,
			tierFor(p.BookID), uid, p.BookID, p.Slug, p.Title, p.Description, surfaces, string(p.Inputs), string(p.Steps), p.NotesMD).Scan(&newID); err != nil {
			if isUniqueViolation(err) {
				writeError(w, http.StatusConflict, "DUPLICATE", "a workflow with this slug already exists")
				return
			}
			writeError(w, http.StatusInternalServerError, "DB_ERROR", "could not create workflow")
			return
		}
		s.audit(r.Context(), uid, "user", "workflow", "create", &newID, p.Slug, "user", map[string]any{"via": "proposal"})
	}
	_, _ = s.db.Exec(r.Context(), `UPDATE workflow_proposals SET status='approved', updated_at=now() WHERE proposal_id=$1`, pid)
	s.bumpCatalogVersion(r.Context())
	registryWrites.WithLabelValues("workflow_proposal", "approve").Inc()
	writeJSON(w, http.StatusOK, map[string]any{"proposal_id": pid, "status": "approved", "slug": p.Slug})
}

func (s *Server) rejectWorkflowProposal(w http.ResponseWriter, r *http.Request) {
	uid, ok := s.requireUser(w, r)
	if !ok {
		return
	}
	pid, ok := parseUUIDParam(w, r, "proposal_id")
	if !ok {
		return
	}
	var body struct {
		Reason string `json:"reason"`
	}
	_ = decodeJSON(w, r, &body)
	ct, err := s.db.Exec(r.Context(),
		`UPDATE workflow_proposals SET status='rejected', reject_reason=$1, updated_at=now() WHERE proposal_id=$2 AND owner_user_id=$3 AND status='pending'`,
		body.Reason, pid, uid)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "could not reject")
		return
	}
	if ct.RowsAffected() == 0 {
		writeError(w, http.StatusNotFound, "NOT_FOUND", "no pending proposal")
		return
	}
	s.audit(r.Context(), uid, "user", "workflow_proposal", "reject", &pid, "", "", nil)
	registryWrites.WithLabelValues("workflow_proposal", "reject").Inc()
	writeJSON(w, http.StatusOK, map[string]any{"proposal_id": pid, "status": "rejected"})
}

// snapshotWorkflowRevision appends the current row to workflow_revisions (best-effort).
func (s *Server) snapshotWorkflowRevision(ctx context.Context, id uuid.UUID) {
	_, _ = s.db.Exec(ctx,
		`INSERT INTO workflow_revisions (workflow_id, title, description, surfaces, inputs, steps, notes_md)
		 SELECT workflow_id, title, description, surfaces, inputs, steps, notes_md FROM workflows WHERE workflow_id=$1`, id)
}

func tierFor(bookID *uuid.UUID) string {
	if bookID != nil {
		return "book"
	}
	return "user"
}

// ── internal reader (X-Internal-Token) — the chat-service step-runner (WS-2b) ─

type workflowFull struct {
	Slug        string            `json:"slug"`
	Title       string            `json:"title"`
	Description string            `json:"description"`
	Tier        string            `json:"tier"`
	Surfaces    []string          `json:"surfaces"`
	Inputs      map[string]string `json:"inputs"`
	Steps       []workflowStepIn  `json:"steps"`
	NotesMD     string            `json:"notes_md"`
}

// internalWorkflows returns the FULL published workflows visible for a (user, book,
// surface) context — System defaults + the user's own + the book's — so the runner can
// list them (workflow_list) and execute one by slug (workflow_load). A user/book slug
// shadows a System slug of the same name (dedup keeps the highest-precedence tier).
func (s *Server) internalWorkflows(w http.ResponseWriter, r *http.Request) {
	if s.db == nil {
		writeError(w, http.StatusServiceUnavailable, "NO_DB", "database unavailable")
		return
	}
	uid, err := uuid.Parse(r.URL.Query().Get("user_id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "VALIDATION_ERROR", "user_id required")
		return
	}
	surface := r.URL.Query().Get("surface")
	bookID := uuid.Nil
	if v := r.URL.Query().Get("book_id"); v != "" {
		if b, err := uuid.Parse(v); err == nil {
			bookID = b
		}
	}
	// GRANT-CHECK the book. `book_id` arrives from the caller (chat-service forwards the
	// FE's client-supplied book_context), so an ungated read here would hand ANY user the
	// book-tier workflows (full steps + notes_md) and the book-tier mode_binding of any
	// book whose UUID they know — a cross-tenant config read that also steers their tool
	// surface. Fail SOFT, not 403: drop to the user's own scope and serve the System ∪
	// user tiers, because a grant-authority blip must not brick every chat turn (the same
	// degrade contract the rest of this route follows).
	if bookID != uuid.Nil {
		if ok, _ := s.bookGrantOK(r.Context(), bookID, uid, grantclient.GrantView); !ok {
			bookID = uuid.Nil
		}
	}
	rows, err := s.db.Query(r.Context(),
		`SELECT slug, title, description, tier, surfaces, inputs, steps, notes_md FROM workflows
		 WHERE status = 'published' AND (
		     tier = 'system'
		     OR (tier = 'user' AND owner_user_id = $1)
		     OR (tier = 'book' AND book_id = $2))
		 ORDER BY slug, (tier = 'book') DESC, (tier = 'user') DESC`, uid, nullUUID(bookID))
	if err != nil {
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "could not resolve workflows")
		return
	}
	defer rows.Close()
	// dedup by slug keeping the first (highest-precedence) row per the ORDER BY.
	seen := map[string]bool{}
	out := []workflowFull{}
	for rows.Next() {
		var wf workflowFull
		var inputsJSON, stepsJSON []byte
		if err := rows.Scan(&wf.Slug, &wf.Title, &wf.Description, &wf.Tier, &wf.Surfaces, &inputsJSON, &stepsJSON, &wf.NotesMD); err != nil {
			continue
		}
		// Filter by surface BEFORE dedup: a higher-precedence row that does NOT match
		// the surface must not claim the slug and shadow out a lower-tier row that
		// WOULD match (else e.g. a user 'foo' on [compose] erases the System 'foo' on
		// [chat] for a chat turn). Shadowing applies only among surface-matching rows.
		if surface != "" && len(wf.Surfaces) > 0 && !contains(wf.Surfaces, surface) {
			continue
		}
		if seen[wf.Slug] {
			continue
		}
		seen[wf.Slug] = true
		_ = json.Unmarshal(inputsJSON, &wf.Inputs)
		_ = json.Unmarshal(stepsJSON, &wf.Steps)
		if wf.Inputs == nil {
			wf.Inputs = map[string]string{}
		}
		if wf.Steps == nil {
			wf.Steps = []workflowStepIn{}
		}
		out = append(out, wf)
	}
	resp := map[string]any{
		"catalog_version": s.catalogVersion(r.Context()),
		"workflows":       out,
	}
	// WS-3 (C6) — the mode→capability binding rides the SAME per-turn fetch the
	// chat-service already makes (one hop, one degrade path: any failure ⇒ the client
	// returns empty ⇒ no binding ⇒ exactly the pre-WS-3 behavior). Absent `mode` ⇒ the
	// field is omitted entirely, so an older client is unaffected.
	if mode := r.URL.Query().Get("mode"); mode != "" {
		if b := s.resolveModeBinding(r.Context(), uid, bookID, mode); b != nil {
			resp["mode_binding"] = b
		}
	}
	writeJSON(w, http.StatusOK, resp)
}

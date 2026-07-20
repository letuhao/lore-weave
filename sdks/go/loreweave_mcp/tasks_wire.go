// ext-tasks durable-gate WIRE (Go) — the gate helpers a Go KIND-C confirm tool uses
// (mirror of sdks/python/loreweave_mcp/tasks_wire.py: open_gate / gate_or_confirm /
// client_supports_tasks). Handle-in-content form (spec §6 "SIMPLIFICATION"): the gate
// tool returns the task HANDLE as its normal result; the ai-gateway forwards it as an
// ordinary CallToolResult; chat-service detects it and drives the provide-input tool.
package loreweave_mcp

import (
	"context"

	"github.com/modelcontextprotocol/go-sdk/mcp"
)

// GateHandleType marks a gate handle in a tool result (kept identical to the Python
// GATE_RESULT_TYPE and chat-service task_detect.GATE_RESULT_TYPE).
const GateHandleType = "io.loreweave/task-handle"

// TasksExtension is the ext-tasks extension id; ClientCapsKey / extensionsKey are the
// per-request client-capability envelope keys (spec §4.2) — identical to the Python side.
const (
	TasksExtension = "io.modelcontextprotocol/tasks"
	clientCapsKey  = "io.modelcontextprotocol/clientCapabilities"
	extensionsKey  = "extensions"
)

// Meta is the per-request _meta map a tool handler reads from req.Params.Meta.
// Aliased to map[string]any so a handler can pass the go-sdk mcp.Meta (itself
// map[string]any) straight in, without this kit importing the go-sdk transport type.
type Meta = map[string]any

func asMap(v any) map[string]any {
	m, _ := v.(map[string]any)
	return m
}

// ClientSupportsTasks reports whether THIS request's client declared the ext-tasks
// extension in per-request _meta (params._meta[clientCapabilities].extensions[tasks]).
// A KIND-C tool gates on this: task iff true, else the confirm_token fallback — so
// flipping a tool never strands a client that can't drive tasks. Fail-closed on any
// missing/mis-typed node (→ confirm_token).
func ClientSupportsTasks(meta Meta) bool {
	if meta == nil {
		return false
	}
	caps := asMap(meta[clientCapsKey])
	exts := asMap(caps[extensionsKey])
	// Require the extension value to be PRESENT AND non-nil — matches the Python
	// client_supports_tasks (`_mget(...) is not None`). A client that sends
	// `tasks: null` explicitly declares no support and must fall back to confirm.
	v, ok := exts[TasksExtension]
	return ok && v != nil
}

// OpenGate durably opens the human gate and returns the task HANDLE the tool returns
// as its result (the client polls/confirms via the provide-input tool).
func OpenGate(store TaskStore, descriptor string, executor TaskExecutor, inputRequests any, ttlMs int) (map[string]any, error) {
	task, err := store.Create(descriptor, executor, inputRequests, ttlMs)
	if err != nil {
		return nil, err
	}
	return map[string]any{
		"type":           GateHandleType,
		"taskId":         task.TaskID,
		"status":         task.Status,
		"pollIntervalMs": task.PollIntervalMs,
		"inputRequests":  inputRequests,
	}, nil
}

// GateOrConfirm is the capability-gated KIND-C gate — the ONE call a Go domain confirm
// tool makes. If the client declared tasks support → open a durable TASK; else →
// confirmFallback() (today's {confirm_token, descriptor, …}). A tool must never call
// OpenGate unconditionally (that would strand a non-tasks client). Mirrors the Python
// gate_or_confirm.
func GateOrConfirm(
	_ context.Context,
	meta Meta,
	store TaskStore,
	descriptor string,
	executor TaskExecutor,
	inputRequests any,
	confirmFallback func() any,
	ttlMs int,
) (any, error) {
	if ClientSupportsTasks(meta) {
		return OpenGate(store, descriptor, executor, inputRequests, ttlMs)
	}
	return confirmFallback(), nil
}

// ProvideInputArgs is the wire input for the `<prefix>_task_provide_input` tool —
// identical to the Python task_provide_input kwargs (flat task_id/accepted/inputs),
// so chat-service's resume driver calls a Go domain's gate the same way it calls
// a Python one. Accepted defaults to true (pointer ⇒ absent means accept).
type ProvideInputArgs struct {
	TaskID   string         `json:"task_id" jsonschema:"the taskId returned in the gate handle"`
	Accepted *bool          `json:"accepted,omitempty" jsonschema:"true to run the gated action, false to decline"`
	Inputs   map[string]any `json:"inputs,omitempty" jsonschema:"the human's response payload"`
}

// ProvideInputResult mirrors the Python provide-input return: taskId + terminal
// status, plus the executor result on completed / the message on failed.
type ProvideInputResult struct {
	TaskID string `json:"taskId"`
	Status string `json:"status"`
	Result any    `json:"result,omitempty"`
	Error  string `json:"error,omitempty"`
}

// RegisterTaskProvideInput registers the `<toolPrefix>_task_provide_input` tool on
// srv — the ONE endpoint a client drives to resolve a Go domain's durable gate. The
// prefix is REQUIRED for any domain reached through the ai-gateway: the gateway
// catalog routes by tool NAME, so a bare `task_provide_input` from two domains would
// collide (mirror of the Python register_task_endpoints tool_prefix rule). Uses the
// kit's RegisterTool so the result-size gate + content-dedup fixes apply.
func RegisterTaskProvideInput(srv *mcp.Server, store TaskStore, toolPrefix string) {
	name := "task_provide_input"
	if toolPrefix != "" {
		name = toolPrefix + "_task_provide_input"
	}
	RegisterTool(srv, &mcp.Tool{
		Name:        name,
		Description: "Resolve a pending durable-gate task: accept to run the gated action, or decline.",
		// CAT-4 visibility:legacy — this is a MECHANISM tool the client (chat-service's
		// resume driver) calls by NAME, not something the LLM should discover via
		// find_tools. Legacy ⇒ excluded from discovery/hot-seed, still callable by name.
		Meta: WithVisibility(mcp.Meta{}, VisibilityLegacy),
	}, func(ctx context.Context, _ *mcp.CallToolRequest, in ProvideInputArgs) (*mcp.CallToolResult, ProvideInputResult, error) {
		accepted := true
		if in.Accepted != nil {
			accepted = *in.Accepted
		}
		payload := map[string]any{}
		for k, v := range in.Inputs {
			payload[k] = v
		}
		payload["accepted"] = accepted
		task, err := store.ProvideInput(ctx, in.TaskID, payload)
		if err != nil {
			return nil, ProvideInputResult{}, err
		}
		out := ProvideInputResult{TaskID: task.TaskID, Status: task.Status}
		if task.Status == TaskCompleted {
			out.Result = task.Result
		}
		if task.Status == TaskFailed && task.ErrorMsg != "" {
			out.Error = task.ErrorMsg
		}
		return nil, out, nil
	})
}

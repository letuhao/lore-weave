package loreweave_mcp

import (
	"context"
	"reflect"

	"github.com/google/jsonschema-go/jsonschema"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

// isEmptyInterface reports whether the type parameter T is `any` (interface{} with no
// methods). A tool that returns different shapes per branch — a durable task HANDLE vs a
// confirm CARD (GateOrConfirm) — legitimately has Out=any.
func isEmptyInterface[T any]() bool {
	et := reflect.TypeOf((*T)(nil)).Elem()
	return et.Kind() == reflect.Interface && et.NumMethod() == 0
}

// compactContentPlaceholder replaces the go-sdk's own auto-generated duplicate
// of a tool's full JSON result. External MCP discoverability audit #9: every
// structured tool result came back as BOTH `structuredContent` (real JSON) AND
// `content[0].text` (the SAME payload, JSON-stringified again) — ~2x tokens on
// every call, cutting against the whole reason find_tools/invoke_tool exist
// (keep token usage down for LLM callers). A client that understands
// structured output (every real MCP client) reads `structuredContent` and
// never looks at `content` — the MCP spec keeps `content` around only for a
// client that DOESN'T understand structured output, so it just needs to
// exist, not duplicate the payload.
const compactContentPlaceholder = "ok — see structuredContent for the full result"

// RegisterTool is a DROP-IN REPLACEMENT for the go-sdk's own generic
// `mcp.AddTool[In, Out]` — same signature, same registration semantics —
// that additionally prevents the payload-duplication bug (external MCP
// discoverability audit #9).
//
// Root cause (verified against go-sdk v1.6.1's `mcp/server.go`, the
// `toolForErr` handler wrapper built by `AddTool`): AFTER a tool handler
// returns, the SDK marshals its typed `Out` into `res.StructuredContent`,
// and — ONLY IF the handler left `res.Content == nil` — ALSO stuffs the
// identical JSON into a `TextContent` block (the "if Content isn't being
// used" fallback the MCP spec suggests for pre-structured-output clients).
// Every handler in this codebase returns `res=nil` (letting the SDK build
// the whole `CallToolResult`), so `res.Content` is ALWAYS nil when the SDK's
// own check runs — the fallback fires on literally every call, every time.
//
// There is no per-handler escape hatch exposed by the SDK itself (the
// `Content == nil` check lives INSIDE the wrapper `AddTool` builds, not
// something a caller of `AddTool` can influence from outside) — so the fix
// has to wrap the HANDLER itself, before it ever reaches `AddTool`: after
// the real handler returns, if it left `Content` nil, this sets it to a
// short, constant placeholder instead of leaving it nil — which makes the
// SDK's own `if res.Content == nil` check FALSE, so its auto-duplication
// never fires. `StructuredContent` (the only field any real client reads)
// is completely unaffected — still built by the SDK exactly as today.
//
// A handler that DOES set its own `res.Content` (a genuine multi-block or
// non-JSON result) is untouched — this only ever fills a nil Content, never
// overwrites one a handler deliberately built.
func RegisterTool[In, Out any](
	s *mcp.Server,
	t *mcp.Tool,
	h mcp.ToolHandlerFor[In, Out],
) {
	wrapped := func(ctx context.Context, req *mcp.CallToolRequest, in In) (*mcp.CallToolResult, Out, error) {
		res, out, err := h(ctx, req, in)
		if err == nil {
			// THE RESULT-SIZE GATE (see result_size.go). Every Go MCP tool in this repo
			// registers through here, so this is the one place that can guarantee no tool
			// ships a payload its caller cannot hold. A 44KB result already cost this project
			// a flagship scenario — the model looped, every unit test stayed green, and the
			// tool "worked". Fail it loudly at the source instead.
			if sizeErr := checkResultSize(t.Name, out); sizeErr != nil {
				var zero Out
				return nil, zero, sizeErr
			}
			if res == nil {
				res = &mcp.CallToolResult{}
			}
			if res.Content == nil {
				res.Content = []mcp.Content{&mcp.TextContent{Text: compactContentPlaceholder}}
			}
		}
		return res, out, err
	}
	// Out=any makes the SDK infer an outputSchema whose `properties.result` is the
	// permissive "any" schema (`true`/empty) — which strict federation validators (the
	// ai-gateway proxy) REJECT, failing the whole provider's list-tools so NONE of its
	// tools route. A GateOrConfirm tool legitimately returns two shapes (task handle vs
	// confirm card), so Out=any is correct; give it an explicit permissive-but-VALID
	// object schema so the SDK keeps this one instead of inferring the unvalidatable one.
	// (The SDK still wraps the value under `structuredContent.result`; clients already
	// unwrap that.) Only when the caller didn't set a schema themselves.
	if t.OutputSchema == nil && isEmptyInterface[Out]() {
		t.OutputSchema = &jsonschema.Schema{Type: "object"}
	}
	mcp.AddTool(s, t, wrapped)
}

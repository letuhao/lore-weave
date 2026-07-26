package api

import (
	"encoding/json"
	"net/http"

	"github.com/loreweave/provider-registry-service/internal/jobs"
)

// headerMcpKeyID is the public-MCP-key envelope header (matches lwmcp.HeaderMcpKeyID),
// minted at the public edge (mcp-public-gateway) and forwarded by ai-gateway + the MCP
// kits. Present on SYNCHRONOUS spend calls (stream / proxy / job submit). For ASYNC
// jobs the header is gone by the time the worker submits to the provider, so the key
// id is persisted in job_meta.mcp_key_id instead — hence isPublicMcpKeyCall checks both.
const headerMcpKeyID = "X-Mcp-Key-Id"

// isPublicMcpKeyCall reports whether a request originated at the public MCP edge —
// via the X-Mcp-Key-Id header OR the job_meta.mcp_key_id tag (pass nil jobMeta on the
// synchronous paths that have no job_meta). First-party traffic carries neither.
func isPublicMcpKeyCall(r *http.Request, jobMeta json.RawMessage) bool {
	if r.Header.Get(headerMcpKeyID) != "" {
		return true
	}
	return jobs.ParseJobMetaMcpKeyID(jobMeta) != nil
}

// rejectPlatformDrawForPublicKey enforces PUB-12 (BYOK-only) at a spend entry point.
// A public MCP key may spend ONLY through the owner's own BYOK credentials, so a
// platform_model draw (free-tier / platform balance) is rejected 402 LLM_BYOK_ONLY.
// Returns true (after writing the 402) when the caller must stop. MUST be called
// BEFORE any guardrail reservation so a rejected public-key platform job never leaks
// a held reserve. Applied uniformly at every provider-registry spend entry point
// (jobs submit, stream, proxy) so no future wiring can bypass it. See
// docs/specs/2026-06-26-public-mcp (PUB-12 / Q-MONEY LOCKED).
func rejectPlatformDrawForPublicKey(w http.ResponseWriter, modelSource string, isPublic bool) bool {
	if modelSource == "platform_model" && isPublic {
		writeError(w, http.StatusPaymentRequired, "LLM_BYOK_ONLY",
			"public MCP keys are BYOK-only; platform models are not permitted")
		return true
	}
	return false
}

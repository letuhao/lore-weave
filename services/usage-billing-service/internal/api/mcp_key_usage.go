package api

import (
	"net/http"

	"github.com/google/uuid"
)

// mcpKeyUsageRow is one public-MCP-key's spend rollup for the requested period.
type mcpKeyUsageRow struct {
	McpKeyID     uuid.UUID `json:"mcp_key_id"`
	RequestCount int       `json:"request_count"`
	TotalTokens  int       `json:"total_tokens"`
	TotalCostUSD float64   `json:"total_cost_usd"`
}

// getMcpKeyUsage — GET /internal/billing/mcp-key-usage?owner_user_id=&period=
//
// Per-key spend rollup (H-C/PUB-11). Aggregates usage_logs for one owner, grouped
// by mcp_key_id, over the requested period. Internal-token gated (the caller — the
// MCP edge — already authenticated the owner, so owner_user_id is an explicit arg,
// not derived from a JWT here). Powers the owner audit view (H-O) and the future
// per-key spend sub-cap (H-K). Only rows with a non-NULL mcp_key_id are returned;
// first-party spend is excluded by construction.
func (s *Server) getMcpKeyUsage(w http.ResponseWriter, r *http.Request) {
	ownerStr := r.URL.Query().Get("owner_user_id")
	owner, err := uuid.Parse(ownerStr)
	if err != nil {
		writeError(w, http.StatusBadRequest, "M03_INVALID_REQUEST", "owner_user_id must be a UUID")
		return
	}
	// Same period vocabulary as getUsageSummary; default = current calendar month.
	var where string
	switch r.URL.Query().Get("period") {
	case "last_24h":
		where = "created_at >= now() - interval '24 hours'"
	case "last_7d":
		where = "created_at >= now() - interval '7 days'"
	case "last_30d":
		where = "created_at >= now() - interval '30 days'"
	case "last_90d":
		where = "created_at >= now() - interval '90 days'"
	default:
		where = "date_trunc('month', created_at) = date_trunc('month', now())"
	}

	// request_status='success' — count only ACTUAL incurred spend; a provider_error /
	// billing_rejected row carries no real cost and must not inflate a per-key rollup
	// that the spend sub-cap (H-K) will read. (/review-impl LOW#3.)
	rows, err := s.pool.Query(r.Context(), `
SELECT mcp_key_id, COUNT(*), COALESCE(SUM(total_tokens),0), COALESCE(SUM(total_cost_usd),0)
FROM usage_logs
WHERE owner_user_id=$1 AND mcp_key_id IS NOT NULL AND request_status='success' AND `+where+`
GROUP BY mcp_key_id
ORDER BY SUM(total_cost_usd) DESC
`, owner)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "M03_USAGE_SUMMARY_FAILED", "failed to read per-key usage")
		return
	}
	defer rows.Close()

	out := make([]mcpKeyUsageRow, 0)
	var totalCost float64
	for rows.Next() {
		var row mcpKeyUsageRow
		if err := rows.Scan(&row.McpKeyID, &row.RequestCount, &row.TotalTokens, &row.TotalCostUSD); err != nil {
			writeError(w, http.StatusInternalServerError, "M03_USAGE_SUMMARY_FAILED", "failed to scan per-key usage")
			return
		}
		totalCost += row.TotalCostUSD
		out = append(out, row)
	}
	if err := rows.Err(); err != nil {
		writeError(w, http.StatusInternalServerError, "M03_USAGE_SUMMARY_FAILED", "failed to read per-key usage")
		return
	}

	writeJSON(w, http.StatusOK, map[string]any{
		"owner_user_id":  owner,
		"keys":           out,
		"total_cost_usd": totalCost,
	})
}

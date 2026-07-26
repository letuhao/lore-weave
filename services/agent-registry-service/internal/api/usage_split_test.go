package api

import (
	"encoding/json"
	"net/http"
	"testing"

	"github.com/google/uuid"
	"github.com/pashagolub/pgxmock/v4"
)

// S-12 badge — /usage splits pending proposals into skill + workflow (so the studio badge
// can route a click) while keeping proposals_pending = the SUM (back-compat).
func TestUsage_SplitsPendingProposals(t *testing.T) {
	s, mock := newMockServer(t)
	defer mock.Close()
	mock.MatchExpectationsInOrder(false) // getUsage fires ~7 COUNTs; match by table, not order

	one := func(n int64) *pgxmock.Rows { return pgxmock.NewRows([]string{"count"}).AddRow(n) }
	mock.ExpectQuery("FROM plugins").WithArgs(pgxmock.AnyArg()).WillReturnRows(one(0))
	mock.ExpectQuery("FROM skills WHERE owner_user_id").WithArgs(pgxmock.AnyArg()).WillReturnRows(one(0))
	mock.ExpectQuery("FROM workflows WHERE owner_user_id").WithArgs(pgxmock.AnyArg()).WillReturnRows(one(0))
	mock.ExpectQuery("FROM mcp_server_registrations").WithArgs(pgxmock.AnyArg()).WillReturnRows(one(0))
	mock.ExpectQuery("FROM slash_commands").WithArgs(pgxmock.AnyArg()).WillReturnRows(one(0))
	mock.ExpectQuery("FROM skill_proposals WHERE owner_user_id").WithArgs(pgxmock.AnyArg()).WillReturnRows(one(2))
	mock.ExpectQuery("FROM workflow_proposals WHERE owner_user_id").WithArgs(pgxmock.AnyArg()).WillReturnRows(one(3))

	rec := doJSON(s, http.MethodGet, "/v1/agent-registry/usage", mintJWT(t, uuid.NewString(), ""), "")
	if rec.Code != http.StatusOK {
		t.Fatalf("want 200, got %d (%s)", rec.Code, rec.Body.String())
	}
	var out struct {
		Skill    int `json:"skill_proposals_pending"`
		Workflow int `json:"workflow_proposals_pending"`
		Total    int `json:"proposals_pending"`
	}
	_ = json.Unmarshal(rec.Body.Bytes(), &out)
	if out.Skill != 2 || out.Workflow != 3 || out.Total != 5 {
		t.Errorf("split wrong: skill=%d workflow=%d total=%d, want 2/3/5", out.Skill, out.Workflow, out.Total)
	}
}

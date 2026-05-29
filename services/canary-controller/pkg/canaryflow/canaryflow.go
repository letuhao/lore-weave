// Package canaryflow is a NON-internal re-export of the canary-controller's
// canary + cohort_router + controller API surface so cross-module consumers
// (tests/integration, future BFF wrappers) can exercise the canary state
// machine WITHOUT importing the internal/ tree.
//
// Intentionally thin: type aliases + small wrapper funcs only. All logic stays
// in internal/. Mirrors the cliapi / statusflow pattern used by sibling
// services.
package canaryflow

import (
	"context"
	"time"

	"github.com/loreweave/foundation/services/canary-controller/internal/canary"
	"github.com/loreweave/foundation/services/canary-controller/internal/cohort_router"
	"github.com/loreweave/foundation/services/canary-controller/internal/controller"
	"github.com/loreweave/foundation/services/canary-controller/internal/deployclass"
)

// ─── canary state machine ────────────────────────────────────────────────────

type (
	Stage       = canary.Stage
	State       = canary.State
	Observation = canary.Observation
	Action      = canary.Action
	Decision    = canary.Decision
)

const (
	StageInternal = canary.StageInternal
	Stage1pct     = canary.Stage1pct
	Stage10pct    = canary.Stage10pct
	Stage50pct    = canary.Stage50pct
	StageFull     = canary.StageFull

	ActionHold     = canary.ActionHold
	ActionAdvance  = canary.ActionAdvance
	ActionAbort    = canary.ActionAbort
	ActionComplete = canary.ActionComplete

	BaselineBurnMultiplier = canary.BaselineBurnMultiplier
)

// Decide re-exports canary.Decide.
func Decide(st State, obs Observation) Decision { return canary.Decide(st, obs) }

// MonitorWindow re-exports canary.MonitorWindow.
func MonitorWindow(s Stage) time.Duration { return canary.MonitorWindow(s) }

// CohortInStage re-exports canary.CohortInStage.
func CohortInStage(cohort int, stage Stage) bool { return canary.CohortInStage(cohort, stage) }

// ─── cohort router ───────────────────────────────────────────────────────────

type (
	Reality       = cohort_router.Reality
	RealitySource = cohort_router.RealitySource
	StaticSource  = cohort_router.StaticSource
	Router        = cohort_router.Router
)

// NewRouter re-exports cohort_router.New.
func NewRouter(src RealitySource) (*Router, error) { return cohort_router.New(src) }

// ─── controller ──────────────────────────────────────────────────────────────

type (
	DeployRecord    = controller.DeployRecord
	DeployStore     = controller.DeployStore
	SLISource       = controller.SLISource
	RolloutExecutor = controller.RolloutExecutor
	Pager           = controller.Pager
	Controller      = controller.Controller
	TickResult      = controller.TickResult
	Clock           = controller.Clock
)

// NewController re-exports controller.New.
func NewController(store DeployStore, sli SLISource, exec RolloutExecutor, pager Pager, now Clock) (*Controller, error) {
	return controller.New(store, sli, exec, pager, now)
}

// ─── deploy classification ───────────────────────────────────────────────────

type (
	Class   = deployclass.Class
	Signals = deployclass.Signals
)

const (
	ClassPatch     = deployclass.Patch
	ClassMinor     = deployclass.Minor
	ClassMajor     = deployclass.Major
	ClassEmergency = deployclass.Emergency
)

// Classify re-exports deployclass.Classify.
func Classify(s Signals) Class { return deployclass.Classify(s) }

// Compile-time assertion that the controller satisfies its own use here.
var _ = context.Background

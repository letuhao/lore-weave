"""Job lifecycle CORE (RAID C8) — the per-job state machine + cost guardrail.

In-process only this cycle (Q-R2 cost discipline): NO Redis Streams runner, NO
end-to-end orchestration (that is C14). The :class:`JobStateMachine` enforces the
legal transition DAG and persists state to the C2 ``enrichment_job`` table; the
:class:`CostGuardrail` accumulates projected spend against a per-job cap and
pauses the job BEFORE the cap is breached.
"""

from app.jobs.cost_guardrail import (
    CostCapExceeded,
    CostGuardrail,
)
from app.jobs.state_machine import (
    IllegalTransitionError,
    JobState,
    JobStateMachine,
    PauseReason,
)

__all__ = [
    "JobState",
    "JobStateMachine",
    "IllegalTransitionError",
    "PauseReason",
    "CostGuardrail",
    "CostCapExceeded",
]

"""DeepEval custom G-Eval metrics for narrative-fiction extraction (cycle 2026-05-27).

Per spec D5: 3 G-Eval metrics, each pinned to a DIFFERENT ensemble judge
to avoid the circular-judge problem (one model judging in both llm_judge.py
AND G-Eval would be 1-judge × 3-paths, not 3-way ensemble).

Metric → judge assignment (spec D5):
- `NarrativeEntityCoverage`     → gemma-4-26b-a4b (judge A)
- `RelationFactualGroundedness` → huihui-qwen3-30b-instruct (judge B)
- `EventActionRecall`           → huihui-claude-4.7-opus (judge C)

Each metric uses DeepEval's `GEval` with natural-language criteria. The
custom `LoreweaveJudgeLLM` adapter wraps our `LLMClient` so DeepEval routes
all judge calls through the gateway invariant (no direct provider SDK).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from deepeval.metrics import GEval
from deepeval.models.base_model import DeepEvalBaseLLM
from deepeval.test_case import SingleTurnParams

logger = logging.getLogger(__name__)


# ── Judge UUIDs per spec D5 ──────────────────────────────────────────────────

# Canonical mapping (per spec D3 + D5; same UUIDs used by llm_judge ensemble).
JUDGE_UUID_GEMMA = "019dc3df-58f3-7170-bb48-f1f0c9bd604c"  # Judge A
JUDGE_UUID_QWEN3_30B = "019e6a20-eeac-7b96-82ee-69a16d8ef68d"  # Judge B
JUDGE_UUID_CLAUDE_47 = "019e5650-eca7-78c2-985d-465aa3bce1ce"  # Judge C


# ── Loreweave-gateway adapter for DeepEval ───────────────────────────────────


class LoreweaveJudgeLLM(DeepEvalBaseLLM):
    """Adapter routing DeepEval `generate()` calls through our `LLMClient`.

    DeepEval's `GEval` calls `model.generate(prompt)` (sync) or `model.a_generate()`
    (async). We map both to a single `/internal/llm/jobs` chat call via the
    SDK. Streaming + tool calls are not used (GEval expects a single text
    response with a numeric score).

    Constructed with a `judge_model_uuid` + a (lazy-loaded) `LLMClient`. The
    same `LoreweaveJudgeLLM` instance can be reused across multiple GEval
    metric invocations — sequential LM Studio swaps happen at the LLM Studio
    side via JIT-loading when the UUID changes between calls.

    NOTE: This adapter is intentionally thin. The integration-phase work
    (sub-checkpoint 1b consumer in test_eval_with_deepeval.py) wires up the
    `LLMClient` from the existing knowledge-service deps tree.
    """

    def __init__(
        self,
        judge_model_uuid: str,
        judge_model_name: str,
        llm_client: Any,  # `app.clients.llm_client.LLMClient`, kept untyped to
        # avoid import-cycle at module-collection time
        user_id: str,
        max_tokens: int = 4096,
    ) -> None:
        self._uuid = judge_model_uuid
        self._name = judge_model_name
        self._client = llm_client
        self._user_id = user_id
        self._max_tokens = max_tokens

    def get_model_name(self) -> str:
        return f"loreweave/{self._name}"

    def load_model(self) -> "LoreweaveJudgeLLM":
        # No local model state to load; the underlying LLMClient is lifespan-
        # managed elsewhere. Return self for DeepEval's pattern.
        return self

    # ── sync path (DeepEval's `generate`)──────────────────────────────────────

    def generate(self, prompt: str, schema: Any | None = None) -> str:
        """DeepEval may call sync `generate`. Run async via asyncio."""

        import asyncio

        return asyncio.run(self.a_generate(prompt, schema=schema))

    # ── async path (DeepEval's `a_generate`) ──────────────────────────────────

    async def a_generate(self, prompt: str, schema: Any | None = None) -> str:
        """Submit a single-turn chat to the gateway + return response text."""

        # llm_client.submit_and_wait expects an input dict shaped like our
        # extractors' calls. Build a minimal chat-only payload.
        job = await self._client.submit_and_wait(
            user_id=self._user_id,
            operation="chat",
            model_source="user_model",
            model_ref=self._uuid,
            input={
                "messages": [{"role": "user", "content": prompt}],
                "response_format": {"type": "text"},  # LM Studio compat
                "temperature": 0.0,
                "max_tokens": self._max_tokens,
            },
        )
        # `job.result` shape depends on the SDK's JobResult model. Defensive
        # extraction: prefer the top-level `content` field, fall back to
        # `text` or the whole stringified result.
        result = getattr(job, "result", None) or {}
        if isinstance(result, dict):
            content = result.get("content") or result.get("text") or ""
            if not content and result:
                content = json.dumps(result, ensure_ascii=False)
            return str(content)
        return str(result)

    # Required-by-base default implementations
    async def a_generate_with_schema(self, prompt: str, schema: Any) -> Any:  # noqa: D102
        text = await self.a_generate(prompt, schema=schema)
        # DeepEval expects schema-shaped output; we return raw text and rely on
        # G-Eval's own response parser. (DeepEval handles non-schema-shaped
        # responses for GEval by extracting a score with regex.)
        return text

    def generate_with_schema(self, prompt: str, schema: Any) -> Any:  # noqa: D102
        import asyncio

        return asyncio.run(self.a_generate_with_schema(prompt, schema))


# ── 3 metric definitions per spec D5 ─────────────────────────────────────────


def build_narrative_entity_coverage(
    judge_client: Any, user_id: str, threshold: float = 0.7
) -> GEval:
    """Metric A: judges entity-level coverage of gold entities by extracted set.

    Spec D5 — pinned to JUDGE A (gemma-4-26b-a4b).

    DeepEval test case shape:
      `LLMTestCase(input=chapter_text, actual_output=extracted_entities_json,
                   expected_output=gold_entities_json)`
    Score: 0.0 (none captured) → 1.0 (all gold captured under any phrasing).
    """

    judge = LoreweaveJudgeLLM(
        judge_model_uuid=JUDGE_UUID_GEMMA,
        judge_model_name="gemma-4-26b-a4b",
        llm_client=judge_client,
        user_id=user_id,
    )
    return GEval(
        name="NarrativeEntityCoverage",
        criteria=(
            "Score on a 0.0 to 1.0 scale based on how well the EXTRACTED entities "
            "(in `actual_output`) cover the GOLD entities (in `expected_output`) "
            "for the given narrative chapter (`input`). "
            "Award full credit when a gold entity is captured under any reasonable "
            "phrasing or canonical alternate; partial credit for paraphrases. "
            "Do NOT penalize the EXTRACTED set for over-extraction (extra entities "
            "outside the gold set) — this metric focuses on COVERAGE of gold only. "
            "Return a numeric score between 0.0 and 1.0."
        ),
        evaluation_params=[
            SingleTurnParams.INPUT,
            SingleTurnParams.ACTUAL_OUTPUT,
            SingleTurnParams.EXPECTED_OUTPUT,
        ],
        model=judge,
        threshold=threshold,
    )


def build_relation_factual_groundedness(
    judge_client: Any, user_id: str, threshold: float = 0.7
) -> GEval:
    """Metric B: judges whether each extracted relation is source-grounded.

    Spec D5 — pinned to JUDGE B (huihui-qwen3-30b-instruct).

    DeepEval test case shape:
      `LLMTestCase(input=chapter_text, actual_output=extracted_relations_json)`
    No `expected_output` — this metric is precision-oriented, not coverage.
    Score: 0.0 (all relations hallucinated) → 1.0 (all relations unambiguously
    supported by the chapter text).
    """

    judge = LoreweaveJudgeLLM(
        judge_model_uuid=JUDGE_UUID_QWEN3_30B,
        judge_model_name="huihui-qwen3-30b-instruct",
        llm_client=judge_client,
        user_id=user_id,
    )
    return GEval(
        name="RelationFactualGroundedness",
        criteria=(
            "Score on a 0.0 to 1.0 scale for the EXTRACTED relations (in "
            "`actual_output`) against the chapter text (`input`). "
            "For each relation tuple (subject, predicate, object): "
            "award 1.0 if the (subject, predicate, object) is unambiguously "
            "supported by the chapter text; 0.0 if it is a hallucination or "
            "an unsupported inference; partial credit for plausible-but-not-"
            "explicit relations. The final score is the average over all "
            "extracted relations. Return a numeric score between 0.0 and 1.0."
        ),
        evaluation_params=[
            SingleTurnParams.INPUT,
            SingleTurnParams.ACTUAL_OUTPUT,
        ],
        model=judge,
        threshold=threshold,
    )


def build_event_action_recall(
    judge_client: Any, user_id: str, threshold: float = 0.7
) -> GEval:
    """Metric C: judges event-coverage of gold events by extracted events.

    Spec D5 — pinned to JUDGE C (huihui-claude-4.7-opus).

    DeepEval test case shape:
      `LLMTestCase(input=chapter_text, actual_output=extracted_events_json,
                   expected_output=gold_events_json)`
    Score: 0.0 (no gold events captured) → 1.0 (every gold event represented).
    Partial credit for over-merged or split events; do not penalize for over-
    extraction (extra events beyond gold).
    """

    judge = LoreweaveJudgeLLM(
        judge_model_uuid=JUDGE_UUID_CLAUDE_47,
        judge_model_name="huihui-claude-4.7-opus",
        llm_client=judge_client,
        user_id=user_id,
    )
    return GEval(
        name="EventActionRecall",
        criteria=(
            "Score on a 0.0 to 1.0 scale based on how many GOLD events "
            "(in `expected_output`) were captured by the EXTRACTED events "
            "(in `actual_output`) for the chapter (`input`). "
            "Award full credit when a gold event is represented under any "
            "reasonable summary phrasing; partial credit for events that are "
            "over-merged into one extraction or split across multiple. "
            "Do NOT penalize for over-extraction (extra events). "
            "Return a numeric score between 0.0 and 1.0."
        ),
        evaluation_params=[
            SingleTurnParams.INPUT,
            SingleTurnParams.ACTUAL_OUTPUT,
            SingleTurnParams.EXPECTED_OUTPUT,
        ],
        model=judge,
        threshold=threshold,
    )


def build_all_metrics(judge_client: Any, user_id: str) -> list[GEval]:
    """Convenience: return all 3 narrative-extraction metrics.

    Caller is responsible for sequencing the metrics (or accepting concurrent
    invocations) — each metric will trigger an LM Studio JIT load of its
    distinct judge model.
    """

    return [
        build_narrative_entity_coverage(judge_client, user_id),
        build_relation_factual_groundedness(judge_client, user_id),
        build_event_action_recall(judge_client, user_id),
    ]

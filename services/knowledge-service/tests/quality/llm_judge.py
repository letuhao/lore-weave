"""Back-compat shim — moved to ``loreweave_eval.llm_judge`` (track phase Q0).

The LLM-as-judge scorer was lifted into the shared ``loreweave_eval`` SDK
package so BOTH knowledge-service (R&D today) and learning-service (the
online-eval consumer, phase Q4) import the SAME code. The judge's LLM client is
now an injected ``JudgeLLMClient`` Protocol (see ``loreweave_eval._client``)
rather than a knowledge-service wrapper import. This module re-exports
everything from the new home so existing ``tests.quality.llm_judge`` /
``quality.llm_judge`` imports keep working unchanged. New code should import
from ``loreweave_eval.llm_judge`` directly.
"""

from loreweave_eval import llm_judge as _moved

globals().update(
    {k: v for k, v in vars(_moved).items() if not k.startswith("__")}
)
del _moved

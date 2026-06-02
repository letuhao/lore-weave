"""Back-compat shim — moved to ``loreweave_eval.eval_harness`` (track phase Q0).

The extraction-quality scorer was lifted into the shared ``loreweave_eval`` SDK
package so BOTH knowledge-service (R&D today) and learning-service (the
online-eval consumer, phase Q4) import the SAME code. This module re-exports
everything from the new home so existing ``tests.quality.eval_harness`` /
``quality.eval_harness`` imports keep working unchanged. New code should import
from ``loreweave_eval.eval_harness`` directly.
"""

from loreweave_eval import eval_harness as _moved

# Copy the moved module's full namespace (public AND underscore-prefixed names
# that unit tests reach for) into this shim so every prior import resolves.
globals().update(
    {k: v for k, v in vars(_moved).items() if not k.startswith("__")}
)
del _moved

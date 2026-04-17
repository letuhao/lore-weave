"""K17.10 — Pytest config for opt-in golden-set quality eval.

The quality eval hits a real LLM (K17.4–K17.8 Pass 2 pipeline) and
so should NOT run in the default unit-test pass. Pass
``--run-quality`` to enable.

    cd services/knowledge-service
    pytest tests/quality/ --run-quality -v

Without the flag, tests marked ``@pytest.mark.quality`` are skipped
with a clear reason.
"""

from __future__ import annotations

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-quality",
        action="store_true",
        default=False,
        help="Run the K17.10 opt-in golden-set extraction quality eval.",
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    if config.getoption("--run-quality"):
        return
    skip = pytest.mark.skip(reason="opt-in K17.10 eval; pass --run-quality")
    for item in items:
        if "quality" in item.keywords:
            item.add_marker(skip)

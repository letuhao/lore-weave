"""Pytest config for PlanForge POC."""

import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "live: integration test requiring LM Studio at :1234")

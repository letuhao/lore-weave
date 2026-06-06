"""Unit test for the service log label (D-COMP-M0-LOG-SERVICE-LABEL).

The M0 skeleton copied knowledge-service's logging_config verbatim, which
hardcoded `record.service = "knowledge-service"` — so composition logs were
mislabeled. This locks the correct label."""

from __future__ import annotations

import logging

from app.logging_config import ContextFilter


def test_context_filter_labels_composition_service():
    rec = logging.LogRecord(
        name="x", level=logging.INFO, pathname=__file__, lineno=1,
        msg="hi", args=(), exc_info=None,
    )
    assert ContextFilter().filter(rec) is True
    assert rec.service == "composition-service"

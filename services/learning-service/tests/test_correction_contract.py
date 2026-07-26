"""No-silent-drop wiring test for the correction-event contract.

The dispatcher must realize EXACTLY the declared correction-event contract — no
declared type left unwired (a silent drop of a real correction), and no handler
registered for a type absent from the contract (an undocumented event). Either
drift fails here (and the missing-handler direction also fails build_dispatcher at
startup). This is the CI half of the Agent-Extensibility "no-silent-no-op" rule
applied to the correction event bus.
"""

import logging

import pytest

from app.events.correction_contract import CORRECTION_EVENT_TYPES
from app.events.dispatcher import EventData, EventDispatcher
from app.main import build_dispatcher


def _event(event_type: str) -> EventData:
    return EventData(
        stream="loreweave:events:glossary",
        message_id="1-0",
        event_type=event_type,
        aggregate_id="a",
        payload={},
        source="s",
        raw={},
    )


def test_dispatcher_realizes_exactly_the_correction_contract():
    registered = set(build_dispatcher().registered_types)
    contract = set(CORRECTION_EVENT_TYPES)

    unwired = contract - registered  # declared but no handler → silent drop
    undocumented = registered - contract  # handled but not in the contract → drift
    assert not unwired, f"declared correction types with NO handler (silent drop): {sorted(unwired)}"
    assert not undocumented, (
        f"handlers registered for types absent from the contract: {sorted(undocumented)} — "
        "add them to app/events/correction_contract.py or remove the registration"
    )


def test_build_dispatcher_fails_fast_on_a_missing_handler(monkeypatch):
    """Prove the startup guard bites: inject an extra declared type with no handler
    and confirm build_dispatcher raises rather than silently under-covering."""
    import app.main as main

    patched = CORRECTION_EVENT_TYPES | {"phantom.correction_never_registered"}
    monkeypatch.setattr(main, "CORRECTION_EVENT_TYPES", patched)
    try:
        main.build_dispatcher()
    except RuntimeError as exc:
        assert "phantom.correction_never_registered" in str(exc)
    else:
        raise AssertionError("build_dispatcher must fail-fast when a contract type has no handler")


@pytest.mark.asyncio
async def test_unhandled_correction_event_warns(caplog):
    """Runtime half of no-silent-drop: an unhandled CORRECTION-class event (e.g. the
    known-unhandled glossary.entity_merged, or any future producer rename) is skipped
    but logged at WARNING so a producer-side drop is VISIBLE, not silent."""
    d = EventDispatcher()  # no handlers registered
    with caplog.at_level(logging.WARNING, logger="app.events.dispatcher"):
        handled = await d.dispatch(_event("glossary.entity_merged"))
    assert handled is False
    warned = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("glossary.entity_merged" in r.getMessage() for r in warned), (
        "an unhandled correction-class event must WARN"
    )


@pytest.mark.asyncio
async def test_unhandled_noncorrection_event_stays_quiet(caplog):
    """A non-correction firehose event with no handler must NOT warn (else the WARN
    channel is spam and the correction signal is lost in the noise)."""
    d = EventDispatcher()
    with caplog.at_level(logging.WARNING, logger="app.events.dispatcher"):
        await d.dispatch(_event("glossary.entity_created"))
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]

"""The discovery path is not suppressible. 281 of 315 tools depend on it.

🔴 WHY THIS EXISTS. Reviewing the rail's action-space gating on 2026-08-13 I read
`GATE_STEP_LOCK`'s description — *"only the CURRENT step's tool (per pinned rail) stays
advertised"* — and concluded that the rail could delete the lazy tail, making the two subsystems
mutually exclusive at one config value. That was wrong: `rail_gate_suppressions` returns only rail
STEP tools, and `_advertise_discovery_tools` applies `suppress_names` **inside the
`for name in active_tool_names` loop only** — the always-on core is added before it, unconditionally.

The invariant was already true and already stated in `rail_gate_suppressions`' docstring ("this can
never strand the agent's discovery/answer path"). It just wasn't *pinned*, so nothing would have
caught it being broken — and a misreading of it cost real review time.

`tool_list`/`tool_load` are the only route to a tool the 2000-token hot seed could not carry. A
suppressor that reached them would not degrade discovery, it would end it: the model would have no
way to learn that the tool it needs exists.
"""
import pytest

from app.services.stream_service import _advertise_discovery_tools

#: Every set that is unioned into `_suppress` at the advertise chokepoint. If a new suppressor is
#: added and not listed here, this file is the place that should have stopped it.
SUPPRESSOR_SOURCES = [
    "rail_gate_suppressions (done_suppress / step_lock)",
    "failure_suppress (repeated-failure breaker)",
    "repeat_read_suppress (repeated-READ breaker)",
    "oneshot deadvertise",
]

CORE = {"tool_list", "tool_load"}


def _names(tools):
    out = set()
    for t in tools or []:
        fn = t.get("function") if isinstance(t, dict) else None
        if isinstance(fn, dict) and fn.get("name"):
            out.add(fn["name"])
    return out


class TestNoSuppressorCanReachTheDiscoveryCore:
    def test_suppressing_literally_everything_still_leaves_the_discovery_core(self):
        """The strongest possible suppressor: every name the chokepoint knows about. Whatever a
        future breaker computes, it is a subset of this."""
        catalog = {
            "composition_list_outline": {"function": {"name": "composition_list_outline"}},
            "plan_propose_spec": {"function": {"name": "plan_propose_spec"}},
            "tool_list": {"function": {"name": "tool_list"}},
            "tool_load": {"function": {"name": "tool_load"}},
        }
        advertised = _advertise_discovery_tools(
            catalog, set(catalog), [], suppress_names=set(catalog),
        )
        assert CORE <= _names(advertised), (
            "a suppressor reached tool_list/tool_load — the lazy tail is the only route to the "
            "281 tools that do not fit the hot seed"
        )

    def test_the_suppressor_still_works_on_ordinary_tools(self):
        """The control. A test that only asserts the core survives would also pass if
        `suppress_names` had been silently disabled altogether."""
        catalog = {
            "composition_list_outline": {"function": {"name": "composition_list_outline"}},
            "plan_propose_spec": {"function": {"name": "plan_propose_spec"}},
        }
        advertised = _advertise_discovery_tools(
            catalog, set(catalog), [], suppress_names={"plan_propose_spec"},
        )
        got = _names(advertised)
        assert "composition_list_outline" in got
        assert "plan_propose_spec" not in got

    @pytest.mark.parametrize("source", SUPPRESSOR_SOURCES)
    def test_every_known_suppressor_feeds_the_same_single_parameter(self, source):
        """All four suppressors union into one `_suppress` set handed to one parameter. That is
        what makes the test above cover them all — if a future one bypassed `suppress_names` and
        filtered the advertised list itself, this invariant would silently stop holding."""
        import pathlib
        src = (pathlib.Path(__file__).resolve().parents[1]
               / "app" / "services" / "stream_service.py").read_text(encoding="utf-8")
        assert "suppress_names=_suppress," in src
        assert src.count("suppress_names=") == 1, (
            f"more than one advertise call takes suppress_names — {source} may be reaching the "
            "wire by another path"
        )

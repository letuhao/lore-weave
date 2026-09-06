"""T25c — the arming signal must stay WIRED, not merely defined.

`knowledge_vector_dual_write_total` is pre-seeded at import, so an unarmed service exposes
all eight series at 0.0 — byte for byte what an armed-but-unwritten one exposes. On
2026-08-21 that cost a real misdiagnosis: `soak-armed-gate` read the family's absence as
"KNOWLEDGE_VECTOR_DB_URL is unset" when the variable had been set for nine days and the
running image was simply too old to carry the metric, and it read an unarmed service's
pre-seeded zeros as ARMED_IDLE. The gauge below is what makes the two distinguishable.

The wiring was proven live in both directions (same image: DSN set -> 1, DSN cleared -> 0),
but a live proof does not survive the next edit. These tests fail if the `.set()` call
leaves the lifespan, which is the only way the gauge can silently go stale at 1.
"""
import ast
import pathlib

from app.metrics import registry, vector_dual_write_armed

_MAIN = pathlib.Path(__file__).resolve().parents[2] / "app" / "main.py"


def _lifespan_node() -> ast.AsyncFunctionDef:
    tree = ast.parse(_MAIN.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "lifespan":
            return node
    raise AssertionError("app/main.py no longer defines an async `lifespan`")


def test_the_arming_gauge_is_SET_inside_the_lifespan_not_just_imported():
    """Parsed, not grepped. A `grep` for the gauge name matches the import line and every
    comment mentioning it — the check would stay green with the call deleted, which is the
    exact "criterion that cannot fail" this whole batch exists to remove.
    """
    calls = [
        n for n in ast.walk(_lifespan_node())
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "set"
        and isinstance(n.func.value, ast.Name)
        and n.func.value.id == "vector_dual_write_armed"
    ]
    assert calls, (
        "app/main.py's lifespan no longer calls vector_dual_write_armed.set(...) — the "
        "arming gauge would keep whatever value it was last given, and soak-armed-gate "
        "would read an UNARMED service as armed"
    )


def test_the_arming_value_is_DERIVED_from_the_dsn_setting_not_a_literal():
    """`.set(1)` would satisfy the test above and be permanently, silently wrong: every
    service would report armed. The argument has to mention the DSN setting.
    """
    node = _lifespan_node()
    call = next(
        n for n in ast.walk(node)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "set"
        and isinstance(n.func.value, ast.Name)
        and n.func.value.id == "vector_dual_write_armed"
    )
    src = ast.dump(call)
    assert "knowledge_vector_db_url" in src, (
        "the arming gauge is set from something other than settings.knowledge_vector_db_url "
        f"— a hardcoded value makes every deployment look armed. Got: {ast.unparse(call)}"
    )


def test_the_gauge_defaults_to_ZERO_so_an_unreached_lifespan_never_reads_armed():
    """Fail-closed. If the lifespan dies before the arming line, the gauge must still be
    exposed at 0 — an absent-or-1 default would let a half-started service read as armed.
    """
    value = registry.get_sample_value("knowledge_vector_dual_write_armed")
    assert value == 0.0, (
        f"expected the arming gauge to be exposed at 0 before the lifespan runs, got {value!r}"
    )
    assert vector_dual_write_armed is not None

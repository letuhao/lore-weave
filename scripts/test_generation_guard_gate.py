"""Teeth for `scripts/generation-guard-gate.py`.

Every test here is one of the injections run by hand against the real contract on 2026-08-01,
pinned so the gate cannot quietly lose a check. The S12 gate went green on its own motivating
example THREE times — once because a doc comment named the crate, once because a workspace list
did, and once because the gate's own docstring did — so "a mention is not a definition" gets its
own test rather than a comment.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

_ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location("ggg", _ROOT / "scripts" / "generation-guard-gate.py")
ggg = importlib.util.module_from_spec(_SPEC)
sys.modules["ggg"] = ggg
_SPEC.loader.exec_module(ggg)

_REAL = _ROOT / "contracts" / "generation-paths.yaml"


@pytest.fixture
def contract(monkeypatch, tmp_path):
    """Point the gate at a COPY. A teeth test that edits the real contract is one interrupted
    run away from committing an injected row."""
    def _use(spec: dict) -> Path:
        p = tmp_path / "generation-paths.yaml"
        p.write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")
        monkeypatch.setattr(ggg, "CONTRACT", p)
        return p
    return _use


def _base() -> dict:
    spec = yaml.safe_load(_REAL.read_text(encoding="utf-8"))
    return spec


def _run(argv=()) -> int:
    monkey = list(sys.argv)
    sys.argv = ["generation-guard-gate.py", *argv]
    try:
        return ggg.main()
    finally:
        sys.argv = monkey


def test_the_real_contract_passes(contract):
    """The control. Without it every test below could pass because the gate is broken."""
    contract(_base())
    assert _run() == 0


def test_a_phantom_FILE_reds(contract):
    spec = _base()
    spec["paths"].append({
        "id": "fake.phantom", "service": "x", "language": "python",
        "file": "services/composition-service/app/engine/does_not_exist.py",
        "symbol": "run_it", "status": "guarded", "coverage_field": "guard_status"})
    contract(spec)
    assert _run() == 1


def test_a_symbol_that_only_APPEARS_IN_A_COMMENT_reds(contract):
    """The S12 shape. `D-CANON-GUARD-SKIPPED-WHOLE-CHAPTER` is all over canon_reflect.py's
    comments and is not a definition of anything."""
    spec = _base()
    spec["paths"].append({
        "id": "fake.comment_only", "service": "x", "language": "python",
        "file": "services/composition-service/app/engine/canon_reflect.py",
        "symbol": "D_CANON_GUARD_SKIPPED_WHOLE_CHAPTER",
        "status": "guarded", "coverage_field": "guard_status"})
    contract(spec)
    assert _run() == 1


def test_a_guarded_claim_with_no_emitted_coverage_field_reds(contract):
    """"It is guarded" is a claim. The field being emitted is the evidence."""
    spec = _base()
    spec["paths"].append({
        "id": "fake.claims_guarded", "service": "x", "language": "python",
        "file": "services/composition-service/app/engine/exit_state.py",
        "symbol": "render_carried_cast", "status": "guarded",
        "coverage_field": "guard_status"})
    contract(spec)
    assert _run() == 1


def test_an_unguarded_gap_with_no_owner_reds(contract):
    spec = _base()
    spec["paths"].append({
        "id": "fake.untracked", "service": "x", "language": "python",
        "file": "services/composition-service/app/engine/exit_state.py",
        "symbol": "render_carried_cast", "status": "unguarded"})
    contract(spec)
    assert _run() == 1


def test_an_unguarded_gap_WITH_an_owner_is_accepted(contract):
    """The control for the test above: a tracked gap is the honest state, not a failure. If
    this reddened, the gate would force every unfinished path to be deleted or lied about."""
    spec = _base()
    spec["paths"].append({
        "id": "fake.tracked", "service": "x", "language": "python",
        "file": "services/composition-service/app/engine/exit_state.py",
        "symbol": "render_carried_cast", "status": "unguarded", "owner": "S9"})
    contract(spec)
    assert _run() == 0


def test_the_model_gateway_caller_count_GROWING_reds(contract):
    spec = _base()
    spec["discovery"]["baseline"]["python"] -= 1
    contract(spec)
    assert _run() == 1


def test_a_missing_baseline_reds_rather_than_being_skipped(contract):
    """An absent number must not read as "no limit". That is the silent-empty shape."""
    spec = _base()
    del spec["discovery"]["baseline"]["rust"]
    contract(spec)
    assert _run() == 1


def test_an_unknown_status_reds(contract):
    spec = _base()
    spec["paths"].append({
        "id": "fake.unknown_status", "service": "x", "language": "python",
        "file": "services/composition-service/app/engine/exit_state.py",
        "symbol": "render_carried_cast", "status": "probably_fine"})
    contract(spec)
    assert _run() == 1


def test_an_unknown_language_reds(contract):
    """A row in a language the gate cannot parse must FAIL, not be skipped — skipping is how a
    whole language quietly leaves the registry's coverage."""
    spec = _base()
    spec["paths"].append({
        "id": "fake.cobol", "service": "x", "language": "cobol",
        "file": "services/composition-service/app/engine/exit_state.py",
        "symbol": "render_carried_cast", "status": "guarded",
        "coverage_field": "guard_status"})
    contract(spec)
    assert _run() == 1


# ── the `via` hop (2026-08-01) ────────────────────────────────────────────────────────────
# Added when consolidating six hand-written canon envelopes into one builder made the gate
# blind: the coverage field left the path's file while the behaviour was unchanged. Following
# the hop is right; the risk is that "follow a hop" degenerates into "accept a claim", so both
# halves get an injection.

def test_a_via_hop_whose_EMITTER_does_not_emit_the_field_reds(contract, capsys):
    """The first version of this check used a bare substring test and PASSED its own injection:
    renaming the emitted `"guard_status"` key left `def guard_status` and four docstring
    mentions behind. Only the quoted-KEY form is evidence.

    The assertion is on the REASON, not on the exit code. The first draft of this test used a
    `via` the path does not call, so it reddened on the OTHER branch while claiming to test
    this one — green for a reason the name disowns, which is the failure this whole file exists
    to catch. `packer/lenses.py` genuinely calls `render_carried_cast`, so the hop is TAKEN and
    the only thing left to fail is the emitter."""
    spec = _base()
    spec["paths"].append({
        "id": "fake.via_empty_emitter", "service": "x", "language": "python",
        "file": "services/composition-service/app/packer/lenses.py",
        "symbol": "gather_carried_cast", "status": "guarded",
        "coverage_field": "guard_status",
        "via": {"file": "services/composition-service/app/engine/exit_state.py",
                "symbol": "render_carried_cast"}})
    contract(spec)
    assert _run() == 1
    out = capsys.readouterr().out + capsys.readouterr().err
    assert "does not EMIT" in out, out


def test_a_via_hop_the_path_never_CALLS_reds(contract, capsys):
    """The other half. A row may not borrow evidence from a builder it does not use."""
    spec = _base()
    spec["paths"].append({
        "id": "fake.via_uncalled", "service": "x", "language": "python",
        "file": "services/composition-service/app/engine/exit_state.py",
        "symbol": "render_carried_cast", "status": "guarded",
        "coverage_field": "guard_status",
        "via": {"file": "services/composition-service/app/engine/canon_check.py",
                "symbol": "canon_envelope"}})
    contract(spec)
    assert _run() == 1
    out = capsys.readouterr().out
    assert "never CALLS it" in out, out


def test_a_via_hop_with_no_declaration_still_reds(contract):
    """No implicit hops. A path whose file lacks the field and declares no `via` is exactly the
    case the gate existed for before this feature, and it must not have become passable."""
    spec = _base()
    spec["paths"].append({
        "id": "fake.no_via", "service": "x", "language": "python",
        "file": "services/composition-service/app/engine/exit_state.py",
        "symbol": "render_carried_cast", "status": "guarded",
        "coverage_field": "guard_status"})
    contract(spec)
    assert _run() == 1

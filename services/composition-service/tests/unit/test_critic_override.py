"""C26 (dị bản M3) — derivative critic dimension: override enforcement.

The dimension activates ONLY for a DERIVATIVE Work (`source_work_id` set), LOADS
the active `entity_override[]` via C25's resolution path (reuse — NO re-merge), and
flags an OVERRIDE SLIP: an overridden entity field that reverts to its canon/base
value in the generated passage → a structured finding (entity + field +
expected-vs-found). It also checks DELTA INTERNAL CONSISTENCY (the scene must not
contradict an established delta fact). Deterministic + AI-free (composition has no
AI imports). A WIRING test proves the dimension actually FIRES at the critique call
site (anti-no-op — the nil-tolerant-decorator bug class).
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from app.engine import critic_override as co


def _ov(target, fields):
    return SimpleNamespace(target_entity_id=target, overridden_fields=fields)


# ── (1) flags an INJECTED override slip ──

def test_flags_override_slip_with_expected_vs_found():
    """An overridden field that reverts to the canon/base value in the passage is
    an override slip — the finding names entity + field + expected + found."""
    tid = uuid4()
    base_present = [{"entity_id": str(tid), "name": "张若尘",
                     "summary": "a young man, the male lead"}]
    overrides = [_ov(tid, {"name": "张若尘", "description": "now a woman (genderbend)"})]
    passage = "张若尘 stood there, a young man, the male lead of the era."
    findings = co.detect_override_findings(
        passage, overrides, base_present, target_anchor={})
    slips = [f for f in findings if f["kind"] == "override_slip"]
    assert len(slips) == 1
    f = slips[0]
    assert f["entity_id"] == str(tid)
    assert f["field"] == "description"
    assert "now a woman" in f["expected"]
    assert "a young man" in f["found"]  # the reverted-to canon value appears


def test_slip_matches_when_target_resolves_via_anchor():
    """The override `target_entity_id` is a KNOWLEDGE node id; the base present item
    keys on the GLOSSARY anchor — C25's anchor map reconciles them (reuse)."""
    knode = uuid4()
    anchor = uuid4()
    base_present = [{"entity_id": str(anchor), "name": "X", "summary": "the old king"}]
    overrides = [_ov(knode, {"description": "the new queen"})]
    passage = "X ruled as the old king of the realm."
    findings = co.detect_override_findings(
        passage, overrides, base_present, target_anchor={str(knode): str(anchor)})
    assert any(f["kind"] == "override_slip" and f["entity_id"] == str(anchor)
               for f in findings)


# ── (2) PASSES a compliant scene (override honoured → no finding) ──

def test_compliant_scene_no_finding():
    """The override is honoured (overridden value present, base value absent) → no
    override-slip finding."""
    tid = uuid4()
    base_present = [{"entity_id": str(tid), "name": "张若尘",
                     "summary": "a young man, the male lead"}]
    overrides = [_ov(tid, {"description": "now a woman (genderbend)"})]
    passage = "张若尘, now a woman, the heroine, raised her hand."
    findings = co.detect_override_findings(
        passage, overrides, base_present, target_anchor={})
    assert not any(f["kind"] == "override_slip" for f in findings)


def test_no_slip_when_neither_value_appears():
    """Neither the base nor the override value appears (the entity isn't described
    on this field) → not a slip (the field simply wasn't asserted)."""
    tid = uuid4()
    base_present = [{"entity_id": str(tid), "name": "Y", "summary": "the old king"}]
    overrides = [_ov(tid, {"description": "the new queen"})]
    passage = "The rain fell on the empty courtyard."
    findings = co.detect_override_findings(
        passage, overrides, base_present, target_anchor={})
    assert not any(f["kind"] == "override_slip" for f in findings)


# ── (3) delta internal-consistency check ──

def test_delta_internal_consistency_violation():
    """An overridden field that ALSO added a canon rule but whose base value
    reverts in the passage contradicts an established delta fact → a
    delta_inconsistency finding (in addition to the slip)."""
    tid = uuid4()
    base_present = [{"entity_id": str(tid), "name": "Z", "summary": "a loyal knight"}]
    overrides = [_ov(tid, {"description": "a traitor now",
                           "canon_rule": "Z betrayed the crown in this dị bản"})]
    passage = "Z, a loyal knight, knelt before the crown he served."
    findings = co.detect_override_findings(
        passage, overrides, base_present, target_anchor={})
    assert any(f["kind"] == "delta_inconsistency" for f in findings)
    dc = next(f for f in findings if f["kind"] == "delta_inconsistency")
    assert "betrayed the crown" in dc["rule"]


def test_compliant_scene_no_delta_inconsistency():
    tid = uuid4()
    base_present = [{"entity_id": str(tid), "name": "Z", "summary": "a loyal knight"}]
    overrides = [_ov(tid, {"description": "a traitor now",
                           "canon_rule": "Z betrayed the crown in this dị bản"})]
    passage = "Z, a traitor now, slipped through the gate at dusk."
    findings = co.detect_override_findings(
        passage, overrides, base_present, target_anchor={})
    assert not any(f["kind"] == "delta_inconsistency" for f in findings)


# ── (6) does NOT flag an INHERITED (non-overridden) entity as a slip ──

def test_inherited_entity_not_flagged():
    """A present entity with NO override is never a slip even though its base value
    appears in the passage — only OVERRIDDEN fields are enforced."""
    overridden = uuid4()
    inherited = uuid4()
    base_present = [
        {"entity_id": str(overridden), "name": "Hero", "summary": "a young man"},
        {"entity_id": str(inherited), "name": "Sage", "summary": "an old mentor"},
    ]
    overrides = [_ov(overridden, {"description": "now a woman"})]
    # the inherited Sage appears at its canon value — must NOT be flagged.
    passage = "Hero, now a woman, sought the Sage, an old mentor, for counsel."
    findings = co.detect_override_findings(
        passage, overrides, base_present, target_anchor={})
    assert all(f.get("entity_id") != str(inherited) for f in findings)


def test_empty_overrides_no_findings():
    findings = co.detect_override_findings("any prose", [], [], target_anchor={})
    assert findings == []


def test_bio_precedence_matches_c25_summary_wins(monkeypatch):
    """Adversary M1 — when an override carries BOTH `description` and `summary`, the
    EXPECTED value MUST be `summary` (the value C25's apply_entity_overrides grounds
    the drafter on). Otherwise the critic flags against a value the model was never
    told to use (two-sources-of-truth drift)."""
    tid = uuid4()
    base_present = [{"entity_id": str(tid), "name": "X", "summary": "the old king"}]
    overrides = [_ov(tid, {"description": "DESC value", "summary": "SUMMARY value"})]
    # passage honours `summary` (the C25 winner) → NO slip; if the critic wrongly
    # treated `description` as expected, this would (incorrectly) flag a slip.
    passage = "X appeared, SUMMARY value, before the court."
    findings = co.detect_override_findings(
        passage, overrides, base_present, target_anchor={})
    assert not any(f["kind"] == "override_slip" for f in findings)
    # and the expected value surfaced in a slip IS the summary, not the description.
    passage2 = "X appeared, the old king, before the court."  # reverted to base
    f2 = co.detect_override_findings(passage2, overrides, base_present, target_anchor={})
    slip = next(f for f in f2 if f["kind"] == "override_slip")
    assert slip["expected"] == "SUMMARY value"


# ── (5) does NOT activate on a canon Work (no source_work_id) ──

class _StubDerivContext:
    def __init__(self, source_project_id, overrides):
        self.source_project_id = source_project_id
        self.branch_point = None
        self.overrides = overrides


async def test_no_activation_on_canon_work(monkeypatch):
    """A Work with no source (build_derivative_context → empty) → the dimension
    does NOT fire (no base fetch, no findings)."""
    work = SimpleNamespace(source_work_id=None, project_id=uuid4(), book_id=uuid4(),
                           id=uuid4())

    async def fake_build(*a, **k):
        return _StubDerivContext(source_project_id=None, overrides=[])

    base_calls = []

    async def fake_base(*a, **k):
        base_calls.append(1)
        return []

    monkeypatch.setattr(co, "build_derivative_context", fake_build)
    out = await co.critique_overrides(
        work=work, user_id=uuid4(), passage="prose", bearer="t",
        works_repo=object(), derivatives_repo=object(),
        glossary=object(), knowledge=object(), book=object(),
        _base_present_fn=fake_base,
    )
    assert out == []           # no findings for a canon Work
    assert base_calls == []     # base lens NEVER queried for a canon Work


# ── (4) WIRING — the dimension actually FIRES for a derivative Work ──

async def test_wiring_dimension_fires_for_derivative(monkeypatch):
    """Spy-injection proof: for a DERIVATIVE Work, critique_overrides resolves the
    derivative context AND queries the base present lens AND runs the detector — a
    wired-but-uninvoked dimension would skip these (the nil-tolerant-decorator bug
    class)."""
    src_proj = uuid4()
    tid = uuid4()
    work = SimpleNamespace(source_work_id=uuid4(), project_id=uuid4(),
                           book_id=uuid4(), id=uuid4())

    derivctx = _StubDerivContext(
        source_project_id=src_proj,
        overrides=[_ov(tid, {"description": "now a woman"})])

    built = []

    async def fake_build(*a, **k):
        built.append(k.get("derivatives_repo"))
        return derivctx

    base_calls = []

    async def fake_base(*, project_id, **k):
        base_calls.append(project_id)
        return [{"entity_id": str(tid), "name": "张若尘", "summary": "a young man"}]

    monkeypatch.setattr(co, "build_derivative_context", fake_build)

    detector_ran = {}
    real_detect = co.detect_override_findings

    def spy_detect(passage, overrides, base_present, **k):
        detector_ran["called"] = True
        return real_detect(passage, overrides, base_present, **k)

    monkeypatch.setattr(co, "detect_override_findings", spy_detect)

    out = await co.critique_overrides(
        work=work, user_id=uuid4(), passage="张若尘 was a young man.",
        bearer="t", works_repo=object(), derivatives_repo=object(),
        glossary=object(), knowledge=object(), book=object(),
        _base_present_fn=fake_base,
    )
    # PROOF the dimension fired end-to-end for a derivative:
    assert built and built[0] is not None        # derivative context resolved
    assert base_calls == [src_proj]               # BASE present lens queried (source project)
    assert detector_ran.get("called") is True     # the detector actually ran
    assert any(f["kind"] == "override_slip" for f in out)  # and produced the slip finding

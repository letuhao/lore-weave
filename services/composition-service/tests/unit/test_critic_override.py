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


# ── D-C26-CRITIC-FN edge (2): substring no longer hides a slip ──

def test_substring_override_no_longer_hides_slip():
    """CFN edge: the override value is a SUBSTRING of the base value. A naive
    `override in passage` is True whenever the BASE value is present (the override
    text is contained inside it) → the slip is hidden. The precise check must NOT
    treat the override as 'present' when its only occurrence is inside the base
    value the scene reverted to."""
    tid = uuid4()
    base_present = [{"entity_id": str(tid), "name": "X", "summary": "a young man"}]
    # override "young" is a substring of the base "a young man".
    overrides = [_ov(tid, {"description": "young"})]
    # the passage reverts to the BASE value; "young" appears ONLY inside it.
    passage = "X stood there, a young man of the era."
    findings = co.detect_override_findings(
        passage, overrides, base_present, target_anchor={})
    assert any(f["kind"] == "override_slip" for f in findings), (
        "the base value reverted and the override only appears as a substring of it "
        "→ this IS a slip and must be flagged"
    )


def test_substring_override_honoured_when_standalone():
    """Counter-case to the above: the override value DOES appear standalone (outside
    any base occurrence) → it was honoured → NO slip (guards against a false-positive
    from the substring fix)."""
    tid = uuid4()
    base_present = [{"entity_id": str(tid), "name": "X", "summary": "a young man"}]
    overrides = [_ov(tid, {"description": "young"})]
    # "young" stands on its own here; the base phrase "a young man" is absent.
    passage = "X, young and fierce, drew the blade."
    findings = co.detect_override_findings(
        passage, overrides, base_present, target_anchor={})
    assert not any(f["kind"] == "override_slip" for f in findings)


# ── FIX 1 (HIGH) — CJK-blind slip detection (Python \w matches CJK ideographs) ──

def test_phrase_occurs_cjk_value_flanked_by_cjk():
    """A Chinese value flanked by Chinese chars: Python's \\w matches CJK, so the old
    word-boundary regex (?<!\\w)…(?!\\w) NEVER matched a CJK value inside CJK prose —
    the gate could not fire for Chinese. Containment is the correct match for a
    script with no word separators."""
    passage = co._norm_name("张若尘乃少年天才，名震天下。")
    assert co._phrase_occurs(passage, "少年天才") is True


def test_phrase_occurs_cjk_value_at_string_head():
    """A CJK value at the very start of the prose (no preceding char) still matches."""
    passage = co._norm_name("故事的主角张若尘登场了")
    assert co._phrase_occurs(passage, "张若尘") is True


def test_phrase_occurs_english_word_boundary_still_precise():
    """The ASCII path KEEPS word-boundary precision: 'king' must NOT match inside
    'kingdom' (the substring-of-base false-positive edge-2 fixed)."""
    assert co._phrase_occurs(co._norm_name("the kingdom fell"), "king") is False
    assert co._phrase_occurs(co._norm_name("the old king fell"), "king") is True


def test_phrase_occurs_mixed_cjk_ascii_value():
    """A value whose edges are CJK is matched by containment even when an ASCII char
    is adjacent (CJK has no word boundary against ASCII)."""
    assert co._phrase_occurs(co._norm_name("X张若尘Y"), "张若尘") is True


def test_cjk_base_bio_reverts_inside_chinese_prose_FIRES_slip():
    """End-to-end FIX 1: a CJK base bio that reverts INSIDE Chinese prose (flanked by
    Chinese chars) now FIRES the slip — the old \\w boundary made this a silent
    false-negative (the gate never fired for Chinese)."""
    tid = uuid4()
    base_present = [{"entity_id": str(tid), "name": "张若尘", "summary": "少年天才"}]
    overrides = [_ov(tid, {"description": "现在是女性"})]  # now a woman
    # the scene reverts to the canon CJK bio, flanked by Chinese chars; override absent.
    passage = "张若尘乃少年天才，名震天下，威风凛凛。"
    findings = co.detect_override_findings(
        passage, overrides, base_present, target_anchor={})
    assert any(f["kind"] == "override_slip" for f in findings)


def test_cjk_compliant_scene_no_slip():
    """Counter-case: a CJK override that IS honoured (override value present, base
    value absent) → NO slip (guards against a CJK false-positive)."""
    tid = uuid4()
    base_present = [{"entity_id": str(tid), "name": "张若尘", "summary": "少年天才"}]
    overrides = [_ov(tid, {"description": "现在是女性"})]
    passage = "张若尘现在是女性，倾国倾城，名震天下。"  # honoured; canon "少年天才" absent
    findings = co.detect_override_findings(
        passage, overrides, base_present, target_anchor={})
    assert not any(f["kind"] == "override_slip" for f in findings)


def test_cjk_bio_trailing_punctuation_tolerant_FIRES_slip():
    """FIX 1 (live-found) — the glossary bio carries trailing sentence punctuation
    (`…重生复仇。`) that prose ends with a comma instead (`…重生复仇，`). The matcher
    trims edge punctuation off the value so a `。`-terminated bio still matches the
    same phrase mid-sentence → the slip FIRES (else a punctuation mismatch silently
    hides every Chinese slip — the live-smoke surfaced this)."""
    tid = uuid4()
    base_present = [{"entity_id": str(tid), "name": "张若尘",
                     "summary": "前世昆仑界明帝独子，被池瑶杀害后重生复仇。"}]
    overrides = [_ov(tid, {"description": "现在是女性"})]
    passage = "张若尘乃前世昆仑界明帝独子，被池瑶杀害后重生复仇，威风凛凛，名震天下。"
    findings = co.detect_override_findings(
        passage, overrides, base_present, target_anchor={})
    assert any(f["kind"] == "override_slip" for f in findings)


def test_edge_punctuation_does_not_match_empty_or_bare_punct():
    """The edge-trim must not turn a punctuation-only / empty value into a spurious
    universal match."""
    assert co._phrase_occurs(co._norm_name("anything at all"), "。，！") is False
    assert co._phrase_occurs(co._norm_name("anything at all"), "   ") is False


def test_cjk_override_honoured_helper():
    """_override_honoured for CJK: the override value asserted standalone (base
    stripped first) → honoured. Containment, not \\w boundary."""
    passage = co._norm_name("张若尘现在是女性，名震天下。")
    assert co._override_honoured(passage, "现在是女性", "少年天才") is True
    # and when the override only appears INSIDE the reverted base → NOT honoured.
    passage2 = co._norm_name("张若尘乃少年天才，威风凛凛。")
    assert co._override_honoured(passage2, "少年", "少年天才") is False


# ── D-C26-CRITIC-FN edge (3): delta_inconsistency fires INDEPENDENTLY ──

def test_delta_inconsistency_fires_without_bio_override():
    """CFN edge: an override that adds a canon_rule but NO bio field (description/
    summary). The base value still surfaces in the passage, contradicting the
    declared delta rule. delta_inconsistency must fire EVEN THOUGH the bio-slip
    path can't (there is no override bio to compare) — it is decoupled."""
    tid = uuid4()
    base_present = [{"entity_id": str(tid), "name": "Z", "summary": "a loyal knight"}]
    # canon_rule ONLY — no description/summary override.
    overrides = [_ov(tid, {"canon_rule": "Z betrayed the crown in this dị bản"})]
    passage = "Z, a loyal knight, knelt before the crown he served."
    findings = co.detect_override_findings(
        passage, overrides, base_present, target_anchor={})
    assert any(f["kind"] == "delta_inconsistency" for f in findings)
    # and NO override_slip (there is no bio override to slip).
    assert not any(f["kind"] == "override_slip" for f in findings)


def test_delta_inconsistency_silent_when_base_absent():
    """No false-positive: a canon_rule override whose base value does NOT appear in
    the passage is not a delta contradiction (the rule simply wasn't touched)."""
    tid = uuid4()
    base_present = [{"entity_id": str(tid), "name": "Z", "summary": "a loyal knight"}]
    overrides = [_ov(tid, {"canon_rule": "Z betrayed the crown in this dị bản"})]
    passage = "The banners snapped in the cold wind over the empty field."
    findings = co.detect_override_findings(
        passage, overrides, base_present, target_anchor={})
    assert not any(f["kind"] == "delta_inconsistency" for f in findings)


# ── D-C26-CRITIC-FN edge (1): base set scoped to the packer's grounded cast ──

async def test_gather_base_present_scopes_to_grounded_cast(monkeypatch):
    """CFN edge: the base lens must mirror the packer's ACTUALLY-grounded set
    (scene cast + scene query), not a broad independent project-wide query — else
    the critic compares against a present item the packer never grounded the drafter
    on. _gather_base_present forwards the scene's present_entity_ids + query through
    to gather_present (reusing C25's resolution scope)."""
    captured = {}

    async def fake_gather_present(glossary, knowledge, *, book_id, user_id,
                                  project_id, bearer, query, present_entity_ids):
        captured["query"] = query
        captured["present_entity_ids"] = present_entity_ids
        return [], set()

    import app.packer.lenses as lenses
    monkeypatch.setattr(lenses, "gather_present", fake_gather_present)

    cast = [uuid4(), uuid4()]
    await co._gather_base_present(
        glossary=object(), knowledge=object(), book=object(),
        book_id=uuid4(), user_id=uuid4(), project_id=uuid4(), bearer="t",
        present_entity_ids=cast, query="the duel at dawn",
    )
    assert captured["present_entity_ids"] == cast    # scene cast forwarded
    assert captured["query"] == "the duel at dawn"   # scene query forwarded


# ── FIX 4 (MED) — base lens GUARANTEES the override target is present (bio) ──

async def test_base_lens_augments_missing_override_target_from_glossary(monkeypatch):
    """Post-C24 the override `target_entity_id` is a GLOSSARY anchor. The explicit pin
    (present_entity_ids → knowledge.get_entity) 404s on a glossary anchor and only adds
    RELATIONS anyway — not the BIO. If the broad semantic read excludes the target (an
    empty query returns NOTHING — the live-found hole), its bio never surfaces and the
    slip is invisible. _gather_base_present must AUGMENT the missing target from the
    book-scoped glossary FTS (the same source the packer falls back to), keyed on the
    glossary anchor — so the bio is present for the detector."""
    anchor = uuid4()
    captured = {}

    async def fake_gather_present(glossary, knowledge, *, book_id, user_id,
                                  project_id, bearer, query, present_entity_ids):
        captured["present_entity_ids"] = present_entity_ids
        return [], set()  # broad read surfaces NOTHING (empty query → semantic empty)

    import app.packer.lenses as lenses
    monkeypatch.setattr(lenses, "gather_present", fake_gather_present)

    class FakeGlossary:
        async def select_for_context(self, book_id, user_id, query, **k):
            captured["augment_query"] = query
            return [{"entity_id": str(anchor), "cached_name": "张若尘",
                     "short_description": "前世昆仑界明帝独子，被池瑶杀害后重生复仇。"}]

    present = await co._gather_base_present(
        glossary=FakeGlossary(), knowledge=object(), book=object(),
        book_id=uuid4(), user_id=uuid4(), project_id=uuid4(), bearer="t",
        present_entity_ids=[anchor], query="",
        override_target_anchors=[str(anchor)],
    )
    # the override target is now present WITH its canon bio (from the glossary augment).
    item = next(p for p in present if str(p["entity_id"]) == str(anchor))
    assert "重生复仇" in item["summary"]
    assert captured["augment_query"] == ""  # book-scoped FTS (no query needed)


async def test_base_lens_no_augment_when_target_already_present(monkeypatch):
    """No redundant glossary round-trip when the broad read already surfaced the target
    (the augment only fills a genuine gap)."""
    anchor = uuid4()

    async def fake_gather_present(glossary, knowledge, *, book_id, user_id,
                                  project_id, bearer, query, present_entity_ids):
        return [{"entity_id": str(anchor), "name": "X", "summary": "canon bio",
                 "relations": []}], set()

    import app.packer.lenses as lenses
    monkeypatch.setattr(lenses, "gather_present", fake_gather_present)

    called = {"augment": False}

    class FakeGlossary:
        async def select_for_context(self, *a, **k):
            called["augment"] = True
            return []

    present = await co._gather_base_present(
        glossary=FakeGlossary(), knowledge=object(), book=object(),
        book_id=uuid4(), user_id=uuid4(), project_id=uuid4(), bearer="t",
        present_entity_ids=[anchor], query="",
        override_target_anchors=[str(anchor)],
    )
    assert called["augment"] is False             # already present → no extra fetch
    assert any(str(p["entity_id"]) == str(anchor) for p in present)


async def test_critique_overrides_passes_target_anchors_to_base_lens(monkeypatch):
    """Wiring: critique_overrides forwards the override target anchors to the base lens
    so the augment can guarantee them (end-to-end, the detector still fires the slip)."""
    src_proj = uuid4()
    anchor = uuid4()
    work = SimpleNamespace(source_work_id=uuid4(), project_id=uuid4(),
                           book_id=uuid4(), id=uuid4())
    derivctx = _StubDerivContext(
        source_project_id=src_proj,
        overrides=[_ov(anchor, {"description": "现在是女性"})])

    async def fake_build(*a, **k):
        return derivctx
    monkeypatch.setattr(co, "build_derivative_context", fake_build)

    async def _no_anchors(knowledge, bearer, overrides):
        return {}
    monkeypatch.setattr(co, "_resolve_override_anchors", _no_anchors)

    captured = {}

    async def fake_base(*, glossary, knowledge, book, book_id, user_id, project_id,
                        bearer, present_entity_ids=None, query="",
                        override_target_anchors=None):
        captured["override_target_anchors"] = override_target_anchors
        return [{"entity_id": str(anchor), "name": "张若尘", "summary": "少年天才"}]

    out = await co.critique_overrides(
        work=work, user_id=uuid4(), passage="张若尘乃少年天才，名震天下。",
        bearer="t", works_repo=object(), derivatives_repo=object(),
        glossary=object(), knowledge=object(), book=object(),
        _base_present_fn=fake_base,
    )
    assert captured["override_target_anchors"] == [str(anchor)]
    assert any(f["kind"] == "override_slip" for f in out)


# ── GATE decision + regeneration attempt cap ──

def _slip():
    return {"kind": "override_slip", "entity_id": "e", "name": "X",
            "field": "description", "expected": "a woman", "found": "a young man"}


def test_gate_blocks_accept_on_slip_first_attempt():
    """A slipped scene → the gate marks needs_regeneration (blocks accept / feeds the
    regenerate loop). attempt 0 (no prior critique) is under the cap."""
    gate = co.evaluate_override_gate([_slip()], prior_attempts=0)
    assert gate["needs_regeneration"] is True
    assert gate["regen_exhausted"] is False
    assert gate["regen_attempts"] == 1          # this critique counts as attempt 1
    assert gate["regen_cap"] == co.REGEN_ATTEMPT_CAP


def test_gate_passes_compliant_scene():
    """No findings → no gating (accept allowed); the attempt counter does NOT advance
    on a clean scene."""
    gate = co.evaluate_override_gate([], prior_attempts=2)
    assert gate["needs_regeneration"] is False
    assert gate["regen_exhausted"] is False
    assert gate["regen_attempts"] == 2          # unchanged — only slips advance it


def test_gate_caps_runaway_loop_and_surfaces_to_human():
    """After REGEN_ATTEMPT_CAP slipped critiques the gate STOPS blocking (fail-open to
    the human) so a stubborn / false-positive slip can't loop forever. The findings
    are still surfaced; needs_regeneration flips to False + regen_exhausted True."""
    gate = co.evaluate_override_gate([_slip()], prior_attempts=co.REGEN_ATTEMPT_CAP)
    assert gate["needs_regeneration"] is False   # no more forced regen
    assert gate["regen_exhausted"] is True       # surfaced to the human instead
    assert gate["regen_attempts"] == co.REGEN_ATTEMPT_CAP + 1


def test_gate_delta_inconsistency_also_gates():
    """A delta_inconsistency finding (even without a bio slip) is a fail too."""
    dc = {"kind": "delta_inconsistency", "entity_id": "e", "name": "Z",
          "rule": "Z betrayed the crown", "why": "..."}
    gate = co.evaluate_override_gate([dc], prior_attempts=0)
    assert gate["needs_regeneration"] is True


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

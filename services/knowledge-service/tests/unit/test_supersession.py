"""WS-2.6b (spec 07 §Q5) — the supersession grouping ("it changed").

Pure over Fact objects (no DB): recall must surface a claim that changed over time as ONE supersession
("Mon: Friday → Wed: Tuesday"), never as two independent truths, and must NOT invent a supersession from
a re-affirmation or from coarse (subjectless / predicate-less) facts.
"""

from __future__ import annotations

from app.db.neo4j_repos.facts import Fact, group_supersessions


def _fact(*, subject, predicate, obj, event_date, content=None):
    return Fact(
        id="f" + (content or f"{subject}{obj}"), user_id="u1", project_id="p1",
        type="statement", content=content or f"{subject} {predicate} {obj}",
        canonical_content=(content or f"{subject} {predicate} {obj}").lower(),
        event_date_iso=event_date, predicate=predicate, object=obj, subject_canonical=subject,
    )


def test_a_changed_claim_is_one_supersession_oldest_to_newest():
    facts = [
        _fact(subject="launch", predicate="scheduled for", obj="Tuesday", event_date="2026-03-04"),
        _fact(subject="launch", predicate="scheduled for", obj="Friday", event_date="2026-03-02"),
    ]
    sup = group_supersessions(facts)
    assert len(sup) == 1
    s = sup[0]
    assert s["subject"] == "launch" and s["changed"] is True
    assert s["latest"] == "Tuesday"  # newest by date wins
    # The chain reads forward in time: Friday (Mon) → Tuesday (Wed).
    assert [c["object"] for c in s["chain"]] == ["Friday", "Tuesday"]


def test_a_reaffirmation_of_the_same_object_is_not_a_supersession():
    facts = [
        _fact(subject="launch", predicate="scheduled for", obj="Friday", event_date="2026-03-02"),
        _fact(subject="launch", predicate="scheduled for", obj="friday", event_date="2026-03-05"),
    ]
    # Same object (case/space-normalized) restated twice — a change did NOT happen.
    assert group_supersessions(facts) == []


def test_different_subjects_or_predicates_do_not_merge():
    facts = [
        _fact(subject="launch", predicate="scheduled for", obj="Friday", event_date="2026-03-02"),
        _fact(subject="review", predicate="scheduled for", obj="Tuesday", event_date="2026-03-03"),
        _fact(subject="launch", predicate="owned by", obj="Alice", event_date="2026-03-04"),
    ]
    # Three distinct (subject, predicate) claims, each with one object — no supersession.
    assert group_supersessions(facts) == []


def test_coarse_facts_missing_the_trio_never_form_a_supersession():
    facts = [
        _fact(subject="launch", predicate=None, obj="Friday", event_date="2026-03-02"),
        _fact(subject="launch", predicate=None, obj="Tuesday", event_date="2026-03-04"),
        Fact(id="fc", user_id="u1", project_id="p1", type="statement",
             content="something happened", canonical_content="something happened"),
    ]
    assert group_supersessions(facts) == []


def test_three_step_change_keeps_the_whole_ordered_chain():
    facts = [
        _fact(subject="budget", predicate="owner", obj="Minh", event_date="2026-03-01"),
        _fact(subject="budget", predicate="owner", obj="Priya", event_date="2026-03-10"),
        _fact(subject="budget", predicate="owner", obj="Alice", event_date="2026-03-05"),
    ]
    sup = group_supersessions(facts)
    assert len(sup) == 1
    assert [c["object"] for c in sup[0]["chain"]] == ["Minh", "Alice", "Priya"]
    assert sup[0]["latest"] == "Priya"

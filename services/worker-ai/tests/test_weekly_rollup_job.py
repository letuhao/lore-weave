"""WS-3.7 — the weekly rollup: recall a week's facts → reduce → a supplement DRAFT. Fakes, no stack."""

from __future__ import annotations

import json

from app import weekly_rollup_job


class FakeKnowledge:
    def __init__(self, facts):
        self._facts = facts
        self.calls: list[dict] = []

    async def recall_facts_range(self, *, user_id, book_id, date_from, date_to, limit=200):
        self.calls.append({"from": date_from, "to": date_to})
        return self._facts


class FakeBook:
    def __init__(self):
        self.writes: list[dict] = []

    async def write_diary_entry(self, **kw):
        self.writes.append(kw)
        return {"chapter_id": "wk-1", "created": True}


class FakeLLM:
    def __init__(self, reduce_obj=None):
        self._reduce = reduce_obj or {"summary": "A productive week.", "decisions": ["Shipped v2."]}

    async def __call__(self, prompt: str) -> str:
        return json.dumps(self._reduce)  # the rollup only ever calls reduce (FACTS: prompt)


class FakeBilling:
    def __init__(self, exhausted=False):
        self._x = exhausted

    async def daily_cap_exhausted(self, *, user_id):
        return self._x


_FACTS = [
    {"type": "decision", "content": "Froze the Q3 budget", "event_date_iso": "2026-03-10",
     "subject": "Alice", "predicate": "froze", "object": "budget"},
    {"type": "event", "content": "Shipped the redesign", "event_date_iso": "2026-03-12"},
]


async def test_weekly_rollup_writes_a_supplement_draft():
    kn = FakeKnowledge(_FACTS)
    book = FakeBook()
    out = await weekly_rollup_job.roll_up_week(
        user_id="u1", book_id="b1", week_start="2026-03-09", week_end="2026-03-15",
        entry_zone="UTC", language="en", llm=FakeLLM(), knowledge_client=kn, book_client=book,
    )
    assert out["status"] == "rolled_up"
    assert out["facts_summarized"] == 2
    assert kn.calls == [{"from": "2026-03-09", "to": "2026-03-15"}]  # recalled the WEEK range
    assert len(book.writes) == 1
    w = book.writes[0]
    assert w["journal_kind"] == "weekly"           # a get-or-replace review kind (M2 idempotent)
    assert w["entry_date"] == "2026-03-15"             # dated to the week's end
    assert "A productive week." in w["body"] and "Weekly review" in (w["title"] or "")


async def test_weekly_rollup_no_facts_writes_nothing():
    book = FakeBook()
    out = await weekly_rollup_job.roll_up_week(
        user_id="u1", book_id="b1", week_start="2026-03-09", week_end="2026-03-15",
        entry_zone="UTC", language="en", llm=FakeLLM(), knowledge_client=FakeKnowledge([]), book_client=book,
    )
    assert out["status"] == "no_facts" and book.writes == []


async def test_weekly_rollup_paused_on_daily_cap():
    book = FakeBook()
    out = await weekly_rollup_job.roll_up_week(
        user_id="u1", book_id="b1", week_start="2026-03-09", week_end="2026-03-15",
        entry_zone="UTC", language="en", llm=FakeLLM(), knowledge_client=FakeKnowledge(_FACTS),
        book_client=book, billing_client=FakeBilling(exhausted=True),
    )
    assert out["status"] == "paused" and book.writes == []

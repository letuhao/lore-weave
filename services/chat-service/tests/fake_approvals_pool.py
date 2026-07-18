"""A faithful in-memory stand-in for the ``user_tool_approvals`` table.

Shared by ``test_spend_gate`` (kind separation) and ``test_tool_permissions`` (the
Track C consent loop) so ONE model of the table serves both — two hand-rolled fakes
would drift, and a fake that has drifted from the schema tests nothing but itself.

It models what actually matters and has actually bitten:
  * the PK ``(user_id, tool_name)`` — an upsert FLIPS a decision, never doubles it;
  * the ``decision`` column — ``fetchval`` returns the DECISION, not ``1``, so a test
    cannot pass by mistaking a deny row's existence for a grant;
  * ``DELETE``'s command tag (``"DELETE 0"`` when nothing matched), which is the only
    thing that tells ``revoke_tool_decision`` a revoke was a no-op.
"""

from __future__ import annotations


class FakeApprovalsPool:
    def __init__(self) -> None:
        self.rows: dict[tuple[str, str], str] = {}   # (user_id, storage_key) -> decision
        self.inserted_keys: list[str] = []

    async def execute(self, sql: str, user_id: str, key: str, decision: str | None = None):
        if "DELETE" in sql.upper():
            existed = self.rows.pop((user_id, key), None) is not None
            return "DELETE 1" if existed else "DELETE 0"
        self.inserted_keys.append(key)
        self.rows[(user_id, key)] = decision or "allow"
        return "INSERT 0 1"

    async def fetchval(self, _sql: str, user_id: str, key: str):
        return self.rows.get((user_id, key))

    async def fetch(self, _sql: str, user_id: str):
        import datetime as _dt

        base = _dt.datetime(2026, 7, 12, tzinfo=_dt.timezone.utc)
        return [
            {"tool_name": key, "decision": decision, "created_at": base}
            for (uid, key), decision in self.rows.items()
            if uid == user_id
        ]

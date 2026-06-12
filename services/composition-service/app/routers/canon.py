"""Canon rules + templates router (§5).

Reuses the M2 CanonRulesRepo (If-Match → 412, soft-archive on DELETE). CR4: a
`from_order > until_order` window is a typo — validated at the router (400),
never persisted. GET /templates lists built-in + the user's structure templates.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from app.db.models import RuleScope
from app.db.repositories import VersionMismatchError
from app.db.repositories.canon_rules import CanonRulesRepo
from app.db.repositories.structure_templates import StructureTemplatesRepo
from app.db.repositories.works import WorksRepo
from app.deps import get_canon_rules_repo, get_structure_templates_repo, get_works_repo
from app.middleware.jwt_auth import get_current_user

router = APIRouter(prefix="/v1/composition")


class CanonRuleCreate(BaseModel):
    text: str
    scope: RuleScope = "world"
    entity_id: UUID | None = None
    from_order: int | None = None
    until_order: int | None = None
    kind: str | None = None


class CanonRulePatch(BaseModel):
    text: str | None = None
    scope: RuleScope | None = None
    entity_id: UUID | None = None
    from_order: int | None = None
    until_order: int | None = None
    kind: str | None = None
    active: bool | None = None


def _validate_window(from_order: int | None, until_order: int | None) -> None:
    """CR4: reject an inverted reveal window (author typo) → 400."""
    if from_order is not None and until_order is not None and from_order > until_order:
        raise HTTPException(status_code=400, detail={
            "code": "CANON_WINDOW_INVERTED", "from_order": from_order, "until_order": until_order})


def _parse_if_match(if_match: str | None) -> int | None:
    if if_match is None:
        return None
    try:
        return int(if_match.strip().strip('"'))
    except ValueError:
        raise HTTPException(status_code=400, detail="If-Match must be an integer version")


async def _require_work(works: WorksRepo, user_id: UUID, project_id: UUID) -> None:
    if await works.get(user_id, project_id) is None:
        raise HTTPException(status_code=404, detail="work not found")


@router.get("/works/{project_id}/canon-rules")
async def list_canon_rules(
    project_id: UUID,
    active_only: bool = False,
    user_id: UUID = Depends(get_current_user),
    works: WorksRepo = Depends(get_works_repo),
    canon: CanonRulesRepo = Depends(get_canon_rules_repo),
) -> dict[str, Any]:
    await _require_work(works, user_id, project_id)
    rules = await (canon.list_active(user_id, project_id) if active_only
                   else canon.list_all(user_id, project_id))
    return {"rules": [r.model_dump(mode="json") for r in rules]}


@router.post("/works/{project_id}/canon-rules", status_code=201)
async def create_canon_rule(
    project_id: UUID,
    body: CanonRuleCreate,
    user_id: UUID = Depends(get_current_user),
    works: WorksRepo = Depends(get_works_repo),
    canon: CanonRulesRepo = Depends(get_canon_rules_repo),
) -> dict[str, Any]:
    await _require_work(works, user_id, project_id)
    _validate_window(body.from_order, body.until_order)
    rule = await canon.create(user_id, project_id, body.text, scope=body.scope,
                              entity_id=body.entity_id, from_order=body.from_order,
                              until_order=body.until_order, kind=body.kind)
    return rule.model_dump(mode="json")


@router.patch("/canon-rules/{rule_id}")
async def patch_canon_rule(
    rule_id: UUID,
    body: CanonRulePatch,
    user_id: UUID = Depends(get_current_user),
    canon: CanonRulesRepo = Depends(get_canon_rules_repo),
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> dict[str, Any]:
    patch = body.model_dump(exclude_unset=True)
    # CR4 on the EFFECTIVE window after the patch — need the current row when the
    # patch sets only one bound.
    if "from_order" in patch or "until_order" in patch:
        current = await canon.get(user_id, rule_id)
        if current is None:
            raise HTTPException(status_code=404, detail="canon rule not found")
        fo = patch.get("from_order", current.from_order)
        uo = patch.get("until_order", current.until_order)
        _validate_window(fo, uo)
    try:
        rule = await canon.update(user_id, rule_id, patch, expected_version=_parse_if_match(if_match))
    except VersionMismatchError as exc:
        raise HTTPException(status_code=412, detail={"code": "CANON_VERSION_CONFLICT",
                                                     "current": exc.current.model_dump(mode="json")})
    if rule is None:
        raise HTTPException(status_code=404, detail="canon rule not found")
    return rule.model_dump(mode="json")


@router.delete("/canon-rules/{rule_id}", status_code=200)
async def delete_canon_rule(
    rule_id: UUID,
    user_id: UUID = Depends(get_current_user),
    canon: CanonRulesRepo = Depends(get_canon_rules_repo),
) -> dict[str, Any]:
    rule = await canon.archive(user_id, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="canon rule not found")
    return rule.model_dump(mode="json")


@router.get("/templates")
async def list_templates(
    user_id: UUID = Depends(get_current_user),
    templates: StructureTemplatesRepo = Depends(get_structure_templates_repo),
) -> dict[str, Any]:
    rows = await templates.list_for_user(user_id)
    return {"templates": [t.model_dump(mode="json") for t in rows]}

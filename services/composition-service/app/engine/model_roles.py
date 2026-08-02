"""One reader for a Work's per-role model settings — the map form, with the legacy fallback.

What was wrong
--------------
`work.settings` can express the Book tier of the model cascade two ways:

    settings["model_roles"]          {role: {model_ref, model_source}}   ← the PREFERRED form
    settings["default_model_ref"]    a scalar meaning role "chat"        ← legacy
    settings["critic_model_ref"]     a scalar meaning role "critic"      ← legacy

`internal_model_settings.py` dual-reads them and says the map "wins if present". Measured
2026-08-03: **the map had ZERO writers repo-wide.** Every writer — the S6 settings affordance,
the only UI that sets a critic — writes the scalars. So the branch the system declares it
prefers was dead in production, exercised by unit tests alone.

That is not merely tidy-up debt. `ModelRole` (chat-service, `settings_resolution.py`) is "the
one canonical closed set of model roles … shared as the key vocabulary across all three model
stores", and it has **six** members: chat, composer, planner, embedding, rerank, critic. Two
scalars can express two of them. So the Book tier of a six-role cascade could hold two roles,
and the shape designed to hold all six was never written — a capability gap wearing a contract,
which the register recorded as "dead weight".

And a second reader had drifted from the first: `critic_policy.resolve_critic` read
`settings["critic_model_ref"]` directly, so a book whose critic lived in the map would have
resolved to NOT_CONFIGURED — the blocking tier silently off — while the internal endpoint
reported the critic correctly. One concept, two readers, and only one of them knew about the
preferred form. This module is the one reader; both import it.
"""
from __future__ import annotations

from typing import Any, Mapping

__all__ = ["model_roles_from_settings", "role_ref", "settings_patch_for_role", "LEGACY_SCALARS"]

#: role -> (ref key, source key) for the two roles that predate the map. Read as a FALLBACK
#: only, and still written by nothing new: they exist so books saved before the map keep
#: resolving. A third role never had a scalar pair, which is why the map exists at all.
LEGACY_SCALARS: dict[str, tuple[str, str]] = {
    "chat": ("default_model_ref", "default_model_source"),
    "critic": ("critic_model_ref", "critic_model_source"),
}


def model_roles_from_settings(settings: Mapping[str, Any] | None) -> dict[str, dict[str, str]]:
    """`{role: {model_ref, model_source}}` — the map, with legacy scalars filling the gaps.

    Only well-formed entries survive: an entry with no `model_ref` is not a setting, it is a
    half-written one, and passing it on would let a caller treat `{"critic": {}}` as a
    configured critic. `model_source` defaults to `user_model` because that is what every
    writer has ever sent; a ref without a source is what `CriticStatus.INCOMPLETE` is for, and
    that judgement belongs to the policy, not here.
    """
    sdict = settings or {}
    roles: dict[str, dict[str, str]] = {}
    existing = sdict.get("model_roles")
    if isinstance(existing, dict):
        for role, val in existing.items():
            if isinstance(val, dict) and val.get("model_ref"):
                roles[str(role)] = {
                    "model_ref": str(val["model_ref"]),
                    "model_source": str(val.get("model_source") or "user_model"),
                }
    for role, (ref_key, src_key) in LEGACY_SCALARS.items():
        ref = sdict.get(ref_key)
        if ref and role not in roles:
            roles[role] = {"model_ref": str(ref),
                           "model_source": str(sdict.get(src_key) or "user_model")}
    return roles


def role_ref(settings: Mapping[str, Any] | None, role: str) -> tuple[Any, Any]:
    """The RAW `(model_source, model_ref)` for one role — map first, then the legacy scalars.

    Deliberately NOT `model_roles_from_settings(...)[role]`, and the difference is the whole
    reason this function exists separately. That one NORMALISES: it drops entries with no
    `model_ref` and defaults a missing `model_source` to `user_model`, which is right for the
    wire shape its consumers read. Here it would be wrong: a ref recorded WITHOUT its source is
    a half-written setting, and `critic_policy` reports it as INCOMPLETE so the author is told
    to re-pick the model. Defaulting the source turns that into CONFIGURED — a state the author
    never chose, with a provider nobody selected.

    Found by writing exactly that and watching two pre-existing tests refuse it. The endpoint
    and the policy ask different questions of the same key; one function answering both would
    have to answer one of them wrongly.
    """
    sdict = settings or {}
    entry = (sdict.get("model_roles") or {}) if isinstance(sdict.get("model_roles"), dict) else {}
    got = entry.get(role)
    if isinstance(got, dict) and (got.get("model_ref") or got.get("model_source")):
        return got.get("model_source"), got.get("model_ref")
    ref_key, src_key = LEGACY_SCALARS.get(role, ("", ""))
    return (sdict.get(src_key), sdict.get(ref_key)) if ref_key else (None, None)


def settings_patch_for_role(
    settings: Mapping[str, Any] | None, role: str,
    model_ref: str | None, model_source: str = "user_model",
) -> dict[str, Any]:
    """The patch that SETS (or clears) one role in the map form.

    Clearing removes the role from the map AND blanks the legacy scalar pair. Both, because a
    dual-read that prefers the map would otherwise fall back to a stale scalar the author
    thought they had just cleared — the setting would appear to un-clear itself, which is worse
    than never having been clearable.
    """
    current = dict((settings or {}).get("model_roles") or {})
    patch: dict[str, Any] = {}
    if model_ref:
        current[role] = {"model_ref": model_ref, "model_source": model_source}
    else:
        current.pop(role, None)
        for key in LEGACY_SCALARS.get(role, ()):
            patch[key] = None
    patch["model_roles"] = current
    return patch

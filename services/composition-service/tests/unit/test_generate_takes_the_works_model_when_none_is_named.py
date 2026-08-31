"""The most expensive tool on the platform must not demand an id the caller cannot know.

    THE INVARIANT. `composition_generate`'s model_ref/model_source are OPTIONAL and resolve from
    the Work the caller already named. When nothing resolves the tool REFUSES and says how to
    set it — it never picks a model on the author's behalf, because every generation SPENDS.

OWNER RULING 2026-08-31, DQ-T35: YES — make composition_generate's model_ref OPTIONAL with a
server-resolved default. 16 of the 19 model_ref properties in the live catalogue are already
optional and state the convention in their own descriptions; only three are required, and
composition_generate is the outlier on the tool where guessing wrong costs the most.

WHY IT IS A DEFECT AND NOT A PREFERENCE, in the row's own words: "a model that has learned from
sixteen tools that omitting it is correct will omit it on the seventeenth." Measured 2026-08-14,
K=5: it sent `model_ref="default"` on 5 of 5 runs, a Tier-A card was minted every time, and the
confirm effect's `UUID(str(model_ref_raw))` produced a bare 400 — approve-then-fail, on a
cost-bearing call.

🔴 WHAT THE RULING DID NOT SETTLE, and is therefore NOT built: the ACCOUNT-tier fallback.
`user_default_models` is populated, but its capabilities are chat|distill|planner|rerank — there
is no composer or prose capability — so defaulting there means spending the author's money
through their CHAT model on a prose call. DQ-T35 says in as many words that which capability a
spending tool falls back to is a product call. So the resolution stops at the Work tier and
refuses honestly below it.
"""
from __future__ import annotations

import inspect
import typing

from app.engine.model_roles import role_ref
from app.mcp import server as mcp


def _field(name):
    return mcp._GenerateArgs.model_fields[name]


class TestThePairIsOptionalTogether:
    def test_model_ref_is_optional(self):
        assert _field("model_ref").default is None, (
            "model_ref is still required — a model that has learned from sixteen sibling tools "
            "that omitting it is correct will omit it here and be refused")

    def test_model_source_is_optional_TOO(self):
        """🔴 THEY TRAVEL AS A PAIR. Leaving model_source required would make the whole change
        inert: a caller that omits model_ref must also omit its source, and `role_ref` returns
        both together precisely because a ref recorded WITHOUT its source is a half-written
        setting that must not be normalised into a configured one."""
        assert _field("model_source").default is None, (
            "model_source is still required, so omitting model_ref is impossible in practice")

    def test_the_description_SAYS_it_is_optional(self):
        """The description is the only declaration the runtime and the model both read. An
        argument that is optional in the schema and silent about it teaches nothing."""
        desc = _field("model_ref").description or ""
        assert "OPTIONAL" in desc, "the schema changed and the description did not"
        assert "omit" in desc.lower()

    def test_it_still_says_a_ref_is_a_UUID_not_a_name(self):
        """The measured failure this description was written for must survive the edit: the
        model sent `model_ref="default"` 5 of 5 before the UUID sentence existed."""
        desc = _field("model_ref").description or ""
        assert "UUID" in desc and "'default'" in desc


class TestItResolvesFromTheWorkAndNeverGuesses:
    @staticmethod
    def _src() -> str:
        return inspect.getsource(mcp.composition_generate)

    def test_the_resolution_uses_the_EXISTING_role_mechanism(self):
        """The Work already carries settings['model_roles'] with legacy scalars behind it, and
        `role_ref` reads that pair. The mechanism existed and was empty — a second resolver
        would be a second thing to get wrong."""
        assert "role_ref(" in self._src()

    def test_it_refuses_rather_than_choosing_a_model_to_spend_through(self):
        """🔴 THE LINE THIS ROW WILL BE JUDGED ON. There is a populated ACCOUNT-tier default and
        it would resolve — through the author's `chat` model, on a prose call nobody priced.
        DQ-T35 calls that a product decision; an unruled product decision must not be taken
        silently inside a bug fix."""
        src = self._src()
        assert "will not pick a model on your behalf" in src, (
            "the no-resolution path does not refuse — check it has not started defaulting")
        # 🔴 STRIP THE COMMENTS FIRST. The block above EXPLAINS why the account tier is not
        # used, so it names `user_default_models` — and a whole-source search was therefore
        # satisfied by my own prose while proving nothing about the code. A guard that its own
        # documentation can defeat is not a guard.
        code = " ".join(ln for ln in src.splitlines()
                        if not ln.lstrip().startswith("#"))
        assert "user_default_models" not in code and "resolve_user_default_model" not in code, (
            "the ACCOUNT tier is being used; DQ-T35 rules that a product call and the ruling "
            "did not settle which capability a spending tool falls back to")

    def test_the_refusal_tells_the_caller_how_to_supply_one(self):
        src = self._src()
        assert "settings_list_models" in src, (
            "the refusal does not name where a model_ref comes from — a dead end")

    def test_a_half_written_setting_is_not_accepted(self):
        """A ref with no source must not resolve. `role_ref` returns the raw pair for exactly
        this reason, and the caller has to check both."""
        src = self._src()
        assert "if _ref and _src:" in src or "not (_ref and _src)" in src


class TestTheRoleLookupItself:
    """Driving `role_ref` rather than reading it — the resolution has to actually work."""

    def test_the_map_wins_over_the_legacy_scalar(self):
        settings = {"model_roles": {"chat": {"model_ref": "MAP", "model_source": "user_model"}},
                    "default_model_ref": "LEGACY"}
        assert role_ref(settings, "chat")[1] == "MAP"

    def test_the_legacy_scalar_still_resolves_for_older_books(self):
        """The DQ measured 0 of 664 Works carrying the map and 13 carrying the legacy scalar.
        If the legacy path stopped resolving, this change would reach ZERO books."""
        src, ref = role_ref({"default_model_ref": "LEGACY",
                             "default_model_source": "user_model"}, "chat")
        assert (src, ref) == ("user_model", "LEGACY")

    def test_an_unconfigured_work_resolves_to_nothing(self):
        assert role_ref({}, "chat") == (None, None)
        assert role_ref(None, "composer") == (None, None)


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))

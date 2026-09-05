"""R1 — a surface must be able to answer the request it is given.

🔴 THIS DEFECT HAS SHIPPED TWICE, and both times the tool had already DECLARED it was the right
one. The surface ignored the declaration.

**v1 — 2026-07-21**, in `tool_surface.py`'s own words: `book_update_details` "was never advertised,
so **every model mis-routed 'update the description' to `book_chapter_create`/`save_draft` — the
tool it could actually see**." It declares the synonyms `"update description"`,
`"change the description"`, `"update the book description"`.

**v2 — 2026-08-13**, measured 5/5 through the real FE path: asked *"Show me the outline I've
planned for this book — what chapters and scenes are in it?"*, `composition_list_outline` was
withheld at `domain_not_selected` in **every pass** while `composition_outline_node_edit` — Tier
A, a write — stayed advertised. The model used the write it could see, and the owning store went
from 7 outline nodes to 10: three chapters created by a question that only asked to see them. That
tool declares `"outline"`, `"chapters"`, `"beats"`, `"story structure"`.

Five mechanisms narrow the surface before the wire — domain selection, the hot-seed budget, the
write allowlist, rail step pre-activation, and the suppressors. Each is locally correct; none is
accountable for whether the RESULT can answer the question. R1 is that accountability, and it
lives at the single advertise chokepoint so every path is covered by one edit.
"""
import pytest

from app.services.stream_service import _advertise_discovery_tools
from app.services.tool_surface import ANSWERABLE_MAX, answerable_tools


def _tool(name, tier, synonyms):
    return {"type": "function", "function": {
        "name": name, "description": "d",
        "parameters": {"type": "object", "properties": {}},
        "_meta": {"tier": tier, "synonyms": synonyms},
    }}


# The live catalogue shape for both incidents.
CATALOG = {t["function"]["name"]: t for t in [
    _tool("composition_list_outline", "R",
          ["outline", "scene graph", "story structure", "chapters", "beats", "list outline"]),
    _tool("composition_outline_node_edit", "A",
          ["edit outline node", "create chapter", "create scene", "delete scene"]),
    _tool("book_update_details", "W",
          ["update description", "change the description", "set genre", "rename book"]),
    _tool("book_chapter_save_draft", "A", ["save draft", "write chapter"]),
    _tool("glossary_search", "R", ["find character", "look up entity"]),
]}

V2 = "Show me the outline I've planned for this book — what chapters and scenes are in it?"
V1 = "update the description of my book"


def _names(tools):
    return {t["function"]["name"] for t in (tools or [])
            if isinstance(t.get("function"), dict) and t["function"].get("name")}


class TestTheTwoIncidents:
    def test_v2_the_read_reaches_the_wire_even_though_nothing_else_selected_it(self):
        """THE FALSIFIER for v2. `active_tool_names` is EMPTY here — i.e. domain selection, the
        budget and the rail all declined to seed it, exactly as measured live."""
        got = _names(_advertise_discovery_tools(CATALOG, set(), [], request_text=V2))
        assert "composition_list_outline" in got

    def test_v2_the_outline_WRITE_is_not_dragged_along_with_it(self):
        """The synonyms discriminate on their own: `outline_node_edit` declares only phrases
        ("create chapter", "delete scene"), so a read phrasing cannot match it. This is why R1
        needs no read/write heuristic of its own."""
        got = _names(_advertise_discovery_tools(CATALOG, set(), [], request_text=V2))
        assert "composition_outline_node_edit" not in got

    def test_v1_the_starved_write_reaches_the_wire_for_the_request_that_needs_it(self):
        """THE FALSIFIER for v1 — the 2026-07-21 incident, which an allowlist entry patched and
        the invariant never covered. Note the phrasing differs from the declared synonym by an
        article ("update THE description"), which a raw substring test misses; that near-miss is
        the whole difference between catching this and shipping it."""
        got = _names(_advertise_discovery_tools(CATALOG, set(), [], request_text=V1))
        assert "book_update_details" in got


class TestItStaysOutOfTheWay:
    @pytest.mark.parametrize("msg", ["ok", "thanks, go on", "write the next chapter for me", ""])
    def test_a_request_matching_no_declared_vocabulary_forces_nothing(self, msg):
        """The cost is bounded by what the user actually said. A turn that matches nothing pays
        nothing — unlike an allowlist, which spends the prefix on every turn forever."""
        got = _names(_advertise_discovery_tools(CATALOG, set(), [], request_text=msg))
        assert got & set(CATALOG) == set()

    def test_a_suppressed_tool_is_NOT_forced_back_onto_the_wire(self):
        """A suppressor is a LOOP breaker — repeated-failure, repeated-read, oneshot. It fires on
        tools the model is already hammering, so forcing one back would restart the loop that
        stage exists to stop. Answerability outranks a BUDGET, never a breaker."""
        got = _names(_advertise_discovery_tools(
            CATALOG, set(), [], request_text=V2,
            suppress_names={"composition_list_outline"}))
        assert "composition_list_outline" not in got

    def test_ask_mode_still_governs_what_may_RUN(self):
        """Answerability governs what is VISIBLE; permission mode governs what may run. A Tier-W
        tool must not become visible in ask mode just because the request named it."""
        got = _names(_advertise_discovery_tools(
            CATALOG, set(), [], request_text=V1, permission_mode="ask"))
        assert "book_update_details" not in got

    def test_a_write_request_still_reaches_its_write(self):
        """The rule is not read-biased: it forces whatever the user's words matched. "Change the
        description" is a write request and must reach the write."""
        got = _names(_advertise_discovery_tools(
            CATALOG, set(), [], request_text="change the description please"))
        assert "book_update_details" in got


class TestTheMatcherItself:
    def test_the_forced_set_is_bounded(self):
        many = {f"t{i}": _tool(f"t{i}", "R", ["outline"]) for i in range(50)}
        assert len(answerable_tools("show me the outline", list(many.values()))) <= ANSWERABLE_MAX

    def test_a_longer_synonym_outranks_a_shorter_one_under_the_ceiling(self):
        """When the ceiling truncates, the most SPECIFIC evidence must survive — a three-word
        phrase is far stronger than a bare noun."""
        cat = [_tool("specific", "R", ["outline of the book"]), _tool("vague", "R", ["book"])]
        cat += [_tool(f"filler{i}", "R", ["book"]) for i in range(ANSWERABLE_MAX + 3)]
        got = answerable_tools("show me the outline of the book", cat)
        assert "specific" in got

    def test_matching_reads_the_DECLARATION_never_the_name(self):
        """`CP-4.d` deleted a name-substring classifier on purpose. A tool named for a thing it
        does not declare must not match."""
        cat = [_tool("composition_list_outline", "R", ["totally unrelated phrase"])]
        assert answerable_tools("show me the outline", cat) == set()


class TestItIsWiredEverywhereATurnCanAdvertise:
    """Three call sites reach the wire — the per-pass loop, the turn-start advertise, and the
    RESUME. A resume is still answering the original request; dropping it there would make the
    post-approval pass the one surface that cannot answer what it suspended on."""

    @pytest.mark.parametrize("needle", [
        "request_text=request_text,",                    # per-pass, inside the tool loop
        "request_text=user_message_content,",            # turn start + _emit_chat_turn
        "request_text=susp.user_message_content,",       # resume
    ])
    def test_every_advertise_site_is_given_the_request(self, needle):
        import pathlib
        src = (pathlib.Path(__file__).resolve().parents[1]
               / "app" / "services" / "stream_service.py").read_text(encoding="utf-8")
        assert needle in src

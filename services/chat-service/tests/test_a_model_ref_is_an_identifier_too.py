"""D-UNDECLARED-REF-BECOMES-A-PLACEHOLDER — approve-then-fail on the platform's costliest tool.

`composition_generate` advertised `model_ref` as a BARE string:

    {"title": "Model Ref", "type": "string"}          # no description at all

while the confirm effect does `UUID(str(model_ref_raw))`. So the argument is a UUID at the
consuming end and declares nothing at the advertising end.

MEASURED LIVE 2026-08-14, K=5, with the chapter named so the tool was actually reached:

    composition_generate(model_ref="default", model_source="platform_model", ...)   5 of 5

A Tier-A confirm card was minted every time. Approving one produces a bare HTTP 400
`action_error` — the author consents to "write my chapter", clicks approve, and gets an opaque
failure on the most expensive tool on the platform.

NO EXISTING ARM COULD SEE IT. `"default"` parses as neither nil-UUID nor whitespace, and the
declaration arm reads the description, which was empty. The name simply did not end in `_id`, so
`_invented_supplier_ids` never looked at it — the loop head was `if not name.endswith("_id")`.

🔴 ONLY THE DECLARED-UUID ARM WIDENS TO `*_ref`, and the count is why. Across the live catalogue
there are 21 `*_ref` properties: 19 `model_ref` and 2 `image_ref`. `image_ref` is a MinIO object
key — world_map_create declares it as "optional MinIO object key of an already-uploaded base
image" — so it is NOT an identifier this platform issues, and a space in one is not proof of a
name. It declares no UUID, so the declared arm cannot touch it; widening the WHITESPACE arm would
have started dropping legitimate object keys.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.services.stream_service import _invented_supplier_ids  # noqa: E402

#: composition_generate's declaration AFTER this cycle named the UUID and its supplier.
MODEL_REF_DECLARED = {
    "model_ref": {"type": "string", "description": (
        "The model's id (UUID). NOT a name, an alias, or 'default' — list the caller's models "
        "with settings_list_models and pass the `model_ref` from there.")},
}
#: world_map_create's real declaration, copied from the live catalogue.
IMAGE_REF = {
    "image_ref": {"type": "string", "description":
                  "optional MinIO object key of an already-uploaded base image"},
}
REAL = "01a02028-9c26-722a-a2d0-80fdca7f2de0"


class TestTheMeasuredCallIsCaught:
    """THE FALSIFIER — the exact argument from 5 of 5 live runs."""

    def test_default_is_dropped(self):
        assert _invented_supplier_ids(
            {"model_ref": "default", "model_source": "platform_model"},
            None, MODEL_REF_DECLARED) == ["model_ref"]

    def test_a_real_uuid_passes(self):
        assert _invented_supplier_ids({"model_ref": REAL}, None, MODEL_REF_DECLARED) == []

    def test_an_undeclared_model_ref_is_left_alone(self):
        """The rule is still 'only what the tool DECLARES'. Before the declaration landed, this
        same value had to pass — which is exactly why the declaration was the other half of the
        fix and not an afterthought."""
        assert _invented_supplier_ids(
            {"model_ref": "default"}, None, {"model_ref": {"type": "string"}}) == []


class TestImageRefIsNotCollateral:
    """🔴 The boundary. `image_ref` is the other `*_ref` on this platform and it is NOT a UUID."""

    def test_an_object_key_is_not_dropped(self):
        assert _invented_supplier_ids(
            {"image_ref": "maps/ashfall-base.png"}, None, IMAGE_REF) == []

    def test_an_object_key_WITH_A_SPACE_is_not_dropped(self):
        """The whitespace arm stays `*_id`-only. A MinIO key may legitimately contain a space;
        an id this platform issues never does. Widening that arm would have broken real uploads."""
        assert _invented_supplier_ids(
            {"image_ref": "maps/base image.png"}, None, IMAGE_REF) == []

    def test_an_id_with_a_space_is_still_dropped(self):
        """…while the `*_id` whitespace arm keeps working — batch 14's node_id="The Hollow Keep"."""
        props = {"node_id": {"type": "string", "description": "The arc/saga (structure_node) id."}}
        assert _invented_supplier_ids({"node_id": "The Hollow Keep"}, None, props) == ["node_id"]


class TestTheLoopHeadAcceptsBothConventions:
    def test_a_non_identifier_argument_is_untouched(self):
        """Scoped to the two identifier conventions — a guide or a title is free text."""
        props = {"guide": {"type": "string", "description": "a UUID-ish sounding hint"}}
        assert _invented_supplier_ids({"guide": "write it like Le Guin"}, None, props) == []

    def test_both_conventions_are_named_in_the_source(self):
        src = (pathlib.Path(__file__).resolve().parents[1]
               / "app" / "services" / "stream_service.py").read_text(encoding="utf-8")
        # Anchored to the function BODY, not a fixed byte window: this file's docstrings are
        # long enough that a `+3000` slice stopped short of the loop head, and a fixed-byte
        # window is a test that rots the next time a comment grows.
        i = src.index("def _invented_supplier_ids(")
        j = src.index(chr(10) + "def ", i + 10)
        body = src[i:j]
        assert 'name.endswith("_id") or name.endswith("_ref")' in body

    def test_the_whitespace_arm_is_still_id_only(self):
        """Pinned: if a later edit lets the whitespace arm see `*_ref`, image_ref breaks."""
        src = (pathlib.Path(__file__).resolve().parents[1]
               / "app" / "services" / "stream_service.py").read_text(encoding="utf-8")
        i = src.index("any(ch.isspace() for ch in value.strip())")
        block = src[i - 700:i]
        assert 'name.endswith("_id")' in block, (
            "the whitespace arm must stay scoped to *_id — image_ref is a MinIO object key")

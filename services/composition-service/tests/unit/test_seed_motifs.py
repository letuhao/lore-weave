"""W7 — system-tier motif seed-pack unit tests (no DB).

These validate the pack CONTENT + the loader's id logic + the copyright guard. They
run in the standard suite (no Postgres). The DB-gated idempotency / tier / NULL-embed
proofs live in tests/integration/db/test_seed_motifs.py.

Map to W7 §5: tests #1-#11.
"""

from __future__ import annotations

import re

import pytest

from app.db.models import Motif, MotifCreateArgs
from app.db.seed_motifs import (
    _MOTIF_PACKS,
    _SYSTEM_VISIBILITY,
    _link_id,
    _motif_id,
    load_link_edges,
    load_motif_rows,
)

GREIMAS_ACTANTS = {"subject", "object", "sender", "receiver", "helper", "opponent"}

# §2.4/§2.5 connective kinds are genre-independent; the genre packs carry the others.
_CONNECTIVE_KINDS = {"hook", "emotion_arc"}
_SCHEME_PACK = "intrigue"

# Copyright lint (§6, test #9): banned proper nouns from well-known source works the
# packs are INSPIRED BY but must never name. A hit on any examples[] line fails the
# build. Lower-cased, word-boundary matched.
_BANNED_PROPER_NOUNS = {
    # famous xianxia / wuxia / web-novel works + protagonists/sects
    "xiao yan", "doupo", "battle through the heavens", "meng hao", "i shall seal the heavens",
    "wang lin", "renegade immortal", "han li", "a will eternal", "nie li", "tang san",
    "douluo", "ye fan", "shi hao", "perfect world", "shrouded", "coiling dragon", "linley",
    "azure dragon", "qin yu", "stellar transformations",
    # famous revenge / intrigue works
    "count of monte cristo", "edmond dantes", "zhen huan", "ruyi", "empresses in the palace",
    "story of yanxi palace", "wei yingluo", "game of thrones", "cersei", "littlefinger",
}


@pytest.fixture(scope="module")
def rows():
    return load_motif_rows()


@pytest.fixture(scope="module")
def edges(rows):
    return load_link_edges(rows)


# ── test #1 — every pack row validates against the F0 Motif contract.
def test_every_pack_row_validates_against_motif_model(rows):
    assert rows, "no seed rows loaded"
    for r in rows:
        # write-arg model (strict ForbidExtra) — source/source_version are seed-only
        # loader fields, never user write-args, so strip them for the write-arg check.
        create_view = {k: v for k, v in r.items() if k not in ("source", "source_version")}
        MotifCreateArgs.model_validate(create_view)
        # read-row model with the loader-stamped system fields.
        m = Motif.model_validate(
            {
                **r,
                "id": _motif_id(r["code"], r.get("language", "en")),
                "owner_user_id": None,
                "visibility": _SYSTEM_VISIBILITY,
            }
        )
        assert m.owner_user_id is None
        assert m.source == "authored"  # W7 is authored-only


# ── test #2 — codes unique per language + match the naming convention.
def test_codes_unique_per_language(rows):
    seen = set()
    genre_re = re.compile(r"^[a-z_]+\.[a-z_]+$")
    connective_re = re.compile(r"^(hook|emotion_arc)\.[a-z_]+$")
    for r in rows:
        key = (r["code"], r.get("language", "en"))
        assert key not in seen, f"duplicate (code, language): {key}"
        seen.add(key)
        code = r["code"]
        assert genre_re.match(code) or connective_re.match(code), f"bad code shape: {code}"


# ── test #3 — kind matches the pack; schemes carry a full info_asymmetry.
def test_kind_matches_pack():
    from app.db.seed_motifs import _read_pack

    for pack in _MOTIF_PACKS:
        pack_rows = _read_pack(pack)
        # the *_vi sibling packs (D-W7-VI-PACK) carry the same kind contract as their
        # en base — normalize the suffix so the per-pack kind check applies to both.
        base = pack[:-3] if pack.endswith("_vi") else pack
        for r in pack_rows:
            kind = r.get("kind")
            if base == "hooks":
                assert kind == "hook"
            elif base == "emotion_arcs":
                assert kind == "emotion_arc"
            elif base == _SCHEME_PACK:
                assert kind == "scheme"
                ia = r.get("info_asymmetry")
                assert ia, f"{r['code']} scheme missing info_asymmetry"
                assert ia.get("knows") and ia.get("deceived") and ia.get("gap"), \
                    f"{r['code']} info_asymmetry missing knows/deceived/gap"
                # D1: also mirrored onto annotations for W5's motif-level read.
                assert r.get("annotations", {}).get("info_asymmetry"), \
                    f"{r['code']} annotations.info_asymmetry missing (D1)"
            else:  # cultivation / revenge
                assert kind in {"sequence", "situation", "pattern"}, f"{r['code']} bad kind {kind}"


# ── test #4 — beats ordered 1..N contiguous, non-empty, every beat has an intent.
def test_beats_ordered_and_nonempty(rows):
    for r in rows:
        beats = r.get("beats", [])
        assert beats, f"{r['code']} has no beats"
        orders = sorted(b["order"] for b in beats)
        assert orders == list(range(1, len(beats) + 1)), \
            f"{r['code']} beat orders not 1..N contiguous: {orders}"
        for b in beats:
            assert b.get("intent"), f"{r['code']} beat {b.get('key')} missing intent"


# ── test #5 — every motif declares a subject; every actant is Greimas-valid.
def test_roles_have_subject(rows):
    for r in rows:
        roles = r.get("roles", [])
        actants = {role["actant"] for role in roles}
        assert "subject" in actants, f"{r['code']} declares no subject role"
        for role in roles:
            assert role["actant"] in GREIMAS_ACTANTS, f"{r['code']} bad actant {role['actant']}"


# ── test #6 — deterministic ids are pure + key on (code, language).
def test_deterministic_ids_stable():
    a1 = _motif_id("cultivation.face_slap", "en")
    a2 = _motif_id("cultivation.face_slap", "en")
    assert a1 == a2  # pure
    assert _motif_id("cultivation.face_slap", "en") != _motif_id("cultivation.closed_door_breakthrough", "en")
    # language is part of the key → distinct rows.
    assert _motif_id("cultivation.face_slap", "en") != _motif_id("cultivation.face_slap", "vi")
    # link ids are likewise pure + distinct.
    l1 = _link_id("a.b", "c.d", "precedes", "en")
    assert l1 == _link_id("a.b", "c.d", "precedes", "en")
    assert l1 != _link_id("a.b", "c.d", "composed_of", "en")


# ── test #7 — every link endpoint resolves; composed_of parents are patterns.
def test_link_endpoints_resolve(rows, edges):
    assert edges, "no link edges loaded"
    ids = {_motif_id(r["code"], r.get("language", "en")) for r in rows}
    for e in edges:
        assert e["from_id"] in ids, f"dangling from_id in {e}"
        assert e["to_id"] in ids, f"dangling to_id in {e}"
    # composed_of parents must be kind='pattern' (load_link_edges enforces; re-assert).
    by_id_kind = {_motif_id(r["code"], r.get("language", "en")): r.get("kind") for r in rows}
    for e in edges:
        if e["kind"] == "composed_of":
            assert by_id_kind[e["from_id"]] == "pattern"


# ── test #8 — the precedes graph over seeded codes is acyclic (matches the DB guard).
def test_precedes_chains_acyclic(rows, edges):
    # build adjacency over precedes edges only.
    adj: dict = {}
    for e in edges:
        if e["kind"] == "precedes":
            adj.setdefault(e["from_id"], []).append(e["to_id"])

    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict = {}

    def has_cycle(node) -> bool:
        color[node] = GRAY
        for nxt in adj.get(node, ()):
            c = color.get(nxt, WHITE)
            if c == GRAY:
                return True
            if c == WHITE and has_cycle(nxt):
                return True
        color[node] = BLACK
        return False

    for node in list(adj.keys()):
        if color.get(node, WHITE) == WHITE:
            assert not has_cycle(node), "precedes graph has a cycle"


# ── test #9 — copyright lint: no examples line names a banned source proper noun.
def test_examples_have_no_banned_proper_nouns(rows):
    for r in rows:
        for ex in r.get("examples", []):
            text = (ex.get("text") or "").lower()
            for banned in _BANNED_PROPER_NOUNS:
                assert not re.search(rf"\b{re.escape(banned)}\b", text), \
                    f"{r['code']} example names banned proper noun {banned!r}: {ex['text']!r}"


# ── test #10 — system tier is by OMISSION: no row sets owner_user_id.
def test_all_seed_rows_are_system_tier():
    from app.db.seed_motifs import _read_pack

    for pack in _MOTIF_PACKS:
        for r in _read_pack(pack):
            assert "owner_user_id" not in r, f"{r.get('code')} must not set owner_user_id"
            assert "embedding" not in r and "embedding_model" not in r, \
                f"{r.get('code')} must not set embedding (W3 owns the platform embed)"


# ── test #11 — no seed row is private (the both-NULL CHECK, §3.3 / D6).
def test_no_seed_row_is_private(rows):
    # The loader stamps every system row 'unlisted'; assert the contract constant + that
    # no pack row tries to override visibility to 'private'.
    assert _SYSTEM_VISIBILITY in ("unlisted", "public")
    assert _SYSTEM_VISIBILITY != "private"
    from app.db.seed_motifs import _read_pack

    for pack in _MOTIF_PACKS:
        for r in _read_pack(pack):
            assert r.get("visibility", _SYSTEM_VISIBILITY) != "private", \
                f"{r.get('code')} must not be private"


# ── bonus — inventory sanity: the pack count matches the W7 §2 inventory.
def test_inventory_counts(rows, edges):
    from app.db.seed_motifs import _read_pack

    counts = {pack: len(_read_pack(pack)) for pack in _MOTIF_PACKS}
    # en base packs (§2 inventory) — and each `*_vi` sibling mirrors its base 1:1.
    for base, n in (("cultivation", 11), ("revenge", 8), ("intrigue", 6),
                    ("hooks", 13), ("emotion_arcs", 6)):
        assert counts[base] == n, f"{base} count {counts[base]} != {n}"
        assert counts[f"{base}_vi"] == n, f"{base}_vi count {counts[f'{base}_vi']} != {n}"
    assert len(rows) == 88  # (11 + 8 + 6 + 13 + 6) × 2 languages (en + vi)
    # links.json is one manifest; the loader emits it per shared language → both the
    # en and vi chains are wired (D-W7-VI-PACK): 12 precedes + 7 composed_of, ×2.
    assert sum(1 for e in edges if e["kind"] == "precedes") == 24
    assert sum(1 for e in edges if e["kind"] == "composed_of") == 14

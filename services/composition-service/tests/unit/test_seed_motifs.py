"""W7 — system-tier motif seed-pack unit tests (no DB).

These validate the pack CONTENT + the loader's id logic + the copyright guard. They
run in the standard suite (no Postgres). The DB-gated idempotency / tier / NULL-embed
proofs live in tests/integration/db/test_seed_motifs.py.

Map to W7 §5: tests #1-#11.
"""

from __future__ import annotations

import re
import uuid

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
        create_view = {k: v for k, v in r.items()
                       if k not in ("source", "source_version", "language")}
        MotifCreateArgs.model_validate(create_view)
        # read-row model with the loader-stamped system fields.
        m = Motif.model_validate(
            {
                **r,
                "id": _motif_id(r["code"]),
                "owner_user_id": None,
                "visibility": _SYSTEM_VISIBILITY,
            }
        )
        assert m.owner_user_id is None
        assert m.source == "authored"  # W7 is authored-only


# ── test #2 — codes are unique OUTRIGHT (MOTIF-I18N: language left the identity key,
# so a code may no longer appear twice for any reason) + match the naming convention.
def test_codes_unique(rows):
    seen = set()
    genre_re = re.compile(r"^[a-z_]+\.[a-z_]+$")
    connective_re = re.compile(r"^(hook|emotion_arc)\.[a-z_]+$")
    for r in rows:
        assert r["code"] not in seen, f"duplicate code: {r['code']}"
        seen.add(r["code"])
        code = r["code"]
        assert genre_re.match(code) or connective_re.match(code), f"bad code shape: {code}"


# ── test #3 — kind matches the pack; schemes carry a full info_asymmetry.
def test_kind_matches_pack():
    from app.db.seed_motifs import _read_pack

    for pack in _MOTIF_PACKS:
        pack_rows = _read_pack(pack)
        base = pack
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
            else:  # every GENRE pack (cultivation/revenge/romance/mystery/rebirth/wuxia/survival)
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


# ── test #6 — deterministic ids are pure + keyed on `code` alone.
def test_deterministic_ids_stable():
    assert _motif_id("cultivation.face_slap") == _motif_id("cultivation.face_slap")  # pure
    assert _motif_id("cultivation.face_slap") != _motif_id("cultivation.closed_door_breakthrough")
    # MOTIF-I18N: the id formula still hashes a literal `en` segment even though language
    # left the identity key, because every already-seeded row in every environment carries
    # that id. Pin the exact value — "cleaning up" the formula would mint a second id per
    # code and re-insert the whole library as duplicates.
    assert str(_motif_id("cultivation.face_slap")) == str(
        uuid.uuid5(uuid.UUID("6d0746f0-0000-5000-8000-000000000001"),
                   "motif|en|cultivation.face_slap"))
    l1 = _link_id("a.b", "c.d", "precedes")
    assert l1 == _link_id("a.b", "c.d", "precedes")
    assert l1 != _link_id("a.b", "c.d", "composed_of")


# ── test #7 — every link endpoint resolves; composed_of parents are patterns.
def test_link_endpoints_resolve(rows, edges):
    assert edges, "no link edges loaded"
    ids = {_motif_id(r["code"]) for r in rows}
    for e in edges:
        assert e["from_id"] in ids, f"dangling from_id in {e}"
        assert e["to_id"] in ids, f"dangling to_id in {e}"
    # composed_of parents must be kind='pattern' (load_link_edges enforces; re-assert).
    by_id_kind = {_motif_id(r["code"]): r.get("kind") for r in rows}
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
    for base, n in (("cultivation", 11), ("revenge", 8), ("intrigue", 6),
                    ("hooks", 13), ("emotion_arcs", 6),
                    ("romance", 9), ("mystery", 8), ("rebirth", 8),
                    ("wuxia", 8), ("survival", 7)):
        assert counts[base] == n, f"{base} count {counts[base]} != {n}"
    # (11+8+6+13+6) original + (9+8+8+8+7) genre-breadth 2026-07-29 = 84.
    # MOTIF-I18N: ONE row per motif — this was 168 when every motif shipped twice.
    assert len(rows) == 84
    # links.json is one manifest and now emits ONE graph (it used to emit a parallel copy
    # per language): 12+34 precedes + 7+2 composed_of.
    assert sum(1 for e in edges if e["kind"] == "precedes") == 46
    assert sum(1 for e in edges if e["kind"] == "composed_of") == 9


# ── MOTIF-I18N — the seeder must survive its own tooling's output.
def test_a_FAILED_report_in_a_translations_dir_does_not_break_the_loader(tmp_path, monkeypatch):
    """scripts/motif_translate.py writes `_FAILED.json` ({pack: [keys]}) whenever a key
    exhausts its heal rounds — i.e. routinely. The loader globbed `*.json` and read that
    report as a translation file, taking a PACK name for a motif code and raising, so ONE
    failed key anywhere would stop composition-service from booting. Reproduced against
    the real loader before the fix; a report file must simply be ignored."""
    import json as _json

    from app.db import seed_motifs as sm

    tdir = tmp_path / "translations" / "xx"
    tdir.mkdir(parents=True)
    (tdir / "_FAILED.json").write_text(
        _json.dumps({"mystery": ["mystery.witness_who_lies|name"]}), encoding="utf-8")
    monkeypatch.setattr(sm, "_TRANSLATION_DIR", tmp_path / "translations")

    assert sm.load_translation_rows(sm.load_motif_rows()) == []


def test_a_recorded_source_hash_survives_an_english_edit(tmp_path, monkeypatch):
    """The staleness signal only means anything if the seeder REPORTS what the
    translation was made from rather than re-deriving it. Re-deriving stamps every
    translation as fresh no matter how far the English has moved — so editing a summary
    and not re-translating would ship stale Vietnamese under a fresh flag, which is the
    'git says one thing, production says another' shape this repo keeps hitting."""
    import json as _json

    from app.db import seed_motifs as sm

    rows = sm.load_motif_rows()
    code = rows[0]["code"]
    tdir = tmp_path / "translations" / "xx"
    tdir.mkdir(parents=True)
    (tdir / "pack.json").write_text(_json.dumps({code: {"name": "translated"}}), encoding="utf-8")
    (tdir / "_source_hash.json").write_text(
        _json.dumps({code: "made-from-an-older-english-summary"}), encoding="utf-8")
    monkeypatch.setattr(sm, "_TRANSLATION_DIR", tmp_path / "translations")

    got = sm.load_translation_rows(rows)
    assert len(got) == 1
    assert got[0]["source_content_hash"] == "made-from-an-older-english-summary", (
        "the seeder re-derived the hash and erased the staleness signal")


def test_a_translation_with_no_recorded_hash_is_assumed_in_sync(tmp_path, monkeypatch):
    """The hand-authored vi packs predate the sidecar. Absent a record, assume the
    translation matches the source it ships beside — which is true for them, and is what
    the seeder did for everything before the sidecar existed."""
    import json as _json

    from app.db import seed_motifs as sm
    from app.motif_i18n import extract_translatable, translatable_hash

    rows = sm.load_motif_rows()
    code = rows[0]["code"]
    tdir = tmp_path / "translations" / "xx"
    tdir.mkdir(parents=True)
    (tdir / "pack.json").write_text(_json.dumps({code: {"name": "translated"}}), encoding="utf-8")
    monkeypatch.setattr(sm, "_TRANSLATION_DIR", tmp_path / "translations")

    got = sm.load_translation_rows(rows)
    assert got[0]["source_content_hash"] == translatable_hash(extract_translatable(rows[0]))

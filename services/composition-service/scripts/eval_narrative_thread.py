"""FD-1 S4b — narrative_thread eval (dropped-promise-rate) + full-loop live-smoke.

Proves the ledger WORKS (the loop fires live) AND HELPS (fewer dropped promises).

For each of n promise-rich premises, build TWO works from the SAME premise+bios
(ON and OFF can't share outline nodes — a 2nd generate on the same node is an
idempotent replay), generate the full arc scene-by-scene on each:
  - arm ON  — settings.narrative_thread_enabled=true  (S2 opens/pays, S3 re-injects+steers)
  - arm OFF — flag off                                  (no ledger, no re-injection)
then a DISJOINT, ledger-BLIND promise-audit (re-detects promises from the PROSE,
NOT from narrative_thread) scores dropped_rate on each arm. Hypothesis: ON < OFF.

Anti-self-reinforcement (lesson): the audit must NOT read the ledger (else the OFF
arm scores 0-introduced by construction). The judge model is DISTINCT from the
drafter where the registry has two.

Inline FULL-LOOP LIVE-SMOKE on the ON arm of premise #1:
  open created (scene 1) → re-injected (scene 2, deterministic) → control OFF=0 →
  pays observed (best-effort, LLM-nondeterministic).

Usage: python eval_narrative_thread.py [n_premises]   (default 3 — PO: powered)
Dump : _nt_dump.json (untracked — both arms' arc text per premise)
"""
import base64
import json
import sys
import time
import urllib.request

GW = "http://localhost:3123"
COMP_INTERNAL = "http://localhost:8217"
GLOSSARY_INTERNAL = "http://localhost:8211"
INTERNAL_TOKEN = "dev_internal_token"
DUMP = "_nt_dump.json"

# Promise-RICH premises (foreshadows / open questions / stated goals / threats) so
# there is something to drop. Bios give the `present` lens identity grounding.
PREMISES = [
    ("A disgraced knight vows to retake a fallen keep before winter; an old debt, a "
     "hidden traitor among the survivors, and a sealed letter he refuses to open all "
     "shadow the march.",
     [("Kael", "Kael is a disgraced male knight, once warden of the border keep; grim and exiled, he seeks redemption."),
      ("Bryn", "Bryn is a loyal male scout, Kael's longtime companion, quick-witted and weather-worn."),
      ("Mira", "Mira is a sharp-eyed female quartermaster among the survivors, practical and unflinching.")]),
    ("A market thief steals a coded ledger, promises to deliver it before the festival, "
     "and discovers a name in it she cannot unsee; a watcher trails her, and a fence "
     "swears the ledger is cursed.",
     [("Sora", "Sora is a nimble young female street thief, wary and resourceful."),
      ("Den", "Den is a grizzled male informant and fence who warns Sora of danger, cautious and indebted."),
      ("Lia", "Lia is an ambitious female festival organizer secretly tied to the conspiracy, poised and persuasive.")]),
    ("Two estranged siblings inherit a haunted observatory and a dangerous ledger; their "
     "father's last note hints at a buried truth, the lawyer hides a clause, and the dome "
     "must be opened on the equinox or the estate is lost.",
     [("Aron", "Aron is the elder male sibling, a meticulous astronomer, reserved and guilt-ridden."),
      ("Vesa", "Vesa is the younger female sibling, estranged and skeptical, fierce and pragmatic."),
      ("Tomas", "Tomas is the family's aging male lawyer who keeps the dangerous ledger, formal and evasive.")]),
]


# ── http ──

def _req(method, path, token=None, body=None, timeout=600):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(GW + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode().strip()
    return json.loads(raw) if raw else {}


def _internal(base, path, body, timeout=600):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("X-Internal-Token", INTERNAL_TOKEN)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode().strip()
    return json.loads(raw) if raw else {}


def login():
    return _req("POST", "/v1/auth/login", body={"email": "claude-test@loreweave.dev",
                                                "password": "Claude@Test2026"})["access_token"]


def jwt_sub(token):
    p = token.split(".")[1]; p += "=" * (-len(p) % 4)
    return json.loads(base64.urlsafe_b64decode(p))["sub"]


def models(token):
    chat = [m for m in _req("GET", "/v1/model-registry/user-models?capability=chat",
                            token)["items"] if m["is_active"]]
    if not chat:
        raise RuntimeError("no active chat model registered")
    drafter = next((m for m in chat if "qwen3.6-35b" in m["provider_model_name"]), chat[0])
    # DISJOINT judge (anti-self-reinforcement) — a different model if one exists.
    judge = next((m for m in chat if m["user_model_id"] != drafter["user_model_id"]), drafter)
    return drafter["user_model_id"], judge["user_model_id"], judge["user_model_id"] != drafter["user_model_id"]


# ── grounding seed (mirrors eval_a_grounded) ──

def seed_bios(book, ch_ids, cast):
    links = [{"chapter_id": c, "chapter_title": f"Chapter {i+1}", "chapter_index": i + 1,
              "relevance": "appears"} for i, c in enumerate(ch_ids)]
    for name, bio in cast:
        er = _internal(GLOSSARY_INTERNAL, f"/internal/books/{book}/extract-entities",
                       {"source_language": "en",
                        "entities": [{"kind_code": "character", "name": name,
                                      "attributes": {}, "evidence": bio, "chapter_links": links}]})
        ents = er.get("entities") or []
        if ents:
            _internal(GLOSSARY_INTERNAL,
                      f"/internal/books/{book}/entities/{ents[0]['entity_id']}/canon-content",
                      {"short_description": bio})


def build_work(token, drafter, premise, cast, *, nt_on):
    """Build a book + 3 chapters + work + decompose plan; set the narrative_thread
    flag. Returns (proj, scenes-in-order)."""
    book = _req("POST", "/v1/books", token,
                {"title": f"NT {int(time.time()*1000) % 100000}", "original_language": "en"})["book_id"]
    chapters = [_req("POST", f"/v1/books/{book}/chapters", token,
                     {"original_language": "en", "title": f"Chapter {i}"})["chapter_id"]
                for i in range(1, 4)]
    proj = _req("POST", f"/v1/composition/books/{book}/work", token)["project_id"]
    # critic = drafter → no in-loop model thrash; the flag under test.
    _req("PATCH", f"/v1/composition/works/{proj}", token,
         {"settings": {"critic_model_source": "user_model", "critic_model_ref": drafter,
                       "narrative_thread_enabled": bool(nt_on)}})
    seed_bios(book, chapters, cast)

    tmpls = _req("GET", "/v1/composition/templates", token)["templates"]
    generic = next((t for t in tmpls if t["kind"] == "generic"), tmpls[0])
    preview = _req("POST", f"/v1/composition/works/{proj}/outline/decompose", token,
                   {"structure_template_id": generic["id"], "premise": premise,
                    "model_source": "user_model", "model_ref": drafter})
    commit = {"arc_title": generic["name"], "chapters": [{
        "chapter_id": c["chapter"]["chapter_id"], "title": c["chapter"]["title"],
        "intent": c["chapter"]["intent"], "beat_role": c["chapter"]["beat_role"],
        "scenes": [{"title": s["title"], "synopsis": s["synopsis"], "tension": s["tension"],
                    "present_entity_ids": s["present_entity_ids"]} for s in c["scenes"]],
    } for c in preview["chapters"]]}
    _req("POST", f"/v1/composition/works/{proj}/outline/decompose/commit", token, commit)
    tree = _req("GET", f"/v1/composition/works/{proj}/outline", token)
    scenes = [n for n in tree["nodes"] if n["kind"] == "scene" and n.get("beat_role")]
    scenes.sort(key=lambda x: (str(x.get("chapter_id")), x.get("story_order") or 0, x.get("rank") or ""))
    return proj, scenes


def gen_auto(token, proj, node_id, drafter):
    """Auto-generate one scene → the full response dict (text + reinjected_promise_count)."""
    return _req("POST", f"/v1/composition/works/{proj}/generate", token,
                {"outline_node_id": node_id, "mode": "auto", "operation": "draft_scene",
                 "model_source": "user_model", "model_ref": drafter, "reasoning": "off",
                 "guide": "", "max_output_tokens": 500})


def threads(token, proj, status="open"):
    return _req("GET", f"/v1/composition/works/{proj}/narrative-threads?status={status}", token)


def gen_arc(token, proj, scenes, drafter, *, smoke=None):
    """Generate every scene in order; concat the prose. When `smoke` is a dict,
    record the per-scene reinjected counts for the live-smoke (ON arm only)."""
    parts = []
    for i, n in enumerate(scenes):
        r = gen_auto(token, proj, n["id"], drafter)
        parts.append(r.get("text", ""))
        if smoke is not None:
            smoke.setdefault("reinjected", []).append(r.get("reinjected_promise_count", 0))
            if i == 0:
                smoke["open_after_scene1"] = threads(token, proj, "open").get("open_count", 0)
    return "\n\n".join(p for p in parts if p)


def audit(user_id, judge, arc_text):
    return _internal(COMP_INTERNAL, "/internal/composition/eval/promise-audit",
                     {"user_id": user_id, "model_source": "user_model", "model_ref": judge,
                      "arc_text": arc_text, "source_language": "en"})


def main():
    pos = [a for a in sys.argv[1:] if not a.startswith("--")]
    n = max(1, min(int(pos[0]) if pos else 3, len(PREMISES)))
    token = login()
    user_id = jwt_sub(token)
    drafter, judge, disjoint = models(token)
    print(f"user={user_id} drafter={drafter} judge={judge} disjoint_judge={disjoint} n={n}")
    if not disjoint:
        print("  ⚠ only ONE chat model registered — judge==drafter (self-reinforcement "
              "caveat ~4-5pp; register a 2nd model for a clean measure).")

    rows, dump = [], []
    for idx, (premise, cast) in enumerate(PREMISES[:n]):
        print(f"\n[{idx+1}/{n}] {premise[:64]}...")
        t0 = time.time()
        # arm OFF
        proj_off, sc_off = build_work(token, drafter, premise, cast, nt_on=False)
        off_text = gen_arc(token, proj_off, sc_off, drafter)
        off_open = threads(token, proj_off, "open").get("open_count", 0)
        # arm ON (collect live-smoke on the first premise)
        smoke = {} if idx == 0 else None
        proj_on, sc_on = build_work(token, drafter, premise, cast, nt_on=True)
        on_text = gen_arc(token, proj_on, sc_on, drafter, smoke=smoke)
        on_all = threads(token, proj_on, "all").get("threads", [])
        paid = sum(1 for t in on_all if t.get("status") == "paid")
        on_open = sum(1 for t in on_all if t.get("status") in ("open", "progressing"))

        a_off = audit(user_id, judge, off_text)
        a_on = audit(user_id, judge, on_text)
        rows.append((idx + 1, a_off, a_on, off_open, on_open, paid))
        dump.append({"premise": premise, "off": off_text, "on": on_text})
        print(f"    OFF dropped_rate={a_off['dropped_rate']:.2f} "
              f"({a_off['dropped_count']}/{a_off['introduced_count']}) | "
              f"ON dropped_rate={a_on['dropped_rate']:.2f} "
              f"({a_on['dropped_count']}/{a_on['introduced_count']}) | "
              f"ledger on: {on_open} open / {paid} paid | {time.time()-t0:.0f}s")

        # ── full-loop live-smoke (premise #1, ON arm) ──
        if smoke is not None:
            reinj = smoke.get("reinjected", [])
            open1 = smoke.get("open_after_scene1", 0)
            later_reinj = max(reinj[1:], default=0)  # any scene after the first
            print("\n  ── FULL-LOOP LIVE-SMOKE (ON arm, premise #1) ──")
            print(f"    [{'PASS' if open1 > 0 else 'WARN'}] S2 opened on scene 1: open_count={open1}")
            cond = (later_reinj > 0) if open1 > 0 else True  # only assertable if scene1 opened
            print(f"    [{'PASS' if cond else 'FAIL'}] S3 re-injected on a later scene: "
                  f"max reinjected_promise_count={later_reinj} (per-scene {reinj})")
            off_ctrl = threads(token, proj_off, "all").get("threads", [])
            print(f"    [{'PASS' if not off_ctrl else 'FAIL'}] control: OFF arm has NO ledger rows "
                  f"({len(off_ctrl)} rows, off_open={off_open})")
            print(f"    [{'PASS' if paid > 0 else 'OBSERVE'}] S2 paid a thread (best-effort, "
                  f"LLM-nondeterministic): {paid} paid")

    json.dump(dump, open(DUMP, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\ndrafts → {DUMP}")

    # ── summary ──
    off_mean = sum(r[1]["dropped_rate"] for r in rows) / len(rows)
    on_mean = sum(r[2]["dropped_rate"] for r in rows) / len(rows)
    wins = sum(1 for r in rows if r[2]["dropped_rate"] < r[1]["dropped_rate"])
    print(f"\n══ DROPPED-PROMISE-RATE (n={len(rows)}, judge {'disjoint' if disjoint else 'SELF'}) ══")
    print(f"  OFF mean={off_mean:.3f}  ON mean={on_mean:.3f}  "
          f"Δ={off_mean - on_mean:+.3f} (positive = ledger helps)")
    print(f"  ON beats OFF on {wins}/{len(rows)} books")
    print("  CAVEATS (review-impl LOW#2/#3): a tie/ceiling is NOT a pass; (a) the arms use "
          "SEPARATE decompose plans (per-work flag + 1:1 book:work is structural — can't "
          "share a plan across two works), so plan variance is noise; (b) re-injection can "
          "make the ON arm SURFACE more promises into prose → a bigger `introduced` "
          "denominator that may MASK a real drop-reduction. Read the per-book drops + the "
          "dump; don't over-claim a lift OR a null.")


if __name__ == "__main__":
    main()

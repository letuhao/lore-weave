#!/usr/bin/env python3
"""dev-model — resolve a BYOK model by ROLE, so nobody has to be told a UUID again.

WHY THIS EXISTS
---------------
`CLAUDE.md` used to say *"prefer a local chat model"* and list five of them. That
is not a default, it is a question — and the PO answered it by hand in session
after session. A first attempt at fixing it pinned the UUIDs into `CLAUDE.md`,
which is worse: **`user_model_id`s are per-machine.** Another developer's stack
has the same models under different ids, and a hardcoded table would send them to
a 404 or, much worse, to somebody else's row.

So the fix is a resolver. Ask for a ROLE — `chat`, `embedding`, `rerank`,
`web_search` — and get whatever *this* stack has, chosen by rules that are stated
here rather than remembered by anyone.

WHAT IT WILL NOT DO
-------------------
**It refuses to return a paid model unless you ask for one.** Provider kind, not
model name, decides: `lm_studio` and `ollama` are local and free; everything else
bills. A resolver that silently returned `gpt-4o` because the local stack was
down would spend real money to paper over an outage, so instead it fails and says
lm_studio is not running. Pass `--allow-paid` to mean it.

HOW IT CHOOSES
--------------
Preference is read from data the user already expressed, not from a name list
baked in here:

  1. capability flag must match the role
  2. free providers first (unless --allow-paid)
  3. `is_favorite` first
  4. then `sort_order` ascending — the order the user arranged in the UI
  5. then alias, for a stable tie-break

Usage:
    python scripts/dev-model.py chat                 # -> the user_model_id
    python scripts/dev-model.py embedding
    python scripts/dev-model.py --list               # what is here, and what it would pick
    python scripts/dev-model.py --env                # exportable lines for every role
    python scripts/dev-model.py chat --allow-paid
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

GATEWAY = os.environ.get("LOREWEAVE_GATEWAY_URL", "http://localhost:3123")
EMAIL = os.environ.get("LOREWEAVE_TEST_EMAIL", "claude-test@loreweave.dev")
PASSWORD = os.environ.get("LOREWEAVE_TEST_PASSWORD", "Claude@Test2026")

#: Provider kinds that run on the developer's own machine and cost nothing.
#: Keyed on the PROVIDER, never on the model name — a name list would go stale
#: every time a model was renamed, and would not generalise to a new local backend.
#:
#: A KIND NOT LISTED HERE IS TREATED AS BILLED. That is deliberate and it is the
#: safe direction: a new provider kind appearing on someone's stack should make
#: this tool refuse and say so, never quietly spend. The cost is that a genuinely
#: local backend nobody added here needs `--allow-paid` until it is added, which
#: is a nuisance rather than a bill.
#:
#: A better signal exists and is NOT used: the credential's `endpoint_base_url`
#: pointing at localhost would be data rather than a list. It needs a second API
#: call per model, and this stays a list until that is worth paying for.
FREE_KINDS = frozenset({
    "lm_studio", "ollama", "local", "llamacpp", "vllm",
    "rerank_local",          # the sibling local-rerank service (:28417)
})

#: role -> the capability flag a `user_model` must carry.
ROLES = {
    "chat": "chat",
    "embedding": "embedding",
    "rerank": "rerank",
    "web_search": "web_search",
    "tts": "tts",
    "tool_calling": "tool_calling",
}

#: role -> the env var the spikes and probes read, so `--env` is directly usable.
ENV_NAMES = {
    "chat": "GAMEGEN_MODEL_REF",
    "embedding": "GAMEGEN_EMBED_REF",
    "rerank": "GAMEGEN_RERANK_REF",
    "web_search": "GAMEGEN_SEARCH_REF",
}


def _post(path: str, body: dict) -> dict:
    req = urllib.request.Request(
        GATEWAY + path, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def _get(path: str, token: str) -> object:
    req = urllib.request.Request(
        GATEWAY + path, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_models() -> list[dict]:
    """Through the PUBLIC API as the test account — not the database.

    Going via SQL would need the postgres container's name, which differs per
    checkout, and would read another service's tables directly. The gateway route
    is documented, portable, and the same one the UI uses.
    """
    try:
        auth = _post("/v1/auth/login", {"email": EMAIL, "password": PASSWORD})
    except urllib.error.URLError as e:
        raise SystemExit(
            f"cannot reach the gateway at {GATEWAY}: {e}\n"
            f"Is the dev stack up? Override with LOREWEAVE_GATEWAY_URL.")
    token = auth.get("access_token") or auth.get("accessToken") or ""
    if not token:
        raise SystemExit(f"login as {EMAIL} returned no access token")
    data = _get("/v1/model-registry/user-models", token)
    if isinstance(data, dict):
        data = data.get("items") or data.get("user_models") or data.get("data") or []
    return [m for m in data if m.get("is_active")]


# PRESENT-AND-NULL DEFEATS `.get(key, default)`.
# It bit three times while writing this file — `sort_order`, `alias`, and
# `provider_kind` all come back as JSON null on rows the user never filled in, and
# `.get(k, default)` returns None for every one of them because the KEY EXISTS.
# The default only applies to a missing key, which is not the case that occurs.
# So both accessors below coerce rather than default, and nothing in this file
# reads a field straight off the dict.


def _order(m: dict) -> int:
    v = m.get("sort_order")
    return v if isinstance(v, int) else 10_000


def _s(m: dict, key: str, fallback: str = "?") -> str:
    v = m.get(key)
    return v if isinstance(v, str) and v else fallback


def is_free(m: dict) -> bool:
    return _s(m, "provider_kind", "").lower() in FREE_KINDS


def candidates(models: list[dict], role: str, allow_paid: bool) -> list[dict]:
    flag = ROLES[role]
    out = [m for m in models if (m.get("capability_flags") or {}).get(flag)]
    if not allow_paid:
        out = [m for m in out if is_free(m)]
    out.sort(key=lambda m: (not m.get("is_favorite", False), _order(m), _s(m, "alias")))
    return out


def resolve(models: list[dict], role: str, allow_paid: bool) -> dict:
    picks = candidates(models, role, allow_paid)
    if picks:
        return picks[0]

    # Fail LOUDLY, and distinguish the two failures — they need different fixes.
    paid = candidates(models, role, allow_paid=True)
    if paid and not allow_paid:
        names = ", ".join(f"{_s(m,'alias')} ({_s(m,'provider_kind')})" for m in paid[:4])
        raise SystemExit(
            f"no FREE model for role {role!r}. Paid ones exist: {names}.\n"
            f"Either start lm_studio, or pass --allow-paid to spend real money "
            f"deliberately.")
    raise SystemExit(
        f"no model at all for role {role!r} on this stack. Active models:\n" +
        "\n".join(f"  {m.get('alias','?'):<42} {m.get('provider_kind','?'):<12} "
                  f"{sorted((m.get('capability_flags') or {}).keys())}"
                  for m in models))


def internal_token() -> str | None:
    """Best-effort: the dev `/internal/*` token, another repeated lookup.

    Discovered rather than hardcoded — the container name differs per checkout.
    Returns None when docker is unavailable, and the caller says so rather than
    printing a guess.
    """
    try:
        names = subprocess.run(["docker", "ps", "--format", "{{.Names}}"],
                               capture_output=True, text=True, timeout=15).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    for n in names.splitlines():
        if "provider-registry" in n:
            try:
                out = subprocess.run(
                    ["docker", "exec", n.strip(), "printenv", "INTERNAL_SERVICE_TOKEN"],
                    capture_output=True, text=True, timeout=15).stdout.strip()
            except (OSError, subprocess.SubprocessError):
                return None
            return out or None
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("role", nargs="?", choices=sorted(ROLES))
    ap.add_argument("--list", action="store_true", help="show everything and the picks")
    ap.add_argument("--env", action="store_true", help="exportable lines for every role")
    ap.add_argument("--allow-paid", action="store_true",
                    help="permit a billed provider; off by default on purpose")
    a = ap.parse_args()

    models = fetch_models()

    if a.list:
        print(f"{len(models)} active model(s) for {EMAIL} via {GATEWAY}\n")
        for m in sorted(models, key=lambda m: (_order(m), _s(m, "alias"))):
            mark = "$" if not is_free(m) else " "
            fav = "*" if m.get("is_favorite") else " "
            print(f" {mark}{fav} {_s(m,'alias'):<44} {_s(m,'provider_kind'):<11} "
                  f"{_s(m,'user_model_id')}  "
                  f"{sorted((m.get('capability_flags') or {}).keys())}")
        print("\n  $ = billed   * = favourite\n\nwould pick:")
        for role in ("chat", "embedding", "rerank", "web_search"):
            try:
                p = resolve(models, role, a.allow_paid)
                print(f"  {role:<12} {_s(p,'alias'):<44} {_s(p,'user_model_id')}")
            except SystemExit as e:
                print(f"  {role:<12} — {str(e).splitlines()[0]}")
        return 0

    if a.env:
        for role, var in ENV_NAMES.items():
            try:
                p = resolve(models, role, a.allow_paid)
            except SystemExit:
                continue
            print(f"export {var}={_s(p,'user_model_id')}   # {_s(p,'alias')}")
        tok = internal_token()
        print(f"export INTERNAL_SERVICE_TOKEN={tok}" if tok else
              "# INTERNAL_SERVICE_TOKEN: docker unavailable — "
              "docker exec <provider-registry> printenv INTERNAL_SERVICE_TOKEN")
        return 0

    if not a.role:
        ap.error("give a role, or --list / --env")
    print(_s(resolve(models, a.role, a.allow_paid), "user_model_id"))
    return 0


if __name__ == "__main__":
    sys.exit(main())

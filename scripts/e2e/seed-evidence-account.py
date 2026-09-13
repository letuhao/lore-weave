#!/usr/bin/env python3
"""Seed a disposable stack so the MODEL-GATED journeys can actually run.

    python scripts/e2e/seed-evidence-account.py --base-url http://localhost:25174
    python scripts/e2e/seed-evidence-account.py --self-test

🔴 WHY THIS EXISTS, measured 2026-09-13 on a freshly built `lw-iso`.

Recording the authoring journey took removing FIVE blockers by hand, none of them written down
anywhere. Each one is the kind that looks like a broken product and is not:

  1. **No account.** `API login claude-test@loreweave.dev failed: 401`. The human-sim standard
     already warns that the documented account lives on `infra`, NOT on `lw-iso`.
  2. **The account that DID exist had an unknown password** — `register → 409`, `login → 401`.
     The iso volumes are not fresh; they carry data from earlier work (one owner holds 308 books).
  3. **Password policy**, which costs a round trip if you guess: the suite's own default is
     `Claude@Test2026`, and anything without a letter AND a digit gets
     `AUTH_VALIDATION_ERROR: invalid email or password policy`.
  4. **No BYOK model**, so `composition-journey` would have **SKIPPED** — `test.skip(chatModels
     .length < 1, 'needs a chat-tagged drafter + LM Studio')`. A skipped leg is not a passed leg,
     and a skip reads as success in a summary line.
  5. **`/onboarding`, not `/books`.** A freshly registered account lands on the chooser while
     `loginViaUI` waits for `**/books`. This is the exact defect the FIRST human-sim run recorded —
     *"an assumption that only ever described an account someone had already onboarded by hand"* —
     and it is still live. The flag is a SERVER preference (`hasSeenOnboarding`), not localStorage.

A recording nobody else can reproduce is an anecdote. This makes the five removable by command.

**It writes: an account, a BYOK provider credential, one chat-tagged model, two preferences.**
So it refuses any non-loopback target, for the same reason `assertDisposableTarget` does.

Exit 0 = seeded; 1 = a step failed; 2 = misuse / self-test failure / refused target.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_EMAIL = "iso-evidence@loreweave.dev"
DEFAULT_PASSWORD = "Claude@Test2026"      # letter + digit; the suite's own default
DEFAULT_BASE = "http://localhost:25174"   # lw-iso
LM_STUDIO_ENDPOINT = "http://host.docker.internal:1234"

#: Loopback only. These journeys REGISTER ACCOUNTS and SEED BOOKS, so pointing this at anything
#: shared would create junk under someone else's domain -- the hazard `assertDisposableTarget`
#: exists for, restated here because this script writes without Playwright ever loading.
LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1", "[::1]"}


def is_loopback(base_url: str) -> bool:
    host = urllib.parse.urlparse(base_url).hostname or ""
    return host in LOOPBACK_HOSTS


def _req(base: str, path: str, method: str = "GET", token: str | None = None,
         body: dict | None = None, timeout: int = 30) -> tuple[int, dict | str]:
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(base.rstrip("/") + path, data=data, method=method)
    r.add_header("Content-Type", "application/json")
    if token:
        r.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, raw


def self_test() -> int:
    fails = []
    for good in ("http://localhost:25174", "http://127.0.0.1:5174", "http://[::1]:1"):
        if not is_loopback(good):
            fails.append(f"refused a loopback target {good!r}")
    for bad in ("https://app.example.com", "http://10.0.0.5:25174", "http://example.com"):
        if is_loopback(bad):
            fails.append(f"ACCEPTED a non-loopback target {bad!r} -- this script WRITES")
    if fails:
        print("seed-evidence-account SELF-TEST FAILED:")
        for f in fails:
            print(f"  - {f}")
        return 2
    print("seed-evidence-account: self-test OK — accepts loopback, refuses anything else "
          "(this script registers an account and writes provider credentials)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default=DEFAULT_BASE)
    ap.add_argument("--email", default=DEFAULT_EMAIL)
    ap.add_argument("--password", default=DEFAULT_PASSWORD)
    ap.add_argument("--model", default="qwen/qwen3.8-27b",
                    help="a model LM Studio actually serves; the e2e helper hardcodes "
                         "qwen/qwen3.6-35b-a3b, which is often not the one loaded")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return self_test()

    if not is_loopback(a.base_url):
        print(f"seed-evidence-account: REFUSED — {a.base_url!r} is not loopback.")
        print("  -> this script REGISTERS AN ACCOUNT and writes provider credentials. Pointing it")
        print("     at a shared deployment creates junk under someone else's domain.")
        return 2

    b = a.base_url
    print(f"target: {b}  (loopback, disposable)")

    # 1. account -- 409 means it already exists, which is fine IF the password matches.
    st, _ = _req(b, "/v1/auth/register", "POST",
                 body={"email": a.email, "password": a.password, "name": "Evidence Run"})
    print(f"  register            -> {st}" + ("  (already existed)" if st == 409 else ""))

    st, payload = _req(b, "/v1/auth/login", "POST",
                       body={"email": a.email, "password": a.password})
    if st != 200 or not isinstance(payload, dict) or "access_token" not in payload:
        print(f"  login               -> {st}  {payload}")
        print("\nFAIL — cannot log in. If register returned 409, the account exists with a")
        print("DIFFERENT password: pass --email to seed a fresh one rather than guessing.")
        return 1
    token = payload["access_token"]
    print("  login               -> 200")

    # 2. BYOK provider. A local backend is registered exactly like any other credential --
    #    never as a per-service *_URL env var (that shortcut is D-RERANK-NOT-BYOK).
    st, payload = _req(b, "/v1/model-registry/providers", token=token)
    if st != 200:
        print(f"  list providers      -> {st}  {payload}")
        return 1
    items = payload.get("items", []) if isinstance(payload, dict) else []
    prov = next((p for p in items if p.get("provider_kind") == "lm_studio"), None)
    if prov:
        provider_id = prov["provider_credential_id"]
        print(f"  provider            -> reused {provider_id}")
    else:
        st, payload = _req(b, "/v1/model-registry/providers", "POST", token=token, body={
            "provider_kind": "lm_studio", "display_name": "LM Studio (evidence run)",
            "endpoint_base_url": LM_STUDIO_ENDPOINT, "api_standard": "lm_studio"})
        if st not in (200, 201):
            print(f"  create provider     -> {st}  {payload}")
            return 1
        provider_id = payload["provider_credential_id"]
        print(f"  provider            -> created {provider_id}")

    # 3. a CHAT-tagged model, or the journeys SKIP rather than run.
    q = "/v1/model-registry/user-models?include_inactive=true&provider_kind=lm_studio"
    st, payload = _req(b, q, token=token)
    models = payload.get("items", []) if isinstance(payload, dict) else []
    if not any(m.get("provider_model_name") == a.model for m in models):
        st, payload = _req(b, "/v1/model-registry/user-models", "POST", token=token, body={
            "provider_credential_id": provider_id, "provider_model_name": a.model,
            "alias": "Evidence drafter", "context_length": 120_000,
            "capability_flags": {"_capability": "chat"}})
        if st not in (200, 201):
            print(f"  create user model   -> {st}  {payload}")
            return 1
    st, payload = _req(b, q, token=token)
    models = payload.get("items", []) if isinstance(payload, dict) else []
    print(f"  chat model(s)       -> {len(models)}: "
          f"{', '.join(m.get('provider_model_name', '?') for m in models)}")
    if not models:
        print("\nFAIL — no chat model on the account, so every model-gated journey will SKIP.")
        print("  -> a skipped leg is not a passed leg, and a skip reads as success in a summary.")
        return 1

    # 4. onboarding. Without this a fresh account lands on /onboarding and loginViaUI waits
    #    forever for **/books.
    st, payload = _req(b, "/v1/me/preferences", "PATCH", token=token,
                       body={"prefs": {"hasSeenOnboarding": True,
                                       "hasSeenStudioOnboarding": True}})
    print(f"  onboarding prefs    -> {st}")
    if st not in (200, 204):
        print(f"\nFAIL — could not set the onboarding flag: {payload}")
        return 1

    print(f"\nSeeded. Run the suite with:\n"
          f"  PLAYWRIGHT_TEST_EMAIL={a.email} PLAYWRIGHT_TEST_PASSWORD=... \\\n"
          f"  PLAYWRIGHT_BASE_URL={b} PLAYWRIGHT_EVIDENCE=1 PLAYWRIGHT_ALLURE=1 npx playwright test")
    return 0


if __name__ == "__main__":
    sys.exit(main())

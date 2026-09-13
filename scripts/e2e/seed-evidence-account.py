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
    ap.add_argument("--allow-second-model", action="store_true",
                    help="register a model even when the account already has an ACTIVE one. "
                         "Off by default because a SECOND active model arms the distinct-critic "
                         "path, which loads TWO models at once -- see the note on SECOND_MODEL_WARNING")
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

    # 🔴 A SECOND ACTIVE MODEL IS NOT ADDITIVE -- IT ARMS A DIFFERENT CODE PATH.
    #
    # Several specs want a drafter AND a distinct critic, and they GUARD on the count:
    #
    #     test.skip(chatModels.length < 1 || allModels.length < 2,
    #       'needs a chat-tagged drafter + >=1 distinct active critic model + LM Studio');
    #     const critic = allModels.find((m) => m.user_model_id !== drafter.user_model_id)!;
    #
    # With ONE active model those tests SKIP. With TWO they RUN, and one test then asks the
    # backend for two models at once. Measured 2026-09-13: this seeder added a second model to an
    # account that already had one, which flipped that guard, and a 35B + 27B pair was requested
    # concurrently -- the developer's machine ran out of memory and LM Studio answered
    # "Engine protocol startup was aborted" to everything after.
    #
    # So the count is a SAFETY setting, not a convenience, and raising it is opt-in.
    active = [m for m in models if m.get("is_active")]
    already = any(m.get("provider_model_name") == a.model for m in models)
    if active and not already and not a.allow_second_model:
        print(f"  chat model(s)       -> {len(active)} active already: "
              f"{', '.join(m.get('provider_model_name', '?') for m in active)}")
        print("\n  REFUSING to add a second ACTIVE model.")
        print("  A second one arms the distinct-critic path, which loads TWO models at once and")
        print("  can exhaust memory. Pass --allow-second-model only if the pair FITS -- two small")
        print("  models, not a 35B beside a 27B. With one, those tests SKIP and say so.")
        models = active
    elif not already:
        st, payload = _req(b, "/v1/model-registry/user-models", "POST", token=token, body={
            "provider_credential_id": provider_id, "provider_model_name": a.model,
            "alias": "Evidence drafter", "context_length": 120_000,
            "capability_flags": {"_capability": "chat"}})
        if st not in (200, 201):
            print(f"  create user model   -> {st}  {payload}")
            return 1
    st, payload = _req(b, q, token=token)
    models = payload.get("items", []) if isinstance(payload, dict) else []
    # ACTIVE is the number that decides behaviour -- `listActiveModels` filters on it, and the
    # distinct-critic guard counts the filtered list. Reporting the raw total said "2" on an
    # account with ONE active model, which is the same misleading-count shape this script exists
    # to stop. Inactive rows are shown, separately, so they are visible without being counted.
    active = [m for m in models if m.get("is_active")]
    inactive = [m for m in models if not m.get("is_active")]
    print(f"  chat model(s)       -> {len(active)} ACTIVE: "
          f"{', '.join(m.get('provider_model_name', '?') for m in active) or '(none)'}")
    if inactive:
        print(f"                         {len(inactive)} inactive (not counted): "
              f"{', '.join(m.get('provider_model_name', '?') for m in inactive)}")
    if not active:
        print("\nFAIL -- no ACTIVE chat model, so every model-gated journey will SKIP.")
        print("  -> a skipped leg is not a passed leg, and a skip reads as success in a summary.")
        return 1

    # 4. DEFAULT models per capability. Having a model on the account is NOT the same as having
    #    one SELECTED, and the difference is most of a suite. Measured 2026-09-13: with a chat
    #    model registered but no default, 23 of the first 65 tests failed, and the error was always
    #    the same shape --
    #        TimeoutError: locator.click: waiting for getByTitle('Send')
    #        locator resolved to <button DISABLED data-testid="chat-send-button" ...>
    #    -- a disabled send button, because nothing was picked. `docs/dev/LOCAL_TEST_ENV.example.md`
    #    says it outright: "user_default_models is typically empty on a fresh account".
    #
    #    `composer` is set DELIBERATELY and is not the same decision as `chat`. The product keeps
    #    them apart on purpose (settings/api.ts: "picking a model for conversation is not consent
    #    to spend it on the most expensive call on the platform"). On a throwaway stack pointed at
    #    a LOCAL model that reasoning does not apply, and leaving it unset silently gates every
    #    drafting journey. It is set here and named here rather than inherited quietly.
    # From ACTIVE only. `models[0]` could be an inactive row -- it was, in the run that found
    # this -- and a default pointing at an inactive model is a control that looks set and
    # resolves to nothing.
    model_id = active[0].get("user_model_id")
    for capability in ("chat", "composer"):
        st, payload = _req(b, f"/v1/model-registry/default-models/{capability}", "PUT",
                           token=token, body={"user_model_id": model_id})
        print(f"  default[{capability:8}]    -> {st}")
        if st not in (200, 204):
            print(f"\nFAIL -- could not set the {capability} default: {payload}")
            print("  -> without it the UI has a model available but none SELECTED, and every")
            print("     journey that sends a message fails on a disabled control.")
            return 1

    # 5. onboarding. Without this a fresh account lands on /onboarding and loginViaUI waits
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

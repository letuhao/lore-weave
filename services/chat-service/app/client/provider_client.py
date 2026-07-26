from loreweave_internal_client import build_internal_client

from app.config import settings
from app.middleware.trace_id import trace_id_var
from app.models import ProviderCredentials


class ProviderRegistryClient:
    def __init__(self) -> None:
        self._base = settings.provider_registry_internal_url
        self._token = settings.internal_service_token

    async def resolve(self, model_source: str, model_ref: str, user_id: str) -> ProviderCredentials:
        url = f"{self._base}/internal/credentials/{model_source}/{model_ref}"
        # W5 (ephemeral wave): shared factory bakes X-Internal-Token + JSON + trace.
        async with build_internal_client(
            self._base, internal_token=self._token,
            timeout_s=10, trace_id_provider=trace_id_var.get,
        ) as client:
            resp = await client.get(url, params={"user_id": user_id})
        if resp.status_code == 404:
            raise ValueError("model not found or inactive")
        resp.raise_for_status()
        return ProviderCredentials(**resp.json())

    async def get_default_model(
        self, capability: str, user_id: str
    ) -> tuple[str, str] | None:
        """Fetch the user's Account-tier default model for a capability (spec §3.4).
        Returns (model_source, model_ref) or None when unset/unsupported. Best-effort:
        a transient upstream error returns None (the tier simply contributes nothing;
        the resolver falls to the next tier) — never raises into the turn."""
        url = f"{self._base}/internal/default-models/{capability}"
        try:
            async with build_internal_client(
                self._base, internal_token=self._token,
                timeout_s=5, trace_id_provider=trace_id_var.get,
            ) as client:
                resp = await client.get(url, params={"user_id": user_id})
            if resp.status_code == 200:
                data = resp.json()
                return (data.get("model_source", "user_model"), data["user_model_id"])
            return None  # 404 (unset) / 400 (unsupported capability) / anything else
        except Exception:
            return None

    async def price_voice(
        self, model_source: str, model_ref: str, user_id: str, kind: str, units: float
    ) -> float:
        """C6 / SD-C6 — resolve the $ cost of ONE STT/TTS invocation from the model's registered rate
        (per_second for kind='stt' with units=audio-seconds; per_kchar for kind='tts' with units=chars).
        The rate lives with the model in provider-registry (invariant: never hardcode a rate here).
        Best-effort: any error / not-found / unpriced ⇒ 0.0 (a local Whisper/Kokoro is genuinely $0, so
        an un-priced voice model correctly contributes no cost rather than blocking the turn).

        cold-review HIGH-1/MED-4 — a genuinely-unpriced model (status != 'ok') is WARNED, so a PAID
        cloud voice model that silently bills $0 (e.g. it carries per_kchar but not per_second, or a
        transient pricing error) is OBSERVABLE. A local $0 model returns status='ok' (priced, cost 0)
        and does NOT warn — the warn fires only for the real revenue-drop cases."""
        import logging as _logging
        url = f"{self._base}/internal/billing/price-voice"
        try:
            async with build_internal_client(
                self._base, internal_token=self._token,
                timeout_s=5, trace_id_provider=trace_id_var.get,
            ) as client:
                resp = await client.post(url, json={
                    "owner_user_id": user_id, "model_source": model_source,
                    "model_ref": model_ref, "kind": kind, "units": units,
                })
            if resp.status_code == 200:
                data = resp.json()
                status = data.get("status")
                if status != "ok":
                    _logging.getLogger(__name__).warning(
                        "voice %s model %s/%s priced as %s (cost $0) — a PAID model billing $0 is a "
                        "revenue drop; confirm it carries the right rate (per_second for STT, per_kchar "
                        "for TTS)", kind, model_source, model_ref, status)
                return float(data.get("cost_usd", 0.0) or 0.0)
            _logging.getLogger(__name__).warning(
                "voice price-voice HTTP %s for %s/%s — billing $0 (transient?); a paid model's cost is "
                "silently dropped on this turn", resp.status_code, model_source, model_ref)
            return 0.0
        except Exception as exc:
            _logging.getLogger(__name__).warning("voice price-voice failed (%s) — billing $0", exc)
            return 0.0

    async def is_live(self, model_source: str, model_ref: str, user_id: str) -> bool:
        """Liveness probe for the settings resolver (spec §3.1). Owner-scoped —
        reuses the existing credential-resolve route (404 ⇒ not found / inactive
        / not-owned). A transient/upstream error (non-404) is treated as
        NOT-dead (returns True) so a flaky provider-registry never silently
        demotes a user's chosen model to a lower tier; the real resolve at submit
        is still authoritative.

        NB: this decrypts credentials (heavier than a pure liveness check). The
        resolver validates only the small DISTINCT candidate set, so cost is
        bounded; a dedicated batch liveness route is a later optimization."""
        try:
            await self.resolve(model_source, model_ref, user_id)
            return True
        except ValueError:
            return False
        except Exception:
            return True


_client: ProviderRegistryClient | None = None


def get_provider_client() -> ProviderRegistryClient:
    global _client
    if _client is None:
        _client = ProviderRegistryClient()
    return _client

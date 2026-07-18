import logging
from uuid import uuid4

from loreweave_internal_client import build_internal_client

from app.config import settings
from app.middleware.trace_id import trace_id_var

logger = logging.getLogger(__name__)


class BillingClient:
    def __init__(self) -> None:
        self._base = settings.usage_billing_service_url
        # D-CHAT-BILLING-01: usage-billing's internal API enforces
        # X-Internal-Token (services/usage-billing-service/internal/api/server.go).
        # Mirrors the pattern in provider_client.py + knowledge_client.py.
        # Without this every per-model usage record was rejected 401
        # ("invalid internal token") — best-effort logging swallowed it,
        # which is exactly why it shipped broken at birth and was only
        # caught by the session-58 cycle-1 live smoke.
        self._token = settings.internal_service_token

    async def log_usage(
        self,
        user_id: str,
        model_source: str,
        model_ref: str,
        provider_kind: str,
        input_tokens: int,
        output_tokens: int,
        session_id: str,
        message_id: str,
        input_payload: dict | list | None = None,
        output_payload: dict | str | None = None,
        purpose: str = "chat",
        cost_usd: float | None = None,
    ) -> None:
        # WS-4.2b — `purpose` lets voice record STT/TTS usage under a distinct lane
        # ('voice_stt' / 'voice_tts') instead of masquerading as chat. STT is metered by
        # audio-seconds, TTS by characters (NOT tokens) — those raw counts ride in the
        # payload; token fields stay 0 so the token-priced cost is not FAKED (precise
        # per-minute/per-char pricing is the billing cost-model follow-on, tracked).
        payload = {
            "request_id": str(uuid4()),
            "owner_user_id": user_id,
            "model_source": model_source,
            "model_ref": model_ref,
            "provider_kind": provider_kind,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "request_status": "success",
            "purpose": purpose,
            "input_payload": input_payload or {},
            "output_payload": output_payload if isinstance(output_payload, dict) else {"content": output_payload or ""},
        }
        # C6 — an authoritative per-invocation cost (e.g. the STT/TTS $ resolved from provider-registry's
        # per_second/per_kchar rate). usage-billing honours `total_cost_usd` verbatim (its override path),
        # so a priced voice record no longer lands at $0. Omitted ⇒ the token-based fallback (chat).
        if cost_usd is not None:
            payload["total_cost_usd"] = cost_usd
        try:
            # W5 (ephemeral wave): shared factory bakes X-Internal-Token + JSON + trace.
            async with build_internal_client(
                self._base, internal_token=self._token,
                timeout_s=10, trace_id_provider=trace_id_var.get,
            ) as client:
                resp = await client.post(
                    f"{self._base}/internal/model-billing/record",
                    json=payload,
                )
                if resp.status_code >= 400:
                    logger.warning("Billing record failed (%d): %s", resp.status_code, resp.text[:200])
        except Exception as exc:
            logger.debug("Billing log_usage failed: %s", exc)


_client: BillingClient | None = None


def get_billing_client() -> BillingClient:
    global _client
    if _client is None:
        _client = BillingClient()
    return _client

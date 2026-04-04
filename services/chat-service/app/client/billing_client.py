import logging
from uuid import uuid4

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class BillingClient:
    def __init__(self) -> None:
        self._base = settings.usage_billing_service_url

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
    ) -> None:
        payload = {
            "request_id": str(uuid4()),
            "owner_user_id": user_id,
            "model_source": model_source,
            "model_ref": model_ref,
            "provider_kind": provider_kind,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "request_status": "success",
            "purpose": "chat",
        }
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(f"{self._base}/internal/model-billing/record", json=payload)
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

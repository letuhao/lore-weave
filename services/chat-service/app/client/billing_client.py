import httpx

from app.config import settings


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
            "owner_user_id": user_id,
            "model_source": model_source,
            "model_ref": model_ref,
            "provider_kind": provider_kind,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "source": "chat",
            "source_ref": message_id,
        }
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(f"{self._base}/v1/model-billing/usage", json=payload)
        except Exception:
            pass  # billing is best-effort, never block the stream


_client: BillingClient | None = None


def get_billing_client() -> BillingClient:
    global _client
    if _client is None:
        _client = BillingClient()
    return _client

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


_client: ProviderRegistryClient | None = None


def get_provider_client() -> ProviderRegistryClient:
    global _client
    if _client is None:
        _client = ProviderRegistryClient()
    return _client

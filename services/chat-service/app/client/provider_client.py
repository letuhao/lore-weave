import httpx

from app.config import settings
from app.models import ProviderCredentials


class ProviderRegistryClient:
    def __init__(self) -> None:
        self._base = settings.provider_registry_internal_url
        self._token = settings.internal_service_token

    async def resolve(self, model_source: str, model_ref: str, user_id: str) -> ProviderCredentials:
        url = f"{self._base}/internal/credentials/{model_source}/{model_ref}"
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                url,
                headers={"X-Internal-Token": self._token},
                params={"user_id": user_id},
            )
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

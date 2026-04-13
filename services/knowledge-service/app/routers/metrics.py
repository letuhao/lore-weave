"""Prometheus /metrics endpoint (K6.5).

No JWT dependency — knowledge-service is internal-only and the
scraper talks to it directly. If the service is later exposed via
the gateway, /metrics must be explicitly denied there.
"""

from fastapi import APIRouter
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.metrics import registry

router = APIRouter(tags=["metrics"])


@router.get("/metrics")
async def metrics() -> Response:
    return Response(
        content=generate_latest(registry),
        media_type=CONTENT_TYPE_LATEST,
    )

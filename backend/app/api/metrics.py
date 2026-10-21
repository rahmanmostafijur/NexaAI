"""Prometheus scrape endpoint, mounted at `/metrics` (outside `/api`)."""

from __future__ import annotations

import hmac
import ipaddress

from fastapi import APIRouter, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.api.deps import SettingsDep
from app.core.errors import ForbiddenError, NotFoundError, UnauthorizedError

router = APIRouter(include_in_schema=False)


def _is_direct_private_caller(request: Request) -> bool:
    """True for a caller on the loopback/private network that did not come through a proxy."""
    if "x-forwarded-for" in request.headers or request.client is None:
        return False
    try:
        address = ipaddress.ip_address(request.client.host)
    except ValueError:
        return False
    return address.is_loopback or address.is_private


@router.get("/metrics")
async def metrics(request: Request, settings: SettingsDep) -> Response:
    if not settings.metrics_enabled:
        raise NotFoundError("Not found")
    expected = settings.metrics_token.get_secret_value()
    if expected:
        header = request.headers.get("authorization", "")
        presented = header[7:] if header.lower().startswith("bearer ") else ""
        if not hmac.compare_digest(presented.encode(), expected.encode()):
            raise UnauthorizedError("A valid metrics token is required.")
    elif not _is_direct_private_caller(request):
        raise ForbiddenError("Metrics are only available to local callers; set METRICS_TOKEN.")
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

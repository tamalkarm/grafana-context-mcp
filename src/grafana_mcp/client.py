from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx

from .config import Settings


class GrafanaApiError(RuntimeError):
    """A Grafana API request failed."""


class GrafanaClient:
    def __init__(self, settings: Settings) -> None:
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {settings.token}",
        }
        if settings.org_id:
            headers["X-Grafana-Org-Id"] = settings.org_id
        self._client = httpx.AsyncClient(
            base_url=f"{settings.url}/",
            headers=headers,
            timeout=settings.timeout_seconds,
            verify=settings.verify_ssl,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def _request(
        self, method: str, path: str, *, params: dict[str, Any] | None = None,
        json: Any = None,
    ) -> Any:
        try:
            response = await self._client.request(method, path.lstrip("/"), params=params, json=json)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:1000]
            raise GrafanaApiError(
                f"Grafana returned HTTP {exc.response.status_code} for {method} {path}: {detail}"
            ) from exc
        except httpx.RequestError as exc:
            raise GrafanaApiError(f"Could not reach Grafana for {method} {path}: {exc}") from exc

        if response.status_code == 204 or not response.content:
            return None
        try:
            return response.json()
        except ValueError as exc:
            raise GrafanaApiError(f"Grafana returned non-JSON content for {method} {path}") from exc

    async def list_datasources(self) -> list[dict[str, Any]]:
        return await self._request("GET", "/api/datasources")

    async def get_datasource(self, uid: str) -> dict[str, Any]:
        return await self._request("GET", f"/api/datasources/uid/{quote(uid, safe='')}")

    async def check_datasource_health(self, uid: str) -> dict[str, Any]:
        return await self._request("GET", f"/api/datasources/uid/{quote(uid, safe='')}/health")

    async def search_dashboards(
        self, query: str = "", tag: str | None = None, limit: int = 50,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"query": query, "type": "dash-db", "limit": limit}
        if tag:
            params["tag"] = tag
        return await self._request("GET", "/api/search", params=params)

    async def get_dashboard(self, uid: str) -> dict[str, Any]:
        return await self._request("GET", f"/api/dashboards/uid/{quote(uid, safe='')}")

    async def query_datasource(self, queries: list[dict[str, Any]], from_: str, to: str) -> dict[str, Any]:
        return await self._request(
            "POST", "/api/ds/query", json={"queries": queries, "from": from_, "to": to}
        )

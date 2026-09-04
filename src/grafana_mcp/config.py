from __future__ import annotations

import os
from dataclasses import dataclass


def _read_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be true or false")


@dataclass(frozen=True, slots=True)
class Settings:
    url: str
    token: str
    org_id: str | None = None
    timeout_seconds: float = 30.0
    verify_ssl: bool = True

    @classmethod
    def from_env(cls) -> Settings:
        url = os.getenv("GRAFANA_URL", "").strip().rstrip("/")
        token = os.getenv("GRAFANA_SERVICE_ACCOUNT_TOKEN", "").strip()
        if not url:
            raise RuntimeError("GRAFANA_URL is required")
        if not token:
            raise RuntimeError("GRAFANA_SERVICE_ACCOUNT_TOKEN is required")
        if not url.startswith(("http://", "https://")):
            raise RuntimeError("GRAFANA_URL must start with http:// or https://")

        try:
            timeout = float(os.getenv("GRAFANA_TIMEOUT_SECONDS", "30"))
        except ValueError as exc:
            raise RuntimeError("GRAFANA_TIMEOUT_SECONDS must be numeric") from exc
        if timeout <= 0:
            raise RuntimeError("GRAFANA_TIMEOUT_SECONDS must be greater than zero")

        return cls(
            url=url,
            token=token,
            org_id=os.getenv("GRAFANA_ORG_ID") or None,
            timeout_seconds=timeout,
            verify_ssl=_read_bool("GRAFANA_VERIFY_SSL", True),
        )

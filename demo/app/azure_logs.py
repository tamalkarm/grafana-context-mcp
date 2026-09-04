from __future__ import annotations

import atexit
import json
import logging
import os
import queue
import sys
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from azure.core.exceptions import AzureError


class LogsClient(Protocol):
    def upload(self, *, rule_id: str, stream_name: str, logs: list[dict[str, Any]]) -> None: ...


@dataclass(frozen=True, slots=True)
class AzureLogsSettings:
    endpoint: str
    rule_id: str
    stream_name: str
    batch_size: int = 25
    flush_interval_seconds: float = 5.0

    @classmethod
    def from_env(
        cls,
        stream_variable: str = "AZURE_MONITOR_STREAM_NAME",
        rule_variable: str = "AZURE_MONITOR_DCR_RULE_ID",
    ) -> AzureLogsSettings | None:
        values = {
            "endpoint": os.getenv("AZURE_MONITOR_ENDPOINT", "").strip(),
            "rule_id": os.getenv(rule_variable, "").strip(),
            "stream_name": os.getenv(stream_variable, "").strip(),
        }
        configured = [name for name, value in values.items() if value]
        if not configured:
            return None
        if len(configured) != len(values):
            missing = [name for name, value in values.items() if not value]
            missing_names = [
                stream_variable
                if name == "stream_name"
                else rule_variable
                if name == "rule_id"
                else "AZURE_MONITOR_ENDPOINT"
                for name in missing
            ]
            raise RuntimeError(
                f"Azure log ingestion is partially configured; missing: {', '.join(missing_names)}"
            )

        batch_size = int(os.getenv("AZURE_MONITOR_BATCH_SIZE", "25"))
        flush_interval = float(os.getenv("AZURE_MONITOR_FLUSH_INTERVAL_SECONDS", "5"))
        if batch_size < 1 or batch_size > 1000:
            raise RuntimeError("AZURE_MONITOR_BATCH_SIZE must be between 1 and 1000")
        if flush_interval <= 0:
            raise RuntimeError("AZURE_MONITOR_FLUSH_INTERVAL_SECONDS must be greater than zero")
        return cls(**values, batch_size=batch_size, flush_interval_seconds=flush_interval)


def create_azure_client(endpoint: str) -> LogsClient:
    from azure.identity import DefaultAzureCredential
    from azure.monitor.ingestion import LogsIngestionClient

    credential = DefaultAzureCredential()
    return LogsIngestionClient(endpoint=endpoint, credential=credential)


class AzureLogExporter:
    def __init__(
        self,
        settings: AzureLogsSettings,
        client_factory: Callable[[str], LogsClient] = create_azure_client,
    ) -> None:
        self._settings = settings
        self._client = client_factory(settings.endpoint)
        self._queue: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=10_000)
        self._stopped = threading.Event()
        self._worker = threading.Thread(target=self._run, name="azure-log-exporter", daemon=True)
        self._worker.start()
        atexit.register(self.close)

    def emit(self, record: dict[str, Any]) -> None:
        try:
            self._queue.put_nowait(record)
        except queue.Full:
            logging.getLogger(__name__).error("Azure log queue is full; dropping one record")

    def close(self) -> None:
        if self._stopped.is_set():
            return
        self._stopped.set()
        self._worker.join(timeout=self._settings.flush_interval_seconds + 5)

    def _run(self) -> None:
        while not self._stopped.is_set() or not self._queue.empty():
            batch = self._next_batch()
            if not batch:
                continue
            try:
                self._client.upload(
                    rule_id=self._settings.rule_id,
                    stream_name=self._settings.stream_name,
                    logs=batch,
                )
            except AzureError:
                logging.getLogger(__name__).exception(
                    "Azure Monitor log upload failed for a batch of %d records", len(batch)
                )

    def _next_batch(self) -> list[dict[str, Any]]:
        try:
            first = self._queue.get(timeout=self._settings.flush_interval_seconds)
        except queue.Empty:
            return []

        batch = [first]
        deadline = time.monotonic() + self._settings.flush_interval_seconds
        while len(batch) < self._settings.batch_size:
            try:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                batch.append(self._queue.get(timeout=remaining))
            except queue.Empty:
                break
        return batch


def write_json_log(record: dict[str, Any]) -> None:
    print(json.dumps(record, separators=(",", ":"), default=str), file=sys.stdout, flush=True)

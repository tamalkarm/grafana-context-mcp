import time

import pytest

from azure_logs import AzureLogExporter, AzureLogsSettings


class RecordingClient:
    def __init__(self) -> None:
        self.uploads = []

    def upload(self, **kwargs) -> None:
        self.uploads.append(kwargs)


def test_settings_reject_partial_configuration(monkeypatch) -> None:
    monkeypatch.setenv("AZURE_MONITOR_ENDPOINT", "https://example.ingest.monitor.azure.com")
    monkeypatch.delenv("AZURE_MONITOR_DCR_RULE_ID", raising=False)
    monkeypatch.delenv("AZURE_MONITOR_STREAM_NAME", raising=False)

    with pytest.raises(RuntimeError, match="partially configured"):
        AzureLogsSettings.from_env()


def test_settings_support_separate_event_stream(monkeypatch) -> None:
    monkeypatch.setenv("AZURE_MONITOR_ENDPOINT", "https://example.ingest.monitor.azure.com")
    monkeypatch.setenv("AZURE_MONITOR_EVENT_DCR_RULE_ID", "dcr-event-immutable-id")
    monkeypatch.setenv("AZURE_MONITOR_EVENT_STREAM_NAME", "Custom-DemoApplicationEvents")

    settings = AzureLogsSettings.from_env(
        "AZURE_MONITOR_EVENT_STREAM_NAME",
        "AZURE_MONITOR_EVENT_DCR_RULE_ID",
    )

    assert settings is not None
    assert settings.stream_name == "Custom-DemoApplicationEvents"
    assert settings.rule_id == "dcr-event-immutable-id"


def test_exporter_batches_records() -> None:
    client = RecordingClient()
    settings = AzureLogsSettings(
        endpoint="https://example.ingest.monitor.azure.com",
        rule_id="dcr-immutable-id",
        stream_name="Custom-DemoApplicationLogs",
        batch_size=2,
        flush_interval_seconds=0.01,
    )
    exporter = AzureLogExporter(settings, client_factory=lambda _: client)

    exporter.emit({"Message": "one"})
    exporter.emit({"Message": "two"})
    exporter.close()
    time.sleep(0.01)

    assert client.uploads == [
        {
            "rule_id": "dcr-immutable-id",
            "stream_name": "Custom-DemoApplicationLogs",
            "logs": [{"Message": "one"}, {"Message": "two"}],
        }
    ]

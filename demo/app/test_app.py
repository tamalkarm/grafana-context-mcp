from prometheus_client import CollectorRegistry

from app import create_app


class RecordingExporter:
    def __init__(self) -> None:
        self.records = []

    def emit(self, record) -> None:
        self.records.append(record)


def test_work_endpoint_exports_request_and_job_metrics() -> None:
    app = create_app(CollectorRegistry())
    client = app.test_client()

    response = client.get("/api/work?delay_ms=0")
    metrics = client.get("/metrics").text

    assert response.status_code == 200
    assert 'demo_jobs_completed_total{outcome="success"} 1.0' in metrics
    assert 'demo_http_requests_total{method="GET",route="/api/work",status="200"} 1.0' in metrics


def test_work_endpoint_can_generate_failure_telemetry() -> None:
    exporter = RecordingExporter()
    app = create_app(CollectorRegistry(), log_exporter=exporter)
    client = app.test_client()

    response = client.get("/api/work?delay_ms=0&fail=true")

    assert response.status_code == 500
    assert response.json == {"duration_ms": 0, "status": "failed"}
    assert response.headers["X-Request-ID"] == exporter.records[0]["RequestId"]
    assert exporter.records[0]["Level"] == "Error"
    assert exporter.records[0]["Route"] == "/api/work"
    assert exporter.records[0]["StatusCode"] == 500
    assert exporter.records[0]["DurationMs"] >= 0


def test_unhandled_exception_exports_application_event() -> None:
    request_exporter = RecordingExporter()
    event_exporter = RecordingExporter()
    app = create_app(
        CollectorRegistry(),
        log_exporter=request_exporter,
        event_exporter=event_exporter,
    )
    client = app.test_client()

    response = client.get("/api/crash")

    assert response.status_code == 500
    assert response.json["request_id"] == request_exporter.records[0]["RequestId"]
    assert event_exporter.records[0]["EventType"] == "ApplicationStarted"
    assert event_exporter.records[1]["EventType"] == "UnhandledException"
    assert event_exporter.records[1]["Level"] == "Error"
    assert event_exporter.records[1]["ExceptionType"] == "RuntimeError"
    assert "Controlled demo application failure" in event_exporter.records[1]["StackTrace"]
    assert event_exporter.records[1]["RequestId"] == response.json["request_id"]


def test_http_exception_preserves_status_without_application_event() -> None:
    request_exporter = RecordingExporter()
    event_exporter = RecordingExporter()
    app = create_app(
        CollectorRegistry(),
        log_exporter=request_exporter,
        event_exporter=event_exporter,
    )
    client = app.test_client()

    response = client.get("/not-found")

    assert response.status_code == 404
    assert request_exporter.records[0]["StatusCode"] == 404
    assert request_exporter.records[0]["Level"] == "Information"
    assert [record["EventType"] for record in event_exporter.records] == ["ApplicationStarted"]

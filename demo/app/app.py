from __future__ import annotations

import atexit
import os
import random
import time
import traceback
import uuid
from datetime import datetime, timezone
from typing import Any

from flask import Flask, Response, g, jsonify, request
from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    ProcessCollector,
    generate_latest,
)
from werkzeug.exceptions import HTTPException

from azure_logs import AzureLogExporter, AzureLogsSettings, write_json_log


def create_app(
    registry: CollectorRegistry | None = None,
    log_exporter: AzureLogExporter | None = None,
    event_exporter: AzureLogExporter | None = None,
) -> Flask:
    app = Flask(__name__)
    metrics_registry = registry or CollectorRegistry()
    ProcessCollector(registry=metrics_registry)
    exporter = log_exporter
    if exporter is None:
        azure_settings = AzureLogsSettings.from_env()
        exporter = AzureLogExporter(azure_settings) if azure_settings else None
    events = event_exporter
    if events is None:
        event_settings = AzureLogsSettings.from_env(
            "AZURE_MONITOR_EVENT_STREAM_NAME",
            "AZURE_MONITOR_EVENT_DCR_RULE_ID",
        )
        events = AzureLogExporter(event_settings) if event_settings else None

    def emit_event(
        event_type: str,
        level: str,
        message: str,
        *,
        exception: BaseException | None = None,
        request_id: str = "",
    ) -> None:
        record = {
            "TimeGenerated": datetime.now(timezone.utc).isoformat(),
            "ServiceName": "prometheus-grafana-demo",
            "Environment": os.getenv("APP_ENVIRONMENT", "demo"),
            "Level": level,
            "EventType": event_type,
            "Message": message,
            "RequestId": request_id,
            "ExceptionType": type(exception).__name__ if exception else "",
            "StackTrace": "".join(traceback.format_exception(exception)) if exception else "",
        }
        write_json_log(record)
        if events:
            events.emit(record)

    emit_event("ApplicationStarted", "Information", "Application initialized")
    atexit.register(
        emit_event,
        "ApplicationStopped",
        "Information",
        "Application shutting down gracefully",
    )

    requests_total = Counter(
        "demo_http_requests_total",
        "HTTP requests processed by the demo application.",
        ("method", "route", "status"),
        registry=metrics_registry,
    )
    request_duration = Histogram(
        "demo_http_request_duration_seconds",
        "HTTP request duration in seconds.",
        ("method", "route"),
        buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5),
        registry=metrics_registry,
    )
    in_progress = Gauge(
        "demo_http_requests_in_progress",
        "HTTP requests currently being processed.",
        registry=metrics_registry,
    )
    jobs_completed = Counter(
        "demo_jobs_completed_total",
        "Synthetic jobs completed by outcome.",
        ("outcome",),
        registry=metrics_registry,
    )

    @app.before_request
    def start_request() -> None:
        g.metrics_started_at = time.perf_counter()
        g.request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        in_progress.inc()

    @app.after_request
    def record_request(response: Response) -> Response:
        started_at = getattr(g, "metrics_started_at", time.perf_counter())
        route = request.url_rule.rule if request.url_rule else "unmatched"
        duration_ms = round((time.perf_counter() - started_at) * 1000, 3)
        request_duration.labels(request.method, route).observe(duration_ms / 1000)
        requests_total.labels(request.method, route, str(response.status_code)).inc()
        in_progress.dec()
        record = {
            "TimeGenerated": datetime.now(timezone.utc).isoformat(),
            "ServiceName": "prometheus-grafana-demo",
            "Environment": os.getenv("APP_ENVIRONMENT", "demo"),
            "Level": "Error" if response.status_code >= 500 else "Information",
            "Message": f"{request.method} {route} completed with HTTP {response.status_code}",
            "RequestId": g.request_id,
            "Method": request.method,
            "Route": route,
            "StatusCode": response.status_code,
            "DurationMs": duration_ms,
            "ClientIp": request.headers.get("X-Forwarded-For", request.remote_addr or ""),
        }
        write_json_log(record)
        if exporter:
            exporter.emit(record)
        response.headers["X-Request-ID"] = g.request_id
        return response

    @app.errorhandler(Exception)
    def handle_unhandled_exception(error: Exception) -> HTTPException | tuple[Response, int]:
        if isinstance(error, HTTPException):
            return error

        request_id = getattr(g, "request_id", "")
        emit_event(
            "UnhandledException",
            "Error",
            str(error) or type(error).__name__,
            exception=error,
            request_id=request_id,
        )
        return jsonify(status="error", request_id=request_id), 500

    @app.get("/")
    def index() -> Any:
        return jsonify(
            service="prometheus-grafana-demo",
            endpoints={"health": "/healthz", "metrics": "/metrics", "work": "/api/work"},
        )

    @app.get("/healthz")
    def health() -> Any:
        return jsonify(status="ok")

    @app.get("/api/work")
    def work() -> tuple[Response, int] | Response:
        delay_ms = request.args.get("delay_ms", default=random.randint(25, 500), type=int)
        delay_ms = max(0, min(delay_ms, 2_000))
        time.sleep(delay_ms / 1_000)

        should_fail = request.args.get("fail", "false").lower() in {"1", "true", "yes"}
        if should_fail:
            jobs_completed.labels("failed").inc()
            return jsonify(status="failed", duration_ms=delay_ms), 500

        jobs_completed.labels("success").inc()
        return jsonify(status="completed", duration_ms=delay_ms)

    @app.get("/api/crash")
    def crash() -> Response:
        raise RuntimeError("Controlled demo application failure")

    @app.get("/metrics")
    def metrics() -> Response:
        return Response(generate_latest(metrics_registry), mimetype="text/plain; version=0.0.4")

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)

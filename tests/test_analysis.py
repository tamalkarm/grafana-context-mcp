from grafana_mcp.analysis import analyze_dashboard_document


def test_analyze_dashboard_extracts_nested_panels_and_queries() -> None:
    document = {
        "dashboard": {
            "uid": "service-overview",
            "title": "Service overview",
            "description": "Golden signals",
            "time": {"from": "now-6h", "to": "now"},
            "templating": {
                "list": [{"name": "cluster", "type": "query", "current": {"value": "prod"}}]
            },
            "panels": [
                {
                    "id": 1,
                    "type": "row",
                    "title": "Traffic",
                    "panels": [
                        {
                            "id": 2,
                            "type": "timeseries",
                            "title": "Request rate",
                            "description": "Requests per second",
                            "datasource": {"uid": "prom-main"},
                            "targets": [{"refId": "A", "expr": "sum(rate(http_requests_total[5m]))"}],
                            "fieldConfig": {
                                "defaults": {
                                    "unit": "reqps",
                                    "thresholds": {"steps": [{"color": "green"}, {"color": "red", "value": 1000}]},
                                }
                            },
                        }
                    ],
                }
            ],
        }
    }

    result = analyze_dashboard_document(document)

    assert result["panel_count"] == 2
    assert result["variable_count"] == 1
    assert result["datasource_usage"] == {"prom-main": 1}
    request_panel = result["panels"][1]
    assert request_panel["unit"] == "reqps"
    assert request_panel["targets"][0]["query"] == "sum(rate(http_requests_total[5m]))"
    assert any("visual thresholds" in item["message"] for item in result["findings"])


def test_analyze_dashboard_reports_missing_context() -> None:
    result = analyze_dashboard_document(
        {"dashboard": {"uid": "empty", "title": "Empty", "panels": [{"id": 1, "type": "stat"}]}}
    )

    messages = [item["message"] for item in result["findings"]]
    assert "The dashboard has no description." in messages
    assert "The dashboard has no template variables." in messages
    assert "Panel 1 has no query targets." in messages

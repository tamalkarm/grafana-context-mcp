from __future__ import annotations

from collections import Counter
from typing import Any


def _panels(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    flattened: list[dict[str, Any]] = []
    for panel in items:
        flattened.append(panel)
        nested = panel.get("panels")
        if isinstance(nested, list):
            flattened.extend(_panels(nested))
    return flattened


def _datasource_uid(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        uid = value.get("uid")
        return str(uid) if uid else None
    return None


def analyze_dashboard_document(document: dict[str, Any]) -> dict[str, Any]:
    dashboard = document.get("dashboard", document)
    panels = _panels(dashboard.get("panels", []))
    variables = dashboard.get("templating", {}).get("list", [])
    panel_summaries: list[dict[str, Any]] = []
    source_counts: Counter[str] = Counter()
    findings: list[dict[str, str]] = []

    for panel in panels:
        targets = panel.get("targets") or []
        panel_source = _datasource_uid(panel.get("datasource"))
        target_summaries = []
        for target in targets:
            source = _datasource_uid(target.get("datasource")) or panel_source or "inherited/unknown"
            source_counts[source] += 1
            expression = next(
                (target[key] for key in ("expr", "query", "rawSql", "target") if target.get(key)),
                None,
            )
            target_summaries.append(
                {
                    "ref_id": target.get("refId"),
                    "datasource_uid": source,
                    "query": expression,
                    "hidden": bool(target.get("hide")),
                }
            )

        field_defaults = panel.get("fieldConfig", {}).get("defaults", {})
        thresholds = field_defaults.get("thresholds", {}).get("steps", [])
        panel_summaries.append(
            {
                "id": panel.get("id"),
                "title": panel.get("title") or "Untitled panel",
                "type": panel.get("type", "unknown"),
                "description": panel.get("description"),
                "unit": field_defaults.get("unit"),
                "targets": target_summaries,
                "transformations": [item.get("id") for item in panel.get("transformations", [])],
                "thresholds": thresholds,
            }
        )
        title = panel.get("title") or f"Panel {panel.get('id', '?')}"
        if panel.get("type") != "row" and not targets:
            findings.append({"severity": "warning", "message": f"{title} has no query targets."})
        if targets and not panel.get("description"):
            findings.append({"severity": "info", "message": f"{title} has no description."})
        if thresholds:
            findings.append(
                {
                    "severity": "info",
                    "message": f"{title} uses visual thresholds; they indicate intent, not incident proof.",
                }
            )

    if not variables:
        findings.append({"severity": "info", "message": "The dashboard has no template variables."})
    if not dashboard.get("description"):
        findings.append({"severity": "warning", "message": "The dashboard has no description."})

    return {
        "title": dashboard.get("title", "Untitled dashboard"),
        "uid": dashboard.get("uid"),
        "description": dashboard.get("description"),
        "tags": dashboard.get("tags", []),
        "time": dashboard.get("time", {}),
        "timezone": dashboard.get("timezone", "browser"),
        "refresh": dashboard.get("refresh"),
        "panel_count": len(panels),
        "variable_count": len(variables),
        "variables": [
            {
                "name": item.get("name"),
                "label": item.get("label"),
                "type": item.get("type"),
                "current": item.get("current"),
            }
            for item in variables
        ],
        "datasource_usage": dict(source_counts),
        "panels": panel_summaries,
        "findings": findings,
        "interpretation_note": (
            "This is structural analysis. Validate hypotheses by querying the relevant time range "
            "and correlating metrics, logs, traces, and annotations."
        ),
    }

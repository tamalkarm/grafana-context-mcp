from __future__ import annotations

from typing import Annotated, Any

from fastmcp import FastMCP
from pydantic import Field

from grafana_mcp.analysis import analyze_dashboard_document
from grafana_mcp.client import GrafanaClient
from grafana_mcp.config import Settings
from grafana_mcp.knowledge import DASHBOARD_GUIDE, DATASOURCE_GUIDE, QUERY_GUIDE

mcp = FastMCP("Grafana Context")


def _client() -> GrafanaClient:
    return GrafanaClient(Settings.from_env())


async def _using(operation: Any) -> Any:
    client = _client()
    try:
        return await operation(client)
    finally:
        await client.close()


@mcp.resource("grafana://guide/datasources", mime_type="text/markdown")
def datasource_guide() -> str:
    """Reference for Grafana data source types and safe communication patterns."""
    return DATASOURCE_GUIDE


@mcp.resource("grafana://guide/dashboards", mime_type="text/markdown")
def dashboard_guide() -> str:
    """Reference for reading dashboards and interpreting what panels mean."""
    return DASHBOARD_GUIDE


@mcp.resource("grafana://guide/querying", mime_type="text/markdown")
def querying_guide() -> str:
    """Guide to querying data sources through Grafana."""
    return QUERY_GUIDE


@mcp.resource("grafana://instance/datasources", mime_type="application/json")
async def instance_datasources() -> list[dict[str, Any]]:
    """Live data source inventory from the configured Grafana instance."""
    return await _using(lambda client: client.list_datasources())


@mcp.resource("grafana://dashboard/{uid}", mime_type="application/json")
async def dashboard_resource(uid: str) -> dict[str, Any]:
    """A live Grafana dashboard and metadata addressed by dashboard UID."""
    return await _using(lambda client: client.get_dashboard(uid))


READ_ONLY = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": True,
}


@mcp.tool(title="List Grafana data sources", annotations=READ_ONLY)
async def list_datasources() -> list[dict[str, Any]]:
    """List configured data sources without exposing stored credentials."""
    return await _using(lambda client: client.list_datasources())


@mcp.tool(title="Get Grafana data source", annotations=READ_ONLY)
async def get_datasource(uid: Annotated[str, Field(description="Grafana data source UID")]) -> dict[str, Any]:
    """Get configuration metadata for one data source by UID."""
    return await _using(lambda client: client.get_datasource(uid))


@mcp.tool(title="Check data source health", annotations=READ_ONLY)
async def check_datasource_health(
    uid: Annotated[str, Field(description="Grafana data source UID")],
) -> dict[str, Any]:
    """Run the Grafana plugin health check for one data source."""
    return await _using(lambda client: client.check_datasource_health(uid))


@mcp.tool(title="Search Grafana dashboards", annotations=READ_ONLY)
async def search_dashboards(
    query: Annotated[str, Field(description="Dashboard title search text")] = "",
    tag: Annotated[str | None, Field(description="Optional exact dashboard tag")] = None,
    limit: Annotated[int, Field(ge=1, le=100, description="Maximum results")] = 50,
) -> list[dict[str, Any]]:
    """Search dashboards by title and optional tag."""
    return await _using(lambda client: client.search_dashboards(query, tag, limit))


@mcp.tool(title="Get Grafana dashboard", annotations=READ_ONLY)
async def get_dashboard(uid: Annotated[str, Field(description="Grafana dashboard UID")]) -> dict[str, Any]:
    """Get the complete dashboard JSON and metadata."""
    return await _using(lambda client: client.get_dashboard(uid))


@mcp.tool(title="Analyze Grafana dashboard", annotations=READ_ONLY)
async def analyze_dashboard(uid: Annotated[str, Field(description="Grafana dashboard UID")]) -> dict[str, Any]:
    """Explain dashboard structure, queries, data sources, variables, semantics, and interpretation risks."""
    document = await _using(lambda client: client.get_dashboard(uid))
    return analyze_dashboard_document(document)


@mcp.tool(title="Query a Grafana data source", annotations=READ_ONLY)
async def query_datasource(
    queries: Annotated[
        list[dict[str, Any]],
        Field(
            min_length=1,
            max_length=20,
            description="Grafana /api/ds/query query objects; include refId and datasource.uid",
        ),
    ],
    from_time: Annotated[str, Field(description="Start time, e.g. now-1h or epoch milliseconds")] = "now-1h",
    to_time: Annotated[str, Field(description="End time, e.g. now or epoch milliseconds")] = "now",
) -> dict[str, Any]:
    """Run bounded, read-only native plugin queries through Grafana's data source query API."""
    return await _using(lambda client: client.query_datasource(queries, from_time, to_time))


@mcp.prompt(title="Investigate a Grafana dashboard")
def investigate_dashboard(
    dashboard_uid: Annotated[str, Field(description="Dashboard UID to investigate")],
    focus: Annotated[str, Field(description="Incident, symptom, or question to focus on")] = "overall health",
) -> str:
    """Guide a careful, evidence-based dashboard investigation."""
    return f"""Investigate Grafana dashboard `{dashboard_uid}` with focus on: {focus}.

1. Read `grafana://guide/dashboards`.
2. Call `analyze_dashboard` and explain its variables, time range, data sources, and panel narrative.
3. Identify panels relevant to the focus and explain their query and display semantics.
4. If live values are needed, use a narrow time range with `query_datasource`.
5. Correlate related signals and distinguish observations from hypotheses.
6. Report evidence, likely meaning, caveats, and concrete next checks. Never infer an incident from color alone.
"""


@mcp.prompt(title="Troubleshoot a Grafana data source")
def troubleshoot_datasource(
    datasource_uid: Annotated[str, Field(description="Data source UID to troubleshoot")],
    symptom: Annotated[str, Field(description="Observed error or symptom")] = "queries are failing",
) -> str:
    """Guide data source connectivity and query troubleshooting."""
    return f"""Troubleshoot Grafana data source `{datasource_uid}`. Symptom: {symptom}.

Read `grafana://guide/datasources`, then get the data source metadata and run its health check.
Separate network/authentication/plugin-health failures from query-language, time-range, variable,
and data-shape problems. Do not request or expose credentials. Summarize evidence and next actions.
"""


@mcp.prompt(title="Explain a dashboard panel")
def explain_panel(
    dashboard_uid: Annotated[str, Field(description="Dashboard UID")],
    panel_title: Annotated[str, Field(description="Exact or approximate panel title")],
) -> str:
    """Explain the meaning and limitations of one dashboard panel."""
    return f"""Analyze dashboard `{dashboard_uid}` and explain panel `{panel_title}`.
Use `analyze_dashboard`, then cover its data source, query, aggregation, unit, transformations,
thresholds, time range, variables, and what an increase/decrease means. State ambiguity explicitly
and list the live evidence needed to validate the interpretation.
"""


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()

DATASOURCE_GUIDE = """# Grafana data sources and how to query them

Grafana normally communicates with data sources through its server-side proxy. Prefer Grafana's
`POST /api/ds/query` endpoint over contacting a backend directly: Grafana resolves credentials,
access mode, plugin behavior, and organization boundaries. A query must include a `refId` and a
data source reference, normally `datasource: {uid: "..."}`. Query fields after that are specific
to the plugin and can be copied from a dashboard panel target.

## Common source types

| Type | Best for | Query language/model | What results mean |
|---|---|---|---|
| Prometheus / Mimir | Numeric time-series metrics | PromQL | Labeled samples over time. Rates need counters and a range window. |
| Loki | Logs and log-derived metrics | LogQL | Log streams selected by labels; pipeline stages filter/parse content. |
| Elasticsearch / OpenSearch | Logs, documents, aggregations | Lucene/query DSL | Documents or bucketed aggregations over a configured time field. |
| InfluxDB | Time-series metrics/events | Flux, InfluxQL, or SQL | Measurements/tables over time with tags and fields. |
| Graphite | Hierarchical metrics | Graphite functions | Series selected by metric paths, often transformed by functions. |
| PostgreSQL / MySQL / MSSQL | Relational operational data | SQL | Tables or time series; use time macros and parameterized variables. |
| Tempo / Jaeger | Distributed traces | TraceQL or trace lookup | Traces contain spans, timing, attributes, errors, and service links. |
| CloudWatch / Azure Monitor | Cloud-native telemetry | Provider query model | Metrics, logs, and dimensions controlled by cloud permissions. |
| JSON/API plugins | External HTTP APIs | Plugin-specific | Shape and semantics depend entirely on the installed plugin. |

## Safe communication workflow

1. List data sources and identify the UID, plugin type, access mode, and default source.
2. Check health; a healthy connection does not prove a particular query is correct.
3. Inspect an existing panel target for the plugin-specific query schema.
4. Query a narrow time range and bounded result size through `query_datasource`.
5. Interpret labels, units, transformations, null handling, and aggregation before drawing conclusions.

The MCP server never returns configured secrets and exposes no create, update, or delete operations.
"""

DASHBOARD_GUIDE = """# How to read a Grafana dashboard

A dashboard is a collection of panels, not an explanation by itself. Read it in this order:

1. **Purpose and scope**: title, description, tags, default time range, timezone, and refresh interval.
2. **Variables**: template variables change query scope. Record their current values before interpreting data.
3. **Rows and panel order**: rows usually express a narrative from overview to diagnosis.
4. **Panel query**: inspect every target, data source UID, query expression, legend, and hidden-query flag.
5. **Transformations**: joins, reductions, renames, and calculations can substantially change raw results.
6. **Display semantics**: unit, min/max, decimals, mappings, thresholds, stacking, and null handling.
7. **Evidence**: correlate metrics with logs, traces, alerts, and deployment annotations.

## Interpretation patterns

- A stat is a reduction over a time range; confirm whether it shows last, mean, max, or total.
- A rate is per unit time and should not be read as a cumulative count.
- Percentages require a clear numerator and denominator; ratios may need multiplication by 100.
- A rising latency percentile means the slow tail changed, not necessarily the typical request.
- Stacked graphs emphasize totals but can conceal individual series behavior.
- Red thresholds encode author intent, not proof of an incident.
- Missing data can mean zero, no traffic, query failure, label mismatch, or collection failure.
- Correlation is not causation. Use annotations and related telemetry to test a hypothesis.

Treat generated insights as hypotheses. Confirm them against live query results, alert rules, and system context.
"""

QUERY_GUIDE = """# Querying through this MCP server

Use `search_dashboards` then `get_dashboard` or `analyze_dashboard`. Use `list_datasources` and
`check_datasource_health` to understand connectivity. `query_datasource` accepts Grafana's native
query objects and sends them to `POST /api/ds/query` with a bounded time range. The easiest reliable
query is an existing panel's target plus its data source UID.

Relative times such as `now-1h` and `now` or epoch milliseconds are accepted by Grafana. Keep time
ranges small initially. Query output is returned as Grafana data frames: inspect field names, labels,
types, values, notices, and errors. Never assume the first numeric field has the unit shown by a panel;
units are usually dashboard display configuration rather than source metadata.
"""

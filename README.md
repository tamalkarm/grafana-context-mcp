# Grafana Context MCP

A Python FastMCP server that gives assistants read-only access to Grafana and the context needed to
interpret what they find. It exposes static guidance and live objects as **resources**, Grafana API
operations as **tools**, and repeatable investigation workflows as **prompts**.

For a concise start, load-injection, architecture, MCP Inspector, and shutdown guide, see
[`DEMO-RUNBOOK.md`](DEMO-RUNBOOK.md).

## Single-VM demo stack

The repository includes a Docker Compose demo with an instrumented Python application, a synthetic
traffic generator, Prometheus, and a pre-provisioned Grafana dashboard. All services run on one VM
and communicate over a private Compose network. Prometheus uses its normal pull model to scrape the
application's `/metrics` endpoint every five seconds.

### Start the demo

Install Docker Engine with the Compose plugin on the VM, clone or copy this project, and run:

```powershell
docker compose up --build -d
docker compose ps
```

Open these endpoints from a browser that can reach the VM:

| Service | Default URL | Credentials/purpose |
|---|---|---|
| Demo app | `http://VM_IP:8000` | Public demo endpoint |
| Prometheus | `http://VM_IP:9090` | Query and target inspection |
| Grafana | `http://VM_IP:3000` | `admin` / `admin` for local demo only |

Grafana opens with the **MCP Demo / Demo Application Overview** dashboard already available. The
load generator makes one normal request per second and injects occasional failures, producing useful
request-rate, latency, error-ratio, job-outcome, and process-memory signals.

### Send application logs to Azure Log Analytics

The application always writes one structured JSON record per request to stdout. When Azure Monitor
settings are supplied, it also batches those records to a Log Analytics workspace using the current
**Azure Monitor Logs Ingestion API** and `DefaultAzureCredential`. On an Azure VM, use a managed
identity so no client secret is stored in Compose or source control.

1. In the Log Analytics workspace, create a custom table named `DemoApplicationLogs_CL`. Use
   `demo\azure\sample-log.json` as the sample schema.
2. Create a **Direct** data collection rule (DCR) in the same region. Its input stream should be
   `Custom-DemoApplicationLogs`, its destination should be the workspace, and its output stream
   should be `Custom-DemoApplicationLogs_CL`. Use `source` as the transformation when the schemas
   match.
3. Enable a system-assigned managed identity on the VM. On the DCR's **Access Control (IAM)** page,
   grant that identity the **Monitoring Metrics Publisher** role. For a user-assigned identity, also
   set `AZURE_CLIENT_ID` to its client ID.
4. Obtain the DCR's immutable ID and `logsIngestion` endpoint from its JSON view, then configure:

```powershell
$env:AZURE_MONITOR_ENDPOINT = "https://<endpoint>.<region>-1.ingest.monitor.azure.com"
$env:AZURE_MONITOR_DCR_RULE_ID = "dcr-<immutable-id>"
$env:AZURE_MONITOR_STREAM_NAME = "Custom-DemoApplicationLogs"
docker compose up --build -d
```

For local testing outside Azure, `DefaultAzureCredential` also supports Azure CLI credentials or the
`AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, and `AZURE_CLIENT_SECRET` service-principal variables. Do not
commit a client secret. A DCE is only required for private-link scenarios or older DCRs without a
direct ingestion endpoint.

Allow several minutes for records to become queryable, then use:

```kusto
DemoApplicationLogs_CL
| where TimeGenerated > ago(15m)
| summarize Requests=count(), Errors=countif(StatusCode >= 500), P95=percentile(DurationMs, 95)
    by bin(TimeGenerated, 1m)
| order by TimeGenerated asc
```

Application lifecycle events and unhandled exceptions are written separately to
`DemoApplicationEvents_CL`. Generate a controlled exception with `GET /api/crash`, then query:

```kusto
DemoApplicationEvents_CL
| where TimeGenerated > ago(15m)
| project TimeGenerated, Level, EventType, Message, ExceptionType, RequestId, StackTrace
| order by TimeGenerated desc
```

The application captures startup events and unhandled Python exceptions, including their stack
traces. An immediate process or host termination (`SIGKILL`, power loss, or kernel failure) cannot
reliably upload its own final event; use Docker/runtime logs and an external availability check for
those failures.

### Run the crash-spike scenario

Start the stack, open the **Demo Application Overview** dashboard with a 15-minute time range, and
run:

```powershell
.\scripts\invoke-crash-spike.ps1 -Count 30 -DelayMilliseconds 100
```

Each call raises a controlled, unhandled `RuntimeError`. The application returns HTTP 500, increments
the Prometheus request counter, and sends a correlated `UnhandledException` record with its stack
trace to `DemoApplicationEvents_CL`. Within the next Prometheus scrape intervals, the dashboard's
**HTTP 5xx spike by route** panel shows a `/api/crash` spike. Log Analytics ingestion can take several
minutes; find records from the latest scenario with:

```kusto
DemoApplicationEvents_CL
| where TimeGenerated > ago(15m)
| where EventType == "UnhandledException"
| summarize Exceptions=count() by bin(TimeGenerated, 1m), ExceptionType
| order by TimeGenerated asc
```

This is an application-exception simulation, not a forced process termination. A process killed with
`SIGKILL` cannot execute its own logging or flush logic.

### Query Log Analytics from Grafana

Grafana provisions **Demo Log Analytics** (UID `log-analytics-demo`) using the built-in Azure
Monitor data source. For this local demo, the application and Grafana use a dedicated Microsoft
Entra service principal. Its client secret is stored only in the git-ignored `.env` file. The
service principal needs **Monitoring Metrics Publisher** on the DCR and **Log Analytics Reader** on
`law-grafana-mcp-demo`.

In Grafana Explore, select **Demo Log Analytics**, choose **Logs**, select workspace
`law-grafana-mcp-demo`, and run:

```kusto
DemoApplicationLogs_CL
| where TimeGenerated > ago(15m)
| project TimeGenerated, Level, Method, Route, StatusCode, DurationMs, RequestId
| order by TimeGenerated desc
```

Upload failures are written as errors to container logs; they do not fail user requests. The exporter
uses a bounded queue and batches records so request handling does not wait on Azure network calls.

Set a non-default password before exposing the VM beyond a private demo network:

```powershell
$env:GRAFANA_ADMIN_PASSWORD = "replace-with-a-strong-password"
docker compose up --build -d
```

Limit VM firewall access to trusted source addresses. The application, Grafana, and Prometheus ports
are published for demo convenience and are not a production security configuration.

### Connect the MCP server to the demo

Create a Grafana service account with the Viewer role and a one-time token:

```powershell
.\scripts\create-grafana-token.ps1 -AdminPassword $env:GRAFANA_ADMIN_PASSWORD
$env:GRAFANA_URL = "http://localhost:3000"
$env:GRAFANA_SERVICE_ACCOUNT_TOKEN = "paste-the-returned-token"
.venv\Scripts\grafana-mcp.exe
```

If the MCP process runs on a different machine, replace `localhost` with the VM address. The demo
dashboard UID is `demo-app-overview`, which can be passed directly to `analyze_dashboard` or the
`investigate_dashboard` prompt. Stop the stack with `docker compose down`; add `-v` only when you
also want to delete all Prometheus and Grafana data.

## Capabilities

| MCP primitive | Included |
|---|---|
| Resources | Data source guide, dashboard-reading guide, querying guide, live data source inventory, dashboard-by-UID |
| Tools | List/get/health-check data sources, search/get/analyze dashboards, execute data source queries |
| Prompts | Investigate a dashboard, troubleshoot a data source, explain a panel |

The dashboard analyzer extracts panel queries, data source usage, variables, units,
transformations, thresholds, and interpretation caveats. Its insights are structural hypotheses;
they must be validated against live values and operational context.

## Setup

Requires Python 3.10+ and a Grafana service-account token with only the permissions you want the
assistant to use. Typical read access includes `datasources:read` and `dashboards:read`; data source
query permissions depend on your Grafana edition and RBAC configuration.

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
$env:GRAFANA_URL = "https://grafana.example.com"
$env:GRAFANA_SERVICE_ACCOUNT_TOKEN = "glsa_..."
.venv\Scripts\grafana-mcp.exe
```

Optional variables are `GRAFANA_ORG_ID`, `GRAFANA_TIMEOUT_SECONDS` (default `30`), and
`GRAFANA_VERIFY_SSL` (default `true`). Do not disable TLS verification outside a controlled local
environment.

## MCP client configuration

After installing the package, configure a stdio server in your MCP client. Use an absolute path to
the virtual environment executable:

```json
{
  "servers": {
    "grafana": {
      "type": "stdio",
      "command": "E:\\AI\\repos\\TestProject\\.venv\\Scripts\\grafana-mcp.exe",
      "env": {
        "GRAFANA_URL": "https://grafana.example.com",
        "GRAFANA_SERVICE_ACCOUNT_TOKEN": "${input:grafana-token}"
      }
    }
  },
  "inputs": [
    {
      "id": "grafana-token",
      "type": "promptString",
      "description": "Grafana read-only service account token",
      "password": true
    }
  ]
}
```

The exact secret-input syntax varies by MCP client. Prefer its secure secret store over saving a
token directly in configuration.

## Querying data sources

`query_datasource` forwards native query objects to Grafana's `POST /api/ds/query`. Query models
are plugin-specific, so inspect a known dashboard panel and reuse its target shape. Every query
should include `refId` and `datasource.uid`. Start with a narrow range such as `now-15m` to `now`.

The server exposes no Grafana create, update, or delete APIs and does not log the token. Tool
annotations describe operations as read-only, but actual security comes from a least-privilege
Grafana service account.

## Development

```powershell
.venv\Scripts\python -m pytest
```

Run interactively with MCP Inspector using `mcp dev src\grafana_mcp\server.py` after installing the
development dependencies, or run the server directly through FastMCP:

```powershell
.venv\Scripts\fastmcp.exe run src\grafana_mcp\server.py:mcp
```

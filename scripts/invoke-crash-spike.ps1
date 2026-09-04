[CmdletBinding()]
param(
    [ValidateRange(1, 1000)]
    [int]$Count = 30,

    [ValidateRange(0, 10000)]
    [int]$DelayMilliseconds = 100,

    [uri]$ApplicationUrl = "http://localhost:8000"
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Net.Http
$client = [System.Net.Http.HttpClient]::new()
$client.Timeout = [TimeSpan]::FromSeconds(10)
$crashUri = [uri]::new($ApplicationUrl, "/api/crash")
$scenarioId = [guid]::NewGuid().ToString()
$failures = 0

try {
    Write-Host "Generating $Count controlled application failures (scenario $scenarioId)..."

    for ($index = 1; $index -le $Count; $index++) {
        $response = $null
        $request = [System.Net.Http.HttpRequestMessage]::new(
            [System.Net.Http.HttpMethod]::Get,
            $crashUri
        )
        $request.Headers.Add("X-Request-ID", "$scenarioId-$index")

        try {
            $response = $client.SendAsync($request).GetAwaiter().GetResult()
            if ([int]$response.StatusCode -eq 500) {
                $failures++
            } else {
                throw "Expected HTTP 500 but received $([int]$response.StatusCode)."
            }
        } finally {
            if ($response) {
                $response.Dispose()
            }
            $request.Dispose()
        }

        if ($DelayMilliseconds -gt 0 -and $index -lt $Count) {
            Start-Sleep -Milliseconds $DelayMilliseconds
        }
    }
} finally {
    $client.Dispose()
}

Write-Host "Generated $failures correlated HTTP 500 and UnhandledException records."
Write-Host "Grafana: http://localhost:3000/d/demo-app-overview"
Write-Host "Log Analytics records can take several minutes to become queryable."

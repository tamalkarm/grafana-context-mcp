param(
    [string]$GrafanaUrl = "http://localhost:3000",
    [string]$AdminUser = "admin",
    [string]$AdminPassword = "admin"
)

$ErrorActionPreference = "Stop"
$pair = "${AdminUser}:${AdminPassword}"
$authorization = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes($pair))
$headers = @{ Authorization = "Basic $authorization" }
$serviceAccountName = "grafana-mcp-demo"

$accounts = Invoke-RestMethod -Uri "$GrafanaUrl/api/serviceaccounts/search?query=$serviceAccountName" -Headers $headers
$account = $accounts.serviceAccounts | Where-Object { $_.name -eq $serviceAccountName } | Select-Object -First 1
if (-not $account) {
    $account = Invoke-RestMethod -Method Post -Uri "$GrafanaUrl/api/serviceaccounts" -Headers $headers `
        -ContentType "application/json" -Body (@{ name = $serviceAccountName; role = "Viewer" } | ConvertTo-Json)
}

$tokenName = "mcp-$([DateTimeOffset]::UtcNow.ToUnixTimeSeconds())"
$token = Invoke-RestMethod -Method Post -Uri "$GrafanaUrl/api/serviceaccounts/$($account.id)/tokens" `
    -Headers $headers -ContentType "application/json" -Body (@{ name = $tokenName } | ConvertTo-Json)

Write-Host "A new Viewer token was created. It is shown only once:" -ForegroundColor Green
Write-Output $token.key

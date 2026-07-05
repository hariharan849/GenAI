param(
    [int]$Count = 100,
    [string]$BaseUrl = $(if ($env:BASE_URL) { $env:BASE_URL } else { "http://localhost:8083" }),
    [double]$SleepSeconds = $(if ($env:SLEEP_SECONDS) { [double]$env:SLEEP_SECONDS } else { 0.3 }),
    [switch]$EnableRag
)

$queries = @(
    "How do I use the Blur node in Nuke?",
    "What is the Merge node used for?",
    "How do I read EXR files in Nuke?",
    "How can I stabilize footage?"
)

function Invoke-DashboardRequest {
    param(
        [string]$Method,
        [string]$Path,
        [object]$Body = $null
    )

    $uri = "$BaseUrl$Path"
    try {
        if ($null -ne $Body) {
            $json = $Body | ConvertTo-Json -Compress
            $response = Invoke-WebRequest -Uri $uri -Method $Method -ContentType "application/json" -Body $json -TimeoutSec 30 -SkipHttpErrorCheck
        }
        else {
            $response = Invoke-WebRequest -Uri $uri -Method $Method -TimeoutSec 30 -SkipHttpErrorCheck
        }
        $code = [int]$response.StatusCode
    }
    catch {
        $code = "ERR"
    }

    $timestamp = Get-Date -Format "HH:mm:ss"
    "{0} {1,-4} {2,-28} -> HTTP {3}" -f "[$timestamp]", $Method, $Path, $code
}

Write-Host "Generating $Count dashboard test requests against $BaseUrl"
Write-Host "Use -EnableRag to include /ask calls."

for ($i = 1; $i -le $Count; $i++) {
    $query = $queries[($i - 1) % $queries.Count]

    switch ($i % 6) {
        0 {
            Invoke-DashboardRequest -Method "GET" -Path "/api/v1/health"
        }
        1 {
            Invoke-DashboardRequest -Method "POST" -Path "/api/v1/hybrid-search/" -Body @{
                query = $query
                size = 3
                use_hybrid = $false
                knowledge_source = "nuke"
            }
        }
        2 {
            Invoke-DashboardRequest -Method "POST" -Path "/api/v1/hybrid-search/" -Body @{
                query = ""
                size = 3
                use_hybrid = $false
                knowledge_source = "nuke"
            }
        }
        3 {
            Invoke-DashboardRequest -Method "GET" -Path "/api/v1/not-found-$i"
        }
        4 {
            Invoke-DashboardRequest -Method "POST" -Path "/api/v1/feedback" -Body @{
                trace_id = "dashboard-test-$i"
                score = 2
                comment = "intentional validation error"
            }
        }
        default {
            if ($EnableRag) {
                Invoke-DashboardRequest -Method "POST" -Path "/api/v1/ask" -Body @{
                    query = $query
                    top_k = 2
                    use_hybrid = $false
                    model = "llama3.2:1b"
                    knowledge_source = "nuke"
                }
            }
            else {
                Invoke-DashboardRequest -Method "GET" -Path "/metrics"
            }
        }
    }

    Start-Sleep -Seconds $SleepSeconds
}

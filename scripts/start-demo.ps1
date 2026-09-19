<#
.SYNOPSIS
    Start every local service needed for the IntentWeave demo.

.DESCRIPTION
    Starts ENGINE01, ENGINE02, ENGINE03, Whisper, Virtual You, and Next.js.
    Existing listeners are reused instead of stopped or duplicated. New processes run
    in the background and write stdout/stderr to gitignored data/runtime/logs.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\scripts\start-demo.ps1

.EXAMPLE
    # Check paths, ports, and the startup plan without changing anything.
    powershell -ExecutionPolicy Bypass -File .\scripts\start-demo.ps1 -WhatIf
#>

[CmdletBinding(SupportsShouldProcess)]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$logsRoot = Join-Path $repoRoot "data\runtime\logs"
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
$engine02Python = Join-Path $repoRoot ".venv-engine02\Scripts\python.exe"
$npm = (Get-Command npm.cmd -ErrorAction SilentlyContinue).Source

function Import-ProjectEnvironment {
    $dotenvPath = Join-Path $repoRoot ".env"
    if (-not (Test-Path -LiteralPath $dotenvPath)) {
        Write-Warning ".env does not exist; services will use their defaults."
        return
    }

    foreach ($line in Get-Content -LiteralPath $dotenvPath) {
        if ($line -notmatch '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$') {
            continue
        }
        $name = $matches[1]
        $value = $matches[2]
        if ($value.Length -ge 2 -and (( $value.StartsWith('"') -and $value.EndsWith('"') ) -or ( $value.StartsWith("'") -and $value.EndsWith("'") ))) {
            $value = $value.Substring(1, $value.Length - 2)
        }

        # Values supplied by the caller's shell take precedence over .env.
        if ($null -eq [Environment]::GetEnvironmentVariable($name, "Process")) {
            [Environment]::SetEnvironmentVariable($name, $value, "Process")
        }
    }
}

function Get-ListeningProcessIds([int]$port) {
    @(Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique)
}

function Start-DemoService {
    param(
        [Parameter(Mandatory)] [string]$Name,
        [Parameter(Mandatory)] [int]$Port,
        [Parameter(Mandatory)] [string]$FilePath,
        [Parameter(Mandatory)] [string[]]$Arguments,
        [Parameter(Mandatory)] [string]$WorkingDirectory,
        [hashtable]$Environment = @{}
    )

    $existing = Get-ListeningProcessIds $Port
    if (@($existing).Count -gt 0) {
        return [PSCustomObject]@{ Name = $Name; Port = $Port; Status = "Reusing existing listener"; Pid = (@($existing) -join ",") }
    }
    if (-not (Test-Path -LiteralPath $FilePath)) {
        throw "$Name launch file does not exist: $FilePath"
    }
    if (-not $PSCmdlet.ShouldProcess("$Name (port $Port)", "Start in background")) {
        return [PSCustomObject]@{ Name = $Name; Port = $Port; Status = "Planned"; Pid = "-" }
    }

    $originalEnvironment = @{}
    foreach ($key in $Environment.Keys) {
        $originalEnvironment[$key] = [Environment]::GetEnvironmentVariable($key, "Process")
        [Environment]::SetEnvironmentVariable($key, [string]$Environment[$key], "Process")
    }

    try {
        $safeName = $Name -replace "[^A-Za-z0-9_-]", "-"
        $stdout = Join-Path $logsRoot "$safeName-$Port.stdout.log"
        $stderr = Join-Path $logsRoot "$safeName-$Port.stderr.log"
        $process = Start-Process -FilePath $FilePath -ArgumentList $Arguments -WorkingDirectory $WorkingDirectory `
            -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
        return [PSCustomObject]@{ Name = $Name; Port = $Port; Status = "Started"; Pid = $process.Id }
    }
    finally {
        foreach ($key in $Environment.Keys) {
            [Environment]::SetEnvironmentVariable($key, $originalEnvironment[$key], "Process")
        }
    }
}

function Test-HealthEndpoint {
    param([Parameter(Mandatory)] [string]$Url)

    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 2
        return $response.StatusCode -ge 200 -and $response.StatusCode -lt 400
    }
    catch {
        return $false
    }
}

Import-ProjectEnvironment
if (-not (Test-Path -LiteralPath $python)) { throw "Missing .venv Python: $python" }
if (-not (Test-Path -LiteralPath $engine02Python)) { throw "Missing ENGINE02 Python: $engine02Python" }
if (-not $npm) { throw "npm.cmd was not found. Install Node.js first." }
New-Item -ItemType Directory -Path $logsRoot -Force | Out-Null

$services = @(
    Start-DemoService -Name "ENGINE02" -Port 8002 -FilePath $engine02Python -WorkingDirectory $repoRoot `
        -Arguments @("-m", "uvicorn", "mcp_servers.catalog.main:app", "--host", "127.0.0.1", "--port", "8002") `
        -Environment @{ ENGINE02_CATALOG = "data/catalog/hm_filled"; ENGINE02_DEMO = "1"; ENGINE02_PUBLIC_BASE = "http://127.0.0.1:8002/engine02" }
    Start-DemoService -Name "ENGINE01" -Port 8000 -FilePath $python -WorkingDirectory $repoRoot `
        -Arguments @("-m", "uvicorn", "backend.engine01_intent.main:app", "--host", "127.0.0.1", "--port", "8000")
    Start-DemoService -Name "ENGINE03" -Port 8003 -FilePath $python -WorkingDirectory $repoRoot `
        -Arguments @("-m", "uvicorn", "backend.engine03_feedback.main:app", "--host", "127.0.0.1", "--port", "8003")
    Start-DemoService -Name "Whisper" -Port 9000 -FilePath $python -WorkingDirectory $repoRoot `
        -Arguments @("-m", "uvicorn", "backend.whisper_transcription.main:app", "--host", "127.0.0.1", "--port", "9000")
    Start-DemoService -Name "Virtual-You" -Port 8081 -FilePath $python -WorkingDirectory $repoRoot `
        -Arguments @("-m", "uvicorn", "backend.virtual_you.main:app", "--host", "127.0.0.1", "--port", "8081") `
        -Environment @{ VIRTUAL_TRY_ON_PROVIDER = ($(if ($env:VIRTUAL_TRY_ON_PROVIDER) { $env:VIRTUAL_TRY_ON_PROVIDER } else { "codex" })) }
    Start-DemoService -Name "Frontend" -Port 3000 -FilePath $npm -WorkingDirectory (Join-Path $repoRoot "frontend") `
        -Arguments @("run", "dev", "--", "--hostname", "127.0.0.1", "--port", "3000")
)

"`nStartup result:"
$services | Format-Table -AutoSize

if ($WhatIfPreference) {
    exit 0
}

$healthChecks = @(
    @{ Name = "ENGINE02"; Url = "http://127.0.0.1:8002/health" },
    @{ Name = "ENGINE01"; Url = "http://127.0.0.1:8000/health" },
    @{ Name = "ENGINE03"; Url = "http://127.0.0.1:8003/health" },
    @{ Name = "Whisper"; Url = "http://127.0.0.1:9000/health" },
    @{ Name = "Virtual-You"; Url = "http://127.0.0.1:8081/healthz" },
    @{ Name = "Frontend"; Url = "http://127.0.0.1:3000" }
)

"Health checks (up to 45 seconds total):"
$healthStatus = @{}
$deadline = (Get-Date).AddSeconds(45)
do {
    foreach ($check in $healthChecks) {
        if (-not $healthStatus[$check.Name] -and (Test-HealthEndpoint -Url $check.Url)) {
            $healthStatus[$check.Name] = $true
        }
    }
    if ($healthStatus.Count -eq $healthChecks.Count) {
        break
    }
    Start-Sleep -Milliseconds 750
} while ((Get-Date) -lt $deadline)

foreach ($check in $healthChecks) {
    $status = if ($healthStatus[$check.Name]) { "Healthy" } else { "Still starting; check logs" }
    "  {0,-12} {1}" -f $check.Name, $status
}
"`nFrontend: http://127.0.0.1:3000"
"Logs: $logsRoot"

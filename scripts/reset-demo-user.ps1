<#
.SYNOPSIS
    Deletes this application's persisted profile for one demo Google account.

.DESCRIPTION
    Removes only data/users/<Google-sub>.json for the supplied email. It never
    deletes the Google account itself. Browser-local conversation, onboarding,
    and login data live in the browser and must be cleared separately (see the
    README). ENGINE01's in-memory conversation sessions are cleared by restart.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\scripts\reset-demo-user.ps1 -Email judge@example.com
#>

[CmdletBinding(SupportsShouldProcess, ConfirmImpact = "High")]
param(
    [Parameter(Mandatory)]
    [ValidateNotNullOrEmpty()]
    [string]$Email
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$usersRoot = Join-Path $repoRoot "data\users"

if (-not (Test-Path -LiteralPath $usersRoot)) {
    throw "No persisted user profiles exist at $usersRoot. Nothing was deleted."
}

$matches = @(
    Get-ChildItem -LiteralPath $usersRoot -File -Filter "*.json" |
        ForEach-Object {
            try {
                $profile = Get-Content -LiteralPath $_.FullName -Raw | ConvertFrom-Json
                if ($profile.email -and $profile.email.Equals($Email, [System.StringComparison]::OrdinalIgnoreCase)) {
                    $_
                }
            }
            catch {
                Write-Warning "Skipped unreadable profile file: $($_.FullName)"
            }
        }
)

if ($matches.Count -eq 0) {
    throw "No application profile was found for $Email. Nothing was deleted."
}
if ($matches.Count -gt 1) {
    throw "More than one profile matched $Email. Refusing to delete an ambiguous target."
}

$target = $matches[0]
if ($PSCmdlet.ShouldProcess($target.FullName, "Delete this application's saved profile for $Email")) {
    Remove-Item -LiteralPath $target.FullName
    Write-Host "Deleted application profile: $($target.FullName)"
    Write-Host "Now clear this site's browser storage and restart ENGINE01 before signing in again."
}

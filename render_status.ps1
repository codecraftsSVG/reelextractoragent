# Render deployment status probe (PowerShell).
# Reads the Render API key from .env (renderapikey=...) without printing it,
# then reports service status, latest deploys, env var NAMES (values are
# write-only in the API), and the live /health + /jobs responses.
#
# Usage:  .\render_status.ps1  [-Service "reelextractoragent"] [-Url https://...]

param(
    [string]$Service = "reelextractoragent",
    [string]$Url = "https://reelextractoragent-wr3s.onrender.com"
)

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path

# --- Load renderapikey from .env (never echo it) ---
$key = $null
foreach ($f in @(".env", ".env.render")) {
    $p = Join-Path $here $f
    if (Test-Path $p) {
        foreach ($line in Get-Content $p) {
            if ($line -match '^renderapikey=(.+)$') { $key = $Matches[1].Trim(); break }
        }
    }
    if ($key) { break }
}
if (-not $key) { throw "renderapikey= not found in .env or .env.render" }
Write-Host "[keys] loaded renderapikey from .env (value hidden)"

$base = "https://api.render.com/v1"
$headers = @{ Authorization = "Bearer $key" }

function Get-Render([string]$path) {
    try {
        return (Invoke-RestMethod -Uri "$base$path" -Headers $headers -TimeoutSec 30)
    } catch {
        Write-Host "[!!] GET $path failed: $($_.Exception.Message)"
        return $null
    }
}

# --- Resolve the service by name or URL slug ---
$svcs = Get-Render "/services?limit=50"
$hit = $null
foreach ($e in $svcs) {
    $s = if ($e.service) { $e.service } else { $e }
    $nm = [string]$s.name; $u = [string]$s.url
    if ($nm -and ($nm.ToLower().Contains($Service.ToLower()) -or
                  ($u -and $u.ToLower().Contains($Service.ToLower())))) { $hit = $s; break }
}
if (-not $hit) {
    Write-Host "no service matching '$Service'. Known:"
    foreach ($e in $svcs) {
        $s = if ($e.service) { $e.service } else { $e }
        Write-Host "  - $($s.name) -> $($s.url)"
    }
    exit 1
}

Write-Host "[service] $($hit.name) ($($hit.id))"
Write-Host "  type=$($hit.type) plan=$($hit.plan)"
Write-Host "  repo=$($hit.repo) branch=$($hit.repoBranch)"
Write-Host "  url=$($hit.url)"
Write-Host "  created=$($hit.createdAt) updated=$($hit.updatedAt)"
Write-Host "  top-level keys: $((($hit | Get-Member -MemberType NoteProperty).Name) -join ', ')"
if ($hit.serviceDetails) {
    Write-Host "  serviceDetails.status=$($hit.serviceDetails.serviceStatus)"
}

# --- Latest deploys ---
Write-Host "[deploys] latest 5:"
$deps = Get-Render "/services/$($hit.id)/deploys?limit=5"
if ($deps) {
    foreach ($d in $deps) {
        $x = if ($d.deploy) { $d.deploy } else { $d }
        $c = if ($x.commit -and $x.commit.id) { [string]$x.commit.id }
             elseif ($x.commitId) { [string]$x.commitId }
             else { [string]$x.commit }
        if ($c.Length -gt 8) { $c = $c.Substring(0, 8) }
        Write-Host ("  {0} | status={1} | created={2} | commit={3} | {4}" -f `
            $x.id, $x.status, $x.createdAt, $c, `
            [string]$x.statusDetails)
    }
}

# --- Env var NAMES only ---
Write-Host "[env-vars] listing key names only (values are write-only):"
$envs = Get-Render "/services/$($hit.id)/env-vars"
if ($envs) {
    $names = @()
    foreach ($e in $envs) {
        $v = if ($e.envVar) { $e.envVar } else { $e }
        if ($v.key) { $names += [string]$v.key }
        elseif ($v.name) { $names += [string]$v.name }
    }
    $names = $names | Sort-Object
    Write-Host "  $($names.Count) keys: $($names -join ', ')"
    foreach ($want in @("GEMINI_API_KEY", "COOKIES_TXT", "DATABASE_URL", "PYTHONUNBUFFERED")) {
        if ($names -contains $want) { Write-Host "  OK      $want" }
        else { Write-Host "  MISSING $want" }
    }
}

# --- Live endpoints ---
$live = $hit.url; if (-not $live) { $live = $Url }
if ($live -notmatch '^https?://') { $live = "https://$live" }
Write-Host "[live] base URL: $live"
foreach ($path in @("/health", "/jobs")) {
    try {
        $r = Invoke-WebRequest -Uri "$live$path" -TimeoutSec 20 -UseBasicParsing
        $body = $r.Content
        if ($body.Length -gt 600) { $body = $body.Substring(0, 600) }
        Write-Host "[live] GET $live$path -> $($r.StatusCode) $body"
    } catch {
        Write-Host "[live] GET $live$path -> ERROR $($_.Exception.Message)"
    }
}

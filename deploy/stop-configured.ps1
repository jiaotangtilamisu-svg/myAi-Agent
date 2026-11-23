[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
$logs=Join-Path $root 'logs/local-run'
foreach ($name in @('web','admin-ui','agent','mcp','admin','search','pay','order','coupon','cart','stock','product','user','gateway')) {
    $path=Join-Path $logs "$name.process.json"
    if (-not (Test-Path $path)) { continue }
    $record=Get-Content $path -Raw | ConvertFrom-Json
    $process=Get-Process -Id $record.Id -ErrorAction SilentlyContinue
    if (-not $process) { Write-Host "$name already stopped"; continue }
    if ($process.StartTime.ToUniversalTime().Ticks.ToString() -ne $record.StartTicks) {
        throw "Process ID reused for $name; refusing to stop it."
    }
    $native=Get-CimInstance Win32_Process -Filter "ProcessId=$($record.Id)"
    $belongs=$native.CommandLine -and $native.CommandLine.Contains($root)
    if ($name -eq 'agent') { $belongs=$native.Name -eq 'python.exe' -and $native.CommandLine -match '-m uvicorn app\.main:app .*--port 7050' }
    if ($name -eq 'mcp') { $belongs=$native.Name -eq 'python.exe' -and $native.CommandLine -match '-m app\.mcp_server' }
    if (-not $belongs) { throw "Cannot verify project command for $name; refusing to stop it." }
    Stop-Process -Id $record.Id
    Write-Host "Stopped $name"
}
Push-Location $root
try {
    docker compose -p simlect-local -f deploy/docker-compose.middleware.yml -f deploy/docker-compose.local.yml stop
    if ($LASTEXITCODE -ne 0) { throw 'Some project containers could not be stopped.' }
} finally { Pop-Location }
Write-Host 'Project stopped. Database volumes and files were preserved.'

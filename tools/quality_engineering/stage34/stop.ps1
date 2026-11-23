param([Parameter(Mandatory=$true)][ValidateSet('guard','user','product','stock','order','search','admin','cart','gateway','mcp','agent','web','admin-ui')][string]$Service)
$ErrorActionPreference='Stop'
$root=(Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
$run=(Get-Content (Join-Path $root '.cache/stage34/active.json') -Raw | ConvertFrom-Json).directory
$recordPath=Join-Path $run "$Service-process.json"
$record=Get-Content -LiteralPath $recordPath -Raw | ConvertFrom-Json
if(-not $record.PID){throw 'No recorded actual test service PID; stop requires manual identity review.'}
$actual=Get-CimInstance Win32_Process -Filter "ProcessId=$($record.PID)"
if(-not $actual){Write-Output "$Service is absent; no process stopped.";exit 0}
if($actual.CreationDate.ToUniversalTime().Ticks -ne ([datetime]$record.CreationDate).ToUniversalTime().Ticks -or $actual.CommandLine -ne $record.CommandLine){throw 'Process identity changed; no process stopped.'}
$owners=@(Get-NetTCPConnection -LocalPort $record.Port -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique)
if($owners.Count -ne 1 -or $owners[0] -ne $record.PID){throw 'Test port owner changed; no process stopped.'}
$history=Join-Path $run ('history/'+$Service+'-'+(Get-Date -Format 'yyyyMMdd-HHmmssfff'))
New-Item -ItemType Directory -Force $history | Out-Null
Copy-Item -LiteralPath $recordPath -Destination $history
Stop-Process -Id $record.PID -Force
$record | Add-Member -NotePropertyName StoppedAt -NotePropertyValue (Get-Date).ToString('o') -Force
$record.State='STOPPED_RECORDED_ISOLATED_PROCESS'
$record | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $recordPath -Encoding utf8
Write-Output "Stopped recorded isolated $Service PID $($record.PID); history retained."

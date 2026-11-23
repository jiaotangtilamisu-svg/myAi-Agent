[CmdletBinding()]
param([switch]$AsJson)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'service-common.ps1')
$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$all = @(Get-CimInstance Win32_Process)
$results = foreach ($name in @('order','mcp','agent')) {
    $plan = Get-IndependentPlan $name
    $latest = Join-Path $root "logs/independent-services/$name/latest.json"
    $record = $null; $recordPath = $null; $recordError = $null
    try {
        if (Test-Path -LiteralPath $latest) {
            $pointer = Get-Content -LiteralPath $latest -Raw | ConvertFrom-Json
            $recordPath = $pointer.Record
        } else { $recordPath = Join-Path $root "logs/local-run/$name.process.json" }
        if (Test-Path -LiteralPath $recordPath) { $record = Get-Content -LiteralPath $recordPath -Raw | ConvertFrom-Json }
    } catch { $recordError='Unable to read process metadata' }
    $recordedId = if ($record.LauncherPID) { $record.LauncherPID } else { $record.Id }
    $exitRecord = $null
    if ($recordPath) {
        $exitPath = Join-Path (Split-Path $recordPath -Parent) 'exit.json'
        if (Test-Path -LiteralPath $exitPath) { try { $exitRecord=Get-Content -LiteralPath $exitPath -Raw | ConvertFrom-Json } catch { $recordError='Unable to read exit metadata' } }
    }
    $recorded = @($all | Where-Object ProcessId -eq $recordedId)
    $verified = $false
    if ($recorded.Count -gt 0) {
        $live = Get-Process -Id $recordedId -ErrorAction SilentlyContinue
        $verified = $live -and $live.StartTime.ToUniversalTime().Ticks.ToString() -eq $record.StartTicks
    }
    $listeners = @(Get-NetTCPConnection -LocalPort $plan.Port -State Listen -ErrorAction SilentlyContinue)
    $ids = @($listeners | Select-Object -ExpandProperty OwningProcess -Unique)
    $related = @($all | Where-Object { $_.ProcessId -in $ids -or ($verified -and ($_.ProcessId -eq $recordedId -or $_.ParentProcessId -eq $recordedId)) })
    $processes = @($related | ForEach-Object {
        [pscustomobject]@{PID=$_.ProcessId;ParentProcessId=$_.ParentProcessId;CreationDate=$_.CreationDate.ToString('o');ExecutablePath=$_.ExecutablePath;CommandLine=(Protect-ServiceText $_.CommandLine $plan.Secrets)}
    })
    $health = [ordered]@{Url=$plan.Health;HttpStatus=$null;Status=$null;Error=$null}
    try {
        $request=[Net.HttpWebRequest]::Create($plan.Health); $request.Proxy=$null; $request.Timeout=5000
        $response=$request.GetResponse()
        try { $health.HttpStatus=[int]$response.StatusCode; $reader=New-Object IO.StreamReader($response.GetResponseStream()); try { $body=$reader.ReadToEnd() | ConvertFrom-Json; $health.Status=$body.status } finally { $reader.Dispose() } } finally { $response.Dispose() }
    } catch { $health.Error='Health request failed; service unavailable or returned an HTTP error' }
    [pscustomobject]@{Service=$name;Port=$plan.Port;Record=$recordPath;RecordError=$recordError;RecordedPID=$recordedId;RecordedIdentityMatches=$verified;RecordedState=$record.State;RecordedExitCode=$record.ExitCode;ExitEvent=$exitRecord;ListenerPIDs=$ids;Processes=$processes;Health=$health}
}
if ($AsJson) { $results | ConvertTo-Json -Depth 8 } else { $results | Format-List }
# Read-only: never creates records, launches processes, or restarts anything.

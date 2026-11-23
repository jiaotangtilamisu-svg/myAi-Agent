param([switch]$IsolatedOnly)
$ErrorActionPreference='Stop'
$root=(Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
Set-Location $root
$run=(Get-Content '.cache/stage34/active.json' -Raw|ConvertFrom-Json).directory
$rows=@()
foreach($role in @('gateway','order','product','stock','search','user','admin','cart','mcp','agent','guard','web','admin-ui')){
 $rec=Get-Content (Join-Path $run ($role+'-process.json')) -Raw|ConvertFrom-Json
 $process=Get-CimInstance Win32_Process -Filter "ProcessId=$($rec.PID)"
 $hostName=if($role -in @('web','admin-ui')){'127.0.0.2'}else{'127.0.0.1'}
 $route=if($role -eq 'guard'){'/quality34/health'}elseif($role -in @('mcp','agent')){'/health'}elseif($role -eq 'web'){'/'}elseif($role -eq 'admin-ui'){'/admin/'}else{'/actuator/health'}
 $http=0;$body=$null
 try{
  $response=Invoke-WebRequest ('http://'+$hostName+':'+$rec.Port+$route) -UseBasicParsing -TimeoutSec 10
  $http=[int]$response.StatusCode
  if($role -notin @('web','admin-ui')){
   $content=$response.Content
   if($content -is [byte[]]){$content=[Text.Encoding]::UTF8.GetString($content)}
   $body=ConvertFrom-Json -InputObject $content
  }
 }catch{}
 $owners=@(Get-NetTCPConnection -LocalPort $rec.Port -State Listen -ErrorAction SilentlyContinue|Select-Object -ExpandProperty OwningProcess -Unique)
 $identity=$process -and $process.CommandLine -eq $rec.CommandLine -and $process.CreationDate.ToUniversalTime().Ticks -eq ([datetime]$rec.CreationDate).ToUniversalTime().Ticks
 $rows+=@{service=$role;http=$http;status=$body.status;javaWeb=$body.java_web;pid=$process.ProcessId;parentPid=$process.ParentProcessId;creationDate=if($process){$process.CreationDate.ToString('o')}else{$null};executablePath=$process.ExecutablePath;commandLine=$process.CommandLine;listenerMatches=($owners -contains $process.ProcessId);identityMatches=[bool]$identity}
}
$rows|ConvertTo-Json -Depth 5|Set-Content (Join-Path $run 'isolated-health-final.json') -Encoding utf8
$rows|ForEach-Object {Write-Output ($_.service+': PID '+$_.pid+', HTTP '+$_.http+', status '+$_.status+', identity '+$_.identityMatches)}
$formalExit=0
if(-not $IsolatedOnly){
 & powershell -NoProfile -ExecutionPolicy Bypass -File tools/quality_engineering/check-runtime.ps1 *> (Join-Path $run 'formal-health-final.log')
 $formalExit=$LASTEXITCODE
 Copy-Item -LiteralPath '.cache/quality-engineering-20261105/runtime-health.json' -Destination (Join-Path $run 'formal-health-final.json')
}
& 'E:/JDK17/bin/jcmd.exe' ((Get-Content (Join-Path $run 'search-process.json') -Raw|ConvertFrom-Json).PID) GC.heap_info | Out-File (Join-Path $run 'search-heap-final.txt') -Encoding utf8
$env:PYTHONUTF8='1';$env:PYTHONPATH=$root
if(-not $IsolatedOnly){
 & 'E:/Python/python.exe' .cache/stage32/db-snapshot.py stage34-final
 if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}
}
if($formalExit -ne 0 -or @($rows|Where-Object { $_.http -ne 200 -or -not $_.identityMatches -or -not $_.listenerMatches }).Count){exit 1}
$agent=@($rows|Where-Object service -eq 'agent')[0]
if($agent.status -ne 'ok' -or $agent.javaWeb -ne $true){exit 1}
if(@($rows|Where-Object {$_.service -notin @('web','admin-ui','mcp','agent','guard') -and $_.status -ne 'UP'}).Count){exit 1}

param()
$ErrorActionPreference='Stop'
$root=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$run=(Get-Content (Join-Path $root '.cache/stage34/active.json') -Raw | ConvertFrom-Json).directory
$control=Join-Path $run 'browser-control'
New-Item -ItemType Directory -Force $control | Out-Null
$state=Join-Path $control 'status.json'
if(Test-Path -LiteralPath $state){
 $old=Get-Content -LiteralPath $state -Raw | ConvertFrom-Json
 $existing=Get-Process -Id $old.pid -ErrorAction SilentlyContinue
 if($old.state -ne 'CLOSED' -and $existing){
  $identity=Get-CimInstance Win32_Process -Filter "ProcessId=$($old.pid)"
  $expected=Join-Path $PSScriptRoot 'scripts/browser-session.mjs'
  $age=[math]::Abs(($existing.StartTime.ToUniversalTime()-([datetime]$old.startedAt).ToUniversalTime()).TotalSeconds)
  if($identity.ExecutablePath -ne 'E:\Nodejs\node.exe' -or -not $identity.CommandLine.Contains($expected) -or $age -gt 30){throw 'Browser session process identity changed; no process attached, stopped or duplicated.'}
  Write-Output 'Existing project browser session identity verified; no second browser launched.';exit 0
 }
}
$stamp=Get-Date -Format 'yyyyMMdd-HHmmssfff'
$env:PLAYWRIGHT_BROWSERS_PATH=Join-Path $root '.cache/playwright-browsers'
$env:TEMP='E:\SimlectRuntime\tmp';$env:TMP=$env:TEMP
$file=Join-Path $PSScriptRoot 'scripts/browser-session.mjs'
$p=Start-Process -FilePath 'E:\Nodejs\node.exe' -ArgumentList @('"'+$file+'"') -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $control "session-$stamp.log") -RedirectStandardError (Join-Path $control "session-$stamp.error.log")
@{pid=$p.Id;creationDate=$p.StartTime.ToUniversalTime().ToString('o');startedAt=(Get-Date).ToString('o');entryPoint=$file;browser='project-managed Chromium; no personal profile or remote-debugging port'}|ConvertTo-Json|Set-Content (Join-Path $control 'launcher.json') -Encoding utf8
Write-Output "Project browser launcher PID $($p.Id); status file $state"

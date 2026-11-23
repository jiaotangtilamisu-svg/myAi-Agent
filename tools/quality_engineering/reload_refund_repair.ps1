param([ValidateSet('isolated','formal')][string]$Environment,
      [ValidateSet('order','agent')][string]$Service)
$ErrorActionPreference='Stop'
$root=(Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$evidence=Join-Path $root '.cache/refund-status-repair'
$sourceJar=Join-Path $evidence 'build/Simlect-backend/Simlect-order/app/target/simlect-order-1.0.0.jar'
$envFile=Join-Path $root 'Simlect-backend/Simlect-agent/.env'
$envHash=(Get-FileHash -LiteralPath $envFile).Hash
$backup=Join-Path $evidence ("reload-$Environment-$Service-"+(Get-Date -Format 'yyyyMMdd-HHmmssfff'))
New-Item -ItemType Directory -Path $backup | Out-Null
if($Environment -eq 'isolated'){
    $run=(Get-Content (Join-Path $root '.cache/stage34/active.json') -Raw|ConvertFrom-Json).directory
    $record=Get-Content (Join-Path $run "$Service-process.json") -Raw|ConvertFrom-Json
    Copy-Item -LiteralPath (Join-Path $run "$Service-process.json") -Destination $backup
    Copy-Item -LiteralPath $record.LogDirectory -Destination (Join-Path $backup 'previous-logs') -Recurse
    if($Service -eq 'order'){
        $target=Join-Path $run 'build/Simlect-backend/Simlect-order/app/target/simlect-order-1.0.0.jar'
        Copy-Item -LiteralPath $target -Destination (Join-Path $backup 'previous-order.jar')
    }
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root 'tools/quality_engineering/stage34/stop.ps1') -Service $Service
    if($LASTEXITCODE -ne 0){throw 'Identity-checked isolated stop failed.'}
    if($Service -eq 'order'){Copy-Item -LiteralPath $sourceJar -Destination $target}
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root 'tools/quality_engineering/stage34/start.ps1') -Service $Service
    if($LASTEXITCODE -ne 0){throw 'Isolated start failed; retained evidence, no retry.'}
    Copy-Item -LiteralPath (Join-Path $run "$Service-process.json") -Destination (Join-Path $backup 'loaded-process.json')
}else{
    $port=if($Service -eq 'order'){8093}else{7050}
    $snapshot=Get-Content (Join-Path $evidence 'runtime-before.json') -Raw|ConvertFrom-Json
    $matching=@($snapshot|Where-Object {$_.Port -eq $port})
    if($matching.Count -ne 1){throw 'Expected exactly one reviewed process identity; nothing stopped.'}
    $expected=$matching[0]
    $actual=Get-CimInstance Win32_Process -Filter "ProcessId=$($expected.PID)"
    if(-not $actual -or $actual.CreationDate.ToUniversalTime().Ticks -ne ([datetime]$expected.CreationDate).ToUniversalTime().Ticks -or $actual.CommandLine -ne $expected.CommandLine){throw 'Formal process identity changed; nothing stopped.'}
    $owners=@(Get-NetTCPConnection -LocalPort $port -State Listen|Select-Object -ExpandProperty OwningProcess -Unique)
    if($owners.Count -ne 1 -or $owners[0] -ne $expected.PID){throw 'Port identity mismatch; nothing stopped.'}
    $expected|ConvertTo-Json|Set-Content (Join-Path $backup 'previous-process.json') -Encoding utf8
    $latest=Join-Path $root "logs/independent-services/$Service/latest.json"
    $oldRecord=(Get-Content $latest -Raw|ConvertFrom-Json).Record
    Copy-Item -LiteralPath (Split-Path $oldRecord -Parent) -Destination (Join-Path $backup 'previous-logs') -Recurse
    if($Service -eq 'order'){
        $target=Join-Path $root 'Simlect-backend/Simlect-order/app/target/simlect-order-1.0.0.jar'
        Copy-Item -LiteralPath $target -Destination (Join-Path $backup 'previous-order.jar')
    }
    # The two reviewed services alone are stopped. No process-tree/middleware operation.
    Stop-Process -Id $expected.PID
    for($i=0;$i -lt 30;$i++){
        if(-not (Get-Process -Id $expected.PID -ErrorAction SilentlyContinue)){break}
        Start-Sleep -Milliseconds 500
    }
    if(Get-Process -Id $expected.PID -ErrorAction SilentlyContinue){throw 'Old process has not exited; no second instance started.'}
    Start-Sleep -Seconds 2
    if($Service -eq 'order'){Copy-Item -LiteralPath $sourceJar -Destination $target}
    $starter=Join-Path $root "scripts/local/start-$Service.ps1"
    $launch=Start-Process -FilePath powershell.exe -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File',('"'+$starter+'"')) -WorkingDirectory $root -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $backup 'launcher.stdout.log') -RedirectStandardError (Join-Path $backup 'launcher.stderr.log')
    $health=if($Service -eq 'order'){"http://127.0.0.1:$port/actuator/health"}else{"http://127.0.0.1:$port/health"}
    $healthy=$false
    for($i=0;$i -lt 90;$i++){
        if($launch.HasExited){throw 'New launcher exited; logs retained, no retry.'}
        try{
            $response=Invoke-RestMethod -Uri $health -TimeoutSec 8
            if(($Service -eq 'order' -and $response.status -eq 'UP') -or ($Service -eq 'agent' -and $response.status -eq 'ok' -and $response.java_web -eq $true)){$healthy=$true;break}
        }catch{}
        Start-Sleep -Seconds 1
    }
    if(-not $healthy){throw 'New instance failed required health; no retry.'}
    $owner=Get-NetTCPConnection -LocalPort $port -State Listen|Select-Object -First 1
    $loaded=Get-CimInstance Win32_Process -Filter "ProcessId=$($owner.OwningProcess)"
    @{Service=$Service;LauncherPID=$launch.Id;PID=$loaded.ProcessId;ParentProcessId=$loaded.ParentProcessId;CreationDate=$loaded.CreationDate.ToString('o');ExecutablePath=$loaded.ExecutablePath;CommandLine=$loaded.CommandLine;Port=$port;Health=$response}|ConvertTo-Json -Depth 6|Set-Content (Join-Path $backup 'loaded-process.json') -Encoding utf8
    Write-Output "$Service loaded; PID $($loaded.ProcessId); port $port; evidence $backup"
}
if((Get-FileHash -LiteralPath $envFile).Hash -ne $envHash){throw '.env hash changed unexpectedly.'}
if($Service -eq 'order'){
    if((Get-FileHash -LiteralPath $sourceJar).Hash -ne (Get-FileHash -LiteralPath $target).Hash){throw 'Loaded JAR differs from tested artifact.'}
}
Write-Output '.env unchanged; only selected service reloaded; logs and prior artifact retained.'

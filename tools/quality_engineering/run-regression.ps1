param()
$ErrorActionPreference='Stop'
$root=(Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$out=Join-Path $root '.cache/quality-engineering-20261105'
New-Item -ItemType Directory -Force $out | Out-Null
$history=Join-Path $out ('history/'+(Get-Date -Format 'yyyyMMdd-HHmmssfff')+'-gates')
foreach($file in @(Get-ChildItem -LiteralPath $out -File | Where-Object {$_.Name -match '^(java-all|web-|admin-|gates|summary|runtime-health)'})){New-Item -ItemType Directory -Force $history|Out-Null;Copy-Item -LiteralPath $file.FullName -Destination $history}
$results=[System.Collections.Generic.List[object]]::new()
function Run-Gate([string]$name,[scriptblock]$work) {
 $started=Get-Date
 $global:LASTEXITCODE=0
 try { & $work; $code=$LASTEXITCODE } catch { $code=1; $_ | Out-File (Join-Path $out "$name-runner-error.log") }
 $results.Add(@{gate=$name;exitCode=$code;seconds=[math]::Round(((Get-Date)-$started).TotalSeconds,2)})
 $results | ConvertTo-Json -Depth 4 | Set-Content (Join-Path $out 'gates.json') -Encoding utf8
 Write-Output "$name exit=$code"
}
Set-Location $root
Run-Gate 'python-all' { & powershell -NoProfile -ExecutionPolicy Bypass -File tools/quality_engineering/run-python.ps1 -Mode all }
Run-Gate 'python-mutation' { & powershell -NoProfile -ExecutionPolicy Bypass -File tools/quality_engineering/run-python.ps1 -Mode mutation }
$env:JAVA_HOME='E:\JDK17';$env:Path="$env:JAVA_HOME\bin;$env:Path";$env:TEMP='E:\SimlectRuntime\tmp';$env:TMP=$env:TEMP
& {
 Run-Gate 'java-all' {
  Push-Location (Join-Path $root 'Simlect-backend')
  $ErrorActionPreference='Continue'
  & 'E:\develop\apache-maven-3.9.4-bin\apache-maven-3.9.4\bin\mvn.cmd' -o test '-DargLine=-Xmx256m -Djava.security.manager=NoNetworkSecurityManager -Dcsp.sentinel.log.dir=E:/SimlectRuntime/logs/csp -Xbootclasspath/a:E:/Simlect-AI-Mall-main/Simlect-AI-Mall-main/.cache/baseline-tests-20261101/harness' *> (Join-Path $out 'java-all.log')
  $code=$LASTEXITCODE;Pop-Location;$global:LASTEXITCODE=$code
 }
}
foreach($app in @('web','admin')) {
 Run-Gate "$app-tests" {
  Push-Location (Join-Path $root "Simlect-front/Simlect-$app")
  $ErrorActionPreference='Continue'
  if($app -eq 'web'){ & node --experimental-strip-types --test tests/*.test.ts *> (Join-Path $out "$app-tests.log") }
  else { & node --test tests/*.test.mjs *> (Join-Path $out "$app-tests.log") }
  $code=$LASTEXITCODE;Pop-Location;$global:LASTEXITCODE=$code
 }
 Run-Gate "$app-build" {
  Push-Location (Join-Path $root "Simlect-front/Simlect-$app")
  $ErrorActionPreference='Continue'
  & npm run build *> (Join-Path $out "$app-build.log")
  $code=$LASTEXITCODE;Pop-Location;$global:LASTEXITCODE=$code
 }
}
Run-Gate 'runtime-health' { & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root 'tools/quality_engineering/check-runtime.ps1') }
& 'E:\Python\python.exe' (Join-Path $root 'tools/quality_engineering/summarize.py')
if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}
if(@($results|Where-Object exitCode -ne 0).Count){exit 1};exit 0

param(
 [ValidateSet('return','all','recovery')][string]$Suite='return',
 [switch]$WithRegression,
 [switch]$EnableRealApi,
 [switch]$CloseBrowser,
 [switch]$CleanTestData,
 [int]$LoginWaitSeconds=900
)
$ErrorActionPreference='Stop'
$root=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$run=(Get-Content (Join-Path $root '.cache/stage34/active.json') -Raw | ConvertFrom-Json).directory
$out=Join-Path $run ('runs/'+(Get-Date -Format 'yyyyMMdd-HHmmssfff'))
New-Item -ItemType Directory -Force $out|Out-Null
$env:PLAYWRIGHT_BROWSERS_PATH=Join-Path $root '.cache/playwright-browsers'
$env:TEMP='E:\SimlectRuntime\tmp';$env:TMP=$env:TEMP
$env:PYTHONPATH=$root;$env:PYTHONUTF8='1'
$gates=[System.Collections.Generic.List[object]]::new()
function Save-Gate($name,$code){$gates.Add(@{gate=$name;exitCode=$code;at=(Get-Date).ToString('o')});$gates|ConvertTo-Json -Depth 4|Set-Content (Join-Path $out 'gates.json') -Encoding utf8}
# Reuse the previously proved namespace. This command never resets fixtures,
# recopies official policy vectors, extracts browser auth, or starts services.
& 'E:\Python\python.exe' -m tools.quality_engineering.stage34.browser_database before-unified *> (Join-Path $out 'database-before.log')
Save-Gate 'isolated-fixture-read-check' $LASTEXITCODE
if($LASTEXITCODE -ne 0){throw 'Isolated fixture database unavailable; no browser writes performed.'}
foreach($url in @('http://127.0.0.2:16001/','http://127.0.0.2:16002/admin/','http://127.0.0.1:17050/health','http://127.0.0.1:17060/health','http://127.0.0.1:18080/actuator/health','http://127.0.0.1:18093/actuator/health','http://127.0.0.1:18099/actuator/health','http://127.0.0.1:18102/actuator/health','http://127.0.0.1:18108/actuator/health')){
 & curl.exe --noproxy '*' --fail --silent --max-time 10 $url -o NUL
 if($LASTEXITCODE -ne 0){Save-Gate ("health: "+$url) 1;throw "Required isolated service unavailable: $url; no automatic restart."}
};Save-Gate 'health' 0
& (Join-Path $PSScriptRoot 'start-browser.ps1')
$browserLaunch=Get-Content (Join-Path $run 'browser-control/launcher.json') -Raw|ConvertFrom-Json
$deadline=(Get-Date).AddSeconds($LoginWaitSeconds)
do{
 $state=Get-Content (Join-Path $run 'browser-control/status.json') -Raw|ConvertFrom-Json
 # Native launch returns before Chromium publishes its first status. Ignore
 # the previous session's CLOSED record, never attach to or revive that session.
 if($state.pid -ne $browserLaunch.pid -or ([datetime]$state.startedAt).ToUniversalTime() -lt ([datetime]$browserLaunch.creationDate).ToUniversalTime().AddSeconds(-5)){
  Start-Sleep -Milliseconds 500
  continue
 }
 if($state.state -in @('BROWSER_LAUNCH_BLOCKED','CLOSED')){throw 'Project browser unavailable; stopped without retry.'}
 if($state.state -eq 'READY'){break}
 Write-Progress -Activity 'Complete normal CAPTCHA login in project Chromium' -Status 'No credentials or auth state will be exported.'
 Start-Sleep -Seconds 2
}while((Get-Date) -lt $deadline)
if($state.state -ne 'READY'){Save-Gate 'normal-browser-login' 3;throw 'BLOCKED: CAPTCHA/normal login not completed; no bypass or automatic retry.'}
Save-Gate 'normal-browser-login' 0
if($EnableRealApi){
 if(Test-Path (Join-Path $run 'api-stopped.json')){throw 'Prior real API failure is latched. Do not retry without review.'}
 @{scope='Stage34 user-authorized bounded phase';llm=4;embedding=6;outputTokens=512;timeoutSeconds=20;retries=0;at=(Get-Date).ToString('o')}|ConvertTo-Json|Set-Content (Join-Path $run 'enable-real.json') -Encoding utf8
}
try{
 if($WithRegression){
  & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root 'tools/quality_engineering/run-regression.ps1') *> (Join-Path $out 'regression.log')
  Save-Gate 'isolated-mock-regression' $LASTEXITCODE
  # Existing runner installs a no-network harness. These are not real LLM tests.
 }
 Push-Location $PSScriptRoot
 try{
  $ErrorActionPreference='Continue'
  & 'E:\Nodejs\node.exe' --test tests/*.test.mjs *> (Join-Path $out 'e2e-contracts.log')
  $contractExit=$LASTEXITCODE;$ErrorActionPreference='Stop'
  Save-Gate 'e2e-harness-contracts' $contractExit
  $testArgs=@('test')
  if($Suite -eq 'return'){$testArgs+=@('tests/return.spec.mjs')}
  if($Suite -eq 'recovery'){$testArgs+=@('--project','recovery','--no-deps')}
  $ErrorActionPreference='Continue' # Native stderr is logged; exit code remains authoritative.
  & 'E:\Nodejs\node.exe' node_modules/@playwright/test/cli.js @testArgs *> (Join-Path $out 'playwright.log')
  $testExit=$LASTEXITCODE;$ErrorActionPreference='Stop'
  Save-Gate 'real-browser-business-flow' $testExit
 }finally{Pop-Location}
 & 'E:\Python\python.exe' -m tools.quality_engineering.stage34.browser_database after-unified *> (Join-Path $out 'database-after.log')
 Save-Gate 'database-result-snapshot' $LASTEXITCODE
 & 'E:\Python\python.exe' -m tools.quality_engineering.stage34.browser_oracle *> (Join-Path $out 'database-oracle.log')
 Save-Gate 'database-outcome-verification' $LASTEXITCODE
 foreach($name in @('playwright-results.json','playwright-report')){if(Test-Path (Join-Path $run $name)){Copy-Item -LiteralPath (Join-Path $run $name) -Destination $out -Recurse}}
 # Preserve the authenticated project browser and failure scene on any failure.
 # Do not force another CAPTCHA handoff just because a test assertion failed.
 if(($CloseBrowser -or $CleanTestData) -and -not @($gates|Where-Object exitCode -ne 0).Count){
  & 'E:\Nodejs\node.exe' (Join-Path $PSScriptRoot 'scripts/close-session.mjs') *> (Join-Path $out 'video-finalization.log')
  Save-Gate 'video-finalization' $LASTEXITCODE
 }
 if($CleanTestData -and -not @($gates|Where-Object exitCode -ne 0).Count){
  & (Join-Path $root 'Simlect-backend/Simlect-agent/.venv/Scripts/python.exe') -m tools.quality_engineering.stage34.cleanup_browser --execute *> (Join-Path $out 'cleanup.log')
  Save-Gate 'disposable-test-data-cleanup' $LASTEXITCODE
 }
}finally{
 # Remove only the disposable enable marker, never business data or API history.
 if($EnableRealApi -and (Test-Path (Join-Path $run 'enable-real.json'))){Remove-Item -LiteralPath (Join-Path $run 'enable-real.json')}
}
Write-Output "Evidence: $out"
if(@($gates|Where-Object exitCode -ne 0).Count){exit 1}

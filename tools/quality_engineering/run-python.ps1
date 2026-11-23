param([ValidateSet('focused','all','mutation')][string]$Mode='all')
$ErrorActionPreference='Stop'
$root=(Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$out=Join-Path $root '.cache/quality-engineering-20261105'
New-Item -ItemType Directory -Force $out | Out-Null
$history=Join-Path $out ('history/'+(Get-Date -Format 'yyyyMMdd-HHmmssfff')+'-'+$Mode)
$prior=@(Join-Path $out "python-$Mode.log";Join-Path $out "python-$Mode.xml")
if($Mode -eq 'mutation'){$prior=@(Join-Path $out 'mutation.log';Join-Path $out 'mutation.json')}
foreach($file in $prior){if(Test-Path -LiteralPath $file){New-Item -ItemType Directory -Force $history | Out-Null;Copy-Item -LiteralPath $file -Destination $history}}
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1';$env:PYTHONDONTWRITEBYTECODE='1';$env:PYTHONUTF8='1'
$env:TEMP='E:\SimlectRuntime\tmp';$env:TMP=$env:TEMP
$env:BASELINE_RUNTIME_SITE="$root/Simlect-backend/Simlect-agent/.venv/Lib/site-packages"
$env:BASELINE_NETWORK_LOG="$out/blocked-network.log"
$env:PYTHONPATH="$root/.cache/baseline-tests-20261101/harness;$root/Simlect-backend/Simlect-agent;$root/Simlect-backend/Simlect-agent/tests;$root"
$env:SIMLECT_INTERNAL_TOKEN='unit-test-internal-token-not-a-real-secret';$env:LLM_API_KEY='unit-test-key';$env:EMBEDDING_API_KEY='unit-test-key';$env:MEMORY_LLM_API_KEY=''
$env:LLM_BASE_URL='https://model.invalid';$env:EMBEDDING_BASE_URL='https://embedding.invalid';$env:SHOPPING_REQUIREMENT_LLM_ENABLED='false';$env:SHOPPING_DATA_MODE='DEMO'
$env:QUALITY_MUTATION_OUTPUT="$out/mutation.json"
$python=Join-Path $root 'Simlect-backend/Simlect-agent/.venv-tests/Scripts/python.exe'
Set-Location (Join-Path $root '.cache')
$ErrorActionPreference='Continue' # Native stderr warnings are captured, exit code is authoritative.
if($Mode -eq 'mutation') { & $python -m tools.quality_engineering.mutation_probe *> "$out/mutation.log" }
else {
 $paths=if($Mode -eq 'focused'){@("$root/Simlect-backend/Simlect-agent/tests/test_quality_properties.py","$root/Simlect-backend/Simlect-agent/tests/test_quality_fault_injection.py")}else{@("$root/Simlect-backend/Simlect-agent/tests","$root/tools/data_governance/tests")}
 & $python -m pytest -p pytest_asyncio.plugin @paths -q --tb=short --junitxml="$out/python-$Mode.xml" *> "$out/python-$Mode.log"
}
exit $LASTEXITCODE


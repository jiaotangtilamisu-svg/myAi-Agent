[CmdletBinding()]
param([ValidateSet('Check','Build','Java','Python','Frontend','All')][string]$Stage='All',
      [ValidateSet('All','gateway','user','product','stock','cart','coupon','order','pay','search','admin')][string]$Service='All')
$ErrorActionPreference='Stop'
$env:JAVA_HOME='E:\JDK17'
$env:Path='E:\JDK17\bin;E:\Nodejs;E:\Python;E:\develop\apache-maven-3.9.4-bin\apache-maven-3.9.4\bin;'+$env:Path
$env:PYTHONUTF8='1'
$env:TEMP='E:\SimlectRuntime\tmp'
$env:TMP=$env:TEMP
$env:JAVA_TOOL_OPTIONS=($env:JAVA_TOOL_OPTIONS+' -Djdk.net.unixdomain.tmpdir=E:\SimlectRuntime\tmp').Trim()
$root=Split-Path $PSScriptRoot -Parent
Push-Location $root
try {
  if ($Stage -eq 'All') {
    docker compose -p simlect-local -f deploy/docker-compose.middleware.yml -f deploy/docker-compose.local.yml up -d --wait --wait-timeout 240 mysql redis rabbitmq nacos elasticsearch sentinel
    if ($LASTEXITCODE -ne 0) { throw 'Middleware startup failed.' }
    foreach ($part in @('Java','Python','Frontend')) { & "$PSScriptRoot/start-local.ps1" -Stage $part }
  } else { & "$PSScriptRoot/start-local.ps1" -Stage $Stage -Service $Service }
} finally { Pop-Location }

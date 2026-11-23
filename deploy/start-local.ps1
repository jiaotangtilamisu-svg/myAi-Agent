[CmdletBinding()]
param(
  [ValidateSet('Check','Middleware','Build','Java','Python','Frontend')]
  [string]$Stage = 'Check',
  [ValidateSet('All','gateway','user','product','stock','cart','coupon','order','pay','search','admin')]
  [string]$Service = 'All'
)
$ErrorActionPreference = 'Stop'
$Root = Split-Path $PSScriptRoot -Parent
$Logs = Join-Path $Root 'logs/local-run'
New-Item -ItemType Directory -Force $Logs | Out-Null
$Compose = @('compose','-p','simlect-local','-f',(Join-Path $PSScriptRoot 'docker-compose.middleware.yml'),'-f',(Join-Path $PSScriptRoot 'docker-compose.local.yml'))
function Invoke-Checked([scriptblock]$Action) {
  & $Action
  if ($LASTEXITCODE -ne 0) { throw "Command failed (exit $LASTEXITCODE)" }
}
function Test-Port([int]$Port) {
  $c = New-Object Net.Sockets.TcpClient
  try { $t=$c.ConnectAsync('127.0.0.1',$Port); return ($t.Wait(700) -and $c.Connected) }
  catch { return $false } finally { $c.Dispose() }
}
function Start-LocalProcess([string]$Name,[int]$Port,[string]$File,[string[]]$Arguments,[string]$Directory) {
  $record = Join-Path $Logs "$Name.process.json"
  if (Test-Port $Port) {
    if (Test-Path $record) {
      $saved=Get-Content $record -Raw | ConvertFrom-Json
      $proc=Get-Process -Id $saved.Id -ErrorAction SilentlyContinue
      $listener=Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
      if ($proc -and $proc.StartTime.ToUniversalTime().Ticks.ToString() -eq $saved.StartTicks -and $listener.OwningProcess -contains $proc.Id) {
        Write-Host "$Name already running on $Port"; return
      }
    }
    throw "Port $Port occupied by an unverified process; no process was stopped."
  }
  $p=Start-Process -FilePath $File -ArgumentList $Arguments -WorkingDirectory $Directory -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $Logs "$Name.out.log") -RedirectStandardError (Join-Path $Logs "$Name.err.log")
  @{Id=$p.Id;StartTicks=$p.StartTime.ToUniversalTime().Ticks.ToString();Port=$Port} | ConvertTo-Json | Set-Content $record
  for ($i=0;$i -lt 90;$i++) {
    if ($p.HasExited) { throw "$Name exited; inspect logs/local-run/$Name.err.log and .out.log" }
    if (Test-Port $Port) {
      # Windows venv python.exe may launch a child interpreter that owns the socket.
      $listener=Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue | Select-Object -First 1
      if ($listener -and $listener.OwningProcess -ne $p.Id) {
        $child=Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)" -ErrorAction SilentlyContinue
        if ($child -and $child.ParentProcessId -eq $p.Id) {
          $owner=Get-Process -Id $child.ProcessId
          @{Id=$owner.Id;StartTicks=$owner.StartTime.ToUniversalTime().Ticks.ToString();Port=$Port} | ConvertTo-Json | Set-Content $record
        }
      }
      Write-Host "$Name listening on $Port (application health still requires verification)"; return
    }
    Start-Sleep -Seconds 1
  }
  throw "$Name startup timeout; inspect logs before retrying."
}
function Load-LocalEnvironment {
  $path=Join-Path $Root 'Simlect-backend/Simlect-agent/.env'
  if (-not (Test-Path $path)) { throw 'Agent .env missing; configure it from .env.example with a strong internal token first.' }
  foreach ($line in Get-Content $path -Encoding UTF8) {
    if ($line -match '^([A-Z][A-Z0-9_]*)=(.*)$') { [Environment]::SetEnvironmentVariable($matches[1],$matches[2],'Process') }
  }
  if (-not $env:SIMLECT_INTERNAL_TOKEN -or $env:SIMLECT_INTERNAL_TOKEN -in @('your-token','changeme')) { throw 'Strong SIMLECT_INTERNAL_TOKEN required.' }
  $env:PYTHONUTF8='1'
  $env:SIMLECT_PAY_LOCAL_MOCK_ENABLED='true'
  # Existing documented local option: no Seata server, no transaction annotation changes.
  $env:SEATA_ENABLED='false'
}
Push-Location $Root
try {
  switch ($Stage) {
    Check {
      & java -version
      & mvn -version
      & python --version
      & node --version
      & npm.cmd --version
      Invoke-Checked { docker info --format '{{.ServerVersion}}' }
      & docker @Compose ps
      Get-CimInstance Win32_OperatingSystem | Select-Object TotalVisibleMemorySize,FreePhysicalMemory
      Get-PSDrive -PSProvider FileSystem | Select-Object Name,Free
      foreach ($port in @(13306,16379,5672,8848,9200,8858,8080,8105,8099,8102,8084,8087,8093,8096,8108,8111,7050,7060,6001,6002)) {
        [pscustomobject]@{Port=$port;Listening=(Test-Port $port)}
      }
    }
    Middleware {
      # Original start-middleware.ps1 always runs initialization. Do not invoke it on existing data.
      Invoke-Checked { docker @Compose config --quiet }
      Invoke-Checked { docker @Compose up -d mysql redis }
      Write-Host 'Database initialization is deliberately separate: use init-local-db.ps1 only for a verified fresh database.'
      Write-Host 'After initialization and freeing memory, start rabbitmq nacos elasticsearch sentinel with the same compose files.'
    }
    Build { Invoke-Checked { mvn -B -ntp -f Simlect-backend/pom.xml package } }
    Java {
      Load-LocalEnvironment
      # Let the Java YAML use its local placeholder when AI credentials are absent.
      foreach ($key in @('LLM_API_KEY','EMBEDDING_API_KEY')) {
        if ([string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($key,'Process'))) {
          [Environment]::SetEnvironmentVariable($key,$null,'Process')
        }
      }
      foreach ($port in @(13306,16379,5672,8848,9200)) { if (-not (Test-Port $port)) { throw "Required middleware port $port unavailable" } }
      $free=(Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory
      $missingPorts=@(8080,8105,8099,8102,8084,8087,8093,8096,8108,8111) | Where-Object { -not (Test-Port $_) }
      if ($Service -eq 'All' -and @($missingPorts).Count -ge 5 -and $free -lt 3GB/1KB) { throw 'Less than 3 GiB physical memory free. Free memory before starting all Java services.' }
      if ($free -lt 4GB/1KB) { Write-Warning 'Less than 4 GiB free; startup may be slow. Close unused applications.' }
      $services=@(@('gateway',8080,''),@('user',8105,'app'),@('product',8099,'app'),@('stock',8102,'app'),@('cart',8084,'app'),@('coupon',8087,'app'),@('order',8093,'app'),@('pay',8096,'app'),@('search',8108,''),@('admin',8111,''))
      foreach ($s in $services) {
        if ($Service -ne 'All' -and $s[0] -ne $Service) { continue }
        $name=$s[0]; $dir=Join-Path $Root "Simlect-backend/Simlect-$name/$($s[2])"
        $jars=@(Get-ChildItem "$dir/target/*.jar" | Where-Object Name -NotMatch '(sources|javadoc|original)')
        if ($jars.Count -ne 1) { throw "Expected one executable jar for $name; run Build first." }
        $args=@('-Xms64m','-Xmx320m','-Dfile.encoding=UTF-8','-jar',('"'+$jars[0].FullName+'"'),'--server.address=127.0.0.1','--spring.cloud.nacos.discovery.ip=127.0.0.1')
        # Python expects /v1 in its base URL; Spring AI appends /v1 itself.
        if ($name -eq 'search' -and $env:EMBEDDING_BASE_URL) {
          $base=$env:EMBEDDING_BASE_URL.TrimEnd('/') -replace '/v1$',''
          $args += "--spring.ai.openai.embedding.base-url=$base"
        }
        if ($name -ne 'gateway') {
          # Existing YAML hardcodes MySQL :3306, so override the full URL only for this process.
          $args += "--spring.datasource.url=jdbc:mysql://127.0.0.1:13306/simlect_${name}?useUnicode=true&characterEncoding=utf-8&serverTimezone=Asia/Shanghai&allowPublicKeyRetrieval=true&allowMultiQueries=true&useSSL=false"
        }
        Start-LocalProcess $name $s[1] (Get-Command java.exe).Source $args $dir
        if ($name -eq 'gateway') { Invoke-WebRequest http://127.0.0.1:8080/actuator/health -UseBasicParsing -TimeoutSec 15 | Select-Object StatusCode }
      }
    }
    Python {
      Load-LocalEnvironment
      foreach ($port in @(13306,16379)) { if (-not (Test-Port $port)) { throw "Required middleware port $port unavailable" } }
      $dir=Join-Path $Root 'Simlect-backend/Simlect-agent'
      $python=Join-Path $dir '.venv/Scripts/python.exe'
      if (-not (Test-Path $python)) { throw 'Create .venv and install requirements-runtime.txt first (PYTHONUTF8=1).' }
      $env:FASTMCP_HOST='127.0.0.1'
      Start-LocalProcess 'mcp' 7060 $python @('-m','app.mcp_server') $dir
      Invoke-RestMethod http://127.0.0.1:7060/health -TimeoutSec 15
      Start-LocalProcess 'agent' 7050 $python @('-m','uvicorn','app.main:app','--host','127.0.0.1','--port','7050') $dir
      Invoke-RestMethod http://127.0.0.1:7050/health -TimeoutSec 15
    }
    Frontend {
      foreach ($s in @(@('web',6001),@('admin',6002))) {
        $dir=Join-Path $Root "Simlect-front/Simlect-$($s[0])"
        $vite=Join-Path $dir 'node_modules/vite/bin/vite.js'
        if (-not (Test-Path $vite)) { throw "Install frontend dependencies in $dir first using npm.cmd ci." }
        # The admin backend uses "admin"; keep frontend PID records/logs separate.
        $processName = if ($s[0] -eq 'admin') { 'admin-ui' } else { $s[0] }
        Start-LocalProcess $processName $s[1] (Get-Command node.exe).Source @(('"'+$vite+'"'),'--host','127.0.0.1','--strictPort','--port',"$($s[1])") $dir
      }
    }
  }
} finally { Pop-Location }

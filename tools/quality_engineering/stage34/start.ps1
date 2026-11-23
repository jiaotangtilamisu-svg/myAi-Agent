param([ValidateSet('guard','user','product','stock','order','search','admin','cart','gateway','mcp','agent','web','admin-ui')][string]$Service)
$ErrorActionPreference='Stop'
$root=(Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
$run=(Get-Content (Join-Path $root '.cache/stage34/active.json') -Raw | ConvertFrom-Json).directory
$plan=Get-Content (Join-Path $run 'plan.json') -Raw | ConvertFrom-Json
$envs=Get-Content (Join-Path $run 'environment-private.json') -Raw | ConvertFrom-Json
$port=$plan.ports.$Service
if(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue){throw 'Test port is occupied; no process stopped or duplicated.'}
$logs=Join-Path $run ('logs/'+$Service+'-'+(Get-Date -Format 'yyyyMMdd-HHmmssfff'))
New-Item -ItemType Directory -Force $logs | Out-Null
$python=Join-Path $root 'Simlect-backend/Simlect-agent/.venv/Scripts/python.exe'
if($Service -in @('guard','mcp','agent')){
 $file=$python;$dir=Join-Path $root 'Simlect-backend/Simlect-agent'
 if($Service -eq 'guard'){$argsList=@('-m','uvicorn','tools.quality_engineering.stage34.guard:app','--host','127.0.0.1','--port',"$port");$health='/quality34/health'}
 elseif($Service -eq 'mcp'){$argsList=@('-m','app.mcp_server');$health='/health'}
 else{$argsList=@('-m','uvicorn','app.main:app','--host','127.0.0.1','--port',"$port");$health='/health'}
}elseif($Service -in @('web','admin-ui')){
 $file='E:/Nodejs/node.exe';$folder=if($Service -eq 'web'){'Simlect-web'}else{'Simlect-admin'}
 $dir=Join-Path $root "Simlect-front/$folder";$vite=Join-Path $dir 'node_modules/vite/bin/vite.js'
 $argsList=@($vite,'--config',(Join-Path $run "$Service.vite.config.mjs"),'--strictPort');$health=if($Service -eq 'web'){'/'}else{'/admin/'}
}else{
 $file='E:/JDK17/bin/java.exe'
 $sub=if($Service -in @('gateway','admin','search')){''}else{'/app'}
 $dir=Join-Path $run "build/Simlect-backend/Simlect-$Service$sub"
 $jar=@(Get-ChildItem -LiteralPath (Join-Path $dir 'target') -Filter '*.jar' | Where-Object Name -NotMatch 'original|sources|javadoc')
 if($jar.Count -ne 1){throw 'Expected one isolated copied-build JAR.'}
 # Actual Search log proved Java heap exhaustion at 160 MiB. Scope this
 # capacity correction to the isolated Search process, not formal services.
 $maxHeap=if($Service -eq 'search'){'-Xmx384m'}else{'-Xmx160m'}
 $argsList=@('-Xms32m',$maxHeap,'-Xss512k','-XX:ActiveProcessorCount=2','-XX:MaxDirectMemorySize=32m','-Dfile.encoding=UTF-8',('-Dsimlect.product.index='+$plan.productIndex),'-jar',$jar[0].FullName,'--server.address=127.0.0.1','--spring.cloud.nacos.discovery.ip=127.0.0.1')
 $health='/actuator/health'
}
$saved=@{}
$outLog=Join-Path $logs 'stdout.log';$errLog=Join-Path $logs 'stderr.log'
if($Service -eq 'search'){
 # Search JVM previously shut down for an unconfirmed reason. Test a separate
 # native process group for only this isolated JVM; do not assert causation.
 $spec=Join-Path $logs 'native-launch-spec.json'
 @{executable='E:/JDK17/bin/java.exe';args=$argsList;cwd=$dir;logs=$logs}|ConvertTo-Json -Depth 5|Set-Content $spec -Encoding utf8
 $file='E:/Nodejs/node.exe';$argsList=@((Join-Path $PSScriptRoot 'native-child.mjs'),$spec)
 $outLog=Join-Path $logs 'launcher.stdout.log';$errLog=Join-Path $logs 'launcher.stderr.log'
}
try{
 foreach($p in $envs.$Service.PSObject.Properties){$saved[$p.Name]=[Environment]::GetEnvironmentVariable($p.Name,'Process');[Environment]::SetEnvironmentVariable($p.Name,[string]$p.Value,'Process')}
 $quoted=@($argsList | ForEach-Object {'"'+$_+'"'})
 $process=Start-Process -FilePath $file -ArgumentList $quoted -WorkingDirectory $dir -WindowStyle Hidden -PassThru -RedirectStandardOutput $outLog -RedirectStandardError $errLog
}finally{foreach($key in $saved.Keys){[Environment]::SetEnvironmentVariable($key,$saved[$key],'Process')}}
$record=@{Service=$Service;LauncherPID=$process.Id;Port=$port;LogDirectory=$logs;Executable=$file;StartedAt=(Get-Date).ToString('o');State='STARTING'}
$recordFile=Join-Path $run "$Service-process.json"
$record | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $recordFile -Encoding utf8
$hostName=if($Service -in @('web','admin-ui')){'127.0.0.2'}else{'127.0.0.1'}
$probeTimeout=if($Service -eq 'agent'){8}else{3}
for($i=0;$i -lt 120;$i++){
 if($process.HasExited){$record.State='EXITED';$record.ExitCode=$process.ExitCode;break}
 try{
  $r=Invoke-WebRequest "http://${hostName}:$port$health" -UseBasicParsing -TimeoutSec $probeTimeout
  if([int]$r.StatusCode -eq 200){
   $listen=Get-NetTCPConnection -LocalPort $port -State Listen | Select-Object -First 1
   $actual=Get-CimInstance Win32_Process -Filter "ProcessId=$($listen.OwningProcess)"
   $record.PID=$actual.ProcessId;$record.ParentProcessId=$actual.ParentProcessId;$record.CreationDate=$actual.CreationDate.ToString('o');$record.CommandLine=$actual.CommandLine;$record.ExecutablePath=$actual.ExecutablePath;$record.State='RESPONDING';break
  }
 }catch{}
 Start-Sleep -Seconds 1
}
$record | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $recordFile -Encoding utf8
Write-Output "$Service $($record.State); PID $($record.PID); port $port; logs $logs"
if($record.State -ne 'RESPONDING'){exit 1}

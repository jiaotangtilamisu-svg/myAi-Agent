param([string]$OutputFile)
$ErrorActionPreference='Stop'
$root=(Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
if(-not $OutputFile){$OutputFile=Join-Path $root '.cache/quality-engineering-20261105/runtime-health.json'}
$targets=@(
 @{Name='gateway';Port=8080;Path='/actuator/health';Status='UP'},
 @{Name='order';Port=8093;Path='/actuator/health';Status='UP'},
 @{Name='product';Port=8099;Path='/actuator/health';Status='UP'},
 @{Name='stock';Port=8102;Path='/actuator/health';Status='UP'},
 @{Name='search';Port=8108;Path='/actuator/health';Status='UP'},
 @{Name='user';Port=8105;Path='/actuator/health';Status='UP'},
 @{Name='cart';Port=8084;Path='/actuator/health';Status='UP'},
 @{Name='coupon';Port=8087;Path='/actuator/health';Status='UP'},
 @{Name='pay';Port=8096;Path='/actuator/health';Status='UP'},
 @{Name='admin';Port=8111;Path='/actuator/health';Status='UP'},
 @{Name='mcp';Port=7060;Path='/health';Status='ok'},
 @{Name='agent';Port=7050;Path='/health';Status='ok'},
 @{Name='web';Port=6001;Path='/';Status=$null},
 @{Name='admin-ui';Port=6002;Path='/admin/';Status=$null}
)
$rows=foreach($t in $targets){
 $owners=@(Get-NetTCPConnection -LocalPort $t.Port -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique)
 $processes=@(foreach($owner in $owners){$p=Get-CimInstance Win32_Process -Filter "ProcessId=$owner";if($p){@{PID=$p.ProcessId;ParentProcessId=$p.ParentProcessId;CreationDate=$p.CreationDate.ToString('o');ExecutablePath=$p.ExecutablePath}}})
 $code=$null;$status=$null;$errorType=$null;$javaWeb=$null
 try{$r=Invoke-WebRequest ("http://127.0.0.1:"+$t.Port+$t.Path) -UseBasicParsing -TimeoutSec 5;$code=[int]$r.StatusCode
  if($t.Status){$content=if($r.Content -is [byte[]]){[System.Text.Encoding]::UTF8.GetString($r.Content)}else{[string]$r.Content};$body=$content | ConvertFrom-Json;$status=$body.status;if($t.Name -eq 'agent'){$javaWeb=$body.java_web}}
 }catch{$errorType=$_.Exception.GetType().Name}
 $ok=$owners.Count -eq 1 -and $code -eq 200 -and (-not $t.Status -or $status -eq $t.Status)
 if($t.Name -eq 'agent'){$ok=$ok -and $javaWeb -eq $true}
 @{Service=$t.Name;Port=$t.Port;Processes=$processes;HTTP=$code;Status=$status;JavaWeb=$javaWeb;Passed=$ok;ErrorType=$errorType}
}
$result=@{Scope='Readonly local health, not business/browser/model acceptance';CheckedAt=(Get-Date).ToString('o');Passed=@($rows | Where-Object Passed -eq $true).Count;Failed=@($rows | Where-Object Passed -ne $true).Count;Services=@($rows)}
$result | ConvertTo-Json -Depth 7 | Set-Content -LiteralPath $OutputFile -Encoding utf8
Write-Output "Local health: $($result.Passed) passed, $($result.Failed) failed"
if($result.Failed){exit 1};exit 0

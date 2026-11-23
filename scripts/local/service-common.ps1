# Shared planning/logging only. Dot-sourcing this file never starts a service.
function Get-IndependentPlan([string]$Name) {
    $root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
    $agent = Join-Path $root 'Simlect-backend/Simlect-agent'
    $envFile = Join-Path $agent '.env'
    if (-not (Test-Path -LiteralPath $envFile)) { throw 'Existing Agent .env is required; it will not be created or replaced.' }
    $environment = @{}
    # Match deploy/start-local.ps1 exactly; do not evaluate dotenv contents as PowerShell.
    foreach ($line in Get-Content -LiteralPath $envFile -Encoding UTF8) {
        if ($line -match '^([A-Z][A-Z0-9_]*)=(.*)$') { $environment[$matches[1]] = $matches[2] }
    }
    if (-not $environment['SIMLECT_INTERNAL_TOKEN'] -or $environment['SIMLECT_INTERNAL_TOKEN'] -in @('your-token','changeme')) {
        throw 'Existing internal token is missing or weak; no service started.'
    }
    $environment['JAVA_HOME'] = 'E:\JDK17'
    $environment['PATH'] = 'E:\JDK17\bin;E:\Nodejs;E:\Python;E:\develop\apache-maven-3.9.4-bin\apache-maven-3.9.4\bin;' + $env:PATH
    $environment['TEMP'] = 'E:\SimlectRuntime\tmp'
    $environment['TMP'] = 'E:\SimlectRuntime\tmp'
    $environment['JAVA_TOOL_OPTIONS'] = ($env:JAVA_TOOL_OPTIONS + ' -Djdk.net.unixdomain.tmpdir=E:\SimlectRuntime\tmp').Trim()
    $environment['PYTHONUTF8'] = '1'
    $environment['PYTHONUNBUFFERED'] = '1'
    $environment['SIMLECT_PAY_LOCAL_MOCK_ENABLED'] = 'true'
    $environment['SEATA_ENABLED'] = 'false'
    $environment['FASTMCP_HOST'] = '127.0.0.1'
    $environment['FASTMCP_PORT'] = '7060'
    if ($Name -in @('agent','mcp')) {
        # Local configured storefront catalogue; REAL remains a separate strict mode.
        $environment['SHOPPING_DATA_MODE'] = 'LOCAL_STORE'
        $environment['SHOPPING_REQUIREMENT_LLM_ENABLED'] = 'false'
    }
    if (-not (Test-Path -LiteralPath 'E:\SimlectRuntime\tmp' -PathType Container)) { throw 'Existing E:\SimlectRuntime\tmp is required.' }
    if ($Name -eq 'order') {
        $directory = Join-Path $root 'Simlect-backend/Simlect-order/app'
        $jars = @(Get-ChildItem -LiteralPath (Join-Path $directory 'target') -Filter '*.jar' | Where-Object Name -NotMatch '(sources|javadoc|original)')
        if ($jars.Count -ne 1) { throw 'Expected exactly one existing Order executable JAR; this script never builds.' }
        $file = 'E:\JDK17\bin\java.exe'
        $arguments = @('-Xms64m','-Xmx320m','-Dfile.encoding=UTF-8','-jar',$jars[0].FullName,'--server.address=127.0.0.1','--spring.cloud.nacos.discovery.ip=127.0.0.1','--spring.datasource.url=jdbc:mysql://127.0.0.1:13306/simlect_order?useUnicode=true&characterEncoding=utf-8&serverTimezone=Asia/Shanghai&allowPublicKeyRetrieval=true&allowMultiQueries=true&useSSL=false')
        $port = 8093; $health = 'http://127.0.0.1:8093/actuator/health'
        foreach ($key in @('LLM_API_KEY','EMBEDDING_API_KEY')) { if ([string]::IsNullOrWhiteSpace($environment[$key])) { $environment[$key] = $null } }
    } else {
        $directory = $agent; $file = Join-Path $agent '.venv/Scripts/python.exe'
        if ($Name -eq 'agent') {
            $arguments = @('-m','uvicorn','app.main:app','--host','127.0.0.1','--port','7050')
            $port = 7050; $health = 'http://127.0.0.1:7050/health'
        } elseif ($Name -eq 'mcp') {
            $arguments = @('-m','app.mcp_server'); $port = 7060; $health = 'http://127.0.0.1:7060/health'
        } else { throw 'Unsupported service name.' }
    }
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { throw "Existing executable not found: $file" }
    $secrets = New-Object 'System.Collections.Generic.List[string]'
    foreach ($entry in [Environment]::GetEnvironmentVariables('Process').GetEnumerator()) {
        if ($entry.Key -match '(?i)KEY|TOKEN|PASSWORD|SECRET|CREDENTIAL' -and ([string]$entry.Value).Length -gt 0) { $secrets.Add([string]$entry.Value) }
    }
    foreach ($key in $environment.Keys) {
        if ($key -match '(?i)KEY|TOKEN|PASSWORD|SECRET|CREDENTIAL' -and ([string]$environment[$key]).Length -gt 0) { $secrets.Add([string]$environment[$key]) }
    }
    [pscustomobject]@{Name=$Name;Root=$root;Directory=$directory;File=$file;Arguments=$arguments;Port=$port;Health=$health;Environment=$environment;Secrets=$secrets.ToArray()}
}

function Protect-ServiceText([string]$Text, [string[]]$Secrets = @()) {
    foreach ($value in ($Secrets | Sort-Object Length -Descending)) { if ($value) { $Text = $Text.Replace($value,'[REDACTED]') } }
    $Text = $Text -replace '(?i)((?:password|passwd|secret|token|api[_-]?key)\s*["'':=]+\s*)[^\s,;"''}]+','$1[REDACTED]'
    $Text -replace '(?i)(Bearer\s+)\S+','$1[REDACTED]'
}

function Invoke-IndependentService([string]$Name, [switch]$ValidateOnly) {
    $plan = Get-IndependentPlan $Name
    if ($ValidateOnly) {
        # No process/environment changes, directories/log files, or network calls in this branch.
        [pscustomobject]@{Service=$Name;Executable=$plan.File;WorkingDirectory=$plan.Directory;Arguments=(Protect-ServiceText ($plan.Arguments -join ' ') $plan.Secrets);Port=$plan.Port;Health=$plan.Health;EnvironmentNames=@($plan.Environment.Keys | Sort-Object);Validation='Plan only; not started'}
        return
    }
    if (Get-NetTCPConnection -LocalPort $plan.Port -State Listen -ErrorAction SilentlyContinue) { throw "Port $($plan.Port) is already occupied; no process stopped." }
    $logRoot = Join-Path $plan.Root "logs/independent-services/$Name"
    $latest = Join-Path $logRoot 'latest.json'
    if (Test-Path -LiteralPath $latest) {
        $previous = Get-Content -LiteralPath $latest -Raw | ConvertFrom-Json
        if (Test-Path -LiteralPath $previous.Record) {
            $record = Get-Content -LiteralPath $previous.Record -Raw | ConvertFrom-Json
            if ($record.LauncherPID) {
                $existing = Get-Process -Id $record.LauncherPID -ErrorAction SilentlyContinue
                if ($existing -and $existing.StartTime.ToUniversalTime().Ticks.ToString() -eq $record.StartTicks) { throw 'A recorded instance is still alive; no second instance started.' }
            }
        }
    }
    $run = Join-Path $logRoot ((Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0,8))
    New-Item -ItemType Directory -Path $run -Force | Out-Null
    $recordFile = Join-Path $run 'process.json'
    $state = [ordered]@{Service=$Name;State='Preparing';StartedAt=[DateTimeOffset]::Now.ToString('o');SupervisorPID=$PID;LauncherPID=$null;StartTicks=$null;WorkingDirectory=$plan.Directory;Executable=$plan.File;Command=(Protect-ServiceText (($plan.File + ' ') + ($plan.Arguments -join ' ')) $plan.Secrets);Port=$plan.Port;Health=$plan.Health;ExitCode=$null;ExitedAt=$null}
    $state | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $recordFile -Encoding UTF8
    @{Record=$recordFile} | ConvertTo-Json | Set-Content -LiteralPath $latest -Encoding UTF8
    $saved = @{}
    try {
        foreach ($key in $plan.Environment.Keys) { $saved[$key]=[Environment]::GetEnvironmentVariable($key,'Process'); [Environment]::SetEnvironmentVariable($key,$plan.Environment[$key],'Process') }
        if (-not ('IndependentServiceLog' -as [type])) { Add-Type -Path (Join-Path $PSScriptRoot 'ServiceLog.cs') }
        $start = New-Object System.Diagnostics.ProcessStartInfo
        $start.FileName=$plan.File
        # All arguments are fixed by this plan. No credential is passed on the command line.
        $start.Arguments=($plan.Arguments | ForEach-Object { '"' + $_ + '"' }) -join ' '
        $start.WorkingDirectory=$plan.Directory; $start.UseShellExecute=$false
        $start.CreateNoWindow=$false; $start.RedirectStandardOutput=$true; $start.RedirectStandardError=$true
        $start.StandardOutputEncoding=[Text.Encoding]::UTF8; $start.StandardErrorEncoding=[Text.Encoding]::UTF8
        $writer = [IndependentServiceLog]::new($start,$run,[string[]]$plan.Secrets)
        try {
            $writer.Start()
            $state.State='Running'; $state.LauncherPID=$writer.Pid; $state.StartTicks=$writer.StartTicks
            $state | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $recordFile -Encoding UTF8
            "Started $Name; launcher PID $($writer.Pid); logs: $run" | Tee-Object -FilePath (Join-Path $run 'startup.log')
            Write-Host 'Keep this manually opened PowerShell window open. Ctrl+C is the preferred graceful stop.'
            $code=$writer.WaitForExit()
            $state.ExitCode=$code; $state.ExitedAt=[DateTimeOffset]::Now.ToString('o'); $state.State='Exited'
            "Exited with code $code at $($state.ExitedAt)" | Add-Content -LiteralPath (Join-Path $run 'startup.log')
            if ($code -ne 0) { Write-Warning "$Name exited with code $code; inspect this run's stderr/stdout." }
        } finally { $writer.Dispose() }
    } catch {
        $message=Protect-ServiceText ($_ | Out-String) $plan.Secrets
        $message | Add-Content -LiteralPath (Join-Path $run 'startup.log') -Encoding UTF8
        if ($state.State -eq 'Preparing') { $state.State='StartFailed' } elseif ($state.State -eq 'Running') { $state.State='SupervisorInterrupted'; $state.ExitCode=$null }
        throw (New-Object System.Exception($message))
    } finally {
        $state | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $recordFile -Encoding UTF8
        foreach ($key in $saved.Keys) { [Environment]::SetEnvironmentVariable($key,$saved[$key],'Process') }
    }
}

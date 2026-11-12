$ErrorActionPreference = 'Stop'

$root = $PSScriptRoot
$logs = Join-Path $root 'logs'
New-Item -ItemType Directory -Path $logs -Force | Out-Null
$guard = [Threading.Mutex]::new($false, 'Local\QianxiaStandaloneWatchdog')
$held = $false

function Write-WatchdogLog {
    param([string]$Message)
    Add-Content -LiteralPath (Join-Path $logs 'watchdog.log') -Encoding utf8 -Value (
        '{0:yyyy-MM-dd HH:mm:ss} {1}' -f (Get-Date), $Message
    )
}

function Start-MissingService {
    param(
        [string]$Name, [int]$Port, [string]$Executable, [string[]]$Arguments,
        [string]$WorkingDirectory, [bool]$AlreadyRunning
    )
    if ($Port -in $listeningPorts -or $AlreadyRunning) {
        return
    }
    if (-not (Test-Path -LiteralPath $Executable -PathType Leaf)) {
        Write-WatchdogLog "$Name executable is missing: $Executable"
        return
    }
    try {
        $process = Start-Process -FilePath $Executable -ArgumentList $Arguments -WorkingDirectory $WorkingDirectory `
            -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logs "$Name.stdout.log") `
            -RedirectStandardError (Join-Path $logs "$Name.stderr.log") -PassThru
        Write-WatchdogLog "$Name launched, PID $($process.Id)"
    } catch {
        Write-WatchdogLog "$Name failed to launch: $($_.Exception.GetType().Name)"
    }
}

try {
    try {
        $held = $guard.WaitOne(0)
    } catch [Threading.AbandonedMutexException] {
        $held = $true
    }
    if (-not $held) { return }

    $listeningPorts = @(Get-NetTCPConnection -State Listen -LocalPort 6099,8000,8080,9880,11434 -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty LocalPort)
    $processes = @(Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='node.exe' OR Name='QQ.exe' OR Name='llama-server.exe' OR Name='powershell.exe'")

    $modelRoot = 'D:\LocalAI\Qwen3.8-27B'
    $modelLauncher = Join-Path $modelRoot 'Start-Qwen.ps1'
    $modelServer = Join-Path $modelRoot 'runtime\llama-server.exe'
    $windowsShell = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    $modelRunning = [bool]($processes | Where-Object {
        $_.ExecutablePath -eq $modelServer -or
        ($_.Name -eq 'powershell.exe' -and $_.CommandLine -like "*$modelLauncher*")
    })
    if (Test-Path -LiteralPath $modelLauncher -PathType Leaf) {
        Start-MissingService 'watchdog-qwen' 11434 $windowsShell `
            @('-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'RemoteSigned', '-File', "`"$modelLauncher`"") $modelRoot $modelRunning
    } else {
        Write-WatchdogLog 'Local Qwen launcher is missing.'
    }

    $napRoot = Join-Path $root 'napcat\node-v4.18.42'
    $napExe = Join-Path $napRoot 'node.exe'
    $napRunning = [bool]($processes | Where-Object ExecutablePath -eq $napExe)
    $napArgs = @('index.js')
    $profiles = @(Get-ChildItem -LiteralPath (Join-Path $napRoot 'napcat\config') -File -ErrorAction SilentlyContinue |
        Where-Object Name -match '^onebot11_[0-9]{5,12}\.json$')
    if ($profiles.Count -eq 1 -and $profiles[0].Name -match '^onebot11_([0-9]{5,12})\.json$') {
        $napArgs += @('-q', $Matches[1])
    }
    $modeFile = Join-Path $root 'napcat\active-mode.json'
    $napMode = if (Test-Path -LiteralPath $modeFile) { (Get-Content -LiteralPath $modeFile -Raw | ConvertFrom-Json).mode } else { 'node' }
    if ($napMode -eq 'framework') {
        $frameworkScript = Join-Path $root 'Start-NapCatFramework.ps1'
        $frameworkQQ = Join-Path $root 'napcat\headful-qq-official-49738\QQ.exe'
        $frameworkRunning = [bool]($processes | Where-Object ExecutablePath -eq $frameworkQQ)
        Start-MissingService 'watchdog-framework' 6099 $windowsShell `
            @('-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'RemoteSigned', '-File', "`"$frameworkScript`"") $root $frameworkRunning
    } elseif ($napMode -eq 'node') {
        Start-MissingService 'watchdog-napcat' 6099 $napExe $napArgs $napRoot $napRunning
    } else {
        throw "Unknown NapCat mode: $napMode"
    }

    $botPython = Join-Path $root '.venv\Scripts\python.exe'
    $botScript = Join-Path $root 'bot.py'
    $botRunning = [bool]($processes | Where-Object {
        $_.Name -eq 'python.exe' -and $_.CommandLine -like "*$botScript*"
    })
    Start-MissingService 'watchdog-bot' 8080 $botPython `
        @('-X', 'utf8', '-u', "`"$botScript`"") $root $botRunning

    $voiceEnv = 'D:\cosmos\miniconda3\envs\gptsovits'
    $voicePython = Join-Path $voiceEnv 'python.exe'
    $sovitsRoot = 'D:\gptsovits\repo'
    $sovitsScript = Join-Path $sovitsRoot 'api_v2.py'
    $voiceRoot = [IO.Path]::GetFullPath((Join-Path $root '..\..\voice'))
    $sovitsRunning = [bool]($processes | Where-Object {
        $_.ExecutablePath -eq $voicePython -and $_.CommandLine -like '*api_v2.py*' -and
        $_.CommandLine -match '(?:^|\s)-p\s+9880(?:\s|$)'
    })
    $voiceRunning = [bool]($processes | Where-Object {
        $_.ExecutablePath -eq $voicePython -and $_.CommandLine -like '*uvicorn*app:app*' -and
        $_.CommandLine -match '(?:^|\s)--port\s+8000(?:\s|$)'
    })
    $previousPath = $env:PATH
    $previousUtf8 = $env:PYTHONUTF8
    try {
        $env:PATH = "$voiceEnv;$voiceEnv\Library\bin;$voiceEnv\Scripts;$previousPath"
        $env:PYTHONUTF8 = '1'
        if (Test-Path -LiteralPath $sovitsScript -PathType Leaf) {
            Start-MissingService 'watchdog-sovits' 9880 $voicePython `
                @('-X', 'utf8', '-u', "`"$sovitsScript`"", '-a', '127.0.0.1', '-p', '9880',
                  '-c', 'GPT_SoVITS/configs/tts_infer.yaml') $sovitsRoot $sovitsRunning
        } else {
            Write-WatchdogLog 'GPT-SoVITS launcher is missing.'
        }
        if (Test-Path -LiteralPath (Join-Path $voiceRoot '.env') -PathType Leaf) {
            Start-MissingService 'watchdog-tts' 8000 $voicePython `
                @('-X', 'utf8', '-u', '-m', 'uvicorn', 'app:app', '--host', '127.0.0.1',
                  '--port', '8000', '--env-file', '.env') $voiceRoot $voiceRunning
        } else {
            Write-WatchdogLog 'Voice adapter configuration is missing.'
        }
    } finally {
        $env:PATH = $previousPath
        $env:PYTHONUTF8 = $previousUtf8
    }

    $connected = [bool](Get-NetTCPConnection -State Established -LocalPort 8080 -ErrorAction SilentlyContinue)
    $state = if ($connected) { 'OneBot connected.' } else { 'Waiting for OneBot. Check NapCat WebUI for QQ login.' }
    $stateFile = Join-Path $logs 'watchdog-state.txt'
    $previous = if (Test-Path -LiteralPath $stateFile) { Get-Content -LiteralPath $stateFile -Raw }
    if ([string]::IsNullOrWhiteSpace($previous) -or $state -ne $previous.Trim()) {
        Write-WatchdogLog $state
        Set-Content -LiteralPath $stateFile -Value $state -Encoding utf8
    }
} finally {
    if ($held) { $guard.ReleaseMutex() }
    $guard.Dispose()
}

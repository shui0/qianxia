$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$framework = Join-Path $root 'napcat\framework-v4.18.42'
$qq = Join-Path $root 'napcat\headful-qq-official-49738\QQ.exe'
$launcher = Join-Path $framework 'napimain.exe'
$inject = Join-Path $framework 'napiloader.dll'
$main = Join-Path $framework 'nativeLoader.cjs'
foreach ($file in @($qq, $launcher, $inject, $main)) {
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { throw "Framework file missing: $file" }
}
$running = Get-CimInstance Win32_Process -Filter "Name='QQ.exe'" |
    Where-Object ExecutablePath -eq $qq
if ($running) { return }
$previousMain = $env:NAPCAT_MAIN_PATH
try {
    $env:NAPCAT_MAIN_PATH = $main.Replace('\', '/')
    Start-Process -FilePath $launcher -ArgumentList @("`"$qq`"", "`"$inject`"", "`"$($env:NAPCAT_MAIN_PATH)`"") `
        -WorkingDirectory $framework -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $root 'logs\framework-launch.stdout.log') `
        -RedirectStandardError (Join-Path $root 'logs\framework-launch.stderr.log') | Out-Null
} finally {
    $env:NAPCAT_MAIN_PATH = $previousMain
}

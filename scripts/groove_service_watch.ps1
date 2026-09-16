# Supervise the existing Groove origin and named tunnel; credentials stay on disk.
[CmdletBinding()]
param([switch]$Once)
$ErrorActionPreference = 'Stop'
$root = 'C:\Groove-Lab'
$logDir = Join-Path $root 'Logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$origin = $null
$tunnel = $null
$originStarted = Get-Date
$tunnelStarted = Get-Date
function Test-HttpReady([string]$Url) {
    try { return (Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5).StatusCode -eq 200 }
    catch { return $false }
}
function Test-OriginPort {
    $socket = New-Object Net.Sockets.TcpClient
    try { $socket.Connect('127.0.0.1', 18765); return $true }
    catch { return $false }
    finally { $socket.Dispose() }
}
function Write-ServiceLog([string]$Message) {
    Add-Content -LiteralPath (Join-Path $logDir 'service-watch.log') -Encoding UTF8 -Value ("{0:o} {1}" -f (Get-Date), $Message)
}
do {
    $originReady = Test-HttpReady 'http://127.0.0.1:18765/'
    $tunnelReady = Test-HttpReady 'http://127.0.0.1:20242/ready'
    if (-not $originReady) {
        if ($null -ne $origin -and -not $origin.HasExited -and ((Get-Date) - $originStarted).TotalSeconds -gt 90) {
            # Stop only a child created by this supervisor, never another origin.
            $origin.Kill()
            $origin.WaitForExit(5000) | Out-Null
            Write-ServiceLog 'Restarting owned unresponsive origin'
        }
        if (($null -eq $origin -or $origin.HasExited) -and -not (Test-OriginPort)) {
            $python = Join-Path $root 'Analysis\venv\Scripts\python.exe'
            if (-not (Test-Path -LiteralPath $python)) { throw 'Groove Python runtime missing' }
            $origin = Start-Process -FilePath $python -WindowStyle Hidden -PassThru -WorkingDirectory $root -ArgumentList '-u "C:\Groove-Lab\server.py" --host 127.0.0.1 --port 18765 --no-browser' -RedirectStandardOutput (Join-Path $logDir 'service-origin-stdout.log') -RedirectStandardError (Join-Path $logDir 'service-origin-stderr.log')
            $originStarted = Get-Date
            Write-ServiceLog "Started origin pid=$($origin.Id)"
        }
    }
    if (-not $tunnelReady) {
        if ($null -ne $tunnel -and -not $tunnel.HasExited -and ((Get-Date) - $tunnelStarted).TotalSeconds -gt 90) {
            $tunnel.Kill()
            $tunnel.WaitForExit(5000) | Out-Null
            Write-ServiceLog 'Restarting owned disconnected connector'
        }
        if ($null -eq $tunnel -or $tunnel.HasExited) {
            $connector = 'C:\Program Files (x86)\cloudflared\cloudflared.exe'
            if (-not (Test-Path -LiteralPath $connector)) { throw 'Cloudflared runtime missing' }
            $tunnel = Start-Process -FilePath $connector -WindowStyle Hidden -PassThru -WorkingDirectory $root -ArgumentList 'tunnel --config "C:\Groove-Lab\config.yml" --metrics 127.0.0.1:20242 run b02ca562-fb29-433e-aab7-7d3ac68de7f1' -RedirectStandardOutput (Join-Path $logDir 'service-tunnel-stdout.log') -RedirectStandardError (Join-Path $logDir 'service-tunnel-stderr.log')
            $tunnelStarted = Get-Date
            Write-ServiceLog "Started connector pid=$($tunnel.Id)"
        }
    }
    $status = [ordered]@{checked_at=(Get-Date).ToString('o'); origin_ready=$originReady; tunnel_ready=$tunnelReady; supervisor_pid=$PID}
    $temp = Join-Path $logDir "service-status.$PID.tmp"
    $status | ConvertTo-Json | Set-Content -LiteralPath $temp -Encoding UTF8
    Move-Item -LiteralPath $temp -Destination (Join-Path $logDir 'service-status.json') -Force
    if (-not $Once) { Start-Sleep -Seconds 30 }
} while (-not $Once)
if (-not ($originReady -and $tunnelReady)) { exit 1 }

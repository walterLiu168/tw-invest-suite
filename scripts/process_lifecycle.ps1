# Read a fresh process and its creation identity on every probe.
function Test-OwnedProcess {
    param([int]$ProcessId, [long]$CreatedUtcTicks)
    $live = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if ($null -eq $live) { return $false }
    try { return $live.StartTime.ToUniversalTime().Ticks -eq $CreatedUtcTicks }
    catch {
        if ($null -eq (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue)) { return $false }
        throw
    }
}
function Wait-OwnedProcess {
    param([int]$ProcessId, [long]$CreatedUtcTicks, [int]$TimeoutMs)
    $deadline = (Get-Date).AddMilliseconds($TimeoutMs)
    while ((Test-OwnedProcess $ProcessId $CreatedUtcTicks) -and (Get-Date) -lt $deadline) {
        Start-Sleep -Milliseconds 200
    }
    return -not (Test-OwnedProcess $ProcessId $CreatedUtcTicks)
}

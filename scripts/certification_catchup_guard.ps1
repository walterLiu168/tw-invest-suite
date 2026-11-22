# Guard for the independent hourly certification catch-up task.
# Skip only when the target session, both sites, reports and Telegram agree.
$ErrorActionPreference = 'Continue'
$runtime = 'C:\Users\icemo\.claude\skills\tw-invest-suite\scripts'
Set-Location $runtime
$debug = Join-Path $runtime '_debug'
New-Item -ItemType Directory -Force -Path $debug | Out-Null
$log = Join-Path $debug 'certification_catchup_guard.log'
function Log([string]$Message) {
    $line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $Message"
    Add-Content -LiteralPath $log -Value $line -Encoding UTF8
    Write-Host $line
}
function Test-Delivery([string]$TargetDate) {
    & C:\Python314\python.exe -c "import sys; from daily_chain_audit import resolve_config, artifact_snapshot, ai_snapshot; c=resolve_config(); t=sys.argv[1]; sys.exit(0 if not artifact_snapshot(c,t)['findings'] and not ai_snapshot(c,t)['findings'] else 1)" $TargetDate
    return ($LASTEXITCODE -eq 0)
}

# Respect a healthy active nightly before inspecting mutable release files.
& C:\Python314\python.exe -c "import sys; from daily_certification_catchup import owner_running; sys.exit(2 if owner_running() else 0)"
if ($LASTEXITCODE -eq 2) {
    Log 'NIGHTLY_ALREADY_RUNNING'
    exit 0
}
if ($LASTEXITCODE -ne 0) { Log 'Unable to verify nightly owner'; exit 10 }

$markerPath = Join-Path $debug 'last_completed.json'
$publicationPath = Join-Path $debug 'publication_result.json'
$maintenancePath = Join-Path $debug 'maintenance_fetch.json'
if (Test-Path $markerPath) {
    try {
        $marker = Get-Content -Raw $markerPath | ConvertFrom-Json
        $publication = if (Test-Path $publicationPath) { Get-Content -Raw $publicationPath | ConvertFrom-Json } else { $null }
        $maintenance = if (Test-Path $maintenancePath) { Get-Content -Raw $maintenancePath | ConvertFrom-Json } else { $null }
        $target = & C:\Python314\python.exe -c "from daily_certification_catchup import expected_catchup_date; print(expected_catchup_date())"
        if ($LASTEXITCODE -ne 0) { throw 'Cannot resolve official target session' }
        # A readable JSON marker is not enough.  Re-run the canonical verifier so
        # publish-only recovery cannot consume stale files or changed source.
        & C:\Python314\python.exe (Join-Path $runtime 'pipeline_state.py') verify *> $null
        $markerVerified = ($LASTEXITCODE -eq 0)
        $reportVerified = ($publication.status -eq 'verified' -and
            $publication.report_status -eq 'verified')
        # A weekend re-render inherits the previous run's maintenance receipt:
        # it re-renders the same canonical inputs without refreshing them, so the
        # receipt that certified those inputs is still the right one.  The rule
        # lives in one place - pipeline_state.maintenance_claim_holds().
        & C:\Python314\python.exe -X utf8 -c "import sys, json; from pathlib import Path; import pipeline_state as ps; m=json.loads(Path(r'$markerPath').read_text(encoding='utf-8-sig')); f=json.loads(Path(r'$maintenancePath').read_text(encoding='utf-8-sig')); sys.exit(0 if ps.maintenance_claim_holds(m, f) else 1)"
        $maintenanceVerified = ($LASTEXITCODE -eq 0)
        $markerReady = ($markerVerified -and $marker.data_date -eq $target -and $marker.status -eq 'ok' -and
            $marker.marker_version -eq 'D056-3' -and $maintenanceVerified)
        $matchingRelease = ($markerReady -and
            $publication.nightly_id -eq $marker.nightly_id -and
            $publication.data_date -eq $marker.data_date -and
            $publication.published_commit -and $reportVerified -and
            $publication.postflight_exit -eq 0)
        if ($matchingRelease) {
            if (Test-Delivery $target) {
                Log "ALREADY_DELIVERED data_date=$($marker.data_date) nightly_id=$($marker.nightly_id)"
                exit 0
            }
            Log 'Delivery evidence incomplete; do not report already delivered'
        }
        $publishedRelease = ($markerVerified -and $marker.data_date -eq $target -and $marker.status -eq 'ok' -and
            $publication.nightly_id -eq $marker.nightly_id -and
            $publication.data_date -eq $marker.data_date -and
            $publication.published_commit -and $reportVerified)
        if ($publishedRelease -and -not $maintenanceVerified) {
            Log "repairing canonical maintenance evidence data_date=$($marker.data_date) nightly_id=$($marker.nightly_id)"
            $env:TW_NIGHTLY_ID = [string]$marker.nightly_id
            $env:TW_DATA_DATE = [string]$marker.data_date
            $stamp = Get-Date -Format 'yyyyMMdd'
            $stageBase = Join-Path $debug "stage_logs\${stamp}_$($marker.nightly_id)_stage1_finmind_maint"
            New-Item -ItemType Directory -Force -Path (Split-Path $stageBase) | Out-Null
            & C:\Python314\python.exe (Join-Path $runtime 'run_stage.py') `
                --label stage1_finmind_maint `
                --out "$stageBase.log" `
                --err "$stageBase.err" `
                --exit-code-file "$stageBase.exit" `
                --timeout 1440 `
                --workdir $runtime `
                'C:\Users\icemo\Projects\tw-invest-suite\src\margin_rebound\finmind_maint.py'
            if ($LASTEXITCODE -eq 0) {
                Log "canonical maintenance evidence repaired"
                $maintenanceVerified = $true
                $markerReady = $markerVerified -and $marker.status -eq 'ok' -and $marker.marker_version -eq 'D056-3'
            } else {
                Log "canonical maintenance repair failed exit=$LASTEXITCODE"
                exit $LASTEXITCODE
            }
        }
        if ($markerReady) {
            # Late provider recovery can finish the certified nightly before the
            # hourly catch-up fires.  Complete only the mutable DB metadata and
            # delivery tail; rebuilding the nightly would create a new marker and
            # invalidate the already certified artifacts.
            Log "PUBLISH_ONLY data_date=$($marker.data_date) nightly_id=$($marker.nightly_id)"
            & C:\Python314\python.exe -X utf8 (Join-Path $runtime 'company_refresh.py') 2>&1 |
                Tee-Object -FilePath (Join-Path $debug 'certification_company_refresh_latest.log')
            if ($LASTEXITCODE -ne 0) {
                Log "company refresh failed exit=$LASTEXITCODE"
                exit $LASTEXITCODE
            }
            & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $runtime 'publish_verified_sites.ps1')
            $publishExit = $LASTEXITCODE
            if ($publishExit -eq 0 -and -not (Test-Delivery $target)) {
                Log 'Publication returned success but delivery evidence remains incomplete'
                exit 10
            }
            Log "publish-only completed exit=$publishExit"
            exit $publishExit
        }
    } catch {
        Log "receipt read failed; delegating to catch-up: $($_.Exception.Message)"
    }
}

Log 'delegating to daily_certification_catchup.py'
& C:\Python314\python.exe daily_certification_catchup.py 2>&1 | Tee-Object -FilePath (Join-Path $debug 'certification_catchup_latest.log')
exit $LASTEXITCODE

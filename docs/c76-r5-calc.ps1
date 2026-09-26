# C7-6 R5: marginal per-ticker cost c and fixed overhead F from the probe log.
# Definitions are in docs/cloud-phase-1-plan.md, C7-6 "R5 執行準備". Run in pwsh 7 from the repo root:
#   pwsh -NoProfile -File docs/c76-r5-calc.ps1 -Log output/c76/r5.jsonl
# Kept under docs/ on purpose: a change under scripts/ triggers an image build, and the image
# retention window allows no more builds until C7-6 closes. Move it to scripts/ afterwards.
# Tested 2026-09-26 against the R4 log only (3 batches, no cut): that proves it runs, the numbers
# it printed for R4 are not R5 results and must not be used as c.
param([string]$Log = 'output/c76/r5.jsonl')
$r = Get-Content $Log | ForEach-Object { $_.Substring(4) | ConvertFrom-Json }
function T($s) { [DateTimeOffset]::Parse([string]$s) }
$job = $r | Where-Object kind -eq 'job'
$batches = @($r | Where-Object kind -eq 'batch' | Sort-Object { T $_.started_at })
$att = @($r | Where-Object kind -eq 'attempt')
$F = ((T $batches[0].started_at) - (T $job.refresh_started_at)).TotalSeconds
$end = (T $job.refresh_started_at).AddSeconds([double]$job.elapsed_seconds)
$rows = for ($i = 0; $i -lt $batches.Count; $i++) {
    $b = $batches[$i]; $s = T $b.started_at; $e = T $b.ended_at; $wall = ($e - $s).TotalSeconds
    $gap = if ($i + 1 -lt $batches.Count) { ((T $batches[$i + 1].started_at) - $e).TotalSeconds } else { $null }
    $mine = @($att | Where-Object run_id -eq $b.run_id)
    $cut = @($mine | Where-Object { $_.adapter.reason -eq 'cycle_budget_exhausted' }).Count
    $limited = @($mine | Where-Object status -eq 'rate_limited').Count
    [pscustomobject]@{
        batch = $i + 1; tickers = [int]$b.tickers; attempts = $mine.Count; wall = [math]::Round($wall, 3)
        gap = if ($null -eq $gap) { $null } else { [math]::Round($gap, 3) }
        c = [math]::Round($wall / $b.tickers, 3)
        c_gap = if ($null -eq $gap) { $null } else { [math]::Round(($wall + $gap) / $b.tickers, 3) }
        budget_cut = $cut; rate_limited = $limited; excluded = ($cut -gt 0 -or $limited -gt 0)
    }
}
$rows | Format-Table -AutoSize | Out-String -Width 200
# p95 by nearest rank: the ceil(0.95 n)-th smallest. With fewer than 20 batches this is the maximum.
function P95($v) { $v = @($v | Sort-Object); if (-not $v.Count) { return $null }; $v[[math]::Ceiling(0.95 * $v.Count) - 1] }
$kept = @($rows | Where-Object { -not $_.excluded })
$c = P95 ($kept | ForEach-Object c)
$cg = P95 ($kept | Where-Object { $null -ne $_.c_gap } | ForEach-Object c_gap)
"F (first batch start - refresh_started_at) = {0:N3} s" -f $F
"W (last batch end - refresh() return)      = {0:N3} s" -f ($end - (T $batches[-1].ended_at)).TotalSeconds
"refresh() elapsed = {0} s; over 110 by {1:N3} s (includes the time before run_job)" -f $job.elapsed_seconds, ([double]$job.elapsed_seconds - 110)
"batches kept for c: {0} of {1}" -f $kept.Count, $rows.Count
if ($null -ne $c) { "c  (p95, nearest rank) = {0} s/ticker -> floor((110 - F) / c)  = {1}" -f $c, [math]::Floor((110 - $F) / $c) }
# The first batch carries the container's first Yahoo request (R4: 2330 took 7.4 s against
# about 2.5 s for the rest). With p95 over a handful of batches that one warm-up can set c on its
# own, so c is also shown without batch 1. Which to use is the user's decision, not this script's.
$warm = @($kept | Where-Object batch -ne 1)
$cw = P95 ($warm | ForEach-Object c)
if ($null -ne $cw) { "c  without batch 1     = {0} s/ticker -> floor((110 - F) / c)  = {1}  ({2} batches)" -f $cw, [math]::Floor((110 - $F) / $cw), $warm.Count }
if ($null -ne $cg) { "c' (p95, gap included) = {0} s/ticker -> floor((110 - F) / c') = {1}" -f $cg, [math]::Floor((110 - $F) / $cg) }
"job: {0} / {1}" -f $job.status, $job.message
"--- attempts by status / reason / executed:"
$att | Group-Object { '{0} | {1} | {2}' -f $_.status, $_.adapter.reason, $_.adapter.executed } -NoElement | Format-Table Count, Name -AutoSize | Out-String -Width 200

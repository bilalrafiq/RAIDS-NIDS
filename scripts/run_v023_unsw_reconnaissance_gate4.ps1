param(
    [string]$RepoRoot = ".",
    [switch]$BuildEventsIfMissing,
    [switch]$SkipTests,
    [switch]$DryRun,
    [switch]$AllowDirty
)

$ErrorActionPreference = "Stop"
Set-Location $RepoRoot

$arguments = @(
    "scripts/run_v023_unsw_reconnaissance_gate4.py",
    "--repo-root", "."
)
if ($BuildEventsIfMissing) { $arguments += "--build-events-if-missing" }
if ($SkipTests) { $arguments += "--skip-tests" }
if ($DryRun) { $arguments += "--dry-run" }
if ($AllowDirty) { $arguments += "--allow-dirty" }

python @arguments

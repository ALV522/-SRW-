<#
.SYNOPSIS
    Build a reproducible local Windows venv for the SRW Python quality gates.

.DESCRIPTION
    The embedded-Python business regression runs its child with "-I -B", which
    ignores PYTHONPATH and user site-packages. On a workstation whose dependencies
    live in %APPDATA%\Python that child cannot import them, and the report used to
    look like a business regression (#172). This script builds exactly the venv the
    isolated child can see.

    No administrator rights, no Native candidate, no user workspace. Any failure
    exits non-zero: this script never warns and continues.

.NOTES
    Native tools (py, pip) write progress to stderr. PowerShell 5.1 turns redirected
    stderr into a terminating error under $ErrorActionPreference = "Stop", so every
    native call here is judged by $LASTEXITCODE instead.

    A venv interpreter on Windows is a launcher that starts the base interpreter as a
    child process. Tests that assert holder.pid -eq os.getppid() (the Host workspace
    lease handshake) therefore fail under any venv, including venv --copies, even
    though their code is correct. Run those with the base interpreter; the business
    regression needs the venv because its child runs with -I -B.
#>
[CmdletBinding()]
param(
    [string]$Root = (Split-Path -Parent $PSScriptRoot),
    [string]$VenvPath = ".venv"
)

$ErrorActionPreference = "Continue"

function Stop-Blocked {
    param([string]$Reason)
    Write-Host ""
    Write-Host "BLOCKED: $Reason" -ForegroundColor Red
    exit 2
}

if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    Stop-Blocked "the Python launcher 'py' is not on PATH; install Python 3.12 and retry"
}

& py -3.12 -c "import sys" 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    Stop-Blocked "Python 3.12 is not registered with 'py'; install it (no fallback to another version)"
}

$requirements = Join-Path $Root "requirements-ci.txt"
if (-not (Test-Path -LiteralPath $requirements)) {
    Stop-Blocked "requirements-ci.txt is missing from $Root"
}

$venv = Join-Path $Root $VenvPath
$python = Join-Path $venv "Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    Write-Host "creating venv: $venv"
    & py -3.12 -m venv $venv
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $python)) {
        Stop-Blocked "venv creation failed"
    }
}
else {
    Write-Host "reusing venv: $venv"
}

Write-Host "installing pinned CI dependencies into the venv only"
& $python -m pip install -r $requirements
$installCode = $LASTEXITCODE
if ($installCode -ne 0) {
    Stop-Blocked "pip install failed with exit code $installCode; the pinned dependencies could not be installed (network or PyPI unavailable)"
}

Write-Host "verifying the isolated interpreter resolves the declared runtime dependencies"
& $python -I -B -c "import httpx, sqlalchemy, starlette"
$importCode = $LASTEXITCODE
if ($importCode -ne 0) {
    Stop-Blocked "the venv interpreter still cannot import httpx/sqlalchemy/starlette under -I (exit $importCode)"
}

Write-Host ""
Write-Host "OK: isolated interpreter ready - $python" -ForegroundColor Green
Write-Host "  isolated imports : `"$python`" -I -B -c `"import httpx, sqlalchemy, starlette`""
Write-Host "  business unit    : `"$python`" -m unittest convergence_tests.test_native_embedded_business"
Write-Host ""
Write-Host "UNSUPPORTED: do not run the full suite with this venv." -ForegroundColor Yellow
Write-Host "A Windows venv interpreter is a launcher that starts the base interpreter as a child," -ForegroundColor Yellow
Write-Host "so the Host lease handshake (holder.pid -eq os.getppid()) fails in" -ForegroundColor Yellow
Write-Host "test_host_parent_subprocess and test_prepared_native_smoke. Those tests are not skipped." -ForegroundColor Yellow
Write-Host "Install requirements-ci.txt into the base registered Python 3.12 interpreter instead:" -ForegroundColor Yellow
Write-Host "  full suite (base): py -3.12 scripts/run_convergence_verification.py"
exit 0

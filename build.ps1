# Builds dist\EnderlitPlayer-<version>-Windows-Portable.zip and dist\SHA256SUMS.txt
param(
    [string]$Python = "python"
)
$ErrorActionPreference = "Stop"

& $Python -m pip install --upgrade pip
& $Python -m pip install -r requirements.txt
& $Python -m pip install -e ".[build]"
& $Python scripts\build_windows.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "Build complete. See the dist folder."

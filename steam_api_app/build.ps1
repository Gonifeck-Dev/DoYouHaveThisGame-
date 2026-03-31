# build.ps1 - Builds a portable single-file .exe for Steam API Helper
# Usage: .\build.ps1
# Output: dist\SteamAPIHelper.exe

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot

Write-Host "=== Steam API Helper Portable Build ===" -ForegroundColor Cyan

# 1. Install runtime dependencies
Write-Host "`n[1/3] Installing runtime dependencies..." -ForegroundColor Yellow
pip install --upgrade -r "$Root\requirements.txt"

# 2. Install PyInstaller (build-only dependency)
Write-Host "`n[2/3] Installing PyInstaller..." -ForegroundColor Yellow
pip install --upgrade pyinstaller

# 3. Build
Write-Host "`n[3/3] Building portable exe..." -ForegroundColor Yellow
$pyiArgs = @(
    "--onefile"
    "--windowed"
    "--name", "SteamAPIHelper"
    "--paths", "$Root\src"
    "--distpath", "$Root\dist"
    "--workpath", "$Root\build"
    "--specpath", "$Root"
    "$Root\app.py"
)

& pyinstaller @pyiArgs

if ($LASTEXITCODE -eq 0) {
    Write-Host "`nBuild successful!" -ForegroundColor Green
    Write-Host "Executable: $Root\dist\SteamAPIHelper.exe" -ForegroundColor Green
}
else {
    Write-Host "`nBuild failed. Check the output above." -ForegroundColor Red
    exit 1
}

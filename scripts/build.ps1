# Build Eye Break: tests -> PyInstaller one-folder app -> Inno Setup installer (if iscc is available).
# Usage:  powershell -ExecutionPolicy Bypass -File scripts\build.ps1 [-SkipTests]
param([switch]$SkipTests)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

uv sync --frozen
if (-not $SkipTests) {
    uv run pytest
    if ($LASTEXITCODE -ne 0) { throw "Tests failed" }
}

if (Test-Path dist\EyeBreak) { Remove-Item -Recurse -Force dist\EyeBreak }
uv run pyinstaller packaging\eye_break.spec --noconfirm --clean --distpath dist --workpath build
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }
$size = (Get-ChildItem dist\EyeBreak -Recurse | Measure-Object Length -Sum).Sum / 1MB
Write-Host ("Portable app: dist\EyeBreak ({0:N1} MB)" -f $size)

$iscc = @(
    (Get-Command iscc -ErrorAction SilentlyContinue).Source,
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
if ($iscc) {
    & $iscc packaging\installer.iss
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }
    Write-Host "Installer: packaging\output\EyeBreak-1.0.0-Setup.exe"
} else {
    Write-Warning "Inno Setup (iscc) not found - skipped installer. Install it from https://jrsoftware.org/isinfo.php"
}

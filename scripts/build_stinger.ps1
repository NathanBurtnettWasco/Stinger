param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path,
    [switch]$InstallPyInstaller,
    [switch]$SkipTests
)

$ErrorActionPreference = 'Stop'

$projectPath = (Resolve-Path $ProjectRoot).Path
$pythonPath = Join-Path $projectPath '.venv\Scripts\python.exe'
$specPath = Join-Path $projectPath 'Stinger.spec'
$distRoot = Join-Path $projectPath 'dist'
# OneDir: PyInstaller outputs to dist\Stinger\ (exe + _internal)
$distPath = Join-Path $distRoot 'Stinger'
$workPath = Join-Path $projectPath 'build\pyinstaller'
$manifestPath = Join-Path $distPath 'build_manifest.json'

if (-not (Test-Path $pythonPath)) {
    throw "Missing virtualenv Python: $pythonPath"
}

if (-not (Test-Path $specPath)) {
    throw "Missing PyInstaller spec file: $specPath"
}

if ($InstallPyInstaller) {
    & $pythonPath -m pip install pyinstaller
}

if (-not $SkipTests) {
    & $pythonPath -m pytest -q tests/test_pressure_conversion.py tests/test_pressure_calibration.py
}

# Remove prior OneDir output so PyInstaller doesn't hit PermissionError when clearing it
$collectDir = Join-Path $distRoot 'Stinger'
if (Test-Path $collectDir) {
    Remove-Item -Recurse -Force $collectDir -ErrorAction SilentlyContinue
    if (Test-Path $collectDir) { Start-Sleep -Seconds 2; Remove-Item -Recurse -Force $collectDir -ErrorAction SilentlyContinue }
}

# OneDir: output goes to distpath/Stinger (COLLECT name), so use distRoot to get dist\Stinger\
# Note: --clean omitted to avoid PermissionError on network/synced build dirs
& $pythonPath -m PyInstaller --noconfirm --distpath "$distRoot" --workpath "$workPath" "$specPath"

$exePath = Join-Path $distPath 'Stinger.exe'
if (-not (Test-Path $exePath)) {
    throw "Build succeeded but executable missing: $exePath"
}

$configSource = Join-Path $projectPath 'stinger_config.yaml'
if (Test-Path $configSource) {
    Copy-Item $configSource (Join-Path $distPath 'stinger_config.yaml') -Force
}

$gitCommit = ''
try {
    $gitCommit = (& git -C "$projectPath" rev-parse --short HEAD).Trim()
} catch {
    $gitCommit = ''
}

$manifest = [ordered]@{
    app_name = 'Stinger'
    artifact = 'Stinger.exe'
    build_timestamp_utc = (Get-Date).ToUniversalTime().ToString('o')
    git_commit = $gitCommit
    source_spec = 'Stinger.spec'
}

$manifest | ConvertTo-Json -Depth 4 | Set-Content -Path $manifestPath -Encoding UTF8

Write-Host "Build complete: $exePath"
Write-Host "Manifest: $manifestPath"

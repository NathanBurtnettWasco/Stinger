param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path,
    [switch]$InstallPyInstaller,
    [switch]$SkipTests
)

$ErrorActionPreference = 'Stop'

$projectPath = (Resolve-Path $ProjectRoot).Path
$pythonPath = Join-Path $projectPath '.venv\Scripts\python.exe'
$specPath = Join-Path $projectPath 'QualityCal.spec'
$distRoot = Join-Path $projectPath 'dist'
$distPath = Join-Path $distRoot 'QualityCal'
$workPath = Join-Path $projectPath 'build\pyinstaller_quality_cal'
$publishPath = 'Z:\Engineering\Program Builds\Python Builds\Stinger\QualityCal'

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
    & $pythonPath -m pytest -q tests/test_quality_cal_config.py tests/test_quality_cal_report.py tests/test_quality_cal_leak.py
}

if (Test-Path $distPath) {
    Remove-Item -Recurse -Force $distPath -ErrorAction SilentlyContinue
    if (Test-Path $distPath) { Start-Sleep -Seconds 2; Remove-Item -Recurse -Force $distPath -ErrorAction SilentlyContinue }
}

& $pythonPath -m PyInstaller --noconfirm --distpath "$distRoot" --workpath "$workPath" "$specPath"

$exePath = Join-Path $distPath 'QualityCal.exe'
if (-not (Test-Path $exePath)) {
    throw "Build succeeded but executable missing: $exePath"
}

$configSource = Join-Path $projectPath 'quality_cal_config.yaml'
if (Test-Path $configSource) {
    Copy-Item $configSource (Join-Path $distPath 'quality_cal_config.yaml') -Force
}

# Publish to shared drive in addition to keeping the local dist output.
New-Item -ItemType Directory -Path $publishPath -Force | Out-Null
& robocopy $distPath $publishPath /MIR /NFL /NDL /NJH /NJS /NC /NS | Out-Null
# Robocopy exit: 0=nothing, 1=copied, 2=extra, 3=copied+extra, 4=mismatch. 8+=error
if ($LASTEXITCODE -ge 8) { throw "Robocopy failed with exit $LASTEXITCODE" }

Write-Host "Build complete: $exePath"
Write-Host "Published to: $publishPath"

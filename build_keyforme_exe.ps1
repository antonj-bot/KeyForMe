$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
if ((Split-Path -Leaf $ProjectRoot) -ne "KeyForMe") {
    $ProjectRoot = "C:\Python Projects\KeyForMe"
}
Set-Location $ProjectRoot

if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    throw "Expected virtual environment at .venv\Scripts\python.exe"
}
$Python = (Resolve-Path ".\.venv\Scripts\python.exe").Path

$Branch = (& git branch --show-current).Trim()
if ($Branch -ne "main") {
    throw "Build only from main. Current branch: $Branch"
}
$Dirty = & git status --porcelain
if ($Dirty) {
    throw "Working tree is not clean. Commit or stash changes before building."
}

Write-Host "Installing pinned application and EXE dependencies..." -ForegroundColor Cyan
& $Python -m pip install -r requirements.txt
& $Python -m pip install -r requirements-exe.txt

Write-Host "Running regression tests..." -ForegroundColor Cyan
$TestPatterns = @(
    "test_ai_providers.py",
    "test_shared_core.py",
    "test_form_engine.py",
    "test_nm_completeness.py"
)
foreach ($Pattern in $TestPatterns) {
    & $Python -m unittest discover -s tests -p $Pattern -v
}

Write-Host "Compiling Python sources..." -ForegroundColor Cyan
& $Python -m compileall -q app tests run_web_ui.py

Write-Host "Cleaning previous build output..." -ForegroundColor Cyan
Remove-Item ".\build" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item ".\dist" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item ".\KeyForMe.spec" -Force -ErrorAction SilentlyContinue

Write-Host "Validating UI assets..." -ForegroundColor Cyan
$StaticDir = Join-Path $ProjectRoot "app\ui\static"
if (-not (Test-Path $StaticDir -PathType Container)) {
    throw "Required UI asset directory is missing: $StaticDir"
}

Write-Host "Building one-file Windows executable..." -ForegroundColor Cyan
$PyInstallerArgs = @(
    "--noconfirm",
    "--clean",
    "--onefile",
    "--windowed",
    "--name", "KeyForMe",
    "--hidden-import", "keyring.backends.Windows",
    "--collect-submodules", "app.ai",
    "--collect-submodules", "app.states",
    "--collect-submodules", "app.extraction",
    "--collect-submodules", "app.browser",
    "--add-data", "$StaticDir;app/ui/static"
)

$TemplatesDir = Join-Path $ProjectRoot "app\ui\templates"
if (Test-Path $TemplatesDir -PathType Container) {
    $PyInstallerArgs += @("--add-data", "$TemplatesDir;app/ui/templates")
}

$PyInstallerArgs += "run_web_ui.py"
& $Python -m PyInstaller @PyInstallerArgs

$Exe = Join-Path $ProjectRoot "dist\KeyForMe.exe"
if (-not (Test-Path $Exe)) {
    throw "Build completed without producing dist\KeyForMe.exe"
}

$Hash = (Get-FileHash $Exe -Algorithm SHA256).Hash
$SizeMB = [math]::Round((Get-Item $Exe).Length / 1MB, 2)
Write-Host ""
Write-Host "Build successful" -ForegroundColor Green
Write-Host "File: $Exe"
Write-Host "Size: $SizeMB MB"
Write-Host "SHA256: $Hash"
Write-Host ""
Write-Host "Do not distribute yet. Test this EXE on a clean Windows user profile with Chrome installed, then test CA and NM without clicking Save or Submit." -ForegroundColor Yellow

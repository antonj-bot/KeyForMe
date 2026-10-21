param([switch]$OneFile)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if ($env:OS -ne "Windows_NT") { throw "Build the Windows EXE on Windows." }
if (-not (Test-Path ".\app\states\__init__.py")) { throw "Install this patch in the full KeyForMe project, not an empty folder." }
python -m pip install -r requirements-exe.txt
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed." }
python -m pip check
if ($LASTEXITCODE -ne 0) { throw "Resolve dependency conflicts before building." }
python -m compileall -q app run_web_ui.py
if ($LASTEXITCODE -ne 0) { throw "Syntax checks failed." }
python -m unittest discover -s tests -p test_desktop_pilot.py -v
if ($LASTEXITCODE -ne 0) { throw "Desktop pilot tests failed." }
python -c "import tkinter; from keyring.backends.Windows import WinVaultKeyring; import playwright, openai, pymupdf, fastapi, uvicorn"
if ($LASTEXITCODE -ne 0) { throw "A required runtime dependency is missing." }
# Never add the project root as data: it may contain .env, reports and mocks.
$mode = "--onedir"
$name = "KeyForMe"
if ($OneFile) { $mode = "--onefile"; $name = "KeyForMe-OneFile" }
$buildArgs = @(
    "--noconfirm", "--clean", $mode, "--windowed", "--name", $name,
    "--add-data", "app/ui/static:app/ui/static",
    "--collect-submodules", "app",
    "--collect-all", "playwright",
    "--collect-all", "keyring",
    "--hidden-import", "keyring.backends.Windows",
    "--hidden-import", "uvicorn.logging",
    "--hidden-import", "uvicorn.loops.asyncio",
    "--hidden-import", "uvicorn.protocols.http.h11_impl",
    "--hidden-import", "uvicorn.lifespan.on",
    "--exclude-module", "pytest",
    "run_web_ui.py"
)
python -m PyInstaller @buildArgs
if ($LASTEXITCODE -ne 0) { throw "Build failed. Review the output above." }
Write-Host "Build complete. Test the EXE before distribution."
if ($OneFile) {
    Write-Host "Output: dist\KeyForMe-OneFile.exe"
} else {
    Write-Host "Output: dist\KeyForMe\KeyForMe.exe (keep the entire folder together)"
}
Write-Host "Chrome must already be installed. No API key or .env is added by this script."

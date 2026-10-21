# KeyForMe Windows EXE pilot patch

This ZIP is a source patch and Windows build kit, **not a compiled EXE**. Install it in the complete working KeyForMe repository. No API key, .env, reports, mocks, or browser profile is included.

## Install safely

Start on a new branch with a clean/committed working tree. Extract this ZIP into a separate staging folder, then run its install_patch.ps1 with -ProjectRoot pointing to KeyForMe. Existing changed files are backed up in .packaging-backups/TIMESTAMP. Add .packaging-backups/, build/, dist/, and *.spec to .gitignore. Never commit backup contents or distribute the whole repository.

The patch changes the launcher and local UI, adds app/desktop_settings.py, tests and build scripts. It does not replace requirements.txt, app/states/__init__.py or CA/NM extraction/filling modules. Supported states and NM readiness remain exactly as configured in your existing project. The original eCrash destination is retained, including its UAT environment: confirm the approved destination before sharing.

## Test from source first

Use the existing working Windows venv:

```powershell
python -m pip install -r requirements-exe.txt
python -m unittest discover -s tests -p test_desktop_pilot.py -v
python .un_web_ui.py
```

On first launch a native masked API Settings window opens. Enter your own authorized API key and a model ID available to your API project. The existing model default is retained, not independently verified. Saving a key does not test API access or spend credits. Cancel with no saved key exits without opening Chrome.

The launcher no longer loads .env for credentials, even when run from source. A key previously kept in your own .env must be entered once in the native window. Do not share that .env. Other existing test scripts are unchanged.

The API Settings button opens a native dialog, not a webpage password field. Save, Remove or Cancel then ends the current browser session; relaunch to continue. This restart prevents cached AI clients from retaining an old key. Finish work before opening Settings. To exit normally, close all Chrome windows launched by this app.

## Credential storage and limitations

Uses the explicit keyring.backends.Windows.WinVaultKeyring backend. No plaintext fallback. A credential is stored under service KeyForMe.OpenAI / account api-key for the current Windows account. It is not written to JSON, HTML, localStorage or the EXE. Model settings live under %LOCALAPPDATA%/KeyForMe/settings.json.

The key is necessarily accessible in the running Python process and to software with sufficient access to the same Windows account. Credential storage is not a central-server security boundary. Do not use a shared personal API key for distribution. Each recipient uses their own authorized key, API billing and model access. No browser endpoint receives or returns the API key. Chrome is launched without inheriting OPENAI_API_KEY.

The loopback server has request-token, Host and Origin checks. This is a pilot, not an independent security audit. Use only approved report data and approved AI services. Existing extraction modules still determine where report data is sent. Audit the full repository for hardcoded secrets and custom data dependencies before release.

## Build a folder release first

```powershell
.uild_exe.ps1
```

Output: dist/KeyForMe/KeyForMe.exe plus its supporting files. Keep the entire folder together. The build uses the installed working dependencies and adds keyring/PyInstaller. It runs pip check and stops on errors; it does not replace the supplied requirements.txt or upgrade the existing AI/browser libraries.

Google Chrome must already be installed in a location Playwright recognizes. The Playwright driver is collected, but no browser download is requested. If your environment already bundles Playwright browsers, the output can be larger. Enterprise browser policy can block automation; do not bypass company controls.

## Build a single-file release

After the folder release works:

```powershell
.uild_exe.ps1 -OneFile
```

Output: dist/KeyForMe-OneFile.exe. This is a portable executable, not an installer or auto-updater. It still needs installed Chrome, network access, eCrash authorization and an authorized API key. One-file startup extracts runtime files to a temporary directory. User settings stay in LocalAppData and Windows credentials, not that directory.

Build on Windows using the intended Python/CPU architecture. Test on another approved Windows computer without Python installed. Test first-launch setup, second-launch key reuse, change/remove key, missing Chrome, invalid key, offline errors, and an approved end-to-end report. Do not assume the source tests prove frozen Windows execution.

## Distribution

For folder mode, zip only dist/KeyForMe. For one-file mode, send only the tested dist/KeyForMe-OneFile.exe through an approved channel. Do not send the source patch, project folder, .env, reports, mocks, or your credentials as the user release. Do not copy your Windows credential store. Recipients enter their own key on first launch and sign in to eCrash themselves.

Unsigned EXEs may be blocked by Windows or company policy. Arrange IT approval/code signing; do not disable security controls. Review dependency licenses and redistribution requirements before broader release. No Save/Submit behavior or new live NM activation is added.

## Errors

Packaged console output is discarded because existing extractors may print report information. Only timestamp and exception class are appended by the launcher to %LOCALAPPDATA%/KeyForMe/errors.log; no exception messages or tracebacks are saved by this new logger. Existing modules may have their own logging behavior, which must be audited separately. For developer troubleshooting, reproduce from source with approved data. Never paste credentials or full report payloads into support chats.

## Validation performed here

- All patch Python files parsed successfully.
- JavaScript syntax check passed.
- Five offline credential/build-policy unit tests passed with a fake vault.
- Local HTTP smoke checks passed for static assets, request token, Host/Origin restrictions, missing-key guard and settings queue.
- Actual Windows credential storage, native dialog, frozen EXE, Chrome launch and real API extraction have NOT been executed in this environment.

References:
- https://keyring.readthedocs.io/en/latest/
- https://playwright.dev/python/docs/library
- https://playwright.dev/python/docs/browsers
- https://pyinstaller.org/en/stable/runtime-information.html
- https://pyinstaller.org/

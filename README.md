# KeyForMe

Police-report keying assistant for LexisNexis eCrash. It downloads the report PDF from the eCrash viewer,
extracts the fields with an AI model, applies the keying rules for that state, and fills the keying form in
your own Chrome through Playwright. **It never clicks Save or Submit: a person reviews every field.**

Supported states: **CA, NM, NJ, NC, PA** (see `app/browser/state_forms.py`).

## How it works

1. `run_web_ui.py` starts a local control panel (FastAPI) and launches Chrome with a persistent profile.
2. The report PDF is downloaded to a temporary file and the state is detected (PDF text first, header image only if needed).
3. `app/extraction/<state>_extractor.py` reads the pages; `app/keying/<state>_rules.py` turns the raw values into a keying payload.
4. `app/browser/engine.py` fills the form. Each state only supplies a `FormSpec` (`state_forms.py`) and its field mapping;
   things the engine cannot drive (hit and run, charges, trailers) live in `app/browser/<state>_extras.py`.
5. The Report ID hotkeys and Excel widget live in `app/rid_export/`.

## Layout

| Folder | Contents |
| --- | --- |
| `app/ai`, `app/extraction`, `app/keying` | AI providers, per-state extractors, per-state keying rules |
| `app/browser`, `app/core`, `app/states` | shared filling engine, tabs/VIN helpers, per-state pipelines |
| `app/ui`, `app/rid_export`, `app/desktop_settings.py` | control panel, Report ID export, Windows API-key storage |
| `tests` | pytest suites (offline, plus browser tests against the saved mock forms in `mock/`) |
| `tools` | build, requirements, new-state, site switch and diagnostic scripts; `manual_*.py` need real PDFs |
| `docs` | known issues and form captures |

## Everyday commands (PowerShell, project root, venv active)

```powershell
python run_web_ui.py                      # run the app
python -m pytest tests -q                 # all tests
python tools/set_site.py status           # which eCrash site is active (prod | uat)
python tools/build_exe.py --dry-run       # run every build check, build nothing
python tools/build_exe.py                 # build dist\KeyForMe.exe from a clean main
python tools/make_requirements.py         # refresh requirements.txt / requirements-dev.txt
python tools/new_state.py XX              # create a disabled adapter for a new state
python capture_form.py --state XX         # capture a blank keying form into mock/xx/
python -m tools.manual_local_pdf "C:\path\report.pdf" --no-fill     # extraction check on one PDF
```

## Rules to keep

- KEY WHAT YOU SEE: values are keyed as printed; state exceptions come only from that state's guide or SOP.
  The shared prompt text is `app/extraction/prompts.py`.
- Build the EXE only from a clean `main` pointed at **production** (`tools/build_exe.py` refuses UAT).
- Each user enters their own API key on first launch; it is stored in Windows Credential Manager, never in the repo or the EXE.
- Report PDFs, `output/`, `.env` and `.*-backups/` are git-ignored. Mock forms are captures from the live site:
  do not commit a capture that still holds a real report id or token.

# KeyForMe shared-state foundation

This is a source migration kit, not a complete replacement app or compiled EXE.
It extracts common mechanics from CA/NM while preserving state-specific extraction,
models, mappers, field selectors, popup handlers, and the existing desktop launcher.
It does not enable additional states, save forms, or submit forms.

## Install

1. Stop KeyForMe. Commit your current working version and create a feature branch.
2. Extract this ZIP into a separate folder, NOT over your repository.
3. In the KeyForMe PowerShell window with the working virtual environment, run:

```powershell
python "C:\path\to\patch\install_scalability.py" --project-root "C:\Python Projects\KeyForMe"
```

This is a dry run. It validates expected functions and parses all proposed Python
before writing. If a function differs, stop and review the error; do not force it.

Apply after reviewing the file list:

```powershell
python "C:\path\to\patch\install_scalability.py" --project-root "C:\Python Projects\KeyForMe" --apply
cd "C:\Python Projects\KeyForMe"
python -m unittest discover -s tests -p test_shared_core.py -v
python -m compileall -q app capture_form.py extract_report.py
python .\run_web_ui.py
```

No new dependencies are required. Existing dependencies must already work.
The installer preserves the existing CA/NM registry entries, adds a small registry
extension, and backs up changed files under .scalability-backups. Backups are
excluded from Git. Never distribute backups: original project files may contain
sensitive configuration. Keep the current virtual environment and model settings.

## What is shared

- app/core/tabs.py: count, add exactly once, wait for the linked panel, activate by
  position and actual href. No generated ui-id assumptions, forced clicks or
  automatic duplicate Add clicks. NM retains the verified vehicle-section Add
  selector and a 300 ms stabilization period. CA retains its existing Add selector.
- app/core/vin.py: one format decision helper; printed VIN is not corrected.
  NM uses the confirmed nonblocking fast path. CA calls the same helper but
  defaults to conservative popup handling until its invalid-VIN behavior is tested.
  To opt CA in AFTER confirming nonblocking validation, change CA_VIN_POLICY in
  app/browser/playwright_filler.py to VinPolicy(skip_invalid_format=True).
  Future adapters must explicitly choose the verified form behavior.
- app/core/options.py: exact matching with state-owned catalogs; semicolon lists,
  embedded commas preserved, unknown options leave the whole field blank.
  Existing NM_DROPDOWNS values remain untouched; nm_dropdown_value delegates to
  this engine. CA code meanings are NOT copied into NM or future states.
- app/core/registry.py + app/state_plugins.py: explicit, disabled-by-default state
  extensions. Existing CA/NM registrations are retained, not reconstructed.
- capture_form.py: choices come from registered pipelines rather than a fixed pair.
- extract_report.py: additive state-aware CLI. The old main.py remains untouched.
  Report JSON is saved only with an explicit --output path and never overwrites
  an existing file. API calls still use your existing extractors and billing.
- tools/new_state.py: creates a disabled adapter, refusing to overwrite a state.
- tests/test_shared_core.py: 17 offline tests with synthetic data/fake controls.

## What stays state-specific

Each adapter owns its report schema, extraction page plan, prompts, source-to-form
mapping, dropdown catalog, field selectors, person roles, and popup semantics.
Do not put report code meanings into the shared browser layer. Different forms
can share mechanics without sharing meanings or assumptions.

The supplied screenshot shows weather, crash-event, lighting, intersection,
injury, seating, and contributing-factor menus. It is reference evidence only,
not a complete machine-readable catalog. The patch does not infer hidden option
values or missing options from that screenshot. Preserve commas within a label
and distinguish the letter O from zero. Native SELECT controls and autocomplete
textboxes need different interaction adapters; this patch does not assume every
menu is a SELECT or implement unverified autocomplete selection.

## Add a future state

```powershell
python .\tools\new_state.py XX
```

XX is an illustrative placeholder, not a newly supported state.
Implement app/states/xx.py using the existing contract:

```python
def extract(pdf_path, model):
    # State-specific extractor -> state-specific mapper.
    return {"incident": {}, "units": [], "other_parties": [], "notes": []}

def fill(page, payload):
    # State-specific selectors + shared mechanics. Never Save or Submit.
    ...
```

The shown empty payload is a contract illustration, not a usable extractor.
New adapters start with ENABLED = False and raise NotImplementedError until
implemented. Add an explicit import and registration in app/state_plugins.py:

```python
from app.states import xx
PLUGINS = {"XX": xx}
```

Then implement and test the adapter before setting ENABLED = True. Verify that
app/states/detect.py can recognize the new report: this kit does not change its
schema or prompt because its current source was not supplied. Rebuild the EXE
after adding code; this is not a runtime plugin installer for an existing EXE.
Static plugin imports make the new modules visible to the build's import graph,
but actual frozen-build execution still requires Windows validation.

## Regression checklist

- CA and NM: one, two and three vehicle units; verify no cross-unit field writes.
- Missing unit: one click creates one tab; rerun does not add duplicates.
- NM: invalid-format VIN continues immediately; valid-format VIN keeps popup flow.
- CA: valid and invalid VIN; verify any modal before opting into fast rejection.
- Owner and driver remain distinct; CA Other Parties remain in their own section.
- Dropdowns: exact known label/code, embedded comma, multiple values, unknown code.
- Unsupported/uncertain state: nothing filled. Notes/review gates remain unchanged.
- No Save/Submit; compare all fields with an approved report before saving manually.
- Desktop: first launch, session key, stored key, changed/removed key, frozen EXE.

## Scope and known limitations

This is an incremental foundation, not a completed universal form engine.
The supplied root scripts contain historical CA-only entrypoints and mock routing.
This kit does not rewrite run_browser.py's root mock/index.html routing or remove
backup/recording scripts. Use state-specific mocks when testing and do not assume
that root mock mode automatically chooses the detected state's form.
The legacy main.py remains CA-only; use extract_report.py for state-aware CLI work.
Extraction prompts/page selection are unchanged, including NM's current fixed
four-page extraction plan. Supporting arbitrary NM layouts is a separate task.

The desktop launcher, credential storage, UI assets, packaging scripts and raw
recordings are not overwritten. Existing diagnostic logs and Chrome environment
inheritance are also unchanged; review them before distributing an EXE.
The actual state registry, detector, CA mapper and build scripts were not in this
upload. The installer patches the real registry on your machine only after
preflight; the isolated validation fixture used a minimal registry stub.
No live eCrash, API, Windows credential or EXE testing was performed here.

## Roll back

The installer prints its backup folder. Review a rollback before applying:

```powershell
python "C:\path\to\patch\rollback_scalability.py" --project-root "C:\Python Projects\KeyForMe" --backup "C:\Python Projects\KeyForMe\.scalability-backups\TIMESTAMP"
```

Add --apply only when ready. Rollback restores changed files and removes newly
added files from that migration, overwriting later edits to those files. Commit
later work before rolling back. Keep the migration ZIP outside the repository.

## Why this structure

Fix browser mechanics once, preserve report-specific rules, and require a tested
adapter for each new state. This reduces repeated selector/VIN fixes without
pretending that a new state is supported just because a module exists.

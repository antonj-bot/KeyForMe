# California CHP 555 Field Extractor

Extracts structured fields from CHP 555 police reports. It deliberately processes only pages 1 and 2 and does not send narrative or sketch pages to the model.

## Setup (PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install chromium
Copy-Item .env.example .env
```

Add your API key to `.env`, then run:

```powershell
python main.py "C:\path\to\3 veh.pdf"
```

The validated result is written to `output/extracted.json`. No webpage is submitted.

## CA keying output

The run also creates `output/ca_keying_payload.json`, which applies the agreed CA keying rules. Browser selectors in `app/browser/field_mapping.py` are placeholders until copied from the real webpage DOM. The filler never submits the form.

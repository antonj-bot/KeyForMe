# New Mexico SH 10074 — extraction starter

**This is intentionally not registered in `PIPELINES` yet.** The NM browser form differs from CA and should not be filled until a local mock test passes.

## Files

- `app/models/nm_models.py` — structured NM fields
- `app/extraction/nm_extractor.py` — extracts the first three pages concurrently and merges Unit 2 across pages
- `app/keying/nm_mapper.py` — NM payload, including **Owner Phone**
- `app/states/nm.py` — extraction entrypoint; `fill()` intentionally disabled
- `tests/test_nm_mapping.py` — cross-page merge and owner-phone regression tests

## Install

Unzip into your KeyForMe project on `feature/nm-support`.

```powershell
python -m compileall -q app
python -m pytest -q tests/test_nm_mapping.py
```

## Test extraction without filling eCrash

```powershell
@'
from pathlib import Path
from dotenv import load_dotenv
from app.states.nm import extract
import os
load_dotenv()
p = extract(Path(r"report-1335078161.pdf"), os.getenv("OPENAI_MODEL", "gpt-6-luna"))
print("Units:", len(p["units"]))
print("Unit 1 owner phone:", p["units"][0]["owner"]["home_phone"])
print("Unit 2 owner phone:", p["units"][1]["owner"]["home_phone"])
print("Warnings:", p["notes"])
'@ | python -
```

Do not paste the complete payload into public chats: it contains personal information.

## Next integration milestone

1. Capture a **blank NM mock** with at least two units and one Other Party.
2. Build `nm_field_mapping.py` and `nm_filler.py` from the sanitized Codegen recording and the mock DOM.
3. Confirm exact dropdown options for NM (weather, crash type, injury, alcohol/drug use, vehicle condition). Do not reuse CA code-letter mappings without validation.
4. Test full extraction → mapping → mock filling with the NM PDF.
5. Only then enable NM in `app/states/__init__.py` and the web UI.

This package adds files only; it does not replace CA code.

import base64
from pathlib import Path
from openai import OpenAI
from app.models import CaliforniaCHP555

SYSTEM_PROMPT = """You extract only labeled fields and marked selections from California CHP 555 forms.
Use page 1 for crash, driver, vehicle, owner, insurance, damage, and disposition fields.
Use page 2 for coding fields and party-specific coded selections.
Never read or use narratives, statements, summaries, sketches, diagrams, maps, or prose to resolve a field.
Never infer missing text. Return null when a field is blank, obscured, ambiguous, or cannot be assigned to a party.
For checkboxes, true or a code requires a visible mark. An unclear mark is null.
Keep each repeated party block separate. Preserve identifiers exactly, including leading zeros.
Dates: normalize complete dates to YYYY-MM-DD. Times: normalize four-digit times to HH:MM.
For every field, provide page, printed label, raw value, and confidence.
Add a warning for every ambiguous party association or low-confidence identifier.
"""

def _data_url(path: Path) -> str:
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"

def extract_chp555(page_paths: list[Path], model: str) -> CaliforniaCHP555:
    client = OpenAI()
    content = [{"type": "input_text", "text": "Extract structured fields from these two CHP 555 field pages only."}]
    for path in page_paths:
        content.append({"type": "input_image", "image_url": _data_url(path), "detail": "high"})
    response = client.responses.parse(
        model=model,
        input=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ],
        text_format=CaliforniaCHP555,
    )
    if response.output_parsed is None:
        raise RuntimeError("Model returned no parsed extraction")
    return response.output_parsed

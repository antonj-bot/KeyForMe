import json
import os
import shutil
import sys
from pathlib import Path
from dotenv import load_dotenv
from app.extraction.pdf_pages import render_field_pages
from app.extraction.openai_extractor import extract_chp555
from app.validation.rules import validate
from app.keying.ca_mapper import map_ca_keying

def main() -> None:
    load_dotenv()
    if len(sys.argv) != 2:
        raise SystemExit('Usage: python main.py "path\to\report.pdf"')
    pdf_path = Path(sys.argv[1]).expanduser().resolve()
    if not pdf_path.exists():
        raise FileNotFoundError(pdf_path)
    temp_dir = Path("temp")
    output_dir = Path("output")
    try:
        pages = render_field_pages(pdf_path, temp_dir)
        result = extract_chp555(pages, os.getenv("OPENAI_MODEL", "gpt-4.1"))
        payload = result.model_dump()
        payload["warnings"] = validate(result)
        output_dir.mkdir(exist_ok=True)
        target = output_dir / "extracted.json"
        target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        keying_target = output_dir / "ca_keying_payload.json"
        keying_target.write_text(json.dumps(map_ca_keying(result), indent=2), encoding="utf-8")
        print(f"Extraction written to {target.resolve()}")
        print(f"Keying payload written to {keying_target.resolve()}")
        print(f"Parties found: {len(result.parties)}")
        print(f"Warnings: {len(payload['warnings'])}")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

if __name__ == "__main__":
    main()

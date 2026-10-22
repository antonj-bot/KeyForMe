"""State-aware CLI. Writes report data only when --output is explicitly supplied."""
import argparse
import json
from pathlib import Path

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--model")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    path = args.pdf.expanduser().resolve()
    if not path.is_file():
        parser.error("PDF file not found.")
    from app import desktop_settings as settings
    if not settings.sync_environment():
        parser.error("Set a session API key or configure desktop settings.")
    from app.states import PIPELINES
    from app.states.detect import detect_state
    model = args.model or settings.read_model()
    found = detect_state(path,model)
    state = (found.state or "").strip().upper()
    pipeline = PIPELINES.get(state)
    if pipeline is None:
        parser.error("Detected state is unsupported or uncertain.")
    payload = pipeline.extract(path,model)
    print(f"State: {state}; units: {len(payload.get('units',[]))}; notes: {len(payload.get('notes',[]))}")
    if args.output:
        with args.output.open("x",encoding="utf-8") as handle:
            json.dump(payload,handle,indent=2,ensure_ascii=False)
        print("Mapped payload saved to the requested output file. Treat it as report data.")
    print("No form was filled, saved or submitted.")

if __name__ == "__main__":
    main()

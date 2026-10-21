from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MOCK = PROJECT_ROOT / "mock"
MOCK.mkdir(parents=True, exist_ok=True)

lt, gt = chr(60), chr(62)  # the < and > characters

frame = (
    f"{lt}iframe id='formIframe' src='ca_form.html' "
    f"style='width:100%;height:100vh;border:0'{gt}{lt}/iframe{gt}"
)

index = MOCK / "index.html"
index.write_text(frame, encoding="utf-8")
print(f"Written: {index}")

form = MOCK / "ca_form.html"
if form.exists():
    print(f"Found:   {form}")
else:
    print(f"MISSING: {form}")
    print("Run capture_form.py again. It saved the form somewhere else.")
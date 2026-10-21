from pathlib import Path

ROOT = Path(__file__).resolve().parent
MOCK = ROOT / "mock"
MOCK.mkdir(parents=True, exist_ok=True)

lt, gt = chr(60), chr(62)
iframe = (
    f'{lt}iframe id="formIframe" src="ca_form.html" '
    f'style="width:100%;height:100vh;border:0;display:block"{gt}'
    f'{lt}/iframe{gt}'
)
html = (
    "<!DOCTYPE html>\n"
    '<html lang="en"><head><meta charset="UTF-8">'
    '<meta name="viewport" content="width=device-width,initial-scale=1">'
    '<title>KeyForMe CA Mock Form</title>'
    '<style>html,body{width:100%;height:100%;margin:0;overflow:hidden}</style>'
    f"</head><body>{iframe}</body></html>"
)

path = MOCK / "index.html"
path.write_text(html, encoding="utf-8")
print(f"Repaired: {path}")
print(f"Size: {path.stat().st_size} bytes")
print(f"Captured form exists: {(MOCK / 'ca_form.html').exists()}")

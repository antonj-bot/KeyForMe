import re
import sys
from pathlib import Path

src = Path(sys.argv[1])
out = src.with_name(src.stem + "_clean.txt")

kept, dropped = [], 0
for line in src.read_text(encoding="utf-8").splitlines():
    low = line.lower()
    # Login lines live outside the form iframe; drop them and any credential text.
    if ("password" in low or "username" in low or "login" in low
            or ("fill(" in line and "formIframe" not in line)):
        dropped += 1
        continue
    # Replace every typed value with TEXT. Selectors and dropdown picks stay.
    line = re.sub(r'\.fill\((["\']).*?\1\)', '.fill("TEXT")', line)
    line = re.sub(r'\.press_sequentially\((["\']).*?\1', '.press_sequentially("TEXT"', line)
    kept.append(line)

out.write_text("\n".join(kept), encoding="utf-8")
print(f"Saved {out.name} | removed {dropped} login/outside-form lines")
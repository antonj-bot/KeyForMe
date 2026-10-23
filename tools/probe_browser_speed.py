"""How fast is YOUR browser on the NJ test form?  (about 30 seconds, nothing is changed or saved)

Run from the project root:
    python tools/probe_browser_speed.py

It opens mock/nj/index.html in Chrome (channel="chrome", the one KeyForMe uses) and, if installed, in
Playwright's own Chromium, then times the same few actions on the full capture (about 1300 fields) and on
a trimmed page (about 400 fields, like a real report). A healthy browser finishes each row in well under
a second. Send the printed table if tests or filling feel slow.
"""
from __future__ import annotations

import functools
import http.server
import os
import platform
import sys
import threading
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
MOCK = ROOT / "mock" / "nj"

TRIM_JS = """(cfg) => {
  const trim = (id, keep) => {
    const s = document.getElementById(id); if (!s) return 0;
    const anchors = Array.from(s.querySelectorAll('ul.ui-tabs-nav > li > a.ui-tabs-anchor'));
    anchors.slice(keep).forEach(a => {
      const pid = a.getAttribute('href').slice(1);
      const panel = Array.from(s.querySelectorAll('[role="tabpanel"]')).find(p => p.id === pid);
      if (panel) panel.remove();
      a.closest('li').remove();
    });
    return anchors.length;
  };
  return [trim('section-page-base-owner-02', cfg.units), trim('section-page-base-passenger-03', cfg.others)];
}"""
TAB_FIX = """() => { document.addEventListener('click', e => {
  const a = e.target.closest('a.ui-tabs-anchor'); if (!a) return; const li = a.closest('li');
  li.parentElement.querySelectorAll('li').forEach(x => x.setAttribute('aria-selected', x === li ? 'true' : 'false'));
}, true); }"""

SLOW = 3.0        # seconds: a row slower than this is flagged


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def timed(fn):
    start = time.perf_counter()
    try:
        fn()
        return time.perf_counter() - start, ""
    except Exception as error:                      # report, never crash the probe
        return time.perf_counter() - start, type(error).__name__


def measure(browser, url, trim: bool):
    rows = []
    page = browser.new_page()
    page.set_default_timeout(15_000)
    seconds, err = timed(lambda: page.goto(url))
    rows.append(("open the form", seconds, err))
    page.wait_for_timeout(300)
    inner = page.frames[1]
    if trim:
        inner.evaluate(TRIM_JS, {"units": 4, "others": 4})
    inner.evaluate(TAB_FIX)
    fields = inner.evaluate("document.querySelectorAll('input,textarea,select').length")
    section = page.frame_locator("#formIframe").locator("#section-page-base-owner-02")
    anchor = section.locator("li[role='tab'] > a.ui-tabs-anchor[role='presentation']").nth(0)
    rows.append(("open unit tab 1", *timed(lambda: anchor.click())))
    field = section.locator("[id^='Vehicle_DamagedAreas-']:visible").first
    rows.append(("click Impact Location", *timed(lambda: field.click())))
    rows.append(("type 'Rear' (4 keys)", *timed(lambda: field.press_sequentially("Rear", delay=20))))
    rows.append(("press Tab", *timed(lambda: field.press("Tab"))))
    rows.append(("fill 10 other fields", *timed(lambda: [
        section.locator("[id^='Person_FirstName-']:visible").first.fill(f"NAME{n}") for n in range(10)])))
    page.close()
    return fields, rows


def run(label, launcher):
    print(f"\n=== {label}")
    started = time.perf_counter()
    try:
        browser = launcher()
    except Exception as error:
        print(f"    not available: {type(error).__name__}")
        return
    print(f"    started in {time.perf_counter() - started:.1f}s, version {browser.version}")
    handler = functools.partial(Quiet, directory=str(MOCK))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}/index.html"
    try:
        for name, trim in (("full capture", False), ("trimmed page", True)):
            fields, rows = measure(browser, url, trim)
            print(f"  -- {name} ({fields} fields)")
            for action, seconds, err in rows:
                flag = "  <-- SLOW" if seconds > SLOW else ""
                note = f"  [{err}]" if err else ""
                print(f"     {action:24s} {seconds:6.2f}s{note}{flag}")
    finally:
        browser.close()
        server.shutdown()
        server.server_close()


def main():
    if not (MOCK / "index.html").exists():
        sys.exit(f"Not found: {MOCK / 'index.html'}  (run from the KeyForMe project root)")
    from importlib import metadata
    try:
        version = metadata.version("playwright")
    except metadata.PackageNotFoundError:
        version = "?"
    print(f"Python {platform.python_version()} | Playwright {version} | {platform.platform()}")
    exe = os.environ.get("KEYFORME_TEST_CHROMIUM")
    with sync_playwright() as p:
        if exe:
            run(f"browser at KEYFORME_TEST_CHROMIUM", lambda: p.chromium.launch(executable_path=exe))
        else:
            run('Chrome (channel="chrome"), headless', lambda: p.chromium.launch(channel="chrome"))
            run('Chrome (channel="chrome"), visible window', lambda: p.chromium.launch(channel="chrome", headless=False))
            run("Playwright's own Chromium, headless", lambda: p.chromium.launch())
    print("\nDone. Nothing was saved or changed.")


if __name__ == "__main__":
    main()

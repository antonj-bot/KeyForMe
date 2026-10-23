"""Finds WHY typing into the Impact Location test field is slow on this machine (about 1 minute).

Run from the KeyForMe project root (nothing is saved or changed):
    python tools\\diagnose_impact_location.py

Background: tools/probe_browser_speed.py showed Chrome is fast on the plain NJ form, yet the browser tests
that add the imitation suggestion list ("fake list") take 7-10 s per test and two time out. This script
repeats the exact steps of those tests - click, type R-e-a-r key by key, press Tab - on the same trimmed
page, once per VARIANT of the fake list, and times every key. Whichever variant is fast names the cause.

It uses the fake list from tests/test_nj_form.py, so it needs that file (v6) and mock/nj/.
"""
from __future__ import annotations

import importlib.util
import platform
import sys
import threading
import time
from importlib import metadata
from pathlib import Path

ROOT = Path.cwd()
MOCK = ROOT / "mock" / "nj"
TEST_FILE = ROOT / "tests" / "test_nj_form.py"
SLOW_TOTAL_S = 1.5          # typing + Tab slower than this counts as slow
STEP_TIMEOUT_MS = 6000

STALL_JS = """() => {
  window.__maxGap = 0; let last = performance.now();
  window.__stall = setInterval(() => { const now = performance.now(); window.__maxGap = Math.max(window.__maxGap, now - last - 10); last = now; }, 10);
}"""
RESET_STALL_JS = "() => { window.__maxGap = 0; }"
READ_STALL_JS = "() => window.__maxGap"
NO_LIST_JS = """() => { window.__events = 0;
  document.querySelectorAll("[id^='Vehicle_DamagedAreas-']").forEach(el => el.addEventListener('input', () => { window.__events++; })); }"""


def load_tests():
    if not TEST_FILE.is_file() or not (MOCK / "index.html").is_file():
        sys.exit("Run this from the KeyForMe project root (needs tests\\test_nj_form.py and mock\\nj\\).")
    sys.path.insert(0, str(ROOT))
    spec = importlib.util.spec_from_file_location("kfm_nj_form_tests", TEST_FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for name in ("FAKE_SUGGEST", "TRIM_JS", "TAB_FIX", "OPTIONS", "QuietHandler"):
        if not hasattr(module, name):
            sys.exit(f"tests\\test_nj_form.py has no {name}: install install_nj_v6.py first.")
    return module


def variants(T):
    base = T.FAKE_SUGGEST
    layout = ("const r = el.getBoundingClientRect(); menu.style.left = r.left + 'px'; "
              "menu.style.top = (r.bottom + window.scrollY) + 'px';")
    show = "menu.style.display = shown.length ? 'block' : 'none';"
    out = [("A  no fake list (plain page)", None, None)]
    out.append(("B  fake list as in the tests", base, "standard"))
    if layout in base:
        out.append(("C  fake list, no position/layout reads", base.replace(layout, ""), "standard"))
    if show in base:
        out.append(("D  fake list, menu never shown", base.replace(show, "menu.style.display = 'none';"), "standard"))
    out.append(("E  fake list, odd markup (test 2)", base, "odd"))
    return out


def open_page(browser, url, T):
    page = browser.new_page()
    page.set_default_timeout(STEP_TIMEOUT_MS)
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(f"pageerror: {str(e)[:100]}"))
    page.on("console", lambda m: errors.append(f"console.{m.type}: {m.text[:100]}") if m.type in ("error", "warning") and "404" not in m.text else None)
    page.goto(url)
    page.wait_for_timeout(300)
    inner = page.frames[1]
    inner.evaluate(T.TRIM_JS, {"units": 4, "others": 4})
    inner.evaluate(T.TAB_FIX)
    section = page.frame_locator("#formIframe").locator("#section-page-base-owner-02")
    anchor = section.locator("li[role='tab'] > a.ui-tabs-anchor[role='presentation']").nth(0)
    href = anchor.get_attribute("href").lstrip("#")
    anchor.click()
    section.locator(f'[id="{href}"]').wait_for(state="visible")
    return page, inner, section.locator(f'[id="{href}"]').locator("[id^='Vehicle_DamagedAreas-']:visible").first, errors


def timed(fn):
    start = time.perf_counter()
    try:
        fn()
        return time.perf_counter() - start, ""
    except Exception as error:
        return time.perf_counter() - start, type(error).__name__


def run_variant(browser, url, T, label, script, mode):
    page, inner, field, errors = open_page(browser, url, T)
    result = {"label": label, "keys": [], "errors": errors}
    try:
        if script is not None:
            inner.evaluate(script, {"options": T.OPTIONS, "mode": mode})
        elif label.startswith("A"):
            inner.evaluate(NO_LIST_JS)
        inner.evaluate(STALL_JS)
        inner.evaluate(RESET_STALL_JS)
        result["click"] = timed(lambda: field.click())
        for ch in "Rear":
            result["keys"].append((ch, *timed(lambda c=ch: field.press(c))))
        result["tab"] = timed(lambda: field.press("Tab"))
        page.wait_for_timeout(150)
        try:
            result["value"] = field.input_value(timeout=2000)
        except Exception as error:
            result["value"] = f"<{type(error).__name__}>"
        try:
            result["stall"] = float(inner.evaluate(READ_STALL_JS)) / 1000.0
        except Exception:
            result["stall"] = None
    finally:
        try:
            page.close()
        except Exception:
            pass
    return result


def total(result):
    seconds = result["click"][0] + sum(k[1] for k in result["keys"]) + result["tab"][0]
    return seconds


def show(result):
    keys = " ".join(f"{ch}={sec:.2f}" + (f"[{err}]" if err else "") for ch, sec, err in result["keys"])
    stall = f"{result['stall']:.2f}s" if result.get("stall") is not None else "n/a"
    flag = "  <-- SLOW" if total(result) > SLOW_TOTAL_S else ""
    print(f"  {result['label']}")
    print(f"      click {result['click'][0]:.2f}s | keys {keys} | Tab {result['tab'][0]:.2f}s | total {total(result):.2f}s{flag}")
    print(f"      value {result.get('value')!r} | longest page stall {stall}")
    for error in result["errors"][:3]:
        print(f"      {error}")


def explain(results):
    by = {r["label"][0]: r for r in results}
    if not all(k in by for k in "AB"):
        return
    slow = lambda key: key in by and total(by[key]) > SLOW_TOTAL_S
    print("\nReading the result:")
    if not slow("B"):
        print("  The fake list was NOT slow in this run. If the tests still time out, run the tests alone and send")
        print("  me both outputs; the cause is then in how the tests run, not in the page.")
    elif not slow("A"):
        causes = []
        if "C" in by and not slow("C"):
            causes.append("positioning the menu (layout reads) on every key press")
        if "D" in by and not slow("D"):
            causes.append("showing the menu on screen")
        print("  Typing is fast on the plain page but slow with the fake list, so the problem is in the fake list.")
        if causes:
            print("  Removing this made it fast: " + "; ".join(causes) + ".")
        else:
            print("  Even without positioning and without showing the menu it stays slow: the cost is in the")
            print("  list's input handler itself.")
    else:
        print("  Typing is slow even on the plain page here, which the probe did not show. Close other Chrome")
        print("  windows and run it again; if it stays slow the browser, not the test, is the problem.")


def main():
    T = load_tests()
    from playwright.sync_api import sync_playwright
    import functools
    import http.server

    try:
        version = metadata.version("playwright")
    except metadata.PackageNotFoundError:
        version = "?"
    print(f"Python {platform.python_version()} | Playwright {version} | {platform.platform()}")
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(T.QuietHandler, directory=str(MOCK)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}/index.html"
    plans = [("Chrome (channel=chrome), headless  <- how the tests run", lambda p: p.chromium.launch(channel="chrome"), variants(T)),
             ("Chrome (channel=chrome), visible window", lambda p: p.chromium.launch(channel="chrome", headless=False), variants(T)[:2]),
             ("Playwright's own Chromium, headless", lambda p: p.chromium.launch(), variants(T)[:2])]
    headless_results = []
    with sync_playwright() as p:
        for title, launcher, plan in plans:
            print(f"\n=== {title}")
            try:
                browser = launcher(p)
            except Exception as error:
                print(f"    not available: {type(error).__name__}")
                continue
            print(f"    version {browser.version}")
            try:
                for label, script, mode in plan:
                    try:
                        result = run_variant(browser, url, T, label, script, mode)
                    except Exception as error:
                        print(f"  {label}\n      could not run: {type(error).__name__}: {str(error)[:120]}")
                        continue
                    show(result)
                    if title.startswith("Chrome (channel=chrome), headless"):
                        headless_results.append(result)
            finally:
                browser.close()
    server.shutdown()
    server.server_close()
    explain(headless_results)
    print("\nDone. Nothing was saved or changed. Please send me everything above.")


if __name__ == "__main__":
    main()

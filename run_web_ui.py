"""KeyForMe local web UI launcher. Run from the KeyForMe project root.

FastAPI serves the control page on a background thread; all synchronous
Playwright actions run in this main thread to avoid cross-thread API calls.
"""
from __future__ import annotations

import os
import socket
import sys
import threading
import time
from contextlib import ExitStack
from pathlib import Path
from queue import Empty
from playwright.sync_api import Error as PlaywrightError
import uvicorn
from playwright.sync_api import sync_playwright


from app.browser.pdf_downloader import download_report_pdf_temporarily
from app.ui import server as ui
from app import desktop_settings as settings
import time

KEYING_URL = "https://azkeying.ecrash.lexisnexisrisk.com/ecrash/"
DOWNLOAD_SELECTOR = "#download"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def find_work_item(context):
    """Return the page containing the PDF viewer, not the control page."""
    for page in reversed(context.pages):
        if page.is_closed():
            continue
        for frame in page.frames:
            if "image-viewer-pdf" in frame.url:
                return page
    return None


def find_keying_form(context):
    for page in reversed(context.pages):
        if page.is_closed() or page.url == "about:blank":
            continue
        try:
            field = page.frame_locator("#formIframe").locator("#Incident_CaseIdentifier")
            if field.count() and field.is_visible():
                return page
        except Exception:
            continue
    return None


def wait_for_keying_form(context, timeout_s=90):
    deadline = time.monotonic() + timeout_s
    announced = False
    while time.monotonic() < deadline:
        page = find_keying_form(context)
        if page is not None:
            return page
        if not announced:
            ui.log("Open the blank keying form in eCrash; waiting for it…")
            announced = True
        # Pump Playwright events so newly opened popups can finish loading.
        live = [p for p in context.pages if not p.is_closed()]
        if live:
            live[0].wait_for_timeout(250)
    return None

from contextlib import contextmanager


@contextmanager
def timed_step(label: str):
    start = time.perf_counter()

    try:
        yield
    finally:
        elapsed = time.perf_counter() - start
        ui.log(f"{label}: {elapsed:.2f}s")


# ---------------- downloads ----------------
# KeyForMe's own PDF download (for extraction) stays temporary. A download the
# user starts by hand is saved to the normal Windows Downloads folder.
_automated_downloads = 0


@contextmanager
def automated_download_guard():
    global _automated_downloads
    _automated_downloads += 1
    try:
        yield
    finally:
        _automated_downloads -= 1


@contextmanager
def automated_pdf_download(context, selector):
    """Temporary PDF for extraction; downloads started inside it are not kept."""
    with ExitStack() as stack:
        with automated_download_guard():
            pdf_path = stack.enter_context(
                download_report_pdf_temporarily(context, selector)
            )
        yield pdf_path


def downloads_dir() -> Path:
    """The user's real Downloads folder (honors Windows folder redirection)."""
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            class GUID(ctypes.Structure):
                _fields_ = [
                    ("Data1", wintypes.DWORD),
                    ("Data2", wintypes.WORD),
                    ("Data3", wintypes.WORD),
                    ("Data4", ctypes.c_ubyte * 8),
                ]

            folder_id = GUID(
                0x374DE290, 0x123F, 0x4565,
                (ctypes.c_ubyte * 8)(0x91, 0x64, 0x39, 0xC4, 0x92, 0x5E, 0x46, 0x7D),
            )
            raw = ctypes.c_wchar_p()
            result = ctypes.windll.shell32.SHGetKnownFolderPath(
                ctypes.byref(folder_id), 0, None, ctypes.byref(raw)
            )
            if result == 0 and raw.value:
                path = Path(raw.value)
                ctypes.windll.ole32.CoTaskMemFree(raw)
                return path
        except Exception:
            pass
    return Path.home() / "Downloads"


def unique_path(folder: Path, filename: str) -> Path:
    """Chrome-style collision handling: name.pdf, name (1).pdf, name (2).pdf."""
    name = Path(filename).name or "download"
    target = folder / name
    stem, suffix, counter = target.stem, target.suffix, 1
    while target.exists():
        target = folder / f"{stem} ({counter}){suffix}"
        counter += 1
    return target


def save_manual_download(download) -> None:
    if _automated_downloads:
        return  # KeyForMe's own temporary PDF download
    try:
        folder = downloads_dir()
        folder.mkdir(parents=True, exist_ok=True)
        download.save_as(str(unique_path(folder, download.suggested_filename)))
        # Remove Playwright's temporary copy right away.
        try:
            download.delete()
        except Exception:
            pass
        ui.log("Download saved to your Downloads folder", "success")
    except Exception as error:
        ui.log(f"Could not save the download ({type(error).__name__})", "warning")


def watch_manual_downloads(context) -> None:
    """Attach the manual-download handler to every current and future page."""
    seen = set()

    def attach(page) -> None:
        if id(page) in seen:
            return
        seen.add(id(page))
        page.on("download", save_manual_download)

    context.on("page", attach)
    for page in context.pages:
        attach(page)


def process_one(context, model: str):
    from app.states import PIPELINES
    from app.states.detect import detect_state
    total_start = time.perf_counter()

    try:
        ui.update(
            status="Checking report",
            report_type="—",
            units=None,
            warnings=0,
        )

        # 1. Check work item
        work = find_work_item(context)

        if work is None:
            ui.log(
                "No report viewer found. Open an eCrash work item first.",
                "warning",
            )
            ui.update(status="Open a work item")
            return

        # 2. Download PDF
        ui.update(status="Downloading PDF")
        ui.log("Downloading report to temporary storage...")

        download_start = time.perf_counter()

        with automated_pdf_download(
            context,
            DOWNLOAD_SELECTOR,
        ) as pdf_path:

            download_elapsed = time.perf_counter() - download_start

            ui.log(
                f"PDF download: {download_elapsed:.2f}s",
                "success",
            )

            # 3. Detect state
            ui.update(status="Detecting state")
            ui.log("Detecting report state...")

            detection_start = time.perf_counter()

            found = detect_state(pdf_path, model)

            detection_elapsed = time.perf_counter() - detection_start

            ui.log(
                f"State detection: {detection_elapsed:.2f}s"
            )

            state = (found.state or "").strip().upper()

            ui.log(
                f"Detected state: {state or 'Unknown'}; "
                f"enabled states: {', '.join(sorted(PIPELINES)) or 'None'}"
            )

            pipeline = PIPELINES.get(state)

            if pipeline is None:
                ui.log(
                    "Report state is unsupported or uncertain; "
                    "nothing was filled.",
                    "warning",
                )

                ui.update(
                    status="Unsupported report",
                    report_type=state or "Unknown",
                )
                return

            ui.update(
                status="Extracting",
                report_type=f"{state} • {found.form_name or 'Report'}",
            )

            ui.log(
                f"State detected: {state}",
                "success",
            )

            # 4. AI extraction
            ui.log(f"Extracting with {model}...")

            extraction_start = time.perf_counter()

            payload = pipeline.extract(pdf_path, model)

            extraction_elapsed = (
                time.perf_counter() - extraction_start
            )

            units = len(payload.get("units", []))
            warnings = len(payload.get("notes", []))

            ui.update(
                units=units,
                warnings=warnings,
            )

            ui.log(
                f"AI extraction: {extraction_elapsed:.2f}s",
                "success",
            )

            ui.log(
                f"Vehicle units detected: {units}"
            )

        # PDF is automatically deleted here.
        ui.log("Temporary PDF removed")

        # 5. Check extracted units
        if not units:
            ui.update(status="Review required")

            ui.log(
                "No vehicle units extracted; nothing was filled.",
                "warning",
            )
            return

        # 6. Wait for keying form
        ui.update(status="Waiting for form")
        ui.log("Looking for the keying form...")

        form_wait_start = time.perf_counter()

        form_page = wait_for_keying_form(context)

        form_wait_elapsed = (
            time.perf_counter() - form_wait_start
        )

        ui.log(
            f"Form wait: {form_wait_elapsed:.2f}s"
        )

        if form_page is None:
            ui.log(
                "Keying form not found; nothing was filled.",
                "warning",
            )

            ui.update(status="Form not found")
            return

        ui.log("Keying form detected", "success")

        # 7. Fill form
        ui.update(status="Filling form")
        ui.log("Filling keying form...")

        filling_start = time.perf_counter()

        pipeline.fill(form_page, payload)

        filling_elapsed = (
            time.perf_counter() - filling_start
        )

        ui.log(
            f"Form filling: {filling_elapsed:.2f}s",
            "success",
        )

        # 8. Completion
        ui.update(status="Review required")

        ui.log(
            "Fields filled. Review against the PDF; "
            "no Save or Submit was clicked.",
            "success",
        )

        if warnings:
            ui.log(
                f"{warnings} mapping note(s) require review.",
                "warning",
            )

    finally:
        # Always record total time, even if processing fails.
        total_elapsed = time.perf_counter() - total_start

        ui.log(
            f"Total processing time: {total_elapsed:.2f}s"
        )

def main():
    ready = settings.sync_environment()
    if not ready:
        ready = settings.show_settings()
    if not ready:
        return
    from app.ai.runtime import configure_ai
    provider = settings.read_provider()
    configure_ai(provider)
    model = settings.read_model()
    ui.update(key_configured=True)
    port = free_port()
    url = f"http://127.0.0.1:{port}/"
    config = uvicorn.Config(ui.app, host="127.0.0.1", port=port, log_level="warning", access_log=False, log_config=None, loop="asyncio", http="h11", ws="none")
    server = uvicorn.Server(config)
    threading.Thread(target=server.run, daemon=True, name="KeyForMe-UI").start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(.05)
    if not server.started:
        raise RuntimeError("Could not start the local web interface")

    ui.log("Application ready. Open an eCrash work item in Chrome.")
    print(f"KeyForMe control panel: {url}")
    print("Close Chrome or press Ctrl+C to stop.")
    try:
        profile_dir = settings.data_dir() / "ChromeProfile"
        profile_dir.mkdir(parents=True, exist_ok=True)
        ui.log("Using the dedicated persistent KeyForMe Chrome profile")
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir),
                channel="chrome",
                headless=False,
                chromium_sandbox=True,
                accept_downloads=True,
                no_viewport=True,
                env=os.environ.copy(),
                # Playwright adds --disable-extensions by default; remove it so
                # extensions installed in this profile load and persist.
                ignore_default_args=["--disable-extensions"],
            )
            watch_manual_downloads(context)
            dashboard = context.pages[0] if context.pages else context.new_page()
            dashboard.goto(KEYING_URL, wait_until="domcontentloaded")
            control = context.new_page()
            control.goto(url, wait_until="domcontentloaded")
            ui.update(status="Ready")
            while any(not p.is_closed() for p in context.pages):
                try:
                    command = ui.commands.get_nowait()
                except Empty:
                    live = [
                        p for p in context.pages
                        if not p.is_closed()
                    ]

                    if not live:
                        break

                    try:
                        live[0].wait_for_timeout(200)
                    except PlaywrightError:
                        # A page can close between the check and the wait.
                        remaining = [
                            p for p in context.pages
                            if not p.is_closed()
                        ]

                        if not remaining:
                            break

                        # Another tab remains open; keep the session running.
                        if live[0].is_closed():
                            continue

                        # Do not hide an unrelated Playwright failure.
                        raise

                    continue
                if command == "settings":
                    try:
                        settings.show_settings()
                        # Restart ensures extractors with cached clients cannot
                        # keep using an old key after replacement or deletion.
                        import tkinter as tk
                        from tkinter import messagebox
                        root = tk.Tk()
                        root.withdraw()
                        messagebox.showinfo("KeyForMe", "Settings closed. KeyForMe will now exit. Double-click KeyForMe again to continue with the saved settings.")
                        root.destroy()
                    finally:
                        try:
                            context.close()
                        except PlaywrightError as error:
                            if type(error).__name__ != "TargetClosedError":
                                raise
                    break
                if command != "extract":
                    continue
                if not settings.sync_environment():
                    ui.update(busy=False, key_configured=False, status="API key required")
                    continue
                try:
                    process_one(context, model)
                except Exception as error:
                    # Do not put exception strings in the UI: they may contain
                    # internal URLs or report information.
                    record_error(error)
                    ui.update(status="Error")
                    ui.log(
                        f"Processing stopped ({type(error).__name__}): {error}",
                        "warning",
                    )
                    import traceback
                    traceback.print_exc()
                finally:
                    ui.update(busy=False)
            try:
                context.close()
            except PlaywrightError as error:
                # Closing an already-closed browser is normal during cleanup.
                if type(error).__name__ != "TargetClosedError":
                    raise   
    except KeyboardInterrupt:
        pass
    finally:
        server.should_exit = True


def record_error(error):
    # Type only: exception strings/tracebacks may contain report data or URLs.
    from datetime import datetime
    with (settings.data_dir() / "errors.log").open("a", encoding="utf-8") as log_file:
        log_file.write(f"{datetime.now().isoformat()} {type(error).__name__}\n")


def launch():
    import sys
    if getattr(sys, "frozen", False):
        # Existing extractors may print personal data; discard console output
        # in the windowless build rather than saving it to disk.
        sys.stdout = open(os.devnull, "w")
        sys.stderr = open(os.devnull, "w")
    try:
        main()
    except Exception as error:
        try:
            record_error(error)
        except Exception:
            pass
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("KeyForMe startup", f"Startup failed ({type(error).__name__}). Check Chrome, Windows credentials and network access. Error types are recorded under LocalAppData/KeyForMe/errors.log.")
        root.destroy()


if __name__ == "__main__":
    launch()

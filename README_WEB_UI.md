# KeyForMe — local web control panel

This is an **additive** UI integration for your existing KeyForMe project. It does not replace `run_browser.py`, `field_mapping.py`, or your extractors.

## Install (from the `feature/web-ui` branch)

1. Unzip into the **root** of `C:\Python Projects\KeyForMe` (preserve folders).
2. Activate your virtual environment and install the UI dependencies:

   ```powershell
   .\.venv\Scripts\Activate.ps1
   pip install fastapi uvicorn
   ```

3. Check your `.env` has `OPENAI_API_KEY` and optionally `OPENAI_MODEL=gpt-6-luna`.
4. Run:

   ```powershell
   python .\run_web_ui.py
   ```

5. Chrome opens eCrash and a **KeyForMe** control tab. Log in to eCrash and open a work item. Click **Extract & Fill** on the control tab.
6. If the blank CA form is not yet open, open it in eCrash; the worker waits for the form before filling. Review the form manually; it never clicks Save or Submit.

## Architecture

- `app/ui/server.py`: local FastAPI server, command queue, in-memory logs and status.
- `app/ui/static/`: HTML/CSS/JS control panel.
- `run_web_ui.py`: browser lifecycle and extraction controller. All Playwright sync calls remain on the main thread.
- Existing `app/states` and `app/browser` files are reused; no changes to their extraction logic.

The local web server listens on `127.0.0.1` only. It does not log names, VINs, addresses, PDFs, or API keys. Temporary report files are removed by the existing downloader. The UI keeps only in-memory operational logs; it does not write them to disk.

## Notes

- This is an integration **starter**, not a verified production build. Test against your local mock and a supervised eCrash work item before using it for real keying.
- The current downloader is expected to accept `(context, selector)` as established in your project.
- The control tab is in the same Chrome session as eCrash. The worker locates the PDF viewer by its iframe URL and the CA form by `#formIframe`.
- The **Extract & Fill** action fills automatically when the blank form is available. It does not save or submit.
- `run_browser.py` remains your stable fallback while you develop on `feature/web-ui`.
- The browser may wait for the user to open the form; it does not choose a work item automatically.

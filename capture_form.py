from pathlib import Path
from tempfile import TemporaryDirectory

from playwright.sync_api import sync_playwright

from run_browser import KEYING_URL, find_form_page, wait_for_enter

PROJECT_ROOT = Path(__file__).resolve().parent
MOCK_DIR = PROJECT_ROOT / "mock"

TAB_SHIM = r"""
<script>
document.addEventListener("click", event => {
    const anchor = event.target.closest("a.ui-tabs-anchor");
    if (!anchor) return;
    const section = anchor.closest('[id^="section-page-base-"]');
    const href = anchor.getAttribute("href");
    if (!section || !href || !href.startsWith("#")) return;

    event.preventDefault();
    const targetId = href.slice(1);
    section.querySelectorAll('[role="tabpanel"]').forEach(panel => {
        const active = panel.id === targetId;
        panel.style.display = active ? "" : "none";
        panel.setAttribute("aria-hidden", active ? "false" : "true");
    });
});
</script>
"""


def make_index_html() -> str:
    # Build angle brackets at runtime so chat/editor sanitizers cannot strip the iframe.
    lt, gt = chr(60), chr(62)
    iframe = (
        f'{lt}iframe id="formIframe" src="ca_form.html" '
        f'style="width:100%;height:100vh;border:0;display:block"{gt}'
        f'{lt}/iframe{gt}'
    )
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en"><head><meta charset="UTF-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>KeyForMe CA Mock Form</title>'
        '<style>html,body{width:100%;height:100%;margin:0;overflow:hidden}</style>'
        f"</head><body>{iframe}</body></html>"
    )


def main() -> None:
    MOCK_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright, TemporaryDirectory(
        prefix="KeyForMe_Chrome_", ignore_cleanup_errors=True
    ) as profile:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=profile,
            channel="chrome",
            headless=False,
            chromium_sandbox=True,
            no_viewport=True,
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(KEYING_URL)

        wait_for_enter(
            context,
            "Open a BLANK CA form; add the units and Other Parties needed for testing; then press Enter...",
        )

        form_page = find_form_page(context)
        iframe_element = form_page.locator("#formIframe").element_handle()
        if iframe_element is None:
            raise RuntimeError("#formIframe was not found.")
        frame = iframe_element.content_frame()
        if frame is None:
            raise RuntimeError("Could not access #formIframe content.")

        html = frame.evaluate(
            """() => {
                const doc = document.documentElement.cloneNode(true);
                doc.querySelectorAll('script').forEach(script => script.remove());
                return '<!DOCTYPE html>' + doc.outerHTML;
            }"""
        )

        form_path = MOCK_DIR / "ca_form.html"
        index_path = MOCK_DIR / "index.html"
        form_path.write_text(html + TAB_SHIM, encoding="utf-8")
        index_path.write_text(make_index_html(), encoding="utf-8")

        print(f"Saved: {form_path}")
        print(f"Saved: {index_path}")
        print(f"index.html size: {index_path.stat().st_size} bytes")
        context.close()


if __name__ == "__main__":
    main()

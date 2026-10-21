from __future__ import annotations

import argparse
from pathlib import Path
from tempfile import TemporaryDirectory

from playwright.sync_api import sync_playwright

from run_browser import KEYING_URL, find_form_page, wait_for_enter


PROJECT_ROOT = Path(__file__).resolve().parent
MOCK_ROOT = PROJECT_ROOT / "mock"


TAB_SHIM = r"""
<script>
document.addEventListener("click", event => {
    const anchor = event.target.closest("a.ui-tabs-anchor");

    if (!anchor) {
        return;
    }

    const section = anchor.closest(
        '[id^="section-page-base-"]'
    );

    const href = anchor.getAttribute("href");

    if (
        !section
        || !href
        || !href.startsWith("#")
    ) {
        return;
    }

    event.preventDefault();

    const targetId = href.slice(1);

    section
        .querySelectorAll('[role="tabpanel"]')
        .forEach(panel => {
            const active = panel.id === targetId;

            panel.style.display = active
                ? ""
                : "none";

            panel.setAttribute(
                "aria-hidden",
                active ? "false" : "true",
            );
        });
});
</script>
"""


def make_index_html(form_filename: str) -> str:
    # Build the iframe tag at runtime so chat formatting
    # cannot remove the angle brackets.
    lt = chr(60)
    gt = chr(62)

    iframe = (
        f'{lt}iframe '
        f'id="formIframe" '
        f'src="{form_filename}" '
        f'style="'
        f'width:100%;'
        f'height:100vh;'
        f'border:0;'
        f'display:block'
        f'"'
        f'{gt}'
        f'{lt}/iframe{gt}'
    )

    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">'
        "<head>"
        '<meta charset="UTF-8">'
        '<meta name="viewport" '
        'content="width=device-width,initial-scale=1">'
        "<title>KeyForMe Mock Form</title>"
        "<style>"
        "html,body{"
        "width:100%;"
        "height:100%;"
        "margin:0;"
        "overflow:hidden;"
        "}"
        "</style>"
        "</head>"
        f"<body>{iframe}</body>"
        "</html>"
    )


def parse_args():
    parser = argparse.ArgumentParser(
        description="Capture a blank eCrash keying form.",
    )

    parser.add_argument(
        "--state",
        required=True,
        choices=("CA", "NM"),
        type=str.upper,
        help="State form to capture.",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    state = args.state

    # CA and NM are stored separately.
    state_dir = MOCK_ROOT / state.lower()
    state_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    form_filename = f"{state.lower()}_form.html"
    form_path = state_dir / form_filename
    index_path = state_dir / "index.html"

    print(f"CAPTURE MODE: {state}")
    print(f"Output directory: {state_dir}")

    with (
        sync_playwright() as playwright,
        TemporaryDirectory(
            prefix="KeyForMe_Chrome_",
            ignore_cleanup_errors=True,
        ) as profile,
    ):
        context = (
            playwright.chromium
            .launch_persistent_context(
                user_data_dir=profile,
                channel="chrome",
                headless=False,
                chromium_sandbox=True,
                no_viewport=True,
            )
        )

        page = (
            context.pages[0]
            if context.pages
            else context.new_page()
        )

        page.goto(KEYING_URL)

        result = wait_for_enter(
            context,
            (
                f"Open a BLANK {state} form. "
                "Add at least 2 vehicle units and "
                "1 Other Party for testing, then press Enter. "
                "Press Q to cancel..."
            ),
        )

        if result == "quit":
            print(
                "Capture cancelled. "
                "No mock files were changed."
            )
            context.close()
            return

        form_page = find_form_page(context)

        iframe_element = form_page.locator(
            "#formIframe"
        ).element_handle()

        if iframe_element is None:
            raise RuntimeError(
                "#formIframe was not found."
            )

        frame = iframe_element.content_frame()

        if frame is None:
            raise RuntimeError(
                "Could not access #formIframe."
            )

        html = frame.evaluate(
            """() => {
                const doc =
                    document.documentElement.cloneNode(
                        true
                    );

                doc
                    .querySelectorAll("script")
                    .forEach(script => script.remove());

                return (
                    "<!DOCTYPE html>"
                    + doc.outerHTML
                );
            }"""
        )

        form_path.write_text(
            html + TAB_SHIM,
            encoding="utf-8",
        )

        index_path.write_text(
            make_index_html(form_filename),
            encoding="utf-8",
        )

        print(f"Saved {state} form: {form_path}")
        print(f"Saved {state} wrapper: {index_path}")

        context.close()


if __name__ == "__main__":
    main()
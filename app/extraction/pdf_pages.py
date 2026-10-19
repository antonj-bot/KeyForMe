from pathlib import Path
import pymupdf as fitz

def render_field_pages(pdf_path: Path, output_dir: Path, dpi: int = 200) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    document = fitz.open(pdf_path)
    if len(document) < 2:
        raise ValueError("Expected a CHP 555 report with at least two pages")
    paths = []
    for page_index in (0, 1):
        page = document.load_page(page_index)
        pixmap = page.get_pixmap(dpi=dpi, alpha=False)
        path = output_dir / f"page_{page_index + 1}.png"
        pixmap.save(path)
        paths.append(path)
    return paths

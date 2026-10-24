import re


def clean_rid_text(text):
    """'Report Id: 9000000001' -> '9000000001'."""
    return re.sub(r"^Report\s*Id:\s*", "", (text or "").strip(), flags=re.IGNORECASE).strip()

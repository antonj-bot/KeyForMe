import re


def clean_rid_text(text):
    """'Report Id: 1327309097' -> '1327309097'."""
    return re.sub(r"^Report\s*Id:\s*", "", (text or "").strip(), flags=re.IGNORECASE).strip()

from pathlib import Path
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
FORM = ROOT / "mock" / "nm" / "nm_form.html"

KEYWORDS = (
    "Incident_",
    "Person_",
    "Vehicle_",
)

def main():
    if not FORM.exists():
        raise SystemExit(f"NM mock not found: {FORM}")

    soup = BeautifulSoup(
        FORM.read_text(encoding="utf-8"),
        "html.parser",
    )

    output = []

    for element in soup.find_all(
        ["input", "select", "textarea"]
    ):
        field_id = element.get("id", "")

        if not field_id.startswith(KEYWORDS):
            continue

        field_type = element.get("type", "text")

        # Remove dynamic unit suffixes.
        base_id = field_id.split("-t")[0]

        if element.name == "select":
            options = [
                {
                    "value": option.get("value", ""),
                    "label": option.get_text(
                        " ",
                        strip=True,
                    ),
                }
                for option in element.find_all("option")
            ]
        else:
            options = []

        output.append({
            "id": base_id,
            "type": field_type,
            "options": options,
        })

    # Remove duplicate fields from additional unit tabs.
    unique = {}

    for field in output:
        unique.setdefault(field["id"], field)

    for field in unique.values():
        print(f"\nFIELD: {field['id']}")
        print(f"TYPE: {field['type']}")

        for option in field["options"]:
            print(
                f"  {option['value']} = {option['label']}"
            )


if __name__ == "__main__":
    main()
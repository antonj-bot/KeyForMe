"""Exact option engine. Catalogs and code meanings belong to each state."""
def normalize(value):
    return " ".join(str(value or "").upper().split())

def map_options(field, raw, mapping, warnings=None):
    if raw is None:
        return ""
    items = raw if isinstance(raw, (list, tuple)) else [raw]
    parts = [normalize(part) for item in items if item is not None
             for part in str(item).split(";") if normalize(part)]
    result = []
    for part in parts:
        if part not in mapping:
            if warnings is not None:
                warnings.append(f"{field}: unrecognized option; entire field left blank.")
            return ""
        for canonical in str(mapping[part]).split(";"):
            if canonical and canonical not in result:
                result.append(canonical)
    return ";".join(result)

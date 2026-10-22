def nm_dropdown_value(field, raw, warnings=None):
    return map_options("NM " + field, raw, NM_DROPDOWNS.get(field, {}), warnings)

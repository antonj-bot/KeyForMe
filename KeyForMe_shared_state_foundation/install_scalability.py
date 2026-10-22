"""Preflighted source migration. Dry run by default; --apply writes with backups."""
import argparse
import ast
from datetime import datetime
import json
from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parent
MARKER = "# KeyForMe shared-core migration v1"

def replace_function(source, name, replacement):
    tree = ast.parse(source)
    matches = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name]
    if len(matches) != 1:
        raise ValueError(f"Expected one function {name}; source differs. Nothing written.")
    node = matches[0]
    lines = source.splitlines(keepends=True)
    lines[node.lineno-1:node.end_lineno] = [replacement.rstrip() + "\n"]
    return "".join(lines)

def insert_imports(source, block):
    if MARKER in source:
        return source
    tree = ast.parse(source)
    position = 0
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str) and position == 0:
            position = node.end_lineno
        elif isinstance(node, ast.ImportFrom) and node.module == "__future__":
            position = node.end_lineno
        else:
            break
    lines = source.splitlines(keepends=True)
    lines[position:position] = ["\n" + MARKER + "\n" + block + "\n"]
    return "".join(lines)

def wire_vin(source, nm):
    name = "_fill_nm_vin" if nm else "fill_vehicle"
    node = next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name == name)
    body = "\n".join(source.splitlines()[node.lineno-1:node.end_lineno]) + "\n"
    if "should_attempt_vin_lookup(" in body:
        expected_policy = "policy=NONBLOCKING_FORMAT_ERRORS" if nm else "policy=CA_VIN_POLICY"
        if expected_policy not in body:
            raise ValueError("A different VIN helper is already installed; reconcile it before migration. Nothing written.")
        return source
    anchor = '        vin_box.press("Tab")'
    if body.count(anchor) != 1:
        raise ValueError("VIN entry structure changed; review migration before applying.")
    start = body.index(anchor) + len(anchor)
    if nm:
        end = body.index('        if not _click_vin_popup_ok(page):', start)
        body = body[:start] + """

        if not should_attempt_vin_lookup(
            vin, policy=NONBLOCKING_FORMAT_ERRORS,
            unit_number=unit_number, warn=warnings.append,
        ):
            return False

""" + body[end:]
    else:
        popup_start = body.index('        if click_popup_ok(page):', start)
        end = body.index('    for key, value in vehicle.items():', popup_start)
        popup = body[popup_start:end]
        popup = "\n".join("    " + line if line else line for line in popup.splitlines())
        body = body[:start] + """
        if should_attempt_vin_lookup(
            vin, policy=CA_VIN_POLICY,
            warn=lambda message: print("  NOTE: " + message),
        ):
""" + popup + "\n\n" + body[end:]
    return replace_function(source, name, body)

def plan(root):
    spec = json.loads((HERE / "migrations/spec.json").read_text())
    changes = {}
    for name, functions in spec["functions"].items():
        relative = "app/" + ("keying/" if name == "nm_dropdowns.py" else "browser/") + name
        path = root / relative
        if name == "nm_dropdowns.py" and not path.is_file():
            candidates = list((root / "app").rglob(name))
            if len(candidates) != 1:
                raise ValueError("Could not uniquely locate app's nm_dropdowns.py. Nothing written.")
            path = candidates[0]
            relative = path.relative_to(root).as_posix()
        source = path.read_text(encoding="utf-8-sig")
        for function in functions:
            replacement = (HERE / "migrations" / name / (function + ".py")).read_text()
            source = replace_function(source, function, replacement)
        source = insert_imports(source, spec["imports"][name])
        if name in ("nm_filler.py", "playwright_filler.py"):
            source = wire_vin(source, name == "nm_filler.py")
        if name == "nm_filler.py":
            # Remove only the unused diagnostic assignment, not filling logic.
            nodes = [n for n in ast.walk(ast.parse(source)) if isinstance(n,ast.Assign)
                     and any(isinstance(t,ast.Name) and t.id == "all_tabs" for t in n.targets)]
            lines = source.splitlines(keepends=True)
            for node in sorted(nodes,key=lambda n:n.lineno,reverse=True):
                del lines[node.lineno-1:node.end_lineno]
            source = "".join(lines)
        changes[relative] = source
    # Preserve existing registrations and extend explicitly with new adapters.
    relative = "app/states/__init__.py"
    source = (root / relative).read_text(encoding="utf-8-sig")
    if "PIPELINES" not in source:
        raise ValueError("Existing PIPELINES registry not found; no files changed.")
    if MARKER not in source:
        source += "\n" + MARKER + "\nfrom app.core.registry import extend_pipelines\nPIPELINES = extend_pipelines(PIPELINES)\n"
    changes[relative] = source
    # Capture supports registered states rather than a fixed CA/NM tuple.
    relative = "capture_form.py"
    source = (root / relative).read_text(encoding="utf-8-sig")
    if 'choices=("CA", "NM")' in source:
        source = source.replace('choices=("CA", "NM")', 'choices=tuple(sorted(PIPELINES))')
        source = insert_imports(source, 'from app.states import PIPELINES\n')
    elif 'choices=tuple(sorted(PIPELINES))' not in source:
        raise ValueError("Capture state choices differ; no files changed.")
    changes[relative] = source
    for path in (HERE / "payload").rglob("*"):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        relative = path.relative_to(HERE / "payload").as_posix()
        text = path.read_text(encoding="utf-8")
        target = root / relative
        if target.exists():
            if relative == "app/state_plugins.py":
                continue  # Never overwrite a user's plugin registrations.
            if target.read_text(encoding="utf-8-sig") != text:
                raise ValueError(f"New shared file already exists and differs: {relative}. Nothing written.")
        changes[relative] = text
    gitignore = root / ".gitignore"
    ignore = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    if ".scalability-backups/" not in ignore.splitlines():
        changes[".gitignore"] = ignore.rstrip() + "\n.scalability-backups/\n"
    for name, source in changes.items():
        if name.endswith(".py"):
            ast.parse(source, filename=name)
    return {name:text for name,text in changes.items()
            if not (root/name).exists() or (root/name).read_text(encoding="utf-8-sig") != text}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    root = args.project_root.resolve()
    changes = plan(root)
    for name in sorted(changes):
        print("UPDATE" if (root/name).exists() else "ADD", name)
    if not args.apply:
        print("Dry run complete. No project files changed. Use --apply after reviewing.")
        return
    if not changes:
        print("Already installed; no changes.")
        return
    backup = root / ".scalability-backups" / datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup.mkdir(parents=True)
    manifest = {"files": list(changes), "existing": []}
    for name in changes:
        target = root/name
        if target.exists():
            destination = backup/name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target,destination)
            manifest["existing"].append(name)
    (backup/"manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    try:
        for name,text in changes.items():
            target = root/name
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_text(text,encoding="utf-8")
    except Exception:
        for name in changes:
            target = root/name
            if name in manifest["existing"]:
                shutil.copy2(backup/name,target)
            elif target.exists():
                target.unlink()
        raise
    print("Installed. Backup:",backup)
    print("Run tests, then supervised CA/NM tests. No live browser or API test was performed by this installer.")

if __name__ == "__main__":
    main()

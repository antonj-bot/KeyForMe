"""Restore an installer backup. Review first; this overwrites post-install edits."""
import argparse
import json
from pathlib import Path
import shutil

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    root = args.project_root.resolve()
    backup = args.backup.resolve()
    manifest = json.loads((backup / "manifest.json").read_text())
    for name in manifest["files"]:
        target = (root / name).resolve()
        if not target.is_relative_to(root):
            raise ValueError("Backup manifest contains an unsafe path.")
        if name in manifest["existing"] and not (backup / name).is_file():
            raise ValueError("Backup is incomplete; no restoration attempted.")
    for name in manifest["files"]:
        print("RESTORE" if name in manifest["existing"] else "REMOVE",name)
    if not args.apply:
        print("Dry run only. Add --apply to restore; later edits to these files will be overwritten.")
        return
    for name in manifest["files"]:
        target = root / name
        if name in manifest["existing"]:
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(backup / name,target)
        elif target.exists():
            target.unlink()
    print("Restored the selected migration backup.")

if __name__ == "__main__":
    main()

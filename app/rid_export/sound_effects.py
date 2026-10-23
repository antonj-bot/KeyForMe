"""Success/fail sounds using Windows' built-in winsound (no pygame).

Put copy_successfully.wav and copy_failed.wav in the sounds/ folder next to
this file. If a file is missing, a standard Windows beep is used instead.
"""
from __future__ import annotations

import sys
from pathlib import Path

SOUNDS_DIR = Path(__file__).resolve().parent / "sounds"
SUCCESS_FILE = "copy_successfully.wav"
FAIL_FILE = "copy_failed.wav"

_muted = False


def is_muted() -> bool:
    return _muted


def set_muted(value: bool) -> None:
    global _muted
    _muted = bool(value)


def toggle_muted() -> bool:
    set_muted(not _muted)
    return _muted


def _play(filename: str, fallback_name: str) -> None:
    if _muted or sys.platform != "win32":
        return
    try:
        import winsound

        path = SOUNDS_DIR / filename
        if path.is_file():
            winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC)
        else:
            winsound.MessageBeep(getattr(winsound, fallback_name))
    except Exception:
        pass  # a sound problem must never break extraction


def play_success() -> None:
    _play(SUCCESS_FILE, "MB_OK")


def play_fail() -> None:
    _play(FAIL_FILE, "MB_ICONHAND")

"""Windows-only credential storage. No plaintext fallback and no browser key API."""
from __future__ import annotations
import os
import sys
import json
from pathlib import Path

SERVICE = "KeyForMe.OpenAI"
ACCOUNT = "api-key"
DEFAULT_MODEL = "gpt-6-luna"


def data_dir():
    if sys.platform != "win32":
        raise RuntimeError("This pilot requires Windows credential storage")
    path = Path(os.environ["LOCALAPPDATA"]) / "KeyForMe"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _vault():
    if sys.platform != "win32":
        raise RuntimeError("Windows is required")
    # Explicit backend: never fall back to a plaintext keyring plugin.
    from keyring.backends.Windows import WinVaultKeyring
    return WinVaultKeyring()


def read_key():
    return _vault().get_password(SERVICE, ACCOUNT) or ""


def save_key(value):
    value = value.strip()
    if not value or any(c.isspace() for c in value):
        raise ValueError("Enter a nonempty API key without whitespace")
    _vault().set_password(SERVICE, ACCOUNT, value)


def delete_key():
    vault = _vault()
    if vault.get_password(SERVICE, ACCOUNT):
        vault.delete_password(SERVICE, ACCOUNT)


def read_model():
    path = data_dir() / "settings.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8")).get("model") or DEFAULT_MODEL
    # Nonsecret developer setting only; never read .env in the packaged launcher.
    return os.getenv("OPENAI_MODEL", DEFAULT_MODEL)


def sync_environment():
    # Development override:
    # temporary key inherited from the current PowerShell session.
    session_key = os.getenv("OPENAI_API_KEY", "").strip()
    if session_key:
        os.environ["OPENAI_API_KEY"] = session_key
        return True

    # Packaged EXE:
    # use the key saved by this Windows user.
    stored_key = read_key().strip()
    if stored_key:
        os.environ["OPENAI_API_KEY"] = stored_key
        return True

    os.environ.pop("OPENAI_API_KEY", None)
    return False


def show_settings():
    """Main-thread native window. Never prefill or return the stored secret."""
    import tkinter as tk
    from tkinter import ttk, messagebox
    window = tk.Tk()
    window.title("KeyForMe - API Settings")
    window.resizable(False, False)
    window.attributes("-topmost", True)
    box = ttk.Frame(window, padding=22)
    box.grid()
    configured = bool(
        os.getenv("OPENAI_API_KEY", "").strip()
        or read_key().strip()
    )
    ttk.Label(box, text="KeyForMe API setup", font=("Segoe UI", 15, "bold")).grid(row=0,column=0,columnspan=3,sticky="w")
    ttk.Label(box, text=("A key is stored for this Windows account." if configured else "Enter your own authorized API key to get started.")).grid(row=1,column=0,columnspan=3,pady=(10,12),sticky="w")
    ttk.Label(box,text="API key (leave empty to keep the stored key)").grid(row=2,column=0,columnspan=3,sticky="w")
    key_var = tk.StringVar()
    entry = ttk.Entry(box,textvariable=key_var,show="*",width=57)
    entry.grid(row=3,column=0,columnspan=3,pady=(4,12))
    ttk.Label(box,text="Model ID (must be available to your API project)").grid(row=4,column=0,columnspan=3,sticky="w")
    model_var = tk.StringVar(value=read_model())
    ttk.Entry(box,textvariable=model_var,width=57).grid(row=5,column=0,columnspan=3,pady=(4,12))
    ttk.Label(box,text="Stored in Windows credentials, not in the EXE.\nSaving does not validate API access. Extraction uses API credits.\nOnly process reports approved for this AI service.",wraplength=440).grid(row=6,column=0,columnspan=3,pady=(0,16),sticky="w")
    def save():
        model = model_var.get().strip()
        if not model:
            messagebox.showerror("Settings", "Enter a model ID", parent=window)
            return
        try:
            if key_var.get().strip():
                save_key(key_var.get())
            elif not read_key():
                messagebox.showerror("Settings", "Enter your API key", parent=window)
                return
            (data_dir()/"settings.json").write_text(json.dumps({"model":model},indent=2),encoding="utf-8")
            key_var.set("")
            window.destroy()
        except Exception as exc:
            messagebox.showerror("Settings",f"Could not save settings ({type(exc).__name__}). No plaintext fallback is used.",parent=window)
    def remove():
        if not messagebox.askyesno("Remove key", "Remove the saved key from this Windows account?",parent=window):
            return
        try:
            delete_key()
            os.environ.pop("OPENAI_API_KEY",None)
            key_var.set("")
            window.destroy()
        except Exception as exc:
            messagebox.showerror("Settings",f"Could not remove key ({type(exc).__name__})",parent=window)
    ttk.Button(box,text="Save",command=save).grid(row=7,column=0,sticky="w")
    ttk.Button(box,text="Remove key",command=remove).grid(row=7,column=1)
    ttk.Button(box,text="Cancel",command=window.destroy).grid(row=7,column=2,sticky="e")
    entry.focus_set()
    window.mainloop()
    return sync_environment()

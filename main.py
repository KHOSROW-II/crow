"""
Contacts Manager - entry point with vault support.

Usage:
    python main.py                    auto mode (prompts vault if present)
    python main.py gui                force GUI
    python main.py tui                curses TUI
    python main.py tui-modern         Textual TUI
    python main.py cli ...            CLI

Vault:
    python main.py vault init         create vault from current files
    python main.py vault status       show vault state
    python main.py vault change       change passphrase
    python main.py vault unlock       decrypt into a working directory (debug)
"""

import os
import sys
from pathlib import Path
from branding import APP_NAME, APP_TITLE

# ============================================================
# GUI passphrase dialog (only used in gui mode)
# ============================================================
def _ask_passphrase_gui(confirm: bool = False) -> str | None:
    """Minimal tkinter dialog to ask for the vault passphrase."""
    import tkinter as tk
    from tkinter import messagebox

    result: dict[str, str | None] = {"pwd": None}

    root = tk.Tk()
    root.title(f"{APP_NAME} — Vault")
    root.configure(bg="#1e1e1e")
    root.resizable(False, False)

    tk.Label(root, text="Vault passphrase:", bg="#1e1e1e", fg="#d4d4d4",
             font=("Sans", 10)).pack(anchor="w", padx=12, pady=(12, 4))

    var1 = tk.StringVar()
    e1 = tk.Entry(root, textvariable=var1, show="•", width=40,
                  bg="#1b1b1b", fg="#d4d4d4", insertbackground="#d4d4d4",
                  relief="flat", font=("Sans", 10))
    e1.pack(fill="x", padx=12, pady=(0, 8), ipady=4)
    e1.focus_set()

    var2 = None
    if confirm:
        tk.Label(root, text="Confirm passphrase:", bg="#1e1e1e", fg="#d4d4d4",
                 font=("Sans", 10)).pack(anchor="w", padx=12, pady=(4, 4))
        var2 = tk.StringVar()
        e2 = tk.Entry(root, textvariable=var2, show="•", width=40,
                      bg="#1b1b1b", fg="#d4d4d4", insertbackground="#d4d4d4",
                      relief="flat", font=("Sans", 10))
        e2.pack(fill="x", padx=12, pady=(0, 8), ipady=4)

    def ok():
        p1 = var1.get()
        if not p1:
            messagebox.showerror("Vault", "Passphrase cannot be empty.",
                                 parent=root)
            return
        if confirm and var2 is not None and p1 != var2.get():
            messagebox.showerror("Vault", "Passphrases do not match.",
                                 parent=root)
            return
        result["pwd"] = p1
        root.destroy()

    def cancel():
        result["pwd"] = None
        root.destroy()

    bar = tk.Frame(root, bg="#1e1e1e")
    bar.pack(fill="x", padx=12, pady=(4, 12))
    tk.Button(bar, text="OK", command=ok, width=10,
              bg="#0e639c", fg="white", relief="flat").pack(side="right")
    tk.Button(bar, text="Cancel", command=cancel, width=10,
              bg="#252526", fg="#d4d4d4", relief="flat").pack(side="right", padx=(0, 6))

    root.bind("<Return>", lambda _e: ok())
    root.bind("<Escape>", lambda _e: cancel())

    root.update_idletasks()
    w, h = root.winfo_width(), root.winfo_height()
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    root.geometry(f"+{(sw - w)//2}+{(sh - h)//3}")
    root.mainloop()

    return result["pwd"]


# ============================================================
# Vault subcommands
# ============================================================
def _vault_init():
    from crypto import prompt_passphrase, generate_random_key
    from vault import vault_exists, init_vault

    if vault_exists():
        print("[!] A vault already exists in ./vault/.")
        return
    print("Creating a new vault from the current plain files.")
    print("The databases and attachments folder will be encrypted.\n")
    ans = input("Generate a random passphrase for me? [y/N]: ").strip().lower()
    if ans == "y":
        pwd = generate_random_key()
        print("\n>>> YOUR VAULT PASSPHRASE <<<")
        print(pwd)
        print(">>> SAVE IT NOW. THERE IS NO RECOVERY. <<<\n")
        input("Press Enter once you've saved the passphrase... ")
    else:
        pwd = prompt_passphrase(confirm=True)

    remove = input(
        "Delete the plain files after encryption? [y/N]: "
    ).strip().lower() == "y"

    init_vault(pwd, source_dir=Path("."), remove_originals=remove)
    print("\n[+] Vault created successfully in ./vault/")
    print("    Use the same passphrase on every startup.")


def _vault_status():
    from vault import vault_exists, VAULT_DIR
    from crypto import read_header
    if not vault_exists():
        print("No vault found. The app is running in plain (unencrypted) mode.")
        return
    header = read_header(VAULT_DIR / "vault.json")
    print(f"Vault           : {VAULT_DIR.resolve()}")
    print(f"Version         : {header.get('version')}")
    print(f"Created at      : {header.get('created_at')}")
    print(f"PBKDF2 iters    : {header.get('iterations')}")


def _vault_change():
    from crypto import prompt_passphrase
    from vault import vault_exists, change_passphrase
    if not vault_exists():
        print("[!] No vault found.")
        return
    print("Enter the CURRENT passphrase.")
    old = prompt_passphrase()
    print("Enter the NEW passphrase.")
    new = prompt_passphrase(confirm=True)
    change_passphrase(old, new)
    print("[+] Passphrase changed.")


def _vault_unlock_debug():
    """Decrypt into a temp dir but don't re-encrypt (for inspection)."""
    from crypto import prompt_passphrase
    from vault import vault_exists, unlock
    if not vault_exists():
        print("[!] No vault found.")
        return
    pwd = prompt_passphrase()
    wd = unlock(pwd)
    print(f"[+] Decrypted into: {wd}")
    print("    The plain files stay there until you delete them.")


# ============================================================
# App dispatch
# ============================================================
def _run_app(mode: str, args: list[str]):
    from db import ensure_schema
    try:
        ensure_schema()
    except Exception as e:
        print(f"[!] Failed to initialize database: {e}")
        sys.exit(1)

    if mode == "gui":
        from gui import run_gui
        run_gui()
        return

    if mode == "tui":
        from tui import run_tui
        run_tui()
        return

    if mode == "tui-modern":
        try:
            from tui_modern import run_tui
        except ImportError as e:
            print(f"[!] Textual is required for tui-modern.\n"
                  f"    pip install textual\n    ({e})")
            sys.exit(1)
        run_tui()
        return

    if mode == "cli":
        from cli import run_cli
        run_cli(args)
        return


def main():
    args = sys.argv[1:]
    mode = "auto"

    # vault subcommand
    if args and args[0] == "vault":
        sub = args[1] if len(args) > 1 else "status"
        if sub == "init":
            _vault_init()
        elif sub == "status":
            _vault_status()
        elif sub == "change":
            _vault_change()
        elif sub == "unlock":
            _vault_unlock_debug()
        else:
            print("Usage: main.py vault [init|status|change|unlock]")
        return

    if args and args[0] in ("gui", "--gui"):
        mode = "gui"; args = args[1:]
    elif args and args[0] in ("tui", "--tui"):
        mode = "tui"; args = args[1:]
    elif args and args[0] in ("tui-modern", "--tui-modern", "tm"):
        mode = "tui-modern"; args = args[1:]
    elif args and args[0] in ("cli", "--cli"):
        mode = "cli"; args = args[1:]
    elif args and args[0].startswith("-"):
        mode = "cli"

    # ----- vault handling -----
    from vault import vault_exists, unlock, lock

    if not vault_exists():
        # no vault - normal flow
        if mode == "auto":
            if sys.stdin.isatty() and sys.stdout.isatty():
                try:
                    import curses  # noqa: F401
                    mode = "tui"
                except Exception:
                    mode = "gui"
            else:
                mode = "gui"
        _run_app(mode, args)
        return

    # vault exists - ask for passphrase
    print("Vault detected. Unlocking...")
    if mode == "gui" or (mode == "auto" and not (sys.stdin.isatty() and sys.stdout.isatty())):
        pwd = _ask_passphrase_gui()
    else:
        from crypto import prompt_passphrase
        pwd = prompt_passphrase()

    if not pwd:
        print("Cancelled.")
        sys.exit(1)

    try:
        workdir = unlock(pwd)
    except Exception as e:
        print(f"[!] Unlock failed: {e}")
        sys.exit(2)

    os.environ["CONTACTS_WORKDIR"] = str(workdir)
    print(f"[+] Unlocked into {workdir}")

    if mode == "auto":
        if sys.stdin.isatty() and sys.stdout.isatty():
            try:
                import curses  # noqa: F401
                mode = "tui"
            except Exception:
                mode = "gui"
        else:
            mode = "gui"

    try:
        _run_app(mode, args)
    finally:
        print("Re-encrypting vault...")
        try:
            lock(workdir, pwd)
            print("[+] Vault locked.")
        except Exception as e:
            print(f"[!] Lock failed: {e}")
            print(f"    Plain files are still in: {workdir}")


if __name__ == "__main__":
    main()
"""
Edit dialog for a contact and its social rows.
"""

import sys
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog
from pathlib import Path
from typing import Any

import core
from text_utils import fa, fa_lines, HAS_BIDI
from db import normalize_phone
from image_utils import (
    load_photo_for_tk,
    load_photo_for_tk_from_bytes,
    SUPPORTED_EXTS,
)

BG         = "#1e1e1e"
BG_PANEL   = "#252526"
BG_ENTRY   = "#1b1b1b"
FG         = "#d4d4d4"
FG_DIM     = "#808080"
ACCENT     = "#0e639c"
ACCENT_HOV = "#1177bb"
OK_GREEN   = "#4ec9b0"
ERR_RED    = "#f48771"

FONT_UI   = ("Tahoma", 10) if sys.platform == "win32" else ("Sans", 10)
FONT_MONO = ("Consolas", 10) if sys.platform == "win32" else ("Monospace", 10)

STATUSES = ["unchecked", "checking", "verified", "invalid", "anonymous"]
EXISTS   = ["unknown", "yes", "no"]


def _mk_entry_raw(parent, textvariable, width=40):
    return tk.Entry(parent, textvariable=textvariable,
                    bg=BG_ENTRY, fg=FG, insertbackground=FG,
                    relief="flat", font=FONT_UI, width=width)


def _mk_combo(parent, textvariable, values, width=22):
    return ttk.Combobox(parent, textvariable=textvariable,
                        values=values, state="readonly", width=width)


# ============================================================
# FaEntry / FaText
# ============================================================
class FaEntry:
    def __init__(self, parent, raw="", width=40):
        self._orig_raw = raw or ""
        self._focused = False
        self.var = tk.StringVar(value=fa(self._orig_raw))
        self.widget = tk.Entry(parent, textvariable=self.var, width=width,
                               bg=BG_ENTRY, fg=FG, insertbackground=FG,
                               relief="flat", font=FONT_UI)
        self.widget.bind("<FocusIn>",  self._on_focus_in,  add="+")
        self.widget.bind("<FocusOut>", self._on_focus_out, add="+")

    def _on_focus_in(self, _e=None):
        self._focused = True
        self.var.set(self._orig_raw)

    def _on_focus_out(self, _e=None):
        self._focused = False
        self._orig_raw = self.var.get()
        self.var.set(fa(self._orig_raw))

    def get(self):
        if self._focused:
            return self.var.get().strip() or None
        return self._orig_raw.strip() or None

    def set_raw(self, raw):
        self._orig_raw = raw or ""
        if self._focused:
            self.var.set(self._orig_raw)
        else:
            self.var.set(fa(self._orig_raw))

    def clear(self):
        self.set_raw("")


class FaText:
    def __init__(self, parent, raw="", height=5, width=40):
        self._raw = raw or ""
        self._focused = False
        self.widget = tk.Text(
            parent,
            height=height, width=width,
            wrap="word",
            bg=BG_ENTRY, fg=FG, insertbackground=FG,
            relief="flat", font=FONT_UI,
            padx=6, pady=4,
        )
        self._render()
        self.widget.bind("<FocusIn>",  self._on_focus_in,  add="+")
        self.widget.bind("<FocusOut>", self._on_focus_out, add="+")

    def _render(self):
        self.widget.delete("1.0", "end")
        if self._focused:
            self.widget.insert("1.0", self._raw)
        else:
            self.widget.insert("1.0", fa_lines(self._raw))

    def _on_focus_in(self, _e=None):
        self._focused = True
        self._render()

    def _on_focus_out(self, _e=None):
        self._focused = False
        self._raw = self.widget.get("1.0", "end-1c")
        self._render()

    def get(self):
        if self._focused:
            return self.widget.get("1.0", "end-1c").strip() or None
        return self._raw.strip() or None

    def set_raw(self, raw):
        self._raw = raw or ""
        self._render()

    def clear(self):
        self._raw = ""
        self._render()


# ============================================================
# Photo preview
# ============================================================
class PhotoPreview(tk.Frame):
    SIZE = 140

    def __init__(self, parent):
        super().__init__(parent, bg=BG_ENTRY,
                         highlightthickness=1,
                         highlightbackground="#3c3c3c")
        self._photo: Any = None
        self.canvas = tk.Canvas(self, width=self.SIZE, height=self.SIZE,
                                bg="#0c0c0c", highlightthickness=0)
        self.canvas.pack()
        self._show_placeholder("no photo")

    def _show_placeholder(self, text="no photo"):
        self.canvas.delete("all")
        self.canvas.create_text(
            self.SIZE // 2, self.SIZE // 2,
            text=text, fill=FG_DIM, font=(FONT_UI[0], 9),
            width=self.SIZE - 8, justify="center",
        )

    def set_path(self, photo_path):
        self._photo = None
        self.canvas.delete("all")
        if not photo_path:
            self._show_placeholder("no photo")
            return
        img = load_photo_for_tk(photo_path, (self.SIZE - 4, self.SIZE - 4))
        if img is None:
            self._show_placeholder(f"preview not available\n({Path(photo_path).name})")
            return
        self._photo = img
        self.canvas.create_image(self.SIZE // 2, self.SIZE // 2, image=img)

    def set_bytes(self, data):
        self._photo = None
        self.canvas.delete("all")
        if not data:
            self._show_placeholder("no photo")
            return
        img = load_photo_for_tk_from_bytes(data, (self.SIZE - 4, self.SIZE - 4))
        if img is None:
            self._show_placeholder("preview not available")
            return
        self._photo = img
        self.canvas.create_image(self.SIZE // 2, self.SIZE // 2, image=img)


# ============================================================
# Dialog
# ============================================================
class ContactEditDialog(tk.Toplevel):
    def __init__(self, parent, contact_id=None):
        super().__init__(parent)
        self.contact_id = contact_id
        self.result = None
        self.platform_added = False

        # pending image, copied into DB only on save
        self._pending_image_path: str | None = None
        self._pending_image_bytes: bytes | None = None
        self._clear_image = False

        self.title(f"Contact #{contact_id}" if contact_id
                   else "New contact")
        self.configure(bg=BG)
        self.geometry("920x880")
        self.minsize(800, 700)
        self.transient(parent)
        self.grab_set()

        self._load()
        self._build()
        self._center(parent)

    def _center(self, parent):
        self.update_idletasks()
        px = parent.winfo_rootx() + (parent.winfo_width()  - self.winfo_width())  // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{max(px, 0)}+{max(py, 0)}")

    def _load(self):
        if self.contact_id:
            self.info = core.get_contact_detail(self.contact_id)
        else:
            self.info = {
                "contact": {"phone_number": "", "status": "unchecked",
                            "name": "", "last_name": "",
                            "national_code": "", "notes": "",
                            "photo_path": "", "pinned": 0, "special": 0},
                "socials": [], "identity": {}, "telegram": {},
                "links": [], "sources": [], "external": {}, "files": [],
                "images": [], "primary_image_id": None,
            }
        self.social_map = {s["platform"]: s for s in self.info["socials"]}
        self.platforms = core.list_platforms()

    def _build(self):
        top = tk.Frame(self, bg=BG)
        top.pack(fill="x", padx=8, pady=(8, 0))
        tk.Button(top, text="+ Add platform",
                  command=self._add_platform_dialog,
                  bg=BG_PANEL, fg=OK_GREEN,
                  activebackground=ACCENT_HOV, activeforeground="white",
                  relief="flat", padx=10, pady=4, cursor="hand2",
                  font=FONT_UI).pack(side="right")

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=8, pady=(4, 4))

        self._build_contact_tab(self.nb)

        self.platform_widgets: dict[str, dict] = {}
        self.platform_tabs: dict[str, tk.Frame] = {}
        for p in self.platforms:
            self._build_platform_tab(self.nb, p)

        bar = tk.Frame(self, bg=BG)
        bar.pack(fill="x", padx=8, pady=(4, 8))

        tk.Button(bar, text="Save", command=self._save,
                  bg="#2d5a2d", fg="white",
                  activebackground="#3a7a3a", activeforeground="white",
                  relief="flat", padx=16, pady=6, cursor="hand2",
                  font=FONT_UI).pack(side="left", padx=3)

        tk.Button(bar, text="Cancel", command=self.destroy,
                  bg=BG_PANEL, fg=FG,
                  activebackground=ACCENT_HOV, activeforeground="white",
                  relief="flat", padx=16, pady=6, cursor="hand2",
                  font=FONT_UI).pack(side="left", padx=3)

        if self.contact_id:
            tk.Button(bar, text="Delete contact", command=self._delete,
                      bg="#5a2d2d", fg="white",
                      activebackground="#7a3a3a", activeforeground="white",
                      relief="flat", padx=16, pady=6, cursor="hand2",
                      font=FONT_UI).pack(side="right", padx=3)

        self.bind("<Escape>", lambda _e: self.destroy())
        self.bind("<Control-s>", lambda _e: self._save())

    def _label(self, parent, row, text):
        tk.Label(parent, text=text, bg=BG, fg=FG,
                 font=FONT_UI, anchor="w").grid(
            row=row, column=0, sticky="w", padx=(0, 10), pady=6)

    def _build_contact_tab(self, nb):
        frame = tk.Frame(nb, bg=BG)
        nb.add(frame, text="  Contact  ")

        wrap = tk.Frame(frame, bg=BG)
        wrap.pack(fill="both", expand=True)

        canvas = tk.Canvas(wrap, bg=BG, highlightthickness=0)
        sb = ttk.Scrollbar(wrap, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas, bg=BG)
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        inner.bind("<Configure>",
                   lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))

        c = self.info["contact"]
        form = tk.Frame(inner, bg=BG)
        form.pack(fill="x", padx=20, pady=20)
        form.columnconfigure(1, weight=1)

        self.v_phone = tk.StringVar(value=c.get("phone_number") or "")
        self._label(form, 0, "Phone number *")
        _mk_entry_raw(form, self.v_phone, 30).grid(
            row=0, column=1, sticky="ew", pady=6)

        self.v_status = tk.StringVar(value=c.get("status") or "unchecked")
        self._label(form, 1, "Status")
        _mk_combo(form, self.v_status, STATUSES, 20).grid(
            row=1, column=1, sticky="w", pady=6)

        self.f_name = FaEntry(form, c.get("name") or "", width=30)
        self._label(form, 2, "Name")
        self.f_name.widget.grid(row=2, column=1, sticky="ew", pady=6)

        self.f_last = FaEntry(form, c.get("last_name") or "", width=30)
        self._label(form, 3, "Last name")
        self.f_last.widget.grid(row=3, column=1, sticky="ew", pady=6)

        self.v_nc = tk.StringVar(value=c.get("national_code") or "")
        self._label(form, 4, "National code")
        _mk_entry_raw(form, self.v_nc, 30).grid(
            row=4, column=1, sticky="ew", pady=6)

        # ---- Photo ----
        tk.Label(form, text="Photo", bg=BG, fg=FG,
                 font=FONT_UI, anchor="nw").grid(
            row=5, column=0, sticky="nw", padx=(0, 10), pady=6)

        photo_row = tk.Frame(form, bg=BG)
        photo_row.grid(row=5, column=1, sticky="ew", pady=6)

        self.photo_preview = PhotoPreview(photo_row)
        self.photo_preview.pack(side="left")

        photo_right = tk.Frame(photo_row, bg=BG)
        photo_right.pack(side="left", fill="x", expand=True, padx=(12, 0))

        self.v_photo_path = tk.StringVar(value="")
        path_entry = tk.Entry(photo_right, textvariable=self.v_photo_path,
                              bg=BG_ENTRY, fg=FG_DIM, insertbackground=FG,
                              relief="flat", font=FONT_UI, width=40,
                              state="readonly", readonlybackground=BG_ENTRY)
        path_entry.pack(fill="x", pady=(0, 6))

        btn_row = tk.Frame(photo_right, bg=BG)
        btn_row.pack(fill="x")
        tk.Button(btn_row, text="Browse image...",
                  command=self._choose_photo,
                  bg=ACCENT, fg="white",
                  activebackground=ACCENT_HOV, activeforeground="white",
                  relief="flat", padx=10, pady=4, cursor="hand2",
                  font=FONT_UI).pack(side="left", padx=(0, 4))
        tk.Button(btn_row, text="Open folder",
                  command=self._open_photo_folder,
                  bg=BG_PANEL, fg=OK_GREEN,
                  activebackground=ACCENT_HOV, activeforeground="white",
                  relief="flat", padx=10, pady=4, cursor="hand2",
                  font=FONT_UI).pack(side="left", padx=4)
        tk.Button(btn_row, text="Clear",
                  command=self._clear_photo,
                  bg=BG_PANEL, fg=ERR_RED,
                  activebackground="#3a1c1c", activeforeground="white",
                  relief="flat", padx=10, pady=4, cursor="hand2",
                  font=FONT_UI).pack(side="left", padx=4)

        tk.Label(photo_right,
                 text=("Any image format is accepted. Images are stored "
                       "inside contacts.db as raw bytes + base64."),
                 bg=BG, fg=FG_DIM, justify="left", wraplength=380,
                 font=(FONT_UI[0], 9)).pack(anchor="w", pady=(8, 0))

        # Load existing primary image if there is one
        primary_id = self.info.get("primary_image_id")
        if primary_id is not None:
            data = core.get_contact_image_bytes(primary_id)
            if data:
                self.photo_preview.set_bytes(data)
                self.v_photo_path.set(f"stored image #{primary_id}")
        elif c.get("photo_path"):
            # legacy path
            self.photo_preview.set_path(c["photo_path"])
            self.v_photo_path.set(str(c["photo_path"]))

        # ---- Notes ----
        notes_label_frame = tk.Frame(form, bg=BG)
        notes_label_frame.grid(row=6, column=0, sticky="nw",
                               padx=(0, 10), pady=6)
        tk.Label(notes_label_frame, text="Notes",
                 bg=BG, fg=FG, font=FONT_UI, anchor="w").pack(anchor="w")
        tk.Label(notes_label_frame, text=fa("توضیحات"),
                 bg=BG, fg=FG, font=FONT_UI, anchor="w").pack(anchor="w")

        notes_wrap = tk.Frame(form, bg=BG_ENTRY,
                              highlightthickness=1,
                              highlightbackground="#3c3c3c")
        notes_wrap.grid(row=6, column=1, sticky="ew", pady=6)

        self.f_notes = FaText(notes_wrap, c.get("notes") or "",
                              height=5, width=40)
        self.f_notes.widget.pack(fill="both", expand=True)

        # ---- Flags ----
        self.v_pinned = tk.IntVar(value=1 if c.get("pinned") else 0)
        self.v_special = tk.IntVar(value=1 if c.get("special") else 0)

        flags = tk.Frame(form, bg=BG)
        flags.grid(row=7, column=0, columnspan=2, sticky="w", pady=(8, 4))

        tk.Checkbutton(
            flags, text="Pin to top", variable=self.v_pinned,
            bg=BG, fg=FG, selectcolor=BG_ENTRY,
            activebackground=BG, activeforeground="#ffcc66",
            font=FONT_UI,
        ).pack(side="left", padx=(0, 20))

        tk.Checkbutton(
            flags, text="Mark as special", variable=self.v_special,
            bg=BG, fg=FG, selectcolor=BG_ENTRY,
            activebackground=BG, activeforeground="#88ccff",
            font=FONT_UI,
        ).pack(side="left")

        if not HAS_BIDI:
            tk.Label(
                form,
                text=("Persian shaping is disabled.\n"
                      "Install with:\n"
                      "    pip install arabic-reshaper python-bidi"),
                bg=BG, fg="#f48771", justify="left",
                font=(FONT_UI[0], 9)
            ).grid(row=8, column=0, columnspan=2, sticky="w", pady=(12, 0))

    # --------------------------------------------------------
    # Photo actions
    # --------------------------------------------------------
    def _choose_photo(self):
        patterns = " ".join("*" + e for e in SUPPORTED_EXTS)
        p = filedialog.askopenfilename(
            title="Choose image",
            filetypes=[("Images", patterns), ("All files", "*.*")],
        )
        if not p:
            return
        self._pending_image_path = p
        self._pending_image_bytes = None
        self._clear_image = False
        self.v_photo_path.set(f"[pending] {Path(p).name}")
        self.photo_preview.set_path(p)

    def _clear_photo(self):
        if self.contact_id is None and not self._pending_image_path:
            return
        if not messagebox.askyesno(
            "Confirm", "Remove the primary photo for this contact?",
            parent=self,
        ):
            return
        self._pending_image_path = None
        self._pending_image_bytes = None
        self._clear_image = True
        self.v_photo_path.set("")
        self.photo_preview.set_bytes(None)

    def _open_photo_folder(self):
        if self.contact_id is None:
            messagebox.showinfo(
                "Open folder",
                "Save the contact first to create its attachment folder.",
                parent=self,
            )
            return
        core.open_contact_folder(self.contact_id)

    # --------------------------------------------------------
    def _build_platform_tab(self, nb, platform_info):
        name    = platform_info["name"]
        display = platform_info.get("display_name") or name.capitalize()

        if name in self.platform_tabs:
            return

        frame = tk.Frame(nb, bg=BG)
        nb.add(frame, text=f"  {fa(display)}  ")
        self.platform_tabs[name] = frame

        existing = self.social_map.get(name) or {}

        form = tk.Frame(frame, bg=BG)
        form.pack(fill="x", padx=20, pady=20)
        form.columnconfigure(1, weight=1)

        v_exists = tk.StringVar(value=existing.get("exists_status") or "unknown")
        v_ver    = tk.StringVar(value=existing.get("verified_status") or "unchecked")
        f_user   = FaEntry(form, existing.get("username") or "", width=32)
        f_disp   = FaEntry(form, existing.get("display_name") or "", width=32)
        v_uid    = tk.StringVar(value=existing.get("user_id") or "")

        self.platform_widgets[name] = {
            "exists":  v_exists,
            "ver":     v_ver,
            "user":    f_user,
            "disp":    f_disp,
            "uid":     v_uid,
            "had_row": bool(existing),
            "tab":     frame,
        }

        self._label(form, 0, "Status on this platform")
        _mk_combo(form, v_exists, EXISTS, 20).grid(
            row=0, column=1, sticky="w", pady=6)

        self._label(form, 1, "Username")
        f_user.widget.grid(row=1, column=1, sticky="ew", pady=6)

        self._label(form, 2, "Display name")
        f_disp.widget.grid(row=2, column=1, sticky="ew", pady=6)

        self._label(form, 3, "User ID")
        _mk_entry_raw(form, v_uid, 32).grid(
            row=3, column=1, sticky="ew", pady=6)

        self._label(form, 4, "Verified status")
        _mk_combo(form, v_ver, STATUSES, 20).grid(
            row=4, column=1, sticky="w", pady=6)

        if existing:
            tk.Button(frame, text=f"Remove {display} row",
                      command=lambda n=name: self._delete_social(n),
                      bg=BG_PANEL, fg=ERR_RED,
                      activebackground="#3a1c1c", activeforeground="white",
                      relief="flat", padx=10, pady=4, cursor="hand2",
                      font=FONT_UI).pack(anchor="w", padx=20, pady=(0, 12))

        tk.Label(frame,
                 text=("Leave all fields empty and Status = unknown\n"
                       "to keep this platform unused for this contact."),
                 bg=BG, fg=FG_DIM, justify="left",
                 font=(FONT_UI[0], 9)).pack(anchor="w", padx=20, pady=(4, 12))

    def _add_platform_dialog(self):
        name = simpledialog.askstring(
            "Add platform",
            "Platform name\n"
            "(lowercase letters, digits, underscore — starts with a letter)",
            parent=self,
        )
        if name is None:
            return
        name = name.strip()
        if not name:
            return

        display = simpledialog.askstring(
            "Add platform",
            f"Display name for '{name}' (leave empty to use '{name.capitalize()}'):",
            parent=self,
        )
        if display is None:
            return
        display = display.strip() or None

        try:
            new_name = core.add_platform(name, display)
        except Exception as e:
            messagebox.showerror("Add platform failed", str(e), parent=self)
            return

        self.platforms = core.list_platforms()
        info = next((p for p in self.platforms if p["name"] == new_name), None)
        if info is None:
            messagebox.showwarning(
                "Add platform",
                "Platform was created but could not be found in the registry.",
                parent=self,
            )
            return

        self._build_platform_tab(self.nb, info)

        frame = self.platform_tabs.get(new_name)
        if frame is not None:
            self.nb.select(frame)

        self.platform_added = True

    def _delete_social(self, platform):
        if not messagebox.askyesno(
            "Confirm", f"Remove the {platform} row for this contact?"
        ):
            return
        if self.contact_id:
            try:
                core.delete_social(self.contact_id, platform)
            except Exception as e:
                messagebox.showerror("Error", str(e), parent=self)
                return
        self.social_map.pop(platform, None)
        w = self.platform_widgets.get(platform)
        if not w:
            return
        w["exists"].set("unknown")
        w["ver"].set("unchecked")
        w["user"].clear()
        w["disp"].clear()
        w["uid"].set("")
        w["had_row"] = False

    def _read_notes(self):
        try:
            raw = self.f_notes.get()
        except Exception:
            raw = None
        return raw or ""

    def _apply_image_action(self):
        if self.contact_id is None:
            return
        try:
            if self._pending_image_path:
                img_id = core.add_contact_image(
                    self.contact_id,
                    self._pending_image_path,
                    set_primary=True,
                )
                self.v_photo_path.set(f"stored image #{img_id}")
            elif self._pending_image_bytes:
                img_id = core.add_contact_image_from_bytes(
                    self.contact_id,
                    self._pending_image_bytes,
                    name="image",
                    set_primary=True,
                )
                self.v_photo_path.set(f"stored image #{img_id}")
            elif self._clear_image:
                primary_id = core.get_primary_image_id(self.contact_id)
                if primary_id is not None:
                    core.delete_contact_image(primary_id)
                self.v_photo_path.set("")
        except Exception as e:
            messagebox.showerror("Image error", str(e), parent=self)

    def _save(self):
        phone_raw = self.v_phone.get().strip()
        phone_norm = normalize_phone(phone_raw)
        if not phone_norm:
            messagebox.showerror(
                "Invalid phone",
                "Please enter a valid Iranian mobile number.",
                parent=self,
            )
            return

        data = {
            "phone":          phone_norm,
            "status":         self.v_status.get(),
            "name":           self.f_name.get(),
            "last_name":      self.f_last.get(),
            "national_code":  self.v_nc.get().strip() or None,
            "notes":          self._read_notes(),
            "pinned":         bool(self.v_pinned.get()),
            "special":        bool(self.v_special.get()),
        }

        try:
            if self.contact_id is None:
                self.contact_id = core.create_contact(**data)
            else:
                core.update_contact(self.contact_id, **data)
        except Exception as e:
            messagebox.showerror("Save failed", str(e), parent=self)
            return

        self._apply_image_action()

        try:
            for platform, w in self.platform_widgets.items():
                exists = w["exists"].get()
                user   = w["user"].get()
                disp   = w["disp"].get()
                uid    = w["uid"].get().strip() or None
                ver    = w["ver"].get()

                if (not w["had_row"]
                        and exists == "unknown"
                        and not user and not disp and not uid):
                    continue

                core.update_social(
                    self.contact_id, platform,
                    exists_status=exists,
                    username=user,
                    display_name=disp,
                    user_id=uid,
                    verified_status=ver,
                )
        except Exception as e:
            messagebox.showerror("Save failed (socials)", str(e), parent=self)
            return

        self.result = True
        self.destroy()

    def _delete(self):
        if not self.contact_id:
            return
        if not messagebox.askyesno(
            "Confirm",
            f"Delete contact #{self.contact_id} and all its files?\n"
            "This cannot be undone (unless you restore from a backup).",
            parent=self,
        ):
            return
        try:
            core.delete_contact(self.contact_id)
        except Exception as e:
            messagebox.showerror("Delete failed", str(e), parent=self)
            return
        self.result = "deleted"
        self.destroy()
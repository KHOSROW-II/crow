"""
GUI dialog for managing external data sources.
"""

import sys
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import core
from db import list_platforms

BG         = "#1e1e1e"
BG_PANEL   = "#252526"
BG_ENTRY   = "#1b1b1b"
FG         = "#d4d4d4"
FG_DIM     = "#808080"
ACCENT     = "#0e639c"
ACCENT_HOV = "#1177bb"
BORDER     = "#3c3c3c"
OK_GREEN   = "#4ec9b0"
ERR_RED    = "#f48771"
SEL_BG     = "#094771"

FONT_UI   = ("Tahoma", 10) if sys.platform == "win32" else ("Sans", 10)
FONT_MONO = ("Consolas", 10) if sys.platform == "win32" else ("Monospace", 10)

MATCHER_LABELS = {
    "phone":         "Phone number",
    "national_code": "National code",
    "name_family":   "Name + family",
}


def _mk_entry(parent, var, width=32):
    return tk.Entry(parent, textvariable=var, width=width,
                    bg=BG_ENTRY, fg=FG, insertbackground=FG,
                    relief="flat", font=FONT_UI)


class SourceManager(tk.Toplevel):
    """
    Table list + edit form for external data sources.
    Sets self.changed=True if any source was modified.
    """

    def __init__(self, parent):
        super().__init__(parent)
        self.title("Data sources")
        self.configure(bg=BG)
        self.geometry("860x620")
        self.minsize(760, 560)
        self.transient(parent)
        self.grab_set()

        self.changed = False
        self._build()
        self._reload()

    def _build(self):
        bar = tk.Frame(self, bg=BG)
        bar.pack(fill="x", padx=8, pady=(8, 4))

        tk.Button(bar, text="Add", command=self._add,
                  bg="#2d5a2d", fg="white",
                  activebackground="#3a7a3a", activeforeground="white",
                  relief="flat", padx=14, pady=6, cursor="hand2",
                  font=FONT_UI).pack(side="left", padx=3)

        tk.Button(bar, text="Edit", command=self._edit,
                  bg=ACCENT, fg="white",
                  activebackground=ACCENT_HOV, activeforeground="white",
                  relief="flat", padx=14, pady=6, cursor="hand2",
                  font=FONT_UI).pack(side="left", padx=3)

        tk.Button(bar, text="Remove", command=self._remove,
                  bg="#5a2d2d", fg="white",
                  activebackground="#7a3a3a", activeforeground="white",
                  relief="flat", padx=14, pady=6, cursor="hand2",
                  font=FONT_UI).pack(side="left", padx=3)

        tk.Button(bar, text="Resync all", command=self._resync_all,
                  bg=BG_PANEL, fg=OK_GREEN,
                  activebackground=ACCENT_HOV, activeforeground="white",
                  relief="flat", padx=14, pady=6, cursor="hand2",
                  font=FONT_UI).pack(side="left", padx=3)

        tk.Button(bar, text="Close", command=self.destroy,
                  bg=BG_PANEL, fg=FG,
                  activebackground=ACCENT_HOV, activeforeground="white",
                  relief="flat", padx=14, pady=6, cursor="hand2",
                  font=FONT_UI).pack(side="right", padx=3)

        wrap = tk.Frame(self, bg=BG)
        wrap.pack(fill="both", expand=True, padx=8, pady=4)

        cols = ("code", "name", "label", "db_path", "table",
                "enabled", "builtin")
        heads = ("Code", "Name", "Label", "DB path", "Table",
                 "Enabled", "Built-in")
        widths = {"code": 50, "name": 110, "label": 140, "db_path": 180,
                  "table": 140, "enabled": 70, "builtin": 70}

        self.tree = ttk.Treeview(wrap, columns=cols, show="headings")
        for c, h in zip(cols, heads):
            self.tree.heading(c, text=h)
            self.tree.column(c, width=widths[c],
                             anchor="center" if c in ("code", "enabled", "builtin")
                             else "w",
                             stretch=False)

        vs = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vs.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vs.grid(row=0, column=1, sticky="ns")
        wrap.rowconfigure(0, weight=1)
        wrap.columnconfigure(0, weight=1)

        self.tree.bind("<Double-1>", lambda _e: self._edit())

        tk.Label(self,
                 text=("Each source is an external SQLite database.\n"
                       "Add a source once and it will be used automatically "
                       "during sync, search and detail views.\n"
                       "Built-in sources (identity, telegram) cannot be removed."),
                 bg=BG, fg=FG_DIM, justify="left",
                 font=(FONT_UI[0], 9)).pack(anchor="w", padx=14, pady=(4, 10))

    def _reload(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        for s in core.list_data_sources():
            self.tree.insert("", "end", iid=s["name"],
                             values=(s["code"], s["name"], s["label"],
                                     s["db_path"], s["table_name"],
                                     "yes" if s["enabled"] else "no",
                                     "yes" if s["is_builtin"] else "no"))

    def _selected(self):
        sel = self.tree.selection()
        return sel[0] if sel else None

    def _add(self):
        dlg = SourceEditDialog(self, source_name=None)
        self.wait_window(dlg)
        if dlg.result:
            self.changed = True
            self._reload()

    def _edit(self):
        name = self._selected()
        if not name:
            messagebox.showinfo("Edit", "Select a source first.", parent=self)
            return
        dlg = SourceEditDialog(self, source_name=name)
        self.wait_window(dlg)
        if dlg.result:
            self.changed = True
            self._reload()

    def _remove(self):
        name = self._selected()
        if not name:
            messagebox.showinfo("Remove", "Select a source first.", parent=self)
            return
        if not messagebox.askyesno(
            "Confirm",
            f"Remove source '{name}'?\n"
            "All contact_links pointing to it will be deleted.\n"
            "The external database file itself is NOT deleted.",
            parent=self,
        ):
            return
        try:
            core.remove_data_source(name)
        except Exception as e:
            messagebox.showerror("Remove failed", str(e), parent=self)
            return
        self.changed = True
        self._reload()

    def _resync_all(self):
        try:
            total = core.run_sync()
        except Exception as e:
            messagebox.showerror("Sync failed", str(e), parent=self)
            return
        self.changed = True
        self._reload()
        messagebox.showinfo("Sync", f"Sync finished. Total matches: {total}",
                            parent=self)


class SourceEditDialog(tk.Toplevel):
    """Add / edit a single data source."""

    def __init__(self, parent, source_name=None):
        super().__init__(parent)
        self.source_name = source_name
        self.result = None

        self.title(f"Edit source: {source_name}" if source_name
                   else "New data source")
        self.configure(bg=BG)
        self.geometry("700x680")
        self.minsize(620, 600)
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
        if self.source_name:
            src = core.get_data_source(self.source_name)
            if not src:
                raise ValueError(f"Source '{self.source_name}' not found.")
        else:
            src = {
                "name": "", "label": "", "code": "",
                "db_path": "", "table_name": "", "pk_column": "id",
                "phone_fields": [], "name_columns": [],
                "national_code_column": "", "matchers": ["phone"],
                "create_missing": 0, "social_platform": None,
                "enabled": 1, "sort_order": 100,
            }
        self.src = src

    def _build(self):
        form = tk.Frame(self, bg=BG)
        form.pack(fill="x", padx=16, pady=(16, 4))
        form.columnconfigure(1, weight=1)

        def row(r, label, widget):
            tk.Label(form, text=label, bg=BG, fg=FG, font=FONT_UI,
                     anchor="w").grid(row=r, column=0, sticky="w",
                                      padx=(0, 10), pady=6)
            widget.grid(row=r, column=1, sticky="ew", pady=6)

        self.v_name  = tk.StringVar(value=self.src["name"])
        self.v_label = tk.StringVar(value=self.src["label"])
        self.v_code  = tk.StringVar(value=self.src["code"])
        self.v_db    = tk.StringVar(value=self.src["db_path"])
        self.v_table = tk.StringVar(value=self.src["table_name"])
        self.v_pk    = tk.StringVar(value=self.src["pk_column"] or "id")

        # name (only editable on create)
        e_name = _mk_entry(form, self.v_name, 30)
        if self.source_name:
            e_name.configure(state="disabled")
        row(0, "Name (id) *", e_name)
        row(1, "Label *",     _mk_entry(form, self.v_label, 30))
        row(2, "Code * (1-2 chars, e.g. I, T, W)", _mk_entry(form, self.v_code, 6))

        db_row = tk.Frame(form, bg=BG)
        db_row.columnconfigure(0, weight=1)
        e_db = _mk_entry(db_row, self.v_db, 26)
        e_db.grid(row=0, column=0, sticky="ew")
        tk.Button(db_row, text="Browse…", command=self._browse_db,
                  bg=BG_PANEL, fg=FG, activebackground=ACCENT_HOV,
                  activeforeground="white", relief="flat",
                  padx=8, pady=2, cursor="hand2",
                  font=FONT_UI).grid(row=0, column=1, padx=(6, 0))
        row(3, "Database path *", db_row)

        row(4, "Table name *", _mk_entry(form, self.v_table, 30))
        row(5, "Primary key column", _mk_entry(form, self.v_pk, 12))

        self.v_phones = tk.StringVar(value=", ".join(self.src["phone_fields"]))
        row(6, "Phone fields (comma-separated)",
            _mk_entry(form, self.v_phones, 30))

        self.v_names = tk.StringVar(value=", ".join(self.src["name_columns"]))
        row(7, "Name columns (first, last)",
            _mk_entry(form, self.v_names, 30))

        self.v_nc = tk.StringVar(value=self.src["national_code_column"] or "")
        row(8, "National code column",
            _mk_entry(form, self.v_nc, 30))

        # matchers
        tk.Label(form, text="Matchers *", bg=BG, fg=FG, font=FONT_UI,
                 anchor="w").grid(row=9, column=0, sticky="nw",
                                  padx=(0, 10), pady=6)
        box = tk.Frame(form, bg=BG)
        box.grid(row=9, column=1, sticky="w", pady=6)
        self.v_m_phone = tk.IntVar(value=1 if "phone" in self.src["matchers"] else 0)
        self.v_m_nc    = tk.IntVar(value=1 if "national_code" in self.src["matchers"] else 0)
        self.v_m_name  = tk.IntVar(value=1 if "name_family" in self.src["matchers"] else 0)
        for var, label in ((self.v_m_phone, MATCHER_LABELS["phone"]),
                           (self.v_m_nc, MATCHER_LABELS["national_code"]),
                           (self.v_m_name, MATCHER_LABELS["name_family"])):
            tk.Checkbutton(box, text=label, variable=var,
                           bg=BG, fg=FG, selectcolor=BG_ENTRY,
                           activebackground=BG, activeforeground=OK_GREEN,
                           font=FONT_UI).pack(anchor="w")

        # create missing + enabled
        self.v_create = tk.IntVar(value=1 if self.src["create_missing"] else 0)
        self.v_enabled = tk.IntVar(value=1 if self.src["enabled"] else 0)

        opts = tk.Frame(form, bg=BG)
        opts.grid(row=10, column=0, columnspan=2, sticky="w", pady=(10, 4))
        tk.Checkbutton(opts, text="Create missing contacts (uses first phone field)",
                       variable=self.v_create,
                       bg=BG, fg=FG, selectcolor=BG_ENTRY,
                       activebackground=BG, activeforeground=OK_GREEN,
                       font=FONT_UI).pack(anchor="w")
        tk.Checkbutton(opts, text="Enabled",
                       variable=self.v_enabled,
                       bg=BG, fg=FG, selectcolor=BG_ENTRY,
                       activebackground=BG, activeforeground=OK_GREEN,
                       font=FONT_UI).pack(anchor="w")

        # social platform
        tk.Label(form, text="Write social row for platform",
                 bg=BG, fg=FG, font=FONT_UI, anchor="w").grid(
            row=11, column=0, sticky="w", padx=(0, 10), pady=6)
        plats = ["(none)"] + [p["name"] for p in list_platforms()]
        current = self.src.get("social_platform") or "(none)"
        self.v_platform = tk.StringVar(value=current)
        ttk.Combobox(form, textvariable=self.v_platform, values=plats,
                     state="readonly", width=20).grid(
            row=11, column=1, sticky="w", pady=6)

        bar = tk.Frame(self, bg=BG)
        bar.pack(fill="x", padx=16, pady=(8, 12))
        tk.Button(bar, text="Save", command=self._save,
                  bg="#2d5a2d", fg="white",
                  activebackground="#3a7a3a", activeforeground="white",
                  relief="flat", padx=18, pady=6, cursor="hand2",
                  font=FONT_UI).pack(side="left", padx=3)
        tk.Button(bar, text="Cancel", command=self.destroy,
                  bg=BG_PANEL, fg=FG,
                  activebackground=ACCENT_HOV, activeforeground="white",
                  relief="flat", padx=18, pady=6, cursor="hand2",
                  font=FONT_UI).pack(side="left", padx=3)

        self.bind("<Escape>", lambda _e: self.destroy())
        self.bind("<Control-s>", lambda _e: self._save())

    def _browse_db(self):
        p = filedialog.askopenfilename(
            title="Choose database",
            filetypes=[("SQLite", "*.db *.sqlite *.sqlite3"),
                       ("All files", "*.*")],
        )
        if p:
            self.v_db.set(p)

    def _save(self):
        def _split(s):
            return [x.strip() for x in (s or "").split(",") if x.strip()]

        matchers = []
        if self.v_m_phone.get(): matchers.append("phone")
        if self.v_m_nc.get():    matchers.append("national_code")
        if self.v_m_name.get():  matchers.append("name_family")

        platform = self.v_platform.get()
        if platform == "(none)":
            platform = None

        data = {
            "name":                 self.v_name.get().strip().lower(),
            "label":                self.v_label.get().strip() or self.v_name.get().strip(),
            "code":                 self.v_code.get().strip() or "?",
            "db_path":              self.v_db.get().strip(),
            "table_name":           self.v_table.get().strip(),
            "pk_column":            self.v_pk.get().strip() or "id",
            "phone_fields":         _split(self.v_phones.get()),
            "name_columns":         _split(self.v_names.get()),
            "national_code_column": self.v_nc.get().strip() or None,
            "matchers":             matchers,
            "create_missing":       bool(self.v_create.get()),
            "social_platform":      platform,
            "enabled":              bool(self.v_enabled.get()),
            "sort_order":           self.src.get("sort_order", 100),
        }

        try:
            if self.source_name:
                core.update_data_source(self.source_name, data)
            else:
                core.add_data_source(data)
        except Exception as e:
            messagebox.showerror("Save failed", str(e), parent=self)
            return
        self.result = True
        self.destroy()


# ------------------------------------------------------------
def run_source_manager(parent):
    dlg = SourceManager(parent)
    parent.wait_window(dlg)
    return dlg.changed
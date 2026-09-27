"""
Tkinter GUI - dark terminal style.

Features:
    - Compact / expanded platform view
    - Double-click platform cell -> popup with full social record
    - Photo column with preview + attachments folder
    - Images stored inside contacts.db (raw + base64)
    - Notes with Persian shaping
    - Pin / Special flags
    - Sources column from data_sources registry
    - Custom tables, custom platforms, backups
    - Maltego import
"""

import csv
import io
import json
import os
import subprocess
import sys
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
from pathlib import Path
from typing import Any
from branding import APP_NAME, APP_TITLE, APP_DESCRIPTION

import core
import backup as bk
from db import ensure_schema, DB_PATH, IDENTITY_DB, list_custom_tables
from text_utils import fa, fa_lines, HAS_BIDI
from image_utils import (
    load_photo_for_tk,
    load_photo_for_tk_from_bytes,
    SUPPORTED_EXTS,
)
from edit_dialog import ContactEditDialog
from platform_manager import PlatformManager
from custom_tables import TableManager, CustomTableBrowser
from source_manager import run_source_manager
import maltego_import

BG          = "#1e1e1e"
BG_PANEL    = "#252526"
BG_ENTRY    = "#1b1b1b"
FG          = "#d4d4d4"
FG_DIM      = "#808080"
ACCENT      = "#0e639c"
ACCENT_HOV  = "#1177bb"
BORDER      = "#3c3c3c"
OK_GREEN    = "#4ec9b0"
SEL_BG      = "#094771"
PIN_FG      = "#ffcc66"
SPECIAL_FG  = "#88ccff"

FONT_MONO = ("Consolas", 10) if sys.platform == "win32" else ("Monospace", 10)
FONT_UI   = ("Tahoma", 10)   if sys.platform == "win32" else ("Sans", 10)

PLAT_COL_PREFIX = "plat_"
PLAT_COL_WIDTH  = 70


# ============================================================
# Module-level helpers
# ============================================================
def open_folder(path: str):
    p = Path(path).resolve()
    p.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        os.startfile(str(p))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(p)])
    else:
        subprocess.Popen(["xdg-open", str(p)])


def _add_section(txt: tk.Text, title: str) -> None:
    txt.insert("end", f"\n=== {title} ===\n", ("h",))


def _add_kv(txt: tk.Text, key: str, value) -> None:
    txt.insert("end", f"{key:22s}: {fa(value)}\n")


# ============================================================
# Application
# ============================================================
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1540x880")
        self.minsize(1100, 680)
        self.configure(bg=BG)

        self.search_var = tk.StringVar()
        self.status_var = tk.StringVar(value="all")
        self.filter_var = tk.StringVar(value="all")
        self.source_var = tk.StringVar(value="all")

        self.compact_platforms = tk.BooleanVar(value=False)
        self.show_photo_only  = tk.BooleanVar(value=False)

        self._row_raw: dict[int, dict[str, Any]] = {}
        self._image_refs: dict[str, Any] = {}

        self._build_style()
        self._build_menu()
        self._build_searchbar()
        self._build_table()
        self._build_log()
        self._build_status()

        core.set_logger(self.append_log)

        self.after(100, self.refresh_table)
        if HAS_BIDI:
            self.log_line("Persian shaping: enabled.")
        else:
            self.log_line("Persian shaping: disabled. "
                          "Run: pip install arabic-reshaper python-bidi")

    # --------------------------------------------------------
    # Style
    # --------------------------------------------------------
    def _build_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("Treeview",
                        background=BG_PANEL, fieldbackground=BG_PANEL,
                        foreground=FG, rowheight=28, borderwidth=0,
                        font=FONT_UI)
        style.configure("Treeview.Heading",
                        background=BORDER, foreground=FG,
                        relief="flat",
                        font=(FONT_UI[0], FONT_UI[1], "bold"))
        style.map("Treeview",
                  background=[("selected", SEL_BG)],
                  foreground=[("selected", "white")])
        style.configure("TEntry",
                        fieldbackground=BG_ENTRY, foreground=FG,
                        insertcolor=FG)
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab",
                        background=BG_PANEL, foreground=FG,
                        padding=[10, 4])
        style.map("TNotebook.Tab",
                  background=[("selected", ACCENT)],
                  foreground=[("selected", "white")])

    # --------------------------------------------------------
    # Menu
    # --------------------------------------------------------
    def _menu_kwargs(self) -> dict[str, Any]:
        return dict(tearoff=0, bg=BG_PANEL, fg=FG,
                    activebackground=ACCENT, activeforeground="white",
                    selectcolor=ACCENT)

    def _build_menu(self):
        bar = tk.Menu(self, bg=BG_PANEL, fg=FG,
                      activebackground=ACCENT, activeforeground="white",
                      tearoff=0)
        kw = self._menu_kwargs()

        file_m = tk.Menu(bar, **kw)
        file_m.add_command(label="New contact", accelerator="Ctrl+N",
                           command=self.act_new)
        file_m.add_command(label="Edit selected", accelerator="Ctrl+E",
                           command=self.act_edit_selected)
        file_m.add_command(label="Delete selected", accelerator="Del",
                           command=self.act_delete_selected)
        file_m.add_separator()
        file_m.add_command(label="Import from tempinput.json",
                           command=self.act_import_default)
        file_m.add_command(label="Import from JSON file ...",
                           command=self.act_import_file)
        file_m.add_command(label="Import Maltego file ...",
                           command=self.act_import_maltego)
        file_m.add_separator()
        file_m.add_command(label="Export CSV ...", command=self.act_export_csv)
        file_m.add_command(label="Export Excel ...", command=self.act_export_excel)
        file_m.add_separator()
        file_m.add_command(label="Exit", command=self.destroy)

        data_m = tk.Menu(bar, **kw)
        data_m.add_command(label="Sync databases", command=self.act_sync)
        data_m.add_separator()
        data_m.add_command(label="Manage data sources ...",
                           command=self.act_manage_sources)
        data_m.add_command(label="Manage platforms ...",
                           command=self.act_manage_platforms)
        data_m.add_separator()
        data_m.add_command(label="Migrate legacy photo_path -> DB",
                           command=self.act_migrate_photos)
        data_m.add_separator()
        data_m.add_command(label="Open attachments folder",
                           command=lambda: open_folder("attachments"))
        data_m.add_command(label="Open backups folder",
                           command=lambda: open_folder("backups"))
        data_m.add_command(label="Open reports folder",
                           command=lambda: open_folder("reports"))
        data_m.add_separator()
        data_m.add_command(label="Backup now ...", command=self.act_backup)
        data_m.add_command(label="Restore ...", command=self.act_restore)

        self.tables_menu = tk.Menu(bar, **kw)
        bar.add_cascade(label="Tables", menu=self.tables_menu)
        self._rebuild_tables_menu()

        sel_m = tk.Menu(bar, **kw)
        sel_m.add_command(label="Edit selected", accelerator="Ctrl+E",
                          command=self.act_edit_selected)
        sel_m.add_command(label="View details", accelerator="Double-click",
                          command=self._open_detail)
        sel_m.add_separator()
        sel_m.add_command(label="Toggle pin", accelerator="Ctrl+P",
                          command=self.act_toggle_pin)
        sel_m.add_command(label="Toggle special", accelerator="Ctrl+T",
                          command=self.act_toggle_special)
        sel_m.add_separator()
        sel_m.add_command(label="Open attachments folder",
                          command=self.act_open_selected_folder)
        sel_m.add_separator()

        copy_m = tk.Menu(sel_m, **kw)
        copy_m.add_command(label="Phone number", command=self._copy_phone)
        copy_m.add_separator()
        copy_m.add_command(label="Row (tab-separated)", command=self._copy_row_tsv)
        copy_m.add_command(label="Row as CSV", command=self._copy_row_csv)
        copy_m.add_command(label="Selected rows as CSV", command=self._copy_selected_csv)
        copy_m.add_separator()
        copy_m.add_command(label="Full record (text)", command=self._copy_record_text)
        copy_m.add_command(label="Full record (JSON)", command=self._copy_record_json)
        sel_m.add_cascade(label="Copy", menu=copy_m)
        sel_m.add_separator()
        sel_m.add_command(label="Delete selected", accelerator="Del",
                          command=self.act_delete_selected)

        filters_m = tk.Menu(bar, **kw)

        status_m = tk.Menu(filters_m, **kw)
        for val, label in [("all", "All"),
                           ("unchecked", "Unchecked"),
                           ("checking", "Checking"),
                           ("verified", "Verified"),
                           ("invalid", "Invalid"),
                           ("anonymous", "Anonymous")]:
            status_m.add_radiobutton(label=fa(label), variable=self.status_var,
                                     value=val, command=self.refresh_table)
        filters_m.add_cascade(label="Status", menu=status_m)

        self.platform_m = tk.Menu(filters_m, **kw)
        self._rebuild_platform_menu()
        filters_m.add_cascade(label="Quick / Platform", menu=self.platform_m)

        self.source_filter_m = tk.Menu(filters_m, **kw)
        self._rebuild_source_filter_menu()
        filters_m.add_cascade(label="Source", menu=self.source_filter_m)

        filters_m.add_separator()
        filters_m.add_checkbutton(label="With photo only",
                                  variable=self.show_photo_only,
                                  command=self.refresh_table)
        filters_m.add_separator()
        filters_m.add_command(label="Clear all filters",
                              command=self._clear_search)

        view_m = tk.Menu(bar, **kw)
        view_m.add_command(label="Refresh", accelerator="F5",
                           command=self.refresh_table)
        view_m.add_separator()
        view_m.add_checkbutton(label="Compact platform view (single column)",
                               variable=self.compact_platforms,
                               command=self._toggle_compact_mode)
        view_m.add_separator()
        view_m.add_command(label="Show pinned only",
                           command=lambda: self._set_quick_filter("pinned"))
        view_m.add_command(label="Show special only",
                           command=lambda: self._set_quick_filter("special"))
        view_m.add_command(label="Show all", command=self._clear_search)

        help_m = tk.Menu(bar, **kw)
        help_m.add_command(label="Sources legend", command=self.act_legend)
        help_m.add_command(label="Keyboard shortcuts", command=self.act_shortcuts)
        help_m.add_command(label="About", command=self.act_about)

        bar.add_cascade(label="File", menu=file_m)
        bar.add_cascade(label="Data", menu=data_m)
        bar.add_cascade(label="Selection", menu=sel_m)
        bar.add_cascade(label="Filters", menu=filters_m)
        bar.add_cascade(label="View", menu=view_m)
        bar.add_cascade(label="Help", menu=help_m)
        self.config(menu=bar)

    def _rebuild_tables_menu(self):
        self.tables_menu.delete(0, "end")
        self.tables_menu.add_command(label="Manage tables ...",
                                     command=self.act_manage_tables)
        self.tables_menu.add_separator()
        tables = list_custom_tables()
        if not tables:
            self.tables_menu.add_command(
                label="(no custom tables yet)", state="disabled")
        else:
            for t in tables:
                self.tables_menu.add_command(
                    label=fa(t["display_name"] or t["name"]),
                    command=lambda n=t["name"]: self.act_open_custom_table(n),
                )
        self.tables_menu.add_separator()
        self.tables_menu.add_command(label="Refresh table list",
                                     command=self._rebuild_tables_menu)

    def _rebuild_platform_menu(self):
        self.platform_m.delete(0, "end")
        kw = self._menu_kwargs()
        for val, label in [("all", "All"),
                           ("pinned", "Pinned only"),
                           ("special", "Special only"),
                           ("has_identity", "With identity"),
                           ("no_identity", "No identity"),
                           ("with_photo", "With photo"),
                           ("no_photo", "Without photo")]:
            self.platform_m.add_radiobutton(label=label,
                                            variable=self.filter_var,
                                            value=val,
                                            command=self.refresh_table)
        self.platform_m.add_separator()
        for p in core.list_platforms():
            name = p["name"]
            disp = fa(p["display_name"] or name.capitalize())
            sub = tk.Menu(self.platform_m, **kw)
            for v, l in [("any", "Any"), ("yes", "Yes"),
                         ("no", "No"), ("unknown", "Unknown")]:
                value = name if v == "any" else f"{name}_{v}"
                sub.add_radiobutton(label=l, variable=self.filter_var,
                                    value=value, command=self.refresh_table)
            self.platform_m.add_cascade(label=disp, menu=sub)

    def _rebuild_source_filter_menu(self):
        self.source_filter_m.delete(0, "end")
        kw = self._menu_kwargs()
        self.source_filter_m.add_radiobutton(
            label="All", variable=self.source_var, value="all",
            command=self.refresh_table)
        self.source_filter_m.add_radiobutton(
            label="Only contacts (no external link)",
            variable=self.source_var, value="only_contacts",
            command=self.refresh_table)
        self.source_filter_m.add_separator()
        for s in core.list_data_sources():
            self.source_filter_m.add_radiobutton(
                label=fa(f"With {s['label']} ({s['name']})"),
                variable=self.source_var, value=f"with_{s['name']}",
                command=self.refresh_table)

    def _set_quick_filter(self, value):
        self.filter_var.set(value)
        self.refresh_table()

    # --------------------------------------------------------
    # Search bar
    # --------------------------------------------------------
    def _build_searchbar(self):
        bar = tk.Frame(self, bg=BG_PANEL, pady=8, padx=8)
        bar.pack(fill="x", padx=6, pady=(6, 0))
        tk.Label(bar, text="Search:", bg=BG_PANEL, fg=FG,
                 font=FONT_UI).pack(side="left", padx=(2, 6))
        e = tk.Entry(bar, textvariable=self.search_var,
                     bg=BG_ENTRY, fg=FG, insertbackground=FG,
                     relief="flat", font=FONT_UI, width=40)
        e.pack(side="left", padx=(0, 6), ipady=4)
        e.bind("<Return>", lambda _e: self.refresh_table())
        tk.Button(bar, text="Search", command=self.refresh_table,
                  bg=ACCENT, fg="white", activebackground=ACCENT_HOV,
                  activeforeground="white", relief="flat",
                  padx=14, pady=4, cursor="hand2",
                  font=FONT_UI).pack(side="left", padx=3)
        tk.Button(bar, text="Clear", command=self._clear_search,
                  bg=BG_PANEL, fg=FG, activebackground=ACCENT_HOV,
                  activeforeground="white", relief="flat",
                  padx=14, pady=4, cursor="hand2",
                  font=FONT_UI).pack(side="left", padx=3)
        self.filter_label = tk.Label(bar, text="", bg=BG_PANEL, fg=FG_DIM,
                                     font=(FONT_UI[0], 9), anchor="w")
        self.filter_label.pack(side="left", padx=(20, 0))

    def _filter_summary(self):
        parts = []
        if self.status_var.get() != "all":
            parts.append(f"status={self.status_var.get()}")
        if self.filter_var.get() != "all":
            parts.append(f"quick={self.filter_var.get()}")
        if self.source_var.get() != "all":
            parts.append(f"source={self.source_var.get()}")
        if self.show_photo_only.get():
            parts.append("photo=yes")
        q = self.search_var.get().strip()
        if q:
            parts.append(f"search='{q}'")
        mode = "compact" if self.compact_platforms.get() else "expanded"
        parts.append(f"view={mode}")
        return "Filters: " + ", ".join(parts)

    def _update_filter_label(self):
        self.filter_label.config(text=self._filter_summary())

    def _clear_search(self):
        self.search_var.set("")
        self.status_var.set("all")
        self.filter_var.set("all")
        self.source_var.set("all")
        self.show_photo_only.set(False)
        self.refresh_table()

    # --------------------------------------------------------
    # Table
    # --------------------------------------------------------
    def _build_table(self):
        wrap = tk.Frame(self, bg=BG)
        wrap.pack(fill="both", expand=True, padx=6, pady=6)
        self._table_wrap = wrap
        self.tree = ttk.Treeview(wrap, columns=(), show="headings",
                                 selectmode="extended")
        vs = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        hs = ttk.Scrollbar(wrap, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vs.set, xscrollcommand=hs.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vs.grid(row=0, column=1, sticky="ns")
        hs.grid(row=1, column=0, sticky="ew")
        wrap.rowconfigure(0, weight=1)
        wrap.columnconfigure(0, weight=1)
        self.tree.tag_configure("verified",  background="#1c3a1c")
        self.tree.tag_configure("invalid",   background="#3a1c1c")
        self.tree.tag_configure("checking",  background="#3a3a1c")
        self.tree.tag_configure("anonymous", background="#2a1c3a")
        self.tree.tag_configure("pinned",    foreground=PIN_FG)
        self.tree.tag_configure("special",   foreground=SPECIAL_FG)
        self.tree.bind("<Double-1>", self._on_tree_double_click)
        self.tree.bind("<Button-3>", self._show_context_menu)
        self.tree.bind("<Button-2>", self._show_context_menu)
        self.bind("<Control-n>", lambda _e: self.act_new())
        self.bind("<Control-e>", lambda _e: self.act_edit_selected())
        self.bind("<Control-p>", lambda _e: self.act_toggle_pin())
        self.bind("<Control-t>", lambda _e: self.act_toggle_special())
        self.bind("<F2>",        lambda _e: self.act_edit_selected())
        self.bind("<Delete>",    lambda _e: self.act_delete_selected())
        self.bind("<F5>",        lambda _e: self.refresh_table())
        self._build_context_menu()
        self._rebuild_columns()

    def _rebuild_columns(self):
        plats = core.list_platforms()
        base_cols  = ["photo", "phone", "status", "flags", "sources",
                      "name", "family"]
        base_heads = ["IMG", "Phone", "Status", "Flags", "Src",
                      "Name", "Family"]
        base_widths = {"photo": 40, "phone": 105, "status": 75,
                       "flags": 55, "sources": 65,
                       "name": 110, "family": 160}
        tail_cols  = ["city", "nc"]
        tail_heads = ["City", "National code"]
        tail_widths = {"city": 90, "nc": 100}
        if self.compact_platforms.get():
            mid_cols = ["platforms"]
            mid_heads = ["Platforms"]
            mid_widths = {"platforms": 320}
        else:
            mid_cols = [f"{PLAT_COL_PREFIX}{p['name']}" for p in plats]
            mid_heads = [fa(p["display_name"] or p["name"]) for p in plats]
            mid_widths = {f"{PLAT_COL_PREFIX}{p['name']}": PLAT_COL_WIDTH
                          for p in plats}
        cols  = base_cols + mid_cols + tail_cols
        heads = base_heads + mid_heads + tail_heads
        widths = {**base_widths, **mid_widths, **tail_widths}
        self.tree["columns"] = cols
        self.tree["show"] = "headings"
        for c, h in zip(cols, heads):
            self.tree.heading(c, text=h)
            anchor = "center" if c in ("photo", "status", "flags", "sources") \
                     or c.startswith(PLAT_COL_PREFIX) else "w"
            self.tree.column(c, width=widths[c], anchor=anchor, stretch=False)

    def _toggle_compact_mode(self):
        self._rebuild_columns()
        self.refresh_table()

    def _build_context_menu(self):
        kw = self._menu_kwargs()
        self._ctx_menu = tk.Menu(self, **kw)
        copy_menu = tk.Menu(self._ctx_menu, **kw)
        copy_menu.add_command(label="Phone number", command=self._copy_phone)
        copy_menu.add_separator()
        copy_menu.add_command(label="Row (tab-separated)", command=self._copy_row_tsv)
        copy_menu.add_command(label="Row as CSV", command=self._copy_row_csv)
        copy_menu.add_command(label="Selected rows as CSV", command=self._copy_selected_csv)
        copy_menu.add_separator()
        copy_menu.add_command(label="Full record (text)", command=self._copy_record_text)
        copy_menu.add_command(label="Full record (JSON)", command=self._copy_record_json)
        self._ctx_menu.add_command(label="Edit", command=self.act_edit_selected)
        self._ctx_menu.add_command(label="View details", command=self._open_detail)
        self._ctx_menu.add_separator()
        self._ctx_menu.add_command(label="Toggle pin", command=self.act_toggle_pin)
        self._ctx_menu.add_command(label="Toggle special", command=self.act_toggle_special)
        self._ctx_menu.add_separator()
        self._ctx_menu.add_command(label="Open attachments folder",
                                   command=self.act_open_selected_folder)
        self._ctx_menu.add_separator()
        self._ctx_menu.add_cascade(label="Copy", menu=copy_menu)
        self._ctx_menu.add_separator()
        self._ctx_menu.add_command(label="Delete", command=self.act_delete_selected)

    def _row_tag(self, status):
        return {"verified":  "verified",
                "invalid":   "invalid",
                "checking":  "checking",
                "anonymous": "anonymous"}.get(status, "")

    def _platform_summary(self, socials, platforms):
        parts = []
        for p in platforms:
            name = p["name"]
            s = socials.get(name)
            if not s:
                continue
            st = (s.get("exists_status") or "?").lower()
            mark = {"yes": "Y", "no": "N"}.get(st, "?")
            parts.append(f"{name}:{mark}")
        return "  ".join(parts)

    def _platform_cell(self, s):
        if not s:
            return ""
        st = (s.get("exists_status") or "").strip().lower()
        if st == "yes":
            return "yes"
        if st == "no":
            return "no"
        if st == "unknown":
            return "?"
        return st or "?"

    def refresh_table(self):
        for r in self.tree.get_children():
            self.tree.delete(r)
        self._row_raw.clear()
        plats = core.list_platforms()
        expected_mid = (
            ["platforms"] if self.compact_platforms.get()
            else [f"{PLAT_COL_PREFIX}{p['name']}" for p in plats]
        )
        current_mid = [c for c in self.tree["columns"]
                       if c == "platforms" or c.startswith(PLAT_COL_PREFIX)]
        if current_mid != expected_mid:
            self._rebuild_columns()
        try:
            rows = core.query_contacts(
                search=self.search_var.get().strip(),
                status=self.status_var.get(),
                platform=self.filter_var.get(),
                source=self.source_var.get(),
            )
        except Exception as e:
            self.log_line(f"[!] query failed: {e}")
            return
        if self.show_photo_only.get():
            rows = [r for r in rows if r.get("has_image")]
        city_by_phone = {}
        try:
            import sqlite3
            if Path(IDENTITY_DB).exists():
                idb = sqlite3.connect(IDENTITY_DB)
                for r in idb.execute("SELECT national_code, city FROM citizens"):
                    raw = r[0]
                    if not raw:
                        continue
                    s = "".join(ch for ch in str(raw) if ch.isdigit())
                    if len(s) == 10 and s.startswith("9"):
                        s = "0" + s
                    city_by_phone[s] = r[1]
                idb.close()
        except Exception:
            pass
        cols = list(self.tree["columns"])
        for r in rows:
            cid      = r["id"]
            socials  = r.get("socials", {})
            pinned   = bool(r.get("pinned"))
            special  = bool(r.get("special"))
            flag_parts = []
            if pinned:  flag_parts.append("P")
            if special: flag_parts.append("S")
            flags = " ".join(flag_parts)
            display_values = []
            raw_record: dict[str, str] = {}
            for col in cols:
                if col == "photo":
                    has = bool(r.get("has_image"))
                    v_d = v_r = "[+]" if has else ""
                elif col == "phone":
                    v_d, v_r = r["phone_number"] or "", r["phone_number"] or ""
                elif col == "status":
                    v_d, v_r = r["status"] or "", r["status"] or ""
                elif col == "flags":
                    v_d, v_r = flags, flags
                elif col == "sources":
                    v_d, v_r = r["sources"] or "", r["sources"] or ""
                elif col == "name":
                    v_d, v_r = fa(r["name"] or ""), r["name"] or ""
                elif col == "family":
                    v_d, v_r = fa(r["last_name"] or ""), r["last_name"] or ""
                elif col == "platforms":
                    v_d = self._platform_summary(socials, plats); v_r = v_d
                elif col == "city":
                    raw_city = city_by_phone.get(r["phone_number"], "")
                    v_d, v_r = fa(raw_city), raw_city
                elif col == "nc":
                    v_d, v_r = r["national_code"] or "", r["national_code"] or ""
                elif col.startswith(PLAT_COL_PREFIX):
                    pname = col[len(PLAT_COL_PREFIX):]
                    v_d = v_r = self._platform_cell(socials.get(pname))
                else:
                    v_d = v_r = ""
                display_values.append(v_d)
                raw_record[col] = v_r
            self._row_raw[cid] = raw_record
            tags = [self._row_tag(r["status"])]
            if special: tags.append("special")
            if pinned:  tags.append("pinned")
            tags = tuple(t for t in tags if t)
            self.tree.insert("", "end", iid=str(cid),
                             values=tuple(display_values), tags=tags)
        self._update_status(len(rows))
        self._update_filter_label()

    # --------------------------------------------------------
    # Double click
    # --------------------------------------------------------
    def _on_tree_double_click(self, event):
        region = self.tree.identify_region(event.x, event.y)
        if region != "cell":
            self._open_detail()
            return
        col = self.tree.identify_column(event.x)
        row = self.tree.identify_row(event.y)
        if not row or not col:
            self._open_detail()
            return
        try:
            col_idx = int(col[1:]) - 1
        except ValueError:
            self._open_detail()
            return
        cols = list(self.tree["columns"])
        if col_idx < 0 or col_idx >= len(cols):
            self._open_detail()
            return
        col_name = cols[col_idx]
        if col_name.startswith(PLAT_COL_PREFIX):
            pname = col_name[len(PLAT_COL_PREFIX):]
            self._show_social_popup(int(row), pname, event.x_root, event.y_root)
            return
        if col_name == "photo":
            self._show_photo_popup(int(row), event.x_root, event.y_root)
            return
        self._open_detail()

    def _show_photo_popup(self, cid, x, y):
        primary_id = core.get_primary_image_id(cid)
        win = tk.Toplevel(self)
        win.title(f"Photo — contact #{cid}")
        win.configure(bg=BG)
        win.transient(self)
        win.resizable(False, False)
        body = tk.Frame(win, bg=BG, padx=12, pady=10)
        body.pack(fill="both", expand=True)
        if primary_id is None:
            tk.Label(body, text="No photo attached.",
                     bg=BG, fg=FG_DIM, font=FONT_UI).pack(anchor="w")
        else:
            tk.Label(body, text=f"stored image #{primary_id}",
                     bg=BG, fg=FG_DIM, font=(FONT_UI[0], 9)).pack(
                anchor="w", pady=(0, 6))
            img_canvas = tk.Canvas(body, width=420, height=420,
                                   bg="#0c0c0c", highlightthickness=0)
            img_canvas.pack()
            data = core.get_contact_image_bytes(primary_id)
            img = load_photo_for_tk_from_bytes(data, (416, 416)) if data else None
            if img is not None:
                self._image_refs[f"popup_{cid}"] = img
                img_canvas.create_image(210, 210, image=img)
            else:
                img_canvas.create_text(
                    210, 210,
                    text="Preview not available.\n"
                         "Install Pillow: pip install Pillow",
                    fill=FG_DIM, font=(FONT_UI[0], 10),
                    width=400, justify="center",
                )
            tk.Button(body, text="Open folder",
                      command=lambda cid=cid: core.open_contact_folder(cid),
                      bg=BG_PANEL, fg=OK_GREEN, relief="flat",
                      padx=10, pady=3, cursor="hand2",
                      font=FONT_UI).pack(anchor="e", pady=(8, 0))
        tk.Button(body, text="Close", command=win.destroy,
                  bg=BG_PANEL, fg=FG, relief="flat", padx=12, pady=4,
                  activebackground=ACCENT_HOV, cursor="hand2",
                  font=FONT_UI).pack(anchor="e", pady=(6, 0))
        win.update_idletasks()
        sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
        ww = win.winfo_width() or 460
        wh = win.winfo_height() or 520
        px = min(x, sw - ww - 10)
        py = min(y, sh - wh - 10)
        win.geometry(f"+{max(px, 0)}+{max(py, 0)}")
        win.focus_set()
        win.bind("<Escape>", lambda _e: win.destroy())

    def _show_social_popup(self, cid, platform, x, y):
        info = core.get_contact_detail(cid)
        social = None
        for s in info["socials"]:
            if s["platform"] == platform:
                social = s
                break
        win = tk.Toplevel(self)
        win.title(f"{platform} — contact #{cid}")
        win.configure(bg=BG)
        win.transient(self)
        win.resizable(False, False)
        body = tk.Frame(win, bg=BG, padx=12, pady=10)
        body.pack(fill="both", expand=True)
        if not social:
            tk.Label(body,
                     text=f"No record for {platform} on this contact.",
                     bg=BG, fg=FG_DIM, font=FONT_UI).pack(anchor="w")
        else:
            rows = [
                ("Platform",        social.get("platform")),
                ("Exists status",   social.get("exists_status")),
                ("Username",        social.get("username")),
                ("Display name",    social.get("display_name")),
                ("User ID",         social.get("user_id")),
                ("Verified status", social.get("verified_status")),
                ("Updated at",      social.get("updated_at")),
            ]
            for label, value in rows:
                line = tk.Frame(body, bg=BG)
                line.pack(fill="x", pady=1)
                tk.Label(line, text=f"{label}:",
                         bg=BG, fg=FG_DIM, font=FONT_UI,
                         width=16, anchor="w").pack(side="left")
                tk.Label(line, text=(fa(value) if value is not None else ""),
                         bg=BG, fg=FG, font=FONT_UI,
                         anchor="w", justify="left").pack(side="left")
            tk.Button(
                body, text="Copy all",
                command=lambda cid=cid, p=platform: self._copy_social(cid, p),
                bg=BG_PANEL, fg=OK_GREEN,
                activebackground=ACCENT_HOV, activeforeground="white",
                relief="flat", padx=10, pady=3, cursor="hand2",
                font=FONT_UI,
            ).pack(anchor="e", pady=(8, 0))
        tk.Button(body, text="Close", command=win.destroy,
                  bg=BG_PANEL, fg=FG,
                  activebackground=ACCENT_HOV, activeforeground="white",
                  relief="flat", padx=12, pady=4, cursor="hand2",
                  font=FONT_UI).pack(anchor="e", pady=(6, 0))
        win.update_idletasks()
        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        ww = win.winfo_width() or 380
        wh = win.winfo_height() or 260
        px = min(x, sw - ww - 10)
        py = min(y, sh - wh - 10)
        win.geometry(f"+{max(px, 0)}+{max(py, 0)}")
        win.focus_set()
        win.bind("<Escape>", lambda _e: win.destroy())

    def _copy_social(self, cid, platform):
        info = core.get_contact_detail(cid)
        social = next((s for s in info["socials"]
                       if s["platform"] == platform), None)
        if not social:
            return
        lines = []
        for k in ("platform", "exists_status", "username",
                  "display_name", "user_id", "verified_status"):
            lines.append(f"{k}: {social.get(k) or ''}")
        self._set_clipboard("\n".join(lines))
        self.log_line(f"[copy] social {platform} for #{cid}")

    # --------------------------------------------------------
    # Log
    # --------------------------------------------------------
    def _build_log(self):
        wrap = tk.Frame(self, bg=BG)
        wrap.pack(fill="x", padx=6, pady=(0, 6))
        header = tk.Frame(wrap, bg=BG)
        header.pack(fill="x")
        tk.Label(header, text="Log", bg=BG, fg=FG_DIM,
                 font=FONT_UI).pack(side="left")
        tk.Button(header, text="Clear", command=self._clear_log,
                  bg=BG_PANEL, fg=FG, relief="flat", padx=8,
                  activebackground=ACCENT_HOV, cursor="hand2",
                  font=FONT_UI).pack(side="right")
        self.log_text = tk.Text(wrap, height=8, bg="#0c0c0c", fg="#c8c8c8",
                                insertbackground=FG, relief="flat",
                                font=FONT_MONO, wrap="word")
        self.log_text.pack(fill="x", expand=False)

    def log_line(self, msg: str):
        self.log_text.insert("end", str(msg) + "\n")
        self.log_text.see("end")

    def append_log(self, msg=""):
        self.log_line(str(msg))

    def _clear_log(self):
        self.log_text.delete("1.0", "end")

    # --------------------------------------------------------
    # Status bar
    # --------------------------------------------------------
    def _build_status(self):
        self.status_label = tk.Label(self, text="", bg=BG, fg=FG_DIM,
                                     anchor="w", font=FONT_UI)
        self.status_label.pack(fill="x", padx=8, pady=(0, 4))

    def _update_status(self, count):
        text = f"{count} shown"
        try:
            import sqlite3
            with sqlite3.connect(DB_PATH) as c:
                total = c.execute("SELECT COUNT(*) FROM contacts").fetchone()[0]
                verified = c.execute(
                    "SELECT COUNT(*) FROM contacts WHERE status='verified'"
                ).fetchone()[0]
                anonymous_n = c.execute(
                    "SELECT COUNT(*) FROM contacts WHERE status='anonymous'"
                ).fetchone()[0]
                pinned_n = c.execute(
                    "SELECT COUNT(*) FROM contacts WHERE pinned=1"
                ).fetchone()[0]
                special_n = c.execute(
                    "SELECT COUNT(*) FROM contacts WHERE special=1"
                ).fetchone()[0]
                with_photo = c.execute(
                    "SELECT COUNT(DISTINCT contact_id) FROM contact_images"
                ).fetchone()[0]
            n_plats = len(core.list_platforms())
            n_sources = len(core.list_data_sources())
            n_tables = len(list_custom_tables())
            backups = len(bk.list_backups())
            text += f"  |  total: {total}  |  verified: {verified}"
            text += f"  |  anonymous: {anonymous_n}"
            text += f"  |  pinned: {pinned_n}  |  special: {special_n}"
            text += f"  |  photo: {with_photo}"
            text += f"  |  sources: {n_sources}  |  platforms: {n_plats}"
            text += f"  |  tables: {n_tables}  |  backups: {backups}"
        except Exception:
            pass
        self.status_label.config(text=text)

    def _selected_ids(self):
        return [int(i) for i in self.tree.selection()]

    def _selected_id(self):
        ids = self._selected_ids()
        return ids[0] if ids else None

    # --------------------------------------------------------
    # Copy actions
    # --------------------------------------------------------
    def _set_clipboard(self, text: str):
        self.clipboard_clear()
        self.clipboard_append(text)

    def _copy_phone(self):
        cid = self._selected_id()
        if cid is None:
            return
        raw = self._row_raw.get(cid, {})
        phone = raw.get("phone", "")
        self._set_clipboard(phone)
        self.log_line(f"[copy] phone: {phone}")

    def _copy_row_tsv(self):
        cid = self._selected_id()
        if cid is None:
            return
        raw = self._row_raw.get(cid)
        if not raw:
            return
        self._set_clipboard("\t".join(str(raw.get(c, ""))
                                      for c in self.tree["columns"]))
        self.log_line(f"[copy] row (tab-separated) for #{cid}")

    def _copy_row_csv(self):
        cid = self._selected_id()
        if cid is None:
            return
        raw = self._row_raw.get(cid)
        if not raw:
            return
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\n")
        w.writerow([str(raw.get(c, "")) for c in self.tree["columns"]])
        self._set_clipboard(buf.getvalue())
        self.log_line(f"[copy] row as CSV for #{cid}")

    def _copy_selected_csv(self):
        ids = self._selected_ids()
        if not ids:
            return
        cols = list(self.tree["columns"])
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\n")
        w.writerow(cols)
        for cid in ids:
            raw = self._row_raw.get(cid, {})
            w.writerow([str(raw.get(c, "")) for c in cols])
        self._set_clipboard(buf.getvalue())
        self.log_line(f"[copy] {len(ids)} row(s) as CSV (with header)")

    def _copy_record_text(self):
        cid = self._selected_id()
        if cid is None:
            return
        info = core.get_contact_detail(cid)
        lines = []
        c = info["contact"]
        lines.append(f"id            : {c.get('id')}")
        lines.append(f"phone         : {c.get('phone_number') or ''}")
        lines.append(f"status        : {c.get('status') or ''}")
        lines.append(f"name          : {c.get('name') or ''}")
        lines.append(f"last_name     : {c.get('last_name') or ''}")
        lines.append(f"national_code : {c.get('national_code') or ''}")
        lines.append(f"pinned        : {bool(c.get('pinned'))}")
        lines.append(f"special       : {bool(c.get('special'))}")
        notes = c.get("notes")
        if notes:
            lines.append(f"notes         : {notes}")
        lines.append("")
        lines.append("images:")
        images = info.get("images") or []
        if not images:
            lines.append("  (none)")
        for im in images:
            lines.append(
                f"  #{im['id']}  {im['name']}  "
                f"mime={im['mime']}  size={im['size_bytes']}  "
                f"primary={bool(im['is_primary'])}"
            )
        lines.append("")
        lines.append("socials:")
        if not info["socials"]:
            lines.append("  (none)")
        for s in info["socials"]:
            lines.append(
                f"  {s['platform']:10s} exists={s['exists_status']:7s} "
                f"username={s['username'] or ''} "
                f"display_name={s['display_name'] or ''} "
                f"user_id={s['user_id'] or ''}"
            )
        if info.get("files"):
            lines.append("")
            lines.append("files:")
            for name, path, size in info["files"]:
                lines.append(f"  {name}  ({size} bytes)")
        for src_name, row in (info.get("external") or {}).items():
            lines.append("")
            lines.append(f"external ({src_name}):")
            for k, v in row.items():
                lines.append(f"  {k:14s}= {v if v is not None else ''}")
        if info["links"]:
            lines.append("")
            lines.append("links:")
            for l in info["links"]:
                lines.append(
                    f"  {l['source_db']}.{l['source_table']}#{l['source_pk']}  "
                    f"match={l['match_key']}  value={l['match_value'] or ''}  "
                    f"conf={l['confidence']}"
                )
        self._set_clipboard("\n".join(lines))
        self.log_line(f"[copy] full record (text) for #{cid}")

    def _copy_record_json(self):
        cid = self._selected_id()
        if cid is None:
            return
        info = core.get_contact_detail(cid)
        self._set_clipboard(
            json.dumps(info, ensure_ascii=False, indent=2, default=str)
        )
        self.log_line(f"[copy] full record (JSON) for #{cid}")

    # --------------------------------------------------------
    # Actions
    # --------------------------------------------------------
    def act_new(self):
        dlg = ContactEditDialog(self, contact_id=None)
        self.wait_window(dlg)
        if dlg.result:
            if dlg.platform_added:
                self._rebuild_platform_menu()
                self._rebuild_columns()
            self.refresh_table()

    def act_edit_selected(self):
        cid = self._selected_id()
        if cid is None:
            messagebox.showinfo("Edit", "Please select a contact first.",
                                parent=self)
            return
        dlg = ContactEditDialog(self, contact_id=cid)
        self.wait_window(dlg)
        if dlg.result:
            if dlg.platform_added:
                self._rebuild_platform_menu()
                self._rebuild_columns()
            self.refresh_table()

    def act_delete_selected(self):
        ids = self._selected_ids()
        if not ids:
            messagebox.showinfo("Delete", "Please select at least one contact.",
                                parent=self)
            return
        if not messagebox.askyesno(
            "Confirm",
            f"Delete {len(ids)} contact(s)?\n"
            "Their attachment folders and images will be removed too.\n"
            "This cannot be undone (unless you restore from a backup).",
            parent=self,
        ):
            return
        try:
            for cid in ids:
                core.delete_contact(cid)
        except Exception as e:
            self.log_line(f"[!] delete failed: {e}")
        self.refresh_table()

    def act_open_selected_folder(self):
        cid = self._selected_id()
        if cid is None:
            messagebox.showinfo("Open folder", "Please select a contact first.",
                                parent=self)
            return
        core.open_contact_folder(cid)

    def act_toggle_pin(self):
        ids = self._selected_ids()
        if not ids:
            messagebox.showinfo("Pin", "Please select a contact first.",
                                parent=self)
            return
        try:
            if len(ids) == 1:
                core.toggle_pin(ids[0])
            else:
                with_pinned = any(
                    "P" not in self._row_raw.get(cid, {}).get("flags", "")
                    for cid in ids
                )
                core.set_pinned_many(ids, with_pinned)
        except Exception as e:
            self.log_line(f"[!] pin failed: {e}")
        self.refresh_table()

    def act_toggle_special(self):
        ids = self._selected_ids()
        if not ids:
            messagebox.showinfo("Special", "Please select a contact first.",
                                parent=self)
            return
        try:
            if len(ids) == 1:
                core.toggle_special(ids[0])
            else:
                with_special = any(
                    "S" not in self._row_raw.get(cid, {}).get("flags", "")
                    for cid in ids
                )
                core.set_special_many(ids, with_special)
        except Exception as e:
            self.log_line(f"[!] special failed: {e}")
        self.refresh_table()

    def _show_context_menu(self, event):
        row_id = self.tree.identify_row(event.y)
        if row_id:
            if row_id not in self.tree.selection():
                self.tree.selection_set(row_id)
            try:
                self._ctx_menu.tk_popup(event.x_root, event.y_root)
            finally:
                self._ctx_menu.grab_release()

    def act_import_default(self):
        try:
            core.import_from_json()
        except Exception as e:
            self.log_line(f"[!] import failed: {e}")
        self.refresh_table()

    def act_import_file(self):
        p = filedialog.askopenfilename(
            title="Choose JSON file",
            initialdir=".", initialfile="tempinput.json",
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
        )
        if p:
            try:
                core.import_from_json(p)
            except Exception as e:
                self.log_line(f"[!] import failed: {e}")
            self.refresh_table()

    def act_import_maltego(self):
        try:
            maltego_import.run_import(self)
        except Exception as e:
            self.log_line(f"[!] maltego import failed: {e}")
        self.refresh_table()

    def act_sync(self):
        try:
            total = core.run_sync()
            self.log_line(f"[sync] total matches: {total}")
        except Exception as e:
            self.log_line(f"[!] sync failed: {e}")
        self.refresh_table()

    def act_migrate_photos(self):
        if not messagebox.askyesno(
            "Migrate",
            "Copy every legacy photo_path into contact_images?\n"
            "Safe: existing images are not overwritten."
        ):
            return
        try:
            n = core.migrate_photo_paths_to_db()
            self.log_line(f"[migrate] {n} photo(s) migrated.")
        except Exception as e:
            self.log_line(f"[!] migrate failed: {e}")
        self.refresh_table()

    def act_export_csv(self):
        p = filedialog.asksaveasfilename(
            initialdir="reports", initialfile="contacts_wide.csv",
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")],
        )
        if p:
            core.export_csv(p)

    def act_export_excel(self):
        p = filedialog.asksaveasfilename(
            initialdir="reports", initialfile="contacts_wide.xlsx",
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx")],
        )
        if p:
            core.export_excel(p)

    def act_manage_platforms(self):
        dlg = PlatformManager(self)
        self.wait_window(dlg)
        if dlg.changed:
            self._rebuild_platform_menu()
            self._rebuild_columns()
            self.refresh_table()

    def act_manage_sources(self):
        try:
            changed = run_source_manager(self)
        except Exception as e:
            self.log_line(f"[!] source manager failed: {e}")
            return
        if changed:
            self._rebuild_source_filter_menu()
            self.refresh_table()

    def act_manage_tables(self):
        dlg = TableManager(self)
        self.wait_window(dlg)
        if dlg.changed:
            self._rebuild_tables_menu()
            self.refresh_table()

    def act_open_custom_table(self, name):
        try:
            CustomTableBrowser(self, name)
        except Exception as e:
            messagebox.showerror("Open failed", str(e), parent=self)

    def act_backup(self):
        try:
            tag = simpledialog.askstring("Backup", "Tag (optional):",
                                         parent=self) or ""
        except Exception:
            tag = ""
        try:
            p = bk.create_backup(tag=tag)
            bk.prune_old_backups(keep=20)
            self.log_line(f"[backup] saved -> {p}")
        except Exception as e:
            self.log_line(f"[!] backup failed: {e}")
        self.refresh_table()

    def act_restore(self):
        files = bk.list_backups()
        if not files:
            messagebox.showinfo("Restore", "No backups found.")
            return
        win = tk.Toplevel(self)
        win.title("Restore backup")
        win.configure(bg=BG)
        win.geometry("560x400")
        tk.Label(win, text="Pick a backup to restore:",
                 bg=BG, fg=FG, font=FONT_UI).pack(anchor="w", padx=10, pady=8)
        lb = tk.Listbox(win, bg=BG_ENTRY, fg=FG, font=FONT_MONO,
                        selectbackground=SEL_BG, relief="flat")
        lb.pack(fill="both", expand=True, padx=10)
        for f in files:
            try:
                size = f.stat().st_size
                lb.insert("end", f"{f.name}   ({size} bytes)")
            except Exception:
                lb.insert("end", f.name)
        lb.selection_set(0)

        def do_restore():
            sel = lb.curselection()
            if not sel:
                return
            chosen = files[sel[0]]
            if not messagebox.askyesno(
                "Confirm",
                f"Restore from {chosen.name}?\n"
                "The current databases and attachments folder will be replaced.\n"
                "A safety backup will be created first."
            ):
                return
            try:
                restored = bk.restore_backup(chosen)
                self.log_line(f"[restore] {restored}")
                messagebox.showinfo("Restore",
                                    "Restored:\n" + "\n".join(restored))
            except Exception as e:
                self.log_line(f"[!] restore failed: {e}")
                messagebox.showerror("Restore failed", str(e))
            win.destroy()
            self._rebuild_tables_menu()
            self._rebuild_source_filter_menu()
            self._rebuild_columns()
            self.refresh_table()

        tk.Button(win, text="Restore", command=do_restore,
                  bg=ACCENT, fg="white", relief="flat", padx=14, pady=4,
                  activebackground=ACCENT_HOV, cursor="hand2",
                  font=FONT_UI).pack(pady=8)

    def act_legend(self):
        labels = core.source_label_map()
        lines = ["Short codes in the Src column:", ""]
        lines.append("  C = contacts.db   (imported from tempinput.json)")
        for s in core.list_data_sources():
            db = f"{s['name']}_db"
            code = labels.get(db, s["code"])
            lines.append(f"  {code} = {s['db_path']}   ({s['table_name']})")
        lines.append("")
        lines.append("Flags column:")
        lines.append("  P = pinned")
        lines.append("  S = special")
        lines.append("")
        lines.append("Statuses:")
        lines.append("  unchecked / checking / verified / invalid / anonymous")
        lines.append("")
        lines.append("Photo column:")
        lines.append("  [+] = has at least one image stored in the DB")
        lines.append("  Images live in the contact_images table as raw bytes + base64.")
        lines.append("  They are encrypted along with contacts.db inside the vault.")
        lines.append("")
        lines.append("Attachments folder:")
        lines.append("  Additional files are kept under attachments/<contact id>/.")
        lines.append("  Data menu -> Migrate legacy photo_path -> DB.")
        messagebox.showinfo("Sources legend", "\n".join(lines))

    def act_shortcuts(self):
        messagebox.showinfo(
            "Keyboard shortcuts",
            "Ctrl+N        New contact\n"
            "Ctrl+E / F2   Edit selected contact\n"
            "Delete        Delete selected contact(s)\n"
            "Ctrl+P        Toggle pin\n"
            "Ctrl+T        Toggle special\n"
            "F5            Refresh table\n"
            "Double-click  Detail / platform cell / photo cell\n"
            "Right-click   Context menu\n"
            "Ctrl+S        (in edit dialog) Save\n"
            "Esc           (in edit dialog) Cancel"
        )

    def act_about(self):
        messagebox.showinfo(
            f"About {APP_NAME}",
            f"{APP_NAME} — {APP_DESCRIPTION}\n\n"
            "Dark terminal-style UI for managing contacts,\n"
            "matching across multiple SQLite databases,\n"
            "keeping automatic backups (databases + attachments),\n"
            "rendering Persian text correctly,\n"
            "storing images inside the database as raw + base64,\n"
            "user-defined platforms, tables and data sources,\n"
            "and importing Maltego files."
        )

    # --------------------------------------------------------
    # Detail window
    # --------------------------------------------------------
    def _open_detail(self, _event=None):
        cid = self._selected_id()
        if cid is None:
            return
        info = core.get_contact_detail(cid)
        win = tk.Toplevel(self)
        win.title(f"Contact #{cid}")
        win.configure(bg=BG)
        win.geometry("940x780")
        nb = ttk.Notebook(win)
        nb.pack(fill="both", expand=True, padx=6, pady=6)
        self._tab_overview(nb, info)
        self._tab_socials(nb, info)
        self._tab_sources(nb, info)
        self._tab_raw(nb, info)
        bar = tk.Frame(win, bg=BG)
        bar.pack(fill="x", padx=6, pady=(0, 6))
        tk.Button(bar, text="Edit",
                  command=lambda: (win.destroy(), self.act_edit_selected()),
                  bg=ACCENT, fg="white", relief="flat", padx=14, pady=4,
                  activebackground=ACCENT_HOV, cursor="hand2",
                  font=FONT_UI).pack(side="left", padx=3)
        tk.Button(bar, text="Open folder",
                  command=lambda cid=cid: core.open_contact_folder(cid),
                  bg=BG_PANEL, fg=OK_GREEN, relief="flat", padx=14, pady=4,
                  activebackground=ACCENT_HOV, cursor="hand2",
                  font=FONT_UI).pack(side="left", padx=3)
        tk.Button(bar, text="Close", command=win.destroy,
                  bg=BG_PANEL, fg=FG, relief="flat", padx=14, pady=4,
                  activebackground=ACCENT_HOV, cursor="hand2",
                  font=FONT_UI).pack(side="right", padx=3)

    def _tab_overview(self, nb, info):
        frame = tk.Frame(nb, bg=BG)
        nb.add(frame, text="  Overview  ")
        outer = tk.Frame(frame, bg=BG)
        outer.pack(fill="both", expand=True)

        # Left: preview of primary image
        left = tk.Frame(outer, bg=BG, width=240)
        left.pack(side="left", fill="y", padx=(8, 4), pady=8)
        left.pack_propagate(False)
        tk.Label(left, text="Photo", bg=BG, fg=FG_DIM,
                 font=FONT_UI).pack(anchor="w")
        img_canvas = tk.Canvas(left, width=220, height=220,
                               bg="#0c0c0c", highlightthickness=1,
                               highlightbackground="#3c3c3c")
        img_canvas.pack(pady=(4, 6))

        contact_id = info["contact"]["id"]
        primary_id = info.get("primary_image_id")
        data = core.get_contact_image_bytes(primary_id) if primary_id else None
        img = load_photo_for_tk_from_bytes(data, (216, 216)) if data else None
        if img is not None:
            self._image_refs[f"overview_{contact_id}"] = img
            img_canvas.create_image(110, 110, image=img)
        else:
            text = "no photo" if not primary_id else "no preview"
            img_canvas.create_text(110, 110, text=text,
                                   fill=FG_DIM, font=(FONT_UI[0], 10))

        tk.Button(left, text="Open folder",
                  command=lambda: core.open_contact_folder(contact_id),
                  bg=BG_PANEL, fg=OK_GREEN, relief="flat", padx=10, pady=3,
                  activebackground=ACCENT_HOV, cursor="hand2",
                  font=FONT_UI).pack(fill="x", pady=(2, 0))

        # Right: text info
        right = tk.Frame(outer, bg=BG)
        right.pack(side="left", fill="both", expand=True, padx=(4, 8), pady=8)
        txt = tk.Text(right, bg="#0c0c0c", fg=FG, relief="flat",
                      font=FONT_MONO, wrap="word")
        txt.pack(fill="both", expand=True)
        txt.tag_configure("h", foreground=OK_GREEN,
                          font=(FONT_MONO[0], FONT_MONO[1], "bold"))

        c = info["contact"]
        _add_section(txt, "Contact")
        for key in ("id", "phone_number", "status", "name", "last_name",
                    "national_code", "pinned", "special",
                    "created_at", "updated_at"):
            _add_kv(txt, key, c.get(key))

        notes = c.get("notes")
        if notes:
            _add_section(txt, fa("Notes / توضیحات"))
            for line in str(notes).split("\n"):
                txt.insert("end", f"{fa(line)}\n")

        images = info.get("images") or []
        if images:
            _add_section(txt, "Images (stored in DB)")
            for im in images:
                txt.insert(
                    "end",
                    f"  #{im['id']}  {im['name']}  "
                    f"mime={im['mime']}  size={im['size_bytes']}  "
                    f"primary={bool(im['is_primary'])}\n",
                )

        files = info.get("files") or []
        if files:
            _add_section(txt, "Files (attachments folder)")
            for name, path, size in files:
                txt.insert("end", f"  {name}  ({size} bytes)\n")

        for src_name, row in (info.get("external") or {}).items():
            src = core.get_data_source(src_name)
            title = (src["label"] if src else src_name)
            _add_section(txt, f"External: {title} ({src_name})")
            for k, v in row.items():
                _add_kv(txt, k, v)

        txt.configure(state="disabled")

    def _tab_socials(self, nb, info):
        frame = tk.Frame(nb, bg=BG)
        nb.add(frame, text="  Socials  ")
        plats = core.list_platforms()
        socials = {s["platform"]: s for s in info["socials"]}
        cols = ("platform", "exists", "username", "display",
                "user_id", "verified")
        heads = ("Platform", "Exists", "Username",
                 "Display name", "User ID", "Verified status")
        widths = {"platform": 120, "exists": 80, "username": 160,
                  "display": 180, "user_id": 140, "verified": 120}
        tree = ttk.Treeview(frame, columns=cols, show="headings",
                            selectmode="browse")
        for c, h in zip(cols, heads):
            tree.heading(c, text=h)
            tree.column(c, width=widths[c],
                        anchor="center" if c in ("exists", "verified") else "w",
                        stretch=False)
        vs = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vs.set)
        tree.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=8)
        vs.pack(side="right", fill="y", padx=(0, 8), pady=8)
        for p in plats:
            name = p["name"]
            disp = p["display_name"] or name
            s = socials.get(name) or {}
            st = (s.get("exists_status") or "").strip().lower()
            mark = {"yes": "yes", "no": "no",
                    "unknown": "?", "": ""}.get(st, st)
            tree.insert("", "end", values=(
                fa(disp), mark,
                fa(s.get("username") or ""),
                fa(s.get("display_name") or ""),
                s.get("user_id") or "",
                s.get("verified_status") or "",
            ))

    def _tab_sources(self, nb, info):
        frame = tk.Frame(nb, bg=BG)
        nb.add(frame, text="  Sources  ")
        txt = tk.Text(frame, bg="#0c0c0c", fg=FG, relief="flat",
                      font=FONT_MONO, wrap="word")
        txt.pack(fill="both", expand=True)
        txt.tag_configure("h",   foreground=OK_GREEN,
                          font=(FONT_MONO[0], FONT_MONO[1], "bold"))
        txt.tag_configure("yes", foreground=OK_GREEN)
        txt.tag_configure("no",  foreground="#f48771")
        sources = info.get("sources", [])
        labels = core.source_label_map()
        txt.insert("end", "\n=== Databases this contact exists in ===\n", ("h",))
        all_codes = ["contacts"] + [f"{s['name']}_db"
                                    for s in core.list_data_sources()]
        for db_name in all_codes:
            present = db_name in sources
            mark = "[x]" if present else "[ ]"
            code = labels.get(db_name, db_name)
            txt.insert("end", f"  {mark} {code}  {db_name}\n",
                       ("yes" if present else "no",))
        txt.insert("end", "\n=== Links recorded in contact_links ===\n", ("h",))
        if not info["links"]:
            txt.insert("end", "(none)\n")
        for l in info["links"]:
            txt.insert("end",
                       f"  - {l['source_db']}.{l['source_table']}#{l['source_pk']}\n")
            txt.insert("end", f"      match_key   : {l['match_key']}\n")
            txt.insert("end", f"      match_value : {fa(l['match_value'])}\n")
            txt.insert("end", f"      confidence  : {l['confidence']}\n")
            txt.insert("end", f"      created_at  : {l['created_at']}\n\n")
        txt.configure(state="disabled")

    def _tab_raw(self, nb, info):
        frame = tk.Frame(nb, bg=BG)
        nb.add(frame, text="  Raw JSON  ")
        txt = tk.Text(frame, bg="#0c0c0c", fg=FG, relief="flat",
                      font=FONT_MONO, wrap="word")
        txt.pack(fill="both", expand=True)
        txt.insert("end", json.dumps(info, ensure_ascii=False,
                                     indent=2, default=str))
        txt.configure(state="disabled")


def run_gui():
    ensure_schema()
    App().mainloop()
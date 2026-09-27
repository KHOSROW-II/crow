"""
Table Manager and data browser for user-defined custom tables.
"""

import sys
import tkinter as tk
from tkinter import ttk, messagebox

import core
from db import (
    list_custom_tables, get_custom_table, create_custom_table,
    update_custom_table, delete_custom_table,
    list_custom_rows, insert_custom_row, update_custom_row,
    delete_custom_row, CUSTOM_COL_TYPES,
)
from text_utils import fa

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


def _mk_entry(parent, textvariable, width=32):
    return tk.Entry(parent, textvariable=textvariable, width=width,
                    bg=BG_ENTRY, fg=FG, insertbackground=FG,
                    relief="flat", font=FONT_UI)


def _mk_combo(parent, textvariable, values, width=20):
    return ttk.Combobox(parent, textvariable=textvariable, values=values,
                        state="readonly", width=width)


# ============================================================
# Table Manager
# ============================================================
class TableManager(tk.Toplevel):
    """List, add, edit, delete custom tables. Returns .changed = True if any."""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("Table Manager")
        self.configure(bg=BG)
        self.geometry("720x560")
        self.minsize(640, 480)
        self.transient(parent)
        self.grab_set()

        self.changed = False
        self._build()
        self._reload()

    def _build(self):
        bar = tk.Frame(self, bg=BG)
        bar.pack(fill="x", padx=8, pady=(8, 4))

        tk.Button(bar, text="New table", command=self._new,
                  bg="#2d5a2d", fg="white",
                  activebackground="#3a7a3a", activeforeground="white",
                  relief="flat", padx=14, pady=6, cursor="hand2",
                  font=FONT_UI).pack(side="left", padx=3)

        tk.Button(bar, text="Edit", command=self._edit,
                  bg=ACCENT, fg="white",
                  activebackground=ACCENT_HOV, activeforeground="white",
                  relief="flat", padx=14, pady=6, cursor="hand2",
                  font=FONT_UI).pack(side="left", padx=3)

        tk.Button(bar, text="Delete", command=self._delete,
                  bg="#5a2d2d", fg="white",
                  activebackground="#7a3a3a", activeforeground="white",
                  relief="flat", padx=14, pady=6, cursor="hand2",
                  font=FONT_UI).pack(side="left", padx=3)

        tk.Button(bar, text="Open", command=self._open,
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

        cols = ("name", "display", "cols", "rows")
        heads = ("Name", "Display name", "Columns", "Rows")
        widths = {"name": 140, "display": 220, "cols": 80, "rows": 80}

        self.tree = ttk.Treeview(wrap, columns=cols, show="headings")
        for c, h in zip(cols, heads):
            self.tree.heading(c, text=h)
            self.tree.column(c, width=widths[c],
                             anchor="center" if c in ("cols", "rows") else "w",
                             stretch=False)

        vs = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vs.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vs.grid(row=0, column=1, sticky="ns")
        wrap.rowconfigure(0, weight=1)
        wrap.columnconfigure(0, weight=1)

        self.tree.bind("<Double-1>", lambda _e: self._edit())

        tk.Label(self,
                 text=("Custom tables are stored inside contacts.db.\n"
                       "Each table gets its own menu entry so you can "
                       "browse and edit its rows."),
                 bg=BG, fg=FG_DIM, justify="left",
                 font=(FONT_UI[0], 9)).pack(anchor="w", padx=14, pady=(4, 10))

    def _reload(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        for t in list_custom_tables():
            try:
                _, cols, rows = list_custom_rows(t["name"])
                n_cols = len(cols)
                n_rows = len(rows)
            except Exception:
                n_cols = "?"
                n_rows = "?"
            self.tree.insert("", "end", iid=t["name"],
                             values=(t["name"],
                                     t["display_name"],
                                     n_cols, n_rows))

    def _selected(self):
        sel = self.tree.selection()
        return sel[0] if sel else None

    def _new(self):
        dlg = TableEditDialog(self, table_name=None)
        self.wait_window(dlg)
        if dlg.result:
            self.changed = True
            self._reload()

    def _edit(self):
        name = self._selected()
        if not name:
            messagebox.showinfo("Edit", "Select a table first.", parent=self)
            return
        dlg = TableEditDialog(self, table_name=name)
        self.wait_window(dlg)
        if dlg.result:
            self.changed = True
            self._reload()

    def _delete(self):
        name = self._selected()
        if not name:
            messagebox.showinfo("Delete", "Select a table first.", parent=self)
            return
        if not messagebox.askyesno(
            "Confirm",
            f"Delete table '{name}' and all its rows?\n"
            "This cannot be undone (unless you restore from a backup).",
            parent=self,
        ):
            return
        try:
            delete_custom_table(name)
        except Exception as e:
            messagebox.showerror("Delete failed", str(e), parent=self)
            return
        self.changed = True
        self._reload()

    def _open(self):
        name = self._selected()
        if not name:
            messagebox.showinfo("Open", "Select a table first.", parent=self)
            return
        CustomTableBrowser(self, name)


# ============================================================
# Table definition dialog (schema designer)
# ============================================================
class TableEditDialog(tk.Toplevel):
    """
    Create or edit a custom table.
    When editing, changing the column list causes a rebuild of the
    underlying SQL table; data for columns with matching names is kept.
    """

    def __init__(self, parent, table_name=None):
        super().__init__(parent)
        self.table_name = table_name
        self.result = None

        self.title(f"Edit table: {table_name}" if table_name else "New table")
        self.configure(bg=BG)
        self.geometry("820x640")
        self.minsize(720, 560)
        self.transient(parent)
        self.grab_set()

        self.rows = []   # list of dicts: name, display, type, required, default
        self._load()
        self._build()
        self._center(parent)

    def _center(self, parent):
        self.update_idletasks()
        px = parent.winfo_rootx() + (parent.winfo_width()  - self.winfo_width())  // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{max(px, 0)}+{max(py, 0)}")

    def _load(self):
        if self.table_name:
            info = get_custom_table(self.table_name)
            if not info:
                raise ValueError(f"Table '{self.table_name}' not found.")
            self.v_name_display = info["table"]["display_name"]
            self.v_description  = info["table"].get("description") or ""
            for c in info["columns"]:
                self.rows.append({
                    "name":          c["name"],
                    "display_name":  c["display_name"],
                    "col_type":      c["col_type"],
                    "is_required":   bool(c["is_required"]),
                    "default_value": c.get("default_value"),
                })
        else:
            self.v_name_display = ""
            self.v_description  = ""

    def _build(self):
        # Top form
        top = tk.Frame(self, bg=BG)
        top.pack(fill="x", padx=12, pady=(12, 4))
        top.columnconfigure(1, weight=1)

        tk.Label(top, text="Table name (id) *", bg=BG, fg=FG,
                 font=FONT_UI, anchor="w").grid(
            row=0, column=0, sticky="w", padx=(0, 10), pady=4)
        self.v_name = tk.StringVar(value=self.table_name or "")
        name_entry = _mk_entry(top, self.v_name, 30)
        if self.table_name:
            name_entry.configure(state="disabled")
        name_entry.grid(row=0, column=1, sticky="ew", pady=4)

        tk.Label(top, text="Display name *", bg=BG, fg=FG,
                 font=FONT_UI, anchor="w").grid(
            row=1, column=0, sticky="w", padx=(0, 10), pady=4)
        self.v_display = tk.StringVar(value=self.v_name_display)
        _mk_entry(top, self.v_display, 30).grid(
            row=1, column=1, sticky="ew", pady=4)

        tk.Label(top, text="Description", bg=BG, fg=FG,
                 font=FONT_UI, anchor="w").grid(
            row=2, column=0, sticky="w", padx=(0, 10), pady=4)
        self.v_desc = tk.StringVar(value=self.v_description)
        _mk_entry(top, self.v_desc, 30).grid(
            row=2, column=1, sticky="ew", pady=4)

        # Columns section
        colhdr = tk.Frame(self, bg=BG)
        colhdr.pack(fill="x", padx=12, pady=(10, 0))
        tk.Label(colhdr, text="Columns", bg=BG, fg=OK_GREEN,
                 font=(FONT_UI[0], FONT_UI[1], "bold")).pack(side="left")

        btnbar = tk.Frame(self, bg=BG)
        btnbar.pack(fill="x", padx=12, pady=(2, 4))
        tk.Button(btnbar, text="+ Add column", command=self._add_column,
                  bg=BG_PANEL, fg=OK_GREEN,
                  activebackground=ACCENT_HOV, activeforeground="white",
                  relief="flat", padx=10, pady=3, cursor="hand2",
                  font=FONT_UI).pack(side="left", padx=2)

        tk.Button(btnbar, text="Remove selected", command=self._remove_column,
                  bg=BG_PANEL, fg=ERR_RED,
                  activebackground="#3a1c1c", activeforeground="white",
                  relief="flat", padx=10, pady=3, cursor="hand2",
                  font=FONT_UI).pack(side="left", padx=2)

        tk.Button(btnbar, text="Move up", command=lambda: self._move(-1),
                  bg=BG_PANEL, fg=FG,
                  activebackground=ACCENT_HOV, activeforeground="white",
                  relief="flat", padx=10, pady=3, cursor="hand2",
                  font=FONT_UI).pack(side="left", padx=2)

        tk.Button(btnbar, text="Move down", command=lambda: self._move(+1),
                  bg=BG_PANEL, fg=FG,
                  activebackground=ACCENT_HOV, activeforeground="white",
                  relief="flat", padx=10, pady=3, cursor="hand2",
                  font=FONT_UI).pack(side="left", padx=2)

        # Columns table
        wrap = tk.Frame(self, bg=BG)
        wrap.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        cols = ("name", "display", "type", "required", "default")
        heads = ("Name", "Display name", "Type", "Required", "Default")
        widths = {"name": 150, "display": 200, "type": 90,
                  "required": 70, "default": 150}

        self.tree = ttk.Treeview(wrap, columns=cols, show="headings")
        for c, h in zip(cols, heads):
            self.tree.heading(c, text=h)
            self.tree.column(c, width=widths[c],
                             anchor="center" if c == "required" else "w",
                             stretch=False)

        vs = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vs.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vs.grid(row=0, column=1, sticky="ns")
        wrap.rowconfigure(0, weight=1)
        wrap.columnconfigure(0, weight=1)

        self.tree.bind("<Double-1>", lambda _e: self._edit_column())

        # Bottom buttons
        bar = tk.Frame(self, bg=BG)
        bar.pack(fill="x", padx=12, pady=(0, 12))

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

        self._refresh_tree()

    def _refresh_tree(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        for idx, row in enumerate(self.rows):
            self.tree.insert("", "end", iid=str(idx),
                             values=(row["name"],
                                     row["display_name"],
                                     row["col_type"],
                                     "yes" if row["is_required"] else "no",
                                     row["default_value"] or ""))

    def _selected_index(self):
        sel = self.tree.selection()
        return int(sel[0]) if sel else None

    def _add_column(self):
        dlg = ColumnEditDialog(self, col=None)
        self.wait_window(dlg)
        if dlg.result:
            self.rows.append(dlg.result)
            self._refresh_tree()

    def _edit_column(self):
        idx = self._selected_index()
        if idx is None:
            return
        dlg = ColumnEditDialog(self, col=self.rows[idx])
        self.wait_window(dlg)
        if dlg.result:
            self.rows[idx] = dlg.result
            self._refresh_tree()

    def _remove_column(self):
        idx = self._selected_index()
        if idx is None:
            return
        del self.rows[idx]
        self._refresh_tree()

    def _move(self, direction):
        idx = self._selected_index()
        if idx is None:
            return
        new_idx = idx + direction
        if new_idx < 0 or new_idx >= len(self.rows):
            return
        self.rows[idx], self.rows[new_idx] = self.rows[new_idx], self.rows[idx]
        self._refresh_tree()
        self.tree.selection_set(str(new_idx))

    def _save(self):
        try:
            if self.table_name:
                update_custom_table(
                    self.table_name,
                    display_name=self.v_display.get().strip() or None,
                    description=self.v_desc.get().strip() or None,
                    columns=self.rows,
                )
            else:
                name = self.v_name.get().strip()
                display = self.v_display.get().strip() or name
                create_custom_table(
                    name, display, self.rows,
                    description=self.v_desc.get().strip() or None,
                )
        except Exception as e:
            messagebox.showerror("Save failed", str(e), parent=self)
            return
        self.result = True
        self.destroy()


class ColumnEditDialog(tk.Toplevel):
    def __init__(self, parent, col=None):
        super().__init__(parent)
        self.result = None

        self.title("Edit column" if col else "New column")
        self.configure(bg=BG)
        self.geometry("420x330")
        self.transient(parent)
        self.grab_set()

        col = col or {}
        self.v_name = tk.StringVar(value=col.get("name", ""))
        self.v_display = tk.StringVar(value=col.get("display_name", ""))
        self.v_type = tk.StringVar(value=col.get("col_type", "text"))
        self.v_required = tk.IntVar(value=1 if col.get("is_required") else 0)
        self.v_default = tk.StringVar(value=col.get("default_value") or "")

        form = tk.Frame(self, bg=BG)
        form.pack(fill="x", padx=16, pady=16)
        form.columnconfigure(1, weight=1)

        def row(r, label, widget):
            tk.Label(form, text=label, bg=BG, fg=FG, font=FONT_UI,
                     anchor="w").grid(row=r, column=0, sticky="w",
                                      padx=(0, 10), pady=6)
            widget.grid(row=r, column=1, sticky="ew", pady=6)

        row(0, "Name (id) *", _mk_entry(form, self.v_name, 26))
        row(1, "Display name", _mk_entry(form, self.v_display, 26))
        row(2, "Type", _mk_combo(form, self.v_type, list(CUSTOM_COL_TYPES), 20))
        row(3, "Required", tk.Checkbutton(
            form, variable=self.v_required, bg=BG, fg=FG,
            selectcolor=BG_ENTRY, activebackground=BG,
            activeforeground=OK_GREEN, font=FONT_UI))
        row(4, "Default value", _mk_entry(form, self.v_default, 26))

        bar = tk.Frame(self, bg=BG)
        bar.pack(fill="x", padx=16, pady=(0, 12))
        tk.Button(bar, text="OK", command=self._ok,
                  bg="#2d5a2d", fg="white",
                  activebackground="#3a7a3a", activeforeground="white",
                  relief="flat", padx=16, pady=5, cursor="hand2",
                  font=FONT_UI).pack(side="left", padx=3)
        tk.Button(bar, text="Cancel", command=self.destroy,
                  bg=BG_PANEL, fg=FG,
                  activebackground=ACCENT_HOV, activeforeground="white",
                  relief="flat", padx=16, pady=5, cursor="hand2",
                  font=FONT_UI).pack(side="left", padx=3)

        self.bind("<Return>", lambda _e: self._ok())
        self.bind("<Escape>", lambda _e: self.destroy())

    def _ok(self):
        name = self.v_name.get().strip().lower()
        if not name:
            messagebox.showerror("Error", "Column name is required.",
                                 parent=self)
            return
        display = self.v_display.get().strip() or name.replace("_", " ").title()
        self.result = {
            "name":          name,
            "display_name":  display,
            "col_type":      self.v_type.get(),
            "is_required":   bool(self.v_required.get()),
            "default_value": self.v_default.get().strip() or None,
        }
        self.destroy()


# ============================================================
# Data browser for a custom table
# ============================================================
class CustomTableBrowser(tk.Toplevel):
    """A Toplevel window showing rows of a custom table."""

    def __init__(self, parent, table_name):
        super().__init__(parent)
        self.table_name = table_name
        self.table, self.columns, self.rows = list_custom_rows(table_name)

        self.title(f"Table: {self.table['display_name']}")
        self.configure(bg=BG)
        self.geometry("900x620")
        self.minsize(700, 500)
        self.transient(parent)

        self._build()
        self._reload()

    def _build(self):
        bar = tk.Frame(self, bg=BG)
        bar.pack(fill="x", padx=8, pady=(8, 4))

        tk.Button(bar, text="New row", command=self._new,
                  bg="#2d5a2d", fg="white",
                  activebackground="#3a7a3a", activeforeground="white",
                  relief="flat", padx=14, pady=6, cursor="hand2",
                  font=FONT_UI).pack(side="left", padx=3)

        tk.Button(bar, text="Edit", command=self._edit,
                  bg=ACCENT, fg="white",
                  activebackground=ACCENT_HOV, activeforeground="white",
                  relief="flat", padx=14, pady=6, cursor="hand2",
                  font=FONT_UI).pack(side="left", padx=3)

        tk.Button(bar, text="Delete", command=self._delete,
                  bg="#5a2d2d", fg="white",
                  activebackground="#7a3a3a", activeforeground="white",
                  relief="flat", padx=14, pady=6, cursor="hand2",
                  font=FONT_UI).pack(side="left", padx=3)

        tk.Button(bar, text="Refresh", command=self._refresh,
                  bg=BG_PANEL, fg=FG,
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

        cols = ["id"] + [c["name"] for c in self.columns]
        heads = ["ID"] + [c["display_name"] for c in self.columns]

        self.tree = ttk.Treeview(wrap, columns=cols, show="headings",
                                 selectmode="extended")
        self.tree["columns"] = cols
        for c, h in zip(cols, heads):
            self.tree.heading(c, text=h)
            self.tree.column(c, width=140, anchor="w", stretch=False)

        vs = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        hs = ttk.Scrollbar(wrap, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vs.set, xscrollcommand=hs.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vs.grid(row=0, column=1, sticky="ns")
        hs.grid(row=1, column=0, sticky="ew")
        wrap.rowconfigure(0, weight=1)
        wrap.columnconfigure(0, weight=1)

        self.tree.bind("<Double-1>", lambda _e: self._edit())

    def _refresh(self):
        self.table, self.columns, self.rows = list_custom_rows(self.table_name)
        self._reload()

    def _reload(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        for r in self.rows:
            values = [r.get("id")]
            for c in self.columns:
                v = r.get(f"c_{c['name']}")
                if v is None:
                    v = ""
                values.append(fa(v) if isinstance(v, str) else v)
            self.tree.insert("", "end", iid=str(r["id"]), values=values)

    def _selected_ids(self):
        return [int(i) for i in self.tree.selection()]

    def _selected_id(self):
        ids = self._selected_ids()
        return ids[0] if ids else None

    def _row_by_id(self, row_id):
        for r in self.rows:
            if r["id"] == row_id:
                return r
        return None

    def _new(self):
        dlg = CustomRowEditDialog(self, self.table_name, self.columns, None)
        self.wait_window(dlg)
        if dlg.result:
            self._refresh()

    def _edit(self):
        rid = self._selected_id()
        if rid is None:
            messagebox.showinfo("Edit", "Select a row first.", parent=self)
            return
        row = self._row_by_id(rid)
        dlg = CustomRowEditDialog(self, self.table_name, self.columns, row)
        self.wait_window(dlg)
        if dlg.result:
            self._refresh()

    def _delete(self):
        ids = self._selected_ids()
        if not ids:
            messagebox.showinfo("Delete", "Select a row first.", parent=self)
            return
        if not messagebox.askyesno(
            "Confirm", f"Delete {len(ids)} row(s) from '{self.table_name}'?",
            parent=self,
        ):
            return
        try:
            for rid in ids:
                delete_custom_row(self.table_name, rid)
        except Exception as e:
            messagebox.showerror("Delete failed", str(e), parent=self)
            return
        self._refresh()


class CustomRowEditDialog(tk.Toplevel):
    """Edit one row of a custom table. `row` is dict or None."""

    def __init__(self, parent, table_name, columns, row):
        super().__init__(parent)
        self.result = None
        self.table_name = table_name
        self.columns = columns
        self.row = row or {}

        self.title("Edit row" if row else "New row")
        self.configure(bg=BG)
        self.geometry("520x560")
        self.transient(parent)
        self.grab_set()

        self.vars = {}
        self._build()
        self._center(parent)

    def _center(self, parent):
        self.update_idletasks()
        px = parent.winfo_rootx() + (parent.winfo_width()  - self.winfo_width())  // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{max(px, 0)}+{max(py, 0)}")

    def _build(self):
        wrap = tk.Frame(self, bg=BG)
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

        inner.columnconfigure(1, weight=1)

        for i, col in enumerate(self.columns):
            tk.Label(inner, text=col["display_name"] +
                     (" *" if col["is_required"] else ""),
                     bg=BG, fg=FG, font=FONT_UI, anchor="w").grid(
                row=i, column=0, sticky="w", padx=(16, 10), pady=6)

            value = self.row.get(f"c_{col['name']}")
            if value is None:
                value = col.get("default_value") or ""
            if col["col_type"] == "bool":
                value = "yes" if value in (1, "1", True, "yes", "true") else "no"

            var = tk.StringVar(value=str(value))
            self.vars[col["name"]] = (var, col["col_type"])

            if col["col_type"] == "bool":
                ttk.Combobox(inner, textvariable=var, values=["yes", "no"],
                             state="readonly", width=20).grid(
                    row=i, column=1, sticky="w", padx=(0, 16), pady=6)
            else:
                _mk_entry(inner, var, 32).grid(
                    row=i, column=1, sticky="ew", padx=(0, 16), pady=6)

        bar = tk.Frame(self, bg=BG)
        bar.pack(fill="x", padx=16, pady=(0, 12))
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

    def _save(self):
        data = {}
        for name, (var, ctype) in self.vars.items():
            data[name] = var.get()
        try:
            if self.row.get("id"):
                update_custom_row(self.table_name, self.row["id"], data)
            else:
                insert_custom_row(self.table_name, data)
        except Exception as e:
            messagebox.showerror("Save failed", str(e), parent=self)
            return
        self.result = True
        self.destroy()
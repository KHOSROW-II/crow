"""
Dialog for managing the platform registry:
  - list all platforms
  - add a new custom platform
  - rename the display name of any platform
  - remove a custom platform (built-ins cannot be removed)
"""

import sys
import tkinter as tk
from tkinter import ttk, messagebox

import core

BG         = "#1e1e1e"
BG_PANEL   = "#252526"
BG_ENTRY   = "#1b1b1b"
FG         = "#d4d4d4"
FG_DIM     = "#808080"
ACCENT     = "#0e639c"
ACCENT_HOV = "#1177bb"
BORDER     = "#3c3c3c"
SEL_BG     = "#094771"

FONT_UI   = ("Tahoma", 10) if sys.platform == "win32" else ("Sans", 10)
FONT_MONO = ("Consolas", 10) if sys.platform == "win32" else ("Monospace", 10)


class PlatformManager(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Platform Manager")
        self.configure(bg=BG)
        self.geometry("620x520")
        self.minsize(560, 460)
        self.transient(parent)
        self.grab_set()

        self.changed = False

        self._build()
        self._reload()

    # --------------------------------------------------------
    def _build(self):
        # toolbar
        bar = tk.Frame(self, bg=BG)
        bar.pack(fill="x", padx=8, pady=(8, 4))

        tk.Button(bar, text="Add platform", command=self._add,
                  bg="#2d5a2d", fg="white",
                  activebackground="#3a7a3a", activeforeground="white",
                  relief="flat", padx=12, pady=6, cursor="hand2",
                  font=FONT_UI).pack(side="left", padx=3)

        tk.Button(bar, text="Rename", command=self._rename,
                  bg=BG_PANEL, fg=FG,
                  activebackground=ACCENT_HOV, activeforeground="white",
                  relief="flat", padx=12, pady=6, cursor="hand2",
                  font=FONT_UI).pack(side="left", padx=3)

        tk.Button(bar, text="Remove", command=self._remove,
                  bg="#5a2d2d", fg="white",
                  activebackground="#7a3a3a", activeforeground="white",
                  relief="flat", padx=12, pady=6, cursor="hand2",
                  font=FONT_UI).pack(side="left", padx=3)

        tk.Button(bar, text="Close", command=self.destroy,
                  bg=BG_PANEL, fg=FG,
                  activebackground=ACCENT_HOV, activeforeground="white",
                  relief="flat", padx=12, pady=6, cursor="hand2",
                  font=FONT_UI).pack(side="right", padx=3)

        # table
        wrap = tk.Frame(self, bg=BG)
        wrap.pack(fill="both", expand=True, padx=8, pady=4)

        cols = ("name", "display", "builtin", "order")
        heads = ("Name", "Display name", "Built-in", "Sort")
        widths = {"name": 130, "display": 220, "builtin": 80, "order": 60}

        self.tree = ttk.Treeview(wrap, columns=cols, show="headings")
        for c, h in zip(cols, heads):
            self.tree.heading(c, text=h)
            self.tree.column(c, width=widths[c],
                             anchor="center" if c in ("builtin", "order") else "w",
                             stretch=False)

        vs = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vs.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vs.grid(row=0, column=1, sticky="ns")
        wrap.rowconfigure(0, weight=1)
        wrap.columnconfigure(0, weight=1)

        tk.Label(self,
                 text=("Built-in platforms cannot be removed, only renamed.\n"
                       "Adding a new platform adds a tab to every contact's\n"
                       "edit window and a filter option in the search bar."),
                 bg=BG, fg=FG_DIM, justify="left",
                 font=(FONT_UI[0], 9)).pack(anchor="w", padx=12, pady=(4, 8))

    # --------------------------------------------------------
    def _reload(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        for p in core.list_platforms():
            self.tree.insert("", "end", iid=p["name"],
                             values=(p["name"],
                                     p["display_name"] or "",
                                     "yes" if p["is_builtin"] else "no",
                                     p["sort_order"]))

    # --------------------------------------------------------
    def _selected(self):
        sel = self.tree.selection()
        return sel[0] if sel else None

    # --------------------------------------------------------
    def _add(self):
        name = tk.simpledialog.askstring(
            "Add platform",
            "Platform name (lowercase letters, digits, underscore):",
            parent=self,
        )
        if not name:
            return
        display = tk.simpledialog.askstring(
            "Add platform",
            "Display name (shown in tabs):",
            parent=self,
        )
        try:
            core.add_platform(name, display)
        except Exception as e:
            messagebox.showerror("Add failed", str(e), parent=self)
            return
        self.changed = True
        self._reload()

    # --------------------------------------------------------
    def _rename(self):
        name = self._selected()
        if not name:
            messagebox.showinfo("Rename", "Select a platform first.", parent=self)
            return
        current = ""
        for p in core.list_platforms():
            if p["name"] == name:
                current = p["display_name"] or ""
                break
        new_display = tk.simpledialog.askstring(
            "Rename platform",
            f"New display name for '{name}':",
            initialvalue=current, parent=self,
        )
        if new_display is None:
            return
        try:
            core.rename_platform(name, new_display)
        except Exception as e:
            messagebox.showerror("Rename failed", str(e), parent=self)
            return
        self.changed = True
        self._reload()

    # --------------------------------------------------------
    def _remove(self):
        name = self._selected()
        if not name:
            messagebox.showinfo("Remove", "Select a platform first.", parent=self)
            return
        if not messagebox.askyesno(
            "Confirm",
            f"Remove platform '{name}'?\n"
            "All rows for this platform in every contact will be deleted.\n"
            "This cannot be undone (unless you restore from a backup).",
            parent=self,
        ):
            return
        try:
            core.remove_platform(name)
        except Exception as e:
            messagebox.showerror("Remove failed", str(e), parent=self)
            return
        self.changed = True
        self._reload()


# simple dialog helper without needing to import tkinter.simpledialog at top
import tkinter.simpledialog
tk.simpledialog = tkinter.simpledialog
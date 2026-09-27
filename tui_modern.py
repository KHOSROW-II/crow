"""
Modern TUI for Contacts Manager using Textual.
"""

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import (
    Header, Footer, DataTable, Input, Static, Label,
)
from textual.binding import Binding
from textual.screen import ModalScreen

import core
import backup as bk
from branding import APP_NAME, APP_TITLE, APP_TITLE_SHORT, APP_DESCRIPTION

def format_platform_cell(s):
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


# ============================================================
# Modal screens
# ============================================================
class DetailScreen(ModalScreen):
    BINDINGS = [Binding("escape,q", "dismiss", "Close", show=False)]

    CSS = """
    DetailScreen { align: center middle; }
    #detail-box {
        width: 92%;
        height: 88%;
        border: thick $accent;
        background: $surface;
        padding: 1 2;
        overflow-y: auto;
    }
    """

    def __init__(self, contact_id):
        super().__init__()
        self.contact_id = contact_id

    def compose(self) -> ComposeResult:
        info = core.get_contact_detail(self.contact_id)
        yield Static(self._format(info), id="detail-box")

    def _format(self, info):
        c = info["contact"]
        out = [f"[b cyan]Contact #{c.get('id')}[/b cyan]"]
        for k in ("phone_number", "status", "name", "last_name",
                  "national_code", "pinned", "special",
                  "created_at", "updated_at"):
            out.append(f"  [b]{k:14s}[/b]: {c.get(k) or ''}")

        if c.get("photo_path"):
            out.append(f"  [b]photo_path    [/b]: {c['photo_path']}")

        if c.get("notes"):
            out.append("")
            out.append("[b cyan]Notes[/b cyan]")
            for line in str(c["notes"]).splitlines() or [c["notes"]]:
                out.append(f"  {line}")

        out.append("")
        out.append("[b cyan]Socials[/b cyan]")
        if not info["socials"]:
            out.append("  (none)")
        for s in info["socials"]:
            out.append(
                f"  [yellow]{s['platform']:10s}[/yellow] "
                f"exists={s['exists_status']:7s} "
                f"username={s.get('username') or ''} "
                f"display={s.get('display_name') or ''} "
                f"uid={s.get('user_id') or ''}"
            )

        files = info.get("files") or []
        if files:
            out.append("")
            out.append("[b cyan]Files[/b cyan]")
            for name, path, size in files:
                out.append(f"  {name}  ({size} bytes)")

        for src_name, row in (info.get("external") or {}).items():
            out.append("")
            out.append(f"[b cyan]External: {src_name}[/b cyan]")
            for k, v in row.items():
                out.append(f"  {k:14s}= {v if v is not None else ''}")

        out.append("")
        out.append("[b cyan]Links[/b cyan]")
        if not info["links"]:
            out.append("  (none)")
        for l in info["links"]:
            out.append(
                f"  {l['source_db']}.{l['source_table']}#{l['source_pk']}  "
                f"match={l['match_key']}  value={l['match_value'] or ''}  "
                f"conf={l['confidence']}"
            )
        return "\n".join(out)


class ConfirmScreen(ModalScreen):
    BINDINGS = [
        Binding("y", "confirm", "Yes"),
        Binding("n,escape,q", "cancel", "No"),
    ]

    CSS = """
    ConfirmScreen { align: center middle; }
    #confirm-box {
        width: 50; height: 7;
        border: thick $warning;
        background: $surface;
        padding: 1 2;
        align: center middle;
    }
    """

    def __init__(self, message):
        super().__init__()
        self.message = message

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-box"):
            yield Label(self.message)
            yield Label("[b]y[/b]=yes  [b]n[/b]=no")

    def action_confirm(self):
        self.dismiss(True)

    def action_cancel(self):
        self.dismiss(False)


class EditContactScreen(ModalScreen):
    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
        Binding("ctrl+s", "save", "Save"),
    ]

    CSS = """
    EditContactScreen { align: center middle; }
    #edit-box {
        width: 80; height: auto;
        border: thick $accent;
        background: $surface;
        padding: 1 2;
    }
    #edit-box Input { margin: 1 0; }
    """

    def __init__(self, contact_id, on_save=None):
        super().__init__()
        self.contact_id = contact_id
        self.on_save = on_save
        if contact_id is not None:
            info = core.get_contact_detail(contact_id)
            self._c = info["contact"]
        else:
            self._c = {"phone_number": "", "status": "unchecked",
                       "name": "", "last_name": "", "national_code": "",
                       "notes": "", "photo_path": ""}

    def compose(self) -> ComposeResult:
        with Vertical(id="edit-box"):
            yield Label("[b]Edit contact[/b]" if self.contact_id
                        else "[b]New contact[/b]")
            yield Label("Phone *")
            yield Input(value=self._c.get("phone_number") or "", id="phone")
            yield Label("Name")
            yield Input(value=self._c.get("name") or "", id="name")
            yield Label("Last name")
            yield Input(value=self._c.get("last_name") or "", id="last")
            yield Label("National code")
            yield Input(value=self._c.get("national_code") or "", id="nc")
            yield Label("Notes")
            yield Input(value=self._c.get("notes") or "", id="notes")
            yield Label("Photo path (empty to keep / clear)")
            yield Input(value=self._c.get("photo_path") or "", id="photo")
            yield Label("Status (unchecked / checking / verified / invalid / anonymous)")
            yield Input(value=self._c.get("status") or "unchecked", id="status")
            yield Label("[b]Ctrl+S[/b] = save  •  [b]Esc[/b] = cancel")

    def action_cancel(self):
        self.dismiss(None)

    def action_save(self):
        photo_val = self.query_one("#photo", Input).value.strip()

        data = {
            "phone":         self.query_one("#phone", Input).value.strip(),
            "name":          self.query_one("#name", Input).value.strip() or None,
            "last_name":     self.query_one("#last", Input).value.strip() or None,
            "national_code": self.query_one("#nc", Input).value.strip() or None,
            "notes":         self.query_one("#notes", Input).value.strip() or "",
            "status":        self.query_one("#status", Input).value.strip() or "unchecked",
        }
        try:
            if self.contact_id is None:
                cid = core.create_contact(**data)
            else:
                cid = self.contact_id
                core.update_contact(cid, **data)

            # photo: copy the file into the contact's folder
            if photo_val:
                try:
                    core.set_contact_photo(cid, photo_val)
                except Exception as e:
                    self.app.notify(f"photo error: {e}", severity="error")
            self.app.notify("saved")
        except Exception as e:
            self.app.notify(f"error: {e}", severity="error")
            return
        if self.on_save:
            try:
                self.on_save()
            except Exception:
                pass
        self.dismiss(True)


class HelpScreen(ModalScreen):
    BINDINGS = [Binding("escape,q,question_mark,f1", "dismiss", "Close")]

    CSS = """
    HelpScreen { align: center middle; }
    #help-box {
        width: 68; height: 85%;
        border: thick $accent;
        background: $surface;
        padding: 1 2;
        overflow-y: auto;
    }
    """

    def compose(self) -> ComposeResult:
        text = (
            f"[b cyan]{APP_NAME} — {APP_DESCRIPTION}[/b cyan]\n"
            "[b cyan]Global shortcuts (always work)[/b cyan]\n\n"
            "  [b]Ctrl+Q[/b]        quit\n"
            "  [b]Ctrl+C[/b]        quit\n"
            "  [b]Ctrl+F[/b]        focus search\n"
            "  [b]Ctrl+R[/b]        refresh\n"
            "  [b]Ctrl+Y[/b]        sync databases\n"
            "  [b]Ctrl+B[/b]        backup now\n"
            "  [b]Ctrl+V[/b]        toggle compact / expanded view\n"
            "  [b]F1[/b]            this help\n\n"
            "[b cyan]When the table has focus[/b cyan]\n\n"
            "  [b]↑ / ↓[/b]         move selection\n"
            "  [b]Enter[/b]         open detail\n"
            "  [b]Esc[/b]           blur search box\n"
            "  [b]/[/b]             focus search box\n"
            "  [b]n[/b]             new contact\n"
            "  [b]e[/b]             edit selected (photo, notes)\n"
            "  [b]d[/b]             delete selected\n"
            "  [b]p[/b]             toggle pin\n"
            "  [b]t[/b]             toggle special\n"
            "  [b]o[/b]             open attachments folder\n"
            "  [b]v[/b]             toggle compact / expanded view\n"
            "  [b]y[/b]             sync\n"
            "  [b]b[/b]             backup\n"
            "  [b]r[/b]             refresh\n"
            "  [b]?[/b]             this help\n"
            "  [b]q[/b]             quit"
        )
        yield Static(text, id="help-box")


# ============================================================
# Main app
# ============================================================
class ContactsTUI(App):
    TITLE = APP_NAME
    SUB_TITLE = APP_DESCRIPTION
    CSS = """
    Screen { layout: vertical; }
    #search { dock: top; height: 3; margin: 1 1 0 1; }
    #main { height: 1fr; margin: 0 1; }
    #table { width: 2fr; }
    #side {
        width: 1fr;
        border-left: solid $accent;
        padding: 0 1;
        overflow-y: auto;
    }
    #status { dock: bottom; height: 1; background: $panel; padding: 0 1; }
    """

    BINDINGS = [
        Binding("ctrl+q", "quit",         "Quit",    priority=True),
        Binding("ctrl+c", "quit",         "Quit",    priority=True, show=False),
        Binding("ctrl+f", "focus_search", "Search",  priority=True),
        Binding("ctrl+r", "reload_data",  "Refresh", priority=True),
        Binding("ctrl+y", "sync",         "Sync",    priority=True),
        Binding("ctrl+b", "backup",       "Backup",  priority=True),
        Binding("ctrl+v", "toggle_view",  "View",    priority=True),
        Binding("f1",     "help",         "Help",    priority=True),

        Binding("q",          "quit",           "Quit",    show=False),
        Binding("slash",      "focus_search",   "Search",  show=False),
        Binding("escape",     "blur_input",     "Blur",    show=False),
        Binding("n",          "new_contact",    "New",     show=False),
        Binding("e",          "edit_contact",   "Edit",    show=False),
        Binding("d",          "delete_contact", "Delete",  show=False),
        Binding("p",          "toggle_pin",     "Pin",     show=False),
        Binding("t",          "toggle_special", "Special", show=False),
        Binding("o",          "open_folder",    "Folder",  show=False),
        Binding("v",          "toggle_view",    "View",    show=False),
        Binding("y",          "sync",           "Sync",    show=False),
        Binding("b",          "backup",         "Backup",  show=False),
        Binding("r",          "reload_data",    "Refresh", show=False),
        Binding("question_mark", "help",        "Help",    show=False),
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._row_index = {}
        self._search_timer = None
        self._side_current = None
        self.expanded = False
        self._cols = []

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Input(placeholder="Type to search…  (Ctrl+F to focus, Esc to blur)",
                    id="search")
        with Horizontal(id="main"):
            yield DataTable(id="table", zebra_stripes=True)
            yield Static("Select a contact…", id="side")
        yield Static("Ready", id="status")
        yield Footer()

    def on_mount(self):
        table = self.query_one("#table", DataTable)
        table.cursor_type = "row"
        self._rebuild_columns()
        self.reload_data()
        table.focus()

    def _rebuild_columns(self):
        table = self.query_one("#table", DataTable)
        cursor = table.cursor_coordinate
        table.clear(columns=True)

        base = [
            ("ID",     "id"),
            ("Ph",     "photo"),
            ("Phone",  "phone_number"),
            ("Status", "status"),
            ("F",      "flags"),
            ("Src",    "sources"),
            ("Name",   "name"),
            ("Family", "last_name"),
        ]
        if self.expanded:
            plats = core.list_platforms()
            for p in plats:
                base.append(((p["display_name"] or p["name"])[:14],
                             f"plat:{p['name']}"))
        else:
            base.append(("Platforms", "platforms"))
        base.append(("NC", "national_code"))

        self._cols = base
        table.add_columns(*[h for h, _ in base])

        try:
            table.cursor_coordinate = cursor
        except Exception:
            pass

    def _cell(self, r, key):
        socials = r.get("socials") or {}
        if key == "id":
            return str(r.get("id") or "")
        if key == "photo":
            return "[+]" if r.get("photo_path") else ""
        if key == "phone_number":
            return r.get("phone_number") or ""
        if key == "status":
            return r.get("status") or ""
        if key == "flags":
            f = ""
            if r.get("pinned"):  f += "P"
            if r.get("special"): f += "S"
            return f
        if key == "sources":
            return r.get("sources") or ""
        if key == "name":
            return r.get("name") or ""
        if key == "last_name":
            return r.get("last_name") or ""
        if key == "national_code":
            return r.get("national_code") or ""
        if key == "platforms":
            parts = []
            for p in core.list_platforms():
                s = socials.get(p["name"])
                if not s:
                    continue
                st = (s.get("exists_status") or "?").lower()
                mark = {"yes": "Y", "no": "N"}.get(st, "?")
                parts.append(f"{p['name']}:{mark}")
            return "  ".join(parts)
        if key.startswith("plat:"):
            return format_platform_cell(socials.get(key[5:]))
        return ""

    def reload_data(self):
        table = self.query_one("#table", DataTable)
        cursor = table.cursor_coordinate
        table.clear()

        self.rows = core.query_contacts(
            search=self.query_one("#search", Input).value or "",
        )
        self._row_index = {r["id"]: r for r in self.rows}

        for r in self.rows:
            table.add_row(
                *[self._cell(r, key) for _, key in self._cols],
                key=str(r["id"]),
            )
        try:
            table.cursor_coordinate = cursor
        except Exception:
            pass
        self._update_status(len(self.rows))

    def _update_status(self, count):
        mode = "expanded" if self.expanded else "compact"
        self.query_one("#status", Static).update(
            f" {count} contact(s)  •  view={mode}  •  "
            f"Ctrl+Q quit  Ctrl+F search  Ctrl+V view  F1 help"
        )

    def _selected_id(self):
        table = self.query_one("#table", DataTable)
        if table.row_count == 0:
            return None
        try:
            cell_key = table.coordinate_to_cell_key(table.cursor_coordinate)
        except Exception:
            return None
        row_key = cell_key.row_key
        if row_key is None or row_key.value is None:
            return None
        try:
            return int(row_key.value)
        except (TypeError, ValueError):
            return None

    def on_input_changed(self, event):
        if self._search_timer is not None:
            try:
                self._search_timer.stop()
            except Exception:
                pass
        self._search_timer = self.set_timer(0.15, self.reload_data)

    def on_input_submitted(self, event):
        self.query_one("#table", DataTable).focus()

    def on_data_table_row_highlighted(self, event):
        try:
            cid = int(event.row_key.value) if event.row_key else None
        except (TypeError, ValueError):
            cid = None
        if cid is None or cid == self._side_current:
            return
        self._side_current = cid
        r = self._row_index.get(cid)
        if r is not None:
            self._update_side_from_row(r)

    def on_data_table_row_selected(self, event):
        try:
            cid = int(event.row_key.value) if event.row_key else None
        except (TypeError, ValueError):
            cid = None
        if cid is not None:
            self.push_screen(DetailScreen(cid))

    def _update_side_from_row(self, r):
        cid = r["id"]
        flags = ""
        if r.get("pinned"):
            flags += "P "
        if r.get("special"):
            flags += "S"

        lines = [f"[b cyan]Contact #{cid}[/b cyan]"]
        lines.append(f"Phone  : {r.get('phone_number') or ''}")
        lines.append(f"Status : {r.get('status') or ''}")
        lines.append(f"Name   : {r.get('name') or ''} {r.get('last_name') or ''}")
        lines.append(f"NC     : {r.get('national_code') or ''}")
        lines.append(f"Flags  : {flags.strip() or '-'}")
        lines.append(f"Photo  : {r.get('photo_path') or '-'}")

        notes = r.get("notes")
        if notes:
            lines.append("")
            lines.append("[b cyan]Notes[/b cyan]")
            for line in str(notes).splitlines() or [notes]:
                lines.append(f"  {line}")

        lines.append("")
        lines.append("[b cyan]Socials[/b cyan]")
        socials = r.get("socials") or {}
        if not socials:
            lines.append("  (none)")
        for name, s in socials.items():
            cell = format_platform_cell(s)
            lines.append(f"  {name:10s} {cell or '-'}")

        lines.append("")
        lines.append("[b cyan]Sources[/b cyan]")
        src = (r.get("sources") or "").split()
        if src:
            for s in src:
                lines.append(f"  • {s}")
        else:
            lines.append("  • C")
        self.query_one("#side", Static).update("\n".join(lines))

    def action_focus_search(self):
        self.query_one("#search", Input).focus()

    def action_blur_input(self):
        self.query_one("#table", DataTable).focus()

    def action_reload_data(self):
        self.reload_data()

    def action_toggle_view(self):
        self.expanded = not self.expanded
        self._rebuild_columns()
        self.reload_data()
        self.notify(f"view: {'expanded' if self.expanded else 'compact'}")

    def action_open_folder(self):
        cid = self._selected_id()
        if cid is None:
            return
        try:
            core.open_contact_folder(cid)
            self.notify(f"opened folder for #{cid}")
        except Exception as e:
            self.notify(f"error: {e}", severity="error")

    def action_sync(self):
        try:
            core.run_sync()
            self.notify("Sync complete")
        except Exception as e:
            self.notify(f"Sync failed: {e}", severity="error")
        self.reload_data()

    def action_backup(self):
        try:
            p = bk.create_backup()
            bk.prune_old_backups(keep=20)
            self.notify(f"Backup: {p.name}")
        except Exception as e:
            self.notify(f"Backup failed: {e}", severity="error")

    def action_toggle_pin(self):
        cid = self._selected_id()
        if cid is None:
            return
        try:
            v = core.toggle_pin(cid)
            self.notify(f"#{cid} pinned={v}")
        except Exception as e:
            self.notify(f"error: {e}", severity="error")
        self.reload_data()

    def action_toggle_special(self):
        cid = self._selected_id()
        if cid is None:
            return
        try:
            v = core.toggle_special(cid)
            self.notify(f"#{cid} special={v}")
        except Exception as e:
            self.notify(f"error: {e}", severity="error")
        self.reload_data()

    def action_delete_contact(self):
        cid = self._selected_id()
        if cid is None:
            return

        def _do(confirmed):
            if not confirmed:
                return
            try:
                core.delete_contact(cid)
                self.notify(f"deleted #{cid}")
            except Exception as e:
                self.notify(f"error: {e}", severity="error")
            self.reload_data()

        self.push_screen(ConfirmScreen(f"Delete contact #{cid}?"), _do)

    def action_edit_contact(self):
        cid = self._selected_id()
        if cid is None:
            self.notify("No contact selected", severity="warning")
            return
        self.push_screen(EditContactScreen(cid, on_save=self.reload_data))

    def action_new_contact(self):
        self.push_screen(EditContactScreen(None, on_save=self.reload_data))

    def action_help(self):
        self.push_screen(HelpScreen())


def run_tui():
    ContactsTUI().run()
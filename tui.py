"""
Terminal UI for Contacts Manager (curses).

Features:
    - compact / expanded platform view (toggle with 'v')
    - horizontal column scrolling in expanded mode ('<' and '>')
    - a photo indicator in the list
    - pending navigation keys are drained to avoid arrow-key backlog
"""

import curses
import locale
import sys
from pathlib import Path

import core
import backup as bk
from db import list_platforms, platform_names
from branding import APP_NAME, APP_TITLE_SHORT

locale.setlocale(locale.LC_ALL, "")

STATUSES = ["all", "unchecked", "checking", "verified", "invalid", "anonymous"]

C_VERIFIED  = 1
C_INVALID   = 2
C_CHECKING  = 3
C_PINNED    = 4
C_SPECIAL   = 5
C_SELECTED  = 6
C_HEADER    = 7
C_FOOTER    = 8
C_ERROR     = 9
C_BORDER    = 10
C_ANONYMOUS = 11

NAV_KEYS = (
    curses.KEY_UP, curses.KEY_DOWN,
    curses.KEY_PPAGE, curses.KEY_NPAGE,
    curses.KEY_HOME, curses.KEY_END,
)


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


class TUIApp:
    def __init__(self, stdscr):
        self.s = stdscr
        self.search = ""
        self.status = "all"
        self.platform = "all"
        self.source = "all"
        self.rows = []
        self.sel = 0
        self.scroll = 0
        self.msg = ""
        self._need_reload = True

        self.expanded = False
        self.col_offset = 0

        try:
            curses.curs_set(0)
        except curses.error:
            pass
        try:
            curses.set_escdelay(25)
        except AttributeError:
            pass

        self._init_colors()

    def _init_colors(self):
        curses.start_color()
        try:
            curses.use_default_colors()
            bg = -1
        except Exception:
            bg = curses.COLOR_BLACK
        curses.init_pair(C_VERIFIED,  curses.COLOR_GREEN, bg)
        curses.init_pair(C_INVALID,   curses.COLOR_RED, bg)
        curses.init_pair(C_CHECKING,  curses.COLOR_YELLOW, bg)
        curses.init_pair(C_PINNED,    curses.COLOR_YELLOW, bg)
        curses.init_pair(C_SPECIAL,   curses.COLOR_CYAN, bg)
        curses.init_pair(C_SELECTED,  curses.COLOR_BLACK, curses.COLOR_CYAN)
        curses.init_pair(C_HEADER,    curses.COLOR_WHITE, curses.COLOR_BLUE)
        curses.init_pair(C_FOOTER,    curses.COLOR_WHITE, curses.COLOR_BLACK)
        curses.init_pair(C_ERROR,     curses.COLOR_RED, bg)
        curses.init_pair(C_BORDER,    curses.COLOR_CYAN, bg)
        curses.init_pair(C_ANONYMOUS, curses.COLOR_MAGENTA, bg)

    def run(self):
        self.s.keypad(True)
        self.s.timeout(-1)

        while True:
            if self._need_reload:
                self._reload()
                self._need_reload = False

            self._draw()

            key = self.s.getch()
            if key == -1:
                continue

            if not self._handle_key(key):
                break

            if key in NAV_KEYS or key in (ord("j"), ord("k")):
                self._drain_nav()

    def _drain_nav(self, max_keys: int = 500):
        self.s.timeout(0)
        try:
            for _ in range(max_keys):
                k = self.s.getch()
                if k == -1:
                    break
                if k in (curses.KEY_UP, ord("k")):
                    self.sel = max(0, self.sel - 1)
                elif k in (curses.KEY_DOWN, ord("j")):
                    if self.rows:
                        self.sel = min(len(self.rows) - 1, self.sel + 1)
                elif k == curses.KEY_PPAGE:
                    self.sel = max(0, self.sel - 10)
                elif k == curses.KEY_NPAGE:
                    if self.rows:
                        self.sel = min(len(self.rows) - 1, self.sel + 10)
                elif k == curses.KEY_HOME:
                    self.sel = 0
                elif k == curses.KEY_END:
                    self.sel = max(0, len(self.rows) - 1)
                else:
                    try:
                        curses.ungetch(k)
                    except curses.error:
                        pass
                    break
        finally:
            self.s.timeout(-1)

    def _reload(self):
        try:
            self.rows = core.query_contacts(
                search=self.search,
                status=self.status,
                platform=self.platform,
                source=self.source,
            )
        except Exception as e:
            self.rows = []
            self.msg = f"query failed: {e}"
        if self.sel >= len(self.rows):
            self.sel = max(0, len(self.rows) - 1)
        if self.sel < 0:
            self.sel = 0

    def _columns(self):
        cols = [
            ("ID",     5,  "id"),
            ("Ph",     3,  "photo"),
            ("Phone",  13, "phone_number"),
            ("St",     10, "status"),
            ("F",      3,  "flags"),
            ("Src",    6,  "sources"),
            ("Name",   12, "name"),
            ("Family", 14, "last_name"),
        ]
        if self.expanded:
            for p in core.list_platforms():
                disp = (p["display_name"] or p["name"])[:10]
                cols.append((disp, 6, f"plat:{p['name']}"))
        else:
            cols.append(("Platforms", 30, "platforms"))
        cols.append(("NC", 11, "national_code"))
        return cols

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

    def _cell_value(self, row, key):
        socials = row.get("socials") or {}
        if key == "id":
            return row.get("id")
        if key == "photo":
            return "[+]" if row.get("photo_path") else ""
        if key == "phone_number":
            return row.get("phone_number") or ""
        if key == "status":
            return row.get("status") or ""
        if key == "flags":
            flags = ""
            if row.get("pinned"):  flags += "P"
            if row.get("special"): flags += "S"
            return flags
        if key == "sources":
            return row.get("sources") or ""
        if key == "name":
            return row.get("name") or ""
        if key == "last_name":
            return row.get("last_name") or ""
        if key == "national_code":
            return row.get("national_code") or ""
        if key == "platforms":
            return self._platform_summary(socials, core.list_platforms())
        if key.startswith("plat:"):
            pname = key[5:]
            return format_platform_cell(socials.get(pname))
        return ""

    def _draw(self):
        self.s.erase()
        h, w = self.s.getmaxyx()

        title = f" {APP_TITLE_SHORT} "
        info = (f" search='{self.search}'  status={self.status}  "
                f"platform={self.platform}  source={self.source}  "
                f"view={'expanded' if self.expanded else 'compact'} ")
        try:
            self.s.attron(curses.color_pair(C_HEADER) | curses.A_BOLD)
            self.s.addstr(0, 0, (title + info).ljust(w - 1)[: w - 1])
            self.s.attroff(curses.color_pair(C_HEADER) | curses.A_BOLD)
        except curses.error:
            pass

        cols = self._columns() or []
        if not cols:
            self.s.refresh()
            return

        if self.col_offset >= len(cols):
            self.col_offset = max(0, len(cols) - 1)
        if self.col_offset < 0:
            self.col_offset = 0

        x = 0
        try:
            self.s.attron(curses.A_BOLD | curses.color_pair(C_BORDER))
            for name, cw, _ in cols[self.col_offset:]:
                if x + cw >= w:
                    break
                self.s.addstr(1, x, name[:cw].ljust(cw))
                x += cw + 1
            self.s.attroff(curses.A_BOLD | curses.color_pair(C_BORDER))
        except curses.error:
            pass

        visible = max(1, h - 4)
        if self.scroll > self.sel:
            self.scroll = self.sel
        if self.sel >= self.scroll + visible:
            self.scroll = self.sel - visible + 1

        for i in range(visible):
            idx = self.scroll + i
            if idx >= len(self.rows):
                break
            self._draw_row(2 + i, idx, cols, w)

        scroll_hint = "  </>=cols" if self.expanded else ""
        footer = (f" Enter=detail  e=edit  n=new  d=del  p=pin  t=special  "
                  f"o=folder  /=search  f=filter  F=platform  v=view{scroll_hint}  "
                  f"y=sync  b=backup  r=refresh  ?=help  q=quit ")
        try:
            self.s.attron(curses.color_pair(C_FOOTER))
            self.s.addstr(h - 1, 0, footer[: w - 1].ljust(w - 1))
            self.s.attroff(curses.color_pair(C_FOOTER))
        except curses.error:
            pass

        if self.msg:
            try:
                self.s.attron(curses.color_pair(C_ERROR) | curses.A_BOLD)
                self.s.addstr(h - 2, 0, self.msg[: w - 1].ljust(w - 1))
                self.s.attroff(curses.color_pair(C_ERROR) | curses.A_BOLD)
            except curses.error:
                pass

        self.s.refresh()

    def _draw_row(self, y, idx, cols, w):
        r = self.rows[idx]

        attr = curses.A_NORMAL
        if idx == self.sel:
            attr |= curses.color_pair(C_SELECTED) | curses.A_BOLD
        else:
            st = r.get("status")
            if st == "verified":
                attr |= curses.color_pair(C_VERIFIED)
            elif st == "invalid":
                attr |= curses.color_pair(C_INVALID)
            elif st == "checking":
                attr |= curses.color_pair(C_CHECKING)
            elif st == "anonymous":
                attr |= curses.color_pair(C_ANONYMOUS) | curses.A_BOLD
            if r.get("pinned"):
                attr |= curses.color_pair(C_PINNED) | curses.A_BOLD
            elif r.get("special"):
                attr |= curses.color_pair(C_SPECIAL)

        x = 0
        for _, cw, key in cols[self.col_offset:]:
            if x + cw >= w:
                break
            raw = self._cell_value(r, key)
            s = "" if raw is None else str(raw)
            if len(s) > cw:
                s = s[: max(0, cw - 1)] + "…"
            try:
                self.s.addstr(y, x, s.ljust(cw), attr)
            except curses.error:
                pass
            x += cw + 1

    def _handle_key(self, key):
        self.msg = ""

        if key in (ord("q"), 27):
            return False
        if key in (3, 17):
            return False

        if key in (curses.KEY_UP, ord("k")):
            self.sel = max(0, self.sel - 1)
        elif key in (curses.KEY_DOWN, ord("j")):
            if self.rows:
                self.sel = min(len(self.rows) - 1, self.sel + 1)
        elif key == curses.KEY_PPAGE:
            self.sel = max(0, self.sel - 10)
        elif key == curses.KEY_NPAGE:
            if self.rows:
                self.sel = min(len(self.rows) - 1, self.sel + 10)
        elif key in (curses.KEY_HOME, ord("g")):
            self.sel = 0
        elif key in (curses.KEY_END, ord("G")):
            self.sel = max(0, len(self.rows) - 1)
        elif key in (10, 13, curses.KEY_ENTER):
            self._show_detail()
        elif key == ord("e"):
            self._edit_selected()
        elif key == ord("n"):
            self._new_contact()
        elif key == ord("d"):
            self._delete_selected()
        elif key == ord("p"):
            self._toggle_pin()
            self._need_reload = True
        elif key == ord("t"):
            self._toggle_special()
            self._need_reload = True
        elif key == ord("o"):
            self._open_selected_folder()
        elif key == ord("/"):
            self.search = self._prompt("Search", self.search)
            self.sel = 0
            self.scroll = 0
            self._need_reload = True
        elif key == ord("f"):
            self._cycle_filter()
            self._need_reload = True
        elif key == ord("F"):
            self._choose_platform_filter()
        elif key == ord("v"):
            self.expanded = not self.expanded
            self.col_offset = 0
            self.msg = f"view: {'expanded' if self.expanded else 'compact'}"
        elif key in (ord("<"), ord(",")):
            self.col_offset = max(0, self.col_offset - 1)
        elif key in (ord(">"), ord(".")):
            cols = self._columns() or []
            if cols:
                self.col_offset = min(len(cols) - 1, self.col_offset + 1)
        elif key == ord("y"):
            self._sync()
            self._need_reload = True
        elif key == ord("b"):
            self._backup()
        elif key == ord("r"):
            self._need_reload = True
        elif key == ord("?"):
            self._show_help()
            self._need_reload = True

        return True

    def _flush_input(self):
        try:
            self.s.timeout(0)
            for _ in range(200):
                k = self.s.getch()
                if k == -1:
                    break
        finally:
            self.s.timeout(-1)

    def _prompt(self, label, default=""):
        h, w = self.s.getmaxyx()
        try:
            curses.curs_set(1)
        except curses.error:
            pass
        curses.echo()
        self.s.move(h - 2, 0)
        self.s.clrtoeol()
        prompt = f"{label} [{default}]: "
        try:
            self.s.addstr(h - 2, 0, prompt[: w - 1])
            self.s.refresh()
            raw = self.s.getstr(h - 2, min(len(prompt), w - 2), 500)
            value = raw.decode("utf-8", "replace")
        except Exception:
            value = ""
        curses.noecho()
        try:
            curses.curs_set(0)
        except curses.error:
            pass
        self._flush_input()
        return value or default

    def _cycle_filter(self):
        try:
            i = STATUSES.index(self.status)
            self.status = STATUSES[(i + 1) % len(STATUSES)]
        except ValueError:
            self.status = "all"
        self.sel = 0
        self.scroll = 0
        self.msg = f"status filter: {self.status}"

    def _choose_platform_filter(self):
        plats = ["all", "pinned", "special", "has_identity", "no_identity",
                 "with_photo", "no_photo"]
        for p in platform_names():
            plats.append(p)
            plats.append(f"{p}_yes")
            plats.append(f"{p}_no")
        self._show_list_picker("Platform filter", plats,
                               on_pick=self._set_platform)

    def _set_platform(self, val):
        self.platform = val or "all"
        self.sel = 0
        self.scroll = 0
        self.msg = f"platform filter: {self.platform}"
        self._need_reload = True

    def _show_list_picker(self, title, items, on_pick):
        h, w = self.s.getmaxyx()
        win_h = min(len(items) + 3, h - 4)
        win_w = min(50, w - 4)
        top = (h - win_h) // 2
        left = (w - win_w) // 2

        win = curses.newwin(win_h, win_w, top, left)
        win.keypad(True)
        win.box()
        win.addstr(0, 2, f" {title} ")
        idx = 0
        offset = 0

        while True:
            for i in range(win_h - 2):
                y = 1 + i
                j = offset + i
                if j >= len(items):
                    break
                win.move(y, 1)
                win.clrtoeol()
                marker = "> " if j == idx else "  "
                attr = curses.A_REVERSE if j == idx else curses.A_NORMAL
                try:
                    win.addstr(y, 1, (marker + str(items[j]))[: win_w - 2], attr)
                except curses.error:
                    pass
            win.refresh()

            k = win.getch()
            if k in (ord("q"), 27, 3, 17):
                break
            if k in (curses.KEY_UP, ord("k")):
                idx = max(0, idx - 1)
                if idx < offset:
                    offset = idx
            elif k in (curses.KEY_DOWN, ord("j")):
                idx = min(len(items) - 1, idx + 1)
                if idx >= offset + win_h - 2:
                    offset = idx - win_h + 3
            elif k in (10, 13, curses.KEY_ENTER):
                on_pick(items[idx])
                break

        del win
        self._flush_input()

    def _selected_row(self):
        if 0 <= self.sel < len(self.rows):
            return self.rows[self.sel]
        return None

    def _open_selected_folder(self):
        r = self._selected_row()
        if not r:
            return
        try:
            core.open_contact_folder(r["id"])
            self.msg = f"opened folder for #{r['id']}"
        except Exception as e:
            self.msg = f"error: {e}"

    def _show_detail(self):
        r = self._selected_row()
        if not r:
            return
        info = core.get_contact_detail(r["id"])
        lines = self._format_detail(info)

        h, w = self.s.getmaxyx()
        pad = curses.newpad(len(lines) + 2, max(w - 2, 40))
        pad.keypad(True)
        offset = 0

        while True:
            pad.erase()
            for i, line in enumerate(lines):
                try:
                    pad.addstr(i, 0, line[: w - 3])
                except curses.error:
                    pass
            visible = h - 4
            pad.refresh(offset, 0, 2, 1, h - 3, w - 2)

            try:
                self.s.addstr(h - 1, 0,
                              " up/down=scroll  q/Esc/Ctrl+Q=back "[: w - 1])
            except curses.error:
                pass
            self.s.refresh()

            k = pad.getch()
            if k in (ord("q"), 27, 3, 17):
                break
            if k in (curses.KEY_UP, ord("k")):
                offset = max(0, offset - 1)
            elif k in (curses.KEY_DOWN, ord("j")):
                offset = min(max(0, len(lines) - visible + 1), offset + 1)
            elif k == curses.KEY_PPAGE:
                offset = max(0, offset - visible)
            elif k == curses.KEY_NPAGE:
                offset = min(max(0, len(lines) - visible + 1), offset + visible)

            self.s.timeout(0)
            while True:
                k2 = self.s.getch()
                if k2 == -1:
                    break
                if k2 in (curses.KEY_UP, ord("k")):
                    offset = max(0, offset - 1)
                elif k2 in (curses.KEY_DOWN, ord("j")):
                    offset = min(max(0, len(lines) - visible + 1), offset + 1)
                else:
                    try:
                        curses.ungetch(k2)
                    except curses.error:
                        pass
                    break
            self.s.timeout(-1)

        del pad
        self._flush_input()

    def _format_detail(self, info):
        c = info["contact"]
        out = [""]
        out.append("=== Contact ===")
        for k in ("id", "phone_number", "status", "name", "last_name",
                  "national_code", "pinned", "special",
                  "created_at", "updated_at"):
            out.append(f"  {k:14s}: {c.get(k) if c.get(k) is not None else ''}")

        if c.get("photo_path"):
            out.append(f"  {'photo_path':14s}: {c['photo_path']}")

        if c.get("notes"):
            out.append("")
            out.append("=== Notes ===")
            for line in str(c["notes"]).splitlines() or [c["notes"]]:
                out.append(f"  {line}")

        out.append("")
        out.append("=== Socials ===")
        if not info["socials"]:
            out.append("  (none)")
        for s in info["socials"]:
            out.append(f"  {s['platform']:10s} exists={s['exists_status']:7s} "
                       f"username={s['username'] or ''} "
                       f"display={s['display_name'] or ''} "
                       f"uid={s['user_id'] or ''}")

        files = info.get("files") or []
        if files:
            out.append("")
            out.append("=== Files ===")
            for name, path, size in files:
                out.append(f"  {name}  ({size} bytes)")

        for src_name, row in (info.get("external") or {}).items():
            out.append("")
            out.append(f"=== External: {src_name} ===")
            for k, v in row.items():
                out.append(f"  {k:14s}= {v if v is not None else ''}")

        out.append("")
        out.append("=== Links ===")
        if not info["links"]:
            out.append("  (none)")
        for l in info["links"]:
            out.append(f"  {l['source_db']}.{l['source_table']}#{l['source_pk']}  "
                       f"match={l['match_key']}  "
                       f"value={l['match_value'] or ''}  "
                       f"conf={l['confidence']}")
        return out

    def _edit_selected(self):
        r = self._selected_row()
        if not r:
            return
        self._edit_contact(r["id"])

    def _new_contact(self):
        self._edit_contact(None)

    def _edit_contact(self, contact_id):
        if contact_id is not None:
            info = core.get_contact_detail(contact_id)
            c = info["contact"]
        else:
            c = {"phone_number": "", "status": "unchecked",
                 "name": "", "last_name": "", "national_code": "",
                 "notes": "", "photo_path": ""}

        phone = self._prompt("Phone", c.get("phone_number") or "")
        if not phone:
            self.msg = "aborted: phone is required"
            return
        name = self._prompt("Name", c.get("name") or "")
        last = self._prompt("Last name", c.get("last_name") or "")
        nc = self._prompt("National code", c.get("national_code") or "")

        notes = self._prompt(
            "Notes (use \\n for newline)",
            (c.get("notes") or "").replace("\n", "\\n"),
        )
        notes = notes.replace("\\n", "\n") if notes else ""

        photo = self._prompt("Photo path (empty to keep)",
                             c.get("photo_path") or "")

        status = self._prompt("Status", c.get("status") or "unchecked")

        try:
            if contact_id is None:
                new_id = core.create_contact(
                    phone, status=status,
                    name=name or None, last_name=last or None,
                    national_code=nc or None,
                    notes=notes or None,
                )
                contact_id = new_id
                self.msg = f"created #{new_id}"
                if photo:
                    try:
                        core.set_contact_photo(contact_id, photo)
                    except Exception as e:
                        self.msg = f"created, photo error: {e}"
            else:
                core.update_contact(
                    contact_id,
                    phone=phone, status=status,
                    name=name or None, last_name=last or None,
                    national_code=nc or None,
                    notes=notes or "",
                )
                self.msg = f"updated #{contact_id}"
                if photo and photo != (c.get("photo_path") or ""):
                    try:
                        core.set_contact_photo(contact_id, photo)
                    except Exception as e:
                        self.msg = f"updated, photo error: {e}"
        except Exception as e:
            self.msg = f"error: {e}"
        self._need_reload = True

    def _delete_selected(self):
        r = self._selected_row()
        if not r:
            return
        ans = self._prompt(f"Delete #{r['id']} and its files? (yes/no)", "no")
        if ans.strip().lower() not in ("y", "yes", "بله"):
            self.msg = "cancelled"
            return
        try:
            core.delete_contact(r["id"])
            self.msg = f"deleted #{r['id']}"
        except Exception as e:
            self.msg = f"error: {e}"
        self._need_reload = True

    def _toggle_pin(self):
        r = self._selected_row()
        if not r:
            return
        try:
            v = core.toggle_pin(r["id"])
            self.msg = f"#{r['id']} pinned={v}"
        except Exception as e:
            self.msg = f"error: {e}"

    def _toggle_special(self):
        r = self._selected_row()
        if not r:
            return
        try:
            v = core.toggle_special(r["id"])
            self.msg = f"#{r['id']} special={v}"
        except Exception as e:
            self.msg = f"error: {e}"

    def _sync(self):
        self.msg = "syncing ..."
        self._draw()
        try:
            core.run_sync()
            self.msg = "sync done"
        except Exception as e:
            self.msg = f"sync error: {e}"

    def _backup(self):
        try:
            p = bk.create_backup()
            bk.prune_old_backups(keep=20)
            self.msg = f"backup: {p.name}"
        except Exception as e:
            self.msg = f"backup error: {e}"

    def _show_help(self):
        lines = [
            "",
            f"{APP_NAME} - keyboard shortcuts",
            "",
            "  up / k          move up",
            "  down / j        move down",
            "  PgUp / PgDn     page up / down",
            "  g / G           first / last",
            "  Enter           detail view",
            "  e               edit selected (photo, notes, ...)",
            "  n               new contact",
            "  d               delete selected (removes its folder)",
            "  p               toggle pin",
            "  t               toggle special",
            "  o               open the contact's attachments folder",
            "  /               search",
            "  f               cycle status filter",
            "  F               pick platform filter",
            "  v               toggle compact / expanded view",
            "  < / >           shift column window (expanded mode)",
            "  y               sync databases",
            "  b               backup now",
            "  r               refresh",
            "  ?               this help",
            "  q / Esc         quit",
            "  Ctrl+Q / Ctrl+C quit",
            "",
            "Press any key to close.",
        ]
        h, w = self.s.getmaxyx()
        self.s.erase()
        for i, line in enumerate(lines):
            if i >= h - 1:
                break
            try:
                self.s.addstr(i, 0, line[: w - 1])
            except curses.error:
                pass
        self.s.refresh()
        self.s.getkey()
        self._flush_input()


def run_tui():
    try:
        curses.wrapper(lambda stdscr: TUIApp(stdscr).run())
    except ImportError:
        print("curses is not available on this system.")
        sys.exit(1)
    except KeyboardInterrupt:
        pass
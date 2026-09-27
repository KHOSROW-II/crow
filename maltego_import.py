"""
Import Maltego files (.mtgx / .mtg / .csv) into contacts.db.

Mapping:
    maltego.PhoneNumber  -> contacts.phone_number
    maltego.Person       -> contacts.name / last_name (first name, last name)
    maltego.Alias        -> contact_socials on platform "maltego"
    maltego.EmailAddress -> contact_socials on platform "maltego"
    maltego.URL          -> contact_socials on platform "maltego"

The user sees a preview dialog before the import runs and can toggle a few
behaviour options.
"""

import csv
import gzip
import io
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import core
from db import (
    connect, DB_PATH, normalize_phone, audit,
    add_platform, platform_names,
)
from text_utils import fa

BG         = "#1e1e1e"
BG_PANEL   = "#252526"
FG         = "#d4d4d4"
FG_DIM     = "#808080"
ACCENT     = "#0e639c"
ACCENT_HOV = "#1177bb"
OK_GREEN   = "#4ec9b0"

FONT_UI   = ("Tahoma", 10) if sys.platform == "win32" else ("Sans", 10)
FONT_MONO = ("Consolas", 10) if sys.platform == "win32" else ("Monospace", 10)

MALTEGO_PLATFORM = "maltego"

PHONE_TYPES = {"maltego.phonenumber", "maltego.phone", "maltego.phonenumbers"}
PERSON_TYPES = {"maltego.person", "maltego.persons"}
ALIAS_TYPES  = {"maltego.alias", "maltego.username", "maltego.nickname"}
EMAIL_TYPES  = {"maltego.emailaddress", "maltego.email"}
URL_TYPES    = {"maltego.url", "maltego.website", "maltego.website.url"}


# ------------------------------------------------------------
# Reading
# ------------------------------------------------------------
def _read_text(path):
    raw = Path(path).read_bytes()
    if raw[:2] == b"\x1f\x8b":
        try:
            return gzip.decompress(raw).decode("utf-8", errors="replace")
        except Exception:
            pass
    return raw.decode("utf-8", errors="replace")


def detect_file_type(path):
    ext = Path(path).suffix.lower()
    if ext in (".mtgx", ".mtg"):
        return "mtgx"
    if ext == ".csv":
        return "csv"
    raw = Path(path).read_bytes()[:8]
    if raw[:2] == b"\x1f\x8b" or raw.lstrip().startswith(b"<"):
        return "mtgx"
    return "csv"


# ------------------------------------------------------------
# Parsers
# ------------------------------------------------------------
def parse_mtgx(path):
    """Return (entities, edges)."""
    text = _read_text(path)
    try:
        root = ET.fromstring(text)
    except ET.ParseError as e:
        raise ValueError(f"Could not parse XML: {e}")

    entities = []
    edges = []

    # Modern format: <node id="..."> <MaltegoEntity type="...">
    for node in root.iter():
        tag = node.tag.split("}")[-1]
        if tag in ("node", "Node"):
            nid = node.get("id") or node.get("Id")
            for child in node:
                etype = child.get("type") or child.get("Type")
                if not etype or "." not in etype:
                    continue
                value, fields = _extract_value_fields(child)
                entities.append({
                    "id": nid or str(len(entities)),
                    "type": etype,
                    "value": value,
                    "fields": fields,
                })

    for node in root.iter():
        tag = node.tag.split("}")[-1]
        if tag in ("edge", "Edge", "link", "Link"):
            src = node.get("source") or node.get("Source")
            dst = node.get("target") or node.get("Target")
            if src and dst:
                edges.append((src, dst))

    # Legacy format: <Entity Type="maltego.PhoneNumber">
    if not entities:
        for node in root.iter():
            etype = node.get("Type") or node.get("type")
            if not etype or "." not in etype:
                continue
            value, fields = _extract_value_fields(node)
            entities.append({
                "id": node.get("id") or str(len(entities)),
                "type": etype,
                "value": value,
                "fields": fields,
            })

    # Legacy edges: <Link Source="..." Target="..."/>
    if not edges:
        for node in root.iter():
            tag = node.tag.split("}")[-1]
            if tag.lower() == "link":
                src = node.get("Source") or node.get("source")
                dst = node.get("Target") or node.get("target")
                if src and dst:
                    edges.append((src, dst))

    return entities, edges


def _extract_value_fields(node):
    value = None
    fields = {}
    for child in node:
        tag = child.tag.split("}")[-1]
        if tag.lower() == "value" and (child.text or "").strip():
            value = child.text.strip()
        elif tag.lower() in ("field", "property"):
            name = child.get("name") or child.get("displayName") or ""
            if name:
                fields[name] = (child.text or "").strip()
    if value is None:
        value = (node.text or "").strip() or None
    return value, fields


def parse_csv(path):
    text = _read_text(path)
    reader = csv.DictReader(io.StringIO(text))
    fields = reader.fieldnames or []
    lower = {f.lower(): f for f in fields}

    type_col = next((lower[c] for c in ("entity type", "type", "kind")
                     if c in lower), None)
    value_col = next((lower[c] for c in ("value", "entity", "text", "name")
                      if c in lower), None)

    entities, edges = [], []

    if type_col and value_col:
        for i, row in enumerate(reader):
            etype = (row.get(type_col) or "").strip()
            value = (row.get(value_col) or "").strip()
            if not value:
                continue
            entities.append({
                "id": str(i),
                "type": etype or "maltego.Phrase",
                "value": value,
                "fields": {},
            })
        return entities, edges

    if len(fields) >= 2:
        reader = csv.reader(io.StringIO(text))
        next(reader)
        for i, row in enumerate(reader):
            if len(row) < 2:
                continue
            s, t = row[0].strip(), row[1].strip()
            if not s or not t:
                continue
            entities.append({"id": f"s{i}", "type": "maltego.Phrase",
                             "value": s, "fields": {}})
            entities.append({"id": f"t{i}", "type": "maltego.Phrase",
                             "value": t, "fields": {}})
            edges.append((f"s{i}", f"t{i}"))
        return entities, edges

    raise ValueError("Unrecognised CSV format.")


# ------------------------------------------------------------
# Classification
# ------------------------------------------------------------
def classify(etype):
    t = (etype or "").strip().lower()
    if t in PHONE_TYPES:
        return "phone"
    if t in PERSON_TYPES:
        return "person"
    if t in ALIAS_TYPES:
        return "alias"
    if t in EMAIL_TYPES:
        return "email"
    if t in URL_TYPES:
        return "url"
    return "other"


# ------------------------------------------------------------
# Preview dialog
# ------------------------------------------------------------
class MaltegoImportPreview(tk.Toplevel):
    def __init__(self, parent, entities, edges, source_path):
        super().__init__(parent)
        self.entities = entities
        self.edges = edges
        self.source_path = source_path
        self.result = None

        self.title("Import Maltego file")
        self.configure(bg=BG)
        self.geometry("780x620")
        self.minsize(700, 540)
        self.transient(parent)
        self.grab_set()

        self._build()
        self._populate()
        self._center(parent)

    def _center(self, parent):
        self.update_idletasks()
        px = parent.winfo_rootx() + (parent.winfo_width()  - self.winfo_width())  // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{max(px, 0)}+{max(py, 0)}")

    def _build(self):
        info = tk.Frame(self, bg=BG)
        info.pack(fill="x", padx=12, pady=(12, 4))
        tk.Label(info, text=f"Source: {self.source_path}",
                 bg=BG, fg=FG_DIM, font=FONT_UI).pack(anchor="w")
        tk.Label(info,
                 text=f"{len(self.entities)} entities, {len(self.edges)} links",
                 bg=BG, fg=FG,
                 font=(FONT_UI[0], FONT_UI[1], "bold")).pack(anchor="w",
                                                             pady=(2, 0))

        wrap = tk.Frame(self, bg=BG)
        wrap.pack(fill="both", expand=True, padx=12, pady=6)

        cols = ("type", "count", "kind", "example")
        heads = ("Entity type", "Count", "Kind", "Example value")
        widths = {"type": 240, "count": 70, "kind": 100, "example": 280}

        self.tree = ttk.Treeview(wrap, columns=cols, show="headings")
        for c, h in zip(cols, heads):
            self.tree.heading(c, text=h)
            self.tree.column(c, width=widths[c],
                             anchor="center" if c == "count" else "w",
                             stretch=False)
        vs = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vs.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vs.grid(row=0, column=1, sticky="ns")
        wrap.rowconfigure(0, weight=1)
        wrap.columnconfigure(0, weight=1)

        opt = tk.Frame(self, bg=BG)
        opt.pack(fill="x", padx=12, pady=(4, 4))

        self.v_attach = tk.IntVar(value=1)
        tk.Checkbutton(opt,
                       text="Attach alias / email / URL entities to their "
                            "linked phone contact",
                       variable=self.v_attach,
                       bg=BG, fg=FG, selectcolor="#1b1b1b",
                       activebackground=BG, activeforeground=OK_GREEN,
                       font=FONT_UI).pack(anchor="w")

        self.v_skip = tk.IntVar(value=1)
        tk.Checkbutton(opt,
                       text="Skip phone numbers that already exist "
                            "(only add new social rows)",
                       variable=self.v_skip,
                       bg=BG, fg=FG, selectcolor="#1b1b1b",
                       activebackground=BG, activeforeground=OK_GREEN,
                       font=FONT_UI).pack(anchor="w")

        self.v_other = tk.IntVar(value=0)
        tk.Checkbutton(opt,
                       text="Also import non-phone entities as contacts "
                            "(prefix: mtg:)",
                       variable=self.v_other,
                       bg=BG, fg=FG, selectcolor="#1b1b1b",
                       activebackground=BG, activeforeground=OK_GREEN,
                       font=FONT_UI).pack(anchor="w")

        bar = tk.Frame(self, bg=BG)
        bar.pack(fill="x", padx=12, pady=(4, 12))

        tk.Button(bar, text="Import", command=self._import,
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

    def _populate(self):
        counts, example = {}, {}
        for e in self.entities:
            t = e["type"] or "(empty)"
            counts[t] = counts.get(t, 0) + 1
            if t not in example and e.get("value"):
                example[t] = e["value"]
        for t in sorted(counts):
            self.tree.insert("", "end", values=(
                t, counts[t], classify(t), example.get(t, "")
            ))

    def _import(self):
        self.result = {
            "attach":  bool(self.v_attach.get()),
            "skip":    bool(self.v_skip.get()),
            "other":   bool(self.v_other.get()),
        }
        self.destroy()


# ------------------------------------------------------------
# Perform import
# ------------------------------------------------------------
def _ensure_maltego_platform():
    if MALTEGO_PLATFORM not in platform_names():
        add_platform(MALTEGO_PLATFORM, "Maltego")


def _do_import(entities, edges, opts):
    _ensure_maltego_platform()

    ent_by_id = {e["id"]: e for e in entities if e.get("id")}
    neighbours = {}
    for s, d in edges:
        neighbours.setdefault(s, set()).add(d)
        neighbours.setdefault(d, set()).add(s)

    stats = {"created": 0, "skipped": 0, "socials": 0}

    with connect(DB_PATH) as conn:
        for entity in entities:
            kind = classify(entity["type"])
            if kind != "phone" and not (opts["other"] and entity.get("value")):
                continue

            raw = entity.get("value")
            if not raw:
                continue

            phone = normalize_phone(raw)
            if kind == "phone":
                if not phone:
                    # keep the raw value if it is not a valid IR number
                    phone = str(raw).strip()
            else:
                # synthesise a marker so the column stays unique
                phone = f"mtg:{raw}"

            existing = conn.execute(
                "SELECT id FROM contacts WHERE phone_number=?", (phone,)
            ).fetchone()

            if existing:
                if opts["skip"] and not opts["attach"]:
                    stats["skipped"] += 1
                    continue
                cid = existing["id"]
                if opts["skip"]:
                    stats["skipped"] += 1
            else:
                first, last = _names_from_neighbours(entity, neighbours, ent_by_id)
                cur = conn.execute("""
                    INSERT INTO contacts
                        (phone_number, status, name, last_name,
                         name_norm, last_name_norm)
                    VALUES (?, 'unchecked', ?, ?, ?, ?)
                """, (
                    phone, first, last,
                    (first or "").lower() or None,
                    (last or "").lower() or None,
                ))
                cid = cur.lastrowid
                stats["created"] += 1

            if not opts["attach"]:
                continue

            for nb_id in neighbours.get(entity["id"], []):
                nb = ent_by_id.get(nb_id)
                if not nb:
                    continue
                if classify(nb["type"]) not in ("alias", "email", "url"):
                    continue
                username = (nb.get("value") or "").strip() or None
                if not username:
                    continue

                row = conn.execute(
                    "SELECT id FROM contact_socials "
                    "WHERE contact_id=? AND platform=?",
                    (cid, MALTEGO_PLATFORM)
                ).fetchone()
                if row:
                    conn.execute("""
                        UPDATE contact_socials SET
                            username = COALESCE(username, ?),
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                    """, (username, row["id"]))
                else:
                    conn.execute("""
                        INSERT INTO contact_socials
                            (contact_id, platform, exists_status,
                             username, display_name)
                        VALUES (?, ?, 'yes', ?, ?)
                    """, (cid, MALTEGO_PLATFORM, username,
                          nb["type"]))
                    stats["socials"] += 1

    audit("maltego_import",
          f"entities={len(entities)}, created={stats['created']}, "
          f"skipped={stats['skipped']}, socials={stats['socials']}")
    core.log(f"[maltego] {stats}")
    return stats


def _names_from_neighbours(entity, neighbours, ent_by_id):
    first, last = None, None
    for nb_id in neighbours.get(entity["id"], []):
        nb = ent_by_id.get(nb_id)
        if not nb or classify(nb["type"]) != "person":
            continue
        raw = (nb.get("value") or "").strip()
        if not raw:
            continue
        parts = raw.split()
        if not first:
            first = parts[0]
        if len(parts) > 1 and not last:
            last = " ".join(parts[1:])
        if first and last:
            break
    return first, last


# ------------------------------------------------------------
# Entry point
# ------------------------------------------------------------
def run_import(parent):
    path = filedialog.askopenfilename(
        title="Import Maltego file",
        initialdir=".",
        filetypes=[
            ("Maltego files", "*.mtgx *.mtg *.csv"),
            ("Maltego Graph (.mtgx)", "*.mtgx"),
            ("Maltego XML (.mtg)", "*.mtg"),
            ("CSV", "*.csv"),
            ("All files", "*.*"),
        ],
    )
    if not path:
        return

    try:
        ftype = detect_file_type(path)
        if ftype == "mtgx":
            entities, edges = parse_mtgx(path)
        else:
            entities, edges = parse_csv(path)
    except Exception as e:
        messagebox.showerror("Parse failed", str(e), parent=parent)
        return

    if not entities:
        messagebox.showinfo("Import",
                            "No entities were found in this file.",
                            parent=parent)
        return

    dlg = MaltegoImportPreview(parent, entities, edges, path)
    parent.wait_window(dlg)
    if not dlg.result:
        return

    try:
        stats = _do_import(entities, edges, dlg.result)
    except Exception as e:
        messagebox.showerror("Import failed", str(e), parent=parent)
        return

    messagebox.showinfo(
        "Import complete",
        "Maltego import summary:\n\n"
        f"  Contacts created : {stats['created']}\n"
        f"  Contacts skipped : {stats['skipped']}\n"
        f"  Socials attached : {stats['socials']}",
        parent=parent,
    )
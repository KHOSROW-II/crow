"""
Simple link-analysis graph view (Maltego-style).

Renders contacts, identities, telegram users and platform accounts
as nodes on a tkinter Canvas, with edges representing the links
between them.

No external dependencies: rendering is done with plain canvas items.
"""

import math
import sys
import tkinter as tk
from tkinter import messagebox

import core
from text_utils import fa

# ------------------------------------------------------------
# Theme
# ------------------------------------------------------------
BG         = "#141414"
BG_PANEL   = "#1e1e1e"
FG         = "#d4d4d4"
FG_DIM     = "#808080"
ACCENT_HOV = "#1177bb"
SEL_COLOR  = "#ffffff"
EDGE_COLOR = "#4a4a4a"
EDGE_TEXT  = "#808080"

FONT_UI   = ("Tahoma", 10) if sys.platform == "win32" else ("Sans", 10)
FONT_NODE = ("Tahoma", 9)  if sys.platform == "win32" else ("Sans", 9)
FONT_INFO = ("Consolas", 10) if sys.platform == "win32" else ("Monospace", 10)

CONTACT_COLOR  = "#4a9eff"
IDENTITY_COLOR = "#4ec9b0"
TELEGRAM_COLOR = "#c586c0"

PLATFORM_COLORS = [
    "#dcdcaa", "#ce9178", "#569cd6", "#f48771",
    "#9cdcfe", "#b5cea8", "#d7ba7d", "#c8c8c8",
]

MAX_CONTACTS = 30


# ------------------------------------------------------------
# Data model
# ------------------------------------------------------------
class GraphNode:
    __slots__ = ("nid", "label", "kind", "data", "x", "y", "r", "items")
    def __init__(self, nid, label, kind, data, x, y, r=30):
        self.nid = nid
        self.label = label
        self.kind = kind
        self.data = data
        self.x = x
        self.y = y
        self.r = r
        self.items = []


class GraphEdge:
    __slots__ = ("src", "dst", "label")
    def __init__(self, src, dst, label=""):
        self.src = src
        self.dst = dst
        self.label = label


# ------------------------------------------------------------
# Graph window
# ------------------------------------------------------------
class GraphView(tk.Toplevel):

    def __init__(self, parent, contact_ids):
        super().__init__(parent)
        self.contact_ids = list(contact_ids)[:MAX_CONTACTS]
        self.truncated = len(contact_ids) > MAX_CONTACTS

        self.title(f"Graph view — {len(self.contact_ids)} contact(s)")
        self.configure(bg=BG)
        self.geometry("1280x800")
        self.minsize(900, 600)
        self.transient(parent)

        self.nodes = {}
        self.edges = []
        self.item_to_node = {}
        self.selected_nid = None
        self.transform = {"scale": 1.0, "dx": 0.0, "dy": 0.0}
        self._drag_start = None
        self._drag_origin = None

        self._build()
        self._build_graph()
        # delay fit until canvas has a real size
        self.after(80, self._fit_view)

    # --------------------------------------------------------
    # UI
    # --------------------------------------------------------
    def _build(self):
        bar = tk.Frame(self, bg=BG)
        bar.pack(fill="x", padx=8, pady=(8, 4))

        tk.Label(bar, text="Graph view", bg=BG, fg=FG,
                 font=(FONT_UI[0], FONT_UI[1], "bold")).pack(
            side="left", padx=(0, 14))

        self._btn(bar, "Fit",     self._fit_view)
        self._btn(bar, "Zoom +",  lambda: self._zoom(1.2))
        self._btn(bar, "Zoom -",  lambda: self._zoom(1 / 1.2))
        self._btn(bar, "Reset",   self._reset_view)

        tk.Button(bar, text="Close", command=self.destroy,
                  bg=BG_PANEL, fg=FG,
                  activebackground=ACCENT_HOV, activeforeground="white",
                  relief="flat", padx=12, pady=4, cursor="hand2",
                  font=FONT_UI).pack(side="right")

        main = tk.Frame(self, bg=BG)
        main.pack(fill="both", expand=True, padx=8, pady=(0, 6))

        self.canvas = tk.Canvas(main, bg=BG, highlightthickness=0)
        self.canvas.pack(side="left", fill="both", expand=True)

        side = tk.Frame(main, bg=BG_PANEL, width=300)
        side.pack(side="right", fill="y", padx=(6, 0))
        side.pack_propagate(False)

        tk.Label(side, text="Details", bg=BG_PANEL, fg=FG_DIM,
                 font=FONT_UI).pack(anchor="w", padx=8, pady=(8, 4))

        self.info_text = tk.Text(side, bg="#0c0c0c", fg=FG, relief="flat",
                                 font=FONT_INFO, wrap="word",
                                 width=36, height=40)
        self.info_text.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self._set_info("Click a node to see details.")

        tk.Label(side, text="Legend", bg=BG_PANEL, fg=FG_DIM,
                 font=FONT_UI).pack(anchor="w", padx=8, pady=(0, 4))
        legend = tk.Frame(side, bg=BG_PANEL)
        legend.pack(fill="x", padx=8, pady=(0, 8))

        self._legend_row(legend, CONTACT_COLOR,  "circle",  "Contact (phone)")
        self._legend_row(legend, IDENTITY_COLOR, "square",  "Identity")
        self._legend_row(legend, TELEGRAM_COLOR, "diamond", "Telegram user")
        self._legend_row(legend, "#dcdcaa",      "hex",     "Platform account")

        self.status = tk.Label(self, text="", bg=BG, fg=FG_DIM,
                               anchor="w", font=FONT_UI)
        self.status.pack(fill="x", padx=10, pady=(0, 4))

        self.canvas.bind("<Button-1>",        self._on_click)
        self.canvas.bind("<B1-Motion>",       self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Double-1>",        self._on_double)
        self.canvas.bind("<Button-4>",
                         lambda e: self._zoom(1.1, e.x, e.y))
        self.canvas.bind("<Button-5>",
                         lambda e: self._zoom(1 / 1.1, e.x, e.y))
        self.canvas.bind("<MouseWheel>",
                         lambda e: self._zoom(1.1 if e.delta > 0 else 1 / 1.1,
                                              e.x, e.y))
        self.canvas.bind("<Configure>", lambda _e: self._draw())

        # keyboard
        self.bind("<Escape>", lambda _e: self.destroy())
        self.bind("<f>",      lambda _e: self._fit_view())
        self.bind("<plus>",   lambda _e: self._zoom(1.2))
        self.bind("<minus>",  lambda _e: self._zoom(1 / 1.2))

    def _btn(self, parent, text, cmd):
        tk.Button(parent, text=text, command=cmd,
                  bg=BG_PANEL, fg=FG,
                  activebackground=ACCENT_HOV, activeforeground="white",
                  relief="flat", padx=10, pady=4, cursor="hand2",
                  font=FONT_UI).pack(side="left", padx=2)

    def _legend_row(self, parent, color, shape, text):
        row = tk.Frame(parent, bg=BG_PANEL)
        row.pack(fill="x", pady=2)
        c = tk.Canvas(row, width=20, height=16, bg=BG_PANEL,
                      highlightthickness=0)
        c.pack(side="left", padx=(0, 6))
        if shape == "circle":
            c.create_oval(2, 2, 18, 14, fill=color, outline="")
        elif shape == "square":
            c.create_rectangle(2, 2, 18, 14, fill=color, outline="")
        elif shape == "diamond":
            c.create_polygon(10, 1, 19, 8, 10, 15, 1, 8, fill=color, outline="")
        elif shape == "hex":
            pts = []
            for i in range(6):
                a = -math.pi / 2 + i * math.pi / 3
                pts.extend([10 + 7 * math.cos(a), 8 + 7 * math.sin(a)])
            c.create_polygon(pts, fill=color, outline="")
        tk.Label(row, text=text, bg=BG_PANEL, fg=FG,
                 font=FONT_NODE).pack(side="left")

    # --------------------------------------------------------
    # Build graph data
    # --------------------------------------------------------
    def _platform_color_map(self):
        plats = [p["name"] for p in core.list_platforms()]
        return {p: PLATFORM_COLORS[i % len(PLATFORM_COLORS)]
                for i, p in enumerate(plats)}

    def _build_graph(self):
        self.nodes.clear()
        self.edges.clear()
        self.item_to_node.clear()

        details = []
        for cid in self.contact_ids:
            info = core.get_contact_detail(cid)
            if info.get("contact"):
                details.append(info)

        if not details:
            return

        n = len(details)
        cols = max(1, int(math.ceil(math.sqrt(n))))
        cell_w, cell_h = 420, 340
        margin = 120

        edge_keys = set()

        def add_edge(a, b, label=""):
            key = (a, b) if a < b else (b, a)
            if key in edge_keys:
                return
            edge_keys.add(key)
            self.edges.append(GraphEdge(a, b, label))

        for i, info in enumerate(details):
            row = i // cols
            col = i % cols
            cx = margin + col * cell_w + cell_w // 2
            cy = margin + row * cell_h + cell_h // 2

            contact = info["contact"]
            cid = contact["id"]
            contact_nid = f"contact:{cid}"

            self.nodes[contact_nid] = GraphNode(
                contact_nid,
                contact.get("phone_number") or f"#{cid}",
                "contact",
                contact,
                cx, cy, r=42,
            )

            satellites = []

            # identity
            identity = info.get("identity") or {}
            if identity:
                iid = identity.get("id")
                identity_nid = f"identity:{iid}" if iid else f"identity:c{cid}"
                name = " ".join(x for x in
                                [identity.get("name"), identity.get("family")]
                                if x).strip() or "identity"
                if identity_nid not in self.nodes:
                    satellites.append((identity_nid, name,
                                       "identity", identity))
                else:
                    add_edge(contact_nid, identity_nid, "phone")

            # telegram
            tg = info.get("telegram") or {}
            if tg:
                tid = tg.get("id")
                tg_nid = f"telegram:{tid}" if tid else f"telegram:c{cid}"
                name = " ".join(x for x in
                                [tg.get("first_name"), tg.get("last_name")]
                                if x).strip()
                if not name:
                    name = tg.get("username") or "telegram"
                if tg_nid not in self.nodes:
                    satellites.append((tg_nid, name, "telegram", tg))
                else:
                    add_edge(contact_nid, tg_nid, "phone")

            # platforms
            for s in info.get("socials", []):
                if s.get("exists_status") != "yes":
                    continue
                plat = s["platform"]
                nid = f"platform:{cid}:{plat}"
                label = (s.get("username")
                         or s.get("display_name")
                         or plat)
                satellites.append((nid, label, f"platform:{plat}", s))

            # place satellites in a circle
            if satellites:
                count = len(satellites)
                step = 2 * math.pi / count
                dist = 140
                for j, (nid, label, kind, data) in enumerate(satellites):
                    angle = -math.pi / 2 + j * step
                    nx = cx + dist * math.cos(angle)
                    ny = cy + dist * math.sin(angle)
                    self.nodes[nid] = GraphNode(
                        nid, label, kind, data, nx, ny, r=30)
                    add_edge(contact_nid, nid)

        total = len(self.nodes)
        msg = f"{total} nodes, {len(self.edges)} edges"
        if self.truncated:
            msg += f"  (only first {MAX_CONTACTS} contacts shown)"
        self.status.config(text=msg)

    # --------------------------------------------------------
    # Coordinate transform
    # --------------------------------------------------------
    def _w2s(self, x, y):
        s = self.transform["scale"]
        return x * s + self.transform["dx"], y * s + self.transform["dy"]

    # --------------------------------------------------------
    # Draw
    # --------------------------------------------------------
    def _draw(self):
        self.canvas.delete("all")
        self.item_to_node.clear()

        # edges first (below nodes)
        for e in self.edges:
            n1 = self.nodes.get(e.src)
            n2 = self.nodes.get(e.dst)
            if not n1 or not n2:
                continue
            x1, y1 = self._w2s(n1.x, n1.y)
            x2, y2 = self._w2s(n2.x, n2.y)
            dx, dy = x2 - x1, y2 - y1
            d = math.hypot(dx, dy)
            if d == 0:
                continue
            r1 = n1.r * self.transform["scale"] + 2
            r2 = n2.r * self.transform["scale"] + 2
            ux, uy = dx / d, dy / d
            self.canvas.create_line(
                x1 + ux * r1, y1 + uy * r1,
                x2 - ux * r2, y2 - uy * r2,
                fill=EDGE_COLOR, width=1,
            )

        # nodes
        for node in self.nodes.values():
            self._draw_node(node)

    def _node_color(self, kind):
        if kind == "contact":
            return CONTACT_COLOR
        if kind == "identity":
            return IDENTITY_COLOR
        if kind == "telegram":
            return TELEGRAM_COLOR
        if kind.startswith("platform:"):
            plat = kind.split(":", 1)[1]
            return self._platform_colors.get(plat, "#9cdcfe")
        return "#808080"

    def _draw_node(self, node):
        x, y = self._w2s(node.x, node.y)
        r = max(8, node.r * self.transform["scale"])
        color = self._node_color(node.kind)
        selected = node.nid == self.selected_nid
        outline = SEL_COLOR if selected else "#0a0a0a"
        width = 3 if selected else 1

        items = []

        if node.kind == "contact":
            items.append(self.canvas.create_oval(
                x - r, y - r, x + r, y + r,
                fill=color, outline=outline, width=width))
        elif node.kind == "identity":
            items.append(self.canvas.create_rectangle(
                x - r, y - r * 0.8, x + r, y + r * 0.8,
                fill=color, outline=outline, width=width))
        elif node.kind == "telegram":
            pts = [x, y - r, x + r, y, x, y + r, x - r, y]
            items.append(self.canvas.create_polygon(
                pts, fill=color, outline=outline, width=width))
        elif node.kind.startswith("platform:"):
            pts = []
            for i in range(6):
                a = -math.pi / 2 + i * math.pi / 3
                pts.extend([x + r * math.cos(a), y + r * math.sin(a)])
            items.append(self.canvas.create_polygon(
                pts, fill=color, outline=outline, width=width))
        else:
            items.append(self.canvas.create_oval(
                x - r, y - r, x + r, y + r,
                fill=color, outline=outline, width=width))

        # label
        label = node.label or node.nid
        if isinstance(label, str):
            label = fa(label)
            if len(label) > 24:
                label = label[:22] + "…"
        text_item = self.canvas.create_text(
            x, y + r + 8,
            text=label, fill=FG, font=FONT_NODE, anchor="n",
        )
        items.append(text_item)

        for it in items:
            self.item_to_node[it] = node
        node.items = items

    # --------------------------------------------------------
    # Interaction
    # --------------------------------------------------------
    def _node_at(self, x, y):
        items = self.canvas.find_overlapping(x - 1, y - 1, x + 1, y + 1)
        for it in reversed(items):
            node = self.item_to_node.get(it)
            if node:
                return node
        return None

    def _on_click(self, event):
        node = self._node_at(event.x, event.y)
        if node:
            self.selected_nid = node.nid
            self._show_info(node)
            self._draw()
            return
        # start pan
        self._drag_start = (event.x, event.y)
        self._drag_origin = (self.transform["dx"], self.transform["dy"])

    def _on_drag(self, event):
        if not self._drag_start:
            return
        dx = event.x - self._drag_start[0]
        dy = event.y - self._drag_start[1]
        self.transform["dx"] = self._drag_origin[0] + dx
        self.transform["dy"] = self._drag_origin[1] + dy
        self._draw()

    def _on_release(self, _event):
        self._drag_start = None
        self._drag_origin = None

    def _on_double(self, event):
        node = self._node_at(event.x, event.y)
        if not node:
            return
        if node.kind == "contact":
            cid = node.data.get("id")
        else:
            # find a contact in the nid
            parts = node.nid.split(":")
            cid = None
            for p in parts:
                if p.startswith("c") and p[1:].isdigit():
                    cid = int(p[1:])
                    break
            if cid is None:
                # try to find from item_to_node by iterating edges
                for e in self.edges:
                    if e.dst == node.nid and e.src.startswith("contact:"):
                        cid = int(e.src.split(":", 1)[1])
                        break
                    if e.src == node.nid and e.dst.startswith("contact:"):
                        cid = int(e.dst.split(":", 1)[1])
                        break
        if cid is None:
            return

        # open detail window from parent
        try:
            self.parent._select_contact_by_id(cid)
            self.parent._open_detail()
        except Exception:
            pass

    def _zoom(self, factor, cx=None, cy=None):
        if cx is None:
            cx = self.canvas.winfo_width() / 2
            cy = self.canvas.winfo_height() / 2
        old = self.transform["scale"]
        new = max(0.15, min(4.0, old * factor))
        if abs(new - old) < 1e-6:
            return
        wx = (cx - self.transform["dx"]) / old
        wy = (cy - self.transform["dy"]) / old
        self.transform["scale"] = new
        self.transform["dx"] = cx - wx * new
        self.transform["dy"] = cy - wy * new
        self._draw()

    def _fit_view(self):
        if not self.nodes:
            return
        xs = [n.x for n in self.nodes.values()]
        ys = [n.y for n in self.nodes.values()]
        minx, maxx = min(xs) - 120, max(xs) + 120
        miny, maxy = min(ys) - 120, max(ys) + 120
        w = max(1, maxx - minx)
        h = max(1, maxy - miny)
        cw = max(200, self.canvas.winfo_width())
        ch = max(200, self.canvas.winfo_height())
        s = min(cw / w, ch / h, 1.6)
        self.transform["scale"] = s
        self.transform["dx"] = (cw - w * s) / 2 - minx * s
        self.transform["dy"] = (ch - h * s) / 2 - miny * s
        self._draw()

    def _reset_view(self):
        self.transform = {"scale": 1.0, "dx": 0.0, "dy": 0.0}
        self._fit_view()

    # --------------------------------------------------------
    # Info panel
    # --------------------------------------------------------
    def _set_info(self, text):
        self.info_text.configure(state="normal")
        self.info_text.delete("1.0", "end")
        self.info_text.insert("end", text)
        self.info_text.configure(state="disabled")

    def _show_info(self, node):
        lines = []
        lines.append(f"Kind : {node.kind}")
        lines.append(f"ID   : {node.nid}")
        lines.append("")

        if node.kind == "contact":
            d = node.data
            lines.append(f"phone        : {d.get('phone_number') or ''}")
            lines.append(f"status       : {d.get('status') or ''}")
            lines.append(f"name         : {d.get('name') or ''}")
            lines.append(f"last_name    : {d.get('last_name') or ''}")
            lines.append(f"national_code: {d.get('national_code') or ''}")
            lines.append(f"pinned       : {bool(d.get('pinned'))}")
            lines.append(f"special      : {bool(d.get('special'))}")
        elif node.kind == "identity":
            for k, v in node.data.items():
                lines.append(f"{k:13s}: {v if v is not None else ''}")
        elif node.kind == "telegram":
            for k, v in node.data.items():
                lines.append(f"{k:13s}: {v if v is not None else ''}")
        elif node.kind.startswith("platform:"):
            for k in ("platform", "exists_status", "username",
                      "display_name", "user_id", "verified_status"):
                lines.append(f"{k:13s}: {node.data.get(k) or ''}")

        # find connected contacts
        contacts = set()
        for e in self.edges:
            if e.src == node.nid and e.dst.startswith("contact:"):
                contacts.add(e.dst.split(":", 1)[1])
            elif e.dst == node.nid and e.src.startswith("contact:"):
                contacts.add(e.src.split(":", 1)[1])
        if contacts:
            lines.append("")
            lines.append("Linked contacts: " + ", ".join(sorted(contacts)))

        self._set_info("\n".join(lines))


# ------------------------------------------------------------
# Public helper
# ------------------------------------------------------------
def open_graph_view(parent, contact_ids):
    if not contact_ids:
        messagebox.showinfo(
            "Graph view",
            "Select at least one contact first.",
            parent=parent,
        )
        return None
    return GraphView(parent, contact_ids)
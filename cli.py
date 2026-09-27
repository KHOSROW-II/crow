"""
Full-featured CLI for Contacts Manager.
"""

import argparse
import json
import sys
from pathlib import Path
from branding import APP_NAME, APP_TITLE, APP_DESCRIPTION

import core
import backup as bk
from db import (
    list_platforms, add_platform, rename_platform, remove_platform,
    list_custom_tables, get_custom_table, create_custom_table,
    update_custom_table, delete_custom_table,
    list_custom_rows, insert_custom_row, update_custom_row,
    delete_custom_row, CUSTOM_COL_TYPES,
    DB_PATH,
)
import maltego_import


def _json_print(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def _pad(s, w):
    s = "" if s is None else str(s)
    if len(s) > w:
        s = s[: max(0, w - 1)] + "…"
    return s.ljust(w)


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


def _print_contacts_table(rows, view="compact"):
    if view == "expanded":
        plats = list_platforms()
        cols = [
            ("id", 5), ("ph", 2), ("phone", 13), ("status", 10),
            ("flags", 6), ("src", 6), ("name", 14), ("family", 18),
        ]
        for p in plats:
            cols.append((p["name"][:10], 6))
        cols.append(("nc", 11))
        cols.append(("notes", 25))
    else:
        cols = [
            ("id", 5), ("ph", 2), ("phone", 13), ("status", 10),
            ("flags", 6), ("src", 6), ("name", 14), ("family", 18),
            ("platforms", 30), ("nc", 11),
        ]

    header = "  ".join(_pad(h.upper(), w) for h, w in cols)
    print(header)
    print("-" * len(header))

    for r in rows:
        socials = r.get("socials") or {}
        flags = ""
        if r.get("pinned"):  flags += "P"
        if r.get("special"): flags += "S"

        photo_mark = "[+]" if r.get("photo_path") else ""

        values = [
            r.get("id"),
            photo_mark,
            r.get("phone_number"),
            r.get("status"),
            flags,
            r.get("sources"),
            r.get("name"),
            r.get("last_name"),
        ]

        if view == "expanded":
            for p in list_platforms():
                values.append(format_platform_cell(socials.get(p["name"])))
        else:
            parts = []
            for p in list_platforms():
                s = socials.get(p["name"])
                if not s:
                    continue
                st = (s.get("exists_status") or "?").lower()
                mark = {"yes": "Y", "no": "N"}.get(st, "?")
                parts.append(f"{p['name']}:{mark}")
            values.append("  ".join(parts))

        values.append(r.get("national_code") or "")
        if view == "expanded":
            notes = (r.get("notes") or "").replace("\n", " ")
            values.append(notes)

        print("  ".join(_pad(v, w) for (_, w), v in zip(cols, values)))
    print(f"\n{len(rows)} contact(s).")


def _print_platforms_table(rows):
    print(_pad("NAME", 20) + _pad("DISPLAY", 24) + _pad("BUILTIN", 8))
    print("-" * 52)
    for p in rows:
        print(_pad(p["name"], 20)
              + _pad(p["display_name"], 24)
              + _pad("yes" if p["is_builtin"] else "no", 8))


def _print_sources_table(rows):
    print(_pad("CODE", 5) + _pad("NAME", 14) + _pad("LABEL", 16)
          + _pad("DB PATH", 22) + _pad("TABLE", 20)
          + _pad("ENABLED", 8) + _pad("BUILT-IN", 9))
    print("-" * 94)
    for s in rows:
        print(_pad(s["code"], 5)
              + _pad(s["name"], 14)
              + _pad(s["label"], 16)
              + _pad(s["db_path"], 22)
              + _pad(s["table_name"], 20)
              + _pad("yes" if s["enabled"] else "no", 8)
              + _pad("yes" if s["is_builtin"] else "no", 9))


def _print_custom_tables(rows):
    print(_pad("NAME", 20) + _pad("DISPLAY", 28) + _pad("ID", 5))
    print("-" * 53)
    for t in rows:
        print(_pad(t["name"], 20) + _pad(t["display_name"], 28) + _pad(t["id"], 5))


def _print_rows(table, columns, rows):
    cols = [("id", 6)]
    for c in columns:
        cols.append((c["name"], max(12, min(24, len(c["name"]) + 6))))
    header = "  ".join(_pad(h.upper(), w) for h, w in cols)
    print(header)
    print("-" * len(header))
    for r in rows:
        vals = [r.get("id")]
        for c in columns:
            v = r.get(f"c_{c['name']}")
            vals.append("" if v is None else v)
        print("  ".join(_pad(v, w) for (_, w), v in zip(cols, vals)))
    print(f"\n{len(rows)} row(s) in '{table}'.")


# ------------------------------------------------------------
# Contacts
# ------------------------------------------------------------
def cmd_contacts_list(args):
    rows = core.query_contacts(
        search=args.search or "",
        status=args.status or "all",
        platform=args.platform or "all",
        source=args.source or "all",
    )
    if getattr(args, "photo_only", False):
        rows = [r for r in rows if r.get("photo_path")]
    if args.json:
        out = []
        for r in rows:
            d = dict(r)
            d["socials"] = list((r.get("socials") or {}).values())
            out.append(d)
        _json_print(out)
        return
    _print_contacts_table(rows, view=args.view or "compact")


def cmd_contacts_show(args):
    info = core.get_contact_detail(args.id)
    if not info["contact"]:
        print(f"[!] Contact #{args.id} not found.", file=sys.stderr)
        sys.exit(2)
    _json_print(info)


def cmd_contacts_add(args):
    try:
        cid = core.create_contact(
            args.phone, status=args.status or "unchecked",
            name=args.name, last_name=args.last_name,
            national_code=args.national_code,
            notes=args.notes,
            pinned=bool(args.pinned), special=bool(args.special),
        )
    except Exception as e:
        print(f"[!] {e}", file=sys.stderr); sys.exit(3)

    if args.photo:
        try:
            core.set_contact_photo(cid, args.photo)
        except Exception as e:
            print(f"[!] photo error: {e}", file=sys.stderr)
    print(f"created contact #{cid}")


def cmd_contacts_edit(args):
    kwargs = {}
    if args.phone is not None:         kwargs["phone"] = args.phone
    if args.status is not None:        kwargs["status"] = args.status
    if args.name is not None:          kwargs["name"] = args.name
    if args.last_name is not None:     kwargs["last_name"] = args.last_name
    if args.national_code is not None: kwargs["national_code"] = args.national_code
    if args.notes is not None:         kwargs["notes"] = args.notes
    if args.pinned is not None:        kwargs["pinned"] = bool(args.pinned)
    if args.special is not None:       kwargs["special"] = bool(args.special)
    try:
        core.update_contact(args.id, **kwargs)
    except Exception as e:
        print(f"[!] {e}", file=sys.stderr); sys.exit(3)

    if args.photo:
        try:
            core.set_contact_photo(args.id, args.photo)
        except Exception as e:
            print(f"[!] photo error: {e}", file=sys.stderr)
    print(f"updated contact #{args.id}")


def cmd_contacts_notes(args):
    try:
        core.set_notes(args.id, args.text)
    except Exception as e:
        print(f"[!] {e}", file=sys.stderr); sys.exit(3)
    print(f"notes for #{args.id} updated")


def cmd_contacts_photo(args):
    try:
        p = core.set_contact_photo(args.id, args.path)
    except Exception as e:
        print(f"[!] {e}", file=sys.stderr); sys.exit(3)
    print(f"photo set: {p}")


def cmd_contacts_clear_photo(args):
    try:
        core.clear_contact_photo(args.id)
    except Exception as e:
        print(f"[!] {e}", file=sys.stderr); sys.exit(3)
    print(f"photo cleared for #{args.id}")


def cmd_contacts_open(args):
    core.open_contact_folder(args.id)
    print(f"opened attachments folder for #{args.id}")


def cmd_contacts_files(args):
    files = core.list_contact_files(args.id)
    if not files:
        print("(no files)")
        return
    for name, path, size in files:
        print(f"{name:40s} {size:>10} bytes")


def cmd_contacts_delete(args):
    try:
        core.delete_contact(args.id)
    except Exception as e:
        print(f"[!] {e}", file=sys.stderr); sys.exit(3)
    print(f"deleted contact #{args.id}")


def cmd_contacts_pin(args):
    if args.off: core.set_pinned_many([args.id], False); print(f"unpinned #{args.id}")
    elif args.on: core.set_pinned_many([args.id], True); print(f"pinned #{args.id}")
    else: print(f"#{args.id} pinned={core.toggle_pin(args.id)}")


def cmd_contacts_special(args):
    if args.off: core.set_special_many([args.id], False); print(f"unset special #{args.id}")
    elif args.on: core.set_special_many([args.id], True); print(f"set special #{args.id}")
    else: print(f"#{args.id} special={core.toggle_special(args.id)}")


def cmd_contacts_social_set(args):
    try:
        core.update_social(
            args.id, args.platform,
            exists_status=args.status,
            username=args.username,
            display_name=args.display_name,
            user_id=args.user_id,
        )
    except Exception as e:
        print(f"[!] {e}", file=sys.stderr); sys.exit(3)
    print(f"social {args.platform} updated for #{args.id}")


def cmd_contacts_social_remove(args):
    core.delete_social(args.id, args.platform)
    print(f"social {args.platform} removed from #{args.id}")


# ------------------------------------------------------------
# Import / sync
# ------------------------------------------------------------
def cmd_import_json(args):
    n = core.import_from_json(args.path)
    print(f"imported {n} contact(s)")


def cmd_import_maltego(args):
    path = args.path
    ftype = maltego_import.detect_file_type(path)
    if ftype == "mtgx":
        entities, edges = maltego_import.parse_mtgx(path)
    else:
        entities, edges = maltego_import.parse_csv(path)
    opts = {"attach": True, "skip": not args.include_existing, "other": args.other}
    stats = maltego_import._do_import(entities, edges, opts)
    if args.json:
        _json_print(stats)
    else:
        print(f"created={stats['created']} skipped={stats['skipped']} "
              f"socials={stats['socials']}")


def cmd_sync(_args):
    total = core.run_sync()
    print(f"total matches: {total}")


# ------------------------------------------------------------
# Backup
# ------------------------------------------------------------
def cmd_backup(args):
    p = bk.create_backup(tag=args.tag or "")
    bk.prune_old_backups(keep=args.keep)
    print(f"backup saved -> {p}")


def cmd_backups_list(_args):
    files = bk.list_backups()
    if not files:
        print("(no backups)"); return
    for f in files:
        print(f"{f.name}  {f.stat().st_size:>10} bytes")


def cmd_restore(args):
    restored = bk.restore_backup(args.path)
    print(f"restored: {', '.join(restored) or '(nothing)'}")


# ------------------------------------------------------------
# Export / report
# ------------------------------------------------------------
def cmd_export_csv(args):
    p = core.export_csv(args.path or "reports/contacts_wide.csv")
    print(f"csv -> {p}" if p else "export failed")


def cmd_export_excel(args):
    p = core.export_excel(args.path or "reports/contacts_wide.xlsx")
    print(f"excel -> {p}" if p else "export failed")


def cmd_report(_args):
    rows = core.build_report_rows()
    total = len(rows)
    counts = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    print(f"total contacts : {total}")
    for st in ("unchecked", "checking", "verified", "invalid", "anonymous"):
        print(f"  {st:10s}: {counts.get(st, 0)}")
    print(f"  pinned     : {sum(1 for r in rows if r.get('pinned'))}")
    print(f"  special    : {sum(1 for r in rows if r.get('special'))}")
    print(f"  with photo : {sum(1 for r in rows if r.get('photo_path'))}")


# ------------------------------------------------------------
# Platforms
# ------------------------------------------------------------
def cmd_platform_list(args):
    plats = list_platforms()
    if args.json: _json_print(plats)
    else: _print_platforms_table(plats)


def cmd_platform_add(args):
    try: add_platform(args.name, args.display)
    except Exception as e: print(f"[!] {e}", file=sys.stderr); sys.exit(3)
    print(f"platform '{args.name}' added")


def cmd_platform_rename(args):
    try: rename_platform(args.name, args.display)
    except Exception as e: print(f"[!] {e}", file=sys.stderr); sys.exit(3)
    print(f"platform '{args.name}' renamed")


def cmd_platform_remove(args):
    try: remove_platform(args.name)
    except Exception as e: print(f"[!] {e}", file=sys.stderr); sys.exit(3)
    print(f"platform '{args.name}' removed")


# ------------------------------------------------------------
# Data sources
# ------------------------------------------------------------
def cmd_source_list(args):
    srcs = core.list_data_sources()
    if args.json: _json_print(srcs)
    else: _print_sources_table(srcs)


def cmd_source_show(args):
    s = core.get_data_source(args.name)
    if not s:
        print(f"[!] source '{args.name}' not found.", file=sys.stderr)
        sys.exit(2)
    _json_print(s)


def cmd_source_add(args):
    try:
        core.add_data_source({
            "name":                 args.name,
            "label":                args.label or args.name,
            "code":                 args.code or "?",
            "db_path":              args.db,
            "table_name":           args.table,
            "pk_column":            args.pk or "id",
            "phone_fields":         [x.strip() for x in (args.phone_fields or "").split(",") if x.strip()],
            "name_columns":         [x.strip() for x in (args.name_columns or "").split(",") if x.strip()],
            "national_code_column": args.nc_column or None,
            "matchers":             (args.matchers or "phone").split(","),
            "create_missing":       bool(args.create_missing),
            "social_platform":      args.social_platform or None,
            "enabled":              not args.disabled,
            "sort_order":           args.sort_order,
        })
    except Exception as e:
        print(f"[!] {e}", file=sys.stderr); sys.exit(3)
    print(f"source '{args.name}' added")


def cmd_source_remove(args):
    try: core.remove_data_source(args.name)
    except Exception as e: print(f"[!] {e}", file=sys.stderr); sys.exit(3)
    print(f"source '{args.name}' removed")


def cmd_source_match(args):
    src = core.get_data_source(args.name)
    if not src:
        print(f"[!] source '{args.name}' not found.", file=sys.stderr)
        sys.exit(2)
    n = core.match_with_source(src)
    print(f"matched: {n}")


# ------------------------------------------------------------
# Custom tables
# ------------------------------------------------------------
def _parse_column_spec(spec):
    parts = spec.split(":", 3)
    name = parts[0].strip().lower()
    col = {"name": name, "display_name": name.replace("_", " ").title(),
           "col_type": "text", "is_required": False, "default_value": None}
    if len(parts) > 1 and parts[1].strip():
        col["col_type"] = parts[1].strip().lower()
    if len(parts) > 2 and parts[2].strip():
        col["is_required"] = parts[2].strip() in ("1", "true", "yes")
    if len(parts) > 3 and parts[3].strip():
        col["default_value"] = parts[3]
    return col


def cmd_table_list(args):
    tables = list_custom_tables()
    if args.json: _json_print(tables)
    else: _print_custom_tables(tables)


def cmd_table_show(args):
    info = get_custom_table(args.name)
    if not info:
        print(f"[!] table '{args.name}' not found.", file=sys.stderr)
        sys.exit(2)
    _, columns, rows = list_custom_rows(args.name)
    if args.json:
        _json_print({"table": info["table"], "columns": columns, "rows": rows})
        return
    print(f"table: {info['table']['display_name']} ({info['table']['name']})")
    print("columns:")
    for c in columns:
        flag = "required" if c["is_required"] else "optional"
        print(f"  - {c['name']:18s} {c['col_type']:8s} {flag}")
    print()
    _print_rows(args.name, columns, rows)


def cmd_table_create(args):
    cols = [_parse_column_spec(s) for s in args.column or []]
    if not cols:
        print("[!] at least one --column required.", file=sys.stderr); sys.exit(2)
    try:
        create_custom_table(args.name, args.display or args.name, cols,
                            description=args.description)
    except Exception as e:
        print(f"[!] {e}", file=sys.stderr); sys.exit(3)
    print(f"table '{args.name}' created")


def cmd_table_drop(args):
    try: delete_custom_table(args.name)
    except Exception as e: print(f"[!] {e}", file=sys.stderr); sys.exit(3)
    print(f"table '{args.name}' dropped")


def cmd_table_rows(args):
    _, columns, rows = list_custom_rows(args.name)
    if args.json: _json_print(rows)
    else: _print_rows(args.name, columns, rows)


def cmd_table_row_add(args):
    data = dict(pair.split("=", 1) for pair in args.set if "=" in pair)
    try: rid = insert_custom_row(args.name, data)
    except Exception as e: print(f"[!] {e}", file=sys.stderr); sys.exit(3)
    print(f"row #{rid} inserted")


def cmd_table_row_edit(args):
    data = dict(pair.split("=", 1) for pair in args.set if "=" in pair)
    try: update_custom_row(args.name, args.id, data)
    except Exception as e: print(f"[!] {e}", file=sys.stderr); sys.exit(3)
    print(f"row #{args.id} updated")


def cmd_table_row_del(args):
    try: delete_custom_row(args.name, args.id)
    except Exception as e: print(f"[!] {e}", file=sys.stderr); sys.exit(3)
    print(f"row #{args.id} deleted")


# ------------------------------------------------------------
# Argparser
# ------------------------------------------------------------
def _build_parser():
    p = argparse.ArgumentParser(
        prog=APP_NAME.lower(),
        description=f"{APP_NAME} — {APP_DESCRIPTION} CLI",
    )
    sub = p.add_subparsers(dest="command", required=True)

    c = sub.add_parser("contacts", help="contact operations")
    csub = c.add_subparsers(dest="sub", required=True)

    cl = csub.add_parser("list")
    cl.add_argument("--search", "-s", default="")
    cl.add_argument("--status", default="all",
                    choices=["all", "unchecked", "checking",
                             "verified", "invalid", "anonymous"])
    cl.add_argument("--platform", default="all")
    cl.add_argument("--source", default="all")
    cl.add_argument("--view", default="compact",
                    choices=["compact", "expanded"])
    cl.add_argument("--photo-only", dest="photo_only", action="store_true")
    cl.add_argument("--json", action="store_true")
    cl.set_defaults(func=cmd_contacts_list)

    cs = csub.add_parser("show")
    cs.add_argument("id", type=int)
    cs.set_defaults(func=cmd_contacts_show)

    ca = csub.add_parser("add")
    ca.add_argument("--phone", required=True)
    ca.add_argument("--status", default="unchecked")
    ca.add_argument("--name")
    ca.add_argument("--last-name", dest="last_name")
    ca.add_argument("--national-code", dest="national_code")
    ca.add_argument("--notes")
    ca.add_argument("--photo")
    ca.add_argument("--pinned", action="store_true")
    ca.add_argument("--special", action="store_true")
    ca.set_defaults(func=cmd_contacts_add)

    ce = csub.add_parser("edit")
    ce.add_argument("id", type=int)
    ce.add_argument("--phone")
    ce.add_argument("--status")
    ce.add_argument("--name")
    ce.add_argument("--last-name", dest="last_name")
    ce.add_argument("--national-code", dest="national_code")
    ce.add_argument("--notes")
    ce.add_argument("--photo")
    ce.add_argument("--pinned", type=int, choices=[0, 1])
    ce.add_argument("--special", type=int, choices=[0, 1])
    ce.set_defaults(func=cmd_contacts_edit)

    cnotes = csub.add_parser("notes", help="set the notes field")
    cnotes.add_argument("id", type=int)
    cnotes.add_argument("text", help="use '' to clear")
    cnotes.set_defaults(func=cmd_contacts_notes)

    cphoto = csub.add_parser("photo", help="attach a photo to a contact")
    cphoto.add_argument("id", type=int)
    cphoto.add_argument("path")
    cphoto.set_defaults(func=cmd_contacts_photo)

    cclear = csub.add_parser("clear-photo", help="remove the photo")
    cclear.add_argument("id", type=int)
    cclear.set_defaults(func=cmd_contacts_clear_photo)

    copen = csub.add_parser("open",
                            help="open the contact's attachments folder")
    copen.add_argument("id", type=int)
    copen.set_defaults(func=cmd_contacts_open)

    cfiles = csub.add_parser("files",
                             help="list files in the contact's folder")
    cfiles.add_argument("id", type=int)
    cfiles.set_defaults(func=cmd_contacts_files)

    cd = csub.add_parser("delete"); cd.add_argument("id", type=int)
    cd.set_defaults(func=cmd_contacts_delete)

    cp = csub.add_parser("pin"); cp.add_argument("id", type=int)
    g = cp.add_mutually_exclusive_group()
    g.add_argument("--on", action="store_true"); g.add_argument("--off", action="store_true")
    cp.set_defaults(func=cmd_contacts_pin)

    csp = csub.add_parser("special"); csp.add_argument("id", type=int)
    g = csp.add_mutually_exclusive_group()
    g.add_argument("--on", action="store_true"); g.add_argument("--off", action="store_true")
    csp.set_defaults(func=cmd_contacts_special)

    csoc = csub.add_parser("social")
    ssoc = csoc.add_subparsers(dest="sub2", required=True)
    sset = ssoc.add_parser("set")
    sset.add_argument("id", type=int); sset.add_argument("platform")
    sset.add_argument("--status", choices=["unknown", "yes", "no"])
    sset.add_argument("--username")
    sset.add_argument("--display-name", dest="display_name")
    sset.add_argument("--user-id", dest="user_id")
    sset.set_defaults(func=cmd_contacts_social_set)
    srm = ssoc.add_parser("remove")
    srm.add_argument("id", type=int); srm.add_argument("platform")
    srm.set_defaults(func=cmd_contacts_social_remove)

    imp = sub.add_parser("import")
    isub = imp.add_subparsers(dest="sub", required=True)
    ij = isub.add_parser("json"); ij.add_argument("path", nargs="?", default=None)
    ij.set_defaults(func=cmd_import_json)
    im = isub.add_parser("maltego"); im.add_argument("path")
    im.add_argument("--other", action="store_true")
    im.add_argument("--include-existing", action="store_true")
    im.add_argument("--json", action="store_true")
    im.set_defaults(func=cmd_import_maltego)

    sy = sub.add_parser("sync"); sy.set_defaults(func=cmd_sync)

    bkp = sub.add_parser("backup")
    bkp.add_argument("--tag", default=""); bkp.add_argument("--keep", type=int, default=20)
    bkp.set_defaults(func=cmd_backup)
    bl = sub.add_parser("backups"); bl.set_defaults(func=cmd_backups_list)
    rs = sub.add_parser("restore"); rs.add_argument("path")
    rs.set_defaults(func=cmd_restore)

    ex = sub.add_parser("export")
    esub = ex.add_subparsers(dest="sub", required=True)
    ec = esub.add_parser("csv"); ec.add_argument("path", nargs="?", default=None)
    ec.set_defaults(func=cmd_export_csv)
    ee = esub.add_parser("excel"); ee.add_argument("path", nargs="?", default=None)
    ee.set_defaults(func=cmd_export_excel)

    rp = sub.add_parser("report"); rp.set_defaults(func=cmd_report)

    pl = sub.add_parser("platform")
    psub = pl.add_subparsers(dest="sub", required=True)
    plist = psub.add_parser("list"); plist.add_argument("--json", action="store_true")
    plist.set_defaults(func=cmd_platform_list)
    padd = psub.add_parser("add"); padd.add_argument("name"); padd.add_argument("--display")
    padd.set_defaults(func=cmd_platform_add)
    pren = psub.add_parser("rename"); pren.add_argument("name"); pren.add_argument("display")
    pren.set_defaults(func=cmd_platform_rename)
    prm = psub.add_parser("remove"); prm.add_argument("name")
    prm.set_defaults(func=cmd_platform_remove)

    sr = sub.add_parser("source", help="manage external data sources")
    ssub = sr.add_subparsers(dest="sub", required=True)

    sl = ssub.add_parser("list"); sl.add_argument("--json", action="store_true")
    sl.set_defaults(func=cmd_source_list)
    ss = ssub.add_parser("show"); ss.add_argument("name")
    ss.set_defaults(func=cmd_source_show)
    sa = ssub.add_parser("add")
    sa.add_argument("name")
    sa.add_argument("--label")
    sa.add_argument("--code")
    sa.add_argument("--db", required=True)
    sa.add_argument("--table", required=True)
    sa.add_argument("--pk", default="id")
    sa.add_argument("--phone-fields", dest="phone_fields", default="")
    sa.add_argument("--name-columns", dest="name_columns", default="")
    sa.add_argument("--nc-column", dest="nc_column", default="")
    sa.add_argument("--matchers", default="phone")
    sa.add_argument("--create-missing", dest="create_missing", action="store_true")
    sa.add_argument("--social-platform", dest="social_platform", default="")
    sa.add_argument("--disabled", action="store_true")
    sa.add_argument("--sort-order", dest="sort_order", type=int, default=100)
    sa.set_defaults(func=cmd_source_add)
    srm2 = ssub.add_parser("remove"); srm2.add_argument("name")
    srm2.set_defaults(func=cmd_source_remove)
    sm = ssub.add_parser("match"); sm.add_argument("name")
    sm.set_defaults(func=cmd_source_match)

    tl = sub.add_parser("table")
    tsub = tl.add_subparsers(dest="sub", required=True)
    tlist = tsub.add_parser("list"); tlist.add_argument("--json", action="store_true")
    tlist.set_defaults(func=cmd_table_list)
    tshow = tsub.add_parser("show"); tshow.add_argument("name"); tshow.add_argument("--json", action="store_true")
    tshow.set_defaults(func=cmd_table_show)
    tcre = tsub.add_parser("create"); tcre.add_argument("name")
    tcre.add_argument("--display"); tcre.add_argument("--description")
    tcre.add_argument("--column", action="append", default=[])
    tcre.set_defaults(func=cmd_table_create)
    tdrop = tsub.add_parser("drop"); tdrop.add_argument("name")
    tdrop.set_defaults(func=cmd_table_drop)
    trows = tsub.add_parser("rows"); trows.add_argument("name"); trows.add_argument("--json", action="store_true")
    trows.set_defaults(func=cmd_table_rows)
    tradd = tsub.add_parser("row-add"); tradd.add_argument("name")
    tradd.add_argument("--set", action="append", default=[])
    tradd.set_defaults(func=cmd_table_row_add)
    tredit = tsub.add_parser("row-edit"); tredit.add_argument("name"); tredit.add_argument("id", type=int)
    tredit.add_argument("--set", action="append", default=[])
    tredit.set_defaults(func=cmd_table_row_edit)
    trdel = tsub.add_parser("row-del"); trdel.add_argument("name"); trdel.add_argument("id", type=int)
    trdel.set_defaults(func=cmd_table_row_del)

    return p


def run_cli(argv=None):
    p = _build_parser()
    args = p.parse_args(argv)
    args.func(args)
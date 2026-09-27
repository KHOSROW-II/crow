<div align="center">

# CROW

### INTELLIGENCE PLATFORM

*A unified, self-hosted platform for contact intelligence, cross-database correlation, and encrypted personal data management.*

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![SQLite](https://img.shields.io/badge/SQLite-3-003B57?logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Linux%20%7C%20macOS%20%7C%20Windows-lightgrey)](#installation)
[![Interface](https://img.shields.io/badge/Interface-GUI%20%7C%20TUI%20%7C%20CLI-blue)](#interfaces)

</div>

---

## Table of Contents

- [Overview](#overview)
- [Why CROW](#why-crow)
- [Features](#features)
- [Interfaces](#interfaces)
- [Architecture](#architecture)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Vault and Encryption](#vault-and-encryption)
- [Data Sources](#data-sources)
- [Attachments and Images](#attachments-and-images)
- [Import and Export](#import-and-export)
- [Backup and Restore](#backup-and-restore)
- [Customization](#customization)
- [Project Structure](#project-structure)
- [Security Model](#security-model)
- [Performance](#performance)
- [Compatibility](#compatibility)
- [Contributing](#contributing)
- [License](#license)

---

## Overview

**CROW** is a desktop and terminal application built for people who need to
manage, correlate, and enrich large sets of contact information that spans
multiple independent databases. It is designed around three principles:

1. **Local-first** — all data lives on your machine. No cloud, no telemetry,
   no external API calls unless you explicitly configure one.
2. **Encrypted at rest** — every database, image, and attachment can be
   protected with a single passphrase using AES-256-GCM.
3. **Multi-interface** — the same core engine powers a graphical interface,
   a curses terminal interface, a modern TUI, and a full CLI.

The name is a reference to the intelligence process itself: gathering
fragments from different sources and assembling them into a single, coherent
picture.

---

## Why CROW

Most contact managers assume one database, one user, and no need for
correlation. Real investigations rarely look like that. Data arrives from
different systems — identity registries, messaging platforms, leaked
databases, manual notes — and each has its own schema, its own key, and its
own quirks.

CROW was built to solve this specific problem:

| Problem | How CROW addresses it |
|---|---|
| Data scattered across unrelated databases | A **data source registry** lets you describe any SQLite database, its phone fields, its name columns, and its matching strategy. Sync is one command. |
| Wrong or duplicated contact entries | A **matching engine** with priorities (phone, national code, name + family) and a **confidence score** for every link. |
| No trace of where a record came from | A **`contact_links` table** records the origin of every match. |
| Sensitive data on disk | **AES-256-GCM vault** with PBKDF2-HMAC-SHA256 (600,000 iterations) and a per-vault salt. |
| Persian/Arabic text rendered incorrectly | **Automatic Arabic shaping and BiDi reordering** for Tkinter, `FaEntry`/`FaText` wrappers that preserve raw text while editing. |
| Platform-specific workflows | **User-defined platforms** in a registry table. Add "eitaa", "igap", "whatsapp", anything — a column appears everywhere. |
| Ad-hoc data models | **User-defined tables** with a schema designer, typed columns, validation, and a real data browser. |
| Migration from other tools | **Maltego file import** (`.mtgx`, `.mtg`, `.csv`) with a preview dialog. |

---

## Features

### Contact Management

- Create, edit, delete, and enrich contact records.
- Full name, family name, national code, phone number, free-form notes.
- Status field with five values: `unchecked`, `checking`, `verified`, `invalid`, `anonymous`.
- **Pin** contacts to the top of the list.
- **Mark as special** for high-priority contacts.
- **Notes** field supports multi-line text and is searchable.

### Multi-Database Correlation

- Describe external SQLite databases in a registry (path, table, columns, matchers).
- Matchers supported out of the box:
  - Phone number (multiple candidate columns per source)
  - National code
  - Name + family
- Priority-based matching with per-link confidence scores.
- Optional **create-missing** mode: contacts that exist only in an external source can be created automatically.

### Platform Tracking

- Every contact can have one row per platform.
- Built-in platforms: **Splus, Bale, Rubika, Telegram, Instagram**.
- Per-platform fields: `exists_status`, `username`, `display_name`, `user_id`, `verified_status`.
- Add new platforms at runtime; they appear in the table, filters, and edit dialog without a restart.

### Attachments and Images

- Images stored **inside the database** as raw BLOB + base64 (portable, encrypted with the vault).
- Automatic MIME/width/height detection.
- Per-contact attachment folder on disk for arbitrary files.
- Open the folder in the OS file browser directly from the UI.

### Backup and Restore

- Single-file zip backup that includes **databases and attachments**.
- Safety backup created automatically before every restore.
- Retention policy: keep the N newest backups.
- All actions logged to `audit_log` inside `contacts.db`.

### Search and Filtering

- Free-text search across phone, name, family, national code, notes, usernames.
- Status filter.
- Quick filters: pinned, special, has identity, no identity, with photo, no photo.
- Per-platform filters with `any` / `yes` / `no` / `unknown`.

### Import and Export

- Import from `tempinput.json` or any compatible JSON file.
- **Import from Maltego** (`.mtgx`, `.mtg`, `.csv`) with a preview and mapping dialog.
- Export to CSV (UTF-8 BOM, Excel-friendly).
- Export to XLSX with all platform columns.

### Customization

- User-defined **platforms** registry.
- User-defined **tables** with a schema designer.
- User-defined **data sources** with a matcher editor.

### Internationalization

- Full Persian/Arabic text support with automatic shaping and RTL.
- Every label, tab, column header, and menu item is shaped for display.
- Input fields switch between shaped (view) and raw (edit) mode without losing data.

---

## Interfaces

CROW exposes four independent front-ends over the same core engine:

| Interface | Command | Best for |
|---|---|---|
| **GUI** | `python3 main.py gui` | Daily work with rich previews, image popups, custom tables. |
| **TUI (curses)** | `python3 main.py tui` | Servers, SSH sessions, low-resource environments. |
| **TUI (Textual)** | `python3 main.py tui-modern` | Modern terminal with mouse support and notifications. |
| **CLI** | `python3 main.py cli ...` | Scripting, batch operations, integration with other tools. |

All four share:

- The same database schema.
- The same Vault encryption.
- The same `core.py` business logic.
- The same configuration.

### GUI

Tkinter-based, dark theme, keyboard-driven. Features:

- Sortable multi-column table with per-platform columns.
- Double-click on a platform cell to inspect the full social record.
- Double-click on the photo cell to preview the image at 420x420.
- Right-click context menu with Copy / Pin / Special / Delete.
- Live search with a summary line of active filters.

### TUI (curses)

Curses-based, no external dependencies. Features:

- Column scrolling for wide tables.
- Color-coded rows by status.
- Arrow-key navigation with backlog draining to avoid key repeats.
- Two view modes: compact (one Platforms column) or expanded (one column per platform).
- All actions bound to single keys, with a full help screen.

### TUI (Textual)

Built on the Textual framework. Features:

- Real table with zebra striping and a cursor row.
- Live side panel showing the selected contact.
- Modal screens for edit, confirm, help.
- Notification toasts for operation results.
- Debounced search to avoid reloading on every keystroke.

### CLI

Full argparse interface. Supports JSON output for every list command. Examples:

```bash
python3 main.py cli contacts list --status verified --json
python3 main.py cli contacts add --phone 0912... --name Ali --pinned
python3 main.py cli contacts photo 12 /path/to/image.jpg
python3 main.py cli contacts files 12
python3 main.py cli source add whatsapp --db whatsapp.db --table accounts ...
python3 main.py cli table create laptops --column serial:text:1

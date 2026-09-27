
<div align="center">

# CROW

### INTELLIGENCE PLATFORM

*A self-hosted OSINT workspace for collecting, correlating, and enriching data across fragmented sources.*

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![SQLite](https://img.shields.io/badge/SQLite-3-003B57?logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Linux%20%7C%20macOS%20%7C%20Windows-lightgrey)](#compatibility)
[![Interface](https://img.shields.io/badge/Interface-GUI%20%7C%20TUI%20%7C%20CLI-blue)](#interfaces)

</div>

---

## Table of Contents

- [What CROW Is](#what-crow-is)
- [What CROW Is Not](#what-crow-is-not)
- [Core Concepts](#core-concepts)
- [Why CROW](#why-crow)
- [Capabilities](#capabilities)
- [Workflow](#workflow)
- [Interfaces](#interfaces)
- [Architecture](#architecture)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Entity Correlation](#entity-correlation)
- [Source Registry](#source-registry)
- [Identity Handles and Platforms](#identity-handles-and-platforms)
- [Attachments and Visual Evidence](#attachments-and-visual-evidence)
- [Import and Export](#import-and-export)
- [Vault and Encryption](#vault-and-encryption)
- [Backup and Restore](#backup-and-restore)
- [Extensibility](#extensibility)
- [Project Structure](#project-structure)
- [Security Model](#security-model)
- [Performance](#performance)
- [Compatibility](#compatibility)
- [Operational Notes](#operational-notes)
- [Contributing](#contributing)
- [License](#license)

---

## What CROW Is

CROW is an **OSINT data management platform**. It is a local workspace for
analysts who need to collect fragments of information from many different
sources and turn them into a coherent, navigable picture of one or more
subjects.

The tool assumes that your data does not live in one place. It lives in
disconnected databases, exported logs, hand-written notes, leaked dumps,
and platform-specific registries. Each has its own schema, its own key
field, and its own quirks. CROW provides the connective tissue between
them.

Concretely, CROW lets you:

- Declare an arbitrary number of **external databases** as read-only sources.
- Describe how each source can be **matched** against your central entity
  index — by phone number, national identifier, or name.
- Track **identities across services** — every handle, username, and account
  a subject uses on any platform.
- Attach **evidence files and images** to subjects, with all of it stored
  and encrypted together.
- Search, filter, pivot, and export the resulting graph of links.
- Keep everything **offline, local, and encrypted at rest**.

CROW is the tool you open when you have a phone number and need to know
everywhere it appears in your collected data.

---

## What CROW Is Not

It is important to be clear about scope, because CROW is often mistaken for
tools in adjacent categories.

| Category | Does CROW do this? | Notes |
|---|---|---|
| Scraping and crawling | No | CROW is not a collection tool. It manages data you already have. |
| Automated external API lookups | No | CROW makes no network calls. Any enrichment must come from a source you provide. |
| Cloud synchronization | No | There is no server, no account, no remote storage. |
| Real-time monitoring | No | CROW is an analytical workspace, not a watchdog. |
| Social media engagement | No | CROW does not interact with external platforms. |
| Contact book / CRM | No | The data model is broader than contacts. It is an entity index. |
| Maltego replacement | Partly | It imports Maltego output and provides a similar graph-over-sources view, but does not replicate the transform ecosystem. |

The acronym OSINT is used here in its strict sense: the tool operates only
on data that you, the operator, have collected through means you are
responsible for.

---

## Core Concepts

CROW uses a small set of vocabulary. Understanding these six concepts is
enough to use the entire platform.

### Entity

The central record. An entity is a person, a company, a device, or any
subject you are investigating. It has an identifier (usually a phone
number), a status, a name, notes, and zero or more attached images.

Entities are stored in the `contacts` table. The name is legacy: the same
record is used for any subject type.

### Identifier

The primary key of an entity. Usually a phone number. CROW normalizes
phone numbers across Iranian formats (`+98...`, `0098...`, `98...`,
`09...`, `9...`) so that all representations resolve to the same entity.

### Handle

A platform-specific account belonging to an entity. Each handle has:

- a platform name (Splus, Telegram, Instagram, or anything you define),
- an existence status (`yes`, `no`, `unknown`),
- an optional username,
- an optional display name,
- an optional platform-specific user ID,
- a verification status.

Handles are stored in the `contact_socials` table.

### Source

An external database that CROW can read from. A source declares its path,
its table, its phone fields, its name columns, and which matching
strategies to use. Sources are stored in the `data_sources` table and can
be added, edited, or disabled at runtime.

### Link

A recorded connection between an entity and a row in an external source.
Every link stores:

- which source produced it,
- the primary key of the source row,
- the matching strategy that fired (`phone`, `national_code`, `name_family`,
  or `created_from_<source>`),
- the matching value,
- a **confidence score** between 0.0 and 1.0.

Links are stored in the `contact_links` table and are what make CROW a
graph rather than a list.

### Vault

An optional encryption layer. When enabled, all databases, images, and
attachments are stored as ciphertext on disk. The plaintext exists only
in memory or in a temporary folder for the duration of a session.

---

## Why CROW

Most OSINT tooling makes one of two assumptions: either everything lives
in one proprietary database, or everything is generated on the fly by
transforms. Real investigative work sits between these two extremes.

CROW is built for that middle ground.

| Problem | How CROW addresses it |
|---|---|
| Fragmented data across unrelated files | A **source registry** describes any SQLite database and matches it against the central index with a single command. |
| Multiple representations of the same value | **Identifier normalization** collapses `+98...`, `0098...`, `98...`, `09...` into one form. |
| Wrong matches and false positives | **Priority-based matchers** with an explicit **confidence score** on every link. |
| Loss of provenance | The `contact_links` table records where every link came from, using which strategy, with what value. |
| No way to model non-contact data | **User-defined tables** with a schema designer support arbitrary structures (vehicles, properties, bank accounts). |
| Scattered handles across platforms | A **platform registry** that grows at runtime; every new platform appears in the table, filters, and edit dialog. |
| Data on a disk you don't fully trust | **AES-256-GCM vault** with PBKDF2-HMAC-SHA256 at 600,000 iterations. |
| Persian/Arabic text corrupted in the UI | **Automatic Arabic shaping and BiDi** for every label, tab, and field, with a raw-mode editor that does not corrupt input. |
| Migration from other tools | **Maltego file import** with a preview dialog for `.mtgx`, `.mtg`, and `.csv`. |

---

## Capabilities

### Entity Management

- Create, edit, delete, and merge entities.
- Fields: identifier, name, family name, national code, free-form notes.
- Status values: `unchecked`, `checking`, `verified`, `invalid`, `anonymous`.
- **Pin** to elevate an entity to the top of every view.
- **Mark as special** as a second-tier flag for high-priority subjects.
- Full-text search across all fields, including notes and handles.

### Multi-Source Correlation

- Add any number of external SQLite databases as read-only sources.
- Match strategies:
  - **Phone** — any number of candidate columns per source.
  - **National code** — exact match with normalization.
  - **Name + family** — with Persian character unification.
  - **Create missing** — optionally create entities for unmatched source rows.
- Per-link confidence scores for downstream filtering.

### Cross-Platform Identity

- Built-in platforms: Splus, Bale, Rubika, Telegram, Instagram.
- Add new platforms at runtime with a name, a display label, and a
  two-character code.
- Per-platform fields: existence status, username, display name, user ID,
  verification status.
- Each platform becomes a column, a filter, and a tab in the edit dialog.

### Evidence Storage

- Images stored **inside the database** as raw BLOB plus base64.
- Automatic MIME detection, dimension extraction, SHA-256 hashing.
- Arbitrary files stored in a per-entity folder on disk.
- One-click open of the folder in the OS file browser.
- All evidence encrypted with the vault.

### Search, Filter, and Navigate

- Free-text search across all fields.
- Status filter.
- Quick filters: pinned, special, has identity, no identity, with photo,
  no photo.
- Per-platform filters with `any` / `yes` / `no` / `unknown`.
- Source filters: with any specific source, or only unlinked entities.

### Import, Export, and Backup

- Import from the built-in JSON list.
- Import from arbitrary JSON with the same schema.
- **Import from Maltego** (`.mtgx`, `.mtg`, `.csv`) with a preview and
  entity-type summary.
- Export to CSV (UTF-8 BOM, Excel-safe).
- Export to XLSX with one column per platform.
- Single-zip backup of all databases and attachments.
- Retention policy and safety backups before every restore.

---

## Workflow

A typical investigative session in CROW follows this shape.

### 1. Load your collected data

You have a set of phone numbers, handles, or names from various collection
efforts. Load them as the initial entity list:

```bash
python3 main.py cli import json my_seed_data.json
```

### 2. Register the databases you will correlate against

For each external SQLite file, describe its structure:

```bash
python3 main.py cli source add registry \
    --label "Civil Registry" \
    --code R \
    --db /data/civil.db \
    --table persons \
    --phone-fields mobile,landline \
    --name-columns first_name,last_name \
    --nc-column national_id \
    --matchers phone,national_code,name_family
```

### 3. Run correlation

```bash
python3 main.py cli sync
```

CROW reads every enabled source, tries every matcher in priority order, and
records every match as a link with a confidence score.

### 4. Inspect the resulting graph

Open the GUI and pivot through the results:

```bash
python3 main.py gui
```

- Filter by "has identity" to see only entities that matched in at least
  one external source.
- Sort by the Flags column to bring pinned and special subjects to the top.
- Double-click a platform cell to see the exact handle record.
- Double-click the photo cell to preview visual evidence.

### 5. Enrich manually

Add handles, images, notes, and custom-table rows as you collect them.

### 6. Package and protect

- Encrypt everything with `python3 main.py vault init`.
- Create a backup with `python3 main.py cli backup --tag case_2026_09`.
- Export a CSV or XLSX for the parts you need to share.

---

## Interfaces

CROW exposes four independent front-ends over the same core engine.

| Interface | Command | Best for |
|---|---|---|
| **GUI** | `python3 main.py gui` | Rich previews, image popups, table designers, daily analysis. |
| **TUI (curses)** | `python3 main.py tui` | SSH sessions, low-resource hosts, keyboard-only workflows. |
| **TUI (Textual)** | `python3 main.py tui-modern` | Modern terminal with mouse support and notifications. |
| **CLI** | `python3 main.py cli ...` | Scripting, batch operations, integration with pipelines. |

### GUI

Tkinter-based, dark theme, keyboard-driven.

- Multi-column table with one column per configured platform.
- Double-click a platform cell to open the full handle record.
- Double-click the photo cell to open a 420x420 image preview.
- Right-click context menu with Copy, Pin, Special, Delete.
- Live search with a filter summary bar.
- Detail window with four tabs: Overview, Socials, Sources, Raw JSON.

### TUI (curses)

No external dependencies.

- Column scrolling for wide tables.
- Color-coded rows by status.
- Arrow-key backlog draining to keep navigation responsive.
- Two view modes: compact (single platforms column) or expanded (one
  column per platform).
- Single-key actions with a full help screen.

### TUI (Textual)

Built on Textual.

- Real table with zebra striping and a cursor row.
- Live side panel for the selected entity.
- Modal screens for edit, confirm, and help.
- Notification toasts.
- Debounced search at 150 ms.

### CLI

Full argparse interface with JSON output on every list command.

```bash
python3 main.py cli contacts list --status verified --json
python3 main.py cli contacts show 12
python3 main.py cli contacts social set 12 telegram --username alice
python3 main.py cli source match registry
python3 main.py cli table rows vehicles
```

---

## Architecture

CROW uses a flat module layout with a small, explicit core.

```
crypto.py         AES-256-GCM and PBKDF2-HMAC-SHA256
vault.py          vault packaging, unlock, lock, passphrase change
branding.py       application name and description

db.py             schema, migrations, connection, normalization
data_sources.py   registry of external databases
core.py           business logic: CRUD, matching, sync, export

image_utils.py    universal image loader (PIL plus Tk fallback)
text_utils.py     Persian shaping helpers
backup.py         zip-based backup and restore

edit_dialog.py        entity edit window
platform_manager.py   platform registry UI
source_manager.py     source registry UI
custom_tables.py      custom table designer and browser

gui.py            Tkinter front-end
tui.py            curses front-end
tui_modern.py     Textual front-end
cli.py            argparse front-end

main.py           dispatch, vault integration, passphrase prompt
```

Every front-end imports `core` and never touches SQL directly. Adding a
new front-end does not require changes to the logic.

---

## Installation

### Requirements

- Python **3.10** or newer
- SQLite 3 (bundled with Python)
- Tkinter (for the GUI)
- `cryptography` (for the vault)
- `Pillow` (for full image format support)
- `arabic-reshaper` and `python-bidi` (for Persian shaping)
- `openpyxl` (for Excel export)
- `textual` (optional, for `tui-modern`)

### Recommended

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip

pip install cryptography Pillow arabic-reshaper python-bidi openpyxl
pip install textual

# Tkinter on Debian/Ubuntu:
sudo apt install python3-tk
```

### Minimal

```bash
pip install arabic-reshaper python-bidi
```

Runs without `cryptography` and without `Pillow`, with reduced
functionality. The vault features require `cryptography`. Full image
support requires `Pillow`.

---

## Quick Start

```bash
git clone https://github.com/<your-user>/crow.git
cd crow
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python3 main.py gui
```

On first run, CROW creates `contacts.db` in the project folder. Load your
seed data:

```bash
python3 main.py cli import json tempinput.json
python3 main.py cli sync
```

Then open the GUI and start pivoting.

### Optional: encrypt everything

```bash
python3 main.py vault init
```

Follow the prompts. From the next launch, CROW asks for the passphrase,
decrypts to a temporary directory, runs the session, and re-encrypts on
exit.

---

## Entity Correlation

The heart of CROW is the matching engine.

### Matchers

A source can declare any combination of the following:

| Matcher | Signal | Default confidence |
|---|---|---|
| `phone` | A phone number found in any of the declared phone fields, after normalization | 1.00 |
| `national_code` | An exact match on the national code column, after digit normalization | 0.95 |
| `name_family` | A match on both name and family columns, after Persian character unification | 0.70 |
| `name_family_ambiguous` | Name and family matched more than one entity; the first is chosen | 0.40 |
| `created_from_<source>` | The entity did not exist and was created from this source row | 1.00 |

### Priority

Matchers run in the order listed above. The first one that succeeds wins;
subsequent matchers are not attempted for that source row.

### Confidence

Every link records a confidence score. Scores are not used to reject
matches; they are there for you to filter, sort, and audit. A
`name_family_ambiguous` link with a 0.4 confidence is a hint, not a fact.

### Provenance

Every link records the source row it came from. This means you can always
answer the question: *why does CROW think this entity is the same as that
record?*

```sql
SELECT source_db, source_table, source_pk,
       match_key, match_value, confidence
FROM contact_links
WHERE contact_id = 12;
```

---

## Source Registry

Sources are declared at runtime and stored in the `data_sources` table
inside `contacts.db`.

| Field | Purpose |
|---|---|
| `name` | Internal identifier, lowercase alphanumeric |
| `label` | Human-readable label for the UI |
| `code` | Two-character code for the Sources column |
| `db_path` | Absolute or relative path to the SQLite file |
| `table_name` | Table inside the file |
| `pk_column` | Primary key column |
| `phone_fields` | Comma-separated list of candidate phone columns |
| `name_columns` | Two columns for first name and family name |
| `national_code_column` | Column containing the national identifier |
| `matchers` | Active strategies |
| `create_missing` | Whether to create entities for unmatched rows |
| `social_platform` | If set, matched rows also produce a handle entry |
| `enabled` | Whether the source participates in sync |

### Example: add a source

```bash
python3 main.py cli source add corporate_records \
    --label "Corporate Records" \
    --code R \
    --db /data/corp.db \
    --table directors \
    --phone-fields mobile_1,mobile_2 \
    --name-columns given_name,surname \
    --matchers phone,name_family \
    --social-platform corporate
```

Then run a targeted sync:

```bash
python3 main.py cli source match corporate_records
```

Or a full sync over every enabled source:

```bash
python3 main.py cli sync
```

The built-in sources `identity` and `telegram` can be edited but not
removed.

---

## Identity Handles and Platforms

A handle is a platform-specific account belonging to an entity.

### The `contact_socials` table

| Column | Purpose |
|---|---|
| `contact_id` | Foreign key to the entity |
| `platform` | Platform identifier |
| `exists_status` | `yes`, `no`, or `unknown` |
| `username` | Handle on that platform |
| `display_name` | Display name shown by the platform |
| `user_id` | Platform-specific numeric or string ID |
| `verified_status` | One of the standard status values |

### The platform registry

Platforms are declared in the `platforms` table and can be added at
runtime.

```bash
python3 main.py cli platform add signal --display Signal
```

Every added platform:

- appears as a column in the GUI table,
- appears in the filters menu,
- appears as a tab in the edit dialog,
- is included in exports,
- is supported by the JSON import.

Built-in platforms (Splus, Bale, Rubika, Telegram, Instagram) cannot be
removed but can be renamed.

---

## Attachments and Visual Evidence

CROW stores images **inside the database**, not as loose files. This makes
them portable, hashable, and encrypted together with the rest of the data.

### The `contact_images` table

| Column | Type | Purpose |
|---|---|---|
| `id` | INTEGER | Primary key |
| `contact_id` | INTEGER | Foreign key to `contacts` |
| `name` | TEXT | Original file name |
| `mime` | TEXT | Detected MIME type |
| `size_bytes` | INTEGER | Size in bytes |
| `width`, `height` | INTEGER | Dimensions when detectable |
| `sha256` | TEXT | Content hash |
| `raw_data` | BLOB | Raw image bytes |
| `encoded_data` | TEXT | Base64-encoded copy of the same bytes |
| `encoding` | TEXT | Currently always `base64` |
| `is_primary` | INTEGER | Marks the primary image |

### Files on disk

Arbitrary non-image files can be stored in `attachments/<entity_id>/`.
These are included in the vault and in backups.

### Export

Any stored image can be written back to disk as a file:

```bash
python3 main.py cli contacts show 12   # shows image IDs
```

In the GUI, right-click a photo cell for the "Open folder" action.

---

## Import and Export

### Import

| Format | Command |
|---|---|
| Built-in JSON | `python3 main.py cli import json` |
| Arbitrary JSON | `python3 main.py cli import json /path/to/file.json` |
| Maltego `.mtgx` | `python3 main.py cli import maltego graph.mtgx` |
| Maltego `.mtg` | `python3 main.py cli import maltego graph.mtg` |
| CSV | `python3 main.py cli import maltego data.csv` |

The Maltego importer maps:

| Maltego entity | CROW target |
|---|---|
| `maltego.PhoneNumber` | Entity identifier |
| `maltego.Person` | Name and family |
| `maltego.Alias` | Handle username |
| `maltego.EmailAddress` | Handle username |
| `maltego.URL` | Handle username |

### Export

| Format | Command |
|---|---|
| CSV | `python3 main.py cli export csv reports/all.csv` |
| XLSX | `python3 main.py cli export excel reports/all.xlsx` |

Both include every platform column and every source code.

---

## Vault and Encryption

CROW can encrypt everything at rest through a single passphrase.

```
vault/
  vault.json              header: version, salt, iterations, timestamp
  contacts.db.enc         encrypted central database
  identity.db.enc         encrypted identity source
  telegram.db.enc         encrypted telegram source
  attachments.zip.enc     encrypted archive of the attachments folder
```

### Cryptographic parameters

| Parameter | Value |
|---|---|
| Cipher | AES-256-GCM (authenticated encryption) |
| Key derivation | PBKDF2-HMAC-SHA256 |
| Iterations | 600,000 |
| Salt | 16 random bytes, unique per vault |
| Nonce | 12 random bytes per encryption, prepended to ciphertext |
| Authentication tag | 16 bytes, appended to ciphertext |

The key is never written to disk. If the passphrase is lost, the data is
unrecoverable.

### Session model

1. On startup, CROW checks for `vault/vault.json`.
2. If present, it prompts for the passphrase.
3. It derives the key, decrypts every file into a temporary directory,
   and exports `CONTACTS_WORKDIR` pointing at that directory.
4. All modules resolve their paths through `CONTACTS_WORKDIR`.
5. On exit, the temporary directory is encrypted back into `vault/` and
   deleted.

### Operations

```bash
python3 main.py vault init      # create a new vault
python3 main.py vault status    # show vault metadata
python3 main.py vault change    # change the passphrase
python3 main.py vault unlock    # decrypt to disk for inspection only
```

---

## Backup and Restore

A backup is a single zip archive containing all databases, the
attachments folder, and a small `meta.json`.

```bash
python3 main.py cli backup --tag case_2026_09
python3 main.py cli backups
python3 main.py cli restore backups/crow_backup_20260927_120000.zip
```

A safety backup is created automatically before every restore. The
retention policy keeps the twenty most recent archives.

---

## Extensibility

### Adding a platform

At runtime, from any interface:

```bash
python3 main.py cli platform add eitaa --display Eitaa
```

### Adding a custom table

For any structured data that does not fit the entity model:

```bash
python3 main.py cli table create vehicles \
    --display "Vehicles" \
    --column plate:text:1 \
    --column make:text \
    --column model:text \
    --column year:integer

python3 main.py cli table row-add vehicles \
    --set plate=12A345 --set make=Toyota
```

Custom tables live inside `contacts.db`, participate in backups, and are
encrypted with the vault.

### Adding a source

See the [Source Registry](#source-registry) section.

### Adding a front-end

A new front-end needs only to import `core` and call its public functions.
No SQL, no direct file access.

---

## Project Structure

```
crow/
├── branding.py             Application name and description
├── crypto.py               AES-256-GCM and PBKDF2
├── vault.py                Vault packaging
├── db.py                   Schema, migrations, connection
├── data_sources.py         External database registry
├── core.py                 Business logic
├── image_utils.py          Image loading
├── text_utils.py           Persian shaping
├── backup.py               Backup and restore
├── edit_dialog.py          Entity edit window
├── platform_manager.py     Platform registry UI
├── source_manager.py       Source registry UI
├── custom_tables.py        Custom table designer and browser
├── gui.py                  Tkinter front-end
├── tui.py                  curses front-end
├── tui_modern.py           Textual front-end
├── cli.py                  argparse front-end
├── main.py                 Entry point
├── maltego_import.py       Maltego file parser
├── requirements.txt
├── .gitignore
└── README.md
```

---

## Security Model

CROW is designed for use on a machine you control.

- **No network activity.** The application opens no sockets unless you
  invoke an import that reads from a remote resource. There is no update
  check, no telemetry, no analytics.
- **Local storage only.** All data lives in SQLite files in the project
  folder or inside the vault.
- **Optional whole-database encryption.** When the vault is active, all
  files on disk are ciphertext.
- **Audit trail.** Every mutation is recorded in the `audit_log` table
  with a timestamp, action name, and detail string.
- **No passphrase caching.** Every launch prompts. There is no
  "remember me" option.

### Threat model

CROW protects against:

- A lost or stolen device, when the vault is enabled and the machine is
  powered off.
- An attacker with read access to files but not to the running process.
- Accidental distribution of backups, when backups are of the vault
  directory rather than of the plaintext.

CROW does **not** protect against:

- A compromised machine with a keylogger or memory scraper.
- An attacker who has the passphrase.
- Filesystem adversaries with control over the operating system.

---

## Performance

CROW is designed for datasets of up to a few hundred thousand entities on
commodity hardware.

- `query_contacts` performs a single JOIN across entities, handles, and
  images. Subqueries have been replaced with aggregated joins.
- The platform registry, source label map, and external source indexes
  are cached in memory and invalidated on writes.
- The curses TUI drains queued navigation keys without redrawing, avoiding
  the arrow-key backlog problem.
- The modern TUI debounces search input by 150 ms.

Vault overhead:

- Unlock: PBKDF2 at 600,000 iterations takes roughly 0.6 to 1.0 seconds
  on a modern CPU.
- Encrypt and decrypt: AES-GCM runs at several hundred MB/s.

For datasets above roughly 100 MB, consider storing the databases on a
filesystem that is already encrypted at rest and using CROW without the
vault layer.

---

## Compatibility

| Component | Supported |
|---|---|
| Python | 3.10, 3.11, 3.12, 3.13, 3.14 |
| Operating systems | Linux, macOS, Windows |
| Terminal | Any ANSI-compatible; 256 colors recommended |
| SQLite | 3.24 or newer |
| Tk | 8.6 or newer |

On Windows, the curses TUI requires `pip install windows-curses`.

---

## Operational Notes

- All commands listed in this README assume a virtual environment is
  active. See [Installation](#installation).
- Databases, the vault folder, attachments, backups, and reports are
  excluded from version control via `.gitignore`. Do not commit them.
- Every mutation is written to `audit_log`. To inspect recent activity:

  ```sql
  SELECT ts, action, detail FROM audit_log ORDER BY id DESC LIMIT 50;
  ```

- The application has no configuration file. All configuration lives in
  the database, so a backup captures everything.

---

## Contributing

Issues and pull requests are welcome. Before opening a PR:

1. Test in all four interfaces and confirm that nothing broke.
2. Do not commit databases, the vault folder, attachments, or backups.
   These are covered by `.gitignore`.
3. Keep `core.py` free of UI code. UI belongs in the respective front-end
   modules.
4. Use plain, non-emoji commit messages.

---

## License

CROW is released under the **CROW Attribution License, Version 1.0**.

You may use, modify, and distribute this software freely, including for
commercial and public deployments, provided that:

- the original project name is credited,
- the license text is preserved,
- any public or commercial deployment displays visible attribution.

See [LICENSE](LICENSE) for the full text and [NOTICE](NOTICE) for the
attribution statement.

---

<div align="center">

**CROW** — *INTELLIGENCE PLATFORM*

A local workspace for people who take their data seriously.

</div>

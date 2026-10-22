from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
from threading import RLock

from .taxonomy import catalog_category, catalog_content_key, catalog_data_status, catalog_family_key, catalog_quality_score
from .utils import utc_now


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "conest_catalog.db"

# Serialize writers and their automatic WAL checkpoints in the server process.
write_lock = RLock()


def database_path() -> Path:
    configured = os.environ.get("CONEST_DB_PATH", "").strip()
    return Path(configured).expanduser().resolve() if configured else DEFAULT_DB_PATH


class ManagedConnection(sqlite3.Connection):
    """Commit/rollback and close each request's connection deterministically."""
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()


def _raw_connect(path: str | Path | None = None) -> sqlite3.Connection:
    target = Path(path) if path else database_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(target, timeout=30, factory=ManagedConnection)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def connect(path: str | Path | None = None) -> sqlite3.Connection:
    # Bootstrap also runs for Passenger/WSGI imports, not just app.py main().
    from .auto_upgrade import ensure_database
    return _raw_connect(ensure_database(path))


@contextmanager
def transaction(path: str | Path | None = None) -> Iterator[sqlite3.Connection]:
    with write_lock:
        conn = connect(path)
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_name TEXT NOT NULL,
    file_sha256 TEXT NOT NULL,
    sheet_name TEXT NOT NULL,
    project_name TEXT,
    import_format TEXT NOT NULL,
    row_count INTEGER NOT NULL DEFAULT 0,
    header_count INTEGER NOT NULL DEFAULT 0,
    assembly_count INTEGER NOT NULL DEFAULT 0,
    component_count INTEGER NOT NULL DEFAULT 0,
    warning_count INTEGER NOT NULL DEFAULT 0,
    imported_at TEXT NOT NULL,
    UNIQUE(file_sha256, sheet_name)
);

CREATE TABLE IF NOT EXISTS catalog_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT,
    name TEXT NOT NULL,
    description TEXT,
    phase TEXT,
    subphase TEXT,
    scope TEXT,
    catalog_key TEXT,
    category TEXT NOT NULL DEFAULT 'Other',
    data_status TEXT NOT NULL DEFAULT 'reference_only',
    is_preferred INTEGER NOT NULL DEFAULT 0,
    base_quantity REAL NOT NULL DEFAULT 1,
    base_uom TEXT,
    source_type TEXT NOT NULL DEFAULT 'conest',
    fingerprint TEXT NOT NULL UNIQUE,
    search_text TEXT NOT NULL,
    is_manual INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    usage_count INTEGER NOT NULL DEFAULT 0,
    material_markup_hint REAL,
    labor_rate_hint REAL,
    overhead_markup_hint REAL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_catalog_code ON catalog_items(code);
CREATE INDEX IF NOT EXISTS idx_catalog_active ON catalog_items(is_active);
CREATE INDEX IF NOT EXISTS idx_catalog_usage ON catalog_items(usage_count DESC);

CREATE TABLE IF NOT EXISTS catalog_components (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    catalog_item_id INTEGER NOT NULL REFERENCES catalog_items(id) ON DELETE CASCADE,
    line_order INTEGER NOT NULL,
    item_no TEXT,
    description TEXT NOT NULL,
    quantity_per_unit REAL NOT NULL DEFAULT 0,
    source_quantity REAL NOT NULL DEFAULT 0,
    uom TEXT,
    q_m TEXT,
    size TEXT,
    unit_material REAL NOT NULL DEFAULT 0,
    material_factor REAL NOT NULL DEFAULT 1,
    unit_hours REAL NOT NULL DEFAULT 0,
    labor_factor REAL NOT NULL DEFAULT 1,
    is_parent INTEGER NOT NULL DEFAULT 0,
    source_row INTEGER,
    quantity_formula TEXT,
    notes TEXT,
    UNIQUE(catalog_item_id, line_order)
);

CREATE INDEX IF NOT EXISTS idx_component_item ON catalog_components(catalog_item_id, line_order);

CREATE TABLE IF NOT EXISTS source_occurrences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    catalog_item_id INTEGER NOT NULL REFERENCES catalog_items(id) ON DELETE CASCADE,
    source_id INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    source_row INTEGER,
    base_quantity REAL NOT NULL DEFAULT 1,
    source_scope TEXT,
    source_phase TEXT,
    source_subphase TEXT,
    source_material_total REAL,
    source_labor_hours REAL,
    UNIQUE(catalog_item_id, source_id, source_row)
);

CREATE TABLE IF NOT EXISTS catalog_aliases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    catalog_item_id INTEGER NOT NULL REFERENCES catalog_items(id) ON DELETE CASCADE,
    alias TEXT NOT NULL,
    normalized_alias TEXT NOT NULL,
    weight REAL NOT NULL DEFAULT 1,
    source TEXT NOT NULL DEFAULT 'import',
    created_at TEXT NOT NULL,
    UNIQUE(catalog_item_id, normalized_alias)
);

CREATE INDEX IF NOT EXISTS idx_alias_normalized ON catalog_aliases(normalized_alias);

CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    client TEXT,
    currency TEXT NOT NULL DEFAULT 'AUD',
    material_markup REAL NOT NULL DEFAULT 0.15,
    labor_rate REAL NOT NULL DEFAULT 120,
    overhead_markup REAL NOT NULL DEFAULT 0.10,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS project_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    catalog_item_id INTEGER REFERENCES catalog_items(id) ON DELETE SET NULL,
    code_snapshot TEXT,
    name_snapshot TEXT NOT NULL,
    description_snapshot TEXT,
    scope_snapshot TEXT,
    category_snapshot TEXT,
    quantity REAL NOT NULL DEFAULT 1,
    uom TEXT,
    sort_order INTEGER NOT NULL DEFAULT 0,
    is_manual INTEGER NOT NULL DEFAULT 0,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_project_lines_project ON project_lines(project_id, sort_order, id);

CREATE TABLE IF NOT EXISTS project_line_components (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_line_id INTEGER NOT NULL REFERENCES project_lines(id) ON DELETE CASCADE,
    line_order INTEGER NOT NULL,
    item_no TEXT,
    description TEXT NOT NULL,
    quantity_per_unit REAL NOT NULL DEFAULT 0,
    uom TEXT,
    q_m TEXT,
    size TEXT,
    unit_material REAL NOT NULL DEFAULT 0,
    material_factor REAL NOT NULL DEFAULT 1,
    unit_hours REAL NOT NULL DEFAULT 0,
    labor_factor REAL NOT NULL DEFAULT 1,
    is_parent INTEGER NOT NULL DEFAULT 0,
    notes TEXT,
    UNIQUE(project_line_id, line_order)
);

CREATE TABLE IF NOT EXISTS selection_feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query TEXT NOT NULL,
    normalized_query TEXT NOT NULL,
    catalog_item_id INTEGER NOT NULL REFERENCES catalog_items(id) ON DELETE CASCADE,
    selected_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS import_issues (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER REFERENCES sources(id) ON DELETE CASCADE,
    severity TEXT NOT NULL,
    issue_code TEXT NOT NULL,
    message TEXT NOT NULL,
    row_no INTEGER,
    payload_json TEXT,
    resolved INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
"""


DEFAULT_SETTINGS = {
    "default_material_markup": "0.15",
    "default_crew_size": "2",
    "default_hours_per_day": "8",
    "default_labor_rate": "120",
    "default_labor_hours_markup": "0",
    "default_save_mode": "estimate",
    "default_overhead_markup": "0.10",
    "currency": "AUD",
    "llm_provider": "gemini",
    "llm_model": "gemini-3.8-flash",
    "llm_enabled": "0",
    "gemini_api_key": "",
}

SECRET_SETTING_KEYS = {"gemini_api_key"}


def _ensure_catalog_metadata_columns(conn: sqlite3.Connection) -> bool:
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(catalog_items)")}
    additions = (
        ("catalog_key", "TEXT"),
        ("category", "TEXT NOT NULL DEFAULT 'Other'"),
        ("data_status", "TEXT NOT NULL DEFAULT 'reference_only'"),
        ("is_preferred", "INTEGER NOT NULL DEFAULT 0"),
    )
    changed = False
    for name, definition in additions:
        if name not in existing:
            conn.execute(f"ALTER TABLE catalog_items ADD COLUMN {name} {definition}")
            changed = True
    conn.execute("CREATE INDEX IF NOT EXISTS idx_catalog_key ON catalog_items(catalog_key, is_active)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_catalog_category ON catalog_items(category, is_active)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_catalog_status ON catalog_items(data_status, is_active)")
    return changed


def _ensure_project_metadata_columns(conn: sqlite3.Connection) -> bool:
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(project_lines)")}
    if "category_snapshot" in existing:
        return False
    conn.execute("ALTER TABLE project_lines ADD COLUMN category_snapshot TEXT")
    return True


def _ensure_manual_pricing_columns(conn: sqlite3.Connection) -> bool:
    additions = {
        "catalog_items": (("work_type", "TEXT NOT NULL DEFAULT 'assembly'"), ("category_override", "TEXT"), ("manual_revision", "INTEGER NOT NULL DEFAULT 0"), ("content_key", "TEXT")),
        "project_lines": (("work_type_snapshot", "TEXT NOT NULL DEFAULT 'assembly'"),),
        "catalog_components": (("labor_pricing", "TEXT NOT NULL DEFAULT 'hours'"), ("unit_labor_price", "REAL NOT NULL DEFAULT 0")),
        "project_line_components": (("labor_pricing", "TEXT NOT NULL DEFAULT 'hours'"), ("unit_labor_price", "REAL NOT NULL DEFAULT 0")),
    }
    changed = False
    for table, columns in additions.items():
        existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
        for name, definition in columns:
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
                changed = True
    conn.execute("CREATE INDEX IF NOT EXISTS idx_catalog_content ON catalog_items(content_key, is_active)")
    return changed


def refresh_catalog_index(conn: sqlite3.Connection) -> dict[str, int]:
    """Organize source variants into clean catalog families without deleting data."""
    rows = conn.execute(
        """SELECT ci.id, ci.code, ci.name, ci.description, ci.phase, ci.scope,
                  ci.source_type, ci.is_manual, ci.usage_count, ci.updated_at,
                  ci.work_type, ci.base_uom, ci.category_override, ci.manual_revision,
                  ci.catalog_key, ci.category, ci.data_status, ci.content_key, ci.is_preferred,
                  COUNT(cc.id) AS component_count,
                  COALESCE(SUM(cc.quantity_per_unit * cc.unit_material * cc.material_factor), 0) AS unit_material,
                  COALESCE(SUM(CASE WHEN cc.labor_pricing='hours' THEN cc.quantity_per_unit * cc.unit_hours * cc.labor_factor ELSE 0 END), 0) AS unit_hours,
                  COALESCE(SUM(CASE WHEN cc.labor_pricing='fixed' THEN cc.quantity_per_unit * cc.unit_labor_price * cc.labor_factor ELSE 0 END), 0) AS unit_labor_price,
                  (SELECT COUNT(*) FROM source_occurrences so WHERE so.catalog_item_id=ci.id) AS source_count
           FROM catalog_items ci
           LEFT JOIN catalog_components cc ON cc.catalog_item_id=ci.id
           GROUP BY ci.id"""
    ).fetchall()
    families: dict[str, list[tuple[int, float, str, int]]] = {}
    updates: list[tuple[str, str, str, str, int]] = []
    components_by_item: dict[int, list[dict]] = {}
    for component in conn.execute("SELECT * FROM catalog_components ORDER BY catalog_item_id, line_order"):
        components_by_item.setdefault(component["catalog_item_id"], []).append(dict(component))
    for row in rows:
        key = catalog_family_key(row["code"], row["name"], row["work_type"], row["base_uom"], bool(row["is_manual"]))
        category = row["category_override"] or catalog_category(row["code"], row["name"], row["description"], row["phase"], row["scope"])
        status = catalog_data_status(row["unit_material"], row["unit_hours"], row["unit_labor_price"])
        quality = catalog_quality_score(
            data_status=status,
            component_count=int(row["component_count"] or 0),
            source_count=int(row["source_count"] or 0),
            source_type=row["source_type"] or "",
            is_manual=bool(row["is_manual"]),
            usage_count=int(row["usage_count"] or 0),
        )
        content_key = catalog_content_key(row, components_by_item.get(row["id"], []))
        updates.append((key, category, status, content_key, int(row["id"])))
        families.setdefault(key, []).append((int(row["manual_revision"]), quality, row["updated_at"] or "", int(row["id"])))

    if updates:
        previous={int(row['id']):row for row in rows}
        changed=[value for value in updates if value[:4] != tuple(previous[value[4]][key] for key in ('catalog_key','category','data_status','content_key'))]
        conn.executemany(
            "UPDATE catalog_items SET catalog_key=?, category=?, data_status=?, content_key=? WHERE id=?",
            changed,
        )
        preferred_ids = {max(members)[3] for members in families.values()}
        # Unchanged catalogue rows must not generate writes and invalidate the
        # shared catalogue cache whenever one unrelated item is edited.
        conn.executemany("UPDATE catalog_items SET is_preferred=? WHERE id=?",
                         ((int(row['id'] in preferred_ids),row['id']) for row in rows
                          if int(row['is_preferred']) != int(row['id'] in preferred_ids)))
    return {
        "catalog_families": len({content for _, _, _, content, _ in updates}),
        "source_families": len(families),
        "source_variants": len(rows),
        "reference_only_variants": sum(1 for _, _, status, _, _ in updates if status == "reference_only"),
    }


def initialize(path: str | Path | None = None) -> Path:
    from .auto_upgrade import ensure_database
    return ensure_database(path)


def _initialize_schema(path: str | Path | None = None) -> Path:
    target = Path(path) if path else database_path()
    with connect(target) as conn:
        conn.execute('PRAGMA journal_mode = WAL')
        conn.executescript(SCHEMA)
        metadata_changed = _ensure_catalog_metadata_columns(conn)
        project_metadata_changed = _ensure_project_metadata_columns(conn)
        pricing_changed = _ensure_manual_pricing_columns(conn)
        metadata_changed = metadata_changed or pricing_changed
        count = conn.execute("SELECT COUNT(*) FROM schema_version").fetchone()[0]
        if not count:
            conn.execute("INSERT INTO schema_version(version) VALUES (6)")
            metadata_changed = True
        else:
            version = int(conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()[0])
            if version < 6:
                conn.execute("UPDATE schema_version SET version=6")
                metadata_changed = True
        now = utc_now()
        for key, value in DEFAULT_SETTINGS.items():
            conn.execute(
                "INSERT OR IGNORE INTO settings(key, value, updated_at) VALUES (?, ?, ?)",
                (key, value, now),
            )

        # Migrate the v1.0 OpenAI default to Gemini without overwriting a
        # Gemini model that the user has already selected.
        current_model = conn.execute("SELECT value FROM settings WHERE key='llm_model'").fetchone()
        if current_model and current_model[0].strip().lower().startswith("gpt-"):
            conn.execute(
                "UPDATE settings SET value=?, updated_at=? WHERE key='llm_model'",
                (DEFAULT_SETTINGS["llm_model"], now),
            )
        conn.execute(
            "UPDATE settings SET value='gemini', updated_at=? WHERE key='llm_provider' AND value <> 'gemini'",
            (now,),
        )

        projects = conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
        if not projects and not conn.execute("SELECT 1 FROM sqlite_sequence WHERE name='projects'").fetchone():
            conn.execute(
                """INSERT INTO projects
                   (name, client, currency, material_markup, labor_rate, overhead_markup, notes, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                ("New Estimate", "", "AUD", 0.15, 120.0, 0.10, "", now, now),
            )
        missing_metadata = conn.execute(
            "SELECT COUNT(*) FROM catalog_items WHERE catalog_key IS NULL OR trim(catalog_key)=''"
        ).fetchone()[0]
        if metadata_changed or missing_metadata:
            refresh_catalog_index(conn)
        if project_metadata_changed:
            conn.execute(
                """UPDATE project_lines
                   SET category_snapshot=COALESCE(
                       (SELECT category FROM catalog_items ci WHERE ci.id=project_lines.catalog_item_id),
                       'Other'
                   )
                   WHERE category_snapshot IS NULL OR trim(category_snapshot)=''"""
            )
        conn.commit()
        from .accounts import initialize_accounts
        from .workspace import initialize_workspace
        initialize_accounts(conn)
        initialize_workspace(conn)
        from .teams import initialize_teams
        initialize_teams(conn)
        from .read_cache import initialize_catalog_generation
        initialize_catalog_generation(conn)
        from .project_notes import initialize_notes
        initialize_notes(conn)
        from .productivity import initialize_productivity
        initialize_productivity(conn)
        from .estimate_options import initialize_options
        initialize_options(conn)
        if 'scope_order' not in {r[1] for r in conn.execute('PRAGMA table_info(projects)')}:
            conn.execute("ALTER TABLE projects ADD COLUMN scope_order TEXT NOT NULL DEFAULT '[]'")
        from .estimate_sections import initialize_sections
        initialize_sections(conn)
        columns={r[1] for r in conn.execute('PRAGMA table_info(projects)')}
        for name,definition in [('crew_size','INTEGER NOT NULL DEFAULT 2'),('hours_per_day','REAL NOT NULL DEFAULT 8')]:
            if name not in columns:conn.execute(f'ALTER TABLE projects ADD COLUMN {name} {definition}')
        if 'email' not in {row[1] for row in conn.execute('PRAGMA table_info(users)')}:
            conn.execute("ALTER TABLE users ADD COLUMN email TEXT NOT NULL DEFAULT ''")
        from .light_prices import ensure_schema
        ensure_schema(conn)
        from .release_v23 import initialize_v23
        initialize_v23(conn)
        conn.commit()
    from .lighting_migration import merge_legacy_prices
    merge_legacy_prices(target)
    with connect(target) as conn:
        from .release_v231 import initialize_v231
        initialize_v231(conn)
        from .release_v233 import initialize_v233
        initialize_v233(conn)
        from .release_v24_hours import initialize_hours
        initialize_hours(conn)
    from .backups import prune_backups
    prune_backups(target.parent/'backups')
    return target


def get_settings(conn: sqlite3.Connection, include_secrets: bool = False) -> dict[str, str]:
    settings = {row["key"]: row["value"] for row in conn.execute("SELECT key, value FROM settings")}
    settings.setdefault("default_save_mode", "estimate")
    if not include_secrets:
        for key in SECRET_SETTING_KEYS:
            settings.pop(key, None)
    return settings


def update_settings(conn: sqlite3.Connection, values: dict[str, str]) -> None:
    now = utc_now()
    for key, value in values.items():
        conn.execute(
            """INSERT INTO settings(key, value, updated_at) VALUES (?, ?, ?)
               ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at""",
            (key, str(value), now),
        )

"""Schema 26: optional project labour-hour markup, zero for existing estimates."""
from .utils import utc_now

def initialize_hours(conn):
    if 'labor_hours_markup' not in {r[1] for r in conn.execute('PRAGMA table_info(projects)')}:
        conn.execute('ALTER TABLE projects ADD COLUMN labor_hours_markup REAL NOT NULL DEFAULT 0')
    conn.execute("INSERT OR IGNORE INTO settings(key,value,updated_at) VALUES ('default_labor_hours_markup','0',?)",(utc_now(),))
    conn.execute('INSERT OR IGNORE INTO app_migrations VALUES (?,?)',('v2.4-labor-hours',utc_now()))
    conn.execute('CREATE INDEX IF NOT EXISTS idx_lines_catalog_recent ON project_lines(catalog_item_id, created_at)')
    conn.execute('UPDATE schema_version SET version=26')

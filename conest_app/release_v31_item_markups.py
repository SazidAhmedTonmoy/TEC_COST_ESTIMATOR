"""Schema 28: estimate-only, opt-out markup settings (existing prices unchanged)."""
from .utils import utc_now
FIELDS = ('exclude_material_markup', 'exclude_hours_markup', 'exclude_final_markup')

def initialize_item_markups(conn):
    columns = {r[1] for r in conn.execute('PRAGMA table_info(project_lines)')}
    for name in FIELDS:
        if name not in columns:
            conn.execute(f'ALTER TABLE project_lines ADD COLUMN {name} INTEGER NOT NULL DEFAULT 0 CHECK ({name} IN (0,1))')
    conn.execute('INSERT OR IGNORE INTO app_migrations VALUES (?,?)', ('v3.1-item-markups', utc_now()))
    conn.execute('UPDATE schema_version SET version=28')

def markup_options(payload, line=None):
    result = {}
    for name in FIELDS:
        if name in payload and type(payload[name]) is not bool:
            raise ValueError('Markup exclusions must be true or false')
        result[name] = int(payload[name]) if name in payload else int(line[name]) if line else 0
    return result

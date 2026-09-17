"""Schema 24: optional profile fields and reviewed quotation imports."""
from .release_v23 import add_columns
from .utils import utc_now
from .auto_upgrade import CURRENT_SCHEMA, MIGRATION_KEY


def initialize_v231(conn):
    conn.commit()
    conn.execute('BEGIN IMMEDIATE')
    try:
        add_columns(conn, 'users', {
            'contact_number': "TEXT NOT NULL DEFAULT ''",
            'avatar_version': 'INTEGER NOT NULL DEFAULT 0',
            'has_avatar': 'INTEGER NOT NULL DEFAULT 0',
        })
        add_columns(conn, 'quotes', {'canonical_hash': 'TEXT', 'file_sha256': 'TEXT'})
        conn.execute('CREATE INDEX IF NOT EXISTS idx_quote_canonical ON quotes(canonical_hash)')
        conn.execute('''CREATE TABLE IF NOT EXISTS user_avatars (
            user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            mime TEXT NOT NULL, image BLOB NOT NULL, updated_at TEXT NOT NULL)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS lighting_import_receipts (
            token TEXT PRIMARY KEY, user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            filename TEXT NOT NULL, file_sha256 TEXT NOT NULL,
            report_json TEXT NOT NULL, created_at TEXT NOT NULL)''')
        from .lighting_imports import backfill_signatures
        backfill_signatures(conn)
        conn.execute('INSERT OR IGNORE INTO app_migrations VALUES (?,?)', (MIGRATION_KEY, utc_now()))
        conn.execute('UPDATE schema_version SET version=?', (CURRENT_SCHEMA,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise

"""Schema 27: review deadlines independent of submission dates."""
from .utils import utc_now

MIGRATION_KEY = 'v3.0-review-workflow'


def initialize_review(conn):
    columns = {r[1] for r in conn.execute('PRAGMA table_info(projects)')}
    for name, definition in [('review_deadline', 'TEXT'), ('review_cycle', 'INTEGER NOT NULL DEFAULT 0')]:
        if name not in columns:
            conn.execute(f'ALTER TABLE projects ADD COLUMN {name} {definition}')
    # Preserve historical completion attribution and activity; only move the phase.
    conn.execute("UPDATE projects SET status='submitted',revision=revision+1 WHERE status='completed'")
    conn.execute('INSERT OR IGNORE INTO app_migrations VALUES (?,?)', (MIGRATION_KEY, utc_now()))
    conn.execute('UPDATE schema_version SET version=27')

"""Schema 25: explicit individual project editors, separate from legacy assignments."""
from .utils import utc_now


def initialize_v233(conn):
    conn.commit()
    conn.execute('BEGIN IMMEDIATE')
    try:
        # Do not reactivate historical project_assignments: those records were
        # converted to team access by an older release and are not current grants.
        conn.execute("""CREATE TABLE IF NOT EXISTS project_user_access (
            project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            granted_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
            granted_at TEXT NOT NULL,
            PRIMARY KEY(project_id,user_id))""")
        conn.execute('CREATE INDEX IF NOT EXISTS idx_project_user_access_user ON project_user_access(user_id,project_id)')
        conn.execute('INSERT OR IGNORE INTO app_migrations VALUES (?,?)',
                     ('v2.3.3-project-access', utc_now()))
        conn.execute('UPDATE schema_version SET version=25')
        conn.commit()
    except Exception:
        conn.rollback()
        raise

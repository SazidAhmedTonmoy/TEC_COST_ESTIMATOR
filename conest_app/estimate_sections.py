"""Project-specific section inclusion; absent settings mean every section is on."""
import json
from .utils import clean_text


def section_key(value):
    """A section's identity; keep the original category snapshot unchanged."""
    return clean_text(value) or 'Other'


def project_section_keys(conn, project_id):
    return {section_key(row[0]) for row in conn.execute(
        'SELECT DISTINCT category_snapshot FROM project_lines WHERE project_id=?', (project_id,))}


def excluded_categories(value):
    """Decode stored/portable settings without silently changing financial totals."""
    if value in (None, ''):
        return set()
    try:
        rows = json.loads(value) if isinstance(value, str) else value
    except (TypeError, ValueError):
        raise ValueError('Estimate section settings must be a JSON array of category names.') from None
    if (not isinstance(rows, list) or len(rows) > 2000 or any(
            not isinstance(name, str) or not clean_text(name) or len(name) > 500 for name in rows)):
        raise ValueError('Estimate section settings must contain valid category names.')
    return {section_key(name) for name in rows}


def encode_exclusions(names):
    return json.dumps(sorted({section_key(name) for name in names}), ensure_ascii=False)


def initialize_sections(conn):
    """An additive migration, valid on SQLite 3.34 without rewriting projects."""
    columns = {row[1]: row for row in conn.execute('PRAGMA table_info(projects)')}
    if 'excluded_categories' not in columns:
        conn.execute("ALTER TABLE projects ADD COLUMN excluded_categories TEXT NOT NULL DEFAULT '[]'")
    else:
        column = columns['excluded_categories']
        default = str(column[4] or '').strip('() ').strip("'\"")
        if str(column[2]).upper() != 'TEXT' or not column[3] or default != '[]':
            from .auto_upgrade import UpgradeError
            raise UpgradeError('The projects.excluded_categories column has incompatible constraints. '
                               'The section migration was not committed.')


def prune_exclusions(conn, project_id):
    """Deleting/renaming the last item leaves a later new section enabled."""
    row = conn.execute('SELECT excluded_categories FROM projects WHERE id=?', (project_id,)).fetchone()
    if row is None:
        return
    before = excluded_categories(row[0])
    if not before:
        return
    names = project_section_keys(conn, project_id)
    after = before & names
    if before != after:
        conn.execute('UPDATE projects SET excluded_categories=? WHERE id=?',
                     (encode_exclusions(after), project_id))

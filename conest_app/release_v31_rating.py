"""Optional catalogue importance; shared item metadata, independent of pricing."""
from .utils import utc_now

def initialize_rating(conn):
    if 'importance_rating' not in {r[1] for r in conn.execute('PRAGMA table_info(catalog_items)')}:
        conn.execute('ALTER TABLE catalog_items ADD COLUMN importance_rating INTEGER NOT NULL DEFAULT 0 CHECK(importance_rating BETWEEN 0 AND 5)')
    conn.execute('INSERT OR IGNORE INTO app_migrations VALUES (?,?)',('v3.1-catalog-rating',utc_now()))
    conn.execute('UPDATE schema_version SET version=29')

def validate_rating(value):
    if type(value) is not int or not 0<=value<=5:raise ValueError('Choose zero to five stars')
    return value

def set_rating(conn,item_id,value):
    value=validate_rating(value)
    row=conn.execute('SELECT id FROM catalog_items WHERE id=? AND is_active=1',(item_id,)).fetchone()
    if not row:raise LookupError('Catalog item not found')
    # The catalogue-generation trigger invalidates shared search caches.
    conn.execute('UPDATE catalog_items SET importance_rating=? WHERE id=?',(value,item_id))
    return value

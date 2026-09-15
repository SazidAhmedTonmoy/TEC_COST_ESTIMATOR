"""Bounded shared read cache, invalidated by committed catalogue changes."""
from collections import OrderedDict
from copy import deepcopy
from functools import wraps
from pathlib import Path
from threading import RLock
import sqlite3

_cache=OrderedDict()
_lock=RLock()


def initialize_catalog_generation(conn):
    conn.execute('CREATE TABLE IF NOT EXISTS catalog_generation(id INTEGER PRIMARY KEY CHECK(id=1),generation INTEGER NOT NULL)')
    conn.execute('INSERT OR IGNORE INTO catalog_generation VALUES (1,1)')
    for table in ('catalog_items','catalog_components','catalog_aliases','sources','source_occurrences'):
        for operation in ('INSERT','UPDATE','DELETE'):
            conn.execute(f'''CREATE TRIGGER IF NOT EXISTS cache_{table}_{operation.lower()}
                AFTER {operation} ON {table} BEGIN
                    UPDATE catalog_generation SET generation=generation+1 WHERE id=1;
                END''')


def catalog_read_cache(function):
    @wraps(function)
    def cached(conn,*args,**kwargs):
        # Writers must see their own uncommitted changes; never cache them.
        if conn.total_changes:
            return function(conn,*args,**kwargs)
        try:
            generation=conn.execute('SELECT generation FROM catalog_generation WHERE id=1').fetchone()[0]
            filename=conn.execute('PRAGMA database_list').fetchone()[2]
            stat=Path(filename).stat()
        except (sqlite3.OperationalError,OSError,TypeError):
            return function(conn,*args,**kwargs)
        key=(filename,stat.st_ino,stat.st_mtime_ns,generation,function.__name__,args,tuple(sorted(kwargs.items())))
        # One computation serves simultaneous identical requests. A bounded
        # cache avoids retaining results for every catalogue revision forever.
        with _lock:
            if key not in _cache:
                _cache[key]=function(conn,*args,**kwargs)
                if len(_cache)>128:_cache.popitem(last=False)
            _cache.move_to_end(key)
            return deepcopy(_cache[key])
    return cached

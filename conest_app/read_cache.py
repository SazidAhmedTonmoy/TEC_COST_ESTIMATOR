"""Bounded shared read cache, invalidated by committed catalogue changes."""
from collections import OrderedDict
from contextlib import contextmanager
from copy import deepcopy
from functools import wraps
from pathlib import Path
from threading import RLock
import sqlite3

_cache=OrderedDict()
_lock=RLock()
_flights={}


@contextmanager
def _single_flight(key):
    """Coalesce the same cold read; unrelated cache keys keep running."""
    with _lock:
        entry = _flights.get(key)
        if entry is None:
            entry = [RLock(), 0]
            _flights[key] = entry
        entry[1] += 1
    try:
        with entry[0]:
            yield
    finally:
        with _lock:
            entry[1] -= 1
            if not entry[1]:
                _flights.pop(key, None)


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
        # Never hold the global cache lock during SQL work. A slow search
        # must not block unrelated catalogue reads in another request.
        with _lock:
            if key in _cache:
                _cache.move_to_end(key)
                return deepcopy(_cache[key])
        with _single_flight(key):
            with _lock:
                if key in _cache:
                    _cache.move_to_end(key)
                    return deepcopy(_cache[key])
            value=function(conn,*args,**kwargs)
            with _lock:
                _cache[key]=value
                _cache.move_to_end(key)
                if len(_cache)>128:_cache.popitem(last=False)
                return deepcopy(value)
    return cached

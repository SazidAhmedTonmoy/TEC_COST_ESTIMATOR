"""Search metadata batching and cache consistency under simultaneous reads."""
from concurrent.futures import ThreadPoolExecutor
import threading
import unittest
from unittest.mock import patch

import test_hours_markup as fixtures
from conest_app.database import connect
from conest_app.catalog import create_manual_catalog_item, search_catalog, _source_summary, _specification
from conest_app.read_cache import catalog_read_cache


class CatalogReadScalingTests(unittest.TestCase):
    setUp = fixtures.HoursMarkupTests.setUp
    tearDown = fixtures.HoursMarkupTests.tearDown

    def seed(self, count=30):
        with connect() as db:
            return [create_manual_catalog_item(db, {
                'name': f'Parallel cable assembly {number}', 'category_override': 'Power',
                'components': [{'description': 'Cable allowance', 'size': f'{number + 1}mm',
                                'quantity_per_unit': 1, 'unit_material': number + 1}],
            })['id'] for number in range(count)]

    def test_search_batches_metadata_and_preserves_display_fields(self):
        self.seed()
        queries = []
        with connect() as db:
            db.execute('BEGIN')
            db.set_trace_callback(queries.append)
            results = search_catalog(db, 'parallel cable', 25)
            db.set_trace_callback(None)
            self.assertEqual(len(results), 25)
            self.assertEqual(sum('FROM catalog_components WHERE catalog_item_id IN (' in query for query in queries), 1)
            self.assertEqual(sum('WHERE so.catalog_item_id IN (' in query for query in queries), 1)
            for item in results:
                self.assertFalse(any(key.startswith('_') for key in item))
                for key, value in _source_summary(db, item['id']).items():
                    self.assertEqual(item[key], value)
                self.assertEqual(item['specification'], _specification(db, item['id'], item['name']))

    def test_cached_titles_prices_and_rollback_never_leak_stale_or_uncommitted_values(self):
        identifier = self.seed(1)[0]
        with connect() as db:
            baseline = search_catalog(db, 'parallel cable')[0]
        with connect() as db:
            db.execute("UPDATE catalog_items SET name='Changed cable' WHERE id=?", (identifier,))
            db.execute('UPDATE catalog_components SET unit_material=77 WHERE catalog_item_id=?', (identifier,))
            self.assertEqual(search_catalog(db, 'changed cable')[0]['unit_material'], 77)
            db.rollback()
        with connect() as db:
            self.assertEqual(search_catalog(db, 'parallel cable')[0], baseline)
            self.assertEqual(search_catalog(db, 'changed cable'), [])
            db.execute("UPDATE catalog_items SET name='Changed cable' WHERE id=?", (identifier,))
            db.execute('UPDATE catalog_components SET unit_material=77 WHERE catalog_item_id=?', (identifier,))
        with connect() as db:
            self.assertEqual(search_catalog(db, 'parallel cable'), [])
            changed = search_catalog(db, 'changed cable')[0]
            self.assertEqual(changed['unit_material'], 77)
            self.assertEqual(changed['display_name'], 'Changed cable')

    def test_page_cache_hits_and_recent_use_changes_without_catalog_generation(self):
        from conest_app.projects import create_project, add_catalog_line
        identifiers = self.seed(2)
        with connect() as db:
            project = create_project(db, {'name': 'Cache recency fixture'})['project']
            add_catalog_line(db, project['id'], identifiers[0], 1, '')
        with connect() as db:
            db.execute('BEGIN')
            expected_page = {}
            expected = search_catalog(db, 'parallel cable', sort_by='recent', page_info=expected_page)
            generation = db.execute('SELECT generation FROM catalog_generation').fetchone()[0]
        with connect() as db, patch('conest_app.catalog._search_catalog_uncached', side_effect=AssertionError('Warm page was recomputed')):
            db.execute('BEGIN')
            page = {}
            self.assertEqual(search_catalog(db, 'parallel cable', sort_by='recent', page_info=page), expected)
            self.assertEqual(page, expected_page)
        with connect() as db:
            db.execute("UPDATE project_lines SET created_at='2098-01-02T03:04:05Z' WHERE project_id=?", (project['id'],))
            self.assertEqual(db.execute('SELECT generation FROM catalog_generation').fetchone()[0], generation)
        with connect() as db:
            db.execute('BEGIN')
            results = search_catalog(db, 'parallel cable', sort_by='recent')
            used = next(item for item in results if item['id'] == identifiers[0])
            self.assertEqual(used['last_used_at'], '2098-01-02T03:04:05Z')

    def test_page_cache_respects_older_read_snapshot_after_another_writer_commits(self):
        identifier = self.seed(1)[0]
        with connect() as older:
            older.execute('BEGIN')
            original = search_catalog(older, 'parallel cable')[0]['unit_material']
            with connect() as writer:
                writer.execute('UPDATE catalog_components SET unit_material=88 WHERE catalog_item_id=?', (identifier,))
            self.assertEqual(search_catalog(older, 'parallel cable')[0]['unit_material'], original)
            with connect() as newer:
                newer.execute('BEGIN')
                self.assertEqual(search_catalog(newer, 'parallel cable')[0]['unit_material'], 88)

    def test_page_cache_keys_keep_query_options_and_pagination_independent(self):
        from conest_app.catalog import _search_catalog_uncached
        self.seed(8)
        cases = [({}, 3), ({'offset': 3}, 3), ({'group_variants': False}, 5),
                 ({'recent_first': True}, 4), ({'include_incomplete': True}, 5),
                 ({'category': 'Lighting'}, 3)]
        cases += [({'sort_by': mode}, 3) for mode in ('legacy', 'recent', 'uploaded', 'relevance')]
        with connect() as db:
            db.execute('BEGIN')
            for options, limit in cases:
                expected_page, actual_page = {}, {}
                expected = _search_catalog_uncached(db, 'parallel cable', limit, page_info=expected_page, **options)
                actual = search_catalog(db, 'parallel cable', limit, page_info=actual_page, **options)
                self.assertEqual((actual, actual_page), (expected, expected_page))
                if actual:
                    actual[0]['name'] = 'Changed by this caller'
                with patch('conest_app.catalog._search_catalog_uncached', side_effect=AssertionError('Page cache missed')):
                    self.assertEqual(search_catalog(db, 'parallel cable', limit, **options), expected)

    def test_identical_cold_reads_coalesce_without_blocking_another_key(self):
        self.seed(1)
        entered = threading.Event()
        release = threading.Event()
        lock = threading.Lock()
        calls = []
        @catalog_read_cache
        def expensive(db, key):
            with lock:
                calls.append(key)
            if key == 'shared':
                entered.set()
                self.assertTrue(release.wait(2))
            return {'items': [key]}
        def read(key):
            with connect() as db:
                return expensive(db, key)
        with ThreadPoolExecutor(max_workers=5) as pool:
            first = pool.submit(read, 'shared')
            self.assertTrue(entered.wait(2))
            followers = [pool.submit(read, 'shared') for _ in range(3)]
            other = pool.submit(read, 'different')
            self.assertEqual(other.result(timeout=1), {'items': ['different']})
            release.set()
            values = [first.result(timeout=2), *(job.result(timeout=2) for job in followers)]
        self.assertEqual(calls.count('shared'), 1)
        values[0]['items'].append('caller mutation')
        self.assertEqual(read('shared'), {'items': ['shared']})


if __name__ == '__main__':
    unittest.main()

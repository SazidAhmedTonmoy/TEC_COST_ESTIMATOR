"""Regression tests for reviewed imports, profiles and automatic schema upgrades.

PDF fixtures are synthetic test documents, never real supplier quotations.
"""
import base64
from copy import deepcopy
from contextlib import closing
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch

from openpyxl import Workbook
from PIL import Image

from conest_app import accounts, lighting_imports, auto_upgrade
from conest_app.database import connect, initialize
from conest_app.light_prices import parse_xlsx, save_quotes
from conest_app.quotation_parser import parse_content, ImportDependencyError

FIXTURES = Path(__file__).parent / 'fixtures'


def workbook_bytes(reference='TEST-231-X', price=90, day='2026-09-17', reverse=False):
    book=Workbook();sheet=book.active;sheet.title='All Items'
    sheet.append(['Project','Quote Ref','Quote Date','Supplier','Qty','Cat No','Description','Unit Ex GST','Total Ex GST','Type','Item'])
    rows=[['Test office',reference,day,'SAMPLE',10,'DL-100','Downlight',price,price*10,'D1','1'],
          ['Test office',reference,day,'SAMPLE',10,'DR-100','Driver',12.5,125,'D1','2']]
    for row in reversed(rows) if reverse else rows:sheet.append(row)
    out=io.BytesIO();book.save(out);book.close();return out.getvalue()


def photo_url(size=(900,600)):
    out=io.BytesIO();Image.new('RGB',size,(64,128,145)).save(out,'PNG')
    return 'data:image/png;base64,'+base64.b64encode(out.getvalue()).decode()


class Patch231Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.env=patch.dict(os.environ,{'CONEST_DB_PATH':str(self.root/'main.db')});self.env.start()
        # No explicit initialize(): a normal connection must migrate the schema.
        with connect() as conn:
            self.admin=dict(conn.execute("SELECT * FROM users WHERE role='admin' LIMIT 1").fetchone())
            self.other=dict(conn.execute("SELECT * FROM users WHERE id<>? LIMIT 1",(self.admin['id'],)).fetchone())
    def tearDown(self):
        self.env.stop();self.tmp.cleanup()
    def preview(self,content=None):
        return lighting_imports.create_preview('quotation.xlsx',content or workbook_bytes(),self.admin)
    def count(self,table='quotes'):
        with connect() as conn:return conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
    def commit(self,preview):
        return lighting_imports.commit_preview(preview['preview_id'],['0'],self.admin)

    def test_first_connection_initializes_schema_and_repeat_is_stable(self):
        with connect() as conn:
            self.assertEqual(conn.execute('SELECT version FROM schema_version').fetchone()[0],24)
            before=[tuple(row) for row in conn.execute('SELECT * FROM users')]
        auto_upgrade._ready.clear();initialize();initialize()
        with connect() as conn:self.assertEqual(before,[tuple(row) for row in conn.execute('SELECT * FROM users')])

    def test_upgrade_is_automatic_and_keeps_protected_snapshot(self):
        with closing(sqlite3.connect(self.root/'main.db')) as conn, conn:
            conn.execute('DROP TABLE user_avatars');conn.execute('DROP TABLE lighting_import_receipts')
            conn.execute('ALTER TABLE users DROP COLUMN contact_number')
            conn.execute('ALTER TABLE users DROP COLUMN avatar_version')
            conn.execute('ALTER TABLE users DROP COLUMN has_avatar')
            conn.execute('UPDATE schema_version SET version=23')
            before=conn.execute('SELECT id,username,name,password_hash FROM users').fetchall()
        auto_upgrade._ready.clear()
        with connect() as conn:
            self.assertEqual(before,[tuple(row) for row in conn.execute('SELECT id,username,name,password_hash FROM users')])
            self.assertEqual(conn.execute('SELECT version FROM schema_version').fetchone()[0],24)
        snapshots=list((self.root/'upgrade_backups').glob('*.db'));self.assertEqual(len(snapshots),1)
        with closing(sqlite3.connect(snapshots[0])) as conn, conn:self.assertEqual(conn.execute('SELECT version FROM schema_version').fetchone()[0],23)
        from conest_app.backups import create_backup
        create_backup();create_backup();self.assertTrue(snapshots[0].exists())

    def test_future_schema_is_not_downgraded(self):
        with closing(sqlite3.connect(self.root/'main.db')) as conn, conn:conn.execute('UPDATE schema_version SET version=999')
        auto_upgrade._ready.clear()
        with self.assertRaises(auto_upgrade.UpgradeError):connect()
        with closing(sqlite3.connect(self.root/'main.db')) as conn, conn:self.assertEqual(conn.execute('SELECT version FROM schema_version').fetchone()[0],999)

    def test_contacts_and_photo_survive_restart_and_remove(self):
        with connect() as conn:
            user=accounts.edit_user(conn,self.admin['id'],{'contact_number':'+61 (0) 412 345 678 ext 9','photo_data_url':photo_url()},self.admin)
            self.assertEqual(user['contact_number'],'+61 (0) 412 345 678 ext 9');self.assertEqual(user['has_avatar'],1)
            row=conn.execute('SELECT image FROM user_avatars WHERE user_id=?',(user['id'],)).fetchone()
            image=Image.open(io.BytesIO(row['image']));self.assertEqual(image.size,(512,512));self.assertFalse(image.getexif())
        auto_upgrade._ready.clear();initialize()
        with connect() as conn:
            self.assertEqual(conn.execute('SELECT contact_number FROM users WHERE id=?',(self.admin['id'],)).fetchone()[0],user['contact_number'])
            removed=accounts.edit_user(conn,self.admin['id'],{'remove_photo':True},self.admin)
            self.assertEqual(removed['has_avatar'],0);self.assertEqual(removed['avatar_version'],2)
        self.assertEqual(self.count('user_avatars'),0)

    def test_deleting_account_removes_private_photo_and_keeps_receipt(self):
        from conest_app.release_v23 import delete_account
        with connect() as conn:
            accounts.edit_user(conn,self.other['id'],{'photo_data_url':photo_url()},self.admin,admin=True)
            conn.execute("INSERT INTO lighting_import_receipts VALUES (?,?,?,?,?,?)",
                         ('receipt-for-deleted-user',self.other['id'],'fixture.xlsx','hash','{}',time.time()))
            result=delete_account(conn,self.other['id'],self.admin,{'confirm_username':self.other['username']})
            self.assertEqual(result['deleted_user_id'],self.other['id'])
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM user_avatars').fetchone()[0],0)
            self.assertIsNone(conn.execute('SELECT user_id FROM lighting_import_receipts').fetchone()[0])
            self.assertFalse(conn.execute('PRAGMA foreign_key_check').fetchall())

    def test_bad_profile_photo_does_not_partially_save_contact(self):
        with connect() as conn:
            with self.assertRaises(ValueError):accounts.edit_user(conn,self.admin['id'],{'contact_number':'0412345678','photo_data_url':'data:image/svg+xml;base64,PHN2Zz4='},self.admin)
            self.assertEqual(conn.execute('SELECT contact_number FROM users WHERE id=?',(self.admin['id'],)).fetchone()[0],'')
        self.assertEqual(self.count('user_avatars'),0)

    def test_profile_authorization_and_phone_validation(self):
        with connect() as conn:
            with self.assertRaises(accounts.AccessError):accounts.edit_user(conn,self.other['id'],{'contact_number':'0412345678'},self.admin)
            with self.assertRaises(ValueError):accounts.edit_user(conn,self.admin['id'],{'contact_number':'<script>alert(1)</script>'},self.admin)
            with self.assertRaises(ValueError):accounts.edit_user(conn,self.admin['id'],{'remove_photo':'yes'},self.admin)
            self.assertEqual(accounts.edit_user(conn,self.admin['id'],{'contact_number':'0012345'},self.admin)['contact_number'],'0012345')

    def test_preview_then_cancel_writes_no_supplier_records(self):
        preview=self.preview();self.assertEqual(preview['quotes'][0]['status'],'new')
        self.assertTrue(preview['quotes'][0]['selected']);self.assertEqual(self.count(),0)
        lighting_imports.cancel_preview(preview['preview_id'],self.admin)
        self.assertEqual(self.count(),0)
        with self.assertRaises(accounts.AccessError):self.commit(preview)

    def test_commit_receipt_is_idempotent(self):
        preview=self.preview();report=self.commit(preview)
        self.assertEqual((report['quotes_added'],report['groups_added'],report['lines_added']),(1,1,2))
        repeated=self.commit(preview);self.assertTrue(repeated['already_completed']);self.assertEqual(self.count(),1)

    def test_identical_quotes_recognized_after_rename_and_row_reorder(self):
        self.commit(self.preview())
        preview=lighting_imports.create_preview('renamed.xlsx',workbook_bytes(reverse=True),self.admin)
        quote=preview['quotes'][0];self.assertEqual(quote['status'],'identical');self.assertFalse(quote['can_import']);self.assertFalse(quote['selected'])
        report=self.commit(preview);self.assertEqual(report['quotes_skipped'],1);self.assertEqual(self.count(),1)

    def test_revised_quote_needs_selection_and_preserves_edits(self):
        self.commit(self.preview())
        with connect() as conn:conn.execute("UPDATE groups SET nickname='Keep my nickname',description='Edited description' WHERE id=1")
        preview=self.preview(workbook_bytes(price=100))
        self.assertEqual(preview['quotes'][0]['status'],'revised');self.assertFalse(preview['quotes'][0]['selected'])
        with self.assertRaises(ValueError):lighting_imports.commit_preview(preview['preview_id'],[],self.admin)
        report=self.commit(preview);self.assertEqual(report['quotes_added'],1);self.assertEqual(self.count(),2)
        with connect() as conn:self.assertEqual(conn.execute('SELECT nickname FROM groups WHERE id=1').fetchone()[0],'Keep my nickname')
        self.assertEqual(self.preview()['quotes'][0]['status'],'identical')

    def test_same_reference_new_date_and_new_reference_same_data_are_flagged(self):
        self.commit(self.preview())
        self.assertEqual(self.preview(workbook_bytes(day='2026-09-18'))['quotes'][0]['status'],'revised')
        other=self.preview(workbook_bytes(reference='OTHER-231-X'))['quotes'][0]
        self.assertEqual(other['status'],'matching_data');self.assertFalse(other['selected'])

    def test_new_quote_existing_products_are_explained_not_overwritten(self):
        self.commit(self.preview())
        other=self.preview(workbook_bytes(reference='OTHER-231-X',price=100))['quotes'][0]
        self.assertEqual(other['status'],'new');self.assertTrue(other['selected']);self.assertEqual(other['matching_product_rows'],2)

    def test_preview_is_owner_bound_and_expiring(self):
        preview=self.preview()
        with self.assertRaises(accounts.AccessError):lighting_imports.commit_preview(preview['preview_id'],['0'],self.other)
        with self.assertRaises(accounts.AccessError):lighting_imports.cancel_preview(preview['preview_id'],self.other)
        path=lighting_imports._preview_path(preview['preview_id']);data=json.loads(path.read_text());data['created_at']=time.time()-1900;path.write_text(json.dumps(data))
        with self.assertRaises(accounts.AccessError) as context:self.commit(preview)
        self.assertEqual(context.exception.status,410);self.assertEqual(self.count(),0)

    def test_live_permission_rechecked_before_commit(self):
        preview=self.preview()
        def denied(conn):raise accounts.AccessError(403,'Account revoked')
        with self.assertRaises(accounts.AccessError):lighting_imports.commit_preview(preview['preview_id'],['0'],self.admin,denied)
        self.assertEqual(self.count(),0)

    def test_concurrent_import_rechecks_exact_duplicates_and_changed_references(self):
        a=self.preview();b=self.preview();self.commit(a)
        self.assertEqual(self.commit(b)['quotes_skipped'],1)
        c=self.preview(workbook_bytes(reference='LATER',price=101))
        q,_=parse_xlsx(workbook_bytes(reference='LATER',price=102));save_quotes(q)
        with self.assertRaises(accounts.AccessError) as context:self.commit(c)
        self.assertEqual(context.exception.status,409);self.assertEqual(self.count(),2)

    def test_blank_invalid_and_unsupported_files_are_actionable(self):
        for filename,content in [('a.pdf',b''),('a.pdf',b'not a PDF'),('a.pdf',b'%PDF-1.4\ncorrupt'),('a.xlsx',b'notzip'),('a.txt',b'hi')]:
            with self.subTest(filename=filename,content=content),self.assertRaises(ValueError):parse_content(filename,content)
        book=Workbook();book.active.title='All Items';out=io.BytesIO();book.save(out)
        with self.assertRaises(ValueError):parse_content('empty.xlsx',out.getvalue())

    def test_standard_compact_and_continuation_pdfs(self):
        hashes=[]
        for name in ('tle_standard.pdf','tle_compact.pdf','tle_continuation.pdf'):
            with self.subTest(name=name):
                quotes,excluded=parse_content(name,(FIXTURES/name).read_bytes());quote=quotes[0]
                self.assertEqual(len(quote['lines']),3);self.assertEqual(excluded,1);self.assertEqual(quote['total_ex'],1025)
                self.assertEqual(quote['quote_date'],'2026-09-17');self.assertIsNone(quote['lines'][2]['total_ex'])
                hashes.append(lighting_imports.canonical_digest(quote))
        self.assertEqual(len(set(hashes)),1)

    def test_encrypted_and_image_only_pdf_messages(self):
        for name,fragment in [('tle_encrypted.pdf','password'),('blank_scan.pdf','scanned')]:
            with self.subTest(name=name),self.assertRaisesRegex(ValueError,fragment):parse_content(name,(FIXTURES/name).read_bytes())

    def test_missing_pdf_dependency_has_specific_error(self):
        import builtins
        original=builtins.__import__
        def missing(name,*args,**kwargs):
            if name=='pdfplumber':raise ModuleNotFoundError('pdfplumber')
            return original(name,*args,**kwargs)
        with patch('builtins.__import__',side_effect=missing),self.assertRaises(ImportDependencyError):
            parse_content('a.pdf',(FIXTURES/'tle_standard.pdf').read_bytes())

    def test_backup_failure_does_not_import(self):
        preview=self.preview()
        with patch('conest_app.backups.create_backup',side_effect=OSError('disk full')):
            with self.assertRaisesRegex(ValueError,'No prices were imported'):self.commit(preview)
        self.assertEqual(self.count(),0)


if __name__=='__main__':unittest.main()

"""Small deterministic app records used only by local automated tests."""
from datetime import date
from conest_app import accounts, light_prices
from conest_app.catalog import create_manual_catalog_item
from conest_app.projects import create_project, add_catalog_line, update_project_line
from conest_app.workspace import register_project, record_activity
from conest_app.project_notes import add_note
from conest_app.productivity import save_revision
from conest_app.utils import utc_now

PASSWORD = 'Test-only-private-232!'


def seed(conn):
    admin = dict(conn.execute("SELECT * FROM users WHERE role='admin' LIMIT 1").fetchone())
    teams = [r[0] for r in conn.execute('SELECT id FROM teams ORDER BY id LIMIT 2')]
    people = []
    for username, team in [('test-owner', teams[0]), ('test-editor', teams[0]), ('test-viewer', teams[1])]:
        u = accounts.create_user(conn, {'username':username, 'name':username.replace('test-','').title()+' Person',
            'password':PASSWORD, 'role':'user', 'team_id':team})
        conn.execute('UPDATE users SET must_change_password=0 WHERE id=?', (u['id'],))
        people.append(dict(conn.execute('SELECT * FROM users WHERE id=?',(u['id'],)).fetchone()))
    owner, editor, viewer = people
    item = create_manual_catalog_item(conn, {'name':'LED Batten','category_override':'Lighting','base_uom':'EA', 'components':[
        {'description':'Fitting supply','quantity_per_unit':1,'unit_material':0,'unit_hours':0},
        {'description':'Cable accessories','size':'2.5 mm2','quantity_per_unit':2,'unit_material':5,'unit_hours':.2},
        {'description':'Commissioning','quantity_per_unit':1,'labor_pricing':'fixed','unit_labor_price':30}]})
    conn.execute('INSERT INTO catalog_aliases(catalog_item_id,alias,normalized_alias,weight,source,created_at) VALUES (?,?,?,?,?,?)',
                 (item['id'],'test linear fitting','test linear fitting',1,'manual',utc_now()))
    project = create_project(conn,{'name':'Orchid Office','client':'Sample Client','material_markup':.1,'labor_rate':90,'overhead_markup':.05})['project']
    pid=project['id'];register_project(conn,pid,owner)
    conn.execute('UPDATE projects SET submission_deadline=?,scope_of_work=? WHERE id=?',(date.today().isoformat(),'Power and lighting refurbishment',pid))
    first=add_catalog_line(conn,pid,item['id'],7)['lines'][0]
    update_project_line(conn,pid,first['id'],{'reference_name':'D1','supply_unit_cost_override':100})
    second=add_catalog_line(conn,pid,item['id'],3)['lines'][-1]
    update_project_line(conn,pid,second['id'],{'reference_name':'D10'})
    note=add_note(conn,pid,owner,{'body':'Check the specified D1 dimming driver.'})[0]
    rid=save_revision(conn,pid,editor,{'label':'Original'})
    record_activity(conn,pid,owner,'Updated lighting allowance','Confirmed D1 supply quantity')
    quote={'reference':'TEST-232-LIGHT','quote_date':'2026-09-18','project':'Orchid Office','source':'test.xlsx','total_ex':1025,
           'lines':[light_prices.normal_line(r,i) for i,r in enumerate([
               {'Type':'D1','Supplier':'Example Supplier','Qty':10,'Cat No':'DL-100','Description':'Downlight body','Unit Ex GST':90,'Total Ex GST':900},
               {'Type':'','Supplier':'Example Supplier','Qty':10,'Cat No':'DRV-100','Description':'DALI driver','Unit Ex GST':12.5,'Total Ex GST':125}],1)]}
    digest=light_prices.quote_digest(quote)
    light_prices.insert_quote(conn,quote,digest)
    gid=conn.execute('SELECT id FROM groups ORDER BY id DESC LIMIT 1').fetchone()[0]
    conn.execute('UPDATE groups SET nickname=? WHERE id=?',('Orchid favourite',gid))
    return dict(admin=admin,owner=owner,editor=editor,viewer=viewer,project_id=pid,catalog_id=item['id'],
                line_id=first['id'],second_line_id=second['id'],note_id=note['id'],revision_id=rid,light_id=gid,teams=teams)

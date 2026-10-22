"""Portable estimate files. Import always creates a new, independently owned project."""
import math
import json
from datetime import date
from .projects import create_project,calculate_project
from .workspace import register_project,require_project,record_activity
from .utils import utc_now
from .taxonomy import WORK_TYPES
from .estimate_sections import excluded_categories, encode_exclusions, section_key

PROJECT='name client currency material_markup labor_rate labor_hours_markup overhead_markup crew_size hours_per_day notes scope_of_work submission_deadline status review_deadline award_status scope_order excluded_categories'.split()
LINE='name_snapshot description_snapshot scope_snapshot category_snapshot quantity uom work_type_snapshot notes reference_name size_snapshot supply_unit_cost_override supply_quantity_override exclude_material_markup exclude_hours_markup exclude_final_markup'.split()
COMPONENT='description quantity_per_unit uom size unit_material material_factor unit_hours labor_factor is_parent notes labor_pricing unit_labor_price is_supply_copy fixed_quantity source_quantity'.split()
NUMBERS=set('material_markup labor_rate labor_hours_markup overhead_markup crew_size hours_per_day quantity quantity_per_unit unit_material material_factor unit_hours labor_factor unit_labor_price source_quantity supply_unit_cost_override supply_quantity_override'.split())
FLAGS=set('is_parent is_supply_copy fixed_quantity exclude_material_markup exclude_hours_markup exclude_final_markup'.split())
NULLABLE={'source_quantity','supply_unit_cost_override','supply_quantity_override','submission_deadline','review_deadline'}

def extract(row,fields):return {k:row[k] for k in fields if k in row}

def export_json(conn,pid,user):
 require_project(conn,pid,user,'view')
 data=calculate_project(conn,pid)
 return {'format':'tec-conest-project','version':1,'project':extract(data['project'],PROJECT),'lines':[
  {**extract(line,LINE),'components':[extract(c,COMPONENT) for c in conn.execute('SELECT * FROM project_line_components WHERE project_line_id=? ORDER BY line_order,id',(line['id'],)).fetchall() for c in [dict(c)]]} for line in data['lines']]}

def checked(raw,fields,label):
 if not isinstance(raw,dict):raise ValueError(label+' must be an object')
 result={}
 for key,value in extract(raw,fields).items():
  if value is None:
   if key in NULLABLE:result[key]=None;continue
   if key not in NUMBERS|FLAGS:value=''
  if key in NUMBERS:
   if type(value) not in (int,float) or not math.isfinite(value) or not 0<=value<=1e12:raise ValueError(label+'.'+key+' must be a finite non-negative number')
  elif key in FLAGS:
   if type(value) not in (int,bool) or value not in (0,1):raise ValueError(label+'.'+key+' must be 0 or 1')
   value=int(value)
  elif not isinstance(value,str) or len(value)>20000:raise ValueError(label+'.'+key+' must be text up to 20,000 characters')
  result[key]=value
 return result

def insert(conn,table,values):
 return conn.execute('INSERT INTO '+table+' ('+','.join(values)+') VALUES ('+','.join('?' for _ in values)+')',tuple(values.values())).lastrowid

def import_json(conn,raw,user):
 if not isinstance(raw,dict) or raw.get('format')!='tec-conest-project' or type(raw.get('version')) is not int or raw['version']!=1:raise ValueError('Use a TEC ConEst project JSON file, version 1')
 p=checked(raw.get('project'),PROJECT,'Project')
 if not p.get('name','').strip() or len(p['name'])>500:raise ValueError('Project name must be 1–500 characters')
 status=p.get('status','draft')
 if status not in ('draft','in_progress','in_review','submitted','closed'):raise ValueError('Invalid project progress')
 for key in ('submission_deadline','review_deadline'):
  if p.get(key):
   try:
    if date.fromisoformat(p[key]).isoformat()!=p[key]:raise ValueError()
   except (ValueError,TypeError):raise ValueError(key+' must use YYYY-MM-DD') from None
 if status=='in_review' and not p.get('review_deadline'):raise ValueError('In review needs a review deadline')
 if p.get('award_status','') not in ('','won','lost'):raise ValueError('Invalid project result')
 if len(p.get('currency','AUD'))>8:raise ValueError('Currency is too long')
 if p.get('scope_order'):
  try:order=json.loads(p['scope_order'])
  except (ValueError,TypeError):raise ValueError('Invalid category order') from None
  if not isinstance(order,list) or any(not isinstance(x,str) for x in order):raise ValueError('Category order must be a JSON array of names')
  p['scope_order']=json.dumps(list(dict.fromkeys(section_key(x) for x in order)))
 rows=raw.get('lines',[])
 if not isinstance(rows,list) or len(rows)>2000:raise ValueError('Use up to 2,000 estimate items per file')
 parsed=[];count=0
 for i,row in enumerate(rows):
  line=checked(row,LINE,f'Item {i+1}')
  if not line.get('name_snapshot','').strip() or len(line['name_snapshot'])>500:raise ValueError('Each item needs a name of up to 500 characters')
  if line.get('work_type_snapshot','assembly') not in WORK_TYPES:raise ValueError('Invalid item work type')
  components=row.get('components',[])
  if not isinstance(components,list):raise ValueError('Components must be an array')
  count+=len(components)
  if count>20000:raise ValueError('Use up to 20,000 components per file')
  parts=[]
  for c in components:
   part=checked(c,COMPONENT,'Component')
   if not part.get('description','').strip():raise ValueError('Each component needs a description')
   if part.get('labor_pricing','hours') not in ('hours','fixed'):raise ValueError('Invalid labour pricing basis')
   parts.append(part)
  parsed.append((line,parts))
 exclusions=excluded_categories(p.get('excluded_categories'))
 categories={section_key(line.get('category_snapshot')) for line,_ in parsed}
 if exclusions - categories:raise ValueError('Excluded sections must match categories in the imported estimate')
 p['excluded_categories']=encode_exclusions(exclusions)
 # Validation above and caller transaction prevent partial projects on failure.
 pid=create_project(conn,{**p,'submission_deadline':None})['project']['id']
 register_project(conn,pid,user)
 extras={k:p[k] for k in ('scope_of_work','submission_deadline','status','review_deadline','award_status','scope_order','excluded_categories') if k in p}
 if status!='in_review':extras['review_deadline']=None
 if extras:conn.execute('UPDATE projects SET '+','.join(k+'=?' for k in extras)+' WHERE id=?',(*extras.values(),pid))
 now=utc_now()
 for i,(line,parts) in enumerate(parsed):
  lid=insert(conn,'project_lines',{'project_id':pid,'catalog_item_id':None,'created_at':now,'updated_at':now,'sort_order':i*10,'is_manual':1,**line})
  for j,part in enumerate(parts):insert(conn,'project_line_components',{'project_line_id':lid,'line_order':j+1,**part})
 record_activity(conn,pid,user,'Imported project JSON',f'{len(parsed)} estimate items')
 return pid

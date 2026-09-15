"""Presentation titles and estimate-only luminaire supply allowances."""
import re
from .utils import clean_text

LIGHTING_CATEGORIES=('Lighting','Emergency & Exit Lighting')

def display_title(value):
    text=clean_text(value)
    def strip(match):
        content=match.group(1).strip()
        if re.fullmatch(r'(?:(?:l|length|qty|quantity)\s*[:=.-]?\s*)?\d+(?:\.\d+)?\s*(?:m|metres?|meters?|ea|pcs|units?|nos?\.?)?',content,re.I):return ''
        return match.group(0)
    return clean_text(re.sub(r'\(([^()]*)\)',strip,text))

def supply_component(category,components):
    if category not in LIGHTING_CATEGORIES or not components:return None
    return next((c for c in components if c.get('is_parent')),components[0])

def annotate_catalog(item,components):
    item['display_name']=display_title(item['name'])
    if item.get('assembly_size'):item['specification']=item['assembly_size']
    supply=supply_component(item.get('category'),components)
    if supply:
        item['pricing_work_type']='installation_only' if not (supply.get('unit_material') or supply.get('unit_hours') or supply.get('unit_labor_price')) else 'supply_install'
        item['supply_unit_cost']=supply.get('unit_material',0)
        item['pricing_label']='Installation only' if item['pricing_work_type']=='installation_only' else 'Supply & installation'
    return item

def initialize_options(conn):
    for table,column in [('catalog_items','assembly_size'),('project_lines','size_snapshot')]:
        if column not in {r['name'] for r in conn.execute(f'PRAGMA table_info({table})')}:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} TEXT NOT NULL DEFAULT ''")

    for table in ('catalog_components','project_line_components'):
        if 'is_supply_copy' not in {r['name'] for r in conn.execute(f'PRAGMA table_info({table})')}:
            conn.execute(f'ALTER TABLE {table} ADD COLUMN is_supply_copy INTEGER NOT NULL DEFAULT 0')

    cols={r['name'] for r in conn.execute('PRAGMA table_info(project_lines)')}
    for name in ('supply_quantity_override','supply_unit_cost_override'):
        if name not in cols:conn.execute(f'ALTER TABLE project_lines ADD COLUMN {name} REAL')
    if not conn.execute("SELECT 1 FROM app_migrations WHERE name='v1.14-persistent-sessions'").fetchone():
        # Extend only sessions that are still valid when upgrading.
        import time
        conn.execute('UPDATE sessions SET expires_at=0 WHERE expires_at>?',(int(time.time()),))
        conn.execute('INSERT INTO app_migrations VALUES (?,?)',('v1.14-persistent-sessions',__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()))

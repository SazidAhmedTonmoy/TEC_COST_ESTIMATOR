from __future__ import annotations

import sqlite3
import json
import math
from datetime import date
from typing import Any

from .catalog import create_manual_catalog_item, update_manual_catalog_item, _validated_components, get_catalog_item, record_selection, _nonnegative
from .utils import as_float, clean_text, utc_now
from .taxonomy import scope_sort_key
from .workspace import check_revision
from .estimate_options import display_title, supply_component, LIGHTING_CATEGORIES


def _project_row(conn: sqlite3.Connection, project_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if not row:
        raise LookupError("Project not found")
    return row


def list_projects(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """SELECT p.*, COUNT(pl.id) AS line_count
           FROM projects p LEFT JOIN project_lines pl ON pl.project_id = p.id
           GROUP BY p.id ORDER BY p.updated_at DESC, p.id DESC"""
    ).fetchall()
    result = []
    for row in rows:
        project = dict(row)
        totals = calculate_project(conn, int(row["id"]), include_components=False)["totals"]
        project["totals"] = totals
        result.append(project)
    return result


def delete_project(conn: sqlite3.Connection, project_id: int) -> dict[str, Any]:
    project = dict(_project_row(conn, project_id))
    # Foreign keys cascade through estimate lines/components, never the catalog.
    conn.execute("DELETE FROM projects WHERE id=?", (project_id,))
    return {"deleted_project_id": project_id, "deleted_project_name": project["name"], "projects": list_projects(conn)}


def crew_plan(payload):
    try: crew=float(payload.get('crew_size',2));hours=float(payload.get('hours_per_day',8))
    except (TypeError,ValueError):raise ValueError('Enter a valid crew size and hours per day')
    if not math.isfinite(crew) or not crew.is_integer() or not 1<=crew<=5000:raise ValueError('Crew size must be a whole number from 1 to 5000')
    if not math.isfinite(hours) or not 0<hours<=24:raise ValueError('Hours per person per day must be greater than zero and at most 24')
    return int(crew),hours


def create_project(conn: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, Any]:
    deadline=payload.get('submission_deadline')
    if deadline:
        try: parsed=date.fromisoformat(deadline)
        except (TypeError,ValueError): raise ValueError('Submission deadline must be a valid date') from None
        if parsed.isoformat()!=deadline or parsed<date.today():
            raise ValueError('New project deadline must be today or a future date')
    name = clean_text(payload.get("name") or "New Estimate")
    now = utc_now()
    defaults=dict(conn.execute('SELECT key,value FROM settings'))
    crew,hours=crew_plan({'crew_size':defaults.get('default_crew_size',2),'hours_per_day':defaults.get('default_hours_per_day',8),**payload})
    cursor = conn.execute(
        """INSERT INTO projects
           (name, client, currency, material_markup, labor_rate, overhead_markup, notes, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            name,
            clean_text(payload.get("client")),
            clean_text(payload.get("currency") or "AUD")[:8],
            max(0.0, as_float(payload.get("material_markup"), 0.15)),
            max(0.0, as_float(payload.get("labor_rate"), 120.0)),
            max(0.0, as_float(payload.get("overhead_markup"), 0.10)),
            clean_text(payload.get("notes")),
            now,
            now,
        ),
    )
    conn.execute('UPDATE projects SET crew_size=?,hours_per_day=? WHERE id=?',(crew,hours,int(cursor.lastrowid)))
    return calculate_project(conn, int(cursor.lastrowid))


def update_project(conn: sqlite3.Connection, project_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    current = dict(_project_row(conn, project_id))
    check_revision(current, payload)
    current.update(payload)
    crew,hours=crew_plan(current)
    name = clean_text(current.get("name"))
    if not name:
        raise ValueError("Project name is required")
    conn.execute(
        """UPDATE projects SET name=?, client=?, currency=?, material_markup=?, labor_rate=?,
           overhead_markup=?, notes=?, updated_at=? WHERE id=?""",
        (
            name,
            clean_text(current.get("client")),
            clean_text(current.get("currency") or "AUD")[:8],
            max(0.0, as_float(current.get("material_markup"), 0.15)),
            max(0.0, as_float(current.get("labor_rate"), 120.0)),
            max(0.0, as_float(current.get("overhead_markup"), 0.10)),
            clean_text(current.get("notes")),
            utc_now(),
            project_id,
        ),
    )
    conn.execute('UPDATE projects SET crew_size=?,hours_per_day=? WHERE id=?',(crew,hours,project_id))
    return calculate_project(conn, project_id)


def add_catalog_line(
    conn: sqlite3.Connection,
    project_id: int,
    catalog_item_id: int,
    quantity: float,
    query: str = "",
) -> dict[str, Any]:
    _project_row(conn, project_id)
    item = get_catalog_item(conn, catalog_item_id)
    if not item or not item["is_active"]:
        raise LookupError("Catalog item not found")
    quantity = _nonnegative(quantity, "Estimate quantity")
    sort_order = conn.execute(
        "SELECT COALESCE(MAX(sort_order), 0) + 10 FROM project_lines WHERE project_id = ?",
        (project_id,),
    ).fetchone()[0]
    now = utc_now()
    cursor = conn.execute(
        """INSERT INTO project_lines
           (project_id, catalog_item_id, code_snapshot, name_snapshot, description_snapshot, scope_snapshot, category_snapshot, quantity,
            uom, sort_order, is_manual, notes, created_at, updated_at, work_type_snapshot)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '', ?, ?, ?)""",
        (
            project_id,
            catalog_item_id,
            item["code"],
            item["name"],
            item["description"],
            item["scope"] or item["phase"],
            item.get("category") or "Other",
            quantity,
            item["base_uom"] or "EA",
            sort_order,
            item["is_manual"],
            now,
            now,
            item.get("work_type") or "assembly",
        ),
    )
    line_id = int(cursor.lastrowid)
    _copy_line_components(conn, line_id, item)
    conn.execute('UPDATE project_lines SET size_snapshot=? WHERE id=?',(item.get('assembly_size',''),line_id))
    if query:
        record_selection(conn, query, catalog_item_id)
    conn.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (now, project_id))
    return calculate_project(conn, project_id)


def _copy_line_components(conn: sqlite3.Connection, line_id: int, item: dict[str, Any]) -> None:
    conn.execute("DELETE FROM project_line_components WHERE project_line_id=?", (line_id,))
    for component in item["components"]:
        conn.execute(
            """INSERT INTO project_line_components
               (project_line_id, line_order, item_no, description, quantity_per_unit, uom, q_m, size,
                unit_material, material_factor, unit_hours, labor_factor, is_parent, notes, labor_pricing, unit_labor_price, is_supply_copy)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                line_id,
                component["line_order"],
                component["item_no"],
                component["description"],
                component["quantity_per_unit"],
                component["uom"],
                component["q_m"],
                component["size"],
                component["unit_material"],
                component["material_factor"],
                component["unit_hours"],
                component["labor_factor"],
                component["is_parent"],
                component["notes"],
                component.get("labor_pricing", "hours"),
                component.get("unit_labor_price", 0),
                component.get("is_supply_copy",0),
            ),
        )


def save_manual_estimate_item(conn, project_id, payload, line_id=None):
    """Save the estimate independently; catalogue writes are an explicit choice."""
    from copy import deepcopy
    _project_row(conn,project_id)
    line=conn.execute('SELECT * FROM project_lines WHERE id=? AND project_id=?',(line_id,project_id)).fetchone() if line_id is not None else None
    if line_id is not None and line is None:raise LookupError('Estimate line not found')
    if line is not None:check_revision(line,payload)
    quantity=_nonnegative(payload.get('quantity',line['quantity'] if line else 1),'Estimate quantity')
    source=payload.get('item')
    if not isinstance(source,dict):raise ValueError('Catalog item details are required')
    raw=deepcopy(source)
    name=clean_text(raw.get('name'));category=clean_text(raw.get('category_override')) or 'Other'
    if not name or len(name)>500:raise ValueError('Enter an item name of 1–500 characters')
    if len(category)>120:raise ValueError('Category must be 120 characters or fewer')
    from .taxonomy import WORK_TYPES
    if raw.get('work_type','assembly') not in WORK_TYPES:raise ValueError('Choose a work type')
    if len(clean_text(raw.get('assembly_size')))>250:raise ValueError('Size must be 250 characters or fewer')
    components=_validated_components(raw)
    fitting=supply_component(category,components)
    supply_price=None
    catalog_components=deepcopy(components)
    if fitting:
        supply_price=fitting['unit_material']*fitting['material_factor']
        reusable_fitting=supply_component(category,catalog_components)
        reusable_fitting['unit_material']=0
        reusable_fitting['material_factor']=1
        for reusable in catalog_components:
            if reusable.get('is_supply_copy'):
                reusable['unit_material']=0
                reusable['material_factor']=1
    raw['components']=catalog_components
    mode=payload.get('save_mode','new')
    if mode not in ('estimate','update','new'):raise ValueError('Choose where to save this item')
    if mode=='estimate' and line is None and not raw.get('source_item_id'):raise ValueError('New items must first be saved to the catalog')
    if mode=='update':
        target=line['catalog_item_id'] if line else raw.get('source_item_id')
        if not target:raise ValueError('Choose a catalog item to update')
        item=update_manual_catalog_item(conn,target,raw)
    elif mode=='new':item=create_manual_catalog_item(conn,raw)
    else:
        item={'id':line['catalog_item_id'] if line else raw['source_item_id'],'code':line['code_snapshot'] if line else raw.get('code',''),'name':name,'description':raw.get('description',name),
              'scope':raw.get('scope',''),'phase':raw.get('phase',''),'category':category,'work_type':raw.get('work_type','assembly'),
              'base_uom':raw.get('base_uom','EA'),'assembly_size':clean_text(raw.get('assembly_size')),'components':components}
    if line is None:
        before={r[0] for r in conn.execute('SELECT id FROM project_lines WHERE project_id=?',(project_id,))}
        add_catalog_line(conn,project_id,item['id'],quantity)
        line_id=next(r[0] for r in conn.execute('SELECT id FROM project_lines WHERE project_id=?',(project_id,)) if r[0] not in before)
        _copy_line_components(conn,line_id,{'components':components})
        conn.execute('UPDATE project_lines SET name_snapshot=?,description_snapshot=?,category_snapshot=?,work_type_snapshot=?,uom=? WHERE id=?',(name,raw.get('description',name),category,raw.get('work_type','assembly'),raw.get('base_uom','EA'),line_id))
    else:
        conn.execute("""UPDATE project_lines SET catalog_item_id=?,name_snapshot=?,description_snapshot=?,category_snapshot=?,
            work_type_snapshot=?,quantity=?,uom=?,size_snapshot=?,updated_at=?,revision=revision+1 WHERE id=? AND project_id=?""",
            (item['id'],name,raw.get('description',name),category,raw.get('work_type','assembly'),quantity,raw.get('base_uom','EA'),
             clean_text(raw.get('assembly_size')),utc_now(),line_id,project_id))
        _copy_line_components(conn,line_id,{'components':components})
    conn.execute('UPDATE project_lines SET supply_unit_cost_override=?,size_snapshot=? WHERE id=?',
                 (supply_price,clean_text(raw.get('assembly_size')),line_id))
    conn.execute('UPDATE projects SET updated_at=? WHERE id=?',(utc_now(),project_id))
    return {'item':item,'catalog_saved':mode!='estimate',**calculate_project(conn,project_id)}


def update_project_line(conn: sqlite3.Connection, project_id: int, line_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    line = conn.execute(
        "SELECT * FROM project_lines WHERE id = ? AND project_id = ?", (line_id, project_id)
    ).fetchone()
    if not line:
        raise LookupError("Estimate line not found")
    check_revision(line, payload)
    quantity = _nonnegative(payload.get("quantity", line["quantity"]), "Estimate quantity")
    category = clean_text(payload.get("category_snapshot", line["category_snapshot"])) or "Other"
    if len(category) > 120:
        raise ValueError("Category must be 120 characters or fewer")
    name=clean_text(payload.get('name_snapshot',line['name_snapshot']))
    if not name or len(name)>500:raise ValueError('Estimate name must be 1–500 characters')
    extra={'name_snapshot':name}
    if 'size_snapshot' in payload:
        size=clean_text(payload['size_snapshot'])
        if len(size)>250:raise ValueError('Size must be 250 characters or fewer')
        extra['size_snapshot']=size
    # Moving a priced fitting to another scope must not drop its project price.
    if line['category_snapshot'] in LIGHTING_CATEGORIES and category not in LIGHTING_CATEGORIES and line['supply_unit_cost_override'] is not None:
        components=[dict(c) for c in conn.execute('SELECT * FROM project_line_components WHERE project_line_id=? ORDER BY line_order,id',(line_id,))]
        fitting=supply_component(line['category_snapshot'],components)
        if fitting:
            conn.execute('UPDATE project_line_components SET unit_material=?,material_factor=1 WHERE id=?',(line['supply_unit_cost_override'],fitting['id']))
        extra.update(supply_unit_cost_override=None,supply_quantity_override=None)
    if 'work_type_snapshot' in payload:
        from .taxonomy import WORK_TYPES
        if payload['work_type_snapshot'] not in WORK_TYPES:raise ValueError('Unknown work type')
        extra['work_type_snapshot']=payload['work_type_snapshot']
    if category in LIGHTING_CATEGORIES and ('quantity' in payload or 'supply_quantity_override' in payload):
        if payload.get('supply_quantity_override') is not None:
            quantity=_nonnegative(payload['supply_quantity_override'],'Quantity')

        payload=dict(payload, supply_quantity_override=None)

    for field in ('supply_quantity_override','supply_unit_cost_override'):
        if field in payload:
            if category not in LIGHTING_CATEGORIES:raise ValueError('Supply overrides apply to Lighting and Emergency & Exit Lighting')
            extra[field]=None if payload[field] is None else _nonnegative(payload[field],field.replace('_',' '))
    conn.execute('UPDATE project_lines SET '+','.join(f'{k}=?' for k in extra)+' WHERE id=? AND project_id=?',tuple(extra.values())+(line_id,project_id))
    conn.execute(
        """UPDATE project_lines SET quantity=?, notes=?, sort_order=?, updated_at=?, category_snapshot=?, revision=revision+1
           WHERE id=? AND project_id=?""",
        (
            quantity,
            clean_text(payload.get("notes", line["notes"])),
            int(as_float(payload.get("sort_order", line["sort_order"]), line["sort_order"])),
            utc_now(),
            category,
            line_id,
            project_id,
        ),
    )
    conn.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (utc_now(), project_id))
    return calculate_project(conn, project_id)


def delete_project_line(conn: sqlite3.Connection, project_id: int, line_id: int) -> dict[str, Any]:
    cursor = conn.execute("DELETE FROM project_lines WHERE id = ? AND project_id = ?", (line_id, project_id))
    if not cursor.rowcount:
        raise LookupError("Estimate line not found")
    conn.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (utc_now(), project_id))
    return calculate_project(conn, project_id)


def calculate_project(
    conn: sqlite3.Connection, project_id: int, include_components: bool = True
) -> dict[str, Any]:
    project = dict(_project_row(conn, project_id))
    material_markup = float(project["material_markup"])
    labor_rate = float(project["labor_rate"])
    overhead_markup = float(project["overhead_markup"])
    lines: list[dict[str, Any]] = []
    total_material = 0.0
    total_hours = 0.0
    total_labor = 0.0
    direct_total = 0.0
    quoted_total = 0.0
    line_rows = conn.execute(
        "SELECT * FROM project_lines WHERE project_id = ? ORDER BY sort_order, id", (project_id,)
    ).fetchall()
    for line_row in line_rows:
        line = dict(line_row)
        line_qty = float(line["quantity"])
        components: list[dict[str, Any]] = []
        line_material = 0.0
        line_hours = 0.0
        line_labor = 0.0
        line_fixed_labor = 0.0
        component_rows = conn.execute(
            "SELECT * FROM project_line_components WHERE project_line_id = ? ORDER BY line_order, id",
            (line["id"],),
        ).fetchall()
        supply=supply_component(line.get('category_snapshot'),[dict(c) for c in component_rows])
        supply_id=supply['id'] if supply else None
        supply_material=0.0
        for component_row in component_rows:
            component = dict(component_row)
            component['is_supply_allowance']=component['id']==supply_id or bool(supply_id is not None and component.get('is_supply_copy'))
            if component['id']==supply_id and line.get('supply_unit_cost_override') is not None:
                component['unit_material']=line['supply_unit_cost_override']
                component['material_factor']=1.0
            scaled_qty = line_qty * float(component["quantity_per_unit"])
            component['supply_quantity_is_overridden']=component['id']==supply_id and line.get('supply_quantity_override') is not None
            if component['supply_quantity_is_overridden']:scaled_qty=float(line['supply_quantity_override'])
            raw_material = scaled_qty * float(component["unit_material"]) * float(component["material_factor"])
            material = raw_material * (1 + material_markup)
            labor_qty=line_qty*float(component["quantity_per_unit"])
            fixed = component["labor_pricing"] == "fixed"
            hours = 0.0 if fixed else labor_qty * float(component["unit_hours"]) * float(component["labor_factor"])
            labor = (labor_qty * float(component["unit_labor_price"]) * float(component["labor_factor"])) if fixed else hours * labor_rate
            grand = material + labor
            component.update(
                {
                    "scaled_quantity": scaled_qty,
                    "raw_material": raw_material,
                    "total_material": material,
                    "total_hours": hours,
                    "total_labor": labor,
                    "grand_total": grand,
                }
            )
            if component['is_supply_allowance']:supply_material+=material
            line_material += material
            line_hours += hours
            line_labor += labor
            if fixed:
                line_fixed_labor += labor
            if include_components:
                components.append(component)
        line['display_name']=display_title(line['name_snapshot'])
        line['has_supply_allowance']=bool(supply)
        if supply:
            cost=line.get('supply_unit_cost_override')
            line['supply_unit_cost']=float(supply['unit_material'] if cost is None else cost)
            qty=line.get('supply_quantity_override')
            line['supply_quantity']=line_qty*float(supply['quantity_per_unit']) if qty is None else float(qty)
            line['pricing_work_type']='supply_install' if (line['supply_unit_cost'] or supply['unit_hours'] or supply['unit_labor_price'] or any(c['is_supply_copy'] and (c['unit_material'] or c['unit_hours'] or c['unit_labor_price']) for c in component_rows)) else 'installation_only'
        line['unit_supply_material']=supply_material/line_qty if line_qty else 0.0
        line['unit_installation_material']=(line_material-supply_material)/line_qty if line_qty else 0.0
        line['supply_material']=supply_material
        line['supply_quoted']=supply_material*(1+overhead_markup)
        line_direct = line_material + line_labor
        line_quoted = line_direct * (1 + overhead_markup)
        line.update(
            {
                "unit_material": line_material / line_qty if line_qty else 0.0,
                "total_material": line_material,
                "unit_hours": line_hours / line_qty if line_qty else 0.0,
                "total_hours": line_hours,
                "unit_labor": line_labor / line_qty if line_qty else 0.0,
                "unit_labor_price": line_fixed_labor / line_qty if line_qty else 0.0,
                "total_labor": line_labor,
                "unit_direct": line_direct / line_qty if line_qty else 0.0,
                "direct_total": line_direct,
                "unit_install_price": line_quoted / line_qty if line_qty else 0.0,
                "quoted_total": line_quoted,
                "components": components,
            }
        )
        total_material += line_material
        total_hours += line_hours
        total_labor += line_labor
        direct_total += line_direct
        quoted_total += line_quoted
        lines.append(line)
    scope_summary: dict[str, dict[str, Any]] = {}
    try: custom_order=json.loads(project.get('scope_order') or '[]')
    except (ValueError,TypeError): custom_order=[]
    if not isinstance(custom_order,list):custom_order=[]
    rank={name:i for i,name in enumerate(custom_order) if isinstance(name,str)}
    lines.sort(key=lambda line: (rank.get(line.get('category_snapshot'),len(rank)), scope_sort_key(line.get('category_snapshot')), line['sort_order'], line['id']))
    for line in lines:
        category = clean_text(line.get("category_snapshot")) or "Other"
        summary = scope_summary.setdefault(category, {
            "category": category, "assemblies": 0, "material": 0.0, "hours": 0.0, "labor": 0.0, "quoted": 0.0,
        })
        summary["assemblies"] += 1
        for output, field in (("material", "total_material"), ("hours", "total_hours"), ("labor", "total_labor"), ("quoted", "quoted_total")):
            summary[output] += line[field]
    for category,summary in scope_summary.items():
        if category in LIGHTING_CATEGORIES:
            supply=sum(l['supply_material'] for l in lines if l['category_snapshot']==category)
            quoted=sum(l['supply_quoted'] for l in lines if l['category_snapshot']==category)
            summary['subcategories']=[
                {'category':'Supply cost','assemblies':summary['assemblies'],'material':supply,'hours':0,'labor':0,'quoted':quoted},
                {'category':'Installation cost','assemblies':summary['assemblies'],'material':summary['material']-supply,'hours':summary['hours'],'labor':summary['labor'],'quoted':summary['quoted']-quoted}]
    from .taxonomy import WORK_TYPES
    work_summary={}
    for line in lines:
        kind=line.get('work_type_snapshot') or 'assembly'
        label=WORK_TYPES.get(kind, 'Installation')
        if kind in ('assembly','installation_only'):label='Installation'
        row=work_summary.setdefault(label,dict(category=label,assemblies=0,material=0.,hours=0.,labor=0.,quoted=0.))
        row['assemblies']+=1
        for out,key in [('material','total_material'),('hours','total_hours'),('labor','total_labor'),('quoted','quoted_total')]:row[out]+=line[key]
    return {
        "crew_plan":{'crew_size':project.get('crew_size',2),'hours_per_day':project.get('hours_per_day',8),'crew_hours_per_day':project.get('crew_size',2)*project.get('hours_per_day',8),'person_days':total_hours/project.get('hours_per_day',8),'working_days':total_hours/(project.get('crew_size',2)*project.get('hours_per_day',8))},
        "work_summary":list(work_summary.values()),
        "project": project,
        "lines": lines,
        "scope_summary": list(scope_summary.values()),
        "totals": {
            "material": total_material,
            "hours": total_hours,
            "labor": total_labor,
            "direct": direct_total,
            "overhead": quoted_total - direct_total,
            "quoted": quoted_total,
            "line_count": len(lines),
        },
    }

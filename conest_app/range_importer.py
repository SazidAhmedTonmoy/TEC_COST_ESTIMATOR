"""Import explicit low/high budget prices without inventing a single quote."""
from .utils import clean_text, normalize_text, as_float


def budget_range_header(ws):
    expected={'item':'name','description spec reference':'description','qty':'quantity',
              'unit price low aud':'low','unit price high aud':'high','notes source':'notes'}
    for row in range(1,min(30,ws.max_row)+1):
        fields={expected[normalize_text(cell.value)]:cell.column for cell in ws[row]
                if normalize_text(cell.value) in expected}
        if {'name','quantity','low','high'}<=fields.keys():return row,fields
    return None


def parse_budget_range(ws):
    from .importer import ParsedSheet,ParsedAssembly,ParsedComponent,ParsedIssue
    header,cols=budget_range_header(ws)
    result=ParsedSheet(ws.title,clean_text(ws.cell(2,1).value),'budget_range',ws.max_row,1)
    for row in range(header+1,ws.max_row+1):
        name=clean_text(ws.cell(row,cols['name']).value)
        if not name:continue
        values={k:ws.cell(row,col).value for k,col in cols.items()}
        if not isinstance(values['low'],(int,float)) or not isinstance(values['high'],(int,float)):continue
        qty=as_float(values['quantity'])
        if qty<=0:continue
        service=any(term in normalize_text(name) for term in ('installation','commissioning','documentation'))
        # The source provides monetary service allowances, not labour hours.
        for basis in ('low','high'):
            price=as_float(values[basis])
            if price<0:continue
            notes=f'Indicative budget {basis} from source range AUD {values["low"]:,.2f}–{values["high"]:,.2f}, ex GST. Confirm before quoting. '+clean_text(values.get('notes'))
            description=clean_text(values.get('description')) or name
            unit='Lot' if service or name in ('AC Power Cabling','Containment / Glanding / Termination hardware') else 'EA'
            component=ParsedComponent(1,'',description,1,qty,uom=unit,
                unit_material=0 if service else price,source_row=row,notes=notes,
                labor_pricing='fixed' if service else 'hours',unit_labor_price=price if service else 0)
            result.assemblies.append(ParsedAssembly('',f'{name} — budget {basis}',description,'','','Communications & Data',
                qty,unit,row,'budget_range',components=[component],source_material_total=0 if service else price*qty,
                work_type='installation_only' if service else 'supply_only',category_override='General & Testing' if service else 'Communications & Data'))
    result.issues.append(ParsedIssue('info','BUDGET_RANGE','Low and high prices imported as separate labelled budget options; source totals, contingency and GST are excluded.'))
    return result

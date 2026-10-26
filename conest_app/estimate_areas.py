"""Quantity-based location allocations; fixed costs are apportioned, never duplicated."""
import json, math
FIELDS={'material':'total_material','hours':'total_hours','labor':'total_labor','quoted':'quoted_total'}
DEFAULT='Shared / Unallocated'
def allocations(value):
    if isinstance(value,str):
        try:value=json.loads(value)
        except ValueError:raise ValueError('Invalid area allocation JSON') from None
    if not isinstance(value,list) or len(value)>200:raise ValueError('Use up to 200 areas per item')
    result=[];seen=set()
    for r in value:
        if not isinstance(r,dict):raise ValueError('Invalid area allocation')
        name=' '.join(str(r.get('area','')).split());q=r.get('quantity')
        if not name or len(name)>120:raise ValueError('Area names must be 1–120 characters')
        if name.casefold() in seen:raise ValueError('An area can appear only once per item')
        if type(q) not in (float,int) or not math.isfinite(q) or not 0<=q<=1e9:raise ValueError('Area quantities must be finite and non-negative')
        seen.add(name.casefold());result.append({'area':name,'quantity':float(q)})
    if result and sum(r['quantity'] for r in result)<=0:raise ValueError('Allocated items need a positive total quantity; clear allocations for a zero-quantity item')
    return result

def parts(line):
    rows=allocations(line.get('area_allocations','[]'))
    total=sum(r['quantity'] for r in rows)
    return [(r['area'],r['quantity'],r['quantity']/total) for r in rows] if rows else [(DEFAULT,line['quantity'],1)]

def summary(lines):
    groups={}
    for line in lines:
        for name,qty,weight in parts(line):
            group=groups.setdefault(name.casefold(),{'area':name,'included':dict.fromkeys(FIELDS,0.),'optional':dict.fromkeys(FIELDS,0.),'items':[]})
            values={k:line[f]*weight for k,f in FIELDS.items()}
            target=group['optional' if line.get('included_in_total') is False else 'included']
            for k in FIELDS:target[k]+=values[k]
            group['items'].append({'id':line['id'],'name':line['name_snapshot'],'category':line['category_key'],'quantity':qty,'uom':line['uom'],'optional':line.get('included_in_total') is False,**values})
    return list(groups.values())

def excel(wb,line_parent_rows):
    from openpyxl.styles import Font,PatternFill,Alignment
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation
    from openpyxl.comments import Comment
    ws=wb.create_sheet('AREA ALLOCATIONS');overview=wb.create_sheet('AREA SUMMARY')
    ws.append(['Area / floor / room','Item','Category','Quantity (edit here)','Material','Hours','Labour','Quoted','Included / Optional'])
    area_rows={};detail=wb['CONNECTED COST DETAIL']
    for line,parent in line_parent_rows:
        entries=parts(line);start=ws.max_row+1;end=start+len(entries)-1
        if allocations(line.get('area_allocations','[]')):detail.cell(parent,4,f"=SUM('AREA ALLOCATIONS'!D{start}:D{end})")
        if allocations(line.get('area_allocations','[]')):detail.cell(parent,4).comment=Comment('Quantity is linked to AREA ALLOCATIONS. Edit the area quantities there. Fixed-total components are distributed proportionally, once per item.','TEC')
        for name,qty,_ in entries:
            allocated=bool(allocations(line.get('area_allocations','[]')))
            row=ws.max_row+1;area_rows.setdefault(name.casefold(),(name,[]))[1].append(row)
            ws.append([name,line['name_snapshot'],line['category_key'],qty,None,None,None,None,'Optional' if line.get('included_in_total') is False else 'Included'])
            # When all allocations are zero, retain fixed costs in the first area.
            weight=f'IF(SUM($D${start}:$D${end})=0,{1 if row==start else 0},D{row}/SUM($D${start}:$D${end}))'
            for col,source in [(5,'G'),(6,'I'),(7,'J'),(8,'L')]:ws.cell(row,col,f"='CONNECTED COST DETAIL'!{source}{parent}*{weight}")
            ws.cell(row,1).data_type='s'
            ws.cell(row,2,f"='CONNECTED COST DETAIL'!B{parent}")
            ws.cell(row,3,f"='CONNECTED COST DETAIL'!A{parent}")
            ws.cell(row,9,f"=IF('CONNECTED COST DETAIL'!P{parent}=1,\"Included\",\"Optional\")")
            if not allocated:ws.cell(row,4,f"='CONNECTED COST DETAIL'!D{parent}")
            ws.cell(row,4).fill=PatternFill('solid',fgColor='FFF7E4')
    rule=DataValidation(type='decimal',operator='greaterThanOrEqual',formula1=0);rule.errorTitle='Invalid quantity';rule.error='Enter zero or a positive quantity.';rule.showErrorMessage=True;rule.errorStyle='stop';ws.add_data_validation(rule)
    if ws.max_row>1:rule.add(f'D2:D{ws.max_row}')
    overview.append(['Area / floor / room','Material','Hours','Labour','Quoted total','Optional material','Optional hours','Optional labour','Optional quoted'])
    for name,rows in area_rows.values():
        row=overview.max_row+1;overview.cell(row,1,name).data_type='s'
        for offset,status in [(0,'Included'),(4,'Optional')]:
            for col,source in [(2,'E'),(3,'F'),(4,'G'),(5,'H')]:
                n=ws.max_row
                overview.cell(row,col+offset,f"=SUMPRODUCT(--('AREA ALLOCATIONS'!$A$2:$A${n}=$A{row}),--('AREA ALLOCATIONS'!$I$2:$I${n}=\"{status}\"),'AREA ALLOCATIONS'!${source}$2:${source}${n})")
    last=overview.max_row;overview.append(['TOTAL'])
    for col in range(2,10):overview.cell(last+1,col,f'=SUM({get_column_letter(col)}2:{get_column_letter(col)}{last})' if last>1 else '=0')
    for sheet in (ws,overview):
        sheet.freeze_panes='D2' if sheet==ws else 'B2';sheet.auto_filter.ref=sheet.dimensions
        sheet.sheet_view.showGridLines=False
        for c in sheet[1]:c.fill=PatternFill('solid',fgColor='173B55');c.font=Font(color='FFFFFF',bold=True)
        for row in sheet.iter_rows(min_row=2):
            for c in row:
                c.alignment=Alignment(vertical='top',wrap_text=True)
                if c.column>1:c.number_format='#,##0.00'
        for col in range(1,10):sheet.column_dimensions[get_column_letter(col)].width=32 if col==1 or (sheet==ws and col in (2,3)) else 19
        sheet.print_title_rows='1:1';sheet.page_setup.orientation='landscape';sheet.sheet_properties.pageSetUpPr.fitToPage=True;sheet.page_setup.fitToWidth=1;sheet.page_setup.fitToHeight=0

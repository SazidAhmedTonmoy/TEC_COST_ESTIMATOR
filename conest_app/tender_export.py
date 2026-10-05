"""Excel export using only Python's standard library. Literal notes stay text."""
from datetime import datetime, timezone
from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED
from xml.sax.saxutils import escape
import re

NS='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
MIME='application/vnd.openxmlformats-officedocument.spreadsheetml'
SHEETS=['Summary','Projects','Builders','Tenders','Follow-ups','Scheduled']
def clean(v):return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]','',str(v))[:32767]
def col(n):
    result=''
    while n:
        n,r=divmod(n-1,26);result=chr(65+r)+result
    return result
def formula(expression,value=0):return {'formula':expression,'value':value}
def serial(v):
    if not v:return None
    try:return (datetime.fromisoformat(v)-datetime(1899,12,30)).total_seconds()/86400
    except (ValueError,TypeError):return None

def cell(address,value,style=5):
    start=f'<c r="{address}" s="{style}"'
    if value is None:return start+'/>'
    if isinstance(value,dict):
        v=value['value'];typ=' t="str"' if isinstance(v,str) else ''
        return start+typ+f'><f>{escape(value["formula"])}</f><v>{escape(clean(v))}</v></c>'
    if isinstance(value,(int,float)):return start+f'><v>{value}</v></c>'
    return start+f' t="inlineStr"><is><t xml:space="preserve">{escape(clean(value))}</t></is></c>'

def styles():
    fonts=''.join(f'<font><sz val="{size}"/><color rgb="FF{color}"/><name val="Aptos"/>{"<b/>" if bold else ""}</font>' for size,color,bold in [(10,'172B3A',False),(18,'FFFFFF',True),(10,'5F7180',False),(10,'FFFFFF',True),(10,'172B3A',True),(10,'806009',False),(24,'173B55',True),(11,'FFFFFF',True)])
    fills='<fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill>'+''.join(f'<fill><patternFill patternType="solid"><fgColor rgb="FF{c}"/><bgColor indexed="64"/></patternFill></fill>' for c in ['0B1F33','173B55','EAF1F5','FFFFFF','F8FAFB','FFF7E4','FFF2A8','E2F3EC','FFF1C2','FBE6E9','E7EEFB','F0E8FA','E8EDF1'])
    definitions=[(0,0,0),(1,2,0),(2,0,0),(3,3,0),(4,4,0),(0,5,0),(0,6,0),(0,5,164),(0,6,164),(0,5,165),(0,6,165),(0,7,0),(4,8,164),(5,5,0),(0,5,166),(3,3,164),(4,8,0),(6,4,0),(6,4,164),(4,9,0),(4,10,0),(4,11,0),(4,12,0),(4,13,0),(4,14,0),(7,3,0),(0,5,9)]
    xfs=''.join(f'<xf numFmtId="{num}" fontId="{font}" fillId="{fill}" borderId="0" xfId="0" applyFont="1" applyFill="1" applyNumberFormat="1" applyAlignment="1"><alignment vertical="center" {('horizontal="left" ' if font==6 else 'horizontal="center" ' if num in (165,166) else '')}wrapText="1"/></xf>' for font,fill,num in definitions)
    return f'''<styleSheet xmlns="{NS}"><numFmts count="3"><numFmt numFmtId="164" formatCode="&quot;$&quot;#,##0.00;[Red](&quot;$&quot;#,##0.00);&quot;$&quot;0.00"/><numFmt numFmtId="165" formatCode="d mmm yyyy"/><numFmt numFmtId="166" formatCode="d mmm yyyy hh:mm"/></numFmts><fonts count="8">{fonts}</fonts><fills count="15">{fills}</fills><borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="{len(definitions)}">{xfs}</cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>'''

def sheet_xml(name,headers,rows,widths,generated,description,note='',money_cols=(),date_cols=(),time_cols=(),links=None,summary=False):
    n=len(headers);last=max(6,5+len(rows));end=col(n)
    def row_xml(i,values,style=None,height=36):
        cells=[]
        for j,v in enumerate(values,1):
            st=style if style is not None else (5 if i%2==0 else 6)
            if style is None:
                if j in money_cols:st=7 if i%2==0 else 8
                if j in date_cols:st=9 if i%2==0 else 10
                if j in time_cols:st=14
                if isinstance(v,str) and headers[j-1] in ('TEC status','Builder outcome','Pricing feedback','Status'):
                    st={'Won':19,'Awarded':22,'Open':20,'Competitive':19,'Lost':21,'Unsuccessful':21,'High':21,'Close':24,'Closed':24,'Hold':23,'Lower':23,'In Progress':20,'Nil':24,'Pending':20,'Completed':19}.get(v,st)
                if summary and j==2 and i<=11:st=12 if i==10 else 16
            cells.append(cell(f'{col(j)}{i}',v,st))
        return f'<row r="{i}" ht="{height}" customHeight="1">'+''.join(cells)+'</row>'
    content=row_xml(1,[f'TEC Tenders — {name}']+[None]*(n-1),1,36)
    content+=row_xml(2,[generated]+[None]*(n-1),2,24)
    content+=row_xml(3,[description]+[None]*(n-1),2,30)
    content+=row_xml(4,[note]+[None]*(n-1),2,32)
    content+=row_xml(5,headers,3,34)
    for i,values in enumerate(rows,6):
        lines=max((sum(max(1,(len(line)+max(8,widths[j]-3)-1)//max(8,widths[j]-3)) for line in str(v.get('value','') if isinstance(v,dict) else v or '').split('\n')) for j,v in enumerate(values)),default=1)
        content+=row_xml(i,values,height=min(240,max(34,15*lines+12)))
    hidden={1,19} if name=='Tenders' else {1,2} if name in ('Follow-ups','Scheduled') else set()
    columns=''.join(f'<col min="{i}" max="{i}" width="{w}" customWidth="1"'+(' hidden="1"' if i in hidden else '')+'/>' for i,w in enumerate(widths,1))
    hyperlinks=[]
    if name!='Summary':hyperlinks.append(f'<hyperlink ref="{"B" if name=="Tenders" else "C" if name in ("Follow-ups","Scheduled") else "A"}2" location="&apos;Summary&apos;!A1" tooltip="Return to Summary"/>')
    for address,target in (links or {}).items():hyperlinks.append(f'<hyperlink ref="{address}" location="{escape(target,{chr(34):"&quot;"})}"/>')
    hl='<hyperlinks>'+''.join(hyperlinks)+'</hyperlinks>' if hyperlinks else ''
    filtering='' if summary else f'<autoFilter ref="A5:{end}{last}"/>'
    freeze='<pane xSplit="3" ySplit="5" topLeftCell="D6" activePane="bottomRight" state="frozen"/>' if name=='Tenders' else '<pane ySplit="5" topLeftCell="A6" activePane="bottomLeft" state="frozen"/>'
    start='B' if name=='Tenders' else 'C' if name in ('Follow-ups','Scheduled') else 'A'
    if start!='A':
        for i in range(1,5):
            # Put the merged title in the first visible column.
            content=content.replace(f'<c r="A{i}"',f'<c r="{start}{i}"',1)
            content=re.sub(fr'<c r="{start}{i}" s="[0-9]+"/>','',content,count=1)
    heading_end='H' if name in ('Tenders','Follow-ups','Scheduled') else end
    merges=''.join(f'<mergeCell ref="{start}{i}:{heading_end}{i}"/>' for i in range(1,5))
    bars=f'<conditionalFormatting sqref="C6:C{last}"><cfRule type="dataBar" priority="1"><dataBar><cfvo type="min"/><cfvo type="max"/><color rgb="FFAFCDD8"/></dataBar></cfRule></conditionalFormatting>' if name in ('Projects','Builders') and rows else ''
    return f'''<worksheet xmlns="{NS}"><sheetPr><pageSetUpPr fitToPage="1"/></sheetPr><dimension ref="A1:{end}{last}"/><sheetViews><sheetView showGridLines="0" workbookViewId="0">{freeze}</sheetView></sheetViews><sheetFormatPr defaultRowHeight="24"/><cols>{columns}</cols><sheetData>{content}</sheetData>{filtering}<mergeCells count="4">{merges}</mergeCells>{bars}{hl}<printOptions horizontalCentered="1"/><pageMargins left="0.25" right="0.25" top="0.4" bottom="0.4" header="0.2" footer="0.2"/><pageSetup paperSize="9" orientation="landscape" fitToWidth="{2 if n>14 else 1}" fitToHeight="0"/><headerFooter><oddFooter>&amp;LTEC Tenders&amp;C{name}&amp;RPage &amp;P of &amp;N</oddFooter></headerFooter></worksheet>'''

def export_workbook(data,ids,description='All submissions'):
    wanted=set(ids)
    tenders=sorted([s for s in data['submissions'] if s['id'] in wanted],key=lambda s:(s['project'].casefold(),s['builder'].casefold(),s['id']))
    lookup={s['id']:(i,s) for i,s in enumerate(tenders,6)}
    chases=sorted([c for c in data['chases'] if c['submissionId'] in lookup],key=lambda c:(c.get('date',''),c['id']),reverse=True)
    reminders=sorted([r for r in data['reminders'] if r['submissionId'] in lookup],key=lambda r:(r['due'],r['id']))
    projects=sorted(set(s['project'] for s in tenders),key=str.casefold)
    builders=sorted(set(s['builder'] for s in tenders),key=str.casefold)
    last=max(6,5+len(tenders));clast=max(6,5+len(chases));rlast=max(6,5+len(reminders))
    tr=lambda c:f"'Tenders'!${c}$6:${c}${last}"
    criterion=lambda ref:'"="&SUBSTITUTE(SUBSTITUTE(SUBSTITUTE('+ref+',"~","~~"),"*","~*"),"?","~?")'
    generated='Exported '+datetime.now(timezone.utc).strftime('%d %b %Y %H:%M UTC')+' · AUD · Follow-up times Australia/Sydney'
    xml={};trows=[]
    for i,s in enumerate(tenders,6):
        cc=sum(c['submissionId']==s['id'] for c in chases);rr=sum(r['submissionId']==s['id'] and not r['done'] for r in reminders)
        trows.append([s['id'],s['project'],s['builder'],s['status'],s.get('builderStatus',''),s.get('pricing',''),s.get('value'),serial(s.get('due')),s.get('region',''),s.get('location',''),s.get('contact',''),s.get('email',''),s.get('month',''),s.get('statusUpdated','') if '1900' not in s.get('statusUpdated','') else '',s.get('latest',''),s.get('remarks',''),formula(f'COUNTIF(\'Follow-ups\'!$B$6:$B${clast},A{i})',cc),formula(f'COUNTIFS(\'Scheduled\'!$B$6:$B${rlast},A{i},\'Scheduled\'!$G$6:$G${rlast},"Pending")',rr),s.get('sourceRow','Manual')])
    xml['Tenders']=sheet_xml('Tenders',['Submission ID','Project','Builder','TEC status','Builder outcome','Pricing feedback','Quote value (AUD)','Submission deadline','Region','Location','Contact','Email','Submission month','Status updated','Latest update','Remarks','Recorded follow-ups','Pending follow-ups','Source row'],trows,[18,42,30,15,21,19,22,21,12,30,23,30,18,18,65,55,18,18,14],generated,description,'Source: current TEC Tenders database. Follow-up counts are linked by submission ID. Click the export timestamp to return to Summary.',money_cols=(7,),date_cols=(8,))
    for name,items in [('Follow-ups',chases),('Scheduled',reminders)]:
        rows=[];links={}
        for i,item in enumerate(items,6):
            target,s=lookup[item['submissionId']];links[f'C{i}']=f"'Tenders'!B{target}"
            def linked(c,key):return formula(f'INDEX({tr(c)},MATCH(B{i},{tr("A")},0))',s.get(key,''))
            common=[item['id'],item['submissionId'],linked('B','project'),linked('C','builder')]
            if name=='Follow-ups':common += [serial(item.get('date')),item.get('method',''),item.get('author',''),item.get('note',''),item.get('createdAt','')]
            else:common += [serial(item.get('due')),item.get('note',''),'Completed' if item['done'] else 'Pending',item.get('createdAt','')]
            rows.append(common)
        headers=['Follow-up ID','Submission ID','Project','Builder','Recorded date','Method','Recorded by','Update','Created at (UTC)'] if name=='Follow-ups' else ['Reminder ID','Submission ID','Project','Builder','Scheduled time (Sydney)','Reminder note','Status','Created at (UTC)']
        widths=[38,38,48,32,26,20,22,70,30] if name=='Follow-ups' else [38,38,48,32,28,70,18,30]
        xml[name]=sheet_xml(name,headers,rows,widths,generated,description,'Project and builder look up their submission ID in Tenders. Click a project to open its tender; click the timestamp to return to Summary.',date_cols=(5,) if name=='Follow-ups' else (),time_cols=(5,) if name=='Scheduled' else (),links=links)
    prows=[];brows=[]
    for kind,names,source,rows in [('project',projects,'B',prows),('builder',builders,'C',brows)]:
        for i,name in enumerate(names,6):
            matching=[s for s in tenders if s[kind]==name];crit=criterion(f'A{i}');mids={s['id'] for s in matching}
            value=max((s.get('value') or 0 for s in matching),default=0) if kind=='project' else sum(s.get('value') or 0 for s in matching)
            vf=f'_xlfn.MAXIFS({tr("G")},{tr(source)},{crit})' if kind=='project' else f'SUMIF({tr(source)},{crit},{tr("G")})'
            rows.append([name,formula(f'COUNTIF({tr(source)},{crit})',len(matching)),formula(vf,value),formula(f'COUNTIFS({tr(source)},{crit},{tr("D")},"Open")',sum(s['status']=='Open' for s in matching)),formula(f'COUNTIFS({tr(source)},{crit},{tr("D")},"Won")',sum(s['status']=='Won' for s in matching)),formula(f'SUMIF({tr(source)},{crit},{tr("Q")})',sum(c['submissionId'] in mids for c in chases)),formula(f'SUMIF({tr(source)},{crit},{tr("R")})',sum(r['submissionId'] in mids and not r['done'] for r in reminders))])
    for name,rows,label in [('Projects',prows,'Highest quote (AUD)'),('Builders',brows,'Submitted value (AUD)')]:
        links={f'A{i}':f"'Tenders'!B{next(j for j,s in lookup.values() if s['project' if name=='Projects' else 'builder']==row[0])}" for i,row in enumerate(rows,6)}
        xml[name]=sheet_xml(name,[name[:-1],'Submissions',label,'Open','TEC wins','Recorded follow-ups','Pending follow-ups'],rows,[54,18,25,14,14,23,23],generated,description,'Project value counts the highest quote per project once. Builder value sums its separate submissions. Click a name to open its first tender.',money_cols=(3,),links=links)
    pvalue=sum(r[2]['value'] for r in prows)
    metrics=[('Submissions',formula(f'COUNTA({tr("A")})',len(tenders))),('Projects',formula(f"COUNTA('Projects'!A6:A{max(6,len(prows)+5)})",len(prows))),('Builders',formula(f"COUNTA('Builders'!A6:A{max(6,len(brows)+5)})",len(brows))),('Recorded follow-ups',formula(f'SUM({tr("Q")})',len(chases))),('Project value (AUD)',formula(f"SUM('Projects'!C6:C{max(6,len(prows)+5)})",pvalue)),('Pending follow-ups',formula(f'SUM({tr("R")})',sum(not r['done'] for r in reminders)))]
    from .tender_export_visuals import dashboard_parts
    visual=dashboard_parts(tenders,metrics,generated,description,tr)
    xml['Summary']=visual.pop('summary')
    output=BytesIO()
    with ZipFile(output,'w',ZIP_DEFLATED) as z:
        overrides=''.join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="{MIME}.worksheet+xml"/>' for i in range(1,7))
        overrides += ''.join(f'<Override PartName="/{part}" ContentType="application/vnd.openxmlformats-officedocument.{"drawingml.chart+xml" if "/charts/" in part else "drawing+xml"}"/>' for part in visual if part.endswith('.xml') and '/_rels/' not in part)
        z.writestr('[Content_Types].xml',f'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="{MIME}.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="{MIME}.styles+xml"/>{overrides}</Types>')
        z.writestr('_rels/.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        sheets=''.join(f'<sheet name="{name}" sheetId="{i}" r:id="rId{i}"/>' for i,name in enumerate(SHEETS,1))
        definitions=''.join(f'<definedName name="_xlnm.Print_Titles" localSheetId="{i}">\'{name}\'!$1:$5</definedName>' for i,name in enumerate(SHEETS))
        z.writestr('xl/workbook.xml',f'<workbook xmlns="{NS}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><bookViews><workbookView/></bookViews><sheets>{sheets}</sheets><definedNames>{definitions}</definedNames><calcPr calcId="191029" fullCalcOnLoad="1" forceFullCalc="1"/></workbook>')
        relationships=''.join(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>' for i in range(1,7))
        z.writestr('xl/_rels/workbook.xml.rels',f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{relationships}<Relationship Id="rId7" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
        z.writestr('xl/styles.xml',styles())
        for part,body in visual.items():z.writestr(part,body)
        for i,name in enumerate(SHEETS,1):z.writestr(f'xl/worksheets/sheet{i}.xml',xml[name])
    return output.getvalue()

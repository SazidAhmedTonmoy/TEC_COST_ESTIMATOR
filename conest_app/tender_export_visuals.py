"""Native Excel dashboard and charts for the application's lightweight exporter."""
from collections import Counter
from xml.sax.saxutils import escape
from .tender_export import NS, cell, col, formula

REL='http://schemas.openxmlformats.org/package/2006/relationships'
OFFICE='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
C='http://schemas.openxmlformats.org/drawingml/2006/chart'
A='http://schemas.openxmlformats.org/drawingml/2006/main'
COLORS={'Open':'D9AA00','Won':'16834A','Lost':'DB3F4B','Closed':'718292','Hold':'A055CC',
        'Awarded':'4D73D8','Unsuccessful':'DB3F4B','In Progress':'D9AA00','Builder Withdrawn':'A055CC','Suspended':'718292',
        'No feedback':'8B9BA7','Competitive':'1BA46F','High':'DB3F4B','Mid-Range':'4D73D8','Lower':'A055CC','Mix':'18AAB5','Not recorded':'718292'}

def chart_xml(labels,values,start):
    c=col(start);v=col(start+2);last=30+len(labels)
    strings=''.join(f'<c:pt idx="{i}"><c:v>{escape(label)}</c:v></c:pt>' for i,label in enumerate(labels))
    numbers=''.join(f'<c:pt idx="{i}"><c:v>{n}</c:v></c:pt>' for i,n in enumerate(values))
    points=''.join(f'<c:dPt><c:idx val="{i}"/><c:spPr><a:solidFill><a:srgbClr val="{COLORS.get(label,"718292")}"/></a:solidFill><a:ln><a:noFill/></a:ln></c:spPr></c:dPt>' for i,label in enumerate(labels))
    return f'''<c:chartSpace xmlns:c="{C}" xmlns:a="{A}"><c:chart><c:autoTitleDeleted val="1"/><c:plotArea><c:layout/><c:doughnutChart><c:varyColors val="1"/><c:ser><c:idx val="0"/><c:order val="0"/>{points}<c:cat><c:strRef><c:f>'Summary'!${c}$31:${c}${last}</c:f><c:strCache><c:ptCount val="{len(labels)}"/>{strings}</c:strCache></c:strRef></c:cat><c:val><c:numRef><c:f>'Summary'!${v}$31:${v}${last}</c:f><c:numCache><c:formatCode>0</c:formatCode><c:ptCount val="{len(values)}"/>{numbers}</c:numCache></c:numRef></c:val></c:ser><c:firstSliceAng val="270"/><c:holeSize val="68"/></c:doughnutChart></c:plotArea><c:plotVisOnly val="1"/><c:dispBlanksAs val="zero"/></c:chart><c:spPr><a:solidFill><a:srgbClr val="FFFFFF"/></a:solidFill><a:ln><a:noFill/></a:ln></c:spPr></c:chartSpace>'''

def dashboard_parts(tenders,metrics,generated,description,tr):
    cells={};merges=[];heights={1:38,2:24,3:34,4:8,5:23,6:40,7:12,8:23,9:40,10:12,11:28,12:27,29:10,30:26}
    def put(r,c,value,style=5):cells[(r,c)]=(value,style)
    def merged(r,c1,c2,value,style):
        merges.append(f'{col(c1)}{r}:{col(c2)}{r}')
        for c in range(c1,c2+1):put(r,c,value if c==c1 else None,style)
    merged(1,1,12,'TEC ConEst | Tender overview',1)
    merged(2,1,12,generated,2);merged(3,1,12,description or 'All submissions',2)
    # Existing metric formulas remain the authoritative links to detail tabs.
    for index,metric in enumerate([metrics[0],metrics[1],metrics[2],metrics[4],metrics[3],metrics[5]]):
        r=5 if index<3 else 8;c=1+(index%3)*4
        merged(r,c,c+3,metric[0],4);merged(r+1,c,c+3,metric[1],18 if index==3 else 17)
    groups=[('TEC submission outcomes','status','D'),('Builder outcomes','builderStatus','E'),('Pricing feedback','pricing','F')]
    pieces={};anchors=[];relationships=[]
    for idx,(title,field,source) in enumerate(groups):
        c=1+idx*4
        merged(11,c,c+3,title,3)
        merged(12,c,c+3,['TEC won = our quote succeeded','Awarded = builder won the project','Feedback on TEC’s quoted price'][idx],2)
        counts=Counter(str(s.get(field) or 'Not recorded') for s in tenders)
        if field=='status': keys=['Open','Won','Lost','Close','Hold']
        else: keys=sorted(counts,key=lambda k:(-counts[k],k)) or ['Not recorded']
        labels=[('Closed' if k=='Close' else 'No feedback' if field=='pricing' and k=='Nil' else k) for k in keys]
        values=[counts[k] for k in keys]
        merged(30,c,c+1,'Category',3);put(30,c+2,'Count',3);put(30,c+3,'Share',3)
        for offset,(key,label,n) in enumerate(zip(keys,labels,values),31):
            style={'Won':19,'Awarded':22,'Open':20,'Competitive':19,'Lost':21,'Unsuccessful':21,'High':21,'Hold':23}.get(key,5)
            merged(offset,c,c+1,label,style)
            criterion='"'+key.replace('"','""').replace('~','~~').replace('*','~*').replace('?','~?')+'"'
            expression=f'COUNTIF({tr(source)},{criterion})'
            if key=='Not recorded': expression=f'COUNTIF({tr(source)},"")+COUNTIF({tr(source)},"Not recorded")'
            put(offset,c+2,formula(expression,n),5)
            put(offset,c+3,formula(f'IF($A$6=0,0,{col(c+2)}{offset}/$A$6)',n/len(tenders) if tenders else 0),26)
        if not tenders:merged(18,c,c+3,'No submissions in this export',2)
        if tenders:
            pieces[f'xl/charts/chart{idx+1}.xml']=chart_xml(labels,values,c)
            anchors.append(f'''<xdr:twoCellAnchor><xdr:from><xdr:col>{c-1}</xdr:col><xdr:colOff>60000</xdr:colOff><xdr:row>13</xdr:row><xdr:rowOff>0</xdr:rowOff></xdr:from><xdr:to><xdr:col>{c+3}</xdr:col><xdr:colOff>0</xdr:colOff><xdr:row>28</xdr:row><xdr:rowOff>0</xdr:rowOff></xdr:to><xdr:graphicFrame macro=""><xdr:nvGraphicFramePr><xdr:cNvPr id="{idx+1}" name="{escape(title)}"/><xdr:cNvGraphicFramePr/></xdr:nvGraphicFramePr><xdr:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/></xdr:xfrm><a:graphic><a:graphicData uri="{C}"><c:chart xmlns:c="{C}" xmlns:r="{OFFICE}" r:id="rId{idx+1}"/></a:graphicData></a:graphic></xdr:graphicFrame><xdr:clientData/></xdr:twoCellAnchor>''')
            relationships.append(f'<Relationship Id="rId{idx+1}" Type="{OFFICE}/chart" Target="../charts/chart{idx+1}.xml"/>')
    end=max(40,max(r for r,c in cells)+2)
    notes=['Project value uses the highest quote per project once. It is not the sum of competing builder submissions.',
           'Open a detail tab below. Filter its header row; submission IDs are retained in hidden columns for reimport.',
           'To update the app: Dashboard > Import Excel. Preview changes before applying; missing records are kept.']
    for r,note in enumerate(notes,end):merged(r,1,12,note,2);heights[r]=28
    rows=''.join(f'<row r="{r}" ht="{heights.get(r,19)}" customHeight="1">'+''.join(cell(f'{col(c)}{r}',*cells[(r,c)]) for c in range(1,13) if (r,c) in cells)+'</row>' for r in range(1,end+3))
    drawing='<drawing r:id="rId1"/>' if anchors else ''
    pieces['summary']=f'''<worksheet xmlns="{NS}" xmlns:r="{OFFICE}"><sheetPr><tabColor rgb="FFD9AA00"/><pageSetUpPr fitToPage="1"/></sheetPr><dimension ref="A1:L{end+2}"/><sheetViews><sheetView showGridLines="0" zoomScale="85" workbookViewId="0"/></sheetViews><sheetFormatPr defaultRowHeight="19"/><cols><col min="1" max="12" width="13" customWidth="1"/></cols><sheetData>{rows}</sheetData><mergeCells count="{len(merges)}">{''.join(f'<mergeCell ref="{m}"/>' for m in merges)}</mergeCells><printOptions horizontalCentered="1"/><pageMargins left="0.3" right="0.3" top="0.3" bottom="0.3" header="0.15" footer="0.15"/><pageSetup paperSize="9" orientation="landscape" fitToWidth="1" fitToHeight="1"/>{drawing}</worksheet>'''
    if anchors:
        pieces['xl/drawings/drawing1.xml']=f'<xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing" xmlns:a="{A}">'+''.join(anchors)+'</xdr:wsDr>'
        pieces['xl/drawings/_rels/drawing1.xml.rels']=f'<Relationships xmlns="{REL}">'+''.join(relationships)+'</Relationships>'
        pieces['xl/worksheets/_rels/sheet1.xml.rels']=f'<Relationships xmlns="{REL}"><Relationship Id="rId1" Type="{OFFICE}/drawing" Target="../drawings/drawing1.xml"/></Relationships>'
    return pieces

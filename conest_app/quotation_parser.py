"""Validated, text-based TLE table extraction with actionable failure messages."""
from __future__ import annotations
import io
import re
from pathlib import Path
from zipfile import BadZipFile, ZipFile

MAX_FILE_BYTES = 30 * 1024 * 1024
MAX_ROWS = 20000


class ImportDependencyError(RuntimeError):
    pass


def parse_content(filename, content):
    if not isinstance(content, bytes) or not content:
        raise ValueError('The quotation file is empty. Choose the original PDF or connected XLSX workbook.')
    if len(content) > MAX_FILE_BYTES:
        raise ValueError('Upload a file smaller than 30 MB')
    suffix = Path(filename).suffix.lower()
    if suffix == '.pdf':
        if b'%PDF-' not in content[:1024]:
            raise ValueError('This file is not a readable PDF. Export the quotation as a PDF and try again.')
        return parse_pdf(content, filename)
    if suffix != '.xlsx':
        raise ValueError('Choose a connected XLSX workbook or a text-based TLE quotation PDF')
    try:
        with ZipFile(io.BytesIO(content)) as archive:
            if sum(info.file_size for info in archive.infolist()) > 150 * 1024 * 1024:
                raise ValueError('This workbook expands beyond the import limit. Split it into smaller workbooks.')
        from .light_prices import parse_xlsx
        quotes, excluded = parse_xlsx(content)
    except (BadZipFile, KeyError, StopIteration, EOFError) as exc:
        raise ValueError('The workbook could not be read. Use a connected XLSX workbook containing an All Items sheet with its column headings.') from exc
    if sum(len(q['lines']) for q in quotes) > MAX_ROWS or len(quotes) > 500:
        raise ValueError('Split the workbook into files with at most 500 quotations and 20,000 price rows')
    return quotes, excluded


def _header(row):
    def key(value):
        return re.sub(r'[^A-Z0-9]', '', str(value or '').upper())
    aliases = {
        'ITEM': 'Item', 'ITEMNO': 'Item', 'TYPE': 'Type', 'SUPPLIER': 'Supplier',
        'QTY': 'Qty', 'QUANTITY': 'Qty', 'CATNO': 'Cat No', 'CATALOGUENO': 'Cat No',
        'DESCRIPTION': 'Description', 'ETA': 'ETA',
        'PEREACHEXCLGST': 'Unit Ex GST', 'PEREACHEXGST': 'Unit Ex GST',
        'UNITEXGST': 'Unit Ex GST', 'UNITEXCLGST': 'Unit Ex GST',
        'TOTALSEXCLGST': 'Total Ex GST', 'TOTALEXCLGST': 'Total Ex GST',
        'TOTALEXGST': 'Total Ex GST', 'TOTALSEXGST': 'Total Ex GST',
    }
    result = {aliases[key(value)]: index for index, value in enumerate(row) if key(value) in aliases}
    needed = {'Item', 'Supplier', 'Qty', 'Cat No', 'Description', 'Unit Ex GST', 'Total Ex GST'}
    return result if needed <= result.keys() else None


def parse_pdf(content, filename):
    try:
        import pdfplumber
        from pdfminer.pdfdocument import PDFPasswordIncorrect
        from pdfminer.pdfparser import PDFSyntaxError
        from pdfminer.psparser import PSEOF, PSSyntaxError
    except ImportError as exc:
        raise ImportDependencyError('PDF import support is missing from the server Python environment. Redeploy the updated requirements.txt; the deployment script installs pdfplumber automatically.') from exc
    try:
        from pdfplumber.utils.exceptions import PdfminerException
    except ImportError:
        class PdfminerException(Exception):
            pass  # Older supported pdfplumber releases expose raw PDF errors.
    from .light_prices import clean, date_text, normal_line, number
    quote = dict(reference='', project='', quote_date='', source=filename, total_ex=None, lines=[])
    excluded = 0
    try:
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            if not pdf.pages:
                raise ValueError('The PDF contains no pages')
            if len(pdf.pages) > 100:
                raise ValueError('Upload a quotation of at most 100 pages')
            first_text = pdf.pages[0].extract_text() or ''
            if not first_text.strip():
                raise ValueError('This PDF is scanned or has no readable text. Use the original text-based quotation PDF, or convert it with OCR before importing.')
            ref = re.search(r'\bREF(?:ERENCE)?\s*[:.]\s*([A-Z0-9][A-Z0-9_./-]*)', first_text, re.I)
            if not ref:
                raise ValueError('No TLE quotation reference was found. Use a TLE quotation PDF or the connected XLSX import template.')
            quote['reference'] = ref[1]
            dat = re.search(r'\bDATE\s*:\s*(.*?)(?:\s+PROJECT\s*:|\n|$)', first_text, re.I)
            quote['quote_date'] = date_text(dat[1]) if dat else ''
            project = re.search(r'\bPROJECT\s*:\s*([^\n]+)', first_text, re.I)
            if project:
                quote['project'] = clean(project[1])
            previous_header, previous_width = None, None
            for page_no, page in enumerate(pdf.pages, 1):
                for table in page.extract_tables():
                    mapping = None
                    for row_no, row in enumerate(table, 1):
                        if not row:
                            continue
                        if clean(row[0]).upper() == 'TO:' and page_no == 1 and len(row) > 3 and not quote['project']:
                            quote['project'] = clean(row[3])
                        detected = _header(row)
                        if detected:
                            mapping, previous_header, previous_width = detected, detected, len(row)
                            continue
                        # Only inherit a header for an explicitly numbered item
                        # on a continuation page. Never guess column positions.
                        if mapping is None and page_no > 1 and previous_header and len(row) == previous_width:
                            if re.fullmatch(r'\d+(?:\.0)?', clean(row[previous_header['Item']])):
                                mapping = previous_header
                        if mapping is None or max(mapping.values()) >= len(row):
                            continue
                        values = {name: row[index] for name, index in mapping.items()}
                        values['PDF Page'] = page_no
                        if not any(clean(values.get(k)) for k in ('Item', 'Type', 'Supplier', 'Qty', 'Cat No', 'Description', 'Unit Ex GST')):
                            if clean(values.get('Total Ex GST')):
                                try:
                                    quote['total_ex'] = number(values['Total Ex GST'])
                                except ValueError:
                                    pass  # A textual footer is not a quotation item.
                            continue
                        if not re.fullmatch(r'\d+(?:\.0)?', clean(values.get('Item'))):
                            # Do not silently drop priced continuation rows.
                            if clean(values.get('Description')) and clean(values.get('Cat No')) and any(clean(values.get(k)) for k in ('Qty', 'Unit Ex GST', 'Total Ex GST')):
                                raise ValueError(f'PDF page {page_no} contains a priced row without an item number. Use the connected XLSX workbook for this layout.')
                            continue
                        try:
                            line = normal_line(values, page_no * 10000 + row_no)
                        except (ValueError, TypeError) as exc:
                            raise ValueError(f'PDF page {page_no}, item {clean(values.get("Item"))}: {exc}. Review that source row before importing.') from exc
                        if line:
                            quote['lines'].append(line)
                            if len(quote['lines']) > MAX_ROWS:
                                raise ValueError('The quotation contains too many price rows; split it into smaller files')
                        else:
                            excluded += 1
                page.close()
            if not quote['lines']:
                raise ValueError('No supported TLE price table was found. Use the original text-based TLE PDF, or a connected XLSX workbook. Scanned and differently formatted supplier PDFs need conversion first.')
            if not quote['project']:
                quote['project'] = quote['reference']
    except PdfminerException as exc:
        underlying = exc.args[0] if exc.args else exc.__context__
        if isinstance(underlying, PDFPasswordIncorrect):
            raise ValueError('This PDF is password-protected. Export an unlocked copy and check it again.') from exc
        raise ValueError('The PDF reader could not read this file reliably. Export a fresh, text-based copy of the supplier quotation and try again.') from exc
    except PDFPasswordIncorrect as exc:
        raise ValueError('This PDF is password-protected. Export an unlocked copy and check it again.') from exc
    except (PDFSyntaxError, PSEOF, PSSyntaxError, OSError, IndexError) as exc:
        raise ValueError('The PDF could not be read reliably. Export a fresh copy from the supplier quotation and try again.') from exc
    return [quote], excluded
